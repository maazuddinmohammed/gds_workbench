"""Read-only runtime contract fingerprint for compatible plugin preflight."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import Tool, ToolAnnotations

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.tools.modeling.common import ContractModel


class ServerContractResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    mcp_server_version: str
    tool_count: int
    tool_contract_sha256: str


class ServerContractToolError(Exception):
    """A bounded compatibility failure safe for MCP serialization."""


def register_server_contract_tool(
    server: MCPServer[None],
    *,
    identity_provider: IdentityProvider,
    audit: ToolCallAuditMiddleware,
    mcp_server_version: str,
    contract_digest: Callable[[list[Tool]], str],
) -> None:
    @server.tool(
        description=(
            "Return the deployed GDS MCP version and complete public-tool contract fingerprint. "
            "A packaged GDS plugin compares this once before its first mutation."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": ToolPolicy.TENANT_READ.value},
        structured_output=True,
    )
    async def get_server_contract(
        ctx: Context[None],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ServerContractResult:
        del schema_version
        try:
            identity_provider.request_principal(ctx.request_context.request)
            tools = await server.list_tools()
            return ServerContractResult(
                mcp_server_version=mcp_server_version,
                tool_count=len(tools),
                tool_contract_sha256=contract_digest(tools),
            )
        except AuthenticationError as error:
            raise ServerContractToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ServerContractToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ServerContractToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_server_contract",
        policy=ToolPolicy.TENANT_READ,
        summarize_input=_audit_input,
        retain_arguments={"schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str]:
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid")
    }


__all__ = ["register_server_contract_tool"]
