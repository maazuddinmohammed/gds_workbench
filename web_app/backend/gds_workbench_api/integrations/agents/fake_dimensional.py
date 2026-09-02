"""Deterministic local-fake Dimensional candidates."""

from __future__ import annotations

import re
from collections.abc import Sequence
from hashlib import sha256
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

_DIMENSIONAL_CONTRIBUTION_REFERENCE = re.compile(r"^object_([0-9]{5})(?:_batch_([0-9]{5}))?$")
_DIMENSIONAL_RELATIONSHIP_SIGNAL_REFERENCE = re.compile(r"^relationship_signal_[0-9]{5}$")
_DIMENSIONAL_VALIDATION_PACKAGE_REFERENCE = re.compile(r"^validation_[0-9]{5}$")
_DIMENSIONAL_VALIDATION_FINDING_REFERENCE = re.compile(r"^validation_[0-9]{5}\.finding_[0-9]{5}$")


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


def detailed_dimensional_candidate(request: AgentExecutionRequest) -> JsonValue:
    original = detailed_original_context(request.context)
    if request.stage == "topology_builder":
        return _fake_dimensional_topology_contribution(original)
    if request.stage == "topology_reconciler":
        return _fake_dimensional_topology_reconciliation(original)
    if request.stage == "entity_detail_builder":
        return _fake_dimensional_entity_detail(original)
    if request.stage == "whole_model_reconciliation":
        if "review_manifest" in original:
            return _fake_dimensional_reconciliation_receipt(original)
        return _fake_dimensional_whole_model_reconciliation(original)
    if request.stage == "validator_worker":
        return _fake_dimensional_validation_worker(original)
    if request.stage == "validator_lead":
        return _fake_dimensional_validation_lead(original)
    raise InvalidRequestError("The local fake does not support this agent execution path.")


def _fake_dimensional_topology_contribution(context: dict[str, JsonValue]) -> JsonValue:
    contribution_ref = context.get("contribution_ref")
    selected = context.get("selected_object")
    if (
        not isinstance(contribution_ref, str)
        or _DIMENSIONAL_CONTRIBUTION_REFERENCE.fullmatch(contribution_ref) is None
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
    match = _DIMENSIONAL_CONTRIBUTION_REFERENCE.fullmatch(contribution_ref)
    if match is None:
        raise InvalidRequestError("The local fake agent context is invalid.")
    position = int(match.group(1))
    return cast(
        JsonValue,
        {
            "contribution_ref": contribution_ref,
            "source_object": source_object,
            "disposition": "represented",
            "rationale": "Selected Object metadata supports Dimensional topology.",
            "proposals": [
                {
                    "local_entity_ref": f"entity_{position:05d}",
                    "candidate_entity_name": f"Dimensional Entity {position}",
                    "candidate_entity_type": "dimension",
                    "candidate_fact_type": None,
                    "candidate_entity_grain_definition": None,
                    "candidate_submodel_names": [],
                    "source_attributes": source_attributes,
                }
            ],
        },
    )


def _fake_dimensional_topology_reconciliation(
    context: dict[str, JsonValue],
) -> JsonValue:
    contributions = context.get("contributions")
    if not isinstance(contributions, list) or not 1 <= len(contributions) <= 50_000:
        raise InvalidRequestError("The local fake agent context is invalid.")

    submodel_names: dict[str, str] = {}
    grouped_entities: dict[str, dict[str, JsonValue]] = {}
    contribution_refs: set[str] = set()
    proposal_refs: set[str] = set()
    proposal_count = 0
    for contribution in contributions:
        if not isinstance(contribution, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_ref = contribution.get("contribution_ref")
        proposals = contribution.get("proposals")
        disposition = contribution.get("disposition")
        if (
            not isinstance(contribution_ref, str)
            or _DIMENSIONAL_CONTRIBUTION_REFERENCE.fullmatch(contribution_ref) is None
            or contribution_ref in contribution_refs
            or disposition not in ("represented", "not_dimensional", "needs_review")
            or not isinstance(proposals, list)
            or len(proposals) > 200
            or (disposition == "represented") != bool(proposals)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_refs.add(contribution_ref)
        for proposal in proposals:
            proposal_count += 1
            if proposal_count > 50_000 or not isinstance(proposal, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            local_ref = proposal.get("local_entity_ref")
            entity_name = proposal.get("candidate_entity_name")
            entity_type = proposal.get("candidate_entity_type")
            fact_type = proposal.get("candidate_fact_type")
            grain = proposal.get("candidate_entity_grain_definition")
            candidate_submodels = proposal.get("candidate_submodel_names")
            if (
                not isinstance(local_ref, str)
                or TARGET_REFERENCE.fullmatch(local_ref) is None
                or not isinstance(entity_name, str)
                or not entity_name.strip()
                or len(entity_name) > 255
                or entity_type not in ("fact", "dimension", "bridge")
                or (entity_type == "fact") != (fact_type is not None)
                or (
                    fact_type is not None
                    and fact_type
                    not in (
                        "transaction",
                        "periodic_snapshot",
                        "accumulating_snapshot",
                        "factless",
                    )
                )
                or (
                    grain is not None
                    and (not isinstance(grain, str) or not grain.strip() or len(grain) > 2_000)
                )
                or (entity_type in ("fact", "bridge") and grain is None)
                or not isinstance(candidate_submodels, list)
                or len(candidate_submodels) > 100
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
            shape = cast(JsonValue, [entity_type, fact_type, grain])
            entity = grouped_entities.setdefault(
                normalized_entity,
                {
                    "dimensional_entity_name": entity_name,
                    "contribution_refs": [],
                    "normalized_submodels": [],
                    "shape": shape,
                },
            )
            if entity["shape"] != shape:
                raise InvalidRequestError("The local fake agent context is invalid.")
            cast(list[JsonValue], entity["contribution_refs"]).append(proposal_ref)
            entity_submodels = cast(list[JsonValue], entity["normalized_submodels"])
            for normalized in normalized_submodels:
                if normalized not in entity_submodels:
                    entity_submodels.append(normalized)

    if len(submodel_names) > 20_000 or len(grouped_entities) > 20_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
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
                        "dimensional_submodel_name": name,
                        "dimensional_submodel_definition": (
                            "A locally generated Dimensional submodel boundary."
                        ),
                        "dimensional_submodel_status": "active",
                        "dimensional_submodel_is_locked": False,
                    },
                }
                for normalized, name in submodel_names.items()
            ],
            "entities": [
                {
                    "canonical_entity_ref": f"entity_{position:05d}",
                    "dimensional_entity_name": entity["dimensional_entity_name"],
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


def _fake_dimensional_entity_detail(context: dict[str, JsonValue]) -> JsonValue:
    topology = context.get("topology")
    entity = context.get("entity")
    contributions = context.get("contributions")
    if (
        not isinstance(topology, dict)
        or not isinstance(entity, dict)
        or not isinstance(contributions, list)
        or not 1 <= len(contributions) <= 50_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    entity_ref = entity.get("canonical_entity_ref")
    entity_name = entity.get("dimensional_entity_name")
    contribution_refs = entity.get("contribution_refs")
    entity_submodel_refs = entity.get("submodel_refs")
    if (
        not isinstance(entity_ref, str)
        or TARGET_REFERENCE.fullmatch(entity_ref) is None
        or not isinstance(entity_name, str)
        or not entity_name.strip()
        or len(entity_name) > 255
        or not isinstance(contribution_refs, list)
        or not 1 <= len(contribution_refs) <= 50_000
        or any(not isinstance(reference, str) for reference in contribution_refs)
        or len(contribution_refs) != len(set(cast(list[str], contribution_refs)))
        or not isinstance(entity_submodel_refs, list)
        or len(entity_submodel_refs) > 100
        or any(not isinstance(reference, str) for reference in entity_submodel_refs)
        or len(entity_submodel_refs) != len(set(cast(list[str], entity_submodel_refs)))
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    raw_submodels = topology.get("submodels")
    if not isinstance(raw_submodels, list) or len(raw_submodels) > 20_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    submodel_names_by_ref: dict[str, str] = {}
    for item in raw_submodels:
        if not isinstance(item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = item.get("canonical_submodel_ref")
        submodel = item.get("submodel")
        name = submodel.get("dimensional_submodel_name") if isinstance(submodel, dict) else None
        if (
            not isinstance(reference, str)
            or TARGET_REFERENCE.fullmatch(reference) is None
            or reference in submodel_names_by_ref
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 255
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
                "membership_status": "active",
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
            or _DIMENSIONAL_CONTRIBUTION_REFERENCE.fullmatch(reference) is None
            or reference in contribution_by_ref
            or not isinstance(source, dict)
            or not isinstance(proposals, list)
            or len(proposals) > 200
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        contribution_by_ref[reference] = contribution
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            local_ref = proposal.get("local_entity_ref")
            if not isinstance(local_ref, str) or TARGET_REFERENCE.fullmatch(local_ref) is None:
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_ref = f"{reference}.{local_ref}"
            if proposal_ref in proposal_by_ref:
                raise InvalidRequestError("The local fake agent context is invalid.")
            proposal_by_ref[proposal_ref] = proposal

    source_objects: list[dict[str, JsonValue]] = []
    source_attributes: list[dict[str, JsonValue]] = []
    seen_objects: set[tuple[str, ...]] = set()
    seen_attributes: set[tuple[str, ...]] = set()
    entity_shape: tuple[str, JsonValue, JsonValue] | None = None
    for proposal_ref in contribution_refs:
        if not isinstance(proposal_ref, str) or proposal_ref not in proposal_by_ref:
            raise InvalidRequestError("The local fake agent context is invalid.")
        proposal = proposal_by_ref[proposal_ref]
        proposal_name = proposal.get("candidate_entity_name")
        entity_type = proposal.get("candidate_entity_type")
        fact_type = proposal.get("candidate_fact_type")
        grain = proposal.get("candidate_entity_grain_definition")
        if (
            not isinstance(proposal_name, str)
            or proposal_name.strip().casefold() != entity_name.strip().casefold()
            or entity_type not in ("fact", "dimension", "bridge")
            or (entity_type == "fact") != (fact_type is not None)
            or (
                fact_type is not None
                and fact_type
                not in (
                    "transaction",
                    "periodic_snapshot",
                    "accumulating_snapshot",
                    "factless",
                )
            )
            or (
                grain is not None
                and (not isinstance(grain, str) or not grain.strip() or len(grain) > 2_000)
            )
            or (entity_type in ("fact", "bridge") and grain is None)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        shape = (entity_type, fact_type, grain)
        if entity_shape is None:
            entity_shape = shape
        elif entity_shape != shape:
            raise InvalidRequestError("The local fake agent context is invalid.")

        contribution_ref = proposal_ref.split(".", maxsplit=1)[0]
        raw_source_object = contribution_by_ref[contribution_ref].get("source_object")
        if not isinstance(raw_source_object, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        source_object = fake_source_object(raw_source_object)
        object_identity = tuple(
            cast(str, source_object[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS
        )
        if object_identity not in seen_objects:
            seen_objects.add(object_identity)
            source_objects.append(source_object)

        proposal_attributes = proposal.get("source_attributes")
        if not isinstance(proposal_attributes, list) or not proposal_attributes:
            raise InvalidRequestError("The local fake agent context is invalid.")
        for raw_attribute in proposal_attributes:
            if not isinstance(raw_attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source_attribute = fake_source_attribute(raw_attribute)
            identity = tuple(
                cast(str, source_attribute[name]).strip().casefold()
                for name in (*FAKE_SOURCE_FIELDS, "attribute_name")
            )
            if identity[:5] != object_identity or identity in seen_attributes:
                raise InvalidRequestError("The local fake agent context is invalid.")
            seen_attributes.add(identity)
            source_attributes.append(source_attribute)
            if len(source_attributes) > 10_000:
                raise InvalidRequestError("The local fake agent context is invalid.")
    if entity_shape is None or not source_objects or not source_attributes:
        raise InvalidRequestError("The local fake agent context is invalid.")
    entity_type, fact_type, grain = entity_shape
    return cast(
        JsonValue,
        {
            "canonical_entity_ref": entity_ref,
            "entity": _fake_dimensional_entity_record(
                entity_name=entity_name,
                entity_type=entity_type,
                fact_type=fact_type,
                grain_definition=grain,
                dependency_order=0,
                memberships=memberships,
                sources=[
                    _fake_dimensional_object_source(
                        source_object,
                        source_order=position,
                    )
                    for position, source_object in enumerate(source_objects, start=1)
                ],
            ),
            "attributes": [
                _fake_dimensional_attribute_record(
                    entity_name=entity_name,
                    attribute_name=_fake_dimensional_attribute_name(source_attribute),
                    ordinal=position,
                    sources=[
                        _fake_dimensional_attribute_source(
                            source_attribute,
                            source_order=1,
                        )
                    ],
                )
                for position, source_attribute in enumerate(source_attributes, start=1)
            ],
        },
    )


def _fake_dimensional_reconciliation_receipt(
    context: dict[str, JsonValue],
) -> JsonValue:
    partition_ref = context.get("partition_ref")
    manifest = context.get("review_manifest")
    signals = context.get("relationship_signals")
    if (
        not isinstance(partition_ref, str)
        or re.fullmatch(r"reconciliation_[0-9]{5}", partition_ref) is None
        or not isinstance(manifest, dict)
        or not isinstance(signals, list)
        or len(signals) > 1_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    reviewed_refs: list[JsonValue] = []
    relationships: list[JsonValue] = []
    relationship_keys: set[tuple[str, str, str, str]] = set()
    for signal in signals:
        if not isinstance(signal, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = signal.get("signal_ref")
        endpoints = (
            signal.get("from_dimensional_entity_name"),
            signal.get("from_dimensional_attribute_name"),
            signal.get("to_dimensional_entity_name"),
            signal.get("to_dimensional_attribute_name"),
        )
        if (
            not isinstance(reference, str)
            or _DIMENSIONAL_RELATIONSHIP_SIGNAL_REFERENCE.fullmatch(reference) is None
            or reference in reviewed_refs
            or any(not isinstance(item, str) or not item.strip() for item in endpoints)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_refs.append(reference)
        typed_endpoints = cast(tuple[str, str, str, str], endpoints)
        key = tuple(item.strip().casefold() for item in typed_endpoints)
        if key in relationship_keys:
            continue
        relationship_keys.add(cast(tuple[str, str, str, str], key))
        from_entity, from_attribute, to_entity, to_attribute = typed_endpoints
        relationships.append(
            {
                "dimensional_relationship_name": (
                    f"Dimensional Relationship {len(relationships) + 1}"
                ),
                "dimensional_relationship_definition": (
                    "A locally generated Dimensional business relationship."
                ),
                "from_dimensional_entity_name": from_entity,
                "from_dimensional_attribute_name": from_attribute,
                "to_dimensional_entity_name": to_entity,
                "to_dimensional_attribute_name": to_attribute,
                "dimensional_relationship_kind": "reference",
                "dimensional_relationship_cardinality": "many_to_one",
                "dimensional_relationship_is_optional": True,
                "dimensional_relationship_role_name": None,
                "dimensional_relationship_confidence": "medium",
                "dimensional_relationship_basis": (
                    "Canonical Attribute evidence supports this relationship."
                ),
                "dimensional_relationship_cardinality_basis": (
                    "The local fake requires review of relationship cardinality."
                ),
                "dimensional_relationship_status": "active",
                "dimensional_relationship_is_locked": False,
            }
        )
    return cast(
        JsonValue,
        {
            "partition_ref": partition_ref,
            "manifest": manifest,
            "reviewed_relationship_signal_refs": reviewed_refs,
            "relationships": relationships,
        },
    )


def _fake_dimensional_whole_model_reconciliation(
    context: dict[str, JsonValue],
) -> JsonValue:
    topology = context.get("topology")
    details = context.get("entity_details")
    ledger = context.get("relationship_signal_ledger")
    applied_refs = context.get("required_applied_record_refs")
    if (
        not isinstance(topology, dict)
        or not isinstance(details, list)
        or len(details) > 20_000
        or not isinstance(ledger, dict)
        or not isinstance(applied_refs, list)
        or len(applied_refs) > 80_000
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")

    raw_submodels = topology.get("submodels")
    if not isinstance(raw_submodels, list) or len(raw_submodels) > 20_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    submodels: list[JsonValue] = []
    reviewed_submodel_refs: list[JsonValue] = []
    known_submodels: set[str] = set()
    for item in raw_submodels:
        if not isinstance(item, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = item.get("canonical_submodel_ref")
        raw_submodel = item.get("submodel")
        name = (
            raw_submodel.get("dimensional_submodel_name")
            if isinstance(raw_submodel, dict)
            else None
        )
        normalized_name = name.strip().casefold() if isinstance(name, str) else ""
        if (
            not isinstance(reference, str)
            or TARGET_REFERENCE.fullmatch(reference) is None
            or reference in reviewed_submodel_refs
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 255
            or normalized_name in known_submodels
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_submodel_refs.append(reference)
        known_submodels.add(normalized_name)
        submodels.append(
            {
                "dimensional_submodel_name": name,
                "dimensional_submodel_definition": (
                    "A locally reconciled Dimensional submodel boundary."
                ),
                "dimensional_submodel_status": "active",
                "dimensional_submodel_is_locked": False,
            }
        )

    entities: list[JsonValue] = []
    attributes: list[JsonValue] = []
    reviewed_entity_refs: list[JsonValue] = []
    known_entities: set[str] = set()
    known_attributes: set[tuple[str, str]] = set()
    entity_types: dict[str, str] = {}
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
            or len(raw_attributes) > 10_000
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        entity_name = raw_entity.get("dimensional_entity_name")
        entity_type = raw_entity.get("dimensional_entity_type")
        fact_type = raw_entity.get("dimensional_fact_type")
        grain = raw_entity.get("dimensional_entity_grain_definition")
        if (
            not isinstance(entity_name, str)
            or not entity_name.strip()
            or len(entity_name) > 255
            or entity_type not in ("fact", "dimension", "bridge")
            or (entity_type == "fact") != (fact_type is not None)
            or (
                fact_type is not None
                and fact_type
                not in (
                    "transaction",
                    "periodic_snapshot",
                    "accumulating_snapshot",
                    "factless",
                )
            )
            or (
                grain is not None
                and (not isinstance(grain, str) or not grain.strip() or len(grain) > 2_000)
            )
            or (entity_type in ("fact", "bridge") and grain is None)
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        normalized_entity = entity_name.strip().casefold()
        if normalized_entity in known_entities:
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_entity_refs.append(reference)
        known_entities.add(normalized_entity)
        entity_types[normalized_entity] = entity_type

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
                or len(name) > 255
                or normalized not in known_submodels
                or normalized in membership_names
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            membership_names.add(normalized)
            memberships.append(
                {
                    "submodel_name": name,
                    "membership_status": "active",
                    "membership_is_locked": False,
                }
            )

        entity_sources = _fake_dimensional_entity_sources(raw_sources)
        entities.append(
            _fake_dimensional_entity_record(
                entity_name=entity_name,
                entity_type=entity_type,
                fact_type=fact_type,
                grain_definition=grain,
                dependency_order=detail_position,
                memberships=memberships,
                sources=entity_sources,
            )
        )

        for attribute_position, raw_attribute in enumerate(raw_attributes, start=1):
            if not isinstance(raw_attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            attribute_entity_name = raw_attribute.get("dimensional_entity_name")
            attribute_name = raw_attribute.get("dimensional_attribute_name")
            if (
                not isinstance(attribute_entity_name, str)
                or attribute_entity_name.strip().casefold() != normalized_entity
                or not isinstance(attribute_name, str)
                or not attribute_name.strip()
                or len(attribute_name) > 255
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            attribute_key = (normalized_entity, attribute_name.strip().casefold())
            if attribute_key in known_attributes:
                raise InvalidRequestError("The local fake agent context is invalid.")
            known_attributes.add(attribute_key)
            raw_attribute_sources = raw_attribute.get("sources")
            if not isinstance(raw_attribute_sources, list) or not raw_attribute_sources:
                raise InvalidRequestError("The local fake agent context is invalid.")
            attribute_sources = _fake_dimensional_attribute_sources(raw_attribute_sources)
            attributes.append(
                _fake_dimensional_attribute_record(
                    entity_name=entity_name,
                    attribute_name=attribute_name,
                    ordinal=attribute_position,
                    sources=attribute_sources,
                )
            )
            if len(submodels) + len(entities) + len(attributes) > 20_000:
                raise InvalidRequestError("The local fake agent context is invalid.")

    raw_signals = ledger.get("signals")
    if not isinstance(raw_signals, list) or len(raw_signals) > 50_000:
        raise InvalidRequestError("The local fake agent context is invalid.")
    reviewed_signal_refs: list[JsonValue] = []
    relationships: list[JsonValue] = []
    relationship_keys: set[tuple[str, ...]] = set()
    projected_entity_pairs: set[tuple[str, str]] = set()
    for signal in raw_signals:
        if not isinstance(signal, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reference = signal.get("signal_ref")
        from_entity = signal.get("from_dimensional_entity_name")
        from_attribute = signal.get("from_dimensional_attribute_name")
        to_entity = signal.get("to_dimensional_entity_name")
        to_attribute = signal.get("to_dimensional_attribute_name")
        endpoints = (from_entity, from_attribute, to_entity, to_attribute)
        if (
            not isinstance(reference, str)
            or _DIMENSIONAL_RELATIONSHIP_SIGNAL_REFERENCE.fullmatch(reference) is None
            or reference in reviewed_signal_refs
            or any(
                not isinstance(value, str) or not value.strip() or len(value) > 255
                for value in endpoints
            )
        ):
            raise InvalidRequestError("The local fake agent context is invalid.")
        reviewed_signal_refs.append(reference)
        from_entity_value, from_attribute_value, to_entity_value, to_attribute_value = cast(
            tuple[str, str, str, str], endpoints
        )
        from_key = (
            from_entity_value.strip().casefold(),
            from_attribute_value.strip().casefold(),
        )
        to_key = (
            to_entity_value.strip().casefold(),
            to_attribute_value.strip().casefold(),
        )
        if from_key not in known_attributes or to_key not in known_attributes:
            raise InvalidRequestError("The local fake agent context is invalid.")
        if entity_types[from_key[0]] == "dimension" and entity_types[to_key[0]] in (
            "fact",
            "bridge",
        ):
            from_entity_value, to_entity_value = to_entity_value, from_entity_value
            from_attribute_value, to_attribute_value = to_attribute_value, from_attribute_value
            from_key, to_key = to_key, from_key
        if entity_types[to_key[0]] in ("fact", "bridge"):
            continue
        entity_pair = (from_key[0], to_key[0])
        if (
            entity_types[from_key[0]] in ("fact", "bridge")
            and entity_pair in projected_entity_pairs
        ):
            continue
        relationship_key = (*from_key, *to_key, "reference", "")
        if relationship_key in relationship_keys:
            continue
        if len(submodels) + len(entities) + len(attributes) + len(relationships) >= 20_000:
            continue
        relationship_keys.add(relationship_key)
        projected_entity_pairs.add(entity_pair)
        relationships.append(
            {
                "dimensional_relationship_name": (
                    f"Dimensional Relationship {len(relationships) + 1}"
                ),
                "dimensional_relationship_definition": (
                    "A locally generated Dimensional business relationship."
                ),
                "from_dimensional_entity_name": from_entity_value,
                "from_dimensional_attribute_name": from_attribute_value,
                "to_dimensional_entity_name": to_entity_value,
                "to_dimensional_attribute_name": to_attribute_value,
                "dimensional_relationship_kind": "reference",
                "dimensional_relationship_cardinality": "many_to_one",
                "dimensional_relationship_is_optional": True,
                "dimensional_relationship_role_name": None,
                "dimensional_relationship_confidence": "medium",
                "dimensional_relationship_basis": (
                    "Canonical Attribute evidence supports this relationship."
                ),
                "dimensional_relationship_cardinality_basis": (
                    "The local fake requires review of relationship cardinality."
                ),
                "dimensional_relationship_status": "active",
                "dimensional_relationship_is_locked": False,
            }
        )
    if (
        not 1 <= len(submodels) + len(entities) + len(attributes) + len(relationships) <= 20_000
        or any(
            not isinstance(reference, str) or not reference.strip() or len(reference) > 10_000
            for reference in applied_refs
        )
        or len(applied_refs) != len(set(cast(list[str], applied_refs)))
    ):
        raise InvalidRequestError("The local fake agent context is invalid.")
    return cast(
        JsonValue,
        {
            "submodels": submodels,
            "entities": entities,
            "attributes": attributes,
            "relationships": relationships,
            "reviewed_submodel_refs": reviewed_submodel_refs,
            "reviewed_entity_refs": reviewed_entity_refs,
            "reviewed_relationship_signal_refs": reviewed_signal_refs,
            "reviewed_applied_record_refs": applied_refs,
        },
    )


def _fake_dimensional_validation_worker(context: dict[str, JsonValue]) -> JsonValue:
    package = context.get("validation_package")
    if not isinstance(package, dict):
        raise InvalidRequestError("The local fake agent context is invalid.")
    package_ref = package.get("package_ref")
    records = package.get("records")
    if (
        not isinstance(package_ref, str)
        or _DIMENSIONAL_VALIDATION_PACKAGE_REFERENCE.fullmatch(package_ref) is None
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
            or len(reference) > 10_000
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


def _fake_dimensional_validation_lead(context: dict[str, JsonValue]) -> JsonValue:
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
            or _DIMENSIONAL_VALIDATION_PACKAGE_REFERENCE.fullmatch(package_ref) is None
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
                or _DIMENSIONAL_VALIDATION_FINDING_REFERENCE.fullmatch(finding_ref) is None
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
                "Repair the blocking Dimensional validation findings." if blocking_refs else None
            ),
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


def _fake_dimensional_attribute_name(
    source_attribute: dict[str, JsonValue],
) -> str:
    object_name = source_attribute.get("object_name")
    attribute_name = source_attribute.get("attribute_name")
    if not isinstance(object_name, str) or not isinstance(attribute_name, str):
        raise InvalidRequestError("The local fake agent context is invalid.")
    value = f"{object_name} {attribute_name}"
    if len(value) <= 255:
        return value
    digest = sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{value[:241]} {digest}"


def _fake_dimensional_entity_sources(
    raw_sources: list[JsonValue],
) -> list[JsonValue]:
    sources: list[JsonValue] = []
    identities: set[tuple[str, ...]] = set()
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        source: dict[str, JsonValue]
        source_type = raw_source.get("support_source_type")
        if source_type == "object":
            raw_source_object = raw_source.get("source_object")
            if not isinstance(raw_source_object, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source_object = fake_source_object(raw_source_object)
            identity = (
                "object",
                *(cast(str, source_object[name]).strip().casefold() for name in FAKE_SOURCE_FIELDS),
            )
            source = _fake_dimensional_object_source(
                source_object,
                source_order=len(sources) + 1,
            )
        elif source_type == "assertion":
            assertion = raw_source.get("assertion_record")
            key = (
                assertion.get("modeling_assertion_record_key")
                if isinstance(assertion, dict)
                else None
            )
            if (
                not isinstance(key, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,99}", key) is None
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            identity = ("assertion", key.strip().casefold())
            source = {
                "support_source_type": "assertion",
                "assertion_record": {"modeling_assertion_record_key": key},
                "source_order": len(sources) + 1,
                "rationale": "Governed Assertion metadata supports this candidate.",
                "status": "active",
                "is_locked": False,
                "source_role": "supporting",
            }
        else:
            raise InvalidRequestError("The local fake agent context is invalid.")
        if identity in identities:
            raise InvalidRequestError("The local fake agent context is invalid.")
        identities.add(identity)
        sources.append(source)
    return sources


def _fake_dimensional_attribute_sources(
    raw_sources: list[JsonValue],
) -> list[JsonValue]:
    sources: list[JsonValue] = []
    identities: set[tuple[str, ...]] = set()
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise InvalidRequestError("The local fake agent context is invalid.")
        source: dict[str, JsonValue]
        source_type = raw_source.get("support_source_type")
        if source_type == "attribute":
            raw_source_attribute = raw_source.get("source_attribute")
            if not isinstance(raw_source_attribute, dict):
                raise InvalidRequestError("The local fake agent context is invalid.")
            source_attribute = fake_source_attribute(raw_source_attribute)
            identity = (
                "attribute",
                *(
                    cast(str, source_attribute[name]).strip().casefold()
                    for name in (*FAKE_SOURCE_FIELDS, "attribute_name")
                ),
            )
            source = _fake_dimensional_attribute_source(
                source_attribute,
                source_order=len(sources) + 1,
            )
        elif source_type == "assertion":
            assertion = raw_source.get("assertion_record")
            key = (
                assertion.get("modeling_assertion_record_key")
                if isinstance(assertion, dict)
                else None
            )
            if (
                not isinstance(key, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,99}", key) is None
            ):
                raise InvalidRequestError("The local fake agent context is invalid.")
            identity = ("assertion", key.strip().casefold())
            source = {
                "support_source_type": "assertion",
                "assertion_record": {"modeling_assertion_record_key": key},
                "source_order": len(sources) + 1,
                "rationale": "Governed Assertion metadata supports this candidate.",
                "status": "active",
                "is_locked": False,
            }
        else:
            raise InvalidRequestError("The local fake agent context is invalid.")
        if identity in identities:
            raise InvalidRequestError("The local fake agent context is invalid.")
        identities.add(identity)
        sources.append(source)
    return sources
