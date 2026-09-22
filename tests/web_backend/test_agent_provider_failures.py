"""Real SDK, in-memory HTTP only: fixed public failures, no partial candidates or tool calls."""

# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID

import httpx2
import pytest
from agents import ModelSettings
from agents.exceptions import ModelTimeoutError
from azure.core.exceptions import ClientAuthenticationError
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolRequestError,
    AgentExecutionFailedError,
    AgentFailureReason,
    LocalAgentToolDefinition,
)
from gds_workbench_api.integrations.agents import LocalFakeAgentAdapter, adapters
from pydantic import JsonValue

from tests.web_backend import (
    test_analysis_executor as analysis,
)
from tests.web_backend import (
    test_code_generation_executor as code_generation,
)
from tests.web_backend import (
    test_conceptual_executor as conceptual,
)
from tests.web_backend import (
    test_dimensional_executor as dimensional,
)
from tests.web_backend import (
    test_logical_executor as logical,
)
from tests.web_backend import (
    test_mapping_executor as mapping,
)
from tests.web_backend import (
    test_validation_executor as validation,
)
from tests.web_backend.mapping_fixtures import mapping_preparation
from tests.web_backend.test_agent_usage import (
    FixtureCatalog,
    MemoryRecorder,
    _request,
    _response,
    _router,
)


@pytest.mark.parametrize("tools, reasoning", [(False, "default"), (False, "none"), (True, "none")])
@pytest.mark.parametrize("timeout_seconds", [480, 900])
async def test_real_sdk_uses_the_configured_model_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tools: bool,
    reasoning: str,
    timeout_seconds: int,
) -> None:
    sends = 0
    settings_seen: list[ModelSettings] = []

    def model_settings(**options: Any) -> ModelSettings:
        settings = ModelSettings(**options)
        settings_seen.append(settings)
        return settings

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), timeout_seconds
        )
        return httpx2.Response(200, json=_response(None, tool=tools and sends == 1))

    monkeypatch.setattr(adapters, "ModelSettings", model_settings)
    request = _request(tools=tools)
    request = request.model_copy(
        update={
            "selection": request.selection.model_copy(update={"reasoning_effort_code": reasoning})
        }
    )
    result = await _router(monkeypatch, None, handler, timeout_seconds=timeout_seconds).execute(
        request
    )
    assert result.candidate == {"result": "valid"}
    assert sends == (2 if tools else 1)
    assert settings_seen and all(item.timeout == timeout_seconds for item in settings_seen)


@pytest.mark.parametrize(
    "status, provider_code, public_code",
    [
        (400, "context_length_exceeded", "agent_context_exhausted"),
        (400, "context_window_exceeded", "agent_context_exhausted"),
        (400, "unknown", "agent_provider_request_rejected"),
        (401, "unknown", "agent_authentication_failed"),
        (403, "unknown", "agent_authentication_failed"),
        (404, "unknown", "agent_provider_request_rejected"),
        (408, "unknown", "agent_timeout"),
        (504, "unknown", "agent_timeout"),
        (429, "unknown", "agent_rate_limited"),
        (503, "unknown", "agent_provider_unavailable"),
    ],
)
async def test_real_sdk_classifies_structured_provider_errors_without_messages(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
    provider_code: str,
    public_code: str,
) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            headers={"retry-after-ms": "1"},
            json={
                "error": {
                    "code": provider_code,
                    "message": "private-marker context exhausted",
                }
            },
        )

    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, None, handler).execute(_request())
    assert captured.value.code == public_code
    assert "private-marker" not in str(captured.value)
    assert "private-marker" not in caplog.text


@pytest.mark.parametrize("transport_timeout", [False, True])
async def test_real_sdk_classifies_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
    transport_timeout: bool,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        error_type = httpx2.ReadTimeout if transport_timeout else httpx2.ConnectError
        raise error_type("private-marker", request=request)

    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, None, handler).execute(_request())
    assert captured.value.code == (
        "agent_timeout" if transport_timeout else "agent_provider_unavailable"
    )
    assert "private-marker" not in str(captured.value)


@pytest.mark.parametrize("metered", [False, True])
@pytest.mark.parametrize("output", ["valid_json", "partial_json", "tool"])
async def test_real_sdk_rejects_truncation_before_candidate_or_tool_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    metered: bool,
    output: str,
) -> None:
    recorder = MemoryRecorder() if metered else None
    sends = 0
    tool_calls = 0

    class Catalog(FixtureCatalog):
        def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
            nonlocal tool_calls
            tool_calls += 1
            return super().invoke(tool_name, arguments)

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        payload = _response(
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            tool=output == "tool",
            content='{"result":' if output == "partial_json" else '{"result":"valid"}',
        )
        choices = cast(list[dict[str, object]], payload["choices"])
        choices[0]["finish_reason"] = "length"
        return httpx2.Response(200, json=payload)

    request = _request(tools=output == "tool")
    if output == "tool":
        request = request.model_copy(update={"local_tool_catalog": Catalog()})
    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, recorder, handler).execute(request)
    assert captured.value.code == "agent_output_truncated"
    assert sends == 1 and tool_calls == 0
    if recorder is not None:
        assert len(recorder.completed) == 1
        assert recorder.completed[0][1].total_tokens == 12


@pytest.mark.parametrize("safe_failure", [False, True])
async def test_real_sdk_preserves_safe_tool_errors_and_redacts_unexpected_tool_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    safe_failure: bool,
) -> None:
    sends = 0

    class Catalog(FixtureCatalog):
        def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
            if safe_failure:
                raise AgentContextToolRequestError()
            raise RuntimeError("private-marker")

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        return httpx2.Response(200, json=_response(None, tool=True))

    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, None, handler).execute(
            _request(tools=True).model_copy(update={"local_tool_catalog": Catalog()})
        )
    assert captured.value.code == (
        "agent_context_tool_request_invalid" if safe_failure else "agent_tool_failed"
    )
    assert sends == 1
    assert "private-marker" not in str(captured.value)
    assert "private-marker" not in caplog.text


async def test_real_sdk_turn_exhaustion_is_distinct_from_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_response(None, tool=True))

    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, None, handler).execute(_request(tools=True, max_turns=1))
    assert captured.value.code == "agent_turn_limit_exceeded"


@pytest.mark.parametrize(
    "error, public_code",
    [
        (ModelTimeoutError(1), "agent_timeout"),
        (
            ClientAuthenticationError(message="private-marker"),
            "agent_authentication_failed",
        ),
    ],
)
async def test_adapter_classifies_sdk_timeout_and_entra_authentication(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    public_code: str,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> object:
        raise error

    def handler(_: httpx2.Request) -> httpx2.Response:
        pytest.fail("No HTTP expected")

    monkeypatch.setattr(adapters.Runner, "run", fail)
    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, None, handler).execute(_request())
    assert captured.value.code == public_code
    assert "private-marker" not in str(captured.value)


async def test_real_sdk_rejects_filtered_output_even_when_json_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        payload = _response(None)
        cast(list[dict[str, object]], payload["choices"])[0]["finish_reason"] = "content_filter"
        return httpx2.Response(200, json=payload)

    with pytest.raises(WorkbenchError) as captured:
        await _router(monkeypatch, None, handler).execute(_request())
    assert captured.value.code == "agent_output_refused"


def test_unlimited_catalog_is_not_wrapped_and_prompts_have_no_character_ceiling() -> None:
    class Catalog(FixtureCatalog):
        max_cumulative_result_bytes = None

    catalog = Catalog()
    request = _request(tools=True)
    values = dict(request)
    values.update(
        local_tool_catalog=catalog,
        system_prompt="x" * 1_000_001,
        instruction_prompt="x" * 1_000_001,
        tool_instruction="x" * 1_000_001,
    )
    request = type(request).model_validate(values)
    assert adapters.OpenAIAgentsSdkAdapter._tool_catalog(request) is catalog


@pytest.mark.parametrize(
    "workflow, mode",
    [
        (workflow, mode)
        for workflow in ("analysis", "conceptual", "logical", "dimensional", "mapping")
        for mode in ("one_shot", "tool_assisted")
    ]
    + [("code_generation", None), ("validation", None)],
)
@pytest.mark.parametrize(
    "reason",
    [
        "context_exhausted",
        "output_truncated",
        "timeout",
        "rate_limited",
        "authentication_failed",
        "provider_unavailable",
        "tool_failed",
    ],
)
async def test_every_authoring_workflow_persists_safe_stage_failure_without_handoff(
    monkeypatch: pytest.MonkeyPatch,
    workflow: str,
    mode: str | None,
    reason: AgentFailureReason,
) -> None:
    # Actual workflow/stage/repair code; in-memory repositories and failure injection.
    error = AgentExecutionFailedError(reason)
    service: Any
    handoff: Any
    lifecycle: Any
    agent: Any
    claim_token = UUID("44444444-4444-4444-4444-444444444444")
    if workflow == "mapping":
        agent = mapping._RecordingFake()
        service, handoff, _no_op, lifecycle = mapping._executor(
            mapping_preparation(execution_mode=cast(Any, mode)), agent
        )
    elif workflow == "code_generation":
        agent = code_generation._AgentExecutor(responses=[])
        service, _, _, handoff, _no_op, lifecycle = code_generation._service(executor=agent)
    elif workflow == "validation":
        service, _, agent, handoff, _no_op, lifecycle = validation._service(
            context=validation._context()
        )
    else:
        fixture: Any = {
            "analysis": analysis,
            "conceptual": conceptual,
            "logical": logical,
            "dimensional": dimensional,
        }[workflow]
        agent = fixture._AgentExecutor(responses=[])
        service, _, _, handoff, lifecycle = fixture._service(
            agent=agent, plan=fixture._plan(mode=mode)
        )
        claim_token = fixture._CLAIM_TOKEN
    execute = AsyncMock(side_effect=error)
    monkeypatch.setattr(agent, "execute", execute)

    with pytest.raises(WorkbenchError) as captured:
        await service.execute_started(
            analysis._principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=claim_token,
        )
    assert captured.value is error
    execute.assert_awaited_once()  # Provider failures are never schema-repair retries.
    assert execute.await_args is not None
    assert execute.await_args.args[0].execution_mode == (mode or "tool_assisted")
    if workflow == "mapping":
        handoff.assert_not_awaited()
        lifecycle.assert_awaited_once()
        assert lifecycle.await_args.kwargs["failure_code"] == error.code
        assert lifecycle.await_args.kwargs["safe_failure_message"] == error.message
    else:
        assert handoff.calls == []
        assert lifecycle.failed == (error.code, error.message)


@pytest.mark.parametrize("workflow", ["code_generation", "validation"])
@pytest.mark.parametrize("enabled", [False, True])
async def test_local_fake_downstream_readers_are_optional_and_use_returned_evidence(
    workflow: str, enabled: bool
) -> None:
    tool_name = "get_code_source_systems" if workflow == "code_generation" else "get_current_code"
    calls: list[str] = []

    class Catalog:
        max_cumulative_result_bytes = None
        definitions = (
            (
                LocalAgentToolDefinition(
                    name=tool_name,
                    description="Read immutable fixture evidence.",
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            )
            if enabled
            else ()
        )

        def invoke(self, name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
            assert enabled and name == tool_name and not arguments
            calls.append(name)
            return {
                "items": [{"system_code": "READ_FROM_TOOL"}],
                "next_cursor": None,
                "is_complete": True,
                "incomplete_object_key": None,
            }

    request = _request(tools=True).model_copy(
        update={
            "workflow": workflow,
            "stage": "sql_generation" if workflow == "code_generation" else "validation_generation",
            "allowed_tool_names": (tool_name,) if enabled else (),
            "local_tool_catalog": Catalog(),
            "context": {
                "original_context": {
                    "__gds_downstream_inputs__": workflow,
                    "values": {
                        "target_ref": "target_1",
                        "system_ref": "system_1",
                        "source_systems": [{"system_code": "INLINE_ONLY"}],
                    },
                },
                "repair": None,
            },
        }
    )
    result = await LocalFakeAgentAdapter(sdk_code="openai_agents_sdk").execute(request)
    assert calls == ([tool_name] if enabled else [])
    assert result.tool_call_count == int(enabled)
    candidate = cast(dict[str, Any], result.candidate)
    if workflow == "code_generation":
        assert candidate["artifacts"][0]["source_system_codes"] == (
            ["READ_FROM_TOOL"] if enabled else ["INLINE_ONLY"]
        )
    else:
        description = candidate["validation_groups"][0]["validation_checks"][0][
            "validation_check_description"
        ]
        assert ("1 SQL artifacts" in description) == enabled
