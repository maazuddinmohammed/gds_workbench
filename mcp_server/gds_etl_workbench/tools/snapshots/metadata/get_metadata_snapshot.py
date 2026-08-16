"""Metadata Snapshot selection, archive generation, and runtime adapters."""

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
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import TenantNotFoundError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation, ReadTransaction
from gds_etl_workbench.tools.snapshots.service import (
    build_and_upload_snapshot,
    create_snapshot_download,
    create_snapshot_window,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotStore

from .archive import (
    EncodedDataset,
    SnapshotArchive,
    SnapshotContractError,
    SnapshotPayloadTooLargeError,
    build_snapshot_archive,
    encode_dataset,
)
from .contracts import DATASETS
from .projection import REFERENCE_ID_COLUMNS, project_id_free_rows
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


@dataclass(frozen=True, slots=True)
class ReadyMetadataSnapshot:
    snapshot_id: UUID
    tenant_id: int
    created_at: datetime
    available_until: datetime
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SelectedMetadataSnapshot:
    tenant_code: str
    datasets: tuple[EncodedDataset, ...]


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
    download_url_expires_at: datetime
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
    store: SnapshotStore,
    download_ttl_seconds: int,
    retention_hours: int,
    max_archive_bytes: int,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Register the small descriptor-only Metadata Snapshot MCP tool."""
    current_time = clock or (lambda: datetime.now(UTC))

    tool_registration = server.tool(
        description=(
            "Create an immutable Metadata Snapshot for one authorized Tenant. Returns "
            "only a temporary read-only download URL and bounded archive metadata; snapshot rows "
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
            download_created_at = current_time()
            download = await create_snapshot_download(
                store,
                snapshot_kind="metadata",
                scope_id=ready.tenant_id,
                schema_version="2.0",
                snapshot_id=ready.snapshot_id,
                available_until=ready.available_until,
                now=download_created_at,
                ttl_seconds=download_ttl_seconds,
            )
            return GetMetadataSnapshotResult(
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

    tool_registration(get_metadata_snapshot)
    audit.register_tool(
        "get_metadata_snapshot",
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


async def select_snapshot_datasets(
    transaction: ReadTransaction,
    *,
    tenant_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
) -> SelectedMetadataSnapshot:
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
        *(row["gds_connection_id"] for row in discovery_scope_rows),
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
        dataset_name: {row[REFERENCE_ID_COLUMNS[dataset_name]] for row in rows}
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
        or row["gds_connection_id"] not in connection_by_id
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
    foundation_rows_by_dataset = {
        "project": project_rows,
        "tenant": tenant_rows,
        "system": system_rows,
        "connection": connection_rows,
        "tenant_metadata_discovery_scope": discovery_scope_rows,
        **reference_rows_by_dataset,
    }
    raw_rows_by_dataset = {
        **foundation_rows_by_dataset,
        **rows_by_dataset,
        **configuration_rows_by_dataset,
    }
    projected_rows = project_id_free_rows(raw_rows_by_dataset)
    encoded_datasets = tuple(
        encode_dataset(definition, projected_rows[definition.name]) for definition in DATASETS
    )
    return SelectedMetadataSnapshot(
        tenant_code=str(requested_tenant["tenant_code"]),
        datasets=encoded_datasets,
    )


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
