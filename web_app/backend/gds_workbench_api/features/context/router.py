"""Authenticated reads for Project Context and its global type catalog."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.dependencies import principal_dependency

from .contracts import (
    ContextGroupDetail,
    ContextGroupFilters,
    ContextGroupPage,
    ContextRecordDetail,
    ContextRecordFilters,
    ContextRecordId,
    ContextRecordPage,
    ContextSourceSystemPage,
    ContextTypeCollection,
)
from .service import ContextService


class ContextSourceSystemListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


class ContextGroupListQuery(ContextGroupFilters):
    model_config = ConfigDict(extra="forbid", strict=False)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


class ContextRecordListQuery(ContextRecordFilters):
    model_config = ConfigDict(extra="forbid", strict=False)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


def create_context_router(
    *, identity_provider: IdentityProvider, service: ContextService
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/context", tags=["context"]
    )

    async def list_types(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ContextTypeCollection:
        return await service.list_types(principal, tenant_id=tenant_id, project_id=project_id)

    async def list_source_systems(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        query: Annotated[ContextSourceSystemListQuery, Query()],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ContextSourceSystemPage:
        return await service.list_source_systems(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    async def list_groups(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        query: Annotated[ContextGroupListQuery, Query()],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ContextGroupPage:
        return await service.list_groups(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            filters=ContextGroupFilters.model_validate(
                query.model_dump(exclude={"page_size", "cursor"})
            ),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    async def read_group(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        context_group_id: Annotated[int, Path(gt=0)],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ContextGroupDetail:
        return await service.read_group(
            principal, tenant_id=tenant_id, project_id=project_id, context_group_id=context_group_id
        )

    async def list_records(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        query: Annotated[ContextRecordListQuery, Query()],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ContextRecordPage:
        return await service.list_records(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            filters=ContextRecordFilters.model_validate(
                query.model_dump(exclude={"page_size", "cursor"})
            ),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    async def read_record(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        context_record_id: ContextRecordId,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ContextRecordDetail:
        return await service.read_record(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            context_record_id=context_record_id,
        )

    router.add_api_route(
        "/types", list_types, methods=["GET"], response_model=ContextTypeCollection
    )
    router.add_api_route(
        "/source-systems",
        list_source_systems,
        methods=["GET"],
        response_model=ContextSourceSystemPage,
    )
    router.add_api_route("/groups", list_groups, methods=["GET"], response_model=ContextGroupPage)
    router.add_api_route(
        "/groups/{context_group_id}", read_group, methods=["GET"], response_model=ContextGroupDetail
    )
    router.add_api_route(
        "/records", list_records, methods=["GET"], response_model=ContextRecordPage
    )
    router.add_api_route(
        "/records/{context_record_id}",
        read_record,
        methods=["GET"],
        response_model=ContextRecordDetail,
    )
    return router
