"""Model SCD guidance survives frozen prompt boundaries without inferred defaults."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any, Literal, cast

import pytest
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_workbench_api.features.mapping.execution_context import build_mapping_execution_context
from gds_workbench_api.features.mapping.preparation_contracts import MappingAuthoringPolicy
from gds_workbench_api.features.workflows.authoring.context import InMemoryAgentContextToolCatalog
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from pydantic import ValidationError

from tests.mcp.model_test_fixtures import (
    complete_physical_scope,
    model_details,
    snapshot_from_graph,
)
from tests.web_backend.mapping_fixtures import mapping_preparation
from tests.web_backend.test_logical_executor import _context_bundle, _plan


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("scd_type", [None, "type_1", "type_2"])
def test_logical_prompt_uses_frozen_model_scd_choice(
    mode: str, scd_type: str | None
) -> None:
    context = _context_bundle(mode=mode).context
    details = context.model_details.model_copy(update={"logical_entity_scd_type": scd_type})
    context = context.model_copy(update={"model_details": details})
    readers = (
        InMemoryAgentContextToolCatalog(
            context=context,
            max_result_bytes=128 * 1024,
            max_catalog_bytes=256 * 1024,
            max_page_records=20,
        )
        if mode == "tool_assisted"
        else None
    )
    plan = _plan(mode=mode)
    key = "workflow.logical.common.candidate_authoring.inputs.logical_entity_scd_type"
    stage = plan.stages[0].model_copy(
        update={
            "variables": (
                PromptVariableDefinition(
                    name="logical_entity_scd_type",
                    resolver_key=key,
                    data_type="json",
                    is_required=False,
                ),
            )
        }
    )
    values = project_prompt_input_values(
        plan=plan,
        stage=stage,
        context=readers.manifest if readers else context.model_dump(mode="json"),
        resolver_values={},
        precomputed_values=readers.prompt_values if readers else None,
    )
    assert values[key] == scd_type
    assert context.model_details.logical_entity_scd_type == scd_type


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("scd_type", [None, "type_1", "type_2"])
@pytest.mark.parametrize("entity_type", ["logical_entity", "dimensional_entity"])
def test_mapping_prompt_retains_model_history_guidance_for_both_layers(
    mode: Any, scd_type: str | None, entity_type: Any
) -> None:
    preparation = mapping_preparation(execution_mode=mode, modeled_entity_type=entity_type)
    policy = preparation.context.authoring.model_copy(
        update={"logical_entity_scd_type": scd_type}
    )
    preparation = preparation.model_copy(
        update={"context": preparation.context.model_copy(update={"authoring": policy})}
    )
    execution = build_mapping_execution_context(preparation=preparation, execution_mode=mode)
    plan = preparation.plan.agent_plan
    key = "workflow.mapping.common.mapping_authoring.inputs.authoring_policy"
    stage = plan.stages[0].model_copy(
        update={
            "variables": (
                PromptVariableDefinition(
                    name="authoring_policy",
                    resolver_key=key,
                    data_type="json",
                    is_required=False,
                ),
            )
        }
    )
    values = project_prompt_input_values(
        plan=plan, stage=stage, context=execution.embedded_context, resolver_values={}
    )
    authoring = cast(dict[str, Any], values[key])
    assert authoring["logical_entity_scd_type"] == scd_type
    assert authoring["naming_instructions"] == policy.naming_instructions
    # Policy intent is preserved; it never fabricates target/history Attributes.
    assert preparation.context.target.attributes == mapping_preparation(
        execution_mode=mode, modeled_entity_type=entity_type
    ).context.target.attributes


@pytest.mark.parametrize("value", ["type_3", "SCD2", 2, True])
def test_mapping_policy_rejects_unknown_scd_guidance(value: object) -> None:
    with pytest.raises(ValidationError):
        MappingAuthoringPolicy.model_validate(
            {"model_name": "Model", "logical_entity_scd_type": value}
        )


@pytest.mark.parametrize("original", [None, "type_1", "type_2"])
@pytest.mark.parametrize("proposed", [None, "type_1", "type_2"])
def test_staged_model_details_cannot_override_governed_history_setting(
    original: Literal["type_1", "type_2"] | None,
    proposed: Literal["type_1", "type_2"] | None,
) -> None:
    details = {**model_details(), "logical_entity_scd_type": original}
    snapshot = snapshot_from_graph({"model_details": [details]})
    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"model_details": [{**details, "logical_entity_scd_type": proposed}]},
        physical_scope=complete_physical_scope(),
    )
    codes = {issue.code for issue in result.issues}
    assert ("model_policy_read_only" in codes) is (original != proposed)
    assert snapshot.model_input_scope.details.logical_entity_scd_type == original
