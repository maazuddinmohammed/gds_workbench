"""Real SDK rejection diagnostics stay actionable without exposing provider content."""

# pyright: reportPrivateUsage=false
import json
from typing import Any, cast

import httpx2
import pytest
from gds_etl_workbench.domain.errors import WorkbenchError

from tests.web_backend import test_code_generation_executor as code
from tests.web_backend.test_agent_usage import _request, _response, _router


@pytest.mark.parametrize(
    "status, error, reason",
    [
        (400, {"code": "content_filter"}, "input_filtered"),
        (
            400,
            {"innererror": {"code": "ResponsibleAIPolicyViolation"}},
            "input_filtered",
        ),
        (400, {"code": "context_length_exceeded"}, "context_exhausted"),
        (400, {"innererror": {"code": "context_window_exceeded"}}, "context_exhausted"),
        (413, {}, "request_too_large"),
        (400, {"param": "reasoning_effort"}, "reasoning_rejected"),
        (422, {"param": "reasoning.effort"}, "reasoning_rejected"),
        (400, {"param": "tools"}, "tool_definition_rejected"),
        (400, {"param": "tools[0].function.parameters"}, "tool_definition_rejected"),
        (400, {"param": "parallel_tool_calls"}, "tool_definition_rejected"),
        (400, {"param": "messages"}, "conversation_rejected"),
        (400, {"param": "messages[12].tool_calls"}, "conversation_rejected"),
        (400, {"param": "response_format"}, "response_format_rejected"),
        (404, {"code": "DeploymentNotFound"}, "model_unavailable"),
        (404, {"code": "model_not_found"}, "model_unavailable"),
    ],
)
async def test_known_provider_rejection_uses_fixed_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
    error: dict[str, Any],
    reason: str,
) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            json={"error": {"message": "private-provider-message", **error}},
        )

    with pytest.raises(WorkbenchError) as raised:
        await _router(monkeypatch, None, handler).execute(_request(tools=True))
    assert raised.value.code == f"agent_{reason}"
    assert "private-provider-message" not in str(raised.value) + caplog.text


@pytest.mark.parametrize("status", [400, 404, 422])
@pytest.mark.parametrize(
    "error",
    [
        {"code": "private-code", "param": "private-param"},
        {"code": {"private-code": True}, "param": ["private-param"]},
        {"param": "messages[1].private-param", "innererror": {"code": "private-code"}},
        {"param": "tools[0].function.parameters.private-param"},
        {
            "code": "content_filter private-code",
            "param": "reasoning_effort private-param",
        },
    ],
)
async def test_unknown_provider_rejection_exposes_only_http_status(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
    error: dict[str, Any],
) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            headers={"x-request-id": "private-header"},
            json={"error": {"message": "private-message", **error}},
        )

    with pytest.raises(WorkbenchError) as raised:
        await _router(monkeypatch, None, handler).execute(_request(tools=True))
    assert raised.value.code == "agent_provider_request_rejected"
    assert f"HTTP {status}" in raised.value.message
    assert "private-" not in str(raised.value) + repr(raised.value) + caplog.text


async def test_real_code_tool_conversation_preserves_later_rejection_in_run(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sends = 0
    tool_names: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert len(body["tools"]) == 5
        outstanding: set[str] = set()
        for message in body["messages"]:
            if message["role"] == "assistant" and message.get("tool_calls"):
                assert not outstanding
                outstanding = {item["id"] for item in message["tool_calls"]}
            elif message["role"] == "tool":
                assert message["tool_call_id"] in outstanding
                outstanding.remove(message["tool_call_id"])
            else:
                assert not outstanding
        assert not outstanding
        sends += 1
        if sends > 5:
            return httpx2.Response(
                400,
                json={
                    "error": {"code": "content_filter", "message": "private-message"}
                },
            )
        name = body["tools"][sends - 1]["function"]["name"]
        tool_names.append(name)
        result = _response(None)
        choices = cast(list[dict[str, Any]], result["choices"])
        choices[0]["message"] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{sends}",
                    "type": "function",
                    "function": {"name": name, "arguments": "{}"},
                }
            ],
        }
        choices[0]["finish_reason"] = "tool_calls"
        return httpx2.Response(200, json=result)

    router = _router(monkeypatch, None, handler)
    service, _, _, handoff, no_op, lifecycle = code._service(executor=router)
    try:
        with pytest.raises(WorkbenchError) as raised:
            await service.execute_started(
                code._principal(),
                tenant_id=7,
                model_id=18,
                workflow_run_id=1048,
                expected_model_revision=7,
                workflow_run_claim_token=code._CLAIM_TOKEN,
            )
    finally:
        await router.close()
    assert sends == 6 and len(set(tool_names)) == 5
    assert raised.value.code == "agent_input_filtered"
    assert lifecycle.failed == (raised.value.code, raised.value.message)
    assert not handoff.calls and not no_op.requests
    assert "private-message" not in str(raised.value) + caplog.text
