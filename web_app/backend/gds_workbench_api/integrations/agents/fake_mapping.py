"""Deterministic local-fake Mapping candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.mapping_contracts import (
    validate_mapping_package_document,
)
from gds_etl_workbench.domain.mapping_profiles import (
    canonical_mapping_json_bytes,
    mapping_package_digest,
)
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)
from gds_workbench_api.integrations.agents.fake_shared import detailed_original_context


def fake_detailed_mapping_candidate(request: AgentExecutionRequest) -> JsonValue:
    original = detailed_original_context(request.context)
    if request.stage == "header_mapper":
        return cast(
            JsonValue,
            fake_mapping_header_candidate(
                context=original,
                output_schema=request.output_schema,
            ),
        )
    if request.stage == "attribute_mapper":
        mapping_context = mapping_dict(original.get("mapping_context"))
        validated_header = mapping_dict(original.get("validated_header"))
        package = mapping_dict(validated_header.get("package"))
        batch_plan = mapping_dict(original.get("batch_plan"))
        return fake_mapping_attribute_batch(
            context=mapping_context,
            package=package,
            batch_plan=batch_plan,
            output_schema=request.output_schema,
        )
    if request.stage == "target_validator":
        review_manifest = original.get("review_manifest")
        if not isinstance(review_manifest, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        review = mapping_dict(review_manifest)
        if review.get("schema_version") != "1.0":
            raise InvalidRequestError("The local fake agent context is invalid.")
        return cast(JsonValue, review)
    raise InvalidRequestError("The local fake does not support this agent execution path.")


def fake_mapping_context_from_tools(
    request: AgentExecutionRequest,
) -> tuple[dict[str, JsonValue], int]:
    catalog = request.local_tool_catalog
    if catalog is None:
        raise InvalidRequestError("The local fake agent context is invalid.")
    manifest = mapping_dict(catalog.invoke("get_mapping_context_manifest", {}))
    if manifest.get("workflow") != "mapping":
        raise InvalidRequestError("The local fake agent context is invalid.")
    counts: dict[str, tuple[int, int]] = {}
    for value in _mapping_list(manifest.get("datasets")):
        item = mapping_dict(value)
        name = _mapping_nonblank_string(item.get("name"))
        record_count = item.get("record_count")
        retrieval_item_count = item.get("retrieval_item_count")
        if (
            isinstance(record_count, bool)
            or not isinstance(record_count, int)
            or record_count < 0
            or isinstance(retrieval_item_count, bool)
            or not isinstance(retrieval_item_count, int)
            or retrieval_item_count < record_count
            or name in counts
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        counts[name] = (record_count, retrieval_item_count)

    datasets: dict[str, list[JsonValue]] = {}
    tool_call_count = 1
    for name in (
        "run",
        "source_dependency_edge",
        "target_dependency_edge",
        "target",
        "target_attribute",
        "source",
        "source_attribute",
        "header",
        "modeled_attribute",
        "existing_mapping_attribute",
        "readiness_header",
    ):
        expected_counts = counts.get(name)
        if expected_counts is None:
            raise InvalidRequestError("The local fake agent context is invalid.")
        expected_record_count, expected_item_count = expected_counts
        items: list[JsonValue] = []
        offset = 0
        while offset < expected_item_count:
            if tool_call_count >= 1_000:
                raise InvalidRequestError("The local fake agent context is invalid.")
            page = mapping_dict(
                catalog.invoke(
                    "get_mapping_context_dataset",
                    {"dataset": name, "offset": offset, "limit": 200},
                )
            )
            tool_call_count += 1
            page_items = _mapping_list(page.get("items"))
            if (
                page.get("dataset") != name
                or page.get("total_count") != expected_item_count
                or page.get("offset") != offset
                or not page_items
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            items.extend(page_items)
            next_offset = page.get("next_offset")
            expected_next = offset + len(page_items)
            if next_offset is None:
                if expected_next != expected_item_count:
                    raise InvalidRequestError("The local fake agent context is invalid.")
                offset = expected_item_count
            elif (
                isinstance(next_offset, bool)
                or not isinstance(next_offset, int)
                or next_offset != expected_next
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            else:
                offset = next_offset
        if len(items) != expected_item_count:
            raise InvalidRequestError("The local fake agent context is invalid.")
        datasets[name] = _reassemble_mapping_dataset(
            items,
            expected_record_count=expected_record_count,
        )

    run_rows = datasets["run"]
    target_rows = datasets["target"]
    if len(run_rows) != 1 or len(target_rows) != 1:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return (
        {
            "run": run_rows[0],
            "source_system_dependency_graph": {"edges": datasets["source_dependency_edge"]},
            "target_dependency_graph": {"edges": datasets["target_dependency_edge"]},
            "target": target_rows[0],
            "target_attributes": datasets["target_attribute"],
            "sources": datasets["source"],
            "source_attributes": datasets["source_attribute"],
            "headers": datasets["header"],
            "modeled_attributes": datasets["modeled_attribute"],
            "existing_mapping_attributes": datasets["existing_mapping_attribute"],
            "readiness": {
                "headers": datasets["readiness_header"],
            },
        },
        tool_call_count,
    )


def _reassemble_mapping_dataset(
    items: Sequence[JsonValue],
    *,
    expected_record_count: int,
) -> list[JsonValue]:
    records: list[JsonValue] = []
    item_index = 0
    while item_index < len(items):
        item = items[item_index]
        if not isinstance(item, dict) or "__gds_context_fragment__" not in item:
            records.append(item)
            item_index += 1
            continue

        marker = mapping_dict(cast(dict[str, JsonValue], item).get("__gds_context_fragment__"))
        record_index = marker.get("record_index")
        fragment_count = marker.get("fragment_count")
        digest = marker.get("record_sha256")
        if (
            isinstance(record_index, bool)
            or not isinstance(record_index, int)
            or record_index != len(records)
            or isinstance(fragment_count, bool)
            or not isinstance(fragment_count, int)
            or fragment_count < 1
            or not isinstance(digest, str)
            or len(digest) != 64
            or marker.get("encoding") != "canonical_json"
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")

        parts: list[str] = []
        for fragment_index in range(fragment_count):
            if item_index >= len(items):
                raise InvalidRequestError("The local fake agent context is invalid.")
            fragment = mapping_dict(items[item_index])
            fragment_marker = mapping_dict(fragment.get("__gds_context_fragment__"))
            text = fragment.get("json_text")
            if (
                fragment_marker.get("record_index") != record_index
                or fragment_marker.get("fragment_index") != fragment_index
                or fragment_marker.get("fragment_count") != fragment_count
                or fragment_marker.get("record_sha256") != digest
                or fragment_marker.get("encoding") != "canonical_json"
                or not isinstance(text, str)
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            parts.append(text)
            item_index += 1

        canonical_text = "".join(parts)
        if hashlib.sha256(canonical_text.encode("utf-8")).hexdigest() != digest:
            raise InvalidRequestError("The local fake agent context is invalid.")
        try:
            record = json.loads(canonical_text)
            if canonical_mapping_json_bytes(record) != canonical_text.encode("utf-8"):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            raise InvalidRequestError("The local fake agent context is invalid.") from None
        records.append(cast(JsonValue, record))

    if len(records) != expected_record_count:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return records


def fake_mapping_header_candidate(
    *,
    context: dict[str, JsonValue],
    output_schema: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    run = mapping_dict(context.get("run"))
    raw_headers = _mapping_list(context.get("headers"))
    raw_sources = _mapping_list(context.get("sources"))
    readiness = mapping_dict(context.get("readiness"))
    readiness_headers = {
        _mapping_positive_int(item.get("mapping_object_id")): item.get("action")
        for item in (mapping_dict(value) for value in _mapping_list(readiness.get("headers")))
    }
    package = _fake_mapping_package(
        context=context,
        run=run,
        headers=raw_headers,
        sources=raw_sources,
    )
    aliases_by_object_id: dict[int, list[str]] = {}
    for value in _mapping_list(package.get("executable_sources")):
        source = mapping_dict(value)
        object_id = _mapping_positive_int(source.get("object_id"))
        alias = _mapping_nonblank_string(source.get("alias"))
        aliases_by_object_id.setdefault(object_id, []).append(alias)

    returned_headers: list[JsonValue] = []
    all_header_ids: list[int] = []
    for value in raw_headers:
        header = mapping_dict(value)
        mapping_object_id = _mapping_positive_int(header.get("mapping_object_id"))
        all_header_ids.append(mapping_object_id)
        if readiness_headers.get(mapping_object_id) not in {"author", "extend"}:
            continue
        entity = mapping_dict(header.get("modeled_entity"))
        entity_id = _mapping_positive_int(entity.get("entity_id"))
        source_aliases: list[str] = []
        for source_value in raw_sources:
            source = mapping_dict(source_value)
            if _mapping_positive_int(source.get("modeled_entity_id")) != entity_id:
                continue
            physical = mapping_dict(source.get("object"))
            source_aliases.extend(
                aliases_by_object_id.get(
                    _mapping_positive_int(physical.get("object_id")),
                    (),
                )
            )
        if not source_aliases:
            raise InvalidRequestError("The local fake agent context is invalid.")
        returned_headers.append(
            cast(
                JsonValue,
                {
                    "mapping_object_id": mapping_object_id,
                    "transformation": _fake_mapping_transformation(
                        output_schema=output_schema,
                        definition_name="ObjectMappingTransformationDocumentV1",
                        source_aliases=tuple(sorted(set(source_aliases))),
                        source_columns=(),
                    ),
                },
            )
        )
    returned_ids = sorted(
        _mapping_positive_int(mapping_dict(item).get("mapping_object_id"))
        for item in returned_headers
    )
    if not returned_headers:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(
        dict[str, JsonValue],
        {
            "schema_version": "1.0",
            "package": package,
            "headers": returned_headers,
            "coverage": {
                "expected_mapping_object_ids": sorted(all_header_ids),
                "returned_mapping_object_ids": returned_ids,
            },
        },
    )


def _fake_mapping_package(
    *,
    context: dict[str, JsonValue],
    run: dict[str, JsonValue],
    headers: list[JsonValue],
    sources: list[JsonValue],
) -> dict[str, JsonValue]:
    raw_preserved_packages = context.get("preserved_mapping_packages")
    preserved_packages = (
        [] if raw_preserved_packages is None else _mapping_list(raw_preserved_packages)
    )
    for stored in preserved_packages:
        if isinstance(stored, dict):
            try:
                return cast(
                    dict[str, JsonValue],
                    validate_mapping_package_document(stored).model_dump(mode="json"),
                )
            except ValueError:
                raise InvalidRequestError("The local fake agent context is invalid.") from None
    for value in headers:
        stored = mapping_dict(value).get("mapping_package_document")
        if isinstance(stored, dict):
            try:
                return cast(
                    dict[str, JsonValue],
                    validate_mapping_package_document(stored).model_dump(mode="json"),
                )
            except ValueError:
                raise InvalidRequestError("The local fake agent context is invalid.") from None

    pair = mapping_dict(run.get("pair"))
    profile = mapping_dict(run.get("profile"))
    target_object_id = _mapping_positive_int(pair.get("target_object_id"))
    source_system_id = _mapping_positive_int(pair.get("source_system_id"))
    executable_sources: list[JsonValue] = []
    seen_object_ids: set[int] = set()
    for value in sources:
        source = mapping_dict(value)
        physical = mapping_dict(source.get("object"))
        object_id = _mapping_positive_int(physical.get("object_id"))
        if object_id in seen_object_ids:
            continue
        seen_object_ids.add(object_id)
        executable_sources.append(
            cast(
                JsonValue,
                {
                    "object_id": object_id,
                    "alias": f"source_{object_id}",
                    "role": "Selected source Object.",
                    "batch_rule": None,
                },
            )
        )
    if not executable_sources:
        raise InvalidRequestError("The local fake agent context is invalid.")

    source_graph = mapping_dict(context.get("source_system_dependency_graph"))
    source_dependencies = [
        {
            "predecessor_source_system_id": _mapping_positive_int(
                edge.get("predecessor_source_system_id")
            ),
            "reason": "Frozen source-System dependency.",
        }
        for edge in (mapping_dict(value) for value in _mapping_list(source_graph.get("edges")))
        if _mapping_positive_int(edge.get("successor_source_system_id")) == source_system_id
    ]
    target_graph = mapping_dict(context.get("target_dependency_graph"))
    target_dependencies = [
        {
            "predecessor_target_object_id": _mapping_positive_int(
                edge.get("predecessor_target_object_id")
            ),
            "reason": "Frozen target dependency.",
        }
        for edge in (mapping_dict(value) for value in _mapping_list(target_graph.get("edges")))
        if _mapping_positive_int(edge.get("successor_target_object_id")) == target_object_id
    ]
    aliases = sorted(
        _mapping_nonblank_string(mapping_dict(item).get("alias")) for item in executable_sources
    )
    raw_package = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "package_ref": f"mapping_{target_object_id}_{source_system_id}",
            "route": run.get("route"),
            "target_object_id": target_object_id,
            "source_system_id": source_system_id,
            "artifact_type": run.get("artifact_type"),
            "artifact_generation_instructions": (
                "Generate one idempotent artifact from this validated Mapping package."
            ),
            "pydantic_profile": {
                "key": profile.get("key"),
                "version": profile.get("version"),
                "schema_digest": profile.get("schema_digest"),
            },
            "executable_sources": executable_sources,
            "non_executable_provenance": [],
            "runtime_parameters": [],
            "source_system_dependencies": source_dependencies,
            "target_dependencies": target_dependencies,
            "steps": [
                {
                    "name": "map_target",
                    "depends_on": [],
                    "inputs": aliases,
                    "output": "mapped_rows",
                    "logic": "Project the selected source metadata into the target Object.",
                }
            ],
            "grain_and_deduplication": "Preserve the modeled target grain.",
            "load": {
                "write_mode": "append",
                "merge_keys": [],
                "partition_basis": None,
                "concurrent_system_write_mode": "serialized",
                "concurrent_write_basis": "Serialize writes for this source System.",
            },
        },
    )
    try:
        return cast(
            dict[str, JsonValue],
            validate_mapping_package_document(raw_package).model_dump(mode="json"),
        )
    except ValueError:
        raise InvalidRequestError("The local fake agent context is invalid.") from None


def fake_mapping_batch_plans(
    *,
    context: dict[str, JsonValue],
    package: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], ...]:
    target_ids = [
        _mapping_positive_int(attribute.get("attribute_id"))
        for attribute in sorted(
            (
                attribute
                for attribute in _mapping_target_attributes(context)
                if attribute.get("is_active") is True
            ),
            key=lambda item: (
                _mapping_positive_int(item.get("attribute_ordinal_position")),
                _mapping_positive_int(item.get("attribute_id")),
            ),
        )
    ]
    if not target_ids:
        raise InvalidRequestError("The local fake agent context is invalid.")
    readiness = mapping_dict(context.get("readiness"))
    actionable_existing_ids = {
        _mapping_positive_int(child.get("mapping_attribute_id"))
        for header in (mapping_dict(value) for value in _mapping_list(readiness.get("headers")))
        for child in (
            mapping_dict(value)
            for value in _mapping_list(header.get("attribute_actions"))
            if mapping_dict(value).get("action") in {"author", "extend"}
        )
    }
    existing_by_target: dict[int, list[int]] = {}
    for _header_id, child in _mapping_existing_attribute_records(context):
        mapping_attribute_id = _mapping_positive_int(child.get("mapping_attribute_id"))
        if mapping_attribute_id in actionable_existing_ids:
            existing_by_target.setdefault(
                _mapping_positive_int(child.get("target_attribute_id")),
                [],
            ).append(mapping_attribute_id)

    groups: list[tuple[list[int], list[int]]] = []
    group_targets: list[int] = []
    group_existing: list[int] = []
    for target_id in target_ids:
        target_existing = sorted(existing_by_target.get(target_id, ()))
        if len(target_existing) > 500:
            raise InvalidRequestError("The local fake agent context is invalid.")
        if group_targets and (
            len(group_targets) >= 100 or len(group_existing) + len(target_existing) > 500
        ):
            groups.append((sorted(group_targets), sorted(group_existing)))
            group_targets = []
            group_existing = []
        group_targets.append(target_id)
        group_existing.extend(target_existing)
    groups.append((sorted(group_targets), sorted(group_existing)))
    if len(groups) > 100:
        raise InvalidRequestError("The local fake agent context is invalid.")

    normalized_package = validate_mapping_package_document(package)
    digest = mapping_package_digest(normalized_package.model_dump(mode="json"))
    plans: list[dict[str, JsonValue]] = []
    for index, (expected_targets, expected_existing) in enumerate(groups, 1):
        manifest = cast(
            dict[str, JsonValue],
            {
                "schema_version": "1.0",
                "package_ref": normalized_package.package_ref,
                "target_object_id": normalized_package.target_object_id,
                "source_system_id": normalized_package.source_system_id,
                "chunk_index": index,
                "chunk_count": len(groups),
                "package_digest": digest,
                "expected_target_attribute_ids": expected_targets,
                "expected_existing_mapping_attribute_ids": expected_existing,
            },
        )
        plans.append(
            {
                **manifest,
                "coverage_manifest_digest": hashlib.sha256(
                    canonical_mapping_json_bytes(manifest)
                ).hexdigest(),
            }
        )
    return tuple(plans)


def fake_mapping_attribute_batch(
    *,
    context: dict[str, JsonValue],
    package: dict[str, JsonValue],
    batch_plan: dict[str, JsonValue],
    output_schema: Mapping[str, JsonValue],
) -> JsonValue:
    raw_headers = [mapping_dict(value) for value in _mapping_list(context.get("headers"))]
    readiness = mapping_dict(context.get("readiness"))
    header_actions: dict[int, str] = {}
    attribute_actions: dict[int, str] = {}
    for value in _mapping_list(readiness.get("headers")):
        item = mapping_dict(value)
        header_id = _mapping_positive_int(item.get("mapping_object_id"))
        action = item.get("action")
        if isinstance(action, str):
            header_actions[header_id] = action
        for child_value in _mapping_list(item.get("attribute_actions")):
            child = mapping_dict(child_value)
            child_action = child.get("action")
            if isinstance(child_action, str):
                attribute_actions[_mapping_positive_int(child.get("mapping_attribute_id"))] = (
                    child_action
                )

    expected_targets = [
        _mapping_positive_int(value)
        for value in _mapping_list(batch_plan.get("expected_target_attribute_ids"))
    ]
    expected_existing = [
        _mapping_positive_int(value)
        for value in _mapping_list(batch_plan.get("expected_existing_mapping_attribute_ids"))
    ]
    existing_records: dict[int, tuple[dict[str, JsonValue], dict[str, JsonValue]]] = {}
    preserved_targets: set[int] = set()
    existing_binding_keys: set[tuple[int, int, int]] = set()
    headers_by_id = {
        _mapping_positive_int(header.get("mapping_object_id")): header for header in raw_headers
    }
    for header_id, child in _mapping_existing_attribute_records(context):
        header = headers_by_id.get(header_id)
        if header is None:
            raise InvalidRequestError("The local fake agent context is invalid.")
        child_id = _mapping_positive_int(child.get("mapping_attribute_id"))
        target_id = _mapping_positive_int(child.get("target_attribute_id"))
        modeled_id = _mapping_positive_int(child.get("modeled_attribute_id"))
        if child_id in existing_records:
            raise InvalidRequestError("The local fake agent context is invalid.")
        existing_records[child_id] = (header, child)
        existing_binding_keys.add((header_id, modeled_id, target_id))
        if (
            attribute_actions.get(child_id) == "preserve"
            and child.get("status") == "active"
            and (
                isinstance(child.get("transformation_document"), dict)
                or child.get("has_transformation_document") is True
            )
        ):
            preserved_targets.add(target_id)

    mappings: list[JsonValue] = []
    dispositions: list[JsonValue] = []
    for target_id in expected_targets:
        target_existing = [
            child_id
            for child_id in expected_existing
            if _mapping_positive_int(existing_records[child_id][1].get("target_attribute_id"))
            == target_id
        ]
        if target_existing:
            for child_id in target_existing:
                header, child = existing_records[child_id]
                mappings.append(
                    _fake_mapping_binding(
                        context=context,
                        package=package,
                        header=header,
                        modeled_attribute_id=_mapping_positive_int(
                            child.get("modeled_attribute_id")
                        ),
                        target_attribute_id=target_id,
                        mapping_attribute_id=child_id,
                        local_ref=None,
                        disposition="update",
                        output_schema=output_schema,
                    )
                )
            disposition = "mapped"
            reason: JsonValue = None
        elif target_id in preserved_targets:
            disposition = "already_mapped"
            reason = None
        else:
            eligible = _fake_mapping_new_binding(
                context=context,
                package=package,
                headers=raw_headers,
                header_actions=header_actions,
                target_attribute_id=target_id,
                existing_binding_keys=existing_binding_keys,
                output_schema=output_schema,
            )
            if eligible is None:
                disposition = "intentionally_unmapped"
                reason = "No eligible modeled Attribute is available in frozen context."
            else:
                mappings.append(eligible)
                disposition = "mapped"
                reason = None
        dispositions.append(
            {
                "target_attribute_id": target_id,
                "disposition": disposition,
                "reason": reason,
            }
        )

    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "package_ref": batch_plan.get("package_ref"),
            "target_object_id": batch_plan.get("target_object_id"),
            "source_system_id": batch_plan.get("source_system_id"),
            "chunk_index": batch_plan.get("chunk_index"),
            "chunk_count": batch_plan.get("chunk_count"),
            "package_digest": batch_plan.get("package_digest"),
            "coverage_manifest_digest": batch_plan.get("coverage_manifest_digest"),
            "attribute_mappings": mappings,
            "target_attribute_dispositions": dispositions,
            "coverage": {
                "expected_target_attribute_ids": expected_targets,
                "returned_target_attribute_ids": expected_targets,
                "expected_existing_mapping_attribute_ids": expected_existing,
                "returned_existing_mapping_attribute_ids": expected_existing,
            },
        },
    )


def _fake_mapping_new_binding(
    *,
    context: dict[str, JsonValue],
    package: dict[str, JsonValue],
    headers: Sequence[dict[str, JsonValue]],
    header_actions: Mapping[int, str],
    target_attribute_id: int,
    existing_binding_keys: set[tuple[int, int, int]],
    output_schema: Mapping[str, JsonValue],
) -> JsonValue | None:
    run = mapping_dict(context.get("run"))
    operation = run.get("operation")
    target_attribute = next(
        (
            item
            for item in _mapping_target_attributes(context)
            if _mapping_positive_int(item.get("attribute_id")) == target_attribute_id
        ),
        None,
    )
    if target_attribute is None:
        raise InvalidRequestError("The local fake agent context is invalid.")
    target_name = _mapping_nonblank_string(target_attribute.get("attribute_name")).casefold()
    choices: list[tuple[bool, int, int, dict[str, JsonValue]]] = []
    for header in headers:
        header_id = _mapping_positive_int(header.get("mapping_object_id"))
        eligible_action = (
            header_actions.get(header_id) == "extend"
            if operation == "extend"
            else header_actions.get(header_id) in {"author", "preserve"}
        )
        if header.get("is_locked") is True or not eligible_action:
            continue
        for attribute in _mapping_modeled_attributes(context, header):
            modeled_id = _mapping_positive_int(attribute.get("attribute_id"))
            if (
                attribute.get("status") != "active"
                or (header_id, modeled_id, target_attribute_id) in existing_binding_keys
            ):
                continue
            modeled_name = _mapping_nonblank_string(attribute.get("attribute_name")).casefold()
            choices.append((modeled_name != target_name, header_id, modeled_id, header))
    if not choices:
        return None
    _name_mismatch, header_id, modeled_id, header = min(choices)
    return _fake_mapping_binding(
        context=context,
        package=package,
        header=header,
        modeled_attribute_id=modeled_id,
        target_attribute_id=target_attribute_id,
        mapping_attribute_id=None,
        local_ref=f"mapping_{header_id}_{modeled_id}_{target_attribute_id}",
        disposition="create",
        output_schema=output_schema,
    )


def _fake_mapping_binding(
    *,
    context: dict[str, JsonValue],
    package: dict[str, JsonValue],
    header: dict[str, JsonValue],
    modeled_attribute_id: int,
    target_attribute_id: int,
    mapping_attribute_id: int | None,
    local_ref: str | None,
    disposition: str,
    output_schema: Mapping[str, JsonValue],
) -> JsonValue:
    run = mapping_dict(context.get("run"))
    modeled_entity_type = _mapping_nonblank_string(run.get("modeled_entity_type"))
    header_id = _mapping_positive_int(header.get("mapping_object_id"))
    entity = mapping_dict(header.get("modeled_entity"))
    entity_id = _mapping_positive_int(entity.get("entity_id"))
    aliases_by_object_id: dict[int, list[str]] = {}
    for value in _mapping_list(package.get("executable_sources")):
        item = mapping_dict(value)
        aliases_by_object_id.setdefault(_mapping_positive_int(item.get("object_id")), []).append(
            _mapping_nonblank_string(item.get("alias"))
        )
    source_columns: list[tuple[str, int]] = []
    for source_value in _mapping_list(context.get("sources")):
        source = mapping_dict(source_value)
        if _mapping_positive_int(source.get("modeled_entity_id")) != entity_id:
            continue
        physical = mapping_dict(source.get("object"))
        aliases = aliases_by_object_id.get(
            _mapping_positive_int(physical.get("object_id")),
            (),
        )
        active_attributes = [
            attribute
            for attribute in _mapping_source_attributes(context, source)
            if attribute.get("is_active") is True
        ]
        if aliases and active_attributes:
            source_attribute = min(
                active_attributes,
                key=lambda item: _mapping_positive_int(item.get("attribute_id")),
            )
            source_columns.append(
                (
                    sorted(aliases)[0],
                    _mapping_positive_int(source_attribute.get("attribute_id")),
                )
            )
            break
    transformation = _fake_mapping_transformation(
        output_schema=output_schema,
        definition_name="AttributeMappingTransformationDocumentV1",
        source_aliases=(),
        source_columns=tuple(source_columns),
    )
    return cast(
        JsonValue,
        {
            "mapping_object_id": header_id,
            "mapping_attribute_id": mapping_attribute_id,
            "local_ref": local_ref,
            "modeled_entity_type": modeled_entity_type,
            "logical_attribute_id": (
                modeled_attribute_id if modeled_entity_type == "logical_entity" else None
            ),
            "dimensional_attribute_id": (
                modeled_attribute_id if modeled_entity_type == "dimensional_entity" else None
            ),
            "target_attribute_id": target_attribute_id,
            "disposition": disposition,
            "transformation": transformation,
        },
    )


def _mapping_target_attributes(
    context: Mapping[str, JsonValue],
) -> list[dict[str, JsonValue]]:
    flat = context.get("target_attributes")
    if flat is not None:
        return [mapping_dict(value) for value in _mapping_list(flat)]
    target = mapping_dict(context.get("target"))
    return [mapping_dict(value) for value in _mapping_list(target.get("attributes"))]


def _mapping_source_attributes(
    context: Mapping[str, JsonValue],
    source: Mapping[str, JsonValue],
) -> list[dict[str, JsonValue]]:
    flat = context.get("source_attributes")
    physical = mapping_dict(source.get("object"))
    if flat is None:
        return [mapping_dict(value) for value in _mapping_list(physical.get("attributes"))]
    source_mapping_id = _mapping_positive_int(source.get("source_mapping_id"))
    modeled_entity_id = _mapping_positive_int(source.get("modeled_entity_id"))
    object_id = _mapping_positive_int(physical.get("object_id"))
    return [
        item
        for item in (mapping_dict(value) for value in _mapping_list(flat))
        if _mapping_positive_int(item.get("source_mapping_id")) == source_mapping_id
        and _mapping_positive_int(item.get("modeled_entity_id")) == modeled_entity_id
        and _mapping_positive_int(item.get("object_id")) == object_id
    ]


def _mapping_modeled_attributes(
    context: Mapping[str, JsonValue],
    header: Mapping[str, JsonValue],
) -> list[dict[str, JsonValue]]:
    flat = context.get("modeled_attributes")
    entity = mapping_dict(header.get("modeled_entity"))
    if flat is None:
        return [mapping_dict(value) for value in _mapping_list(entity.get("attributes"))]
    header_id = _mapping_positive_int(header.get("mapping_object_id"))
    entity_id = _mapping_positive_int(entity.get("entity_id"))
    return [
        item
        for item in (mapping_dict(value) for value in _mapping_list(flat))
        if _mapping_positive_int(item.get("mapping_object_id")) == header_id
        and _mapping_positive_int(item.get("modeled_entity_id")) == entity_id
    ]


def _mapping_existing_attribute_records(
    context: Mapping[str, JsonValue],
) -> list[tuple[int, dict[str, JsonValue]]]:
    flat = context.get("existing_mapping_attributes")
    if flat is not None:
        return [
            (_mapping_positive_int(item.get("mapping_object_id")), item)
            for item in (mapping_dict(value) for value in _mapping_list(flat))
        ]
    return [
        (_mapping_positive_int(header.get("mapping_object_id")), child)
        for header in (
            mapping_dict(header_value) for header_value in _mapping_list(context.get("headers"))
        )
        for child in (
            mapping_dict(child_value)
            for child_value in _mapping_list(header.get("attribute_mappings"))
        )
    ]


def _fake_mapping_transformation(
    *,
    output_schema: Mapping[str, JsonValue],
    definition_name: str,
    source_aliases: tuple[str, ...],
    source_columns: tuple[tuple[str, int], ...],
) -> dict[str, JsonValue]:
    definitions = mapping_dict(output_schema.get("$defs"))
    schema = mapping_dict(definitions.get(definition_name))
    properties = mapping_dict(schema.get("properties"))
    kinds = _mapping_list(mapping_dict(properties.get("transformation_kind")).get("enum"))
    kind = next((item for item in kinds if isinstance(item, str)), None)
    if kind is None:
        raise InvalidRequestError("The local fake agent output contract is invalid.")
    transformation: dict[str, JsonValue] = {
        "schema_version": "1.0",
        "transformation_kind": kind,
    }
    templated = schema.get("additionalProperties") is False
    for name, value in properties.items():
        if name in transformation:
            continue
        field_schema = mapping_dict(value)
        if name == "source_aliases":
            generated: JsonValue = list(source_aliases)
        elif name == "source_columns":
            generated = [
                {
                    "source_alias": alias,
                    "source_attribute_id": attribute_id,
                }
                for alias, attribute_id in source_columns
            ]
        elif name == "step_output":
            generated = "mapped_rows"
        else:
            generated = _fake_mapping_schema_value(field_schema)
        if templated:
            transformation[name] = generated
    if not templated:
        if definition_name == "ObjectMappingTransformationDocumentV1":
            transformation.update(
                {
                    "source_aliases": list(source_aliases),
                    "joins": [],
                    "unions": [],
                    "filters": [],
                    "aggregations": [],
                    "entity_contribution_logic": ("Use the selected source Objects directly."),
                    "rationale": "Deterministic local Mapping candidate.",
                }
            )
        else:
            transformation.update(
                {
                    "source_columns": [
                        {
                            "source_alias": alias,
                            "source_attribute_id": attribute_id,
                        }
                        for alias, attribute_id in source_columns
                    ],
                    "step_output": None,
                    "expression": None,
                    "logic": "Map the selected modeled Attribute to the target Attribute.",
                }
            )
    return transformation


def _fake_mapping_schema_value(schema: Mapping[str, JsonValue]) -> JsonValue:
    data_type = schema.get("type")
    if data_type == "string":
        return "Locally generated Mapping detail."
    if data_type == "integer":
        return 1
    if data_type == "number":
        return 1.0
    if data_type == "boolean":
        return False
    if data_type == "object":
        return {}
    if data_type == "array":
        return []
    raise InvalidRequestError("The local fake agent output contract is invalid.")


def mapping_dict(value: JsonValue | None) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(dict[str, JsonValue], value)


def _mapping_list(value: JsonValue | None) -> list[JsonValue]:
    if not isinstance(value, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(list[JsonValue], value)


def _mapping_positive_int(value: JsonValue | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return value


def _mapping_nonblank_string(value: JsonValue | None) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    return value.strip()
