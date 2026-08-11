from __future__ import annotations

from gds_etl_workbench.tools.snapshots.metadata.archive import build_schema_document
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS,
    TABLES,
    SnapshotSection,
)

EXPECTED_DATASET_NAMES = (
    "project",
    "tenant",
    "system",
    "connection",
    "tenant_metadata_discovery_scope",
    "system_type",
    "connection_type",
    "object_type",
    "zone",
    "chunk_type",
    "file_type",
    "data_operation",
    "process_type",
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
)


def test_metadata_snapshot_registry_has_exact_dataset_contract() -> None:
    assert tuple(dataset.name for dataset in DATASETS) == EXPECTED_DATASET_NAMES
    assert len({dataset.name for dataset in DATASETS}) == 29
    assert len({dataset.database_table for dataset in DATASETS}) == 23

    foundation = tuple(
        dataset for dataset in DATASETS if dataset.section is SnapshotSection.FOUNDATION
    )
    metadata = tuple(dataset for dataset in DATASETS if dataset.section is SnapshotSection.METADATA)
    assert len(foundation) == 13
    assert len(metadata) == 16
    assert all(not dataset.change_set_eligible for dataset in foundation)
    assert all(dataset.change_set_eligible for dataset in metadata)


def test_metadata_snapshot_registry_uses_fixed_safe_paths() -> None:
    data_paths = {dataset.data_path for dataset in DATASETS}
    index_paths = {dataset.index_path for dataset in DATASETS}

    assert len(data_paths) == 29
    assert len(index_paths) == 29
    assert data_paths.isdisjoint(index_paths)
    assert next(dataset for dataset in DATASETS if dataset.name == "project").data_path == (
        "foundation/core/project/rows.jsonl"
    )
    assert (
        next(dataset for dataset in DATASETS if dataset.name == "system_type").index_path
        == "foundation/reference/system_type/index.jsonl"
    )
    assert (
        next(dataset for dataset in DATASETS if dataset.name == "gold_attribute").data_path
        == "metadata/core/gold_attribute/rows.jsonl"
    )
    assert all(".." not in path.split("/") and not path.startswith("/") for path in data_paths)


def test_zone_datasets_share_physical_tables_without_sharing_paths() -> None:
    object_datasets = tuple(
        dataset for dataset in DATASETS if dataset.database_table == "core.object"
    )
    attribute_datasets = tuple(
        dataset for dataset in DATASETS if dataset.database_table == "core.attribute"
    )

    assert tuple(dataset.name for dataset in object_datasets) == (
        "source_object",
        "bronze_object",
        "silver_object",
        "gold_object",
    )
    assert tuple(dataset.name for dataset in attribute_datasets) == (
        "source_attribute",
        "bronze_attribute",
        "silver_attribute",
        "gold_attribute",
    )
    assert len({dataset.data_path for dataset in (*object_datasets, *attribute_datasets)}) == 8


def test_physical_schema_contract_is_closed_and_self_consistent() -> None:
    assert len(TABLES) == 23
    assert len({table.database_table for table in TABLES}) == 23
    tables = {table.database_table: table for table in TABLES}

    for dataset in DATASETS:
        table = tables[dataset.database_table]
        column_names = {column.name for column in table.columns}
        assert set(dataset.primary_key) <= column_names
        assert set(dataset.display_columns) <= column_names
        assert all(set(group) <= column_names for group in table.unique_column_groups)
        for foreign_key in table.foreign_keys:
            assert set(foreign_key.columns) <= column_names
            referenced_table = tables[foreign_key.references_table]
            referenced_columns = {column.name for column in referenced_table.columns}
            assert set(foreign_key.references_columns) <= referenced_columns
            assert len(foreign_key.columns) == len(foreign_key.references_columns)


def test_schema_document_contains_complete_viewer_metadata() -> None:
    schema = build_schema_document()
    assert schema["schema_version"] == "1.0"
    assert schema["snapshot_kind"] == "metadata"
    datasets = schema["datasets"]
    assert isinstance(datasets, list)
    assert len(datasets) == 29

    source_object = next(dataset for dataset in datasets if dataset["name"] == "source_object")
    bronze_object = next(dataset for dataset in datasets if dataset["name"] == "bronze_object")
    assert source_object == {
        "name": "source_object",
        "label": "Source Objects",
        "database_table": "core.object",
        "section": "metadata",
        "change_set_eligible": True,
        "data_files": ["metadata/core/source_object/rows.jsonl"],
        "primary_key": ["object_id"],
        "display_columns": ["object_schema", "object_name"],
        "unique_column_groups": [
            ["object_id", "connection_id"],
            ["object_id", "zone_id"],
            ["connection_id", "object_schema", "object_name"],
        ],
        "columns": [
            {
                "name": column.name,
                "type": column.type,
                "nullable": column.nullable,
                "generated": column.generated,
            }
            for column in next(
                table for table in TABLES if table.database_table == "core.object"
            ).columns
        ],
        "foreign_keys": [
            {
                "columns": ["connection_id"],
                "references_table": "core.connection",
                "references_columns": ["connection_id"],
            },
            {
                "columns": ["object_type_id"],
                "references_table": "reference.object_type",
                "references_columns": ["object_type_id"],
            },
            {
                "columns": ["zone_id"],
                "references_table": "reference.zone",
                "references_columns": ["zone_id"],
            },
        ],
    }
    assert bronze_object["columns"] == source_object["columns"]
    assert bronze_object["foreign_keys"] == source_object["foreign_keys"]
    assert bronze_object["data_files"] == ["metadata/core/bronze_object/rows.jsonl"]
