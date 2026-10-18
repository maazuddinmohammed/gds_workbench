"""Governed Workflow Run creation and cancellation HTTP route."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Response, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.workflows.commands.contracts import (
    CreateWorkflowRunRequest,
    WorkflowRunCancellationResult,
    WorkflowRunCommandResult,
)
from gds_workbench_api.features.workflows.commands.service import WorkflowCommandService


def create_workflow_commands_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowCommandService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/runs",
        tags=["workflow-runs"],
    )

    async def create_run(
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        command: CreateWorkflowRunRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> WorkflowRunCommandResult:
        result = await service.create_run(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=idempotency_key,
            command=command,
        )
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    router.add_api_route(
        "",
        create_run,
        methods=["POST"],
        response_model=WorkflowRunCommandResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def cancel_run(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> WorkflowRunCancellationResult:
        return await service.cancel_run(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
        )

    router.add_api_route(
        "/{workflow_run_id}/cancel",
        cancel_run,
        methods=["POST"],
        response_model=WorkflowRunCancellationResult,
    )
    return router
