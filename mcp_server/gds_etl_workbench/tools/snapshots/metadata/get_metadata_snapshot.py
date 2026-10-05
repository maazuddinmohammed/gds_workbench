"""MCP Metadata Snapshot creation and download adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.metadata_snapshot.archive import (
    EncodedDataset,
    SnapshotArchive,
    SnapshotPayloadTooLargeError,
    build_snapshot_archive,
)
from gds_etl_workbench.application.metadata_snapshot.selection import select_snapshot_datasets
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation
from gds_etl_workbench.tools.snapshots.service import (
    build_and_upload_snapshot,
    create_snapshot_download,
    create_snapshot_window,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotStore


@dataclass(frozen=True, slots=True)
class ReadyMetadataSnapshot:
    snapshot_id: UUID
    tenant_id: int
    created_at: datetime
    available_until: datetime
    size_bytes: int
    sha256: str


class MetadataSnapshotContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateMetadataSnapshotRequest(MetadataSnapshotContractModel):
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    schema_version: Literal["2.0"] = "2.0"
    source_tenant_ids: tuple[Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)], ...] = (
        Field(default=(), max_length=200)
    )


class CreateMetadataSnapshotResult(MetadataSnapshotContractModel):
    schema_version: Literal["2.0"] = "2.0"
    snapshot_id: UUID
    snapshot_kind: Literal["metadata"] = "metadata"
    status: Literal["ready"] = "ready"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    download_url: str = Field(min_length=1, max_length=2048)
    download_url_expires_at: datetime
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["application/zip"] = "application/zip"


class MetadataSnapshotToolError(Exception):
    """A bounded tool failure safe for MCP serialization."""


def register_create_metadata_snapshot_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
    store: SnapshotStore,
    download_ttl_seconds: int,
    retention_hours: int,
    max_archive_bytes: int,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Register the small descriptor-only Metadata Snapshot MCP tool."""
    current_time = clock or (lambda: datetime.now(UTC))

    tool_registration = server.tool(
        name="create_metadata_snapshot",
        description=(
            "Create a new complete, immutable Metadata Snapshot ZIP for one authorized "
            "Tenant, optionally including explicitly authorized Source Tenants as input context. "
            "Additional Source/Bronze metadata is read-only for this Tenant Change Set. "
            "The response contains bounded archive metadata "
            "and a temporary client download URL, never Snapshot rows. Download promptly and "
            "verify the returned Snapshot ID, byte size, and SHA-256 before installing it."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": ToolPolicy.TENANT_READ.value},
        structured_output=True,
    )

    async def create_metadata_snapshot_tool(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        schema_version: Literal["2.0"] = "2.0",
        source_tenant_ids: Annotated[
            tuple[Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)], ...],
            Field(max_length=200),
        ] = (),
    ) -> CreateMetadataSnapshotResult:
        try:
            request = CreateMetadataSnapshotRequest(
                tenant_id=tenant_id,
                schema_version=schema_version,
                source_tenant_ids=source_tenant_ids,
            )
            http_request = ctx.request_context.request
            principal = identity_provider.request_principal(http_request)
            ready = await create_metadata_snapshot(
                database,
                store,
                tenant_id=request.tenant_id,
                source_tenant_ids=request.source_tenant_ids,
                request_principal=principal,
                authorizer=authorizer,
                retention_hours=retention_hours,
                max_archive_bytes=max_archive_bytes,
                created_at=current_time(),
            )
            download_created_at = current_time()
            download = await create_snapshot_download(
                store,
                snapshot_kind="metadata",
                tenant_id=ready.tenant_id,
                scope_id=ready.tenant_id,
                schema_version="2.0",
                snapshot_id=ready.snapshot_id,
                created_at=ready.created_at,
                available_until=ready.available_until,
                now=download_created_at,
                ttl_seconds=download_ttl_seconds,
            )
            return CreateMetadataSnapshotResult(
                snapshot_id=ready.snapshot_id,
                tenant_id=ready.tenant_id,
                download_url=download.url,
                download_url_expires_at=download.expires_at,
                size_bytes=ready.size_bytes,
                sha256=ready.sha256,
            )
        except AuthenticationError as error:
            raise MetadataSnapshotToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataSnapshotToolError(f"{error.code}: {error.message}") from None
        except SnapshotPayloadTooLargeError:
            raise MetadataSnapshotToolError(
                "payload_too_large: The generated snapshot exceeds its configured limit."
            ) from None
        except Exception:
            raise MetadataSnapshotToolError(
                "internal_error: The operation could not be completed."
            ) from None

    tool_registration(create_metadata_snapshot_tool)
    audit.register_tool(
        "create_metadata_snapshot",
        policy=ToolPolicy.TENANT_READ,
        summarize_input=_audit_input_metadata,
        retain_arguments={"tenant_id", "schema_version"},
        tenant_argument="tenant_id",
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    raw_tenant_id = arguments.get("tenant_id")
    tenant_id: int | str = (
        raw_tenant_id
        if type(raw_tenant_id) is int and 0 < raw_tenant_id <= 9_223_372_036_854_775_807
        else "invalid"
    )
    return {
        "schema_version": "2.0" if arguments.get("schema_version", "2.0") == "2.0" else "invalid",
        "tenant_id": tenant_id,
    }


async def create_metadata_snapshot(
    database: Database,
    store: SnapshotStore,
    *,
    tenant_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
    retention_hours: int,
    max_archive_bytes: int,
    created_at: datetime | None = None,
    snapshot_id: UUID | None = None,
    source_tenant_ids: tuple[int, ...] = (),
) -> ReadyMetadataSnapshot:
    """Select, archive, upload, and clean up one immutable Metadata Snapshot."""
    window = create_snapshot_window(
        retention_hours=retention_hours,
        created_at=created_at,
        snapshot_id=snapshot_id,
    )

    async with database.read_transaction(isolation=ReadIsolation.REPEATABLE_READ) as transaction:
        selected = await select_snapshot_datasets(
            transaction,
            tenant_id=tenant_id,
            request_principal=request_principal,
            authorizer=authorizer,
            source_tenant_ids=source_tenant_ids,
        )

    return await build_and_upload_metadata_snapshot(
        selected.datasets,
        store,
        tenant_id=tenant_id,
        tenant_code=selected.tenant_code,
        snapshot_id=window.snapshot_id,
        created_at=window.created_at,
        available_until=window.available_until,
        max_archive_bytes=max_archive_bytes,
    )


async def build_and_upload_metadata_snapshot(
    encoded_datasets: Sequence[EncodedDataset],
    store: SnapshotStore,
    *,
    tenant_id: int,
    tenant_code: str,
    snapshot_id: UUID,
    created_at: datetime,
    available_until: datetime,
    max_archive_bytes: int,
) -> ReadyMetadataSnapshot:
    """Build and upload through the shared governed Snapshot service."""

    def build_archive(output: Path) -> SnapshotArchive:
        return build_snapshot_archive(
            output,
            tenant_code=tenant_code,
            snapshot_id=snapshot_id,
            created_time=created_at,
            available_until=available_until,
            encoded_datasets=encoded_datasets,
            max_archive_bytes=max_archive_bytes,
        )

    ready = await build_and_upload_snapshot(
        store,
        snapshot_kind="metadata",
        tenant_id=tenant_id,
        scope_id=tenant_id,
        schema_version="2.0",
        snapshot_id=snapshot_id,
        created_at=created_at,
        available_until=available_until,
        build_archive=build_archive,
    )
    return ReadyMetadataSnapshot(
        snapshot_id=ready.snapshot_id,
        tenant_id=ready.scope_id,
        created_at=ready.created_at,
        available_until=ready.available_until,
        size_bytes=ready.size_bytes,
        sha256=ready.sha256,
    )
