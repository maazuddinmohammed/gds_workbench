"""FastAPI routes for governed Model Change Sets."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request, Response, status
from gds_etl_workbench.application.change_sets.contracts import MAX_STAGE_CHUNKS
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.snapshots.model import ModelDataset

from .contracts import (
    ApplyModelChangeSetResult,
    ArchiveModelChangeSetResult,
    BeginModelStageBatchRequest,
    BeginModelStageBatchResult,
    CommitModelStageBatchResult,
    CreateModelChangeSetRequest,
    CreateModelChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetModelChangeSetResult,
    PutModelStageChunkRequest,
    PutModelStageChunkResult,
    StageModelChangeSetRequest,
    StageModelChangeSetResult,
    ValidateModelChangeSetResult,
)

type PositivePathId = Annotated[int, Path(gt=0)]
type ChunkIndex = Annotated[int, Path(gt=0, le=MAX_STAGE_CHUNKS)]
type IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


class ModelChangeSetService(Protocol):
    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: CreateModelChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateModelChangeSetResult: ...

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: StageModelChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageModelChangeSetResult: ...

    async def begin_stage_batch(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: BeginModelStageBatchRequest,
        idempotency_key: UUID,
    ) -> BeginModelStageBatchResult: ...

    async def put_stage_chunk(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        chunk_index: int,
        command: PutModelStageChunkRequest,
        idempotency_key: UUID,
    ) -> PutModelStageChunkResult: ...

    async def commit_stage_batch(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> CommitModelStageBatchResult: ...

    async def get(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        dataset: ModelDataset | None,
    ) -> GetModelChangeSetResult: ...

    async def validate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ValidateModelChangeSetResult: ...

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyModelChangeSetResult: ...

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveModelChangeSetResult: ...


def create_model_change_sets_router(
    *,
    identity_provider: IdentityProvider,
    service: ModelChangeSetService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/change-sets",
        tags=["model-change-sets"],
    )

    async def create_or_resume(
        request: Request,
        response: Response,
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        command: CreateModelChangeSetRequest,
        idempotency_key: IdempotencyKey,
    ) -> CreateModelChangeSetResult:
        principal = identity_provider.authenticate(request.headers)
        result = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    router.add_api_route(
        "",
        create_or_resume,
        methods=["POST"],
        response_model=CreateModelChangeSetResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def stage(
        request: Request,
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        change_set_id: UUID,
        command: StageModelChangeSetRequest,
        idempotency_key: IdempotencyKey,
    ) -> StageModelChangeSetResult:
        return await service.stage(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage",
        stage,
        methods=["PUT"],
        response_model=StageModelChangeSetResult,
    )

    async def begin_stage_batch(
        request: Request,
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        change_set_id: UUID,
        command: BeginModelStageBatchRequest,
        idempotency_key: IdempotencyKey,
    ) -> BeginModelStageBatchResult:
        return await service.begin_stage_batch(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage-batches",
        begin_stage_batch,
        methods=["POST"],
        response_model=BeginModelStageBatchResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def put_stage_chunk(
        request: Request,
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        change_set_id: UUID,
        stage_batch_id: UUID,
        chunk_index: ChunkIndex,
        command: PutModelStageChunkRequest,
        idempotency_key: IdempotencyKey,
    ) -> PutModelStageChunkResult:
        return await service.put_stage_chunk(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=change_set_id,
            stage_batch_id=stage_batch_id,
            chunk_index=chunk_index,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage-batches/{stage_batch_id}/chunks/{chunk_index}",
        put_stage_chunk,
        methods=["PUT"],
        response_model=PutModelStageChunkResult,
    )

    async def commit_stage_batch(
        request: Request,
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        change_set_id: UUID,
        stage_batch_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> CommitModelStageBatchResult:
        return await service.commit_stage_batch(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=change_set_id,
            stage_batch_id=stage_batch_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage-batches/{stage_batch_id}/commit",
        commit_stage_batch,
        methods=["POST"],
        response_model=CommitModelStageBatchResult,
    )

    async def get_change_set(
        request: Request,
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        change_set_id: UUID,
        dataset: Annotated[ModelDataset | None, Query()] = None,
    ) -> GetModelChangeSetResult:
        return await service.get(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=change_set_id,
            dataset=dataset,
        )

    router.add_api_route(
        "/{change_set_id}",
        get_change_set,
        methods=["GET"],
        response_model=GetModelChangeSetResult,
    )

    def add_revision_command_route(
        path: str,
        operation: str,
        response_model: type[
            ValidateModelChangeSetResult | ApplyModelChangeSetResult | ArchiveModelChangeSetResult
        ],
    ) -> None:
        async def command_route(
            request: Request,
            tenant_id: PositivePathId,
            model_id: PositivePathId,
            change_set_id: UUID,
            command: ExpectedDraftRevisionRequest,
            idempotency_key: IdempotencyKey,
        ) -> object:
            method = getattr(service, operation)
            return await method(
                identity_provider.authenticate(request.headers),
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=change_set_id,
                command=command,
                idempotency_key=idempotency_key,
            )

        router.add_api_route(
            path,
            command_route,
            methods=["POST"],
            response_model=response_model,
        )

    add_revision_command_route(
        "/{change_set_id}/validate",
        "validate",
        ValidateModelChangeSetResult,
    )
    add_revision_command_route(
        "/{change_set_id}/apply",
        "apply",
        ApplyModelChangeSetResult,
    )
    add_revision_command_route(
        "/{change_set_id}/archive",
        "archive",
        ArchiveModelChangeSetResult,
    )
    return router
