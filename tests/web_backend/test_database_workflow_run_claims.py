from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    WorkflowContext,
    create_workflow_run_parameters,
    seed_workflow_context,
)

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
)

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


VERIFY_INSTALL_SQL = Path(__file__).parents[2] / "database" / "13_verify_install.sql"


def _create_run(
    connection: psycopg.Connection[dict[str, object]],
    context: WorkflowContext,
    *,
    start: bool,
) -> int:
    created = require_row(
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(context, correlation_id=uuid4()),
        ).fetchone()
    )
    workflow_run_id = created["workflow_run_id"]
    assert isinstance(workflow_run_id, int)
    if start:
        _start_run(connection, context, workflow_run_id)
    return workflow_run_id


def _start_run(
    connection: psycopg.Connection[dict[str, object]],
    context: WorkflowContext,
    workflow_run_id: int,
) -> None:
    require_row(
        connection.execute(
            """
            SELECT *
              FROM application.start_workflow_run(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  %s::BIGINT
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                workflow_run_id,
                context.model_revision,
            ),
        ).fetchone()
    )


def _complete_run(
    connection: psycopg.Connection[dict[str, object]],
    context: WorkflowContext,
    workflow_run_id: int,
) -> None:
    require_row(
        connection.execute(
            """
            SELECT *
              FROM application.complete_workflow_run(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  %s::BIGINT,
                  0::INTEGER
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                workflow_run_id,
                context.model_revision,
            ),
        ).fetchone()
    )


def _expire_claim(
    connection: psycopg.Connection[dict[str, object]],
    workflow_run_id: int,
) -> None:
    connection.execute(
        """
        UPDATE application.workflow_run
           SET workflow_run_claimed_time = clock_timestamp() - INTERVAL '3 minutes',
               workflow_run_claim_heartbeat_time =
                   clock_timestamp() - INTERVAL '2 minutes',
               workflow_run_claim_expires_time =
                   clock_timestamp() - INTERVAL '1 minute',
               updated_time = clock_timestamp(),
               updated_by = CURRENT_USER
         WHERE workflow_run_id = %s
        """,
        (workflow_run_id,),
    )


@pytest.mark.asyncio
async def test_worker_repository_uses_the_exact_claim_renew_and_release_contract(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        workflow_run_id = _create_run(connection, context, start=True)

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    repository = DatabaseWorkflowClaimRepository(database=database)
    await database.open()
    try:
        claim = await repository.claim_next(lease_duration_seconds=30)
        assert claim is not None
        assert claim.workflow_run_id == workflow_run_id
        assert claim.tenant_id == context.tenant_id
        assert claim.model_id == context.model_id
        assert claim.model_revision == context.model_revision
        assert claim.principal.entra_tenant_id == context.entra_tenant_id
        assert claim.principal.entra_object_id == context.entra_object_id

        renewed = await repository.renew(
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            lease_duration_seconds=60,
        )
        assert renewed.workflow_run_id == workflow_run_id
        assert renewed.workflow_run_claim_expires_time > renewed.workflow_run_claim_heartbeat_time

        assert await repository.release(
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        _complete_run(connection, context, workflow_run_id)


def test_web_worker_claims_the_oldest_running_run_without_persisting_raw_token(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        oldest_running_id = _create_run(connection, context, start=True)
        newer_running_id = _create_run(connection, context, start=True)
        queued_id = _create_run(connection, context, start=False)

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        with pytest.raises(RaiseException, match="between 1 and 300"):
            connection.execute("SELECT * FROM application.claim_next_workflow_run(0)").fetchone()
        claimed = require_row(
            connection.execute(
                "SELECT * FROM application.claim_next_workflow_run(%s::INTEGER)",
                (30,),
            ).fetchone()
        )

    assert claimed["workflow_run_id"] == oldest_running_id
    assert claimed["tenant_id"] == context.tenant_id
    assert claimed["model_id"] == context.model_id
    assert claimed["model_revision"] == context.model_revision
    assert claimed["model_workflow"] == "conceptual"
    assert claimed["workflow_execution_mode"] == "one_shot"
    assert claimed["actor_principal_type"] == "user"
    assert claimed["actor_entra_tenant_id"] == context.entra_tenant_id
    assert claimed["actor_entra_object_id"] == context.entra_object_id
    assert isinstance(claimed["workflow_run_claim_token"], UUID)
    assert claimed["workflow_run_recovery_count"] == 0

    with web_postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT workflow_run_claim_token_digest,
                       workflow_run_claimed_time,
                       workflow_run_claim_heartbeat_time,
                       workflow_run_claim_expires_time
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (oldest_running_id,),
            ).fetchone()
        )
        column_names = {
            row["column_name"]
            for row in connection.execute(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'application'
                   AND table_name = 'workflow_run'
                """
            ).fetchall()
        }
        states = {
            row["workflow_run_id"]: row["workflow_run_state"]
            for row in connection.execute(
                """
                SELECT workflow_run_id, workflow_run_state
                  FROM application.workflow_run
                 WHERE workflow_run_id = ANY(%s)
                """,
                ([oldest_running_id, newer_running_id, queued_id],),
            ).fetchall()
        }

    assert isinstance(stored["workflow_run_claim_token_digest"], str)
    assert len(stored["workflow_run_claim_token_digest"]) == 64
    assert stored["workflow_run_claimed_time"] is not None
    assert stored["workflow_run_claim_heartbeat_time"] is not None
    assert stored["workflow_run_claim_expires_time"] is not None
    assert "workflow_run_claim_token" not in column_names
    assert states == {
        oldest_running_id: "running",
        newer_running_id: "running",
        queued_id: "queued",
    }

    with web_postgres_database.connect_owner() as connection:
        _complete_run(connection, context, oldest_running_id)
        _complete_run(connection, context, newer_running_id)
        _start_run(connection, context, queued_id)
        _complete_run(connection, context, queued_id)


def test_claim_rejects_inactive_actor_or_exact_identity(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        workflow_run_id = _create_run(connection, context, start=True)
        actor_identity_id = require_row(
            connection.execute(
                """
                SELECT actor_entra_principal_identity_id
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        )["actor_entra_principal_identity_id"]
        connection.execute(
            """
            UPDATE security.entra_principal_identity
               SET is_active = FALSE
             WHERE entra_principal_identity_id = %s
            """,
            (actor_identity_id,),
        )

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as worker:
        worker.execute("SET ROLE gds_web_write")
        assert (
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
            is None
        )

        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE security.entra_principal_identity
                   SET is_active = TRUE
                 WHERE entra_principal_identity_id = %s
                """,
                (actor_identity_id,),
            )
            connection.execute(
                """
                UPDATE security.principal
                   SET is_active = FALSE
                 WHERE principal_id = %s
                """,
                (context.principal_id,),
            )

        assert (
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
            is None
        )

        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE security.principal
                   SET is_active = TRUE
                 WHERE principal_id = %s
                """,
                (context.principal_id,),
            )

        claimed = require_row(
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
        )
        assert claimed["workflow_run_id"] == workflow_run_id
        assert claimed["actor_principal_type"] == "user"
        assert claimed["actor_entra_tenant_id"] == context.entra_tenant_id
        assert claimed["actor_entra_object_id"] == context.entra_object_id
        claim_token = claimed["workflow_run_claim_token"]
        assert isinstance(claim_token, UUID)
        worker.execute(
            """
            SELECT application.release_workflow_run_claim(
                %s::BIGINT, %s::UUID
            )
            """,
            (workflow_run_id, claim_token),
        )

    with web_postgres_database.connect_owner() as connection:
        _complete_run(connection, context, workflow_run_id)


def test_nullable_actor_identity_requires_one_unambiguous_active_identity(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    second_entra_tenant_id = uuid4()
    second_entra_object_id = uuid4()
    with web_postgres_database.connect_owner() as connection:
        second_identity_id = require_row(
            connection.execute(
                """
                INSERT INTO security.entra_principal_identity (
                    principal_id,
                    principal_type,
                    entra_tenant_id,
                    entra_object_id
                ) VALUES (%s, 'user', %s, %s)
                RETURNING entra_principal_identity_id
                """,
                (
                    context.principal_id,
                    second_entra_tenant_id,
                    second_entra_object_id,
                ),
            ).fetchone()
        )["entra_principal_identity_id"]
        workflow_run_id = require_row(
            connection.execute(
                """
                INSERT INTO application.workflow_run (
                    model_id,
                    model_revision,
                    model_workflow,
                    actor_principal_id,
                    actor_entra_principal_identity_id,
                    selected_scope_digest,
                    selected_scope_count,
                    workflow_run_state,
                    correlation_id,
                    started_time
                ) VALUES (
                    %s,
                    %s,
                    'profiling',
                    %s,
                    NULL,
                    repeat('0', 64),
                    1,
                    'running',
                    %s,
                    CURRENT_TIMESTAMP
                )
                RETURNING workflow_run_id
                """,
                (
                    context.model_id,
                    context.model_revision,
                    context.principal_id,
                    uuid4(),
                ),
            ).fetchone()
        )["workflow_run_id"]

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as worker:
        worker.execute("SET ROLE gds_web_write")
        assert (
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
            is None
        )

        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE security.entra_principal_identity
                   SET is_active = FALSE
                 WHERE entra_principal_identity_id = %s
                """,
                (second_identity_id,),
            )

        claimed = require_row(
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
        )
        assert claimed["workflow_run_id"] == workflow_run_id
        assert claimed["tenant_id"] == context.tenant_id
        assert claimed["workflow_execution_mode"] is None
        assert claimed["actor_principal_type"] == "user"
        assert claimed["actor_entra_tenant_id"] == context.entra_tenant_id
        assert claimed["actor_entra_object_id"] == context.entra_object_id
        claim_token = claimed["workflow_run_claim_token"]
        assert isinstance(claim_token, UUID)
        worker.execute(
            """
            SELECT application.release_workflow_run_claim(
                %s::BIGINT, %s::UUID
            )
            """,
            (workflow_run_id, claim_token),
        )

    with web_postgres_database.connect_owner() as connection:
        _complete_run(connection, context, workflow_run_id)


def test_terminal_and_queued_runs_are_not_claimable(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        terminal_id = _create_run(connection, context, start=True)
        queued_id = _create_run(connection, context, start=False)

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        claimed = require_row(
            connection.execute(
                "SELECT * FROM application.claim_next_workflow_run(30)",
            ).fetchone()
        )
    assert claimed["workflow_run_id"] == terminal_id

    with web_postgres_database.connect_owner() as connection:
        _complete_run(connection, context, terminal_id)
        terminal = require_row(
            connection.execute(
                """
                SELECT workflow_run_state,
                       workflow_run_claim_token_digest,
                       workflow_run_claimed_time,
                       workflow_run_claim_heartbeat_time,
                       workflow_run_claim_expires_time
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (terminal_id,),
            ).fetchone()
        )

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        no_claim = connection.execute(
            "SELECT * FROM application.claim_next_workflow_run(30)"
        ).fetchone()

    assert terminal == {
        "workflow_run_state": "completed",
        "workflow_run_claim_token_digest": None,
        "workflow_run_claimed_time": None,
        "workflow_run_claim_heartbeat_time": None,
        "workflow_run_claim_expires_time": None,
    }
    assert no_claim is None
    assert queued_id > 0


def test_claim_renewal_and_release_require_the_exact_token(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        workflow_run_id = _create_run(connection, context, start=True)

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        claimed = require_row(
            connection.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
        )
        claim_token = claimed["workflow_run_claim_token"]
        assert isinstance(claim_token, UUID)

        with pytest.raises(RaiseException, match="claim is unavailable"):
            connection.execute(
                """
                SELECT *
                  FROM application.renew_workflow_run_claim(
                      %s::BIGINT, %s::UUID, 60
                  )
                """,
                (workflow_run_id, uuid4()),
            ).fetchone()

        renewed = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.renew_workflow_run_claim(
                      %s::BIGINT, %s::UUID, 60
                  )
                """,
                (workflow_run_id, claim_token),
            ).fetchone()
        )
        assert renewed["workflow_run_id"] == workflow_run_id
        renewed_expiry = renewed["workflow_run_claim_expires_time"]
        claimed_expiry = claimed["workflow_run_claim_expires_time"]
        assert isinstance(renewed_expiry, datetime)
        assert isinstance(claimed_expiry, datetime)
        assert renewed_expiry > claimed_expiry

        with pytest.raises(RaiseException, match="between 1 and 300"):
            connection.execute(
                """
                SELECT *
                  FROM application.renew_workflow_run_claim(
                      %s::BIGINT, %s::UUID, 301
                  )
                """,
                (workflow_run_id, claim_token),
            ).fetchone()

        with pytest.raises(RaiseException, match="claim is unavailable"):
            connection.execute(
                """
                SELECT application.release_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                )
                """,
                (workflow_run_id, uuid4()),
            ).fetchone()

        released = require_row(
            connection.execute(
                """
                SELECT application.release_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                ) AS released
                """,
                (workflow_run_id, claim_token),
            ).fetchone()
        )
        assert released == {"released": True}

        with pytest.raises(RaiseException, match="claim is unavailable"):
            connection.execute(
                """
                SELECT application.release_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                )
                """,
                (workflow_run_id, claim_token),
            ).fetchone()

    with web_postgres_database.connect_owner() as connection:
        released_run = require_row(
            connection.execute(
                """
                SELECT workflow_run_claim_token_digest,
                       workflow_run_claimed_time,
                       workflow_run_claim_heartbeat_time,
                       workflow_run_claim_expires_time,
                       workflow_run_recovery_count
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        )
        _complete_run(connection, context, workflow_run_id)

    assert released_run == {
        "workflow_run_claim_token_digest": None,
        "workflow_run_claimed_time": None,
        "workflow_run_claim_heartbeat_time": None,
        "workflow_run_claim_expires_time": None,
        "workflow_run_recovery_count": 0,
    }


def test_expired_claim_recovery_is_bounded_and_fenced_by_the_rotated_token(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        workflow_run_id = _create_run(connection, context, start=True)

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as worker:
        worker.execute("SET ROLE gds_web_write")
        first = require_row(
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
        )
        current_token = first["workflow_run_claim_token"]
        assert isinstance(current_token, UUID)

        for expected_recovery_count in range(1, 6):
            with web_postgres_database.connect_owner() as owner:
                _expire_claim(owner, workflow_run_id)

            with pytest.raises(RaiseException, match="claim is unavailable"):
                worker.execute(
                    """
                    SELECT application.assert_workflow_run_claim(
                        %s::BIGINT, %s::UUID
                    )
                    """,
                    (workflow_run_id, current_token),
                ).fetchone()
            with pytest.raises(RaiseException, match="claim is unavailable"):
                worker.execute(
                    """
                    SELECT *
                      FROM application.renew_workflow_run_claim(
                          %s::BIGINT, %s::UUID, 30
                      )
                    """,
                    (workflow_run_id, current_token),
                ).fetchone()

            recovered = require_row(
                worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
            )
            rotated_token = recovered["workflow_run_claim_token"]
            assert isinstance(rotated_token, UUID)
            assert rotated_token != current_token
            assert recovered["workflow_run_recovery_count"] == expected_recovery_count

            with pytest.raises(RaiseException, match="claim is unavailable"):
                worker.execute(
                    """
                    SELECT application.assert_workflow_run_claim(
                        %s::BIGINT, %s::UUID
                    )
                    """,
                    (workflow_run_id, current_token),
                ).fetchone()
            worker.execute(
                """
                SELECT application.assert_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                )
                """,
                (workflow_run_id, rotated_token),
            ).fetchone()
            current_token = rotated_token

        with web_postgres_database.connect_owner() as owner:
            _expire_claim(owner, workflow_run_id)

        assert (
            worker.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
            is None
        )
        with pytest.raises(RaiseException, match="claim is unavailable"):
            worker.execute(
                """
                SELECT application.assert_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                )
                """,
                (workflow_run_id, current_token),
            ).fetchone()

    with web_postgres_database.connect_owner() as connection:
        exhausted = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       run.failure_code,
                       run.failure_message,
                       run.completed_time,
                       run.workflow_run_claim_token_digest,
                       run.workflow_run_claimed_time,
                       run.workflow_run_claim_heartbeat_time,
                       run.workflow_run_claim_expires_time,
                       count(event.model_event_log_id)::INTEGER AS failed_events
                  FROM application.workflow_run AS run
                  LEFT JOIN model.model_event_log AS event
                    ON event.workflow_run_id = run.workflow_run_id
                   AND event.model_event_log_stage = 'workflow_run'
                   AND event.model_event_log_status = 'failed'
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_id
                """,
                (workflow_run_id,),
            ).fetchone()
        )

    assert exhausted == {
        "workflow_run_state": "failed",
        "failure_code": "workflow_run_recovery_exhausted",
        "failure_message": "Workflow Run recovery limit exhausted.",
        "completed_time": exhausted["completed_time"],
        "workflow_run_claim_token_digest": None,
        "workflow_run_claimed_time": None,
        "workflow_run_claim_heartbeat_time": None,
        "workflow_run_claim_expires_time": None,
        "failed_events": 1,
    }
    assert exhausted["completed_time"] is not None


def test_concurrent_workers_cannot_claim_the_same_run(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        workflow_run_id = _create_run(connection, context, start=True)

    barrier = Barrier(2)

    def claim() -> dict[str, object] | None:
        with psycopg.Connection[dict[str, object]].connect(
            web_postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
            autocommit=True,
        ) as connection:
            connection.execute("SET ROLE gds_web_write")
            barrier.wait(timeout=5)
            return connection.execute(
                "SELECT * FROM application.claim_next_workflow_run(30)"
            ).fetchone()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(claim) for _worker_index in range(2))
        results = tuple(future.result() for future in futures)

    claims = [result for result in results if result is not None]
    assert len(claims) == 1
    assert claims[0]["workflow_run_id"] == workflow_run_id
    claim_token = claims[0]["workflow_run_claim_token"]
    assert isinstance(claim_token, UUID)

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            """
            SELECT application.release_workflow_run_claim(
                %s::BIGINT, %s::UUID
            )
            """,
            (workflow_run_id, claim_token),
        ).fetchone()

    with web_postgres_database.connect_owner() as connection:
        _complete_run(connection, context, workflow_run_id)


def test_only_the_web_runtime_can_execute_governed_claim_functions(
    web_postgres_database: DisposablePostgres,
) -> None:
    signatures = (
        "application.claim_next_workflow_run(integer)",
        "application.renew_workflow_run_claim(bigint,uuid,integer)",
        "application.release_workflow_run_claim(bigint,uuid)",
        "application.assert_workflow_run_claim(bigint,uuid)",
    )
    with web_postgres_database.connect_owner() as connection:
        privileges = connection.execute(
            """
            SELECT signature,
                   has_function_privilege(
                       'gds_web_write', signature, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', signature, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public', signature, 'EXECUTE'
                   ) AS public_can_execute
              FROM unnest(%s::TEXT[]) AS function_record(signature)
             ORDER BY signature
            """,
            (list(signatures),),
        ).fetchall()
        table_privileges = require_row(
            connection.execute(
                """
                SELECT has_table_privilege(
                           'gds_web_write',
                           'application.workflow_run',
                           'UPDATE'
                       ) AS web_can_update,
                       has_table_privilege(
                           'gds_app_write',
                           'application.workflow_run',
                           'SELECT,INSERT,UPDATE,DELETE'
                       ) AS mcp_has_table_access
                """
            ).fetchone()
        )

    assert privileges == [
        {
            "signature": signature,
            "web_can_execute": True,
            "mcp_can_execute": False,
            "public_can_execute": False,
        }
        for signature in sorted(signatures)
    ]
    assert table_privileges == {
        "web_can_update": False,
        "mcp_has_table_access": False,
    }

    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        with pytest.raises(InsufficientPrivilege):
            connection.execute(
                """
                UPDATE application.workflow_run
                   SET workflow_run_recovery_count = workflow_run_recovery_count
                """
            )


def test_install_verifier_rejects_broad_run_dml_and_public_claim_execute(
    web_postgres_database: DisposablePostgres,
) -> None:
    verify_install_sql = cast(
        LiteralString,
        VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
    )
    with (
        web_postgres_database.connect_owner() as connection,
        pytest.raises(
            RaiseException,
            match="application runtime table privileges",
        ),
        connection.transaction(),
    ):
        connection.execute("GRANT UPDATE ON application.workflow_run TO gds_web_write")
        connection.execute(verify_install_sql)

    with (
        web_postgres_database.connect_owner() as connection,
        pytest.raises(
            RaiseException,
            match="application private function privileges",
        ),
        connection.transaction(),
    ):
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION application.claim_next_workflow_run(
                INTEGER
            ) TO PUBLIC
            """
        )
        connection.execute(verify_install_sql)
