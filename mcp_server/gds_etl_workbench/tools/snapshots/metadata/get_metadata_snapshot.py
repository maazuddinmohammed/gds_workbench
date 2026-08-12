"""Metadata Snapshot selection, archive generation, and runtime adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    DependencyUnavailableError,
    TenantNotFoundError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation, ReadTransaction

from .archive import (
    EncodedDataset,
    SnapshotContractError,
    SnapshotPayloadTooLargeError,
    build_snapshot_archive,
    encode_dataset,
)
from .contracts import DATASETS_BY_NAME
from .sql import (
    ATTRIBUTE_ROWS_SQL,
    COPY_GROUP_CONTROL_ROWS_SQL,
    COPY_GROUP_ROWS_SQL,
    COPY_ROWS_SQL,
    DISCOVERY_SCOPE_ROWS_SQL,
    FOUNDATION_CONNECTION_ROWS_SQL,
    FOUNDATION_PROJECT_ROWS_SQL,
    FOUNDATION_SYSTEM_ROWS_SQL,
    FOUNDATION_TENANT_ROWS_SQL,
    INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL,
    INGESTION_OBJECT_MAPPING_ROWS_SQL,
    MEMBER_GROUP_ROWS_SQL,
    OBJECT_CLOSURE_SQL,
    OBJECT_ROWS_SQL,
    PROCESS_GROUP_ROWS_SQL,
    PROCESS_ROWS_SQL,
    REFERENCE_ROWS_SQL,
)
from .storage import MetadataSnapshotStore


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


class GetMetadataSnapshotRequest(MetadataSnapshotContractModel):
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    schema_version: Literal["2.0"] = "2.0"


class GetMetadataSnapshotResult(MetadataSnapshotContractModel):
    schema_version: Literal["2.0"] = "2.0"
    snapshot_id: UUID
    snapshot_kind: Literal["metadata"] = "metadata"
    status: Literal["ready"] = "ready"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    download_url: str = Field(min_length=1, max_length=2048)
    available_until: datetime
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["application/zip"] = "application/zip"


class MetadataSnapshotToolError(Exception):
    """A bounded tool failure safe for MCP serialization."""


def register_get_metadata_snapshot_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
    store: MetadataSnapshotStore,
    retention_hours: int,
    max_archive_bytes: int,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Register the small descriptor-only Metadata Snapshot MCP tool."""
    current_time = clock or (lambda: datetime.now(UTC))

    tool_registration = server.tool(
        description=(
            "Create an immutable Metadata Snapshot for one authorized Tenant. Returns "
            "only a protected download URL and bounded archive metadata; snapshot rows "
            "never enter the MCP response."
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

    async def get_metadata_snapshot(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        schema_version: Literal["2.0"] = "2.0",
    ) -> GetMetadataSnapshotResult:
        try:
            request = GetMetadataSnapshotRequest(
                tenant_id=tenant_id,
                schema_version=schema_version,
            )
            http_request = ctx.request_context.request
            principal = identity_provider.request_principal(http_request)
            ready = await create_metadata_snapshot(
                database,
                store,
                tenant_id=request.tenant_id,
                request_principal=principal,
                authorizer=authorizer,
                retention_hours=retention_hours,
                max_archive_bytes=max_archive_bytes,
                created_at=current_time(),
            )
            download_url = _absolute_download_url(
                http_request,
                tenant_id=ready.tenant_id,
                snapshot_id=ready.snapshot_id,
            )
            return GetMetadataSnapshotResult(
                snapshot_id=ready.snapshot_id,
                tenant_id=ready.tenant_id,
                download_url=download_url,
                available_until=ready.available_until,
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

    tool_registration(get_metadata_snapshot)
    audit.register_tool(
        "get_metadata_snapshot",
        policy=ToolPolicy.TENANT_READ,
        summarize_input=_audit_input_metadata,
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


def _absolute_download_url(
    request: object | None,
    *,
    tenant_id: int,
    snapshot_id: UUID,
) -> str:
    if not isinstance(request, Request):
        raise SnapshotContractError("snapshot creation requires an HTTP request context")
    base_url = str(request.base_url).rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SnapshotContractError("snapshot download origin is invalid")
    download_url = f"{base_url}/metadata-snapshots/{tenant_id}/{snapshot_id}/download"
    if len(download_url) > 2048:
        raise SnapshotContractError("snapshot download URL is too long")
    return download_url


def register_metadata_snapshot_download_route(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    store: MetadataSnapshotStore,
    download_ttl_seconds: int,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Register the reauthorizing, non-disclosing browser download boundary."""
    current_time = clock or (lambda: datetime.now(UTC))

    async def download(request: Request) -> Response:
        identity = _download_identity(request)
        if identity is None:
            return _snapshot_not_found()
        tenant_id, snapshot_id = identity
        try:
            principal = identity_provider.request_principal(request)
            async with database.read_transaction() as transaction:
                await authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_READ,
                )
            read_url = await store.create_read_url(
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
                now=current_time(),
                ttl_seconds=download_ttl_seconds,
            )
            if read_url is None:
                return _snapshot_not_found()
            return RedirectResponse(
                read_url,
                status_code=302,
                headers={"Cache-Control": "no-store"},
            )
        except AuthenticationError as error:
            return JSONResponse(
                {
                    "error": {
                        "code": error.public_code,
                        "message": error.message,
                        "retryable": False,
                    }
                },
                status_code=error.http_status,
                headers={"Cache-Control": "no-store"},
            )
        except DependencyUnavailableError:
            return JSONResponse(
                {
                    "error": {
                        "code": "dependency_unavailable",
                        "message": "A required dependency is unavailable.",
                        "retryable": True,
                    }
                },
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        except (WorkbenchError, SnapshotContractError):
            return _snapshot_not_found()

    server.custom_route(
        "/metadata-snapshots/{tenant_id}/{snapshot_id}/download",
        methods=["GET"],
    )(download)


def _download_identity(request: Request) -> tuple[int, UUID] | None:
    raw_tenant_id = request.path_params.get("tenant_id", "")
    raw_snapshot_id = request.path_params.get("snapshot_id", "")
    if not raw_tenant_id.isascii() or not raw_tenant_id.isdecimal() or len(raw_tenant_id) > 19:
        return None
    tenant_id = int(raw_tenant_id)
    if tenant_id <= 0 or tenant_id > 9_223_372_036_854_775_807 or str(tenant_id) != raw_tenant_id:
        return None
    try:
        snapshot_id = UUID(raw_snapshot_id)
    except ValueError:
        return None
    if snapshot_id.version != 4 or str(snapshot_id) != raw_snapshot_id:
        return None
    return tenant_id, snapshot_id


def _snapshot_not_found() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "not_found",
                "message": "Snapshot was not found.",
                "retryable": False,
            }
        },
        status_code=404,
        headers={"Cache-Control": "no-store"},
    )


async def select_snapshot_datasets(
    transaction: ReadTransaction,
    *,
    tenant_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
) -> tuple[EncodedDataset, ...]:
    """Authorize Tenant Read and select the complete 29-dataset snapshot closure."""
    if tenant_id <= 0:
        raise SnapshotContractError("tenant_id must be positive")
    await authorizer.authorize_tenant(
        transaction,
        request_principal,
        tenant_id=tenant_id,
        policy=ToolPolicy.TENANT_READ,
    )
    closure_rows = await transaction.fetch_all(OBJECT_CLOSURE_SQL, (tenant_id,))
    if not closure_rows:
        raise TenantNotFoundError()
    if closure_rows[0]["invalid_discovery_scope"]:
        raise SnapshotContractError("active Metadata Discovery Scope configuration is invalid")

    zone_by_object_id: dict[int, str] = {}
    for row in closure_rows:
        object_id = row["object_id"]
        if object_id is None:
            continue
        zone_code = row["snapshot_zone_code"]
        if row["snapshot_zone_is_active"] is not True or zone_code not in {
            "source",
            "bronze",
            "silver",
            "gold",
        }:
            raise SnapshotContractError("included Object has an unsupported or inactive Zone")
        zone_by_object_id[object_id] = zone_code

    object_ids = sorted(zone_by_object_id)
    object_rows = await transaction.fetch_all(OBJECT_ROWS_SQL, (object_ids,))
    attribute_rows = await transaction.fetch_all(ATTRIBUTE_ROWS_SQL, (object_ids,))
    if {row["object_id"] for row in object_rows} != set(object_ids):
        raise SnapshotContractError("included Object closure changed during snapshot selection")

    rows_by_dataset: dict[str, list[dict[str, object]]] = {
        f"{zone_code}_object": [] for zone_code in ("source", "bronze", "silver", "gold")
    }
    rows_by_dataset.update(
        {f"{zone_code}_attribute": [] for zone_code in ("source", "bronze", "silver", "gold")}
    )
    for row in object_rows:
        rows_by_dataset[f"{zone_by_object_id[row['object_id']]}_object"].append(row)
    for row in attribute_rows:
        object_id = row["object_id"]
        zone_code = zone_by_object_id.get(object_id)
        if zone_code is None:
            raise SnapshotContractError("included Attribute has no included Object")
        rows_by_dataset[f"{zone_code}_attribute"].append(row)

    ingestion_object_mapping_rows = await transaction.fetch_all(
        INGESTION_OBJECT_MAPPING_ROWS_SQL,
        (object_ids, object_ids),
    )
    ingestion_object_mapping_ids = [
        row["ingestion_object_mapping_id"] for row in ingestion_object_mapping_rows
    ]
    ingestion_attribute_mapping_rows = await transaction.fetch_all(
        INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL,
        (ingestion_object_mapping_ids,),
    )
    copy_group_rows = await transaction.fetch_all(COPY_GROUP_ROWS_SQL, (tenant_id,))
    member_group_rows = await transaction.fetch_all(MEMBER_GROUP_ROWS_SQL, (tenant_id,))
    copy_group_control_rows = await transaction.fetch_all(
        COPY_GROUP_CONTROL_ROWS_SQL,
        (tenant_id,),
    )
    copy_rows = await transaction.fetch_all(COPY_ROWS_SQL, (tenant_id,))
    process_group_rows = await transaction.fetch_all(PROCESS_GROUP_ROWS_SQL, (tenant_id,))
    process_rows = await transaction.fetch_all(PROCESS_ROWS_SQL, (tenant_id,))

    object_connection_by_id = {row["object_id"]: row["connection_id"] for row in object_rows}
    attribute_object_by_id = {row["attribute_id"]: row["object_id"] for row in attribute_rows}
    ingestion_object_mapping_by_id = {
        row["ingestion_object_mapping_id"]: row for row in ingestion_object_mapping_rows
    }
    copy_group_by_id = {row["copy_group_id"]: row for row in copy_group_rows}
    member_group_by_id = {row["member_group_id"]: row for row in member_group_rows}
    process_group_by_id = {row["process_group_id"]: row for row in process_group_rows}

    for row in ingestion_object_mapping_rows:
        if (
            row["source_object_id"] not in object_connection_by_id
            or row["target_object_id"] not in object_connection_by_id
        ):
            raise SnapshotContractError(
                "selected Ingestion Object Mapping has incomplete Object closure"
            )
    for row in ingestion_attribute_mapping_rows:
        parent = ingestion_object_mapping_by_id.get(row["ingestion_object_mapping_id"])
        if (
            parent is None
            or parent["source_object_id"] != row["source_object_id"]
            or parent["target_object_id"] != row["target_object_id"]
            or attribute_object_by_id.get(row["source_attribute_id"]) != row["source_object_id"]
            or attribute_object_by_id.get(row["target_attribute_id"]) != row["target_object_id"]
        ):
            raise SnapshotContractError(
                "selected Ingestion Attribute Mapping has incomplete relational closure"
            )
    for row in copy_group_rows:
        if row["tenant_id"] != tenant_id:
            raise SnapshotContractError("selected Copy Group has invalid Tenant ownership")
    for row in member_group_rows:
        if row["tenant_id"] != tenant_id:
            raise SnapshotContractError("selected Member Group has invalid Tenant ownership")
    for row in copy_group_control_rows:
        copy_group = copy_group_by_id.get(row["copy_group_id"])
        member_group = member_group_by_id.get(row["member_group_id"])
        if (
            row["tenant_id"] != tenant_id
            or copy_group is None
            or copy_group["system_id"] != row["system_id"]
            or (
                row["member_group_id"] is not None
                and (member_group is None or member_group["system_id"] != row["system_id"])
            )
        ):
            raise SnapshotContractError(
                "selected Copy Group Control has incomplete relational closure"
            )
    for row in copy_rows:
        if (
            row["copy_group_id"] not in copy_group_by_id
            or row["ingestion_object_mapping_id"] not in ingestion_object_mapping_by_id
        ):
            raise SnapshotContractError("selected Copy has incomplete relational closure")
    for row in process_group_rows:
        copy_group = copy_group_by_id.get(row["copy_group_id"])
        if (
            row["tenant_id"] != tenant_id
            or copy_group is None
            or copy_group["system_id"] != row["system_id"]
        ):
            raise SnapshotContractError("selected Process Group has incomplete relational closure")
    for row in process_rows:
        if (
            row["process_group_id"] not in process_group_by_id
            or object_connection_by_id.get(row["object_id"]) != row["connection_id"]
        ):
            raise SnapshotContractError("selected Process has incomplete relational closure")

    discovery_scope_rows = await transaction.fetch_all(
        DISCOVERY_SCOPE_ROWS_SQL,
        (tenant_id,),
    )
    required_connection_ids = {
        *(row["connection_id"] for row in object_rows),
        *(row["connection_id"] for row in discovery_scope_rows),
    }
    connection_rows = await transaction.fetch_all(
        FOUNDATION_CONNECTION_ROWS_SQL,
        (tenant_id, sorted(required_connection_ids), tenant_id),
    )
    connection_by_id = {row["connection_id"]: row for row in connection_rows}
    tenant_rows = await transaction.fetch_all(
        FOUNDATION_TENANT_ROWS_SQL,
        (tenant_id, sorted({row["tenant_id"] for row in connection_rows})),
    )
    tenant_by_id = {row["tenant_id"]: row for row in tenant_rows}
    requested_tenant = tenant_by_id.get(tenant_id)
    if requested_tenant is None:
        raise SnapshotContractError("requested Tenant disappeared during snapshot selection")
    if requested_tenant["gds_connection_id"] is not None:
        required_connection_ids.add(requested_tenant["gds_connection_id"])
    if not required_connection_ids.issubset(connection_by_id):
        raise SnapshotContractError("foundation Connection closure is incomplete")

    project_ids = {row["project_id"] for row in tenant_rows}
    project_rows = await transaction.fetch_all(
        FOUNDATION_PROJECT_ROWS_SQL,
        (sorted(project_ids),),
    )
    if {row["project_id"] for row in project_rows} != project_ids:
        raise SnapshotContractError("foundation Project closure is incomplete")

    required_system_ids = {
        *(row["system_id"] for row in connection_rows),
        *(row["system_id"] for row in copy_group_rows),
        *(row["system_id"] for row in member_group_rows),
        *(row["system_id"] for row in process_group_rows),
    }
    system_rows = await transaction.fetch_all(
        FOUNDATION_SYSTEM_ROWS_SQL,
        (sorted(required_system_ids),),
    )
    system_by_id = {row["system_id"]: row for row in system_rows}
    if set(system_by_id) != required_system_ids:
        raise SnapshotContractError("foundation System closure is incomplete")

    reference_rows_by_dataset = {
        dataset_name: await transaction.fetch_all(query)
        for dataset_name, query in REFERENCE_ROWS_SQL.items()
    }
    reference_ids_by_dataset = {
        dataset_name: {row[DATASETS_BY_NAME[dataset_name].primary_key[0]] for row in rows}
        for dataset_name, rows in reference_rows_by_dataset.items()
    }
    if any(
        connection["tenant_id"] not in tenant_by_id
        or connection["system_id"] not in system_by_id
        or connection["connection_type_id"] not in reference_ids_by_dataset["connection_type"]
        for connection in connection_rows
    ):
        raise SnapshotContractError("foundation Connection relationship is incomplete")
    if any(
        system["system_type_id"] not in reference_ids_by_dataset["system_type"]
        for system in system_rows
    ):
        raise SnapshotContractError("foundation System relationship is incomplete")
    if any(
        row["connection_id"] not in connection_by_id
        or row["object_type_id"] not in reference_ids_by_dataset["object_type"]
        or row["zone_id"] not in reference_ids_by_dataset["zone"]
        for row in object_rows
    ):
        raise SnapshotContractError("foundation Object relationship is incomplete")
    if any(
        row["tenant_id"] != tenant_id
        or row["connection_id"] not in connection_by_id
        or row["zone_id"] not in reference_ids_by_dataset["zone"]
        for row in discovery_scope_rows
    ):
        raise SnapshotContractError("foundation Discovery Scope relationship is incomplete")
    if any(
        (row["chunk_type_id"] is not None)
        and row["chunk_type_id"] not in reference_ids_by_dataset["chunk_type"]
        or (row["source_file_type_id"] is not None)
        and row["source_file_type_id"] not in reference_ids_by_dataset["file_type"]
        or row["source_data_operation_id"] not in reference_ids_by_dataset["data_operation"]
        or row["target_data_operation_id"] not in reference_ids_by_dataset["data_operation"]
        for row in copy_rows
    ):
        raise SnapshotContractError("foundation Copy reference relationship is incomplete")
    if any(
        row["zone_id"] not in reference_ids_by_dataset["zone"] for row in process_group_rows
    ) or any(
        row["process_type_id"] not in reference_ids_by_dataset["process_type"]
        for row in process_rows
    ):
        raise SnapshotContractError("foundation Process reference relationship is incomplete")

    object_attribute_datasets = tuple(
        encode_dataset(DATASETS_BY_NAME[dataset_name], rows_by_dataset[dataset_name])
        for zone_code in ("source", "bronze", "silver", "gold")
        for dataset_name in (f"{zone_code}_object", f"{zone_code}_attribute")
    )
    configuration_rows_by_dataset = {
        "ingestion_object_mapping": ingestion_object_mapping_rows,
        "ingestion_attribute_mapping": ingestion_attribute_mapping_rows,
        "copy_group": copy_group_rows,
        "member_group": member_group_rows,
        "copy_group_control": copy_group_control_rows,
        "copy": copy_rows,
        "process_group": process_group_rows,
        "process": process_rows,
    }
    metadata_datasets = object_attribute_datasets + tuple(
        encode_dataset(DATASETS_BY_NAME[dataset_name], rows)
        for dataset_name, rows in configuration_rows_by_dataset.items()
    )
    foundation_rows_by_dataset = {
        "project": project_rows,
        "tenant": tenant_rows,
        "system": system_rows,
        "connection": connection_rows,
        "tenant_metadata_discovery_scope": discovery_scope_rows,
        **reference_rows_by_dataset,
    }
    foundation_datasets = tuple(
        encode_dataset(DATASETS_BY_NAME[dataset_name], rows)
        for dataset_name, rows in foundation_rows_by_dataset.items()
    )
    return foundation_datasets + metadata_datasets


async def create_metadata_snapshot(
    database: Database,
    store: MetadataSnapshotStore,
    *,
    tenant_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
    retention_hours: int,
    max_archive_bytes: int,
    created_at: datetime | None = None,
    snapshot_id: UUID | None = None,
) -> ReadyMetadataSnapshot:
    """Select, archive, upload, and clean up one immutable Metadata Snapshot."""
    requested_creation_time = created_at or datetime.now(UTC)
    identifier = snapshot_id or uuid4()
    if requested_creation_time.utcoffset() is None or identifier.version != 4:
        raise SnapshotContractError("snapshot creation identity is invalid")
    created = requested_creation_time.astimezone(UTC)
    if not 1 <= retention_hours <= 168:
        raise SnapshotContractError("snapshot retention is invalid")
    available_until = created + timedelta(hours=retention_hours)

    async with database.read_transaction(isolation=ReadIsolation.REPEATABLE_READ) as transaction:
        encoded_datasets = await select_snapshot_datasets(
            transaction,
            tenant_id=tenant_id,
            request_principal=request_principal,
            authorizer=authorizer,
        )

    return await build_and_upload_metadata_snapshot(
        encoded_datasets,
        store,
        tenant_id=tenant_id,
        snapshot_id=identifier,
        created_at=created,
        available_until=available_until,
        max_archive_bytes=max_archive_bytes,
    )


async def build_and_upload_metadata_snapshot(
    encoded_datasets: Sequence[EncodedDataset],
    store: MetadataSnapshotStore,
    *,
    tenant_id: int,
    snapshot_id: UUID,
    created_at: datetime,
    available_until: datetime,
    max_archive_bytes: int,
) -> ReadyMetadataSnapshot:
    """Build in a private temporary directory and retain no local snapshot files."""
    with TemporaryDirectory(prefix="gds-metadata-snapshot-") as temporary_directory:
        archive = await asyncio.to_thread(
            build_snapshot_archive,
            Path(temporary_directory) / "metadata-snapshot.zip",
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            created_time=created_at,
            available_until=available_until,
            encoded_datasets=encoded_datasets,
            max_archive_bytes=max_archive_bytes,
        )
        await store.upload_archive(
            archive,
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            created_at=created_at,
            available_until=available_until,
        )
        return ReadyMetadataSnapshot(
            snapshot_id=snapshot_id,
            tenant_id=tenant_id,
            created_at=created_at,
            available_until=available_until,
            size_bytes=archive.size_bytes,
            sha256=archive.sha256,
        )
