"""Active Model Input Scope read HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.model_input_scope.contracts import (
    ModelInputScopeCandidatePage,
    ModelInputScopeDetail,
    ModelInputScopePage,
    ModelInputScopeQuery,
    ScopeSearchOptions,
)
from gds_workbench_api.features.model_input_scope.service import ModelInputScopeService


def create_input_scope_router(
    *,
    identity_provider: IdentityProvider,
    service: ModelInputScopeService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/input-scope",
        tags=["model-input-scope"],
    )

    async def list_input_scope(
        tenant_id: int,
        model_id: int,
        zone: Annotated[str | None, Query(max_length=30)] = None,
        system_code: Annotated[str | None, Query(max_length=100)] = None,
        source_tenant_code: Annotated[str | None, Query(max_length=100)] = None,
        object_name: Annotated[str | None, Query(max_length=400)] = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelInputScopePage:
        query = ModelInputScopeQuery.model_validate(
            {
                "zone": zone,
                "system_code": system_code,
                "source_tenant_code": source_tenant_code,
                "object_name": object_name,
                "page_size": page_size,
                "cursor": cursor,
            }
        )
        return await service.list_input_scope(
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
        list_input_scope,
        methods=["GET"],
        response_model=ModelInputScopePage,
    )

    async def search_options(
        tenant_id: int, model_id: int, *, principal: RequestPrincipal = Depends(authenticate)
    ) -> ScopeSearchOptions:
        return await service.search_options(principal, tenant_id=tenant_id, model_id=model_id)

    router.add_api_route(
        "/options", search_options, methods=["GET"], response_model=ScopeSearchOptions
    )

    async def list_candidates(
        tenant_id: int,
        model_id: int,
        placement_tenant_id: Annotated[int | None, Query(gt=0)] = None,
        zone: Annotated[str | None, Query(max_length=30)] = None,
        system_code: Annotated[str | None, Query(max_length=100)] = None,
        source_tenant_code: Annotated[str | None, Query(max_length=100)] = None,
        object_name: Annotated[str | None, Query(max_length=400)] = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelInputScopeCandidatePage:
        query = ModelInputScopeQuery.model_validate(
            {
                "zone": zone,
                "system_code": system_code,
                "source_tenant_code": source_tenant_code,
                "object_name": object_name,
                "page_size": page_size,
                "cursor": cursor,
            }
        )
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
            placement_tenant_id=placement_tenant_id,
        )

    router.add_api_route(
        "/candidates",
        list_candidates,
        methods=["GET"],
        response_model=ModelInputScopeCandidatePage,
    )

    async def read_input_scope_object(
        tenant_id: int,
        model_id: int,
        object_id: int,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelInputScopeDetail:
        return await service.read_input_scope_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            object_id=object_id,
        )

    router.add_api_route(
        "/{object_id}",
        read_input_scope_object,
        methods=["GET"],
        response_model=ModelInputScopeDetail,
    )
    return router
