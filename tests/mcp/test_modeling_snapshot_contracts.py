from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
    AnalysisResultRecord,
    GeneratedCodeRecord,
    ProfilingProfileRecord,
    QAAuthoringContextRecord,
    ValidationCheckRecord,
)
from gds_etl_workbench.tools.change_sets.model_validation import validate_staged_records
from gds_etl_workbench.tools.snapshots.model.archive import (
    build_model_snapshot_archive,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    AnalysisSection,
    ModelChangeSetDataset,
    ModelDataset,
    ModelSnapshot,
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


def test_qa_authoring_context_requires_digest_reference_count_parity() -> None:
    with pytest.raises(ValidationError):
        QAAuthoringContextRecord.model_validate(
            {
                "tenant_code": "northwind",
                "system_code": "erp",
                "mapping_context_digest": "a" * 64,
                "code_context_digest": "b" * 64,
                "mapping_target_count": 1,
                "current_code_target_count": 0,
                "current_code_references": (),
            }
        )


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
        "generated_code",
        "qa_authoring_context",
        "validation_group",
        "validation_check",
    }
    assert DATASETS_BY_NAME["profiling_profile"].canonical_key[-1] == "attribute_name"


def test_model_snapshot_catalog_discovers_code_generation_and_qa(
    tmp_path: Path,
) -> None:
    snapshot = ModelSnapshot.model_validate(
        {
            "model_id": 7,
            "model_name": "Orders",
            "model_revision": 4,
            "model_scope": {
                "details": {
                    "model_name": "Orders",
                    "model_description": None,
                    "silver_model_naming_instructions": None,
                    "silver_model_audit_columns_template": None,
                    "gold_model_naming_instructions": None,
                    "gold_model_technical_columns_template": None,
                    "gold_model_audit_columns_template": None,
                },
                "objects": (),
            },
            "profiling": {"profiles": ()},
            "analysis": {"relationships": ()},
            "assertion": {"documents": (), "records": ()},
            "conceptual": {"objects": (), "relationships": ()},
            "logical": {
                "submodels": (),
                "entities": (),
                "attributes": (),
                "relationships": (),
            },
            "dimensional": {
                "submodels": (),
                "entities": (),
                "attributes": (),
                "relationships": (),
            },
            "mapping": {"dependencies": (), "objects": (), "attributes": ()},
        }
    )
    created_at = datetime(2026, 8, 31, tzinfo=UTC)
    output = tmp_path / "model-snapshot.zip"
    build_model_snapshot_archive(
        output,
        snapshot_id=uuid4(),
        snapshot=snapshot,
        created_time=created_at,
        available_until=created_at + timedelta(hours=1),
        max_archive_bytes=4 * 1024 * 1024,
    )

    with zipfile.ZipFile(output) as archive:
        catalog = json.loads(archive.read("model-snapshot/catalog.json"))
        generated_schema = json.loads(
            archive.read("model-snapshot/schemas/model/generated_code.schema.json")
        )
        check_schema = json.loads(
            archive.read("model-snapshot/schemas/model/validation_check.schema.json")
        )
        qa_context_schema = json.loads(
            archive.read(
                "model-snapshot/schemas/model/qa_authoring_context.schema.json"
            )
        )

    sections = {section["name"]: section for section in catalog["sections"]}
    assert [item["name"] for item in sections["code_generation"]["datasets"]] == [
        "generated_code"
    ]
    assert [item["name"] for item in sections["qa"]["datasets"]] == [
        "qa_authoring_context",
        "validation_group",
        "validation_check",
    ]
    qa_context_catalog = sections["qa"]["datasets"][0]
    assert qa_context_catalog["change_set_eligible"] is False
    assert qa_context_schema["x-gds-change-set-eligible"] is False
    trusted_context = qa_context_schema["x-gds-trusted-context-contract"]
    assert trusted_context["copy_to_validation_group"] == {
        "join_fields": ["tenant_code", "system_code"],
        "fields": ["mapping_context_digest", "code_context_digest"],
        "copy_unchanged": True,
    }
    assert trusted_context["current_code_join"]["dataset"] == "generated_code"
    assert trusted_context["current_code_join"]["exclude_unreferenced_records"] is True
    assert trusted_context["bounds"] == {
        "maximum_system_contexts_per_snapshot": 20_000,
        "maximum_mapping_targets_per_system": 20_000,
        "maximum_current_code_references_per_system": 20_000,
        "maximum_target_system_associations_per_snapshot": 50_000,
    }
    assert sections["code_generation"]["authoring_prerequisites"] == {
        "required_applied_sections": ["mapping"],
        "optional_applied_sections": [],
        "successive_change_set_required": True,
    }
    assert sections["qa"]["authoring_prerequisites"] == {
        "required_applied_sections": ["mapping"],
        "optional_applied_sections": ["code_generation"],
        "successive_change_set_required": True,
    }
    assert (
        generated_schema["x-gds-context-digest-contract"]["source_context_digest"][
            "result_field"
        ]
        == "target_source_context_digest"
    )
    execution_shape = next(
        shape
        for shape in check_schema["x-gds-assertion-shapes"]
        if shape["operators"] == ["executes_successfully"]
    )
    comparison_shape = next(
        shape
        for shape in check_schema["x-gds-assertion-shapes"]
        if shape["operators"] == ["equal", "not_equal"]
    )
    assert execution_shape["query_a_result_cardinality"] == "ignored"
    assert comparison_shape["query_a_result_cardinality"] == (
        "exactly_one_row_one_column"
    )
    assert comparison_shape["query_b_result_cardinality"] == (
        "exactly_one_row_one_column_when_present"
    )
    assert comparison_shape["cardinality_mismatch_outcome"] == (
        "query_contract_execution_error"
    )
    assert comparison_shape["cardinality_mismatch_is_assertion_failure"] is False


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


def test_model_change_set_dataset_literal_excludes_read_only_contexts() -> None:
    assert "model_scope" not in CHANGE_SET_DATASETS_BY_NAME
    assert "qa_authoring_context" not in CHANGE_SET_DATASETS_BY_NAME
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
        expected = name not in {"model_scope", "qa_authoring_context"}
        assert (
            build_model_dataset_schema(definition)["x-gds-change-set-eligible"]
            is expected
        )


def test_every_model_snapshot_schema_embeds_complete_authoring_guidance() -> None:
    for definition in DATASETS_BY_NAME.values():
        schema = build_model_dataset_schema(definition)

        assert schema["x-gds-population-rules"]
        for property_schema in schema["properties"].values():
            assert property_schema["description"].strip()
            assert property_schema["x-gds-population-guidance"].strip()
        for definition_schema in schema["$defs"].values():
            assert definition_schema["description"].strip()
            assert definition_schema["x-gds-population-guidance"].strip()
            if definition_schema.get("type") != "object":
                continue
            for property_schema in definition_schema["properties"].values():
                assert property_schema["description"].strip()
                assert property_schema["x-gds-population-guidance"].strip()

    nested_expectations = (
        ("conceptual_object", "ObjectSupportRecord", "support_reason", "evidence"),
        ("logical_entity", "LogicalObjectSourceRecord", "source_order", "order"),
        ("dimensional_attribute", "PhysicalAttributeKey", "attribute_name", "physical"),
        ("qa_authoring_context", "QACurrentCodeReference", "generated_code_digest", "digest"),
        ("logical_entity", "SubmodelMembershipRecord", "submodel_name", "submodel"),
    )
    for dataset, definition, field, expected in nested_expectations:
        schema = build_model_dataset_schema(DATASETS_BY_NAME[dataset])
        property_schema = schema["$defs"][definition]["properties"][field]
        assert expected in (
            property_schema["description"]
            + property_schema["x-gds-population-guidance"]
        ).lower()


def test_mapping_json_fields_publish_exact_governed_authoring_schemas() -> None:
    object_schema = build_model_dataset_schema(DATASETS_BY_NAME["mapping_object"])
    attribute_schema = build_model_dataset_schema(DATASETS_BY_NAME["mapping_attribute"])

    package = object_schema["properties"]["mapping_package_document"]
    object_transformation = object_schema["properties"][
        "object_mapping_transformation_document"
    ]
    attribute_transformation = attribute_schema["properties"][
        "attribute_mapping_transformation_document"
    ]

    assert package["x-gds-authoritative-validator"] == (
        "MappingPackageDocumentV1"
    )
    assert object_transformation["x-gds-authoritative-validator"] == (
        "ObjectMappingTransformationDocumentV1"
    )
    assert attribute_transformation["x-gds-authoritative-validator"] == (
        "AttributeMappingTransformationDocumentV1"
    )

    for property_schema in (
        package,
        object_transformation,
        attribute_transformation,
    ):
        governed = property_schema["x-gds-governed-authoring-schema"]
        assert governed["additionalProperties"] is False
        assert governed["required"]
        assert governed["description"].strip()
        assert governed["x-gds-population-guidance"].strip()
        for governed_property in governed["properties"].values():
            assert governed_property["description"].strip()
            assert governed_property["x-gds-population-guidance"].strip()
        for definition_schema in governed.get("$defs", {}).values():
            assert definition_schema["description"].strip()
            assert definition_schema["x-gds-population-guidance"].strip()
            if definition_schema.get("type") != "object":
                continue
            for nested_property in definition_schema["properties"].values():
                assert nested_property["description"].strip()
                assert nested_property["x-gds-population-guidance"].strip()

    assert "package_ref" in package["x-gds-governed-authoring-schema"]["properties"]
    assert "joins" in object_transformation[
        "x-gds-governed-authoring-schema"
    ]["properties"]
    assert "source_columns" in attribute_transformation[
        "x-gds-governed-authoring-schema"
    ]["properties"]


def test_generated_code_contract_verifies_content_and_digest() -> None:
    content = (
        "CREATE OR REPLACE TEMP VIEW prepared AS SELECT 1;\nSELECT * FROM prepared;"
    )
    record = GeneratedCodeRecord.model_validate(
        {
            "tenant_code": "northwind",
            "system_code": "warehouse",
            "connection_code": "target",
            "object_schema": "silver",
            "object_name": "orders",
            "modeled_entity_type": "logical_entity",
            "artifact_type": "sql_file",
            "generated_code_content": content,
            "mapping_context_digest": "a" * 64,
            "source_context_digest": "b" * 64,
            "generated_code_digest": hashlib.sha256(content.encode()).hexdigest(),
            "generated_code_status": "active",
            "generated_code_is_locked": False,
        }
    )

    assert record.generated_code_content == content
    with pytest.raises(ValidationError, match="digest"):
        GeneratedCodeRecord.model_validate(
            {**record.model_dump(mode="python"), "generated_code_digest": "c" * 64}
        )
    control_content = "SELECT '\x00'"
    with pytest.raises(ValidationError, match="control character"):
        GeneratedCodeRecord.model_validate(
            {
                **record.model_dump(mode="python"),
                "generated_code_content": control_content,
                "generated_code_digest": hashlib.sha256(
                    control_content.encode()
                ).hexdigest(),
            }
        )

    large_content = "x" * (400 * 1024 + 1)
    large_record = GeneratedCodeRecord.model_validate(
        {
            **record.model_dump(mode="python"),
            "generated_code_content": large_content,
            "generated_code_digest": hashlib.sha256(large_content.encode()).hexdigest(),
        }
    )
    assert large_record.generated_code_content == large_content


def test_validation_check_contract_supports_query_execution_and_assertions() -> None:
    common = {
        "tenant_code": "northwind",
        "system_code": "erp",
        "validation_group_name": "Order reconciliation",
        "validation_check_description": None,
        "validation_category_code": "technical",
        "validation_severity": "blocking",
        "validation_query_sql": "SELECT count(*) FROM catalog.silver.orders",
        "is_active": True,
    }
    execution = ValidationCheckRecord.model_validate(
        {
            **common,
            "validation_check_name": "Query executes",
            "validation_comparison_query_sql": None,
            "validation_result_data_type": None,
            "validation_comparison_operator": "executes_successfully",
            "validation_comparison_value_type": "none",
            "validation_comparison_value": None,
        }
    )
    comparison = ValidationCheckRecord.model_validate(
        {
            **common,
            "validation_check_name": "Source and target counts match",
            "validation_comparison_query_sql": (
                "SELECT count(*) FROM catalog.bronze.orders"
            ),
            "validation_result_data_type": "integer",
            "validation_comparison_operator": "equal",
            "validation_comparison_value_type": "query",
            "validation_comparison_value": None,
        }
    )

    assert execution.validation_result_data_type is None
    assert comparison.validation_comparison_query_sql is not None


def test_validation_check_contract_rejects_mixed_literal_lists() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        ValidationCheckRecord.model_validate(
            {
                "tenant_code": "northwind",
                "system_code": "erp",
                "validation_group_name": "Order reconciliation",
                "validation_check_name": "Allowed states",
                "validation_check_description": None,
                "validation_category_code": "business",
                "validation_severity": "warning",
                "validation_query_sql": "SELECT max(state) FROM catalog.silver.orders",
                "validation_comparison_query_sql": None,
                "validation_result_data_type": "integer",
                "validation_comparison_operator": "in",
                "validation_comparison_value_type": "literal_list",
                "validation_comparison_value": (1, "two"),
                "is_active": True,
            }
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
