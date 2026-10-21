"""Separate durable Workflow execution process."""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.infrastructure.postgres import ReadinessRecord

from gds_workbench_api.capabilities import (
    load_default_agent_capabilities,
    select_agent_runtime_capabilities,
)
from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
    WorkerRunResult,
    WorkflowExecutionDispatcher,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.execution.assembly import (
    WorkflowRuntimeDatabase,
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)
from gds_workbench_api.features.workflows.execution.configuration import (
    WorkflowExecutionConfiguration,
)
from gds_workbench_api.features.workflows.execution.worker import workflow_failure_category
from gds_workbench_api.integrations.databricks import create_databricks_execution_adapters
from gds_workbench_api.runtime_diagnostics import ReadinessCode, RuntimeDiagnostics

_logger = logging.getLogger(__name__)


class WorkerLoop(Protocol):
    async def run_once(self) -> WorkerRunResult: ...


class WorkerProcessDatabase(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> ReadinessRecord: ...


class WorkflowWorkerDatabase(
    WorkflowRuntimeDatabase,
    WorkerProcessDatabase,
    Protocol,
):
    """Complete database boundary for the worker process."""


@dataclass(frozen=True, slots=True)
class WorkflowWorkerRuntime:
    database: WorkerProcessDatabase
    worker: WorkflowExecutionWorker
    configuration: WorkflowExecutionConfiguration
    services: WorkflowRuntimeServices
    diagnostics: RuntimeDiagnostics | None = None

    async def run(self, shutdown: asyncio.Event) -> None:
        try:
            await run_worker_process(
                database=self.database,
                worker=self.worker,
                configuration=self.configuration,
                shutdown=shutdown,
                diagnostics=self.diagnostics,
            )
        finally:
            await self.services.close()


async def run_worker_loop(
    worker: WorkerLoop,
    *,
    configuration: WorkflowExecutionConfiguration,
    wait: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Claim continuously, waiting only when no useful immediate work remains."""
    while True:
        try:
            result = await worker.run_once()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            _logger.warning("workflow_poll_failed category=%s", workflow_failure_category(error))
            delay = configuration.error_poll_interval_seconds
        else:
            if result is WorkerRunResult.COMPLETED:
                continue
            delay = (
                configuration.idle_poll_interval_seconds
                if result is WorkerRunResult.IDLE
                else configuration.error_poll_interval_seconds
            )
        await wait(delay)


async def run_worker_process(
    *,
    database: WorkerProcessDatabase,
    worker: WorkerLoop,
    configuration: WorkflowExecutionConfiguration,
    shutdown: asyncio.Event,
    diagnostics: RuntimeDiagnostics | None = None,
) -> None:
    """Require a compatible database before claiming; release work on shutdown."""

    async def run_ready_worker() -> None:
        if shutdown.is_set():
            return
        if diagnostics is not None:
            diagnostics.started = True
            diagnostics.enter("database_open")
        try:
            await database.open()
            if diagnostics is not None:
                diagnostics.enter("database_readiness")
            readiness = await database.readiness()
        except Exception as error:
            if diagnostics is not None:
                diagnostics.readiness_code = "database_unavailable"
                diagnostics.record_fault(
                    workflow_failure_category(error),
                    "database_open"
                    if diagnostics.boundary == "database_open"
                    else "database_readiness",
                )
            _logger.error("workflow_database_not_ready code=database_unavailable")
            raise RuntimeError("workflow_database_not_ready") from None
        if shutdown.is_set():
            return
        if not readiness.ready:
            safe_code = (
                readiness.code
                if readiness.code
                in {
                    "database_version_invalid",
                    "database_schema_unavailable",
                    "database_role_invalid",
                    "database_unavailable",
                }
                else "database_unavailable"
            )
            if diagnostics is not None:
                diagnostics.readiness_code = cast(ReadinessCode, safe_code)
                diagnostics.record_fault(
                    "database_access"
                    if safe_code == "database_role_invalid"
                    else "database_connectivity"
                    if safe_code == "database_unavailable"
                    else "database_schema",
                    "database_readiness",
                )
            _logger.error("workflow_database_not_ready code=%s", safe_code)
            raise RuntimeError("workflow_database_not_ready")
        if diagnostics is not None:
            diagnostics.readiness_code = "ready"
            diagnostics.state = "ready"
            diagnostics.boundary = None
        # One long Run (for example a slow model call) must not hold every other Tenant's
        # Run in the queue. Claims stay exclusive per Run; PostgreSQL still allows one
        # running Run per Tenant.
        async with asyncio.TaskGroup() as loops:
            for _ in range(configuration.max_concurrent_runs):
                loops.create_task(run_worker_loop(worker, configuration=configuration))

    loop_task = asyncio.create_task(run_ready_worker())
    shutdown_task = asyncio.create_task(shutdown.wait())
    try:
        done, _ = await asyncio.wait(
            {loop_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if loop_task in done:
            await loop_task
    finally:
        tasks = (loop_task, shutdown_task)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        try:
            await database.close()
        finally:
            if diagnostics is not None:
                diagnostics.state = "stopped"
                diagnostics.boundary = None


def create_worker_runtime(
    *,
    settings: RuntimeSettings | None = None,
    database: WorkflowWorkerDatabase | None = None,
    diagnostics: RuntimeDiagnostics | None = None,
) -> WorkflowWorkerRuntime:
    """Assemble the worker without opening a database or starting execution."""
    runtime_settings = settings or RuntimeSettings.from_environment()
    runtime_diagnostics = diagnostics or RuntimeDiagnostics.capture_installed_sources()
    runtime_diagnostics.state = "starting"
    runtime_database = database or WebPostgresDatabase(
        dsn=runtime_settings.database_dsn,
        pool_min=runtime_settings.pool_min,
        # Each concurrent Run can hold an execution, a heartbeat and a sub-task connection.
        pool_max=max(
            runtime_settings.pool_max,
            3 * runtime_settings.workflow_execution.max_concurrent_runs,
        ),
        pool_timeout_seconds=runtime_settings.pool_timeout_seconds,
    )
    authorizer = AuthorizationService()
    all_agent_capabilities = load_default_agent_capabilities()
    agent_capabilities = (
        all_agent_capabilities
        if runtime_settings.agent_runtime.mode == "fake"
        else select_agent_runtime_capabilities(
            all_agent_capabilities,
            configured_models={
                (connection.provider_code, connection.model_code)
                for connection in runtime_settings.agent_runtime.connections
            },
        )
    )
    services = create_workflow_runtime_services(
        database=runtime_database,
        authorizer=authorizer,
        agent_runtime=runtime_settings.agent_runtime,
        agent_capability_registry=agent_capabilities,
        databricks_environment_code=runtime_settings.databricks_environment_code,
        databricks_execution=create_databricks_execution_adapters(
            runtime_settings.databricks_execution_mode
        ),
    )
    configuration = runtime_settings.workflow_execution
    worker = WorkflowExecutionWorker(
        claims=DatabaseWorkflowClaimRepository(database=runtime_database),
        dispatcher=WorkflowExecutionDispatcher(
            services.execution_services(), diagnostics=runtime_diagnostics
        ),
        lease_duration_seconds=configuration.lease_duration_seconds,
        heartbeat_interval_seconds=configuration.heartbeat_interval_seconds,
        diagnostics=runtime_diagnostics,
    )
    return WorkflowWorkerRuntime(
        database=runtime_database,
        worker=worker,
        configuration=configuration,
        services=services,
        diagnostics=runtime_diagnostics,
    )


async def _run_worker_entry() -> None:
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(stop_signal, shutdown.set)
    await create_worker_runtime().run(shutdown)


def main() -> None:
    asyncio.run(_run_worker_entry())


if __name__ == "__main__":
    main()


__all__ = [
    "WorkflowWorkerDatabase",
    "WorkflowWorkerRuntime",
    "create_worker_runtime",
    "main",
    "run_worker_loop",
    "run_worker_process",
]
