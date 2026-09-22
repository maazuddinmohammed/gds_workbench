"""Read-only, Tenant-scoped Model Workflow Overview HTTP route."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.workflows.overview.contracts import ModelWorkflowOverview
from gds_workbench_api.features.workflows.overview.service import WorkflowOverviewService


def create_workflow_overview_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowOverviewService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}",
        tags=["models"],
    )

    async def read_overview(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelWorkflowOverview:
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
