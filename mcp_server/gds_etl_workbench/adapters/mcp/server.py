"""MCP server composition and non-tool routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import cast

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gds_etl_workbench import __version__
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import (
    Database,
    DatabricksConnectionDatabase,
    WriteDatabase,
)
from gds_etl_workbench.tools.catalog.inspect_metadata import (
    register_inspect_metadata_tool,
)
from gds_etl_workbench.tools.change_sets.metadata import (
    register_metadata_change_set_tools,
)
from gds_etl_workbench.tools.change_sets.model import register_model_change_set_tools
from gds_etl_workbench.tools.databricks.execute_sql import (
    register_execute_databricks_sql_tool,
)
from gds_etl_workbench.tools.databricks.executor import (
    ConnectorDatabricksSqlExecutor,
    DatabricksSqlExecutor,
)
from gds_etl_workbench.tools.modeling.model_details import register_list_models_tool
from gds_etl_workbench.tools.modeling.model_input_scope import (
    register_get_model_input_scope_tool,
)
from gds_etl_workbench.tools.modeling.read_model_section import (
    register_read_model_section_tool,
)
from gds_etl_workbench.tools.snapshots.dbml.get_model_dbml import (
    register_export_model_dbml_tool,
)
from gds_etl_workbench.tools.snapshots.metadata.describe_metadata_dataset import (
    register_describe_metadata_dataset_tool,
)
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    register_create_metadata_snapshot_tool,
)
from gds_etl_workbench.tools.snapshots.model.describe_model_dataset import (
    register_describe_model_dataset_tool,
)
from gds_etl_workbench.tools.snapshots.model.get_model_snapshot import (
    register_create_model_snapshot_tool,
)
from gds_etl_workbench.tools.snapshots.storage import AzureSnapshotStore, SnapshotStore
from gds_etl_workbench.tools.tenants.get_tenant_details import (
    register_get_tenant_details_tool,
)
from gds_etl_workbench.tools.tenants.list_tenants import register_list_tenants_tool
from gds_etl_workbench.tools.tenants.tenant_locks import register_tenant_lock_tools

from .tool_audit import ToolCallAuditMiddleware

MCP_SERVER_VERSION = __version__


def create_mcp_server(
    settings: RuntimeSettings,
    database: Database,
    identity_provider: IdentityProvider,
    snapshot_store: SnapshotStore | None = None,
    databricks_executor: DatabricksSqlExecutor | None = None,
) -> MCPServer[None]:
    shared_snapshot_store = snapshot_store or AzureSnapshotStore(settings)
    sql_executor = databricks_executor or ConnectorDatabricksSqlExecutor()

    @asynccontextmanager
    async def lifespan(_server: MCPServer[None]) -> AsyncGenerator[None]:
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
            await shared_snapshot_store.close()
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
        version=MCP_SERVER_VERSION,
        description="Governed GDS context, Snapshot, and Change Set workflows.",
        instructions=(
            "Use focused reads for bounded questions and Snapshots for broad authoring or "
            "applied Code and Validation context. Reads and local drafts require no lock. "
            "A clear user acknowledgement of the exact local result authorizes acquiring an "
            "ordinary free Tenant Lock, reconciliation, Stage, and Change Set validation; do "
            "not ask again before those actions. Lock override and Apply require separate "
            "explicit approval. Model Input Scope must Apply before Profiling or model "
            "development. Metadata registration must Apply before Model Binding; Binding must "
            "Apply before Mapping; Mapping must Apply before Code or Validation. Refresh the "
            "affected Snapshot after Apply. On revision mismatch, stop and reassess against a "
            "fresh Snapshot without auto-merge. Release any lock acquired here when work stops. "
            "The server derives identity and authorization. Summarize safe results; never copy "
            "credentials, signed URLs, raw rows, prompts, SQL, or raw tool output into chat. "
            "The user may manually download a Snapshot from its client tool result. "
            "execute_databricks_sql defaults to environment_code=dev, requires qualified "
            "persistent relations, and permits only reads or unqualified temporary objects."
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
    register_get_tenant_details_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_list_models_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_get_model_input_scope_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_tenant_lock_tools(
        server,
        database=cast(WriteDatabase, database),
        identity_provider=identity_provider,
        audit=audit,
    )
    register_metadata_change_set_tools(
        server,
        database=cast(WriteDatabase, database),
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_model_change_set_tools(
        server,
        database=cast(WriteDatabase, database),
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_inspect_metadata_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_read_model_section_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_execute_databricks_sql_tool(
        server,
        database=cast(DatabricksConnectionDatabase, database),
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        executor=sql_executor,
        max_rows=settings.databricks_sql_max_rows,
        timeout_seconds=settings.databricks_sql_timeout_seconds,
    )
    register_describe_model_dataset_tool(
        server,
        identity_provider=identity_provider,
        audit=audit,
    )
    register_create_model_snapshot_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        store=shared_snapshot_store,
        download_ttl_seconds=settings.metadata_snapshot_download_ttl_seconds,
        retention_hours=settings.metadata_snapshot_retention_hours,
        max_archive_bytes=settings.metadata_snapshot_max_archive_bytes,
    )
    register_export_model_dbml_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        store=shared_snapshot_store,
        download_ttl_seconds=settings.metadata_snapshot_download_ttl_seconds,
        retention_hours=settings.metadata_snapshot_retention_hours,
        max_archive_bytes=settings.metadata_snapshot_max_archive_bytes,
    )
    register_describe_metadata_dataset_tool(
        server,
        identity_provider=identity_provider,
        audit=audit,
    )
    register_create_metadata_snapshot_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        store=shared_snapshot_store,
        download_ttl_seconds=settings.metadata_snapshot_download_ttl_seconds,
        retention_hours=settings.metadata_snapshot_retention_hours,
        max_archive_bytes=settings.metadata_snapshot_max_archive_bytes,
    )

    async def live(_request: Request) -> Response:
        return JSONResponse(
            {"status": "live"},
            headers={"Cache-Control": "no-store"},
        )

    async def ready(_request: Request) -> Response:
        readiness = await database.readiness()
        tools = await server.list_tools()
        return JSONResponse(
            {
                "status": "ready" if readiness.ready else "not_ready",
                "code": readiness.code,
                "schema_version": settings.schema_version,
                "mcp_server_version": MCP_SERVER_VERSION,
                "tool_count": len(tools),
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
                "scopes_supported": [f"{settings.mcp_public_url}/workbench.access"],
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
