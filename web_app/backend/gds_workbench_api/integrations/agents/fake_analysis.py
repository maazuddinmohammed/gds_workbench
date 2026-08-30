"""Deterministic local fake outputs for detailed Analysis stages."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)

from .fake_shared import detailed_original_context


def fake_detailed_analysis_candidate(request: AgentExecutionRequest) -> JsonValue:
    context = detailed_original_context(request.context)
    if request.stage == "candidate_finder":
        return _candidate_finder(context)
    if request.stage == "relationship_resolver":
        return _relationship_resolver(context)
    if request.stage == "whole_slice_reconciler":
        return _whole_slice_reconciler(context)
    if request.stage == "analysis_reviewer":
        return _analysis_reviewer(context)
    raise InvalidRequestError("The local fake does not support this agent execution path.")


def _candidate_finder(context: dict[str, JsonValue]) -> JsonValue:
    slice_ref = context.get("slice_ref")
    selected = context.get("selected_objects")
    if not isinstance(slice_ref, str) or not isinstance(selected, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    attributes: list[dict[str, JsonValue]] = []
    for item in selected:
        if not isinstance(item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        raw_attributes = item.get("attributes")
        if not isinstance(raw_attributes, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for attribute in raw_attributes:
            if not isinstance(attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            attributes.append(attribute)

    candidates: list[JsonValue] = []
    seen_pairs: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for left_index, left in enumerate(attributes):
        for right in attributes[left_index + 1 :]:
            left_name = left.get("attribute_name")
            right_name = right.get("attribute_name")
            if (
                not isinstance(left_name, str)
                or not isinstance(right_name, str)
                or left_name.strip().casefold() != right_name.strip().casefold()
            ):
                continue
            left_key = _attribute_key(left)
            right_key = _attribute_key(right)
            if left_key == right_key:
                continue
            pair = (left_key, right_key) if left_key <= right_key else (right_key, left_key)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            candidates.append(
                {
                    "candidate_ref": f"{slice_ref}_candidate_{len(candidates) + 1:05d}",
                    "left_attribute": _physical_attribute(left),
                    "right_attribute": _physical_attribute(right),
                    "evidence_signals": [
                        {
                            "signal_type": "name",
                            "signal_detail": "Normalized Attribute names match.",
                        }
                    ],
                }
            )
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "coverage": {
                "slice_ref": slice_ref,
                "disposition": "candidates_found" if candidates else "no_candidate",
            },
            "candidates": candidates,
        },
    )


def _relationship_resolver(context: dict[str, JsonValue]) -> JsonValue:
    finder = context.get("candidate_finder_result")
    if not isinstance(finder, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    candidates = finder.get("candidates")
    if not isinstance(candidates, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    decisions: list[JsonValue] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = candidate.get("candidate_ref")
        left = candidate.get("left_attribute")
        right = candidate.get("right_attribute")
        if (
            not isinstance(reference, str)
            or not isinstance(left, dict)
            or not isinstance(right, dict)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        decisions.append(
            {
                "candidate_ref": reference,
                "disposition": "relationship",
                "relationship": {
                    **{f"from_{name}": value for name, value in _physical_attribute(left).items()},
                    **{f"to_{name}": value for name, value in _physical_attribute(right).items()},
                    "relationship_kind": "reference",
                    "relationship_confidence": "medium",
                    "relationship_basis": "Matching Attribute names support this candidate.",
                },
                "rationale": "The supplied evidence supports a reference candidate.",
            }
        )
    return cast(JsonValue, {"schema_version": "1.0", "decisions": decisions})


def _whole_slice_reconciler(context: dict[str, JsonValue]) -> JsonValue:
    work_items = context.get("reconciliation_work_items")
    if isinstance(work_items, list):
        return _fragmented_reconciliation(work_items)
    raw_resolutions = context.get("resolutions")
    raw_applied = context.get("applied_records")
    if not isinstance(raw_resolutions, list) or not isinstance(raw_applied, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    coverage: list[JsonValue] = []
    relationships: list[JsonValue] = []
    seen_relationships: set[tuple[str, ...]] = set()
    for resolution in raw_resolutions:
        if not isinstance(resolution, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        decisions = resolution.get("decisions")
        if not isinstance(decisions, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for decision in decisions:
            if not isinstance(decision, dict) or not isinstance(decision.get("candidate_ref"), str):
                raise InvalidRequestError("The local fake agent context is invalid.")
            relationship = decision.get("relationship")
            accepted = decision.get("disposition") == "relationship" and isinstance(
                relationship, dict
            )
            coverage.append(
                {
                    "candidate_ref": decision["candidate_ref"],
                    "disposition": "accepted" if accepted else "rejected",
                }
            )
            if accepted:
                typed_relationship = cast(dict[str, JsonValue], relationship)
                key = _relationship_key(typed_relationship)
                if key not in seen_relationships:
                    seen_relationships.add(key)
                    relationships.append(typed_relationship)

    applied_coverage: list[JsonValue] = []
    for item in raw_applied:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("applied_record_ref"), str)
            or not isinstance(item.get("relationship"), dict)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        applied_coverage.append(
            {
                "applied_record_ref": item["applied_record_ref"],
                "disposition": "preserved",
            }
        )
        relationship = cast(dict[str, JsonValue], item["relationship"])
        key = _relationship_key(relationship)
        if key not in seen_relationships:
            seen_relationships.add(key)
            relationships.append(_inference_relationship(relationship))
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": coverage,
            "applied_record_coverage": applied_coverage,
            "relationships": relationships,
        },
    )


def _fragmented_reconciliation(work_items: list[JsonValue]) -> JsonValue:
    candidate_coverage: list[JsonValue] = []
    applied_coverage: list[JsonValue] = []
    relationships: list[JsonValue] = []
    for item in work_items:
        if not isinstance(item, dict) or not isinstance(item.get("review_ref"), str):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = cast(str, item["review_ref"])
        if item.get("work_item_type") == "applied_analysis_fragment":
            applied_coverage.append({"applied_record_ref": reference, "disposition": "preserved"})
            continue
        summary = item.get("decision_summary")
        if item.get("work_item_type") != "resolution_fragment" or not isinstance(summary, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        relationship = summary.get("relationship")
        accepted = summary.get("disposition") == "relationship" and isinstance(relationship, dict)
        candidate_coverage.append(
            {
                "candidate_ref": reference,
                "disposition": "accepted" if accepted else "rejected",
            }
        )
        if accepted:
            relationships.append(
                _inference_relationship_from_summary(cast(dict[str, JsonValue], relationship))
            )
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": candidate_coverage,
            "applied_record_coverage": applied_coverage,
            "relationships": relationships,
        },
    )


def _analysis_reviewer(context: dict[str, JsonValue]) -> JsonValue:
    work_items = context.get("review_work_items")
    if isinstance(work_items, list):
        relationship_refs: list[str] = []
        applied_refs: list[str] = []
        for item in work_items:
            if not isinstance(item, dict) or not isinstance(item.get("review_ref"), str):
                raise InvalidRequestError("The local fake agent context is invalid.")
            reference = cast(str, item["review_ref"])
            if item.get("work_item_type") == "relationship_fragment":
                relationship_refs.append(reference)
            elif item.get("work_item_type") == "applied_analysis_fragment":
                applied_refs.append(reference)
            else:
                raise InvalidRequestError("The local fake agent context is invalid.")
        return cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "reviewed_relationship_refs": relationship_refs,
                "reviewed_applied_record_refs": applied_refs,
                "findings": [],
            },
        )
    relationships = context.get("relationships")
    legacy_applied_refs = context.get("required_applied_record_refs")
    if not isinstance(relationships, list) or not isinstance(legacy_applied_refs, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    refs: list[str] = []
    for item in relationships:
        if not isinstance(item, dict) or not isinstance(item.get("relationship_ref"), str):
            raise InvalidRequestError("The local fake agent context is invalid.")
        refs.append(cast(str, item["relationship_ref"]))
    if any(not isinstance(item, str) for item in legacy_applied_refs):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "reviewed_relationship_refs": refs,
            "reviewed_applied_record_refs": cast(list[str], legacy_applied_refs),
            "findings": [],
        },
    )


_ATTRIBUTE_FIELDS = (
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
    "attribute_name",
)


def _physical_attribute(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    result = {name: value.get(name) for name in _ATTRIBUTE_FIELDS}
    if any(not isinstance(item, str) or not item.strip() for item in result.values()):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return result


def _attribute_key(value: dict[str, JsonValue]) -> tuple[str, ...]:
    return tuple(
        cast(str, _physical_attribute(value)[name]).strip().casefold() for name in _ATTRIBUTE_FIELDS
    )


def _relationship_key(value: dict[str, JsonValue]) -> tuple[str, ...]:
    fields = tuple(
        cast(str, value.get(f"{endpoint}_{name}", "")).strip().casefold()
        for endpoint in ("from", "to")
        for name in _ATTRIBUTE_FIELDS
    )
    kind = value.get("relationship_kind")
    if any(not item for item in fields) or not isinstance(kind, str) or not kind.strip():
        raise InvalidRequestError("The local fake agent context is invalid.")
    return (*fields, kind.strip().casefold())


def _inference_relationship(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    result = {
        f"{endpoint}_{name}": value.get(f"{endpoint}_{name}")
        for endpoint in ("from", "to")
        for name in _ATTRIBUTE_FIELDS
    }
    result.update(
        {
            "relationship_kind": value.get("relationship_kind"),
            "relationship_confidence": value.get("relationship_confidence"),
            "relationship_basis": value.get("relationship_basis"),
        }
    )
    if any(not isinstance(item, str) or not item.strip() for item in result.values()):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return result


def _inference_relationship_from_summary(
    value: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    result = {
        f"{endpoint}_{name}": value.get(f"{endpoint}_{name}")
        for endpoint in ("from", "to")
        for name in _ATTRIBUTE_FIELDS
    }
    result.update(
        {
            "relationship_kind": value.get("relationship_kind"),
            "relationship_confidence": value.get("relationship_confidence"),
            "relationship_basis": "Byte-bounded evidence supports this relationship.",
        }
    )
    if any(not isinstance(item, str) or not item.strip() for item in result.values()):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return result


__all__ = ["fake_detailed_analysis_candidate"]
