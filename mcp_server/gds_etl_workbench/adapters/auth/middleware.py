"""ASGI authentication boundary for MCP."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider


class ProtectedMCPMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        identity_provider: IdentityProvider,
        require_https: bool,
    ) -> None:
        self._app = app
        self._identity_provider = identity_provider
        self._require_https = require_https

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/mcp"):
            await self._app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if self._require_https:
            forwarded_protocol = headers.get("x-forwarded-proto", "").split(",", maxsplit=1)[0]
            if forwarded_protocol.strip().lower() != "https":
                response = JSONResponse(
                    {
                        "error": {
                            "code": "invalid_request",
                            "message": "HTTPS is required.",
                            "retryable": False,
                        }
                    },
                    status_code=400,
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return

        try:
            principal = self._identity_provider.authenticate(headers)
        except AuthenticationError as error:
            response = JSONResponse(
                {
                    "error": {
                        "code": error.public_code,
                        "message": error.message,
                        "retryable": False,
                    }
                },
                status_code=error.http_status,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["request_principal"] = principal
        await self._app(scope, receive, send)
