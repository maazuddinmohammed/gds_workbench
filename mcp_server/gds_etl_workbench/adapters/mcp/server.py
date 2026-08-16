"""MCP server composition and non-tool routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import cast

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import (
    Database,
    DatabricksConnectionDatabase,
    WriteDatabase,
)
from gds_etl_workbench.tools.catalog.get_object_lineage import (
    register_get_object_lineage_tool,
)
from gds_etl_workbench.tools.catalog.get_objects import register_get_objects_tool
from gds_etl_workbench.tools.catalog.list_objects import register_list_objects_tool
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
from gds_etl_workbench.tools.ingestion.copy_groups import register_copy_group_tools
from gds_etl_workbench.tools.modeling.assertions import (
    register_modeling_assertion_tools,
)
from gds_etl_workbench.tools.modeling.conceptual import register_conceptual_tools
from gds_etl_workbench.tools.modeling.dimensional import register_dimensional_tools
from gds_etl_workbench.tools.modeling.logical import register_logical_tools
from gds_etl_workbench.tools.modeling.mapping import register_mapping_tools
from gds_etl_workbench.tools.modeling.model_details import register_get_model_tool
from gds_etl_workbench.tools.modeling.model_scope import register_get_model_scope_tool
from gds_etl_workbench.tools.modeling.profiling_analysis import (
    register_profiling_analysis_tools,
)
from gds_etl_workbench.tools.processing.process_groups import register_process_group_tools
from gds_etl_workbench.tools.snapshots.dbml.get_model_dbml import (
    register_get_model_dbml_tool,
)
from gds_etl_workbench.tools.snapshots.metadata.describe_metadata_dataset import (
    register_describe_metadata_dataset_tool,
)
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    register_get_metadata_snapshot_tool,
)
from gds_etl_workbench.tools.snapshots.model.describe_model_dataset import (
    register_describe_model_dataset_tool,
)
from gds_etl_workbench.tools.snapshots.model.get_model_snapshot import (
    register_get_model_snapshot_tool,
)
from gds_etl_workbench.tools.snapshots.storage import AzureSnapshotStore, SnapshotStore
from gds_etl_workbench.tools.tenants.get_tenant_details import (
    register_get_tenant_details_tool,
)
from gds_etl_workbench.tools.tenants.list_tenants import register_list_tenants_tool
from gds_etl_workbench.tools.tenants.tenant_locks import register_tenant_lock_tools

from .tool_audit import ToolCallAuditMiddleware


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
        version="0.1.0",
        description="Governed metadata access for GDS ETL Workbench.",
        instructions=(
            "Check /health/ready before use. Start with list_tenants, then use Tenant, "
            "Object, Copy Group, Process Group, or direct ingestion-lineage reads. Prefer "
            "these bounded summaries before requesting a protected Metadata Snapshot. "
            "Snapshots and local drafting need no Tenant Lock. For a metadata change, "
            "first get_metadata_snapshot and build and review the complete local draft. "
            "Only when it is ready for server work, check_tenant_lock and ask before "
            "acquire_tenant_lock. Then create_metadata_change_set, describe only needed "
            "dataset contracts, stage complete ID-free dataset lists atomically, and call "
            "validate_metadata_change_set. If create returns an existing "
            "Change Set, review every nonempty pending dataset before continuing. Apply only after "
            "review; apply_metadata_change_set revalidates atomically. Archive abandoned "
            "drafts. For modeling, use the focused Profiling, Analysis, Assertion, "
            "Conceptual, Logical, Dimensional, and Mapping reads when database IDs help "
            "navigation. Use get_model_snapshot for the complete ID-free state, or "
            "get_model_dbml for a governed conceptual, logical, dimensional, or full "
            "DBML archive with optional Submodel files. Before "
            "staging a Model dataset, call describe_model_dataset for its exact shared "
            "Snapshot/Change-Set schema. Then create, stage, validate, and apply the "
            "Model Change Set under an Architect-owned Tenant Lock. Each supplied Model "
            "dataset replaces only that pending dataset; omitted datasets remain untouched. "
            "Metadata get and archive enforce ownership but do not require a current lock. "
            "Use renew_tenant_lock only for your own lock. Release it when finished. "
            "override_tenant_lock only force-releases another owner's lock; it never "
            "acquires a replacement. Tenant identity, roles, and lock ownership are "
            "always resolved server-side. execute_databricks_sql accepts only reads and "
            "unqualified temporary views/tables on an active global Connection; it "
            "rejects DML and persistent DDL."
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
    register_get_model_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_get_model_scope_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
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
    register_list_objects_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_get_objects_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_get_object_lineage_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_copy_group_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_process_group_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_profiling_analysis_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_modeling_assertion_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_conceptual_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_logical_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_dimensional_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=settings.cursor_signing_key,
    )
    register_mapping_tools(
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
    register_get_model_snapshot_tool(
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
    register_get_model_dbml_tool(
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
    register_get_metadata_snapshot_tool(
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
