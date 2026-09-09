"""FastAPI routes for governed Tenant Metadata Change Sets."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request, Response, status
from gds_etl_workbench.application.change_sets.metadata import ChangeSetDataset
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError

from gds_workbench_api.features.metadata.workbook import MAX_XLSX_BYTES, XLSX_MEDIA_TYPE

from .contracts import (
    ApplyMetadataChangeSetResult,
    ArchiveMetadataChangeSetResult,
    CreateMetadataChangeSetRequest,
    CreateMetadataChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetMetadataChangeSetResult,
    ImportMetadataWorkbookResult,
    StageMetadataChangeSetRequest,
    StageMetadataChangeSetResult,
    ValidateMetadataChangeSetResult,
)

type PositiveTenantId = Annotated[int, Path(gt=0)]
type IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]
type ExpectedDraftRevision = Annotated[int, Header(alias="If-Match", gt=0)]


class MetadataChangeSetService(Protocol):
    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        command: CreateMetadataChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateMetadataChangeSetResult: ...

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: StageMetadataChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageMetadataChangeSetResult: ...

    async def get(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        dataset: ChangeSetDataset | None,
    ) -> GetMetadataChangeSetResult: ...

    async def validate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
    ) -> ValidateMetadataChangeSetResult: ...

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyMetadataChangeSetResult: ...

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveMetadataChangeSetResult: ...

    async def import_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        expected_draft_revision: int,
        content: bytes,
        idempotency_key: UUID,
    ) -> ImportMetadataWorkbookResult: ...


def create_metadata_change_sets_router(
    *,
    identity_provider: IdentityProvider,
    service: MetadataChangeSetService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/metadata-change-sets",
        tags=["metadata-change-sets"],
    )

    async def create_or_resume(
        request: Request,
        response: Response,
        tenant_id: PositiveTenantId,
        command: CreateMetadataChangeSetRequest,
        idempotency_key: IdempotencyKey,
    ) -> CreateMetadataChangeSetResult:
        result = await service.create_or_resume(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    router.add_api_route(
        "",
        create_or_resume,
        methods=["POST"],
        response_model=CreateMetadataChangeSetResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def stage(
        request: Request,
        tenant_id: PositiveTenantId,
        change_set_id: UUID,
        command: StageMetadataChangeSetRequest,
        idempotency_key: IdempotencyKey,
    ) -> StageMetadataChangeSetResult:
        return await service.stage(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/stage",
        stage,
        methods=["PUT"],
        response_model=StageMetadataChangeSetResult,
    )

    async def get_change_set(
        request: Request,
        tenant_id: PositiveTenantId,
        change_set_id: UUID,
        dataset: Annotated[ChangeSetDataset | None, Query()] = None,
    ) -> GetMetadataChangeSetResult:
        return await service.get(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            dataset=dataset,
        )

    router.add_api_route(
        "/{change_set_id}",
        get_change_set,
        methods=["GET"],
        response_model=GetMetadataChangeSetResult,
    )

    async def validate(
        request: Request,
        tenant_id: PositiveTenantId,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
    ) -> ValidateMetadataChangeSetResult:
        return await service.validate(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            command=command,
        )

    router.add_api_route(
        "/{change_set_id}/validate",
        validate,
        methods=["POST"],
        response_model=ValidateMetadataChangeSetResult,
    )

    async def apply(
        request: Request,
        tenant_id: PositiveTenantId,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ApplyMetadataChangeSetResult:
        return await service.apply(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/apply",
        apply,
        methods=["POST"],
        response_model=ApplyMetadataChangeSetResult,
    )

    async def archive(
        request: Request,
        tenant_id: PositiveTenantId,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ArchiveMetadataChangeSetResult:
        return await service.archive(
            identity_provider.authenticate(request.headers),
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/archive",
        archive,
        methods=["POST"],
        response_model=ArchiveMetadataChangeSetResult,
    )

    async def import_workbook(
        request: Request,
        tenant_id: PositiveTenantId,
        change_set_id: UUID,
        expected_draft_revision: ExpectedDraftRevision,
        idempotency_key: IdempotencyKey,
    ) -> ImportMetadataWorkbookResult:
        principal = identity_provider.authenticate(request.headers)
        if request.headers.get("content-type", "").strip().lower() != XLSX_MEDIA_TYPE:
            raise InvalidRequestError("XLSX Content-Type is invalid.")
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_XLSX_BYTES:
                raise InvalidRequestError("XLSX package size is invalid.")
            content.extend(chunk)
        return await service.import_workbook(
            principal,
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            expected_draft_revision=expected_draft_revision,
            content=bytes(content),
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/{change_set_id}/imports/xlsx",
        import_workbook,
        methods=["POST"],
        response_model=ImportMetadataWorkbookResult,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    return router


__all__ = ["MetadataChangeSetService", "create_metadata_change_sets_router"]
