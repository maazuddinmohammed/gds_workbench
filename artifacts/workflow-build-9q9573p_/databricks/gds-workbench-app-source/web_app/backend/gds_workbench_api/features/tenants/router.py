"""Tenant entry HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from gds_etl_workbench.application.identity import IdentityProvider

from gds_workbench_api.features.tenants.contracts import (
    TenantCollection,
    TenantHome,
    TenantSelection,
)
from gds_workbench_api.features.tenants.service import (
    TenantService,
)


def create_tenants_router(
    *,
    identity_provider: IdentityProvider,
    service: TenantService,
) -> APIRouter:
    """Build the authenticated Tenant entry surface."""

    router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

    async def list_tenants(
        request: Request,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> TenantCollection:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_tenants(
            principal,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "",
        list_tenants,
        methods=["GET"],
        response_model=TenantCollection,
    )

    async def select_tenant(
        request: Request,
        tenant_id: int,
    ) -> TenantSelection:
        principal = identity_provider.authenticate(request.headers)
        return await service.select_tenant(principal, tenant_id=tenant_id)

    router.add_api_route(
        "/{tenant_id}/select",
        select_tenant,
        methods=["POST"],
        response_model=TenantSelection,
    )

    async def read_tenant_home(
        request: Request,
        tenant_id: int,
    ) -> TenantHome:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_tenant_home(principal, tenant_id=tenant_id)

    router.add_api_route(
        "/{tenant_id}/home",
        read_tenant_home,
        methods=["GET"],
        response_model=TenantHome,
    )
    return router
