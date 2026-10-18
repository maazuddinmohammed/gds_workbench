"""Keep Stage upload tools on the Atlas Stage Runner's MCP connection."""

from __future__ import annotations

from typing import Any, cast

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.types import CallToolResult, TextContent
from mcp_types.methods import serialize_server_result
from starlette.requests import Request

STAGE_RUNNER_HEADER = "x-gds-mcp-client"
STAGE_RUNNER_CLIENT = "atlas-stage-runner"
STAGE_UPLOAD_TOOLS = frozenset(
    f"{operation}_{area}_{target}"
    for area in ("metadata", "project")
    for operation, target in (
        ("stage", "change_set"),
        ("begin", "stage_batch"),
        ("put", "stage_chunk"),
        ("commit", "stage_batch"),
    )
)


class StageRunnerGate:
    """Hide and refuse Stage upload tools on connections other than the Stage Runner.

    The runner uploads only records whose digest the user approved locally. Its header
    is self-declared, so this is not authentication: every tool still authorizes the
    Principal. The gate stops an agent's own MCP connection from bypassing that review.
    In-memory sessions have no HTTP request; only development identity treats them as
    the runner.
    """

    def __init__(self, *, allow_in_memory: bool) -> None:
        self._allow_in_memory = allow_in_memory

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        if ctx.method not in ("tools/list", "tools/call"):
            return await call_next(ctx)
        request = ctx.request
        if request is None:
            from_stage_runner = self._allow_in_memory
        else:
            from_stage_runner = (
                isinstance(request, Request)
                and request.headers.get(STAGE_RUNNER_HEADER) == STAGE_RUNNER_CLIENT
            )
        if from_stage_runner:
            return await call_next(ctx)

        if ctx.method == "tools/call":
            name = ctx.params.get("name") if ctx.params is not None else None
            if name not in STAGE_UPLOAD_TOOLS:
                return await call_next(ctx)
            # Same text as SDK tool failures so clients parse one error format; a
            # short-circuiting middleware owns the protocol-version wire shape.
            message = (
                f"Error executing tool {name}: stage_runner_required: Stage uploads run only "
                "through the Atlas Stage Runner after the user approves the local review."
            )
            refused = CallToolResult(
                content=[TextContent(type="text", text=message)], is_error=True
            )
            return serialize_server_result(
                "tools/call",
                ctx.protocol_version,
                refused.model_dump(by_alias=True, mode="json", exclude_none=True),
            )

        result = await call_next(ctx)
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            return result
        visible: list[object] = [
            tool
            for tool in cast(list[object], result["tools"])
            if not (
                isinstance(tool, dict)
                and cast(dict[str, object], tool).get("name") in STAGE_UPLOAD_TOOLS
            )
        ]
        return {**result, "tools": visible}


__all__ = [
    "STAGE_RUNNER_CLIENT",
    "STAGE_RUNNER_HEADER",
    "STAGE_UPLOAD_TOOLS",
    "StageRunnerGate",
]
