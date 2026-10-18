"""FastAPI routes for governed Project Change Sets."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from gds_etl_workbench.application.change_sets.contracts import MAX_STAGE_CHUNKS
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.snapshots.project import ProjectDataset

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.context.authoring import (
    SaveContextGroupRequest,
    SaveContextRecordRequest,
)
from gds_workbench_api.features.project_change_sets.input_scope import AddInputScopeRequest

from .contracts import (
    ApplyProjectChangeSetResult,
    ArchiveProjectChangeSetResult,
    BeginProjectStageBatchRequest,
    BeginProjectStageBatchResult,
    CommitProjectStageBatchResult,
    CreateProjectChangeSetRequest,
    CreateProjectChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetProjectChangeSetResult,
    PreviewProjectRecordsRequest,
    PreviewProjectRecordsResult,
    ProjectRecordHistoryPage,
    PutProjectStageChunkRequest,
    PutProjectStageChunkResult,
    ReviewProjectRecordsRequest,
    ReviewProjectRecordsResult,
    StageProjectChangeSetRequest,
    StageProjectChangeSetResult,
    ValidateProjectChangeSetResult,
)
from .editor import ProjectRecordEditor, ProjectRecordEditorRequest, SaveProjectRecordRequest
from .review import ProjectReviewDataset

type PositivePathId = Annotated[int, Path(gt=0)]
type ChunkIndex = Annotated[int, Path(gt=0, le=MAX_STAGE_CHUNKS)]
type IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


class ProjectChangeSetService(Protocol):
    async def edit_record(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: ProjectRecordEditorRequest | SaveProjectRecordRequest,
        idempotency_key: UUID | None = None,
    ) -> ProjectRecordEditor | ReviewProjectRecordsResult: ...

    async def add_input_scope(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: AddInputScopeRequest,
        idempotency_key: UUID,
    ) -> ReviewProjectRecordsResult: ...

    async def save_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: SaveContextGroupRequest | SaveContextRecordRequest,
        idempotency_key: UUID,
    ) -> ReviewProjectRecordsResult: ...

    async def list_review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dataset: ProjectReviewDataset,
        expected_project_revision: int,
        page: int = 1,
        entity_type: str | None = None,
    ) -> ProjectRecordHistoryPage: ...

    async def preview_record_review(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: PreviewProjectRecordsRequest,
        page: int = 1,
    ) -> PreviewProjectRecordsResult: ...

    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: ReviewProjectRecordsRequest,
        idempotency_key: UUID,
    ) -> ReviewProjectRecordsResult: ...

    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: CreateProjectChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateProjectChangeSetResult: ...

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: StageProjectChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageProjectChangeSetResult: ...

    async def begin_stage_batch(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: BeginProjectStageBatchRequest,
        idempotency_key: UUID,
    ) -> BeginProjectStageBatchResult: ...

    async def put_stage_chunk(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        chunk_index: int,
        command: PutProjectStageChunkRequest,
        idempotency_key: UUID,
    ) -> PutProjectStageChunkResult: ...

    async def commit_stage_batch(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> CommitProjectStageBatchResult: ...

    async def get(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        dataset: ProjectDataset | None,
    ) -> GetProjectChangeSetResult: ...

    async def validate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ValidateProjectChangeSetResult: ...

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyProjectChangeSetResult: ...

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveProjectChangeSetResult: ...


def create_project_change_sets_router(
    *,
    identity_provider: IdentityProvider,
    service: ProjectChangeSetService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/change-sets",
        tags=["project-change-sets"],
    )

    async def add_input_scope(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: AddInputScopeRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ReviewProjectRecordsResult:
        return await service.add_input_scope(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/input-scope/add",
        add_input_scope,
        methods=["POST"],
        response_model=ReviewProjectRecordsResult,
    )

    async def save_context_group(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: SaveContextGroupRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ReviewProjectRecordsResult:
        return await service.save_context(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/context-groups",
        save_context_group,
        methods=["POST"],
        response_model=ReviewProjectRecordsResult,
    )

    async def save_context_record(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: SaveContextRecordRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ReviewProjectRecordsResult:
        return await service.save_context(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/context-records",
        save_context_record,
        methods=["POST"],
        response_model=ReviewProjectRecordsResult,
    )

    async def load_record_editor(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: ProjectRecordEditorRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectRecordEditor | ReviewProjectRecordsResult:
        return await service.edit_record(
            principal, tenant_id=tenant_id, project_id=project_id, command=command
        )

    async def save_record(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: SaveProjectRecordRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectRecordEditor | ReviewProjectRecordsResult:
        return await service.edit_record(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/review/editor", load_record_editor, methods=["POST"], response_model=ProjectRecordEditor
    )
    router.add_api_route(
        "/review/edit", save_record, methods=["POST"], response_model=ReviewProjectRecordsResult
    )

    async def list_review_records(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        dataset: ProjectReviewDataset,
        expected_project_revision: Annotated[int, Query(gt=0)],
        page: Annotated[int, Query(ge=1, le=250)] = 1,
        *,
        entity_type: Annotated[str | None, Query()] = None,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ProjectRecordHistoryPage:
        return await service.list_review_records(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            dataset=dataset,
            expected_project_revision=expected_project_revision,
            page=page,
            **({"entity_type": entity_type} if entity_type is not None else {}),
        )

    router.add_api_route(
        "/review/records",
        list_review_records,
        methods=["GET"],
        response_model=ProjectRecordHistoryPage,
    )

    async def preview_record_review(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: PreviewProjectRecordsRequest,
        page: Annotated[int, Query(ge=1, le=250)] = 1,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PreviewProjectRecordsResult:
        return await service.preview_record_review(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            page=page,
        )

    router.add_api_route(
        "/review/preview",
        preview_record_review,
        methods=["POST"],
        response_model=PreviewProjectRecordsResult,
    )

    async def review_records(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: ReviewProjectRecordsRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ReviewProjectRecordsResult:
        return await service.review_records(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/review",
        review_records,
        methods=["POST"],
        response_model=ReviewProjectRecordsResult,
    )

    async def create_or_resume(
        response: Response,
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        command: CreateProjectChangeSetRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> CreateProjectChangeSetResult:
        result = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    router.add_api_route(
        "",
        create_or_resume,
        methods=["POST"],
        response_model=CreateProjectChangeSetResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def stage(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        change_set_id: UUID,
        command: StageProjectChangeSetRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> StageProjectChangeSetResult:
        return await service.stage(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage",
        stage,
        methods=["PUT"],
        response_model=StageProjectChangeSetResult,
    )

    async def begin_stage_batch(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        change_set_id: UUID,
        command: BeginProjectStageBatchRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> BeginProjectStageBatchResult:
        return await service.begin_stage_batch(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage-batches",
        begin_stage_batch,
        methods=["POST"],
        response_model=BeginProjectStageBatchResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def put_stage_chunk(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        change_set_id: UUID,
        stage_batch_id: UUID,
        chunk_index: ChunkIndex,
        command: PutProjectStageChunkRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PutProjectStageChunkResult:
        return await service.put_stage_chunk(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
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
        response_model=PutProjectStageChunkResult,
    )

    async def commit_stage_batch(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        change_set_id: UUID,
        stage_batch_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: IdempotencyKey,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> CommitProjectStageBatchResult:
        return await service.commit_stage_batch(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=change_set_id,
            stage_batch_id=stage_batch_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage-batches/{stage_batch_id}/commit",
        commit_stage_batch,
        methods=["POST"],
        response_model=CommitProjectStageBatchResult,
    )

    async def get_change_set(
        tenant_id: PositivePathId,
        project_id: PositivePathId,
        change_set_id: UUID,
        dataset: Annotated[ProjectDataset | None, Query()] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> GetProjectChangeSetResult:
        return await service.get(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=change_set_id,
            dataset=dataset,
        )

    router.add_api_route(
        "/{change_set_id}",
        get_change_set,
        methods=["GET"],
        response_model=GetProjectChangeSetResult,
    )

    def add_revision_command_route(
        path: str,
        operation: str,
        response_model: type[
            ValidateProjectChangeSetResult
            | ApplyProjectChangeSetResult
            | ArchiveProjectChangeSetResult
        ],
    ) -> None:
        async def command_route(
            tenant_id: PositivePathId,
            project_id: PositivePathId,
            change_set_id: UUID,
            command: ExpectedDraftRevisionRequest,
            idempotency_key: IdempotencyKey,
            *,
            principal: RequestPrincipal = Depends(authenticate),
        ) -> object:
            method = getattr(service, operation)
            return await method(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
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
        ValidateProjectChangeSetResult,
    )
    add_revision_command_route(
        "/{change_set_id}/apply",
        "apply",
        ApplyProjectChangeSetResult,
    )
    add_revision_command_route(
        "/{change_set_id}/archive",
        "archive",
        ArchiveProjectChangeSetResult,
    )
    return router
