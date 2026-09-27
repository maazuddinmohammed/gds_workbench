"""Select one authorized Metadata Snapshot with complete relational closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import TenantNotFoundError
from gds_etl_workbench.domain.snapshots.metadata import DATASETS
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

from .archive import (
    EncodedDataset,
    SnapshotContractError,
    encode_dataset,
)
from .projection import REFERENCE_ID_COLUMNS, project_id_free_rows
from .sql import (
    ATTRIBUTE_ROWS_SQL,
    COPY_GROUP_CONTROL_ROWS_SQL,
    COPY_GROUP_ROWS_SQL,
    COPY_ROWS_SQL,
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
class SelectedMetadataSnapshot:
    tenant_code: str
    datasets: tuple[EncodedDataset, ...]


async def select_snapshot_datasets(
    transaction: ReadTransaction,
    *,
    tenant_id: int,
    request_principal: RequestPrincipal,
    authorizer: AuthorizationService,
    source_tenant_ids: tuple[int, ...] = (),
) -> SelectedMetadataSnapshot:
    """Authorize Tenant Read and select the complete 28-dataset snapshot closure."""
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
    if len(source_tenant_ids) > 200 or any(
        type(value) is not int or not 0 < value <= 9_223_372_036_854_775_807
        for value in source_tenant_ids
    ):
        raise SnapshotContractError("Source Tenant selection is invalid")
    for source_tenant_id in sorted(set(source_tenant_ids) - {tenant_id}):
        await authorizer.authorize_tenant(
            transaction,
            request_principal,
            tenant_id=source_tenant_id,
            policy=ToolPolicy.TENANT_READ,
        )
        additional = await transaction.fetch_all(OBJECT_CLOSURE_SQL, (source_tenant_id,))
        if not additional:
            raise TenantNotFoundError()
        closure_rows.extend(
            row for row in additional if row["snapshot_zone_code"] in {"source", "bronze"}
        )
    zone_by_object_id: dict[int, str] = {}
    tenant_by_object_id: dict[int, int] = {}
    for row in closure_rows:
        object_id = row["object_id"]
        if object_id is None:
            continue
        object_tenant_id = row["object_tenant_id"]
        if (
            isinstance(object_tenant_id, bool)
            or not isinstance(object_tenant_id, int)
            or object_tenant_id < 1
        ):
            raise SnapshotContractError("included Object has no resolved Tenant")
        zone_code = row["snapshot_zone_code"]
        if row["snapshot_zone_is_active"] is not True or zone_code not in {
            "source",
            "bronze",
            "silver",
            "gold",
        }:
            raise SnapshotContractError("included Object has an unsupported or inactive Zone")
        zone_by_object_id[object_id] = zone_code
        tenant_by_object_id[object_id] = object_tenant_id

    object_ids = sorted(zone_by_object_id)
    selected_object_rows = await transaction.fetch_all(OBJECT_ROWS_SQL, (object_ids,))
    attribute_rows = await transaction.fetch_all(ATTRIBUTE_ROWS_SQL, (object_ids,))
    if {row["object_id"] for row in selected_object_rows} != set(object_ids):
        raise SnapshotContractError("included Object closure changed during snapshot selection")
    if any(
        row["source_tenant_id"] != tenant_by_object_id[row["object_id"]]
        for row in selected_object_rows
    ):
        raise SnapshotContractError("included Object ownership changed during snapshot selection")
    object_rows = selected_object_rows

    rows_by_dataset: dict[str, list[dict[str, Any]]] = {
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

    required_connection_ids = {
        *(row["connection_id"] for row in object_rows),
    }
    connection_rows = await transaction.fetch_all(
        FOUNDATION_CONNECTION_ROWS_SQL,
        (tenant_id, sorted(required_connection_ids), tenant_id),
    )
    connection_by_id = {row["connection_id"]: row for row in connection_rows}
    tenant_rows = await transaction.fetch_all(
        FOUNDATION_TENANT_ROWS_SQL,
        (
            tenant_id,
            sorted(
                {
                    *(row["tenant_id"] for row in connection_rows),
                    *tenant_by_object_id.values(),
                }
            ),
        ),
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
        or row["source_tenant_id"] not in tenant_by_id
        or row["object_type_id"] not in reference_ids_by_dataset["object_type"]
        or row["zone_id"] not in reference_ids_by_dataset["zone"]
        for row in object_rows
    ):
        raise SnapshotContractError("foundation Object relationship is incomplete")
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
