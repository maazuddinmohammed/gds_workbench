"""Deterministic local-fake Mapping candidate using the compact contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import AgentExecutionRequest
from gds_workbench_api.integrations.agents.fake_shared import detailed_original_context


def fake_detailed_mapping_candidate(request: AgentExecutionRequest) -> JsonValue:
    return fake_mapping_candidate(detailed_original_context(request.context))


def fake_mapping_candidate(context: dict[str, JsonValue]) -> JsonValue:
    headers = [mapping_dict(item) for item in _mapping_list(context.get("headers"))]
    readiness = mapping_dict(context.get("readiness"))
    readiness_headers = [mapping_dict(item) for item in _mapping_list(readiness.get("headers"))]
    if len(headers) != 1 or len(readiness_headers) != 1:
        raise InvalidRequestError("The local fake agent context is invalid.")
    header = headers[0]
    ready = readiness_headers[0]
    entity = mapping_dict(header.get("modeled_entity"))
    modeled_attributes = {
        _nonblank(item.get("attribute_name")): item
        for item in (mapping_dict(value) for value in _mapping_list(entity.get("attributes")))
    }
    actionable_ids = {
        _positive(item.get("modeled_attribute_id"))
        for item in (mapping_dict(value) for value in _mapping_list(ready.get("attribute_actions")))
        if item.get("action") in {"author", "extend"}
    }
    attributes: list[JsonValue] = []
    for name, attribute in sorted(modeled_attributes.items()):
        if _positive(attribute.get("attribute_id")) not in actionable_ids:
            continue
        attributes.append(
            {
                "modeled_attribute_name": name,
                "attribute_mapping_transformation_document": {
                    "kind": "derived",
                    "logic": f"Populate {name} from the frozen source context.",
                },
            }
        )
    object_mapping: JsonValue = None
    if ready.get("action") in {"author", "extend"}:
        dependency_order = header.get("object_dependency_order")
        if isinstance(dependency_order, bool) or not isinstance(dependency_order, int):
            raise InvalidRequestError("The local fake agent context is invalid.")
        object_mapping = {
            "object_dependency_order": dependency_order,
            "mapping_transformation_document": {
                "kind": "derived",
                "logic": "Build the bound target from the frozen executable sources.",
            },
        }
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "object_mapping": object_mapping,
            "attribute_mappings": attributes,
        },
    )


def fake_mapping_context_from_tools(
    request: AgentExecutionRequest,
) -> tuple[dict[str, JsonValue], int]:
    catalog = request.local_tool_catalog
    if catalog is None:
        raise InvalidRequestError("The local fake agent context is invalid.")
    manifest = mapping_dict(catalog.invoke("get_mapping_context_manifest", {}))
    counts: dict[str, tuple[int, int]] = {}
    for raw in _mapping_list(manifest.get("datasets")):
        item = mapping_dict(raw)
        name = _nonblank(item.get("name"))
        record_count = item.get("record_count")
        retrieval_count = item.get("retrieval_item_count")
        if (
            isinstance(record_count, bool)
            or not isinstance(record_count, int)
            or isinstance(retrieval_count, bool)
            or not isinstance(retrieval_count, int)
            or record_count < 0
            or retrieval_count < record_count
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        counts[name] = (record_count, retrieval_count)

    datasets: dict[str, list[JsonValue]] = {}
    calls = 1
    for name, (record_count, retrieval_count) in counts.items():
        items: list[JsonValue] = []
        offset = 0
        while offset < retrieval_count:
            page = mapping_dict(
                catalog.invoke(
                    "get_mapping_context_dataset",
                    {"dataset": name, "offset": offset, "limit": 200},
                )
            )
            calls += 1
            page_items = _mapping_list(page.get("items"))
            if not page_items:
                raise InvalidRequestError("The local fake agent context is invalid.")
            items.extend(page_items)
            offset += len(page_items)
        datasets[name] = _reassemble(items, expected_count=record_count)

    run = _one(datasets, "run")
    target = _one(datasets, "target")
    headers = datasets.get("header", [])
    modeled = datasets.get("modeled_attribute", [])
    existing = datasets.get("existing_mapping_attribute", [])
    for header in headers:
        document = mapping_dict(header)
        entity = mapping_dict(document.get("modeled_entity"))
        entity_id = _positive(entity.get("entity_id"))
        entity["attributes"] = [
            item
            for item in modeled
            if _positive(mapping_dict(item).get("modeled_entity_id")) == entity_id
        ]
        document["modeled_entity"] = entity
        document["attribute_mappings"] = [
            item
            for item in existing
            if mapping_dict(item).get("model_object_binding_id")
            == document.get("model_object_binding_id")
        ]
    return (
        {
            "run": run,
            "target": target,
            "headers": headers,
            "readiness": {"headers": datasets.get("readiness_header", [])},
        },
        calls,
    )


def mapping_dict(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    document = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in document):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(dict[str, JsonValue], value)


def _mapping_list(value: object) -> list[JsonValue]:
    if not isinstance(value, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(list[JsonValue], value)


def _one(datasets: dict[str, list[JsonValue]], name: str) -> JsonValue:
    rows = datasets.get(name)
    if rows is None or len(rows) != 1:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return rows[0]


def _positive(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return value


def _nonblank(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestError("The local fake agent context is invalid.")
    return value


def _reassemble(items: Sequence[JsonValue], *, expected_count: int) -> list[JsonValue]:
    records: list[JsonValue] = []
    index = 0
    while index < len(items):
        item = items[index]
        if not isinstance(item, dict) or "__gds_context_fragment__" not in item:
            records.append(item)
            index += 1
            continue
        marker = mapping_dict(item.get("__gds_context_fragment__"))
        count = marker.get("fragment_count")
        digest = marker.get("record_sha256")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or not isinstance(digest, str)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        parts: list[str] = []
        for fragment_index in range(count):
            fragment = mapping_dict(items[index])
            fragment_marker = mapping_dict(fragment.get("__gds_context_fragment__"))
            text = fragment.get("json_text")
            if fragment_marker.get("fragment_index") != fragment_index or not isinstance(text, str):
                raise InvalidRequestError("The local fake agent context is invalid.")
            parts.append(text)
            index += 1
        canonical = "".join(parts)
        if hashlib.sha256(canonical.encode()).hexdigest() != digest:
            raise InvalidRequestError("The local fake agent context is invalid.")
        records.append(cast(JsonValue, json.loads(canonical)))
    if len(records) != expected_count:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return records
