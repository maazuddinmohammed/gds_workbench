"""Deterministic local-fake Logical answers in the compact shape."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)
from gds_workbench_api.integrations.agents.fake_shared import (
    FAKE_SOURCE_FIELDS,
    original_context,
)


def fake_table_index(request: AgentExecutionRequest) -> tuple[dict[str, JsonValue], ...]:
    """Read the frozen table_index the provider receives as a Prompt input."""
    values: object = (
        getattr(request.local_tool_catalog, "prompt_values", None)
        if request.execution_mode == "tool_assisted"
        else original_context(request.context).get("prompt_inputs")
    )
    table_index = (
        cast(dict[str, object], values).get("table_index") if isinstance(values, dict) else None
    )
    if not isinstance(table_index, list) or any(
        not isinstance(entry, dict) for entry in cast(list[object], table_index)
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return tuple(cast(list[dict[str, JsonValue]], table_index))


def fake_logical_candidate(
    *,
    schema_name: str,
    table_index: tuple[dict[str, JsonValue], ...],
    source_objects: tuple[dict[str, JsonValue], ...],
    source_attributes: tuple[dict[str, JsonValue], ...],
) -> JsonValue:
    table_ids = {
        tuple(str(entry[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS): entry["table"]
        for entry in table_index
    }
    entities: list[JsonValue] = []
    attributes_by_table: dict[str, list[JsonValue]] = {}
    for position, source_object in enumerate(source_objects, start=1):
        key = tuple(
            cast(str, source_object[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
        )
        table_id = table_ids.get(key)
        if not isinstance(table_id, str):
            raise InvalidRequestError("The local fake agent context is invalid.")
        attributes: list[JsonValue] = []
        attributes_by_table[table_id] = attributes
        entities.append(
            {
                "schema": schema_name,
                "name": f"Logical Entity {position}",
                "type": "core",
                "definition": "A locally generated Logical entity candidate.",
                "grain": "One governed Logical entity record.",
                "sources": [table_id],
                "attributes": attributes,
            }
        )
    for attribute in source_attributes:
        key = tuple(cast(str, attribute[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS)
        table_id = table_ids.get(key)
        if not isinstance(table_id, str) or table_id not in attributes_by_table:
            raise InvalidRequestError("The local fake agent context is invalid.")
        attributes = attributes_by_table[table_id]
        attributes.append(
            {
                "name": f"Logical Attribute {len(attributes) + 1}",
                "type": "string",
                "nullable": True,
                "from": f"{table_id}.{attribute['attribute_name']}",
                "definition": "A locally generated Logical attribute candidate.",
            }
        )
    return cast(JsonValue, {"entities": entities, "relationships": [], "retire": []})
