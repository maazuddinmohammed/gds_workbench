from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from gds_etl_workbench.domain.metadata_records import (
    CopyGroupControlRecord,
    CopyRecord,
    IngestionAttributeMappingRecord,
    IngestionObjectMappingRecord,
)
from gds_etl_workbench.domain.portable_validation import METADATA_RECORD_VALIDATIONS
from gds_etl_workbench.tools.snapshots.metadata.archive import (
    build_dataset_document,
)
from gds_etl_workbench.domain.snapshots.metadata import (
    DATASETS,
    PHYSICAL_TABLE_COUNT,
    SnapshotSection,
)

EXPECTED_DATASET_NAMES = (
    "project",
    "tenant",
    "system",
    "connection",
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


def test_metadata_records_reject_database_constraint_failures_before_apply() -> None:
    object_mapping = {
        **{
            f"{side}_{field}": "same"
            for side in ("source", "target")
            for field in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        },
        "is_active": True,
    }
    attribute_mapping = {
        **object_mapping,
        "source_attribute_name": "same",
        "target_attribute_name": " SAME ",
    }
    copy = {
        "tenant_code": "TENANT",
        "system_code": "SYSTEM",
        "copy_group_name": "GROUP",
        **{key: value for key, value in object_mapping.items() if key != "is_active"},
        "copy_source_record_limit": "9223372036854775808",
        "copy_source_record_limit_attribute": None,
        "chunk_type_name": None,
        "copy_source_initial_sql_script": None,
        "copy_source_incremental_sql_script": None,
        "copy_source_file_name": None,
        "copy_source_file_pattern": None,
        "copy_source_file_delimiter": None,
        "source_file_type_name": None,
        "copy_source_order": 1,
        "source_data_operation_name": "APPEND",
        "target_data_operation_name": "APPEND",
        "is_active": True,
    }

    invalid = (
        (IngestionObjectMappingRecord, object_mapping),
        (IngestionAttributeMappingRecord, attribute_mapping),
        (
            CopyGroupControlRecord,
            {
                "tenant_code": "TENANT",
                "system_code": "SYSTEM",
                "copy_group_name": "GROUP",
                "member_group_name": None,
                "copy_group_control_initial_load_date": None,
                "copy_group_control_last_run_time": None,
                "copy_group_control_last_run_value": "   ",
            },
        ),
        (CopyRecord, copy),
    )
    for model, record in invalid:
        with pytest.raises(ValidationError):
            model.model_validate(record)


def test_every_custom_metadata_record_validator_is_exported_for_local_parity() -> None:
    custom = {
        definition.name
        for definition in DATASETS
        if definition.row_model.__pydantic_decorators__.field_validators
        or definition.row_model.__pydantic_decorators__.model_validators
    }

    assert set(METADATA_RECORD_VALIDATIONS) == custom
    for definition in DATASETS:
        if definition.name not in custom:
            continue
        assert build_dataset_document(definition).schema["x-gds-record-validation"] == {
            "version": "1.0",
            "rules": list(METADATA_RECORD_VALIDATIONS[definition.name]),
        }


def _object_value(document: dict[str, object], key: str) -> dict[str, object]:
    value = document[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _object_list_value(
    document: dict[str, object],
    key: str,
) -> list[dict[str, object]]:
    value = document[key]
    assert isinstance(value, list)
    items = cast(list[object], value)
    assert all(isinstance(item, dict) for item in items)
    return cast(list[dict[str, object]], items)


def _string_list_value(document: dict[str, object], key: str) -> list[str]:
    value = document[key]
    assert isinstance(value, list)
    items = cast(list[object], value)
    assert all(isinstance(item, str) for item in items)
    return cast(list[str], items)


def _columns_by_name(schema: dict[str, object]) -> dict[str, dict[str, object]]:
    columns: dict[str, dict[str, object]] = {}
    for column in _object_list_value(schema, "x-gds-columns"):
        name = column["name"]
        assert isinstance(name, str)
        columns[name] = column
    return columns


def test_metadata_snapshot_registry_has_exact_dataset_contract() -> None:
    assert tuple(dataset.name for dataset in DATASETS) == EXPECTED_DATASET_NAMES
    assert len({dataset.name for dataset in DATASETS}) == 28
    assert PHYSICAL_TABLE_COUNT == 22

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
    assert len(foundational) == 4
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

    assert len(rows_paths) == 28
    assert len(schema_paths) == 28
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
    assert "is_locked" in object_datasets[0].row_model.model_fields
    assert "is_locked" not in attribute_datasets[0].row_model.model_fields


def test_dataset_schema_exposes_enforced_fields_keys_and_references() -> None:
    source_object = next(
        dataset for dataset in DATASETS if dataset.name == "source_object"
    )
    schema = build_dataset_document(source_object).schema

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
    assert schema["x-gds-key-normalization"] == {
        "version": "1.0",
        "string_field_suffixes": ["_code", "_name", "_schema"],
        "trim_code_points": ["U+0020"],
        "case": "unicode-lowercase",
        "unicode_normalization": "none",
        "other_values": "identity",
    }
    assert schema["x-gds-references"] == [
        {
            "columns": ["tenant_code"],
            "target_record_type": "tenant",
            "target_columns": ["tenant_code"],
            "nullable": False,
        },
        {
            "columns": ["source_tenant_code"],
            "target_record_type": "tenant",
            "target_columns": ["tenant_code"],
            "nullable": False,
        },
        {
            "columns": ["system_code"],
            "target_record_type": "system",
            "target_columns": ["system_code"],
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
    properties = _object_value(schema, "properties")
    assert _object_value(properties, "zone_code")["const"] == "source"


def test_all_dataset_columns_publish_complete_authoring_guidance() -> None:
    accepted_kinds = {"fixed", "literal", "reference", "constrained", "freeform"}

    for dataset in DATASETS:
        schema = build_dataset_document(dataset).schema
        properties = _object_value(schema, "properties")
        columns = _object_list_value(schema, "x-gds-columns")
        assert [column["name"] for column in columns] == list(
            dataset.row_model.model_fields
        )
        assert schema["x-gds-population-rules"]

        for column in columns:
            name = column["name"]
            description = column["description"]
            population_guidance = column["population_guidance"]
            assert isinstance(name, str)
            assert isinstance(description, str) and description
            assert isinstance(population_guidance, str) and population_guidance
            accepted_values = _object_value(column, "accepted_values")
            property_schema = _object_value(properties, name)
            assert accepted_values["kind"] in accepted_kinds
            assert property_schema["description"] == description
            assert property_schema["x-gds-population-guidance"] == population_guidance
            assert property_schema["x-gds-accepted-values"] == accepted_values


def test_column_guidance_distinguishes_value_sources_and_constraints() -> None:
    source_object = build_dataset_document(
        next(dataset for dataset in DATASETS if dataset.name == "source_object")
    ).schema
    source_columns = _columns_by_name(source_object)

    assert source_columns["zone_code"]["accepted_values"] == {
        "kind": "fixed",
        "values": ["source"],
        "references": [
            {
                "record_type": "zone",
                "datasets": ["zone"],
                "column": "zone_code",
                "composite_columns": ["zone_code"],
                "target_columns": ["zone_code"],
                "nullable": False,
            }
        ],
        "constraints": {},
    }
    assert (
        _object_value(source_columns["object_type_code"], "accepted_values")["kind"]
        == "reference"
    )
    assert _object_value(source_columns["is_active"], "accepted_values")["values"] == [
        False,
        True,
    ]

    tenant = build_dataset_document(
        next(dataset for dataset in DATASETS if dataset.name == "tenant")
    ).schema
    tenant_columns = _columns_by_name(tenant)
    assert _object_value(tenant_columns["tenant_visibility"], "accepted_values")[
        "values"
    ] == [
        "global",
        "private",
    ]
    assert any(
        "must be populated together" in rule
        for rule in _string_list_value(tenant, "x-gds-population-rules")
    )

    copy_dataset = build_dataset_document(
        next(dataset for dataset in DATASETS if dataset.name == "copy")
    ).schema
    copy_columns = _columns_by_name(copy_dataset)
    copy_record_limit_values = _object_value(
        copy_columns["copy_source_record_limit"],
        "accepted_values",
    )
    assert copy_record_limit_values["kind"] == "constrained"
    assert copy_record_limit_values["constraints"]
