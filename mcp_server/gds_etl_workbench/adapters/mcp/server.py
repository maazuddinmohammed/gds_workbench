"""MCP server composition and non-tool routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    register_get_metadata_snapshot_tool,
    register_metadata_snapshot_download_route,
)
from gds_etl_workbench.tools.snapshots.metadata.storage import (
    AzureMetadataSnapshotStore,
    MetadataSnapshotStore,
)
from gds_etl_workbench.tools.tenants.list_tenants import register_list_tenants_tool

from .tool_audit import ToolCallAuditMiddleware


def create_mcp_server(
    settings: RuntimeSettings,
    database: Database,
    identity_provider: IdentityProvider,
    metadata_snapshot_store: MetadataSnapshotStore | None = None,
) -> MCPServer[None]:
    snapshot_store = metadata_snapshot_store or AzureMetadataSnapshotStore(settings)

    @asynccontextmanager
    async def lifespan(_server: MCPServer[None]) -> AsyncGenerator[None, None]:
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
            await snapshot_store.close()
            await database.close()

    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](
        name="gds-etl-workbench",
        title="GDS ETL Workbench",
        version="0.1.0",
        description="Governed metadata access for GDS ETL Workbench.",
        instructions=(
            "Check /health/ready before use. Read-only tools list authorized Tenants and "
            "create protected Metadata Snapshot downloads. Tenant visibility and roles "
            "are always resolved server-side."
        ),
        lifespan=lifespan,
        middleware=[audit],
    )

    register_list_tenants_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_get_metadata_snapshot_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        store=snapshot_store,
        retention_hours=settings.metadata_snapshot_retention_hours,
        max_archive_bytes=settings.metadata_snapshot_max_archive_bytes,
    )
    register_metadata_snapshot_download_route(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        store=snapshot_store,
        download_ttl_seconds=settings.metadata_snapshot_download_ttl_seconds,
    )

    async def live(_request: Request) -> Response:
        return JSONResponse(
            {"status": "live"},
            headers={"Cache-Control": "no-store"},
        )

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

    async def oauth_protected_resource_metadata(_request: Request) -> Response:
        return JSONResponse(
            {
                "resource": settings.mcp_public_url,
                "authorization_servers": [
                    f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
                ],
                "scopes_supported": [f"api://{settings.entra_api_client_id}/workbench.access"],
                "bearer_methods_supported": ["header"],
            },
            headers={"Cache-Control": "public, max-age=300"},
        )

    server.custom_route("/health/live", methods=["GET"])(live)
    server.custom_route("/health/ready", methods=["GET"])(ready)
    server.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(
        oauth_protected_resource_metadata
    )
    server.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])(
        oauth_protected_resource_metadata
    )
    return server


async def _expire_tenant_locks(database: Database) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await database.expire_tenant_locks()
        except DependencyUnavailableError:
            continue
