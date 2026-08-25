"""Single-claim durable Workflow Run worker behavior."""

import asyncio
from contextlib import suppress
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .contracts import WorkflowExecutionClaim
from .repository import WorkflowClaimLease


class WorkflowClaimRepository(Protocol):
    async def claim_next(
        self,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowExecutionClaim | None: ...

    async def renew(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        lease_duration_seconds: int,
    ) -> WorkflowClaimLease: ...

    async def release(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
    ) -> bool: ...


class WorkflowClaimDispatcher(Protocol):
    async def execute(self, claim: WorkflowExecutionClaim) -> object: ...


class WorkerRunResult(StrEnum):
    IDLE = "idle"
    COMPLETED = "completed"
    EXECUTION_FAILED = "execution_failed"
    CLAIM_LOST = "claim_lost"


class WorkflowExecutionWorker:
    def __init__(
        self,
        *,
        claims: WorkflowClaimRepository,
        dispatcher: WorkflowClaimDispatcher,
        lease_duration_seconds: int,
        heartbeat_interval_seconds: float,
    ) -> None:
        if lease_duration_seconds < 1 or lease_duration_seconds > 300:
            raise ValueError("Workflow Run lease duration must be between 1 and 300 seconds")
        if heartbeat_interval_seconds <= 0 or heartbeat_interval_seconds >= lease_duration_seconds:
            raise ValueError("Workflow Run heartbeat must be positive and shorter than its lease")
        self._claims = claims
        self._dispatcher = dispatcher
        self._lease_duration_seconds = lease_duration_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

    async def run_once(self) -> WorkerRunResult:
        claim = await self._claims.claim_next(lease_duration_seconds=self._lease_duration_seconds)
        if claim is None:
            return WorkerRunResult.IDLE

        execution = asyncio.create_task(self._dispatcher.execute(claim))
        heartbeat = asyncio.create_task(self._heartbeat(claim, execution))
        try:
            done, _ = await asyncio.wait(
                {execution, heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if execution in done:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
                try:
                    await execution
                except asyncio.CancelledError:
                    raise
                except Exception:
                    return WorkerRunResult.EXECUTION_FAILED
                return WorkerRunResult.COMPLETED

            try:
                await heartbeat
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            execution.cancel()
            with suppress(asyncio.CancelledError):
                await execution
            return WorkerRunResult.CLAIM_LOST
        except asyncio.CancelledError:
            execution.cancel()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await execution
            with suppress(asyncio.CancelledError):
                await heartbeat
            with suppress(Exception):
                await asyncio.shield(
                    self._claims.release(
                        workflow_run_id=claim.workflow_run_id,
                        workflow_run_claim_token=claim.workflow_run_claim_token,
                    )
                )
            raise

    async def _heartbeat(
        self,
        claim: WorkflowExecutionClaim,
        execution: asyncio.Task[object],
    ) -> None:
        while not execution.done():
            await asyncio.sleep(self._heartbeat_interval_seconds)
            if execution.done():
                return
            await self._claims.renew(
                workflow_run_id=claim.workflow_run_id,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                lease_duration_seconds=self._lease_duration_seconds,
            )


__all__ = [
    "WorkerRunResult",
    "WorkflowClaimDispatcher",
    "WorkflowClaimRepository",
    "WorkflowExecutionWorker",
]
