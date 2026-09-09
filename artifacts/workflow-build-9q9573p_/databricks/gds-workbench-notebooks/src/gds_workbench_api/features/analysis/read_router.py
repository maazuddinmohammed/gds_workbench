"""HTTP router for Analysis finding review."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from gds_etl_workbench.application.identity import IdentityProvider

from gds_workbench_api.features.analysis.read_contracts import (
    AnalysisFindingDetail,
    AnalysisFindingFilters,
    AnalysisFindingPage,
)
from gds_workbench_api.features.analysis.read_service import AnalysisReviewService


def create_analysis_review_router(
    *,
    identity_provider: IdentityProvider,
    service: AnalysisReviewService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}",
        tags=["analysis"],
    )

    async def list_analysis_findings(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        object_id: Annotated[int | None, Query(gt=0)] = None,
        from_object_id: Annotated[int | None, Query(gt=0)] = None,
        to_object_id: Annotated[int | None, Query(gt=0)] = None,
        validation_state: Annotated[str | None, Query(max_length=20)] = None,
        status: Annotated[str | None, Query(max_length=20)] = None,
        locked: Annotated[bool | None, Query()] = None,
        show_inactive: Annotated[bool, Query()] = False,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> AnalysisFindingPage:
        filters = AnalysisFindingFilters.model_validate(
            {
                "object_id": object_id,
                "from_object_id": from_object_id,
                "to_object_id": to_object_id,
                "validation_state": validation_state,
                "status": status,
                "locked": locked,
                "show_inactive": show_inactive,
            }
        )
        principal = identity_provider.authenticate(request.headers)
        return await service.list_analysis_findings(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "/analysis",
        list_analysis_findings,
        methods=["GET"],
        response_model=AnalysisFindingPage,
    )

    async def read_analysis_finding(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        analysis_result_id: Annotated[int, Path(gt=0)],
    ) -> AnalysisFindingDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_analysis_finding(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            analysis_result_id=analysis_result_id,
        )

    router.add_api_route(
        "/analysis/{analysis_result_id}",
        read_analysis_finding,
        methods=["GET"],
        response_model=AnalysisFindingDetail,
    )

    return router
