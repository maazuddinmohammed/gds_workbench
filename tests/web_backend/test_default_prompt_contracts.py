"""Repository default contracts; synthetic examples only, no model or database calls."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    list_prompt_input_contracts,
    project_prompt_input_values,
)
from gds_workbench_api.features.workflows.authoring.tool_configuration import (
    registered_tool_definitions,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
    render_prompt,
)
from jsonschema import Draft202012Validator

from tests.web_backend.mapping_fixtures import mapping_preparation

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = json.loads(
    (ROOT / "database/seed/05_global_prompt_defaults.template.sql")
    .read_text()
    .split("$workflow_defaults$")[1]
)


@pytest.mark.parametrize(
    "default",
    DEFAULTS,
    ids=[
        f"{row['model_workflow']}.{row['workflow_execution_mode'] or 'common'}"
        for row in DEFAULTS
    ],
)
def test_seeded_defaults_render_contract_examples_and_match_reviewed_exports(
    default: dict[str, Any],
) -> None:
    workflow = default["model_workflow"]
    mode = default["workflow_execution_mode"]
    stage = default["workflow_stage_code"]
    contracts = list_prompt_input_contracts(
        model_workflow=workflow, workflow_execution_mode=mode, stage_code=stage
    )
    assert contracts
    for contract in contracts:
        Draft202012Validator.check_schema(contract.value_schema)
        assert cast(Any, Draft202012Validator(contract.value_schema)).is_valid(
            contract.example
        )
    filename = f"{'code' if workflow == 'code_generation' else workflow}.{mode or 'tool_assisted'}"
    reviewed = json.loads((ROOT / f"docs/workflow-prompts/{filename}.json").read_text())
    assert reviewed["status"] == "implemented_default"
    assert set(reviewed["variables"]) <= {contract.name for contract in contracts}
    for component in ("system_prompt", "instruction_prompt"):
        # A failure must not print prompt content through pytest assertion introspection.
        assert (
            hashlib.sha256(default[component].encode()).digest()
            == hashlib.sha256(reviewed[component].encode()).digest()
        )
    tool_names = sorted(reviewed["tools"])
    assert default["agent_tool_names"] == (tool_names if mode != "one_shot" else None)
    if mode == "one_shot":
        assert not tool_names
    else:
        assert tool_names == sorted(
            tool.name for tool in registered_tool_definitions(workflow)
        )
    rendered = render_prompt(
        templates=PromptComponentTemplates(
            system=default["system_prompt"], instruction=default["instruction_prompt"]
        ),
        variables=tuple(
            PromptVariableDefinition(
                name=contract.name,
                resolver_key=contract.resolver_key,
                data_type=contract.data_type,
                is_required=False,
            )
            for contract in contracts
        ),
        resolver_values={
            contract.resolver_key: contract.example for contract in contracts
        },
    )
    assert bool(rendered.system) and bool(rendered.instruction)
    assert not rendered.warning_codes and not rendered.unknown_placeholders


@pytest.mark.parametrize(
    "workflow", ("metadata_enrichment_object", "metadata_enrichment_attribute")
)
def test_enrichment_examples_have_one_object_and_explicit_write_targets(
    workflow: str,
) -> None:
    contracts = workflow_input_contracts(workflow)
    for spec in contracts.values():
        assert cast(Any, Draft202012Validator(spec["schema"])).is_valid(spec["example"])
    objects = contracts["object_context"]["example"]
    groups = contracts["object_attribute_context"]["example"]
    assert len(objects) == len(groups) == 1
    group = groups[0]
    fields = (
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    )
    assert tuple(objects[0][field] for field in fields) == tuple(
        group[field] for field in fields
    )
    selected = group["selected_attribute_names"]
    assert bool(selected) == (workflow == "metadata_enrichment_attribute")
    assert set(selected) < {
        attribute["attribute_name"] for attribute in group["attributes"]
    }


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
def test_mapping_defaults_render_selected_seeded_templates_with_nested_guidance(
    mode: Any,
) -> None:
    preparation = mapping_preparation(execution_mode=mode)
    preparation_document = preparation.model_dump(mode="json")
    plan = preparation.plan.agent_plan
    contracts = list_prompt_input_contracts(
        model_workflow="mapping",
        workflow_execution_mode=mode,
        stage_code="mapping_authoring",
    )
    variables = tuple(
        PromptVariableDefinition(
            name=contract.name,
            resolver_key=contract.resolver_key,
            data_type=contract.data_type,
            is_required=False,
        )
        for contract in contracts
    )
    stage = plan.stages[0].model_copy(update={"variables": variables})
    seeded = json.loads(
        (ROOT / "database/seed/07_global_mapping_output_templates.template.sql")
        .read_text()
        .split("$mapping_templates$")[1]
    )
    definitions: list[dict[str, Any]] = []
    for index, raw in enumerate(seeded, start=1):
        template = {
            key.removeprefix("output_template_"): value
            for key, value in raw.items()
            if key != "fields"
        }
        template["is_active"] = True
        template["fields"] = [
            {
                key.removeprefix("output_template_field_"): value
                for key, value in field.items()
            }
            for field in raw["fields"]
        ]
        name = (
            "object_output_template"
            if template["target_type"] == "mapping_object"
            else "attribute_output_template"
        )
        contract = next(contract for contract in contracts if contract.name == name)
        assert contract.example == template
        assert isinstance(template["fields"][0]["example"][0], dict)
        validator = cast(Any, Draft202012Validator(contract.value_schema))
        assert validator.is_valid(None)
        assert validator.is_valid(template)
        template["output_template_id"] = index
        template["schema_digest"] = "a" * 64
        template["schema_digest_is_valid"] = True
        definitions.append(template)
        for scope in ("plan", "context"):
            preparation_document[scope]["output_template_selections"][
                template["target_type"]
            ] = {
                "output_template_id": index,
                "schema_digest": "a" * 64,
            }
    preparation_document["context"]["output_templates"] = {
        "ids": [1, 2],
        "definitions": definitions,
    }
    preparation = type(preparation).model_validate(preparation_document, strict=False)
    context = build_mapping_execution_context(
        preparation=preparation, execution_mode=mode
    ).embedded_context
    values = project_prompt_input_values(
        plan=plan, stage=stage, context=context, resolver_values={}
    )
    default = next(
        row
        for row in DEFAULTS
        if row["model_workflow"] == "mapping" and row["workflow_execution_mode"] == mode
    )
    rendered = render_prompt(
        templates=PromptComponentTemplates(
            system=default["system_prompt"], instruction=default["instruction_prompt"]
        ),
        variables=variables,
        resolver_values=values,
    )
    assert bool(rendered.system) and bool(rendered.instruction)
    assert not rendered.warning_codes and not rendered.unknown_placeholders
    invalid_context = cast(dict[str, Any], deepcopy(context))
    invalid_context["values"]["object_output_template"]["fields"][0]["is_required"] = (
        "yes"
    )
    with pytest.raises(
        InvalidRequestError, match="frozen workflow Prompt input is invalid"
    ):
        project_prompt_input_values(
            plan=plan, stage=stage, context=invalid_context, resolver_values={}
        )
