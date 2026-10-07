"""Large synthetic selections must reach the provider and survive repair intact."""

# Reuse synthetic workflow fixtures without database or provider calls.
# pyright: reportPrivateUsage=false

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.context import (
    AgentAuthoringContext,
    InMemoryAgentContextToolCatalog,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    agent_input_payload,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
    AgentContextPolicy,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    list_prompt_input_contracts,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from tests.web_backend.test_default_prompt_contracts import DEFAULTS
from tests.web_backend.test_logical_executor import (
    _CLAIM_TOKEN,
    _AgentExecutor,
    _candidate,
    _context_bundle,
    _empty_candidate,
    _plan,
    _principal,
    _selected_object,
    _service,
)


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_27_objects_883_attributes_require_complete_repair(
    mode: str, repair_succeeds: bool
) -> None:
    bundle = _context_bundle(mode=mode)
    raw = bundle.context.model_dump(mode="json")
    selected: list[dict[str, Any]] = []
    complete = cast(dict[str, Any], _candidate())
    entity_template = deepcopy(complete["entities"][0])
    attribute_template = deepcopy(complete["attributes"][0])
    complete["entities"] = cast(list[dict[str, Any]], [])
    complete["attributes"] = cast(list[dict[str, Any]], [])
    for index in range(27):
        item = cast(dict[str, Any], deepcopy(_selected_object()))
        item["selection_order"] = index + 1
        object_name = "customer_raw" if index == 0 else f"source_{index}"
        entity_name = "Customer" if index == 0 else f"Entity{index}"
        item["object"]["object_name"] = object_name
        source_key = {
            key: item["object"][key]
            for key in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        }
        entity = deepcopy(entity_template)
        entity["logical_entity_name"] = entity_name
        entity["sources"][0]["source_object"] = source_key
        complete["entities"].append(entity)
        physical_template = deepcopy(item["attributes"][0])
        item["attributes"] = cast(list[dict[str, Any]], [])
        for column in range(33 if index < 26 else 25):
            name = "customer_id" if column == 0 else f"column_{column}"
            physical = {
                **physical_template,
                "object_name": object_name,
                "attribute_name": name,
                "attribute_ordinal_position": column + 1,
            }
            item["attributes"].append(physical)
            attribute = deepcopy(attribute_template)
            attribute.update(
                logical_entity_name=entity_name,
                logical_attribute_name=f"Column{column}",
                logical_attribute_ordinal_position=column + 1,
            )
            attribute["sources"][0]["source_attribute"] = {
                **source_key,
                "attribute_name": name,
            }
            complete["attributes"].append(attribute)
        selected.append(item)
    raw["selected_objects"] = selected
    context = AgentAuthoringContext.model_validate(raw, strict=False)
    catalog = (
        InMemoryAgentContextToolCatalog(
            context=context,
            max_result_bytes=2_000_000,
            max_catalog_bytes=2_000_000,
            max_page_records=20,
        )
        if mode == "tool_assisted"
        else None
    )
    bundle = replace(
        bundle,
        context=context,
        tool_catalog=catalog,
        embedded_context=catalog.manifest if catalog else cast(JsonValue, raw),
    )
    agent = _AgentExecutor(
        responses=[
            _candidate(),
            cast(JsonValue, complete) if repair_succeeds else _candidate(),
        ]
    )
    plan = _plan(mode=mode)
    default = next(
        row
        for row in DEFAULTS
        if row["model_workflow"] == "logical" and row["workflow_execution_mode"] == mode
    )
    contracts = list_prompt_input_contracts(
        model_workflow="logical",
        workflow_execution_mode=mode,
        stage_code="candidate_authoring",
    )
    stage = plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system=default["system_prompt"],
                instruction=default["instruction_prompt"],
            ),
            "variables": tuple(
                PromptVariableDefinition(
                    name=contract.name,
                    resolver_key=contract.resolver_key,
                    data_type=contract.data_type,
                    is_required=False,
                )
                for contract in contracts
                if "conceptual" not in contract.name
            ),
            "agent_tool_names": (
                tuple(default["agent_tool_names"])
                if default["agent_tool_names"] is not None
                else None
            ),
        }
    )
    plan = plan.model_copy(update={"stages": (stage,)})
    service, _, _, handoff, lifecycle = _service(
        agent=agent,
        plan=plan,
        context_bundle=bundle,
        context_policy=AgentContextPolicy(
            max_candidate_bytes=2_000_000, max_validation_issues=20
        ),
    )
    execution = service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    if repair_succeeds:
        await execution
    else:
        with pytest.raises(AgentCandidateValidationError):
            await execution
    assert len(agent.requests) == 2
    repair = cast(dict[str, Any], agent.requests[1].context)["repair"]
    assert {issue["code"] for issue in repair["validation_issues"]} == {
        "candidate.object_coverage_incomplete",
        "candidate.attribute_coverage_incomplete",
    }
    if mode == "one_shot":
        instruction = agent_input_payload(agent.requests[0])["instruction"]
        assert isinstance(instruction, str)
        assert instruction.count('"attribute_name"') == 883
        assert all(f'"source_{i}"' in instruction for i in range(1, 27))
        supplied = cast(dict[str, Any], agent.requests[0].context)["original_context"][
            "selected_objects"
        ]
        assert len(supplied) == 27
        assert sum(len(item["attributes"]) for item in supplied) == 883
    else:
        assert catalog is not None
        cursor = None
        attribute_count = object_count = 0
        while True:
            page = cast(
                dict[str, Any],
                catalog.invoke(
                    "get_object_details",
                    {"cursor": cursor} if cursor else {},
                ),
            )
            object_count += len(page["items"])
            attribute_count += sum(len(item["attributes"]) for item in page["items"])
            cursor = page["next_cursor"]
            if page["is_complete"]:
                break
        assert (object_count, attribute_count) == (27, 883)
    if not repair_succeeds:
        assert handoff.calls == []
        assert len(handoff.retained) == 1
        assert {issue.dataset for issue in handoff.retained[0]["issues"]} == {
            "logical_entity",
            "logical_attribute",
        }
        return
    assert len(handoff.calls) == 1 and lifecycle.failed is None
    entities = next(
        change for change in handoff.calls[0] if change.dataset == "logical_entity"
    )
    attributes = next(
        change for change in handoff.calls[0] if change.dataset == "logical_attribute"
    )
    assert len(entities.records) == 27
    assert sum(bool(record["sources"]) for record in attributes.records) == 883
    assert handoff.final_events[0].attempt == 2


async def test_empty_fresh_model_is_rejected_without_success_handoff() -> None:
    agent = _AgentExecutor(responses=[_empty_candidate(), _empty_candidate()])
    service, _, _, handoff, lifecycle = _service(agent=agent)
    with pytest.raises(AgentCandidateValidationError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )
    assert len(agent.requests) == 2
    assert handoff.calls == []
    assert lifecycle.failed is not None
