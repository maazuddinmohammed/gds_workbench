from __future__ import annotations

import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_vscode_style_stdio_process_lists_and_calls_remote_tool() -> None:
    fixture = Path(__file__).with_name("stdio_test_server.py")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(fixture)],
        cwd=Path(__file__).parents[2],
    )

    transport = stdio_client(parameters)
    async with Client(transport) as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_tenants")

    assert [tool.name for tool in tools.tools] == ["list_tenants"]
    assert result.structured_content == {"tenant_names": ["Tenant One"]}
