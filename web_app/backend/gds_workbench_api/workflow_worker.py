"""Separate durable Workflow execution process."""

import asyncio
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService

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
from gds_workbench_api.integrations.databricks import create_databricks_execution_adapters


class WorkerLoop(Protocol):
    async def run_once(self) -> WorkerRunResult: ...


class WorkerProcessDatabase(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...


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

    async def run(self, shutdown: asyncio.Event) -> None:
        try:
            await run_worker_process(
                database=self.database,
                worker=self.worker,
                configuration=self.configuration,
                shutdown=shutdown,
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
        except Exception:
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
) -> None:
    """Own database lifecycle; cancel execution and release its lease on shutdown."""
    await database.open()
    loop_task = asyncio.create_task(run_worker_loop(worker, configuration=configuration))
    shutdown_task = asyncio.create_task(shutdown.wait())
    try:
        done, _ = await asyncio.wait(
            {loop_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if loop_task in done:
            await loop_task
    finally:
        loop_task.cancel()
        shutdown_task.cancel()
        with suppress(asyncio.CancelledError):
            await loop_task
        with suppress(asyncio.CancelledError):
            await shutdown_task
        await database.close()


def create_worker_runtime(
    *,
    settings: RuntimeSettings | None = None,
    database: WorkflowWorkerDatabase | None = None,
) -> WorkflowWorkerRuntime:
    """Assemble the worker without opening a database or starting execution."""
    runtime_settings = settings or RuntimeSettings.from_environment()
    runtime_database = database or WebPostgresDatabase(
        dsn=runtime_settings.database_dsn,
        pool_min=runtime_settings.pool_min,
        pool_max=runtime_settings.pool_max,
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
        dispatcher=WorkflowExecutionDispatcher(services.execution_services()),
        lease_duration_seconds=configuration.lease_duration_seconds,
        heartbeat_interval_seconds=configuration.heartbeat_interval_seconds,
    )
    return WorkflowWorkerRuntime(
        database=runtime_database,
        worker=worker,
        configuration=configuration,
        services=services,
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
