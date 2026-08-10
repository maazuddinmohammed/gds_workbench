"""Complete list_tenants vertical slice: contract, SQL, policy, and MCP binding."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    ResolvedPrincipal,
)
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import ActorKind, TenantRole, ToolPolicy
from gds_etl_workbench.domain.errors import AuthorizationDeniedError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadTransaction

_COLLECTION = "list_tenants"
POLICY = ToolPolicy.TENANT_READ

_AUTHORIZED_TENANTS_SQL = """
WITH actor (principal_id, is_super_admin) AS (
    VALUES (%s::BIGINT, %s::BOOLEAN)
)
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility,
       CASE
           WHEN actor.is_super_admin THEN 'super_admin'
           WHEN membership.tenant_role IS NOT NULL THEN membership.tenant_role
           ELSE 'viewer'
       END AS effective_role
  FROM actor
 CROSS JOIN core.tenant AS tenant
  LEFT JOIN security.tenant_principal_access AS membership
    ON membership.tenant_id = tenant.tenant_id
   AND membership.principal_id = actor.principal_id
   AND membership.is_active
   AND (
       membership.access_expires_time IS NULL
       OR membership.access_expires_time > CURRENT_TIMESTAMP
   )
 WHERE tenant.is_active
   AND (
       actor.is_super_admin
       OR tenant.tenant_visibility = 'global'
       OR membership.tenant_id IS NOT NULL
   )
 ORDER BY lower(tenant.tenant_name), tenant.tenant_id
 LIMIT %s OFFSET %s
"""

_DEV_TENANTS_SQL = """
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility,
       'development' AS effective_role
  FROM core.tenant AS tenant
 WHERE tenant.is_active
 ORDER BY lower(tenant.tenant_name), tenant.tenant_id
 LIMIT %s OFFSET %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListTenantsRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


class TenantSummary(ContractModel):
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)
    tenant_description: str | None = Field(default=None, max_length=2000)
    tenant_visibility: Literal["global", "private"]
    effective_role: TenantRole


class ListTenantsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenants: tuple[TenantSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_list_tenants_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    cursor_signing_key: bytes,
) -> None:
    """Register list_tenants with its explicit shared dependencies."""
    cursors = CursorCodec(cursor_signing_key)

    @server.tool(
        description=(
            "List active Tenants the current Principal can read. Global Tenants are "
            "visible to every active registered Principal; private Tenants require current "
            "Tenant access. Super admins can read every active Tenant."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def list_tenants(
        ctx: Context[None],
        schema_version: Literal["1.0"] = "1.0",
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
    ) -> ListTenantsResult:
        """List the Tenant summaries visible to the current Principal."""
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            request = ListTenantsRequest(
                schema_version=schema_version,
                page_size=page_size,
                cursor=cursor,
            )
            offset = cursors.decode(request.cursor, collection=_COLLECTION)
            async with database.read_transaction() as transaction:
                actor = await authorizer.resolve_principal(transaction, principal)
                rows = await _query_visible_tenants(
                    transaction,
                    actor,
                    limit=request.page_size + 1,
                    offset=offset,
                )
            tenants = tuple(
                TenantSummary(
                    tenant_id=row["tenant_id"],
                    tenant_code=row["tenant_code"],
                    tenant_name=row["tenant_name"],
                    tenant_description=row["tenant_description"],
                    tenant_visibility=row["tenant_visibility"],
                    effective_role=TenantRole(row["effective_role"]),
                )
                for row in rows[: request.page_size]
            )
            next_cursor = None
            if len(rows) > request.page_size:
                next_cursor = cursors.encode(
                    collection=_COLLECTION,
                    offset=offset + request.page_size,
                )
            return ListTenantsResult(tenants=tenants, next_cursor=next_cursor)
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None


async def _query_visible_tenants(
    transaction: ReadTransaction,
    principal: ResolvedPrincipal,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    if principal.actor_kind is ActorKind.DEVELOPMENT:
        return await transaction.fetch_all(_DEV_TENANTS_SQL, (limit, offset))
    if principal.principal_id is None:
        raise AuthorizationDeniedError()
    return await transaction.fetch_all(
        _AUTHORIZED_TENANTS_SQL,
        (
            principal.principal_id,
            principal.is_super_admin,
            limit,
            offset,
        ),
    )
