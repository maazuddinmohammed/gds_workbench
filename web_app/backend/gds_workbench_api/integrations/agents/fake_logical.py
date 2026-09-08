"""Deterministic local-fake Logical candidates."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.integrations.agents.fake_shared import (
    FAKE_SOURCE_FIELDS,
)


def fake_logical_candidate(
    *,
    source_objects: tuple[dict[str, JsonValue], ...],
    source_attributes: tuple[dict[str, JsonValue], ...],
) -> JsonValue:
    object_positions = {
        tuple(cast(str, source[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS): position
        for position, source in enumerate(source_objects, start=1)
    }
    attributes_by_position: dict[int, list[dict[str, JsonValue]]] = {
        position: [] for position in object_positions.values()
    }
    for attribute in source_attributes:
        object_key = tuple(
            cast(str, attribute[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
        )
        position = object_positions.get(object_key)
        if position is None:
            raise InvalidRequestError("The local fake agent context is invalid.")
        attributes_by_position[position].append(attribute)

    entities: list[JsonValue] = []
    attributes: list[JsonValue] = []
    for position, source_object in enumerate(source_objects, start=1):
        entity_name = f"Logical Entity {position}"
        entities.append(
            {
                "logical_entity_name": entity_name,
                "logical_entity_definition": "A locally generated Logical entity candidate.",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One governed Logical entity record.",
                "logical_entity_dependency_order": position - 1,
                "logical_entity_confidence": "medium",
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "submodels": [],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": source_object,
                        "source_order": 1,
                        "rationale": "Selected Object metadata supports this candidate.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            }
        )
        for ordinal, source_attribute in enumerate(
            attributes_by_position[position],
            start=1,
        ):
            attributes.append(
                {
                    "logical_entity_name": entity_name,
                    "logical_attribute_name": f"Logical Attribute {ordinal}",
                    "logical_attribute_definition": (
                        "A locally generated Logical attribute candidate."
                    ),
                    "logical_attribute_data_type": "string",
                    "logical_attribute_is_nullable": True,
                    "logical_attribute_is_primary_key": False,
                    "logical_attribute_is_natural_key": False,
                    "logical_attribute_is_surrogate_key": False,
                    "logical_attribute_ordinal_position": ordinal,
                    "logical_attribute_is_audit_column": False,
                    "logical_attribute_status": "active",
                    "logical_attribute_is_locked": False,
                    "sources": [
                        {
                            "support_source_type": "attribute",
                            "source_attribute": source_attribute,
                            "source_order": 1,
                            "rationale": ("Selected Attribute metadata supports this candidate."),
                            "status": "active",
                            "is_locked": False,
                        }
                    ],
                }
            )
    return cast(
        JsonValue,
        {
            "submodels": [],
            "entities": entities,
            "attributes": attributes,
            "relationships": [],
        },
    )
