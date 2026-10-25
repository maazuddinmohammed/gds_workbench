"""Tenant-owned Subject Area review HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.subject_areas.read_contracts import (
    ScopeTablePage,
    SubjectAreaDetail,
    SubjectAreaPage,
)
from gds_workbench_api.features.subject_areas.read_service import SubjectAreaService


def create_subject_area_router(
    *,
    identity_provider: IdentityProvider,
    service: SubjectAreaService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/subject-areas",
        tags=["subject-areas"],
    )

    async def list_subject_areas(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SubjectAreaPage:
        return await service.list_subject_areas(
            principal, tenant_id=tenant_id, project_id=project_id
        )

    async def list_scope_tables(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ScopeTablePage:
        return await service.list_scope_tables(
            principal, tenant_id=tenant_id, project_id=project_id
        )

    async def read_subject_area(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        subject_area_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> SubjectAreaDetail:
        return await service.read_subject_area(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            subject_area_id=subject_area_id,
        )

    router.add_api_route("", list_subject_areas, methods=["GET"], response_model=SubjectAreaPage)
    router.add_api_route(
        "/tables", list_scope_tables, methods=["GET"], response_model=ScopeTablePage
    )
    router.add_api_route(
        "/{subject_area_id}",
        read_subject_area,
        methods=["GET"],
        response_model=SubjectAreaDetail,
    )
    return router


__all__ = ["create_subject_area_router"]
