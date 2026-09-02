from __future__ import annotations

import json
from typing import cast

import pytest
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ConceptualObjectRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from pydantic import JsonValue

from gds_workbench_api.features.conceptual.detailed import (
    DetailedEntityConsolidationValidator,
    DetailedEntityDetail,
    DetailedEntityDetailValidator,
    DetailedObjectContributionValidator,
    DetailedReconciliationValidator,
    derive_relationship_packages,
    load_default_detailed_conceptual_policy,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
)


def _source(name: str) -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=name,
    )


def test_default_policy_loads_from_validated_json() -> None:
    policy = load_default_detailed_conceptual_policy()

    assert policy.schema_version == "1.0"
    assert policy.max_relationship_packages == 20_000


def _support(name: str) -> dict[str, JsonValue]:
    return {
        "support_source_type": "object",
        "source_object": _source(name).model_dump(mode="json"),
        "support_role": "source",
        "support_reason": "The selected Object supports this proposal.",
        "support_reason_detail": None,
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": False,
    }


def _object(name: str, *source_names: str) -> dict[str, JsonValue]:
    return {
        "conceptual_object_name": name,
        "conceptual_object_definition": f"A governed {name}.",
        "conceptual_object_type": "entity",
        "conceptual_object_grain": f"One {name}.",
        "conceptual_object_aliases": [],
        "conceptual_object_confidence": "high",
        "conceptual_object_status": "active",
        "conceptual_object_is_locked": False,
        "supports": [_support(source_name) for source_name in source_names],
    }


def _parsed_object(name: str, *source_names: str) -> ConceptualObjectRecord:
    return ConceptualObjectRecord.model_validate_json(
        json.dumps(_object(name, *source_names)),
        strict=True,
    )


async def test_object_contribution_requires_exact_source_and_explicit_disposition() -> (
    None
):
    validator = DetailedObjectContributionValidator(
        contribution_ref="object_1",
        source_object=_source("customer_raw"),
    )
    valid = {
        "contribution_ref": "object_1",
        "source_object": _source("customer_raw").model_dump(mode="json"),
        "disposition": "represented",
        "rationale": "The source represents a customer.",
        "proposals": [
            {
                "local_entity_ref": "customer",
                "object": _object("Customer", "customer_raw"),
            }
        ],
    }

    assert (await validator.validate(cast(JsonValue, valid))).issues == ()
    parsed = validator.parse_validated(cast(JsonValue, valid))
    assert parsed.proposal_refs == ("object_1.customer",)

    invalid = {**valid, "disposition": "context_only"}
    assert (await validator.validate(cast(JsonValue, invalid))).issues[0].code == (
        "detailed.object_contribution_invalid"
    )


async def test_consolidation_assigns_or_discards_every_proposal_exactly_once() -> None:
    first_validator = DetailedObjectContributionValidator(
        contribution_ref="object_1",
        source_object=_source("customer_raw"),
    )
    second_validator = DetailedObjectContributionValidator(
        contribution_ref="object_2",
        source_object=_source("customer_address_raw"),
    )
    first = first_validator.parse_validated(
        cast(
            JsonValue,
            {
                "contribution_ref": "object_1",
                "source_object": _source("customer_raw").model_dump(mode="json"),
                "disposition": "represented",
                "rationale": "Customer evidence.",
                "proposals": [
                    {
                        "local_entity_ref": "customer",
                        "object": _object("Customer", "customer_raw"),
                    }
                ],
            },
        )
    )
    second = second_validator.parse_validated(
        cast(
            JsonValue,
            {
                "contribution_ref": "object_2",
                "source_object": _source("customer_address_raw").model_dump(
                    mode="json"
                ),
                "disposition": "represented",
                "rationale": "Customer address evidence.",
                "proposals": [
                    {
                        "local_entity_ref": "customer",
                        "object": _object("Customer", "customer_address_raw"),
                    }
                ],
            },
        )
    )
    validator = DetailedEntityConsolidationValidator(contributions=(first, second))
    candidate = cast(
        JsonValue,
        {
            "entities": [
                {
                    "canonical_entity_ref": "customer",
                    "contribution_refs": ["object_1.customer", "object_2.customer"],
                    "candidate_names": ["Customer"],
                }
            ],
            "discarded_contribution_refs": [],
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate).entities[0].canonical_entity_ref == (
        "customer"
    )

    missing = cast(
        JsonValue,
        {
            "entities": [
                {
                    "canonical_entity_ref": "customer",
                    "contribution_refs": ["object_1.customer"],
                    "candidate_names": ["Customer"],
                }
            ],
            "discarded_contribution_refs": [],
        },
    )
    assert (await validator.validate(missing)).issues[0].code == (
        "detailed.entity_consolidation_coverage_invalid"
    )


async def test_entity_detail_preserves_every_consolidated_physical_support() -> None:
    contribution_validator = DetailedObjectContributionValidator(
        contribution_ref="object_1",
        source_object=_source("customer_raw"),
    )
    contribution = contribution_validator.parse_validated(
        cast(
            JsonValue,
            {
                "contribution_ref": "object_1",
                "source_object": _source("customer_raw").model_dump(mode="json"),
                "disposition": "represented",
                "rationale": "Customer evidence.",
                "proposals": [
                    {
                        "local_entity_ref": "customer",
                        "object": _object("Customer", "customer_raw"),
                    }
                ],
            },
        )
    )
    consolidation = DetailedEntityConsolidationValidator(
        contributions=(contribution,)
    ).parse_validated(
        cast(
            JsonValue,
            {
                "entities": [
                    {
                        "canonical_entity_ref": "customer",
                        "contribution_refs": ["object_1.customer"],
                        "candidate_names": ["Customer"],
                    }
                ],
                "discarded_contribution_refs": [],
            },
        )
    )
    validator = DetailedEntityDetailValidator(
        entity=consolidation.entities[0],
        contributions=(contribution,),
    )
    candidate = cast(
        JsonValue,
        {
            "canonical_entity_ref": "customer",
            "object": _object("Customer", "customer_raw"),
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate).object.conceptual_object_name == (
        "Customer"
    )

    missing_support = cast(
        JsonValue,
        {
            "canonical_entity_ref": "customer",
            "object": _object("Customer"),
        },
    )
    assert (await validator.validate(missing_support)).issues[0].code == (
        "detailed.entity_detail_support_invalid"
    )


def test_relationship_derivation_is_deterministic_and_never_creates_self_pairs() -> (
    None
):
    customer = DetailedEntityDetail(
        canonical_entity_ref="customer",
        object=_parsed_object("Customer", "customer_raw"),
    )
    order = DetailedEntityDetail(
        canonical_entity_ref="order",
        object=_parsed_object("Order", "order_raw"),
    )
    attributes = (
        PhysicalAttributeKey(
            **_source("customer_raw").model_dump(), attribute_name="customer_id"
        ),
        PhysicalAttributeKey(
            **_source("customer_raw").model_dump(), attribute_name="name"
        ),
        PhysicalAttributeKey(
            **_source("order_raw").model_dump(), attribute_name="customer_id"
        ),
    )
    analysis = AnalysisResultRecord.model_validate(
        {
            "from_tenant_code": "NWA",
            "from_system_code": "CRM",
            "from_connection_code": "SOURCE",
            "from_object_schema": "bronze",
            "from_object_name": "order_raw",
            "from_attribute_name": "customer_id",
            "to_tenant_code": "NWA",
            "to_system_code": "CRM",
            "to_connection_code": "SOURCE",
            "to_object_schema": "bronze",
            "to_object_name": "customer_raw",
            "to_attribute_name": "customer_id",
            "relationship_kind": "reference",
            "relationship_confidence": "high",
            "relationship_basis": "Validated matching key evidence.",
            "validation_policy_version": None,
            "validation_result": None,
            "validation_source_non_null_count": None,
            "validation_source_distinct_count": None,
            "validation_target_non_null_count": None,
            "validation_target_distinct_count": None,
            "validation_source_missing_target_count": None,
            "validation_unused_target_count": None,
            "validation_duplicate_target_key_count": None,
            "analysis_result_status": "active",
            "analysis_result_is_locked": False,
        },
        strict=True,
    )

    packages = derive_relationship_packages(
        entity_details=(customer, order),
        attributes=attributes,
        analysis_relationships=(analysis,),
        max_packages=100,
    )

    assert len(packages) == 1
    assert packages[0].package_ref == "relationship_00001"
    assert (packages[0].from_entity_ref, packages[0].to_entity_ref) == (
        "customer",
        "order",
    )
    assert [signal.signal_type for signal in packages[0].signals] == [
        "analysis_relationship",
        "matching_attribute",
    ]


def test_matching_physical_attribute_names_do_not_create_a_business_relationship() -> None:
    customer = DetailedEntityDetail(
        canonical_entity_ref="customer",
        object=_parsed_object("Customer", "customer_raw"),
    )
    order = DetailedEntityDetail(
        canonical_entity_ref="order",
        object=_parsed_object("Order", "order_raw"),
    )
    attributes = (
        PhysicalAttributeKey(
            **_source("customer_raw").model_dump(), attribute_name="customer_id"
        ),
        PhysicalAttributeKey(
            **_source("order_raw").model_dump(), attribute_name="customer_id"
        ),
    )

    assert derive_relationship_packages(
        entity_details=(customer, order),
        attributes=attributes,
        analysis_relationships=(),
        max_packages=100,
    ) == ()


async def test_reconciliation_requires_exhaustive_run_local_coverage() -> None:
    details = (
        DetailedEntityDetail(
            canonical_entity_ref="customer",
            object=_parsed_object("Customer", "customer_raw"),
        ),
    )
    validator = DetailedReconciliationValidator(
        entity_details=details,
        input_contribution_refs=("object_1",),
        relationship_package_refs=("relationship_00001",),
        applied_record_refs=("object:account",),
    )
    candidate = cast(
        JsonValue,
        {
            "objects": [_object("Customer", "customer_raw")],
            "relationships": [],
            "entity_coverage": [
                {
                    "canonical_entity_ref": "customer",
                    "conceptual_object_name": "Customer",
                }
            ],
            "reviewed_input_contribution_refs": ["object_1"],
            "reviewed_relationship_package_refs": ["relationship_00001"],
            "reviewed_applied_record_refs": ["object:account"],
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    assert validator.materialize_validated(candidate) == {
        "objects": [_object("Customer", "customer_raw")],
        "relationships": [],
    }

    incomplete = cast(
        JsonValue,
        {
            **cast(dict[str, JsonValue], candidate),
            "reviewed_relationship_package_refs": [],
        },
    )
    assert (await validator.validate(incomplete)).issues[0].code == (
        "detailed.reconciliation_coverage_invalid"
    )
    with pytest.raises(AgentCandidateValidationError):
        validator.materialize_validated(incomplete)
