# GDS Workbench local MCP bridge

This local `stdio` MCP server forwards tool discovery and tool calls to the
authenticated Azure MCP endpoint. Tool schemas stay owned by the remote server.

## Required Entra desktop client

Create one Entra app registration for installed users:

1. Name: `GDS Workbench MCP Bridge`.
2. Supported accounts: this organization only.
3. Authentication > Add platform > Mobile and desktop applications.
4. Add custom redirect URI `http://localhost:8400`.
5. Enable public client flows.
6. API permissions > your GDS Workbench API > delegated `workbench.access`.
7. Grant tenant admin consent if your tenant requires it.

No client secret is used. Copy the desktop application's **Application (client)
ID** into `GDS_BRIDGE_ENTRA_CLIENT_ID` when VS Code first starts the bridge.

## Local preparation

```bash
uv sync --project mcp_bridge --all-groups
```

VS Code starts the bridge from `.vscode/mcp.json`. The first tool discovery opens
the system browser. Later starts use the operating system's encrypted token cache.

## Verification

```bash
cd mcp_bridge
.venv/bin/pytest -c pyproject.toml -q ../tests/bridge
.venv/bin/ruff check gds_workbench_bridge ../tests/bridge
.venv/bin/pyright --project pyproject.toml
```
