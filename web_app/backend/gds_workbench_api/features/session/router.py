"""Server-derived Principal Session HTTP route."""

from fastapi import APIRouter, Depends
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.session.contracts import SessionRecord
from gds_workbench_api.features.session.service import SessionService


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
