"""Tenant-owned normalized Logical model review HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from gds_etl_workbench.adapters.auth.identity import IdentityProvider

from gds_workbench_api.features.logical.read_contracts import (
    LogicalAttributeDetail,
    LogicalAttributeFilters,
    LogicalAttributeListQuery,
    LogicalAttributePage,
    LogicalEntityDetail,
    LogicalEntityFilters,
    LogicalEntityListQuery,
    LogicalEntityPage,
    LogicalRelationshipDetail,
    LogicalRelationshipFilters,
    LogicalRelationshipListQuery,
    LogicalRelationshipPage,
    LogicalSubmodelDetail,
    LogicalSubmodelPage,
    ModeledFilters,
    ModeledListQuery,
)
from gds_workbench_api.features.logical.read_service import LogicalService


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


def _entity_filters_from_query(query: LogicalEntityListQuery) -> LogicalEntityFilters:
    return LogicalEntityFilters.model_validate(
        {
            "status": query.status,
            "locked": query.locked,
            "name_exact": query.name_exact,
            "name_prefix": query.name_prefix,
            "logical_submodel_id": query.logical_submodel_id,
        },
        strict=True,
    )


def create_logical_router(
    *,
    identity_provider: IdentityProvider,
    service: LogicalService,
) -> APIRouter:
    """Create the Logical review router for later runtime composition."""
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/logical",
        tags=["logical"],
    )

    async def list_entities(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[LogicalEntityListQuery, Query()],
    ) -> LogicalEntityPage:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_entities(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=_entity_filters_from_query(query),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/entities",
        list_entities,
        methods=["GET"],
        response_model=LogicalEntityPage,
    )

    async def read_entity(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        logical_entity_id: Annotated[int, Path(gt=0)],
    ) -> LogicalEntityDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_entity(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_entity_id=logical_entity_id,
        )

    router.add_api_route(
        "/entities/{logical_entity_id}",
        read_entity,
        methods=["GET"],
        response_model=LogicalEntityDetail,
    )

    async def list_attributes(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[LogicalAttributeListQuery, Query()],
    ) -> LogicalAttributePage:
        principal = identity_provider.authenticate(request.headers)
        filters = LogicalAttributeFilters.model_validate(
            {
                "status": query.status,
                "locked": query.locked,
                "name_exact": query.name_exact,
                "name_prefix": query.name_prefix,
                "logical_entity_id": query.logical_entity_id,
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
        response_model=LogicalAttributePage,
    )

    async def read_attribute(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        logical_attribute_id: Annotated[int, Path(gt=0)],
    ) -> LogicalAttributeDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_attribute(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_attribute_id=logical_attribute_id,
        )

    router.add_api_route(
        "/attributes/{logical_attribute_id}",
        read_attribute,
        methods=["GET"],
        response_model=LogicalAttributeDetail,
    )

    async def list_relationships(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[LogicalRelationshipListQuery, Query()],
    ) -> LogicalRelationshipPage:
        principal = identity_provider.authenticate(request.headers)
        filters = LogicalRelationshipFilters.model_validate(
            {
                "status": query.status,
                "locked": query.locked,
                "name_exact": query.name_exact,
                "name_prefix": query.name_prefix,
                "logical_entity_id": query.logical_entity_id,
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
        response_model=LogicalRelationshipPage,
    )

    async def read_relationship(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        logical_relationship_id: Annotated[int, Path(gt=0)],
    ) -> LogicalRelationshipDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_relationship(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_relationship_id=logical_relationship_id,
        )

    router.add_api_route(
        "/relationships/{logical_relationship_id}",
        read_relationship,
        methods=["GET"],
        response_model=LogicalRelationshipDetail,
    )

    async def list_submodels(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[ModeledListQuery, Query()],
    ) -> LogicalSubmodelPage:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_submodels(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=_filters_from_query(query),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/submodels",
        list_submodels,
        methods=["GET"],
        response_model=LogicalSubmodelPage,
    )

    async def read_submodel(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        logical_submodel_id: Annotated[int, Path(gt=0)],
    ) -> LogicalSubmodelDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_submodel(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_submodel_id=logical_submodel_id,
        )

    router.add_api_route(
        "/submodels/{logical_submodel_id}",
        read_submodel,
        methods=["GET"],
        response_model=LogicalSubmodelDetail,
    )
    return router
