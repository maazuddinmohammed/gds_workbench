"""Tenant-owned Model read HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from gds_etl_workbench.adapters.auth.identity import IdentityProvider

from gds_workbench_api.features.models.contracts import (
    ModelCollection,
    ModelDetail,
    ModelStatus,
)
from gds_workbench_api.features.models.service import ModelService


def create_models_router(
    *,
    identity_provider: IdentityProvider,
    service: ModelService,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/models", tags=["models"])

    async def list_models(
        request: Request,
        tenant_id: int,
        status: ModelStatus = "active",
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> ModelCollection:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_models(
            principal,
            tenant_id=tenant_id,
            model_status=status,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "",
        list_models,
        methods=["GET"],
        response_model=ModelCollection,
    )

    async def read_model(
        request: Request,
        tenant_id: int,
        model_id: int,
    ) -> ModelDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_model(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    router.add_api_route(
        "/{model_id}",
        read_model,
        methods=["GET"],
        response_model=ModelDetail,
    )
    return router
