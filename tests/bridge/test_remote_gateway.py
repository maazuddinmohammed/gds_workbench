from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import httpx2
import mcp.types as types
from mcp.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from gds_workbench_bridge.configuration import BridgeSettings
from gds_workbench_bridge.remote import (
    AuthenticatedRemoteMcpGateway,
    OAuthMetadata,
)


class FakeTokenProvider:
    def __init__(self) -> None:
        self.metadata: OAuthMetadata | None = None
        self.closed = False

    async def get_token(self, metadata: OAuthMetadata) -> str:
        self.metadata = metadata
        return "test-access-token"

    async def close(self) -> None:
        self.closed = True


async def test_remote_gateway_discovers_auth_and_forwards_bearer_token() -> None:
    tenant_id = UUID("11111111-1111-1111-1111-111111111111")
    remote_url = "https://testserver/mcp"
    seen_authorization: list[str | None] = []

    @asynccontextmanager
    async def lifespan(_server: Server[None]) -> AsyncGenerator[None]:
        yield None

    async def list_tools(
        _context: object,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name="list_tenants",
                    input_schema={"type": "object", "properties": {}},
                )
            ]
        )

    async def metadata(_request: Request) -> Response:
        return JSONResponse(
            {
                "resource": remote_url,
                "authorization_servers": [
                    f"https://login.microsoftonline.com/{tenant_id}/v2.0"
                ],
                "scopes_supported": [f"{remote_url}/workbench.access"],
                "bearer_methods_supported": ["header"],
            }
        )

    remote_server = Server[None](
        "remote-test-server",
        lifespan=lifespan,
        on_list_tools=list_tools,
    )
    application = remote_server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["testserver"],
            allowed_origins=[],
        ),
        custom_starlette_routes=[
            Route(
                "/.well-known/oauth-protected-resource/mcp",
                metadata,
                methods=["GET"],
            )
        ],
    )

    class CaptureAuthorizationMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self._app = app

        async def __call__(
            self,
            scope: Scope,
            receive: Receive,
            send: Send,
        ) -> None:
            if scope.get("type") == "http" and scope.get("path") == "/mcp":
                headers = dict(scope.get("headers", []))
                raw = headers.get(b"authorization")
                seen_authorization.append(raw.decode() if raw else None)
            await self._app(scope, receive, send)

    protected_application = CaptureAuthorizationMiddleware(application)
    http_transport = httpx2.ASGITransport(app=protected_application)
    token_provider = FakeTokenProvider()
    gateway = AuthenticatedRemoteMcpGateway(
        BridgeSettings(
            remote_url=remote_url,
            entra_client_id=UUID("22222222-2222-2222-2222-222222222222"),
            redirect_uri="http://localhost:8400",
        ),
        token_provider,
        http_transport=http_transport,
    )

    async with application.router.lifespan_context(application):
        result = await gateway.list_tools(None)
    await gateway.close()

    assert [tool.name for tool in result.tools] == ["list_tenants"]
    assert seen_authorization
    assert set(seen_authorization) == {"Bearer test-access-token"}
    assert token_provider.metadata == OAuthMetadata(
        tenant_id=tenant_id,
        scope=f"{remote_url}/workbench.access",
    )
    assert token_provider.closed is True
