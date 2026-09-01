"""Compile and validate Mapping transformation documents from frozen templates."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Literal, cast

from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS_BY_NAME,
    build_model_dataset_schema,
)
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextUnavailableError,
    reject_forbidden_provider_json,
)

from .contracts import AttributeMapperBatchOutputV1, HeaderMapperOutputV1
from .preparation_contracts import MappingOutputTemplate, MappingOutputTemplateField

type MappingOutputTargetType = Literal["mapping_object", "mapping_attribute"]

_OBJECT_DOCUMENT_BYTES = 262_144
_ATTRIBUTE_DOCUMENT_BYTES = 65_536
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 50_000

_MAPPING_ENVELOPE_GUIDANCE: dict[str, tuple[str, str]] = {
    "_CompleteMappingCandidateSchemaV1": (
        "One complete atomic Mapping candidate containing Header and Attribute output.",
        "Return the exact Header once and every immutable Attribute batch once.",
    ),
    "HeaderMapperOutputV1": (
        "Complete Object Mapping Header output for one frozen target/source pair.",
        "Return the frozen package, every expected Header binding, and matching coverage.",
    ),
    "HeaderMappingV1": (
        "One existing Object Mapping binding and its complete governed transformation.",
        "Copy the frozen Mapping Object ID and author its transformation from allowed sources.",
    ),
    "HeaderCoverageV1": (
        "Exact expected and returned Object Mapping ID coverage ledger.",
        "Copy expected IDs from context and list every returned Header ID exactly once.",
    ),
    "AttributeMapperBatchOutputV1": (
        "One immutable Attribute Mapping batch for a frozen package and target Object.",
        "Copy every batch identity field and return complete Mapping and disposition coverage.",
    ),
    "AttributeMappingItemV1": (
        "One modeled-to-target Attribute binding with its complete transformation.",
        "Use context IDs and exactly one existing Mapping ID or new local reference.",
    ),
    "TargetAttributeDispositionV1": (
        "Explicit disposition for one target Attribute in this immutable batch.",
        "Return each expected target once; explain only intentionally unmapped targets.",
    ),
    "AttributeCoverageV1": (
        "Exact expected and returned target and existing-Mapping Attribute coverage ledger.",
        "Copy expected IDs from context and derive returned IDs from this same batch output.",
    ),
}

_MAPPING_ENVELOPE_FIELD_GUIDANCE: dict[tuple[str, str], tuple[str, str]] = {
    ("_CompleteMappingCandidateSchemaV1", "schema_version"): (
        "Version discriminator for the complete Mapping candidate envelope.",
        "Use the exact literal 1.0.",
    ),
    ("_CompleteMappingCandidateSchemaV1", "header"): (
        "Complete Object Header output for this target/source pair.",
        "Return the entire Header envelope; do not return a fragment or field patch.",
    ),
    ("_CompleteMappingCandidateSchemaV1", "attribute_batches"): (
        "Complete immutable Attribute batch ledger for the validated Header package.",
        "Return every supplied batch index exactly once using its frozen identity fields.",
    ),
    ("HeaderMapperOutputV1", "schema_version"): (
        "Version discriminator for the Header Mapper output envelope.",
        "Use the exact literal 1.0.",
    ),
    ("HeaderMapperOutputV1", "package"): (
        "Complete executable Mapping package shared by all returned Header bindings.",
        "Author one internally consistent package from frozen context and return it whole.",
    ),
    ("HeaderMapperOutputV1", "headers"): (
        "Complete list of Object Mapping transformations in this Header request.",
        "Return each expected Mapping Object ID exactly once.",
    ),
    ("HeaderMapperOutputV1", "coverage"): (
        "Header ID coverage proving the response is complete.",
        "Copy expected IDs from context and make returned IDs equal the Header list.",
    ),
    ("HeaderMappingV1", "mapping_object_id"): (
        "Database ID of the existing Mapping Object being authored.",
        "Copy the exact frozen Mapping Object ID; never invent or repoint it.",
    ),
    ("HeaderMappingV1", "transformation"): (
        "Complete governed Object transformation for this Mapping Object.",
        "Use only package aliases and the exact selected output-template shape.",
    ),
    ("HeaderCoverageV1", "expected_mapping_object_ids"): (
        "Immutable Object Mapping IDs the backend requires in this response.",
        "Copy the complete unique sorted list from frozen context unchanged.",
    ),
    ("HeaderCoverageV1", "returned_mapping_object_ids"): (
        "Object Mapping IDs actually returned in headers.",
        "List every headers[].mapping_object_id exactly once in sorted order.",
    ),
    ("AttributeMapperBatchOutputV1", "schema_version"): (
        "Version discriminator for the Attribute Mapper batch envelope.",
        "Use the exact literal 1.0.",
    ),
    ("AttributeMapperBatchOutputV1", "package_ref"): (
        "Stable reference of the validated Header package used by this batch.",
        "Copy the exact frozen package reference unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "target_object_id"): (
        "Database ID of the registered target Object for this batch.",
        "Copy the exact frozen target Object ID unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "source_system_id"): (
        "Database ID of the source System represented by this batch.",
        "Copy the exact frozen source System ID unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "chunk_index"): (
        "One-based immutable position of this Attribute batch.",
        "Copy the exact supplied chunk index unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "chunk_count"): (
        "Total immutable Attribute batches for this target/source pair.",
        "Copy the exact supplied chunk count unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "package_digest"): (
        "Lowercase SHA-256 digest of the validated Header package.",
        "Copy the exact frozen package digest unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "coverage_manifest_digest"): (
        "Lowercase SHA-256 digest identifying this immutable coverage batch.",
        "Copy the exact frozen coverage manifest digest unchanged.",
    ),
    ("AttributeMapperBatchOutputV1", "attribute_mappings"): (
        "Authored Attribute bindings created or updated by this batch.",
        "Return complete records using only modeled and physical IDs supplied for this batch.",
    ),
    ("AttributeMapperBatchOutputV1", "target_attribute_dispositions"): (
        "Complete disposition ledger for every target Attribute in this batch.",
        "Return each expected target Attribute ID exactly once.",
    ),
    ("AttributeMapperBatchOutputV1", "coverage"): (
        "Target and existing-Mapping Attribute ID coverage for this batch.",
        "Copy expected lists and derive returned lists from this same output.",
    ),
    ("AttributeMappingItemV1", "mapping_object_id"): (
        "Database ID of the owning Mapping Object.",
        "Copy the exact parent Mapping Object ID from frozen context.",
    ),
    ("AttributeMappingItemV1", "mapping_attribute_id"): (
        "Existing Mapping Attribute ID, or null for a new binding.",
        "Copy the context ID for update; use null only with a new local_ref.",
    ),
    ("AttributeMappingItemV1", "local_ref"): (
        "Batch-local stable reference for a new Mapping Attribute.",
        "Populate only for create when mapping_attribute_id is null.",
    ),
    ("AttributeMappingItemV1", "modeled_entity_type"): (
        "Modeled layer owning the referenced Attribute.",
        "Copy logical_entity or dimensional_entity from frozen context.",
    ),
    ("AttributeMappingItemV1", "logical_attribute_id"): (
        "Logical Attribute ID for a Logical binding.",
        "Populate only for logical_entity; otherwise use null.",
    ),
    ("AttributeMappingItemV1", "dimensional_attribute_id"): (
        "Dimensional Attribute ID for a Dimensional binding.",
        "Populate only for dimensional_entity; otherwise use null.",
    ),
    ("AttributeMappingItemV1", "target_attribute_id"): (
        "Database ID of the registered physical target Attribute.",
        "Copy an exact expected target Attribute ID from this batch.",
    ),
    ("AttributeMappingItemV1", "disposition"): (
        "Whether this binding is created or updates an existing Mapping Attribute.",
        "Use create for local_ref and update for mapping_attribute_id in authorable output.",
    ),
    ("AttributeMappingItemV1", "transformation"): (
        "Complete governed Attribute transformation for this binding.",
        "Use the exact selected output-template shape and only allowed source references.",
    ),
    ("TargetAttributeDispositionV1", "target_attribute_id"): (
        "Database ID of one expected target Attribute.",
        "Copy the exact target Attribute ID from this batch.",
    ),
    ("TargetAttributeDispositionV1", "disposition"): (
        "Coverage outcome for this target Attribute.",
        "Use mapped, already_mapped, or intentionally_unmapped from actual batch handling.",
    ),
    ("TargetAttributeDispositionV1", "reason"): (
        "Reason an expected target Attribute is intentionally unmapped.",
        "Populate only for intentionally_unmapped; otherwise use null.",
    ),
    ("AttributeCoverageV1", "expected_target_attribute_ids"): (
        "Immutable target Attribute IDs required in this batch.",
        "Copy the complete unique sorted list from frozen context unchanged.",
    ),
    ("AttributeCoverageV1", "returned_target_attribute_ids"): (
        "Target Attribute IDs represented by the disposition ledger.",
        "List every target_attribute_dispositions[].target_attribute_id exactly once.",
    ),
    ("AttributeCoverageV1", "expected_existing_mapping_attribute_ids"): (
        "Existing Mapping Attribute IDs expected to be preserved or updated.",
        "Copy the complete unique sorted list from frozen context unchanged.",
    ),
    ("AttributeCoverageV1", "returned_existing_mapping_attribute_ids"): (
        "Existing Mapping Attribute IDs returned by authored bindings.",
        "List every non-null attribute_mappings[].mapping_attribute_id exactly once.",
    ),
}


class MappingTransformationDocumentError(ValueError):
    """A dynamic Mapping transformation is incompatible with its frozen schema."""


def compile_header_mapper_output_schema(
    *,
    template: MappingOutputTemplate | None,
) -> dict[str, JsonValue]:
    """Replace only the Object transformation leaf in the frozen header envelope."""

    return _compile_stage_schema(
        root=HeaderMapperOutputV1,
        definition_name="ObjectMappingTransformationDocumentV1",
        target_type="mapping_object",
        template=template,
    )


def compile_attribute_mapper_output_schema(
    *,
    template: MappingOutputTemplate | None,
) -> dict[str, JsonValue]:
    """Replace only the Attribute transformation leaf in the frozen batch envelope."""

    schema = _compile_stage_schema(
        root=AttributeMapperBatchOutputV1,
        definition_name="AttributeMappingTransformationDocumentV1",
        target_type="mapping_attribute",
        template=template,
    )
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        raise RuntimeError("The frozen Mapping Attribute schema is incomplete.")
    mapping_item = definitions.get("AttributeMappingItemV1")
    if not isinstance(mapping_item, dict):
        raise RuntimeError("The frozen Mapping Attribute item schema is incomplete.")
    properties = mapping_item.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("The frozen Mapping Attribute item schema is incomplete.")
    disposition = properties.get("disposition")
    if not isinstance(disposition, dict):
        raise RuntimeError("The frozen Mapping Attribute disposition schema is incomplete.")
    disposition["enum"] = ["create", "update"]
    return schema


def compile_mapping_transformation_schema(
    *,
    target_type: MappingOutputTargetType,
    template: MappingOutputTemplate | None,
) -> dict[str, JsonValue]:
    """Build the exact agent-output schema for one transformation leaf."""

    _validate_template_identity(target_type, template)
    properties: dict[str, JsonValue] = {
        "schema_version": {"const": "1.0", "type": "string"},
        "transformation_kind": {
            "enum": list(_transformation_kinds(target_type)),
            "type": "string",
        },
    }
    required = ["schema_version", "transformation_kind"]
    if template is not None:
        for field in template.fields:
            field_schema = _field_schema(field)
            properties[field.name] = field_schema
            if field.is_required:
                required.append(field.name)
    return cast(
        dict[str, JsonValue],
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": template is None,
            "properties": properties,
            "required": required,
            "type": "object",
        },
    )


def _compile_stage_schema(
    *,
    root: type[HeaderMapperOutputV1] | type[AttributeMapperBatchOutputV1],
    definition_name: str,
    target_type: MappingOutputTargetType,
    template: MappingOutputTemplate | None,
) -> dict[str, JsonValue]:
    schema = cast(
        dict[str, JsonValue],
        deepcopy(root.model_json_schema(mode="validation")),
    )
    raw_definitions = schema.get("$defs")
    if not isinstance(raw_definitions, dict) or definition_name not in raw_definitions:
        raise RuntimeError("The frozen Mapping stage schema is incomplete.")
    definitions = cast(dict[str, JsonValue], raw_definitions)
    definitions[definition_name] = compile_mapping_transformation_schema(
        target_type=target_type,
        template=template,
    )
    enrich_mapping_agent_output_schema(schema)
    return schema


def enrich_mapping_agent_output_schema(schema: dict[str, JsonValue]) -> None:
    """Attach canonical and envelope guidance without changing validation keywords."""

    raw_definitions = schema.get("$defs")
    definitions = (
        cast(dict[str, object], raw_definitions) if isinstance(raw_definitions, dict) else {}
    )
    for dataset, field in (
        ("mapping_object", "mapping_package_document"),
        ("mapping_object", "object_mapping_transformation_document"),
        ("mapping_attribute", "attribute_mapping_transformation_document"),
    ):
        canonical = build_model_dataset_schema(DATASETS_BY_NAME[dataset])
        raw_properties = canonical.get("properties")
        if not isinstance(raw_properties, dict):
            raise RuntimeError("The canonical Mapping schema is incomplete.")
        canonical_properties = cast(dict[str, object], raw_properties)
        raw_property = canonical_properties.get(field)
        if not isinstance(raw_property, dict):
            raise RuntimeError("The canonical Mapping schema is incomplete.")
        canonical_property = cast(dict[str, object], raw_property)
        governed = canonical_property.get("x-gds-governed-authoring-schema")
        if not isinstance(governed, dict):
            raise RuntimeError("The canonical Mapping authoring schema is incomplete.")
        governed_schema = cast(dict[str, object], governed)
        governed_name = governed_schema.get("title")
        target_governed = definitions.get(governed_name) if isinstance(governed_name, str) else None
        if isinstance(target_governed, dict):
            _copy_mapping_semantic_guidance(
                cast(dict[str, object], target_governed),
                governed_schema,
            )
        governed_definitions = governed_schema.get("$defs")
        if not isinstance(governed_definitions, dict):
            continue
        source_definitions = cast(dict[str, object], governed_definitions)
        for definition_name, raw_source in source_definitions.items():
            raw_target = definitions.get(definition_name)
            if isinstance(raw_source, dict) and isinstance(raw_target, dict):
                _copy_mapping_semantic_guidance(
                    cast(dict[str, object], raw_target),
                    cast(dict[str, object], raw_source),
                )

    root_name = schema.get("title")
    _fill_mapping_envelope_guidance(
        cast(dict[str, object], schema),
        root_name if isinstance(root_name, str) else "",
    )
    for definition_name, raw_definition in definitions.items():
        if isinstance(raw_definition, dict):
            _fill_mapping_envelope_guidance(
                cast(dict[str, object], raw_definition),
                definition_name,
            )


def _copy_mapping_semantic_guidance(
    target: dict[str, object],
    source: dict[str, object],
) -> None:
    for key in ("description", "x-gds-population-guidance", "examples"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            target[key] = value
        elif key == "examples" and isinstance(value, list) and value:
            target[key] = deepcopy(cast(list[object], value))
    target_properties = target.get("properties")
    source_properties = source.get("properties")
    if not isinstance(target_properties, dict) or not isinstance(source_properties, dict):
        return
    typed_target_properties = cast(dict[str, object], target_properties)
    typed_source_properties = cast(dict[str, object], source_properties)
    for field, raw_target in typed_target_properties.items():
        raw_source = typed_source_properties.get(field)
        if isinstance(raw_target, dict) and isinstance(raw_source, dict):
            _copy_mapping_semantic_guidance(
                cast(dict[str, object], raw_target),
                cast(dict[str, object], raw_source),
            )


def _fill_mapping_envelope_guidance(schema: dict[str, object], owner: str) -> None:
    schema_guidance = _MAPPING_ENVELOPE_GUIDANCE.get(owner)
    if schema_guidance is not None:
        schema.setdefault("description", schema_guidance[0])
        schema.setdefault("x-gds-population-guidance", schema_guidance[1])
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        return
    properties = cast(dict[str, object], raw_properties)
    for field, raw_property in properties.items():
        if not isinstance(raw_property, dict):
            continue
        property_schema = cast(dict[str, object], raw_property)
        guidance = _MAPPING_ENVELOPE_FIELD_GUIDANCE.get((owner, field))
        if guidance is not None:
            property_schema.setdefault("description", guidance[0])
            property_schema.setdefault("x-gds-population-guidance", guidance[1])
            continue
        description = property_schema.get("description")
        if isinstance(description, str) and description.strip():
            property_schema.setdefault(
                "x-gds-population-guidance",
                "Populate this field exactly as declared by the frozen Mapping output template.",
            )


def validate_mapping_transformation_document(
    *,
    target_type: MappingOutputTargetType,
    template: MappingOutputTemplate | None,
    document: JsonValue,
) -> dict[str, JsonValue]:
    """Validate and deterministically order one transformation document."""

    _validate_template_identity(target_type, template)
    normalized_value = _normalize_json(document)
    if not isinstance(normalized_value, dict):
        raise MappingTransformationDocumentError(
            "Mapping transformation document must have an object root."
        )
    normalized_input = cast(dict[str, JsonValue], normalized_value)
    try:
        reject_forbidden_provider_json(
            normalized_input,
            allow_identity_keys=True,
            reject_sensitive_values=True,
        )
    except AgentContextUnavailableError:
        raise MappingTransformationDocumentError(
            "Mapping transformation contains sensitive provider data."
        ) from None
    if normalized_input.get("schema_version") != "1.0":
        raise MappingTransformationDocumentError(
            "Mapping transformation schema_version must be 1.0."
        )
    transformation_kind = normalized_input.get("transformation_kind")
    if transformation_kind not in _transformation_kinds(target_type):
        raise MappingTransformationDocumentError(
            "Mapping transformation_kind is invalid for the target type."
        )

    if template is None:
        normalized = {
            "schema_version": cast(JsonValue, "1.0"),
            "transformation_kind": cast(JsonValue, transformation_kind),
        }
        normalized.update(
            (key, normalized_input[key])
            for key in sorted(normalized_input)
            if key not in normalized
        )
    else:
        allowed = {"schema_version", "transformation_kind"}
        allowed.update(field.name for field in template.fields)
        undeclared = sorted(set(normalized_input) - allowed)
        if undeclared:
            raise MappingTransformationDocumentError(
                f"Mapping transformation contains undeclared field {undeclared[0]}."
            )
        normalized = {
            "schema_version": cast(JsonValue, "1.0"),
            "transformation_kind": cast(JsonValue, transformation_kind),
        }
        for field in template.fields:
            if field.name not in normalized_input:
                if field.is_required:
                    raise MappingTransformationDocumentError(
                        f"Mapping transformation field {field.name} is required."
                    )
                continue
            value = normalized_input[field.name]
            _validate_field_value(field, value)
            normalized[field.name] = value

    limit = _OBJECT_DOCUMENT_BYTES if target_type == "mapping_object" else _ATTRIBUTE_DOCUMENT_BYTES
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(", ", ": "),
    ).encode("utf-8")
    if len(encoded) > limit:
        raise MappingTransformationDocumentError(
            "Mapping transformation exceeds its database size limit."
        )
    return normalized


def _validate_template_identity(
    target_type: MappingOutputTargetType,
    template: MappingOutputTemplate | None,
) -> None:
    if template is None:
        return
    if template.target_type != target_type:
        raise MappingTransformationDocumentError(
            "The Mapping output template has the wrong target type."
        )
    if not template.schema_digest_is_valid:
        raise MappingTransformationDocumentError(
            "The Mapping output-template schema digest does not match its fields."
        )
    if any(field.name in {"schema_version", "transformation_kind"} for field in template.fields):
        raise MappingTransformationDocumentError(
            "The Mapping output template contains a reserved field."
        )


def _transformation_kinds(
    target_type: MappingOutputTargetType,
) -> tuple[str, str]:
    return ("direct", "derived") if target_type == "mapping_object" else ("direct", "expression")


def _field_schema(field: MappingOutputTemplateField) -> dict[str, JsonValue]:
    if field.data_type == "array":
        assert field.array_item_type is not None
        schema: dict[str, JsonValue] = {
            "description": field.description,
            "items": {"type": field.array_item_type},
            "type": "array",
        }
    else:
        schema = {
            "description": field.description,
            "type": field.data_type,
        }
    if field.example is not None:
        _validate_field_value(field, field.example, label="example")
        schema["examples"] = [field.example]
    return schema


def _validate_field_value(
    field: MappingOutputTemplateField,
    value: JsonValue,
    *,
    label: str = "field",
) -> None:
    if field.data_type == "array":
        if not isinstance(value, list):
            _raise_type_error(field, label)
        assert field.array_item_type is not None
        array_value = cast(list[JsonValue], value)
        if any(not _matches_type(item, field.array_item_type) for item in array_value):
            _raise_type_error(field, label)
        return
    if not _matches_type(value, field.data_type):
        _raise_type_error(field, label)


def _raise_type_error(field: MappingOutputTemplateField, label: str) -> None:
    expected = (
        f"array of {field.array_item_type}" if field.data_type == "array" else field.data_type
    )
    raise MappingTransformationDocumentError(
        f"Mapping transformation {label} {field.name} must be {expected}."
    )


def _matches_type(value: JsonValue, data_type: str) -> bool:
    if data_type == "string":
        return isinstance(value, str)
    if data_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            return False
        return not isinstance(value, float) or math.isfinite(value)
    if data_type == "boolean":
        return isinstance(value, bool)
    if data_type == "object":
        return isinstance(value, dict)
    return False


def _normalize_json(value: object) -> JsonValue:
    node_count = 0

    def visit(item: object, *, depth: int) -> JsonValue:
        nonlocal node_count
        node_count += 1
        if node_count > _MAX_JSON_NODES:
            raise MappingTransformationDocumentError(
                "Mapping transformation exceeds its JSON node limit."
            )
        if depth > _MAX_JSON_DEPTH:
            raise MappingTransformationDocumentError(
                "Mapping transformation exceeds its JSON nesting limit."
            )
        if item is None or isinstance(item, str | bool | int):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise MappingTransformationDocumentError(
                    "Mapping transformation numbers must be finite."
                )
            return item
        if isinstance(item, list):
            items = cast(list[object], item)
            return [visit(child, depth=depth + 1) for child in items]
        if isinstance(item, dict):
            items = cast(dict[object, object], item)
            if any(not isinstance(key, str) for key in items):
                raise MappingTransformationDocumentError(
                    "Mapping transformation object keys must be strings."
                )
            return {cast(str, key): visit(child, depth=depth + 1) for key, child in items.items()}
        raise MappingTransformationDocumentError(
            "Mapping transformation contains a non-JSON value."
        )

    return visit(value, depth=0)
