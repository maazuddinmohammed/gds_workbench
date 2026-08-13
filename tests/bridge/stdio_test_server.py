"""Subprocess fixture used to verify the bridge's stdio transport."""

from __future__ import annotations

import asyncio

import mcp.types as types
from mcp.server.stdio import stdio_server

from gds_workbench_bridge.server import create_bridge_server


class FixtureRemoteGateway:
    async def list_tools(
        self,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        del params
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name="list_tenants",
                    input_schema={"type": "object", "properties": {}},
                )
            ]
        )

    async def call_tool(
        self,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult | types.InputRequiredResult:
        assert params.name == "list_tenants"
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Tenant One")],
            structured_content={"tenant_names": ["Tenant One"]},
        )

    async def close(self) -> None:
        return None


async def run() -> None:
    server = create_bridge_server(FixtureRemoteGateway())
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(run())
