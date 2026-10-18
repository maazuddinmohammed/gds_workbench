"""Atomic validated-draft handoff and optional Workflow Run completion."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from functools import partial
from typing import Any, Protocol
from uuid import UUID, uuid4

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import (
    StageProjectChange,
    pending_project_change_set_datasets,
    project_change_set_documents,
    project_validation_outcome,
    validate_locked_project_change_set,
    validate_project_change_set_document_bounds,
    validate_project_stage_changes,
)
from gds_etl_workbench.application.change_sets.project_validation import (
    ProjectValidationIssue,
    ValidatedProjectChangeSet,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    WorkbenchError,
)
from gds_etl_workbench.domain.snapshots.project import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.project_change_sets.repository import (
    PostgresProjectChangeSetRepository,
    require_datetime,
)
from gds_workbench_api.features.projects import ProjectNotFoundError, ProjectRevisionConflictError
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowTerminalResult,
    append_agent_workflow_event,
    complete_agent_workflow_run,
    fail_agent_workflow_run,
)
from gds_workbench_api.features.workflows.authoring.plan import ProjectWorkflow
from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

type ChangeSetValidator = Callable[
    [WriteTransaction, ProjectReadContext, Mapping[str, Any]],
    Awaitable[ValidatedProjectChangeSet],
]

_AUTHORING_WORKFLOWS = frozenset(
    {
        "analysis",
        "conceptual",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
        "validation",
    }
)


class WorkflowChangeSetDatabase(Protocol):
    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class WorkflowChangeSetHandoffResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: int = Field(gt=0)
    workflow_run_id: int = Field(gt=0)
    project_change_set_id: UUID
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

    def __init__(self, issues: tuple[ProjectValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__(
            code="workflow_change_set_validation_failed",
            message="Authoritative Project Change Set validation failed.",
        )


class WorkflowChangeSetFinalizer(Protocol):
    async def retain_failed_candidate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageProjectChange, ...],
        issues: tuple[ProjectValidationIssue, ...],
        failure_code: str,
        safe_failure_message: str,
    ) -> object: ...

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageProjectChange, ...],
        final_event: AgentWorkflowEvent,
    ) -> WorkflowChangeSetFinalizationResult: ...


class WorkflowChangeSetHandoff:
    """Create or replay one draft, with optional atomic Run completion."""

    def __init__(
        self,
        *,
        database: WorkflowChangeSetDatabase,
        authorizer: AuthorizationService,
        validator: ChangeSetValidator | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._validator = validator or partial(
            validate_locked_project_change_set, enforce_row_limits=False
        )

    async def handoff(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageProjectChange, ...],
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
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                expected_workflow=expected_workflow,
                expected_project_revision=expected_project_revision,
                staged=staged,
                staged_record_count=staged_record_count,
            )

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageProjectChange, ...],
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
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                expected_workflow=expected_workflow,
                expected_project_revision=expected_project_revision,
                staged=staged,
                staged_record_count=staged_record_count,
            )
            await append_agent_workflow_event(
                transaction,
                principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                event=final_event,
            )
            completion = await complete_agent_workflow_run(
                transaction,
                principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                finding_count=staged_record_count,
            )
            return WorkflowChangeSetFinalizationResult(
                handoff=handoff,
                completion=completion,
            )

    async def retain_failed_candidate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageProjectChange, ...],
        issues: tuple[ProjectValidationIssue, ...],
        failure_code: str,
        safe_failure_message: str,
    ) -> AgentWorkflowTerminalResult:
        """Retain a canonical rejected draft and fail its Run in one transaction."""
        if not issues:
            raise InvalidRequestError("Failed draft retention requires validation findings.")
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
            current, project, _replayed = await self._stage_in_transaction(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                expected_workflow=expected_workflow,
                expected_project_revision=expected_project_revision,
                staged=staged,
                staged_record_count=staged_record_count,
            )
            if current["project_change_set_status"] != "active":
                raise InvalidRequestError("Only an active rejected draft can be retained.")
            if project.project_revision != expected_project_revision:
                raise ProjectRevisionConflictError()
            validation = await self._validator(transaction, project, current)
            if validation.valid:
                raise InvalidRequestError("The candidate no longer fails authoritative validation.")
            repository = PostgresProjectChangeSetRepository(transaction)
            change_set_id = current["project_change_set_id"]
            retained = await repository.record_validation(
                change_set_id=change_set_id,
                status="active",
                candidate_digest=None,
                outcome=project_validation_outcome(validation),
                valid=False,
            )
            if retained is None:
                raise DependencyUnavailableError()
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type="validation_failed",
                draft_revision=retained["draft_revision"],
                section=None,
                action_count=staged_record_count,
                outcome="invalid",
                metadata={"phase": validation.phase, "error_count": len(validation.issues)},
                correlation_id=current["correlation_id"],
            )
            return await fail_agent_workflow_run(
                transaction,
                principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                failure_code=failure_code,
                safe_failure_message=safe_failure_message,
            )

    async def _stage_in_transaction(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        staged: dict[str, list[dict[str, object]]],
        staged_record_count: int,
    ) -> tuple[Mapping[str, Any], ProjectReadContext, bool]:
        repository = PostgresProjectChangeSetRepository(transaction)
        project_row = await repository.get_project_for_update(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if project_row is None:
            raise ProjectNotFoundError()

        authorization = await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=ToolPolicy.TENANT_PROJECT_WRITE,
            project_id=project_id,
        )
        source_tenants = authorization.readable_source_tenant_ids
        principal_id = authorization.principal.principal_id
        if principal_id is None:
            raise AuthorizationDeniedError()

        run = await repository.get_workflow_run_for_update(
            workflow_run_id=workflow_run_id,
            project_id=project_id,
        )
        if run is None:
            raise WorkflowRunNotFoundError()
        if run["actor_principal_id"] != principal_id:
            raise AuthorizationDeniedError()
        if run["project_workflow"] != expected_workflow:
            raise InvalidRequestError(
                "Workflow Run does not match the requested authoring workflow."
            )
        if run["workflow_execution_mode"] is None and expected_workflow not in {
            "code_generation",
            "validation",
        }:
            raise InvalidRequestError(
                "A deterministic Workflow Run cannot author a Project Change Set."
            )
        correlation_id = run["correlation_id"]
        if not isinstance(correlation_id, UUID):
            raise DependencyUnavailableError()

        project = ProjectReadContext(
            project_id=project_row["project_id"],
            tenant_id=project_row["tenant_id"],
            project_name=project_row["project_name"],
            project_revision=project_row["project_revision"],
            readable_source_tenant_ids=source_tenants,
        )

        existing = await repository.get_by_workflow_run(
            workflow_run_id=workflow_run_id,
            project_id=project_id,
        )
        if existing is not None:
            if existing["created_by_principal_id"] != principal_id:
                raise AuthorizationDeniedError()
            if (
                existing["base_project_revision"] != expected_project_revision
                or existing["correlation_id"] != correlation_id
            ):
                raise DependencyUnavailableError()
            if pending_project_change_set_datasets(existing) != staged:
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
            return existing, project, True

        if run["workflow_run_state"] != "running":
            raise InvalidRequestError(
                "Workflow Run must be running before Project Change Set handoff."
            )
        if project_row["project_revision"] != expected_project_revision:
            raise ProjectRevisionConflictError()

        change_set = await repository.create(
            change_set_id=uuid4(),
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            principal_id=principal_id,
            correlation_id=correlation_id,
        )
        if change_set is None:
            raise DependencyUnavailableError()
        change_set_id = change_set["project_change_set_id"]
        if not isinstance(change_set_id, UUID):
            raise DependencyUnavailableError()

        await repository.insert_event(
            change_set_id=change_set_id,
            project_id=project_id,
            event_type="created",
            draft_revision=change_set["draft_revision"],
            section=None,
            action_count=0,
            outcome="created",
            metadata={},
            correlation_id=correlation_id,
        )

        documents = project_change_set_documents(change_set)
        for dataset, records in staged.items():
            section = DATASETS_BY_NAME[dataset].section
            documents[section][dataset] = records
        validate_project_change_set_document_bounds(documents)
        staged_row = await repository.stage_documents(
            documents=documents,
            change_set_id=change_set_id,
        )
        if staged_row is None:
            raise DependencyUnavailableError()
        await repository.insert_event(
            change_set_id=change_set_id,
            project_id=project_id,
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
            project_id=project_id,
            for_update=True,
        )
        if current is None:
            raise DependencyUnavailableError()
        return current, project, False

    async def _handoff_in_transaction(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_project_revision: int,
        staged: dict[str, list[dict[str, object]]],
        staged_record_count: int,
    ) -> WorkflowChangeSetHandoffResult:
        current, project, replayed = await self._stage_in_transaction(
            transaction,
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            expected_workflow=expected_workflow,
            expected_project_revision=expected_project_revision,
            staged=staged,
            staged_record_count=staged_record_count,
        )
        if replayed:
            return self._result(
                current, project_id=project_id, workflow_run_id=workflow_run_id, replayed=True
            )
        repository = PostgresProjectChangeSetRepository(transaction)
        change_set_id = current["project_change_set_id"]
        correlation_id = current["correlation_id"]
        validation = await self._validator(transaction, project, current)
        if not validation.valid:
            raise WorkflowChangeSetValidationError(validation.issues)
        if validation.candidate_digest is None:
            raise DependencyUnavailableError()

        validated = await repository.record_validation(
            change_set_id=change_set_id,
            status="validated",
            candidate_digest=validation.candidate_digest,
            outcome=project_validation_outcome(validation),
            valid=True,
        )
        if validated is None:
            raise DependencyUnavailableError()
        await repository.insert_event(
            change_set_id=change_set_id,
            project_id=project_id,
            event_type="validated",
            draft_revision=validated["draft_revision"],
            section=None,
            action_count=sum(len(records) for records in validation.records.values()),
            outcome="valid",
            metadata={"phase": validation.phase, "error_count": 0},
            correlation_id=correlation_id,
        )

        return WorkflowChangeSetHandoffResult(
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            project_change_set_id=change_set_id,
            replayed=False,
            draft_revision=validated["draft_revision"],
            candidate_digest=validation.candidate_digest,
            staged_record_count=staged_record_count,
            validated_at=require_datetime(validated, "validated_time"),
        )

    @staticmethod
    def _validate_changes(
        *,
        expected_workflow: ProjectWorkflow,
        changes: tuple[StageProjectChange, ...],
    ) -> tuple[dict[str, list[dict[str, object]]], int]:
        if expected_workflow not in _AUTHORING_WORKFLOWS:
            raise InvalidRequestError(
                "This Workflow does not produce an authoring Project Change Set."
            )
        if not changes or any(not change.records for change in changes):
            raise InvalidRequestError(
                "A Workflow Project Change Set requires at least one changed record."
            )
        if any(DATASETS_BY_NAME[change.dataset].section != expected_workflow for change in changes):
            raise InvalidRequestError(
                "Workflow output contains a dataset from another authoring section."
            )
        staged = validate_project_stage_changes(list(changes))
        return staged, sum(len(records) for records in staged.values())

    @staticmethod
    def _result(
        row: Mapping[str, Any],
        *,
        project_id: int,
        workflow_run_id: int,
        replayed: bool,
    ) -> WorkflowChangeSetHandoffResult:
        if row["project_change_set_status"] != "validated":
            raise DependencyUnavailableError()
        candidate_digest = row["candidate_digest"]
        if not isinstance(candidate_digest, str):
            raise DependencyUnavailableError()
        return WorkflowChangeSetHandoffResult(
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            project_change_set_id=row["project_change_set_id"],
            replayed=replayed,
            draft_revision=row["draft_revision"],
            candidate_digest=candidate_digest,
            staged_record_count=sum(
                len(records) for records in pending_project_change_set_datasets(row).values()
            ),
            validated_at=require_datetime(row, "validated_time"),
        )


__all__ = [
    "WorkflowChangeSetFinalizationResult",
    "WorkflowChangeSetFinalizer",
    "WorkflowChangeSetHandoff",
    "WorkflowChangeSetHandoffResult",
    "WorkflowChangeSetValidationError",
]
