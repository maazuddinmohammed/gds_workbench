"""Central append-only audit boundary for MCP tool calls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import uuid4

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS
from pydantic import ValidationError

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    ResolvedPrincipal,
)
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ToolCallLogRecord

type InputMetadata = Mapping[str, str | int | bool | None]
type InputMetadataBuilder = Callable[[Mapping[str, Any]], InputMetadata]


@dataclass(frozen=True, slots=True)
class ToolAuditSpec:
    policy: ToolPolicy
    summarize_input: InputMetadataBuilder
    tenant_argument: str | None


class ToolCallAuditMiddleware:
    """Append one bounded record after each configured MCP tool finishes."""

    def __init__(
        self,
        *,
        database: Database,
        identity_provider: IdentityProvider,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._identity_provider = identity_provider
        self._authorizer = authorizer
        self._tools: dict[str, ToolAuditSpec] = {}

    def register_tool(
        self,
        name: str,
        *,
        policy: ToolPolicy,
        summarize_input: InputMetadataBuilder,
        tenant_argument: str | None = None,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"duplicate tool audit registration: {name}")
        self._tools[name] = ToolAuditSpec(
            policy=policy,
            summarize_input=summarize_input,
            tenant_argument=tenant_argument,
        )

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        if ctx.method != "tools/call" or ctx.params is None:
            return await call_next(ctx)

        tool_name = ctx.params.get("name")
        if not isinstance(tool_name, str) or (spec := self._tools.get(tool_name)) is None:
            return await call_next(ctx)

        arguments = ctx.params.get("arguments")
        safe_arguments: Mapping[str, Any] = (
            cast(Mapping[str, Any], arguments) if isinstance(arguments, Mapping) else {}
        )
        input_metadata = spec.summarize_input(safe_arguments)
        tenant_id = None
        if spec.tenant_argument is not None:
            raw_tenant_id: Any = safe_arguments.get(spec.tenant_argument)
            if type(raw_tenant_id) is int and 0 < raw_tenant_id <= 9_223_372_036_854_775_807:
                tenant_id = raw_tenant_id

        try:
            request_principal = self._identity_provider.request_principal(ctx.request)
            async with self._database.read_transaction() as transaction:
                principal = await self._authorizer.resolve_principal(
                    transaction,
                    request_principal,
                )
        except (AuthenticationError, WorkbenchError):
            # No active server-side Principal exists to satisfy the audit row's
            # Principal constraint. The tool returns its normal safe denial.
            return await call_next(ctx)

        try:
            result = await call_next(ctx)
        except Exception as error:
            await self._append(
                principal=principal,
                tool_name=tool_name,
                spec=spec,
                input_metadata=input_metadata,
                tenant_id=tenant_id,
                status="failed",
                failure_code=_protocol_failure_code(error),
            )
            raise

        failed = isinstance(result, Mapping) and result.get("isError") is True
        await self._append(
            principal=principal,
            tool_name=tool_name,
            spec=spec,
            input_metadata=input_metadata,
            tenant_id=tenant_id,
            status="failed" if failed else "succeeded",
            failure_code="tool_error" if failed else None,
        )
        return result

    async def _append(
        self,
        *,
        principal: ResolvedPrincipal,
        tool_name: str,
        spec: ToolAuditSpec,
        input_metadata: InputMetadata,
        tenant_id: int | None,
        status: Literal["succeeded", "failed"],
        failure_code: str | None,
    ) -> None:
        try:
            await self._database.append_tool_call_log(
                ToolCallLogRecord(
                    tool_call_id=uuid4(),
                    principal_id=principal.principal_id,
                    principal_display_name=principal.display_name,
                    actor_kind=principal.actor_kind,
                    tool_name=tool_name,
                    tool_policy=spec.policy,
                    tenant_id=tenant_id,
                    input_metadata=input_metadata,
                    status=status,
                    failure_code=failure_code,
                )
            )
        except WorkbenchError:
            raise MCPError(
                code=INTERNAL_ERROR,
                message="Tool-call audit is unavailable.",
            ) from None


def _protocol_failure_code(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "invalid_request"
    if isinstance(error, MCPError) and error.code == INVALID_PARAMS:
        return "invalid_request"
    return "internal_error"
