"""Read physical enrichment outcomes through the existing Run identity route."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from gds_etl_workbench.application.identity import IdentityProvider

from .read_contracts import MetadataEnrichmentResultPage
from .read_service import MetadataEnrichmentReadService


def create_metadata_enrichment_read_router(
    *, identity_provider: IdentityProvider, service: MetadataEnrichmentReadService
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/runs",
        tags=["metadata-enrichment"],
    )

    async def read_results(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        offset: Annotated[int, Query(ge=0, le=10_200)] = 0,
    ) -> MetadataEnrichmentResultPage:
        return await service.read_results(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            limit=limit,
            offset=offset,
        )

    router.add_api_route(
        "/{workflow_run_id}/metadata-enrichment",
        read_results,
        methods=["GET"],
        response_model=MetadataEnrichmentResultPage,
    )
    return router
