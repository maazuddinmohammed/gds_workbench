"""Tenant-owned Project read HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import JsonValue

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.projects.contracts import (
    ProjectCollection,
    ProjectDetail,
    ProjectStatus,
)
from gds_workbench_api.features.projects.service import ProjectService
from gds_workbench_api.features.projects.templates import default_project_templates


def create_projects_router(
    *,
    identity_provider: IdentityProvider,
    service: ProjectService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/projects", tags=["projects"])

    async def list_projects(
        tenant_id: int,
        status: ProjectStatus = "active",
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectCollection:
        return await service.list_projects(
            principal,
            tenant_id=tenant_id,
            project_status=status,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "",
        list_projects,
        methods=["GET"],
        response_model=ProjectCollection,
    )

    async def read_templates(
        tenant_id: int, *, principal: RequestPrincipal = Depends(authenticate)
    ) -> dict[str, JsonValue]:
        # Reuse the existing Tenant read authorization boundary.
        await service.list_projects(
            principal, tenant_id=tenant_id, project_status="active", page_size=1, cursor=None
        )
        return default_project_templates()

    router.add_api_route("/templates", read_templates, methods=["GET"])

    async def read_project(
        tenant_id: int, project_id: int, *, principal: RequestPrincipal = Depends(authenticate)
    ) -> ProjectDetail:
        return await service.read_project(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
        )

    router.add_api_route(
        "/{project_id}",
        read_project,
        methods=["GET"],
        response_model=ProjectDetail,
    )
    return router
