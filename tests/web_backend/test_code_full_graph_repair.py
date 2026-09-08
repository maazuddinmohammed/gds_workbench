"""Locked Code plus replacement artifacts must repair before final handoff."""

# pyright: reportPrivateUsage=false
from typing import Any, cast

import pytest
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_workbench_api.features.workflows.authoring.repair import AgentCandidateValidationError
from pydantic import JsonValue

from tests.web_backend.test_code_generation_executor import (
    _CLAIM_TOKEN,
    _AgentExecutor,
    _applied_execution_context,
    _principal,
    _service,
    code_validation_context,
)


@pytest.mark.parametrize("repair", [True, False])
async def test_code_reconciles_locked_artifact_before_handoff_or_retains_complete_rejection(
    repair: bool,
) -> None:
    context = _applied_execution_context()
    first, second = context.targets
    second = second.model_copy(
        update={
            "applied_generated_code": tuple(
                row.model_copy(update={"generated_code_is_locked": True})
                for row in second.applied_generated_code
            ),
            "applied_generated_code_source_systems": tuple(
                row.model_copy(update={"generated_code_source_system_is_locked": True})
                for row in second.applied_generated_code_source_systems
            ),
        }
    )
    context = code_validation_context(context.model_copy(update={"targets": (first, second)}))
    first_candidate: JsonValue = {
        "artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 10;"}]
    }
    invalid: JsonValue = {
        "artifacts": [
            {
                "target_ref": "target_2",
                "artifact_name": "replacement.sql",
                "generated_sql": "SELECT 20;",
            }
        ]
    }
    corrected: JsonValue = {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]}
    agent = _AgentExecutor(responses=[first_candidate, invalid, corrected if repair else None])
    service, _, _, handoff, _, lifecycle = _service(executor=agent, context=context)
    if repair:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )
        assert len(handoff.calls) == 1 and not handoff.retained
        assert context.snapshot is not None and context.physical_scope is not None
        assert validate_future_graph(
            snapshot=context.snapshot,
            physical_scope=context.physical_scope,
            staged_documents={c.dataset: c.records for c in handoff.calls[0]},
        ).valid
    else:
        with pytest.raises(AgentCandidateValidationError):
            await service.execute_started(
                _principal(),
                tenant_id=7,
                model_id=18,
                workflow_run_id=1048,
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
            )
        assert not handoff.calls and len(handoff.retained) == 1
        changes = handoff.retained[0]["changes"]
        assert {r["modeled_entity_name"] for c in changes for r in c.records} == {
            "TargetOne",
            "TargetTwo",
        }
    assert lifecycle.failed is None and len(agent.requests) == 3
    feedback = cast(dict[str, Any], agent.requests[-1].context)["repair"]["validation_issues"]
    assert any(issue["code"] == "candidate.active_dependency_invalid" for issue in feedback)
