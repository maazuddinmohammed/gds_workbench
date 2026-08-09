"""Thin MCP binding for the catalog feature."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.ports import StateRepository
from gds_etl_workbench.catalog.feature import CatalogFeature
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.contracts.catalog import ListTenantsRequest, ListTenantsResult
from gds_etl_workbench.domain.errors import WorkbenchError


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: RuntimeSettings
    identity_provider: IdentityProvider
    catalog: CatalogFeature


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def create_mcp_server(
    settings: RuntimeSettings,
    repository: StateRepository,
    identity_provider: IdentityProvider,
) -> MCPServer[AppContext]:
    catalog = CatalogFeature(repository, CursorCodec(settings.cursor_signing_key))

    @asynccontextmanager
    async def lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
        await repository.open()
        try:
            yield AppContext(
                settings=settings,
                identity_provider=identity_provider,
                catalog=catalog,
            )
        finally:
            await repository.close()

    server = MCPServer[AppContext](
        name="gds-etl-workbench",
        title="GDS ETL Workbench",
        version="0.1.0",
        description="Read-only governed metadata access for GDS ETL Workbench.",
        instructions=(
            "Check /health/ready before use. This scaffold exposes one read-only tool: "
            "list_tenants. Tenant visibility and roles are always resolved server-side."
        ),
        lifespan=lifespan,
    )

    @server.tool(
        description=(
            "List active Tenants the current human Principal can read. Global Tenants are "
            "visible to every active registered Principal; private Tenants require current "
            "Tenant access. Super admins can read every active Tenant."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def list_tenants(
        ctx: Context[AppContext],
        schema_version: Literal["1.0"] = "1.0",
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
    ) -> ListTenantsResult:
        """List the Tenant summaries visible to the current human Principal."""
        app_context = ctx.request_context.lifespan_context
        try:
            principal = app_context.identity_provider.authenticate(ctx.headers)
            request = ListTenantsRequest(
                schema_version=schema_version,
                page_size=page_size,
                cursor=cursor,
            )
            return await app_context.catalog.list_tenants(principal, request)
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    @server.custom_route("/health/live", methods=["GET"])
    async def live(_request: Request) -> Response:
        return JSONResponse(
            {"status": "live"},
            headers={"Cache-Control": "no-store"},
        )

    @server.custom_route("/health/ready", methods=["GET"])
    async def ready(_request: Request) -> Response:
        readiness = await repository.readiness()
        return JSONResponse(
            {
                "status": "ready" if readiness.ready else "not_ready",
                "code": readiness.code,
                "schema_version": settings.schema_version,
            },
            status_code=200 if readiness.ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    return server
