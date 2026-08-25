"""Deterministic local-fake Logical candidates."""

from __future__ import annotations

import re
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
    fake_source_attribute,
    fake_source_object,
    selected_source_attributes,
)

_LOGICAL_CONTRIBUTION_REFERENCE = re.compile(r"^object_[0-9]{5}$")
_LOGICAL_RELATIONSHIP_SIGNAL_REFERENCE = re.compile(r"^relationship_signal_[0-9]{5}$")
_LOGICAL_VALIDATION_PACKAGE_REFERENCE = re.compile(r"^validation_[0-9]{5}$")
_LOGICAL_VALIDATION_FINDING_REFERENCE = re.compile(r"^validation_[0-9]{5}\.finding_[0-9]{5}$")


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
                "logical_entity_status": "needs_review",
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
                    "logical_attribute_status": "needs_review",
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


def detailed_logical_candidate(request: AgentExecutionRequest) -> JsonValue:
    original = detailed_original_context(request.context)
    if request.stage == "topology_builder":
        return _fake_logical_topology_contribution(original)
    if request.stage == "topology_reconciler":
        return _fake_logical_topology_reconciliation(original)
    if request.stage == "entity_detail_builder":
        return _fake_logical_entity_detail(original)
    if request.stage == "whole_model_reconciliation":
        return _fake_logical_whole_model_reconciliation(original)
    if request.stage == "validator_worker":
        return _fake_logical_validation_worker(original)
    if request.stage == "validator_lead":
        return _fake_logical_validation_lead(original)
    raise InvalidRequestError("The local fake does not support this agent execution path.")


def _fake_logical_topology_contribution(context: dict[str, JsonValue]) -> JsonValue:
    contribution_ref = context.get("contribution_ref")
    selected = context.get("selected_object")
    if (
        not isinstance(contribution_ref, str)
        or _LOGICAL_CONTRIBUTION_REFERENCE.fullmatch(contribution_ref) is None
        or not isinstance(selected, dict)
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    source = selected.get("object")
    if not isinstance(source, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    source_object = fake_source_object(source)
    source_attributes = selected_source_attributes(
        selected,
        source_object=source_object,
    )
    position = int(contribution_ref.removeprefix("object_"))
    return cast(
        JsonValue,
        {
            "contribution_ref": contribution_ref,
            "source_object": source_object,
            "disposition": "represented",
            "rationale": "Selected Object metadata supports Logical topology.",
            "proposals": [
                {
                    "local_entity_ref": f"entity_{position:05d}",
                    "candidate_entity_name": f"Logical Entity {position}",
                    "candidate_entity_type": "core",
                    "candidate_entity_grain": "One governed Logical entity record.",
                    "candidate_submodel_names": [],
                    "source_attributes": source_attributes,
                }
            ],
        },
    )


def _fake_logical_topology_reconciliation(context: dict[str, JsonValue]) -> JsonValue:
    contributions = context.get("contributions")
    if not isinstance(contributions, list) or not 1 <= len(contributions) <= 50_000:
        raise InvalidRequestError("The local fake agent context is invalid.")

    submodel_names: dict[str, str] = {}
    grouped_entities: dict[str, dict[str, JsonValue]] = {}
    proposal_refs: set[str] = set()
    for contribution in contributions:
        if not isinstance(contribution, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_ref = contribution.get("contribution_ref")
        proposals = contribution.get("proposals")
        if (
            not isinstance(contribution_ref, str)
            or _LOGICAL_CONTRIBUTION_REFERENCE.fullmatch(contribution_ref) is None
            or not isinstance(proposals, list)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            local_ref = proposal.get("local_entity_ref")
            entity_name = proposal.get("candidate_entity_name")
            candidate_submodels = proposal.get("candidate_submodel_names")
            if (
                not isinstance(local_ref, str)
                or TARGET_REFERENCE.fullmatch(local_ref) is None
                or not isinstance(entity_name, str)
                or not entity_name.strip()
                or len(entity_name) > 255
                or not isinstance(candidate_submodels, list)
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_ref = f"{contribution_ref}.{local_ref}"
            if proposal_ref in proposal_refs:
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_refs.add(proposal_ref)

            normalized_submodels: list[str] = []
            for submodel_name in candidate_submodels:
                if (
                    not isinstance(submodel_name, str)
                    or not submodel_name.strip()
                    or len(submodel_name) > 255
                ):
                    raise InvalidRequestError("The local fake agent context is invalid.")
                normalized = submodel_name.strip().casefold()
                if normalized in normalized_submodels:
                    raise InvalidRequestError("The local fake agent context is invalid.")
                normalized_submodels.append(normalized)
                submodel_names.setdefault(normalized, submodel_name)

            normalized_entity = entity_name.strip().casefold()
            entity = grouped_entities.setdefault(
                normalized_entity,
                {
                    "logical_entity_name": entity_name,
                    "contribution_refs": [],
                    "normalized_submodels": [],
                },
            )
            cast(list[JsonValue], entity["contribution_refs"]).append(proposal_ref)
            entity_submodels = cast(list[JsonValue], entity["normalized_submodels"])
            for normalized in normalized_submodels:
                if normalized not in entity_submodels:
                    entity_submodels.append(normalized)

    submodel_refs = {
        normalized: f"submodel_{position:05d}"
        for position, normalized in enumerate(submodel_names, start=1)
    }
    return cast(
        JsonValue,
        {
            "submodels": [
                {
                    "canonical_submodel_ref": submodel_refs[normalized],
                    "submodel": {
                        "logical_submodel_name": name,
                        "logical_submodel_definition": (
                            "A locally generated Logical submodel boundary."
                        ),
                        "logical_submodel_status": "needs_review",
                        "logical_submodel_is_locked": False,
                    },
                }
                for normalized, name in submodel_names.items()
            ],
            "entities": [
                {
                    "canonical_entity_ref": f"entity_{position:05d}",
                    "logical_entity_name": entity["logical_entity_name"],
                    "contribution_refs": entity["contribution_refs"],
                    "submodel_refs": [
                        submodel_refs[cast(str, normalized)]
                        for normalized in cast(
                            list[JsonValue],
                            entity["normalized_submodels"],
                        )
                    ],
                }
                for position, entity in enumerate(grouped_entities.values(), start=1)
            ],
            "discarded_contribution_refs": [],
        },
    )


def _fake_logical_entity_detail(context: dict[str, JsonValue]) -> JsonValue:
    topology = context.get("topology")
    entity = context.get("entity")
    contributions = context.get("contributions")
    if (
        not isinstance(topology, dict)
        or not isinstance(entity, dict)
        or not isinstance(contributions, list)
        or not contributions
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    entity_ref = entity.get("canonical_entity_ref")
    entity_name = entity.get("logical_entity_name")
    contribution_refs = entity.get("contribution_refs")
    entity_submodel_refs = entity.get("submodel_refs")
    if (
        not isinstance(entity_ref, str)
        or TARGET_REFERENCE.fullmatch(entity_ref) is None
        or not isinstance(entity_name, str)
        or not entity_name.strip()
        or not isinstance(contribution_refs, list)
        or not contribution_refs
        or not isinstance(entity_submodel_refs, list)
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    raw_submodels = topology.get("submodels")
    if not isinstance(raw_submodels, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    submodel_names_by_ref: dict[str, str] = {}
    for item in raw_submodels:
        if not isinstance(item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = item.get("canonical_submodel_ref")
        submodel = item.get("submodel")
        name = submodel.get("logical_submodel_name") if isinstance(submodel, dict) else None
        if (
            not isinstance(reference, str)
            or TARGET_REFERENCE.fullmatch(reference) is None
            or reference in submodel_names_by_ref
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        submodel_names_by_ref[reference] = name
    memberships: list[JsonValue] = []
    for reference in entity_submodel_refs:
        if not isinstance(reference, str) or reference not in submodel_names_by_ref:
            raise InvalidRequestError("The local fake agent context is invalid.")
        memberships.append(
            {
                "submodel_name": submodel_names_by_ref[reference],
                "membership_status": "needs_review",
                "membership_is_locked": False,
            }
        )

    contribution_by_ref: dict[str, dict[str, JsonValue]] = {}
    proposal_by_ref: dict[str, dict[str, JsonValue]] = {}
    for contribution in contributions:
        if not isinstance(contribution, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = contribution.get("contribution_ref")
        source = contribution.get("source_object")
        proposals = contribution.get("proposals")
        if (
            not isinstance(reference, str)
            or reference in contribution_by_ref
            or not isinstance(source, dict)
            or not isinstance(proposals, list)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_by_ref[reference] = contribution
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            local_ref = proposal.get("local_entity_ref")
            if not isinstance(local_ref, str):
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_ref = f"{reference}.{local_ref}"
            if proposal_ref in proposal_by_ref:
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_by_ref[proposal_ref] = proposal

    source_objects: list[dict[str, JsonValue]] = []
    source_attributes: list[dict[str, JsonValue]] = []
    seen_objects: set[tuple[str, ...]] = set()
    seen_attributes: set[tuple[str, ...]] = set()
    for proposal_ref in contribution_refs:
        if not isinstance(proposal_ref, str) or proposal_ref not in proposal_by_ref:
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_ref = proposal_ref.split(".", maxsplit=1)[0]
        source = contribution_by_ref[contribution_ref].get("source_object")
        if not isinstance(source, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        source_object = fake_source_object(source)
        object_identity = tuple(
            cast(str, source_object[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
        )
        if object_identity not in seen_objects:
            seen_objects.add(object_identity)
            source_objects.append(source_object)

        proposal_attributes = proposal_by_ref[proposal_ref].get("source_attributes")
        if not isinstance(proposal_attributes, list) or not proposal_attributes:
            raise InvalidRequestError("The local fake agent context is invalid.")
        for raw_attribute in proposal_attributes:
            if not isinstance(raw_attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            values = tuple(
                raw_attribute.get(name) for name in (*FAKE_SOURCE_FIELDS, "attribute_name")
            )
            if any(
                not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 400
                for value in values
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            identity = cast(tuple[str, ...], values)
            normalized = tuple(value.strip().casefold() for value in identity)
            if normalized not in seen_attributes:
                seen_attributes.add(normalized)
                source_attributes.append(
                    dict(
                        zip(
                            (*FAKE_SOURCE_FIELDS, "attribute_name"),
                            identity,
                            strict=True,
                        )
                    )
                )

    return cast(
        JsonValue,
        {
            "canonical_entity_ref": entity_ref,
            "entity": {
                "logical_entity_name": entity_name,
                "logical_entity_definition": (
                    "A locally generated detailed Logical entity candidate."
                ),
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One governed Logical entity record.",
                "logical_entity_dependency_order": 0,
                "logical_entity_confidence": "medium",
                "logical_entity_status": "needs_review",
                "logical_entity_is_locked": False,
                "submodels": memberships,
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": source_object,
                        "source_order": position,
                        "rationale": "Selected Object metadata supports this candidate.",
                        "status": "active",
                        "is_locked": False,
                    }
                    for position, source_object in enumerate(source_objects, start=1)
                ],
            },
            "attributes": [
                {
                    "logical_entity_name": entity_name,
                    "logical_attribute_name": f"Logical Attribute {position}",
                    "logical_attribute_definition": (
                        "A locally generated detailed Logical attribute candidate."
                    ),
                    "logical_attribute_data_type": "string",
                    "logical_attribute_is_nullable": True,
                    "logical_attribute_is_primary_key": False,
                    "logical_attribute_is_natural_key": False,
                    "logical_attribute_is_surrogate_key": False,
                    "logical_attribute_ordinal_position": position,
                    "logical_attribute_is_audit_column": False,
                    "logical_attribute_status": "needs_review",
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
                for position, source_attribute in enumerate(
                    source_attributes,
                    start=1,
                )
            ],
        },
    )


def _fake_logical_whole_model_reconciliation(
    context: dict[str, JsonValue],
) -> JsonValue:
    topology = context.get("topology")
    details = context.get("entity_details")
    ledger = context.get("relationship_signal_ledger")
    applied_refs = context.get("required_applied_record_refs")
    if (
        not isinstance(topology, dict)
        or not isinstance(details, list)
        or not details
        or not isinstance(ledger, dict)
        or not isinstance(applied_refs, list)
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    raw_submodels = topology.get("submodels")
    if not isinstance(raw_submodels, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    submodels: list[JsonValue] = []
    reviewed_submodel_refs: list[JsonValue] = []
    known_submodels: set[str] = set()
    for item in raw_submodels:
        if not isinstance(item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = item.get("canonical_submodel_ref")
        raw_submodel = item.get("submodel")
        name = raw_submodel.get("logical_submodel_name") if isinstance(raw_submodel, dict) else None
        normalized_name = name.strip().casefold() if isinstance(name, str) else ""
        if (
            not isinstance(reference, str)
            or TARGET_REFERENCE.fullmatch(reference) is None
            or reference in reviewed_submodel_refs
            or not isinstance(name, str)
            or not name.strip()
            or normalized_name in known_submodels
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_submodel_refs.append(reference)
        known_submodels.add(normalized_name)
        submodels.append(
            {
                "logical_submodel_name": name,
                "logical_submodel_definition": ("A locally reconciled Logical submodel boundary."),
                "logical_submodel_status": "needs_review",
                "logical_submodel_is_locked": False,
            }
        )

    entities: list[JsonValue] = []
    attributes: list[JsonValue] = []
    reviewed_entity_refs: list[JsonValue] = []
    known_entities: set[str] = set()
    known_attributes: set[tuple[str, str]] = set()
    for detail_position, detail in enumerate(details):
        if not isinstance(detail, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = detail.get("canonical_entity_ref")
        raw_entity = detail.get("entity")
        raw_attributes = detail.get("attributes")
        if (
            not isinstance(reference, str)
            or TARGET_REFERENCE.fullmatch(reference) is None
            or reference in reviewed_entity_refs
            or not isinstance(raw_entity, dict)
            or not isinstance(raw_attributes, list)
            or not raw_attributes
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        entity_name = raw_entity.get("logical_entity_name")
        if not isinstance(entity_name, str) or not entity_name.strip():
            raise InvalidRequestError("The local fake agent context is invalid.")
        normalized_entity = entity_name.strip().casefold()
        if normalized_entity in known_entities:
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_entity_refs.append(reference)
        known_entities.add(normalized_entity)

        raw_memberships = raw_entity.get("submodels")
        raw_sources = raw_entity.get("sources")
        if not isinstance(raw_memberships, list) or not isinstance(raw_sources, list):
            raise InvalidRequestError("The local fake agent context is invalid.")
        memberships: list[JsonValue] = []
        membership_names: set[str] = set()
        for membership in raw_memberships:
            name = membership.get("submodel_name") if isinstance(membership, dict) else None
            normalized = name.strip().casefold() if isinstance(name, str) else ""
            if (
                not isinstance(name, str)
                or not name.strip()
                or normalized not in known_submodels
                or normalized in membership_names
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            membership_names.add(normalized)
            memberships.append(
                {
                    "submodel_name": name,
                    "membership_status": "needs_review",
                    "membership_is_locked": False,
                }
            )

        entity_sources: list[JsonValue] = []
        entity_source_keys: set[tuple[str, ...]] = set()
        for raw_source in raw_sources:
            if (
                not isinstance(raw_source, dict)
                or raw_source.get("support_source_type") != "object"
            ):
                continue
            raw_source_object = raw_source.get("source_object")
            if not isinstance(raw_source_object, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source_object = fake_source_object(raw_source_object)
            source_key = tuple(
                cast(str, source_object[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
            )
            if source_key in entity_source_keys:
                raise InvalidRequestError("The local fake agent context is invalid.")
            entity_source_keys.add(source_key)
            entity_sources.append(
                {
                    "support_source_type": "object",
                    "source_object": source_object,
                    "source_order": len(entity_sources) + 1,
                    "rationale": "Selected Object metadata supports this candidate.",
                    "status": "active",
                    "is_locked": False,
                }
            )
        if not entity_sources:
            raise InvalidRequestError("The local fake agent context is invalid.")

        entities.append(
            {
                "logical_entity_name": entity_name,
                "logical_entity_definition": (
                    "A locally reconciled detailed Logical entity candidate."
                ),
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One governed Logical entity record.",
                "logical_entity_dependency_order": detail_position,
                "logical_entity_confidence": "medium",
                "logical_entity_status": "needs_review",
                "logical_entity_is_locked": False,
                "submodels": memberships,
                "sources": entity_sources,
            }
        )

        for attribute_position, raw_attribute in enumerate(raw_attributes, start=1):
            if not isinstance(raw_attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            attribute_entity_name = raw_attribute.get("logical_entity_name")
            attribute_name = raw_attribute.get("logical_attribute_name")
            if (
                not isinstance(attribute_entity_name, str)
                or attribute_entity_name.strip().casefold() != normalized_entity
                or not isinstance(attribute_name, str)
                or not attribute_name.strip()
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            attribute_key = (normalized_entity, attribute_name.strip().casefold())
            if attribute_key in known_attributes:
                raise InvalidRequestError("The local fake agent context is invalid.")
            known_attributes.add(attribute_key)
            raw_attribute_sources = raw_attribute.get("sources")
            if not isinstance(raw_attribute_sources, list):
                raise InvalidRequestError("The local fake agent context is invalid.")
            attribute_sources: list[JsonValue] = []
            attribute_source_keys: set[tuple[str, ...]] = set()
            for raw_source in raw_attribute_sources:
                if (
                    not isinstance(raw_source, dict)
                    or raw_source.get("support_source_type") != "attribute"
                ):
                    continue
                raw_source_attribute = raw_source.get("source_attribute")
                if not isinstance(raw_source_attribute, dict):
                    raise InvalidRequestError("The local fake agent context is invalid.")
                source_attribute = fake_source_attribute(raw_source_attribute)
                source_key = tuple(
                    cast(str, source_attribute[name]).strip().casefold()
                    for name in (*FAKE_SOURCE_FIELDS, "attribute_name")
                )
                if source_key in attribute_source_keys:
                    raise InvalidRequestError("The local fake agent context is invalid.")
                attribute_source_keys.add(source_key)
                attribute_sources.append(
                    {
                        "support_source_type": "attribute",
                        "source_attribute": source_attribute,
                        "source_order": len(attribute_sources) + 1,
                        "rationale": ("Selected Attribute metadata supports this candidate."),
                        "status": "active",
                        "is_locked": False,
                    }
                )
            if not attribute_sources:
                raise InvalidRequestError("The local fake agent context is invalid.")
            attributes.append(
                {
                    "logical_entity_name": entity_name,
                    "logical_attribute_name": attribute_name,
                    "logical_attribute_definition": (
                        "A locally reconciled detailed Logical attribute candidate."
                    ),
                    "logical_attribute_data_type": "string",
                    "logical_attribute_is_nullable": True,
                    "logical_attribute_is_primary_key": False,
                    "logical_attribute_is_natural_key": False,
                    "logical_attribute_is_surrogate_key": False,
                    "logical_attribute_ordinal_position": attribute_position,
                    "logical_attribute_is_audit_column": False,
                    "logical_attribute_status": "needs_review",
                    "logical_attribute_is_locked": False,
                    "sources": attribute_sources,
                }
            )

    raw_signals = ledger.get("signals")
    if not isinstance(raw_signals, list):
        raise InvalidRequestError("The local fake agent context is invalid.")
    reviewed_signal_refs: list[JsonValue] = []
    for signal in raw_signals:
        reference = signal.get("signal_ref") if isinstance(signal, dict) else None
        if (
            not isinstance(reference, str)
            or _LOGICAL_RELATIONSHIP_SIGNAL_REFERENCE.fullmatch(reference) is None
            or reference in reviewed_signal_refs
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_signal_refs.append(reference)
    if any(not isinstance(reference, str) for reference in applied_refs) or len(
        applied_refs
    ) != len(set(cast(list[str], applied_refs))):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(
        JsonValue,
        {
            "submodels": submodels,
            "entities": entities,
            "attributes": attributes,
            "relationships": [],
            "reviewed_submodel_refs": reviewed_submodel_refs,
            "reviewed_entity_refs": reviewed_entity_refs,
            "reviewed_relationship_signal_refs": reviewed_signal_refs,
            "reviewed_applied_record_refs": applied_refs,
        },
    )


def _fake_logical_validation_worker(context: dict[str, JsonValue]) -> JsonValue:
    package = context.get("validation_package")
    if not isinstance(package, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    package_ref = package.get("package_ref")
    records = package.get("records")
    if (
        not isinstance(package_ref, str)
        or _LOGICAL_VALIDATION_PACKAGE_REFERENCE.fullmatch(package_ref) is None
        or not isinstance(records, list)
        or not 1 <= len(records) <= 1_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    record_refs: list[JsonValue] = []
    for record in records:
        reference = record.get("record_ref") if isinstance(record, dict) else None
        if (
            not isinstance(reference, str)
            or not reference.strip()
            or len(reference) > 1_000
            or reference in record_refs
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        record_refs.append(reference)
    return cast(
        JsonValue,
        {
            "package_ref": package_ref,
            "reviewed_record_refs": record_refs,
            "findings": [],
        },
    )


def _fake_logical_validation_lead(context: dict[str, JsonValue]) -> JsonValue:
    worker_results = context.get("worker_results")
    if not isinstance(worker_results, list) or not 1 <= len(worker_results) <= 10_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    package_refs: list[JsonValue] = []
    finding_refs: list[JsonValue] = []
    blocking_refs: list[JsonValue] = []
    for result in worker_results:
        if not isinstance(result, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        package_ref = result.get("package_ref")
        findings = result.get("findings")
        if (
            not isinstance(package_ref, str)
            or _LOGICAL_VALIDATION_PACKAGE_REFERENCE.fullmatch(package_ref) is None
            or package_ref in package_refs
            or not isinstance(findings, list)
            or len(findings) > 200
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        package_refs.append(package_ref)
        for finding in findings:
            if not isinstance(finding, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            finding_ref = finding.get("finding_ref")
            severity = finding.get("severity")
            if (
                not isinstance(finding_ref, str)
                or _LOGICAL_VALIDATION_FINDING_REFERENCE.fullmatch(finding_ref) is None
                or not finding_ref.startswith(f"{package_ref}.")
                or finding_ref in finding_refs
                or severity not in ("warning", "error")
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            finding_refs.append(finding_ref)
            if severity == "error":
                blocking_refs.append(finding_ref)
    return cast(
        JsonValue,
        {
            "reviewed_package_refs": package_refs,
            "reviewed_finding_refs": finding_refs,
            "blocking_finding_refs": blocking_refs,
            "repair_brief": (
                "Repair the blocking Logical validation findings." if blocking_refs else None
            ),
        },
    )
