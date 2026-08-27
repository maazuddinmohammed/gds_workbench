from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import UUID, uuid4

import pytest
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.types.json import Jsonb

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_notebook_workflows import (
    NotebookActor,
    _create_notebook_profiling_run,
    _seed_notebook_tenant,
    _start_and_claim,
)
from tests.mcp.test_database_profiling_persistence import (
    _create_run,
    _profile,
    _seed_attributes,
    _source_context_digests,
)
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    seed_workflow_context,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


VERIFY_INSTALL_SQL = Path(__file__).parents[2] / "database" / "13_verify_install.sql"

GET_CONTEXT_SQL = """
SELECT *
  FROM application.get_notebook_profiling_execution_context(
      %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::UUID
  )
"""

GET_CONNECTION_VALUES_SQL = """
SELECT *
  FROM application.get_notebook_profiling_connection_values(
      %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::UUID
  )
"""

APPEND_EVENT_SQL = """
SELECT *
  FROM application.append_notebook_profiling_event(
      %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::UUID,
      %s::BIGINT, %s::VARCHAR, %s::VARCHAR, %s::VARCHAR,
      %s::INTEGER, %s::INTEGER, %s::INTEGER
  )
"""

COMMIT_SQL = """
SELECT *
  FROM application.persist_and_complete_notebook_profiling_run(
      %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::UUID,
      %s::JSONB
  )
"""

FAIL_SQL = """
SELECT *
  FROM application.fail_notebook_profiling_run(
      %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::UUID,
      %s::VARCHAR, %s::VARCHAR
  )
"""


@pytest.fixture(scope="module")
def notebook_actor(
    bootstrap_postgres_database: DisposablePostgres,
) -> NotebookActor:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with bootstrap_postgres_database.connect_owner() as connection:
        principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    service_principal_application_id,
                    service_principal_type,
                    is_super_admin
                ) VALUES (
                    'service_principal',
                    'Notebook Profiling Runtime',
                    %s,
                    'application',
                    TRUE
                )
                RETURNING principal_id
                """,
                (uuid4(),),
            ).fetchone()
        )["principal_id"]
        identity_id = require_row(
            connection.execute(
                """
                INSERT INTO security.entra_principal_identity (
                    principal_id,
                    principal_type,
                    entra_tenant_id,
                    entra_object_id
                ) VALUES (%s, 'service_principal', %s, %s)
                RETURNING entra_principal_identity_id
                """,
                (principal_id, entra_tenant_id, entra_object_id),
            ).fetchone()
        )["entra_principal_identity_id"]
        runtime_role = require_row(
            connection.execute(
                """
                SELECT oid, rolname
                  FROM pg_catalog.pg_roles
                 WHERE rolname = 'gds_notebook_runtime'
                """
            ).fetchone()
        )
        connection.execute(
            """
            INSERT INTO security.notebook_runtime_principal (
                database_role_oid,
                database_role_name,
                entra_principal_identity_id,
                principal_id,
                principal_type,
                databricks_environment_code
            ) VALUES (%s, %s, %s, %s, 'service_principal', 'TEST')
            """,
            (
                runtime_role["oid"],
                runtime_role["rolname"],
                identity_id,
                principal_id,
            ),
        )
    return NotebookActor(
        database=bootstrap_postgres_database,
        principal_id=principal_id,
        entra_principal_identity_id=identity_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )


@dataclass(frozen=True, slots=True)
class NotebookProfilingSeed:
    actor: NotebookActor
    context: WorkflowContext
    workflow_run_id: int
    claim_token: UUID
    connection_id: int
    attributes: tuple[tuple[int, int], ...]
    server_hostname: str = field(repr=False)
    http_path: str = field(repr=False)
    access_token: str = field(repr=False)


def _seed_notebook_profiling(actor: NotebookActor) -> NotebookProfilingSeed:
    context = _seed_notebook_tenant(actor)
    attributes = _seed_attributes(actor.database, context)
    server_hostname = f"{uuid4().hex}.example.invalid"
    http_path = f"/sql/1.0/warehouses/{uuid4()}"
    access_token = uuid4().hex

    with actor.database.connect_owner() as connection:
        object_row = require_row(
            connection.execute(
                """
                SELECT object_record.connection_id,
                       object_record.zone_id,
                       object_record.object_schema
                  FROM core.object AS object_record
                 WHERE object_record.object_id = %s
                """,
                (context.selected_object_ids[0],),
            ).fetchone()
        )
        connection_id = int(object_row["connection_id"])
        connection.execute(
            """
            UPDATE core.connection
               SET is_global_data_store = TRUE
             WHERE connection_id = %s
            """,
            (connection_id,),
        )
        connection.execute(
            """
            INSERT INTO core.tenant_metadata_discovery_scope (
                tenant_id,
                gds_connection_id,
                zone_id,
                object_schema
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                context.tenant_id,
                connection_id,
                object_row["zone_id"],
                object_row["object_schema"],
            ),
        )
        for object_id, attribute_id in attributes:
            connection.execute(
                """
                UPDATE core.object AS object_record
                   SET batch_attribute_name = attribute.attribute_name
                  FROM core.attribute AS attribute
                 WHERE object_record.object_id = %s
                   AND attribute.attribute_id = %s
                   AND attribute.object_id = object_record.object_id
                """,
                (object_id, attribute_id),
            )

        environment_row = connection.execute(
            """
            SELECT environment_id
              FROM reference.environment
             WHERE lower(btrim(environment_code)) = 'test'
            """
        ).fetchone()
        if environment_row is None:
            environment_row = require_row(
                connection.execute(
                    """
                    INSERT INTO reference.environment (
                        environment_code,
                        environment_name
                    ) VALUES ('TEST', 'Notebook test')
                    RETURNING environment_id
                    """
                ).fetchone()
            )
        environment_id = int(environment_row["environment_id"])
        connection.execute(
            """
            INSERT INTO reference.connection_parameter (
                connection_parameter_code,
                connection_parameter_name
            ) VALUES
                ('databricks_host_name', 'Databricks Host Name'),
                ('databricks_http_path', 'Databricks HTTP Path'),
                ('databricks_token', 'Databricks Token')
            ON CONFLICT DO NOTHING
            """
        )
        parameter_rows = connection.execute(
            """
            SELECT connection_parameter_id, connection_parameter_code
              FROM reference.connection_parameter
             WHERE lower(btrim(connection_parameter_code)) IN (
                       'databricks_host_name',
                       'databricks_http_path',
                       'databricks_token'
                   )
            """
        ).fetchall()
        parameter_ids = {
            str(row["connection_parameter_code"]).strip().lower(): int(
                row["connection_parameter_id"]
            )
            for row in parameter_rows
        }
        connection.execute(
            """
            INSERT INTO core.connection_value (
                environment_id,
                connection_id,
                connection_parameter_id,
                connection_value
            ) VALUES
                (%s, %s, %s, %s),
                (%s, %s, %s, %s),
                (%s, %s, %s, %s)
            """,
            (
                environment_id,
                connection_id,
                parameter_ids["databricks_host_name"],
                server_hostname,
                environment_id,
                connection_id,
                parameter_ids["databricks_http_path"],
                http_path,
                environment_id,
                connection_id,
                parameter_ids["databricks_token"],
                access_token,
            ),
        )

    created = _create_notebook_profiling_run(actor, context)
    workflow_run_id = int(created["workflow_run_id"])
    claimed = require_row(_start_and_claim(actor, context, workflow_run_id))
    claim_token = claimed["workflow_run_claim_token"]
    assert isinstance(claim_token, UUID)
    return NotebookProfilingSeed(
        actor=actor,
        context=context,
        workflow_run_id=workflow_run_id,
        claim_token=claim_token,
        connection_id=connection_id,
        attributes=attributes,
        server_hostname=server_hostname,
        http_path=http_path,
        access_token=access_token,
    )


def _claim_parameters(seed: NotebookProfilingSeed) -> tuple[object, ...]:
    return (
        seed.context.tenant_id,
        seed.context.model_id,
        seed.workflow_run_id,
        seed.context.model_revision,
        seed.claim_token,
    )


def _profiles(seed: NotebookProfilingSeed) -> list[dict[str, object]]:
    digests = _source_context_digests(
        seed.actor.database,
        seed.context,
        seed.workflow_run_id,
    )
    return [
        _profile(
            object_id,
            attribute_id,
            source_context_digest=digests[attribute_id],
        )
        for object_id, attribute_id in seed.attributes
    ]


def test_notebook_profiling_reads_exact_claimed_context_and_bound_environment(
    notebook_actor: NotebookActor,
) -> None:
    seed = _seed_notebook_profiling(notebook_actor)

    with notebook_actor.database.connect_notebook_runtime() as connection:
        context_rows = connection.execute(
            GET_CONTEXT_SQL,
            _claim_parameters(seed),
        ).fetchall()
        connection_rows = connection.execute(
            GET_CONNECTION_VALUES_SQL,
            _claim_parameters(seed),
        ).fetchall()

    assert [
        (row["object_id"], row["attribute_id"]) for row in context_rows
    ] == list(seed.attributes)
    assert len(connection_rows) == 1
    assert connection_rows[0]["gds_connection_id"] == seed.connection_id
    assert connection_rows[0]["environment_code"] == "TEST"
    assert connection_rows[0]["failure_code"] is None
    assert connection_rows[0]["databricks_host_name"] == seed.server_hostname
    assert connection_rows[0]["databricks_http_path"] == seed.http_path
    assert connection_rows[0]["databricks_token"] == seed.access_token

    with notebook_actor.database.connect_notebook_runtime() as connection:
        for parameters in (
            (
                seed.context.tenant_id + 1,
                seed.context.model_id,
                seed.workflow_run_id,
                seed.context.model_revision,
                seed.claim_token,
            ),
            (*_claim_parameters(seed)[:-1], uuid4()),
        ):
            with (
                pytest.raises(
                    RaiseException,
                    match="Notebook Profiling Run is unavailable|claim is unavailable",
                ),
                connection.transaction(),
            ):
                connection.execute(GET_CONTEXT_SQL, parameters).fetchall()

    with notebook_actor.database.connect_notebook_runtime() as connection:
        released = require_row(
            connection.execute(
            """
            SELECT released, denial_code
              FROM security.release_notebook_tenant_lock(%s::BIGINT)
            """,
            (seed.context.tenant_id,),
            ).fetchone()
        )
    assert released == {"released": True, "denial_code": None}
    with (
        notebook_actor.database.connect_notebook_runtime() as connection,
        pytest.raises(RaiseException, match="tenant_lock_required"),
    ):
        connection.execute(GET_CONTEXT_SQL, _claim_parameters(seed)).fetchall()


def test_notebook_profiling_rejects_other_owner_and_other_workflow(
    notebook_actor: NotebookActor,
) -> None:
    user_context = seed_workflow_context(notebook_actor.database)
    user_run_id = _create_run(notebook_actor.database, user_context)
    user_claim_token = uuid4()
    with notebook_actor.database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE application.workflow_run
               SET workflow_run_claim_token_digest = encode(
                       sha256(convert_to(%s::UUID::TEXT, 'UTF8')),
                       'hex'
                   ),
                   workflow_run_claimed_time = clock_timestamp(),
                   workflow_run_claim_heartbeat_time = clock_timestamp(),
                   workflow_run_claim_expires_time =
                       clock_timestamp() + INTERVAL '5 minutes'
             WHERE workflow_run_id = %s
            """,
            (user_claim_token, user_run_id),
        )
    with (
        notebook_actor.database.connect_notebook_runtime() as connection,
        pytest.raises(RaiseException, match="Notebook Profiling Run is unavailable"),
    ):
        connection.execute(
            GET_CONTEXT_SQL,
            (
                user_context.tenant_id,
                user_context.model_id,
                user_run_id,
                user_context.model_revision,
                user_claim_token,
            ),
        ).fetchall()

    context = _seed_notebook_tenant(notebook_actor)
    with notebook_actor.database.connect_notebook_runtime() as connection:
        created = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.create_notebook_workflow_run(
                      %s::BIGINT, %s::BIGINT, %s::BIGINT,
                      'analysis'::VARCHAR, NULL::VARCHAR,
                      NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
                      NULL::VARCHAR, NULL::INTEGER, NULL::INTEGER,
                      %s::BIGINT[], NULL::VARCHAR, NULL::VARCHAR,
                      %s::UUID, '{}'::JSONB
                  )
                """,
                (
                    context.tenant_id,
                    context.model_id,
                    context.model_revision,
                    list(context.selected_object_ids),
                    uuid4(),
                ),
            ).fetchone()
        )
        claimed = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.start_and_claim_notebook_workflow_run(
                      %s::BIGINT, %s::BIGINT, %s::BIGINT, %s::BIGINT,
                      'analysis'::VARCHAR, 30::INTEGER
                  )
                """,
                (
                    context.tenant_id,
                    context.model_id,
                    created["workflow_run_id"],
                    context.model_revision,
                ),
            ).fetchone()
        )
        with (
            pytest.raises(
                RaiseException,
                match="Notebook Profiling Run is unavailable",
            ),
            connection.transaction(),
        ):
            connection.execute(
                GET_CONTEXT_SQL,
                (
                    context.tenant_id,
                    context.model_id,
                    created["workflow_run_id"],
                    context.model_revision,
                    claimed["workflow_run_claim_token"],
                ),
            ).fetchall()


def test_notebook_profiling_event_is_exact_claim_fenced_and_idempotent(
    notebook_actor: NotebookActor,
) -> None:
    seed = _seed_notebook_profiling(notebook_actor)
    event_parameters = (
        *_claim_parameters(seed),
        2,
        "profiling.read",
        "running",
        "Profiling selected attributes.",
        1,
        3,
        0,
    )

    with notebook_actor.database.connect_notebook_runtime() as connection:
        appended = require_row(
            connection.execute(APPEND_EVENT_SQL, event_parameters).fetchone()
        )
        replayed = require_row(
            connection.execute(APPEND_EVENT_SQL, event_parameters).fetchone()
        )
        with (
            pytest.raises(RaiseException, match="event sequence conflict"),
            connection.transaction(),
        ):
            connection.execute(
                APPEND_EVENT_SQL,
                (*event_parameters[:8], "Different safe message.", *event_parameters[9:]),
            ).fetchone()
        with (
            pytest.raises(RaiseException, match="claim is unavailable"),
            connection.transaction(),
        ):
            connection.execute(
                APPEND_EVENT_SQL,
                (*event_parameters[:4], uuid4(), *event_parameters[5:]),
            ).fetchone()

    assert appended["model_event_log_id"] == replayed["model_event_log_id"]
    assert appended["event_attempt"] == 1
    assert appended["percent_complete"] == Decimal("33.33")


def test_notebook_profiling_commit_rolls_back_then_retries_and_completes(
    notebook_actor: NotebookActor,
) -> None:
    seed = _seed_notebook_profiling(notebook_actor)
    profiles = _profiles(seed)
    invalid_profiles = [dict(profile) for profile in profiles]
    invalid_profiles[0]["source_context_digest"] = "0" * 64

    with notebook_actor.database.connect_notebook_runtime() as connection:
        with (
            pytest.raises(RaiseException, match="source context has changed"),
            connection.transaction(),
        ):
            connection.execute(
                COMMIT_SQL,
                (*_claim_parameters(seed), Jsonb(invalid_profiles)),
            ).fetchone()

    with notebook_actor.database.connect_owner() as connection:
        unchanged = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       target_model.model_revision,
                       count(profile.attribute_id)::INTEGER AS profile_count,
                       run.workflow_run_claim_token_digest IS NOT NULL AS claimed
                  FROM application.workflow_run AS run
                  JOIN model.model AS target_model
                    ON target_model.model_id = run.model_id
                  LEFT JOIN workflow.attribute_profile AS profile
                    ON profile.model_id = run.model_id
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_id, target_model.model_id
                """,
                (seed.workflow_run_id,),
            ).fetchone()
        )
    assert unchanged == {
        "workflow_run_state": "running",
        "model_revision": seed.context.model_revision,
        "profile_count": 0,
        "claimed": True,
    }

    with notebook_actor.database.connect_notebook_runtime() as connection:
        committed = require_row(
            connection.execute(
                COMMIT_SQL,
                (*_claim_parameters(seed), Jsonb(profiles)),
            ).fetchone()
        )

    assert committed["changed"] is True
    assert committed["workflow_run_id"] == seed.workflow_run_id
    assert committed["model_revision"] == seed.context.model_revision + 1
    assert committed["submitted_profile_count"] == len(profiles)
    assert committed["changed_profile_count"] == len(profiles)
    assert committed["workflow_run_state"] == "completed"

    with notebook_actor.database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       run.workflow_run_claim_token_digest,
                       count(profile.attribute_id)::INTEGER AS profile_count,
                       count(*) FILTER (
                           WHERE profile.workflow_run_id = run.workflow_run_id
                       )::INTEGER AS run_profile_count
                  FROM application.workflow_run AS run
                  LEFT JOIN workflow.attribute_profile AS profile
                    ON profile.model_id = run.model_id
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_id
                """,
                (seed.workflow_run_id,),
            ).fetchone()
        )
    assert stored == {
        "workflow_run_state": "completed",
        "workflow_run_claim_token_digest": None,
        "profile_count": len(profiles),
        "run_profile_count": len(profiles),
    }


def test_notebook_profiling_fail_is_exact_claim_fenced(
    notebook_actor: NotebookActor,
) -> None:
    seed = _seed_notebook_profiling(notebook_actor)
    failure_parameters = (
        *_claim_parameters(seed),
        "notebook_profiling_failed",
        "Notebook Profiling execution failed safely.",
    )

    with notebook_actor.database.connect_notebook_runtime() as connection:
        with (
            pytest.raises(RaiseException, match="claim is unavailable"),
            connection.transaction(),
        ):
            connection.execute(
                FAIL_SQL,
                (*failure_parameters[:4], uuid4(), *failure_parameters[5:]),
            ).fetchone()
        failed = require_row(
            connection.execute(FAIL_SQL, failure_parameters).fetchone()
        )

    assert failed["changed"] is True
    assert failed["workflow_run_state"] == "failed"
    with notebook_actor.database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT run.failure_code,
                       run.failure_message,
                       run.workflow_run_claim_token_digest,
                       count(event.model_event_log_id) FILTER (
                           WHERE event.model_event_log_status = 'failed'
                       )::INTEGER AS failed_event_count
                  FROM application.workflow_run AS run
                  LEFT JOIN model.model_event_log AS event
                    ON event.workflow_run_id = run.workflow_run_id
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_id
                """,
                (seed.workflow_run_id,),
            ).fetchone()
        )
    assert stored == {
        "failure_code": "notebook_profiling_failed",
        "failure_message": "Notebook Profiling execution failed safely.",
        "workflow_run_claim_token_digest": None,
        "failed_event_count": 1,
    }


def test_notebook_profiling_acl_is_wrapper_only_and_verified(
    notebook_actor: NotebookActor,
) -> None:
    allowed = (
        "application.append_notebook_profiling_event(bigint,bigint,bigint,bigint,uuid,bigint,character varying,character varying,character varying,integer,integer,integer)",
        "application.fail_notebook_profiling_run(bigint,bigint,bigint,bigint,uuid,character varying,character varying)",
        "application.get_notebook_profiling_connection_values(bigint,bigint,bigint,bigint,uuid)",
        "application.get_notebook_profiling_execution_context(bigint,bigint,bigint,bigint,uuid)",
        "application.persist_and_complete_notebook_profiling_run(bigint,bigint,bigint,bigint,uuid,jsonb)",
    )
    forbidden = (
        "application.append_workflow_run_event(uuid,uuid,character varying,bigint,bigint,bigint,integer,character varying,character varying,character varying,integer,integer,integer)",
        "application.complete_workflow_run(uuid,uuid,character varying,bigint,bigint,integer)",
        "application.fail_workflow_run(uuid,uuid,character varying,bigint,bigint,character varying,character varying)",
        "application.get_profiling_connection_values(uuid,uuid,character varying,bigint,bigint,character varying)",
        "application.get_profiling_execution_context(uuid,uuid,character varying,bigint,bigint)",
        "application.persist_profiling_results(uuid,uuid,character varying,bigint,bigint,jsonb)",
        "application.resolve_notebook_profiling_claim(bigint,bigint,bigint,bigint,uuid)",
    )
    with notebook_actor.database.connect_owner() as connection:
        allowed_rows = connection.execute(
            """
            SELECT signature,
                   has_function_privilege(
                       'gds_notebook_runtime', signature, 'EXECUTE'
                   ) AS notebook_can_execute,
                   has_function_privilege(
                       'gds_web_write', signature, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', signature, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public', signature, 'EXECUTE'
                   ) AS public_can_execute
              FROM unnest(%s::TEXT[]) AS allowed_function(signature)
             ORDER BY signature
            """,
            (list(allowed),),
        ).fetchall()
        forbidden_rows = connection.execute(
            """
            SELECT signature,
                   has_function_privilege(
                       'gds_notebook_runtime', signature, 'EXECUTE'
                   ) AS notebook_can_execute
              FROM unnest(%s::TEXT[]) AS forbidden_function(signature)
             ORDER BY signature
            """,
            (list(forbidden),),
        ).fetchall()
        connection.execute(
            cast(LiteralString, VERIFY_INSTALL_SQL.read_text(encoding="utf-8"))
        )

    assert allowed_rows == [
        {
            "signature": signature,
            "notebook_can_execute": True,
            "web_can_execute": False,
            "mcp_can_execute": False,
            "public_can_execute": False,
        }
        for signature in sorted(allowed)
    ]
    assert forbidden_rows == [
        {"signature": signature, "notebook_can_execute": False}
        for signature in sorted(forbidden)
    ]

    with (
        notebook_actor.database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute("SELECT attribute_id FROM workflow.attribute_profile")
