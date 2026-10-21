import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString, Never
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_workbench_api.app_process import run_app_processes
from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
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
from test_app_process import FakeServer
from test_workflow_claim_repository import ClaimDatabase, ClaimTransaction


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


@pytest.mark.asyncio
async def test_worker_loop_reports_invalid_claim_without_logging_its_contents(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_marker = "synthetic-private-claim-input"

    class InvalidClaimTransaction(ClaimTransaction):
        async def fetch_one(
            self,
            query: LiteralString,
            parameters: tuple[Any, ...] = (),
        ) -> dict[str, Any] | None:
            row = await super().fetch_one(query, parameters)
            assert row is not None
            row["workflow_execution_mode"] = private_marker
            return row

    database = ClaimDatabase()
    database.transaction = InvalidClaimTransaction()
    dispatcher = BlockingDispatcher()
    worker = WorkflowExecutionWorker(
        claims=DatabaseWorkflowClaimRepository(database=database),
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
    )

    async def stop_after_failure(delay: float) -> None:
        assert delay == 5
        raise StopLoopError

    with pytest.raises(StopLoopError):
        await run_worker_loop(
            worker,
            configuration=WorkflowExecutionConfiguration.from_environment({}),
            wait=stop_after_failure,
        )

    assert "workflow_poll_failed category=invalid_contract" in caplog.text
    assert private_marker not in caplog.text
    assert str(database.transaction.claim_token) not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert dispatcher.started.is_set() is False
    assert database.rolled_back is True


class ProcessDatabase:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.readiness_calls = 0
        self.ready = True

    async def readiness(self) -> ReadinessRecord:
        assert self.opened and not self.closed
        self.readiness_calls += 1
        return ReadinessRecord(
            ready=self.ready, code="ready" if self.ready else "database_schema_unavailable"
        )

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
        project_id=18,
        project_revision=4,
        project_workflow="logical",
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
    assert database.readiness_calls == 1
    assert claims.release_calls == [(701, claim.workflow_run_claim_token)]


@pytest.mark.asyncio
async def test_incompatible_database_stops_worker_before_claiming_and_closes_resources(
    caplog: pytest.LogCaptureFixture,
) -> None:
    database = ProcessDatabase()
    database.ready = False
    worker = SequencedWorker([WorkerRunResult.IDLE])

    with pytest.raises(RuntimeError, match="^workflow_database_not_ready$") as caught:
        await asyncio.wait_for(
            run_worker_process(
                database=database,
                worker=worker,
                configuration=WorkflowExecutionConfiguration.from_environment({}),
                shutdown=asyncio.Event(),
            ),
            timeout=1,
        )

    assert caught.value.__cause__ is None
    assert database.closed and database.readiness_calls == 1
    assert "workflow_database_not_ready code=database_schema_unavailable" in caplog.text
    assert worker._results == [WorkerRunResult.IDLE]  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_startup_readiness_error_is_redacted_and_database_is_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class UnavailableDatabase(ProcessDatabase):
        async def readiness(self) -> ReadinessRecord:
            raise RuntimeError("synthetic-private-database-diagnostic")

    database = UnavailableDatabase()
    with pytest.raises(RuntimeError, match="^workflow_database_not_ready$") as caught:
        await run_worker_process(
            database=database,
            worker=SequencedWorker([]),
            configuration=WorkflowExecutionConfiguration.from_environment({}),
            shutdown=asyncio.Event(),
        )

    assert database.closed
    assert caught.value.__suppress_context__
    assert "workflow_database_not_ready code=database_unavailable" in caplog.text
    assert "synthetic-private-database-diagnostic" not in caplog.text


@pytest.mark.asyncio
async def test_incompatible_worker_database_stops_http_and_closes_agent_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = ProcessDatabase()
    database.ready = False
    runtime = create_worker_runtime(settings=_settings(), database=database)
    close_agent = AsyncMock()
    monkeypatch.setattr(runtime.services.agent_executor, "close", close_agent)
    server = FakeServer()

    with pytest.raises(RuntimeError, match="^workflow_database_not_ready$"):
        await asyncio.wait_for(run_app_processes(server=server, worker=runtime), timeout=1)

    assert database.closed and server.stopped.is_set()
    close_agent.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["open", "readiness"])
async def test_http_shutdown_interrupts_worker_database_startup(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    checking = asyncio.Event()

    class CheckingDatabase(ProcessDatabase):
        async def open(self) -> None:
            await super().open()
            if phase == "open":
                checking.set()
                await asyncio.Event().wait()

        async def readiness(self) -> ReadinessRecord:
            checking.set()
            await asyncio.Event().wait()
            return await super().readiness()

    database = CheckingDatabase()
    runtime = create_worker_runtime(settings=_settings(), database=database)
    claim = AsyncMock(side_effect=AssertionError("Startup must not claim a run"))
    monkeypatch.setattr(runtime.worker, "run_once", claim)
    close_agent = AsyncMock()
    monkeypatch.setattr(runtime.services.agent_executor, "close", close_agent)
    server = FakeServer()
    process = asyncio.create_task(
        run_app_processes(server=server, worker=runtime, shutdown_timeout_seconds=0.05)
    )
    await asyncio.wait_for(checking.wait(), timeout=1)
    server.should_exit = True
    await asyncio.wait_for(process, timeout=1)

    assert database.closed and server.stopped.is_set()
    claim.assert_not_awaited()
    close_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_never_claims_after_shutdown_was_already_requested() -> None:
    database = ProcessDatabase()
    worker = SequencedWorker([WorkerRunResult.IDLE])
    shutdown = asyncio.Event()
    shutdown.set()
    await run_worker_process(
        database=database,
        worker=worker,
        configuration=WorkflowExecutionConfiguration.from_environment({}),
        shutdown=shutdown,
    )

    assert database.closed
    assert worker._results == [WorkerRunResult.IDLE]  # pyright: ignore[reportPrivateUsage]


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
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
