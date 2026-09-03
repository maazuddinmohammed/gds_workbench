from __future__ import annotations

import json
from datetime import date
from typing import Any, cast

from gds_etl_workbench.tools.snapshots.metadata.archive import encode_dataset
from gds_etl_workbench.domain.snapshots.metadata import DATASETS
from gds_etl_workbench.tools.snapshots.metadata.projection import project_id_free_rows


def test_projection_resolves_ids_and_every_projected_row_matches_its_model() -> None:
    raw = _raw_rows()
    projected = project_id_free_rows(raw)
    encoded = {
        definition.name: encode_dataset(definition, projected[definition.name])
        for definition in DATASETS
    }

    assert set(encoded) == {definition.name for definition in DATASETS}
    assert all(
        not any(field == "id" or field.endswith("_id") for field in row)
        for dataset in encoded.values()
        for row in _decode(dataset.rows_jsonl)
    )
    tenant = _decode(encoded["tenant"].rows_jsonl)[0]
    assert tenant["project_code"] == "PROJECT"
    assert tenant["gds_connection_code"] == "GDS"
    process = _decode(encoded["process"].rows_jsonl)[0]
    assert process["object_connection_code"] == "GDS"
    assert process["object_schema"] == "dbo"


def _decode(content: bytes) -> list[dict[str, Any]]:
    return [
        cast(dict[str, Any], json.loads(line)) for line in content.decode().splitlines()
    ]


def _raw_rows() -> dict[str, list[dict[str, object]]]:
    references = {
        "system_type": [
            {
                "system_type_id": 10,
                "system_type_code": "DATABASE",
                "system_type_name": "Database",
                "system_type_description": None,
                "is_active": True,
            }
        ],
        "connection_type": [
            {
                "connection_type_id": 11,
                "connection_type_code": "POSTGRES",
                "connection_type_name": "PostgreSQL",
                "connection_type_description": None,
                "is_active": True,
            }
        ],
        "object_type": [
            {
                "object_type_id": 12,
                "object_type_code": "TABLE",
                "object_type_name": "Table",
                "object_type_description": None,
                "is_active": True,
            }
        ],
        "zone": [
            {
                "zone_id": zone_id,
                "zone_code": zone_code,
                "zone_name": zone_code.title(),
                "zone_description": None,
                "is_active": True,
            }
            for zone_id, zone_code in enumerate(
                ("source", "bronze", "silver", "gold"), start=20
            )
        ],
        "chunk_type": [
            {
                "chunk_type_id": 30,
                "chunk_type_name": "None",
                "chunk_type_description": None,
                "is_active": True,
            }
        ],
        "file_type": [
            {
                "file_type_id": 31,
                "file_type_name": "CSV",
                "file_type_description": None,
                "is_active": True,
            }
        ],
        "data_operation": [
            {
                "data_operation_id": 32,
                "data_operation_name": "Upsert",
                "data_operation_description": None,
                "is_active": True,
            }
        ],
        "process_type": [
            {
                "process_type_id": 33,
                "process_type_name": "Notebook",
                "process_type_description": None,
                "is_active": True,
            }
        ],
    }
    object_common = {
        "connection_id": 3,
        "source_tenant_id": 2,
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": None,
        "batch_attribute_name": None,
        "object_type_id": 12,
        "is_locked": False,
        "is_active": True,
    }
    attribute_common = {
        "fc_attribute_name": None,
        "attribute_ordinal_position": 1,
        "attribute_description": None,
        "attribute_data_type": "bigint",
        "attribute_nullability": False,
        "attribute_custom_code": None,
        "is_surrogate_key": False,
        "is_natural_key": True,
        "is_meta_data": False,
        "is_masking_required": False,
        "is_mapped": True,
        "is_purge": False,
        "is_active": True,
    }
    return cast(
        dict[str, list[dict[str, object]]],
        {
            "project": [
                {
                    "project_id": 1,
                    "project_code": "PROJECT",
                    "project_name": "Project",
                    "project_description": None,
                    "is_active": True,
                }
            ],
            "tenant": [
                {
                    "tenant_id": 2,
                    "project_id": 1,
                    "tenant_code": "TENANT",
                    "tenant_name": "Tenant",
                    "tenant_description": None,
                    "tenant_catalog": "tenant",
                    "gds_admin_catalog": "admin",
                    "gds_connection_id": 3,
                    "tenant_visibility": "private",
                    "is_active": True,
                }
            ],
            "system": [
                {
                    "system_id": 4,
                    "system_code": "ERP",
                    "system_name": "ERP",
                    "system_description": None,
                    "system_type_id": 10,
                    "is_active": True,
                }
            ],
            "connection": [
                {
                    "connection_id": 3,
                    "tenant_id": 2,
                    "system_id": 4,
                    "connection_code": "GDS",
                    "connection_name": "GDS",
                    "connection_type_id": 11,
                    "has_foreign_catalog": False,
                    "foreign_catalog": None,
                    "is_global_data_store": True,
                    "is_active": True,
                }
            ],
            **references,
            "source_object": [
                {
                    "object_id": 40,
                    **object_common,
                    "object_schema": "dbo",
                    "object_name": "orders_source",
                    "zone_id": 20,
                }
            ],
            "source_attribute": [
                {
                    "attribute_id": 42,
                    "object_id": 40,
                    "attribute_name": "order_id",
                    **attribute_common,
                }
            ],
            "bronze_object": [
                {
                    "object_id": 41,
                    **object_common,
                    "object_schema": "dbo",
                    "object_name": "orders_bronze",
                    "zone_id": 21,
                }
            ],
            "bronze_attribute": [
                {
                    "attribute_id": 43,
                    "object_id": 41,
                    "attribute_name": "order_id",
                    **attribute_common,
                }
            ],
            "silver_object": [],
            "silver_attribute": [],
            "gold_object": [],
            "gold_attribute": [],
            "ingestion_object_mapping": [
                {
                    "ingestion_object_mapping_id": 50,
                    "source_object_id": 40,
                    "target_object_id": 41,
                    "is_active": True,
                }
            ],
            "ingestion_attribute_mapping": [
                {
                    "ingestion_attribute_mapping_id": 51,
                    "ingestion_object_mapping_id": 50,
                    "source_object_id": 40,
                    "target_object_id": 41,
                    "source_attribute_id": 42,
                    "target_attribute_id": 43,
                    "is_active": True,
                }
            ],
            "copy_group": [
                {
                    "copy_group_id": 60,
                    "tenant_id": 2,
                    "system_id": 4,
                    "copy_group_name": "daily",
                    "copy_group_description": None,
                    "is_member_group_required": True,
                    "is_active": True,
                }
            ],
            "member_group": [
                {
                    "member_group_id": 61,
                    "tenant_id": 2,
                    "system_id": 4,
                    "member_group_name": "north",
                    "member_group_description": None,
                    "member_group_initial_load_date": date(2026, 8, 1),
                    "is_active": True,
                }
            ],
            "copy_group_control": [
                {
                    "copy_group_control_id": 62,
                    "copy_group_id": 60,
                    "member_group_id": 61,
                    "tenant_id": 2,
                    "system_id": 4,
                    "copy_group_control_initial_load_date": None,
                    "copy_group_control_last_run_time": None,
                    "copy_group_control_last_run_value": None,
                }
            ],
            "copy": [
                {
                    "copy_id": 63,
                    "copy_group_id": 60,
                    "ingestion_object_mapping_id": 50,
                    "copy_source_record_limit": 10,
                    "copy_source_record_limit_attribute": None,
                    "chunk_type_id": 30,
                    "copy_source_initial_sql_script": "select * from dbo.orders_source",
                    "copy_source_incremental_sql_script": None,
                    "copy_source_file_name": None,
                    "copy_source_file_pattern": None,
                    "copy_source_file_delimiter": None,
                    "source_file_type_id": 31,
                    "copy_source_order": 1,
                    "source_data_operation_id": 32,
                    "target_data_operation_id": 32,
                    "is_active": True,
                }
            ],
            "process_group": [
                {
                    "process_group_id": 70,
                    "tenant_id": 2,
                    "system_id": 4,
                    "zone_id": 21,
                    "process_group_name": "bronze_load",
                    "process_group_description": None,
                    "copy_group_id": 60,
                    "is_active": True,
                }
            ],
            "process": [
                {
                    "process_id": 71,
                    "connection_id": 3,
                    "object_id": 41,
                    "process_execution_order": 1,
                    "process_location": "/bronze",
                    "process_executable": "load",
                    "process_type_id": 33,
                    "process_group_id": 70,
                    "is_active": True,
                }
            ],
        },
    )
