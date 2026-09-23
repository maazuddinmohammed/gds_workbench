"""Validation replacement must account for retained locked Checks."""

# pyright: reportPrivateUsage=false
from typing import Any, cast

import pytest
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from pydantic import JsonValue

from tests.web_backend.test_validation_executor import (
    _CLAIM_TOKEN,
    _candidate,
    _context,
    _principal,
    _service,
)


async def test_retiring_group_with_locked_check_preserves_parent_without_agent_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(applied=True)
    system = context.systems[0]
    context = context.model_copy(
        update={
            "systems": (
                system.model_copy(
                    update={
                        "applied_checks": tuple(
                            row.model_copy(update={"is_locked": True})
                            for row in system.applied_checks
                        ),
                    }
                ),
            )
        }
    )
    service, _, agent, handoff, no_op, lifecycle = _service(context=context)
    invalid = cast(dict[str, Any], _candidate())
    invalid["validation_groups"][0]["validation_group_name"] = "replacement"
    responses: list[JsonValue] = [invalid]

    async def execute(request: AgentExecutionRequest) -> AgentExecutionResult:
        agent.requests.append(request)
        return AgentExecutionResult(
            candidate=responses.pop(0), turn_count=1, tool_call_count=0
        )

    monkeypatch.setattr(agent, "execute", execute)
    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    assert not no_op.requests and not handoff.retained and lifecycle.failed is None
    assert len(handoff.calls) == 1 and len(agent.requests) == 1
    assert all(
        row["is_active"] and row["validation_group_name"] == "replacement"
        for change in handoff.calls[0]
        for row in change.records
    )
