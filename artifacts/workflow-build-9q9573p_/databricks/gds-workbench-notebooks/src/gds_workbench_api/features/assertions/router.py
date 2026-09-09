"""FastAPI routes for normalized Modeling Assertion review."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from gds_etl_workbench.application.identity import IdentityProvider
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from gds_workbench_api.features.assertions.contracts import (
    ApplicableLayer,
    AssertionDocumentDetail,
    AssertionDocumentFilters,
    AssertionDocumentPage,
    AssertionRecordDetail,
    AssertionRecordFilters,
    AssertionRecordPage,
    AssertionStatus,
)
from gds_workbench_api.features.assertions.service import AssertionsService


class AssertionDocumentListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, max_length=100)
    active: bool | None = None
    name_prefix: str | None = Field(default=None, max_length=255)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("source_system_code", "name_prefix", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        return _normalize_query_text(value, info.field_name)


class AssertionRecordListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int | None = Field(default=None, gt=0)
    document_name: str | None = Field(default=None, max_length=255)
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, max_length=100)
    status: AssertionStatus | None = None
    locked: bool | None = None
    applicable_layer: ApplicableLayer | None = None
    key_prefix: str | None = Field(default=None, max_length=100)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator(
        "document_name",
        "source_system_code",
        "status",
        "applicable_layer",
        "key_prefix",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        return _normalize_query_text(value, info.field_name)


def create_assertions_router(
    *,
    identity_provider: IdentityProvider,
    service: AssertionsService,
) -> APIRouter:
    """Create the Modeling Assertion read router for runtime composition."""
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/assertions",
        tags=["assertions"],
    )

    async def list_documents(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[AssertionDocumentListQuery, Query()],
    ) -> AssertionDocumentPage:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_documents(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=AssertionDocumentFilters.model_validate(
                {
                    "source_system_id": query.source_system_id,
                    "source_system_code": query.source_system_code,
                    "active": query.active,
                    "name_prefix": query.name_prefix,
                },
                strict=True,
            ),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/documents",
        list_documents,
        methods=["GET"],
        response_model=AssertionDocumentPage,
    )

    async def read_document(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        modeling_assertion_document_id: Annotated[int, Path(gt=0)],
    ) -> AssertionDocumentDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_document(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            modeling_assertion_document_id=modeling_assertion_document_id,
        )

    router.add_api_route(
        "/documents/{modeling_assertion_document_id}",
        read_document,
        methods=["GET"],
        response_model=AssertionDocumentDetail,
    )

    async def list_records(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[AssertionRecordListQuery, Query()],
    ) -> AssertionRecordPage:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=AssertionRecordFilters.model_validate(
                {
                    "document_id": query.document_id,
                    "document_name": query.document_name,
                    "source_system_id": query.source_system_id,
                    "source_system_code": query.source_system_code,
                    "status": query.status,
                    "locked": query.locked,
                    "applicable_layer": query.applicable_layer,
                    "key_prefix": query.key_prefix,
                },
                strict=True,
            ),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/records",
        list_records,
        methods=["GET"],
        response_model=AssertionRecordPage,
    )

    async def read_record(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        modeling_assertion_record_id: Annotated[int, Path(gt=0)],
    ) -> AssertionRecordDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_record(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            modeling_assertion_record_id=modeling_assertion_record_id,
        )

    router.add_api_route(
        "/records/{modeling_assertion_record_id}",
        read_record,
        methods=["GET"],
        response_model=AssertionRecordDetail,
    )
    return router


def _normalize_query_text(value: object, field_name: str | None) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip(" ").lower()
    if not normalized:
        raise ValueError(f"{field_name or 'filter'} must be nonblank")
    return normalized
