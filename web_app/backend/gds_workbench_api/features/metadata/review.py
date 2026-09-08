"""Human description and lifecycle edits through one governed SQL operation."""

import re
from contextlib import AbstractAsyncContextManager
from typing import Annotated, Literal, LiteralString, Protocol, Self
from uuid import UUID

from fastapi import APIRouter, Header, Path, Request
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AttributeLockedError,
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    ObjectLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
    TenantWorkflowConflictError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

type RecordId = Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
type ReviewRevision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]


class MetadataReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_id: RecordId
    expected_revision: ReviewRevision
    description: str | None = Field(default=None, max_length=2000, repr=False)

    @field_validator("description")
    @classmethod
    def bound_description(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value.encode("utf-8")) > 2000
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value)
        ):
            raise ValueError("Descriptions must be bounded text")
        return value


class ReviewMetadataRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_type: Literal["object", "attribute"]
    action: Literal["lock", "unlock", "deactivate", "reactivate", "describe"]
    records: list[MetadataReviewRecord] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if len({record.record_id for record in self.records}) != len(self.records):
            raise ValueError("Select each Metadata record only once")
        if any(
            ("description" in record.model_fields_set) != (self.action == "describe")
            for record in self.records
        ):
            raise ValueError("Only description edits require a description value")
        return self


class ReviewedMetadataRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_id: RecordId
    review_revision: ReviewRevision
    is_active: bool
    is_locked: bool


class ReviewMetadataRecordsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    review_event_id: RecordId
    action_count: int = Field(ge=0, le=200)
    records: list[ReviewedMetadataRecord] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        ids = [row.record_id for row in self.records]
        if ids != sorted(set(ids)) or self.action_count > len(ids):
            raise ValueError("The Metadata review result is inconsistent")
        return self


class MetadataReviewDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class MetadataReviewService(Protocol):
    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        command: ReviewMetadataRecordsRequest,
        idempotency_key: UUID,
    ) -> ReviewMetadataRecordsResult: ...


_REVIEW_SQL: LiteralString = """
SELECT denial_code, review_event_id, action_count, records
  FROM application.review_metadata_records(%s, %s, %s, %s, %s, %s, %s, %s)
"""


class DatabaseMetadataReviewService:
    def __init__(self, *, database: MetadataReviewDatabase) -> None:
        self._database = database

    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        command: ReviewMetadataRecordsRequest,
        idempotency_key: UUID,
    ) -> ReviewMetadataRecordsResult:
        if (
            principal.actor_kind is not ActorKind.HUMAN
            or principal.entra_tenant_id is None
            or principal.entra_object_id is None
        ):
            raise AuthorizationDeniedError()
        # SQL obtains the Tenant Lock before metadata-write authorization.
        # A preauthorization here would acquire SHARE then upgrade and deadlock.
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _REVIEW_SQL,
                (
                    principal.entra_tenant_id,
                    principal.entra_object_id,
                    "user",
                    tenant_id,
                    command.record_type,
                    command.action,
                    Jsonb(
                        [
                            record.model_dump(mode="json", exclude_unset=True)
                            for record in sorted(
                                command.records, key=lambda record: record.record_id
                            )
                        ]
                    ),
                    idempotency_key,
                ),
            )
            if row is None:
                raise DependencyUnavailableError()
            denial = row["denial_code"]
            if denial is not None:
                errors: dict[str, WorkbenchError] = {
                    "invalid_request": InvalidRequestError(
                        "The Metadata review selection is invalid."
                    ),
                    "authorization_denied": AuthorizationDeniedError(),
                    "tenant_not_found": TenantNotFoundError(),
                    "tenant_lock_required": TenantLockRequiredError(),
                    "tenant_locked": TenantLockRequiredError(),
                    "tenant_workflow_conflict": TenantWorkflowConflictError(),
                    "metadata_selection_conflict": WorkbenchError(
                        "metadata_selection_conflict",
                        "Some selected Metadata records are unavailable. Refresh and select again.",
                    ),
                    "metadata_revision_conflict": WorkbenchError(
                        "metadata_revision_conflict",
                        "Selected Metadata changed after it was read. Refresh and review again.",
                    ),
                    "metadata_review_conflict": WorkbenchError(
                        "metadata_review_conflict",
                        "This review request key was already used for a different action.",
                    ),
                    "object_locked": ObjectLockedError(),
                    "attribute_locked": AttributeLockedError(),
                }
                raise errors.get(denial, DependencyUnavailableError())
            try:
                result = ReviewMetadataRecordsResult.model_validate(
                    {key: row[key] for key in ("review_event_id", "action_count", "records")},
                    strict=True,
                )
            except ValidationError:
                raise DependencyUnavailableError() from None
            if {record.record_id for record in result.records} != {
                record.record_id for record in command.records
            }:
                raise DependencyUnavailableError()
            return result


def create_metadata_review_router(
    *, identity_provider: IdentityProvider, service: MetadataReviewService
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/metadata", tags=["metadata"])

    async def review_records(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
        command: ReviewMetadataRecordsRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> ReviewMetadataRecordsResult:
        principal = identity_provider.authenticate(request.headers)
        return await service.review_records(
            principal, tenant_id=tenant_id, command=command, idempotency_key=idempotency_key
        )

    router.add_api_route(
        "/review", review_records, methods=["POST"], response_model=ReviewMetadataRecordsResult
    )
    return router
