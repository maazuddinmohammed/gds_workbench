from __future__ import annotations

from typing import Any

import mcp.types as types
from mcp import Client

from gds_workbench_bridge.server import create_bridge_server


class FakeRemoteGateway:
    def __init__(self) -> None:
        self.list_params: types.PaginatedRequestParams | None = None
        self.call_params: types.CallToolRequestParams | None = None
        self.closed = False

    async def list_tools(
        self,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        self.list_params = params
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name="list_tenants",
                    description="List visible tenants.",
                    input_schema={"type": "object", "properties": {}},
                )
            ]
        )

    async def call_tool(
        self,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult | types.InputRequiredResult:
        self.call_params = params
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Tenant One")],
            structured_content={"tenants": [{"tenant_name": "Tenant One"}]},
        )

    async def close(self) -> None:
        self.closed = True


async def test_bridge_forwards_tool_schema_without_a_local_copy() -> None:
    remote = FakeRemoteGateway()
    server = create_bridge_server(remote)

    async with Client(server) as client:
        result = await client.list_tools(cursor="next-page")

    assert [tool.name for tool in result.tools] == ["list_tenants"]
    assert remote.list_params is not None
    assert remote.list_params.cursor == "next-page"
    assert remote.closed is True


async def test_bridge_forwards_complete_tool_call_and_result() -> None:
    remote = FakeRemoteGateway()
    server = create_bridge_server(remote)
    arguments: dict[str, Any] = {"limit": 10}

    async with Client(server) as client:
        result = await client.call_tool("list_tenants", arguments)

    assert remote.call_params is not None
    assert remote.call_params.name == "list_tenants"
    assert remote.call_params.arguments == arguments
    assert result.structured_content == {
        "tenants": [{"tenant_name": "Tenant One"}]
    }
    assert remote.closed is True
