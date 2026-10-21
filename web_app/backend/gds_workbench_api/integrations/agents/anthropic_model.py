"""Foundry Messages transport for the existing, non-streaming Agents SDK loop."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import AsyncIterator
from email.utils import mktime_tz, parsedate_tz
from typing import Any, cast
from uuid import uuid4

import httpx2
from agents import FunctionTool, ModelSettings, Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import (
    ModelResponse,
    TResponseInputItem,
    TResponseOutputItem,
    TResponseStreamEvent,
)
from agents.models.interface import Model, ModelTracing
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)
from openai.types.responses.response_prompt_param import ResponsePromptParam

from gds_workbench_api.capabilities import MAX_AGENT_HTTP_RETRIES
from gds_workbench_api.features.workflows.authoring.agent_execution import AgentExecutionFailedError
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
    ModelAuthentication,
)
from gds_workbench_api.integrations.agents.usage import ProviderUsageHooks

_MAX_RETRY_AFTER_SECONDS = 120


class FoundryAnthropicModel(Model):
    """Translate only Atlas text/function turns; keep native thinking private to this run."""

    def __init__(
        self,
        *,
        connection: AgentProviderConnection,
        authentication: ModelAuthentication,
        http_client: httpx2.AsyncClient,
        hooks: ProviderUsageHooks,
    ) -> None:
        self._connection = connection
        self._authentication = authentication
        self._http_client = http_client
        self._hooks = hooks
        # SDK history contains opaque markers, never native thinking/signatures.
        self._assistant_turns: dict[str, tuple[list[dict[str, Any]], list[str]]] = {}
        self._call_ids: set[str] = set()

    async def close(self) -> None:
        self._assistant_turns.clear()
        self._call_ids.clear()

    def _messages(self, items: str | list[TResponseInputItem]) -> list[dict[str, Any]]:
        if isinstance(items, str):
            return [{"role": "user", "content": items}]
        messages: list[dict[str, Any]] = []
        siblings: list[str] = []
        pending_calls: set[str] = set()
        for item in items:
            value = cast(dict[str, Any], item)
            if siblings:
                if value.get("id") != siblings.pop(0):
                    raise AgentExecutionFailedError("conversation_rejected")
                continue
            if value.get("type") == "reasoning":
                turn = self._assistant_turns.get(value.get("id", ""))
                if turn is None or pending_calls:
                    raise AgentExecutionFailedError("conversation_rejected")
                content, output_ids = turn
                messages.append({"role": "assistant", "content": content})
                siblings = list(output_ids)
                pending_calls = {part["id"] for part in content if part["type"] == "tool_use"}
            elif value.get("type") == "function_call_output":
                call_id = value.get("call_id")
                output = value.get("output")
                if call_id not in pending_calls or not isinstance(output, str):
                    raise AgentExecutionFailedError("conversation_rejected")
                pending_calls.remove(call_id)
                block = {"type": "tool_result", "tool_use_id": call_id, "content": output}
                if messages and messages[-1]["role"] == "user":
                    messages[-1]["content"].append(block)
                else:
                    messages.append({"role": "user", "content": [block]})
            elif value.get("role") == "user" and not pending_calls:
                content = value.get("content")
                if isinstance(content, list) and all(
                    isinstance(part, dict)
                    and cast(dict[str, object], part).get("type") == "input_text"
                    and isinstance(cast(dict[str, object], part).get("text"), str)
                    for part in cast(list[object], content)
                ):
                    content = "\n".join(
                        part["text"] for part in cast(list[dict[str, str]], content)
                    )
                if not isinstance(content, str):
                    raise AgentExecutionFailedError("conversation_rejected")
                messages.append({"role": "user", "content": content})
            else:
                raise AgentExecutionFailedError("conversation_rejected")
        if siblings or pending_calls or not messages or messages[-1]["role"] != "user":
            raise AgentExecutionFailedError("conversation_rejected")
        return messages

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        status = 503
        for attempt in range(MAX_AGENT_HTTP_RETRIES + 1):
            retry_delay = 0.5 * (2**attempt)
            if self._hooks.error is not None:
                raise self._hooks.error
            credentials = await self._authentication.authenticate()
            headers = {"anthropic-version": "2023-06-01"}
            if self._connection.foundry_api_key is not None:
                headers["x-api-key"] = credentials.api_key.get_secret_value()
            else:
                headers["Authorization"] = "Bearer " + credentials.api_key.get_secret_value()
            try:
                response = await self._http_client.post(
                    credentials.base_url.rstrip("/") + "/v1/messages",
                    headers=headers,
                    json=payload,
                    follow_redirects=False,
                )
            except httpx2.TimeoutException:
                if attempt == MAX_AGENT_HTTP_RETRIES:
                    raise AgentExecutionFailedError("timeout") from None
            except httpx2.TransportError:
                if attempt == MAX_AGENT_HTTP_RETRIES:
                    raise AgentExecutionFailedError("provider_unavailable") from None
            else:
                if self._hooks.error is not None:
                    raise self._hooks.error
                if response.is_success:
                    try:
                        decoded: object = response.json()
                    except ValueError:
                        raise AgentExecutionFailedError() from None
                    if not isinstance(decoded, dict):
                        raise AgentExecutionFailedError()
                    return cast(dict[str, Any], decoded)
                status = response.status_code
                if status not in {408, 409, 429} and status < 500:
                    break
                if attempt == MAX_AGENT_HTTP_RETRIES:
                    break
                # Match the OpenAI SDK's bounded provider-directed waits. Retrying
                # before a rate-limit window resets only spends the retry allowance.
                retry_after: float | None = None
                for header, divisor in (("retry-after-ms", 1000), ("retry-after", 1)):
                    raw_delay = response.headers.get(header)
                    if raw_delay is None:
                        continue
                    try:
                        retry_after = float(raw_delay) / divisor
                    except ValueError:
                        continue
                    break
                else:
                    try:
                        retry_date = parsedate_tz(response.headers.get("retry-after", ""))
                        if retry_date is not None:
                            retry_after = mktime_tz(retry_date) - time.time()
                    except ValueError, TypeError, OverflowError, OSError:
                        pass
                if retry_after is not None and math.isfinite(retry_after):
                    if retry_after > _MAX_RETRY_AFTER_SECONDS:
                        break
                    if retry_after > 0:
                        retry_delay = retry_after
            await asyncio.sleep(retry_delay)
        # Never surface provider messages, headers, or identifiers.
        if status in {401, 403}:
            raise AgentExecutionFailedError("authentication_failed")
        if status in {408, 504}:
            raise AgentExecutionFailedError("timeout")
        if status == 429:
            raise AgentExecutionFailedError("rate_limited")
        if status == 404:
            raise AgentExecutionFailedError("model_unavailable")
        if status == 413:
            raise AgentExecutionFailedError("request_too_large")
        if status >= 500:
            raise AgentExecutionFailedError("provider_unavailable")
        raise AgentExecutionFailedError("provider_request_rejected", provider_http_status=status)

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        if (
            handoffs
            or previous_response_id
            or conversation_id
            or prompt
            or not tracing.is_disabled()
            or (output_schema is not None and not output_schema.is_plain_text())
            or model_settings.tool_choice not in (None, "auto")
        ):
            raise AgentExecutionFailedError("provider_request_rejected")
        effort = model_settings.reasoning.effort if model_settings.reasoning else None
        if effort not in (None, "low", "medium", "high", "xhigh", "max"):
            raise AgentExecutionFailedError("reasoning_rejected")
        native_tools: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, FunctionTool):
                raise AgentExecutionFailedError("tool_definition_rejected")
            native_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.params_json_schema,
                }
            )
        payload: dict[str, Any] = {
            "model": self._connection.model_endpoint,
            "max_tokens": 128_000,
            "thinking": {"type": "adaptive"},
            "messages": self._messages(input),
        }
        if system_instructions:
            payload["system"] = system_instructions
        if effort is not None:
            payload["output_config"] = {"effort": effort}
        if native_tools:
            payload["tools"] = native_tools
            payload["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}
        # Atlas's JSON instruction and candidate validation/repair remain authoritative.
        # OpenAI json_object / encrypted reasoning parameters are not Claude API fields.
        decoded = await self._send(payload)
        content = decoded.get("content")
        stop_reason = decoded.get("stop_reason")
        if stop_reason in ("max_tokens", "model_context_window_exceeded"):
            raise AgentExecutionFailedError("output_truncated")
        if stop_reason == "refusal":
            raise AgentExecutionFailedError("output_refused")
        if stop_reason not in ("end_turn", "tool_use") or not isinstance(content, list):
            raise AgentExecutionFailedError()
        marker = "claude_turn_" + uuid4().hex
        output: list[TResponseOutputItem] = [
            ResponseReasoningItem(id=marker, type="reasoning", summary=[]),
        ]
        siblings: list[str] = []
        tool_count = 0
        text_parts: list[str] = []
        native_content: list[dict[str, Any]] = []
        tool_names = {tool["name"] for tool in native_tools}
        for part in cast(list[object], content):
            if not isinstance(part, dict):
                raise AgentExecutionFailedError()
            block = cast(dict[str, Any], part)
            native_content.append(block)
            block_type = block.get("type")
            item_id = "claude_item_" + uuid4().hex
            if block_type in ("thinking", "redacted_thinking"):
                continue
            if block_type == "text" and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
                continue
            elif block_type == "tool_use":
                call_id = block.get("id")
                name = block.get("name")
                arguments = block.get("input")
                if (
                    not isinstance(call_id, str)
                    or not call_id
                    or call_id in self._call_ids
                    or not isinstance(name, str)
                    or name not in tool_names
                    or not isinstance(arguments, dict)
                ):
                    raise AgentExecutionFailedError("tool_definition_rejected")
                self._call_ids.add(call_id)
                tool_count += 1
                output.append(
                    ResponseFunctionToolCall(
                        id=item_id,
                        type="function_call",
                        call_id=call_id,
                        name=name,
                        arguments=json.dumps(arguments, ensure_ascii=False, allow_nan=False),
                        status="completed",
                    )
                )
            else:
                raise AgentExecutionFailedError()
            siblings.append(item_id)
        if text_parts:
            # Runner uses the final SDK message as its result. Native text blocks may
            # split one JSON document; preserve every block in that single message.
            item_id = "claude_item_" + uuid4().hex
            output.append(
                ResponseOutputMessage(
                    id=item_id,
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[
                        ResponseOutputText(
                            type="output_text", text="".join(text_parts), annotations=[]
                        )
                    ],
                )
            )
            siblings.append(item_id)
        if (stop_reason == "tool_use") != bool(tool_count) or len(output) == 1:
            raise AgentExecutionFailedError()
        self._assistant_turns[marker] = (native_content, siblings)
        # Persistent counters are recorded by ProviderUsageHooks, including failed attempts.
        # SDK usage is not persisted and must never carry the raw provider payload.
        counts = self._hooks.last_usage
        return ModelResponse(
            output=output,
            usage=Usage(
                requests=1,
                input_tokens=counts.input_tokens or 0,
                output_tokens=counts.output_tokens or 0,
                total_tokens=counts.total_tokens or 0,
            ),
            response_id=None,
        )

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError("Atlas uses non-streaming model execution")
