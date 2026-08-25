import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from gds_workbench_api.features.workflows.execution import (
    WorkerRunResult,
    WorkflowClaimLease,
    WorkflowExecutionClaim,
    WorkflowExecutionWorker,
)


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


class FakeClaimRepository:
    def __init__(self, claim: WorkflowExecutionClaim | None) -> None:
        self.claim = claim
        self.claim_calls: list[int] = []
        self.renew_calls: list[tuple[int, UUID, int]] = []
        self.release_calls: list[tuple[int, UUID]] = []
        self.renewed = asyncio.Event()
        self.released = asyncio.Event()
        self.renew_fails = False

    async def claim_next(
        self,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowExecutionClaim | None:
        self.claim_calls.append(lease_duration_seconds)
        claimed, self.claim = self.claim, None
        return claimed

    async def renew(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        lease_duration_seconds: int,
    ) -> WorkflowClaimLease:
        self.renew_calls.append(
            (
                workflow_run_id,
                workflow_run_claim_token,
                lease_duration_seconds,
            )
        )
        self.renewed.set()
        if self.renew_fails:
            raise RuntimeError("claim lost")
        now = datetime.now(UTC)
        return WorkflowClaimLease(
            workflow_run_id=workflow_run_id,
            workflow_run_claim_heartbeat_time=now,
            workflow_run_claim_expires_time=now + timedelta(seconds=lease_duration_seconds),
        )

    async def release(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
    ) -> bool:
        self.release_calls.append((workflow_run_id, workflow_run_claim_token))
        self.released.set()
        return True


class BlockingDispatcher:
    def __init__(self) -> None:
        self.claims: list[WorkflowExecutionClaim] = []
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.failure: Exception | None = None

    async def execute(self, claim: WorkflowExecutionClaim) -> object:
        self.claims.append(claim)
        self.started.set()
        try:
            await self.finish.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        if self.failure is not None:
            raise self.failure
        return object()


@pytest.mark.asyncio
async def test_worker_returns_idle_without_dispatch_when_no_run_is_claimable() -> None:
    repository = FakeClaimRepository(None)
    dispatcher = BlockingDispatcher()
    worker = WorkflowExecutionWorker(
        claims=repository,
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.01,
    )

    result = await worker.run_once()

    assert result is WorkerRunResult.IDLE
    assert repository.claim_calls == [30]
    assert dispatcher.claims == []


@pytest.mark.asyncio
async def test_worker_renews_a_live_claim_until_execution_completes() -> None:
    claim = _claim()
    repository = FakeClaimRepository(claim)
    dispatcher = BlockingDispatcher()
    worker = WorkflowExecutionWorker(
        claims=repository,
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.001,
    )

    attempt = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(repository.renewed.wait(), timeout=1)
    dispatcher.finish.set()

    assert await attempt is WorkerRunResult.COMPLETED
    assert repository.renew_calls[0] == (
        701,
        claim.workflow_run_claim_token,
        30,
    )
    assert repository.release_calls == []


@pytest.mark.asyncio
async def test_worker_leaves_an_unexpected_failure_claimed_for_bounded_recovery() -> None:
    repository = FakeClaimRepository(_claim())
    dispatcher = BlockingDispatcher()
    dispatcher.failure = RuntimeError("safe test failure")
    dispatcher.finish.set()
    worker = WorkflowExecutionWorker(
        claims=repository,
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.01,
    )

    result = await worker.run_once()

    assert result is WorkerRunResult.EXECUTION_FAILED
    assert repository.release_calls == []


@pytest.mark.asyncio
async def test_worker_cancels_execution_when_the_claim_is_lost() -> None:
    repository = FakeClaimRepository(_claim())
    repository.renew_fails = True
    dispatcher = BlockingDispatcher()
    worker = WorkflowExecutionWorker(
        claims=repository,
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.001,
    )

    result = await worker.run_once()

    assert result is WorkerRunResult.CLAIM_LOST
    assert dispatcher.cancelled.is_set()
    assert repository.release_calls == []


@pytest.mark.asyncio
async def test_worker_releases_the_exact_claim_during_graceful_shutdown() -> None:
    claim = _claim()
    repository = FakeClaimRepository(claim)
    dispatcher = BlockingDispatcher()
    worker = WorkflowExecutionWorker(
        claims=repository,
        dispatcher=dispatcher,
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.01,
    )

    attempt = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(dispatcher.started.wait(), timeout=1)
    attempt.cancel()

    with pytest.raises(asyncio.CancelledError):
        await attempt
    assert repository.release_calls == [(701, claim.workflow_run_claim_token)]
