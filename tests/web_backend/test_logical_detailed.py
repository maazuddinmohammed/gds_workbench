from __future__ import annotations

import json
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    LogicalAttributeRecord,
    LogicalEntityRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.tools.snapshots.model.contracts import LogicalSection
from pydantic import JsonValue

from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator
from gds_workbench_api.features.logical.detailed import (
    DetailedLogicalEntityDetail,
    DetailedLogicalEntityDetailValidator,
    DetailedLogicalReconciliationValidator,
    DetailedLogicalTopologyContributionValidator,
    DetailedLogicalTopologyReconciliation,
    DetailedLogicalTopologyReconciliationValidator,
    DetailedLogicalValidationLeadValidator,
    DetailedLogicalValidationWorkerResult,
    DetailedLogicalValidationWorkerValidator,
    build_logical_relationship_signal_ledger,
    build_logical_validation_packages,
    decide_logical_detailed_handoff,
    load_default_detailed_logical_policy,
    logical_applied_record_refs,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
)


def _object(name: str) -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=name,
    )


def _attribute(object_name: str, name: str) -> PhysicalAttributeKey:
    return PhysicalAttributeKey(
        **_object(object_name).model_dump(),
        attribute_name=name,
    )


def _entity(
    name: str,
    source_object: PhysicalObjectKey,
    *submodels: str,
) -> dict[str, JsonValue]:
    return {
        "logical_entity_name": name,
        "logical_entity_definition": f"One governed {name}.",
        "logical_entity_type": "core",
        "logical_entity_type_detail": None,
        "logical_entity_grain": f"One row per {name}.",
        "logical_entity_dependency_order": 0,
        "logical_entity_confidence": "high",
        "logical_entity_status": "active",
        "logical_entity_is_locked": False,
        "submodels": [
            {
                "submodel_name": submodel,
                "membership_status": "active",
                "membership_is_locked": False,
            }
            for submodel in submodels
        ],
        "sources": [
            {
                "support_source_type": "object",
                "source_object": source_object.model_dump(mode="json"),
                "source_order": 1,
                "rationale": "Selected Bronze Object evidence.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def _logical_attribute(
    entity_name: str,
    name: str,
    source_attribute: PhysicalAttributeKey,
    *,
    ordinal: int,
) -> dict[str, JsonValue]:
    return {
        "logical_entity_name": entity_name,
        "logical_attribute_name": name,
        "logical_attribute_definition": f"Governed {name}.",
        "logical_attribute_data_type": "bigint",
        "logical_attribute_is_nullable": False,
        "logical_attribute_is_primary_key": ordinal == 1,
        "logical_attribute_is_natural_key": ordinal == 1,
        "logical_attribute_is_surrogate_key": False,
        "logical_attribute_ordinal_position": ordinal,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_status": "active",
        "logical_attribute_is_locked": False,
        "sources": [
            {
                "support_source_type": "attribute",
                "source_attribute": source_attribute.model_dump(mode="json"),
                "source_order": 1,
                "rationale": "Selected Bronze Attribute evidence.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def _submodel(name: str) -> dict[str, JsonValue]:
    return {
        "logical_submodel_name": name,
        "logical_submodel_definition": f"The {name} boundary.",
        "logical_submodel_status": "active",
        "logical_submodel_is_locked": False,
    }


def _contribution(
    *,
    contribution_ref: str,
    source_object: PhysicalObjectKey,
    source_attributes: tuple[PhysicalAttributeKey, ...],
    local_entity_ref: str,
    entity_name: str,
    submodel_names: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "contribution_ref": contribution_ref,
        "source_object": source_object.model_dump(mode="json"),
        "disposition": "represented",
        "rationale": "The selected Object contributes one Logical Entity.",
        "proposals": [
            {
                "local_entity_ref": local_entity_ref,
                "candidate_entity_name": entity_name,
                "candidate_entity_type": "core",
                "candidate_entity_grain": f"One row per {entity_name}.",
                "candidate_submodel_names": list(submodel_names),
                "source_attributes": [item.model_dump(mode="json") for item in source_attributes],
            }
        ],
    }


def test_default_detailed_logical_policy_loads_from_validated_json() -> None:
    policy = load_default_detailed_logical_policy()

    assert policy.schema_version == "1.0"
    assert policy.max_relationship_signals == 50_000
    assert policy.validation_package_size == 100


async def test_topology_builder_has_exact_frozen_object_and_attribute_coverage() -> None:
    source = _object("customer_raw")
    attributes = (
        _attribute("customer_raw", "customer_id"),
        _attribute("customer_raw", "account_id"),
    )
    validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=attributes,
    )
    candidate = cast(
        JsonValue,
        _contribution(
            contribution_ref="object_00001",
            source_object=source,
            source_attributes=attributes,
            local_entity_ref="customer",
            entity_name="Customer",
            submodel_names=("Customer Domain", "Shared Party"),
        ),
    )

    assert (await validator.validate(candidate)).issues == ()
    parsed = validator.parse_validated(candidate)
    assert parsed.proposal_refs == ("object_00001.customer",)
    assert parsed.proposals[0].candidate_submodel_names == (
        "Customer Domain",
        "Shared Party",
    )

    missing = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    proposal = cast(list[dict[str, JsonValue]], missing["proposals"])[0]
    source_attributes = cast(list[JsonValue], proposal["source_attributes"])
    proposal["source_attributes"] = source_attributes[:1]
    assert (await validator.validate(cast(JsonValue, missing))).issues[0].code == (
        "detailed.topology_contribution_coverage_invalid"
    )


async def test_topology_reconciler_covers_every_proposal_and_allows_many_to_many() -> None:
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    contribution_validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=(source_attribute,),
    )
    contribution = contribution_validator.parse_validated(
        cast(
            JsonValue,
            _contribution(
                contribution_ref="object_00001",
                source_object=source,
                source_attributes=(source_attribute,),
                local_entity_ref="customer",
                entity_name="Customer",
                submodel_names=("Customer Domain", "Shared Party"),
            ),
        )
    )
    validator = DetailedLogicalTopologyReconciliationValidator(contributions=(contribution,))
    candidate = cast(
        JsonValue,
        {
            "submodels": [
                {
                    "canonical_submodel_ref": "customer_domain",
                    "submodel": _submodel("Customer Domain"),
                },
                {
                    "canonical_submodel_ref": "shared_party",
                    "submodel": _submodel("Shared Party"),
                },
            ],
            "entities": [
                {
                    "canonical_entity_ref": "customer",
                    "logical_entity_name": "Customer",
                    "contribution_refs": ["object_00001.customer"],
                    "submodel_refs": ["customer_domain", "shared_party"],
                }
            ],
            "discarded_contribution_refs": [],
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    topology = validator.parse_validated(candidate)
    assert topology.entities[0].submodel_refs == (
        "customer_domain",
        "shared_party",
    )

    incomplete = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    incomplete["discarded_contribution_refs"] = ["object_00001.customer"]
    assert (await validator.validate(cast(JsonValue, incomplete))).issues[0].code == (
        "detailed.topology_reconciliation_coverage_invalid"
    )


def _build_topology_and_detail() -> tuple[
    DetailedLogicalTopologyReconciliation,
    DetailedLogicalEntityDetail,
]:
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    contribution_validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=(source_attribute,),
    )
    contribution = contribution_validator.parse_validated(
        cast(
            JsonValue,
            _contribution(
                contribution_ref="object_00001",
                source_object=source,
                source_attributes=(source_attribute,),
                local_entity_ref="customer",
                entity_name="Customer",
                submodel_names=("Customer Domain", "Shared Party"),
            ),
        )
    )
    topology = DetailedLogicalTopologyReconciliationValidator(
        contributions=(contribution,)
    ).parse_validated(
        cast(
            JsonValue,
            {
                "submodels": [
                    {
                        "canonical_submodel_ref": "customer_domain",
                        "submodel": _submodel("Customer Domain"),
                    },
                    {
                        "canonical_submodel_ref": "shared_party",
                        "submodel": _submodel("Shared Party"),
                    },
                ],
                "entities": [
                    {
                        "canonical_entity_ref": "customer",
                        "logical_entity_name": "Customer",
                        "contribution_refs": ["object_00001.customer"],
                        "submodel_refs": ["customer_domain", "shared_party"],
                    }
                ],
                "discarded_contribution_refs": [],
            },
        )
    )
    detail_validator = DetailedLogicalEntityDetailValidator(
        entity=topology.entities[0],
        topology=topology,
        contributions=(contribution,),
    )
    detail_candidate = cast(
        JsonValue,
        {
            "canonical_entity_ref": "customer",
            "entity": _entity(
                "Customer",
                source,
                "Customer Domain",
                "Shared Party",
            ),
            "attributes": [
                _logical_attribute(
                    "Customer",
                    "Customer Id",
                    source_attribute,
                    ordinal=1,
                )
            ],
        },
    )
    detail = detail_validator.parse_validated(detail_candidate)
    return topology, detail


async def test_entity_detail_preserves_sources_and_exact_many_to_many_memberships() -> None:
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    contribution_validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=(source_attribute,),
    )
    contribution = contribution_validator.parse_validated(
        cast(
            JsonValue,
            _contribution(
                contribution_ref="object_00001",
                source_object=source,
                source_attributes=(source_attribute,),
                local_entity_ref="customer",
                entity_name="Customer",
                submodel_names=("Customer Domain", "Shared Party"),
            ),
        )
    )
    topology = _build_topology_and_detail()[0]
    validator = DetailedLogicalEntityDetailValidator(
        entity=topology.entities[0],
        topology=topology,
        contributions=(contribution,),
    )
    candidate = cast(
        JsonValue,
        {
            "canonical_entity_ref": "customer",
            "entity": _entity(
                "Customer",
                source,
                "Customer Domain",
                "Shared Party",
            ),
            "attributes": [
                _logical_attribute(
                    "Customer",
                    "Customer Id",
                    source_attribute,
                    ordinal=1,
                )
            ],
        },
    )

    assert (await validator.validate(candidate)).issues == ()

    incomplete = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    cast(dict[str, JsonValue], incomplete["entity"])["submodels"] = []
    assert (await validator.validate(cast(JsonValue, incomplete))).issues[0].code == (
        "detailed.entity_detail_coverage_invalid"
    )


def test_code_owned_relationship_signal_ledger_is_stable_bounded_and_has_no_self_pairs() -> None:
    _topology, customer = _build_topology_and_detail()
    order_source = _object("order_raw")
    order_source_attribute = _attribute("order_raw", "customer_id")
    order = DetailedLogicalEntityDetail(
        canonical_entity_ref="order",
        entity=LogicalEntityRecord.model_validate_json(
            json.dumps(_entity("Order", order_source)), strict=True
        ),
        attributes=(
            LogicalAttributeRecord.model_validate_json(
                json.dumps(
                    _logical_attribute(
                        "Order",
                        "Customer Id",
                        order_source_attribute,
                        ordinal=1,
                    )
                ),
                strict=True,
            ),
        ),
    )

    ledger = build_logical_relationship_signal_ledger(
        entity_details=(customer, order),
        max_signals=100,
    )

    assert ledger.signal_refs == ("relationship_signal_00001",)
    assert ledger.signals[0].from_entity_ref == "customer"
    assert ledger.signals[0].to_entity_ref == "order"
    assert (
        build_logical_relationship_signal_ledger(
            entity_details=(order, customer),
            max_signals=100,
        )
        == ledger
    )

    with pytest.raises(InvalidRequestError):
        build_logical_relationship_signal_ledger(
            entity_details=(customer, order),
            max_signals=0,
        )


async def test_whole_model_reconciliation_requires_exact_coverage_before_materializing() -> None:
    topology, detail = _build_topology_and_detail()
    ledger = build_logical_relationship_signal_ledger(
        entity_details=(detail,),
        max_signals=100,
    )
    final_validator = LogicalCandidateValidator(
        selected_object_keys=(_object("customer_raw"),),
        selected_attribute_keys=(_attribute("customer_raw", "customer_id"),),
        assertion_record_keys=(),
        applied=None,
    )
    validator = DetailedLogicalReconciliationValidator(
        topology=topology,
        entity_details=(detail,),
        relationship_signal_refs=ledger.signal_refs,
        applied_record_refs=(),
        final_validator=final_validator,
    )
    candidate = cast(
        JsonValue,
        {
            "submodels": [item.submodel.model_dump(mode="json") for item in topology.submodels],
            "entities": [detail.entity.model_dump(mode="json")],
            "attributes": [item.model_dump(mode="json") for item in detail.attributes],
            "relationships": [],
            "reviewed_submodel_refs": [item.canonical_submodel_ref for item in topology.submodels],
            "reviewed_entity_refs": [detail.canonical_entity_ref],
            "reviewed_relationship_signal_refs": [],
            "reviewed_applied_record_refs": [],
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    assert set(cast(dict[str, JsonValue], validator.materialize_validated(candidate))) == {
        "submodels",
        "entities",
        "attributes",
        "relationships",
    }

    incomplete = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    incomplete["reviewed_entity_refs"] = []
    assert (await validator.validate(cast(JsonValue, incomplete))).issues[0].code == (
        "detailed.reconciliation_coverage_invalid"
    )
    with pytest.raises(AgentCandidateValidationError):
        validator.materialize_validated(cast(JsonValue, incomplete))


async def test_bounded_validator_workers_and_single_lead_gate_atomic_handoff() -> None:
    topology, detail = _build_topology_and_detail()
    reconciliation = cast(
        JsonValue,
        {
            "submodels": [item.submodel.model_dump(mode="json") for item in topology.submodels],
            "entities": [detail.entity.model_dump(mode="json")],
            "attributes": [item.model_dump(mode="json") for item in detail.attributes],
            "relationships": [],
            "reviewed_submodel_refs": [item.canonical_submodel_ref for item in topology.submodels],
            "reviewed_entity_refs": [detail.canonical_entity_ref],
            "reviewed_relationship_signal_refs": [],
            "reviewed_applied_record_refs": [],
        },
    )
    reconciliation_validator = DetailedLogicalReconciliationValidator(
        topology=topology,
        entity_details=(detail,),
        relationship_signal_refs=(),
        applied_record_refs=(),
    )
    parsed = reconciliation_validator.parse_validated(reconciliation)
    packages = build_logical_validation_packages(
        candidate=parsed,
        package_size=2,
        max_packages=10,
    )

    assert len(packages) == 2
    assert all(len(package.records) <= 2 for package in packages)

    worker_results: list[DetailedLogicalValidationWorkerResult] = []
    for package in packages:
        worker_validator = DetailedLogicalValidationWorkerValidator(package=package)
        finding = (
            [
                {
                    "finding_ref": f"{package.package_ref}.finding_00001",
                    "severity": "error",
                    "code": "logical.review_required",
                    "message": "A worker found one blocking model concern.",
                    "record_refs": [package.record_refs[0]],
                }
            ]
            if package == packages[0]
            else []
        )
        worker_candidate = cast(
            JsonValue,
            {
                "package_ref": package.package_ref,
                "reviewed_record_refs": list(package.record_refs),
                "findings": finding,
            },
        )
        assert (await worker_validator.validate(worker_candidate)).issues == ()
        worker_results.append(worker_validator.parse_validated(worker_candidate))

    lead_validator = DetailedLogicalValidationLeadValidator(worker_results=tuple(worker_results))
    finding_ref = worker_results[0].findings[0].finding_ref
    lead_candidate = cast(
        JsonValue,
        {
            "reviewed_package_refs": [package.package_ref for package in packages],
            "reviewed_finding_refs": [finding_ref],
            "blocking_finding_refs": [finding_ref],
            "repair_brief": "Repair the blocking validation concern in the whole model.",
        },
    )
    assert (await lead_validator.validate(lead_candidate)).issues == ()
    lead = lead_validator.parse_validated(lead_candidate)

    decision = decide_logical_detailed_handoff(
        reconciliation_validator=reconciliation_validator,
        reconciliation_candidate=reconciliation,
        validation_lead=lead,
        worker_results=tuple(worker_results),
    )

    assert decision.next_stage == "whole_model_reconciliation"
    assert decision.handoff_candidate is None
    assert decision.validation_failures == worker_results[0].findings

    clean_results = tuple(item.model_copy(update={"findings": ()}) for item in worker_results)
    clean_lead_validator = DetailedLogicalValidationLeadValidator(worker_results=clean_results)
    clean_lead = clean_lead_validator.parse_validated(
        cast(
            JsonValue,
            {
                "reviewed_package_refs": [package.package_ref for package in packages],
                "reviewed_finding_refs": [],
                "blocking_finding_refs": [],
                "repair_brief": None,
            },
        )
    )
    clean_decision = decide_logical_detailed_handoff(
        reconciliation_validator=reconciliation_validator,
        reconciliation_candidate=reconciliation,
        validation_lead=clean_lead,
        worker_results=clean_results,
    )
    assert clean_decision.next_stage == "handoff"
    assert clean_decision.handoff_candidate is not None


def test_applied_record_refs_are_complete_and_stable() -> None:
    topology, detail = _build_topology_and_detail()
    applied = LogicalSection(
        submodels=tuple(item.submodel for item in topology.submodels),
        entities=(detail.entity,),
        attributes=detail.attributes,
        relationships=(),
    )
    refs = logical_applied_record_refs(applied)

    assert refs == tuple(sorted(refs))
    assert len(refs) == 4
    assert any(ref.startswith("entity:") for ref in refs)
