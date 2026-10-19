"""Single-claim durable Workflow Run worker behavior."""

import asyncio
import logging
from contextlib import suppress
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from gds_etl_workbench.domain.errors import DependencyUnavailableError, WorkbenchError
from psycopg import InterfaceError, OperationalError
from psycopg.errors import (
    DeadlockDetected,
    InsufficientPrivilege,
    InvalidAuthorizationSpecification,
    InvalidSchemaName,
    LockNotAvailable,
    QueryCanceled,
    RaiseException,
    SerializationFailure,
    UndefinedColumn,
    UndefinedFunction,
    UndefinedObject,
    UndefinedTable,
)

from .contracts import WorkflowExecutionClaim
from .repository import WorkflowClaimLease

_logger = logging.getLogger(__name__)


def _failure_category(error: Exception) -> str:
    """Classify a bounded exception chain without reading messages or diagnostics."""
    current: BaseException | None = error
    seen: set[int] = set()
    category = "unexpected"
    for _ in range(6):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(
            current,
            UndefinedFunction
            | UndefinedTable
            | UndefinedColumn
            | UndefinedObject
            | InvalidSchemaName,
        ):
            return "database_schema"
        if isinstance(current, InsufficientPrivilege | InvalidAuthorizationSpecification):
            return "database_access"
        if isinstance(
            current, DeadlockDetected | SerializationFailure | LockNotAvailable | QueryCanceled
        ):
            return "database_contention"
        if isinstance(current, OperationalError | InterfaceError):
            return "database_connectivity"
        if isinstance(current, RaiseException):
            return "workflow_guard"
        if isinstance(current, DependencyUnavailableError):
            category = "dependency_unavailable"
        elif isinstance(current, WorkbenchError):
            category = "workflow_guard"
        current = current.__cause__ or current.__context__
    return category


class WorkflowClaimLeaseRepository(Protocol):
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


class WorkflowClaimRepository(WorkflowClaimLeaseRepository, Protocol):
    async def claim_next(
        self,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowExecutionClaim | None: ...


class WorkflowClaimDispatcher(Protocol):
    async def execute(self, claim: WorkflowExecutionClaim) -> object: ...


class WorkerRunResult(StrEnum):
    IDLE = "idle"
    COMPLETED = "completed"
    EXECUTION_FAILED = "execution_failed"
    CLAIM_LOST = "claim_lost"


class WorkflowClaimRunner:
    def __init__(
        self,
        *,
        claims: WorkflowClaimLeaseRepository,
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

    async def run(self, claim: WorkflowExecutionClaim) -> WorkerRunResult:
        """Execute one already-acquired claim with the shared lease behavior."""
        execution = asyncio.create_task(self._dispatcher.execute(claim))
        heartbeat = asyncio.create_task(self._heartbeat(claim, execution))
        try:
            done, _ = await asyncio.wait(
                {execution, heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if execution not in done:
                category = "unexpected"
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    category = _failure_category(error)
                # Completion may clear the claim while its last heartbeat is in
                # flight. A finished executor remains the authoritative outcome.
                if not execution.done():
                    _logger.warning(
                        "workflow_claim_lost run_id=%s recovery_count=%s category=%s",
                        claim.workflow_run_id,
                        claim.workflow_run_recovery_count,
                        category,
                    )
                    execution.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await execution
                    return WorkerRunResult.CLAIM_LOST

            heartbeat.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await heartbeat
            try:
                await execution
            except asyncio.CancelledError:
                raise
            except Exception as error:
                _logger.warning(
                    "workflow_execution_failed run_id=%s recovery_count=%s category=%s",
                    claim.workflow_run_id,
                    claim.workflow_run_recovery_count,
                    _failure_category(error),
                )
                return WorkerRunResult.EXECUTION_FAILED
            return WorkerRunResult.COMPLETED
        except asyncio.CancelledError:
            execution.cancel()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await execution
            with suppress(asyncio.CancelledError, Exception):
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


class WorkflowExecutionWorker:
    def __init__(
        self,
        *,
        claims: WorkflowClaimRepository,
        dispatcher: WorkflowClaimDispatcher,
        lease_duration_seconds: int,
        heartbeat_interval_seconds: float,
    ) -> None:
        self._claims = claims
        self._runner = WorkflowClaimRunner(
            claims=claims,
            dispatcher=dispatcher,
            lease_duration_seconds=lease_duration_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
        )
        self._lease_duration_seconds = lease_duration_seconds

    async def run_once(self) -> WorkerRunResult:
        claim = await self._claims.claim_next(lease_duration_seconds=self._lease_duration_seconds)
        if claim is None:
            return WorkerRunResult.IDLE
        return await self._runner.run(claim)


__all__ = [
    "WorkerRunResult",
    "WorkflowClaimDispatcher",
    "WorkflowClaimLeaseRepository",
    "WorkflowClaimRepository",
    "WorkflowClaimRunner",
    "WorkflowExecutionWorker",
]
