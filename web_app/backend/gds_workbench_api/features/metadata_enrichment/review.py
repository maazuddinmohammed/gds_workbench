"""Human edits of Model enrichment, with revision fencing and durable replay."""

from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockRequiredError,
    WorkbenchError,
)
from psycopg import Error
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.metadata.review import (
    MetadataReviewDatabase,
    MetadataReviewRecord,
    ReviewMetadataRecordsResult,
)
from gds_workbench_api.features.models import ModelNotFoundError
from gds_workbench_api.features.workflows.authoring.lifecycle import raise_workflow_lifecycle_error


class EnrichmentReviewRecord(MetadataReviewRecord):
    attribute_inferred_data_type: str | None = Field(default=None, max_length=100)
    is_natural_key: bool | None = None
    is_primary_key: bool | None = None
    is_nullable: bool | None = None
    is_pii: bool | None = None


class ReviewEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    expected_model_revision: int = Field(gt=0)
    record_type: Literal["object", "attribute"]
    action: Literal["edit", "lock", "unlock"]
    records: list[EnrichmentReviewRecord] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_records(self) -> Self:
        fields = {"record_id", "expected_revision"}
        if self.action == "edit":
            fields.add("description")
            if self.record_type == "attribute":
                fields.update(
                    (
                        "attribute_inferred_data_type",
                        "is_natural_key",
                        "is_primary_key",
                        "is_nullable",
                        "is_pii",
                    )
                )
        if len({record.record_id for record in self.records}) != len(self.records) or any(
            record.model_fields_set != fields for record in self.records
        ):
            raise ValueError("Provide exactly the selected enrichment fields once per record")
        return self


class DatabaseEnrichmentReviewService:
    def __init__(self, *, database: MetadataReviewDatabase) -> None:
        self._database = database

    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: ReviewEnrichmentRequest,
        idempotency_key: UUID,
    ) -> ReviewMetadataRecordsResult:
        if (
            principal.actor_kind is not ActorKind.HUMAN
            or principal.entra_tenant_id is None
            or principal.entra_object_id is None
        ):
            raise AuthorizationDeniedError()
        async with self._database.write_transaction() as transaction:
            try:
                row = await transaction.fetch_one(
                    "SELECT application.review_model_enrichment("
                    "%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result",
                    (
                        principal.entra_tenant_id,
                        principal.entra_object_id,
                        tenant_id,
                        model_id,
                        command.expected_model_revision,
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
            except Error as error:
                message = error.diag.message_primary
                if message == "enrichment_invalid_review":
                    raise InvalidRequestError("The enrichment edit is invalid.") from None
                if message in (
                    "enrichment_revision_conflict",
                    "enrichment_selection_conflict",
                    "enrichment_review_conflict",
                    "enrichment_locked",
                    "object_locked",
                ):
                    raise WorkbenchError(
                        "metadata_revision_conflict",
                        "Enrichment changed or is locked. Refresh and review before saving.",
                    ) from None
                if message in ("authorization_denied", "principal_not_found", "principal_inactive"):
                    raise AuthorizationDeniedError() from None
                if message == "model_not_found":
                    raise ModelNotFoundError() from None
                if message in ("tenant_locked", "tenant_lock_required"):
                    raise TenantLockRequiredError() from None
                raise_workflow_lifecycle_error(error)
        if row is None:
            raise DependencyUnavailableError()
        result = ReviewMetadataRecordsResult.model_validate(row["result"])
        if {record.record_id for record in result.records} != {
            record.record_id for record in command.records
        }:
            raise DependencyUnavailableError()
        return result


def create_enrichment_review_router(
    *,
    identity_provider: IdentityProvider,
    service: DatabaseEnrichmentReviewService,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/metadata-enrichment")
    authenticate = principal_dependency(identity_provider)

    async def review_records(
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        command: ReviewEnrichmentRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ReviewMetadataRecordsResult:
        return await service.review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    router.add_api_route(
        "/review", review_records, methods=["POST"], response_model=ReviewMetadataRecordsResult
    )

    return router
