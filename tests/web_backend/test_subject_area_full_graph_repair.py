"""Whole-graph rejections of staged memberships reach the agent as repairable issues."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import Any, cast

import pytest
from gds_etl_workbench.application.change_sets.project_validation import validate_future_graph
from gds_etl_workbench.domain.snapshots.project import SubjectAreaSection
from pydantic import JsonValue
from tests.web_backend.test_subject_area_executor import (
    _CLAIM_TOKEN,
    _AgentExecutor,
    _context_bundle,
    _plan,
    _principal,
    _service,
    _validation_bundle,
)

from gds_workbench_api.features.subject_areas.service import _candidate_validator
from gds_workbench_api.features.workflows.authoring.context import AgentContextBundle
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
)

# order_raw (t2) left the Input Scope after the run froze its selection. The answer
# check accepts t2; only the whole-graph check sees that it is no longer in Scope.
_LISTS_T2: JsonValue = {
    "areas": [{"name": "Sales", "definition": "Customer orders.", "tables": ["t1", "t2"]}],
    "unassigned": [],
    "retire": [],
}
_CORRECTED: JsonValue = {
    "areas": [{"name": "Sales", "definition": "Customer orders.", "tables": ["t1"]}],
    "unassigned": ["t2"],
    "retire": [],
}


def _bundle(mode: str) -> AgentContextBundle:
    bundle = _validation_bundle(
        _context_bundle(mode=mode, applied=SubjectAreaSection(areas=(), tables=()))
    )
    assert bundle.physical_scope is not None
    scope = bundle.physical_scope
    return replace(
        bundle,
        physical_scope=replace(
            scope,
            project_input_objects=frozenset(
                key for key in scope.project_input_objects if key[4] != "order_raw"
            ),
        ),
    )


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_graph_rejection_is_repaired_before_handoff(mode: str) -> None:
    agent = _AgentExecutor(responses=[_LISTS_T2, _CORRECTED])
    bundle = _bundle(mode)
    service, _, _, handoff, lifecycle = _service(agent=agent, plan=_plan(mode=mode), bundle=bundle)

    await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert not (await _candidate_validator(bundle).validate(_LISTS_T2)).issues
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    first, second = [cast(dict[str, Any], request.context) for request in agent.requests]
    assert first["original_context"] == second["original_context"]
    # Graph issues carry no record number, so the issue points at all area tables.
    assert [(issue["code"], issue["path"]) for issue in second["repair"]["validation_issues"]] == [
        ("candidate.project_input_reference_invalid", ["areas", "tables"])
    ]
    assert len(handoff.calls) == 1 and lifecycle.failed is None
    assert (handoff.final_events[-1].attempt, handoff.final_events[-1].status) == (2, "warning")
    assert validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={change.dataset: change.records for change in handoff.calls[0]},
        physical_scope=bundle.physical_scope,
    ).valid


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("later_malformed", [False, True])
async def test_exhaustion_retains_the_last_complete_invalid_draft(
    mode: str, later_malformed: bool
) -> None:
    agent = _AgentExecutor(responses=[_LISTS_T2, None if later_malformed else _LISTS_T2])
    bundle = _bundle(mode)
    service, _, _, handoff, lifecycle = _service(agent=agent, plan=_plan(mode=mode), bundle=bundle)

    with pytest.raises(AgentCandidateValidationError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            project_id=18,
            workflow_run_id=1048,
            expected_project_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert len(agent.requests) == 2
    assert not handoff.calls and lifecycle.failed is None
    assert len(handoff.retained) == 1
    assert handoff.retained[0]["changes"] == _candidate_validator(bundle).parse_validated(_LISTS_T2)
    assert handoff.retained[0]["issues"][0].code == "project_input_reference_invalid"
