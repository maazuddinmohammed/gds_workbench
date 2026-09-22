"""Tenant-owned normalized Dimensional model review HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.dimensional.read_contracts import (
    DimensionalAttributeDetail,
    DimensionalAttributeFilters,
    DimensionalAttributeListQuery,
    DimensionalAttributePage,
    DimensionalObjectDetail,
    DimensionalObjectPage,
    DimensionalRelationshipDetail,
    DimensionalRelationshipFilters,
    DimensionalRelationshipListQuery,
    DimensionalRelationshipPage,
)
from gds_workbench_api.features.dimensional.read_service import DimensionalService
from gds_workbench_api.features.logical import ModeledFilters, ModeledListQuery


def _filters_from_query(query: ModeledListQuery) -> ModeledFilters:
    return ModeledFilters.model_validate(
        {
            "status": query.status,
            "locked": query.locked,
            "name_exact": query.name_exact,
            "name_prefix": query.name_prefix,
        },
        strict=True,
    )


def create_dimensional_router(
    *,
    identity_provider: IdentityProvider,
    service: DimensionalService,
) -> APIRouter:
    """Create the Dimensional review router for later runtime composition."""
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/dimensional",
        tags=["dimensional"],
    )

    async def list_objects(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[ModeledListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> DimensionalObjectPage:
        return await service.list_objects(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=_filters_from_query(query),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/objects",
        list_objects,
        methods=["GET"],
        response_model=DimensionalObjectPage,
    )

    async def read_object(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        dimensional_entity_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> DimensionalObjectDetail:
        return await service.read_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dimensional_entity_id=dimensional_entity_id,
        )

    router.add_api_route(
        "/objects/{dimensional_entity_id}",
        read_object,
        methods=["GET"],
        response_model=DimensionalObjectDetail,
    )

    async def list_attributes(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[DimensionalAttributeListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> DimensionalAttributePage:
        filters = DimensionalAttributeFilters.model_validate(
            {
                "status": query.status,
                "locked": query.locked,
                "name_exact": query.name_exact,
                "name_prefix": query.name_prefix,
                "dimensional_entity_id": query.dimensional_entity_id,
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
        response_model=DimensionalAttributePage,
    )

    async def read_attribute(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        dimensional_attribute_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> DimensionalAttributeDetail:
        return await service.read_attribute(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dimensional_attribute_id=dimensional_attribute_id,
        )

    router.add_api_route(
        "/attributes/{dimensional_attribute_id}",
        read_attribute,
        methods=["GET"],
        response_model=DimensionalAttributeDetail,
    )

    async def list_relationships(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[DimensionalRelationshipListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> DimensionalRelationshipPage:
        filters = DimensionalRelationshipFilters.model_validate(
            {
                "status": query.status,
                "locked": query.locked,
                "name_exact": query.name_exact,
                "name_prefix": query.name_prefix,
                "dimensional_entity_id": query.dimensional_entity_id,
            },
            strict=True,
        )
        return await service.list_relationships(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/relationships",
        list_relationships,
        methods=["GET"],
        response_model=DimensionalRelationshipPage,
    )

    async def read_relationship(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        dimensional_relationship_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> DimensionalRelationshipDetail:
        return await service.read_relationship(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dimensional_relationship_id=dimensional_relationship_id,
        )

    router.add_api_route(
        "/relationships/{dimensional_relationship_id}",
        read_relationship,
        methods=["GET"],
        response_model=DimensionalRelationshipDetail,
    )
    return router
