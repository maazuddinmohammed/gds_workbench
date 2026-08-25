"""Project internal database-ID rows into the shared ID-free record contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .archive import SnapshotContractError

type Rows = Sequence[Mapping[str, Any]]

REFERENCE_ID_COLUMNS = {
    "system_type": "system_type_id",
    "connection_type": "connection_type_id",
    "object_type": "object_type_id",
    "zone": "zone_id",
    "chunk_type": "chunk_type_id",
    "file_type": "file_type_id",
    "data_operation": "data_operation_id",
    "process_type": "process_type_id",
}


def project_id_free_rows(
    raw_rows: Mapping[str, Rows],
) -> dict[str, list[dict[str, object]]]:
    """Resolve every internal ID to the target record's natural key."""
    project_by_id = _by_id(raw_rows["project"], "project_id")
    tenant_by_id = _by_id(raw_rows["tenant"], "tenant_id")
    system_by_id = _by_id(raw_rows["system"], "system_id")
    connection_by_id = _by_id(raw_rows["connection"], "connection_id")
    object_rows = [
        row
        for dataset_name in (
            "source_object",
            "bronze_object",
            "silver_object",
            "gold_object",
        )
        for row in raw_rows[dataset_name]
    ]
    attribute_rows = [
        row
        for dataset_name in (
            "source_attribute",
            "bronze_attribute",
            "silver_attribute",
            "gold_attribute",
        )
        for row in raw_rows[dataset_name]
    ]
    object_by_id = _by_id(object_rows, "object_id")
    attribute_by_id = _by_id(attribute_rows, "attribute_id")
    object_mapping_by_id = _by_id(
        raw_rows["ingestion_object_mapping"],
        "ingestion_object_mapping_id",
    )
    copy_group_by_id = _by_id(raw_rows["copy_group"], "copy_group_id")
    member_group_by_id = _by_id(raw_rows["member_group"], "member_group_id")
    process_group_by_id = _by_id(raw_rows["process_group"], "process_group_id")
    reference_by_name_and_id = {
        dataset_name: _by_id(raw_rows[dataset_name], id_column)
        for dataset_name, id_column in REFERENCE_ID_COLUMNS.items()
    }

    def tenant_code(tenant_id: int) -> str:
        return str(tenant_by_id[tenant_id]["tenant_code"])

    def system_code(system_id: int) -> str:
        return str(system_by_id[system_id]["system_code"])

    def reference_value(dataset_name: str, reference_id: int, column: str) -> str:
        return str(reference_by_name_and_id[dataset_name][reference_id][column])

    def connection_key(connection_id: int, prefix: str = "") -> dict[str, object]:
        connection = connection_by_id[connection_id]
        return {
            f"{prefix}tenant_code": tenant_code(connection["tenant_id"]),
            f"{prefix}system_code": system_code(connection["system_id"]),
            f"{prefix}connection_code": connection["connection_code"],
        }

    def object_connection_key(row: Mapping[str, Any], prefix: str = "") -> dict[str, object]:
        connection = connection_by_id[row["connection_id"]]
        return {
            f"{prefix}tenant_code": tenant_code(row["object_tenant_id"]),
            f"{prefix}system_code": system_code(connection["system_id"]),
            f"{prefix}connection_code": connection["connection_code"],
        }

    def object_key(object_id: int, prefix: str = "") -> dict[str, object]:
        row = object_by_id[object_id]
        return {
            **object_connection_key(row, prefix),
            f"{prefix}object_schema": row["object_schema"],
            f"{prefix}object_name": row["object_name"],
        }

    def attribute_key(attribute_id: int, prefix: str = "") -> dict[str, object]:
        row = attribute_by_id[attribute_id]
        return {
            **object_key(row["object_id"], prefix),
            f"{prefix}attribute_name": row["attribute_name"],
        }

    def copy_group_key(copy_group_id: int) -> dict[str, object]:
        row = copy_group_by_id[copy_group_id]
        return {
            "tenant_code": tenant_code(row["tenant_id"]),
            "system_code": system_code(row["system_id"]),
            "copy_group_name": row["copy_group_name"],
        }

    def process_group_key(process_group_id: int) -> dict[str, object]:
        row = process_group_by_id[process_group_id]
        return {
            "tenant_code": tenant_code(row["tenant_id"]),
            "system_code": system_code(row["system_id"]),
            "zone_code": reference_value("zone", row["zone_id"], "zone_code"),
            "process_group_name": row["process_group_name"],
        }

    projected: dict[str, list[dict[str, object]]] = {
        "project": [_without(row, "project_id") for row in raw_rows["project"]],
        "tenant": [],
        "system": [],
        "connection": [],
        "tenant_metadata_discovery_scope": [],
    }
    for row in raw_rows["tenant"]:
        gds_connection = (
            connection_key(row["gds_connection_id"])
            if row["gds_connection_id"] is not None
            else None
        )
        projected["tenant"].append(
            {
                "tenant_code": row["tenant_code"],
                "project_code": project_by_id[row["project_id"]]["project_code"],
                "tenant_name": row["tenant_name"],
                "tenant_description": row["tenant_description"],
                "tenant_catalog": row["tenant_catalog"],
                "gds_admin_catalog": row["gds_admin_catalog"],
                "gds_connection_tenant_code": (
                    gds_connection["tenant_code"] if gds_connection is not None else None
                ),
                "gds_connection_system_code": (
                    gds_connection["system_code"] if gds_connection is not None else None
                ),
                "gds_connection_code": (
                    gds_connection["connection_code"] if gds_connection is not None else None
                ),
                "tenant_visibility": row["tenant_visibility"],
                "is_active": row["is_active"],
            }
        )
    for row in raw_rows["system"]:
        projected["system"].append(
            {
                "system_code": row["system_code"],
                "system_name": row["system_name"],
                "system_description": row["system_description"],
                "system_type_code": reference_value(
                    "system_type", row["system_type_id"], "system_type_code"
                ),
                "is_active": row["is_active"],
            }
        )
    for row in raw_rows["connection"]:
        projected["connection"].append(
            {
                **connection_key(row["connection_id"]),
                "connection_name": row["connection_name"],
                "connection_type_code": reference_value(
                    "connection_type",
                    row["connection_type_id"],
                    "connection_type_code",
                ),
                "has_foreign_catalog": row["has_foreign_catalog"],
                "foreign_catalog": row["foreign_catalog"],
                "is_global_data_store": row["is_global_data_store"],
                "is_active": row["is_active"],
            }
        )
    for row in raw_rows["tenant_metadata_discovery_scope"]:
        scope_connection = connection_key(row["gds_connection_id"])
        projected["tenant_metadata_discovery_scope"].append(
            {
                "scope_tenant_code": tenant_code(row["tenant_id"]),
                "connection_tenant_code": scope_connection["tenant_code"],
                "connection_system_code": scope_connection["system_code"],
                "connection_code": scope_connection["connection_code"],
                "zone_code": reference_value("zone", row["zone_id"], "zone_code"),
                "object_schema": row["object_schema"],
                "is_active": row["is_active"],
            }
        )

    for dataset_name, id_column in REFERENCE_ID_COLUMNS.items():
        projected[dataset_name] = [_without(row, id_column) for row in raw_rows[dataset_name]]

    for zone_code in ("source", "bronze", "silver", "gold"):
        projected[f"{zone_code}_object"] = [
            {
                **object_connection_key(row),
                "object_schema": row["object_schema"],
                "object_name": row["object_name"],
                "fc_object_schema": row["fc_object_schema"],
                "fc_object_name": row["fc_object_name"],
                "object_transformation": row["object_transformation"],
                "object_description": row["object_description"],
                "batch_attribute_name": row["batch_attribute_name"],
                "object_type_code": reference_value(
                    "object_type", row["object_type_id"], "object_type_code"
                ),
                "zone_code": reference_value("zone", row["zone_id"], "zone_code"),
                "is_locked": row["is_locked"],
                "is_active": row["is_active"],
            }
            for row in raw_rows[f"{zone_code}_object"]
        ]
        projected[f"{zone_code}_attribute"] = [
            {
                **object_key(row["object_id"]),
                **_without(row, "attribute_id", "object_id"),
            }
            for row in raw_rows[f"{zone_code}_attribute"]
        ]

    projected["ingestion_object_mapping"] = [
        {
            **object_key(row["source_object_id"], "source_"),
            **object_key(row["target_object_id"], "target_"),
            "is_active": row["is_active"],
        }
        for row in raw_rows["ingestion_object_mapping"]
    ]
    projected["ingestion_attribute_mapping"] = [
        {
            **attribute_key(row["source_attribute_id"], "source_"),
            **attribute_key(row["target_attribute_id"], "target_"),
            "is_active": row["is_active"],
        }
        for row in raw_rows["ingestion_attribute_mapping"]
    ]
    projected["copy_group"] = [
        {
            **copy_group_key(row["copy_group_id"]),
            "copy_group_description": row["copy_group_description"],
            "is_member_group_required": row["is_member_group_required"],
            "is_active": row["is_active"],
        }
        for row in raw_rows["copy_group"]
    ]
    projected["member_group"] = [
        {
            "tenant_code": tenant_code(row["tenant_id"]),
            "system_code": system_code(row["system_id"]),
            "member_group_name": row["member_group_name"],
            "member_group_description": row["member_group_description"],
            "member_group_initial_load_date": row["member_group_initial_load_date"],
            "is_active": row["is_active"],
        }
        for row in raw_rows["member_group"]
    ]
    projected["copy_group_control"] = [
        {
            **copy_group_key(row["copy_group_id"]),
            "member_group_name": (
                member_group_by_id[row["member_group_id"]]["member_group_name"]
                if row["member_group_id"] is not None
                else None
            ),
            "copy_group_control_initial_load_date": row["copy_group_control_initial_load_date"],
            "copy_group_control_last_run_time": row["copy_group_control_last_run_time"],
            "copy_group_control_last_run_value": row["copy_group_control_last_run_value"],
        }
        for row in raw_rows["copy_group_control"]
    ]
    projected["copy"] = []
    for row in raw_rows["copy"]:
        mapping = object_mapping_by_id[row["ingestion_object_mapping_id"]]
        projected["copy"].append(
            {
                **copy_group_key(row["copy_group_id"]),
                **object_key(mapping["source_object_id"], "source_"),
                **object_key(mapping["target_object_id"], "target_"),
                "copy_source_record_limit": (
                    str(row["copy_source_record_limit"])
                    if row["copy_source_record_limit"] is not None
                    else None
                ),
                "copy_source_record_limit_attribute": row["copy_source_record_limit_attribute"],
                "chunk_type_name": (
                    reference_value("chunk_type", row["chunk_type_id"], "chunk_type_name")
                    if row["chunk_type_id"] is not None
                    else None
                ),
                "copy_source_initial_sql_script": row["copy_source_initial_sql_script"],
                "copy_source_incremental_sql_script": row["copy_source_incremental_sql_script"],
                "copy_source_file_name": row["copy_source_file_name"],
                "copy_source_file_pattern": row["copy_source_file_pattern"],
                "copy_source_file_delimiter": row["copy_source_file_delimiter"],
                "source_file_type_name": (
                    reference_value("file_type", row["source_file_type_id"], "file_type_name")
                    if row["source_file_type_id"] is not None
                    else None
                ),
                "copy_source_order": row["copy_source_order"],
                "source_data_operation_name": reference_value(
                    "data_operation",
                    row["source_data_operation_id"],
                    "data_operation_name",
                ),
                "target_data_operation_name": reference_value(
                    "data_operation",
                    row["target_data_operation_id"],
                    "data_operation_name",
                ),
                "is_active": row["is_active"],
            }
        )
    projected["process_group"] = [
        {
            **process_group_key(row["process_group_id"]),
            "process_group_description": row["process_group_description"],
            "copy_group_name": copy_group_by_id[row["copy_group_id"]]["copy_group_name"],
            "is_active": row["is_active"],
        }
        for row in raw_rows["process_group"]
    ]
    projected["process"] = []
    for row in raw_rows["process"]:
        process_object = object_key(row["object_id"])
        projected["process"].append(
            {
                **process_group_key(row["process_group_id"]),
                "process_execution_order": row["process_execution_order"],
                "process_location": row["process_location"],
                "process_executable": row["process_executable"],
                "object_tenant_code": process_object["tenant_code"],
                "object_system_code": process_object["system_code"],
                "object_connection_code": process_object["connection_code"],
                "object_schema": process_object["object_schema"],
                "object_name": process_object["object_name"],
                "process_type_name": reference_value(
                    "process_type", row["process_type_id"], "process_type_name"
                ),
                "is_active": row["is_active"],
            }
        )
    return projected


def _by_id(rows: Rows, id_column: str) -> dict[int, Mapping[str, Any]]:
    by_id: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        identifier = row[id_column]
        if isinstance(identifier, bool) or not isinstance(identifier, int):
            raise SnapshotContractError("snapshot projection received an invalid database ID")
        if identifier in by_id:
            raise SnapshotContractError("snapshot projection received a duplicate database ID")
        by_id[identifier] = row
    return by_id


def _without(row: Mapping[str, Any], *excluded: str) -> dict[str, object]:
    return {key: value for key, value in row.items() if key not in excluded}
