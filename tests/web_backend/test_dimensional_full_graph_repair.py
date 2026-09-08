"""Projection and full-graph repair using real canonical graphs."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_workbench_api.features.dimensional.service import (
    _candidate_validator,
    _project_dimensional_changes,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    InMemoryAgentContextToolCatalog,
    modeled_layer_dependencies,
)
from gds_workbench_api.features.workflows.authoring.repair import AgentCandidateValidationError
from pydantic import JsonValue

from tests.mcp.model_test_fixtures import (
    GOLD_CUSTOMER,
    SILVER_ORDER,
    attribute_binding,
    complete_model_graph,
    complete_physical_scope,
    object_binding,
    snapshot_from_graph,
)
from tests.web_backend.test_dimensional_executor import (
    _CLAIM_TOKEN,
    _AgentExecutor,
    _candidate,
    _context_bundle,
    _plan,
    _principal,
    _service,
)


def _complete_model_candidate() -> dict[str, JsonValue]:
    full = cast(dict[str, JsonValue], deepcopy(_candidate()))
    submodel = cast(list[JsonValue], full["submodels"])[0]
    entity = cast(list[JsonValue], full["entities"])[0]
    attributes = cast(list[dict[str, JsonValue]], full["attributes"])
    customer_id = attributes[0]
    sale_customer_id = attributes[1]
    sale_customer_id.update(
        {
            "dimensional_entity_name": "Customer Dimension",
            "dimensional_attribute_name": "Sale Customer ID",
            "dimensional_attribute_definition": "Sale-side customer identifier.",
            "dimensional_attribute_is_nullable": False,
            "dimensional_attribute_ordinal_position": 2,
            "dimensional_attribute_change_behavior": "fixed",
        }
    )
    customer_segment = deepcopy(customer_id)
    customer_segment.update(
        {
            "dimensional_attribute_name": "Customer Segment",
            "dimensional_attribute_definition": "Governed customer segment.",
            "dimensional_attribute_is_nullable": True,
            "dimensional_attribute_ordinal_position": 3,
            "dimensional_attribute_role": "descriptor",
            "dimensional_attribute_key_role": "none",
            "dimensional_attribute_is_grain_component": False,
            "dimensional_attribute_change_behavior": "overwrite",
            "sources": [
                {
                    "support_source_type": "assertion",
                    "assertion_record": {
                        "modeling_assertion_record_key": "assertion.customer_segment"
                    },
                    "source_order": 1,
                    "rationale": "Governed customer-segmentation assertion.",
                    "status": "active",
                    "is_locked": False,
                }
            ],
        }
    )
    return {
        "submodels": [submodel],
        "entities": [entity],
        "attributes": [customer_id, sale_customer_id, customer_segment],
        "relationships": [],
    }


def _physical_sources(value: Any) -> Any:
    if isinstance(value, list):
        return [_physical_sources(item) for item in cast(list[Any], value)]
    if not isinstance(value, dict):
        return value
    result = {name: _physical_sources(item) for name, item in cast(dict[str, Any], value).items()}
    if result.get("object_name") == "sales_customer":
        result.update(
            dict(
                zip(
                    (
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    ),
                    SILVER_ORDER,
                    strict=True,
                )
            )
        )
        if "source_tenant_code" in result:
            result["source_tenant_code"] = "TENANT-A"
        if "attribute_name" in result:
            result["attribute_name"] = {"customer_id": "CustomerID", "sale_customer_id": "OrderID"}[
                result["attribute_name"]
            ]
    return result


def _bundle(*, bound: bool) -> tuple[AgentContextBundle, dict[str, Any]]:
    initial = _context_bundle()
    context = initial.context.model_validate(
        _physical_sources(initial.context.model_dump(mode="json")), strict=False
    )
    graph = complete_model_graph()
    for dataset in tuple(graph):
        if dataset.startswith(("dimensional_", "generated_code", "validation_")):
            graph[dataset] = []
        elif dataset.startswith(("model_object_binding", "model_attribute_binding", "mapping_")):
            graph[dataset] = [
                record
                for record in graph[dataset]
                if record.get("modeled_entity_type") != "dimensional_entity"
            ]
    graph["model_details"] = [context.model_details.model_dump(mode="json")]
    graph["modeling_assertion_document"].extend(
        item.model_dump(mode="json") for item in context.assertion.documents
    )
    graph["modeling_assertion_record"].extend(
        item.model_dump(mode="json") for item in context.assertion.records
    )
    scope = complete_physical_scope()
    snapshot = snapshot_from_graph(graph)
    assert validate_future_graph(snapshot=snapshot, staged_documents={}, physical_scope=scope).valid
    candidate = cast(dict[str, Any], _physical_sources(_complete_model_candidate()))
    bundle = replace(initial, context=context, snapshot=snapshot, physical_scope=scope)
    validator = _candidate_validator(bundle)
    projected = _project_dimensional_changes(
        validator=validator, candidate=cast(JsonValue, candidate), context=bundle
    )
    assert validate_future_graph(
        snapshot=snapshot,
        staged_documents={item.dataset: item.records for item in projected},
        physical_scope=scope,
    ).valid
    if bound:
        for item in projected:
            graph[item.dataset] = item.records
        graph["model_object_binding"].append(
            object_binding("dimensional_entity", "Customer Dimension", GOLD_CUSTOMER)
        )
        attributes = graph["dimensional_attribute"]
        gold = tuple(part.casefold() for part in GOLD_CUSTOMER)
        physical_attributes = frozenset(
            (*gold, f"column_{index}") for index in range(len(attributes))
        )
        for index, attribute in enumerate(attributes):
            graph["model_attribute_binding"].append(
                attribute_binding(
                    "dimensional_entity",
                    "Customer Dimension",
                    cast(str, attribute["dimensional_attribute_name"]),
                    f"column_{index}",
                )
            )
        scope = replace(
            scope,
            attributes=frozenset(key for key in scope.attributes if key[:5] != gold)
            | physical_attributes,
            dimensional_mapping_target_attributes=frozenset(
                key for key in scope.dimensional_mapping_target_attributes if key[:5] != gold
            )
            | physical_attributes,
        )
        snapshot = snapshot_from_graph(graph)
        assert validate_future_graph(
            snapshot=snapshot, staged_documents={}, physical_scope=scope
        ).valid
        context = context.model_copy(
            update={
                "applied": context.applied.model_copy(update={"dimensional": snapshot.dimensional})
            }
        )
        bundle = replace(bundle, context=context, snapshot=snapshot, physical_scope=scope)
    return bundle, candidate


@pytest.mark.asyncio
@pytest.mark.parametrize("bound", [False, True], ids=["new_unbound", "retained_bound"])
async def test_local_status_passes_but_complete_graph_rejects_active_children(bound: bool) -> None:
    bundle, candidate = _bundle(bound=bound)
    candidate["entities"][0]["dimensional_entity_status"] = "inactive"
    validator = _candidate_validator(bundle)
    assert not (await validator.validate(cast(JsonValue, candidate))).issues
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    projected = _project_dimensional_changes(
        validator=validator, candidate=cast(JsonValue, candidate), context=bundle
    )
    checked = validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={item.dataset: item.records for item in projected},
        physical_scope=bundle.physical_scope,
    )
    assert checked.issues and all(
        item.code == "active_dependency_invalid" for item in checked.issues
    )


@pytest.mark.asyncio
async def test_historize_is_valid_before_policy_but_breaks_retained_binding_coverage() -> None:
    bundle, candidate = _bundle(bound=True)
    candidate["attributes"][2]["dimensional_attribute_change_behavior"] = "historize"
    validator = _candidate_validator(bundle)
    assert not (await validator.validate(cast(JsonValue, candidate))).issues
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    raw = validator.parse_validated(cast(JsonValue, candidate))
    assert validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={item.dataset: item.records for item in raw},
        physical_scope=bundle.physical_scope,
    ).valid
    projected = _project_dimensional_changes(
        validator=validator, candidate=cast(JsonValue, candidate), context=bundle
    )
    checked = validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={item.dataset: item.records for item in projected},
        physical_scope=bundle.physical_scope,
    )
    assert [item.code for item in checked.issues] == ["binding_coverage_missing"]
    added = {
        record["dimensional_attribute_name"]
        for item in projected
        if item.dataset == "dimensional_attribute"
        for record in item.records
    }
    assert {"Effective From", "Effective To", "Is Current"} <= added


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("fault", ["inactive_parent", "bound_historize", "projected_name_overflow"])
@pytest.mark.parametrize("outcome", ["repair", "exhaust", "later_malformed"])
async def test_dimensional_projection_and_graph_failures_enter_bounded_repair(
    mode: str,
    fault: str,
    outcome: str,
) -> None:
    bundle, valid = _bundle(bound=fault == "bound_historize")
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    context = bundle.context.model_copy(
        update={
            "workflow_execution_mode": mode,
            "read_only_dependencies": modeled_layer_dependencies(
                bundle.snapshot, modeled_entity_type="dimensional_entity"
            ),
        }
    )
    catalog = (
        InMemoryAgentContextToolCatalog(
            context=context,
            max_result_bytes=128 * 1024,
            max_catalog_bytes=128 * 1024,
            max_page_records=20,
        )
        if mode == "tool_assisted"
        else None
    )
    bundle = replace(
        bundle,
        context=context,
        tool_catalog=catalog,
        embedded_context=catalog.manifest
        if catalog
        else cast(JsonValue, context.model_dump(mode="json")),
    )
    invalid = deepcopy(valid)
    if fault == "inactive_parent":
        invalid["entities"][0]["dimensional_entity_status"] = "inactive"
        expected_code = "active_dependency_invalid"
    elif fault == "bound_historize":
        invalid["attributes"][2]["dimensional_attribute_change_behavior"] = "historize"
        expected_code = "binding_coverage_missing"
        assert {item.dataset for item in context.read_only_dependencies} == {
            "model_object_binding",
            "model_attribute_binding",
        }
    else:
        invalid["entities"][0]["dimensional_entity_name"] = "D" * 253
        for attribute in invalid["attributes"]:
            attribute["dimensional_entity_name"] = "D" * 253
        expected_code = "gold_projection_conflict"
    assert not (await _candidate_validator(bundle).validate(cast(JsonValue, invalid))).issues
    # Ensure the corrected bound candidate changes something, rather than becoming a no-op.
    valid["entities"][0]["dimensional_entity_definition"] = (
        "Customers represented at one customer per row."
    )
    agent = _AgentExecutor(
        responses=[
            cast(JsonValue, invalid),
            cast(
                JsonValue,
                valid if outcome == "repair" else invalid if outcome == "exhaust" else None,
            ),
        ]
    )
    service, _, _, handoff, lifecycle = _service(
        agent=agent, context=bundle, plan=_plan(mode=cast(Any, mode))
    )

    async def execute() -> None:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    if outcome == "repair":
        await execute()
        assert len(handoff.calls) == 1 and not handoff.retained
        assert bundle.snapshot is not None and bundle.physical_scope is not None
        assert (
            handoff.final_events[-1].attempt == 2 and handoff.final_events[-1].status == "warning"
        )
        assert validate_future_graph(
            snapshot=bundle.snapshot,
            staged_documents={item.dataset: item.records for item in handoff.calls[0]},
            physical_scope=bundle.physical_scope,
        ).valid
    else:
        with pytest.raises(AgentCandidateValidationError):
            await execute()
        assert not handoff.calls and len(handoff.retained) == 1
        assert handoff.retained[0]["issues"][0].code == expected_code
    assert len(agent.requests) == 2 and lifecycle.failed is None
    first, second = [cast(dict[str, Any], request.context) for request in agent.requests]
    assert first["original_context"] == second["original_context"]
    assert second["repair"]["validation_issues"][0]["code"] == "candidate." + expected_code
