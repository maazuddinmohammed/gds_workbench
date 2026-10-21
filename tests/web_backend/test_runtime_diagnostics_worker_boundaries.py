"""Observe real worker control flow without database or provider connections."""

# pyright: reportPrivateUsage=false

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import ReadinessRecord
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.execution import (
    WorkerRunResult,
    WorkflowClaimLease,
    WorkflowExecutionClaim,
    WorkflowExecutionDispatcher,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.execution.configuration import (
    WorkflowExecutionConfiguration,
)
from gds_workbench_api.features.workflows.usage.service import (
    DatabaseWorkflowUsageRecorder,
)
from gds_workbench_api.runtime_diagnostics import RuntimeDiagnostics
from gds_workbench_api.workflow_worker import run_worker_process
from psycopg.errors import InsufficientPrivilege, QueryCanceled, UndefinedFunction
from test_workflow_execution_dispatcher import _claim, _services
from test_workflow_execution_worker import FakeClaimRepository
from test_workflow_worker_runtime import ProcessDatabase, SequencedWorker


@pytest.mark.asyncio
@pytest.mark.parametrize("terminalization_fails", [False, True])
async def test_usage_failure_retains_original_category_after_heartbeat_and_idle(
    caplog: pytest.LogCaptureFixture,
    terminalization_fails: bool,
) -> None:
    claim = _claim(project_workflow="metadata_enrichment", workflow_execution_mode="one_shot")
    claims = FakeClaimRepository(claim)
    diagnostics = RuntimeDiagnostics(clock=lambda: 10.0)
    private_marker = "synthetic-private-usage-error"
    original = DependencyUnavailableError()
    original.__cause__ = InsufficientPrivilege(private_marker)
    calls: list[str] = []

    class UsageDatabase:
        @asynccontextmanager
        async def write_transaction(self) -> AsyncGenerator[Any]:
            yield self

        async def fetch_one(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ) -> dict[str, Any]:
            calls.append(query)
            if "application.begin_workflow_run_usage" in query:
                # A successful renewal must not replace the active usage boundary.
                await claims.renewed.wait()
                assert diagnostics.snapshot().worker.boundary == "usage_initialization"
                raise original
            if "application.assert_workflow_run_claim" in query:
                return {"assert_workflow_run_claim": None}
            assert "application.fail_workflow_run" in query
            if terminalization_fails:
                raise UndefinedFunction("synthetic-private-terminal-error")
            return {
                "changed": True,
                "workflow_run_id": claim.workflow_run_id,
                "workflow_run_state": "failed",
                "completed_at": datetime(2026, 10, 19, tzinfo=UTC),
            }

    database = UsageDatabase()
    services, executors = _services()
    services = replace(
        services,
        usage_recorder=DatabaseWorkflowUsageRecorder(database=database),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=database),
    )
    worker = WorkflowExecutionWorker(
        claims=claims,
        dispatcher=WorkflowExecutionDispatcher(services, diagnostics=diagnostics),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.001,
        diagnostics=diagnostics,
    )

    assert await asyncio.wait_for(worker.run_once(), timeout=1) is WorkerRunResult.EXECUTION_FAILED
    failed = diagnostics.snapshot().worker
    assert failed.last_fault is not None
    assert failed.last_fault.category == "database_access"
    assert failed.last_fault.boundary == "usage_initialization"
    assert failed.last_poll_result == "execution_failed"
    assert not any(executor.calls for executor in executors.values())
    assert len(calls) == 3

    assert await worker.run_once() is WorkerRunResult.IDLE
    idle = diagnostics.snapshot().worker
    assert idle.last_poll_result == "idle"
    assert idle.last_fault == failed.last_fault
    assert idle.boundary is None
    visible = json.dumps(asdict(diagnostics.snapshot())) + caplog.text
    assert private_marker not in visible
    assert "synthetic-private-terminal-error" not in visible
    assert str(claim.workflow_run_claim_token) not in visible
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_heartbeat_loss_during_usage_startup_has_heartbeat_boundary() -> None:
    claim = _claim(project_workflow="metadata_enrichment", workflow_execution_mode="one_shot")
    diagnostics = RuntimeDiagnostics()
    initializing = asyncio.Event()
    cancelled = asyncio.Event()

    class LostClaimRepository(FakeClaimRepository):
        async def renew(
            self,
            *,
            workflow_run_id: int,
            workflow_run_claim_token: UUID,
            lease_duration_seconds: int,
        ) -> WorkflowClaimLease:
            await initializing.wait()
            raise QueryCanceled("synthetic-private-renew-error")

    class BlockingUsageDatabase:
        @asynccontextmanager
        async def write_transaction(self) -> AsyncGenerator[Any]:
            yield self

        async def fetch_one(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ) -> dict[str, Any]:
            assert "application.begin_workflow_run_usage" in query
            initializing.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("A lost claim must cancel usage initialization")

    services, executors = _services()
    database = BlockingUsageDatabase()
    services = replace(
        services,
        usage_recorder=DatabaseWorkflowUsageRecorder(database=database),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=database),
    )
    # Contention is retried while the lease may be live, so use a short lease that
    # runs out before the claim is reported lost.
    worker = WorkflowExecutionWorker(
        claims=LostClaimRepository(claim),
        dispatcher=WorkflowExecutionDispatcher(services, diagnostics=diagnostics),
        lease_duration_seconds=1,
        heartbeat_interval_seconds=0.3,
        diagnostics=diagnostics,
    )

    assert await asyncio.wait_for(worker.run_once(), timeout=5) is WorkerRunResult.CLAIM_LOST
    snapshot = diagnostics.snapshot().worker
    assert snapshot.last_poll_result == "claim_lost"
    assert snapshot.last_fault is not None
    assert snapshot.last_fault.category == "database_contention"
    assert snapshot.last_fault.boundary == "heartbeat"
    assert cancelled.is_set()
    assert not any(executor.calls for executor in executors.values())
    assert "synthetic-private-renew-error" not in json.dumps(asdict(snapshot))


@pytest.mark.asyncio
async def test_completed_executor_does_not_record_concurrent_heartbeat_failure() -> None:
    claim = _claim(project_workflow="profiling")
    diagnostics = RuntimeDiagnostics()
    committed = asyncio.Event()

    class TerminalClaimRepository(FakeClaimRepository):
        async def renew(
            self,
            *,
            workflow_run_id: int,
            workflow_run_claim_token: UUID,
            lease_duration_seconds: int,
        ) -> WorkflowClaimLease:
            committed.set()
            raise InsufficientPrivilege("synthetic-private-final-renew-error")

    class CommitDispatcher:
        async def execute(self, claim: WorkflowExecutionClaim) -> object:
            await committed.wait()
            return object()

    worker = WorkflowExecutionWorker(
        claims=TerminalClaimRepository(claim),
        dispatcher=CommitDispatcher(),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.001,
        diagnostics=diagnostics,
    )

    assert await asyncio.wait_for(worker.run_once(), timeout=1) is WorkerRunResult.COMPLETED
    snapshot = diagnostics.snapshot().worker
    assert snapshot.last_poll_result == "completed"
    assert snapshot.last_fault is None
    assert snapshot.boundary is None


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["open", "readiness"])
async def test_startup_exception_retains_safe_boundary_after_resource_cleanup(
    phase: str, caplog: pytest.LogCaptureFixture
) -> None:
    diagnostics = RuntimeDiagnostics()
    private_marker = "synthetic-private-startup-error"

    class UnavailableDatabase(ProcessDatabase):
        async def open(self) -> None:
            if phase == "open":
                raise InsufficientPrivilege(private_marker)
            await super().open()

        async def readiness(self) -> ReadinessRecord:
            raise InsufficientPrivilege(private_marker)

    database = UnavailableDatabase()
    worker = SequencedWorker([WorkerRunResult.IDLE])
    with pytest.raises(RuntimeError, match="^workflow_database_not_ready$"):
        await run_worker_process(
            database=database,
            worker=worker,
            configuration=WorkflowExecutionConfiguration.from_environment({}),
            shutdown=asyncio.Event(),
            diagnostics=diagnostics,
        )

    snapshot = diagnostics.snapshot().worker
    assert database.closed
    assert worker._results == [WorkerRunResult.IDLE]
    assert snapshot.state == "stopped"
    assert snapshot.readiness_code == "database_unavailable"
    assert snapshot.last_fault is not None
    assert snapshot.last_fault.category == "database_access"
    assert snapshot.last_fault.boundary == f"database_{phase}"
    assert private_marker not in json.dumps(asdict(snapshot)) + caplog.text


@pytest.mark.asyncio
async def test_readiness_rejection_remains_visible_after_worker_stops() -> None:
    diagnostics = RuntimeDiagnostics()
    database = ProcessDatabase()
    database.ready = False
    worker = SequencedWorker([WorkerRunResult.IDLE])

    with pytest.raises(RuntimeError, match="^workflow_database_not_ready$"):
        await run_worker_process(
            database=database,
            worker=worker,
            configuration=WorkflowExecutionConfiguration.from_environment({}),
            shutdown=asyncio.Event(),
            diagnostics=diagnostics,
        )

    snapshot = diagnostics.snapshot().worker
    assert database.closed
    assert worker._results == [WorkerRunResult.IDLE]
    assert snapshot.state == "stopped"
    assert snapshot.readiness_code == "database_schema_unavailable"
    assert snapshot.last_poll_result is None
