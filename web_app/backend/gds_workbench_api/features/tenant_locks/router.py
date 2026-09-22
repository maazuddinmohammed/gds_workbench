"""Explicit governed Tenant Lock HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.tenant_locks.contracts import (
    AcquireLockRequest,
    LockHistoryPage,
    OverrideLockRequest,
    RenewLockRequest,
    TenantLockMutation,
)
from gds_workbench_api.features.tenant_locks.service import TenantLockService


def create_tenant_lock_router(
    *,
    identity_provider: IdentityProvider,
    service: TenantLockService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/lock", tags=["tenant-lock"])

    async def acquire(
        tenant_id: int,
        body: AcquireLockRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> TenantLockMutation:
        return await service.acquire(
            principal,
            tenant_id=tenant_id,
            duration_minutes=body.duration_minutes,
            purpose=body.purpose,
        )

    async def renew(
        tenant_id: int,
        body: RenewLockRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> TenantLockMutation:
        return await service.renew(
            principal,
            tenant_id=tenant_id,
            duration_minutes=body.duration_minutes,
        )

    async def release(
        tenant_id: int, *, principal: RequestPrincipal = Depends(authenticate)
    ) -> TenantLockMutation:
        return await service.release(principal, tenant_id=tenant_id)

    async def override(
        tenant_id: int,
        body: OverrideLockRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> TenantLockMutation:
        return await service.override(
            principal,
            tenant_id=tenant_id,
            reason=body.reason,
        )

    async def history(
        tenant_id: int,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> LockHistoryPage:
        return await service.history(
            principal,
            tenant_id=tenant_id,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "/acquire",
        acquire,
        methods=["POST"],
        response_model=TenantLockMutation,
    )
    router.add_api_route(
        "/renew",
        renew,
        methods=["POST"],
        response_model=TenantLockMutation,
    )
    router.add_api_route(
        "/release",
        release,
        methods=["POST"],
        response_model=TenantLockMutation,
    )
    router.add_api_route(
        "/override",
        override,
        methods=["POST"],
        response_model=TenantLockMutation,
    )
    router.add_api_route(
        "/history",
        history,
        methods=["GET"],
        response_model=LockHistoryPage,
    )
    return router
