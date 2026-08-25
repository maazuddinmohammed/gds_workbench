"""Governed Workflow Run creation HTTP route."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Request, Response, status
from gds_etl_workbench.adapters.auth.identity import IdentityProvider

from gds_workbench_api.features.workflows.commands.contracts import (
    CreateWorkflowRunRequest,
    WorkflowRunCommandResult,
)
from gds_workbench_api.features.workflows.commands.service import WorkflowCommandService


def create_workflow_commands_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowCommandService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/runs",
        tags=["workflow-runs"],
    )

    async def create_run(
        request: Request,
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        command: CreateWorkflowRunRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> WorkflowRunCommandResult:
        principal = identity_provider.authenticate(request.headers)
        result = await service.create_run(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
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
    return router
