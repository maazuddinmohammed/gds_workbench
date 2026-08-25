"""HTTP router for profiled Object review."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from gds_etl_workbench.adapters.auth.identity import IdentityProvider

from gds_workbench_api.features.profiling.read_contracts import (
    ProfilingObjectDetail,
    ProfilingObjectFilters,
    ProfilingObjectPage,
)
from gds_workbench_api.features.profiling.read_service import ProfilingReviewService


def create_profiling_router(
    *,
    identity_provider: IdentityProvider,
    service: ProfilingReviewService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}",
        tags=["profiling"],
    )

    async def list_profiling_objects(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        object_id: Annotated[int | None, Query(gt=0)] = None,
        source_tenant_code: Annotated[str | None, Query(max_length=100)] = None,
        system_code: Annotated[str | None, Query(max_length=100)] = None,
        object_schema: Annotated[str | None, Query(max_length=400)] = None,
        object_name: Annotated[str | None, Query(max_length=400)] = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> ProfilingObjectPage:
        filters = ProfilingObjectFilters(
            object_id=object_id,
            source_tenant_code=source_tenant_code,
            system_code=system_code,
            object_schema=object_schema,
            object_name=object_name,
        )
        principal = identity_provider.authenticate(request.headers)
        return await service.list_profiling_objects(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "/profiling",
        list_profiling_objects,
        methods=["GET"],
        response_model=ProfilingObjectPage,
    )

    async def read_profiling_object(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        object_id: Annotated[int, Path(gt=0)],
    ) -> ProfilingObjectDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_profiling_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            object_id=object_id,
        )

    router.add_api_route(
        "/profiling/{object_id}",
        read_profiling_object,
        methods=["GET"],
        response_model=ProfilingObjectDetail,
    )

    return router
