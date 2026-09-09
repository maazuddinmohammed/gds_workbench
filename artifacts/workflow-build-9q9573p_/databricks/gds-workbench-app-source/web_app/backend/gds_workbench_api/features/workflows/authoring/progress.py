"""Contiguous, bounded progress events for one claimed agent Workflow Run."""

from __future__ import annotations

from math import ceil
from typing import Protocol
from uuid import UUID

from gds_etl_workbench.domain.authorization import RequestPrincipal

from .lifecycle import AgentWorkflowEvent, ProgressStatus


class AgentWorkflowProgressLifecycle(Protocol):
    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None: ...


class AgentWorkflowProgress:
    """Allocate and persist one contiguous event sequence for an active Run."""

    def __init__(
        self,
        *,
        lifecycle: AgentWorkflowProgressLifecycle,
        principal: RequestPrincipal,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> None:
        self._lifecycle = lifecycle
        self._principal = principal
        self._workflow_run_id = workflow_run_id
        self._expected_model_revision = expected_model_revision
        self._workflow_run_claim_token = workflow_run_claim_token
        self._next_sequence = 2

    def event(
        self,
        *,
        attempt: int,
        stage: str,
        status: ProgressStatus,
        message: str,
        current: int | None,
        total: int | None,
        finding_count: int,
    ) -> AgentWorkflowEvent:
        event = AgentWorkflowEvent(
            sequence=self._next_sequence,
            attempt=attempt,
            stage=stage,
            status=status,
            message=message,
            current=current,
            total=total,
            finding_count=finding_count,
        )
        self._next_sequence += 1
        return event

    async def append(
        self,
        *,
        attempt: int,
        stage: str,
        status: ProgressStatus,
        message: str,
        current: int | None,
        total: int | None,
        finding_count: int,
    ) -> None:
        await self._lifecycle.append_event(
            self._principal,
            workflow_run_id=self._workflow_run_id,
            expected_model_revision=self._expected_model_revision,
            workflow_run_claim_token=self._workflow_run_claim_token,
            event=self.event(
                attempt=attempt,
                stage=stage,
                status=status,
                message=message,
                current=current,
                total=total,
                finding_count=finding_count,
            ),
        )


def intermediate_progress_points(
    total: int,
    *,
    minimum_interval: int = 10,
    maximum_events: int = 8,
) -> frozenset[int]:
    """Return bounded intermediate counts; completion remains a separate event."""
    if total <= minimum_interval or minimum_interval < 1 or maximum_events < 1:
        return frozenset()
    interval = max(minimum_interval, ceil(total / maximum_events))
    return frozenset(range(interval, total, interval))
