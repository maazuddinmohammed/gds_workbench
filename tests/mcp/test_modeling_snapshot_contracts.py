from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
    AnalysisResultRecord,
    ProfilingProfileRecord,
)
from gds_etl_workbench.tools.change_sets.model_validation import validate_staged_records
from gds_etl_workbench.tools.snapshots.model.contracts import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    AnalysisSection,
    ModelChangeSetDataset,
    ModelDataset,
    build_model_dataset_schema,
)


def _profile() -> dict[str, object]:
    return {
        "tenant_code": "northwind",
        "system_code": "erp",
        "connection_code": "source",
        "object_schema": "sales",
        "object_name": "orders",
        "attribute_name": "customer_id",
        "row_count": 100,
        "non_null_count": 90,
        "null_count": 10,
        "blank_count": 0,
        "distinct_count": 45,
        "min_data_length": 1,
        "max_data_length": 10,
        "avg_data_length": Decimal("5.5"),
        "percent_populated": Decimal("90"),
        "percent_duplicates": Decimal("50"),
        "percent_null": Decimal("10"),
        "percent_blank": Decimal("0"),
        "percent_distinct": Decimal("50"),
    }


def _analysis() -> dict[str, object]:
    return {
        "from_tenant_code": "northwind",
        "from_system_code": "erp",
        "from_connection_code": "source",
        "from_object_schema": "sales",
        "from_object_name": "orders",
        "from_attribute_name": "customer_id",
        "to_tenant_code": "northwind",
        "to_system_code": "erp",
        "to_connection_code": "source",
        "to_object_schema": "sales",
        "to_object_name": "customers",
        "to_attribute_name": "customer_id",
        "relationship_kind": "foreign_key_candidate",
        "relationship_confidence": "high",
        "relationship_basis": "Names and values suggest a relationship.",
        "validation_policy_version": "1.0.0",
        "validation_result": "supported",
        "validation_source_non_null_count": 90,
        "validation_source_distinct_count": 45,
        "validation_target_non_null_count": 50,
        "validation_target_distinct_count": 50,
        "validation_source_missing_target_count": 0,
        "validation_unused_target_count": 5,
        "validation_duplicate_target_key_count": 0,
        "analysis_result_status": "active",
        "analysis_result_is_locked": False,
    }


def test_modeling_records_are_strict_id_free_contracts() -> None:
    record = ProfilingProfileRecord.model_validate(_profile())
    assert record.object_name == "orders"

    for forbidden in (
        "object_id",
        "attribute_id",
        "agent_run_id",
        "created_by",
        "updated_time",
    ):
        invalid = {**_profile(), forbidden: 1}
        with pytest.raises(ValidationError):
            ProfilingProfileRecord.model_validate(invalid)


def test_all_model_datasets_share_one_registry() -> None:
    assert set(DATASETS_BY_NAME) == {
        "model_details",
        "model_scope",
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
        "mapping_dependency",
        "mapping_object",
        "mapping_attribute",
    }
    assert DATASETS_BY_NAME["profiling_profile"].canonical_key[-1] == "attribute_name"


def test_model_details_schema_uses_canonical_naming_instructions() -> None:
    schema = build_model_dataset_schema(DATASETS_BY_NAME["model_details"])
    properties = schema["properties"]

    assert isinstance(properties, dict)
    assert "silver_model_naming_instructions" in properties
    assert "gold_model_naming_instructions" in properties
    assert "silver_model_naming_template" not in properties
    assert "gold_model_naming_template" not in properties


def test_model_dataset_literal_matches_the_registry() -> None:
    assert TypeAdapter(ModelDataset).json_schema() == {
        "enum": list(DATASETS_BY_NAME),
        "type": "string",
    }


def test_model_change_set_dataset_literal_excludes_model_scope() -> None:
    assert "model_scope" not in CHANGE_SET_DATASETS_BY_NAME
    assert TypeAdapter(ModelChangeSetDataset).json_schema() == {
        "enum": list(CHANGE_SET_DATASETS_BY_NAME),
        "type": "string",
    }


def test_model_scope_is_snapshot_only_and_exposes_eligibility() -> None:
    schema = build_model_dataset_schema(DATASETS_BY_NAME["model_scope"])

    assert schema["x-gds-change-set-eligible"] is False
    assert schema["required"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "zone_code",
        "is_bronze_source_eligible",
        "is_dimensional_source_eligible",
        "is_logical_mapping_target_eligible",
        "is_dimensional_mapping_target_eligible",
        "model_scope_is_locked",
        "is_active",
    ]

    for name, definition in DATASETS_BY_NAME.items():
        expected = name != "model_scope"
        assert (
            build_model_dataset_schema(definition)["x-gds-change-set-eligible"]
            is expected
        )


def test_described_schemas_explain_layer_specific_source_roles() -> None:
    logical = str(build_model_dataset_schema(DATASETS_BY_NAME["logical_entity"]))
    dimensional = str(
        build_model_dataset_schema(DATASETS_BY_NAME["dimensional_entity"])
    )

    assert "source_role" not in logical
    assert "source_role" in dimensional


def test_dimensional_relationship_schema_requires_typed_optionality() -> None:
    schema = build_model_dataset_schema(DATASETS_BY_NAME["dimensional_relationship"])
    required = schema["required"]
    properties = schema["properties"]

    assert isinstance(required, list)
    assert isinstance(properties, dict)
    assert "dimensional_relationship_is_optional" in required
    optionality = properties["dimensional_relationship_is_optional"]
    assert isinstance(optionality, dict)
    assert optionality["type"] == "boolean"


def test_analysis_validation_evidence_is_optional_as_one_complete_group() -> None:
    validated = AnalysisResultRecord.model_validate(_analysis())
    inference_only_document = {
        key: value
        for key, value in _analysis().items()
        if key not in ANALYSIS_VALIDATION_FIELDS
    }
    inference_only = AnalysisResultRecord.model_validate(inference_only_document)

    assert validated.validation_result == "supported"
    assert inference_only.validation_result is None
    assert AnalysisSection(relationships=(inference_only,)).relationships == (
        inference_only,
    )
    staged, issues = validate_staged_records(
        "analysis_result",
        [inference_only_document],
    )
    assert len(staged) == 1
    assert issues == ()


def test_analysis_rejects_partial_validation_evidence() -> None:
    partial = {
        key: value
        for key, value in _analysis().items()
        if key not in ANALYSIS_VALIDATION_FIELDS[1:]
    }

    with pytest.raises(ValidationError, match="all be present or all be absent"):
        AnalysisResultRecord.model_validate(partial)

    staged, issues = validate_staged_records("analysis_result", [partial])
    assert staged == ()
    assert issues[0].code == "record_schema_invalid"
