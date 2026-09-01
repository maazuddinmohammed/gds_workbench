from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AGENT_OUTPUT_CONTRACT_INSTRUCTION,
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentContextPolicy,
    AgentContextTooLargeError,
    AgentValidationIssue,
    ValidationRepairRunner,
    agent_request_envelope_bytes,
    load_default_agent_context_policy,
    parse_pydantic_candidate,
)


class _LeakyCrossFieldCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    private_value: str
    enabled: bool

    @model_validator(mode="after")
    def reject_enabled(self) -> _LeakyCrossFieldCandidate:
        if self.enabled:
            raise ValueError(f"Never expose {self.private_value}")
        return self


def _request(*, retries: int = 2, context: JsonValue | None = None) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage="candidate_authoring",
        execution_mode="one_shot",
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-primary",
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


def test_pydantic_diagnostics_never_copy_candidate_values_or_messages() -> None:
    parsed, issues = parse_pydantic_candidate(
        _LeakyCrossFieldCandidate,
        cast(
            JsonValue,
            {"private_value": "never-copy-this-private-value", "enabled": True},
        ),
    )

    assert parsed is None
    assert len(issues) == 1
    assert issues[0].code == "candidate.cross_field_invalid"
    assert issues[0].path == ()
    assert "never-copy-this-private-value" not in issues[0].model_dump_json()


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
async def test_output_schema_issues_give_exact_safe_paths_to_the_repair_turn() -> None:
    secret_value = "never-copy-this-candidate-value"
    patterned_secret_value = "never-copy-this-patterned-value"
    invalid: JsonValue = {
        "entities": [
            {
                "x-note": patterned_secret_value,
                "unexpected": secret_value,
            }
        ]
    }
    valid: JsonValue = {"entities": [{"name": "customer"}]}
    request = _request(retries=1).model_copy(
        update={
            "output_schema": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "patternProperties": {"^x-": {"type": "string"}},
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["entities"],
                "additionalProperties": False,
            }
        }
    )
    executor = FakeExecutor(candidates=[invalid, valid])
    validator = FakeValidator(outcomes=[()])

    result = await ValidationRepairRunner(
        executor=executor,
        policy=_policy(),
    ).run(request=request, validator=validator)

    assert result.candidate == valid
    assert validator.candidates == [valid]
    repair = cast(dict[str, JsonValue], executor.requests[1].context)["repair"]
    assert isinstance(repair, dict)
    raw_issues = cast(list[dict[str, JsonValue]], repair["validation_issues"])
    assert {
        (issue["code"], tuple(cast(list[str | int], issue["path"])), issue["message"])
        for issue in raw_issues
    } == {
        (
            "candidate.output_schema_required",
            ("entities", 0, "name"),
            "A required output field is missing.",
        ),
        (
            "candidate.output_schema_additional_property",
            ("entities", 0, "unexpected"),
            "The output contains a field that the schema does not allow.",
        ),
    }
    assert secret_value not in json.dumps(raw_issues, sort_keys=True)
    assert patterned_secret_value not in json.dumps(raw_issues, sort_keys=True)


@pytest.mark.asyncio
async def test_invalid_output_schema_pattern_fails_without_executing_the_agent() -> None:
    executor = FakeExecutor(candidates=[{"unexpected": "candidate-value"}])
    request = _request().model_copy(
        update={
            "output_schema": {
                "type": "object",
                "patternProperties": {"[": {"type": "string"}},
                "additionalProperties": False,
            }
        }
    )

    with pytest.raises(AgentCandidateValidationError):
        await ValidationRepairRunner(executor=executor, policy=_policy()).run(
            request=request,
            validator=FakeValidator(outcomes=[()]),
        )

    assert executor.requests == []


@pytest.mark.asyncio
async def test_output_schema_bound_issues_are_value_free() -> None:
    invalid: JsonValue = {
        "short": "sek",
        "long": "secret-candidate-value",
        "low": -999,
        "high": 999,
    }
    valid: JsonValue = {"short": "valid", "long": "ok", "low": 11, "high": 9}
    request = _request(retries=1).model_copy(
        update={
            "output_schema": {
                "type": "object",
                "properties": {
                    "short": {"type": "string", "minLength": 5},
                    "long": {"type": "string", "maxLength": 2},
                    "low": {"type": "number", "exclusiveMinimum": 10},
                    "high": {"type": "number", "exclusiveMaximum": 10},
                },
                "required": ["short", "long", "low", "high"],
                "additionalProperties": False,
            }
        }
    )
    executor = FakeExecutor(candidates=[invalid, valid])
    validator = FakeValidator(outcomes=[()])

    await ValidationRepairRunner(executor=executor, policy=_policy()).run(
        request=request,
        validator=validator,
    )

    repair = cast(dict[str, JsonValue], executor.requests[1].context)["repair"]
    assert isinstance(repair, dict)
    raw_issues = cast(list[dict[str, JsonValue]], repair["validation_issues"])
    assert {
        (issue["code"], tuple(cast(list[str | int], issue["path"])), issue["message"])
        for issue in raw_issues
    } == {
        (
            "candidate.output_schema_string_bound",
            ("short",),
            "The output string is shorter than the allowed minimum.",
        ),
        (
            "candidate.output_schema_string_bound",
            ("long",),
            "The output string exceeds the allowed maximum length.",
        ),
        (
            "candidate.output_schema_number_bound",
            ("low",),
            "The output number is not above the exclusive minimum.",
        ),
        (
            "candidate.output_schema_number_bound",
            ("high",),
            "The output number is not below the exclusive maximum.",
        ),
    }
    serialized_issues = json.dumps(raw_issues, sort_keys=True)
    for candidate_value in ("sek", "secret-candidate-value", "-999", "999"):
        assert candidate_value not in serialized_issues


def test_agent_envelope_budget_counts_the_shared_output_contract_instruction() -> None:
    request = _request()
    envelope = cast(
        JsonValue,
        {
            "system": f"{request.system_prompt}\n\n{AGENT_OUTPUT_CONTRACT_INSTRUCTION}",
            "input": {
                "instruction": request.instruction_prompt,
                "context": request.context,
                "required_output_schema": request.output_schema,
            },
            "tools": [],
        },
    )

    expected = len(
        json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )

    assert agent_request_envelope_bytes(request) == expected


@pytest.mark.asyncio
async def test_context_limit_applies_to_the_complete_outbound_envelope() -> None:
    context: JsonValue = {"scope": ["x" * 100]}
    context_bytes = len(
        json.dumps(
            context,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    issue = AgentValidationIssue(
        code="missing_entity_name",
        path=("entities", 0, "name"),
        message="Every entity requires a name.",
    )
    executor = FakeExecutor(candidates=[{"entities": [{}]}, {"entities": [{"name": "customer"}]}])

    with pytest.raises(AgentContextTooLargeError):
        await ValidationRepairRunner(
            executor=executor,
            policy=_policy(one_shot_bytes=context_bytes),
        ).run(
            request=_request(retries=1, context=context),
            validator=FakeValidator(outcomes=[(issue,), ()]),
        )

    assert executor.requests == []


@pytest.mark.asyncio
async def test_prompt_and_output_schema_count_toward_the_provider_limit() -> None:
    executor = FakeExecutor(candidates=[{"entities": []}])
    request = _request().model_copy(
        update={
            "instruction_prompt": "Use only this bounded evidence. " + "x" * 400,
            "output_schema": {
                "type": "object",
                "description": "y" * 400,
            },
        }
    )

    with pytest.raises(AgentContextTooLargeError):
        await ValidationRepairRunner(
            executor=executor,
            policy=_policy(one_shot_bytes=700),
        ).run(
            request=request,
            validator=FakeValidator(outcomes=[()]),
        )

    assert executor.requests == []


@pytest.mark.asyncio
async def test_large_previous_candidate_uses_a_bounded_repair_summary() -> None:
    issue = AgentValidationIssue(
        code="missing_entity_name",
        path=("entities", 0, "name"),
        message="Every entity requires a name.",
    )
    executor = FakeExecutor(
        candidates=[
            {"entities": [{"description": "x" * 1000}]},
            {"entities": [{"name": "customer"}]},
        ]
    )

    result = await ValidationRepairRunner(
        executor=executor,
        policy=_policy(one_shot_bytes=1000),
    ).run(
        request=_request(retries=1),
        validator=FakeValidator(outcomes=[(issue,), ()]),
    )

    assert result.attempt_count == 2
    repair = cast(dict[str, JsonValue], executor.requests[1].context)["repair"]
    assert isinstance(repair, dict)
    assert repair["previous_candidate"] is None
    assert repair["previous_candidate_omitted"] is True
    assert len(cast(str, repair["previous_candidate_digest"])) == 64
    assert repair["validation_issues"] == [issue.model_dump(mode="json")]


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
