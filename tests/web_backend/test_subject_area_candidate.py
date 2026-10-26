"""Subject Area answers expand into canonical, lock-preserving, non-deleting changes."""

from __future__ import annotations

from typing import cast

import pytest
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    ProjectValidationIssue,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    PhysicalObjectKey,
    SubjectAreaRecord,
    SubjectAreaTableRecord,
)
from gds_etl_workbench.domain.snapshots.project import (
    ProjectChangeSetDataset,
    SubjectAreaSection,
)
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.subject_areas.candidate import (
    SubjectAreaCandidateValidator,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    MAX_COVERAGE_SOURCE_REFS,
    ValidationRepairRunner,
    load_default_agent_context_policy,
)

# table_index numbers the selection in order: t1, t2, t3.
TABLES = ("customer_raw", "order_raw", "invoice_raw")


def _key(name: str) -> dict[str, str]:
    return {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": name,
    }


def _area(
    name: str = "Sales",
    *,
    definition: str = "Customer orders.",
    is_active: bool = True,
    locked: bool = False,
) -> SubjectAreaRecord:
    return SubjectAreaRecord(
        subject_area_name=name,
        subject_area_definition=definition,
        subject_area_is_active=is_active,
        subject_area_is_locked=locked,
    )


def _member(
    table: str, *, area: str = "Sales", is_active: bool = True, locked: bool = False
) -> SubjectAreaTableRecord:
    return SubjectAreaTableRecord.model_validate(
        {
            "subject_area_name": area,
            **_key(table),
            "subject_area_table_is_active": is_active,
            "subject_area_table_is_locked": locked,
        }
    )


def _validator(
    *,
    names: tuple[str, ...] = TABLES,
    areas: tuple[SubjectAreaRecord, ...] = (),
    members: tuple[SubjectAreaTableRecord, ...] = (),
) -> SubjectAreaCandidateValidator:
    return SubjectAreaCandidateValidator(
        selected_object_keys=tuple(PhysicalObjectKey.model_validate(_key(name)) for name in names),
        applied=SubjectAreaSection(areas=areas, tables=members),
    )


def _answer(
    areas: list[JsonValue],
    *,
    unassigned: list[JsonValue] | None = None,
    retire: list[JsonValue] | None = None,
) -> JsonValue:
    return {"areas": areas, "unassigned": unassigned or [], "retire": retire or []}


async def _issues(
    validator: SubjectAreaCandidateValidator, answer: JsonValue
) -> list[tuple[str, tuple[str | int, ...]]]:
    return [(issue.code, issue.path) for issue in (await validator.validate(answer)).issues]


async def test_new_areas_expand_into_area_and_membership_records() -> None:
    validator = _validator()
    answer = _answer(
        [
            {"name": "Sales", "definition": "Customer orders.", "tables": ["t1", "t2"]},
            {"name": "Billing", "definition": "Invoices for orders.", "tables": ["t2", "t3"]},
        ]
    )

    assert await _issues(validator, answer) == []
    areas, tables = validator.parse_validated(answer)

    assert areas == StageProjectChange(
        dataset="subject_area",
        records=[
            _area().model_dump(mode="json"),
            _area("Billing", definition="Invoices for orders.").model_dump(mode="json"),
        ],
    )
    # A table may sit in several areas; new memberships are active and unlocked.
    assert tables == StageProjectChange(
        dataset="subject_area_table",
        records=[
            _member("customer_raw").model_dump(mode="json"),
            _member("order_raw").model_dump(mode="json"),
            _member("order_raw", area="Billing").model_dump(mode="json"),
            _member("invoice_raw", area="Billing").model_dump(mode="json"),
        ],
    )


async def test_listed_saved_area_replaces_its_unlocked_tables_and_keeps_locked_ones() -> None:
    validator = _validator(
        areas=(_area(),),
        members=(
            _member("customer_raw"),
            _member("order_raw", locked=True),
            _member("invoice_raw"),
        ),
    )
    # Omitting the definition keeps the saved one; the saved name spelling is kept.
    narrowed = _answer([{"name": "sales", "tables": ["t1"]}], unassigned=["t3"])
    redefined = _answer(
        [{"name": "Sales", "definition": "Orders and their customers.", "tables": ["t1", "t2"]}],
        unassigned=["t3"],
    )

    assert await _issues(validator, narrowed) == []
    # Unchanged records are not restaged: only the unlisted unlocked table leaves.
    assert validator.parse_validated(narrowed) == (
        StageProjectChange(
            dataset="subject_area_table",
            records=[_member("invoice_raw", is_active=False).model_dump(mode="json")],
        ),
    )
    assert validator.parse_validated(redefined) == (
        StageProjectChange(
            dataset="subject_area",
            records=[_area(definition="Orders and their customers.").model_dump(mode="json")],
        ),
        StageProjectChange(
            dataset="subject_area_table",
            records=[_member("invoice_raw", is_active=False).model_dump(mode="json")],
        ),
    )


async def test_locked_area_may_be_listed_unchanged_but_never_changed() -> None:
    validator = _validator(areas=(_area(locked=True),), members=(_member("customer_raw"),))
    unchanged = _answer([{"name": "Sales", "tables": ["t1"]}], unassigned=["t2", "t3"])

    changed: tuple[JsonValue, ...] = (
        {"name": "Sales", "definition": "Changed definition.", "tables": ["t1"]},
        {"name": "Sales", "tables": []},
    )

    assert await _issues(validator, unchanged) == []
    assert validator.parse_validated(unchanged) == ()
    for area in changed:
        answer = _answer([area], unassigned=["t2", "t3"])
        assert await _issues(validator, answer) == [("candidate.record_locked", ("areas", 0))]


async def test_a_locked_out_table_cannot_be_listed_again() -> None:
    # A reviewer kept invoice_raw (t3) out of Sales and locked that decision.
    validator = _validator(
        areas=(_area(),),
        members=(_member("customer_raw"), _member("invoice_raw", is_active=False, locked=True)),
    )
    relisted = _answer([{"name": "Sales", "tables": ["t1", "t3"]}], unassigned=["t2"])
    kept_out = _answer([{"name": "Sales", "tables": ["t1"]}], unassigned=["t2", "t3"])

    # The issue points at the table itself, and t3 must then be placed in unassigned.
    assert await _issues(validator, relisted) == [
        ("candidate.record_locked", ("areas", 0, "tables", 1)),
        ("candidate.table_unaccounted", ("unassigned",)),
    ]
    assert await _issues(validator, kept_out) == []
    assert validator.parse_validated(kept_out) == ()


async def test_retire_marks_the_area_and_its_active_tables_inactive() -> None:
    validator = _validator(
        areas=(_area(), _area("Billing", definition="Invoices for orders.")),
        members=(
            _member("customer_raw"),
            _member("order_raw", is_active=False),
            _member("order_raw", area="Billing"),
            _member("invoice_raw", area="Billing"),
        ),
    )
    answer = _answer([], unassigned=["t1"], retire=["sales"])

    assert await _issues(validator, answer) == []
    # Nothing is deleted; already inactive tables and other areas stay as saved.
    assert validator.parse_validated(answer) == (
        StageProjectChange(
            dataset="subject_area", records=[_area(is_active=False).model_dump(mode="json")]
        ),
        StageProjectChange(
            dataset="subject_area_table",
            records=[_member("customer_raw", is_active=False).model_dump(mode="json")],
        ),
    )


async def test_a_run_over_selected_tables_keeps_other_members_of_the_areas_it_changes() -> None:
    # This run selected customer_raw and order_raw; crm_customer is in Sales but not in the run.
    validator = _validator(
        names=("customer_raw", "order_raw"),
        areas=(_area(),),
        members=(_member("customer_raw"), _member("crm_customer")),
    )
    answer = _answer([{"name": "Sales", "tables": ["t2"]}], unassigned=["t1"])

    assert await _issues(validator, answer) == []
    # Only this run's tables change: customer_raw leaves Sales, order_raw joins, and the
    # member outside the run is not touched.
    assert validator.parse_validated(answer) == (
        StageProjectChange(
            dataset="subject_area_table",
            records=[
                _member("order_raw").model_dump(mode="json"),
                _member("customer_raw", is_active=False).model_dump(mode="json"),
            ],
        ),
    )


@pytest.mark.parametrize(("still_in_scope", "accepted"), [(True, False), (False, True)])
async def test_a_partial_run_cannot_retire_an_area_with_scope_tables_outside_it(
    still_in_scope: bool, accepted: bool
) -> None:
    # crm_customer is an active Sales member outside this run; it may have left the scope.
    scope = {
        tuple(value.casefold() for value in _key(name).values())
        for name in ("customer_raw", "order_raw", *(("crm_customer",) if still_in_scope else ()))
    }
    validator = SubjectAreaCandidateValidator(
        selected_object_keys=tuple(
            PhysicalObjectKey.model_validate(_key(name)) for name in ("customer_raw", "order_raw")
        ),
        applied=SubjectAreaSection(
            areas=(_area(),), tables=(_member("customer_raw"), _member("crm_customer"))
        ),
        scope_object_keys=frozenset(scope),
    )
    answer = _answer([], unassigned=["t1", "t2"], retire=["Sales"])

    # A refused retire keeps Sales active, so t1 is still in it and cannot be unassigned.
    assert await _issues(validator, answer) == (
        []
        if accepted
        else [
            ("candidate.retire_outside_run", ("retire", 0)),
            ("candidate.unassigned_conflict", ("unassigned", 0)),
        ]
    )


@pytest.mark.parametrize(
    ("areas", "members", "answer", "expected"),
    [
        pytest.param(
            (),
            (),
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2", "t3"]}],
                retire=["Old"],
            ),
            [("candidate.record_missing", ("retire", 0))],
            id="unknown",
        ),
        pytest.param(
            (_area("Archive", locked=True),),
            (),
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2", "t3"]}],
                retire=["Archive"],
            ),
            [("candidate.record_locked", ("retire", 0))],
            id="locked_area",
        ),
        pytest.param(
            (_area("Archive"),),
            (_member("invoice_raw", area="Archive", locked=True),),
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2"]}],
                retire=["Archive"],
            ),
            [("candidate.record_locked", ("retire", 0))],
            id="locked_table",
        ),
        pytest.param(
            (_area("Archive"),),
            (),
            _answer([{"name": "Archive", "tables": ["t1", "t2", "t3"]}], retire=["archive"]),
            # The conflicting area is not expanded, so its tables are not placed either.
            [
                ("candidate.retire_conflict", ("areas", 0, "name")),
                ("candidate.table_unaccounted", ("unassigned",)),
            ],
            id="listed_and_retired",
        ),
    ],
)
async def test_retire_rejects_unknown_locked_and_listed_areas(
    areas: tuple[SubjectAreaRecord, ...],
    members: tuple[SubjectAreaTableRecord, ...],
    answer: JsonValue,
    expected: list[tuple[str, tuple[str | int, ...]]],
) -> None:
    assert await _issues(_validator(areas=areas, members=members), answer) == expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param(
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t9"]}],
                unassigned=["t2", "t3"],
            ),
            [("candidate.table_unknown", ("areas", 0, "tables", 1))],
            id="unknown_table",
        ),
        pytest.param(
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2", "t3", "t1"]}]
            ),
            [("candidate.duplicate_record", ("areas", 0, "tables", 3))],
            id="duplicate_table",
        ),
        pytest.param(
            _answer(
                [
                    {"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2", "t3"]},
                    {"name": " SALES", "definition": "Orders again.", "tables": ["t1"]},
                ]
            ),
            [("candidate.duplicate_record", ("areas", 1, "name"))],
            id="duplicate_area",
        ),
        pytest.param(
            _answer([{"name": "Sales", "tables": ["t1"]}], unassigned=["t2", "t3"]),
            [
                ("candidate.new_record_field_required", ("areas", 0, "definition")),
                ("candidate.table_unaccounted", ("unassigned",)),
            ],
            id="new_area_without_definition",
        ),
        pytest.param(
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2", "t3"]}],
                unassigned=["t4"],
            ),
            [("candidate.table_unknown", ("unassigned", 0))],
            id="unknown_unassigned_table",
        ),
        pytest.param(
            _answer(
                [{"name": "Sales", "definition": "Orders.", "tables": ["t1", "t2"]}],
                unassigned=["t3", "t2"],
            ),
            [("candidate.unassigned_conflict", ("unassigned", 1))],
            id="assigned_and_unassigned",
        ),
    ],
)
async def test_answer_mistakes_are_reported_at_the_agents_own_paths(
    answer: JsonValue, expected: list[tuple[str, tuple[str | int, ...]]]
) -> None:
    assert await _issues(_validator(), answer) == expected


async def test_area_size_is_not_limited() -> None:
    names = tuple(f"table_{position}" for position in range(1, 61))
    every_table: list[JsonValue] = [f"t{position}" for position in range(1, 61)]

    assert (
        await _issues(
            _validator(names=names),
            _answer([{"name": "Sales", "definition": "Orders.", "tables": every_table}]),
        )
        == []
    )


async def test_every_table_ends_in_an_active_area_or_unassigned() -> None:
    names = tuple(f"table_{position}" for position in range(1, 61))
    unplaced = (await _validator(names=names).validate(_answer([]))).issues
    # Unlisted saved areas stay as saved, so their active tables are placed.
    saved = _validator(areas=(_area(),), members=(_member("customer_raw"),))
    retired = _validator(
        areas=(_area(is_active=False),), members=(_member("customer_raw", is_active=False),)
    )
    remaining = _answer([], unassigned=["t2", "t3"])

    assert len(unplaced) == 1
    assert (unplaced[0].code, unplaced[0].path) == ("candidate.table_unaccounted", ("unassigned",))
    assert unplaced[0].message.startswith("60 of 60 tables are in no active area")
    # Source refs stay bounded and name tables by id and physical key, never row values.
    assert len(unplaced[0].source_refs) == MAX_COVERAGE_SOURCE_REFS
    assert unplaced[0].source_refs[0] == {"table": "t1", **_key("table_1")}
    assert await _issues(saved, remaining) == []
    assert saved.parse_validated(remaining) == ()
    retired_issues = (await retired.validate(remaining)).issues
    assert [issue.source_refs for issue in retired_issues] == [
        ({"table": "t1", **_key("customer_raw")},)
    ]


async def test_parse_validated_emits_only_changed_records_and_rejects_invalid_answers() -> None:
    validator = _validator(areas=(_area(),), members=(_member("customer_raw"),))
    resubmitted = _answer(
        [{"name": "Sales", "definition": "Customer orders.", "tables": ["t1"]}],
        unassigned=["t2", "t3"],
    )

    assert await _issues(validator, resubmitted) == []
    assert validator.parse_validated(resubmitted) == ()
    with pytest.raises(InvalidRequestError):
        validator.parse_validated(_answer([], unassigned=["t2"]))


async def test_agent_issues_map_staged_records_back_to_answer_paths() -> None:
    validator = _validator(areas=(_area("Old"),), members=(_member("invoice_raw", area="Old"),))
    answer = _answer(
        [
            {"name": "Sales", "definition": "Customer orders.", "tables": ["t1"]},
            {"name": "Billing", "definition": "Invoices.", "tables": ["t2", "t3"]},
        ],
        retire=["Old"],
    )
    staged: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
        change.dataset: change.records for change in validator.parse_validated(answer)
    }

    def issue(code: str, dataset: str, record_number: int | None) -> ProjectValidationIssue:
        return ProjectValidationIssue(
            code=code,
            dataset=dataset,
            record_number=record_number,
            fields=("object_name",),
            message=f"{code} message.",
        )

    translated = validator.agent_issues(
        answer,
        (
            # Staged order: Sales/t1, Billing/t2, Billing/t3, then the retired Old/t3.
            issue("record_schema_invalid", "subject_area_table", 3),
            issue("record_schema_invalid", "subject_area_table", 4),
            issue("duplicate_canonical_key", "subject_area", 1),
            # Whole-graph issues carry no record number, or one outside the staged list.
            issue("record_locked", "subject_area_table", None),
            issue("reference_not_found", "subject_area", 99),
            issue("project_input_reference_invalid", "project_input_scope", None),
        ),
        staged,
    )

    assert [(item.code, item.path, item.message) for item in translated] == [
        ("candidate.record_schema_invalid", ("areas", 1), "record_schema_invalid message."),
        ("candidate.record_schema_invalid", ("retire", 0), "record_schema_invalid message."),
        ("candidate.duplicate_canonical_key", ("areas", 0), "duplicate_canonical_key message."),
        ("candidate.record_locked", ("areas", "tables"), "record_locked message."),
        ("candidate.reference_not_found", ("areas",), "reference_not_found message."),
        (
            "candidate.project_input_reference_invalid",
            ("project_input_scope", "object_name"),
            "project_input_reference_invalid message.",
        ),
    ]


def test_output_schema_has_no_column_cap() -> None:
    schema = _validator().output_schema()

    assert set(cast(dict[str, JsonValue], schema["properties"])) == {
        "areas",
        "unassigned",
        "retire",
    }
    assert "column" not in cast(str, schema["description"])


async def test_large_answer_repairs_every_area_after_bounded_feedback() -> None:
    validator = _validator(names=("customer_raw",))
    invalid = _answer(
        [
            {"name": f"Area {index}", "definition": "Orders.", "tables": ["t2"]}
            for index in range(201)
        ]
    )
    corrected = _answer(
        [
            {"name": f"Area {index}", "definition": "Orders.", "tables": ["t1"]}
            for index in range(201)
        ]
    )
    requests: list[AgentExecutionRequest] = []

    class Executor:
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            requests.append(request)
            return AgentExecutionResult(
                candidate=invalid if len(requests) == 1 else corrected,
                turn_count=1,
                tool_call_count=0,
            )

    assert len((await validator.validate(invalid)).issues) == 200
    result = await ValidationRepairRunner(
        executor=Executor(), policy=load_default_agent_context_policy()
    ).run(
        request=AgentExecutionRequest(
            workflow_run_id=1048,
            workflow="subject_area",
            stage="candidate_authoring",
            execution_mode="one_shot",
            selection=AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                reasoning_effort_code="medium",
                max_turns=6,
                validation_retry_count=2,
            ),
            system_prompt="Group the Input Scope into Subject Areas.",
            instruction_prompt="Repair unknown table ids.",
            context={},
            output_schema=validator.output_schema(),
        ),
        validator=validator,
    )

    assert result.attempt_count == 2
    repair = cast(dict[str, JsonValue], requests[1].context)["repair"]
    assert isinstance(repair, dict)
    assert len(cast(list[JsonValue], repair["validation_issues"])) == 100
    areas, tables = validator.parse_validated(result.candidate)
    assert len(areas.records) == len(tables.records) == 201
