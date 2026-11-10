"""Add soft output-template guidance to the Mapping agent schema."""

from __future__ import annotations

from copy import deepcopy
from typing import cast

from pydantic import JsonValue

from .contracts import CompleteMappingCandidateV1
from .preparation_contracts import MappingOutputTemplate, MappingPreparation


def compile_mapping_output_schema(
    *,
    preparation: MappingPreparation,
) -> dict[str, JsonValue]:
    schema = cast(
        dict[str, JsonValue],
        deepcopy(CompleteMappingCandidateV1.model_json_schema()),
    )
    description = (
        "Return only the Mapping transformation content. Identity, lifecycle status, "
        "templates and provenance are derived by the backend. Partial output is valid: "
        "return supported Object and Attribute transformations and leave unsupported "
        "documents null or omit them. Missing selected transformations are cleared; "
        "locked and unselected mappings are preserved. Return no transformations "
        "when nothing is supported. Never invent rules to fill blanks. "
        "A System contributes only when it supplies a supported business rowset or "
        "business Attribute transformation. Generated surrogate keys, audit/history "
        "population, and 'omit from load select' notes alone are not a contribution. "
        "For such a pair return outcome no_applicable_source, object_mapping null "
        "and attribute_mappings []."
    )
    guidance: dict[str, JsonValue] = {}
    object_template = _selected_template(preparation, "mapping_object")
    attribute_template = _selected_template(preparation, "mapping_attribute")
    if object_template is not None:
        guidance["mapping_transformation_document"] = _template_guidance(object_template)
    if attribute_template is not None:
        guidance["attribute_mapping_transformation_document"] = _template_guidance(
            attribute_template
        )
    if uses_standard_mapping_templates(preparation, include_v2=True):
        description += (
            " In sample_query describe the driver, joins and shared steps. Put row filters "
            "in filter_criteria and each column's value in its own transformation_logic."
        )
    schema["description"] = description
    if guidance:
        schema["x-gds-output-template-guidance"] = guidance
    return schema


def uses_standard_mapping_templates(preparation: MappingPreparation, *, include_v2: bool) -> bool:
    """Both selected templates must use the standard layer-specific field contracts."""
    layer = preparation.plan.modeled_entity_type.removesuffix("_entity")
    selections = preparation.plan.output_template_selections
    for kind, selection, expected in (
        (
            "object",
            selections.mapping_object,
            {"source_tables": "array", "filter_criteria": "string", "sample_query": "string"},
        ),
        (
            "attribute",
            selections.mapping_attribute,
            {
                "source_columns": "array",
                "default_record": "string",
                "transformation_logic": "string",
            },
        ),
    ):
        if selection is None:
            continue
        template = _selected_template(preparation, f"mapping_{kind}")
        code = f"mapping_{layer}_{kind}_default"
        codes = (code, f"{code}_v2") if include_v2 and kind == "object" else (code,)
        if (
            template is None
            or template.code not in codes
            or template.modeled_entity_type != preparation.plan.modeled_entity_type
            or {field.name: field.data_type for field in template.fields} != expected
            or not all(
                field.is_required
                and (field.data_type != "array" or field.array_item_type == "object")
                for field in template.fields
            )
        ):
            return False
    return True


def _selected_template(
    preparation: MappingPreparation,
    target_type: str,
) -> MappingOutputTemplate | None:
    selection = (
        preparation.plan.output_template_selections.mapping_object
        if target_type == "mapping_object"
        else preparation.plan.output_template_selections.mapping_attribute
    )
    if selection is None:
        return None
    return next(
        (
            item
            for item in preparation.context.output_templates.definitions
            if item.output_template_id == selection.output_template_id
            and item.target_type == target_type
            and item.modeled_entity_type in (None, preparation.plan.modeled_entity_type)
        ),
        None,
    )


def _template_guidance(template: MappingOutputTemplate) -> JsonValue:
    return {
        "template_code": template.code,
        "description": template.description,
        "fields": [
            {
                "name": field.name,
                "description": field.description,
                "data_type": field.data_type,
                "array_item_type": field.array_item_type,
                "is_required": field.is_required,
                "example": field.example,
            }
            for field in template.fields
        ],
    }
