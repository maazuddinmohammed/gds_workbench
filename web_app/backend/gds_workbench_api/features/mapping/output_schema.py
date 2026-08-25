"""Compile and validate Mapping transformation documents from frozen templates."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Literal, cast

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
    return schema


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
