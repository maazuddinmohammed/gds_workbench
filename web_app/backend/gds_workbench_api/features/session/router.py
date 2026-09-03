"""Server-derived Principal Session HTTP route."""

from fastapi import APIRouter, Request
from gds_etl_workbench.application.identity import IdentityProvider

from gds_workbench_api.features.session.contracts import SessionRecord
from gds_workbench_api.features.session.service import SessionService


def create_session_router(
    *,
    identity_provider: IdentityProvider,
    service: SessionService,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["session"])

    async def session(request: Request) -> SessionRecord:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_session(principal)

    router.add_api_route(
        "/session",
        session,
        methods=["GET"],
        response_model=SessionRecord,
    )
    return router
