"""Atomic validated-draft handoff and optional Workflow Run completion."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets.model import (
    StageModelChange,
    model_change_set_documents,
    model_validation_outcome,
    pending_model_change_set_datasets,
    validate_locked_model_change_set,
    validate_model_change_set_document_bounds,
    validate_model_stage_changes,
)
from gds_etl_workbench.tools.change_sets.model_validation import (
    ModelValidationIssue,
    ValidatedModelChangeSet,
)
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from gds_etl_workbench.tools.snapshots.model.contracts import DATASETS_BY_NAME
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.model_change_sets.repository import (
    PostgresModelChangeSetRepository,
    require_datetime,
)
from gds_workbench_api.features.models import ModelNotFoundError, ModelRevisionConflictError
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowTerminalResult,
    append_agent_workflow_event,
    complete_agent_workflow_run,
)
from gds_workbench_api.features.workflows.authoring.plan import ModelWorkflow
from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

type ChangeSetValidator = Callable[
    [WriteTransaction, ModelReadContext, Mapping[str, Any]],
    Awaitable[ValidatedModelChangeSet],
]

_AUTHORING_WORKFLOWS = frozenset({"analysis", "conceptual", "logical", "dimensional", "mapping"})


class WorkflowChangeSetDatabase(Protocol):
    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class WorkflowChangeSetHandoffResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_id: int = Field(gt=0)
    workflow_run_id: int = Field(gt=0)
    model_change_set_id: UUID
    replayed: bool
    draft_revision: int = Field(gt=0)
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    staged_record_count: int = Field(gt=0)
    validated_at: datetime


class WorkflowChangeSetFinalizationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    handoff: WorkflowChangeSetHandoffResult
    completion: AgentWorkflowTerminalResult


class WorkflowChangeSetValidationError(WorkbenchError):
    __slots__ = ("issues",)

    def __init__(self, issues: tuple[ModelValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__(
            code="workflow_change_set_validation_failed",
            message="Authoritative Model Change Set validation failed.",
        )


class WorkflowChangeSetHandoff:
    """Create or replay one draft, with optional atomic Run completion."""

    def __init__(
        self,
        *,
        database: WorkflowChangeSetDatabase,
        authorizer: AuthorizationService,
        validator: ChangeSetValidator = validate_locked_model_change_set,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._validator = validator

    async def handoff(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageModelChange, ...],
    ) -> WorkflowChangeSetHandoffResult:
        staged, staged_record_count = self._validate_changes(
            expected_workflow=expected_workflow,
            changes=changes,
        )

        async with self._database.write_transaction() as transaction:
            await assert_workflow_run_claim(
                transaction,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            return await self._handoff_in_transaction(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow=expected_workflow,
                expected_model_revision=expected_model_revision,
                staged=staged,
                staged_record_count=staged_record_count,
            )

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
    ) -> WorkflowChangeSetFinalizationResult:
        """Validate the draft, append its exact event, and complete atomically."""
        staged, staged_record_count = self._validate_changes(
            expected_workflow=expected_workflow,
            changes=changes,
        )
        if (
            final_event.stage != f"{expected_workflow}.backend_validation"
            or final_event.finding_count != staged_record_count
        ):
            raise InvalidRequestError(
                "The final Workflow event does not match the authoring output."
            )

        async with self._database.write_transaction() as transaction:
            await assert_workflow_run_claim(
                transaction,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            handoff = await self._handoff_in_transaction(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow=expected_workflow,
                expected_model_revision=expected_model_revision,
                staged=staged,
                staged_record_count=staged_record_count,
            )
            await append_agent_workflow_event(
                transaction,
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                event=final_event,
            )
            completion = await complete_agent_workflow_run(
                transaction,
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                finding_count=staged_record_count,
            )
            return WorkflowChangeSetFinalizationResult(
                handoff=handoff,
                completion=completion,
            )

    async def _handoff_in_transaction(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_model_revision: int,
        staged: dict[str, list[dict[str, object]]],
        staged_record_count: int,
    ) -> WorkflowChangeSetHandoffResult:
        repository = PostgresModelChangeSetRepository(transaction)
        model_row = await repository.get_model_for_update(
            tenant_id=tenant_id,
            model_id=model_id,
        )
        if model_row is None:
            raise ModelNotFoundError()

        authorization = await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=ToolPolicy.TENANT_MODEL_WRITE,
        )
        principal_id = authorization.principal.principal_id
        if principal_id is None:
            raise AuthorizationDeniedError()

        run = await repository.get_workflow_run_for_update(
            workflow_run_id=workflow_run_id,
            model_id=model_id,
        )
        if run is None:
            raise WorkflowRunNotFoundError()
        if run["actor_principal_id"] != principal_id:
            raise AuthorizationDeniedError()
        if run["model_workflow"] != expected_workflow:
            raise InvalidRequestError(
                "Workflow Run does not match the requested authoring workflow."
            )
        if run["workflow_execution_mode"] is None:
            raise InvalidRequestError(
                "A deterministic Workflow Run cannot author a Model Change Set."
            )
        correlation_id = run["correlation_id"]
        if not isinstance(correlation_id, UUID):
            raise DependencyUnavailableError()

        existing = await repository.get_by_workflow_run(
            workflow_run_id=workflow_run_id,
            model_id=model_id,
        )
        if existing is not None:
            if existing["created_by_principal_id"] != principal_id:
                raise AuthorizationDeniedError()
            if (
                existing["base_model_revision"] != expected_model_revision
                or existing["correlation_id"] != correlation_id
            ):
                raise DependencyUnavailableError()
            if pending_model_change_set_datasets(existing) != staged:
                raise InvalidRequestError(
                    "Workflow Run output does not match the existing validated output."
                )
            if run["workflow_run_state"] not in {
                "running",
                "completed",
                "completed_with_repair",
            }:
                raise InvalidRequestError(
                    "Workflow Run output cannot be replayed from its current state."
                )
            return self._result(
                existing,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                replayed=True,
            )

        if run["workflow_run_state"] != "running":
            raise InvalidRequestError(
                "Workflow Run must be running before Model Change Set handoff."
            )
        if model_row["model_revision"] != expected_model_revision:
            raise ModelRevisionConflictError()

        change_set = await repository.create(
            change_set_id=uuid4(),
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            principal_id=principal_id,
            correlation_id=correlation_id,
        )
        if change_set is None:
            raise DependencyUnavailableError()
        change_set_id = change_set["model_change_set_id"]
        if not isinstance(change_set_id, UUID):
            raise DependencyUnavailableError()

        await repository.insert_event(
            change_set_id=change_set_id,
            model_id=model_id,
            event_type="created",
            draft_revision=change_set["draft_revision"],
            section=None,
            action_count=0,
            outcome="created",
            metadata={},
            correlation_id=correlation_id,
        )

        documents = model_change_set_documents(change_set)
        for dataset, records in staged.items():
            section = DATASETS_BY_NAME[dataset].section
            documents[section][dataset] = records
        validate_model_change_set_document_bounds(documents)
        staged_row = await repository.stage_documents(
            documents=documents,
            change_set_id=change_set_id,
        )
        if staged_row is None:
            raise DependencyUnavailableError()
        await repository.insert_event(
            change_set_id=change_set_id,
            model_id=model_id,
            event_type="section_put",
            draft_revision=staged_row["draft_revision"],
            section=expected_workflow,
            action_count=staged_record_count,
            outcome="staged",
            metadata={"datasets": sorted(staged)},
            correlation_id=correlation_id,
        )

        current = await repository.get_change_set(
            change_set_id=change_set_id,
            model_id=model_id,
            for_update=True,
        )
        if current is None:
            raise DependencyUnavailableError()
        model = ModelReadContext(
            model_id=model_row["model_id"],
            tenant_id=model_row["tenant_id"],
            model_name=model_row["model_name"],
            model_revision=model_row["model_revision"],
        )
        validation = await self._validator(transaction, model, current)
        if not validation.valid:
            raise WorkflowChangeSetValidationError(validation.issues)
        if validation.candidate_digest is None:
            raise DependencyUnavailableError()

        validated = await repository.record_validation(
            change_set_id=change_set_id,
            status="validated",
            candidate_digest=validation.candidate_digest,
            outcome=model_validation_outcome(validation),
            valid=True,
        )
        if validated is None:
            raise DependencyUnavailableError()
        await repository.insert_event(
            change_set_id=change_set_id,
            model_id=model_id,
            event_type="validated",
            draft_revision=validated["draft_revision"],
            section=None,
            action_count=sum(len(records) for records in validation.records.values()),
            outcome="valid",
            metadata={"phase": validation.phase, "error_count": 0},
            correlation_id=correlation_id,
        )

        return WorkflowChangeSetHandoffResult(
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            model_change_set_id=change_set_id,
            replayed=False,
            draft_revision=validated["draft_revision"],
            candidate_digest=validation.candidate_digest,
            staged_record_count=staged_record_count,
            validated_at=require_datetime(validated, "validated_time"),
        )

    @staticmethod
    def _validate_changes(
        *,
        expected_workflow: ModelWorkflow,
        changes: tuple[StageModelChange, ...],
    ) -> tuple[dict[str, list[dict[str, object]]], int]:
        if expected_workflow not in _AUTHORING_WORKFLOWS:
            raise InvalidRequestError(
                "This Workflow does not produce an authoring Model Change Set."
            )
        if not changes or any(not change.records for change in changes):
            raise InvalidRequestError(
                "A Workflow Model Change Set requires at least one changed record."
            )
        if any(DATASETS_BY_NAME[change.dataset].section != expected_workflow for change in changes):
            raise InvalidRequestError(
                "Workflow output contains a dataset from another authoring section."
            )
        staged = validate_model_stage_changes(list(changes))
        return staged, sum(len(records) for records in staged.values())

    @staticmethod
    def _result(
        row: Mapping[str, Any],
        *,
        model_id: int,
        workflow_run_id: int,
        replayed: bool,
    ) -> WorkflowChangeSetHandoffResult:
        if row["model_change_set_status"] != "validated":
            raise DependencyUnavailableError()
        candidate_digest = row["candidate_digest"]
        if not isinstance(candidate_digest, str):
            raise DependencyUnavailableError()
        return WorkflowChangeSetHandoffResult(
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            model_change_set_id=row["model_change_set_id"],
            replayed=replayed,
            draft_revision=row["draft_revision"],
            candidate_digest=candidate_digest,
            staged_record_count=sum(
                len(records) for records in pending_model_change_set_datasets(row).values()
            ),
            validated_at=require_datetime(row, "validated_time"),
        )


__all__ = [
    "WorkflowChangeSetFinalizationResult",
    "WorkflowChangeSetHandoff",
    "WorkflowChangeSetHandoffResult",
    "WorkflowChangeSetValidationError",
]
