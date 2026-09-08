"""Mapping inputs follow actual pair preparation, not generic authoring context."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    downstream_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from jsonschema import Draft202012Validator

from tests.web_backend.mapping_fixtures import mapping_preparation


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("entity_type", ["logical_entity", "dimensional_entity"])
def test_mapping_inputs_preserve_actual_pair_and_evidence(mode: Any, entity_type: Any) -> None:
    preparation = mapping_preparation(
        execution_mode=mode, existing=True, modeled_entity_type=entity_type
    )
    context = build_mapping_execution_context(
        preparation=preparation, execution_mode=mode
    ).embedded_context
    plan = preparation.plan.agent_plan
    inputs = downstream_input_contracts("mapping")
    prefix = "workflow.mapping.common.mapping_authoring.inputs."
    stage = plan.stages[0].model_copy(
        update={
            "variables": tuple(
                PromptVariableDefinition(
                    name=name,
                    resolver_key=prefix + name,
                    data_type="text" if inputs[name][0].get("type") == "string" else "json",
                    is_required=False,
                )
                for name in inputs
            )
        }
    )
    before = deepcopy(context)
    values = project_prompt_input_values(
        plan=plan, stage=stage, context=context, resolver_values={"legacy": context}
    )
    for name in inputs:
        contract = get_prompt_input_contract(
            model_workflow="mapping",
            workflow_execution_mode=mode,
            stage_code=stage.stage_code,
            resolver_key=prefix + name,
        )
        assert contract is not None
        validator = cast(Any, Draft202012Validator(contract.value_schema))
        assert validator.is_valid(contract.example)
        assert validator.is_valid(values[prefix + name])
    assert values[prefix + "mapping_route"] == preparation.plan.route
    headers = cast(list[dict[str, Any]], values[prefix + "existing_mapping"])
    assert (
        headers[0]["modeled_entity"]["entity_name"]
        == preparation.context.headers[0].modeled_entity.entity_name
    )
    assert "model_object_binding_id" not in headers[0]
    assert headers[0]["attribute_mappings"][0]["modeled_attribute_name"] == "CustomerID"
    assert before == context and values["legacy"] is context
    with pytest.raises(InvalidRequestError):
        project_prompt_input_values(
            plan=plan,
            stage=stage,
            context=context,
            resolver_values={prefix + next(iter(inputs)): "wrong"},
        )
