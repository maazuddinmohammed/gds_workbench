"""Capture numeric usage before the Agents SDK normalizes absent counts to zero."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import httpx2
from gds_etl_workbench.domain.errors import DependencyUnavailableError, WorkbenchError

from gds_workbench_api.features.workflows.usage.contracts import (
    ModelRequestRecorder,
    ModelTokenUsage,
)


class ProviderUsageHooks:
    """One HTTP client's invocation; every transport retry gets its own durable row."""

    def __init__(self, recorder: ModelRequestRecorder) -> None:
        self._recorder = recorder
        self._request_ordinal = 0
        self.error: WorkbenchError | None = None

    async def on_request(self, request: httpx2.Request) -> None:
        if self.error is not None:
            raise self.error
        self._request_ordinal += 1
        request.extensions["gds_model_request_id"] = await self._recorder.begin_request(
            self._request_ordinal
        )

    async def on_response(self, response: httpx2.Response) -> None:
        request_id = response.request.extensions.get("gds_model_request_id")
        if not isinstance(request_id, UUID):
            raise ValueError("The model request usage identity is missing")
        # The SDK also reads this non-streaming response. Never retain its body in telemetry.
        content = await response.aread()
        usage = ModelTokenUsage()
        if len(content) <= 24 * 1024 * 1024:
            try:
                payload: object = response.json()
                if isinstance(payload, dict):
                    raw = cast(dict[str, object], payload).get("usage")
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
            except (ValueError, RecursionError):
                # Invalid/missing provider counters are unknown, never fabricated free calls.
                usage = ModelTokenUsage()
        try:
            await self._recorder.complete_request(request_id, usage)
        except Exception as error:
            # Raising here makes the SDK retry a paid response. Stop subsequent HTTP sends
            # and report the recording failure after the SDK returns; the pending row remains.
            self.error = (
                error if isinstance(error, WorkbenchError) else DependencyUnavailableError()
            )
