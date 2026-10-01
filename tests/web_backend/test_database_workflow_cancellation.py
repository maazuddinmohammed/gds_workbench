"""Cancellation fences use only the disposable PostgreSQL fixture."""

# Shared fixture lifecycle helpers are confined to disposable database tests.
# pyright: reportPrivateUsage=false

from typing import TYPE_CHECKING

import psycopg
import pytest
from psycopg.errors import ObjectNotInPrerequisiteState, RaiseException
from psycopg.rows import dict_row

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context
from tests.web_backend.test_database_workflow_run_claims import (
    _complete_run,
    _create_run,
    _start_run,
)

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres

CANCEL_SQL = "SELECT * FROM application.cancel_workflow_run(%s, %s, 'user', %s, %s, %s)"


@pytest.mark.parametrize("started", [False, True])
def test_cancellation_is_terminal_idempotent_and_revokes_claim(
    web_postgres_database: DisposablePostgres,
    started: bool,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=started)
    parameters = (
        context.entra_tenant_id,
        context.entra_object_id,
        context.tenant_id,
        context.model_id,
        run_id,
    )
    with psycopg.Connection[dict[str, object]].connect(
        web_postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
        autocommit=True,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        claim = connection.execute(
            "SELECT * FROM application.claim_next_workflow_run(30)"
        ).fetchone()
        assert (claim is not None) is started
        first = require_row(connection.execute(CANCEL_SQL, parameters).fetchone())
        repeated = require_row(connection.execute(CANCEL_SQL, parameters).fetchone())
        assert first["workflow_run_state"] == "cancelled"
        assert first["changed"] is True and repeated["changed"] is False
        assert first["completed_time"] == repeated["completed_time"]
        assert (
            connection.execute("SELECT * FROM application.claim_next_workflow_run(30)").fetchone()
            is None
        )
        if claim is not None:
            with pytest.raises(RaiseException, match="claim is unavailable"):
                connection.execute(
                    "SELECT * FROM application.renew_workflow_run_claim(%s, %s, 30)",
                    (run_id, claim["workflow_run_claim_token"]),
                )
            with pytest.raises(RaiseException, match="claim is unavailable"):
                connection.execute(
                    "SELECT application.assert_workflow_run_claim(%s, %s)",
                    (run_id, claim["workflow_run_claim_token"]),
                )
    with web_postgres_database.connect_owner() as connection:
        assert _start_run(connection, context, run_id)["workflow_run_state"] == "cancelled"
        events = connection.execute(
            "SELECT model_event_log_stage FROM model.model_event_log WHERE workflow_run_id = %s",
            (run_id,),
        ).fetchall()
        assert (
            sum(event["model_event_log_stage"] == "workflow_run.cancelled" for event in events) == 1
        )
        with (
            pytest.raises(ObjectNotInPrerequisiteState, match="terminal workflow run is immutable"),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE application.workflow_run SET workflow_run_state = 'running' "
                "WHERE workflow_run_id = %s",
                (run_id,),
            )
        with pytest.raises(RaiseException), connection.transaction():
            _complete_run(connection, context, run_id)


def test_cancellation_checks_path_ownership_lock_and_terminal_race(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    other = seed_workflow_context(web_postgres_database)
    parameters = (
        context.entra_tenant_id,
        context.entra_object_id,
        context.tenant_id,
        context.model_id,
    )
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)
        # An authorized caller cannot use another Tenant or Model's Run ID.
        with pytest.raises(RaiseException, match="unavailable"), connection.transaction():
            connection.execute(
                CANCEL_SQL,
                (
                    other.entra_tenant_id,
                    other.entra_object_id,
                    other.tenant_id,
                    other.model_id,
                    run_id,
                ),
            )
        with pytest.raises(RaiseException, match="denied"), connection.transaction():
            connection.execute(
                CANCEL_SQL,
                (
                    other.entra_tenant_id,
                    other.entra_object_id,
                    context.tenant_id,
                    context.model_id,
                    run_id,
                ),
            )
        # Even the run owner needs the current Tenant Lock.
        with connection.transaction(force_rollback=True):
            connection.execute(
                """UPDATE security.tenant_lock
                   SET tenant_lock_acquired_time = clock_timestamp() - INTERVAL '2 minutes',
                       tenant_lock_expires_time = clock_timestamp() - INTERVAL '1 second'
                 WHERE tenant_id = %s""",
                (context.tenant_id,),
            )
            with (
                pytest.raises(RaiseException, match="tenant_lock_required"),
                connection.transaction(),
            ):
                connection.execute(CANCEL_SQL, (*parameters, run_id))
        _complete_run(connection, context, run_id)
        with (
            pytest.raises(RaiseException, match="cancellation_conflict"),
            connection.transaction(),
        ):
            connection.execute(CANCEL_SQL, (*parameters, run_id))
        stored = require_row(
            connection.execute(
                "SELECT workflow_run_state FROM application.workflow_run "
                "WHERE workflow_run_id = %s",
                (run_id,),
            ).fetchone()
        )
        assert stored["workflow_run_state"] == "completed"


@pytest.mark.asyncio
async def test_cancel_service_interrupts_the_worker_and_rejects_late_writes(
    web_postgres_database: DisposablePostgres,
) -> None:
    import asyncio

    from gds_etl_workbench.application.authorization import AuthorizationService
    from gds_workbench_api.capabilities import load_default_agent_capabilities
    from gds_workbench_api.database import WebPostgresDatabase
    from gds_workbench_api.features.workflows.commands import (
        DatabaseWorkflowCommandService,
    )
    from gds_workbench_api.features.workflows.execution import (
        DatabaseWorkflowClaimRepository,
        WorkerRunResult,
        WorkflowClaimRunner,
    )

    from tests.web_backend.test_workflow_execution_worker import BlockingDispatcher

    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        claims = DatabaseWorkflowClaimRepository(database=database)
        claim = await claims.claim_next(lease_duration_seconds=30)
        assert claim is not None and claim.workflow_run_id == run_id
        dispatcher = BlockingDispatcher()
        runner = WorkflowClaimRunner(
            claims=claims,
            dispatcher=dispatcher,
            lease_duration_seconds=30,
            heartbeat_interval_seconds=0.05,
        )
        async with asyncio.TaskGroup() as group:
            execution = group.create_task(runner.run(claim))
            await asyncio.wait_for(dispatcher.started.wait(), timeout=2)
            service = DatabaseWorkflowCommandService(
                database=database,
                authorizer=AuthorizationService(),
                agent_capability_registry=load_default_agent_capabilities(),
            )
            cancelled = await service.cancel_run(
                claim.principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                workflow_run_id=run_id,
            )
            assert cancelled.workflow_run_state == "cancelled"
            assert await asyncio.wait_for(execution, timeout=2) is WorkerRunResult.CLAIM_LOST
        assert dispatcher.cancelled.is_set()
        assert await claims.claim_next(lease_duration_seconds=30) is None
    finally:
        await database.close()


def test_cancel_and_completion_race_has_exactly_one_terminal_winner(
    web_postgres_database: DisposablePostgres,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)
    ready = Barrier(2)

    def finish(cancel: bool) -> bool:
        try:
            with web_postgres_database.connect_owner() as connection:
                ready.wait(timeout=5)
                if cancel:
                    connection.execute(
                        CANCEL_SQL,
                        (
                            context.entra_tenant_id,
                            context.entra_object_id,
                            context.tenant_id,
                            context.model_id,
                            run_id,
                        ),
                    )
                else:
                    _complete_run(connection, context, run_id)
            return True
        except RaiseException:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(finish, [True, False]))
    assert sum(outcomes) == 1
    with web_postgres_database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                "SELECT workflow_run_state FROM application.workflow_run "
                "WHERE workflow_run_id = %s",
                (run_id,),
            ).fetchone()
        )
        assert row["workflow_run_state"] == ("cancelled" if outcomes[0] else "completed")


def test_cancellation_can_stop_a_stale_run_and_free_the_tenant_slot(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)
        with connection.transaction(force_rollback=True):
            connection.execute(
                "UPDATE model.model SET model_revision = model_revision + 1 WHERE model_id = %s",
                (context.model_id,),
            )
            result = require_row(
                connection.execute(
                    CANCEL_SQL,
                    (
                        context.entra_tenant_id,
                        context.entra_object_id,
                        context.tenant_id,
                        context.model_id,
                        run_id,
                    ),
                ).fetchone()
            )
            assert result["workflow_run_state"] == "cancelled"
        connection.execute(
            CANCEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                context.tenant_id,
                context.model_id,
                run_id,
            ),
        )
        next_run_id = _create_run(connection, context, start=True)
        connection.execute(
            CANCEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                context.tenant_id,
                context.model_id,
                next_run_id,
            ),
        )
