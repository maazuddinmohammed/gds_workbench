"""Active Model Scope read HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from gds_etl_workbench.adapters.auth.identity import IdentityProvider

from gds_workbench_api.features.model_scope.contracts import (
    ModelScopeCandidatePage,
    ModelScopeDetail,
    ModelScopePage,
    ModelScopeQuery,
)
from gds_workbench_api.features.model_scope.service import ModelScopeService


def create_scope_router(
    *,
    identity_provider: IdentityProvider,
    service: ModelScopeService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/scope",
        tags=["model-scope"],
    )

    async def list_scope(
        request: Request,
        tenant_id: int,
        model_id: int,
        zone: Annotated[str | None, Query(max_length=30)] = None,
        system_code: Annotated[str | None, Query(max_length=100)] = None,
        source_tenant_code: Annotated[str | None, Query(max_length=100)] = None,
        object_name: Annotated[str | None, Query(max_length=400)] = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> ModelScopePage:
        query = ModelScopeQuery.model_validate(
            {
                "zone": zone,
                "system_code": system_code,
                "source_tenant_code": source_tenant_code,
                "object_name": object_name,
                "page_size": page_size,
                "cursor": cursor,
            }
        )
        principal = identity_provider.authenticate(request.headers)
        return await service.list_scope(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            zone_code=query.zone,
            system_code=query.system_code,
            source_tenant_code=query.source_tenant_code,
            object_name=query.object_name,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "",
        list_scope,
        methods=["GET"],
        response_model=ModelScopePage,
    )

    async def list_candidates(
        request: Request,
        tenant_id: int,
        model_id: int,
        zone: Annotated[str | None, Query(max_length=30)] = None,
        system_code: Annotated[str | None, Query(max_length=100)] = None,
        source_tenant_code: Annotated[str | None, Query(max_length=100)] = None,
        object_name: Annotated[str | None, Query(max_length=400)] = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> ModelScopeCandidatePage:
        query = ModelScopeQuery.model_validate(
            {
                "zone": zone,
                "system_code": system_code,
                "source_tenant_code": source_tenant_code,
                "object_name": object_name,
                "page_size": page_size,
                "cursor": cursor,
            }
        )
        principal = identity_provider.authenticate(request.headers)
        return await service.list_candidates(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            zone_code=query.zone,
            system_code=query.system_code,
            source_tenant_code=query.source_tenant_code,
            object_name=query.object_name,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/candidates",
        list_candidates,
        methods=["GET"],
        response_model=ModelScopeCandidatePage,
    )

    async def read_scope_object(
        request: Request,
        tenant_id: int,
        model_id: int,
        object_id: int,
    ) -> ModelScopeDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_scope_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            object_id=object_id,
        )

    router.add_api_route(
        "/{object_id}",
        read_scope_object,
        methods=["GET"],
        response_model=ModelScopeDetail,
    )
    return router
