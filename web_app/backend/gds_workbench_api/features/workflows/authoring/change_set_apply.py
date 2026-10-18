"""Explicitly apply one completed authoring run's validated draft."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import validate_locked_project_change_set
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DependencyUnavailableError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ProjectChangeSetNotActiveError,
    ProjectChangeSetNotFoundError,
    ProjectChangeSetNotValidatedError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.project_change_sets.repository import (
    PostgresProjectChangeSetRepository,
    require_datetime,
)
from gds_workbench_api.features.projects import ProjectNotFoundError, ProjectRevisionConflictError
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

_EXPLICIT_APPLY_WORKFLOWS = frozenset(
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
_MODELESS_APPLY_WORKFLOWS = frozenset({"code_generation", "validation"})


class ApplyWorkflowDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_project_revision: int = Field(gt=0)
    expected_draft_revision: int = Field(gt=0)
    expected_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApplyWorkflowDraftResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    project_id: int = Field(gt=0)
    workflow_run_id: int = Field(gt=0)
    project_change_set_id: UUID
    replayed: bool
    draft_revision: int = Field(gt=0)
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_count: int = Field(ge=0)
    project_revision: int = Field(gt=0)
    applied_at: datetime


class WorkflowDraftApplyDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseWorkflowDraftApplyService:
    """Review fences and atomically apply one supported authoring draft."""

    def __init__(
        self,
        *,
        database: WorkflowDraftApplyDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        command: ApplyWorkflowDraftRequest,
        idempotency_key: UUID,
    ) -> ApplyWorkflowDraftResult:
        async with self._database.write_transaction() as transaction:
            repository = PostgresProjectChangeSetRepository(transaction)
            project_row = await repository.get_project(
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if project_row is None:
                raise ProjectNotFoundError()

            read_authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            source_tenants = read_authorization.readable_source_tenant_ids
            principal_id = read_authorization.principal.principal_id
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
            project_workflow = run["project_workflow"]
            execution_mode = run["workflow_execution_mode"]
            if project_workflow not in _EXPLICIT_APPLY_WORKFLOWS or (
                (project_workflow in _MODELESS_APPLY_WORKFLOWS) != (execution_mode is None)
            ):
                raise InvalidRequestError(
                    "Only a completed Analysis, Conceptual, Logical, Dimensional, "
                    "Mapping, Code Generation, or Validation authoring run with its expected "
                    "execution-mode shape can use this apply path."
                )
            if run["workflow_run_state"] not in {
                "completed",
                "completed_with_repair",
            }:
                raise InvalidRequestError(
                    "Workflow Run must be completed before its draft can be applied."
                )

            object_output_template_id = run["mapping_object_output_template_id"]
            attribute_output_template_id = run["mapping_attribute_output_template_id"]
            if (
                object_output_template_id is not None
                and not isinstance(object_output_template_id, int)
            ) or (
                attribute_output_template_id is not None
                and not isinstance(attribute_output_template_id, int)
            ):
                raise DependencyUnavailableError()
            row = await repository.get_by_workflow_run(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
            )
            if row is None:
                raise ProjectChangeSetNotFoundError()
            if row["created_by_principal_id"] != principal_id:
                raise AuthorizationDeniedError()
            if row["correlation_id"] != run["correlation_id"]:
                raise DependencyUnavailableError()
            self._require_fences(row, command)
            change_set_id = row["project_change_set_id"]
            if not isinstance(change_set_id, UUID):
                raise DependencyUnavailableError()

            if row["project_change_set_status"] == "applied":
                return await self._replay(
                    repository,
                    row=row,
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                    change_set_id=change_set_id,
                    idempotency_key=idempotency_key,
                )
            if row["project_change_set_status"] != "validated":
                raise ProjectChangeSetNotValidatedError()
            if require_datetime(row, "expires_time") <= require_datetime(
                row,
                "database_time",
            ):
                raise ProjectChangeSetNotActiveError()
            if project_row["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()

            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            source_tenants = authorization.readable_source_tenant_ids
            project = ProjectReadContext(
                project_id=project_row["project_id"],
                tenant_id=project_row["tenant_id"],
                project_name=project_row["project_name"],
                project_revision=project_row["project_revision"],
                readable_source_tenant_ids=source_tenants,
            )
            validation = await validate_locked_project_change_set(
                transaction, project, row, enforce_row_limits=False
            )
            if not validation.valid or validation.candidate_digest is None:
                raise CandidateDigestConflictError()
            if validation.candidate_digest != command.expected_candidate_digest:
                raise CandidateDigestConflictError()

            materializer = ProjectMaterializer.for_workflow_apply(
                transaction=transaction,
                project_id=project_id,
                source_context_digest=row["base_source_context_digest"],
                workflow_run_id=workflow_run_id,
                project_workflow=project_workflow,
                mapping_object_output_template_id=object_output_template_id,
                mapping_attribute_output_template_id=attribute_output_template_id,
            )
            action_count = await materializer.apply(validation.records)
            revision = await repository.advance_project_revision(
                project_id=project_id,
                expected_project_revision=command.expected_project_revision,
                changed=action_count > 0,
            )
            if revision is None:
                raise ProjectRevisionConflictError()
            applied = await repository.mark_workflow_applied(
                change_set_id=change_set_id,
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                draft_revision=command.expected_draft_revision,
                candidate_digest=command.expected_candidate_digest,
            )
            if applied is None:
                raise DependencyUnavailableError()
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type="applied",
                draft_revision=command.expected_draft_revision,
                section=None,
                action_count=action_count,
                outcome="applied",
                metadata={"project_revision": revision["project_revision"]},
                correlation_id=idempotency_key,
            )
            return ApplyWorkflowDraftResult(
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                project_change_set_id=change_set_id,
                replayed=False,
                draft_revision=command.expected_draft_revision,
                candidate_digest=command.expected_candidate_digest,
                action_count=action_count,
                project_revision=revision["project_revision"],
                applied_at=require_datetime(applied, "applied_time"),
            )

    @staticmethod
    def _require_fences(
        row: Mapping[str, Any],
        command: ApplyWorkflowDraftRequest,
    ) -> None:
        if row["base_project_revision"] != command.expected_project_revision:
            raise ProjectRevisionConflictError()
        if row["draft_revision"] != command.expected_draft_revision:
            current = row["draft_revision"]
            if not isinstance(current, int):
                raise DependencyUnavailableError()
            raise DraftRevisionConflictError(current)
        if row["candidate_digest"] != command.expected_candidate_digest:
            raise CandidateDigestConflictError()

    @staticmethod
    async def _replay(
        repository: PostgresProjectChangeSetRepository,
        *,
        row: Mapping[str, Any],
        project_id: int,
        workflow_run_id: int,
        change_set_id: UUID,
        idempotency_key: UUID,
    ) -> ApplyWorkflowDraftResult:
        event = await repository.get_applied_event(
            change_set_id=change_set_id,
            project_id=project_id,
        )
        if event is None or event["correlation_id"] != idempotency_key:
            raise InvalidRequestError("Idempotency key conflicts with the recorded draft apply.")
        raw_metadata = event["event_metadata"]
        if not isinstance(raw_metadata, Mapping):
            raise DependencyUnavailableError()
        metadata = cast(Mapping[str, object], raw_metadata)
        project_revision = metadata.get("project_revision")
        action_count = event["action_count"]
        if not isinstance(project_revision, int) or not isinstance(action_count, int):
            raise DependencyUnavailableError()
        candidate_digest = row["candidate_digest"]
        draft_revision = row["draft_revision"]
        if not isinstance(candidate_digest, str) or not isinstance(draft_revision, int):
            raise DependencyUnavailableError()
        return ApplyWorkflowDraftResult(
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            project_change_set_id=change_set_id,
            replayed=True,
            draft_revision=draft_revision,
            candidate_digest=candidate_digest,
            action_count=action_count,
            project_revision=project_revision,
            applied_at=require_datetime(row, "applied_time"),
        )


__all__ = [
    "ApplyWorkflowDraftRequest",
    "ApplyWorkflowDraftResult",
    "DatabaseWorkflowDraftApplyService",
    "WorkflowDraftApplyDatabase",
]
