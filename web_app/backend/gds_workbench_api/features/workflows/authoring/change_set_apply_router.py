"""HTTP boundary for explicit Workflow draft application."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, Path, Request
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from .change_set_apply import ApplyWorkflowDraftRequest, ApplyWorkflowDraftResult


class WorkflowDraftApplyService(Protocol):
    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        command: ApplyWorkflowDraftRequest,
        idempotency_key: UUID,
    ) -> ApplyWorkflowDraftResult: ...


def create_workflow_draft_apply_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowDraftApplyService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/runs",
        tags=["workflow-drafts"],
    )

    async def apply_draft(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        command: ApplyWorkflowDraftRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> ApplyWorkflowDraftResult:
        return await service.apply(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{workflow_run_id}/draft/apply",
        apply_draft,
        methods=["POST"],
        response_model=ApplyWorkflowDraftResult,
    )
    return router


__all__ = [
    "WorkflowDraftApplyService",
    "create_workflow_draft_apply_router",
]
