from __future__ import annotations

from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    PhysicalAttributeKey,
)
from pydantic import JsonValue

from gds_workbench_api.features.analysis.candidate import (
    AnalysisInferenceCandidateValidator,
)


def _attribute(*, object_name: str, attribute_name: str) -> PhysicalAttributeKey:
    return PhysicalAttributeKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=object_name,
        attribute_name=attribute_name,
    )


def _candidate(
    *,
    basis: str = "Names and profile evidence suggest a relationship.",
    extra: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    record: dict[str, JsonValue] = {
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
        "relationship_basis": basis,
    }
    record.update(extra or {})
    return record


def _applied(
    *,
    basis: str = "Original evidence.",
    locked: bool = False,
    relationship_kind: str = "reference",
) -> AnalysisResultRecord:
    return AnalysisResultRecord.model_validate(
        {
            **_candidate(basis=basis),
            "relationship_kind": relationship_kind,
            "validation_policy_version": "1.0.0",
            "validation_result": "supported",
            "validation_source_non_null_count": 10,
            "validation_source_distinct_count": 8,
            "validation_target_non_null_count": 8,
            "validation_target_distinct_count": 8,
            "validation_source_missing_target_count": 0,
            "validation_unused_target_count": 0,
            "validation_duplicate_target_key_count": 0,
            "analysis_result_status": "needs_review",
            "analysis_result_is_locked": locked,
        },
        strict=True,
    )


def _validator(
    *,
    applied: tuple[AnalysisResultRecord, ...] = (),
) -> AnalysisInferenceCandidateValidator:
    return AnalysisInferenceCandidateValidator(
        selected_attribute_keys=(
            _attribute(object_name="order_raw", attribute_name="customer_id"),
            _attribute(object_name="customer_raw", attribute_name="customer_id"),
        ),
        applied=applied,
    )


@pytest.mark.asyncio
async def test_new_inference_normalizes_only_agent_owned_fields() -> None:
    validator = _validator()
    candidate: JsonValue = {"relationships": [_candidate()]}

    assert (await validator.validate(candidate)).issues == ()
    changes = validator.parse_validated(candidate)

    assert len(changes) == 1
    assert changes[0].dataset == "analysis_result"
    stored = changes[0].records[0]
    assert stored["analysis_result_status"] == "needs_review"
    assert stored["analysis_result_is_locked"] is False
    assert stored["validation_result"] is None

    schema = validator.output_schema()
    relationships = cast(dict[str, JsonValue], schema["properties"])["relationships"]
    items = cast(dict[str, JsonValue], cast(dict[str, JsonValue], relationships)["items"])
    reference = cast(str, items["$ref"])
    definition_name = reference.rsplit("/", 1)[-1]
    definition = cast(dict[str, JsonValue], schema["$defs"])[definition_name]
    fields = cast(dict[str, JsonValue], cast(dict[str, JsonValue], definition)["properties"])
    assert "relationship_basis" in fields
    assert "validation_result" not in fields
    assert "analysis_result_status" not in fields
    assert "analysis_result_is_locked" not in fields


@pytest.mark.asyncio
async def test_inference_preserves_validation_lifecycle_and_lock_fields() -> None:
    validator = _validator(applied=(_applied(),))
    candidate: JsonValue = {"relationships": [_candidate(basis="Updated inference evidence.")]}

    assert (await validator.validate(candidate)).issues == ()
    stored = validator.parse_validated(candidate)[0].records[0]

    assert stored["relationship_basis"] == "Updated inference evidence."
    assert stored["validation_result"] == "supported"
    assert stored["validation_source_non_null_count"] == 10
    assert stored["analysis_result_status"] == "needs_review"
    assert stored["analysis_result_is_locked"] is False


@pytest.mark.asyncio
async def test_locked_relationship_cannot_be_changed_by_inference() -> None:
    validator = _validator(applied=(_applied(locked=True),))
    candidate: JsonValue = {"relationships": [_candidate(basis="Changed while locked.")]}

    validation = await validator.validate(candidate)

    assert [issue.code for issue in validation.issues] == ["candidate.record_locked"]
    with pytest.raises(InvalidRequestError):
        validator.parse_validated(candidate)


@pytest.mark.asyncio
async def test_inference_rejects_endpoints_outside_immutable_selection() -> None:
    validator = _validator()
    candidate: JsonValue = {
        "relationships": [_candidate(extra={"to_object_name": "outside_scope_raw"})]
    }

    validation = await validator.validate(candidate)

    assert [issue.code for issue in validation.issues] == ["candidate.endpoint_outside_selection"]


@pytest.mark.asyncio
async def test_inference_rejects_unowned_fields_and_duplicate_identities() -> None:
    validator = _validator()
    unowned: JsonValue = {"relationships": [_candidate(extra={"analysis_result_is_locked": True})]}
    duplicate: JsonValue = {
        "relationships": [_candidate(), _candidate(basis="Duplicate identity.")]
    }

    assert [issue.code for issue in (await validator.validate(unowned)).issues] == [
        "candidate.schema_invalid"
    ]
    assert [issue.code for issue in (await validator.validate(duplicate)).issues] == [
        "candidate.relationship_duplicate"
    ]


@pytest.mark.asyncio
async def test_empty_or_unchanged_inference_is_a_valid_noop() -> None:
    applied = _applied()
    validator = _validator(applied=(applied,))

    assert (await validator.validate({"relationships": []})).issues == ()
    assert validator.parse_validated({"relationships": []}) == ()
    assert (
        validator.parse_validated({"relationships": [_candidate(basis="Original evidence.")]}) == ()
    )


@pytest.mark.asyncio
async def test_existing_canonical_identity_keeps_its_stored_relationship_kind() -> None:
    applied = _applied(relationship_kind="Reference")
    validator = _validator(applied=(applied,))
    candidate: JsonValue = {
        "relationships": [
            _candidate(
                basis="Original evidence.",
                extra={"relationship_kind": " reference "},
            )
        ]
    }

    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate) == ()
