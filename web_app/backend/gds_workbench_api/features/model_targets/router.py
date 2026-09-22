"""Authorized Model target export and target discovery routes."""

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Path, Query, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.metadata.contracts import MetadataWorkbookDownload
from gds_workbench_api.features.metadata.workbook import XLSX_MEDIA_TYPE

from .contracts import (
    ExportModelTargetsRequest,
    ModelTargetBindingPage,
    ModelTargetOptions,
    RegisteredTargetPage,
    TargetLayer,
)


class ModelTargetsService(Protocol):
    async def bindings(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        layer: TargetLayer,
        after: int = 0,
    ) -> ModelTargetBindingPage: ...
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
    async def targets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        layer: TargetLayer,
        search: str,
        after: int,
        object_schema: str | None = None,
    ) -> RegisteredTargetPage: ...


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

    async def targets(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        layer: TargetLayer,
        search: Annotated[str, Query(max_length=200)] = "",
        after: Annotated[int, Query(ge=0)] = 0,
        object_schema: Annotated[str | None, Query(min_length=1, max_length=400)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> RegisteredTargetPage:
        return await service.targets(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            layer=layer,
            search=search,
            after=after,
            object_schema=object_schema,
        )

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

    async def bindings(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        layer: TargetLayer,
        after: Annotated[int, Query(ge=0)] = 0,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelTargetBindingPage:
        return await service.bindings(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            layer=layer,
            after=after,
        )

    router.add_api_route("/bindings", bindings, methods=["GET"])
    router.add_api_route("/options", options, methods=["GET"])
    router.add_api_route("", targets, methods=["GET"])
    router.add_api_route("/export", export, methods=["POST"])
    return router
