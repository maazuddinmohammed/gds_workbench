"""Mapping inputs follow actual pair preparation, not generic authoring context."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from typing import Any, cast

import pytest
from atlas_mcp.domain.errors import InvalidRequestError
from atlas_platform.features.mapping import assess_mapping_readiness
from atlas_platform.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from atlas_platform.features.mapping.preparation_contracts import MappingTargetDependencyEdge
from atlas_platform.features.workflows.authoring.context import (
    AgentContextToolRequestError,
)
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    compact_mapping_basis,
    downstream_input_contracts,
)
from atlas_platform.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from atlas_platform.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from jsonschema import Draft202012Validator

from tests.web_backend.mapping_fixtures import mapping_preparation


@pytest.mark.parametrize("batch", [None, "GDSBatchID", "absent"])
def test_mapping_basis_preserves_batch_registration_state(batch: str | None) -> None:
    preparation = mapping_preparation()
    context = build_mapping_execution_context(
        preparation=preparation, execution_mode="one_shot"
    ).embedded_context
    assert isinstance(context, dict)
    values = cast(dict[str, Any], context["values"])
    source = values["source_evidence"][0]["object"]
    if batch == "absent":
        source.pop("batch_attribute_name", None)
    else:
        source["batch_attribute_name"] = batch
    card = next(row["record"] for row in compact_mapping_basis(values) if row["kind"] == "source")
    if batch == "absent":
        assert "batch_attribute_name" not in card
    else:
        assert "batch_attribute_name" in card
        assert card["batch_attribute_name"] == batch


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("entity_type", ["logical_entity", "dimensional_entity"])
def test_mapping_inputs_preserve_actual_pair_and_evidence(
    mode: Any, entity_type: Any
) -> None:
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
                    data_type="text"
                    if inputs[name][0].get("type") == "string"
                    else "json",
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
            project_workflow="mapping",
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
    assert "project_object_binding_id" not in headers[0]
    assert headers[0]["attribute_mappings"][0]["modeled_attribute_name"] == "CustomerID"
    assert before == context and values["legacy"] is context
    with pytest.raises(InvalidRequestError):
        project_prompt_input_values(
            plan=plan,
            stage=stage,
            context=context,
            resolver_values={prefix + next(iter(inputs)): "wrong"},
        )


def test_mapping_basis_pages_wide_sources_and_retains_ambiguous_late_candidates() -> (
    None
):
    preparation = mapping_preparation(execution_mode="one_shot", existing=True)
    context = build_mapping_execution_context(
        preparation=preparation, execution_mode="one_shot"
    ).embedded_context
    assert isinstance(context, dict)
    values = cast(dict[str, Any], context["values"])
    assert "mapping_basis" not in values
    physical = values["source_evidence"][0]
    candidate = deepcopy(physical)
    candidate.update(
        role="candidate", rationale="Separate connection with the same table name."
    )
    candidate["object"]["connection_code"] = "alternate"
    values["source_evidence"].insert(0, candidate)
    column = physical["object"]["attributes"][0]
    candidate["object"]["attributes"].extend(
        {**column, "attribute_name": f"fallback_{index}"} for index in range(30)
    )
    physical["object"]["attributes"].extend(
        {**column, "attribute_name": f"active_{index}", "is_natural_key": index == 65}
        for index in range(66)
    )
    physical["object"]["attributes"].append(
        {**column, "attribute_name": "retired", "is_active": False}
    )
    values["mapping_support_records"].append(
        {
            "evidence_type": "context_record",
            "record": {"rule": "Use the alternate connection."},
        }
    )

    cards = compact_mapping_basis(values)
    target, field = cards[:2]
    assert (
        target["record"]["saved"]
        == values["existing_mapping"][0]["transformation_document"]
    )
    assert (
        field["record"]["saved"]
        == values["existing_mapping"][0]["attribute_mappings"][0][
            "transformation_document"
        ]
    )
    lineage = values["mapping_support_records"][0]["record"]
    assert field["record"]["sources"] == lineage["sources"]
    assert field["record"]["action"] == "extend"
    source, fallback = [card["record"] for card in cards if card["kind"] == "source"]
    assert source["object_name"] == fallback["object_name"]
    assert source["connection_code"] != fallback["connection_code"]
    assert source["tenant_catalog"] == physical["object"]["tenant_catalog"]
    assert fallback["rationale"] == candidate["rationale"]
    directory_position = cards.index({"kind": "source", "record": fallback})
    assert cards[directory_position - 1]["kind"] == "context_record"
    columns = [
        dict(zip(source["column_fields"], row["record"]["values"], strict=True))
        for row in cards
        if row["kind"] == "column" and row["record"]["source"] == source["ref"]
    ]
    assert len(columns) == 67 and columns[-1]["is_natural_key"] is True
    assert columns[-2]["is_natural_key"] is False

    reader = build_downstream_readers(
        "mapping",
        values,
        max_result_bytes=1600,
        max_page_records=12,
        max_cumulative_result_bytes=32_000,
    )
    page = reader.invoke("get_mapping_basis", {})
    assert page["next_cursor"] is not None
    items = list(page["items"])
    while page["next_cursor"] is not None:
        page = reader.invoke("get_mapping_basis", {"cursor": page["next_cursor"]})
        items.extend(page["items"])
    assert items == cards[: directory_position + 1]
    assert (
        reader.invoke("get_mapping_basis", {"candidate_refs": []})["items"]
        == (reader.invoke("get_mapping_basis", {})["items"])
    )
    page = reader.invoke("get_mapping_basis", {"candidate_refs": [fallback["ref"]]})
    assert page["next_cursor"] is not None
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke(
            "get_mapping_basis",
            {"cursor": page["next_cursor"], "candidate_refs": [source["ref"]]},
        )
    selected = list(page["items"])
    while page["next_cursor"] is not None:
        page = reader.invoke("get_mapping_basis", {"cursor": page["next_cursor"]})
        selected.extend(page["items"])
    assert selected == cards[directory_position:]
    for invalid in (
        source["ref"],
        "s999",
        fallback["object_name"],
        fallback["ref"].upper(),
    ):
        with pytest.raises(AgentContextToolRequestError):
            reader.invoke(
                "get_mapping_basis", {"candidate_refs": [fallback["ref"], invalid]}
            )
    assert "mapping_basis" not in values


def test_saved_custom_mapping_prompt_resolves_only_named_jinja_inputs() -> None:
    prep = mapping_preparation(execution_mode="one_shot", existing=True)
    plan = prep.plan.agent_plan
    prefix = "workflow.mapping.common.mapping_authoring.inputs."
    stage = plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="The word mapping_basis here is ordinary text.",
                instruction="{% for source in source_evidence %}{{ source.role }}{% endfor %}",
            ),
            "variables": tuple(
                PromptVariableDefinition(
                    name=name,
                    resolver_key=prefix + name,
                    data_type="json",
                    is_required=False,
                )
                for name in ("source_evidence", "mapping_basis")
            ),
        }
    )
    # The older frozen prompt still resolves even without any data for a compact basis.
    available: dict[str, object] = {"source_evidence": []}
    result = project_prompt_input_values(
        plan=plan,
        stage=stage,
        context={},
        resolver_values={},
        precomputed_values=available,
        only_referenced=True,
    )
    assert result == {prefix + "source_evidence": []}


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
def test_mapping_basis_marks_only_the_cyclic_fk_for_initial_mapping(mode: Any) -> None:
    prep = mapping_preparation(attribute_count=2, execution_mode=mode)
    independent, cyclic = (a.attribute_name for a in prep.context.target.attributes)
    target = prep.context.target
    self_lookup = prep.context.sources[0].model_copy(update={"role": "lookup", "object": target})
    self_edge = MappingTargetDependencyEdge(
        predecessor_modeled_entity_id=target.entity_id,
        successor_modeled_entity_id=target.entity_id,
        child_attribute_names=(cyclic,),
    )
    context = prep.context.model_copy(update={
        "sources": (*prep.context.sources, self_lookup),
        "target_dependency_graph": prep.context.target_dependency_graph.model_copy(
            update={"edges": (self_edge,)}
        ),
    })
    readiness = assess_mapping_readiness(plan=prep.plan, context=context)
    assert readiness.ready and readiness.deferred_dependency_attributes == (cyclic,)
    assert "deferred_dependency_parent_ids" not in readiness.model_dump()
    prep = prep.model_copy(update={"context": context, "readiness": readiness})
    agent_plan = prep.plan.agent_plan
    stage = agent_plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="Map the target.", instruction="{{ mapping_basis }}"
            )
        }
    )
    plan = prep.plan.model_copy(
        update={"agent_plan": agent_plan.model_copy(update={"stages": (stage,)})}
    )
    request = build_mapping_execution_context(
        preparation=prep.model_copy(update={"plan": plan}), execution_mode=mode
    )
    if mode == "one_shot":
        cards = cast(dict[str, Any], request.embedded_context)["values"]["mapping_basis"]
    else:
        assert request.tool_catalog is not None
        page = cast(dict[str, Any], request.tool_catalog.invoke("get_mapping_basis", {}))
        cards = page["items"]
    fields = {c["record"]["attribute_name"]: c["record"] for c in cards if c["kind"] == "field"}
    assert fields[cyclic]["defer_lookup"] is True
    assert "defer_lookup" not in fields[independent]
    directory = [row["record"] for row in cards if row["kind"] == "source"]
    assert {row["role"] for row in directory} == {"support"}
    assert directory[0]["object_name"] == "customer"
