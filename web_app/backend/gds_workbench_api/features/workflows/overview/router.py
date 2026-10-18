"""Read-only, Tenant-scoped Project Workflow Overview HTTP route."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.workflows.overview.contracts import ProjectWorkflowOverview
from gds_workbench_api.features.workflows.overview.service import WorkflowOverviewService


def create_workflow_overview_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowOverviewService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}",
        tags=["projects"],
    )

    async def read_overview(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectWorkflowOverview:
        return await service.read_overview(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
        )

    router.add_api_route(
        "/overview",
        read_overview,
        methods=["GET"],
        response_model=ProjectWorkflowOverview,
    )
    return router
