"""Mapping prompt schemas derived from preparation DTOs and their public projection."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import Annotated, Any, cast

from gds_etl_workbench.application.mapping_context import (
    OPAQUE_CONTEXT_DOCUMENT_FIELDS,
    is_internal_context_field,
)
from pydantic import Field, TypeAdapter

from gds_workbench_api.features.mapping.preparation_contracts import (
    ExistingMappingHeader,
    MappingAuthoringPolicy,
    MappingModeledEntity,
    MappingOperation,
    MappingOutputTemplate,
    MappingReadiness,
    MappingRoute,
    MappingSource,
    MappingSourceSystem,
)


def _project_schema(value: Any) -> Any:
    """Remove metadata properties, retaining opaque document schemas intact."""
    if isinstance(value, list):
        return [_project_schema(item) for item in cast(list[Any], value)]
    if not isinstance(value, dict):
        return deepcopy(value)
    node = cast(dict[str, Any], value)
    projected: dict[str, Any] = {}
    for name, item in node.items():
        if name == "properties":
            projected[name] = {
                field: deepcopy(schema)
                if field in OPAQUE_CONTEXT_DOCUMENT_FIELDS
                else _project_schema(schema)
                for field, schema in cast(dict[str, Any], item).items()
                if not is_internal_context_field(field)
            }
        elif name == "required" and "properties" in node:
            projected[name] = [
                field for field in cast(list[str], item) if not is_internal_context_field(field)
            ]
        else:
            projected[name] = _project_schema(item)
    return projected


@cache
def mapping_input_schemas() -> dict[str, dict[str, Any]]:
    """Derive only the DTO-backed Mapping inputs; evidence notes remain explicit."""
    adapters: dict[str, TypeAdapter[Any]] = {
        "mapping_route": TypeAdapter(MappingRoute),
        "operation": TypeAdapter(MappingOperation),
        "target_metadata": TypeAdapter(MappingModeledEntity),
        "source_evidence": TypeAdapter(Annotated[list[MappingSource], Field(max_length=128)]),
        "existing_mapping": TypeAdapter(
            Annotated[list[ExistingMappingHeader], Field(min_length=1, max_length=1)]
        ),
        "authoring_policy": TypeAdapter(MappingAuthoringPolicy),
        "readiness": TypeAdapter(MappingReadiness),
        "source_system": TypeAdapter(MappingSourceSystem),
        "mapping_templates": TypeAdapter(list[MappingOutputTemplate]),
    }
    schemas: dict[str, dict[str, Any]] = {
        name: _project_schema(adapter.json_schema()) for name, adapter in adapters.items()
    }
    # project_downstream_inputs resolves these IDs through the owning Entity's
    # Attributes. Retain the published natural-name limit rather than narrowing it.
    for name, definition in (
        ("existing_mapping", "ExistingMappingAttribute"),
        ("readiness", "MappingAttributeReadiness"),
    ):
        attribute_schema = schemas[name]["$defs"][definition]
        attribute_schema["properties"]["modeled_attribute_name"] = {
            "type": "string",
            "minLength": 1,
            "maxLength": 400,
        }
        attribute_schema.setdefault("required", []).append("modeled_attribute_name")

    template = _project_schema(TypeAdapter(MappingOutputTemplate).json_schema())
    # Keep the existing nullable, inline-root schema shape and its local $defs.
    template_schema = {
        "$defs": template.pop("$defs"),
        "anyOf": [template, {"type": "null"}],
    }
    schemas["object_output_template"] = template_schema
    schemas["attribute_output_template"] = deepcopy(template_schema)
    schemas["mapping_support_records"] = {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "evidence_type": {
                    "enum": [
                        "target_attribute_lineage",
                        "target_relationship",
                        "analysis_relationship",
                        "profile",
                        "assertion",
                        "source_logical_entity",
                        "source_logical_attribute",
                        "source_logical_relationship",
                        "source_object_mapping",
                        "source_attribute_mapping",
                        "source_mapping_template",
                        "physical_object",
                        "physical_attribute",
                    ]
                },
                "record": {"type": "object"},
            },
            "required": ["evidence_type", "record"],
        },
    }
    return schemas
