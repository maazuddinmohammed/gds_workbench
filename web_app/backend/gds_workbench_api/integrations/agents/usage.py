"""Capture numeric usage and terminal finish signals before SDK normalization."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import httpx2
from gds_etl_workbench.domain.errors import DependencyUnavailableError, WorkbenchError

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionFailedError,
)
from gds_workbench_api.features.workflows.usage.contracts import (
    ModelRequestRecorder,
    ModelTokenUsage,
)


class ProviderUsageHooks:
    """Keep only safe failures and counters; optionally record each transport attempt."""

    def __init__(self, recorder: ModelRequestRecorder | None) -> None:
        self._recorder = recorder
        self._request_ordinal = 0
        self.error: WorkbenchError | None = None

    async def on_request(self, request: httpx2.Request) -> None:
        if self.error is not None:
            raise self.error
        if self._recorder is None:
            return
        self._request_ordinal += 1
        request.extensions["gds_model_request_id"] = await self._recorder.begin_request(
            self._request_ordinal
        )

    async def on_response(self, response: httpx2.Response) -> None:
        request_id = response.request.extensions.get("gds_model_request_id")
        if self._recorder is not None and not isinstance(request_id, UUID):
            raise ValueError("The model request usage identity is missing")
        # The SDK also reads this non-streaming response. Never retain its body in telemetry.
        await response.aread()
        usage = ModelTokenUsage()
        try:
            payload: object = response.json()
            if isinstance(payload, dict):
                decoded = cast(dict[str, object], payload)
                choices = decoded.get("choices")
                if response.is_success and isinstance(choices, list) and choices:
                    choice = cast(list[object], choices)[0]
                    if isinstance(choice, dict):
                        finish_reason = cast(dict[str, object], choice).get("finish_reason")
                        if finish_reason == "length":
                            self.error = AgentExecutionFailedError("output_truncated")
                        elif finish_reason == "content_filter":
                            self.error = AgentExecutionFailedError("output_refused")
                raw = decoded.get("usage")
                if isinstance(raw, dict):
                    counts = cast(dict[str, object], raw)
                    input_details = counts.get("prompt_tokens_details")
                    output_details = counts.get("completion_tokens_details")
                    prompt: Mapping[str, object] = (
                        cast(Mapping[str, object], input_details)
                        if isinstance(input_details, dict)
                        else {}
                    )
                    completion: Mapping[str, object] = (
                        cast(Mapping[str, object], output_details)
                        if isinstance(output_details, dict)
                        else {}
                    )
                    usage = ModelTokenUsage.model_validate(
                        {
                            "input_tokens": counts.get("prompt_tokens"),
                            "output_tokens": counts.get("completion_tokens"),
                            "total_tokens": counts.get("total_tokens"),
                            "cached_input_tokens": prompt.get("cached_tokens"),
                            "cache_write_input_tokens": prompt.get("cache_write_tokens"),
                            "reasoning_output_tokens": completion.get("reasoning_tokens"),
                            "other_token_types": any(
                                value not in (None, 0)
                                for detail, supported in (
                                    (prompt, {"cached_tokens", "cache_write_tokens"}),
                                    (completion, {"reasoning_tokens"}),
                                )
                                for key, value in detail.items()
                                if key not in supported
                            ),
                        }
                    )
        except ValueError, RecursionError:
            # Invalid/missing provider counters are unknown, never fabricated free calls.
            usage = ModelTokenUsage()
        if self._recorder is None:
            return
        assert isinstance(request_id, UUID)
        try:
            await self._recorder.complete_request(request_id, usage)
        except Exception as error:
            # Raising here makes the SDK retry a paid response. Stop subsequent HTTP sends
            # and report the recording failure after the SDK returns; the pending row remains.
            self.error = (
                error if isinstance(error, WorkbenchError) else DependencyUnavailableError()
            )
