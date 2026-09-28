"""Responses usage and terminal states preserve the provider safety boundary."""

from typing import Any

import httpx2
import pytest
from gds_workbench_api.integrations.agents.usage import ProviderUsageHooks

from tests.web_backend.test_agent_usage import MemoryRecorder


async def observe(payload: dict[str, Any]) -> tuple[ProviderUsageHooks, MemoryRecorder]:
    recorder = MemoryRecorder()
    hooks = ProviderUsageHooks(recorder)
    request = httpx2.Request("POST", "https://fixture.invalid/openai/v1/responses")
    await hooks.on_request(request)
    await hooks.on_response(httpx2.Response(200, request=request, json=payload))
    return hooks, recorder


async def test_responses_usage_records_only_numeric_counters() -> None:
    hooks, recorder = await observe(
        {
            "object": "response",
            "status": "completed",
            "output": [{"type": "reasoning", "encrypted_content": "private-reasoning"}],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 10},
                "output_tokens_details": {"reasoning_tokens": 30},
                "private-provider-field": "private-value",
            },
        }
    )
    assert hooks.error is None
    assert len(recorder.started) == len(recorder.completed) == 1
    usage = recorder.completed[0][1]
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (
        100,
        50,
        150,
    )
    assert (usage.cached_input_tokens, usage.cache_write_input_tokens) == (20, 10)
    assert usage.reasoning_output_tokens == 30
    assert not usage.other_token_types
    assert "private-" not in repr(recorder.completed)


@pytest.mark.parametrize("invalid", [True, -1, 1_000_000_000_001, "100"])
async def test_invalid_responses_usage_remains_unknown(invalid: Any) -> None:
    hooks, recorder = await observe(
        {
            "status": "completed",
            "usage": {
                "input_tokens": invalid,
                "output_tokens": 10,
                "total_tokens": 110,
            },
        }
    )
    assert hooks.error is None
    usage = recorder.completed[0][1]
    assert usage.input_tokens is usage.output_tokens is usage.total_tokens is None


async def test_responses_usage_marks_unpriced_token_categories() -> None:
    _, recorder = await observe(
        {"status": "completed", "usage": {"input_tokens_details": {"audio_tokens": 2}}}
    )
    assert recorder.completed[0][1].other_token_types


@pytest.mark.parametrize(
    "status,details,content,code",
    [
        ("incomplete", {"reason": "max_output_tokens"}, [], "agent_output_truncated"),
        ("incomplete", {"reason": "content_filter"}, [], "agent_output_refused"),
        ("incomplete", {"reason": "private-reason"}, [], "agent_execution_failed"),
        ("failed", None, [], "agent_execution_failed"),
        (
            "completed",
            None,
            [{"type": "refusal", "refusal": "private-refusal"}],
            "agent_output_refused",
        ),
    ],
)
async def test_responses_terminal_failures_are_safe_and_keep_usage(
    status: str, details: object, content: list[dict[str, str]], code: str
) -> None:
    hooks, recorder = await observe(
        {
            "status": status,
            "incomplete_details": details,
            "error": {"message": "private-error"},
            "output": [{"type": "message", "content": content}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }
    )
    assert hooks.error is not None and hooks.error.code == code
    assert "private-" not in str(hooks.error) + repr(recorder.completed)
    assert recorder.completed[0][1].total_tokens == 15


async def test_responses_truncation_is_detected_without_usage_recorder() -> None:
    hooks = ProviderUsageHooks(None)
    await hooks.on_response(
        httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://fixture.invalid/openai/v1/responses"),
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [],
            },
        )
    )
    assert hooks.error is not None and hooks.error.code == "agent_output_truncated"
