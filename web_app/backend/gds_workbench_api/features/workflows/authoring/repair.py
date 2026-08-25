"""Bounded validation-repair loop with immutable original context."""

from __future__ import annotations

import json
from copy import deepcopy
from importlib.resources import files
from typing import Literal, Protocol

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)


class AgentValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    path: tuple[str | int, ...] = Field(max_length=20)
    message: str = Field(min_length=1, max_length=500)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: tuple[str | int, ...]) -> tuple[str | int, ...]:
        if any(
            isinstance(item, bool)
            or (isinstance(item, int) and item < 0)
            or (isinstance(item, str) and (not item or len(item) > 100))
            for item in value
        ):
            raise ValueError("Agent validation issue path is invalid")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Agent validation issue message is invalid")
        return value


class AgentCandidateValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    issues: tuple[AgentValidationIssue, ...] = Field(max_length=200)


class AgentContextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    one_shot_max_context_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    stage_max_context_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_candidate_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_validation_issues: int = Field(ge=1, le=200)


class AgentAuthoringResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate: JsonValue = Field(repr=False)
    attempt_count: int = Field(ge=1, le=6)
    was_repaired: bool
    turn_count: int = Field(ge=1, le=300)
    tool_call_count: int = Field(ge=0, le=6_000)


class AgentExecutor(Protocol):
    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult: ...


class AgentCandidateValidator(Protocol):
    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation: ...


class AgentContextTooLargeError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_too_large",
            message=(
                "The selected execution mode cannot accept this context. "
                "Choose another mode explicitly."
            ),
        )


class AgentCandidateValidationError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_candidate_validation_failed",
            message="The agent candidate did not pass complete backend validation.",
        )


class ValidationRepairRunner:
    """Return one complete validated candidate or fail without a writable result."""

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        policy: AgentContextPolicy,
    ) -> None:
        self._executor = executor
        self._policy = policy

    async def run(
        self,
        *,
        request: AgentExecutionRequest,
        validator: AgentCandidateValidator,
    ) -> AgentAuthoringResult:
        original_context = deepcopy(request.context)
        context_limit = (
            self._policy.one_shot_max_context_bytes
            if request.execution_mode == "one_shot"
            else self._policy.stage_max_context_bytes
        )
        attempt_count = 0
        turn_count = 0
        tool_call_count = 0
        repair: dict[str, JsonValue] | None = None

        while True:
            attempt_request = request.model_copy(
                update={
                    "context": {
                        "original_context": deepcopy(original_context),
                        "repair": deepcopy(repair),
                    }
                }
            )
            if _json_bytes(attempt_request.context) > context_limit:
                raise AgentContextTooLargeError()

            execution = await self._executor.execute(attempt_request)
            attempt_count += 1
            turn_count += execution.turn_count
            tool_call_count += execution.tool_call_count
            if _json_bytes(execution.candidate) > self._policy.max_candidate_bytes:
                raise AgentCandidateValidationError()

            try:
                validation = await validator.validate(execution.candidate)
            except WorkbenchError:
                raise
            except Exception:
                raise AgentCandidateValidationError() from None
            if len(validation.issues) > self._policy.max_validation_issues:
                raise AgentCandidateValidationError()
            if not validation.issues:
                return AgentAuthoringResult(
                    candidate=execution.candidate,
                    attempt_count=attempt_count,
                    was_repaired=attempt_count > 1,
                    turn_count=turn_count,
                    tool_call_count=tool_call_count,
                )
            if attempt_count > request.selection.validation_retry_count:
                raise AgentCandidateValidationError()

            repair = {
                "attempt": attempt_count,
                "previous_candidate": execution.candidate,
                "validation_issues": [issue.model_dump(mode="json") for issue in validation.issues],
            }


def _json_bytes(value: JsonValue) -> int:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except TypeError, ValueError:
        raise AgentCandidateValidationError() from None
    return len(encoded)


def load_default_agent_context_policy() -> AgentContextPolicy:
    resource = files("gds_workbench_api").joinpath("config/agent_execution.json")
    raw = resource.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("agent execution configuration is too large")
    return AgentContextPolicy.model_validate_json(raw, strict=True)
