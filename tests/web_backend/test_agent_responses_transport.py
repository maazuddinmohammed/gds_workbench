"""Foundry tool/reasoning compatibility through the real SDK, with no provider I/O."""

# pyright: reportPrivateUsage=false
import json
from typing import Any, cast

import httpx2
import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.tool_configuration import configure_tools

from tests.web_backend import test_code_generation_executor as code
from tests.web_backend.test_agent_usage import _request, _response, _responses_response, _router


@pytest.mark.parametrize("effort", ["xhigh", "default"])
async def test_code_reads_all_mapping_tools_with_reasoning_without_stored_responses(
    monkeypatch: pytest.MonkeyPatch,
    effort: str,
) -> None:
    """GPT-6.1 Sol tool calls require Responses, including default reasoning.

    https://developers.openai.com/api/docs/models/gpt-6.1-sol
    """
    sends = 0
    tools_seen: set[str] = set()

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        body = json.loads(request.content)
        if request.url.path.endswith("/chat/completions") and body.get("tools"):
            return httpx2.Response(
                400,
                json={"error": {"code": "unsupported_value", "param": "reasoning_effort"}},
            )
        assert request.url.path.endswith("/responses")
        assert body["model"] == "gpt-6.1-sol"
        assert body["text"] == {"format": {"type": "json_object"}}
        assert "response_format" not in body and "reasoning_effort" not in body
        assert body.get("reasoning") == (None if effort == "default" else {"effort": effort})
        assert body["store"] is False
        assert "previous_response_id" not in body and "conversation" not in body
        assert "reasoning.encrypted_content" in body["include"]
        assert body["parallel_tool_calls"] is False
        assert len(body["tools"]) == 5
        target = sends // 6 + 1
        turn = sends % 6
        history = body["input"]
        # Stateless tool turns must preserve both reasoning and tool-call/output identities.
        encrypted = [item for item in history if item.get("type") == "reasoning"]
        assert len(encrypted) == turn
        assert all(item["encrypted_content"] == "fixture-encrypted-reasoning" for item in encrypted)
        calls = {item["call_id"] for item in history if item.get("type") == "function_call"}
        outputs = {
            item["call_id"] for item in history if item.get("type") == "function_call_output"
        }
        assert calls == outputs and len(calls) == turn
        sends += 1
        if turn < 5:
            name = body["tools"][turn]["name"]
            tools_seen.add(name)
            response = _responses_response(
                None, tool=True, tool_name=name, call_id=f"call_{target}_{turn}"
            )
            output = cast(list[dict[str, Any]], response["output"])
            response["output"] = [
                {
                    "id": f"reasoning_{target}_{turn}",
                    "type": "reasoning",
                    "summary": [],
                    "encrypted_content": "fixture-encrypted-reasoning",
                },
                *output,
            ]
        else:
            response = _responses_response(
                None,
                content=json.dumps(
                    {
                        "artifacts": [
                            {
                                "target_ref": f"target_{target}",
                                "artifact_name": f"target_{target}.sql",
                                "artifact_role": "target_transformation",
                                "source_system_codes": ["CRM"],
                                "generated_sql": f"SELECT {target};",
                            }
                        ]
                    }
                ),
            )
        return httpx2.Response(200, json=response)

    router = _router(monkeypatch, None, handler)
    plan = code._plan()
    plan = plan.model_copy(
        update={
            "selection": plan.selection.model_copy(update={"reasoning_effort_code": effort}),
        }
    )
    service, _, _, handoff, no_op, lifecycle = code._service(
        executor=router, plan_repository=code._PlanRepository(plan=plan)
    )
    try:
        result = await service.execute_started(
            code._principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=code._CLAIM_TOKEN,
        )
    finally:
        await router.close()
    assert sends == 12 and len(tools_seen) == 5
    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 4
    assert len(handoff.calls) == 1 and not no_op.requests and lifecycle.failed is None


@pytest.mark.parametrize("empty_tool_catalog", [False, True])
async def test_no_enabled_tools_keeps_chat_completions_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    empty_tool_catalog: bool,
) -> None:
    request = _request(tools=empty_tool_catalog)
    if empty_tool_catalog:
        catalog = configure_tools(
            request.local_tool_catalog, (), workflow="logical", execution_mode="tool_assisted"
        )
        request = request.model_copy(
            update={
                "allowed_tool_names": (),
                "local_tool_catalog": catalog,
            }
        )
    request = request.model_copy(
        update={
            "selection": request.selection.model_copy(update={"reasoning_effort_code": "xhigh"}),
        }
    )

    def handler(raw: httpx2.Request) -> httpx2.Response:
        body = json.loads(raw.content)
        assert raw.url.path.endswith("/chat/completions")
        assert body["reasoning_effort"] == "xhigh"
        assert body["response_format"] == {"type": "json_object"}
        assert "tools" not in body and "parallel_tool_calls" not in body
        assert "reasoning" not in body and "text" not in body
        return httpx2.Response(200, json=_response(None))

    router = _router(monkeypatch, None, handler)
    try:
        result = await router.execute(request)
    finally:
        await router.close()
    assert result.candidate == {"result": "valid"}


@pytest.mark.parametrize(
    "status, detail, reason",
    [
        ("incomplete", "max_output_tokens", "output_truncated"),
        ("incomplete", "content_filter", "output_refused"),
        ("failed", "private-provider-code", "execution_failed"),
        ("completed", "refusal", "output_refused"),
    ],
)
async def test_responses_never_accepts_json_from_an_unsuccessful_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: str,
    detail: str,
    reason: str,
) -> None:
    sends = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        assert request.url.path.endswith("/responses")
        response = _responses_response(None)
        response["status"] = status
        if status == "incomplete":
            response["incomplete_details"] = {"reason": detail}
        elif status == "failed":
            response["error"] = {"code": detail, "message": "private-provider-message"}
        else:
            output = cast(list[dict[str, Any]], response["output"])
            output[0]["content"] = [{"type": "refusal", "refusal": "private-provider-refusal"}]
        return httpx2.Response(200, json=response)

    router = _router(monkeypatch, None, handler)
    try:
        with pytest.raises(WorkbenchError) as raised:
            await router.execute(_request(tools=True))
    finally:
        await router.close()
    assert sends == 1
    assert raised.value.code == f"agent_{reason}"
    assert "private-provider-" not in str(raised.value) + repr(raised.value) + caplog.text
