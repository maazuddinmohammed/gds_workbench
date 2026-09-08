"""Canonical full-graph repair regressions; no database or provider I/O."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
    validate_future_graph,
)
from gds_workbench_api.features.conceptual.service import _candidate_validator
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    InMemoryAgentContextToolCatalog,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
)
from pydantic import JsonValue

from tests.mcp.model_test_fixtures import snapshot_from_graph
from tests.web_backend.test_conceptual_candidate import _relationship
from tests.web_backend.test_conceptual_executor import (
    _CLAIM_TOKEN,
    _AgentExecutor,
    _candidate_object,
    _context_bundle,
    _plan,
    _principal,
    _service,
)


def _applied_relationship_bundle(
    mode: str, *, partitioned: bool = False, new_records: bool = False
) -> AgentContextBundle:
    bundle = _context_bundle(mode=mode)
    customer = _candidate_object()
    order = deepcopy(customer)
    order["conceptual_object_name"] = "Order"
    if partitioned:
        order["conceptual_object_definition"] = "Retained business definition. " * 1400
    snapshot = snapshot_from_graph(
        {
            "model_details": [bundle.context.model_details.model_dump(mode="json")],
            "model_input_scope": [
                {
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "connection_code": "SOURCE",
                    "object_schema": "bronze",
                    "object_name": "customer_raw",
                    "model_input_scope_is_locked": False,
                    "is_active": True,
                }
            ],
            "conceptual_object": []
            if new_records
            else cast(list[dict[str, object]], [customer, order]),
            "conceptual_relationship": []
            if new_records
            else cast(list[dict[str, object]], [_relationship()]),
        }
    ).model_copy(update={"model_id": 18, "model_revision": 7})
    source = ("nwa", "crm", "source", "bronze", "customer_raw")
    scope = PhysicalModelCatalog(
        model_tenant_code="nwa",
        active_system_codes=frozenset({"crm"}),
        objects=frozenset({source}),
        attributes=frozenset(),
        model_input_objects=frozenset({source}),
        model_input_attributes=frozenset(),
        dimensional_source_objects=frozenset(),
        dimensional_source_attributes=frozenset(),
        logical_mapping_target_objects=frozenset(),
        logical_mapping_target_attributes=frozenset(),
        dimensional_mapping_target_objects=frozenset(),
        dimensional_mapping_target_attributes=frozenset(),
    )
    assert validate_future_graph(snapshot=snapshot, staged_documents={}, physical_scope=scope).valid
    context = bundle.context.model_copy(
        update={
            "applied": bundle.context.applied.model_copy(update={"conceptual": snapshot.conceptual})
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
    return replace(
        bundle,
        context=context,
        embedded_context=catalog.manifest
        if catalog
        else cast(JsonValue, context.model_dump(mode="json")),
        tool_catalog=catalog,
        snapshot=snapshot,
        physical_scope=scope,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize(
    "new_records", [False, True], ids=["retained_relationship", "new_relationship"]
)
async def test_retained_active_relationship_repairs_changed_parent_before_handoff(
    mode: str,
    new_records: bool,
) -> None:
    bundle = _applied_relationship_bundle(mode, new_records=new_records)
    invalid_object = _candidate_object()
    invalid_object["conceptual_object_status"] = "inactive"
    invalid: JsonValue = {"objects": [invalid_object], "relationships": []}
    corrected_object = _candidate_object()
    corrected_object["conceptual_object_definition"] = "Customer identified by its business key."
    corrected: JsonValue = {"objects": [corrected_object], "relationships": []}
    if new_records:
        order = _candidate_object()
        order["conceptual_object_name"] = "Order"
        invalid = {"objects": [invalid_object, order], "relationships": [_relationship()]}
        corrected = {"objects": [corrected_object, order], "relationships": [_relationship()]}
    validator = _candidate_validator(bundle)
    assert not (await validator.validate(invalid)).issues
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    checked = validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={
            change.dataset: change.records for change in validator.parse_validated(invalid)
        },
        physical_scope=bundle.physical_scope,
    )
    assert [issue.code for issue in checked.issues] == ["active_dependency_invalid"]
    agent = _AgentExecutor(responses=[invalid, corrected])
    service, _, _, handoff, lifecycle = _service(agent=agent, plan=_plan(mode=mode), bundle=bundle)
    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    assert len(agent.requests) == 2
    first, second = [cast(dict[str, Any], request.context) for request in agent.requests]
    assert first["original_context"] == second["original_context"]
    assert second["repair"]["validation_issues"][0]["code"] == "candidate.active_dependency_invalid"
    assert len(handoff.calls) == 1 and lifecycle.failed is None
    assert handoff.final_events[-1].attempt == 2
    assert handoff.final_events[-1].status == "warning"
    assert validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={change.dataset: change.records for change in handoff.calls[0]},
        physical_scope=bundle.physical_scope,
    ).valid


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("later_malformed", [False, True])
async def test_exhaustion_retains_the_last_complete_invalid_draft(
    mode: str, later_malformed: bool
) -> None:
    bundle = _applied_relationship_bundle(mode)
    invalid_object = _candidate_object()
    invalid_object["conceptual_object_status"] = "inactive"
    invalid: JsonValue = {"objects": [invalid_object], "relationships": []}
    agent = _AgentExecutor(responses=[invalid, None if later_malformed else invalid])
    service, _, _, handoff, lifecycle = _service(agent=agent, plan=_plan(mode=mode), bundle=bundle)
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
    assert not handoff.calls and lifecycle.failed is None
    assert len(handoff.retained) == 1
    assert handoff.retained[0]["changes"] == _candidate_validator(bundle).parse_validated(invalid)
    assert handoff.retained[0]["issues"][0].code == "active_dependency_invalid"


