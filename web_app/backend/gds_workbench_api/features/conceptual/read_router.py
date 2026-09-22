"""Tenant-owned Conceptual Object and Relationship review HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.conceptual.read_contracts import (
    ConceptualFilters,
    ConceptualListQuery,
    ConceptualObjectDetail,
    ConceptualObjectPage,
    ConceptualRelationshipDetail,
    ConceptualRelationshipPage,
)
from gds_workbench_api.features.conceptual.read_service import ConceptualService


def create_conceptual_router(
    *,
    identity_provider: IdentityProvider,
    service: ConceptualService,
) -> APIRouter:
    """Create the Conceptual read router for later runtime composition."""
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/conceptual",
        tags=["conceptual"],
    )

    async def list_objects(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[ConceptualListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ConceptualObjectPage:
        filters = ConceptualFilters.model_validate(
            {
                "status": query.status,
                "locked": query.locked,
                "name_exact": query.name_exact,
                "name_prefix": query.name_prefix,
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
        response_model=ConceptualObjectPage,
    )

    async def read_object(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        conceptual_object_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ConceptualObjectDetail:
        return await service.read_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            conceptual_object_id=conceptual_object_id,
        )

    router.add_api_route(
        "/objects/{conceptual_object_id}",
        read_object,
        methods=["GET"],
        response_model=ConceptualObjectDetail,
    )

    async def list_relationships(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[ConceptualListQuery, Query()],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ConceptualRelationshipPage:
        filters = ConceptualFilters.model_validate(
            {
                "status": query.status,
                "locked": query.locked,
                "name_exact": query.name_exact,
                "name_prefix": query.name_prefix,
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
        response_model=ConceptualRelationshipPage,
    )

    async def read_relationship(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        conceptual_relationship_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ConceptualRelationshipDetail:
        return await service.read_relationship(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            conceptual_relationship_id=conceptual_relationship_id,
        )

    router.add_api_route(
        "/relationships/{conceptual_relationship_id}",
        read_relationship,
        methods=["GET"],
        response_model=ConceptualRelationshipDetail,
    )
    return router
