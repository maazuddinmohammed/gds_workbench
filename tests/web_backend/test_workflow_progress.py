from dataclasses import dataclass, field
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.features.workflows.authoring.lifecycle import AgentWorkflowEvent
from gds_workbench_api.features.workflows.authoring.progress import (
    AgentWorkflowProgress,
    intermediate_progress_points,
)

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


@dataclass
class _Lifecycle:
    events: list[AgentWorkflowEvent] = field(default_factory=list)

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None:
        assert principal == _principal()
        assert workflow_run_id == 1048
        assert expected_model_revision == 7
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.events.append(event)


def test_intermediate_progress_points_are_bounded_and_exclude_completion() -> None:
    assert intermediate_progress_points(8) == frozenset()
    assert intermediate_progress_points(80) == frozenset(range(10, 80, 10))
    points = intermediate_progress_points(1_000)
    assert len(points) <= 8
    assert max(points) < 1_000


@pytest.mark.asyncio
async def test_progress_allocates_contiguous_events_and_reserves_the_final_event() -> (
    None
):
    lifecycle = _Lifecycle()
    progress = AgentWorkflowProgress(
        lifecycle=lifecycle,
        principal=_principal(),
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    await progress.append(
        attempt=1,
        stage="conceptual.object_contribution",
        status="running",
        message="Detailed coverage started for 80 selected Objects.",
        current=0,
        total=80,
        finding_count=0,
    )
    await progress.append(
        attempt=1,
        stage="conceptual.object_contribution",
        status="running",
        message="Object contribution coverage processed 10 of 80 selected Objects.",
        current=10,
        total=80,
        finding_count=0,
    )
    final_event = progress.event(
        attempt=1,
        stage="conceptual.backend_validation",
        status="running",
        message="Conceptual candidate is ready in a validated draft.",
        current=1,
        total=1,
        finding_count=4,
    )

    assert [event.sequence for event in lifecycle.events] == [2, 3]
    assert final_event.sequence == 4
