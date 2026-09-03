"""Read-only, Tenant-scoped Model Workflow Overview HTTP route."""

from typing import Annotated

from fastapi import APIRouter, Path, Request
from gds_etl_workbench.application.identity import IdentityProvider

from gds_workbench_api.features.workflows.overview.contracts import ModelWorkflowOverview
from gds_workbench_api.features.workflows.overview.service import WorkflowOverviewService


def create_workflow_overview_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowOverviewService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}",
        tags=["models"],
    )

    async def read_overview(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
    ) -> ModelWorkflowOverview:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_overview(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    router.add_api_route(
        "/overview",
        read_overview,
        methods=["GET"],
        response_model=ModelWorkflowOverview,
    )
    return router
