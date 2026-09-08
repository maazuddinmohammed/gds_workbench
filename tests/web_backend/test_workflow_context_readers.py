"""Frozen nominal-key readers and compact prompt projections."""

# Reuse synthetic executor fixtures at the shared input boundary.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import AnalysisResultRecord
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolResultTooLargeError,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    InMemoryAgentContextToolCatalog,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    INPUT_EXAMPLES,
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import OBJECT_FIELDS
from gds_workbench_api.features.workflows.authoring.context_readers import (
    FrozenContextReaders,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    project_prompt_input_values,
)
from gds_workbench_api.features.workflows.authoring.tool_configuration import (
    ConfiguredToolCatalog,
    configure_tools,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from jsonschema import Draft202012Validator

from tests.web_backend.test_analysis_executor import _candidate, _context_bundle, _plan


def catalog(
    workflow: str = "analysis",
    *,
    size: int = 100_000,
    page: int = 200,
    values: dict[str, Any] | None = None,
) -> FrozenContextReaders:
    return FrozenContextReaders(
        workflow=workflow,
        values=values or INPUT_EXAMPLES[workflow],
        max_result_bytes=size,
        max_page_records=page,
        max_cumulative_result_bytes=200_000,
    )


def physical_key(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in OBJECT_FIELDS}


@pytest.mark.parametrize("workflow", ["analysis", "conceptual", "logical"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("locked", [False, True])
def test_existing_relationships_preserve_the_registered_lock_field(
    workflow: str,
    mode: str,
    locked: bool,
) -> None:
    relationship = AnalysisResultRecord.model_validate(
        {
            **cast(dict[str, Any], _candidate())["relationships"][0],
            "analysis_result_status": "active",
            "analysis_result_is_locked": locked,
        }
    )
    context = _context_bundle().context.model_copy(
        update={
            "model_workflow": workflow,
            "workflow_execution_mode": mode,
            "analysis_relationships": (relationship,),
        }
    )
    plan = _plan().model_copy(update={"model_workflow": workflow, "workflow_execution_mode": mode})
    code = "relationship_inference" if workflow == "analysis" else "candidate_authoring"
    key = f"workflow.{workflow}.common.{code}.inputs.object_relationship_context"
    stage = plan.stages[0].model_copy(
        update={
            "stage_code": code,
            "variables": (
                PromptVariableDefinition(
                    name="object_relationship_context",
                    resolver_key=key,
                    data_type="json",
                    is_required=False,
                ),
            ),
        }
    )
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
    values = project_prompt_input_values(
        plan=plan,
        stage=stage,
        context=readers.manifest if readers else context.model_dump(mode="json"),
        resolver_values={},
        precomputed_values=readers.prompt_values if readers else None,
    )
    groups = cast(list[dict[str, Any]], values[key])
    assert groups[0]["incoming_relationships"] == groups[1]["outgoing_relationships"] == []
    expected = relationship.model_dump(
        mode="json",
        exclude={
            field for field in AnalysisResultRecord.model_fields if field.startswith("validation_")
        },
    )
    assert groups[0]["outgoing_relationships"] == groups[1]["incoming_relationships"] == [expected]
    assert expected["analysis_result_is_locked"] is locked
    if readers:
        result = cast(dict[str, Any], readers.invoke("get_object_relationships", {}))
        assert result["items"] == groups


@pytest.mark.parametrize(
    ("workflow", "count"),
    [
        ("analysis", 6),
        ("conceptual", 10),
        ("logical", 18),
        ("dimensional", 21),
    ],
)
def test_approved_schema_examples_and_every_no_input_reader(workflow: str, count: int) -> None:
    reader = catalog(workflow)
    assert len(reader.definitions) == count
    for definition in workflow_input_contracts(workflow).values():
        Draft202012Validator.check_schema(definition["schema"])
        assert cast(Any, Draft202012Validator(definition["schema"])).is_valid(definition["example"])
    for tool in reader.definitions:
        assert cast(Any, Draft202012Validator(tool.input_schema)).is_valid({})
        result = reader.invoke(tool.name, {})
        assert isinstance(result, dict) and result["is_complete"] is True
        assert set(result) == {
            "items",
            "next_cursor",
            "is_complete",
            "incomplete_object_key",
        }


def test_source_connection_filter_returns_actual_gds_keys_and_never_broadens() -> None:
    reader = catalog()
    values = INPUT_EXAMPLES["analysis"]
    source = {f: values["source_context"][0][f] for f in OBJECT_FIELDS[:3]}
    result = reader.invoke("get_objects", {"source_connection_key": source})
    assert result["items"] == values["object_context"]
    assert all(obj["tenant_code"] != source["tenant_code"] for obj in result["items"])
    key = physical_key(result["items"][0])
    details = reader.invoke("get_object_details", {"object_keys": [key, key]})
    assert len(details["items"]) == 1
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke(
            "get_objects",
            {"source_connection_key": {"connection_code": source["connection_code"]}},
        )
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke("get_object_details", {"object_keys": [{**key, "tenant_code": "UNKNOWN"}]})
    assert reader.invoke("get_object_details", {"object_keys": []}) == reader.invoke(
        "get_object_details", {}
    )


def test_cursors_keep_frozen_filter_and_repeat_deterministically() -> None:
    reader = catalog(page=1)
    first = reader.invoke("get_object_details", {})
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)
    second = reader.invoke("get_object_details", {"cursor": cursor})
    assert second == reader.invoke("get_object_details", {"cursor": cursor, "object_keys": []})
    first["items"].clear()
    assert reader.invoke("get_object_details", {})["items"]
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke("get_objects", {"cursor": cursor})
    with pytest.raises(AgentContextToolRequestError):
        catalog(page=1).invoke("get_object_details", {"cursor": cursor})
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke(
            "get_object_details",
            {"cursor": cursor, "object_keys": [physical_key(second["items"][0])]},
        )


def test_physical_groups_continue_by_whole_attributes_with_explicit_marker() -> None:
    values = deepcopy(INPUT_EXAMPLES["analysis"])
    group = values["object_attribute_context"][0]
    prototype = group["attributes"][0]
    group["attributes"] = [{**prototype, "attribute_name": f"field_{n}"} for n in range(12)]
    group["selected_attribute_names"] = [attr["attribute_name"] for attr in group["attributes"]]
    values["object_attribute_context"] = [group]
    reader = catalog(values=values, size=1800)
    page = reader.invoke("get_object_details", {})
    assert page["incomplete_object_key"] == physical_key(group)
    recovered: list[dict[str, Any]] = []
    names: list[str] = []
    while True:
        assert len(page["items"]) == 1
        part = page["items"][0]
        recovered.extend(part["attributes"])
        names.extend(part["selected_attribute_names"])
        if page["is_complete"]:
            assert page["incomplete_object_key"] is None
            break
        page = reader.invoke("get_object_details", {"cursor": page["next_cursor"]})
    assert recovered == group["attributes"]
    assert names == group["selected_attribute_names"]


def test_saved_model_records_are_whole_and_unavailable_is_not_empty() -> None:
    values = deepcopy(INPUT_EXAMPLES["logical"])
    values["logical_entities"][0]["logical_entity_definition"] = "x" * 2000
    reader = catalog("logical", values=values, size=1000)
    assert reader.invoke("list_logical_entities", {})["items"]
    with pytest.raises(AgentContextToolResultTooLargeError):
        reader.invoke("get_logical_entities", {})
    values["logical_entities"] = None
    with pytest.raises(AgentContextToolRequestError):
        catalog("logical", values=values).invoke("get_logical_entities", {})


def test_empty_tool_selection_is_valid_and_preserves_inline_inputs() -> None:
    reader = catalog()
    configured = configure_tools(reader, (), workflow="analysis", execution_mode="tool_assisted")
    assert isinstance(configured, ConfiguredToolCatalog) and configured.definitions == ()
    assert configured.prompt_values == reader.prompt_values
    with pytest.raises(InvalidRequestError, match="not enabled"):
        configured.invoke("get_objects", {})


@pytest.mark.parametrize("workflow", ["code_generation", "validation"])
def test_workflows_without_public_modes_can_choose_any_or_no_readers(
    workflow: str,
) -> None:
    from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
        build_downstream_readers,
        downstream_input_contracts,
    )
    from gds_workbench_api.features.workflows.authoring.tool_configuration import (
        AgentToolName,
    )

    values = {
        name: example for name, (_, _, example) in downstream_input_contracts(workflow).items()
    }
    reader = build_downstream_readers(
        workflow,
        values,
        max_result_bytes=100_000,
        max_page_records=100,
        max_cumulative_result_bytes=200_000,
    )
    first_name = cast(AgentToolName, reader.definitions[0].name)
    selected = configure_tools(reader, (first_name,), workflow=workflow, execution_mode=None)
    assert selected is not None and tuple(d.name for d in selected.definitions) == (first_name,)
    assert selected.invoke(first_name, {}) == reader.invoke(first_name, {})
    empty = configure_tools(reader, (), workflow=workflow, execution_mode=None)
    assert empty is not None and empty.definitions == ()
    with pytest.raises(InvalidRequestError, match="not enabled"):
        empty.invoke(first_name, {})
