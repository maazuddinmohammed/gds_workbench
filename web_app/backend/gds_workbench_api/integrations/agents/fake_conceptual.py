"""Deterministic local-fake Conceptual candidates."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)
from gds_workbench_api.integrations.agents.fake_shared import (
    FAKE_SOURCE_FIELDS,
    TARGET_REFERENCE,
    detailed_original_context,
    fake_source_object,
)


def detailed_conceptual_candidate(request: AgentExecutionRequest) -> JsonValue:
    original = detailed_original_context(request.context)
    if request.stage == "object_contribution":
        return _fake_object_contribution(original)
    if request.stage == "entity_consolidation":
        return _fake_entity_consolidation(original)
    if request.stage == "entity_attribute_detail":
        return _fake_entity_detail(original)
    if request.stage == "relationship_cardinality_refinement":
        return _fake_relationship_refinement(original)
    if request.stage == "whole_model_reconciliation":
        return _fake_whole_model_reconciliation(original)
    raise InvalidRequestError("The local fake does not support this agent execution path.")


def _fake_object_contribution(context: dict[str, JsonValue]) -> JsonValue:
    contribution_ref = context.get("contribution_ref")
    selected = context.get("selected_object")
    if (
        not isinstance(contribution_ref, str)
        or TARGET_REFERENCE.fullmatch(contribution_ref) is None
        or not isinstance(selected, dict)
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    source = selected.get("object")
    if not isinstance(source, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    source_object = fake_source_object(source)
    local_ref = "business_concept"
    conceptual_name = "BusinessConcept"
    return cast(
        JsonValue,
        {
            "contribution_ref": contribution_ref,
            "source_object": source_object,
            "disposition": "represented",
            "rationale": "The selected Object contributes governed metadata.",
            "proposals": [
                {
                    "local_entity_ref": local_ref,
                    "object": {
                        "conceptual_object_name": conceptual_name,
                        "conceptual_object_definition": (
                            f"A locally generated {conceptual_name} concept."
                        ),
                        "conceptual_object_type": "business_concept",
                        "conceptual_object_grain": (
                            "A stable business subject represented across the selected scope."
                        ),
                        "conceptual_object_aliases": [],
                        "conceptual_object_confidence": "medium",
                        "conceptual_object_status": "active",
                        "conceptual_object_is_locked": False,
                        "supports": [_fake_object_support(source_object)],
                    },
                }
            ],
        },
    )


def _fake_entity_consolidation(context: dict[str, JsonValue]) -> JsonValue:
    contributions = context.get("contributions")
    if not isinstance(contributions, list) or not contributions:
        raise InvalidRequestError("The local fake agent context is invalid.")
    grouped: dict[str, dict[str, list[str]]] = {}
    for contribution in contributions:
        if not isinstance(contribution, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_ref = contribution.get("contribution_ref")
        proposals = contribution.get("proposals")
        if not isinstance(contribution_ref, str) or not isinstance(proposals, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            local_ref = proposal.get("local_entity_ref")
            object_record = proposal.get("object")
            if not isinstance(local_ref, str) or not isinstance(object_record, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            name = object_record.get("conceptual_object_name")
            if not isinstance(name, str):
                raise InvalidRequestError("The local fake agent context is invalid.")
            group = grouped.setdefault(
                local_ref,
                {"contribution_refs": [], "candidate_names": []},
            )
            group["contribution_refs"].append(f"{contribution_ref}.{local_ref}")
            if name not in group["candidate_names"]:
                group["candidate_names"].append(name)
    return cast(
        JsonValue,
        {
            "entities": [
                {
                    "canonical_entity_ref": ref,
                    "contribution_refs": values["contribution_refs"],
                    "candidate_names": values["candidate_names"],
                }
                for ref, values in sorted(grouped.items())
            ],
            "discarded_contribution_refs": [],
        },
    )


def _fake_entity_detail(context: dict[str, JsonValue]) -> JsonValue:
    entity = context.get("entity")
    contributions = context.get("contributions")
    if not isinstance(entity, dict) or not isinstance(contributions, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    entity_ref = entity.get("canonical_entity_ref")
    contribution_refs = entity.get("contribution_refs")
    if not isinstance(entity_ref, str) or not isinstance(contribution_refs, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    proposals = _fake_proposals_by_ref(contributions)
    selected_proposals = [
        proposals[reference]
        for reference in contribution_refs
        if isinstance(reference, str) and reference in proposals
    ]
    if len(selected_proposals) != len(contribution_refs) or not selected_proposals:
        raise InvalidRequestError("The local fake agent context is invalid.")
    first = selected_proposals[0]
    object_record = first.get("object")
    if not isinstance(object_record, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    merged_object = dict(object_record)
    supports: list[JsonValue] = []
    seen_sources: set[tuple[str, ...]] = set()
    for proposal in selected_proposals:
        proposal_object = proposal.get("object")
        if not isinstance(proposal_object, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        proposal_supports = proposal_object.get("supports")
        if not isinstance(proposal_supports, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for support in proposal_supports:
            if not isinstance(support, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source = support.get("source_object")
            if not isinstance(source, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source_object = fake_source_object(source)
            source_key = tuple(str(source_object[name]) for name in FAKE_SOURCE_FIELDS)
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                supports.append(support)
    merged_object["supports"] = supports
    return cast(
        JsonValue,
        {"canonical_entity_ref": entity_ref, "object": merged_object},
    )


def _fake_relationship_refinement(context: dict[str, JsonValue]) -> JsonValue:
    package = context.get("relationship_package")
    if not isinstance(package, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    package_ref = package.get("package_ref")
    if not isinstance(package_ref, str):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(
        JsonValue,
        {
            "package_ref": package_ref,
            "disposition": "needs_review",
            "rationale": "The local fake leaves relationship meaning for review.",
            "relationship": None,
        },
    )


def _fake_whole_model_reconciliation(context: dict[str, JsonValue]) -> JsonValue:
    details = context.get("entity_details")
    packages = context.get("relationship_packages")
    refinements = context.get("relationship_refinements")
    work_items = context.get("reconciliation_work_items")
    if isinstance(work_items, list):
        details = [
            item["entity_detail"]
            for item in work_items
            if isinstance(item, dict)
            and item.get("work_item_type") == "entity_detail"
            and isinstance(item.get("entity_detail"), dict)
        ]
        packages = [
            item
            for item in work_items
            if isinstance(item, dict) and item.get("work_item_type") == "relationship_refinement"
        ]
        refinements = [
            item["refinement"] for item in packages if isinstance(item.get("refinement"), dict)
        ]
    applied_refs = context.get(
        "required_applied_record_refs",
        context.get("required_applied_review_refs"),
    )
    input_refs = context.get("required_input_contribution_refs")
    if (
        not isinstance(details, list)
        or not isinstance(packages, list)
        or not isinstance(refinements, list)
        or not isinstance(applied_refs, list)
        or not isinstance(input_refs, list)
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    objects: list[JsonValue] = []
    entity_coverage: list[JsonValue] = []
    for detail in details:
        if not isinstance(detail, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        entity_ref = detail.get("canonical_entity_ref")
        object_record = detail.get("object")
        if object_record is None and isinstance(entity_ref, str):
            object_record = {
                "conceptual_object_name": detail.get("conceptual_object_name"),
                "conceptual_object_definition": detail.get("conceptual_object_definition"),
                "conceptual_object_type": detail.get("conceptual_object_type"),
                "conceptual_object_grain": detail.get("conceptual_object_grain"),
                "conceptual_object_aliases": detail.get("conceptual_object_aliases", []),
                "conceptual_object_confidence": detail.get("conceptual_object_confidence"),
                "conceptual_object_status": detail.get("conceptual_object_status"),
                "conceptual_object_is_locked": False,
                "supports": [
                    {
                        **support,
                        "support_role": "source",
                        "support_reason": "Selected evidence supports this business concept.",
                        "support_reason_detail": None,
                        "support_confidence": "medium",
                        "support_status": "active",
                        "support_is_locked": False,
                    }
                    for support in cast(
                        list[dict[str, JsonValue]],
                        detail.get("support_sources", []),
                    )
                ],
            }
        if not isinstance(entity_ref, str) or not isinstance(object_record, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        name = object_record.get("conceptual_object_name")
        if not isinstance(name, str):
            raise InvalidRequestError("The local fake agent context is invalid.")
        objects.append(cast(JsonValue, object_record))
        entity_coverage.append(
            {
                "canonical_entity_ref": entity_ref,
                "conceptual_object_name": name,
            }
        )
    package_refs: list[JsonValue] = []
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("package_ref"), str):
            raise InvalidRequestError("The local fake agent context is invalid.")
        package_refs.append(cast(str, package["package_ref"]))
    relationships: list[JsonValue] = []
    for refinement in refinements:
        if not isinstance(refinement, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        relationship = refinement.get("relationship")
        if relationship is not None:
            if not isinstance(relationship, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            relationships.append(relationship)
    if any(not isinstance(value, str) for value in applied_refs):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(
        JsonValue,
        {
            "objects": objects,
            "relationships": relationships,
            "entity_coverage": entity_coverage,
            "reviewed_input_contribution_refs": input_refs,
            "reviewed_relationship_package_refs": package_refs,
            "reviewed_applied_record_refs": applied_refs,
        },
    )


def _fake_object_support(source_object: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "support_source_type": "object",
        "source_object": source_object,
        "support_role": "source",
        "support_reason": "The selected Object supports this local candidate.",
        "support_reason_detail": None,
        "support_confidence": "medium",
        "support_status": "active",
        "support_is_locked": False,
    }


def _fake_proposals_by_ref(
    contributions: list[JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    proposals: dict[str, dict[str, JsonValue]] = {}
    for contribution in contributions:
        if not isinstance(contribution, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_ref = contribution.get("contribution_ref")
        values = contribution.get("proposals")
        if not isinstance(contribution_ref, str) or not isinstance(values, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for proposal in values:
            if not isinstance(proposal, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            local_ref = proposal.get("local_entity_ref")
            if not isinstance(local_ref, str):
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_ref = f"{contribution_ref}.{local_ref}"
            if proposal_ref in proposals:
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposals[proposal_ref] = proposal
    return proposals
