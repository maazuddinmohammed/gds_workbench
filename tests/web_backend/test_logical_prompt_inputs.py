"""Logical inputs describe exact source evidence and applied layer history."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from jsonschema import Draft202012Validator
from pydantic import JsonValue

from tests.web_backend.test_logical_executor import _context_bundle, _plan

NAMES = {
    "one_shot": (
        "model_brief",
        "selected_metadata",
        "profile_evidence",
        "modeling_assertions",
        "analysis_evidence",
        "applied_conceptual",
        "applied_logical",
    ),
    "tool_assisted": ("model_identity", "evidence_datasets"),
}


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_logical_inputs_match_actual_context_and_documented_examples(mode: str) -> None:
    plan = _plan(mode=mode)
    prefix = f"workflow.logical.{mode}.candidate_authoring.inputs."
    stage = plan.stages[0].model_copy(
        update={
            "variables": (
                *plan.stages[0].variables,
                *(
                    PromptVariableDefinition(
                        name=name, resolver_key=prefix + name, data_type="json", is_required=False
                    )
                    for name in NAMES[mode]
                ),
            )
        }
    )
    plan = plan.model_copy(update={"stages": (stage,)})
    context = _context_bundle(mode=mode).embedded_context
    before = deepcopy(context)
    legacy = {"legacy": context, "model.naming_instructions": "Keep supplied names."}
    values = project_prompt_input_values(
        plan=plan, stage=stage, context=context, resolver_values=legacy
    )
    assert context == before and values["legacy"] is context
    assert values["model.naming_instructions"] is legacy["model.naming_instructions"]
    assert set(values) - set(legacy) == {prefix + name for name in NAMES[mode]}
    for name in NAMES[mode]:
        contract = get_prompt_input_contract(
            model_workflow="logical",
            workflow_execution_mode=mode,
            stage_code="candidate_authoring",
            resolver_key=prefix + name,
        )
        assert contract is not None
        schema = cast(Any, Draft202012Validator(contract.value_schema))
        assert not list(schema.iter_errors(contract.example))
        assert not list(schema.iter_errors(values[prefix + name]))
    if mode == "one_shot":
        assert values[prefix + "applied_conceptual"] is None
        assert values[prefix + "applied_logical"] is None
        nullable = cast(dict[str, JsonValue], deepcopy(context))
        cast(dict[str, JsonValue], nullable["applied"])["conceptual"] = None
        assert (
            project_prompt_input_values(
                plan=plan, stage=stage, context=nullable, resolver_values={}
            )[prefix + "applied_conceptual"]
            is None
        )
        broken = cast(dict[str, JsonValue], deepcopy(context))
        broken.pop("applied")
        with pytest.raises(InvalidRequestError):
            project_prompt_input_values(
                plan=plan, stage=stage, context=broken, resolver_values=legacy
            )

    else:
        broken = cast(dict[str, JsonValue], deepcopy(context))
        broken["model_workflow"] = "analysis"
        with pytest.raises(InvalidRequestError):
            project_prompt_input_values(
                plan=plan, stage=stage, context=broken, resolver_values=legacy
            )


def test_logical_manifest_contains_actual_applied_and_downstream_datasets() -> None:
    from gds_workbench_api.features.workflows.authoring.context import (
        InMemoryAgentContextToolCatalog,
        modeled_layer_dependencies,
    )

    from tests.mcp.model_test_fixtures import complete_model_graph, snapshot_from_graph

    snapshot = snapshot_from_graph(complete_model_graph())
    context = _context_bundle(mode="tool_assisted").context
    context = context.model_copy(
        update={
            "applied": context.applied.model_copy(update={"logical": snapshot.logical}),
            "read_only_dependencies": modeled_layer_dependencies(
                snapshot, modeled_entity_type="logical_entity"
            ),
        }
    )
    catalog = InMemoryAgentContextToolCatalog(
        context=context, max_result_bytes=8192, max_catalog_bytes=1024 * 1024, max_page_records=20
    )
    plan = _plan(mode="tool_assisted")
    prefix = "workflow.logical.tool_assisted.candidate_authoring.inputs."
    stage = plan.stages[0].model_copy(
        update={
            "variables": (
                PromptVariableDefinition(
                    name="evidence_datasets",
                    resolver_key=prefix + "evidence_datasets",
                    data_type="json",
                    is_required=False,
                ),
            )
        }
    )
    projected = project_prompt_input_values(
        plan=plan, stage=stage, context=catalog.manifest, resolver_values={}
    )
    datasets = {
        item["dataset"]
        for item in cast(list[dict[str, Any]], projected[prefix + "evidence_datasets"])
    }
    assert {
        "logical_entity",
        "logical_attribute",
        "read_only_model_object_binding",
        "read_only_mapping_object",
        "read_only_generated_code",
    } <= datasets
