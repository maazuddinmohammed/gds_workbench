"""Analysis inputs retain canonical evidence and distinguish tool count semantics."""

# Synthetic executor fixture reuse.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan, WorkflowExecutionMode
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from jsonschema import Draft202012Validator
from pydantic import JsonValue

from tests.web_backend.test_analysis_executor import _context_bundle, _plan

NAMES = {
    "one_shot": (
        "model_brief",
        "selected_metadata",
        "profile_evidence",
        "applied_relationships",
        "modeling_assertions",
    ),
    "tool_assisted": ("model_identity", "evidence_datasets"),
}


def named_plan(mode: str) -> AgentRunPlan:
    plan = _plan(mode=cast(WorkflowExecutionMode, mode))
    stage = plan.stages[0].model_copy(
        update={
            "variables": (
                *plan.stages[0].variables,
                *(
                    PromptVariableDefinition(
                        name=name,
                        resolver_key=key(mode, name),
                        data_type="json",
                        is_required=False,
                    )
                    for name in NAMES[mode]
                ),
            )
        }
    )
    return plan.model_copy(update={"stages": (stage,)})


def key(mode: str, name: str) -> str:
    return f"workflow.analysis.{mode}.relationship_inference.inputs.{name}"


@pytest.mark.parametrize(
    ("mode", "name"), [(mode, name) for mode, names in NAMES.items() for name in names]
)
def test_registered_input_examples_and_actual_wire_values_match_schema(
    mode: str, name: str
) -> None:
    contract = get_prompt_input_contract(
        model_workflow="analysis",
        workflow_execution_mode=mode,
        stage_code="relationship_inference",
        resolver_key=key(mode, name),
    )
    assert contract is not None and contract.source and contract.availability
    schema = cast(Any, Draft202012Validator(contract.value_schema))
    assert not list(schema.iter_errors(contract.example))
    plan = named_plan(mode)
    context = _context_bundle(mode=cast(WorkflowExecutionMode, mode)).embedded_context
    legacy = {"legacy": context}
    before = deepcopy(context)
    result = project_prompt_input_values(
        plan=plan,
        stage=plan.stages[0],
        context=context,
        resolver_values=legacy,
    )
    assert result["legacy"] is context and legacy == {"legacy": context}
    assert context == before
    assert not list(schema.iter_errors(result[key(mode, name)]))
    assert (
        project_prompt_input_values(
            plan=plan,
            stage=plan.stages[0],
            context=context,
            resolver_values=result,
        )
        == result
    )


def test_tool_manifest_counts_keep_fragmented_source_and_retrieval_counts_distinct() -> None:
    plan = named_plan("tool_assisted")
    context = cast(dict[str, JsonValue], _context_bundle(mode="tool_assisted").embedded_context)
    context.pop("selected_objects", None)  # Valid compact manifest.
    context["dataset_counts"] = {"selected_attribute": 7}
    context["dataset_record_counts"] = {"selected_attribute": 3}
    context["fragmented_record_counts"] = {"selected_attribute": 1}
    result = project_prompt_input_values(
        plan=plan,
        stage=plan.stages[0],
        context=context,
        resolver_values={},
    )
    assert result[key("tool_assisted", "evidence_datasets")] == [
        {
            "dataset": "selected_attribute",
            "source_record_count": 3,
            "retrieval_item_count": 7,
            "fragmented_record_count": 1,
        }
    ]
    assert set(result) == {key("tool_assisted", name) for name in NAMES["tool_assisted"]}
    assert "selected_metadata" not in str(result.keys())


@pytest.mark.parametrize(
    "fault",
    ["missing", "negative", "bool", "wrong_semantics", "unmarked_fragments", "unknown_dataset"],
)
def test_inconsistent_tool_manifest_is_rejected_without_exposing_values(fault: str) -> None:
    plan = named_plan("tool_assisted")
    context = cast(dict[str, JsonValue], _context_bundle(mode="tool_assisted").embedded_context)
    if fault == "missing":
        context.pop("dataset_record_counts")
    elif fault == "negative":
        context["dataset_record_counts"] = {"selected_attribute": -1}
    elif fault == "bool":
        context["dataset_counts"] = {"selected_attribute": True}
    elif fault == "wrong_semantics":
        context["dataset_count_semantics"] = {"dataset_counts": "private-sentinel"}
    elif fault == "unknown_dataset":
        context["dataset_counts"] = {"private-sentinel": 1}
    else:
        context["dataset_counts"] = {"selected_attribute": 7}
        context["dataset_record_counts"] = {"selected_attribute": 3}
    with pytest.raises(InvalidRequestError) as caught:
        project_prompt_input_values(
            plan=plan,
            stage=plan.stages[0],
            context=context,
            resolver_values={},
        )
    assert "private-sentinel" not in str(caught.value)


def test_one_shot_does_not_turn_missing_evidence_into_empty_or_copy_private_fields() -> None:
    plan = named_plan("one_shot")
    context = cast(dict[str, JsonValue], _context_bundle().embedded_context)
    context["private_snapshot"] = {"private-sentinel": True}
    result = project_prompt_input_values(
        plan=plan,
        stage=plan.stages[0],
        context=context,
        resolver_values={},
    )
    assert "private-sentinel" not in str(result)
    assert result[key("one_shot", "profile_evidence")] == []
    context.pop("profiles")
    with pytest.raises(InvalidRequestError):
        project_prompt_input_values(
            plan=plan,
            stage=plan.stages[0],
            context=context,
            resolver_values={},
        )


def test_only_registered_inputs_are_projected_and_conflicting_values_rejected() -> None:
    plan = named_plan("one_shot")
    context = _context_bundle().embedded_context
    old = _plan()
    original = {"legacy": object()}
    result = project_prompt_input_values(
        plan=old,
        stage=old.stages[0],
        context=None,
        resolver_values=original,
    )
    assert result == original and result["legacy"] is original["legacy"]
    with pytest.raises(InvalidRequestError):
        project_prompt_input_values(
            plan=plan,
            stage=plan.stages[0],
            context=context,
            resolver_values={key("one_shot", "model_brief"): {"model_name": "conflict"}},
        )
    assert (
        get_prompt_input_contract(
            model_workflow="analysis",
            workflow_execution_mode="one_shot",
            stage_code="unknown_stage",
            resolver_key=key("one_shot", "selected_metadata"),
        )
        is None
    )
