"""Tenant-owned Mapping review HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.mapping.read_contracts import (
    MappingAttributeDetail,
    MappingAttributeFilters,
    MappingAttributeListQuery,
    MappingAttributePage,
    MappingDependencyFilters,
    MappingDependencyPage,
    MappingEntityType,
    MappingGenerationPage,
    MappingListQuery,
    MappingObjectDetail,
    MappingObjectPage,
    MappingTargetPage,
)
from gds_workbench_api.features.mapping.read_service import MappingReviewService


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

    async def list_dependencies(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[MappingListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingDependencyPage:
        filters = MappingDependencyFilters.model_validate(
            {
                "entity_type": query.entity_type,
                "source_system_id": query.source_system_id,
                "source_system_code": query.source_system_code,
                "status": query.status,
                "locked": query.locked,
            },
            strict=True,
        )
        return await service.list_dependencies(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/dependencies",
        list_dependencies,
        methods=["GET"],
        response_model=MappingDependencyPage,
    )

    async def list_targets(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        entity_type: Annotated[MappingEntityType, Query()],
        page_size: Annotated[int, Query(ge=1, le=200)] = 200,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> MappingTargetPage:
        return await service.list_targets(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            entity_type=entity_type,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "/targets",
        list_targets,
        methods=["GET"],
        response_model=MappingTargetPage,
    )

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
        filters = MappingDependencyFilters.model_validate(
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
