from __future__ import annotations

import json
from copy import deepcopy
from typing import cast

from gds_etl_workbench.domain.modeling_records import (
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalSubmodelRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.tools.snapshots.model.contracts import LogicalSection
from jsonschema import Draft202012Validator
from pydantic import JsonValue

from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator


def _object(name: str = "customer_raw") -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=name,
    )


def _attribute(name: str = "customer_id") -> PhysicalAttributeKey:
    return PhysicalAttributeKey(**_object().model_dump(), attribute_name=name)


def _candidate() -> dict[str, object]:
    return {
        "submodels": [
            {
                "logical_submodel_name": "Customer Domain",
                "logical_submodel_definition": "Customer data.",
                "logical_submodel_status": "active",
                "logical_submodel_is_locked": False,
            }
        ],
        "entities": [
            {
                "logical_entity_name": "Customer",
                "logical_entity_definition": "One customer.",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One row per customer.",
                "logical_entity_dependency_order": 0,
                "logical_entity_confidence": "high",
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "submodels": [
                    {
                        "submodel_name": "Customer Domain",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": _object().model_dump(mode="json"),
                        "source_order": 1,
                        "rationale": "Primary customer source.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            }
        ],
        "attributes": [
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "Customer Id",
                "logical_attribute_definition": "Customer identifier.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": True,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 1,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": _attribute().model_dump(mode="json"),
                        "source_order": 1,
                        "rationale": "Primary customer key.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            }
        ],
        "relationships": [],
    }


def _validator(*, applied: LogicalSection | None = None) -> LogicalCandidateValidator:
    return LogicalCandidateValidator(
        selected_object_keys=(_object(),),
        selected_attribute_keys=(_attribute(),),
        assertion_record_keys=(),
        applied=applied,
    )


def _first_record(candidate: dict[str, object], key: str) -> dict[str, object]:
    records = cast(list[object], candidate[key])
    return cast(dict[str, object], records[0])


async def test_valid_candidate_normalizes_to_exact_logical_changes() -> None:
    candidate = cast(JsonValue, _candidate())
    validator = _validator()

    assert (await validator.validate(candidate)).issues == ()
    changes = validator.parse_validated(candidate)

    assert [change.dataset for change in changes] == [
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
    ]
    assert sum(len(change.records) for change in changes) == 3


async def test_candidate_rejects_physical_evidence_outside_frozen_selection() -> None:
    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    sources = cast(list[object], entity["sources"])
    source = cast(dict[str, object], sources[0])
    source["source_object"] = _object("unselected_raw").model_dump(mode="json")

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert {issue.code for issue in issues} == {"candidate.source_outside_selection"}


async def test_candidate_requires_complete_future_references() -> None:
    candidate = _candidate()
    attribute = _first_record(candidate, "attributes")
    attribute["logical_entity_name"] = "Missing"

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert "candidate.entity_missing" in {issue.code for issue in issues}


async def test_candidate_preserves_omitted_nested_records_and_rejects_locked_change() -> (
    None
):
    original = _candidate()
    applied = LogicalSection(
        submodels=(
            LogicalSubmodelRecord.model_validate_json(
                json.dumps(_first_record(original, "submodels")), strict=True
            ),
        ),
        entities=(
            LogicalEntityRecord.model_validate_json(
                json.dumps(_first_record(original, "entities")), strict=True
            ),
        ),
        attributes=(
            LogicalAttributeRecord.model_validate_json(
                json.dumps(_first_record(original, "attributes")), strict=True
            ),
        ),
        relationships=(),
    )
    locked_entity = applied.entities[0].model_copy(
        update={"logical_entity_is_locked": True}
    )
    applied = applied.model_copy(update={"entities": (locked_entity,)})
    candidate = deepcopy(original)
    entity = _first_record(candidate, "entities")
    entity["logical_entity_definition"] = "Changed by the agent."
    entity["sources"] = []

    issues = (
        await _validator(applied=applied).validate(cast(JsonValue, candidate))
    ).issues

    assert "candidate.record_locked" in {issue.code for issue in issues}


async def test_candidate_schema_forbids_agent_lock_authority() -> None:
    schema = _validator().output_schema()
    encoded = str(schema)

    assert "'const': False" in encoded

    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    entity["logical_entity_is_locked"] = True
    submodel = _first_record(candidate, "submodels")
    submodel["logical_submodel_is_locked"] = True
    issues = (await _validator().validate(cast(JsonValue, candidate))).issues
    assert [issue.code for issue in issues].count("candidate.lock_forbidden") == 2


async def test_candidate_forbids_agent_authored_audit_columns() -> None:
    candidate = _candidate()
    attribute = _first_record(candidate, "attributes")
    attribute["logical_attribute_is_audit_column"] = True

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert "candidate.audit_column_forbidden" in {issue.code for issue in issues}


async def test_candidate_reports_cross_field_failure_at_the_invalid_record() -> None:
    candidate = _candidate()
    attribute = _first_record(candidate, "attributes")
    attribute["logical_attribute_name"] = "never-copy-this-candidate-value"
    attribute["logical_attribute_is_surrogate_key"] = True
    validator = _validator()

    assert tuple(
        Draft202012Validator(validator.output_schema()).iter_errors(  # pyright: ignore[reportUnknownMemberType]
            cast(JsonValue, candidate)
        )
    ) == ()

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert len(issues) == 1
    assert issues[0].code == "candidate.cross_field_invalid"
    assert issues[0].path == ("attributes", 0)
    assert "never-copy-this-candidate-value" not in issues[0].model_dump_json()


def test_candidate_schema_includes_shared_logical_population_rules() -> None:
    schema = _validator().output_schema()
    definitions = cast(dict[str, object], schema["$defs"])
    attribute_schema = cast(dict[str, object], definitions["LogicalAttributeRecord"])

    assert any(
        "Use PascalCase; identifier Attributes end in ID" in rule
        for rule in cast(list[str], attribute_schema["x-gds-population-rules"])
    )


def test_parse_accepts_an_explicit_unchanged_candidate() -> None:
    assert (
        _validator().parse_validated(
            {
                "submodels": [],
                "entities": [],
                "attributes": [],
                "relationships": [],
            }
        )
        == ()
    )
