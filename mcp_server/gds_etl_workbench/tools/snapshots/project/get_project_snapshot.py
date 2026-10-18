"""Complete ID-free Project Snapshot built from the shared dataset contracts."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from gds_etl_workbench.application.project_read import POLICY, authorize_project_read
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.snapshots.project import ProjectSnapshot
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation
from gds_etl_workbench.infrastructure.snapshot_archive import (
    SnapshotArchive,
    SnapshotPayloadTooLargeError,
)
from gds_etl_workbench.tools.snapshots.service import (
    build_and_upload_snapshot,
    create_snapshot_download,
    create_snapshot_window,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotStore

from .archive import build_project_snapshot_archive


class ProjectSnapshotToolError(Exception):
    """A bounded Snapshot failure safe for MCP serialization."""


@dataclass(frozen=True, slots=True)
class ReadyProjectSnapshot:
    snapshot_id: UUID
    tenant_id: int
    project_id: int
    project_revision: int
    created_at: datetime
    available_until: datetime
    size_bytes: int
    sha256: str


class ProjectSnapshotContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateProjectSnapshotRequest(ProjectSnapshotContractModel):
    project_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    schema_version: Literal["3.0"] = "3.0"


class CreateProjectSnapshotResult(ProjectSnapshotContractModel):
    schema_version: Literal["3.0"] = "3.0"
    snapshot_id: UUID
    snapshot_kind: Literal["project"] = "project"
    status: Literal["ready"] = "ready"
    project_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    project_revision: int = Field(gt=0)
    download_url: str = Field(min_length=1, max_length=2048)
    download_url_expires_at: datetime
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["application/zip"] = "application/zip"


def register_create_project_snapshot_tool(
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
    current_time = clock or (lambda: datetime.now(UTC))

    @server.tool(
        name="create_project_snapshot",
        description=(
            "Create a new complete, immutable, ID-free Project Snapshot ZIP for broad local "
            "authoring. It includes Input Scope, Profiling, Analysis, Context, modeled "
            "layers, Bindings, Mapping, Code, and Validation. The response contains bounded "
            "archive metadata and a temporary "
            "client download URL, never Snapshot rows. Download promptly and verify the returned "
            "Snapshot ID, byte size, and SHA-256 before installing it."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def create_project_snapshot_tool(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["3.0"] = "3.0",
    ) -> CreateProjectSnapshotResult:
        try:
            request = CreateProjectSnapshotRequest(
                project_id=project_id,
                schema_version=schema_version,
            )
            principal = identity_provider.request_principal(ctx.request_context.request)
            ready = await create_project_snapshot(
                database,
                store,
                project_id=request.project_id,
                request_principal=principal,
                authorizer=authorizer,
                retention_hours=retention_hours,
                max_archive_bytes=max_archive_bytes,
                created_at=current_time(),
            )
            download_created_at = current_time()
            download = await create_snapshot_download(
                store,
                snapshot_kind="project",
                tenant_id=ready.tenant_id,
                scope_id=ready.project_id,
                schema_version="3.0",
                snapshot_id=ready.snapshot_id,
                created_at=ready.created_at,
                available_until=ready.available_until,
                now=download_created_at,
                ttl_seconds=download_ttl_seconds,
            )
            return CreateProjectSnapshotResult(
                snapshot_id=ready.snapshot_id,
                project_id=ready.project_id,
                project_revision=ready.project_revision,
                download_url=download.url,
                download_url_expires_at=download.expires_at,
                size_bytes=ready.size_bytes,
                sha256=ready.sha256,
            )
        except AuthenticationError as error:
            raise ProjectSnapshotToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectSnapshotToolError(f"{error.code}: {error.message}") from None
        except SnapshotPayloadTooLargeError:
            raise ProjectSnapshotToolError(
                "payload_too_large: The generated snapshot exceeds its configured limit."
            ) from None
        except Exception:
            raise ProjectSnapshotToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "create_project_snapshot",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"project_id", "schema_version"},
    )


async def create_project_snapshot(
    database: Database,
    store: SnapshotStore,
    *,
    project_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
    retention_hours: int,
    max_archive_bytes: int,
    created_at: datetime | None = None,
    snapshot_id: UUID | None = None,
) -> ReadyProjectSnapshot:
    """Select, archive, upload, and clean up one immutable Project Snapshot."""
    window = create_snapshot_window(
        retention_hours=retention_hours,
        created_at=created_at,
        snapshot_id=snapshot_id,
    )

    tenant_id, snapshot = await select_project_snapshot(
        database,
        project_id=project_id,
        request_principal=request_principal,
        authorizer=authorizer,
    )

    return await build_and_upload_project_snapshot(
        snapshot,
        store,
        tenant_id=tenant_id,
        snapshot_id=window.snapshot_id,
        created_at=window.created_at,
        available_until=window.available_until,
        max_archive_bytes=max_archive_bytes,
    )


async def select_project_snapshot(
    database: Database,
    *,
    project_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
) -> tuple[int, ProjectSnapshot]:
    """Authorize and select one Project Snapshot under repeatable read."""
    async with database.read_transaction(isolation=ReadIsolation.REPEATABLE_READ) as transaction:
        project = await authorize_project_read(
            transaction,
            authorizer=authorizer,
            principal=request_principal,
            project_id=project_id,
        )
        return project.tenant_id, await build_project_snapshot(transaction, project)


async def build_and_upload_project_snapshot(
    snapshot: ProjectSnapshot,
    store: SnapshotStore,
    *,
    tenant_id: int,
    snapshot_id: UUID,
    created_at: datetime,
    available_until: datetime,
    max_archive_bytes: int,
) -> ReadyProjectSnapshot:
    """Build and upload through the shared governed Snapshot service."""

    def build_archive(output: Path) -> SnapshotArchive:
        return build_project_snapshot_archive(
            output,
            snapshot_id=snapshot_id,
            snapshot=snapshot,
            created_time=created_at,
            available_until=available_until,
            max_archive_bytes=max_archive_bytes,
        )

    ready = await build_and_upload_snapshot(
        store,
        snapshot_kind="project",
        tenant_id=tenant_id,
        scope_id=snapshot.project_id,
        schema_version="3.0",
        snapshot_id=snapshot_id,
        created_at=created_at,
        available_until=available_until,
        build_archive=build_archive,
    )
    return ReadyProjectSnapshot(
        snapshot_id=ready.snapshot_id,
        tenant_id=tenant_id,
        project_id=ready.scope_id,
        project_revision=snapshot.project_revision,
        created_at=ready.created_at,
        available_until=ready.available_until,
        size_bytes=ready.size_bytes,
        sha256=ready.sha256,
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    project_id = arguments.get("project_id")
    return {
        "schema_version": ("3.0" if arguments.get("schema_version", "3.0") == "3.0" else "invalid"),
        "project_id": project_id if type(project_id) is int and project_id > 0 else "invalid",
    }
