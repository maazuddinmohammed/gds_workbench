"""Conceptual inputs reuse canonical evidence while keeping business history explicit."""

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

from tests.web_backend.test_conceptual_executor import _context_bundle, _plan

NAMES = {
    "one_shot": (
        "model_brief",
        "selected_metadata",
        "profile_evidence",
        "modeling_assertions",
        "analysis_evidence",
        "applied_conceptual",
    ),
    "tool_assisted": ("model_identity", "evidence_datasets"),
}


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_conceptual_inputs_match_actual_context_and_documented_examples(mode: str) -> None:
    plan = _plan(mode=mode)
    prefix = f"workflow.conceptual.{mode}.candidate_authoring.inputs."
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
            model_workflow="conceptual",
            workflow_execution_mode=mode,
            stage_code="candidate_authoring",
            resolver_key=prefix + name,
        )
        assert contract is not None
        schema = cast(Any, Draft202012Validator(contract.value_schema))
        assert not list(schema.iter_errors(contract.example))
        assert not list(schema.iter_errors(values[prefix + name]))
    if mode == "one_shot":
        assert values[prefix + "applied_conceptual"] == {"objects": [], "relationships": []}
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
