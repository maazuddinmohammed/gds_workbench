"""Large synthetic selections must reach the provider and survive repair intact."""

# Reuse synthetic workflow fixtures without database or provider calls.
# pyright: reportPrivateUsage=false

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    agent_input_payload,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentAuthoringContext,
    InMemoryAgentContextToolCatalog,
)
from gds_workbench_api.features.workflows.authoring.no_op import AuthoringNoOpReceipt
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    list_prompt_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from pydantic import JsonValue

from tests.mcp.model_test_fixtures import complete_model_graph
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
async def test_27_objects_883_attributes_require_object_coverage_with_selected_attributes(
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
            # All input columns reach the agent; the design keeps one per Object.
            if column == 0:
                complete["attributes"].append(attribute)
        selected.append(item)
    selected[0]["object"]["object_description"] = "Enriched customer business meaning."
    selected[0]["attributes"][0].update(
        attribute_description="Enriched customer business identifier.",
        attribute_inferred_data_type="STRING",
        enrichment={
            "is_natural_key": True,
            "is_primary_key": True,
            "is_nullable": False,
            "is_pii": None,
        },
    )
    evidence = complete_model_graph()
    source_key = {
        key: selected[0]["object"][key]
        for key in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    # Preserve contradictory observations instead of silently trusting enrichment flags.
    raw["profiles"] = [{**evidence["profiling_profile"][0], **source_key}]
    raw["profile_provenance"] = [
        {
            **source_key,
            "attribute_name": "customer_id",
            "profiled_at": "2026-10-06T00:00:00Z",
            "row_scope": "batch",
            "batch_attribute_name": "batch_id",
            "batch_id": "synthetic-batch",
        }
    ]
    relationship = {
        **evidence["analysis_result"][0],
        **{
            f"{side}_{key}": value
            for side in ("from", "to")
            for key, value in source_key.items()
        },
        "to_object_name": "source_1",
        "validation_result": "unsupported",
        "validation_target_non_null_count": 6,
        "validation_duplicate_target_key_count": 1,
    }
    raw["analysis_relationships"] = [relationship]
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
    # Reach the 70% threshold on the second attempt, or use all three attempts.
    complete["entities"] = complete["entities"][:19]
    complete["attributes"] = [
        record for record in complete["attributes"]
        if record["logical_entity_name"] in {
            entity["logical_entity_name"] for entity in complete["entities"]
        }
    ]
    agent = _AgentExecutor(
        responses=[
            _candidate(),
            cast(JsonValue, complete) if repair_succeeds else _candidate(),
            _candidate(),
        ]
    )
    plan = _plan(mode=mode, retry_count=2)
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
    await execution
    assert len(agent.requests) == (2 if repair_succeeds else 3)
    repair = cast(dict[str, Any], agent.requests[1].context)["repair"]
    assert {issue["code"] for issue in repair["validation_issues"]} == {
        "candidate.object_coverage_incomplete",
    }
    assert len(repair["validation_issues"][0]["source_refs"]) == 26
    if mode == "one_shot":
        instruction = agent_input_payload(agent.requests[0])["instruction"]
        assert isinstance(instruction, str)
        assert instruction.count('"attribute_name"') == 883
        assert all(f'"source_{i}"' in instruction for i in range(1, 27))
        for evidence_value in (
            '"object_description":"Enriched customer business meaning."',
            '"attribute_description":"Enriched customer business identifier."',
            '"attribute_inferred_data_type":"STRING"',
            '"is_primary_key":true',
            '"is_pii":null',
            '"row_count":10',
            '"null_count":1',
            '"blank_count":0',
            '"percent_duplicates":44.4444',
            '"row_scope":"batch"',
            '"profiled_at":"2026-10-06T00:00:00Z"',
            '"relationship_confidence":"high"',
            '"validation_result":"unsupported"',
            '"validation_duplicate_target_key_count":1',
        ):
            assert evidence_value in instruction
        supplied = cast(dict[str, Any], agent.requests[0].context)["original_context"][
            "selected_objects"
        ]
        assert len(supplied) == 27
        assert sum(len(item["attributes"]) for item in supplied) == 883
    else:
        assert catalog is not None
        cursor = None
        attribute_count = object_count = 0
        supplied_details: list[dict[str, Any]] = []
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
            supplied_details.extend(page["items"])
            cursor = page["next_cursor"]
            if page["is_complete"]:
                break
        assert (object_count, attribute_count) == (27, 883)
        objects = cast(dict[str, Any], catalog.invoke("get_objects", {}))
        assert (
            objects["items"][0]["object_description"]
            == "Enriched customer business meaning."
        )
        attribute = supplied_details[0]["attributes"][0]
        assert (
            attribute["attribute_description"]
            == "Enriched customer business identifier."
        )
        assert attribute["attribute_inferred_data_type"] == "STRING"
        assert attribute["is_primary_key"] is True and attribute["is_pii"] is None
        assert attribute["profile"]["row_count"] == 10
        assert attribute["profile"]["null_count"] == 1
        assert attribute["profile"]["blank_count"] == 0
        assert attribute["profile"]["percent_duplicates"] == 44.4444
        assert attribute["profile"]["row_scope"] == "batch"
        assert attribute["profile"]["profiled_at"] == "2026-10-06T00:00:00Z"
        relationships = cast(
            dict[str, Any], catalog.invoke("get_object_relationships", {})
        )
        assert relationships["items"][0]["outgoing_relationships"] == [relationship]
    assert handoff.retained == []
    assert len(handoff.calls) == 1 and lifecycle.failed is None
    entities = next(
        change for change in handoff.calls[0] if change.dataset == "logical_entity"
    )
    attributes = next(
        change for change in handoff.calls[0] if change.dataset == "logical_attribute"
    )
    assert len(entities.records) == (19 if repair_succeeds else 1)
    assert sum(bool(record["sources"]) for record in attributes.records) == (
        19 if repair_succeeds else 1
    )
    assert handoff.final_events[0].attempt == (2 if repair_succeeds else 3)
    if not repair_succeeds:
        assert handoff.final_events[0].status == "warning"
        assert "1/27" in handoff.final_events[0].message
        assert "final attempt" in handoff.final_events[0].message


async def test_empty_final_candidate_reports_zero_coverage_without_creating_a_draft() -> None:
    agent = _AgentExecutor(responses=[_empty_candidate(), _empty_candidate()])
    service, _, _, handoff, lifecycle = _service(agent=agent)
    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    assert len(agent.requests) == 2
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.final_event.status == "warning"
    assert "0/1" in result.final_event.message
