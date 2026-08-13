"""Governed Tenant Lock MCP tools and their fixed database calls."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Annotated, Any, Literal, LiteralString, Protocol
from uuid import UUID

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import Database, WriteTransaction

POLICY = ToolPolicy.TENANT_LOCK_MANAGE
_CHECK_TOOL = "check_tenant_lock"
_ACQUIRE_TOOL = "acquire_tenant_lock"
_RENEW_TOOL = "renew_tenant_lock"
_RELEASE_TOOL = "release_tenant_lock"
_OVERRIDE_TOOL = "override_tenant_lock"

_CHECK_SQL: LiteralString = """
SELECT authorized,
       denial_code,
       is_locked,
       owner_display_name,
       owned_by_current_principal,
       purpose,
       acquired_time,
       expires_time
  FROM security.check_tenant_lock(%s, %s, %s, %s)
"""

_ACQUIRE_SQL: LiteralString = """
SELECT acquired,
       denial_code,
       owner_display_name,
       purpose,
       acquired_time,
       expires_time
  FROM security.acquire_tenant_lock(%s, %s, %s, %s, %s, %s)
"""

_RENEW_SQL: LiteralString = """
SELECT renewed,
       denial_code,
       owner_display_name,
       purpose,
       acquired_time,
       expires_time
  FROM security.renew_tenant_lock(%s, %s, %s, %s, %s)
"""

_RELEASE_SQL: LiteralString = """
SELECT released,
       denial_code,
       owner_display_name,
       acquired_time,
       expires_time
  FROM security.release_tenant_lock(%s, %s, %s, %s)
"""

_OVERRIDE_SQL: LiteralString = """
SELECT overridden,
       denial_code,
       previous_owner_display_name,
       previous_owned_by_current_principal,
       previous_purpose,
       previous_acquired_time,
       previous_expires_time
  FROM security.override_tenant_lock(%s, %s, %s, %s, %s)
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TenantLockDetails(ContractModel):
    owner_display_name: str = Field(min_length=1, max_length=200)
    owned_by_current_principal: bool
    purpose: str | None = Field(default=None, max_length=500)
    acquired_at: datetime
    expires_at: datetime


class CheckTenantLockResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    is_locked: bool
    lock: TenantLockDetails | None


class AcquireTenantLockResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    acquired: Literal[True] = True
    lock: TenantLockDetails


class RenewTenantLockResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    renewed: Literal[True] = True
    lock: TenantLockDetails


class ReleaseTenantLockResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    released: Literal[True] = True
    is_locked: Literal[False] = False


class OverrideTenantLockResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    overridden: Literal[True] = True
    is_locked: Literal[False] = False
    previous_lock: TenantLockDetails


class TenantLockToolError(Exception):
    """A bounded tool failure safe for MCP serialization."""


class TenantLockDatabase(Database, Protocol):
    """Database capabilities needed only by governed Tenant Lock tools."""

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


def register_tenant_lock_tools(
    server: MCPServer[None],
    *,
    database: TenantLockDatabase,
    identity_provider: IdentityProvider,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Check whether one authorized Tenant currently has an active Tenant Lock. "
            "Returns only bounded owner display and timing details."
        ),
        annotations=_annotations(read_only=True, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def check_tenant_lock(
        ctx: Context[None],
        tenant_id: Annotated[
            int,
            Field(gt=0, le=9_223_372_036_854_775_807),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> CheckTenantLockResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.read_transaction() as transaction:
                row = await transaction.fetch_one(
                    _CHECK_SQL,
                    (*identity_arguments, tenant_id),
                )
            _raise_authorization_denial(row)
            assert row is not None
            is_locked = row["is_locked"] is True
            lock = (
                _lock_details(
                    row,
                    owned_by_current_principal=row["owned_by_current_principal"],
                )
                if is_locked
                else None
            )
            return CheckTenantLockResult(
                tenant_id=tenant_id,
                is_locked=is_locked,
                lock=lock,
            )
        except AuthenticationError as error:
            raise TenantLockToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise TenantLockToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise TenantLockToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _CHECK_TOOL,
        policy=POLICY,
        summarize_input=_tenant_audit,
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Acquire an unlocked Tenant for the current Principal. Fails when any "
            "active lock exists; use renew_tenant_lock for a lock you already own."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def acquire_tenant_lock(
        ctx: Context[None],
        tenant_id: Annotated[
            int,
            Field(gt=0, le=9_223_372_036_854_775_807),
        ],
        duration_minutes: Annotated[int, Field(ge=1, le=240)] = 60,
        purpose: Annotated[str | None, Field(max_length=500)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> AcquireTenantLockResult:
        del schema_version
        try:
            if purpose is not None and not purpose.strip():
                raise InvalidRequestError("Lock purpose must be nonblank when provided.")
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _ACQUIRE_SQL,
                    (
                        *identity_arguments,
                        tenant_id,
                        duration_minutes,
                        purpose,
                    ),
                )
            _raise_lock_operation_denial(row, success_field="acquired")
            assert row is not None
            return AcquireTenantLockResult(
                tenant_id=tenant_id,
                lock=_lock_details(row, owned_by_current_principal=True),
            )
        except AuthenticationError as error:
            raise TenantLockToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise TenantLockToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise TenantLockToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _ACQUIRE_TOOL,
        policy=POLICY,
        summarize_input=_acquire_audit,
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Renew the current Principal's active Tenant Lock. Fails when no active "
            "lock exists or another Principal owns it."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def renew_tenant_lock(
        ctx: Context[None],
        tenant_id: Annotated[
            int,
            Field(gt=0, le=9_223_372_036_854_775_807),
        ],
        duration_minutes: Annotated[int, Field(ge=1, le=240)] = 60,
        schema_version: Literal["1.0"] = "1.0",
    ) -> RenewTenantLockResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _RENEW_SQL,
                    (*identity_arguments, tenant_id, duration_minutes),
                )
            _raise_lock_operation_denial(row, success_field="renewed")
            assert row is not None
            return RenewTenantLockResult(
                tenant_id=tenant_id,
                lock=_lock_details(row, owned_by_current_principal=True),
            )
        except AuthenticationError as error:
            raise TenantLockToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise TenantLockToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise TenantLockToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _RENEW_TOOL,
        policy=POLICY,
        summarize_input=_renew_audit,
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Release the current Principal's active Tenant Lock. Fails when no active "
            "lock exists or another Principal owns it."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def release_tenant_lock(
        ctx: Context[None],
        tenant_id: Annotated[
            int,
            Field(gt=0, le=9_223_372_036_854_775_807),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ReleaseTenantLockResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _RELEASE_SQL,
                    (*identity_arguments, tenant_id),
                )
            _raise_lock_operation_denial(row, success_field="released")
            return ReleaseTenantLockResult(tenant_id=tenant_id)
        except AuthenticationError as error:
            raise TenantLockToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise TenantLockToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise TenantLockToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _RELEASE_TOOL,
        policy=POLICY,
        summarize_input=_tenant_audit,
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Force-release another Principal's active Tenant Lock. Requires an audit "
            "reason and does not acquire a replacement lock."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def override_tenant_lock(
        ctx: Context[None],
        tenant_id: Annotated[
            int,
            Field(gt=0, le=9_223_372_036_854_775_807),
        ],
        reason: Annotated[str, Field(min_length=1, max_length=2000)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> OverrideTenantLockResult:
        del schema_version
        try:
            if not reason.strip():
                raise InvalidRequestError("Lock override reason must be nonblank.")
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _OVERRIDE_SQL,
                    (*identity_arguments, tenant_id, reason),
                )
            _raise_override_denial(row)
            assert row is not None
            return OverrideTenantLockResult(
                tenant_id=tenant_id,
                previous_lock=TenantLockDetails(
                    owner_display_name=row["previous_owner_display_name"],
                    owned_by_current_principal=False,
                    purpose=row["previous_purpose"],
                    acquired_at=row["previous_acquired_time"],
                    expires_at=row["previous_expires_time"],
                ),
            )
        except AuthenticationError as error:
            raise TenantLockToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise TenantLockToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise TenantLockToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _OVERRIDE_TOOL,
        policy=POLICY,
        summarize_input=_override_audit,
        tenant_argument="tenant_id",
    )


def _identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    expected_type = "user" if principal.actor_kind is ActorKind.HUMAN else "service_principal"
    return principal.entra_tenant_id, principal.entra_object_id, expected_type


def _raise_authorization_denial(row: Mapping[str, Any] | None) -> None:
    if row is None:
        raise AuthorizationDeniedError()
    if row["authorized"] is True:
        return
    if row["denial_code"] == "tenant_not_found":
        raise TenantNotFoundError()
    raise AuthorizationDeniedError()


def _raise_lock_operation_denial(
    row: Mapping[str, Any] | None,
    *,
    success_field: str,
) -> None:
    if row is None:
        raise AuthorizationDeniedError()
    if row[success_field] is True:
        return
    if row["denial_code"] == "tenant_not_found":
        raise TenantNotFoundError()
    if row["denial_code"] == "tenant_locked":
        raise TenantLockedError(row["owner_display_name"] or "another Principal")
    if row["denial_code"] == "tenant_lock_required":
        raise TenantLockRequiredError()
    raise AuthorizationDeniedError()


def _raise_override_denial(row: Mapping[str, Any] | None) -> None:
    if row is None:
        raise AuthorizationDeniedError()
    if row["overridden"] is True:
        return
    if row["denial_code"] == "tenant_not_found":
        raise TenantNotFoundError()
    if row["denial_code"] == "tenant_lock_required":
        raise InvalidRequestError("Tenant is not currently locked.")
    if row["denial_code"] == "tenant_locked" and row["previous_owned_by_current_principal"] is True:
        raise InvalidRequestError(
            "The current Principal owns this Tenant Lock; use release_tenant_lock."
        )
    raise AuthorizationDeniedError()


def _lock_details(
    row: Mapping[str, Any],
    *,
    owned_by_current_principal: bool,
) -> TenantLockDetails:
    return TenantLockDetails(
        owner_display_name=row["owner_display_name"],
        owned_by_current_principal=owned_by_current_principal,
        purpose=row["purpose"],
        acquired_at=row["acquired_time"],
        expires_at=row["expires_time"],
    )


def _tenant_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    raw_tenant_id = arguments.get("tenant_id")
    tenant_id: int | str = (
        raw_tenant_id
        if type(raw_tenant_id) is int and 0 < raw_tenant_id <= 9_223_372_036_854_775_807
        else "invalid"
    )
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "tenant_id": tenant_id,
    }


def _acquire_audit(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    summary: dict[str, str | int | bool] = _tenant_audit(arguments)
    raw_duration = arguments.get("duration_minutes", 60)
    summary["duration_minutes"] = (
        raw_duration if type(raw_duration) is int and 1 <= raw_duration <= 240 else "invalid"
    )
    raw_purpose = arguments.get("purpose")
    summary["has_purpose"] = isinstance(raw_purpose, str) and bool(raw_purpose.strip())
    return summary


def _renew_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    summary = _tenant_audit(arguments)
    raw_duration = arguments.get("duration_minutes", 60)
    summary["duration_minutes"] = (
        raw_duration if type(raw_duration) is int and 1 <= raw_duration <= 240 else "invalid"
    )
    return summary


def _override_audit(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    summary: dict[str, str | int | bool] = _tenant_audit(arguments)
    raw_reason = arguments.get("reason")
    summary["has_reason"] = isinstance(raw_reason, str) and bool(raw_reason.strip())
    return summary


def _annotations(
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
) -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=False,
    )
