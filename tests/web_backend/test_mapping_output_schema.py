"""Dynamic Mapping transformation schemas derived from immutable templates."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

import pytest

from gds_workbench_api.features.mapping.output_schema import (
    MappingTransformationDocumentError,
    compile_attribute_mapper_output_schema,
    compile_header_mapper_output_schema,
    compile_mapping_transformation_schema,
    enrich_mapping_agent_output_schema,
    validate_mapping_transformation_document,
)
from gds_workbench_api.features.mapping.complete_candidate import (
    _CompleteMappingCandidateSchemaV1,
)
from gds_workbench_api.features.mapping import (
    MappingOutputTemplate,
    MappingOutputTemplateField,
)


def test_selected_object_template_compiles_one_closed_ordered_schema() -> None:
    schema = compile_mapping_transformation_schema(
        target_type="mapping_object",
        template=_object_template(),
    )

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    properties = _properties(schema)
    assert list(properties) == [
        "schema_version",
        "transformation_kind",
        "source_objects",
        "filter_criteria",
        "quality_score",
    ]
    assert schema["required"] == [
        "schema_version",
        "transformation_kind",
        "source_objects",
        "quality_score",
    ]
    assert properties["schema_version"] == {"const": "1.0", "type": "string"}
    assert properties["transformation_kind"] == {
        "enum": ["direct", "derived"],
        "type": "string",
    }
    assert properties["source_objects"]["items"] == {"type": "object"}
    assert properties["source_objects"]["description"] == "Source Object details."
    assert properties["source_objects"]["examples"] == [[{"object": "customer_raw"}]]
    assert properties["quality_score"] == {
        "description": "Confidence from zero to one.",
        "examples": [0.95],
        "type": "number",
    }


def test_selected_template_validation_is_strict_and_normalizes_field_order() -> None:
    validated = validate_mapping_transformation_document(
        target_type="mapping_object",
        template=_object_template(),
        document={
            "quality_score": 0.95,
            "transformation_kind": "derived",
            "source_objects": [{"object": "customer_raw"}],
            "schema_version": "1.0",
        },
    )

    assert list(validated) == [
        "schema_version",
        "transformation_kind",
        "source_objects",
        "quality_score",
    ]

    invalid_documents: tuple[tuple[dict[str, Any], str], ...] = (
        (
            {
                "schema_version": "1.0",
                "transformation_kind": "derived",
                "quality_score": 0.9,
            },
            "source_objects",
        ),
        (
            {
                "schema_version": "1.0",
                "transformation_kind": "derived",
                "source_objects": [],
                "quality_score": 0.9,
                "unknown": True,
            },
            "undeclared",
        ),
        (
            {
                "schema_version": "1.0",
                "transformation_kind": "expression",
                "source_objects": [],
                "quality_score": 0.9,
            },
            "transformation_kind",
        ),
        (
            {
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "source_objects": ["customer_raw"],
                "quality_score": 1,
            },
            "source_objects",
        ),
        (
            {
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "source_objects": [],
                "quality_score": math.inf,
            },
            "finite",
        ),
    )
    for document, message in invalid_documents:
        with pytest.raises(MappingTransformationDocumentError, match=message):
            validate_mapping_transformation_document(
                target_type="mapping_object",
                template=_object_template(),
                document=document,
            )


def test_attribute_template_uses_its_distinct_envelope_and_types() -> None:
    template = MappingOutputTemplate(
        output_template_id=8,
        code="attribute.standard",
        name="Attribute standard",
        description=None,
        target_type="mapping_attribute",
        schema_digest="b" * 64,
        schema_digest_is_valid=True,
        is_active=True,
        fields=(
            MappingOutputTemplateField(
                name="logic",
                description="Transformation logic.",
                data_type="string",
                array_item_type=None,
                example="trim(source.customer_name)",
                is_required=True,
                order=10,
            ),
            MappingOutputTemplateField(
                name="source_ordinals",
                description="Source ordinals.",
                data_type="array",
                array_item_type="integer",
                example=[1, 2],
                is_required=False,
                order=20,
            ),
        ),
    )

    schema = compile_mapping_transformation_schema(
        target_type="mapping_attribute",
        template=template,
    )
    assert _properties(schema)["transformation_kind"]["enum"] == [
        "direct",
        "expression",
    ]
    assert (
        validate_mapping_transformation_document(
            target_type="mapping_attribute",
            template=template,
            document={
                "schema_version": "1.0",
                "transformation_kind": "expression",
                "logic": "trim(source.customer_name)",
                "source_ordinals": [1, 2],
            },
        )["logic"]
        == "trim(source.customer_name)"
    )

    with pytest.raises(MappingTransformationDocumentError, match="source_ordinals"):
        validate_mapping_transformation_document(
            target_type="mapping_attribute",
            template=template,
            document={
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "logic": "source.customer_name",
                "source_ordinals": [True],
            },
        )


def test_no_template_is_bounded_free_form_but_keeps_the_database_envelope() -> None:
    schema = compile_mapping_transformation_schema(
        target_type="mapping_attribute",
        template=None,
    )

    assert schema["additionalProperties"] is True
    assert schema["required"] == ["schema_version", "transformation_kind"]
    assert validate_mapping_transformation_document(
        target_type="mapping_attribute",
        template=None,
        document={
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "agent_defined": {"sources": ["customer_raw.customer_id"]},
        },
    )["agent_defined"] == {"sources": ["customer_raw.customer_id"]}

    with pytest.raises(MappingTransformationDocumentError, match="object root"):
        validate_mapping_transformation_document(
            target_type="mapping_attribute",
            template=None,
            document=[],
        )
    with pytest.raises(MappingTransformationDocumentError, match="size limit"):
        validate_mapping_transformation_document(
            target_type="mapping_attribute",
            template=None,
            document={
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "logic": "x" * 65_536,
            },
        )


@pytest.mark.parametrize(
    "document",
    [
        {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "client_secret": "must-never-persist",
        },
        {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "notes": "Bearer must-never-persist",
        },
        {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "notes": "raw prompt from a prior run",
        },
    ],
)
def test_free_form_transformation_rejects_sensitive_provider_data(
    document: dict[str, Any],
) -> None:
    with pytest.raises(MappingTransformationDocumentError, match="sensitive"):
        validate_mapping_transformation_document(
            target_type="mapping_object",
            template=None,
            document=cast(Any, document),
        )


def test_template_identity_must_match_the_requested_target_and_frozen_digest() -> None:
    wrong_target = _object_template().model_copy(
        update={"target_type": "mapping_attribute"}
    )
    with pytest.raises(MappingTransformationDocumentError, match="target type"):
        compile_mapping_transformation_schema(
            target_type="mapping_object",
            template=wrong_target,
        )

    drifted = _object_template().model_copy(update={"schema_digest_is_valid": False})
    with pytest.raises(MappingTransformationDocumentError, match="digest"):
        compile_mapping_transformation_schema(
            target_type="mapping_object",
            template=drifted,
        )


def test_stage_schemas_keep_the_frozen_envelope_and_replace_only_dynamic_leaves() -> (
    None
):
    header_schema = compile_header_mapper_output_schema(template=_object_template())
    attribute_schema = compile_attribute_mapper_output_schema(template=None)

    header_definitions = _definitions(header_schema)
    attribute_definitions = _definitions(attribute_schema)
    assert "MappingPackageDocumentV1" in header_definitions
    assert _without_semantic_guidance(
        header_definitions["ObjectMappingTransformationDocumentV1"]
    ) == _without_semantic_guidance(
        compile_mapping_transformation_schema(
            target_type="mapping_object",
            template=_object_template(),
        )
    )
    assert _without_semantic_guidance(
        attribute_definitions["AttributeMappingTransformationDocumentV1"]
    ) == _without_semantic_guidance(
        compile_mapping_transformation_schema(
            target_type="mapping_attribute",
            template=None,
        )
    )
    header_transformation = header_definitions["HeaderMappingV1"]["properties"][
        "transformation"
    ]
    attribute_transformation = attribute_definitions["AttributeMappingItemV1"][
        "properties"
    ]["transformation"]
    assert header_transformation["$ref"] == (
        "#/$defs/ObjectMappingTransformationDocumentV1"
    )
    assert attribute_transformation["$ref"] == (
        "#/$defs/AttributeMappingTransformationDocumentV1"
    )


def test_stage_and_complete_mapping_schemas_explain_every_declared_field() -> None:
    complete_schema = _CompleteMappingCandidateSchemaV1.model_json_schema()
    complete_constraints = _without_semantic_guidance(complete_schema)
    schemas = [
        compile_header_mapper_output_schema(template=_object_template()),
        compile_attribute_mapper_output_schema(template=None),
        complete_schema,
    ]
    enrich_mapping_agent_output_schema(schemas[-1])

    assert _without_semantic_guidance(complete_schema) == complete_constraints
    for schema in schemas:
        _assert_declared_fields_have_semantic_guidance(schema)


def _object_template() -> MappingOutputTemplate:
    return MappingOutputTemplate(
        output_template_id=7,
        code="object.standard",
        name="Object standard",
        description="Structured Object Mapping output.",
        target_type="mapping_object",
        schema_digest="a" * 64,
        schema_digest_is_valid=True,
        is_active=True,
        fields=(
            MappingOutputTemplateField(
                name="source_objects",
                description="Source Object details.",
                data_type="array",
                array_item_type="object",
                example=[{"object": "customer_raw"}],
                is_required=True,
                order=10,
            ),
            MappingOutputTemplateField(
                name="filter_criteria",
                description="Optional filter criteria.",
                data_type="string",
                array_item_type=None,
                example=None,
                is_required=False,
                order=20,
            ),
            MappingOutputTemplateField(
                name="quality_score",
                description="Confidence from zero to one.",
                data_type="number",
                array_item_type=None,
                example=0.95,
                is_required=True,
                order=40,
            ),
        ),
    )


def _properties(schema: Mapping[str, object]) -> dict[str, dict[str, object]]:
    value = schema["properties"]
    assert isinstance(value, dict)
    return cast(dict[str, dict[str, object]], value)


def _definitions(schema: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    value = schema["$defs"]
    assert isinstance(value, dict)
    return cast(dict[str, dict[str, Any]], value)


def _assert_declared_fields_have_semantic_guidance(schema: Mapping[str, Any]) -> None:
    objects = [schema, *_definitions(schema).values()]
    for object_schema in objects:
        properties = object_schema.get("properties")
        if not isinstance(properties, dict):
            continue
        typed_properties = cast(dict[str, object], properties)
        for field, raw_property in typed_properties.items():
            assert isinstance(raw_property, dict), field
            property_schema = cast(dict[str, object], raw_property)
            description = property_schema.get("description")
            population_guidance = property_schema.get("x-gds-population-guidance")
            assert isinstance(description, str) and description.strip(), field
            assert (
                isinstance(population_guidance, str) and population_guidance.strip()
            ), field


def _without_semantic_guidance(value: object) -> object:
    document = deepcopy(value)
    if isinstance(document, dict):
        typed_document = cast(dict[str, object], document)
        for key in ("description", "x-gds-population-guidance", "examples"):
            typed_document.pop(key, None)
        return {
            key: _without_semantic_guidance(item) for key, item in typed_document.items()
        }
    if isinstance(document, list):
        return [_without_semantic_guidance(item) for item in cast(list[object], document)]
    return document
