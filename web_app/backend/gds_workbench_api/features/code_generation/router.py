"""Explicit Code Generation Workflow Run execution route."""

from typing import Annotated, Protocol

from fastapi import APIRouter, Path, Request, Response, status
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)


class ExecuteCodeGenerationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class CodeGenerationWorkflowService(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart: ...


def create_code_generation_workflow_router(
    *,
    identity_provider: IdentityProvider,
    service: CodeGenerationWorkflowService,
) -> APIRouter:
    router = APIRouter(
        prefix=("/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/runs"),
        tags=["code-generation"],
    )

    async def execute_run(
        request: Request,
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        command: ExecuteCodeGenerationRunRequest,
    ) -> AgentWorkflowRunStart:
        principal = identity_provider.authenticate(request.headers)
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
        response_model=AgentWorkflowRunStart,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
