# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    LogicalAttributeKey,
    LogicalEntityKey,
)
from gds_etl_workbench.domain.snapshots.project import DimensionalSection
from gds_etl_workbench.domain.snapshots.project_guidance import (
    project_dataset_population_rules,
)
from pydantic import JsonValue
from tests.web_backend.test_dimensional_policy import (
    _audit_template,
    _projected_baseline,
    _technical_template,
)

from gds_workbench_api.features.dimensional.candidate import (
    DimensionalCandidateValidator,
)
from gds_workbench_api.features.dimensional.policy import (
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
)


def _object(name: str = "dim_customer") -> LogicalEntityKey:
    return LogicalEntityKey(logical_entity_schema_name="silver_nwa", logical_entity_name=name)


def _attribute(name: str = "customer_id") -> LogicalAttributeKey:
    return LogicalAttributeKey(**_object().model_dump(), logical_attribute_name=name)


def _candidate() -> dict[str, object]:
    return {
        "entities": [
            {
                "dimensional_entity_schema_name": "gold",
                "dimensional_entity_name": "Customer Dimension",
                "dimensional_entity_definition": "One customer.",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "dimensional_entity_dependency_order": 0,
                "dimensional_entity_is_active": True,
                "dimensional_entity_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "logical_entity",
                        "source_logical_entity": _object().model_dump(mode="json"),
                        "rationale": "Logical customer source.",
                        "is_active": True,
                        "is_locked": False,
                    }
                ],
            }
        ],
        "attributes": [
            {
                "dimensional_entity_schema_name": "gold",
                "dimensional_entity_name": "Customer Dimension",
                "dimensional_attribute_name": "Customer ID",
                "dimensional_attribute_definition": "Customer identifier.",
                "dimensional_attribute_data_type": "bigint",
                "dimensional_attribute_is_nullable": False,
                "dimensional_attribute_ordinal_position": 1,
                "dimensional_attribute_is_natural_key": True,
                "dimensional_attribute_is_surrogate_key": False,
                "dimensional_attribute_is_audit_column": False,
                "dimensional_attribute_is_active": True,
                "dimensional_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "logical_attribute",
                        "source_logical_attribute": _attribute().model_dump(mode="json"),
                        "rationale": "Silver business key.",
                        "is_active": True,
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
    context_record_ids: tuple[str, ...] = (),
    fact_types: tuple[str, ...] = ("transaction", "periodic_snapshot"),
) -> DimensionalCandidateValidator:
    return DimensionalCandidateValidator(
        selected_entity_keys=(_object(),),
        selected_attribute_keys=(_attribute(),),
        context_record_ids=context_record_ids,
        applied=applied,
        fact_types=fact_types,
    )


def _first_record(candidate: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], cast(list[object], candidate[key])[0])


async def test_valid_candidate_normalizes_to_exact_dimensional_changes() -> None:
    candidate = cast(JsonValue, _candidate())

    assert (await _validator().validate(candidate)).issues == ()
    changes = _validator().parse_validated(candidate)

    assert [change.dataset for change in changes] == [
        "dimensional_entity",
        "dimensional_attribute",
    ]
    assert sum(len(change.records) for change in changes) == 2


async def test_empty_answer_is_valid_and_changes_nothing() -> None:
    empty = cast(JsonValue, {"entities": [], "attributes": [], "relationships": []})
    validator = _validator(applied=_applied())

    assert (await validator.validate(empty)).issues == ()
    assert validator.parse_validated(empty) == ()
    # Saved support still counts toward coverage.
    assert validator.validate_coverage(empty) == ()


async def test_fact_type_must_be_an_active_listed_code() -> None:
    candidate = _candidate()
    fact = deepcopy(_first_record(candidate, "entities"))
    fact.update(
        {
            "dimensional_entity_name": "Sales Fact",
            "dimensional_entity_type": "fact",
            "dimensional_fact_type": "accumulating_snapshot",
            "dimensional_entity_grain_definition": "One sale.",
        }
    )
    cast(list[object], candidate["entities"]).append(fact)
    validator = _validator(fact_types=("transaction", "periodic_snapshot"))

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert [(issue.code, issue.path) for issue in issues] == [
        ("candidate.fact_type_unknown", ("entities", 1, "dimensional_fact_type"))
    ]
    # The answer schema offers only the active codes.
    entity_schema = cast(dict[str, Any], validator.output_schema()["$defs"])[
        "DimensionalEntityRecord"
    ]
    assert entity_schema["properties"]["dimensional_fact_type"]["anyOf"][0] == {
        "enum": ["transaction", "periodic_snapshot"]
    }
    fact["dimensional_fact_type"] = "periodic_snapshot"
    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()


async def test_dimensional_coverage_rejects_ignored_selected_logical_entities() -> None:
    validator = DimensionalCandidateValidator(
        selected_entity_keys=(
            _object(),
            *(_object(f"entity_{i}") for i in range(1, 27)),
        ),
        selected_attribute_keys=(_attribute(),),
        context_record_ids=(),
        applied=None,
    )
    issues = validator.validate_coverage(cast(JsonValue, _candidate()))
    assert len(issues) == 1
    assert issues[0].code == "candidate.entity_coverage_incomplete"
    assert "26 of 27" in issues[0].message
    assert _validator(applied=_applied()).validate_coverage(cast(JsonValue, _candidate())) == ()


async def test_candidate_rejects_silver_evidence_outside_frozen_selection() -> None:
    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    source = cast(dict[str, object], cast(list[object], entity["sources"])[0])
    source["source_logical_entity"] = _object("unselected_silver").model_dump(mode="json")

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert {issue.code for issue in issues} == {"candidate.source_outside_selection"}


async def test_candidate_rejects_context_evidence_outside_frozen_context() -> None:
    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    entity["sources"] = [
        {
            "support_source_type": "context_record",
            "context_record": {"context_record_id": "00000000-0000-4000-8000-000000000098"},
            "rationale": "Business Context record.",
            "is_active": True,
            "is_locked": False,
        }
    ]
    attribute = _first_record(candidate, "attributes")
    attribute["sources"] = [
        {
            "support_source_type": "context_record",
            "context_record": {"context_record_id": "00000000-0000-4000-8000-000000000099"},
            "rationale": None,
            "is_active": True,
            "is_locked": False,
        }
    ]

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert [issue.code for issue in issues].count("candidate.context_unavailable") == 2


async def test_candidate_requires_complete_future_references() -> None:
    candidate = _candidate()
    attribute = _first_record(candidate, "attributes")
    attribute["dimensional_entity_name"] = "Missing Dimension"
    candidate["relationships"] = [
        {
            "from_dimensional_entity_schema_name": "gold",
            "from_dimensional_entity_name": "Customer Dimension",
            "from_dimensional_attribute_name": "Customer ID",
            "to_dimensional_entity_schema_name": "gold",
            "to_dimensional_entity_name": "Missing Dimension",
            "to_dimensional_attribute_name": "Missing ID",
            "dimensional_relationship_role_name": None,
            "dimensional_relationship_basis": "Expected dimensional join.",
            "dimensional_relationship_is_active": True,
            "dimensional_relationship_is_locked": False,
        }
    ]

    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert {"candidate.entity_missing", "candidate.relationship_endpoint_missing"} <= {
        issue.code for issue in issues
    }


async def test_relationship_is_identified_by_its_child_foreign_key() -> None:
    from tests.web_backend.test_dimensional_executor import (
        _candidate as complete_candidate,
    )

    candidate = cast(dict[str, Any], complete_candidate())
    sales = _object("sales_customer")
    validator = DimensionalCandidateValidator(
        selected_entity_keys=(sales,),
        selected_attribute_keys=tuple(
            LogicalAttributeKey(**sales.model_dump(), logical_attribute_name=name)
            for name in ("customer_id", "sale_customer_id")
        ),
        context_record_ids=(),
        applied=None,
        fact_types=("transaction",),
    )
    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    # A second role from the same business key needs its own foreign-key Attribute.
    second_role = deepcopy(candidate["relationships"][0])
    second_role["dimensional_relationship_role_name"] = "Ship To Customer"
    candidate["relationships"].append(second_role)

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert {issue.code for issue in issues} == {"candidate.duplicate_canonical_key"}


async def test_candidate_omission_preserves_applied_nested_records() -> None:
    original = _candidate()
    candidate = deepcopy(original)
    entity = _first_record(candidate, "entities")
    entity["sources"] = []
    attribute = _first_record(candidate, "attributes")
    attribute["sources"] = []
    validator = _validator(applied=_applied(original))

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    assert validator.parse_validated(cast(JsonValue, candidate)) == ()


async def test_candidate_schema_forbids_agent_lock_authority() -> None:
    assert "'const': False" in str(_validator().output_schema())

    candidate = _candidate()
    entity = _first_record(candidate, "entities")
    entity["dimensional_entity_is_locked"] = True
    source = cast(dict[str, object], cast(list[object], entity["sources"])[0])
    source["is_locked"] = True
    attribute = _first_record(candidate, "attributes")
    attribute["dimensional_attribute_is_locked"] = True
    issues = (await _validator().validate(cast(JsonValue, candidate))).issues

    assert [issue.code for issue in issues].count("candidate.lock_forbidden") == 3


def test_candidate_schema_replaces_only_the_shared_policy_attribute_rule() -> None:
    schema = _validator().output_schema()
    definitions = cast(dict[str, object], schema["$defs"])
    attribute_schema = cast(dict[str, object], definitions["DimensionalAttributeRecord"])
    rules = cast(list[str], attribute_schema["x-gds-population-rules"])

    # The backend projects technical and audit Attributes and rejects authored ones.
    shared = project_dataset_population_rules("dimensional_attribute")
    changed = [(old, new) for old, new in zip(shared, rules, strict=True) if old != new]
    assert len(changed) == 1
    assert "including technical, audit" in changed[0][0]
    assert "the backend projects surrogate-key, foreign-key" in changed[0][1]


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


async def test_retiring_an_entity_retires_its_attributes_and_the_relationships_using_them() -> None:
    baseline = _projected_baseline()
    # A locked Attribute is a user's decision and stays as it is.
    baseline = baseline.model_copy(
        update={
            "attributes": tuple(
                row.model_copy(update={"dimensional_attribute_is_locked": True})
                if row.dimensional_attribute_name == "Customer Name"
                else row
                for row in baseline.attributes
            )
        }
    )
    dimension = baseline.entities[0].model_dump(mode="json")
    dimension["dimensional_entity_is_active"] = False
    validator = _validator(applied=baseline)
    candidate = cast(JsonValue, {"entities": [dimension], "attributes": [], "relationships": []})

    assert (await validator.validate(candidate)).issues == ()
    changes = {change.dataset: change.records for change in validator.parse_validated(candidate)}

    assert [
        (row["dimensional_entity_name"], row["dimensional_entity_is_active"])
        for row in changes["dimensional_entity"]
    ] == [("Customer Dimension", False)]
    assert sorted(
        (
            row["dimensional_entity_name"],
            row["dimensional_attribute_name"],
            row["dimensional_attribute_is_active"],
        )
        for row in changes["dimensional_attribute"]
    ) == [
        ("Customer Dimension", "Customer Dimension key", False),
        ("Customer Dimension", "Loaded At", False),
        # The Fact's edge to the retired Dimension retires its projected foreign key.
        ("Sales Fact", "Bill To Customer key", False),
    ]
    assert [
        (
            row["from_dimensional_entity_name"],
            row["from_dimensional_attribute_name"],
            row["dimensional_relationship_is_active"],
        )
        for row in changes["dimensional_relationship"]
    ] == [("Sales Fact", "Bill To Customer key", False)]


async def test_renaming_a_dimension_repoints_saved_fact_edges_to_the_new_record() -> None:
    """Optimize adds a missing Dim prefix as a new record and retires the old one."""
    baseline = _projected_baseline()
    old = baseline.entities[0].model_dump(mode="json")
    renamed = {**old, "dimensional_entity_name": "DimCustomer Dimension"}
    retired = {**old, "dimensional_entity_is_active": False}
    business = next(
        row.model_dump(mode="json")
        for row in baseline.attributes
        if row.dimensional_attribute_name == "Customer Name"
    )
    # The saved Fact edge keeps its foreign key and changes only its parent.
    edge = {
        **baseline.relationships[0].model_dump(mode="json"),
        "to_dimensional_entity_name": "DimCustomer Dimension",
        "to_dimensional_attribute_name": "Customer Name",
    }
    candidate = cast(
        JsonValue,
        {
            "entities": [renamed, retired],
            "attributes": [{**business, "dimensional_entity_name": "DimCustomer Dimension"}],
            "relationships": [edge],
        },
    )
    validator = _validator(applied=baseline)
    assert (await validator.validate(candidate)).issues == ()

    projected = project_dimensional_foreign_key_policy(
        changes=project_dimensional_gold_policy(
            changes=validator.parse_validated(candidate),
            applied=baseline,
            raw_technical_template=_technical_template(),
            raw_audit_template=_audit_template(),
        ),
        applied=baseline,
        raw_technical_template=_technical_template(),
    )
    changes = {change.dataset: change.records for change in projected}

    assert sorted(
        (
            row["dimensional_entity_name"],
            row["dimensional_attribute_name"],
            row["dimensional_attribute_is_active"],
        )
        for row in changes["dimensional_attribute"]
    ) == [
        ("Customer Dimension", "Customer Dimension key", False),
        ("Customer Dimension", "Customer Name", False),
        ("Customer Dimension", "Loaded At", False),
        # Without its Dim prefix the new key keeps the old name, so the Fact keeps its key.
        ("DimCustomer Dimension", "Customer Dimension key", True),
        ("DimCustomer Dimension", "Customer Name", True),
        ("DimCustomer Dimension", "Loaded At", True),
        # Only its definition changes, to name the new parent.
        ("Sales Fact", "Bill To Customer key", True),
    ]
    assert [
        (
            row["from_dimensional_attribute_name"],
            row["to_dimensional_entity_name"],
            row["to_dimensional_attribute_name"],
            row["dimensional_relationship_is_active"],
        )
        for row in changes["dimensional_relationship"]
    ] == [("Bill To Customer key", "DimCustomer Dimension", "Customer Dimension key", True)]

async def test_retiring_a_saved_fact_edge_retires_its_projected_foreign_key() -> None:
    baseline = _projected_baseline()
    edge = baseline.relationships[0].model_dump(mode="json")
    edge["dimensional_relationship_is_active"] = False
    validator = _validator(applied=baseline)
    candidate = cast(JsonValue, {"entities": [], "attributes": [], "relationships": [edge]})

    assert (await validator.validate(candidate)).issues == ()
    changes = {change.dataset: change.records for change in validator.parse_validated(candidate)}

    assert [
        (
            row["dimensional_entity_name"],
            row["dimensional_attribute_name"],
            row["dimensional_attribute_is_active"],
        )
        for row in changes["dimensional_attribute"]
    ] == [("Sales Fact", "Bill To Customer key", False)]
    assert [
        row["dimensional_relationship_is_active"] for row in changes["dimensional_relationship"]
    ] == [False]
    assert set(changes) == {"dimensional_attribute", "dimensional_relationship"}
    # A locked foreign key is not retired with its edge.
    locked = baseline.model_copy(
        update={
            "attributes": tuple(
                row.model_copy(update={"dimensional_attribute_is_locked": True})
                if row.dimensional_attribute_name == "Bill To Customer key"
                else row
                for row in baseline.attributes
            )
        }
    )
    assert [change.dataset for change in _validator(applied=locked).parse_validated(candidate)] == [
        "dimensional_relationship"
    ]


async def test_candidate_forbids_flagged_and_configured_policy_columns() -> None:
    candidate = _candidate()
    business = _first_record(candidate, "attributes")
    audit = deepcopy(business)
    audit.update(
        {
            "dimensional_attribute_name": "Custom audit",
            "dimensional_attribute_is_audit_column": True,
        }
    )
    surrogate = deepcopy(business)
    surrogate.update(
        {
            "dimensional_attribute_name": "Custom identity",
            "dimensional_attribute_is_natural_key": False,
            "dimensional_attribute_is_surrogate_key": True,
        }
    )
    configured = deepcopy(business)
    configured.update(
        {
            "dimensional_attribute_name": "Loaded At",
            "dimensional_attribute_is_natural_key": False,
        }
    )
    history = deepcopy(configured)
    history["dimensional_attribute_name"] = "Effective From"
    cast(list[object], candidate["attributes"]).extend((audit, surrogate, configured, history))
    validator = DimensionalCandidateValidator(
        selected_entity_keys=(_object(),),
        selected_attribute_keys=(_attribute(),),
        context_record_ids=(),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    issues = (await validator.validate(cast(JsonValue, candidate))).issues
    assert [issue.code for issue in issues].count("candidate.policy_column_forbidden") == 4


async def test_candidate_forbids_foreign_key_derived_from_effective_relationship() -> None:
    from tests.web_backend.test_dimensional_executor import (
        _candidate as complete_candidate,
    )

    candidate = cast(dict[str, object], complete_candidate())
    attributes = cast(list[dict[str, object]], candidate["attributes"])
    foreign = deepcopy(attributes[1])
    foreign.update(
        {
            "dimensional_attribute_name": "Bill To Customer key",
            "dimensional_attribute_is_natural_key": False,
        }
    )
    attributes.append(foreign)
    validator = DimensionalCandidateValidator(
        selected_entity_keys=(_object(),),
        selected_attribute_keys=(_attribute(),),
        context_record_ids=(),
        applied=None,
        fact_types=("transaction",),
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    issues = (await validator.validate(cast(JsonValue, candidate))).issues
    assert any(
        issue.code == "candidate.policy_column_forbidden" and issue.path[:2] == ("attributes", 2)
        for issue in issues
    )


async def test_candidate_preserves_existing_foreign_key_after_template_name_changes() -> None:
    baseline = _projected_baseline()
    renamed_attributes = tuple(
        row.model_copy(update={"dimensional_attribute_name": "Legacy Customer FK"})
        if row.dimensional_attribute_name == "Bill To Customer key"
        else row
        for row in baseline.attributes
    )
    baseline = baseline.model_copy(
        update={
            "attributes": renamed_attributes,
            "relationships": tuple(
                row.model_copy(update={"from_dimensional_attribute_name": "Legacy Customer FK"})
                for row in baseline.relationships
            ),
        }
    )
    proposed = next(
        row for row in renamed_attributes if row.dimensional_attribute_name == "Legacy Customer FK"
    )
    proposed = proposed.model_copy(
        update={"dimensional_attribute_definition": "Proposed business edit."}
    )
    validator = DimensionalCandidateValidator(
        selected_entity_keys=(_object(),),
        selected_attribute_keys=(),
        context_record_ids=(),
        applied=baseline,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    issues = (
        await validator.validate(
            {
                "entities": [],
                "attributes": [proposed.model_dump(mode="json")],
                "relationships": [],
            }
        )
    ).issues
    assert any(issue.code == "candidate.policy_column_forbidden" for issue in issues)
