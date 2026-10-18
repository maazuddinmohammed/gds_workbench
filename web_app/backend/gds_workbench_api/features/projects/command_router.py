"""Governed complete-Project command HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.projects.command_contracts import (
    ArchiveProjectRequest,
    CompleteProjectRequest,
    ProjectCommandResult,
    SetProjectLockRequest,
    UpdateProjectRequest,
)
from gds_workbench_api.features.projects.command_service import ProjectCommandService

type PositivePathId = Annotated[int, Path(gt=0)]


def create_project_commands_router(
    *,
    identity_provider: IdentityProvider,
    service: ProjectCommandService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/projects", tags=["projects"])

    async def set_project_lock(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: SetProjectLockRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectCommandResult:
        return await service.set_project_lock(
            principal, tenant_id=tenant_id, project_id=project_id, request=command
        )

    router.add_api_route(
        "/{project_id}/lock", set_project_lock, methods=["PUT"], response_model=ProjectCommandResult
    )

    async def create_project(
        tenant_id: PositivePathId,
        command: CompleteProjectRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectCommandResult:
        return await service.create_project(
            principal,
            tenant_id=tenant_id,
            request=command,
        )

    router.add_api_route(
        "",
        create_project,
        methods=["POST"],
        response_model=ProjectCommandResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def update_project(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: UpdateProjectRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectCommandResult:
        return await service.update_project(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            request=command,
        )

    router.add_api_route(
        "/{project_id}",
        update_project,
        methods=["PUT"],
        response_model=ProjectCommandResult,
    )

    async def archive_project(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: ArchiveProjectRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectCommandResult:
        return await service.archive_project(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            request=command,
        )

    router.add_api_route(
        "/{project_id}/archive",
        archive_project,
        methods=["POST"],
        response_model=ProjectCommandResult,
    )

    return router
