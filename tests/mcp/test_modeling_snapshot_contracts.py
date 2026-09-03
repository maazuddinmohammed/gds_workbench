from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    ProfilingProfileRecord,
    ValidationCheckRecord,
)
from gds_etl_workbench.domain.portable_validation import MODEL_RECORD_VALIDATIONS
from gds_etl_workbench.tools.snapshots.archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.model.archive import (
    build_model_snapshot_archive,
    encode_model_snapshot,
)
from gds_etl_workbench.domain.snapshots.model import (
    CHANGE_SET_DATASETS,
    DATASETS,
    DATASETS_BY_NAME,
    MODEL_SECTIONS,
    build_model_dataset_schema,
    model_snapshot_records,
)
from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    snapshot_from_graph,
)

EXPECTED_DATASETS = (
    "model_details",
    "model_input_scope",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "model_object_binding",
    "model_attribute_binding",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "generated_code_source_system",
    "validation_group",
    "validation_check",
)


def test_model_snapshot_has_exact_25_dataset_registry() -> None:
    assert tuple(definition.name for definition in DATASETS) == EXPECTED_DATASETS
    assert len(DATASETS_BY_NAME) == 25
    assert CHANGE_SET_DATASETS == DATASETS
    assert MODEL_SECTIONS == (
        "model_input_scope",
        "profiling",
        "analysis",
        "assertion",
        "conceptual",
        "logical",
        "dimensional",
        "model_binding",
        "mapping",
        "code_generation",
        "validation",
    )


def test_every_dataset_is_id_free_and_uses_real_canonical_key_fields() -> None:
    for definition in DATASETS:
        fields = set(definition.row_model.model_fields)
        assert not any(field == "id" or field.endswith("_id") for field in fields)
        assert set(definition.canonical_key) <= fields
        assert definition.change_set_eligible is True
        assert definition.rows_path.startswith(f"data/{definition.section}/")
        assert definition.schema_path == f"schemas/model/{definition.name}.schema.json"


def test_model_schemas_forbid_removed_authoring_metadata() -> None:
    forbidden = {
        "agent_run_id",
        "workflow_run_id",
        "mapping_profile_key",
        "mapping_profile_version",
        "mapping_package_document",
        "package_digest",
        "mapping_context_digest",
        "source_context_digest",
        "generated_code_digest",
        "generated_code_is_locked",
        "is_logged",
        "execution_result",
    }

    for definition in DATASETS:
        schema = build_model_dataset_schema(definition)
        assert schema["additionalProperties"] is False
        assert schema["x-gds-database-ids-included"] is False
        assert schema["x-gds-change-set-eligible"] is True
        assert forbidden.isdisjoint(schema["properties"])


def test_every_custom_model_record_validator_is_exported_for_local_parity() -> None:
    custom = {
        definition.name
        for definition in DATASETS
        if definition.row_model.__pydantic_decorators__.field_validators
        or definition.row_model.__pydantic_decorators__.model_validators
    }

    assert set(MODEL_RECORD_VALIDATIONS) == custom
    for dataset, rules in MODEL_RECORD_VALIDATIONS.items():
        assert build_model_dataset_schema(DATASETS_BY_NAME[dataset])[
            "x-gds-record-validation"
        ] == {"version": "1.0", "rules": list(rules)}


def test_model_schema_accepts_every_decimal_representation_accepted_at_stage() -> None:
    schema = build_model_dataset_schema(DATASETS_BY_NAME["profiling_profile"])

    assert schema["properties"]["avg_data_length"]["anyOf"][0] == {
        "minimum": 0.0,
        "type": "number",
    }
    assert schema["properties"]["percent_populated"]["anyOf"][0] == {
        "maximum": 100.0,
        "minimum": 0.0,
        "type": "number",
    }


def test_status_contract_has_only_applied_lifecycle_values() -> None:
    for dataset in (
        "conceptual_object",
        "logical_entity",
        "dimensional_entity",
        "model_object_binding",
        "mapping_object",
        "generated_code",
    ):
        schema = build_model_dataset_schema(DATASETS_BY_NAME[dataset])
        status_property = next(
            value
            for name, value in schema["properties"].items()
            if name.endswith("_status")
        )
        assert status_property["enum"] == ["active", "inactive", "deprecated"]


def test_logical_entity_schema_exports_server_type_detail_rule() -> None:
    schema = build_model_dataset_schema(DATASETS_BY_NAME["logical_entity"])

    assert schema["allOf"] == [
        {
            "if": {
                "properties": {"logical_entity_type": {"const": "other"}},
                "required": ["logical_entity_type"],
            },
            "then": {
                "properties": {"logical_entity_type_detail": {"type": "string"}}
            },
            "else": {
                "properties": {"logical_entity_type_detail": {"type": "null"}}
            },
        }
    ]


def test_generated_code_and_validation_public_shapes_are_minimal() -> None:
    generated = build_model_dataset_schema(DATASETS_BY_NAME["generated_code"])
    source_system = build_model_dataset_schema(
        DATASETS_BY_NAME["generated_code_source_system"]
    )
    group = build_model_dataset_schema(DATASETS_BY_NAME["validation_group"])

    assert set(generated["properties"]) == {
        "modeled_entity_type",
        "modeled_entity_name",
        "artifact_name",
        "artifact_type",
        "generated_code_content",
        "generated_code_status",
    }
    assert set(source_system["properties"]) == {
        "modeled_entity_type",
        "modeled_entity_name",
        "artifact_name",
        "source_system_code",
        "generated_code_source_system_status",
    }
    assert set(group["properties"]) == {
        "tenant_code",
        "system_code",
        "validation_group_name",
        "validation_group_description",
        "is_active",
    }


def test_records_reject_database_or_removed_fields() -> None:
    graph = complete_model_graph()

    assert ProfilingProfileRecord.model_validate(
        graph["profiling_profile"][0], strict=False
    )
    assert GeneratedCodeRecord.model_validate(graph["generated_code"][0], strict=False)
    assert ValidationCheckRecord.model_validate(
        graph["validation_check"][0], strict=False
    )

    for model, record, extra in (
        (ProfilingProfileRecord, graph["profiling_profile"][0], {"attribute_id": 1}),
        (GeneratedCodeRecord, graph["generated_code"][0], {"is_logged": True}),
        (
            ValidationCheckRecord,
            graph["validation_check"][0],
            {"execution_result": "passed"},
        ),
    ):
        with pytest.raises(ValidationError):
            model.model_validate({**record, **extra}, strict=False)


def test_snapshot_flattens_binding_mapping_code_and_validation_sections() -> None:
    graph = complete_model_graph()
    records = model_snapshot_records(snapshot_from_graph(graph))

    assert tuple(records) == EXPECTED_DATASETS
    assert len(records["model_object_binding"]) == 4
    assert len(records["model_attribute_binding"]) == 6
    assert len(records["mapping_object"]) == 1
    assert len(records["generated_code"]) == 1
    assert len(records["generated_code_source_system"]) == 1
    assert len(records["validation_group"]) == 1
    assert len(records["validation_check"]) == 1


def test_snapshot_encoding_sorts_rows_and_rejects_duplicate_keys() -> None:
    graph = complete_model_graph()
    graph["conceptual_object"].reverse()
    encoded = {
        item.definition.name: item
        for item in encode_model_snapshot(snapshot_from_graph(graph))
    }
    rows = encoded["conceptual_object"].rows_jsonl.decode().splitlines()
    assert [json.loads(row)["conceptual_object_name"] for row in rows] == [
        "Customer",
        "Order",
    ]

    duplicate = deepcopy(graph["conceptual_object"][0])
    duplicate["conceptual_object_name"] = (
        f" {duplicate['conceptual_object_name'].upper()} "
    )
    graph["conceptual_object"].append(duplicate)
    with pytest.raises(SnapshotContractError, match="duplicate canonical key"):
        encode_model_snapshot(snapshot_from_graph(graph))


def test_snapshot_archive_catalogs_all_sections_and_datasets(tmp_path: Path) -> None:
    snapshot = snapshot_from_graph(complete_model_graph()).model_copy(update={
        "model_tenant_code": "TENANT_A",
        "other_active_model_names": ("Legacy Model", "Other Model"),
    })
    created_at = datetime(2026, 9, 1, tzinfo=UTC)
    output = tmp_path / "model-snapshot.zip"

    result = build_model_snapshot_archive(
        output,
        snapshot_id=uuid4(),
        snapshot=snapshot,
        created_time=created_at,
        available_until=created_at + timedelta(hours=1),
        max_archive_bytes=16 * 1024 * 1024,
    )

    assert result.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        catalog = json.loads(archive.read("model-snapshot/catalog.json"))
        manifest = json.loads(archive.read("model-snapshot/manifest.json"))
        names = archive.namelist()

    sections = {section["name"]: section for section in catalog["sections"]}
    assert tuple(sections) == MODEL_SECTIONS
    assert [item["name"] for item in sections["model_binding"]["datasets"]] == [
        "model_object_binding",
        "model_attribute_binding",
    ]
    assert [item["name"] for item in sections["code_generation"]["datasets"]] == [
        "generated_code",
        "generated_code_source_system",
    ]
    assert [item["name"] for item in sections["validation"]["datasets"]] == [
        "validation_group",
        "validation_check",
    ]
    assert catalog["model"]["tenant_code"] == "TENANT_A"
    assert catalog["model"]["other_active_model_names"] == [
        "Legacy Model",
        "Other Model",
    ]
    assert manifest["counts"]["logical_dataset_count"] == 25
    assert manifest["database_ids_included"] is False
    assert len([name for name in names if name.endswith(".schema.json")]) == 25
    assert len([name for name in names if name.endswith("rows.jsonl")]) == 25
    assert not any("qa" in name.casefold() or "model_scope" in name for name in names)
