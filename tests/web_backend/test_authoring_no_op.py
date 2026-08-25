from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import DependencyUnavailableError

from gds_workbench_api.features.workflows.authoring.lifecycle import AgentWorkflowEvent
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpRequest,
    DatabaseAuthoringNoOpService,
    authoring_no_op_candidate_digest,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_candidate_digest_is_canonical_and_plan_bound() -> None:
    plan = cast(
        AgentRunPlan,
        SimpleNamespace(
            model_id=18,
            model_revision=7,
            model_workflow="conceptual",
            workflow_execution_mode="one_shot",
            selected_scope_digest="a" * 64,
        ),
    )

    assert authoring_no_op_candidate_digest(plan) == (
        "af2d492ba6a8801a6fecc29695210c52e2fc8dceb2fb358e8a4d13e28fb36461"
    )


class NoOpTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.changed = True
        self.candidate_digest = "c" * 64
        self.claim_assertion_fails = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "application.assert_workflow_run_claim" in query:
            assert parameters == (1048, _CLAIM_TOKEN)
            if self.claim_assertion_fails:
                return None
            return {"assert_workflow_run_claim": None}
        return {
            "changed": self.changed,
            "workflow_run_id": 1048,
            "workflow_run_state": "completed_with_repair",
            "model_id": 18,
            "model_revision": 7,
            "model_workflow": "conceptual",
            "workflow_execution_mode": "one_shot",
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "candidate_digest": self.candidate_digest,
            "final_event_sequence": 3,
            "final_event_attempt": 2,
            "final_event_stage": "conceptual.backend_validation",
            "final_event_status": "warning",
            "final_event_message": ("Conceptual authoring completed with no effective change."),
            "final_event_current": 1,
            "final_event_total": 1,
            "final_finding_count": 0,
            "completed_at": datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
        }


class NoOpDatabase:
    def __init__(self) -> None:
        self.transaction = NoOpTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[NoOpTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_service_commits_one_server_owned_no_op_receipt() -> None:
    database = NoOpDatabase()
    service = DatabaseAuthoringNoOpService(database=database)
    request = AuthoringNoOpRequest(
        expected_workflow="conceptual",
        expected_execution_mode="one_shot",
        expected_correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        expected_model_revision=7,
        candidate_digest="c" * 64,
        final_event=AgentWorkflowEvent(
            sequence=3,
            attempt=2,
            stage="conceptual.backend_validation",
            status="warning",
            message="Conceptual authoring completed with no effective change.",
            current=1,
            total=1,
            finding_count=0,
        ),
    )

    receipt = await service.complete(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        request=request,
    )

    assert receipt.replayed is False
    assert receipt.workflow_run_state == "completed_with_repair"
    assert receipt.model_revision == 7
    assert receipt.candidate_digest == "c" * 64
    assert receipt.final_event.stage == "conceptual.backend_validation"
    assert receipt.final_event.status == "warning"
    assert receipt.final_event.message == (
        "Conceptual authoring completed with no effective change."
    )
    assert receipt.final_event.finding_count == 0
    assert len(database.transaction.calls) == 2
    fence_query, fence_parameters = database.transaction.calls[0]
    assert "application.assert_workflow_run_claim" in fence_query
    assert fence_parameters == (1048, _CLAIM_TOKEN)
    query, parameters = database.transaction.calls[1]
    assert "application.complete_authoring_workflow_run_no_op" in query
    assert parameters == (
        UUID("11111111-1111-1111-1111-111111111111"),
        UUID("22222222-2222-2222-2222-222222222222"),
        "user",
        7,
        18,
        1048,
        "conceptual",
        "one_shot",
        UUID("33333333-3333-3333-3333-333333333333"),
        7,
        "c" * 64,
        3,
        2,
        "conceptual.backend_validation",
        "warning",
        "Conceptual authoring completed with no effective change.",
        1,
        1,
        0,
    )

    database.transaction.changed = False
    replay = await service.complete(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        request=request,
    )

    assert replay.replayed is True
    assert replay.final_event == receipt.final_event
    assert len(database.transaction.calls) == 4

    database.transaction.candidate_digest = "d" * 64
    with pytest.raises(DependencyUnavailableError):
        await service.complete(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            request=request,
        )


@pytest.mark.asyncio
async def test_service_stops_before_no_op_completion_when_claim_fence_fails() -> None:
    database = NoOpDatabase()
    database.transaction.claim_assertion_fails = True
    service = DatabaseAuthoringNoOpService(database=database)
    request = AuthoringNoOpRequest(
        expected_workflow="conceptual",
        expected_execution_mode="one_shot",
        expected_correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        expected_model_revision=7,
        candidate_digest="c" * 64,
        final_event=AgentWorkflowEvent(
            sequence=3,
            attempt=2,
            stage="conceptual.backend_validation",
            status="warning",
            message="Conceptual authoring completed with no effective change.",
            current=1,
            total=1,
            finding_count=0,
        ),
    )

    with pytest.raises(DependencyUnavailableError):
        await service.complete(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            request=request,
        )

    assert len(database.transaction.calls) == 1
    assert "application.assert_workflow_run_claim" in database.transaction.calls[0][0]
