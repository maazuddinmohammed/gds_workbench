from __future__ import annotations

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    build_dataset_schema_document,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS,
    PHYSICAL_TABLE_COUNT,
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
    assert PHYSICAL_TABLE_COUNT == 23

    foundational = tuple(
        dataset
        for dataset in DATASETS
        if dataset.section is SnapshotSection.FOUNDATIONAL
    )
    reference = tuple(
        dataset for dataset in DATASETS if dataset.section is SnapshotSection.REFERENCE
    )
    operational = tuple(
        dataset
        for dataset in DATASETS
        if dataset.section is SnapshotSection.OPERATIONAL
    )
    assert len(foundational) == 5
    assert len(reference) == 8
    assert len(operational) == 16
    assert all(
        not dataset.change_set_eligible for dataset in (*foundational, *reference)
    )
    assert all(dataset.change_set_eligible for dataset in operational)


def test_registry_uses_flat_rows_per_dataset_schemas_and_selective_lookups() -> None:
    rows_paths = {dataset.rows_path for dataset in DATASETS}
    schema_paths = {dataset.schema_path for dataset in DATASETS}
    lookup_paths = {
        dataset.lookup_path for dataset in DATASETS if dataset.lookup_path is not None
    }

    assert len(rows_paths) == 29
    assert len(schema_paths) == 29
    assert len(lookup_paths) == 10
    assert next(
        dataset for dataset in DATASETS if dataset.name == "project"
    ).rows_path == ("data/foundational/project/rows.jsonl")
    assert (
        next(
            dataset for dataset in DATASETS if dataset.name == "source_object"
        ).lookup_path
        == "data/operational/source_object/lookup.jsonl"
    )
    assert (
        next(dataset for dataset in DATASETS if dataset.name == "system_type").rows_path
        == "data/reference/system_type/rows.jsonl"
    )
    assert (
        next(
            dataset for dataset in DATASETS if dataset.name == "system_type"
        ).lookup_path
        is None
    )
    assert all(
        ".." not in path.split("/") and not path.startswith("/") for path in rows_paths
    )


def test_all_row_models_are_id_free_and_keys_are_real_fields() -> None:
    for dataset in DATASETS:
        fields = set(dataset.row_model.model_fields)
        assert not any(field == "id" or field.endswith("_id") for field in fields)
        assert set(dataset.canonical_key) <= fields
        assert all(
            set(constraint) <= fields for constraint in dataset.unique_constraints
        )
        assert set(dataset.lookup_fields) <= fields
        for reference in dataset.references:
            assert set(reference.columns) <= fields
            assert len(reference.columns) == len(reference.target_columns)


def test_zone_datasets_share_record_models_without_nested_attributes() -> None:
    object_datasets = tuple(
        dataset for dataset in DATASETS if dataset.record_type == "object"
    )
    attribute_datasets = tuple(
        dataset for dataset in DATASETS if dataset.record_type == "attribute"
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
    assert "attributes" not in object_datasets[0].row_model.model_fields


def test_dataset_schema_exposes_enforced_fields_keys_and_references() -> None:
    source_object = next(
        dataset for dataset in DATASETS if dataset.name == "source_object"
    )
    schema = build_dataset_schema_document(source_object)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "schemas/source_object.schema.json"
    assert schema["additionalProperties"] is False
    assert schema["x-gds-canonical-key"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    ]
    assert schema["x-gds-unique-constraints"] == [schema["x-gds-canonical-key"]]
    assert schema["x-gds-references"] == [
        {
            "columns": ["tenant_code", "system_code", "connection_code"],
            "target_record_type": "connection",
            "target_columns": ["tenant_code", "system_code", "connection_code"],
            "nullable": False,
        },
        {
            "columns": ["object_type_code"],
            "target_record_type": "object_type",
            "target_columns": ["object_type_code"],
            "nullable": False,
        },
        {
            "columns": ["zone_code"],
            "target_record_type": "zone",
            "target_columns": ["zone_code"],
            "nullable": False,
        },
    ]
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert properties["zone_code"]["const"] == "source"
