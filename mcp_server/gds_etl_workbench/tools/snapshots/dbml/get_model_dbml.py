"""DBML Snapshot selection, rendering, archive generation, and delivery."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import asyncio
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
from gds_etl_workbench.application.model_read import POLICY
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.tools.snapshots.archive import (
    SnapshotArchive,
    SnapshotPayloadTooLargeError,
)
from gds_etl_workbench.tools.snapshots.model.get_model_snapshot import (
    select_model_snapshot,
)
from gds_etl_workbench.tools.snapshots.service import (
    build_and_upload_snapshot,
    create_snapshot_download,
    create_snapshot_window,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotStore

from .archive import build_dbml_snapshot_archive
from .renderer import DbmlModelType, render_dbml_documents


class ModelDbmlToolError(Exception):
    """A bounded DBML Snapshot failure safe for MCP serialization."""


@dataclass(frozen=True, slots=True)
class ReadyModelDbml:
    snapshot_id: UUID
    model_id: int
    model_revision: int
    model_type: DbmlModelType
    include_submodels: bool
    dbml_file_count: int
    created_at: datetime
    available_until: datetime
    size_bytes: int
    sha256: str


class ModelDbmlContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExportModelDbmlRequest(ModelDbmlContractModel):
    model_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    model_type: DbmlModelType
    include_submodels: bool = True
    schema_version: Literal["2.0"] = "2.0"


class ExportModelDbmlResult(ModelDbmlContractModel):
    schema_version: Literal["2.0"] = "2.0"
    snapshot_id: UUID
    snapshot_kind: Literal["dbml"] = "dbml"
    status: Literal["ready"] = "ready"
    model_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    model_revision: int = Field(gt=0)
    model_type: DbmlModelType
    include_submodels: bool
    dbml_file_count: int = Field(gt=0, le=1_002)
    download_url: str = Field(min_length=1, max_length=2048)
    download_url_expires_at: datetime
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["application/zip"] = "application/zip"


def register_export_model_dbml_tool(
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
    """Register the descriptor-only DBML Snapshot MCP tool."""
    current_time = clock or (lambda: datetime.now(UTC))

    @server.tool(
        name="export_model_dbml",
        description=(
            "Only when the user explicitly requests DBML, export conceptual, logical, "
            "dimensional, or full DBML for one authorized Model. "
            "The ZIP contains each selected complete layer and, when requested, Logical and "
            "Dimensional files by active Submodel. Returns archive metadata and a temporary "
            "client download URL."
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
    async def export_model_dbml(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        model_type: DbmlModelType,
        include_submodels: bool = True,
        schema_version: Literal["2.0"] = "2.0",
    ) -> ExportModelDbmlResult:
        try:
            request = ExportModelDbmlRequest(
                model_id=model_id,
                model_type=model_type,
                include_submodels=include_submodels,
                schema_version=schema_version,
            )
            principal = identity_provider.request_principal(ctx.request_context.request)
            ready = await create_model_dbml_snapshot(
                database,
                store,
                model_id=request.model_id,
                model_type=request.model_type,
                include_submodels=request.include_submodels,
                request_principal=principal,
                authorizer=authorizer,
                retention_hours=retention_hours,
                max_archive_bytes=max_archive_bytes,
                created_at=current_time(),
            )
            download_created_at = current_time()
            download = await create_snapshot_download(
                store,
                snapshot_kind="dbml",
                scope_id=ready.model_id,
                schema_version="2.0",
                snapshot_id=ready.snapshot_id,
                available_until=ready.available_until,
                now=download_created_at,
                ttl_seconds=download_ttl_seconds,
            )
            return ExportModelDbmlResult(
                snapshot_id=ready.snapshot_id,
                model_id=ready.model_id,
                model_revision=ready.model_revision,
                model_type=ready.model_type,
                include_submodels=ready.include_submodels,
                dbml_file_count=ready.dbml_file_count,
                download_url=download.url,
                download_url_expires_at=download.expires_at,
                size_bytes=ready.size_bytes,
                sha256=ready.sha256,
            )
        except AuthenticationError as error:
            raise ModelDbmlToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelDbmlToolError(f"{error.code}: {error.message}") from None
        except SnapshotPayloadTooLargeError:
            raise ModelDbmlToolError(
                "payload_too_large: The generated snapshot exceeds its configured limit."
            ) from None
        except Exception:
            raise ModelDbmlToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "export_model_dbml",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={
            "model_id",
            "model_type",
            "include_submodels",
            "schema_version",
        },
    )


async def create_model_dbml_snapshot(
    database: Database,
    store: SnapshotStore,
    *,
    model_id: int,
    model_type: DbmlModelType,
    include_submodels: bool,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
    retention_hours: int,
    max_archive_bytes: int,
    created_at: datetime | None = None,
    snapshot_id: UUID | None = None,
) -> ReadyModelDbml:
    """Select once, render, archive, upload, and clean up one DBML Snapshot."""
    window = create_snapshot_window(
        retention_hours=retention_hours,
        created_at=created_at,
        snapshot_id=snapshot_id,
    )
    snapshot = await select_model_snapshot(
        database,
        model_id=model_id,
        request_principal=request_principal,
        authorizer=authorizer,
    )
    documents = await asyncio.to_thread(
        render_dbml_documents,
        snapshot,
        model_type=model_type,
        include_submodels=include_submodels,
    )

    def build_archive(output: Path) -> SnapshotArchive:
        return build_dbml_snapshot_archive(
            output,
            snapshot_id=window.snapshot_id,
            snapshot=snapshot,
            model_type=model_type,
            include_submodels=include_submodels,
            documents=documents,
            created_time=window.created_at,
            available_until=window.available_until,
            max_archive_bytes=max_archive_bytes,
        )

    ready = await build_and_upload_snapshot(
        store,
        snapshot_kind="dbml",
        scope_id=snapshot.model_id,
        schema_version="2.0",
        snapshot_id=window.snapshot_id,
        created_at=window.created_at,
        available_until=window.available_until,
        build_archive=build_archive,
    )
    return ReadyModelDbml(
        snapshot_id=ready.snapshot_id,
        model_id=ready.scope_id,
        model_revision=snapshot.model_revision,
        model_type=model_type,
        include_submodels=include_submodels,
        dbml_file_count=len(documents),
        created_at=ready.created_at,
        available_until=ready.available_until,
        size_bytes=ready.size_bytes,
        sha256=ready.sha256,
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    model_id = arguments.get("model_id")
    model_type = arguments.get("model_type")
    include_submodels = arguments.get("include_submodels", True)
    return {
        "schema_version": ("2.0" if arguments.get("schema_version", "2.0") == "2.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "model_type": (
            model_type
            if model_type in {"full", "conceptual", "logical", "dimensional"}
            else "invalid"
        ),
        "include_submodels": (include_submodels if type(include_submodels) is bool else "invalid"),
    }
