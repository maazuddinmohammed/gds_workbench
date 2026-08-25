from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentContextPolicy,
    AgentValidationIssue,
    ValidationRepairRunner,
    load_default_agent_context_policy,
)


def _request(*, retries: int = 2, context: JsonValue | None = None) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage="candidate_authoring",
        execution_mode="one_shot",
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="microsoft_foundry",
            model_code="gpt-5.6",
            reasoning_effort_code="medium",
            max_turns=6,
            validation_retry_count=retries,
        ),
        system_prompt="system",
        instruction_prompt="instruction",
        tool_instruction=None,
        context={"scope": [1, 2]} if context is None else context,
        output_schema={"type": "object"},
    )


@dataclass
class FakeExecutor:
    candidates: list[JsonValue]
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        candidate = self.candidates[len(self.requests) - 1]
        return AgentExecutionResult(
            candidate=candidate,
            turn_count=2,
            tool_call_count=1,
        )


@dataclass
class FakeValidator:
    outcomes: list[tuple[AgentValidationIssue, ...]]
    candidates: list[JsonValue] = field(default_factory=lambda: list[JsonValue]())

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        self.candidates.append(candidate)
        return AgentCandidateValidation(issues=self.outcomes[len(self.candidates) - 1])


@dataclass
class MutatingExecutor:
    requests: list[JsonValue] = field(default_factory=lambda: list[JsonValue]())

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(deepcopy(request.context))
        envelope = cast(dict[str, JsonValue], request.context)
        original = cast(dict[str, JsonValue], envelope["original_context"])
        scope = cast(list[JsonValue], original["scope"])
        scope.append(999)
        return AgentExecutionResult(
            candidate=(
                {"entities": [{}]}
                if len(self.requests) == 1
                else {"entities": [{"name": "customer"}]}
            ),
            turn_count=1,
            tool_call_count=0,
        )


def _policy(*, one_shot_bytes: int = 4096) -> AgentContextPolicy:
    return AgentContextPolicy(
        one_shot_max_context_bytes=one_shot_bytes,
        stage_max_context_bytes=8192,
        max_candidate_bytes=4096,
        max_validation_issues=20,
    )


def test_default_agent_context_policy_is_bounded_and_validated() -> None:
    policy = load_default_agent_context_policy()

    assert policy.schema_version == "1.0"
    assert policy.one_shot_max_context_bytes < policy.stage_max_context_bytes
    assert policy.max_candidate_bytes <= 10 * 1024 * 1024
    assert policy.max_validation_issues <= 200


@pytest.mark.asyncio
async def test_valid_candidate_returns_without_a_repair_attempt() -> None:
    executor = FakeExecutor(candidates=[{"entities": []}])
    validator = FakeValidator(outcomes=[()])

    result = await ValidationRepairRunner(
        executor=executor,
        policy=_policy(),
    ).run(request=_request(), validator=validator)

    assert result.candidate == {"entities": []}
    assert result.attempt_count == 1
    assert result.was_repaired is False
    assert result.turn_count == 2
    assert result.tool_call_count == 1
    assert executor.requests[0].context == {
        "original_context": {"scope": [1, 2]},
        "repair": None,
    }


@pytest.mark.asyncio
async def test_repair_keeps_original_context_and_exact_run_configuration() -> None:
    issue = AgentValidationIssue(
        code="missing_entity_name",
        path=("entities", 0, "name"),
        message="Every entity requires a name.",
    )
    executor = FakeExecutor(candidates=[{"entities": [{}]}, {"entities": [{"name": "customer"}]}])
    validator = FakeValidator(outcomes=[(issue,), ()])
    request = _request(retries=1)

    result = await ValidationRepairRunner(
        executor=executor,
        policy=_policy(),
    ).run(request=request, validator=validator)

    assert result.attempt_count == 2
    assert result.was_repaired is True
    assert result.turn_count == 4
    assert result.tool_call_count == 2
    first, second = executor.requests
    assert second.workflow_run_id == first.workflow_run_id == request.workflow_run_id
    assert second.selection == first.selection == request.selection
    assert second.system_prompt == first.system_prompt == request.system_prompt
    assert second.context == {
        "original_context": {"scope": [1, 2]},
        "repair": {
            "attempt": 1,
            "previous_candidate": {"entities": [{}]},
            "validation_issues": [issue.model_dump(mode="json")],
        },
    }
    assert request.context == {"scope": [1, 2]}


@pytest.mark.asyncio
async def test_repair_gives_each_adapter_attempt_a_fresh_original_context() -> None:
    issue = AgentValidationIssue(
        code="missing_entity_name",
        path=("entities", 0, "name"),
        message="Every entity requires a name.",
    )
    executor = MutatingExecutor()
    request = _request(retries=1)

    result = await ValidationRepairRunner(
        executor=executor,
        policy=_policy(),
    ).run(
        request=request,
        validator=FakeValidator(outcomes=[(issue,), ()]),
    )

    assert result.attempt_count == 2
    assert [cast(dict[str, JsonValue], item)["original_context"] for item in executor.requests] == [
        {"scope": [1, 2]},
        {"scope": [1, 2]},
    ]
    assert request.context == {"scope": [1, 2]}


@pytest.mark.asyncio
async def test_validation_exhaustion_fails_loudly_without_returning_candidate() -> None:
    issue = AgentValidationIssue(
        code="invalid_candidate",
        path=(),
        message="The complete candidate is invalid.",
    )
    executor = FakeExecutor(candidates=[{}, {}])
    validator = FakeValidator(outcomes=[(issue,), (issue,)])

    with pytest.raises(WorkbenchError) as captured:
        await ValidationRepairRunner(
            executor=executor,
            policy=_policy(),
        ).run(request=_request(retries=1), validator=validator)

    assert captured.value.code == "agent_candidate_validation_failed"
    assert len(executor.requests) == 2


@pytest.mark.asyncio
async def test_oversized_one_shot_context_fails_without_implicit_mode_fallback() -> None:
    executor = FakeExecutor(candidates=[{}])
    validator = FakeValidator(outcomes=[()])

    with pytest.raises(WorkbenchError) as captured:
        await ValidationRepairRunner(
            executor=executor,
            policy=_policy(one_shot_bytes=20),
        ).run(
            request=_request(context={"large": "x" * 100}),
            validator=validator,
        )

    assert captured.value.code == "agent_context_too_large"
    assert executor.requests == []


@pytest.mark.asyncio
async def test_too_many_validation_issues_fails_safely() -> None:
    issues = tuple(
        AgentValidationIssue(
            code=f"issue_{index}",
            path=(),
            message="Candidate validation failed.",
        )
        for index in range(21)
    )
    executor = FakeExecutor(candidates=[{}])
    validator = FakeValidator(outcomes=[issues])

    with pytest.raises(WorkbenchError) as captured:
        await ValidationRepairRunner(
            executor=executor,
            policy=_policy(),
        ).run(request=_request(), validator=validator)

    assert captured.value.code == "agent_candidate_validation_failed"
    assert "issue_20" not in str(captured.value)
