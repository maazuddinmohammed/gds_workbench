"""Real Profiling worker and PostgreSQL; synthetic warehouse aggregates only."""

# pyright: reportPrivateUsage=false
import asyncio
from collections.abc import Iterator
from typing import Any, LiteralString, cast

import gds_workbench_api.database as database_module
import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.profiling.execution import ProfileMetric, ProfileQuery
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
    WorkerRunResult,
    WorkflowExecutionDispatcher,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.execution.assembly import create_workflow_runtime_services
from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration
from gds_workbench_api.integrations.databricks import (
    LocalFakeProfilingExecutor,
    create_databricks_execution_adapters,
)

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,  # pyright: ignore[reportPrivateUsage]
)
from tests.mcp.test_database_profiling_execution_context import (
    _seed_profiling_execution,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture(scope="module")
def profiling_worker_postgres() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
        yield database


async def test_profiling_worker_completes_after_initial_lease_expires(
    profiling_worker_postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _seed_profiling_execution(profiling_worker_postgres)
    database = WebPostgresDatabase(
        dsn=profiling_worker_postgres.web_runtime_dsn(),
        pool_min=2,
        pool_max=3,
        pool_timeout_seconds=5,
    )
    services = create_workflow_runtime_services(
        database=database,
        authorizer=AuthorizationService(),
        agent_runtime=AgentRuntimeConfiguration(mode="fake", timeout_seconds=120, connections=()),
        agent_capability_registry=load_default_agent_capabilities(),
        databricks_environment_code=seed.environment_code,
        databricks_execution=create_databricks_execution_adapters("fake"),
    )
    original_execute = LocalFakeProfilingExecutor.execute
    executed_objects: set[int] = set()

    async def delayed_execute(
        self: LocalFakeProfilingExecutor,
        *,
        connection: DatabricksSqlConnection,
        query: ProfileQuery,
        timeout_seconds: int,
    ) -> tuple[ProfileMetric, ...]:
        await asyncio.sleep(2.25)
        async with database.read_transaction() as transaction:
            lease = await transaction.fetch_one(
                "SELECT clock_timestamp() > workflow_run_claimed_time + interval '2 seconds' "
                "AS initial_lease_elapsed, "
                "workflow_run_claim_heartbeat_time > workflow_run_claimed_time AS renewed, "
                "workflow_run_claim_expires_time > clock_timestamp() AS live "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (seed.workflow_run_id,),
            )
        assert lease == {"initial_lease_elapsed": True, "renewed": True, "live": True}
        executed_objects.add(query.object_id)
        return await original_execute(
            self, connection=connection, query=query, timeout_seconds=timeout_seconds
        )

    monkeypatch.setattr(LocalFakeProfilingExecutor, "execute", delayed_execute)
    await database.open()
    try:
        assert (await database.readiness()).ready
        worker = WorkflowExecutionWorker(
            claims=DatabaseWorkflowClaimRepository(database=database),
            dispatcher=WorkflowExecutionDispatcher(services.execution_services()),
            lease_duration_seconds=2,
            heartbeat_interval_seconds=0.2,
        )
        result = await asyncio.wait_for(worker.run_once(), timeout=10)
        assert result is WorkerRunResult.COMPLETED
        assert executed_objects == set(seed.context.selected_object_ids)
        async with database.read_transaction() as transaction:
            state = await transaction.fetch_one(
                "SELECT workflow_run_state, workflow_run_recovery_count, "
                "workflow_run_claim_token_digest IS NULL AS claim_cleared "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (seed.workflow_run_id,),
            )
        assert state == {
            "workflow_run_state": "completed",
            "workflow_run_recovery_count": 0,
            "claim_cleared": True,
        }
    finally:
        await services.close()
        await database.close()


@pytest.mark.parametrize("historical_context_lock", [False, True], ids=["current", "historical"])
async def test_slow_profiling_context_preserves_claim_only_with_compatible_row_lock(
    profiling_worker_postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    historical_context_lock: bool,
) -> None:
    seed = _seed_profiling_execution(profiling_worker_postgres)
    original_definition: str | None = None
    if historical_context_lock:
        # Reproduce the prior installation only in the disposable container.
        with profiling_worker_postgres.connect_owner() as connection:
            row = connection.execute(
                "SELECT pg_get_functiondef('application.get_profiling_execution_context("
                "uuid,uuid,character varying,bigint,bigint)'::regprocedure) AS definition"
            ).fetchone()
            assert row is not None
            original_definition = str(row["definition"])
            assert "FOR KEY SHARE OF run FOR SHARE OF target_project" in original_definition
            connection.execute(
                cast(
                    LiteralString,
                    original_definition.replace(
                        "FOR KEY SHARE OF run FOR SHARE OF target_project",
                        "FOR SHARE OF run, target_project",
                    ),
                )
            )
    database = WebPostgresDatabase(
        dsn=profiling_worker_postgres.web_runtime_dsn(),
        pool_min=2,
        pool_max=3,
        pool_timeout_seconds=5,
    )
    services = create_workflow_runtime_services(
        database=database,
        authorizer=AuthorizationService(),
        agent_runtime=AgentRuntimeConfiguration(mode="fake", timeout_seconds=120, connections=()),
        agent_capability_registry=load_default_agent_capabilities(),
        databricks_environment_code=seed.environment_code,
        databricks_execution=create_databricks_execution_adapters("fake"),
    )
    original_fetch = database_module._WebTransaction.fetch_all

    async def slow_context(
        self: database_module._WebTransaction,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        rows = await original_fetch(self, query, parameters)
        if "FROM application.get_profiling_execution_context" in query:
            # Hold the real REPEATABLE READ transaction between its context read
            # and the connection getter, which reads the same context again.
            await asyncio.sleep(2.25)
        return rows

    monkeypatch.setattr(database_module._WebTransaction, "fetch_all", slow_context)
    try:
        await database.open()
        readiness = await database.readiness()
        assert readiness.ready is not historical_context_lock
        if historical_context_lock:
            assert readiness.code == "database_schema_unavailable"
        worker = WorkflowExecutionWorker(
            claims=DatabaseWorkflowClaimRepository(database=database),
            dispatcher=WorkflowExecutionDispatcher(services.execution_services()),
            lease_duration_seconds=2,
            heartbeat_interval_seconds=0.2,
        )
        # Direct execution deliberately bypasses today's startup readiness guard
        # to reproduce the older deployment's six expired acquisitions.
        for _ in range(7 if historical_context_lock else 1):
            await asyncio.wait_for(worker.run_once(), timeout=10)
        async with database.read_transaction() as transaction:
            state = await transaction.fetch_one(
                "SELECT workflow_run_state, failure_code, workflow_run_recovery_count "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (seed.workflow_run_id,),
            )
            events = await transaction.fetch_one(
                "SELECT count(*) AS prepare_count FROM project.project_event_log "
                "WHERE workflow_run_id=%s AND project_event_log_stage='profiling.prepare'",
                (seed.workflow_run_id,),
            )
        if historical_context_lock:
            assert state == {
                "workflow_run_state": "failed",
                "failure_code": "workflow_run_recovery_exhausted",
                "workflow_run_recovery_count": 5,
            }
            assert events == {"prepare_count": 0}
        else:
            assert state == {
                "workflow_run_state": "completed",
                "failure_code": None,
                "workflow_run_recovery_count": 0,
            }
            assert events == {"prepare_count": 1}
    finally:
        await services.close()
        await database.close()
        if original_definition is not None:
            with profiling_worker_postgres.connect_owner() as connection:
                connection.execute(cast(LiteralString, original_definition))
