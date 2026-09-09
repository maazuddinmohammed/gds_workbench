"""Complete list_tenants vertical slice: contract, SQL, policy, and MCP binding."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import (
    AuthorizationService,
)
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.tenants import query_visible_tenants
from gds_etl_workbench.domain.authorization import TenantRole, ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import (
    Database,
    ReadIsolation,
)

_COLLECTION = "list_tenants"
POLICY = ToolPolicy.TENANT_READ


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
    audit: ToolCallAuditMiddleware,
    cursor_signing_key: bytes,
) -> None:
    """Register list_tenants with its explicit shared dependencies."""
    cursors = CursorCodec(cursor_signing_key)

    @server.tool(
        name=_COLLECTION,
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
    async def _list_tenants(
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
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                actor = await authorizer.resolve_principal(transaction, principal)
                rows = await query_visible_tenants(
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

    del _list_tenants
    audit.register_tool(
        _COLLECTION,
        policy=POLICY,
        summarize_input=_audit_input_metadata,
        retain_arguments={"schema_version", "page_size"},
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    raw_schema_version = arguments.get("schema_version", "1.0")
    raw_page_size = arguments.get("page_size", 50)
    schema_version = "1.0" if raw_schema_version == "1.0" else "invalid"
    page_size: int | str = (
        raw_page_size if type(raw_page_size) is int and 1 <= raw_page_size <= 200 else "invalid"
    )
    return {
        "schema_version": schema_version,
        "page_size": page_size,
        "cursor_provided": arguments.get("cursor") is not None,
    }
