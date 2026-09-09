"""Common, bounded Workflow Run read HTTP routes."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.errors import InvalidRequestError
from starlette.responses import StreamingResponse

from gds_workbench_api.features.workflows.runs.contracts import (
    ModelWorkflow,
    RunEventCollection,
    RunState,
    WorkflowRunCollection,
    WorkflowRunDetail,
)
from gds_workbench_api.features.workflows.runs.service import WorkflowRunService


def create_workflow_runs_router(
    *,
    identity_provider: IdentityProvider,
    service: WorkflowRunService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/runs",
        tags=["workflow-runs"],
    )

    async def list_runs(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow: Annotated[ModelWorkflow | None, Query()] = None,
        run_state: Annotated[RunState | None, Query(alias="state")] = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> WorkflowRunCollection:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_runs(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow=workflow,
            run_state=run_state,
            page_size=page_size,
            cursor=cursor,
        )

    router.add_api_route(
        "",
        list_runs,
        methods=["GET"],
        response_model=WorkflowRunCollection,
    )

    async def read_run(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
    ) -> WorkflowRunDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_run(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
        )

    router.add_api_route(
        "/{workflow_run_id}",
        read_run,
        methods=["GET"],
        response_model=WorkflowRunDetail,
    )

    async def list_events(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        after_sequence: Annotated[int, Query(ge=0)] = 0,
        page_size: Annotated[int, Query(ge=1, le=200)] = 200,
    ) -> RunEventCollection:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_events(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            after_sequence=after_sequence,
            page_size=page_size,
        )

    router.add_api_route(
        "/{workflow_run_id}/events",
        list_events,
        methods=["GET"],
        response_model=RunEventCollection,
    )

    async def stream_events(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        after_sequence: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[
            str | None,
            Header(alias="Last-Event-ID", max_length=20),
        ] = None,
    ) -> StreamingResponse:
        principal = identity_provider.authenticate(request.headers)
        sequence = after_sequence
        if last_event_id is not None:
            try:
                reconnect_sequence = int(last_event_id)
            except ValueError as error:
                raise InvalidRequestError("Last-Event-ID must be a nonnegative integer.") from error
            if reconnect_sequence < 0:
                raise InvalidRequestError("Last-Event-ID must be a nonnegative integer.")
            sequence = max(sequence, reconnect_sequence)

        async def event_source():
            current_sequence = sequence
            yield "retry: 2000\n\n"
            while True:
                collection = await service.list_events(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    after_sequence=current_sequence,
                    page_size=200,
                )
                for event in collection.items:
                    current_sequence = event.sequence
                    yield (
                        f"id: {event.sequence}\n"
                        "event: run_event\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
                run = await service.read_run(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                )
                if run.workflow_run_state in {
                    "completed",
                    "completed_with_repair",
                    "failed",
                }:
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(2)

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    router.add_api_route(
        "/{workflow_run_id}/events/stream",
        stream_events,
        methods=["GET"],
        response_class=StreamingResponse,
    )
    return router
