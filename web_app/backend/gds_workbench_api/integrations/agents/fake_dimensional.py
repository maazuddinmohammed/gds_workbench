"""Deterministic local-fake Dimensional candidates."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.integrations.agents.fake_logical import pascal_case

LOGICAL_SOURCE_FIELDS = ("logical_entity_schema_name", "logical_entity_name")


def fake_dimensional_candidate(
    *,
    schema_name: str,
    source_entities: tuple[dict[str, JsonValue], ...],
    source_attributes: tuple[dict[str, JsonValue], ...],
) -> JsonValue:
    """One dimension per Logical Entity, named after it so areas sharing it reuse it."""
    if len(source_entities) + len(source_attributes) > 20_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    attributes_by_entity: dict[tuple[str, ...], list[dict[str, JsonValue]]] = {
        _key(source): [] for source in source_entities
    }
    if len(attributes_by_entity) != len(source_entities):
        raise InvalidRequestError("The local fake agent context is invalid.")
    for attribute in source_attributes:
        rows = attributes_by_entity.get(_key(attribute))
        if rows is None:
            raise InvalidRequestError("The local fake agent context is invalid.")
        rows.append(attribute)

    entities: list[JsonValue] = []
    attributes: list[JsonValue] = []
    for position, source_entity in enumerate(source_entities, start=1):
        entity_name = f"Dim{pascal_case(cast(str, source_entity['logical_entity_name']))}"
        entities.append(
            {
                "dimensional_entity_schema_name": schema_name,
                "dimensional_entity_name": entity_name,
                "dimensional_entity_definition": "One row per locally generated member.",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "dimensional_entity_dependency_order": position - 1,
                "dimensional_entity_is_active": True,
                "dimensional_entity_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "logical_entity",
                        "source_logical_entity": source_entity,
                        "rationale": None,
                        "is_active": True,
                        "is_locked": False,
                    }
                ],
            }
        )
        for ordinal, source_attribute in enumerate(attributes_by_entity[_key(source_entity)], 1):
            attributes.append(
                {
                    "dimensional_entity_schema_name": schema_name,
                    "dimensional_entity_name": entity_name,
                    "dimensional_attribute_name": f"Dimensional Attribute {ordinal}",
                    "dimensional_attribute_definition": "A locally generated Attribute.",
                    "dimensional_attribute_data_type": "string",
                    "dimensional_attribute_is_nullable": True,
                    "dimensional_attribute_ordinal_position": ordinal,
                    "dimensional_attribute_is_natural_key": False,
                    "dimensional_attribute_is_surrogate_key": False,
                    "dimensional_attribute_is_audit_column": False,
                    "dimensional_attribute_is_active": True,
                    "dimensional_attribute_is_locked": False,
                    "sources": [
                        {
                            "support_source_type": "logical_attribute",
                            "source_logical_attribute": source_attribute,
                            "rationale": None,
                            "is_active": True,
                            "is_locked": False,
                        }
                    ],
                }
            )
    return cast(
        JsonValue,
        {"entities": entities, "attributes": attributes, "relationships": []},
    )


def _key(record: dict[str, JsonValue]) -> tuple[str, ...]:
    return tuple(cast(str, record[name]).strip().casefold() for name in LOGICAL_SOURCE_FIELDS)
