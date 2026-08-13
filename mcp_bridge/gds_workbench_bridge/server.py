"""Local MCP surface that forwards tool operations to a remote gateway."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol

import mcp.types as types
from mcp.server import Server
from mcp.server.context import ServerRequestContext


class RemoteMcpGateway(Protocol):
    """Remote operations required by the local bridge."""

    async def list_tools(
        self,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult: ...

    async def call_tool(
        self,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult | types.InputRequiredResult: ...

    async def close(self) -> None: ...


def create_bridge_server(remote: RemoteMcpGateway) -> Server[None]:
    """Create a local server without copying remote tool definitions."""

    @asynccontextmanager
    async def lifespan(_server: Server[None]) -> AsyncGenerator[None]:
        try:
            yield None
        finally:
            await remote.close()

    async def list_tools(
        _context: ServerRequestContext[None],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return await remote.list_tools(params)

    async def call_tool(
        _context: ServerRequestContext[None],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult | types.InputRequiredResult:
        return await remote.call_tool(params)

    return Server[None](
        name="gds-workbench-local-bridge",
        version="0.1.0",
        title="GDS Workbench Local Bridge",
        description="Local authenticated bridge to the GDS Workbench MCP server.",
        instructions=(
            "Tool definitions and tool calls are forwarded to the governed remote "
            "GDS Workbench MCP server."
        ),
        lifespan=lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
