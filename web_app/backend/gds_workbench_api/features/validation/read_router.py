"""Validation eligibility and applied-ledger HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency

from .contracts import ValidationEligibleSystemCollection, ValidationLedger
from .read_service import ValidationReadService


def create_validation_read_router(
    *,
    identity_provider: IdentityProvider,
    service: ValidationReadService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/validation",
        tags=["validation"],
    )

    async def list_eligible_systems(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ValidationEligibleSystemCollection:
        return await service.list_eligible_systems(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    router.add_api_route(
        "/systems",
        list_eligible_systems,
        methods=["GET"],
        response_model=ValidationEligibleSystemCollection,
    )

    async def read_ledger(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ValidationLedger:
        return await service.read_ledger(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    router.add_api_route(
        "/ledger",
        read_ledger,
        methods=["GET"],
        response_model=ValidationLedger,
    )
    return router


__all__ = ["create_validation_read_router"]
