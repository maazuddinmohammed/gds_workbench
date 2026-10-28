"""Dimensional Build inputs follow one Subject Area; Optimize inputs summarize the model."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.project import DimensionalSection, LogicalSection
from jsonschema import Draft202012Validator
from pydantic import JsonValue
from tests.mcp.project_test_fixtures import snapshot_from_graph
from tests.web_backend.test_dimensional_executor import (
    _BILLING,
    _SALES,
    _applied_dimensional_section,
    _context_bundle,
    _plan,
    _selected_logical_entity,
    _subject_areas,
)

from gds_workbench_api.features.workflows.authoring.context import (
    AgentAuthoringContext,
    InMemoryAgentContextToolCatalog,
    _provider_context,
    focus_subject_area,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    list_prompt_input_contracts,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition

_FACT_TYPES = [
    {
        "dimensional_fact_type_code": "transaction",
        "dimensional_fact_type_description": "One row per business event.",
        "dimensional_fact_type_is_active": True,
    },
    {
        "dimensional_fact_type_code": "factless",
        "dimensional_fact_type_description": "Retired here.",
        "dimensional_fact_type_is_active": False,
    },
]


# The bundle's only Context record; its Type is routed to no workflow.
_CITED = "1cdbab8d-73b2-5b3f-a650-6d5579728c83"


def _citation(record_id: str) -> dict[str, Any]:
    return {
        "support_source_type": "context_record",
        "context_record": {"context_record_id": record_id},
        "rationale": "Cited requirement.",
        "is_active": True,
        "is_locked": False,
    }


def _model(*, fact_source: str) -> dict[str, Any]:
    """Saved Customer Dimension and Sales Fact (built from fact_source) and a Product Dimension."""
    model = _applied_dimensional_section().model_dump(mode="json")
    model["fact_types"] = _FACT_TYPES
    model["entities"][1]["sources"][0]["source_logical_entity"]["logical_entity_name"] = fact_source
    product = deepcopy(model["entities"][0])
    product.update(
        dimensional_entity_name="Product Dimension",
        dimensional_entity_definition="One product. Sold in every region.",
        sources=[],
    )
    model["entities"].append(product)
    return model


def _registered_values(
    plan: AgentRunPlan,
    *,
    context: JsonValue,
    catalog: InMemoryAgentContextToolCatalog | None,
    resolver_values: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, Any]]:
    """Every registered input for the plan's stage, resolved as a saved template would."""
    stage = plan.stages[0]
    contracts = {
        contract.resolver_key: contract
        for contract in list_prompt_input_contracts(
            project_workflow="dimensional",
            workflow_execution_mode=plan.workflow_execution_mode,
            stage_code=stage.stage_code,
        )
    }
    stage = stage.model_copy(
        update={
            "variables": tuple(
                PromptVariableDefinition(
                    name=contract.name,
                    resolver_key=contract.resolver_key,
                    data_type=contract.data_type,
                    is_required=False,
                )
                for contract in contracts.values()
            )
        }
    )
    values = project_prompt_input_values(
        plan=plan,
        stage=stage,
        context=context,
        resolver_values=resolver_values or {},
        precomputed_values=catalog.prompt_values if catalog else None,
    )
    for key, contract in contracts.items():
        validator = cast(Any, Draft202012Validator(contract.value_schema))
        assert validator.is_valid(values[key]), contract.name
        assert validator.is_valid(contract.example), contract.name
    return values, {contract.name: values[key] for key, contract in contracts.items()}


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_build_inputs_show_one_area_its_links_and_the_model_around_it(
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    bundle = replace(_context_bundle(mode=mode), snapshot=snapshot_from_graph({}))
    link = {
        "from_logical_entity_schema_name": "silver_nwa",
        "from_logical_entity_name": "sales_order",
        "from_logical_attribute_name": "customer_id",
        "to_logical_entity_schema_name": "silver_nwa",
        "to_logical_entity_name": "sales_customer",
        "to_logical_attribute_name": "customer_id",
        "logical_relationship_cardinality": "many_to_one",
        "logical_relationship_basis": "Each order has one customer.",
        "logical_relationship_is_active": True,
        "logical_relationship_is_locked": False,
    }
    unrelated = {
        **link,
        "from_logical_entity_name": "sales_order",
        "from_logical_attribute_name": "product_id",
        "to_logical_entity_name": "product",
        "to_logical_attribute_name": "product_id",
    }
    raw_model = _model(fact_source="sales_order")
    raw_model["entities"][0]["sources"].append(_citation(_CITED))
    model = DimensionalSection.model_validate(raw_model, strict=False)
    focused = focus_subject_area(
        bundle,
        plan=_plan(mode=mode),
        subject_area=_SALES,
        logical=LogicalSection.model_validate(
            {"entities": [], "attributes": [], "relationships": [link, unrelated]}, strict=False
        ),
        dimensional=model,
    )
    assert focused is not None

    _, values = _registered_values(
        _plan(mode=mode), context=focused.embedded_context, catalog=focused.tool_catalog
    )

    assert values["subject_area_context"] == {
        "name": "Sales",
        "definition": "Customer sales activity.",
        "input_count": 1,
    }
    assert values["selected_logical_entities"] == [
        item.model_dump(mode="json") for item in bundle.context.selected_logical_entities
    ]
    assert values["logical_links"] == [
        {
            "from": "silver_nwa.sales_order.customer_id",
            "to": "silver_nwa.sales_customer",
            "cardinality": "many_to_one",
        }
    ]
    # The Customer Dimension is built from this area; the Sales Fact links to it from
    # outside; the Product Dimension is only listed.
    existing = values["existing_entities"]
    assert [row["dimensional_entity_name"] for row in existing["entities"]] == [
        "Customer Dimension"
    ]
    assert [row["dimensional_attribute_name"] for row in existing["attributes"]] == [
        "Customer Dimension key",
        "Customer ID",
        "Loaded At",
    ]
    assert [row["from_dimensional_entity_name"] for row in existing["relationships"]] == [
        "Sales Fact"
    ]
    assert values["neighbor_entities"] == [
        {
            "schema": "gold_nwa",
            "name": "Sales Fact",
            "type": "fact",
            "grain": "One sale per customer.",
            "natural_keys": [{"name": "Source Customer ID", "type": "bigint"}],
            "linked_via": ["relationship"],
        }
    ]
    assert values["entity_directory"] == [
        {
            "schema": "gold_nwa",
            "name": "Product Dimension",
            "type": "dimension",
            "summary": "One product.",
        }
    ]
    assert values["dimensional_fact_types"] == [
        {"code": "transaction", "description": "One row per business event."}
    ]
    # Routed to no workflow, yet the shown Customer Dimension cites it.
    assert [row["context_record_id"] for row in values["context_records"]] == [_CITED]
    # Optimize findings are not Build inputs.
    for name in ("model_summary", "conformance_candidates", "entity_details"):
        assert (
            get_prompt_input_contract(
                project_workflow="dimensional",
                workflow_execution_mode=mode,
                stage_code="build_authoring",
                resolver_key=f"workflow.dimensional.common.build_authoring.inputs.{name}",
            )
            is None
        )


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_optimize_inputs_summarize_the_whole_model_and_its_findings(
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    raw = _context_bundle(mode=mode, operation="optimize").context.model_dump(mode="json")
    invoice = _selected_logical_entity("sales_invoice", table="sales_invoice", order=2)
    raw["selected_logical_entities"].append(invoice)
    raw["applied"]["subject_area"] = _subject_areas(
        (_SALES, ("sales_customer",)), (_BILLING, ("sales_invoice",))
    )
    raw["applied"]["logical"] = {
        "entities": [item["entity"] for item in raw["selected_logical_entities"]],
        "attributes": [],
        "relationships": [],
    }
    model = _model(fact_source="sales_invoice")
    # A second Customer dimension, built from the same Logical Entity, with a plural name
    # and a differently typed Customer ID.
    copy = deepcopy(model["entities"][0])
    copy["dimensional_entity_name"] = "Customer Dimensions"
    customer_id = next(
        row for row in model["attributes"] if row["dimensional_attribute_name"] == "Customer ID"
    )
    model["entities"].append(copy)
    model["attributes"].append(
        {
            **customer_id,
            "dimensional_entity_name": "Customer Dimensions",
            "dimensional_attribute_data_type": "string",
        }
    )
    # A detailed Entity's Attribute citation passes; the unshown Product Dimension's does not.
    customer_id["sources"] = [*customer_id["sources"], _citation(_CITED)]
    unshown = "00000000-0000-4000-8000-0000000000b2"
    model["entities"][2]["sources"] = [_citation(unshown)]
    raw["context"]["records"].append(
        {**raw["context"]["records"][0], "context_record_id": unshown}
    )
    raw["applied"]["dimensional"] = model
    context = AgentAuthoringContext.model_validate(raw, strict=False)
    catalog = (
        InMemoryAgentContextToolCatalog(
            context=context, max_result_bytes=None, max_catalog_bytes=None, max_page_records=200
        )
        if mode == "tool_assisted"
        else None
    )
    embedded = catalog.manifest if catalog else _provider_context(context)
    plan = _plan(mode=mode, operation="optimize")

    _, values = _registered_values(plan, context=embedded, catalog=catalog)

    summary = {row["name"]: row for row in values["model_summary"]["entities"]}
    assert {name: row["subject_areas"] for name, row in summary.items()} == {
        "Customer Dimension": ["Sales"],
        "Sales Fact": ["Billing"],
        "Product Dimension": [],
        "Customer Dimensions": ["Sales"],
    }
    assert summary["Sales Fact"]["logical_sources"] == ["silver_nwa.sales_invoice"]
    assert summary["Sales Fact"]["fact_type"] == "transaction"
    assert values["model_summary"]["relationships"] == [
        {
            "from": "gold_nwa.Sales Fact.Bill To Customer key",
            "to": "gold_nwa.Customer Dimension",
            "role": "Bill To Customer",
        }
    ]
    pair = ["gold_nwa.Customer Dimension", "gold_nwa.Customer Dimensions"]
    assert values["conformance_candidates"] == [
        {"reason": "same_logical_source", "dimensions": pair},
        {"reason": "name_variant", "dimensions": pair},
    ]
    assert values["type_conflicts"] == [
        {
            "kind": "shared_name",
            "attribute": "Customer ID",
            "values": [
                {"entity": pair[0], "attribute": "Customer ID", "type": "bigint"},
                {"entity": pair[1], "attribute": "Customer ID", "type": "string"},
            ],
        }
    ]
    assert values["name_variants"] == [{"kind": "entity", "names": pair}]
    details = values["entity_details"]
    assert sorted(row["dimensional_entity_name"] for row in details["entities"]) == [
        "Customer Dimension",
        "Customer Dimensions",
    ]
    assert [row["from_dimensional_entity_name"] for row in details["relationships"]] == [
        "Sales Fact"
    ]
    assert [row["context_record_id"] for row in values["context_records"]] == [_CITED]
    # Optimize works on no single area.
    assert "subject_area_context" not in workflow_input_contracts("dimensional_optimize")


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_optimize_offers_prefix_renames_only_for_free_unpinned_unused_entities(
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    raw = _context_bundle(mode=mode, operation="optimize").context.model_dump(mode="json")
    model = _model(fact_source="sales_customer")
    template = model["entities"][0]

    def entity(name: str, kind: str = "dimension", **changes: Any) -> dict[str, Any]:
        return {
            **template,
            "dimensional_entity_name": name,
            "dimensional_entity_type": kind,
            "dimensional_fact_type": "transaction" if kind == "fact" else None,
            "dimensional_entity_grain_definition": "One shipment." if kind == "fact" else None,
            "sources": [],
            **changes,
        }

    model["entities"] += [
        entity("Product"),
        entity("Shipment", "fact"),
        entity("DimRegion"),
        entity("Store", dimensional_entity_is_locked=True),
        entity("Warehouse"),
        entity("DimWarehouse", dimensional_entity_is_active=False),
        entity("Supplier"),
        entity("Carrier"),
    ]
    model["attributes"].append(
        {
            **model["attributes"][0],
            "dimensional_entity_name": "Carrier",
            "dimensional_attribute_is_locked": True,
        }
    )
    raw["applied"]["dimensional"] = model
    schema = template["dimensional_entity_schema_name"]
    raw["read_only_dependencies"] = [
        {
            "dataset": "mapping_object",
            "record": {
                "modeled_entity_type": "dimensional_entity",
                "modeled_entity_schema_name": schema,
                "modeled_entity_name": "Supplier",
            },
        }
    ]
    context = AgentAuthoringContext.model_validate(raw, strict=False)
    catalog = (
        InMemoryAgentContextToolCatalog(
            context=context, max_result_bytes=None, max_catalog_bytes=None, max_page_records=200
        )
        if mode == "tool_assisted"
        else None
    )
    embedded = catalog.manifest if catalog else _provider_context(context)

    _, values = _registered_values(
        _plan(mode=mode, operation="optimize"), context=embedded, catalog=catalog
    )

    # Already prefixed, locked, pinned by a locked Attribute, used by Mapping or with a
    # taken new name: none of those; names with spaces are not PascalCase.
    assert values["prefix_renames"] == [
        {"entity": f"{schema}.Product", "new_name": "DimProduct"},
        {"entity": f"{schema}.Shipment", "new_name": "FactShipment"},
    ]
    assert {
        row["dimensional_entity_name"] for row in values["entity_details"]["entities"]
    } >= {"Product", "Shipment"}

@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_inconsistent_resolver_value_is_rejected(
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    bundle = replace(_context_bundle(mode=mode), snapshot=snapshot_from_graph({}))
    focused = focus_subject_area(
        bundle,
        plan=_plan(mode=mode),
        subject_area=_SALES,
        logical=LogicalSection(entities=(), attributes=(), relationships=()),
    )
    assert focused is not None
    key = "workflow.dimensional.common.build_authoring.inputs.subject_area_context"

    with pytest.raises(InvalidRequestError):
        _registered_values(
            _plan(mode=mode),
            context=focused.embedded_context,
            catalog=focused.tool_catalog,
            resolver_values={key: {"unrelated": True}},
        )


_ORDER_PROBE = """
import json
from copy import deepcopy
from gds_workbench_api.features.workflows.authoring.context_inputs import project_context_inputs
from tests.web_backend.test_dimensional_executor import (
    _applied_dimensional_section,
    _context_bundle,
)

model = _applied_dimensional_section().model_dump(mode="json")
copy = deepcopy(model["entities"][0])
copy["dimensional_entity_name"] = "Customer Dimensions"
model["entities"].append(copy)
model["attributes"].append(
    {**model["attributes"][1], "dimensional_entity_name": "Customer Dimensions"}
)
inputs = {}
for operation, name in (("build", "existing_entities"), ("optimize", "entity_details")):
    context = _context_bundle(operation=operation).context.model_dump(mode="json")
    context["applied"]["dimensional"] = model
    inputs[operation] = project_context_inputs(context)[name]
print(json.dumps(inputs))
"""


def test_build_and_optimize_inputs_do_not_depend_on_the_process_hash_seed() -> None:
    """The same frozen context must give the same prompt in every worker process."""
    root = Path(__file__).resolve().parents[2]
    outputs = {
        seed: subprocess.run(
            [sys.executable, "-c", _ORDER_PROBE],
            check=True,
            capture_output=True,
            text=True,
            cwd=root,
            env={
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": os.pathsep.join(
                    str(root / path) for path in ("mcp_server", "web_app/backend", ".")
                ),
            },
        ).stdout
        for seed in ("0", "1", "2")
    }
    assert outputs["0"] == outputs["1"] == outputs["2"]
