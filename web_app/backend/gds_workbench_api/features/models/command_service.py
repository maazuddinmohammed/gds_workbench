"""Governed complete-Model command authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Never, Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from psycopg.types.json import Jsonb

from gds_workbench_api.capabilities import AgentCapabilityRegistry
from gds_workbench_api.features.models.command_contracts import (
    ArchiveModelRequest,
    CompleteModelRequest,
    JsonObject,
    ModelCommandResult,
    ModelRevisionConflictError,
    UpdateModelRequest,
)
from gds_workbench_api.features.models.contracts import ModelNotFoundError

_CREATE_MODEL_SQL = """
SELECT created.model_id,
       created.tenant_id,
       created.model_revision,
       created.is_active,
       created.updated_time AS updated_at
  FROM application.create_model(
       %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s
  ) AS created
"""

_MODEL_OWNER_SQL = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_UPDATE_MODEL_SQL = """
SELECT updated.model_id,
       updated.tenant_id,
       updated.model_revision,
       updated.is_active,
       updated.updated_time AS updated_at
  FROM application.update_model(
       %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s, %s
  ) AS updated
"""

_ARCHIVE_MODEL_SQL = """
SELECT archived.model_id,
       archived.tenant_id,
       archived.model_revision,
       archived.is_active,
       archived.updated_time AS updated_at
  FROM application.archive_model(%s, %s, %s, %s, %s) AS archived
"""


class ModelCommandService(Protocol):
    async def create_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        request: CompleteModelRequest,
    ) -> ModelCommandResult: ...

    async def update_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        request: UpdateModelRequest,
    ) -> ModelCommandResult: ...

    async def archive_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        request: ArchiveModelRequest,
    ) -> ModelCommandResult: ...


class ModelCommandDatabase(Protocol):
    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseModelCommandService:
    def __init__(
        self,
        *,
        database: ModelCommandDatabase,
        authorizer: AuthorizationService,
        agent_capability_registry: AgentCapabilityRegistry,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._agent_capability_registry = agent_capability_registry

    async def create_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        request: CompleteModelRequest,
    ) -> ModelCommandResult:
        selection = request.agent_selection()
        if selection is not None:
            self._agent_capability_registry.validate_selection(selection)

        try:
            async with self._database.write_transaction() as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_MODEL_WRITE,
                )
                entra_tenant_id, entra_object_id, principal_type = _identity_triple(principal)
                row = await transaction.fetch_one(
                    _CREATE_MODEL_SQL,
                    (
                        entra_tenant_id,
                        entra_object_id,
                        principal_type,
                        tenant_id,
                    )
                    + _complete_model_parameters(request),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ModelCommandResult.model_validate(row, strict=True)

    async def update_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        request: UpdateModelRequest,
    ) -> ModelCommandResult:
        selection = request.agent_selection()
        if selection is not None:
            self._agent_capability_registry.validate_selection(selection)

        try:
            async with self._database.write_transaction() as transaction:
                identity = await self._authorize_owned_model(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                )
                row = await transaction.fetch_one(
                    _UPDATE_MODEL_SQL,
                    identity
                    + (model_id, request.expected_model_revision)
                    + _complete_model_parameters(request),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ModelCommandResult.model_validate(row, strict=True)

    async def archive_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        request: ArchiveModelRequest,
    ) -> ModelCommandResult:
        try:
            async with self._database.write_transaction() as transaction:
                identity = await self._authorize_owned_model(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                )
                row = await transaction.fetch_one(
                    _ARCHIVE_MODEL_SQL,
                    identity + (model_id, request.expected_model_revision),
                )
        except Exception as error:
            _raise_safe_command_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ModelCommandResult.model_validate(row, strict=True)

    async def _authorize_owned_model(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> tuple[UUID, UUID, str]:
        await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=ToolPolicy.TENANT_MODEL_WRITE,
        )
        owner = await transaction.fetch_one(_MODEL_OWNER_SQL, (tenant_id, model_id))
        if owner is None:
            raise ModelNotFoundError()
        return _identity_triple(principal)


def _identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type


def _as_jsonb(value: JsonObject | None) -> Jsonb | None:
    return None if value is None else Jsonb(value)


def _complete_model_parameters(request: CompleteModelRequest) -> tuple[object, ...]:
    return (
        request.model_name,
        request.model_description,
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
    )


def _raise_safe_command_error(error: Exception) -> Never:
    if isinstance(error, WorkbenchError) and not isinstance(error, DependencyUnavailableError):
        raise error

    message = _primary_database_message(error)
    if message == "stale_model_revision":
        raise ModelRevisionConflictError() from error
    if message == "Model is unavailable":
        raise ModelNotFoundError() from error
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
        "Model creation denied: ",
        "Model update denied: ",
        "Model archive denied: ",
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
