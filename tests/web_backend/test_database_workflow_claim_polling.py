"""Real workers must acquire new Runs after repeated empty, prepared polls."""

# Reuse fixture-only setup; all providers remain synthetic.
# pyright: reportPrivateUsage=false

import asyncio
import re
import threading
from collections.abc import Iterator, Sequence
from dataclasses import replace
from types import TracebackType
from typing import Self
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.profiling.execution import (
    _RESULT_COLUMNS,
    ConnectorProfilingExecutor,
)
from gds_etl_workbench.infrastructure.databricks_sql import ConnectorDatabricksSqlExecutor
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
    WorkerRunResult,
    WorkflowExecutionDispatcher,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.execution.assembly import create_workflow_runtime_services
from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration
from gds_workbench_api.integrations.databricks import create_databricks_execution_adapters
from gds_workbench_api.runtime_diagnostics import RuntimeDiagnostics

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.enrichment_test_support import seed_project_enrichment
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)
from tests.mcp.test_database_metadata_enrichment_registration import _create
from tests.mcp.test_database_profiling_execution_context import _seed_profiling_execution
from tests.mcp.test_database_profiling_persistence import _seed_attributes
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context


@pytest.fixture(scope="module")
def polling_postgres() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
        _seed_super_admin(database)
        _apply_sql(database, _render_seed())
        yield database


@pytest.mark.parametrize("workflow", ["profiling", "metadata_enrichment"])
async def test_worker_completes_run_created_after_prepared_idle_polls(
    polling_postgres: DisposablePostgres,
    workflow: str,
) -> None:
    fixture = polling_postgres
    if workflow == "profiling":
        seed = _seed_profiling_execution(fixture, start=False)
        context = seed.context
        run_id = seed.workflow_run_id
        environment_code = seed.environment_code
    else:
        context = seed_workflow_context(fixture)
        _seed_attributes(fixture, context)
        with fixture.connect_owner() as connection:
            connection.execute(
                "UPDATE project.project SET default_agent_sdk_code='openai_agents_sdk', "
                "default_agent_provider_code='microsoft_foundry', "
                "default_agent_model_code='foundry-primary' WHERE project_id=%s",
                (context.project_id,),
            )
            seed_project_enrichment(connection, context.project_id)
        run_id = _create(fixture, context, correlation_id=uuid4())["workflow_run_id"]
        environment_code = "fixture"

    # One connection guarantees every idle poll and pickup uses the warmed session.
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    services = create_workflow_runtime_services(
        database=database,
        authorizer=AuthorizationService(),
        agent_runtime=AgentRuntimeConfiguration(mode="fake", timeout_seconds=120, connections=()),
        agent_capability_registry=load_default_agent_capabilities(),
        databricks_environment_code=environment_code,
        databricks_execution=create_databricks_execution_adapters("fake"),
    )
    diagnostics = RuntimeDiagnostics()
    worker = WorkflowExecutionWorker(
        claims=DatabaseWorkflowClaimRepository(database=database),
        dispatcher=WorkflowExecutionDispatcher(
            services.execution_services(), diagnostics=diagnostics
        ),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
        diagnostics=diagnostics,
    )
    try:
        await database.open()
        assert (await database.readiness()).ready
        for _ in range(12):
            assert await worker.run_once() is WorkerRunResult.IDLE
        async with database.read_transaction() as transaction:
            prepared = await transaction.fetch_one(
                "SELECT count(*) > 0 AS claim_prepared FROM pg_prepared_statements "
                "WHERE statement LIKE '%%application.claim_next_workflow_run%%'"
            )
        assert prepared == {"claim_prepared": True}
        assert diagnostics.snapshot().worker.last_fault is None

        with fixture.connect_owner() as connection:
            connection.execute(
                "SELECT application.start_workflow_run(%s,%s,'user',%s,%s)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.project_revision,
                ),
            )

        assert await asyncio.wait_for(worker.run_once(), timeout=15) is WorkerRunResult.COMPLETED
        async with database.read_transaction() as transaction:
            state = await transaction.fetch_one(
                "SELECT workflow_run_state, failure_code, workflow_run_recovery_count, "
                "usage_tracking_version, usage_tracked_recovery_count, "
                "workflow_run_claim_token_digest IS NULL AS claim_cleared "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (run_id,),
            )
        assert state == {
            "workflow_run_state": "completed",
            "failure_code": None,
            "workflow_run_recovery_count": 0,
            "usage_tracking_version": 1,
            "usage_tracked_recovery_count": 0,
            "claim_cleared": True,
        }
        assert diagnostics.snapshot().worker.last_poll_result == "completed"
        assert diagnostics.snapshot().worker.last_fault is None
    finally:
        await services.close()
        await database.close()


@pytest.mark.parametrize("workflow", ["profiling", "metadata_enrichment"])
@pytest.mark.parametrize("blocked_call", ["connect", "execute", "fetch"])
async def test_native_connector_stalls_do_not_prevent_worker_heartbeats(
    polling_postgres: DisposablePostgres,
    workflow: str,
    blocked_call: str,
) -> None:
    fixture = polling_postgres
    seed = _seed_profiling_execution(fixture, start=False)
    context = seed.context
    run_id = seed.workflow_run_id
    if workflow == "metadata_enrichment":
        # Reuse the fixture's synthetic warehouse coordinates, never a real connector.
        with fixture.connect_owner() as connection:
            connection.execute(
                "UPDATE project.project SET default_agent_sdk_code='openai_agents_sdk', "
                "default_agent_provider_code='microsoft_foundry', "
                "default_agent_model_code='foundry-primary' WHERE project_id=%s",
                (context.project_id,),
            )
            seed_project_enrichment(connection, context.project_id)
        run_id = _create(fixture, context, correlation_id=uuid4())["workflow_run_id"]
    with fixture.connect_owner() as connection:
        connection.execute(
            "SELECT application.start_workflow_run(%s,%s,'user',%s,%s)",
            (
                context.entra_tenant_id,
                context.entra_object_id,
                run_id,
                context.project_revision,
            ),
        )

    entered = threading.Event()
    released = threading.Event()
    synchronization = threading.Lock()
    calls = {"connect": 0, "execute": 0, "fetch": 0}

    def stall_once(boundary: str) -> None:
        with synchronization:
            calls[boundary] += 1
            should_stall = boundary == blocked_call and calls[boundary] == 1
        if should_stall:
            entered.set()
            if not released.wait(8):
                raise AssertionError("Synthetic synchronous connector was not released")

    class Cursor:
        def __init__(self) -> None:
            self.description: tuple[tuple[str], ...] = ()
            self.rows: list[tuple[object, ...]] = []

        def execute(self, operation: str, parameters: Sequence[object] = ()) -> None:
            del parameters
            stall_once("execute")
            if workflow == "profiling":
                self.description = tuple((name,) for name in _RESULT_COLUMNS)
                attribute_ids = re.findall(r"CAST\((\d+) AS BIGINT\) AS attribute_id", operation)
                self.rows = [
                    (int(attribute_id), 0, 0, 0, 0, 0, None, None, None, 0, 0, 0, 0, 0)
                    for attribute_id in attribute_ids
                ]
                assert self.rows
            else:
                assert ".information_schema.columns" in operation
                names = re.findall(r"'([^']*)'", operation.split(" IN (", 1)[1])
                self.description = (("column_name",), ("full_data_type",), ("comment",))
                self.rows = [(name, "BIGINT", None) for name in names]
                assert self.rows

        def fetchmany(self, size: int) -> list[tuple[object, ...]]:
            stall_once("fetch")
            return self.rows[:size]

        def cancel(self) -> None:
            released.set()

        def __enter__(self) -> Self:
            return self

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            pass

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

        def __enter__(self) -> Self:
            return self

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            pass

    def connect(**_arguments: object) -> Connection:
        stall_once("connect")
        return Connection()

    adapters = create_databricks_execution_adapters("fake")
    if workflow == "profiling":
        adapters = replace(adapters, profiling=ConnectorProfilingExecutor(connect=connect))
    else:
        adapters = replace(
            adapters, metadata_enrichment_sql=ConnectorDatabricksSqlExecutor(connect=connect)
        )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=2, pool_max=3, pool_timeout_seconds=5
    )
    services = create_workflow_runtime_services(
        database=database,
        authorizer=AuthorizationService(),
        agent_runtime=AgentRuntimeConfiguration(mode="fake", timeout_seconds=120, connections=()),
        agent_capability_registry=load_default_agent_capabilities(),
        databricks_environment_code=seed.environment_code,
        databricks_execution=adapters,
    )
    diagnostics = RuntimeDiagnostics()
    worker = WorkflowExecutionWorker(
        claims=DatabaseWorkflowClaimRepository(database=database),
        dispatcher=WorkflowExecutionDispatcher(
            services.execution_services(), diagnostics=diagnostics
        ),
        lease_duration_seconds=2,
        heartbeat_interval_seconds=0.2,
        diagnostics=diagnostics,
    )
    execution: asyncio.Task[WorkerRunResult] | None = None
    try:
        await database.open()
        assert (await database.readiness()).ready
        execution = asyncio.create_task(worker.run_once())
        assert await asyncio.to_thread(entered.wait, 3)
        await asyncio.sleep(2.25)
        assert not execution.done()
        async with database.read_transaction() as transaction:
            lease = await transaction.fetch_one(
                "SELECT clock_timestamp() > workflow_run_claimed_time + interval '2 seconds' "
                "AS initial_lease_elapsed, "
                "workflow_run_claim_heartbeat_time > workflow_run_claimed_time AS renewed, "
                "workflow_run_claim_expires_time > clock_timestamp() AS live, "
                "workflow_run_recovery_count FROM application.workflow_run "
                "WHERE workflow_run_id=%s",
                (run_id,),
            )
        assert lease == {
            "initial_lease_elapsed": True,
            "renewed": True,
            "live": True,
            "workflow_run_recovery_count": 0,
        }
        released.set()
        assert await asyncio.wait_for(execution, timeout=10) is WorkerRunResult.COMPLETED
        async with database.read_transaction() as transaction:
            state = await transaction.fetch_one(
                "SELECT workflow_run_state, failure_code, workflow_run_recovery_count "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (run_id,),
            )
        assert state == {
            "workflow_run_state": "completed",
            "failure_code": None,
            "workflow_run_recovery_count": 0,
        }
        assert all(count > 0 for count in calls.values())
        assert diagnostics.snapshot().worker.last_fault is None
    finally:
        released.set()
        if execution is not None:
            if not execution.done():
                execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
        await services.close()
        await database.close()
