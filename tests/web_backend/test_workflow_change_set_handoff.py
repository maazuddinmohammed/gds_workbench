from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.change_sets.model_validation import (
    ModelValidationIssue,
    ValidatedModelChangeSet,
)

from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import AgentWorkflowEvent

_NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
_CHANGE_SET_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_CORRELATION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_CLAIM_TOKEN = UUID("44444444-4444-4444-8444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _change() -> StageModelChange:
    return StageModelChange(
        dataset="conceptual_object",
        records=[
            {
                "conceptual_object_name": "Customer",
                "conceptual_object_definition": "A governed customer.",
                "conceptual_object_type": "business_object",
                "conceptual_object_grain": "One customer.",
                "conceptual_object_aliases": [],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "supports": [],
            }
        ],
    )


def _change_set_row(*, status: str = "active") -> dict[str, Any]:
    return {
        "model_change_set_id": _CHANGE_SET_ID,
        "model_id": 18,
        "workflow_run_id": 1048,
        "model_change_set_status": status,
        "base_model_revision": 7,
        "base_source_context_digest": "a" * 64,
        "base_assertion_digest": "b" * 64,
        "base_policy_digest": "c" * 64,
        "draft_revision": 2 if status == "validated" else 1,
        "candidate_digest": "d" * 64 if status == "validated" else None,
        "validation_outcome": {} if status == "validated" else None,
        "model_scope_document": {},
        "profiling_document": {},
        "assertion_document": {},
        "analysis_document": {},
        "conceptual_document": {"conceptual_object": _change().records},
        "logical_document": {},
        "dimensional_document": {},
        "mapping_document": {},
        "code_generation_document": {},
        "qa_document": {},
        "created_by_principal_id": 41,
        "correlation_id": _CORRELATION_ID,
        "created_time": _NOW,
        "last_activity_time": _NOW,
        "expires_time": _NOW + timedelta(hours=4),
        "validated_time": _NOW if status == "validated" else None,
        "applied_time": None,
        "terminal_time": None,
    }


class HandoffTransaction:
    def __init__(
        self,
        *,
        existing: dict[str, Any] | None = None,
        actor_principal_id: int = 41,
        workflow: str = "conceptual",
        state: str = "running",
        model_revision: int = 7,
        fail_event: bool = False,
        fail_workflow_event: bool = False,
        claim_assertion_fails: bool = False,
    ) -> None:
        self.existing = existing
        self.actor_principal_id = actor_principal_id
        self.workflow = workflow
        self.state = state
        self.model_revision = model_revision
        self.fail_event = fail_event
        self.fail_workflow_event = fail_workflow_event
        self.claim_assertion_fails = claim_assertion_fails
        self.created = False
        self.events: list[str] = []
        self.workflow_calls: list[str] = []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.row: dict[str, Any] | None = existing

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
        if "INSERT INTO mcp.model_change_set (" in query:
            self.created = True
            self.row = _change_set_row()
            return self.row
        if "FROM model.model AS target_model" in query:
            return {
                "model_id": 18,
                "tenant_id": 7,
                "model_name": "Customer 360",
                "model_revision": self.model_revision,
            }
        if "security.authorize_tenant_operation" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": _NOW + timedelta(hours=1),
            }
        if "application.lock_authoring_workflow_run" in query:
            return {
                "workflow_run_id": 1048,
                "model_id": 18,
                "model_workflow": self.workflow,
                "workflow_execution_mode": "one_shot",
                "actor_principal_id": self.actor_principal_id,
                "workflow_run_state": self.state,
                "correlation_id": _CORRELATION_ID,
            }
        if "model_change_set.workflow_run_id" in query:
            return self.existing
        if "INSERT INTO mcp.model_change_set_event" in query:
            event_type = parameters[2]
            assert isinstance(event_type, str)
            self.events.append(event_type)
            if self.fail_event:
                raise RuntimeError("event persistence failed")
            return {"model_change_set_event_id": len(self.events)}
        if "SET profiling_document" in query:
            assert self.row is not None
            self.row = {**self.row, "draft_revision": 2}
            return {
                "draft_revision": 2,
                "model_change_set_status": "active",
                "expires_time": _NOW + timedelta(hours=4),
            }
        if "model_change_set.model_change_set_id" in query:
            return self.row
        if "SET model_change_set_status = %s" in query:
            assert self.row is not None
            self.row = {
                **self.row,
                "model_change_set_status": "validated",
                "draft_revision": 2,
                "candidate_digest": "d" * 64,
                "validated_time": _NOW,
            }
            return {
                "model_change_set_status": "validated",
                "draft_revision": 2,
                "candidate_digest": "d" * 64,
                "validated_time": _NOW,
                "expires_time": _NOW + timedelta(hours=4),
            }
        if "application.append_workflow_run_event" in query:
            self.workflow_calls.append("append")
            if self.fail_workflow_event:
                raise RuntimeError("workflow event persistence failed")
            return {"model_event_log_id": 91}
        if "application.complete_workflow_run" in query:
            self.workflow_calls.append("complete")
            return {
                "changed": self.state == "running",
                "workflow_run_id": 1048,
                "workflow_run_state": "completed",
                "completed_at": _NOW,
            }
        raise AssertionError((query, parameters))

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class HandoffDatabase:
    def __init__(self, transaction: HandoffTransaction) -> None:
        self.transaction = transaction
        self.rolled_back = False
        self.write_count = 0

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[HandoffTransaction]:
        self.write_count += 1
        try:
            yield self.transaction
        except Exception:
            self.rolled_back = True
            raise


async def _valid_validator(
    transaction: object,
    model: object,
    row: object,
) -> ValidatedModelChangeSet:
    del transaction, model, row
    return ValidatedModelChangeSet(
        records={"conceptual_object": ()},
        phase="complete",
        candidate_digest="d" * 64,
        issues=(),
        action_review=(),
    )


def _final_event() -> AgentWorkflowEvent:
    return AgentWorkflowEvent(
        sequence=3,
        attempt=1,
        stage="conceptual.backend_validation",
        status="running",
        message="Conceptual candidate is ready in a validated draft.",
        current=1,
        total=1,
        finding_count=1,
    )


@pytest.mark.asyncio
async def test_handoff_atomically_creates_stages_and_validates_one_bound_draft() -> None:
    database = HandoffDatabase(HandoffTransaction())
    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    result = await handoff.handoff(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_workflow="conceptual",
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        changes=(_change(),),
    )

    assert result.replayed is False
    assert result.model_change_set_id == _CHANGE_SET_ID
    assert result.draft_revision == 2
    assert result.candidate_digest == "d" * 64
    assert result.staged_record_count == 1
    assert "application.assert_workflow_run_claim" in database.transaction.calls[0][0]
    assert database.transaction.calls[0][1] == (1048, _CLAIM_TOKEN)
    assert database.transaction.created is True
    assert database.transaction.events == ["created", "section_put", "validated"]
    assert database.rolled_back is False


@pytest.mark.asyncio
async def test_handoff_replays_the_existing_validated_bound_draft() -> None:
    database = HandoffDatabase(HandoffTransaction(existing=_change_set_row(status="validated")))
    validator_called = False

    async def unexpected_validator(
        transaction: object,
        model: object,
        row: object,
    ) -> ValidatedModelChangeSet:
        del transaction, model, row
        nonlocal validator_called
        validator_called = True
        raise AssertionError("validated replay must not revalidate")

    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=unexpected_validator,
    )

    result = await handoff.handoff(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_workflow="conceptual",
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        changes=(_change(),),
    )

    assert result.replayed is True
    assert validator_called is False
    assert database.transaction.created is False
    assert database.transaction.events == []


@pytest.mark.asyncio
async def test_finalization_commits_draft_event_and_completion_together() -> None:
    database = HandoffDatabase(HandoffTransaction())
    finalizer = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    result = await finalizer.finalize(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_workflow="conceptual",
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        changes=(_change(),),
        final_event=_final_event(),
    )

    assert database.write_count == 1
    assert result.handoff.replayed is False
    assert result.completion.changed is True
    assert result.completion.workflow_run_state == "completed"
    claim_assertions = [
        call
        for call in database.transaction.calls
        if "application.assert_workflow_run_claim" in call[0]
    ]
    assert claim_assertions == [(database.transaction.calls[0][0], (1048, _CLAIM_TOKEN))]
    assert database.transaction.events == ["created", "section_put", "validated"]
    assert database.transaction.workflow_calls == ["append", "complete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["handoff", "finalize"])
async def test_claim_fence_rejection_stops_before_handoff_or_finalization(
    operation: str,
) -> None:
    transaction = HandoffTransaction(claim_assertion_fails=True)
    database = HandoffDatabase(transaction)
    service = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    with pytest.raises(DependencyUnavailableError):
        if operation == "handoff":
            await service.handoff(
                _principal(),
                tenant_id=7,
                model_id=18,
                workflow_run_id=1048,
                expected_workflow="conceptual",
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
                changes=(_change(),),
            )
        else:
            await service.finalize(
                _principal(),
                tenant_id=7,
                model_id=18,
                workflow_run_id=1048,
                expected_workflow="conceptual",
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
                changes=(_change(),),
                final_event=_final_event(),
            )

    assert len(transaction.calls) == 1
    assert "application.assert_workflow_run_claim" in transaction.calls[0][0]
    assert transaction.created is False
    assert transaction.events == []
    assert transaction.workflow_calls == []


@pytest.mark.asyncio
async def test_finalization_replays_terminal_receipt_without_current_revision() -> None:
    database = HandoffDatabase(
        HandoffTransaction(
            existing=_change_set_row(status="validated"),
            state="completed",
            model_revision=8,
        )
    )
    finalizer = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    result = await finalizer.finalize(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_workflow="conceptual",
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        changes=(_change(),),
        final_event=_final_event(),
    )

    assert result.handoff.replayed is True
    assert result.completion.changed is False
    assert result.completion.workflow_run_state == "completed"
    assert database.transaction.created is False
    assert database.transaction.events == []
    assert database.transaction.workflow_calls == ["append", "complete"]


@pytest.mark.asyncio
async def test_finalization_rolls_back_the_draft_when_workflow_event_fails() -> None:
    database = HandoffDatabase(HandoffTransaction(fail_workflow_event=True))
    finalizer = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    with pytest.raises(DependencyUnavailableError):
        await finalizer.finalize(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_workflow="conceptual",
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            changes=(_change(),),
            final_event=_final_event(),
        )

    assert database.rolled_back is True
    assert database.transaction.workflow_calls == ["append"]


@pytest.mark.asyncio
async def test_handoff_rejects_different_output_for_the_same_workflow_run() -> None:
    database = HandoffDatabase(HandoffTransaction(existing=_change_set_row(status="validated")))
    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )
    changed_record = dict(_change().records[0])
    changed_record["conceptual_object_definition"] = "A different candidate."

    with pytest.raises(
        InvalidRequestError,
        match="does not match the existing validated output",
    ):
        await handoff.handoff(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_workflow="conceptual",
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            changes=(
                StageModelChange(
                    dataset="conceptual_object",
                    records=[changed_record],
                ),
            ),
        )

    assert database.transaction.created is False
    assert database.transaction.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transaction", "error_type"),
    [
        (HandoffTransaction(actor_principal_id=99), AuthorizationDeniedError),
        (HandoffTransaction(workflow="logical"), InvalidRequestError),
        (HandoffTransaction(state="completed"), InvalidRequestError),
        (HandoffTransaction(model_revision=8), ModelRevisionConflictError),
    ],
)
async def test_handoff_rejects_wrong_run_binding_before_creating_a_draft(
    transaction: HandoffTransaction,
    error_type: type[Exception],
) -> None:
    database = HandoffDatabase(transaction)
    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    with pytest.raises(error_type):
        await handoff.handoff(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_workflow="conceptual",
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            changes=(_change(),),
        )

    assert transaction.created is False


@pytest.mark.asyncio
async def test_handoff_rolls_back_an_invalid_candidate_without_a_bound_draft() -> None:
    database = HandoffDatabase(HandoffTransaction())

    async def invalid_validator(
        transaction: object,
        model: object,
        row: object,
    ) -> ValidatedModelChangeSet:
        del transaction, model, row
        return ValidatedModelChangeSet(
            records={},
            phase="references",
            candidate_digest=None,
            issues=(
                ModelValidationIssue(
                    code="reference_not_found",
                    dataset="conceptual_relationship",
                    record_number=1,
                    fields=("to_conceptual_object_name",),
                    message="Referenced Conceptual Object is unavailable.",
                ),
            ),
            action_review=(),
        )

    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=invalid_validator,
    )

    with pytest.raises(WorkflowChangeSetValidationError) as error:
        await handoff.handoff(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_workflow="conceptual",
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            changes=(_change(),),
        )

    assert error.value.issues[0].code == "reference_not_found"
    assert database.rolled_back is True


@pytest.mark.asyncio
async def test_handoff_rolls_back_when_event_persistence_fails() -> None:
    database = HandoffDatabase(HandoffTransaction(fail_event=True))
    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
        validator=_valid_validator,
    )

    with pytest.raises(RuntimeError, match="event persistence failed"):
        await handoff.handoff(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_workflow="conceptual",
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            changes=(_change(),),
        )

    assert database.rolled_back is True
