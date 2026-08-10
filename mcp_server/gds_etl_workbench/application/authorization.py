"""Shared Principal resolution and Tenant policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import LiteralString

from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

_RESOLVE_PRINCIPAL_SQL: LiteralString = """
SELECT principal.principal_id,
       principal.principal_display_name,
       principal.is_super_admin
  FROM security.entra_principal_identity AS identity
  JOIN security.principal AS principal
    ON principal.principal_id = identity.principal_id
   AND principal.principal_type = identity.principal_type
 WHERE identity.entra_tenant_id = %s
   AND identity.entra_object_id = %s
   AND identity.principal_type = %s
   AND identity.is_active
   AND principal.is_active
   AND (
       identity.principal_type <> 'service_principal'
       OR principal.is_super_admin
   )
 FOR SHARE OF identity, principal
"""

_AUTHORIZE_TENANT_SQL: LiteralString = """
SELECT principal_id,
       principal_display_name,
       is_super_admin,
       effective_role,
       authorized,
       denial_code,
       lock_owner_display_name,
       lock_expires_time
  FROM security.authorize_tenant_operation(%s, %s, %s, %s, %s)
"""


@dataclass(frozen=True, slots=True)
class ResolvedPrincipal:
    principal_id: int | None
    actor_kind: ActorKind
    display_name: str
    is_super_admin: bool


@dataclass(frozen=True, slots=True)
class TenantAuthorization:
    principal: ResolvedPrincipal
    effective_role: TenantRole
    lock_expires_time: datetime | None


class AuthorizationService:
    """Resolve server-owned identity and enforce one declared tool policy."""

    async def resolve_principal(
        self,
        transaction: ReadTransaction,
        request_principal: RequestPrincipal,
    ) -> ResolvedPrincipal:
        if request_principal.actor_kind is ActorKind.DEVELOPMENT:
            return ResolvedPrincipal(
                principal_id=None,
                actor_kind=ActorKind.DEVELOPMENT,
                display_name="Local Developer",
                is_super_admin=True,
            )
        if request_principal.entra_tenant_id is None or request_principal.entra_object_id is None:
            raise AuthorizationDeniedError()

        expected_type = (
            "user" if request_principal.actor_kind is ActorKind.HUMAN else "service_principal"
        )
        row = await transaction.fetch_one(
            _RESOLVE_PRINCIPAL_SQL,
            (
                request_principal.entra_tenant_id,
                request_principal.entra_object_id,
                expected_type,
            ),
        )
        if row is None:
            raise AuthorizationDeniedError()
        return ResolvedPrincipal(
            principal_id=row["principal_id"],
            actor_kind=request_principal.actor_kind,
            display_name=row["principal_display_name"],
            is_super_admin=row["is_super_admin"],
        )

    async def authorize_tenant(
        self,
        transaction: ReadTransaction,
        request_principal: RequestPrincipal,
        *,
        tenant_id: int,
        policy: ToolPolicy,
    ) -> TenantAuthorization:
        if request_principal.actor_kind is ActorKind.DEVELOPMENT:
            if policy in (
                ToolPolicy.TENANT_METADATA_WRITE,
                ToolPolicy.TENANT_MODEL_WRITE,
            ):
                raise TenantLockRequiredError()
            return TenantAuthorization(
                principal=await self.resolve_principal(transaction, request_principal),
                effective_role=TenantRole.DEVELOPMENT,
                lock_expires_time=None,
            )
        if request_principal.entra_tenant_id is None or request_principal.entra_object_id is None:
            raise AuthorizationDeniedError()

        expected_type = (
            "user" if request_principal.actor_kind is ActorKind.HUMAN else "service_principal"
        )
        row = await transaction.fetch_one(
            _AUTHORIZE_TENANT_SQL,
            (
                request_principal.entra_tenant_id,
                request_principal.entra_object_id,
                expected_type,
                tenant_id,
                policy.value,
            ),
        )
        if row is None:
            raise AuthorizationDeniedError()
        if not row["authorized"]:
            denial_code = row["denial_code"]
            if denial_code == "tenant_not_found":
                raise TenantNotFoundError()
            if denial_code == "tenant_lock_required":
                raise TenantLockRequiredError()
            if denial_code == "tenant_locked":
                raise TenantLockedError(_safe_display_name(row["lock_owner_display_name"]))
            raise AuthorizationDeniedError()

        return TenantAuthorization(
            principal=ResolvedPrincipal(
                principal_id=row["principal_id"],
                actor_kind=request_principal.actor_kind,
                display_name=row["principal_display_name"],
                is_super_admin=row["is_super_admin"],
            ),
            effective_role=TenantRole(row["effective_role"]),
            lock_expires_time=row["lock_expires_time"],
        )


def _safe_display_name(value: object) -> str:
    if not isinstance(value, str):
        return "another Principal"
    normalized = " ".join(value.split())[:200]
    return normalized or "another Principal"
