from __future__ import annotations

import json
from copy import deepcopy
from typing import cast

from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalSubmodelRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.tools.snapshots.model.contracts import DimensionalSection
from pydantic import JsonValue

from gds_workbench_api.features.dimensional.candidate import DimensionalCandidateValidator


def _object(name: str = "dim_customer") -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code="NWA",
        system_code="GDS",
        connection_code="PRIMARY",
        object_schema="silver_nwa",
        object_name=name,
    )


def _attribute(name: str = "customer_id") -> PhysicalAttributeKey:
    return PhysicalAttributeKey(**_object().model_dump(), attribute_name=name)


def _candidate() -> dict[str, object]:
    return {
        "submodels": [
            {
                "dimensional_submodel_name": "Customer Analytics",
                "dimensional_submodel_definition": "Customer analytics.",
                "dimensional_submodel_status": "active",
                "dimensional_submodel_is_locked": False,
            }
        ],
        "entities": [
            {
                "dimensional_entity_name": "Customer Dimension",
                "dimensional_entity_definition": "One customer.",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "dimensional_entity_dependency_order": 0,
                "dimensional_entity_confidence": "high",
                "dimensional_entity_status": "active",
                "dimensional_entity_is_locked": False,
                "submodels": [
                    {
                        "submodel_name": "Customer Analytics",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": _object().model_dump(mode="json"),
                        "source_order": 1,
                        "rationale": "Registered Silver customer source.",
                        "status": "active",
                        "is_locked": False,
                        "source_role": "primary",
                    }
                ],
            }
        ],
        "attributes": [
            {
                "dimensional_entity_name": "Customer Dimension",
                "dimensional_attribute_name": "Customer ID",
                "dimensional_attribute_definition": "Customer identifier.",
                "dimensional_attribute_data_type": "bigint",
                "dimensional_attribute_is_nullable": False,
                "dimensional_attribute_ordinal_position": 1,
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
                        "source_attribute": _attribute().model_dump(mode="json"),
                        "source_order": 1,
                        "rationale": "Silver business key.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            }
        ],
        "relationships": [],
    }


def _applied(candidate: dict[str, object] | None = None) -> DimensionalSection:
    value = candidate or _candidate()
    return DimensionalSection(
        submodels=(
            DimensionalSubmodelRecord.model_validate_json(
                json.dumps(_first_record(value, "submodels")), strict=True
            ),
        ),
        entities=(
            DimensionalEntityRecord.model_validate_json(
                json.dumps(_first_record(value, "entities")), strict=True
            ),
        ),
        attributes=(
            DimensionalAttributeRecord.model_validate_json(
                json.dumps(_first_record(value, "attributes")), strict=True
            ),
        ),
        relationships=(),
    )


def _validator(
    *,
    applied: DimensionalSection | None = None,
    assertion_record_keys: tuple[str, ...] = (),
) -> DimensionalCandidateValidator:
    return DimensionalCandidateValidator(
        selected_object_keys=(_object(),),
        selected_attribute_keys=(_attribute(),),
        assertion_record_keys=assertion_record_keys,
        applied=applied,
    )


def _first_record(candidate: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], cast(list[object], candidate[key])[0])


async def test_valid_candidate_normalizes_to_exact_dimensional_changes() -> None:
    candidate: JsonValue = _candidate()  # type: ignore[assignment]

    assert (await _validator().validate(candidate)).issues == ()
    changes = _validator().parse_validated(candidate)

    assert [change.dataset for change in changes] == [
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
    ]
    assert sum(len(change.records) for change in changes) == 3


async def test_candidate_rejects_silver_evidence_outside_frozen_selection() -> None:
    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    source = cast(dict[str, object], cast(list[object], entity["sources"])[0])
    source["source_object"] = _object("unselected_silver").model_dump(mode="json")

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert {issue.code for issue in issues} == {"candidate.source_outside_selection"}


async def test_candidate_rejects_assertion_evidence_outside_frozen_context() -> None:
    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    entity["sources"] = [
        {
            "support_source_type": "assertion",
            "assertion_record": {"modeling_assertion_record_key": "assertion.customer"},
            "source_order": 1,
            "rationale": "Business assertion.",
            "status": "active",
            "is_locked": False,
            "source_role": "business_context",
        }
    ]
    attribute = _first_record(candidate, "attributes")
    attribute["sources"] = [
        {
            "support_source_type": "assertion",
            "assertion_record": {"modeling_assertion_record_key": "assertion.customer_key"},
            "source_order": 1,
            "rationale": "Key assertion.",
            "status": "active",
            "is_locked": False,
        }
    ]

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert [issue.code for issue in issues].count("candidate.assertion_unavailable") == 2


async def test_candidate_requires_complete_future_references() -> None:
    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    membership = cast(dict[str, object], cast(list[object], entity["submodels"])[0])
    membership["submodel_name"] = "Missing Submodel"
    attribute = _first_record(candidate, "attributes")
    attribute["dimensional_entity_name"] = "Missing Dimension"
    candidate["relationships"] = [
        {
            "dimensional_relationship_name": "Missing relationship",
            "dimensional_relationship_definition": "Missing endpoint.",
            "from_dimensional_entity_name": "Customer Dimension",
            "from_dimensional_attribute_name": "Customer ID",
            "to_dimensional_entity_name": "Missing Dimension",
            "to_dimensional_attribute_name": "Missing ID",
            "dimensional_relationship_kind": "foreign_key",
            "dimensional_relationship_cardinality": "many_to_one",
            "dimensional_relationship_is_optional": True,
            "dimensional_relationship_role_name": None,
            "dimensional_relationship_confidence": "high",
            "dimensional_relationship_basis": "Expected dimensional join.",
            "dimensional_relationship_cardinality_basis": "Many facts to one dimension.",
            "dimensional_relationship_status": "active",
            "dimensional_relationship_is_locked": False,
        }
    ]

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert {
        "candidate.submodel_missing",
        "candidate.entity_missing",
        "candidate.relationship_endpoint_missing",
    }.issubset({issue.code for issue in issues})


async def test_candidate_omission_preserves_applied_nested_records() -> None:
    original = _candidate()
    candidate = deepcopy(original)
    entity = _first_record(candidate, "entities")
    entity["submodels"] = []
    entity["sources"] = []
    attribute = _first_record(candidate, "attributes")
    attribute["sources"] = []
    validator = _validator(applied=_applied(original))

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    assert validator.parse_validated(cast(JsonValue, candidate)) == ()


async def test_candidate_schema_forbids_agent_lock_authority() -> None:
    assert "'const': False" in str(_validator().output_schema())

    candidate = _candidate()
    submodel = _first_record(candidate, "submodels")
    submodel["dimensional_submodel_is_locked"] = True
    entity = _first_record(candidate, "entities")
    entity["dimensional_entity_is_locked"] = True
    source = cast(dict[str, object], cast(list[object], entity["sources"])[0])
    source["is_locked"] = True
    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert [issue.code for issue in issues].count("candidate.lock_forbidden") == 3


async def test_candidate_rejects_changes_to_applied_main_and_nested_locks() -> None:
    applied = _applied()
    locked_source = applied.entities[0].sources[0].model_copy(update={"is_locked": True})
    entity = applied.entities[0].model_copy(update={"sources": (locked_source,)})
    attribute = applied.attributes[0].model_copy(update={"dimensional_attribute_is_locked": True})
    applied = applied.model_copy(update={"entities": (entity,), "attributes": (attribute,)})
    candidate = _candidate()
    candidate_entity = _first_record(candidate, "entities")
    source = cast(dict[str, object], cast(list[object], candidate_entity["sources"])[0])
    source["rationale"] = "Agent changed locked lineage."
    candidate_attribute = _first_record(candidate, "attributes")
    candidate_attribute["dimensional_attribute_definition"] = "Agent changed locked row."

    issues = (await _validator(applied=applied).validate(cast(JsonValue, candidate))).issues

    assert [issue.code for issue in issues].count("candidate.record_locked") == 2


async def test_candidate_forbids_all_agent_authored_gold_policy_columns() -> None:
    candidate = _candidate()
    technical = _first_record(candidate, "attributes")
    technical["dimensional_attribute_role"] = "technical"
    audit = deepcopy(technical)
    audit["dimensional_attribute_name"] = "Loaded At"
    audit["dimensional_attribute_role"] = "audit"
    audit["dimensional_attribute_key_role"] = "none"
    audit["dimensional_attribute_is_grain_component"] = False
    audit["dimensional_attribute_is_audit_column"] = True
    audit["sources"] = []
    surrogate = deepcopy(_first_record(candidate, "attributes"))
    surrogate["dimensional_attribute_name"] = "Customer Dimension Key"
    surrogate["dimensional_attribute_key_role"] = "surrogate"
    foreign = deepcopy(_first_record(candidate, "attributes"))
    foreign["dimensional_attribute_name"] = "Account Dimension Key"
    foreign["dimensional_attribute_key_role"] = "foreign"
    cast(list[object], candidate["attributes"]).extend((audit, surrogate, foreign))

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert [issue.code for issue in issues].count("candidate.policy_column_forbidden") == 4
