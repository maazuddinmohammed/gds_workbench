"""Native Foundry Messages through the real Agents Runner; in-memory HTTP only."""

# pyright: reportPrivateUsage=false
import json
from collections.abc import Callable, Mapping
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx2
import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError, WorkbenchError
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.features.workflows.authoring.agent_execution import AgentExecutionRouter
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    ValidationRepairRunner,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.usage.contracts import ModelTokenUsage
from gds_workbench_api.integrations.agents import adapters, anthropic_model
from gds_workbench_api.integrations.agents.adapters import (
    OpenAIAgentsSdkAdapter,
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.anthropic_model import FoundryAnthropicModel
from gds_workbench_api.integrations.agents.configuration import AgentProviderConnection
from openai import DefaultAsyncHttpxClient
from pydantic import JsonValue, SecretStr

from tests.web_backend.test_agent_usage import FixtureCatalog, MemoryRecorder, _request

CLAUDE_CODE = "foundry-claude-opus-5-5"
BASE_URL = "https://fixture.services.ai.azure.com/anthropic/"
USAGE = {
    "input_tokens": 10,
    "output_tokens": 4,
    "cache_read_input_tokens": 3,
    "cache_creation_input_tokens": 2,
}


class RefreshingAuthentication:
    def __init__(self) -> None:
        self.calls = 0

    async def authenticate(self) -> OpenAIProviderCredentials:
        self.calls += 1
        return OpenAIProviderCredentials(
            api_key=SecretStr(f"synthetic-token-{self.calls}"),
            base_url=BASE_URL,
        )


def _response(
    *,
    content: str = '{"result":"valid"}',
    tool_id: str | None = None,
    tool_name: str = "read_fixture",
    usage: object = USAGE,
    stop_reason: str | None = None,
) -> dict[str, object]:
    blocks: list[dict[str, object]] = [
        {
            "type": "thinking",
            "thinking": "private-native-thinking",
            "signature": "private-signature",
        },
        {"type": "redacted_thinking", "data": "private-redacted-data"},
        {"type": "text", "text": "Read fixture metadata." if tool_id else content},
    ]
    if tool_id:
        blocks.append({"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}})
    return {
        "id": "fixture-native-message",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": blocks,
        "stop_reason": stop_reason or ("tool_use" if tool_id else "end_turn"),
        "stop_sequence": None,
        "usage": usage,
    }


def _router(
    monkeypatch: pytest.MonkeyPatch,
    recorder: MemoryRecorder | None,
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    api_key: bool = True,
    authentication: RefreshingAuthentication | None = None,
    models: list[FoundryAnthropicModel] | None = None,
    clients: list[httpx2.AsyncClient] | None = None,
) -> AgentExecutionRouter:
    def client_factory(**options: Any) -> httpx2.AsyncClient:
        client = DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler), **options)
        if clients is not None:
            clients.append(client)
        return client

    def model_factory(**options: Any) -> FoundryAnthropicModel:
        model = FoundryAnthropicModel(**options)
        if models is not None:
            models.append(model)
        return model

    monkeypatch.setattr(adapters, "DefaultAsyncHttpxClient", client_factory)
    monkeypatch.setattr(adapters, "FoundryAnthropicModel", model_factory)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code=CLAUDE_CODE,
                model_endpoint="claude-opus-5-5",
                api_protocol="anthropic_messages",
                anthropic_base_url=BASE_URL,
                foundry_api_key=SecretStr("synthetic-configured-key") if api_key else None,
                token_scope=None if api_key else "https://ai.azure.com/.default",
                timeout_seconds=90,
            ),
        ),
        model_authentications={
            "microsoft_foundry.anthropic": authentication or RefreshingAuthentication(),
        },
    )
    return AgentExecutionRouter(
        capabilities=load_default_agent_capabilities(),
        adapters=(adapter,),
        usage_recorder=recorder,
    )


@pytest.mark.parametrize("tools", [False, True])
@pytest.mark.parametrize("effort", ["default", "low", "medium", "high", "xhigh", "max"])
async def test_native_efforts_and_tool_turns_preserve_thinking_and_clear_private_cache(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tools: bool,
    effort: str,
) -> None:
    recorder = MemoryRecorder()
    models: list[FoundryAnthropicModel] = []
    clients: list[httpx2.AsyncClient] = []
    assistant_history: list[object] = []
    sends = 0

    def handler(raw: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        body: dict[str, Any] = json.loads(raw.content)
        assert raw.url.path == "/anthropic/v1/messages"
        assert raw.headers["anthropic-version"] == "2023-06-01"
        assert body["model"] == "claude-opus-5-5"
        assert body["max_tokens"] == 128_000
        assert body["thinking"] == {"type": "adaptive"}
        assert body.get("output_config") == (None if effort == "default" else {"effort": effort})
        assert not {
            "reasoning",
            "reasoning_effort",
            "response_format",
            "text",
            "store",
            "include",
            "parallel_tool_calls",
            "previous_response_id",
        }.intersection(body)
        assert raw.extensions["timeout"] == dict.fromkeys(("connect", "read", "write", "pool"), 90)
        messages = cast(list[dict[str, Any]], body["messages"])
        assert [
            message["content"] for message in messages if message["role"] == "assistant"
        ] == assistant_history
        if tools:
            assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
            assert [tool["name"] for tool in body["tools"]] == ["read_fixture"]
            assert body["tools"][0]["input_schema"] == FixtureCatalog.definitions[0].input_schema
            if sends > 1:
                results = messages[-1]["content"]
                assert results == [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"fixture-call-{sends - 1}",
                        "content": '{"available":true}',
                    }
                ]
        else:
            assert "tools" not in body and "tool_choice" not in body
        response = _response(tool_id=f"fixture-call-{sends}" if tools and sends < 3 else None)
        assistant_history.append(response["content"])
        return httpx2.Response(200, json=response)

    request = _request(tools=tools, model_code=CLAUDE_CODE)
    request = request.with_selection(
        request.selection.model_copy(update={"reasoning_effort_code": effort})
    )
    router = _router(monkeypatch, recorder, handler, models=models, clients=clients)
    try:
        result = await router.execute(request)
    finally:
        await router.close()
    assert result.candidate == {"result": "valid"}
    assert result.turn_count == sends == (3 if tools else 1)
    assert result.tool_call_count == (2 if tools else 0)
    assert len(recorder.started) == len(recorder.completed) == sends
    assert all(usage.total_tokens == 19 for _, usage in recorder.completed)
    assert models and all(not model._assistant_turns and not model._call_ids for model in models)
    assert clients and all(client.is_closed for client in clients)
    for private in ("private-native-thinking", "private-signature", "private-redacted-data"):
        assert private not in caplog.text
        assert private not in repr(recorder.completed)


@pytest.mark.parametrize("api_key", [False, True])
async def test_native_authentication_refreshes_on_retry_and_each_tool_turn(
    monkeypatch: pytest.MonkeyPatch,
    api_key: bool,
) -> None:
    recorder = MemoryRecorder()
    authentication = RefreshingAuthentication()
    observed: list[str] = []
    monkeypatch.setattr(anthropic_model.asyncio, "sleep", AsyncMock())

    def handler(raw: httpx2.Request) -> httpx2.Response:
        expected = f"synthetic-token-{authentication.calls}"
        if api_key:
            assert raw.headers["x-api-key"] == expected
            assert "authorization" not in raw.headers
            assert "api-key" not in raw.headers
        else:
            assert raw.headers["authorization"] == "Bearer " + expected
            assert "api-key" not in raw.headers
            assert "x-api-key" not in raw.headers
        observed.append(expected)
        if len(observed) == 1:
            return httpx2.Response(503, json={"error": {"message": "private-provider-failure"}})
        return httpx2.Response(
            200, json=_response(tool_id="retry-call" if len(observed) == 2 else None)
        )

    router = _router(monkeypatch, recorder, handler, api_key=api_key, authentication=authentication)
    try:
        result = await router.execute(_request(tools=True, model_code=CLAUDE_CODE))
    finally:
        await router.close()
    assert result.candidate == {"result": "valid"}
    assert result.turn_count == 2 and result.tool_call_count == 1
    assert len(observed) == len(set(observed)) == 3
    assert [ordinal for _, ordinal in recorder.started] == [1, 2, 3]
    assert [usage.total_tokens for _, usage in recorder.completed] == [None, 19, 19]


@pytest.mark.parametrize("api_key", [False, True])
async def test_native_redirect_never_forwards_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
    api_key: bool,
) -> None:
    requests: list[str] = []

    def handler(raw: httpx2.Request) -> httpx2.Response:
        requests.append(str(raw.url))
        return httpx2.Response(
            307,
            headers={"location": "https://redirected.example.invalid/v1/messages"},
        )

    router = _router(monkeypatch, None, handler, api_key=api_key)
    try:
        with pytest.raises(WorkbenchError) as raised:
            await router.execute(_request(model_code=CLAUDE_CODE))
    finally:
        await router.close()
    assert raised.value.code == "agent_provider_request_rejected"
    assert requests == [BASE_URL + "v1/messages"]


async def test_native_split_text_keeps_complete_json_and_original_tool_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_reply = _response(tool_id="split-text-call")
    native_tool_content: list[dict[str, object]] = [
        {"type": "text", "text": "Read "},
        {"type": "thinking", "thinking": "private-thought", "signature": "private-signature"},
        {"type": "text", "text": "fixture metadata."},
        {"type": "tool_use", "id": "split-text-call", "name": "read_fixture", "input": {}},
    ]
    tool_reply["content"] = native_tool_content
    final_reply = _response()
    final_reply["content"] = [
        {"type": "text", "text": '{"result":'},
        {"type": "thinking", "thinking": "private-thought", "signature": "private-signature"},
        {"type": "text", "text": '"valid"}'},
    ]
    sends = 0

    def handler(raw: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        if sends == 1:
            return httpx2.Response(200, json=tool_reply)
        messages = json.loads(raw.content)["messages"]
        assert messages[1] == {"role": "assistant", "content": native_tool_content}
        return httpx2.Response(200, json=final_reply)

    router = _router(monkeypatch, None, handler)
    try:
        result = await router.execute(_request(tools=True, model_code=CLAUDE_CODE))
    finally:
        await router.close()
    assert result.candidate == {"result": "valid"}
    assert result.turn_count == sends == 2
    assert result.tool_call_count == 1


@pytest.mark.parametrize(
    "usage, expected",
    [
        (None, ModelTokenUsage()),
        ({}, ModelTokenUsage()),
        ({"input_tokens": 10, "output_tokens": 4}, ModelTokenUsage(output_tokens=4)),
        (
            USAGE,
            ModelTokenUsage(
                input_tokens=15,
                output_tokens=4,
                total_tokens=19,
                cached_input_tokens=3,
                cache_write_input_tokens=2,
            ),
        ),
        (
            {**USAGE, "server_tool_use": {"web_search_requests": 1}},
            ModelTokenUsage(
                input_tokens=15,
                output_tokens=4,
                total_tokens=19,
                cached_input_tokens=3,
                cache_write_input_tokens=2,
                other_token_types=True,
            ),
        ),
        (
            {**USAGE, "input_tokens": "10"},
            ModelTokenUsage(output_tokens=4, cached_input_tokens=3, cache_write_input_tokens=2),
        ),
        ({**USAGE, "cache_read_input_tokens": -1}, ModelTokenUsage()),
        ({**USAGE, "output_tokens": True}, ModelTokenUsage()),
    ],
)
async def test_native_usage_records_cache_totals_and_keeps_invalid_counts_unknown(
    monkeypatch: pytest.MonkeyPatch,
    usage: object,
    expected: ModelTokenUsage,
) -> None:
    recorder = MemoryRecorder()
    router = _router(
        monkeypatch, recorder, lambda _: httpx2.Response(200, json=_response(usage=usage))
    )
    try:
        result = await router.execute(_request(model_code=CLAUDE_CODE))
    finally:
        await router.close()
    assert result.candidate == {"result": "valid"}
    assert len(recorder.completed) == 1
    assert recorder.completed[0][1] == expected


@pytest.mark.parametrize(
    "stop_reason, code",
    [
        ("refusal", "agent_output_refused"),
        ("max_tokens", "agent_output_truncated"),
        ("model_context_window_exceeded", "agent_output_truncated"),
    ],
)
async def test_native_refusal_or_truncation_never_accepts_partial_candidate(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stop_reason: str,
    code: str,
) -> None:
    recorder = MemoryRecorder()
    models: list[FoundryAnthropicModel] = []
    router = _router(
        monkeypatch,
        recorder,
        lambda _: httpx2.Response(200, json=_response(stop_reason=stop_reason)),
        models=models,
    )
    try:
        with pytest.raises(WorkbenchError) as raised:
            await router.execute(_request(model_code=CLAUDE_CODE))
    finally:
        await router.close()
    assert raised.value.code == code
    assert len(recorder.started) == len(recorder.completed) == 1
    assert recorder.completed[0][1].total_tokens == 19
    assert models and all(not model._assistant_turns for model in models)
    assert "private-native-thinking" not in caplog.text + str(raised.value)


@pytest.mark.parametrize(
    "status, code, attempts",
    [
        (401, "agent_authentication_failed", 1),
        (404, "agent_model_unavailable", 1),
        (413, "agent_request_too_large", 1),
        (422, "agent_provider_request_rejected", 1),
        (429, "agent_rate_limited", 3),
        (503, "agent_provider_unavailable", 3),
    ],
)
async def test_native_http_failures_are_bounded_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
    code: str,
    attempts: int,
) -> None:
    recorder = MemoryRecorder()
    monkeypatch.setattr(anthropic_model.asyncio, "sleep", AsyncMock())
    router = _router(
        monkeypatch,
        recorder,
        lambda _: httpx2.Response(
            status,
            json={"error": {"message": "private-native-failure", "type": "private-code"}},
        ),
    )
    try:
        with pytest.raises(WorkbenchError) as raised:
            await router.execute(_request(model_code=CLAUDE_CODE))
    finally:
        await router.close()
    assert raised.value.code == code
    assert len(recorder.started) == len(recorder.completed) == attempts
    assert all(usage.total_tokens is None for _, usage in recorder.completed)
    assert "private-native-failure" not in caplog.text + str(raised.value)


@pytest.mark.parametrize("status", [200, 503])
async def test_native_recorder_failure_stops_retry_and_tool_execution(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    recorder = MemoryRecorder(fail_complete=True)
    sends = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        return httpx2.Response(status, json=_response(tool_id="never-executed"))

    class ForbiddenCatalog(FixtureCatalog):
        def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
            raise AssertionError("A recording failure must prevent local tool execution")

    request = _request(tools=True, model_code=CLAUDE_CODE).model_copy(
        update={"local_tool_catalog": ForbiddenCatalog()},
    )
    router = _router(monkeypatch, recorder, handler)
    try:
        with pytest.raises(DependencyUnavailableError):
            await router.execute(request)
    finally:
        await router.close()
    assert sends == len(recorder.started) == 1
    assert not recorder.completed


@pytest.mark.parametrize(
    "failure, code, tool_calls",
    [
        ("unknown", "agent_tool_definition_rejected", 0),
        ("budget", "agent_context_tool_result_too_large", 1),
        ("turn_limit", "agent_turn_limit_exceeded", 1),
    ],
)
async def test_native_tools_keep_catalog_result_budget_and_turn_limits(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    code: str,
    tool_calls: int,
) -> None:
    class RecordingCatalog(FixtureCatalog):
        calls = 0

        def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
            self.calls += 1
            return super().invoke(tool_name, arguments)

    catalog = RecordingCatalog()
    if failure == "budget":
        catalog.max_cumulative_result_bytes = 1
    recorder = MemoryRecorder()
    router = _router(
        monkeypatch,
        recorder,
        lambda _: httpx2.Response(
            200,
            json=_response(
                tool_id="fixture-call",
                tool_name="unregistered_tool" if failure == "unknown" else "read_fixture",
            ),
        ),
    )
    request = _request(tools=True, max_turns=1, model_code=CLAUDE_CODE).model_copy(
        update={"local_tool_catalog": catalog},
    )
    try:
        with pytest.raises(WorkbenchError) as raised:
            await router.execute(request)
    finally:
        await router.close()
    assert raised.value.code == code
    assert len(recorder.started) == len(recorder.completed) == 1
    assert catalog.calls == tool_calls


async def test_native_malformed_json_enters_existing_repair_with_stable_usage_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = MemoryRecorder()
    replies = iter(('{"result":', '{"result":"valid"}'))
    repaired: list[bool] = []

    def handler(raw: httpx2.Request) -> httpx2.Response:
        body = json.loads(raw.content)
        assert len(body["messages"]) == 1
        prompt = json.loads(body["messages"][0]["content"])
        repaired.append(prompt["context"]["repair"] is not None)
        return httpx2.Response(200, json=_response(content=next(replies)))

    class Validator:
        async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
            assert candidate == {"result": "valid"}
            return AgentCandidateValidation(issues=())

    router = _router(monkeypatch, recorder, handler)
    try:
        result = await ValidationRepairRunner(
            executor=router,
            policy=load_default_agent_context_policy(),
        ).run(request=_request(model_code=CLAUDE_CODE), validator=Validator())
    finally:
        await router.close()
    assert result.candidate == {"result": "valid"}
    assert result.attempt_count == 2 and result.was_repaired
    assert repaired == [False, True]
    assert [attempt for _, attempt in recorder.invocations] == [1, 2]
    assert recorder.invocations[0][0] == recorder.invocations[1][0]
    assert len(recorder.completed) == 2
