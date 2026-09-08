"""Exercise real SDK HTTP handling against in-memory transport; never provider I/O."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID, uuid4

import httpx2
import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError, WorkbenchError
from gds_workbench_api.capabilities import AgentRunSelection, load_default_agent_capabilities
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionRouter,
    LocalAgentToolDefinition,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    ValidationRepairRunner,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.usage.contracts import AgentUsageRecorder, ModelTokenUsage
from gds_workbench_api.integrations.agents import adapters
from gds_workbench_api.integrations.agents.adapters import (
    OpenAIAgentsSdkAdapter,
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.configuration import AgentProviderConnection
from gds_workbench_api.integrations.agents.usage import ProviderUsageHooks
from openai import DefaultAsyncHttpxClient
from pydantic import JsonValue, SecretStr


class MemoryRecorder:
    def __init__(self, *, fail_complete: bool = False) -> None:
        self.started: list[tuple[UUID, int]] = []
        self.completed: list[tuple[UUID, ModelTokenUsage]] = []
        self.invocations: list[tuple[UUID, int]] = []
        self.fail_complete = fail_complete

    def make_invocation_recorder(
        self,
        *,
        workflow_run_id: int,
        stage_code: str,
        invocation_id: UUID,
        authoring_attempt: int,
    ) -> "MemoryRecorder":
        assert workflow_run_id == 101 and stage_code == "candidate_authoring"
        self.invocations.append((invocation_id, authoring_attempt))
        return self

    async def begin_request(self, request_ordinal: int) -> UUID:
        request_id = uuid4()
        self.started.append((request_id, request_ordinal))
        return request_id

    async def complete_request(self, request_id: UUID, usage: ModelTokenUsage) -> None:
        assert any(started == request_id for started, _ in self.started)
        if self.fail_complete:
            raise DependencyUnavailableError()
        self.completed.append((request_id, usage))


class FixtureAuthentication:
    async def authenticate(self) -> OpenAIProviderCredentials:
        return OpenAIProviderCredentials(
            api_key=SecretStr("fixture-key"),
            base_url="https://fixture.services.ai.azure.com/openai/v1/",
        )


class FixtureCatalog:
    definitions = (
        LocalAgentToolDefinition(
            name="read_fixture",
            description="Read immutable fixture metadata.",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        ),
    )
    max_cumulative_result_bytes = 1024

    def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
        assert tool_name == "read_fixture" and arguments == {}
        return {"available": True}


def _request(*, tools: bool = False, max_turns: int = 3) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=101,
        workflow="logical",
        stage="candidate_authoring",
        execution_mode="tool_assisted" if tools else "one_shot",
        selection=AgentRunSelection(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-primary",
            reasoning_effort_code="none",
            max_turns=max_turns,
            validation_retry_count=1,
        ),
        system_prompt="Private fixture instruction.",
        instruction_prompt="Produce the candidate.",
        context={"private": "must never enter usage"},
        output_schema={"type": "object", "required": ["result"]},
        allowed_tool_names=("read_fixture",) if tools else (),
        local_tool_catalog=FixtureCatalog() if tools else None,
    )


def _response(
    usage: object,
    *,
    tool: bool = False,
    content: str = '{"result":"valid"}',
) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if tool:
        message.update(
            content=None,
            tool_calls=[
                {
                    "id": "fixture_call",
                    "type": "function",
                    "function": {"name": "read_fixture", "arguments": "{}"},
                }
            ],
        )
    return {
        "id": "fixture_response",
        "object": "chat.completion",
        "created": 0,
        "model": "fixture",
        "choices": [
            {"index": 0, "message": message, "finish_reason": "tool_calls" if tool else "stop"}
        ],
        "usage": usage,
    }


def _router(
    monkeypatch: pytest.MonkeyPatch,
    recorder: AgentUsageRecorder,
    handler: Any,
) -> AgentExecutionRouter:
    def client_factory(**options: Any) -> httpx2.AsyncClient:
        return DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler), **options)

    monkeypatch.setattr(adapters, "DefaultAsyncHttpxClient", client_factory)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                model_endpoint="gpt-5.6-sol",
                timeout_seconds=10,
            ),
        ),
        model_authentications={"microsoft_foundry": FixtureAuthentication()},
    )
    return AgentExecutionRouter(
        capabilities=load_default_agent_capabilities(),
        adapters=(adapter,),
        usage_recorder=recorder,
    )


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, ModelTokenUsage()),
        ({}, ModelTokenUsage()),
        (
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ModelTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        ),
        (
            {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 2},
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
            ModelTokenUsage(
                input_tokens=12,
                output_tokens=3,
                total_tokens=15,
                cached_input_tokens=4,
                cache_write_input_tokens=2,
                reasoning_output_tokens=1,
            ),
        ),
        ({"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3}, ModelTokenUsage()),
        ({"prompt_tokens": -1, "completion_tokens": 2, "total_tokens": 1}, ModelTokenUsage()),
        ({"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 99}, ModelTokenUsage()),
        (
            {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 3},
            },
            ModelTokenUsage(),
        ),
        (
            {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
                "prompt_tokens_details": {"audio_tokens": 1},
            },
            ModelTokenUsage(
                input_tokens=12, output_tokens=3, total_tokens=15, other_token_types=True
            ),
        ),
        (
            {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
                "completion_tokens_details": {"future_token_category": 1},
            },
            ModelTokenUsage(
                input_tokens=12, output_tokens=3, total_tokens=15, other_token_types=True
            ),
        ),
        (
            {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
                "completion_tokens_details": {"future_token_category": 0},
            },
            ModelTokenUsage(input_tokens=12, output_tokens=3, total_tokens=15),
        ),
    ],
)
async def test_http_usage_preserves_presence_and_never_collects_model_content(
    raw: object,
    expected: ModelTokenUsage,
) -> None:
    recorder = MemoryRecorder()
    hooks = ProviderUsageHooks(recorder)
    async with DefaultAsyncHttpxClient(
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=_response(raw))),
        event_hooks={"request": [hooks.on_request], "response": [hooks.on_response]},
    ) as client:
        await client.post("https://fixture.invalid/chat/completions", json={"private": "prompt"})
    assert len(recorder.started) == len(recorder.completed) == 1
    assert recorder.completed[0][1] == expected
    assert "private" not in repr(recorder.completed) and "valid" not in repr(recorder.completed)


@pytest.mark.parametrize("max_turns, expected_requests", [(1, 1), (3, 4)])
async def test_real_sdk_keeps_reported_turn_usage_when_a_later_turn_fails(
    monkeypatch: pytest.MonkeyPatch,
    max_turns: int,
    expected_requests: int,
) -> None:
    recorder = MemoryRecorder()
    sends = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        assert len(recorder.started) == sends  # Pending row precedes the transport.
        if sends == 1:
            return httpx2.Response(
                200,
                json=_response(
                    {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                    tool=True,
                ),
            )
        assert len(recorder.completed) == 1
        raise httpx2.ReadTimeout("Fixture transport timeout", request=request)

    router = _router(monkeypatch, recorder, handler)
    with pytest.raises(WorkbenchError):
        await router.execute(_request(tools=True, max_turns=max_turns))
    assert sends == expected_requests
    assert len(recorder.started) == expected_requests and len(recorder.completed) == 1
    assert recorder.completed[0][1].total_tokens == 12


async def test_real_sdk_records_every_repair_with_one_stable_stage_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = MemoryRecorder()
    outputs = iter(('```json\n{"result":"valid"}\n```', '{"result":"valid"}'))

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=_response(
                {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                content=next(outputs),
            ),
        )

    class Validator:
        async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
            assert candidate == {"result": "valid"}
            return AgentCandidateValidation(issues=())

    router = _router(monkeypatch, recorder, handler)
    result = await ValidationRepairRunner(
        executor=router,
        policy=load_default_agent_context_policy(),
    ).run(request=_request(), validator=Validator())
    assert result.attempt_count == 2
    assert len(recorder.completed) == 2
    assert sum(cast(int, usage.total_tokens) for _, usage in recorder.completed) == 24
    assert [attempt for _, attempt in recorder.invocations] == [1, 2]
    assert recorder.invocations[0][0] == recorder.invocations[1][0]


@pytest.mark.parametrize("tool", [False, True])
async def test_recording_failure_does_not_retry_a_paid_model_response(
    monkeypatch: pytest.MonkeyPatch,
    tool: bool,
) -> None:
    recorder = MemoryRecorder(fail_complete=True)
    sends = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        return httpx2.Response(
            200,
            json=_response(
                {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                tool=tool,
            ),
        )

    router = _router(monkeypatch, recorder, handler)
    with pytest.raises(DependencyUnavailableError):
        await router.execute(_request(tools=tool))
    assert sends == 1 and len(recorder.started) == 1 and not recorder.completed


async def test_http_retry_without_usage_remains_unknown_next_to_reported_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = MemoryRecorder()
    sends = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        if sends == 1:
            return httpx2.Response(
                429,
                headers={"retry-after-ms": "1"},
                json={"error": {"message": "Private fixture provider response"}},
            )
        return httpx2.Response(
            200,
            json=_response(
                {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            ),
        )

    result = await _router(monkeypatch, recorder, handler).execute(_request())
    assert result.candidate == {"result": "valid"}
    assert [ordinal for _, ordinal in recorder.started] == [1, 2]
    assert recorder.started[0][0] != recorder.started[1][0]
    assert recorder.completed[0][1].total_tokens is None
    assert recorder.completed[1][1].total_tokens == 12
    assert "Private" not in repr(recorder.completed)


async def test_usage_survives_candidate_size_rejection_after_sdk_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = MemoryRecorder()

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=_response(
                {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            ),
        )

    class Validator:
        async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
            raise AssertionError("Candidate size must be checked before validation")

    with pytest.raises(WorkbenchError):
        await ValidationRepairRunner(
            executor=_router(monkeypatch, recorder, handler),
            policy=load_default_agent_context_policy(),
        ).run(request=_request(), validator=Validator(), max_candidate_bytes=1)
    assert len(recorder.started) == len(recorder.completed) == 1
    assert recorder.completed[0][1].total_tokens == 12
