import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Never
from uuid import UUID

import pytest
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.features.workflows.execution import (
    WorkerRunResult,
    WorkflowClaimLease,
    WorkflowExecutionClaim,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.execution.configuration import (
    WorkflowExecutionConfiguration,
)
from gds_workbench_api.workflow_worker import (
    create_worker_runtime,
    run_worker_loop,
    run_worker_process,
)


class StopLoopError(Exception):
    pass


class SequencedWorker:
    def __init__(self, results: list[WorkerRunResult]) -> None:
        self._results = results

    async def run_once(self) -> WorkerRunResult:
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_worker_loop_waits_with_distinct_idle_and_error_intervals() -> None:
    configuration = WorkflowExecutionConfiguration.from_environment({})
    worker = SequencedWorker([WorkerRunResult.IDLE, WorkerRunResult.EXECUTION_FAILED])
    delays: list[float] = []

    async def wait(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 2:
            raise StopLoopError

    with pytest.raises(StopLoopError):
        await run_worker_loop(worker, configuration=configuration, wait=wait)

    assert delays == [1, 5]


class ProcessDatabase:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        del isolation
        yield _unreachable()

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[WriteTransaction]:
        del isolation
        yield _unreachable()


def _unreachable() -> Never:
    raise AssertionError("No database transaction is expected")


def _claim() -> WorkflowExecutionClaim:
    claimed_at = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
    return WorkflowExecutionClaim(
        workflow_run_id=701,
        tenant_id=7,
        model_id=18,
        model_revision=4,
        model_workflow="logical",
        workflow_execution_mode="one_shot",
        correlation_id=UUID("11111111-1111-1111-1111-111111111111"),
        actor_principal_type="user",
        actor_entra_tenant_id=UUID("22222222-2222-2222-2222-222222222222"),
        actor_entra_object_id=UUID("33333333-3333-3333-3333-333333333333"),
        workflow_run_claim_token=UUID("44444444-4444-4444-4444-444444444444"),
        workflow_run_claimed_time=claimed_at,
        workflow_run_claim_expires_time=claimed_at + timedelta(seconds=30),
        workflow_run_recovery_count=0,
    )


class OneClaimRepository:
    def __init__(self, claim: WorkflowExecutionClaim) -> None:
        self._claim: WorkflowExecutionClaim | None = claim
        self.release_calls: list[tuple[int, UUID]] = []

    async def claim_next(
        self,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowExecutionClaim | None:
        del lease_duration_seconds
        claim, self._claim = self._claim, None
        return claim

    async def renew(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        lease_duration_seconds: int,
    ) -> WorkflowClaimLease:
        del workflow_run_id, workflow_run_claim_token, lease_duration_seconds
        raise AssertionError("Shutdown must happen before the heartbeat")

    async def release(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
    ) -> bool:
        self.release_calls.append((workflow_run_id, workflow_run_claim_token))
        return True


class BlockingDispatcher:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, claim: WorkflowExecutionClaim) -> object:
        del claim
        self.started.set()
        await asyncio.Event().wait()
        return object()


@pytest.mark.asyncio
async def test_worker_process_closes_database_and_releases_active_claim_on_shutdown() -> (
    None
):
    database = ProcessDatabase()
    claim = _claim()
    claims = OneClaimRepository(claim)
    dispatcher = BlockingDispatcher()
    worker = WorkflowExecutionWorker(
        claims=claims,
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
    )
    shutdown = asyncio.Event()

    process = asyncio.create_task(
        run_worker_process(
            database=database,
            worker=worker,
            configuration=WorkflowExecutionConfiguration.from_environment({}),
            shutdown=shutdown,
        )
    )
    await asyncio.wait_for(dispatcher.started.wait(), timeout=1)
    shutdown.set()
    await asyncio.wait_for(process, timeout=1)

    assert database.opened is True
    assert database.closed is True
    assert claims.release_calls == [(701, claim.workflow_run_claim_token)]


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_PUBLIC_URL": "http://localhost:8000",
            "GDS_WEB_FRONTEND_ORIGIN": "http://localhost:5173",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
        }
    )


def test_worker_entry_assembles_without_opening_the_database() -> None:
    database = ProcessDatabase()

    runtime = create_worker_runtime(settings=_settings(), database=database)

    assert runtime.database is database
    assert isinstance(runtime.worker, WorkflowExecutionWorker)
    assert database.opened is False
    assert database.closed is False
