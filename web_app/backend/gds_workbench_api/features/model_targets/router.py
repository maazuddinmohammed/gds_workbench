"""Authorized Model target export and target discovery routes."""

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Path, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.metadata.contracts import MetadataWorkbookDownload
from gds_workbench_api.features.metadata.workbook import XLSX_MEDIA_TYPE

from .contracts import (
    ExportModelDdlRequest,
    ExportModelTargetsRequest,
    ModelTargetOptions,
)


class ModelTargetsService(Protocol):
    async def export_ddl(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: ExportModelDdlRequest,
    ) -> str: ...

    async def options(
        self, principal: RequestPrincipal, *, tenant_id: int, model_id: int
    ) -> ModelTargetOptions: ...
    async def export(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: ExportModelTargetsRequest,
    ) -> MetadataWorkbookDownload: ...


def create_model_targets_router(
    *, identity_provider: IdentityProvider, service: ModelTargetsService
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/model-targets", tags=["model-targets"]
    )

    async def options(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelTargetOptions:
        return await service.options(principal, tenant_id=tenant_id, model_id=model_id)

    async def export(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        command: ExportModelTargetsRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        result = await service.export(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
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
        model_id: Annotated[int, Path(gt=0)],
        command: ExportModelDdlRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        content = await service.export_ddl(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command,
        )
        filename = f"gds_{command.layer}__model_{model_id}__r{command.expected_model_revision}.sql"
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
