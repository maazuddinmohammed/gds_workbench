"""Governed, idempotent Workflow Run creation implementation."""

from contextlib import AbstractAsyncContextManager
from typing import Never, Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from psycopg.types.json import Jsonb

from gds_workbench_api.capabilities import AgentCapabilityRegistry
from gds_workbench_api.features.models import ModelNotFoundError, ModelRevisionConflictError
from gds_workbench_api.features.workflows.commands.contracts import (
    CreateWorkflowRunRequest,
    WorkflowRunCommandResult,
)

_MODEL_OWNER_SQL = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_CREATE_WORKFLOW_RUN_SQL = """
SELECT created.created,
       created.workflow_run_id,
       created.workflow_run_state,
       created.correlation_id,
       created.prompt_snapshot_count,
       created.model_revision,
       created.selected_scope_digest,
       created.selected_scope_count,
       created.code_generation_coverage_mode,
       created.sql_generation_guide_id,
       created.sql_generation_guide_version_id,
       created.sql_generation_guide_digest,
       created.created_time AS created_at
  FROM application.create_workflow_run(
       %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s
  ) AS created
"""


class WorkflowCommandService(Protocol):
    async def create_run(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        correlation_id: UUID,
        command: CreateWorkflowRunRequest,
    ) -> WorkflowRunCommandResult: ...


class WorkflowCommandDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseWorkflowCommandService:
    def __init__(
        self,
        *,
        database: WorkflowCommandDatabase,
        authorizer: AuthorizationService,
        agent_capability_registry: AgentCapabilityRegistry,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._agent_capability_registry = agent_capability_registry

    async def create_run(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        correlation_id: UUID,
        command: CreateWorkflowRunRequest,
    ) -> WorkflowRunCommandResult:
        if command.agent is not None:
            self._agent_capability_registry.validate_selection(command.agent)
        try:
            async with self._database.write_transaction() as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_MODEL_WRITE,
                )
                owner = await transaction.fetch_one(
                    _MODEL_OWNER_SQL,
                    (tenant_id, model_id),
                )
                if owner is None:
                    raise ModelNotFoundError()
                identity = _identity_triple(principal)
                agent = command.agent
                row = await transaction.fetch_one(
                    _CREATE_WORKFLOW_RUN_SQL,
                    identity
                    + (
                        model_id,
                        command.expected_model_revision,
                        command.model_workflow,
                        command.workflow_execution_mode,
                        None if agent is None else agent.sdk_code,
                        None if agent is None else agent.provider_code,
                        None if agent is None else agent.model_code,
                        None if agent is None else agent.reasoning_effort_code,
                        None if agent is None else agent.max_turns,
                        None if agent is None else agent.validation_retry_count,
                        command.selected_object_ids,
                        command.modeled_entity_type,
                        command.requested_batch_id,
                        correlation_id,
                        Jsonb(command.prompt_overrides),
                        command.mapping_operation,
                        command.mapping_coverage_mode,
                        command.mapping_artifact_type,
                        command.mapping_source_system_id,
                        command.mapping_object_output_template_id,
                        command.mapping_attribute_output_template_id,
                        command.code_generation_coverage_mode,
                        command.sql_generation_guide_version_id,
                    ),
                )
        except Exception as error:
            _raise_safe_workflow_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return WorkflowRunCommandResult.model_validate(row, strict=True)


def _identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type


def _raise_safe_workflow_error(error: Exception) -> Never:
    if isinstance(error, WorkbenchError) and not isinstance(
        error,
        DependencyUnavailableError,
    ):
        raise error
    message = _primary_database_message(error)
    if message == "stale_model_revision":
        raise ModelRevisionConflictError() from error
    if message in {
        "Workflow Run Model is unavailable",
        "Model is unavailable",
    }:
        raise ModelNotFoundError() from error
    if message in {
        "Selected Scope must contain between 1 and 50000 Objects",
        "Selected Scope Object IDs must be positive",
        "Selected Scope Object IDs must be unique",
        "Selected Scope contains an unavailable or ineligible Object",
        "Agent configuration is required for this Workflow Run",
        "Agent configuration override must be complete",
        "Deterministic Workflow Run cannot use agent configuration",
        "Deterministic Workflow Run cannot use prompt overrides",
        "No usable prompt is assigned to Workflow Stage",
        "Resolved prompt version is unavailable to the Model",
        "Workflow Run correlation conflict",
        "Mapping route is inferred by the server",
        "Mapping requires one complete selected target and source System pair",
        "Mapping inputs are unavailable for this Workflow Run",
        "Selected Mapping target has no preregistered header",
        "Selected Mapping target contains mixed modeled layers",
        "Selected Mapping target contains an unavailable or locked header",
        "Selected Mapping target is unavailable",
        "Selected Mapping target has a mixed or wrong-zone route",
        "Selected Mapping Object output template is unavailable",
        "Selected Mapping Attribute output template is unavailable",
    } or message.startswith("No usable prompt is assigned to Workflow Stage "):
        raise InvalidRequestError("The requested workflow run is invalid.") from error

    denial_code = _controlled_denial_code(message)
    if denial_code == "tenant_not_found":
        raise TenantNotFoundError() from error
    if denial_code == "tenant_lock_required":
        raise TenantLockRequiredError() from error
    if denial_code == "tenant_locked":
        raise TenantLockedError("another Principal") from error
    if denial_code == "authorization_denied":
        raise AuthorizationDeniedError() from error
    raise DependencyUnavailableError() from error


def _primary_database_message(error: Exception) -> str:
    current: BaseException = error
    for _ in range(4):
        diagnostic = getattr(current, "diag", None)
        primary = getattr(diagnostic, "message_primary", None)
        if isinstance(primary, str) and primary:
            return primary
        if current.__cause__ is None:
            return str(current)
        current = current.__cause__
    return ""


def _controlled_denial_code(message: str) -> str | None:
    prefix = "Workflow Run creation denied: "
    if not message.startswith(prefix):
        return None
    code = message.removeprefix(prefix)
    if code in {
        "tenant_not_found",
        "tenant_lock_required",
        "tenant_locked",
        "authorization_denied",
    }:
        return code
    return None
