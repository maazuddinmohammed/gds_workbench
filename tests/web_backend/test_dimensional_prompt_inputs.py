"""Dimensional inputs retain eligible Silver evidence and explicit Gold policy."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.workflows.authoring.context import (
    InMemoryAgentContextToolCatalog,
    modeled_layer_dependencies,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from jsonschema import Draft202012Validator

from tests.mcp.model_test_fixtures import complete_model_graph, snapshot_from_graph
from tests.web_backend.test_dimensional_executor import _context_bundle, _plan


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_dimensional_inputs_match_real_history_policy_and_dataset_shapes(mode: Any) -> None:
    names = (
        (
            "model_brief",
            "selected_metadata",
            "profile_evidence",
            "modeling_assertions",
            "analysis_evidence",
            "applied_logical",
            "applied_dimensional",
            "applied_mapping",
            "gold_technical_policy",
            "gold_audit_policy",
        )
        if mode == "one_shot"
        else ("model_identity", "evidence_datasets")
    )
    snapshot = snapshot_from_graph(complete_model_graph())
    base = _context_bundle(mode=mode).context
    base = base.model_copy(
        update={
            "applied": base.applied.model_copy(
                update={
                    "logical": snapshot.logical,
                    "dimensional": snapshot.dimensional,
                    "mapping": snapshot.mapping,
                }
            ),
            "read_only_dependencies": modeled_layer_dependencies(
                snapshot, modeled_entity_type="dimensional_entity"
            ),
        }
    )
    context = (
        base.model_dump(mode="json")
        if mode == "one_shot"
        else (
            InMemoryAgentContextToolCatalog(
                context=base,
                max_result_bytes=8192,
                max_catalog_bytes=1024 * 1024,
                max_page_records=20,
            ).manifest
        )
    )
    plan = _plan(mode=mode)
    prefix = f"workflow.dimensional.{mode}.candidate_authoring.inputs."
    stage = plan.stages[0].model_copy(
        update={
            "variables": tuple(
                PromptVariableDefinition(
                    name=name, resolver_key=prefix + name, data_type="json", is_required=False
                )
                for name in names
            )
        }
    )
    before = deepcopy(context)
    values = project_prompt_input_values(
        plan=plan, stage=stage, context=context, resolver_values={"legacy": context}
    )
    assert before == context and values["legacy"] is context
    for name in names:
        contract = get_prompt_input_contract(
            model_workflow="dimensional",
            workflow_execution_mode=mode,
            stage_code="candidate_authoring",
            resolver_key=prefix + name,
        )
        assert contract is not None
        validator = cast(Any, Draft202012Validator(contract.value_schema))
        assert validator.is_valid(values[prefix + name])
        assert validator.is_valid(contract.example)
    if mode == "one_shot":
        assert values[prefix + "selected_metadata"] == [
            item.model_dump(mode="json") for item in base.selected_objects
        ]
        assert all(item.object.zone_code == "silver" for item in base.selected_objects)
        assert values[prefix + "applied_dimensional"] == snapshot.dimensional.model_dump(
            mode="json"
        )
        assert values[prefix + "applied_mapping"] == snapshot.mapping.model_dump(mode="json")
        assert values[prefix + "gold_technical_policy"] == (
            base.model_details.gold_model_technical_columns_template
        )
        broken = cast(dict[str, Any], deepcopy(context))
        broken["model_details"]["gold_model_technical_columns_template"] = None
        with pytest.raises(InvalidRequestError):
            project_prompt_input_values(plan=plan, stage=stage, context=broken, resolver_values={})
    else:
        datasets = {
            item["dataset"]
            for item in cast(list[dict[str, Any]], values[prefix + "evidence_datasets"])
        }
        assert {
            "logical_entity",
            "dimensional_entity",
            "mapping_object",
        } <= datasets
    with pytest.raises(InvalidRequestError):
        project_prompt_input_values(
            plan=plan,
            stage=stage,
            context=context,
            resolver_values={prefix + names[0]: {"unrelated": True}},
        )
