"""Authenticated HTTP commands for Profiling Workflow Runs."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.profiling.workflow import ProfilingRunStart


class ExecuteProfilingRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class ProfilingWorkflowService(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart: ...

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> None: ...


def create_profiling_workflow_router(
    *,
    identity_provider: IdentityProvider,
    service: ProfilingWorkflowService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/profiling/runs",
        tags=["profiling"],
    )

    async def execute_run(
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        command: ExecuteProfilingRunRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProfilingRunStart:
        result = await service.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=command.expected_model_revision,
        )
        if result.changed and result.workflow_run_state == "running":
            response.status_code = status.HTTP_202_ACCEPTED
        else:
            response.status_code = status.HTTP_200_OK
        return result

    router.add_api_route(
        "/{workflow_run_id}/execute",
        execute_run,
        methods=["POST"],
        response_model=ProfilingRunStart,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
