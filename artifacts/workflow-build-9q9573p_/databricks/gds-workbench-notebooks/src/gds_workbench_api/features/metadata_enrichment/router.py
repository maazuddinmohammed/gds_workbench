"""Start a queued enrichment Run through the governed workflow lifecycle."""

from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Path, Request, Response, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.workflows.authoring.lifecycle import AgentWorkflowRunStart


class ExecuteMetadataEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    execution_mode: Literal["one_shot"]
    expected_model_revision: int = Field(gt=0)


class MetadataEnrichmentWorkflowService(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart: ...


def create_metadata_enrichment_workflow_router(
    *, identity_provider: IdentityProvider, service: MetadataEnrichmentWorkflowService
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/metadata-enrichment/runs",
        tags=["metadata-enrichment"],
    )

    async def execute_run(
        request: Request,
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        command: ExecuteMetadataEnrichmentRequest,
    ) -> AgentWorkflowRunStart:
        result = await service.start(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=command.expected_model_revision,
        )
        response.status_code = (
            status.HTTP_202_ACCEPTED
            if result.changed and result.workflow_run_state == "running"
            else status.HTTP_200_OK
        )
        return result

    router.add_api_route(
        "/{workflow_run_id}/execute",
        execute_run,
        methods=["POST"],
        response_model=AgentWorkflowRunStart,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
