"""Frozen natural-key joins and optional reader behavior, without database access."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolResultTooLargeError,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    downstream_input_contracts,
    project_downstream_inputs,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from jsonschema import Draft202012Validator

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "downstream_prompt_contexts.json").read_text()
)


@pytest.mark.parametrize("workflow", ("code_generation", "validation"))
def test_existing_code_and_validation_resolvers_use_canonical_prompt_evidence(
    workflow: Literal["code_generation", "validation"],
) -> None:
    stage_code = (
        "sql_generation" if workflow == "code_generation" else "validation_generation"
    )
    prefix = f"workflow.{workflow}.common.{stage_code}.inputs."
    contracts = downstream_input_contracts(workflow)
    existing_names = (
        {
            "target_ref",
            "target_metadata",
            "source_metadata",
            "source_systems",
            "object_transformations",
            "attribute_transformations",
        }
        if workflow == "code_generation"
        else {
            "system_ref",
            "system_scope",
            "mapping_evidence",
            "current_code",
            "applied_groups",
            "applied_checks",
        }
    )
    assert existing_names <= contracts.keys()
    variables: list[PromptVariableDefinition] = []
    for name in existing_names:
        descriptor = get_prompt_input_contract(
            model_workflow=workflow,
            workflow_execution_mode=None,
            stage_code=stage_code,
            resolver_key=prefix + name,
        )
        assert descriptor is not None
        assert descriptor.value_schema == contracts[name][0]
        assert descriptor.delivery == "inline_value" and descriptor.context_path is None
        variables.append(
            PromptVariableDefinition(
                name=name,
                resolver_key=prefix + name,
                data_type=descriptor.data_type,
                is_required=False,
            )
        )
    stage = FrozenAgentStage(
        workflow_stage_id=1,
        stage_code=stage_code,
        stage_order=10,
        prompt_template_version_id=1,
        prompt_template_digest="a" * 64,
        templates=PromptComponentTemplates(
            system="Use frozen evidence.", instruction="Return the required output."
        ),
        variables=tuple(variables),
    )
    is_code = workflow == "code_generation"
    plan = AgentRunPlan(
        workflow_run_id=1,
        model_id=1,
        model_revision=1,
        correlation_id=UUID("11111111-1111-1111-1111-111111111111"),
        model_workflow=workflow,
        workflow_execution_mode=None,
        modeled_entity_type="logical_entity" if is_code else None,
        code_generation_coverage_mode="selected_targets" if is_code else None,
        sql_generation_guide_id=1 if is_code else None,
        sql_generation_guide_version_id=1 if is_code else None,
        sql_generation_guide_digest="b" * 64 if is_code else None,
        selected_scope_digest="c" * 64,
        selected_object_ids=(1,) if is_code else (),
        selected_system_codes=() if is_code else ("CRM",),
        selection=AgentRunSelection(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-primary",
            reasoning_effort_code="none",
            max_turns=6,
            validation_retry_count=1,
        ),
        stages=(stage,),
    )
    context = deepcopy(FIXTURE[workflow])
    projected = project_downstream_inputs(workflow, context)
    actual = project_prompt_input_values(
        plan=plan, stage=stage, context=context, resolver_values={}
    )
    assert actual == {prefix + name: projected[name] for name in existing_names}
    for key in (prefix + "unknown_input", prefix + "context.targets"):
        assert (
            get_prompt_input_contract(
                model_workflow=workflow,
                workflow_execution_mode=None,
                stage_code=stage_code,
                resolver_key=key,
            )
            is None
        )


@pytest.mark.parametrize("workflow", ["mapping", "code_generation", "validation"])
def test_contract_examples_and_projected_context_have_exact_schema(
    workflow: str,
) -> None:
    values = project_downstream_inputs(workflow, deepcopy(FIXTURE[workflow]))
    contracts = downstream_input_contracts(workflow)
    assert values.keys() == contracts.keys()
    for name, (schema, _, example) in contracts.items():
        validator = cast(Any, Draft202012Validator(schema))
        validator.validate(values[name])
        validator.validate(example)
    assert (
        project_downstream_inputs(
            workflow, {"__gds_downstream_inputs__": workflow, "values": values}
        )
        == values
    )


def test_mapping_joins_names_from_real_bindings_and_keeps_document_business_keys() -> (
    None
):
    raw = deepcopy(FIXTURE["mapping"])
    child = raw["headers"][0]["attribute_mappings"][0]
    child["transformation_document"] = {
        "customer_id": 42,
        "nested": {"object_id": "business"},
    }
    values = project_downstream_inputs("mapping", raw)
    result = values["existing_mapping"][0]["attribute_mappings"][0]
    assert result["modeled_attribute_name"] == "CustomerID"
    assert result["target_attribute_name"] == "CustomerID"
    assert "modeled_attribute_id" not in result and "target_attribute_id" not in result
    assert result["transformation_document"] == child["transformation_document"]
    result["transformation_document"]["customer_id"] = 10
    assert child["transformation_document"]["customer_id"] == 42


@pytest.mark.parametrize("broken", ["modeled_attribute_id", "target_attribute_id"])
def test_mapping_broken_binding_is_not_resolved_by_similar_names(broken: str) -> None:
    raw = deepcopy(FIXTURE["mapping"])
    raw["headers"][0]["attribute_mappings"][0][broken] = 999_999
    with pytest.raises(InvalidRequestError):
        project_downstream_inputs("mapping", raw)


def test_code_system_links_are_resolved_without_replacing_physical_placement() -> None:
    raw = deepcopy(FIXTURE["code_generation"])
    source = raw["targets"][0]["context"]["physical_sources"][0]
    source["object"].update(
        tenant_code="GDS", system_code="WAREHOUSE", connection_code="MAIN"
    )
    values = project_downstream_inputs("code_generation", raw)
    assert values["source_metadata"][0]["object"]["tenant_code"] == "GDS"
    assert values["source_metadata"][0]["object"]["system_code"] == "WAREHOUSE"
    assert values["source_metadata"][0]["source_system_code"] == "CRM"
    assert values["attribute_transformations"][0]["modeled_entity_name"] == "Customer"
    assert "mapping_object_id" not in values["attribute_transformations"][0]
    source["selected_source_system_id"] = 999_999
    with pytest.raises(InvalidRequestError):
        project_downstream_inputs("code_generation", raw)


@pytest.mark.parametrize("workflow", ["mapping", "code_generation", "validation"])
def test_all_readers_accept_no_input_and_preserve_prompt_value_shapes(
    workflow: str,
) -> None:
    values = project_downstream_inputs(workflow, deepcopy(FIXTURE[workflow]))
    catalog = build_downstream_readers(
        workflow,
        values,
        max_result_bytes=100_000,
        max_page_records=2,
        max_cumulative_result_bytes=500_000,
    )
    assert catalog.prompt_values == values
    for definition in catalog.definitions:
        page = catalog.invoke(definition.name, {})
        assert page["is_complete"] is True
        assert page["next_cursor"] is None
        assert page["incomplete_object_key"] is None
        assert isinstance(page["items"], list)


def test_nested_source_key_filter_is_complete_frozen_and_cursor_bound() -> None:
    values = project_downstream_inputs(
        "code_generation", deepcopy(FIXTURE["code_generation"])
    )
    first = values["source_metadata"][0]
    second = deepcopy(first)
    second["object"]["connection_code"] = "SECOND"
    values["source_metadata"].append(second)
    catalog = build_downstream_readers(
        "code_generation",
        values,
        max_result_bytes=100_000,
        max_page_records=1,
        max_cumulative_result_bytes=500_000,
    )
    keys = [
        {
            name: row["object"][name]
            for name in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        }
        for row in values["source_metadata"]
    ]
    values["source_metadata"].clear()
    selected = catalog.invoke("get_code_sources", {"source_object_keys": [keys[1]]})
    assert selected["items"] == [second]
    page = catalog.invoke("get_code_sources", {})
    assert page["items"] == [first] and page["is_complete"] is False
    next_page = catalog.invoke("get_code_sources", {"cursor": page["next_cursor"]})
    assert next_page["items"] == [second]
    assert (
        catalog.invoke("get_code_sources", {"cursor": page["next_cursor"]}) == next_page
    )
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke(
            "get_code_sources",
            {
                "cursor": page["next_cursor"],
                "source_object_keys": [keys[1]],
            },
        )
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke("get_existing_mapping", {"cursor": page["next_cursor"]})
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke(
            "get_code_sources",
            {
                "source_object_keys": [{**keys[0], "connection_code": "missing"}],
            },
        )


def test_known_validation_group_with_no_checks_returns_empty_and_unknown_group_fails() -> (
    None
):
    values = project_downstream_inputs("validation", deepcopy(FIXTURE["validation"]))
    values["applied_checks"] = []
    name = values["applied_groups"][0]["validation_group_name"]
    catalog = build_downstream_readers(
        "validation",
        values,
        max_result_bytes=100_000,
        max_page_records=10,
        max_cumulative_result_bytes=500_000,
    )
    assert catalog.invoke("get_applied_checks", {"group_names": [name]})["items"] == []
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke("get_applied_checks", {"group_names": ["missing"]})


def test_oversized_whole_mapping_document_fails_without_truncation() -> None:
    values = project_downstream_inputs("mapping", deepcopy(FIXTURE["mapping"]))
    values["existing_mapping"][0]["transformation_document"] = {"rule": "x" * 10_000}
    catalog = build_downstream_readers(
        "mapping",
        values,
        max_result_bytes=500,
        max_page_records=10,
        max_cumulative_result_bytes=500_000,
    )
    with pytest.raises(AgentContextToolResultTooLargeError):
        catalog.invoke("get_existing_mapping", {})
