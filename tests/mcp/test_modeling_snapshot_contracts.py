from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    DimensionalAttributeRecord,
    GeneratedCodeRecord,
    LogicalAttributeRecord,
    ProfilingProfileRecord,
    ValidationCheckRecord,
)
from gds_etl_workbench.domain.portable_validation import PROJECT_RECORD_VALIDATIONS
from gds_etl_workbench.domain.snapshots.project import (
    CHANGE_SET_DATASETS,
    DATASETS,
    DATASETS_BY_NAME,
    PROJECT_SECTIONS,
    ProjectChangeSetDataset,
    ProjectSnapshot,
    build_project_dataset_schema,
    project_snapshot_records,
)
from gds_etl_workbench.infrastructure.snapshot_archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.project.archive import (
    build_project_snapshot_archive,
    encode_project_snapshot,
)
from pydantic import ValidationError

from tests.mcp.project_test_fixtures import (
    complete_project_graph,
    snapshot_from_graph,
)

EXPECTED_DATASETS = (
    "project_details",
    "project_input_scope",
    "profiling_profile",
    "object_enrichment",
    "attribute_enrichment",
    "analysis_result",
    "context_type",
    "context_group",
    "context_record",
    "subject_area",
    "subject_area_table",
    "logical_entity_type",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_fact_type",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "generated_code_source_system",
    "validation_group",
    "validation_check",
)
READ_ONLY_DATASETS = {"context_type", "logical_entity_type", "dimensional_fact_type"}
MODEL_DATASETS = (
    "subject_area",
    "subject_area_table",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
)


def test_project_snapshot_has_exact_25_dataset_registry() -> None:
    assert tuple(definition.name for definition in DATASETS) == EXPECTED_DATASETS
    assert len(DATASETS_BY_NAME) == 25
    assert CHANGE_SET_DATASETS == tuple(d for d in DATASETS if d.name not in READ_ONLY_DATASETS)
    assert len(CHANGE_SET_DATASETS) == 22
    assert PROJECT_SECTIONS == (
        "project_input_scope",
        "profiling",
        "enrichment",
        "analysis",
        "context",
        "subject_area",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
        "validation",
    )


def test_every_dataset_is_id_free_and_uses_real_canonical_key_fields() -> None:
    for definition in DATASETS:
        fields = set(definition.row_model.model_fields)
        assert {field for field in fields if field == "id" or field.endswith("_id")} == (
            {"context_record_id"} if definition.name == "context_record" else set()
        )
        assert set(definition.canonical_key) <= fields
        assert definition.change_set_eligible is (definition.name not in READ_ONLY_DATASETS)
        assert definition.rows_path.startswith(f"data/{definition.section}/")
        assert definition.schema_path == f"schemas/project/{definition.name}.schema.json"


def test_project_schemas_forbid_removed_authoring_metadata() -> None:
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
        "is_logged",
        "execution_result",
    }

    for definition in DATASETS:
        schema = build_project_dataset_schema(definition)
        assert schema["additionalProperties"] is False
        assert schema["x-gds-database-ids-included"] is False
        assert schema["x-gds-portable-identity-fields"] == (
            ["context_record_id"] if definition.name == "context_record" else []
        )
        assert schema["x-gds-change-set-eligible"] is (definition.name not in READ_ONLY_DATASETS)
        assert forbidden.isdisjoint(schema["properties"])


def test_logical_attribute_contract_uses_key_origins_without_primary_key() -> None:
    schema = build_project_dataset_schema(DATASETS_BY_NAME["logical_attribute"])
    assert "logical_attribute_is_primary_key" not in schema["properties"]
    record = complete_project_graph()["logical_attribute"][0]
    validated = LogicalAttributeRecord.model_validate_json(json.dumps(record))
    assert validated.logical_attribute_is_natural_key
    assert not validated.logical_attribute_is_surrogate_key
    assert not validated.logical_attribute_is_audit_column
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LogicalAttributeRecord.model_validate_json(
            json.dumps({**record, "logical_attribute_is_primary_key": True})
        )
    with pytest.raises(ValidationError, match="cannot be nullable"):
        LogicalAttributeRecord.model_validate_json(
            json.dumps({**record, "logical_attribute_is_nullable": True})
        )
    with pytest.raises(ValidationError, match="both natural and surrogate"):
        LogicalAttributeRecord.model_validate_json(
            json.dumps({**record, "logical_attribute_is_surrogate_key": True})
        )


@pytest.mark.parametrize("flag", ["natural", "surrogate"])
def test_dimensional_key_flags_enforce_identity_and_nullability(flag: str) -> None:
    record = {
        **complete_project_graph()["dimensional_attribute"][0],
        "dimensional_attribute_is_natural_key": flag == "natural",
        "dimensional_attribute_is_surrogate_key": flag == "surrogate",
    }
    DimensionalAttributeRecord.model_validate_json(json.dumps(record))
    with pytest.raises(ValidationError, match="cannot be nullable"):
        DimensionalAttributeRecord.model_validate_json(
            json.dumps({**record, "dimensional_attribute_is_nullable": True})
        )
    with pytest.raises(ValidationError, match="both natural and surrogate"):
        DimensionalAttributeRecord.model_validate_json(
            json.dumps(
                {
                    **record,
                    "dimensional_attribute_is_natural_key": True,
                    "dimensional_attribute_is_surrogate_key": True,
                }
            )
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("dimensional_attribute_role", "measure"),
        ("dimensional_attribute_key_role", "business"),
        ("dimensional_attribute_is_grain_component", True),
        ("dimensional_attribute_additivity", "additive"),
        ("dimensional_attribute_default_aggregation", "SUM"),
        ("dimensional_attribute_aggregation_basis", "Across products"),
        ("dimensional_attribute_change_behavior", "historize"),
        ("dimensional_attribute_confidence", "high"),
    ],
)
def test_dimensional_records_reject_removed_fields(field: str, value: object) -> None:
    record = complete_project_graph()["dimensional_attribute"][0]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DimensionalAttributeRecord.model_validate_json(json.dumps({**record, field: value}))


def test_published_project_schemas_have_no_confidence_fields() -> None:
    def inspect(value: object) -> None:
        if isinstance(value, dict):
            properties = value.get("properties", {})
            assert not any(name.endswith("confidence") for name in properties)
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    for definition in DATASETS:
        inspect(build_project_dataset_schema(definition))


def test_every_custom_project_record_validator_is_exported_for_local_parity() -> None:
    custom = {
        definition.name
        for definition in DATASETS
        if definition.row_model.__pydantic_decorators__.field_validators
        or definition.row_model.__pydantic_decorators__.model_validators
    }

    assert set(PROJECT_RECORD_VALIDATIONS) == custom
    for dataset, rules in PROJECT_RECORD_VALIDATIONS.items():
        assert build_project_dataset_schema(DATASETS_BY_NAME[dataset])[
            "x-gds-record-validation"
        ] == {
            "version": "1.0",
            "rules": list(rules),
        }


def test_project_schema_accepts_every_decimal_representation_accepted_at_stage() -> None:
    schema = build_project_dataset_schema(DATASETS_BY_NAME["profiling_profile"])

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
    for dataset in ("mapping_object", "generated_code"):
        schema = build_project_dataset_schema(DATASETS_BY_NAME[dataset])
        status_property = next(
            value for name, value in schema["properties"].items() if name.endswith("_status")
        )
        assert status_property["enum"] == ["active", "inactive", "deprecated"]


@pytest.mark.parametrize("dataset", MODEL_DATASETS)
def test_model_records_use_an_is_active_boolean_instead_of_status(dataset: str) -> None:
    schema = build_project_dataset_schema(DATASETS_BY_NAME[dataset])

    assert schema["properties"][f"{dataset}_is_active"]["type"] == "boolean"
    assert f"{dataset}_is_active" in schema["required"]
    assert not any(name.endswith("_status") for name in schema["properties"])
    nested = schema["$defs"]
    assert not any(
        name in {"status", "source_order"}
        for definition in nested.values()
        for name in definition.get("properties", {})
    )


def test_type_codes_come_from_read_only_reference_lists() -> None:
    entity = build_project_dataset_schema(DATASETS_BY_NAME["logical_entity"])
    dimensional = build_project_dataset_schema(DATASETS_BY_NAME["dimensional_entity"])

    assert "allOf" not in entity
    assert "logical_entity_type_detail" not in entity["properties"]
    assert entity["properties"]["logical_entity_type"]["pattern"] == r"^[a-z][a-z0-9_]{0,49}$"
    assert "enum" not in entity["properties"]["logical_entity_type"]
    assert {"type": "string", "pattern": r"^[a-z][a-z0-9_]{0,49}$"} in dimensional["properties"][
        "dimensional_fact_type"
    ]["anyOf"]
    for name, code_field in (
        ("logical_entity_type", "logical_entity_type_code"),
        ("dimensional_fact_type", "dimensional_fact_type_code"),
    ):
        definition = DATASETS_BY_NAME[name]
        assert definition.change_set_eligible is False
        assert definition.canonical_key == (code_field,)
        assert set(definition.row_model.model_fields) == {
            code_field,
            f"{name}_description",
            f"{name}_is_active",
        }


def test_snapshot_exposes_the_read_only_type_lists() -> None:
    records = project_snapshot_records(snapshot_from_graph(complete_project_graph()))

    assert [record.logical_entity_type_code for record in records["logical_entity_type"]] == [
        "association",
        "core",
        "event",
        "history",
        "reference",
        "snapshot",
        "transaction",
    ]
    assert [record.dimensional_fact_type_code for record in records["dimensional_fact_type"]] == [
        "accumulating_snapshot",
        "factless",
        "periodic_snapshot",
        "transaction",
    ]
    encoded = {
        item.definition.name: item
        for item in encode_project_snapshot(snapshot_from_graph(complete_project_graph()))
    }
    assert json.loads(encoded["dimensional_fact_type"].rows_jsonl.decode().splitlines()[0]) == {
        "dimensional_fact_type_code": "accumulating_snapshot",
        "dimensional_fact_type_description": "The accumulating_snapshot fact type.",
        "dimensional_fact_type_is_active": True,
    }


@pytest.mark.parametrize(
    "dataset,removed",
    [
        ("logical_relationship", "logical_relationship_name"),
        ("logical_relationship", "logical_relationship_definition"),
        ("logical_relationship", "logical_relationship_cardinality_basis"),
        ("dimensional_relationship", "dimensional_relationship_name"),
        ("dimensional_relationship", "dimensional_relationship_kind"),
        ("dimensional_relationship", "dimensional_relationship_cardinality"),
        ("dimensional_relationship", "dimensional_relationship_is_optional"),
        ("logical_entity", "submodels"),
        ("dimensional_entity", "submodels"),
    ],
)
def test_model_records_reject_removed_fields(
    dataset: ProjectChangeSetDataset, removed: str
) -> None:
    record = complete_project_graph()[dataset][0]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DATASETS_BY_NAME[dataset].row_model.model_validate({**record, removed: "x"}, strict=False)


def test_relationships_are_keyed_by_their_foreign_key_attribute() -> None:
    for layer in ("logical", "dimensional"):
        assert DATASETS_BY_NAME[f"{layer}_relationship"].canonical_key == (
            f"from_{layer}_entity_schema_name",
            f"from_{layer}_entity_name",
            f"from_{layer}_attribute_name",
        )
    record = complete_project_graph()["logical_relationship"][0]
    for cardinality in ("many_to_one", "one_to_one"):
        assert DATASETS_BY_NAME["logical_relationship"].row_model.model_validate(
            {**record, "logical_relationship_cardinality": cardinality}
        )
    for cardinality in ("one_to_many", "many_to_many"):
        with pytest.raises(ValidationError):
            DATASETS_BY_NAME["logical_relationship"].row_model.model_validate(
                {**record, "logical_relationship_cardinality": cardinality}
            )


def test_generated_code_and_validation_public_shapes_are_minimal() -> None:
    generated = build_project_dataset_schema(DATASETS_BY_NAME["generated_code"])
    source_system = build_project_dataset_schema(DATASETS_BY_NAME["generated_code_source_system"])
    group = build_project_dataset_schema(DATASETS_BY_NAME["validation_group"])

    assert set(generated["properties"]) == {
        "modeled_entity_type",
        "modeled_entity_schema_name",
        "modeled_entity_name",
        "artifact_name",
        "artifact_type",
        "code_storage_type",
        "code_repository_url",
        "code_commit_path",
        "code_entry_point",
        "code_parameters",
        "generated_code_content",
        "generated_code_status",
        "generated_code_is_locked",
    }
    assert set(source_system["properties"]) == {
        "modeled_entity_type",
        "modeled_entity_schema_name",
        "modeled_entity_name",
        "artifact_name",
        "source_system_code",
        "generated_code_source_system_status",
        "generated_code_source_system_is_locked",
    }
    assert set(group["properties"]) == {
        "tenant_code",
        "system_code",
        "validation_group_name",
        "validation_group_description",
        "is_active",
        "is_locked",
    }


@pytest.mark.parametrize(
    "dataset,lock_field",
    [
        ("generated_code", "generated_code_is_locked"),
        ("generated_code_source_system", "generated_code_source_system_is_locked"),
        ("validation_group", "is_locked"),
        ("validation_check", "is_locked"),
    ],
)
def test_code_validation_locks_are_required_in_portable_records(
    dataset: ProjectChangeSetDataset, lock_field: str
) -> None:
    definition = DATASETS_BY_NAME[dataset]
    schema = build_project_dataset_schema(definition)
    assert lock_field in schema["required"]
    assert schema["properties"][lock_field]["type"] == "boolean"
    record = deepcopy(complete_project_graph()[dataset][0])
    del record[lock_field]
    with pytest.raises(ValidationError):
        definition.row_model.model_validate(record, strict=False)


@pytest.mark.parametrize("parameters", [None, {}, {"batch": 42}, ["--full", 2], "custom", False, 0])
def test_git_code_accepts_flexible_nullable_metadata(parameters: object) -> None:
    raw = {
        **complete_project_graph()["generated_code"][0],
        "code_storage_type": "git",
        "code_repository_url": "any repository reference",
        "code_commit_path": "branch/ref or arbitrary text \\ path\nline",
        "code_entry_point": "",
        "code_parameters": parameters,
        "generated_code_content": None,
    }
    record = GeneratedCodeRecord.model_validate(raw)
    assert record.model_dump() == raw
    assert GeneratedCodeRecord.model_validate({**raw, "code_repository_url": None})


def test_code_storage_defaults_and_content_requirements() -> None:
    raw = complete_project_graph()["generated_code"][0]
    assert GeneratedCodeRecord.model_validate(raw).code_storage_type == "table"
    for content in (None, "", "   "):
        with pytest.raises(ValidationError):
            GeneratedCodeRecord.model_validate({**raw, "generated_code_content": content})
    with pytest.raises(ValidationError):
        GeneratedCodeRecord.model_validate({**raw, "code_storage_type": "other"})
    git = {key: value for key, value in raw.items() if key != "generated_code_content"}
    assert GeneratedCodeRecord.model_validate({**git, "code_storage_type": "git"})


def test_records_reject_database_or_removed_fields() -> None:
    graph = complete_project_graph()

    assert ProfilingProfileRecord.model_validate(graph["profiling_profile"][0], strict=False)
    assert GeneratedCodeRecord.model_validate(graph["generated_code"][0], strict=False)
    assert ValidationCheckRecord.model_validate(graph["validation_check"][0], strict=False)

    for project, record, extra in (
        (ProfilingProfileRecord, graph["profiling_profile"][0], {"attribute_id": 1}),
        (GeneratedCodeRecord, graph["generated_code"][0], {"is_logged": True}),
        (
            ValidationCheckRecord,
            graph["validation_check"][0],
            {"execution_result": "passed"},
        ),
    ):
        with pytest.raises(ValidationError):
            project.model_validate({**record, **extra}, strict=False)


@pytest.mark.parametrize(
    "cardinality",
    ["one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"],
)
def test_analysis_inference_is_independent_of_measured_evidence(
    cardinality: str,
) -> None:
    record = complete_project_graph()["analysis_result"][0]
    inferred = AnalysisResultRecord.model_validate(
        {**record, "inferred_cardinality": cardinality}, strict=True
    )
    assert inferred.inferred_cardinality == cardinality
    assert inferred.validation_source_non_null_count == 9
    assert inferred.validation_source_distinct_count == 5
    assert inferred.validation_result == "supported"


def test_analysis_cardinality_defaults_unknown_and_rejects_invalid_values() -> None:
    record = complete_project_graph()["analysis_result"][0]
    record.pop("inferred_cardinality")
    assert (
        AnalysisResultRecord.model_validate(record, strict=True).inferred_cardinality == "unknown"
    )
    for invalid in (None, "one", 1):
        with pytest.raises(ValidationError):
            AnalysisResultRecord.model_validate({**record, "inferred_cardinality": invalid})


def test_snapshot_flattens_entity_mapping_code_and_validation_sections() -> None:
    graph = complete_project_graph()
    records = project_snapshot_records(snapshot_from_graph(graph))

    assert tuple(records) == EXPECTED_DATASETS
    assert len(records["mapping_object"]) == 1
    assert len(records["generated_code"]) == 1
    assert len(records["generated_code_source_system"]) == 1
    assert len(records["validation_group"]) == 1
    assert len(records["validation_check"]) == 1


def test_snapshot_encoding_sorts_rows_and_rejects_duplicate_keys() -> None:
    graph = complete_project_graph()
    graph["subject_area"].append({**graph["subject_area"][0], "subject_area_name": "Billing"})
    graph["subject_area"].reverse()
    encoded = {
        item.definition.name: item for item in encode_project_snapshot(snapshot_from_graph(graph))
    }
    rows = encoded["subject_area"].rows_jsonl.decode().splitlines()
    assert [json.loads(row)["subject_area_name"] for row in rows] == [
        "Billing",
        "Sales",
    ]

    duplicate = deepcopy(graph["subject_area"][0])
    duplicate["subject_area_name"] = f" {duplicate['subject_area_name'].upper()} "
    graph["subject_area"].append(duplicate)
    with pytest.raises(SnapshotContractError, match="duplicate canonical key"):
        encode_project_snapshot(snapshot_from_graph(graph))


def test_snapshot_archive_catalogs_all_sections_and_datasets(tmp_path: Path) -> None:
    snapshot = snapshot_from_graph(complete_project_graph()).model_copy(
        update={
            "project_tenant_code": "TENANT_A",
            "other_active_project_names": ("Legacy Project", "Other Project"),
        }
    )
    created_at = datetime(2026, 9, 1, tzinfo=UTC)
    output = tmp_path / "project-snapshot.zip"

    result = build_project_snapshot_archive(
        output,
        snapshot_id=uuid4(),
        snapshot=snapshot,
        created_time=created_at,
        available_until=created_at + timedelta(hours=1),
        max_archive_bytes=16 * 1024 * 1024,
    )

    assert result.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        catalog = json.loads(archive.read("project-snapshot/catalog.json"))
        manifest = json.loads(archive.read("project-snapshot/manifest.json"))
        names = archive.namelist()

    sections = {section["name"]: section for section in catalog["sections"]}
    assert tuple(sections) == PROJECT_SECTIONS
    assert "project_binding" not in sections
    assert [item["name"] for item in sections["code_generation"]["datasets"]] == [
        "generated_code",
        "generated_code_source_system",
    ]
    assert [item["name"] for item in sections["validation"]["datasets"]] == [
        "validation_group",
        "validation_check",
    ]
    assert catalog["project"]["tenant_code"] == "TENANT_A"
    assert catalog["project"]["other_active_project_names"] == [
        "Legacy Project",
        "Other Project",
    ]
    assert manifest["counts"]["logical_dataset_count"] == 25
    assert manifest["database_ids_included"] is False
    assert len([name for name in names if name.endswith(".schema.json")]) == 25
    assert len([name for name in names if name.endswith("rows.jsonl")]) == 25
    assert not any("qa" in name.casefold() or "project_scope" in name for name in names)


def test_removed_mapping_dependency_is_absent_and_legacy_snapshot_section_is_rejected() -> None:
    snapshot = snapshot_from_graph(complete_project_graph())
    assert "mapping_dependency" not in DATASETS_BY_NAME
    assert set(snapshot.mapping.model_dump()) == {"objects", "attributes"}
    legacy = snapshot.model_dump(mode="json")
    legacy["mapping"]["dependencies"] = []
    with pytest.raises(ValidationError) as error:
        ProjectSnapshot.model_validate(legacy)
    assert any(item["loc"] == ("mapping", "dependencies") for item in error.value.errors())
