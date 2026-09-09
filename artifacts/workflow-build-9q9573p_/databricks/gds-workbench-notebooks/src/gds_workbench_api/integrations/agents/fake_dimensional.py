"""Deterministic local-fake Dimensional candidates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.integrations.agents.fake_shared import (
    FAKE_SOURCE_FIELDS,
)


def fake_dimensional_candidate(
    *,
    source_objects: tuple[dict[str, JsonValue], ...],
    source_attributes: tuple[dict[str, JsonValue], ...],
) -> JsonValue:
    if len(source_objects) + len(source_attributes) > 20_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    object_positions = {
        tuple(cast(str, source[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS): position
        for position, source in enumerate(source_objects, start=1)
    }
    if len(object_positions) != len(source_objects):
        raise InvalidRequestError("The local fake agent context is invalid.")
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
        entity_name = f"Dimensional Entity {position}"
        entities.append(
            _fake_dimensional_entity_record(
                entity_name=entity_name,
                entity_type="dimension",
                fact_type=None,
                grain_definition=None,
                dependency_order=position - 1,
                memberships=[],
                sources=[_fake_dimensional_object_source(source_object, source_order=1)],
            )
        )
        for ordinal, source_attribute in enumerate(
            attributes_by_position[position],
            start=1,
        ):
            attributes.append(
                _fake_dimensional_attribute_record(
                    entity_name=entity_name,
                    attribute_name=f"Dimensional Attribute {ordinal}",
                    ordinal=ordinal,
                    sources=[
                        _fake_dimensional_attribute_source(
                            source_attribute,
                            source_order=1,
                        )
                    ],
                )
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


def _fake_dimensional_object_source(
    source_object: dict[str, JsonValue],
    *,
    source_order: int,
) -> dict[str, JsonValue]:
    return {
        "support_source_type": "object",
        "source_object": source_object,
        "source_order": source_order,
        "rationale": "Selected Object metadata supports this candidate.",
        "status": "active",
        "is_locked": False,
        "source_role": "primary",
    }


def _fake_dimensional_attribute_source(
    source_attribute: dict[str, JsonValue],
    *,
    source_order: int,
) -> dict[str, JsonValue]:
    return {
        "support_source_type": "attribute",
        "source_attribute": source_attribute,
        "source_order": source_order,
        "rationale": "Selected Attribute metadata supports this candidate.",
        "status": "active",
        "is_locked": False,
    }


def _fake_dimensional_entity_record(
    *,
    entity_name: str,
    entity_type: str,
    fact_type: JsonValue,
    grain_definition: JsonValue,
    dependency_order: int,
    memberships: Sequence[JsonValue],
    sources: Sequence[JsonValue],
) -> dict[str, JsonValue]:
    return {
        "dimensional_entity_name": entity_name,
        "dimensional_entity_definition": (
            "A locally generated Dimensional business entity candidate."
        ),
        "dimensional_entity_type": entity_type,
        "dimensional_fact_type": fact_type,
        "dimensional_entity_grain_definition": grain_definition,
        "dimensional_entity_dependency_order": dependency_order,
        "dimensional_entity_confidence": "medium",
        "dimensional_entity_status": "active",
        "dimensional_entity_is_locked": False,
        "submodels": list(memberships),
        "sources": list(sources),
    }


def _fake_dimensional_attribute_record(
    *,
    entity_name: str,
    attribute_name: str,
    ordinal: int,
    sources: Sequence[JsonValue],
) -> dict[str, JsonValue]:
    return {
        "dimensional_entity_name": entity_name,
        "dimensional_attribute_name": attribute_name,
        "dimensional_attribute_definition": (
            "A locally generated Dimensional business attribute candidate."
        ),
        "dimensional_attribute_data_type": "string",
        "dimensional_attribute_is_nullable": True,
        "dimensional_attribute_ordinal_position": ordinal,
        "dimensional_attribute_role": "descriptor",
        "dimensional_attribute_key_role": "none",
        "dimensional_attribute_is_grain_component": False,
        "dimensional_attribute_additivity": None,
        "dimensional_attribute_default_aggregation": None,
        "dimensional_attribute_aggregation_basis": None,
        "dimensional_attribute_change_behavior": "overwrite",
        "dimensional_attribute_is_audit_column": False,
        "dimensional_attribute_confidence": "medium",
        "dimensional_attribute_status": "active",
        "dimensional_attribute_is_locked": False,
        "sources": list(sources),
    }
