"""Explicit Validation Workflow Run execution route."""

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Path, Response, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)


class ExecuteValidationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_project_revision: int = Field(gt=0)


class ValidationWorkflowService(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
    ) -> AgentWorkflowRunStart: ...


def create_validation_workflow_router(
    *,
    identity_provider: IdentityProvider,
    service: ValidationWorkflowService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/validation/runs",
        tags=["validation"],
    )

    async def execute_run(
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        command: ExecuteValidationRunRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> AgentWorkflowRunStart:
        result = await service.start(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            expected_project_revision=command.expected_project_revision,
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


__all__ = [
    "ExecuteValidationRunRequest",
    "ValidationWorkflowService",
    "create_validation_workflow_router",
]
