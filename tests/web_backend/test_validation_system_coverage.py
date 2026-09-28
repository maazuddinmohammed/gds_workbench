"""Every selected System must succeed before Validation can hand off a draft."""

# pyright: reportPrivateUsage=false
from typing import Any, Literal, cast

import pytest
from gds_workbench_api.features.validation.service import ValidationExecutionFailedError
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan
from pydantic import JsonValue

from tests.web_backend.test_validation_executor import (
    _CLAIM_TOKEN,
    _candidate,
    _context,
    _plan,
    _PlanRepository,
    _principal,
    _service,
)


@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
@pytest.mark.parametrize("fail_second_system", [False, True])
async def test_validation_authors_every_system_and_never_hands_off_partial_results(
    monkeypatch: pytest.MonkeyPatch,
    layer: Literal["logical_entity", "dimensional_entity"],
    fail_second_system: bool,
) -> None:
    context = _context()
    template = context.systems[0]
    systems = tuple(
        template.model_copy(
            update={
                "system_ref": f"system_{index}",
                "system_code": code,
                "modeled_entity_type": layer,
                "agent_context": {
                    **cast(dict[str, JsonValue], template.agent_context),
                    "system_ref": f"system_{index}",
                    "scope": {"tenant_code": "acme", "system_code": code},
                },
            }
        )
        for index, code in enumerate(("erp", "crm"), start=1)
    )
    context = context.model_copy(update={"systems": systems})
    service, _, agent, handoff, no_op, lifecycle = _service(context=context)

    async def load_plan(
        self: _PlanRepository, transaction: object, **_: object
    ) -> AgentRunPlan:
        del self, transaction
        return _plan().model_copy(
            update={
                "selected_system_codes": ("erp", "crm"),
                "modeled_entity_type": layer,
            }
        )

    async def execute(request: AgentExecutionRequest) -> AgentExecutionResult:
        agent.requests.append(request)
        position = len(agent.requests)
        if position == 2 and fail_second_system:
            raise TimeoutError("Synthetic provider timeout")
        candidate = cast(dict[str, Any], _candidate())
        candidate["system_ref"] = f"system_{position}"
        return AgentExecutionResult(
            candidate=cast(JsonValue, candidate), turn_count=1, tool_call_count=0
        )

    monkeypatch.setattr(_PlanRepository, "load", load_plan)
    monkeypatch.setattr(agent, "execute", execute)
    if fail_second_system:
        with pytest.raises(ValidationExecutionFailedError):
            await service.execute_started(
                _principal(),
                tenant_id=7,
                model_id=18,
                workflow_run_id=1048,
                expected_model_revision=7,
                workflow_run_claim_token=_CLAIM_TOKEN,
            )
        assert handoff.calls == [] and handoff.retained == []
        assert lifecycle.failed is not None
        assert lifecycle.failed[0] == "validation_execution_failed"
    else:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )
        assert len(handoff.calls) == 1 and lifecycle.failed is None
        changes = {change.dataset: change.records for change in handoff.calls[0]}
        for dataset in ("validation_group", "validation_check"):
            assert {row["system_code"] for row in changes[dataset]} == {"erp", "crm"}
            assert len(changes[dataset]) == 2
            prefix = "Logical · " if layer == "logical_entity" else "Dimensional · "
            assert all(
                str(row["validation_group_name"]).startswith(prefix)
                for row in changes[dataset]
            )
    assert len(agent.requests) == 2
    assert all(request.workflow == "validation" for request in agent.requests)
    assert no_op.requests == []
