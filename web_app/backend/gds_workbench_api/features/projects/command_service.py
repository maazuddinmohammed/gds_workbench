"""Governed complete-Project command authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Never, Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
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
from gds_workbench_api.features.projects.command_contracts import (
    ArchiveProjectRequest,
    CompleteProjectRequest,
    JsonObject,
    ProjectCommandResult,
    ProjectNameConflictError,
    ProjectRevisionConflictError,
    ProjectSchemaConflictError,
    SetProjectLockRequest,
    UpdateProjectRequest,
)
from gds_workbench_api.features.projects.contracts import ProjectNotFoundError

_CREATE_PROJECT_SQL = """
SELECT created.project_id,
       created.tenant_id,
       created.project_revision,
       created.is_active,
       created.updated_time AS updated_at
  FROM application.create_project(
       %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
  ) AS created
"""

_PROJECT_OWNER_SQL = """
SELECT target_project.project_revision
  FROM project.project AS target_project
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
"""

_UPDATE_PROJECT_SQL = """
SELECT updated.project_id,
       updated.tenant_id,
       updated.project_revision,
       updated.is_active,
       updated.updated_time AS updated_at
  FROM application.update_project(
       %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
  ) AS updated
"""

_ARCHIVE_PROJECT_SQL = """
SELECT archived.project_id,
       archived.tenant_id,
       archived.project_revision,
       archived.is_active,
       archived.updated_time AS updated_at
  FROM application.archive_project(%s, %s, %s, %s, %s) AS archived
"""


class ProjectCommandService(Protocol):
    async def set_project_lock(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: SetProjectLockRequest,
    ) -> ProjectCommandResult: ...

    async def create_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        request: CompleteProjectRequest,
    ) -> ProjectCommandResult: ...

    async def update_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: UpdateProjectRequest,
    ) -> ProjectCommandResult: ...

    async def archive_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: ArchiveProjectRequest,
    ) -> ProjectCommandResult: ...


class ProjectCommandDatabase(Protocol):
    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseProjectCommandService:
    def __init__(
        self,
        *,
        database: ProjectCommandDatabase,
        authorizer: AuthorizationService,
        agent_capability_registry: AgentCapabilityRegistry,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._agent_capability_registry = agent_capability_registry

    async def set_project_lock(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: SetProjectLockRequest,
    ) -> ProjectCommandResult:
        if principal.actor_kind is not ActorKind.HUMAN:
            raise AuthorizationDeniedError()
        identity = _identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    "SELECT project_id, tenant_id, project_revision, is_active, "
                    "updated_time AS updated_at "
                    "FROM application.set_project_lock(%s,%s,%s,%s,%s,%s)",
                    (
                        identity[0],
                        identity[1],
                        tenant_id,
                        project_id,
                        request.expected_project_revision,
                        request.is_locked,
                    ),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ProjectCommandResult.model_validate(row, strict=True)

    async def create_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        request: CompleteProjectRequest,
    ) -> ProjectCommandResult:
        selection = request.agent_selection()
        if selection is not None:
            self._agent_capability_registry.validate_selection(selection)

        try:
            async with self._database.write_transaction() as transaction:
                authorization = await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_PROJECT_WRITE,
                )
                if authorization.effective_role not in (
                    TenantRole.TENANT_ADMIN,
                    TenantRole.SUPER_ADMIN,
                ):
                    raise AuthorizationDeniedError()
                entra_tenant_id, entra_object_id, principal_type = _identity_triple(principal)
                row = await transaction.fetch_one(
                    _CREATE_PROJECT_SQL,
                    (
                        entra_tenant_id,
                        entra_object_id,
                        principal_type,
                        tenant_id,
                    )
                    + _complete_project_parameters(request),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ProjectCommandResult.model_validate(row, strict=True)

    async def update_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: UpdateProjectRequest,
    ) -> ProjectCommandResult:
        selection = request.agent_selection()
        if selection is not None:
            self._agent_capability_registry.validate_selection(selection)

        try:
            async with self._database.write_transaction() as transaction:
                identity = await self._authorize_owned_project(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                row = await transaction.fetch_one(
                    _UPDATE_PROJECT_SQL,
                    identity
                    + (project_id, request.expected_project_revision)
                    + _complete_project_parameters(request),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ProjectCommandResult.model_validate(row, strict=True)

    async def archive_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: ArchiveProjectRequest,
    ) -> ProjectCommandResult:
        try:
            async with self._database.write_transaction() as transaction:
                identity = await self._authorize_owned_project(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                row = await transaction.fetch_one(
                    _ARCHIVE_PROJECT_SQL,
                    identity + (project_id, request.expected_project_revision),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ProjectCommandResult.model_validate(row, strict=True)

    async def _authorize_owned_project(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> tuple[UUID, UUID, str]:
        await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=ToolPolicy.TENANT_PROJECT_WRITE,
            project_id=project_id,
        )
        owner = await transaction.fetch_one(_PROJECT_OWNER_SQL, (tenant_id, project_id))
        if owner is None:
            raise ProjectNotFoundError()
        return _identity_triple(principal)


def _identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type


def _as_jsonb(value: JsonObject | None) -> Jsonb | None:
    return None if value is None else Jsonb(value)


def _complete_project_parameters(request: CompleteProjectRequest) -> tuple[object, ...]:
    return (
        request.project_name,
        request.project_description,
        Jsonb([item.model_dump() for item in request.logical_schemas]),
        Jsonb([item.model_dump() for item in request.dimensional_schemas]),
        request.silver_model_naming_instructions,
        _as_jsonb(request.silver_model_audit_columns_template),
        request.gold_model_naming_instructions,
        _as_jsonb(request.gold_model_technical_columns_template),
        _as_jsonb(request.gold_model_audit_columns_template),
        request.default_agent_sdk_code,
        request.default_agent_provider_code,
        request.default_agent_model_code,
        request.default_reasoning_effort_code,
        request.default_max_turns,
        request.default_validation_retry_count,
        request.default_mapping_source_system_id,
        request.logical_entity_scd_type,
        request.dimensional_entity_scd_type,
        request.logical_coverage_threshold_percent,
        request.dimensional_coverage_threshold_percent,
        request.logical_enforce_coverage_threshold,
        request.dimensional_enforce_coverage_threshold,
    )


def _raise_safe_command_error(error: Exception) -> Never:
    if isinstance(error, WorkbenchError) and not isinstance(error, DependencyUnavailableError):
        raise error

    cause: BaseException | None = error
    for _ in range(4):
        if cause is None:
            break
        if (
            getattr(cause, "sqlstate", None) == "23505"
            and getattr(getattr(cause, "diag", None), "constraint_name", None)
            == "ux_project_tenant_name_ci"
        ):
            raise ProjectNameConflictError() from error
        cause = cause.__cause__

    message = _primary_database_message(error)
    if message == "stale_project_revision":
        raise ProjectRevisionConflictError() from error
    if message == "A referenced Project schema cannot be removed or renamed":
        raise ProjectSchemaConflictError() from error
    if message == "Default Mapping System is unavailable for this Tenant":
        raise InvalidRequestError(
            "Choose an active default Mapping System with a Connection in this Tenant."
        ) from error
    if message == "Project is unavailable":
        raise ProjectNotFoundError() from error
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
        cause = current.__cause__
        if cause is None:
            return str(current)
        current = cause
    return ""


def _controlled_denial_code(message: str) -> str | None:
    prefixes = (
        "Project lock denied: ",
        "Project creation denied: ",
        "Project update denied: ",
        "Project archive denied: ",
    )
    for prefix in prefixes:
        if message.startswith(prefix):
            code = message.removeprefix(prefix)
            if code in {
                "tenant_not_found",
                "tenant_lock_required",
                "tenant_locked",
                "authorization_denied",
            }:
                return code
    return None
