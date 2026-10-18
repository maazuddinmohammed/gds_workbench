"""Authorized Project target export and target discovery routes."""

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Path, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.metadata.contracts import MetadataWorkbookDownload
from gds_workbench_api.features.metadata.workbook import XLSX_MEDIA_TYPE

from .contracts import (
    ExportProjectDdlRequest,
    ExportProjectTargetsRequest,
    ProjectTargetOptions,
)


class ProjectTargetsService(Protocol):
    async def export_ddl(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: ExportProjectDdlRequest,
    ) -> str: ...

    async def options(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> ProjectTargetOptions: ...
    async def export(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: ExportProjectTargetsRequest,
    ) -> MetadataWorkbookDownload: ...


def create_project_targets_router(
    *, identity_provider: IdentityProvider, service: ProjectTargetsService
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/project-targets",
        tags=["project-targets"],
    )

    async def options(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectTargetOptions:
        return await service.options(principal, tenant_id=tenant_id, project_id=project_id)

    async def export(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        command: ExportProjectTargetsRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        result = await service.export(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
        )
        return Response(
            content=result.content,
            media_type=XLSX_MEDIA_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    router.add_api_route("/options", options, methods=["GET"])
    router.add_api_route("/export", export, methods=["POST"])

    async def export_ddl(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        command: ExportProjectDdlRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        content = await service.export_ddl(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
        )
        filename = (
            f"gds_{command.layer}__project_{project_id}__r{command.expected_project_revision}.sql"
        )
        return Response(
            content=content,
            media_type="application/sql",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    router.add_api_route("/ddl", export_ddl, methods=["POST"])
    return router
