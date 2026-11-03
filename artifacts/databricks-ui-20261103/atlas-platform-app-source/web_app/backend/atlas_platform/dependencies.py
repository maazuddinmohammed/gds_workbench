"""Shared FastAPI dependencies; authorization stays in feature services."""

from collections.abc import Awaitable, Callable

from atlas_mcp.application.identity import IdentityProvider
from atlas_mcp.domain.authorization import RequestPrincipal
from fastapi import Request


def principal_dependency(
    identity_provider: IdentityProvider,
) -> Callable[[Request], Awaitable[RequestPrincipal]]:
    """Bind authentication to this router's provider, isolated from other apps."""

    async def authenticate(request: Request) -> RequestPrincipal:
        return identity_provider.authenticate(request.headers)

    return authenticate
