"""Tenant-owned Mapping review HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.mapping.read_contracts import (
    MappingAttributeDetail,
    MappingAttributeFilters,
    MappingAttributeListQuery,
    MappingAttributePage,
    MappingEntityType,
    MappingFilters,
    MappingGenerationPage,
    MappingListQuery,
    MappingObjectDetail,
    MappingObjectPage,
)
from gds_workbench_api.features.mapping.read_service import MappingReviewService
from gds_workbench_api.features.metadata.workbook import XLSX_MEDIA_TYPE


class MappingExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_model_revision: int = Field(gt=0)
    entity_type: MappingEntityType
    source_system_code: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")


def create_mapping_review_router(
    *,
    identity_provider: IdentityProvider,
    service: MappingReviewService,
) -> APIRouter:
    """Create the Mapping read router for later runtime composition."""
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/mapping",
        tags=["mapping"],
    )

    async def export_workbook(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        command: MappingExportRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        result = await service.export_workbook(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            entity_type=command.entity_type,
            source_system_code=command.source_system_code,
            expected_model_revision=command.expected_model_revision,
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

    router.add_api_route("/export", export_workbook, methods=["POST"])

    async def list_generation_targets(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        entity_type: Annotated[MappingEntityType, Query()],
        page_size: Annotated[int, Query(ge=1, le=200)] = 200,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingGenerationPage:
        return await service.list_generation_targets(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            entity_type=entity_type,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "/generation-targets",
        list_generation_targets,
        methods=["GET"],
        response_model=MappingGenerationPage,
    )

    async def list_objects(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[MappingListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingObjectPage:
        filters = MappingFilters.model_validate(
            {
                "entity_type": query.entity_type,
                "source_system_id": query.source_system_id,
                "source_system_code": query.source_system_code,
                "status": query.status,
                "locked": query.locked,
            },
            strict=True,
        )
        return await service.list_objects(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/objects",
        list_objects,
        methods=["GET"],
        response_model=MappingObjectPage,
    )

    async def read_object(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        mapping_object_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingObjectDetail:
        return await service.read_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            mapping_object_id=mapping_object_id,
        )

    router.add_api_route(
        "/objects/{mapping_object_id}",
        read_object,
        methods=["GET"],
        response_model=MappingObjectDetail,
    )

    async def list_attributes(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[MappingAttributeListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingAttributePage:
        filters = MappingAttributeFilters.model_validate(
            {
                "mapping_object_id": query.mapping_object_id,
                "entity_type": query.entity_type,
                "source_system_id": query.source_system_id,
                "source_system_code": query.source_system_code,
                "status": query.status,
                "locked": query.locked,
            },
            strict=True,
        )
        return await service.list_attributes(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/attributes",
        list_attributes,
        methods=["GET"],
        response_model=MappingAttributePage,
    )

    async def read_attribute(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        mapping_attribute_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingAttributeDetail:
        return await service.read_attribute(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            mapping_attribute_id=mapping_attribute_id,
        )

    router.add_api_route(
        "/attributes/{mapping_attribute_id}",
        read_attribute,
        methods=["GET"],
        response_model=MappingAttributeDetail,
    )
    return router
