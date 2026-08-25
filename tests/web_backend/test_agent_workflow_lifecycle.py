from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    DatabaseAgentWorkflowLifecycle,
)

_CLAIM_TOKEN = UUID("33333333-3333-3333-3333-333333333333")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


class LifecycleTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
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
        if "target_model.model_revision" in query:
            return {"model_revision": 7}
        if "start_workflow_run" in query:
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "workflow_run_state": "running",
                "started_at": datetime(2026, 8, 24, 10, tzinfo=UTC),
            }
        if "append_workflow_run_event" in query:
            return {"model_event_log_id": 91}
        if "complete_workflow_run" in query:
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "workflow_run_state": "completed_with_repair",
                "completed_at": datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
            }
        if "fail_workflow_run" in query:
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "workflow_run_state": "failed",
                "completed_at": datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
            }
        raise AssertionError("unexpected lifecycle query")


class LifecycleDatabase:
    def __init__(self) -> None:
        self.transaction = LifecycleTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[LifecycleTransaction]:
        del isolation
        yield self.transaction

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[LifecycleTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_lifecycle_uses_governed_functions_with_server_identity() -> None:
    database = LifecycleDatabase()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)

    started = await lifecycle.start(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_workflow="conceptual",
        expected_execution_mode="one_shot",
        expected_model_revision=7,
    )
    await lifecycle.append_event(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        event=AgentWorkflowEvent(
            sequence=2,
            attempt=1,
            stage="candidate_authoring",
            status="running",
            message="Candidate validation started.",
            current=0,
            total=1,
            finding_count=0,
        ),
    )
    completed = await lifecycle.complete(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        finding_count=12,
    )

    assert started.workflow_run_state == "running"
    assert completed.workflow_run_state == "completed_with_repair"
    identity = (
        UUID("11111111-1111-1111-1111-111111111111"),
        UUID("22222222-2222-2222-2222-222222222222"),
        "user",
    )
    assert database.transaction.calls[0][1] == (
        7,
        18,
        1048,
        "conceptual",
        "one_shot",
    )
    assert database.transaction.calls[1][1] == identity + (1048, 7)
    assert "application.assert_workflow_run_claim" in database.transaction.calls[2][0]
    assert database.transaction.calls[2][1] == (1048, _CLAIM_TOKEN)
    assert database.transaction.calls[3][1] == identity + (
        1048,
        7,
        2,
        1,
        "candidate_authoring",
        "running",
        "Candidate validation started.",
        0,
        1,
        0,
    )
    assert "application.assert_workflow_run_claim" in database.transaction.calls[4][0]
    assert database.transaction.calls[4][1] == (1048, _CLAIM_TOKEN)
    assert database.transaction.calls[5][1] == identity + (1048, 7, 12)


@pytest.mark.asyncio
async def test_lifecycle_failure_is_safe_and_bounded() -> None:
    database = LifecycleDatabase()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)

    result = await lifecycle.fail(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        failure_code="agent_candidate_validation_failed",
        safe_failure_message="Candidate validation failed.",
    )

    assert result.workflow_run_state == "failed"
    assert "sensitive" not in repr(result)
    assert "application.assert_workflow_run_claim" in database.transaction.calls[0][0]
    assert "application.fail_workflow_run" in database.transaction.calls[1][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["append", "complete", "fail"])
async def test_lifecycle_claim_fence_rejection_stops_before_mutation(
    operation: str,
) -> None:
    database = LifecycleDatabase()
    database.transaction.claim_assertion_fails = True
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)

    with pytest.raises(DependencyUnavailableError):
        if operation == "append":
            await lifecycle.append_event(
                _principal(),
                workflow_run_id=1048,
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage="candidate_authoring",
                    status="running",
                    message="Candidate validation started.",
                    finding_count=0,
                ),
            )
        elif operation == "complete":
            await lifecycle.complete(
                _principal(),
                workflow_run_id=1048,
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
                finding_count=1,
            )
        else:
            await lifecycle.fail(
                _principal(),
                workflow_run_id=1048,
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
                failure_code="agent_candidate_validation_failed",
                safe_failure_message="Candidate validation failed.",
            )

    assert len(database.transaction.calls) == 1
    assert "application.assert_workflow_run_claim" in database.transaction.calls[0][0]


def test_event_rejects_unsafe_or_incomplete_progress() -> None:
    with pytest.raises(ValueError):
        AgentWorkflowEvent(
            sequence=2,
            attempt=1,
            stage="candidate_authoring",
            status="running",
            message="unsafe\nmessage",
            current=1,
            total=None,
            finding_count=0,
        )
