"""Exercise worker boundaries without database connections or provider requests."""

# pyright: reportPrivateUsage=false

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.execution import (
    WorkerRunResult,
    WorkflowClaimLease,
    WorkflowClaimRunner,
    WorkflowExecutionClaim,
    WorkflowExecutionDispatcher,
)
from gds_workbench_api.features.workflows.usage.service import (
    DatabaseWorkflowUsageRecorder,
)
from psycopg.errors import UndefinedFunction
from test_workflow_execution_dispatcher import RecordingExecutor, _claim, _services
from test_workflow_execution_worker import FakeClaimRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("terminalization_fails", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
async def test_usage_startup_failure_has_safe_diagnostic_before_executor_runs(
    caplog: pytest.LogCaptureFixture,
    terminalization_fails: bool,
    wrapped: bool,
) -> None:
    claim = _claim(
        project_workflow="metadata_enrichment", workflow_execution_mode="one_shot"
    )
    private_marker = "synthetic-private-database-error"
    private_error = UndefinedFunction(private_marker)
    original_error = DependencyUnavailableError() if wrapped else private_error
    if wrapped:
        # WebPostgresDatabase wraps driver errors before the recorder sees them.
        original_error.__cause__ = private_error
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class FailingUsageDatabase:
        @asynccontextmanager
        async def write_transaction(self) -> AsyncGenerator[Any]:
            yield self

        async def fetch_one(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ) -> dict[str, Any]:
            calls.append((query, parameters))
            if "application.begin_workflow_run_usage" in query:
                raise original_error
            if "application.assert_workflow_run_claim" in query:
                assert parameters == (claim.workflow_run_id, claim.workflow_run_claim_token)
                return {"assert_workflow_run_claim": None}
            assert "application.fail_workflow_run" in query
            assert parameters == (
                claim.actor_entra_tenant_id,
                claim.actor_entra_object_id,
                claim.actor_principal_type,
                claim.workflow_run_id,
                claim.project_revision,
                "workflow_usage_unavailable",
                "Workflow usage tracking could not initialize before execution. "
                "Check database compatibility and access.",
            )
            if terminalization_fails:
                raise RuntimeError("synthetic-private-lifecycle-error")
            return {
                "changed": True,
                "workflow_run_id": claim.workflow_run_id,
                "workflow_run_state": "failed",
                "completed_at": datetime(2026, 10, 19, tzinfo=UTC),
            }

    database = FailingUsageDatabase()
    services, executors = _services()
    services = replace(
        services,
        usage_recorder=DatabaseWorkflowUsageRecorder(database=database),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=database),
    )
    runner = WorkflowClaimRunner(
        claims=FakeClaimRepository(claim),
        dispatcher=WorkflowExecutionDispatcher(services),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
    )

    assert await runner.run(claim) is WorkerRunResult.EXECUTION_FAILED
    assert not any(executor.calls for executor in executors.values())
    assert len(calls) == 3
    assert "workflow_execution_failed" in caplog.text
    assert "database_schema" in caplog.text
    assert "run_id=701" in caplog.text
    assert "recovery_count=0" in caplog.text
    assert private_marker not in caplog.text
    assert "synthetic-private-lifecycle-error" not in caplog.text
    assert str(claim.workflow_run_claim_token) not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)

    # A failed terminal transition must not replace the diagnostic's original cause.
    with pytest.raises(type(original_error)) as caught:
        await WorkflowExecutionDispatcher(services).execute(claim)
    assert caught.value is original_error


@pytest.mark.asyncio
async def test_executor_failure_does_not_trigger_duplicate_startup_terminalization() -> None:
    claim = _claim(
        project_workflow="metadata_enrichment", workflow_execution_mode="one_shot"
    )
    calls: list[str] = []

    class UsageDatabase:
        @asynccontextmanager
        async def write_transaction(self) -> AsyncGenerator[Any]:
            yield self

        async def fetch_one(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ) -> dict[str, Any]:
            calls.append(query)
            assert "application.begin_workflow_run_usage" in query
            return {"agent_model_code": "synthetic-model"}

    class FailedExecutor(RecordingExecutor):
        async def execute_started(self, *args: Any, **kwargs: Any) -> object:
            raise DependencyUnavailableError()

    database = UsageDatabase()
    services, _ = _services()
    services = replace(
        services,
        metadata_enrichment=FailedExecutor(),
        usage_recorder=DatabaseWorkflowUsageRecorder(database=database),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=database),
    )
    with pytest.raises(DependencyUnavailableError):
        await WorkflowExecutionDispatcher(services).execute(claim)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_committed_completion_wins_concurrent_heartbeat_rejection() -> None:
    claim = _claim(
        project_workflow="metadata_enrichment", workflow_execution_mode="one_shot"
    )
    committed = asyncio.Event()

    class TerminalClaimRepository(FakeClaimRepository):
        async def renew(
            self,
            *,
            workflow_run_id: int,
            workflow_run_claim_token: UUID,
            lease_duration_seconds: int,
        ) -> WorkflowClaimLease:
            # Terminal completion clears the claim before the heartbeat can renew it.
            committed.set()
            raise DependencyUnavailableError()

    class CommitDispatcher:
        async def execute(self, claim: WorkflowExecutionClaim) -> object:
            assert claim.project_workflow == "metadata_enrichment"
            await committed.wait()
            return object()

    runner = WorkflowClaimRunner(
        claims=TerminalClaimRepository(claim),
        dispatcher=CommitDispatcher(),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.001,
    )

    assert await runner.run(claim) is WorkerRunResult.COMPLETED
