from __future__ import annotations

from typing import cast

import pytest
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    PhysicalAttributeKey,
)
from pydantic import JsonValue

from gds_workbench_api.features.analysis.candidate import (
    AnalysisInferenceCandidateValidator,
)
from gds_workbench_api.features.analysis.detailed import (
    DetailedAnalysisCandidateFinderValidator,
    DetailedAnalysisReconciliationValidator,
    DetailedAnalysisRelationshipResolverValidator,
    DetailedAnalysisReviewerValidator,
    load_default_detailed_analysis_policy,
)


def _attribute(object_name: str, attribute_name: str) -> PhysicalAttributeKey:
    return PhysicalAttributeKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=object_name,
        attribute_name=attribute_name,
    )


def _relationship() -> dict[str, JsonValue]:
    return {
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
        "relationship_basis": "Matching names and compatible profile evidence.",
    }


def _finder_candidate() -> JsonValue:
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "coverage": {
                "slice_ref": "slice_00001",
                "disposition": "candidates_found",
            },
            "candidates": [
                {
                    "candidate_ref": "slice_00001_candidate_00001",
                    "left_attribute": _attribute("order_raw", "customer_id").model_dump(
                        mode="json"
                    ),
                    "right_attribute": _attribute(
                        "customer_raw", "customer_id"
                    ).model_dump(mode="json"),
                    "evidence_signals": [
                        {
                            "signal_type": "name",
                            "signal_detail": "Normalized Attribute names match.",
                        }
                    ],
                }
            ],
        },
    )


def test_default_detailed_analysis_policy_is_bounded() -> None:
    policy = load_default_detailed_analysis_policy()

    assert policy.schema_version == "1.0"
    assert 1 <= policy.max_object_pairs <= 20_000
    assert 1 <= policy.max_candidate_slices <= 20_000
    assert 1 <= policy.max_candidates_per_slice <= 2_000
    assert 1 <= policy.max_total_candidates <= 20_000
    assert 1 <= policy.max_review_findings <= 1_000


@pytest.mark.asyncio
async def test_candidate_finder_requires_exact_slice_and_safe_endpoint_candidates() -> (
    None
):
    validator = DetailedAnalysisCandidateFinderValidator(
        slice_ref="slice_00001",
        allowed_attributes=(
            _attribute("order_raw", "customer_id"),
            _attribute("customer_raw", "customer_id"),
        ),
    )

    assert (await validator.validate(_finder_candidate())).issues == ()
    parsed = validator.parse_validated(_finder_candidate())
    assert parsed.coverage.slice_ref == "slice_00001"
    assert parsed.candidates[0].candidate_ref == "slice_00001_candidate_00001"

    outside = cast(dict[str, object], _finder_candidate())
    outside_candidates = cast(list[dict[str, object]], outside["candidates"])
    outside_candidates[0]["right_attribute"] = _attribute(
        "outside_raw", "customer_id"
    ).model_dump(mode="json")
    issues = (await validator.validate(cast(JsonValue, outside))).issues
    assert [issue.code for issue in issues] == [
        "detailed.candidate_finder_coverage_invalid"
    ]


@pytest.mark.asyncio
async def test_candidate_finder_requires_slice_namespaced_references_and_cross_object_pairs() -> (
    None
):
    left = (
        _attribute("order_raw", "customer_id"),
        _attribute("order_raw", "product_id"),
    )
    right = (_attribute("customer_raw", "customer_id"),)
    validator = DetailedAnalysisCandidateFinderValidator(
        slice_ref="slice_00001",
        left_attributes=left,
        right_attributes=right,
    )

    unscoped = cast(dict[str, object], _finder_candidate())
    unscoped_candidates = cast(list[dict[str, object]], unscoped["candidates"])
    unscoped_candidates[0]["candidate_ref"] = "candidate_00001"
    assert (await validator.validate(cast(JsonValue, unscoped))).issues

    same_side = cast(dict[str, object], _finder_candidate())
    same_side_candidates = cast(list[dict[str, object]], same_side["candidates"])
    same_side_candidates[0]["right_attribute"] = left[1].model_dump(mode="json")
    assert (await validator.validate(cast(JsonValue, same_side))).issues


@pytest.mark.asyncio
async def test_relationship_resolver_covers_every_candidate_exactly_once() -> None:
    finder_validator = DetailedAnalysisCandidateFinderValidator(
        slice_ref="slice_00001",
        allowed_attributes=(
            _attribute("order_raw", "customer_id"),
            _attribute("customer_raw", "customer_id"),
        ),
    )
    finder = finder_validator.parse_validated(_finder_candidate())
    validator = DetailedAnalysisRelationshipResolverValidator(
        candidates=finder.candidates,
    )
    candidate = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "decisions": [
                {
                    "candidate_ref": "slice_00001_candidate_00001",
                    "disposition": "relationship",
                    "relationship": _relationship(),
                    "rationale": "The supplied evidence supports a reference.",
                }
            ],
        },
    )

    assert (await validator.validate(candidate)).issues == ()

    assert validator.parse_validated(candidate).decisions[0].relationship is not None

    missing = cast(JsonValue, {"schema_version": "1.0", "decisions": []})
    assert [issue.code for issue in (await validator.validate(missing)).issues] == [
        "detailed.relationship_resolution_coverage_invalid"
    ]


@pytest.mark.asyncio
async def test_reconciliation_enforces_candidate_and_applied_coverage_then_final_schema() -> (
    None
):
    selected = (
        _attribute("order_raw", "customer_id"),
        _attribute("customer_raw", "customer_id"),
    )
    final_validator = AnalysisInferenceCandidateValidator(
        selected_attribute_keys=selected,
        applied=(),
    )
    finder = DetailedAnalysisCandidateFinderValidator(
        slice_ref="slice_00001",
        allowed_attributes=selected,
    ).parse_validated(_finder_candidate())
    resolver = DetailedAnalysisRelationshipResolverValidator(
        candidates=finder.candidates
    )
    resolution = resolver.parse_validated(
        cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "decisions": [
                    {
                        "candidate_ref": "slice_00001_candidate_00001",
                        "disposition": "relationship",
                        "relationship": _relationship(),
                        "rationale": "Supported.",
                    }
                ],
            },
        )
    )
    validator = DetailedAnalysisReconciliationValidator(
        decisions=resolution.decisions,
        applied_by_ref={},
        final_validator=final_validator,
    )
    candidate = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": [
                {
                    "candidate_ref": "slice_00001_candidate_00001",
                    "disposition": "accepted",
                }
            ],
            "applied_record_coverage": [],
            "relationships": [_relationship()],
        },
    )

    assert (await validator.validate(candidate)).issues == ()

    assert validator.parse_validated(candidate).relationships[0].relationship_kind == (
        "reference"
    )
    assert validator.materialize_validated(candidate) == {
        "relationships": [_relationship()]
    }

    missing_coverage = cast(dict[str, object], candidate)
    missing_coverage["candidate_coverage"] = []
    assert [
        issue.code
        for issue in (
            await validator.validate(cast(JsonValue, missing_coverage))
        ).issues
    ] == ["detailed.reconciliation_coverage_invalid"]


@pytest.mark.asyncio
async def test_reconciliation_rejects_relationship_without_candidate_or_applied_provenance() -> (
    None
):
    selected = (
        _attribute("order_raw", "customer_id"),
        _attribute("customer_raw", "customer_id"),
        _attribute("order_raw", "product_id"),
        _attribute("product_raw", "product_id"),
    )
    finder = DetailedAnalysisCandidateFinderValidator(
        slice_ref="slice_00001",
        allowed_attributes=selected,
    ).parse_validated(_finder_candidate())
    resolution = DetailedAnalysisRelationshipResolverValidator(
        candidates=finder.candidates
    ).parse_validated(
        cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "decisions": [
                    {
                        "candidate_ref": "slice_00001_candidate_00001",
                        "disposition": "relationship",
                        "relationship": _relationship(),
                        "rationale": "Supported.",
                    }
                ],
            },
        )
    )
    validator = DetailedAnalysisReconciliationValidator(
        decisions=resolution.decisions,
        applied_by_ref={},
        final_validator=AnalysisInferenceCandidateValidator(
            selected_attribute_keys=selected,
            applied=(),
        ),
    )
    invented = {
        **_relationship(),
        "from_attribute_name": "product_id",
        "to_object_name": "product_raw",
        "to_attribute_name": "product_id",
    }
    candidate = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": [
                {
                    "candidate_ref": "slice_00001_candidate_00001",
                    "disposition": "accepted",
                }
            ],
            "applied_record_coverage": [],
            "relationships": [_relationship(), invented],
        },
    )

    assert [issue.code for issue in (await validator.validate(candidate)).issues] == [
        "detailed.reconciliation_coverage_invalid"
    ]


@pytest.mark.asyncio
async def test_reconciliation_accepts_preserved_applied_relationship_provenance() -> (
    None
):
    relationship = AnalysisResultRecord.model_validate(
        {
            **_relationship(),
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
        strict=False,
    )
    selected = (
        _attribute("order_raw", "customer_id"),
        _attribute("customer_raw", "customer_id"),
    )
    validator = DetailedAnalysisReconciliationValidator(
        decisions=(),
        applied_by_ref={"applied_00001": relationship},
        final_validator=AnalysisInferenceCandidateValidator(
            selected_attribute_keys=selected,
            applied=(relationship,),
        ),
    )
    candidate = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": [],
            "applied_record_coverage": [
                {
                    "applied_record_ref": "applied_00001",
                    "disposition": "preserved",
                }
            ],
            "relationships": [_relationship()],
        },
    )

    assert (await validator.validate(candidate)).issues == ()

    preserved_without_reemitting = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": [],
            "applied_record_coverage": [
                {
                    "applied_record_ref": "applied_00001",
                    "disposition": "preserved",
                }
            ],
            "relationships": [],
        },
    )
    assert (await validator.validate(preserved_without_reemitting)).issues == ()
    assert validator.materialize_validated(preserved_without_reemitting) == {
        "relationships": []
    }

    unsupported_delete = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "candidate_coverage": [],
            "applied_record_coverage": [
                {
                    "applied_record_ref": "applied_00001",
                    "disposition": "superseded",
                }
            ],
            "relationships": [],
        },
    )
    assert (await validator.validate(unsupported_delete)).issues


@pytest.mark.asyncio
async def test_reviewer_covers_candidate_without_mutating_it() -> None:
    relationship = AnalysisResultRecord.model_validate(
        {
            **_relationship(),
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
        strict=False,
    )
    validator = DetailedAnalysisReviewerValidator(
        relationships=(relationship,),
        applied_record_refs=(),
    )
    candidate = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "reviewed_relationship_refs": ["relationship_00001"],
            "reviewed_applied_record_refs": [],
            "findings": [],
        },
    )

    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate).findings == ()
