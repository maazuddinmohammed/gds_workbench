"""Explicitly apply one completed authoring run's validated draft."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DependencyUnavailableError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ModelChangeSetNotActiveError,
    ModelChangeSetNotFoundError,
    ModelChangeSetNotValidatedError,
)
from gds_etl_workbench.domain.mapping_profiles import (
    resolve_mapping_profile_schema_digest,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets.model import validate_locked_model_change_set
from gds_etl_workbench.tools.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.model_change_sets.repository import (
    PostgresModelChangeSetRepository,
    require_datetime,
)
from gds_workbench_api.features.models import ModelNotFoundError, ModelRevisionConflictError
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

_EXPLICIT_APPLY_WORKFLOWS = frozenset(
    {"analysis", "conceptual", "logical", "dimensional", "mapping"}
)


class ApplyWorkflowDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)
    expected_draft_revision: int = Field(gt=0)
    expected_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApplyWorkflowDraftResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    workflow_run_id: int = Field(gt=0)
    model_change_set_id: UUID
    replayed: bool
    draft_revision: int = Field(gt=0)
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_count: int = Field(ge=0)
    model_revision: int = Field(gt=0)
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
        model_id: int,
        workflow_run_id: int,
        command: ApplyWorkflowDraftRequest,
        idempotency_key: UUID,
    ) -> ApplyWorkflowDraftResult:
        async with self._database.write_transaction() as transaction:
            repository = PostgresModelChangeSetRepository(transaction)
            model_row = await repository.get_model(
                tenant_id=tenant_id,
                model_id=model_id,
            )
            if model_row is None:
                raise ModelNotFoundError()

            read_authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            principal_id = read_authorization.principal.principal_id
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
            if (
                run["model_workflow"] not in _EXPLICIT_APPLY_WORKFLOWS
                or run["workflow_execution_mode"] is None
            ):
                raise InvalidRequestError(
                    "Only a completed Analysis, Conceptual, Logical, Dimensional, or "
                    "Mapping authoring run can use this apply path."
                )
            if run["workflow_run_state"] not in {
                "completed",
                "completed_with_repair",
            }:
                raise InvalidRequestError(
                    "Workflow Run must be completed before its draft can be applied."
                )

            model_workflow = run["model_workflow"]
            object_output_template_id = run["mapping_object_output_template_id"]
            attribute_output_template_id = run["mapping_attribute_output_template_id"]
            if (
                not isinstance(model_workflow, str)
                or (
                    object_output_template_id is not None
                    and not isinstance(object_output_template_id, int)
                )
                or (
                    attribute_output_template_id is not None
                    and not isinstance(attribute_output_template_id, int)
                )
            ):
                raise DependencyUnavailableError()
            if model_workflow == "mapping":
                profile_key = run["mapping_profile_key"]
                profile_version = run["mapping_profile_version"]
                profile_schema_digest = run["mapping_profile_schema_digest"]
                if not all(
                    isinstance(value, str)
                    for value in (
                        profile_key,
                        profile_version,
                        profile_schema_digest,
                    )
                ):
                    raise DependencyUnavailableError()
                try:
                    resolved_profile_digest = resolve_mapping_profile_schema_digest(
                        profile_key,
                        profile_version,
                    )
                except ValueError:
                    raise DependencyUnavailableError() from None
                if resolved_profile_digest != profile_schema_digest:
                    raise DependencyUnavailableError()

            row = await repository.get_by_workflow_run(
                workflow_run_id=workflow_run_id,
                model_id=model_id,
            )
            if row is None:
                raise ModelChangeSetNotFoundError()
            if row["created_by_principal_id"] != principal_id:
                raise AuthorizationDeniedError()
            if row["correlation_id"] != run["correlation_id"]:
                raise DependencyUnavailableError()
            self._require_fences(row, command)
            change_set_id = row["model_change_set_id"]
            if not isinstance(change_set_id, UUID):
                raise DependencyUnavailableError()

            if row["model_change_set_status"] == "applied":
                return await self._replay(
                    repository,
                    row=row,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    change_set_id=change_set_id,
                    idempotency_key=idempotency_key,
                )
            if row["model_change_set_status"] != "validated":
                raise ModelChangeSetNotValidatedError()
            if require_datetime(row, "expires_time") <= require_datetime(
                row,
                "database_time",
            ):
                raise ModelChangeSetNotActiveError()
            if model_row["model_revision"] != command.expected_model_revision:
                raise ModelRevisionConflictError()

            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            model = ModelReadContext(
                model_id=model_row["model_id"],
                tenant_id=model_row["tenant_id"],
                model_name=model_row["model_name"],
                model_revision=model_row["model_revision"],
            )
            validation = await validate_locked_model_change_set(transaction, model, row)
            if not validation.valid or validation.candidate_digest is None:
                raise CandidateDigestConflictError()
            if validation.candidate_digest != command.expected_candidate_digest:
                raise CandidateDigestConflictError()

            materializer = ModelMaterializer.for_workflow_apply(
                transaction=transaction,
                model_id=model_id,
                source_context_digest=row["base_source_context_digest"],
                workflow_run_id=workflow_run_id,
                model_workflow=model_workflow,
                mapping_object_output_template_id=object_output_template_id,
                mapping_attribute_output_template_id=attribute_output_template_id,
            )
            action_count = await materializer.apply(validation.records)
            revision = await repository.advance_model_revision(
                model_id=model_id,
                expected_model_revision=command.expected_model_revision,
                changed=action_count > 0,
            )
            if revision is None:
                raise ModelRevisionConflictError()
            applied = await repository.mark_workflow_applied(
                change_set_id=change_set_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                draft_revision=command.expected_draft_revision,
                candidate_digest=command.expected_candidate_digest,
            )
            if applied is None:
                raise DependencyUnavailableError()
            await repository.insert_event(
                change_set_id=change_set_id,
                model_id=model_id,
                event_type="applied",
                draft_revision=command.expected_draft_revision,
                section=None,
                action_count=action_count,
                outcome="applied",
                metadata={"model_revision": revision["model_revision"]},
                correlation_id=idempotency_key,
            )
            return ApplyWorkflowDraftResult(
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                model_change_set_id=change_set_id,
                replayed=False,
                draft_revision=command.expected_draft_revision,
                candidate_digest=command.expected_candidate_digest,
                action_count=action_count,
                model_revision=revision["model_revision"],
                applied_at=require_datetime(applied, "applied_time"),
            )

    @staticmethod
    def _require_fences(
        row: Mapping[str, Any],
        command: ApplyWorkflowDraftRequest,
    ) -> None:
        if row["base_model_revision"] != command.expected_model_revision:
            raise ModelRevisionConflictError()
        if row["draft_revision"] != command.expected_draft_revision:
            current = row["draft_revision"]
            if not isinstance(current, int):
                raise DependencyUnavailableError()
            raise DraftRevisionConflictError(current)
        if row["candidate_digest"] != command.expected_candidate_digest:
            raise CandidateDigestConflictError()

    @staticmethod
    async def _replay(
        repository: PostgresModelChangeSetRepository,
        *,
        row: Mapping[str, Any],
        model_id: int,
        workflow_run_id: int,
        change_set_id: UUID,
        idempotency_key: UUID,
    ) -> ApplyWorkflowDraftResult:
        event = await repository.get_applied_event(
            change_set_id=change_set_id,
            model_id=model_id,
        )
        if event is None or event["correlation_id"] != idempotency_key:
            raise InvalidRequestError("Idempotency key conflicts with the recorded draft apply.")
        raw_metadata = event["event_metadata"]
        if not isinstance(raw_metadata, Mapping):
            raise DependencyUnavailableError()
        metadata = cast(Mapping[str, object], raw_metadata)
        model_revision = metadata.get("model_revision")
        action_count = event["action_count"]
        if not isinstance(model_revision, int) or not isinstance(action_count, int):
            raise DependencyUnavailableError()
        candidate_digest = row["candidate_digest"]
        draft_revision = row["draft_revision"]
        if not isinstance(candidate_digest, str) or not isinstance(draft_revision, int):
            raise DependencyUnavailableError()
        return ApplyWorkflowDraftResult(
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            model_change_set_id=change_set_id,
            replayed=True,
            draft_revision=draft_revision,
            candidate_digest=candidate_digest,
            action_count=action_count,
            model_revision=model_revision,
            applied_at=require_datetime(row, "applied_time"),
        )


__all__ = [
    "ApplyWorkflowDraftRequest",
    "ApplyWorkflowDraftResult",
    "DatabaseWorkflowDraftApplyService",
    "WorkflowDraftApplyDatabase",
]
