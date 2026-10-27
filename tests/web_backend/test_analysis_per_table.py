# pyright: reportPrivateUsage=false
"""Per-table Analysis: prompt inputs, answer checks, duplicate handling and the run loop."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import AnalysisResultRecord, PhysicalAttributeKey
from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.analysis.candidate import (
    AnalysisTableCandidateValidator,
    merge_table_findings,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    SelectedObjectContext,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    INPUT_EXAMPLES,
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import (
    analysis_table_inputs,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from jsonschema import Draft202012Validator
from pydantic import JsonValue

from tests.web_backend import test_analysis_executor as executor
from tests.web_backend.test_analysis_executor import (
    _CLAIM_TOKEN,
    _context_bundle,
    _principal,
)

_KEY = {
    "tenant_code": "GDS",
    "system_code": "WAREHOUSE",
    "connection_code": "MAIN",
    "object_schema": "bronze",
}


def _saved(
    *, from_object: str, to_object: str, kind: str = "reference", locked: bool = False
) -> dict[str, Any]:
    return {
        **{f"from_{name}": value for name, value in _KEY.items()},
        "from_object_name": from_object,
        "from_attribute_name": "CustomerCode",
        **{f"to_{name}": value for name, value in _KEY.items()},
        "to_object_name": to_object,
        "to_attribute_name": "CustomerCode",
        "relationship_kind": kind,
        "inferred_cardinality": "many_to_one",
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
        "analysis_result_is_locked": locked,
    }


def _example_context(*saved: dict[str, Any]) -> dict[str, Any]:
    """Orders (t1) and Customers (t2) from the registered Analysis input examples."""
    return {
        "prompt_inputs": deepcopy(INPUT_EXAMPLES["analysis"]),
        "analysis_relationships": list(saved),
    }


def _selected_keys() -> tuple[PhysicalAttributeKey, ...]:
    return tuple(
        PhysicalAttributeKey(**_KEY, object_name=name, attribute_name="CustomerCode")
        for name in ("Orders", "Customers")
    )


def _link(
    from_name: str = "CustomerCode",
    to: str = "t2.CustomerCode",
    cardinality: str = "many_to_one",
    kind: str = "reference",
) -> dict[str, JsonValue]:
    return {
        "from_attribute_name": from_name,
        "to": to,
        "relationship_kind": kind,
        "inferred_cardinality": cardinality,
    }


def test_each_table_gets_its_inputs_and_the_shared_key_directory() -> None:
    saved = _saved(from_object="Orders", to_object="Customers")
    tables = analysis_table_inputs(_example_context(saved))

    assert [table["focus_table"]["table"] for table in tables] == ["t1", "t2"]
    contracts = workflow_input_contracts("analysis_per_table")
    for inputs in tables:
        assert list(inputs) == list(contracts)
        for name, spec in contracts.items():
            assert cast(Any, Draft202012Validator(spec["schema"])).is_valid(inputs[name]), name
    orders, customers = tables
    # Every call sees the same directory, the focus table included.
    assert orders["key_directory"] == customers["key_directory"]
    directory = {entry["table"]: entry for entry in orders["key_directory"]}
    # Orders.CustomerCode repeats and has no key flag; Customers.CustomerCode is a key.
    assert directory["t1"]["key_columns"] == []
    assert [column["attribute_name"] for column in directory["t1"]["other_columns"]] == [
        "CustomerCode"
    ]
    key_column = directory["t2"]["key_columns"][0]
    assert key_column["attribute_name"] == "CustomerCode"
    assert key_column["attribute_data_type"] == "VARCHAR"
    assert key_column["attribute_inferred_data_type"] == "VARCHAR"
    assert key_column["profile"]["distinct_count"] == key_column["profile"]["non_null_count"]
    assert directory["t2"]["other_columns"] == []
    # Each Bronze table names the System its data comes from, through its lineage.
    assert [entry["source_systems"] for entry in orders["key_directory"]] == [["ERP"], ["ERP"]]
    assert orders["focus_table"]["source_systems"] == ["ERP"]
    # Lineage and saved findings are cut to the focus table.
    assert [entry["target"]["object_name"] for entry in orders["ingestion_mapping"]] == ["Orders"]
    assert [entry["target"]["object_name"] for entry in customers["ingestion_mapping"]] == [
        "Customers"
    ]
    assert orders["saved_relationships"] == customers["saved_relationships"]
    assert orders["saved_relationships"][0]["from"] == "t1.CustomerCode"
    assert orders["saved_relationships"][0]["to"] == "t2.CustomerCode"


def test_saved_finding_to_a_table_outside_the_run_is_left_out() -> None:
    saved = _saved(from_object="Orders", to_object="Elsewhere")
    tables = analysis_table_inputs(_example_context(saved))
    assert all(table["saved_relationships"] == [] for table in tables)


@pytest.mark.asyncio
async def test_answer_expands_to_full_keys_with_registered_spelling() -> None:
    inputs = analysis_table_inputs(_example_context())[0]
    validator = AnalysisTableCandidateValidator(
        inputs=inputs, selected_attribute_keys=_selected_keys(), applied=()
    )
    candidate: JsonValue = {
        "relationships": [_link(from_name=" customercode ", to="t2.CUSTOMERCODE")]
    }

    assert (await validator.validate(candidate)).issues == ()
    (change,) = validator.parse_validated(candidate)
    (record,) = change.records
    assert change.dataset == "analysis_result"
    assert record["from_object_name"] == "Orders"
    assert record["from_attribute_name"] == "CustomerCode"
    assert record["to_object_name"] == "Customers"
    assert record["to_attribute_name"] == "CustomerCode"
    assert record["analysis_result_status"] == "active"
    assert "relationship_basis" not in record
    schema = validator.output_schema()
    assert "relationship_basis" not in str(schema)


@pytest.mark.asyncio
async def test_answer_must_start_in_the_focus_table_and_end_at_a_shown_column() -> None:
    inputs = analysis_table_inputs(_example_context())[0]
    validator = AnalysisTableCandidateValidator(
        inputs=inputs, selected_attribute_keys=_selected_keys(), applied=()
    )
    candidate: JsonValue = {
        "relationships": [
            _link(from_name="OrderID"),
            _link(to="t9.CustomerCode"),
            _link(to="t2.CustomerName"),
            _link(to="t1.CustomerCode"),
        ]
    }

    issues = (await validator.validate(candidate)).issues
    assert [(issue.code, issue.path) for issue in issues] == [
        ("candidate.from_outside_focus_table", ("relationships", 0, "from_attribute_name")),
        ("candidate.to_not_shown", ("relationships", 1, "to")),
        ("candidate.to_not_shown", ("relationships", 2, "to")),
        # A column cannot point at itself; the full-record check reports the original path.
        ("candidate.record_schema_invalid", ("relationships", 3)),
    ]
    with pytest.raises(InvalidRequestError):
        validator.parse_validated(candidate)
    assert (await validator.validate({"relationships": [{"to": "t2.x"}]})).issues[
        0
    ].code == "candidate.schema_invalid"


@pytest.mark.asyncio
async def test_locked_saved_finding_cannot_change_in_a_per_table_answer() -> None:
    saved = _saved(from_object="Orders", to_object="Customers", locked=True)
    inputs = analysis_table_inputs(_example_context(saved))[0]
    validator = AnalysisTableCandidateValidator(
        inputs=inputs,
        selected_attribute_keys=_selected_keys(),
        applied=(AnalysisResultRecord.model_validate(saved),),
    )
    issues = (await validator.validate({"relationships": [_link(cardinality="one_to_one")]})).issues
    assert [(issue.code, issue.path) for issue in issues] == [
        ("candidate.record_locked", ("relationships", 0))
    ]


def test_merge_keeps_one_finding_per_column_pair_in_table_order() -> None:
    saved = AnalysisResultRecord.model_validate(
        _saved(from_object="Orders", to_object="Customers", kind="foreign_key")
    )
    tables = analysis_table_inputs(_example_context())
    validators = [
        AnalysisTableCandidateValidator(
            inputs=inputs, selected_attribute_keys=_selected_keys(), applied=(saved,)
        )
        for inputs in tables
    ]
    # Orders updates the saved finding's cardinality: an update, not a duplicate.
    orders = validators[0].parse_validated(
        {"relationships": [_link(kind="foreign_key", cardinality="one_to_one")]}
    )
    # Customers proposes the reverse of that pair under another kind: a duplicate.
    customers = validators[1].parse_validated({"relationships": [_link(to="t1.CustomerCode")]})

    changes, dropped = merge_table_findings([orders, customers], (saved,))

    assert dropped == 1
    (change,) = changes
    (record,) = change.records
    assert (record["from_object_name"], record["relationship_kind"]) == ("Orders", "foreign_key")
    assert record["inferred_cardinality"] == "one_to_one"


def test_merge_drops_a_new_kind_on_an_already_linked_pair() -> None:
    saved = AnalysisResultRecord.model_validate(
        _saved(from_object="Orders", to_object="Customers", kind="foreign_key")
    )
    inputs = analysis_table_inputs(_example_context())[0]
    validator = AnalysisTableCandidateValidator(
        inputs=inputs, selected_attribute_keys=_selected_keys(), applied=(saved,)
    )
    answer = validator.parse_validated({"relationships": [_link()]})

    assert merge_table_findings([answer], (saved,)) == ((), 1)
    assert merge_table_findings([(), ()], ()) == ((), 0)


def _per_table_plan(
    *, retry_count: int = 1, stage_code: str = "per_table_authoring"
) -> AgentRunPlan:
    prefix = "workflow.analysis.common.per_table_authoring.inputs."
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "project_revision": 7,
            "project_workflow": "analysis",
            "workflow_execution_mode": "one_shot",
            "workflow_operation": "per_table",
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (501, 502),
            "selection": AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=retry_count,
            ),
            "stages": (
                FrozenAgentStage(
                    workflow_stage_id=22,
                    stage_code=stage_code,
                    stage_order=20,
                    prompt_template_version_id=72,
                    prompt_template_digest="b" * 64,
                    templates=PromptComponentTemplates(
                        system="Analyze one table.",
                        instruction=(
                            "Keys {{key_directory}}. Focus {{focus_table}}. "
                            "Saved {{saved_relationships}}. Repair {{validation_failures}}."
                        ),
                    ),
                    variables=(
                        *(
                            PromptVariableDefinition(
                                name=name,
                                resolver_key=prefix + name,
                                data_type="json",
                                is_required=True,
                            )
                            for name in ("key_directory", "focus_table", "saved_relationships")
                        ),
                        PromptVariableDefinition(
                            name="validation_failures",
                            resolver_key="workflow.validation_failures",
                            data_type="json",
                            is_required=False,
                        ),
                    ),
                ),
            ),
        },
        strict=False,
    )


@dataclass
class _TableAgent:
    """Answers each call by its focus table, so call order does not matter."""

    answers: dict[str, list[JsonValue]]
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        inputs = cast(dict[str, Any], request.context)["original_context"]["prompt_inputs"]
        answer = self.answers[inputs["focus_table"]["table"]].pop(0)
        return AgentExecutionResult(candidate=answer, turn_count=1, tool_call_count=0)


def _bundle_link(to: str) -> dict[str, JsonValue]:
    return {
        "from_attribute_name": "customer_id",
        "to": to,
        "relationship_kind": "reference",
        "inferred_cardinality": "many_to_one",
    }


@pytest.mark.asyncio
async def test_per_table_run_makes_one_call_per_table_and_hands_off_one_draft() -> None:
    agent = _TableAgent(
        answers={
            "t1": [{"relationships": [_bundle_link("t2.customer_id")]}],
            # The reverse of the first table's link is dropped before the draft.
            "t2": [{"relationships": [_bundle_link("t1.customer_id")]}],
        }
    )
    service, _database, _authorizer, handoff, lifecycle = executor._service(
        agent=agent, plan=_per_table_plan(), context_bundle=_context_bundle()
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert result is not None
    assert [
        (request.workflow, request.stage, request.execution_mode, request.allowed_tool_names)
        for request in agent.requests
    ] == [("analysis_inference", "per_table_authoring", "one_shot", ())] * 2
    assert sorted(
        cast(dict[str, Any], request.context)["original_context"]["prompt_inputs"]["focus_table"][
            "object_name"
        ]
        for request in agent.requests
    ) == ["customer_raw", "order_raw"]
    # Each prompt carries the whole key directory, not only its own table.
    for request in agent.requests:
        assert '"table":"t1"' in request.instruction_prompt
        assert '"table":"t2"' in request.instruction_prompt
    (changes,) = handoff.calls
    (change,) = changes
    (record,) = change.records
    assert (record["from_object_name"], record["to_object_name"]) == ("order_raw", "customer_raw")
    # A dropped duplicate is reported, but it is not a warning.
    final = handoff.final_events[-1]
    assert final.status == "running"
    assert "Dropped 1 finding on column pairs that were already linked." in final.message
    # Two tables are below the first progress checkpoint, so only the start is logged.
    assert [event.stage for event in lifecycle.events] == ["analysis.relationship_inference"]
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_failed_table_adds_a_note_and_keeps_the_other_tables() -> None:
    good: JsonValue = {"relationships": [_bundle_link("t2.customer_id")]}
    wrong: JsonValue = {"relationships": [_bundle_link("t9.customer_id")]}
    agent = _TableAgent(answers={"t1": [good], "t2": [wrong, wrong]})
    service, _database, _authorizer, handoff, lifecycle = executor._service(
        agent=agent, plan=_per_table_plan(retry_count=1), context_bundle=_context_bundle()
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    (changes,) = handoff.calls
    assert [record["from_object_name"] for record in changes[0].records] == ["order_raw"]
    final = handoff.final_events[-1]
    assert final.status == "warning"
    assert "bronze.customer_raw was not analyzed" in final.message
    assert [(event.stage, event.status) for event in lifecycle.events[1:]] == [
        ("analysis.per_table_authoring", "warning")
    ]
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_run_fails_when_no_table_could_be_analyzed() -> None:
    wrong: JsonValue = {"relationships": [_bundle_link("t9.customer_id")]}
    agent = _TableAgent(answers={"t1": [wrong, wrong], "t2": [wrong, wrong]})
    service, _database, _authorizer, handoff, lifecycle = executor._service(
        agent=agent, plan=_per_table_plan(retry_count=1), context_bundle=_context_bundle()
    )

    with pytest.raises(WorkbenchError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            project_id=18,
            workflow_run_id=1048,
            expected_project_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )
    assert handoff.calls == []
    assert lifecycle.failed is not None


def _bundle_with_tables(count: int) -> AgentContextBundle:
    context = _context_bundle().context.model_copy(
        update={
            "selected_objects": tuple(
                SelectedObjectContext.model_validate(
                    executor._selected_object(f"table_{position}", position), strict=False
                )
                for position in range(1, count + 1)
            )
        }
    )
    return AgentContextBundle(
        context=context, embedded_context=cast(JsonValue, context.model_dump(mode="json"))
    )


@pytest.mark.asyncio
async def test_progress_is_logged_every_six_tables() -> None:
    empty: JsonValue = {"relationships": []}
    agent = _TableAgent(answers={f"t{position}": [empty] for position in range(1, 14)})
    service, _database, _authorizer, handoff, lifecycle = executor._service(
        agent=agent, plan=_per_table_plan(), context_bundle=_bundle_with_tables(13)
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert result is None and handoff.calls == []
    assert len(agent.requests) == 13
    # The start, then every 6 tables; completion has its own final event.
    assert [(event.message, event.current, event.total) for event in lifecycle.events[1:]] == [
        ("Analyzed 6 of 13 tables.", 6, 13),
        ("Analyzed 12 of 13 tables.", 12, 13),
    ]


@pytest.mark.asyncio
async def test_per_table_run_needs_its_own_stage() -> None:
    agent = _TableAgent(answers={})
    service, *_ = executor._service(
        agent=agent,
        plan=_per_table_plan(stage_code="relationship_inference"),
        context_bundle=_context_bundle(),
    )

    with pytest.raises(InvalidRequestError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            project_id=18,
            workflow_run_id=1048,
            expected_project_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )
    assert agent.requests == []


def test_per_table_plans_are_one_shot_analysis_plans() -> None:
    plan = _per_table_plan().model_dump()
    with pytest.raises(ValueError, match="one-shot Analysis"):
        AgentRunPlan.model_validate({**plan, "workflow_execution_mode": "tool_assisted"})
    with pytest.raises(ValueError, match="Build and Optimize"):
        AgentRunPlan.model_validate({**plan, "project_workflow": "logical"})
