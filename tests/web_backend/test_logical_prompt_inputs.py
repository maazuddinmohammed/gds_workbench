"""Logical Build and Optimize stages read their own input sets from the actual call context."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from jsonschema import Draft202012Validator
from pydantic import JsonValue
from tests.mcp.project_test_fixtures import complete_project_graph, snapshot_from_graph
from tests.web_backend.test_logical_executor import (
    _context_bundle,
    _plan,
    _saved_customer,
    _validation_context,
)

from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    InMemoryAgentContextToolCatalog,
    focus_subject_area,
    modeled_layer_dependencies,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import WORKFLOW_INPUTS
from gds_workbench_api.features.workflows.authoring.context_inputs import (
    _logical_optimize_inputs,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    list_prompt_input_contracts,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition


def _call_bundle(mode: str, operation: Literal["build", "optimize"]) -> AgentContextBundle:
    """The bundle one agent call receives, over a saved Customer built from customer_raw."""
    loaded = _validation_context(
        _context_bundle(mode=mode, operation=operation), graph=_saved_customer()
    )
    if operation == "optimize":
        return loaded
    plan = _plan(mode=mode)
    assert loaded.snapshot is not None
    focused = focus_subject_area(
        loaded, plan=plan, subject_area=plan.subject_areas[0], logical=loaded.snapshot.logical
    )
    assert focused is not None
    return focused


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("operation", ["build", "optimize"])
def test_stage_inputs_match_actual_context_and_documented_contracts(
    mode: str, operation: Literal["build", "optimize"]
) -> None:
    stage_code = f"{operation}_authoring"
    contracts = list_prompt_input_contracts(
        project_workflow="logical", workflow_execution_mode=mode, stage_code=stage_code
    )
    input_set = "logical" if operation == "build" else "logical_optimize"
    assert [contract.name for contract in contracts] == list(WORKFLOW_INPUTS[input_set])
    plan = _plan(mode=mode, operation=operation)
    stage = plan.stages[0].model_copy(
        update={
            "variables": tuple(
                PromptVariableDefinition(
                    name=contract.name,
                    resolver_key=contract.resolver_key,
                    data_type=contract.data_type,
                    is_required=False,
                )
                for contract in contracts
            )
        }
    )
    plan = plan.model_copy(update={"stages": (stage,)})
    bundle = _call_bundle(mode, operation)
    context = bundle.embedded_context
    before = deepcopy(context)

    values = project_prompt_input_values(
        plan=plan,
        stage=stage,
        context=context,
        resolver_values={},
        precomputed_values=bundle.tool_catalog.prompt_values if bundle.tool_catalog else None,
    )

    assert context == before
    for contract in contracts:
        schema = cast(Any, Draft202012Validator(contract.value_schema))
        assert not list(schema.iter_errors(contract.example)), contract.name
        assert not list(schema.iter_errors(values[contract.resolver_key])), contract.name
    prefix = f"workflow.logical.common.{stage_code}.inputs."
    assert values[prefix + "table_index"] == [
        {
            "table": "t1",
            "tenant_code": "NWA",
            "system_code": "CRM",
            "connection_code": "SOURCE",
            "object_schema": "bronze",
            "object_name": "customer_raw",
        }
    ]
    if operation == "build":
        assert values[prefix + "subject_area_context"] == {
            "name": "Customers",
            "definition": "Customers business area.",
            "input_count": 1,
        }
        # The saved Customer is built from this area's table, so it is shown in full.
        existing = cast(dict[str, Any], values[prefix + "existing_entities"])
        assert [(entity["name"], entity["sources"]) for entity in existing["entities"]] == [
            ("Customer", ["t1"])
        ]
        assert values[prefix + "neighbor_entities"] == []
        assert values[prefix + "entity_directory"] == []
    else:
        summary = cast(dict[str, Any], values[prefix + "model_summary"])
        assert [
            (entity["name"], entity["subject_areas"], entity["sources"])
            for entity in summary["entities"]
        ] == [("Customer", ["Customers"], ["t1"])]
        for finding in ("unlinked_analysis_edges", "type_conflicts", "name_variants"):
            assert values[prefix + finding] == []
    if mode == "one_shot":
        # A frozen input that no longer matches its contract fails closed.
        broken = cast(dict[str, JsonValue], deepcopy(context))
        cast(dict[str, JsonValue], broken["prompt_inputs"])["table_index"] = "t1"
        with pytest.raises(InvalidRequestError):
            project_prompt_input_values(plan=plan, stage=stage, context=broken, resolver_values={})


def test_logical_manifest_contains_actual_applied_and_downstream_datasets() -> None:
    snapshot = snapshot_from_graph(complete_project_graph())
    context = _context_bundle(mode="tool_assisted").context
    context = context.model_copy(
        update={
            "applied": context.applied.model_copy(update={"logical": snapshot.logical}),
            "read_only_dependencies": modeled_layer_dependencies(
                snapshot, modeled_entity_type="logical_entity"
            ),
        }
    )
    catalog = InMemoryAgentContextToolCatalog(
        context=context,
        max_result_bytes=8192,
        max_catalog_bytes=1024 * 1024,
        max_page_records=20,
    )

    datasets = cast(dict[str, Any], catalog.manifest)["dataset_counts"]

    assert {
        "logical_entity",
        "logical_attribute",
        "logical_relationship",
        "read_only_mapping_object",
        "read_only_generated_code",
    } <= set(datasets)
    # Subject Areas choose tables; they are not datasets of a Logical context.
    assert not {"subject_area", "subject_area_table"} & set(datasets)


def test_optimize_context_adds_records_only_the_detailed_entities_cite() -> None:
    shown, unshown = (f"00000000-0000-4000-8000-00000000000{n}" for n in (1, 2))

    def entity(name: str, cites: str) -> dict[str, Any]:
        return {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": name,
            "logical_entity_type": "core",
            "logical_entity_definition": f"One {name}.",
            "logical_entity_grain": f"One row per {name}.",
            "logical_entity_is_active": True,
            "logical_entity_is_locked": False,
            "sources": [
                {
                    "support_source_type": "context_record",
                    "context_record": {"context_record_id": cites},
                    "is_active": True,
                }
            ],
        }

    group = {
        "context_group_name": "Rules",
        "context_type_name": "Logical Requirement",
        "source_system_code": None,
        "is_active": True,
    }
    context: dict[str, Any] = {
        "applied": {
            "logical": {
                # Customer and Customers are a name variant, so only they are detailed.
                "entities": [
                    entity("Customer", shown),
                    entity("Customers", shown),
                    entity("Product", unshown),
                ],
                "attributes": [],
                "relationships": [],
                "entity_types": [],
            }
        },
        "analysis_relationships": [],
        "context": {
            "types": [{"context_type_name": "Logical Requirement", "context_type_workflows": []}],
            "groups": [group],
            "records": [
                {
                    "context_record_id": record_id,
                    "context_group_name": "Rules",
                    "context_text": "A rule.",
                    "source_reference": None,
                    "status": "active",
                }
                for record_id in (shown, unshown)
            ],
        },
    }

    values = _logical_optimize_inputs(context, {}, [])

    assert [row["name"] for row in values["entity_details"]["entities"]] == [
        "Customer",
        "Customers",
    ]
    assert [row["context_record_id"] for row in values["context_records"]] == [shown]


def test_optimize_flags_one_subject_named_once_per_source_system() -> None:
    def entity(name: str) -> dict[str, Any]:
        return {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": name,
            "logical_entity_type": "core",
            "logical_entity_definition": f"One {name}.",
            "logical_entity_grain": f"One row per {name}.",
            "logical_entity_is_active": True,
            "logical_entity_is_locked": False,
            "sources": [],
        }

    context: dict[str, Any] = {
        "applied": {
            "logical": {
                "entities": [entity("CRMCustomer"), entity("Customer_ERP"), entity("Product")],
                "attributes": [],
                "relationships": [],
                "entity_types": [],
            }
        },
        "analysis_relationships": [],
        "source_context": [{"system_code": "CRM"}, {"system_code": "ERP"}],
        "context": {"types": [], "groups": [], "records": []},
    }

    values = _logical_optimize_inputs(context, {}, [])

    assert values["name_variants"] == [
        {"kind": "entity", "names": ["silver.CRMCustomer", "silver.Customer_ERP"]}
    ]
    assert [row["name"] for row in values["entity_details"]["entities"]] == [
        "CRMCustomer",
        "Customer_ERP",
    ]
