"""Subject Area runs see their tables, all or selected Bronze Scope, by table id."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
    SubjectAreaRecord,
    SubjectAreaTableRecord,
)
from gds_etl_workbench.domain.snapshots.project import SubjectAreaSection
from jsonschema import Draft202012Validator
from pydantic import JsonValue
from tests.web_backend.test_subject_area_executor import _context_bundle, _plan

from gds_workbench_api.features.workflows.authoring.context import (
    AgentAuthoringContext,
    InMemoryAgentContextToolCatalog,
    _provider_context,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import WORKFLOW_INPUTS
from gds_workbench_api.features.workflows.authoring.context_inputs import (
    project_context_inputs,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    list_prompt_input_contracts,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition

_KEY = {
    "tenant_code": "NWA",
    "system_code": "CRM",
    "connection_code": "SOURCE",
    "object_schema": "bronze",
}
# Aggregate counts that reconcile with each measured result; never sample rows.
_EVIDENCE = {
    "supported": (20, 10, 10, 10, 0, 0, 0),
    "inconclusive": (0, 0, 10, 10, 0, 10, 0),
    "unsupported": (20, 10, 10, 10, 2, 2, 0),
}


def _profile(table: str, column: str, row_count: int) -> dict[str, object]:
    return {
        **_KEY,
        "object_name": table,
        "attribute_name": column,
        "row_count": row_count,
        "non_null_count": row_count,
        "null_count": 0,
    }


def _edge(
    source: str, target: str, result: str | None, *, status: str = "active"
) -> dict[str, object]:
    """One column-level Analysis edge, written as table.column."""
    counts = _EVIDENCE[result] if result else (None,) * 7
    return {
        **{
            f"{side}_{name}": value
            for side, end in (("from", source), ("to", target))
            for name, value in (
                *_KEY.items(),
                ("object_name", end.split(".")[0]),
                ("attribute_name", end.split(".")[1]),
            )
        },
        "relationship_kind": "reference",
        "relationship_basis": "Matching key names.",
        "validation_policy_version": "1.0.0" if result else None,
        "validation_result": result,
        **dict(zip(ANALYSIS_VALIDATION_FIELDS[2:], counts, strict=True)),
        "analysis_result_status": status,
        "analysis_result_is_locked": False,
    }


def _member(
    area: str, table: str, *, is_active: bool = True, locked: bool = False
) -> SubjectAreaTableRecord:
    return SubjectAreaTableRecord.model_validate(
        {
            "subject_area_name": area,
            **_KEY,
            "object_name": table,
            "subject_area_table_is_active": is_active,
            "subject_area_table_is_locked": locked,
        }
    )


def _context() -> AgentAuthoringContext:
    """t1 customer_raw (2 columns) and t2 order_raw (3 columns), with saved evidence."""
    applied = SubjectAreaSection(
        areas=(
            SubjectAreaRecord(
                subject_area_name="Sales",
                subject_area_definition="Customer orders.",
                subject_area_is_active=True,
                subject_area_is_locked=False,
            ),
            SubjectAreaRecord(
                subject_area_name="Archive",
                subject_area_definition="Retired tables.",
                subject_area_is_active=False,
                subject_area_is_locked=True,
            ),
        ),
        tables=(
            _member("Sales", "order_raw"),
            _member("Sales", "customer_raw", locked=True),
            _member("Sales", "crm_customer"),  # Outside this run's selection.
            _member("Archive", "customer_raw", is_active=False),
            _member("Archive", "order_raw", is_active=False, locked=True),
        ),
    )
    context = _context_bundle(applied=applied).context.model_dump(mode="json")
    return AgentAuthoringContext.model_validate(
        {
            **context,
            "profiles": [
                _profile("customer_raw", "customer_id", 10),
                _profile("customer_raw", "customer_name", 12),
            ],
            "analysis_relationships": [
                _edge("order_raw.customer_id", "customer_raw.customer_id", "inconclusive"),
                _edge("order_raw.billing_customer_id", "customer_raw.customer_id", "supported"),
                _edge(
                    "order_raw.customer_id",
                    "customer_raw.customer_name",
                    "supported",
                    status="inactive",
                ),
                _edge("customer_raw.customer_id", "order_raw.customer_id", None),
                _edge("customer_raw.customer_id", "order_raw.billing_customer_id", "unsupported"),
                _edge("order_raw.customer_id", "crm_customer.customer_id", "supported"),
                _edge("customer_raw.customer_name", "customer_raw.customer_id", None),
            ],
        },
        strict=False,
    )


def test_inputs_compact_the_run_tables_by_table_id() -> None:
    values = project_context_inputs(_context().model_dump(mode="json"))

    assert list(values) == list(WORKFLOW_INPUTS["subject_area"])
    assert values["table_index"] == [
        {"table": "t1", **_KEY, "object_name": "customer_raw"},
        {"table": "t2", **_KEY, "object_name": "order_raw"},
    ]
    # row_count is the largest profiled count; null when a table is unprofiled.
    assert values["scope_tables"] == [
        {
            "table": "t1",
            "description": "customer_raw source metadata.",
            "zone_code": "bronze",
            "row_count": 12,
            "column_count": 2,
            "column_names": ["customer_id", "customer_name"],
        },
        {
            "table": "t2",
            "description": "order_raw source metadata.",
            "zone_code": "bronze",
            "row_count": None,
            "column_count": 3,
            "column_names": ["order_id", "customer_id", "billing_customer_id"],
        },
    ]
    # One link per ordered pair of selected tables: the strongest active result, where an
    # unvalidated null outranks unsupported. Inactive, outside and self edges are left out.
    assert values["table_links"] == [
        {"from": "t1", "to": "t2", "validation_result": None, "edge_count": 2},
        {"from": "t2", "to": "t1", "validation_result": "supported", "edge_count": 2},
    ]
    # tables lists active members; locked_tables lists every locked member, by table id.
    assert values["existing_subject_areas"] == [
        {
            "name": "Sales",
            "definition": "Customer orders.",
            "is_active": True,
            "is_locked": False,
            "tables": ["t1", "t2"],
            "locked_tables": ["t1"],
            # crm_customer is an active member outside this run; it keeps its membership.
            "other_table_count": 1,
        },
        {
            "name": "Archive",
            "definition": "Retired tables.",
            "is_active": False,
            "is_locked": True,
            "tables": [],
            "locked_tables": ["t2"],
            "other_table_count": 0,
        },
    ]
    assert "max_subject_area_columns" not in values
    assert values["context_records"] == values["source_context"] == values["gds_context"] == []


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_registered_inputs_match_their_contracts_in_both_modes(mode: str) -> None:
    context = _context()
    contracts = list_prompt_input_contracts(
        project_workflow="subject_area",
        workflow_execution_mode=mode,
        stage_code="candidate_authoring",
    )
    expected = project_context_inputs(context.model_dump(mode="json"))
    plan = _plan(mode=mode)
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
    catalog = (
        InMemoryAgentContextToolCatalog(
            context=context, max_result_bytes=None, max_catalog_bytes=None, max_page_records=200
        )
        if mode == "tool_assisted"
        else None
    )
    embedded = catalog.manifest if catalog else _provider_context(context)

    values = project_prompt_input_values(
        plan=plan.model_copy(update={"stages": (stage,)}),
        stage=stage,
        context=embedded,
        resolver_values={},
        precomputed_values=catalog.prompt_values if catalog else None,
    )

    assert [contract.name for contract in contracts] == list(WORKFLOW_INPUTS["subject_area"])
    for contract in contracts:
        schema = cast(Any, Draft202012Validator(contract.value_schema))
        assert not list(schema.iter_errors(contract.example)), contract.name
        assert not list(schema.iter_errors(values[contract.resolver_key])), contract.name
        assert values[contract.resolver_key] == expected[contract.name]
    if catalog is None:
        # A frozen input that no longer matches its contract is rejected, never sent.
        tampered = cast(dict[str, Any], deepcopy(embedded))
        tampered["prompt_inputs"]["table_links"][0]["edge_count"] = 0
        with pytest.raises(InvalidRequestError):
            project_prompt_input_values(
                plan=plan.model_copy(update={"stages": (stage,)}),
                stage=stage,
                context=cast(JsonValue, tampered),
                resolver_values={},
            )
