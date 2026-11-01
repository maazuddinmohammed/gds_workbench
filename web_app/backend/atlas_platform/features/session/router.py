"""Server-derived Principal Session HTTP route."""

from atlas_mcp.application.identity import IdentityProvider
from atlas_mcp.domain.authorization import RequestPrincipal
from fastapi import APIRouter, Depends

from atlas_platform.dependencies import principal_dependency
from atlas_platform.features.session.contracts import SessionRecord
from atlas_platform.features.session.service import SessionService


def create_session_router(
    *,
    identity_provider: IdentityProvider,
    service: SessionService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(prefix="/api/v1", tags=["session"])

    async def session(*, principal: RequestPrincipal = Depends(authenticate)) -> SessionRecord:
        return await service.read_session(principal)

    router.add_api_route(
        "/session",
        session,
        methods=["GET"],
        response_model=SessionRecord,
    )
    return router
