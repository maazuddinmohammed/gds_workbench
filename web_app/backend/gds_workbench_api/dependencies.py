"""Shared FastAPI dependencies; authorization stays in feature services."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal


def principal_dependency(
    identity_provider: IdentityProvider,
) -> Callable[[Request], Awaitable[RequestPrincipal]]:
    """Bind authentication to this router's provider, isolated from other apps."""

    async def authenticate(request: Request) -> RequestPrincipal:
        return identity_provider.authenticate(request.headers)

    return authenticate
