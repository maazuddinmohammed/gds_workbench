from __future__ import annotations

import json
from typing import cast

import pytest
from gds_etl_workbench.domain.modeling_records import (
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    PhysicalObjectKey,
)
from gds_etl_workbench.tools.snapshots.model.contracts import ConceptualSection
from pydantic import JsonValue

from gds_workbench_api.features.conceptual.candidate import (
    ConceptualCandidateValidator,
)


def _physical_object(*, name: str = "customer_raw") -> dict[str, JsonValue]:
    return {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": name,
    }


def _support(
    *,
    name: str = "customer_raw",
    locked: bool = False,
) -> dict[str, JsonValue]:
    return {
        "support_source_type": "object",
        "source_object": _physical_object(name=name),
        "support_role": "source",
        "support_reason": "The physical Object supports this concept.",
        "support_reason_detail": None,
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": locked,
    }


def _object(
    *,
    name: str = "Customer",
    definition: str = "A governed customer.",
    locked: bool = False,
    supports: list[dict[str, JsonValue]] | None = None,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        {
            "conceptual_object_name": name,
            "conceptual_object_definition": definition,
            "conceptual_object_type": "party",
            "conceptual_object_grain": "One customer.",
            "conceptual_object_aliases": [],
            "conceptual_object_confidence": "high",
            "conceptual_object_status": "active",
            "conceptual_object_is_locked": locked,
            "supports": supports or [],
        },
    )


def _relationship() -> dict[str, JsonValue]:
    return {
        "from_conceptual_object_name": "Order",
        "to_conceptual_object_name": "Customer",
        "conceptual_relationship_name": "belongs to",
        "conceptual_relationship_type": "association",
        "conceptual_relationship_definition": "Order belongs to customer.",
        "conceptual_relationship_cardinality": "many_to_one",
        "conceptual_relationship_basis": "Business rule.",
        "conceptual_relationship_cardinality_basis": "Many orders per customer.",
        "conceptual_relationship_confidence": "high",
        "conceptual_relationship_status": "active",
        "conceptual_relationship_is_locked": False,
        "supports": [],
    }


def _validator(
    *,
    applied_objects: tuple[ConceptualObjectRecord, ...] = (),
    applied_relationships: tuple[ConceptualRelationshipRecord, ...] = (),
) -> ConceptualCandidateValidator:
    return ConceptualCandidateValidator(
        selected_object_keys=(
            PhysicalObjectKey.model_validate(_physical_object(), strict=True),
        ),
        assertion_record_keys=(),
        applied=ConceptualSection(
            objects=applied_objects,
            relationships=applied_relationships,
        ),
    )


@pytest.mark.asyncio
async def test_candidate_normalizes_new_records_into_canonical_changes() -> None:
    validator = _validator()
    candidate: JsonValue = {
        "objects": [_object(supports=[_support()])],
        "relationships": [],
    }

    validation = await validator.validate(candidate)
    changes = validator.parse_validated(candidate)

    assert validation.issues == ()
    assert len(changes) == 1
    assert changes[0].dataset == "conceptual_object"
    stored = changes[0].records[0]
    supports = cast(list[dict[str, object]], stored["supports"])
    assert stored["conceptual_object_is_locked"] is False
    assert supports[0]["support_is_locked"] is False
    schema = validator.output_schema()
    properties = cast(dict[str, JsonValue], schema["properties"])
    assert "objects" in properties


@pytest.mark.asyncio
async def test_candidate_preserves_omitted_supports_and_existing_lock_state() -> None:
    applied = ConceptualObjectRecord.model_validate_json(
        json.dumps(
            _object(
                definition="Original definition.",
                supports=[_support(locked=True)],
            )
        ),
        strict=True,
    )
    validator = _validator(applied_objects=(applied,))
    candidate: JsonValue = {
        "objects": [_object(definition="Updated definition.")],
        "relationships": [],
    }

    validation = await validator.validate(candidate)
    changes = validator.parse_validated(candidate)

    assert validation.issues == ()
    assert len(changes) == 1
    stored = changes[0].records[0]
    supports = cast(list[dict[str, object]], stored["supports"])
    assert stored["conceptual_object_definition"] == "Updated definition."
    assert len(supports) == 1
    assert supports[0]["support_is_locked"] is True


@pytest.mark.asyncio
async def test_candidate_omits_unchanged_and_unmentioned_applied_records() -> None:
    customer = ConceptualObjectRecord.model_validate_json(
        json.dumps(_object()),
        strict=True,
    )
    order = ConceptualObjectRecord.model_validate_json(
        json.dumps(_object(name="Order")),
        strict=True,
    )
    validator = _validator(applied_objects=(customer, order))
    candidate: JsonValue = {"objects": [_object()], "relationships": []}

    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate) == ()


@pytest.mark.asyncio
async def test_candidate_rejects_agent_lock_authority_and_locked_record_changes() -> (
    None
):
    locked = ConceptualObjectRecord.model_validate_json(
        json.dumps(_object(locked=True)),
        strict=True,
    )
    validator = _validator(applied_objects=(locked,))

    asserted_lock = await validator.validate(
        cast(
            JsonValue,
            {"objects": [_object(name="Prospect", locked=True)], "relationships": []},
        )
    )
    changed_lock = await validator.validate(
        cast(
            JsonValue,
            {
                "objects": [_object(definition="Changed locked definition.")],
                "relationships": [],
            },
        )
    )

    assert asserted_lock.issues[0].code == "candidate.lock_forbidden"
    assert changed_lock.issues[0].code == "candidate.record_locked"


@pytest.mark.asyncio
async def test_candidate_rejects_unknown_evidence_and_relationship_endpoints() -> None:
    validator = _validator()

    unknown_support = await validator.validate(
        cast(
            JsonValue,
            {
                "objects": [_object(supports=[_support(name="other_raw")])],
                "relationships": [],
            },
        )
    )
    missing_endpoint = await validator.validate(
        cast(
            JsonValue,
            {"objects": [_object()], "relationships": [_relationship()]},
        )
    )

    assert unknown_support.issues[0].code == "candidate.support_outside_selection"
    assert missing_endpoint.issues[0].code == "candidate.relationship_endpoint_missing"


def test_parse_accepts_an_explicit_unchanged_candidate() -> None:
    validator = _validator()

    assert validator.parse_validated({"objects": [], "relationships": []}) == ()
