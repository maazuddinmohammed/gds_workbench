"""QA eligibility and applied-ledger HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Path, Request
from gds_etl_workbench.adapters.auth.identity import IdentityProvider

from .contracts import QAEligibleSystemCollection, QALedger
from .read_service import QAReadService


def create_qa_read_router(
    *,
    identity_provider: IdentityProvider,
    service: QAReadService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/qa",
        tags=["qa"],
    )

    async def list_eligible_systems(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
    ) -> QAEligibleSystemCollection:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_eligible_systems(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    router.add_api_route(
        "/systems",
        list_eligible_systems,
        methods=["GET"],
        response_model=QAEligibleSystemCollection,
    )

    async def read_ledger(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
    ) -> QALedger:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_ledger(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    router.add_api_route(
        "/ledger",
        read_ledger,
        methods=["GET"],
        response_model=QALedger,
    )
    return router


__all__ = ["create_qa_read_router"]
