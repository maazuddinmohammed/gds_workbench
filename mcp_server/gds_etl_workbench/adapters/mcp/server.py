"""MCP server composition and non-tool routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.tools.tenants.list_tenants import register_list_tenants_tool


def create_mcp_server(
    settings: RuntimeSettings,
    database: Database,
    identity_provider: IdentityProvider,
) -> MCPServer[None]:
    @asynccontextmanager
    async def lifespan(_server: MCPServer[None]) -> AsyncIterator[None]:
        await database.open()
        with suppress(DependencyUnavailableError):
            await database.expire_tenant_locks()
        expiry_task = asyncio.create_task(_expire_tenant_locks(database))
        try:
            yield None
        finally:
            expiry_task.cancel()
            with suppress(asyncio.CancelledError):
                await expiry_task
            await database.close()

    server = MCPServer[None](
        name="gds-etl-workbench",
        title="GDS ETL Workbench",
        version="0.1.0",
        description="Governed metadata access for GDS ETL Workbench.",
        instructions=(
            "Check /health/ready before use. This scaffold exposes one read-only tool: "
            "list_tenants. Tenant visibility and roles are always resolved server-side."
        ),
        lifespan=lifespan,
    )

    register_list_tenants_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
        cursor_signing_key=settings.cursor_signing_key,
    )

    @server.custom_route("/health/live", methods=["GET"])
    async def live(_request: Request) -> Response:
        return JSONResponse(
            {"status": "live"},
            headers={"Cache-Control": "no-store"},
        )

    @server.custom_route("/health/ready", methods=["GET"])
    async def ready(_request: Request) -> Response:
        readiness = await database.readiness()
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


async def _expire_tenant_locks(database: Database) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await database.expire_tenant_locks()
        except DependencyUnavailableError:
            continue
