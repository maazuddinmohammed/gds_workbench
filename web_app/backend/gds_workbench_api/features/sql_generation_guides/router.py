"""Tenant-scoped SQL Generation Guide HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.sql_generation_guides.contracts import (
    SaveSqlGenerationGuideDraftRequest,
    SqlGenerationGuideDetail,
    SqlGenerationGuidePage,
    SqlGenerationGuideVersionState,
)
from gds_workbench_api.features.sql_generation_guides.service import (
    SqlGenerationGuideService,
)


def create_sql_generation_guides_router(
    *,
    identity_provider: IdentityProvider,
    service: SqlGenerationGuideService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/sql-generation-guides",
        tags=["sql-generation-guides"],
    )
    tenant_path = Path(gt=0)
    id_path = Path(gt=0)

    async def list_guides(
        tenant_id: Annotated[int, tenant_path],
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SqlGenerationGuidePage:
        return await service.list_guides(
            principal,
            tenant_id=tenant_id,
            page_size=page_size,
            cursor=cursor,
        )

    async def read_guide(
        tenant_id: Annotated[int, tenant_path],
        sql_generation_guide_id: Annotated[int, id_path],
        history_page_size: Annotated[int, Query(ge=1, le=200)] = 20,
        history_cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SqlGenerationGuideDetail:
        return await service.read_guide(
            principal,
            tenant_id=tenant_id,
            sql_generation_guide_id=sql_generation_guide_id,
            history_page_size=history_page_size,
            history_cursor=history_cursor,
        )

    async def save_draft(
        tenant_id: Annotated[int, tenant_path],
        sql_generation_guide_id: Annotated[int, id_path],
        body: SaveSqlGenerationGuideDraftRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SqlGenerationGuideVersionState:
        return await service.save_draft(
            principal,
            tenant_id=tenant_id,
            sql_generation_guide_id=sql_generation_guide_id,
            body=body,
        )

    async def publish_version(
        tenant_id: Annotated[int, tenant_path],
        sql_generation_guide_id: Annotated[int, id_path],
        sql_generation_guide_version_id: Annotated[int, id_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SqlGenerationGuideVersionState:
        return await service.publish_version(
            principal,
            tenant_id=tenant_id,
            sql_generation_guide_id=sql_generation_guide_id,
            sql_generation_guide_version_id=sql_generation_guide_version_id,
        )

    async def retire_version(
        tenant_id: Annotated[int, tenant_path],
        sql_generation_guide_id: Annotated[int, id_path],
        sql_generation_guide_version_id: Annotated[int, id_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SqlGenerationGuideVersionState:
        return await service.retire_version(
            principal,
            tenant_id=tenant_id,
            sql_generation_guide_id=sql_generation_guide_id,
            sql_generation_guide_version_id=sql_generation_guide_version_id,
        )

    router.add_api_route(
        "",
        list_guides,
        methods=["GET"],
        response_model=SqlGenerationGuidePage,
    )
    router.add_api_route(
        "/{sql_generation_guide_id}",
        read_guide,
        methods=["GET"],
        response_model=SqlGenerationGuideDetail,
    )
    router.add_api_route(
        "/{sql_generation_guide_id}/draft",
        save_draft,
        methods=["PUT"],
        response_model=SqlGenerationGuideVersionState,
    )
    router.add_api_route(
        "/{sql_generation_guide_id}/versions/{sql_generation_guide_version_id}/publish",
        publish_version,
        methods=["POST"],
        response_model=SqlGenerationGuideVersionState,
    )
    router.add_api_route(
        "/{sql_generation_guide_id}/versions/{sql_generation_guide_version_id}/retire",
        retire_version,
        methods=["POST"],
        response_model=SqlGenerationGuideVersionState,
    )
    return router
