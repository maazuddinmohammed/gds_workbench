"""Tenant entry HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
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
    authenticate = principal_dependency(identity_provider)

    router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

    async def list_tenants(
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> TenantCollection:
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
        tenant_id: int, *, principal: RequestPrincipal = Depends(authenticate)
    ) -> TenantSelection:
        return await service.select_tenant(principal, tenant_id=tenant_id)

    router.add_api_route(
        "/{tenant_id}/select",
        select_tenant,
        methods=["POST"],
        response_model=TenantSelection,
    )

    async def read_tenant_home(
        tenant_id: int, *, principal: RequestPrincipal = Depends(authenticate)
    ) -> TenantHome:
        return await service.read_tenant_home(principal, tenant_id=tenant_id)

    router.add_api_route(
        "/{tenant_id}/home",
        read_tenant_home,
        methods=["GET"],
        response_model=TenantHome,
    )
    return router
