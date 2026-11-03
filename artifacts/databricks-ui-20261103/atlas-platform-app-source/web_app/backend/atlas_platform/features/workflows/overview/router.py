"""Read-only, Tenant-scoped Project Workflow Overview HTTP route."""

from typing import Annotated

from atlas_mcp.application.identity import IdentityProvider
from atlas_mcp.domain.authorization import RequestPrincipal
from fastapi import APIRouter, Depends, Path

from atlas_platform.dependencies import principal_dependency
from atlas_platform.features.workflows.overview.contracts import ProjectWorkflowOverview
from atlas_platform.features.workflows.overview.service import WorkflowOverviewService


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
