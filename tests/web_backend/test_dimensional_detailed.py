from __future__ import annotations

import json
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AttributePhysicalSourceRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.snapshots.model.contracts import DimensionalSection
from pydantic import JsonValue, ValidationError

from gds_workbench_api.features.dimensional.candidate import (
    DimensionalCandidateValidator,
)
from gds_workbench_api.features.dimensional.detailed import (
    DetailedDimensionalEntityDetail,
    DetailedDimensionalEntityDetailValidator,
    DetailedDimensionalReconciliationValidator,
    DetailedDimensionalTopologyContribution,
    DetailedDimensionalTopologyContributionValidator,
    DetailedDimensionalTopologyReconciliation,
    DetailedDimensionalTopologyReconciliationValidator,
    DetailedDimensionalValidationLeadValidator,
    DetailedDimensionalValidationWorkerResult,
    DetailedDimensionalValidationWorkerValidator,
    build_dimensional_relationship_signal_ledger,
    build_dimensional_validation_packages,
    build_projected_dimensional_validation_packages,
    decide_dimensional_detailed_handoff,
    dimensional_applied_record_refs,
    load_default_detailed_dimensional_policy,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
)


def _object(name: str) -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="CURATED",
        object_schema="silver",
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
        "dimensional_entity_name": name,
        "dimensional_entity_definition": f"One governed {name}.",
        "dimensional_entity_type": "dimension",
        "dimensional_fact_type": None,
        "dimensional_entity_grain_definition": None,
        "dimensional_entity_dependency_order": 0,
        "dimensional_entity_confidence": "high",
        "dimensional_entity_status": "active",
        "dimensional_entity_is_locked": False,
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
                "rationale": "Selected eligible Silver Object contribution.",
                "status": "active",
                "is_locked": False,
                "source_role": "primary",
            }
        ],
    }


def _dimensional_attribute(
    entity_name: str,
    name: str,
    source_attribute: PhysicalAttributeKey,
    *,
    ordinal: int,
) -> dict[str, JsonValue]:
    return {
        "dimensional_entity_name": entity_name,
        "dimensional_attribute_name": name,
        "dimensional_attribute_definition": f"Governed {name}.",
        "dimensional_attribute_data_type": "bigint",
        "dimensional_attribute_is_nullable": False,
        "dimensional_attribute_ordinal_position": ordinal,
        "dimensional_attribute_role": "key",
        "dimensional_attribute_key_role": "business",
        "dimensional_attribute_is_grain_component": True,
        "dimensional_attribute_additivity": None,
        "dimensional_attribute_default_aggregation": None,
        "dimensional_attribute_aggregation_basis": None,
        "dimensional_attribute_change_behavior": "fixed",
        "dimensional_attribute_is_audit_column": False,
        "dimensional_attribute_confidence": "high",
        "dimensional_attribute_status": "active",
        "dimensional_attribute_is_locked": False,
        "sources": [
            {
                "support_source_type": "attribute",
                "source_attribute": source_attribute.model_dump(mode="json"),
                "source_order": 1,
                "rationale": "Selected eligible Silver Attribute contribution.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def _submodel(name: str) -> dict[str, JsonValue]:
    return {
        "dimensional_submodel_name": name,
        "dimensional_submodel_definition": f"The {name} boundary.",
        "dimensional_submodel_status": "active",
        "dimensional_submodel_is_locked": False,
    }


def _relationship(*, optional: bool) -> dict[str, JsonValue]:
    return {
        "dimensional_relationship_name": "Customer alternate key",
        "dimensional_relationship_definition": "Relates two governed business keys.",
        "from_dimensional_entity_name": "Customer",
        "from_dimensional_attribute_name": "Customer Id",
        "to_dimensional_entity_name": "Customer",
        "to_dimensional_attribute_name": "Customer Code",
        "dimensional_relationship_kind": "business_key",
        "dimensional_relationship_cardinality": "one_to_one",
        "dimensional_relationship_is_optional": optional,
        "dimensional_relationship_role_name": None,
        "dimensional_relationship_confidence": "high",
        "dimensional_relationship_basis": "The Silver contribution contains both keys.",
        "dimensional_relationship_cardinality_basis": "Each key identifies one customer.",
        "dimensional_relationship_status": "active",
        "dimensional_relationship_is_locked": False,
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
        "rationale": "The selected Object contributes one Dimensional Entity.",
        "proposals": [
            {
                "local_entity_ref": local_entity_ref,
                "candidate_entity_name": entity_name,
                "candidate_entity_type": "dimension",
                "candidate_fact_type": None,
                "candidate_entity_grain_definition": None,
                "candidate_submodel_names": list(submodel_names),
                "source_attributes": [
                    item.model_dump(mode="json") for item in source_attributes
                ],
            }
        ],
    }


def test_default_detailed_dimensional_policy_loads_from_validated_json() -> None:
    policy = load_default_detailed_dimensional_policy()

    assert policy.schema_version == "1.0"
    assert policy.max_relationship_signals == 50_000
    assert policy.validation_package_size == 100


async def test_topology_builder_has_exact_frozen_object_and_attribute_coverage() -> (
    None
):
    source = _object("customer_raw")
    attributes = (
        _attribute("customer_raw", "customer_id"),
        _attribute("customer_raw", "account_id"),
    )
    validator = DetailedDimensionalTopologyContributionValidator(
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

    assert parsed.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        parsed.rationale = "Changed after context freeze."


async def test_topology_builder_enforces_dimensional_role_and_grain_contract() -> None:
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    validator = DetailedDimensionalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=(source_attribute,),
    )
    candidate = _contribution(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=(source_attribute,),
        local_entity_ref="customer",
        entity_name="Customer",
        submodel_names=("Customer Domain",),
    )
    proposal = cast(list[dict[str, JsonValue]], candidate["proposals"])[0]

    proposal["candidate_entity_type"] = "fact"
    proposal["candidate_entity_grain_definition"] = "One row per customer event."
    assert (await validator.validate(cast(JsonValue, candidate))).issues[0].code == (
        "detailed.topology_contribution_invalid"
    )

    proposal["candidate_fact_type"] = "transaction"
    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()

    proposal["candidate_entity_type"] = "bridge"
    proposal["candidate_fact_type"] = None
    proposal["candidate_entity_grain_definition"] = None
    assert (await validator.validate(cast(JsonValue, candidate))).issues[0].code == (
        "detailed.topology_contribution_invalid"
    )


async def test_terminal_topology_disposition_covers_the_whole_frozen_object() -> None:
    source = _object("customer_raw")
    source_attributes = (
        _attribute("customer_raw", "customer_id"),
        _attribute("customer_raw", "customer_name"),
    )
    validator = DetailedDimensionalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source,
        source_attributes=source_attributes,
    )
    terminal = cast(
        JsonValue,
        {
            "contribution_ref": "object_00001",
            "source_object": source.model_dump(mode="json"),
            "disposition": "not_dimensional",
            "rationale": "The complete Silver Object is not an analytical contribution.",
            "proposals": [],
        },
    )

    for disposition in ("not_dimensional", "needs_review"):
        terminal_for_disposition = cast(
            dict[str, JsonValue], json.loads(json.dumps(terminal))
        )
        terminal_for_disposition["disposition"] = disposition
        assert (
            await validator.validate(cast(JsonValue, terminal_for_disposition))
        ).issues == ()
        validator.parse_validated(cast(JsonValue, terminal_for_disposition))

    contribution = validator.parse_validated(terminal)
    topology_validator = DetailedDimensionalTopologyReconciliationValidator(
        contributions=(contribution,)
    )
    empty_topology = cast(
        JsonValue,
        {"submodels": [], "entities": [], "discarded_contribution_refs": []},
    )
    assert (await topology_validator.validate(empty_topology)).issues == ()

    partial = cast(dict[str, JsonValue], json.loads(json.dumps(terminal)))
    partial["proposals"] = cast(
        JsonValue,
        [
            {
                "local_entity_ref": "customer",
                "candidate_entity_name": "Customer",
                "candidate_entity_type": "dimension",
                "candidate_fact_type": None,
                "candidate_entity_grain_definition": None,
                "candidate_submodel_names": [],
                "source_attributes": [source_attributes[0].model_dump(mode="json")],
            }
        ],
    )
    assert (await validator.validate(cast(JsonValue, partial))).issues[0].code == (
        "detailed.topology_contribution_invalid"
    )


async def test_topology_reconciler_covers_every_proposal_and_allows_many_to_many() -> (
    None
):
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    contribution_validator = DetailedDimensionalTopologyContributionValidator(
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
    validator = DetailedDimensionalTopologyReconciliationValidator(
        contributions=(contribution,)
    )
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
                    "dimensional_entity_name": "Customer",
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
    DetailedDimensionalTopologyReconciliation,
    DetailedDimensionalEntityDetail,
    DetailedDimensionalTopologyContribution,
]:
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    contribution_validator = DetailedDimensionalTopologyContributionValidator(
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
    topology = DetailedDimensionalTopologyReconciliationValidator(
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
                        "dimensional_entity_name": "Customer",
                        "contribution_refs": ["object_00001.customer"],
                        "submodel_refs": ["customer_domain", "shared_party"],
                    }
                ],
                "discarded_contribution_refs": [],
            },
        )
    )
    detail_validator = DetailedDimensionalEntityDetailValidator(
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
                _dimensional_attribute(
                    "Customer",
                    "Customer Id",
                    source_attribute,
                    ordinal=1,
                )
            ],
        },
    )
    detail = detail_validator.parse_validated(detail_candidate)
    return topology, detail, contribution


def test_reconciliation_context_requires_each_topology_entity_detail_exactly_once() -> (
    None
):
    topology, detail, _contribution_record = _build_topology_and_detail()

    with pytest.raises(ValueError, match="exactly match"):
        DetailedDimensionalReconciliationValidator(
            topology=topology,
            entity_details=(),
            relationship_signal_refs=(),
            applied_record_refs=(),
        )
    with pytest.raises(ValueError, match="unique"):
        DetailedDimensionalReconciliationValidator(
            topology=topology,
            entity_details=(detail, detail),
            relationship_signal_refs=(),
            applied_record_refs=(),
        )

    extra = detail.model_copy(
        update={
            "canonical_entity_ref": "extra",
            "entity": detail.entity.model_copy(
                update={"dimensional_entity_name": "Extra"}
            ),
        }
    )
    with pytest.raises(ValueError, match="exactly match"):
        DetailedDimensionalReconciliationValidator(
            topology=topology,
            entity_details=(detail, extra),
            relationship_signal_refs=(),
            applied_record_refs=(),
        )

    renamed = detail.model_copy(
        update={
            "entity": detail.entity.model_copy(
                update={"dimensional_entity_name": "Renamed Customer"}
            )
        }
    )
    with pytest.raises(ValueError, match="exactly match"):
        DetailedDimensionalReconciliationValidator(
            topology=topology,
            entity_details=(renamed,),
            relationship_signal_refs=(),
            applied_record_refs=(),
        )

    oversized = detail.model_copy(update={"attributes": detail.attributes * 20_000})
    with pytest.raises(ValueError, match="too large"):
        DetailedDimensionalReconciliationValidator(
            topology=topology,
            entity_details=(oversized,),
            relationship_signal_refs=(),
            applied_record_refs=(),
        )


async def test_entity_detail_preserves_sources_and_exact_many_to_many_memberships() -> (
    None
):
    source = _object("customer_raw")
    source_attribute = _attribute("customer_raw", "customer_id")
    contribution_validator = DetailedDimensionalTopologyContributionValidator(
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
    validator = DetailedDimensionalEntityDetailValidator(
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
                _dimensional_attribute(
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

    missing_attribute = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    cast(list[dict[str, JsonValue]], missing_attribute["attributes"])[0]["sources"] = []
    assert (await validator.validate(cast(JsonValue, missing_attribute))).issues[
        0
    ].code == ("detailed.entity_detail_coverage_invalid")

    wrong_shape = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    wrong_entity = cast(dict[str, JsonValue], wrong_shape["entity"])
    wrong_entity["dimensional_entity_type"] = "bridge"
    wrong_entity["dimensional_entity_grain_definition"] = (
        "One row per customer bridge member."
    )
    assert (await validator.validate(cast(JsonValue, wrong_shape))).issues[0].code == (
        "detailed.entity_detail_coverage_invalid"
    )


async def test_detailed_agent_output_is_lockless_and_excludes_code_owned_attributes() -> (
    None
):
    topology, detail, contribution = _build_topology_and_detail()
    validator = DetailedDimensionalEntityDetailValidator(
        entity=topology.entities[0],
        topology=topology,
        contributions=(contribution,),
    )
    schema = validator.output_schema()
    attribute_properties = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], schema["$defs"])["DimensionalAttributeRecord"],
    )["properties"]
    properties = cast(dict[str, JsonValue], attribute_properties)

    assert (
        cast(dict[str, JsonValue], properties["dimensional_attribute_is_locked"])[
            "const"
        ]
        is False
    )
    assert (
        cast(dict[str, JsonValue], properties["dimensional_attribute_is_audit_column"])[
            "const"
        ]
        is False
    )
    assert cast(dict[str, JsonValue], properties["dimensional_attribute_key_role"])[
        "enum"
    ] == [
        "none",
        "business",
    ]

    base = cast(dict[str, JsonValue], detail.model_dump(mode="json"))
    locked = cast(dict[str, JsonValue], json.loads(json.dumps(base)))
    cast(dict[str, JsonValue], locked["entity"])["dimensional_entity_is_locked"] = True
    assert (await validator.validate(cast(JsonValue, locked))).issues[0].code == (
        "detailed.entity_detail_coverage_invalid"
    )

    for role, key_role, audit in (
        ("technical", "none", False),
        ("audit", "none", True),
        ("key", "surrogate", False),
        ("key", "foreign", False),
    ):
        policy_owned = cast(dict[str, JsonValue], json.loads(json.dumps(base)))
        attribute = cast(list[dict[str, JsonValue]], policy_owned["attributes"])[0]
        attribute["dimensional_attribute_role"] = role
        attribute["dimensional_attribute_key_role"] = key_role
        attribute["dimensional_attribute_is_audit_column"] = audit
        assert (await validator.validate(cast(JsonValue, policy_owned))).issues[
            0
        ].code == ("detailed.entity_detail_coverage_invalid")


async def test_entity_detail_allows_only_owned_and_sourced_extra_attributes() -> None:
    topology, detail, contribution = _build_topology_and_detail()
    default_validator = DetailedDimensionalEntityDetailValidator(
        entity=topology.entities[0],
        topology=topology,
        contributions=(contribution,),
    )
    base = cast(dict[str, JsonValue], detail.model_dump(mode="json"))
    extra = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(detail.attributes[0].model_dump(mode="json"))),
    )
    extra.update(
        {
            "dimensional_attribute_name": "Customer Segment",
            "dimensional_attribute_ordinal_position": 2,
            "dimensional_attribute_role": "descriptor",
            "dimensional_attribute_key_role": "none",
            "dimensional_attribute_is_grain_component": False,
            "sources": [],
        }
    )
    source_less = cast(dict[str, JsonValue], json.loads(json.dumps(base)))
    cast(list[JsonValue], source_less["attributes"]).append(cast(JsonValue, extra))
    assert (await default_validator.validate(cast(JsonValue, source_less))).issues[
        0
    ].code == ("detailed.entity_detail_coverage_invalid")

    extra["sources"] = cast(
        JsonValue,
        [
            {
                "support_source_type": "assertion",
                "assertion_record": {
                    "modeling_assertion_record_key": "assertion.customer_segment"
                },
                "source_order": 1,
                "rationale": "Governed customer segmentation assertion.",
                "status": "active",
                "is_locked": False,
            }
        ],
    )
    assertion_backed = cast(dict[str, JsonValue], json.loads(json.dumps(base)))
    cast(list[JsonValue], assertion_backed["attributes"]).append(cast(JsonValue, extra))
    assert (await default_validator.validate(cast(JsonValue, assertion_backed))).issues[
        0
    ].code == "detailed.entity_detail_coverage_invalid"

    owned_validator = DetailedDimensionalEntityDetailValidator(
        entity=topology.entities[0],
        topology=topology,
        contributions=(contribution,),
        assertion_record_keys=("assertion.customer_segment",),
    )
    assert (
        await owned_validator.validate(cast(JsonValue, assertion_backed))
    ).issues == ()


def test_code_owned_relationship_signal_ledger_is_stable_bounded_and_has_no_self_pairs() -> (
    None
):
    _topology, customer, _contribution_record = _build_topology_and_detail()
    order_source = _object("order_raw")
    order_source_attribute = _attribute("order_raw", "customer_id")
    order = DetailedDimensionalEntityDetail(
        canonical_entity_ref="order",
        entity=DimensionalEntityRecord.model_validate_json(
            json.dumps(_entity("Order", order_source)), strict=True
        ),
        attributes=(
            DimensionalAttributeRecord.model_validate_json(
                json.dumps(
                    _dimensional_attribute(
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

    ledger = build_dimensional_relationship_signal_ledger(
        entity_details=(customer, order),
        max_signals=100,
    )

    assert ledger.signal_refs == ("relationship_signal_00001",)
    assert ledger.signals[0].from_entity_ref == "customer"
    assert ledger.signals[0].to_entity_ref == "order"
    assert (
        build_dimensional_relationship_signal_ledger(
            entity_details=(order, customer),
            max_signals=100,
        )
        == ledger
    )

    invoice = order.model_copy(
        update={
            "canonical_entity_ref": "invoice",
            "entity": order.entity.model_copy(
                update={"dimensional_entity_name": "Invoice"}
            ),
            "attributes": (
                order.attributes[0].model_copy(
                    update={"dimensional_entity_name": "Invoice"}
                ),
            ),
        }
    )
    with pytest.raises(InvalidRequestError):
        build_dimensional_relationship_signal_ledger(
            entity_details=(customer, order, invoice),
            max_signals=1,
        )

    customer_source = cast(
        AttributePhysicalSourceRecord, customer.attributes[0].sources[0]
    )
    order_source_record = cast(
        AttributePhysicalSourceRecord, order.attributes[0].sources[0]
    )
    wide_customer = customer.model_copy(
        update={
            "attributes": (
                customer.attributes[0].model_copy(
                    update={
                        "sources": tuple(
                            customer_source.model_copy(
                                update={
                                    "source_attribute": _attribute(
                                        "customer_raw", f"customer_key_{position:04d}"
                                    )
                                }
                            )
                            for position in range(1_001)
                        )
                    }
                ),
            )
        }
    )
    wide_order = order.model_copy(
        update={
            "attributes": (
                order.attributes[0].model_copy(
                    update={
                        "sources": tuple(
                            order_source_record.model_copy(
                                update={
                                    "source_attribute": _attribute(
                                        "order_raw", f"order_key_{position:04d}"
                                    )
                                }
                            )
                            for position in range(1_001)
                        )
                    }
                ),
            )
        }
    )
    wide_ledger = build_dimensional_relationship_signal_ledger(
        entity_details=(wide_customer, wide_order),
        max_signals=1,
    )
    assert len(wide_ledger.signals[0].from_source_attributes) == 1_001

    with pytest.raises(InvalidRequestError):
        build_dimensional_relationship_signal_ledger(
            entity_details=(customer, order),
            max_signals=0,
        )


async def test_whole_model_reconciliation_requires_exact_coverage_before_materializing() -> (
    None
):
    topology, detail, _contribution_record = _build_topology_and_detail()
    relationship_signal_refs = ("relationship_signal_00001",)
    applied_record_refs = ("entity:applied_dimension",)
    final_validator = DimensionalCandidateValidator(
        selected_object_keys=(_object("customer_raw"),),
        selected_attribute_keys=(_attribute("customer_raw", "customer_id"),),
        assertion_record_keys=(),
        applied=None,
    )
    validator = DetailedDimensionalReconciliationValidator(
        topology=topology,
        entity_details=(detail,),
        relationship_signal_refs=relationship_signal_refs,
        applied_record_refs=applied_record_refs,
        final_validator=final_validator,
    )
    candidate = cast(
        JsonValue,
        {
            "submodels": [
                item.submodel.model_dump(mode="json") for item in topology.submodels
            ],
            "entities": [detail.entity.model_dump(mode="json")],
            "attributes": [item.model_dump(mode="json") for item in detail.attributes],
            "relationships": [],
            "reviewed_submodel_refs": [
                item.canonical_submodel_ref for item in topology.submodels
            ],
            "reviewed_entity_refs": [detail.canonical_entity_ref],
            "reviewed_relationship_signal_refs": list(relationship_signal_refs),
            "reviewed_applied_record_refs": list(applied_record_refs),
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    assert set(
        cast(dict[str, JsonValue], validator.materialize_validated(candidate))
    ) == {
        "submodels",
        "entities",
        "attributes",
        "relationships",
    }

    lost_sources = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    cast(list[dict[str, JsonValue]], lost_sources["entities"])[0]["sources"] = []
    cast(list[dict[str, JsonValue]], lost_sources["attributes"])[0]["sources"] = []
    assert (await validator.validate(cast(JsonValue, lost_sources))).issues[0].code == (
        "detailed.reconciliation_coverage_invalid"
    )

    missing_topology_entity = cast(
        dict[str, JsonValue], json.loads(json.dumps(candidate))
    )
    missing_topology_entity["entities"] = []
    assert (await validator.validate(cast(JsonValue, missing_topology_entity))).issues[
        0
    ].code == "detailed.reconciliation_coverage_invalid"

    arbitrary = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    extra_entity = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(detail.entity.model_dump(mode="json"))),
    )
    extra_entity["dimensional_entity_name"] = "Arbitrary Dimension"
    extra_attribute = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(detail.attributes[0].model_dump(mode="json"))),
    )
    extra_attribute["dimensional_entity_name"] = "Arbitrary Dimension"
    cast(list[JsonValue], arbitrary["entities"]).append(cast(JsonValue, extra_entity))
    cast(list[JsonValue], arbitrary["attributes"]).append(
        cast(JsonValue, extra_attribute)
    )
    assert (await validator.validate(cast(JsonValue, arbitrary))).issues[0].code == (
        "detailed.reconciliation_coverage_invalid"
    )

    for ledger_name in (
        "reviewed_submodel_refs",
        "reviewed_entity_refs",
        "reviewed_relationship_signal_refs",
        "reviewed_applied_record_refs",
    ):
        incomplete = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
        incomplete[ledger_name] = []
        assert (await validator.validate(cast(JsonValue, incomplete))).issues[
            0
        ].code == ("detailed.reconciliation_coverage_invalid")

    incomplete = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    incomplete["reviewed_entity_refs"] = cast(
        JsonValue, [detail.canonical_entity_ref] * 2
    )
    with pytest.raises(AgentCandidateValidationError):
        validator.materialize_validated(cast(JsonValue, incomplete))


async def test_reconciliation_uses_canonical_required_relationship_optionality() -> (
    None
):
    topology, detail, _contribution_record = _build_topology_and_detail()
    customer_code = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(detail.attributes[0].model_dump(mode="json"))),
    )
    customer_code.update(
        {
            "dimensional_attribute_name": "Customer Code",
            "dimensional_attribute_ordinal_position": 2,
            "dimensional_attribute_role": "descriptor",
            "dimensional_attribute_key_role": "none",
            "dimensional_attribute_is_grain_component": False,
            "sources": [],
        }
    )
    customer_code_record = DimensionalAttributeRecord.model_validate_json(
        json.dumps(customer_code),
        strict=True,
    )
    applied = DimensionalSection(
        submodels=(),
        entities=(),
        attributes=(customer_code_record,),
        relationships=(),
    )
    applied_record_refs = dimensional_applied_record_refs(applied)
    validator = DetailedDimensionalReconciliationValidator(
        topology=topology,
        entity_details=(detail,),
        relationship_signal_refs=(),
        applied_record_refs=applied_record_refs,
        final_validator=DimensionalCandidateValidator(
            selected_object_keys=(_object("customer_raw"),),
            selected_attribute_keys=(_attribute("customer_raw", "customer_id"),),
            assertion_record_keys=(),
            applied=applied,
        ),
    )
    candidate = cast(
        JsonValue,
        {
            "submodels": [
                item.submodel.model_dump(mode="json") for item in topology.submodels
            ],
            "entities": [detail.entity.model_dump(mode="json")],
            "attributes": [
                *[item.model_dump(mode="json") for item in detail.attributes],
                customer_code,
            ],
            "relationships": [_relationship(optional=True)],
            "reviewed_submodel_refs": [
                item.canonical_submodel_ref for item in topology.submodels
            ],
            "reviewed_entity_refs": [detail.canonical_entity_ref],
            "reviewed_relationship_signal_refs": [],
            "reviewed_applied_record_refs": list(applied_record_refs),
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    materialized = cast(
        dict[str, JsonValue], validator.materialize_validated(candidate)
    )
    relationship = cast(list[dict[str, JsonValue]], materialized["relationships"])[0]
    assert relationship["dimensional_relationship_is_optional"] is True

    conflicting = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    cast(list[JsonValue], conflicting["relationships"]).append(
        cast(JsonValue, _relationship(optional=False))
    )
    assert (await validator.validate(cast(JsonValue, conflicting))).issues[0].code == (
        "detailed.reconciliation_coverage_invalid"
    )
    with pytest.raises(AgentCandidateValidationError):
        validator.materialize_validated(cast(JsonValue, conflicting))

    missing_optionality = cast(dict[str, JsonValue], json.loads(json.dumps(candidate)))
    cast(list[dict[str, JsonValue]], missing_optionality["relationships"])[0].pop(
        "dimensional_relationship_is_optional"
    )
    assert (await validator.validate(cast(JsonValue, missing_optionality))).issues[
        0
    ].code == ("detailed.reconciliation_invalid")


async def test_bounded_validator_workers_and_single_lead_gate_atomic_handoff() -> None:
    topology, detail, _contribution_record = _build_topology_and_detail()
    reconciliation = cast(
        JsonValue,
        {
            "submodels": [
                item.submodel.model_dump(mode="json") for item in topology.submodels
            ],
            "entities": [detail.entity.model_dump(mode="json")],
            "attributes": [item.model_dump(mode="json") for item in detail.attributes],
            "relationships": [],
            "reviewed_submodel_refs": [
                item.canonical_submodel_ref for item in topology.submodels
            ],
            "reviewed_entity_refs": [detail.canonical_entity_ref],
            "reviewed_relationship_signal_refs": [],
            "reviewed_applied_record_refs": [],
        },
    )
    reconciliation_validator = DetailedDimensionalReconciliationValidator(
        topology=topology,
        entity_details=(detail,),
        relationship_signal_refs=(),
        applied_record_refs=(),
    )
    parsed = reconciliation_validator.parse_validated(reconciliation)
    packages = build_dimensional_validation_packages(
        candidate=parsed,
        package_size=2,
        max_packages=10,
    )

    assert len(packages) == 2
    assert all(len(package.records) <= 2 for package in packages)
    reordered = parsed.model_copy(
        update={
            "submodels": tuple(reversed(parsed.submodels)),
            "entities": tuple(reversed(parsed.entities)),
            "attributes": tuple(reversed(parsed.attributes)),
            "relationships": tuple(reversed(parsed.relationships)),
        }
    )
    assert (
        build_dimensional_validation_packages(
            candidate=reordered,
            package_size=2,
            max_packages=10,
        )
        == packages
    )
    with pytest.raises(InvalidRequestError):
        build_dimensional_validation_packages(
            candidate=parsed,
            package_size=2,
            max_packages=1,
        )

    worker_results: list[DetailedDimensionalValidationWorkerResult] = []
    for package in packages:
        worker_validator = DetailedDimensionalValidationWorkerValidator(package=package)
        finding = (
            [
                {
                    "finding_ref": f"{package.package_ref}.finding_00001",
                    "severity": "error",
                    "code": "dimensional.review_required",
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
        if package == packages[0]:
            incomplete_worker = cast(
                dict[str, JsonValue], json.loads(json.dumps(worker_candidate))
            )
            incomplete_worker["reviewed_record_refs"] = [package.record_refs[0]]
            assert (
                await worker_validator.validate(cast(JsonValue, incomplete_worker))
            ).issues[0].code == "detailed.validation_worker_coverage_invalid"
        worker_results.append(worker_validator.parse_validated(worker_candidate))

    lead_validator = DetailedDimensionalValidationLeadValidator(
        worker_results=tuple(worker_results)
    )
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
    incomplete_lead = cast(dict[str, JsonValue], json.loads(json.dumps(lead_candidate)))
    incomplete_lead["reviewed_finding_refs"] = []
    assert (await lead_validator.validate(cast(JsonValue, incomplete_lead))).issues[
        0
    ].code == ("detailed.validation_lead_coverage_invalid")

    decision = decide_dimensional_detailed_handoff(
        reconciliation_validator=reconciliation_validator,
        reconciliation_candidate=reconciliation,
        validation_lead=lead,
        worker_results=tuple(worker_results),
    )

    assert decision.next_stage == "whole_model_reconciliation"
    assert decision.handoff_candidate is None
    assert decision.validation_failures == worker_results[0].findings

    clean_results = tuple(
        item.model_copy(update={"findings": ()}) for item in worker_results
    )
    clean_lead_validator = DetailedDimensionalValidationLeadValidator(
        worker_results=clean_results
    )
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
    clean_decision = decide_dimensional_detailed_handoff(
        reconciliation_validator=reconciliation_validator,
        reconciliation_candidate=reconciliation,
        validation_lead=clean_lead,
        worker_results=clean_results,
    )
    assert clean_decision.next_stage == "handoff"
    assert clean_decision.handoff_candidate is not None


def test_projected_validation_packages_include_code_owned_rows_and_relationships() -> (
    None
):
    source_attribute = _attribute("customer_raw", "customer_id")
    technical = _dimensional_attribute(
        "Customer",
        "Customer key",
        source_attribute,
        ordinal=2,
    )
    technical.update(
        {
            "dimensional_attribute_role": "technical",
            "dimensional_attribute_key_role": "surrogate",
            "sources": [],
        }
    )
    audit = _dimensional_attribute(
        "Customer",
        "Loaded At",
        source_attribute,
        ordinal=3,
    )
    audit.update(
        {
            "dimensional_attribute_role": "audit",
            "dimensional_attribute_key_role": "none",
            "dimensional_attribute_is_grain_component": False,
            "dimensional_attribute_is_audit_column": True,
            "sources": [],
        }
    )
    rewritten_relationship = _relationship(optional=True)
    rewritten_relationship.update(
        {
            "from_dimensional_entity_name": "Sales Fact",
            "from_dimensional_attribute_name": "Customer key",
            "to_dimensional_attribute_name": "Customer key",
            "dimensional_relationship_kind": "dimension_reference",
            "dimensional_relationship_role_name": "Bill To Customer",
        }
    )
    projected = (
        StageModelChange(
            dataset="dimensional_relationship",
            records=[cast(dict[str, object], rewritten_relationship)],
        ),
        StageModelChange(
            dataset="dimensional_attribute",
            records=[
                cast(dict[str, object], audit),
                cast(dict[str, object], technical),
            ],
        ),
    )

    packages = build_projected_dimensional_validation_packages(
        projected_changes=projected,
        package_size=2,
        max_packages=10,
    )

    records = tuple(record for package in packages for record in package.records)
    assert [record.dataset for record in records] == [
        "dimensional_attribute",
        "dimensional_attribute",
        "dimensional_relationship",
    ]
    attributes = [
        cast(DimensionalAttributeRecord, record.record)
        for record in records
        if record.dataset == "dimensional_attribute"
    ]
    assert {item.dimensional_attribute_role for item in attributes} == {
        "technical",
        "audit",
    }
    relationship = cast(DimensionalRelationshipRecord, records[-1].record)
    assert relationship.from_dimensional_attribute_name == "Customer key"
    assert relationship.dimensional_relationship_is_optional is True
    assert (
        build_projected_dimensional_validation_packages(
            projected_changes=tuple(reversed(projected)),
            package_size=2,
            max_packages=10,
        )
        == packages
    )

    with pytest.raises(InvalidRequestError):
        build_projected_dimensional_validation_packages(
            projected_changes=(
                StageModelChange(dataset="logical_submodel", records=[]),
            ),
            package_size=2,
            max_packages=10,
        )


def test_applied_record_refs_are_complete_and_stable() -> None:
    topology, detail, _contribution_record = _build_topology_and_detail()
    relationship = DimensionalRelationshipRecord.model_validate_json(
        json.dumps(_relationship(optional=True)),
        strict=True,
    )
    applied = DimensionalSection(
        submodels=tuple(item.submodel for item in topology.submodels),
        entities=(detail.entity,),
        attributes=detail.attributes,
        relationships=(relationship,),
    )
    refs = dimensional_applied_record_refs(applied)

    assert refs == tuple(sorted(refs))
    assert len(refs) == 5
    assert any(ref.startswith("entity:") for ref in refs)
    assert (
        'relationship:["customer","customer id","customer","customer code","business_key",""]'
    ) in refs
    renamed = relationship.model_copy(
        update={
            "dimensional_relationship_name": "Renamed relationship",
            "dimensional_relationship_is_optional": False,
        }
    )
    assert dimensional_applied_record_refs(
        applied.model_copy(update={"relationships": (renamed,)})
    ) == (refs)


def test_composite_applied_record_refs_are_collision_safe() -> None:
    source_attribute = _attribute("customer_raw", "customer_id")
    left_attribute = DimensionalAttributeRecord.model_validate_json(
        json.dumps(_dimensional_attribute("A|B", "C", source_attribute, ordinal=1)),
        strict=True,
    )
    right_attribute = DimensionalAttributeRecord.model_validate_json(
        json.dumps(_dimensional_attribute("A", "B|C", source_attribute, ordinal=1)),
        strict=True,
    )
    left_relationship = _relationship(optional=True)
    left_relationship.update(
        {
            "from_dimensional_entity_name": "A|B",
            "from_dimensional_attribute_name": "C",
        }
    )
    right_relationship = _relationship(optional=True)
    right_relationship.update(
        {
            "from_dimensional_entity_name": "A",
            "from_dimensional_attribute_name": "B|C",
        }
    )
    section = DimensionalSection(
        submodels=(),
        entities=(),
        attributes=(left_attribute, right_attribute),
        relationships=(
            DimensionalRelationshipRecord.model_validate_json(
                json.dumps(left_relationship), strict=True
            ),
            DimensionalRelationshipRecord.model_validate_json(
                json.dumps(right_relationship), strict=True
            ),
        ),
    )

    refs = dimensional_applied_record_refs(section)

    assert len(refs) == 4
    assert 'attribute:["a","b|c"]' in refs
    assert 'attribute:["a|b","c"]' in refs
    assert len([item for item in refs if item.startswith("relationship:")]) == 2
