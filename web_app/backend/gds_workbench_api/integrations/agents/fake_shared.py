"""Shared deterministic local-fake context and tool helpers."""

from __future__ import annotations

import re
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)

TARGET_REFERENCE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


def selected_source_attributes(
    selected: dict[str, JsonValue],
    *,
    source_object: dict[str, JsonValue],
) -> list[JsonValue]:
    raw_attributes = selected.get("attributes")
    if not isinstance(raw_attributes, list) or not 1 <= len(raw_attributes) <= 10_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    expected_object = tuple(
        cast(str, source_object[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
    )
    source_attributes: list[JsonValue] = []
    identities: set[tuple[str, ...]] = set()
    for raw_attribute in raw_attributes:
        if not isinstance(raw_attribute, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        values = tuple(raw_attribute.get(name) for name in (*FAKE_SOURCE_FIELDS, "attribute_name"))
        if any(
            not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 400
            for value in values
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        identity = cast(tuple[str, ...], values)
        normalized = tuple(value.strip().casefold() for value in identity)
        if normalized[:5] != expected_object or normalized in identities:
            raise InvalidRequestError("The local fake agent context is invalid.")
        identities.add(normalized)
        source_attributes.append(
            dict(zip((*FAKE_SOURCE_FIELDS, "attribute_name"), identity, strict=True))
        )
    return source_attributes


def detailed_original_context(context: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(context, dict) or set(context) != {"original_context", "repair"}:
        raise InvalidRequestError("The local fake agent context is invalid.")
    repair = context.get("repair")
    if repair is not None and not isinstance(repair, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    original = context.get("original_context")
    if not isinstance(original, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return original


FAKE_SOURCE_FIELDS = (
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
)


def fake_source_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    source: dict[str, JsonValue] = {}
    for field in FAKE_SOURCE_FIELDS:
        item = value.get(field)
        if not isinstance(item, str) or not item.strip() or len(item.encode("utf-8")) > 400:
            raise InvalidRequestError("The local fake agent context is invalid.")
        source[field] = item
    return source


def fake_source_attribute(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    source = fake_source_object(value)
    attribute_name = value.get("attribute_name")
    if (
        not isinstance(attribute_name, str)
        or not attribute_name.strip()
        or len(attribute_name.encode("utf-8")) > 400
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    source["attribute_name"] = attribute_name
    return source


def code_generation_target_refs(context: JsonValue) -> tuple[str, ...]:
    if not isinstance(context, dict) or set(context) != {
        "original_context",
        "repair",
    }:
        raise InvalidRequestError("The local fake agent context is invalid.")
    original = context.get("original_context")
    if not isinstance(original, dict) or set(original) != {"targets"}:
        raise InvalidRequestError("The local fake agent context is invalid.")
    targets = original.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 50_000:
        raise InvalidRequestError("The local fake agent context is invalid.")

    target_refs: list[str] = []
    for target in targets:
        if not isinstance(target, dict) or set(target) != {"target_ref", "context"}:
            raise InvalidRequestError("The local fake agent context is invalid.")
        target_ref = target.get("target_ref")
        if not isinstance(target_ref, str) or TARGET_REFERENCE.fullmatch(target_ref) is None:
            raise InvalidRequestError("The local fake agent context is invalid.")
        target_refs.append(target_ref)
    if len(target_refs) != len(set(target_refs)):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return tuple(target_refs)


def conceptual_source_objects(
    context: JsonValue,
) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(context, dict) or set(context) != {
        "original_context",
        "repair",
    }:
        raise InvalidRequestError("The local fake agent context is invalid.")
    original = context.get("original_context")
    if not isinstance(original, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    selected = original.get("selected_objects")
    if not isinstance(selected, list) or not 1 <= len(selected) <= 50_000:
        raise InvalidRequestError("The local fake agent context is invalid.")

    required = (
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    )
    sources: list[dict[str, JsonValue]] = []
    identities: set[tuple[str, ...]] = set()
    for selected_item in selected:
        if not isinstance(selected_item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        source = selected_item.get("object")
        if not isinstance(source, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        values = tuple(source.get(name) for name in required)
        if any(
            not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 400
            for value in values
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        identity = cast(tuple[str, ...], values)
        normalized = tuple(value.strip().casefold() for value in identity)
        if normalized in identities:
            raise InvalidRequestError("The local fake agent context is invalid.")
        identities.add(normalized)
        sources.append(dict(zip(required, identity, strict=True)))
    return tuple(sources)


def tool_assisted_conceptual_sources(
    request: AgentExecutionRequest,
) -> tuple[tuple[dict[str, JsonValue], ...], int]:
    catalog = request.local_tool_catalog
    if catalog is None:
        raise InvalidRequestError("The local fake agent context is invalid.")
    manifest = catalog.invoke("get_agent_context_manifest", {})
    if not isinstance(request.context, dict) or set(request.context) != {
        "original_context",
        "repair",
    }:
        raise InvalidRequestError("The local fake agent context is invalid.")
    if request.context.get("original_context") != manifest:
        raise InvalidRequestError("The local fake agent context is invalid.")
    if request.context.get("repair") is not None:
        repair = request.context.get("repair")
        if not isinstance(repair, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
    if not isinstance(manifest, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    counts = manifest.get("dataset_counts")
    if not isinstance(counts, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    selected_count = counts.get("selected_object")
    if (
        isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or not 1 <= selected_count <= 50_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    dataset_definition = next(
        (
            definition
            for definition in catalog.definitions
            if definition.name == "get_agent_context_dataset"
        ),
        None,
    )
    if dataset_definition is None:
        raise InvalidRequestError("The local fake agent context is invalid.")
    properties = dataset_definition.input_schema.get("properties")
    if not isinstance(properties, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    limit_schema = properties.get("limit")
    if not isinstance(limit_schema, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    page_limit = limit_schema.get("maximum")
    if (
        isinstance(page_limit, bool)
        or not isinstance(page_limit, int)
        or not 1 <= page_limit <= 1_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    sources: list[dict[str, JsonValue]] = []
    identities: set[tuple[str, ...]] = set()
    offset = 0
    page_calls = 0
    while offset < selected_count:
        limit = min(page_limit, selected_count - offset)
        page = catalog.invoke(
            "get_agent_context_dataset",
            {"dataset": "selected_object", "offset": offset, "limit": limit},
        )
        page_calls += 1
        if page_calls > selected_count or not isinstance(page, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        items = page.get("items")
        next_offset = page.get("next_offset")
        if (
            page.get("dataset") != "selected_object"
            or page.get("total_count") != selected_count
            or page.get("offset") != offset
            or not isinstance(items, list)
            or len(items) != limit
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for item in items:
            if not isinstance(item, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source = _conceptual_source_from_tool_item(item)
            identity = tuple(
                cast(str, source[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
            )
            if identity in identities:
                raise InvalidRequestError("The local fake agent context is invalid.")
            identities.add(identity)
            sources.append(source)
        expected_next = offset + limit
        if expected_next < selected_count:
            if next_offset != expected_next:
                raise InvalidRequestError("The local fake agent context is invalid.")
            offset = expected_next
        else:
            if next_offset is not None:
                raise InvalidRequestError("The local fake agent context is invalid.")
            offset = selected_count
    if len(sources) != selected_count:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return tuple(sources), page_calls + 1


def tool_assisted_logical_sources(
    request: AgentExecutionRequest,
) -> tuple[
    tuple[dict[str, JsonValue], ...],
    tuple[dict[str, JsonValue], ...],
    int,
]:
    source_objects, tool_call_count = tool_assisted_conceptual_sources(request)
    catalog = request.local_tool_catalog
    context = request.context
    if catalog is None or not isinstance(context, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    manifest = context.get("original_context")
    if not isinstance(manifest, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    counts = manifest.get("dataset_counts")
    if not isinstance(counts, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    selected_count = counts.get("selected_attribute")
    if (
        isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or not 0 <= selected_count <= 50_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    dataset_definition = next(
        (
            definition
            for definition in catalog.definitions
            if definition.name == "get_agent_context_dataset"
        ),
        None,
    )
    properties = (
        dataset_definition.input_schema.get("properties")
        if dataset_definition is not None
        else None
    )
    limit_schema = properties.get("limit") if isinstance(properties, dict) else None
    page_limit = limit_schema.get("maximum") if isinstance(limit_schema, dict) else None
    if (
        isinstance(page_limit, bool)
        or not isinstance(page_limit, int)
        or not 1 <= page_limit <= 1_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    source_attributes: list[dict[str, JsonValue]] = []
    identities: set[tuple[str, ...]] = set()
    offset = 0
    page_calls = 0
    while offset < selected_count:
        limit = min(page_limit, selected_count - offset)
        page = catalog.invoke(
            "get_agent_context_dataset",
            {"dataset": "selected_attribute", "offset": offset, "limit": limit},
        )
        page_calls += 1
        if page_calls > max(selected_count, 1) or not isinstance(page, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        items = page.get("items")
        next_offset = page.get("next_offset")
        if (
            page.get("dataset") != "selected_attribute"
            or page.get("total_count") != selected_count
            or page.get("offset") != offset
            or not isinstance(items, list)
            or len(items) != limit
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for item in items:
            if not isinstance(item, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source = _conceptual_source_from_tool_item(item)
            attribute_name = item.get("attribute_name")
            if (
                not isinstance(attribute_name, str)
                or not attribute_name.strip()
                or len(attribute_name.encode("utf-8")) > 400
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source["attribute_name"] = attribute_name
            identity = tuple(
                cast(str, source[name]).strip().casefold()
                for name in (*FAKE_SOURCE_FIELDS, "attribute_name")
            )
            if identity in identities:
                raise InvalidRequestError("The local fake agent context is invalid.")
            identities.add(identity)
            source_attributes.append(source)
        expected_next = offset + limit
        if expected_next < selected_count:
            if next_offset != expected_next:
                raise InvalidRequestError("The local fake agent context is invalid.")
            offset = expected_next
        else:
            if next_offset is not None:
                raise InvalidRequestError("The local fake agent context is invalid.")
            offset = selected_count
    return source_objects, tuple(source_attributes), tool_call_count + page_calls


def _conceptual_source_from_tool_item(
    item: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    required = (
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    )
    source: dict[str, JsonValue] = {}
    for name in required:
        value = item.get(name)
        if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 400:
            raise InvalidRequestError("The local fake agent context is invalid.")
        source[name] = value
    return source


def analysis_selected_attributes(
    context: JsonValue,
) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(context, dict) or set(context) != {
        "original_context",
        "repair",
    }:
        raise InvalidRequestError("The local fake agent context is invalid.")
    original = context.get("original_context")
    if not isinstance(original, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    selected = original.get("selected_objects")
    if not isinstance(selected, list) or not 1 <= len(selected) <= 50_000:
        raise InvalidRequestError("The local fake agent context is invalid.")

    required = (
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "attribute_name",
    )
    attributes: list[dict[str, JsonValue]] = []
    identities: set[tuple[str, ...]] = set()
    for selected_item in selected:
        if not isinstance(selected_item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        raw_attributes = selected_item.get("attributes")
        if not isinstance(raw_attributes, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for raw_attribute in raw_attributes:
            if not isinstance(raw_attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            values = tuple(raw_attribute.get(name) for name in required)
            if any(
                not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 400
                for value in values
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            identity = cast(tuple[str, ...], values)
            normalized = tuple(value.strip().casefold() for value in identity)
            if normalized in identities:
                raise InvalidRequestError("The local fake agent context is invalid.")
            identities.add(normalized)
            attributes.append(dict(zip(required, identity, strict=True)))
            if len(attributes) > 50_000:
                raise InvalidRequestError("The local fake agent context is invalid.")
    return tuple(attributes)
