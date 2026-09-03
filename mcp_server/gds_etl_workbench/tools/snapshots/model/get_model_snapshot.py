"""Complete ID-free Model Snapshot built from the shared dataset contracts."""

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
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation
from gds_etl_workbench.tools.modeling.common import POLICY, authorize_model_read
from gds_etl_workbench.tools.snapshots.archive import (
    SnapshotArchive,
    SnapshotPayloadTooLargeError,
)
from gds_etl_workbench.tools.snapshots.service import (
    build_and_upload_snapshot,
    create_snapshot_download,
    create_snapshot_window,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotStore

from .archive import build_model_snapshot_archive
from .contracts import ModelSnapshot
from .selection import build_model_snapshot


class ModelSnapshotToolError(Exception):
    """A bounded Snapshot failure safe for MCP serialization."""


@dataclass(frozen=True, slots=True)
class ReadyModelSnapshot:
    snapshot_id: UUID
    model_id: int
    model_revision: int
    created_at: datetime
    available_until: datetime
    size_bytes: int
    sha256: str


class ModelSnapshotContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateModelSnapshotRequest(ModelSnapshotContractModel):
    model_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    schema_version: Literal["2.0"] = "2.0"


class CreateModelSnapshotResult(ModelSnapshotContractModel):
    schema_version: Literal["2.0"] = "2.0"
    snapshot_id: UUID
    snapshot_kind: Literal["model"] = "model"
    status: Literal["ready"] = "ready"
    model_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    model_revision: int = Field(gt=0)
    download_url: str = Field(min_length=1, max_length=2048)
    download_url_expires_at: datetime
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["application/zip"] = "application/zip"


def register_create_model_snapshot_tool(
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
        name="create_model_snapshot",
        description=(
            "Create a new complete, immutable, ID-free Model Snapshot ZIP for broad local "
            "authoring. It includes Input Scope, evidence, models, Bindings, Mapping, Code, "
            "and Validation. The response contains bounded archive metadata and a temporary "
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
    async def create_model_snapshot_tool(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["2.0"] = "2.0",
    ) -> CreateModelSnapshotResult:
        try:
            request = CreateModelSnapshotRequest(
                model_id=model_id,
                schema_version=schema_version,
            )
            principal = identity_provider.request_principal(ctx.request_context.request)
            ready = await create_model_snapshot(
                database,
                store,
                model_id=request.model_id,
                request_principal=principal,
                authorizer=authorizer,
                retention_hours=retention_hours,
                max_archive_bytes=max_archive_bytes,
                created_at=current_time(),
            )
            download_created_at = current_time()
            download = await create_snapshot_download(
                store,
                snapshot_kind="model",
                scope_id=ready.model_id,
                schema_version="2.0",
                snapshot_id=ready.snapshot_id,
                available_until=ready.available_until,
                now=download_created_at,
                ttl_seconds=download_ttl_seconds,
            )
            return CreateModelSnapshotResult(
                snapshot_id=ready.snapshot_id,
                model_id=ready.model_id,
                model_revision=ready.model_revision,
                download_url=download.url,
                download_url_expires_at=download.expires_at,
                size_bytes=ready.size_bytes,
                sha256=ready.sha256,
            )
        except AuthenticationError as error:
            raise ModelSnapshotToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelSnapshotToolError(f"{error.code}: {error.message}") from None
        except SnapshotPayloadTooLargeError:
            raise ModelSnapshotToolError(
                "payload_too_large: The generated snapshot exceeds its configured limit."
            ) from None
        except Exception:
            raise ModelSnapshotToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "create_model_snapshot",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "schema_version"},
    )


async def create_model_snapshot(
    database: Database,
    store: SnapshotStore,
    *,
    model_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
    retention_hours: int,
    max_archive_bytes: int,
    created_at: datetime | None = None,
    snapshot_id: UUID | None = None,
) -> ReadyModelSnapshot:
    """Select, archive, upload, and clean up one immutable Model Snapshot."""
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

    return await build_and_upload_model_snapshot(
        snapshot,
        store,
        snapshot_id=window.snapshot_id,
        created_at=window.created_at,
        available_until=window.available_until,
        max_archive_bytes=max_archive_bytes,
    )


async def select_model_snapshot(
    database: Database,
    *,
    model_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
) -> ModelSnapshot:
    """Authorize and select one Model Snapshot under repeatable read."""
    async with database.read_transaction(isolation=ReadIsolation.REPEATABLE_READ) as transaction:
        model = await authorize_model_read(
            transaction,
            authorizer=authorizer,
            principal=request_principal,
            model_id=model_id,
        )
        return await build_model_snapshot(transaction, model)


async def build_and_upload_model_snapshot(
    snapshot: ModelSnapshot,
    store: SnapshotStore,
    *,
    snapshot_id: UUID,
    created_at: datetime,
    available_until: datetime,
    max_archive_bytes: int,
) -> ReadyModelSnapshot:
    """Build and upload through the shared governed Snapshot service."""

    def build_archive(output: Path) -> SnapshotArchive:
        return build_model_snapshot_archive(
            output,
            snapshot_id=snapshot_id,
            snapshot=snapshot,
            created_time=created_at,
            available_until=available_until,
            max_archive_bytes=max_archive_bytes,
        )

    ready = await build_and_upload_snapshot(
        store,
        snapshot_kind="model",
        scope_id=snapshot.model_id,
        schema_version="2.0",
        snapshot_id=snapshot_id,
        created_at=created_at,
        available_until=available_until,
        build_archive=build_archive,
    )
    return ReadyModelSnapshot(
        snapshot_id=ready.snapshot_id,
        model_id=ready.scope_id,
        model_revision=snapshot.model_revision,
        created_at=ready.created_at,
        available_until=ready.available_until,
        size_bytes=ready.size_bytes,
        sha256=ready.sha256,
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    model_id = arguments.get("model_id")
    return {
        "schema_version": ("2.0" if arguments.get("schema_version", "2.0") == "2.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
    }
