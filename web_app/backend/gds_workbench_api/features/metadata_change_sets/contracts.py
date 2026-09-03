"""Web DTOs for governed Tenant Metadata Change Sets."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from gds_etl_workbench.application.change_sets.contracts import SHA256_PATTERN
from gds_etl_workbench.application.change_sets.metadata import ChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CreateMetadataChangeSetRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"


class StageMetadataDatasetRequest(ContractModel):
    dataset: ChangeSetDataset
    records: Annotated[list[dict[str, object]], Field(max_length=50_000)]


class StageMetadataChangeSetRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    expected_draft_revision: int = Field(gt=0)
    changes: Annotated[
        list[StageMetadataDatasetRequest],
        Field(min_length=1, max_length=16),
    ]


class ExpectedDraftRevisionRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    expected_draft_revision: int = Field(gt=0)


class CreateMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    created: bool
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    created_at: datetime
    expires_at: datetime


class MetadataChangeSetDatasetCount(ContractModel):
    dataset: ChangeSetDataset
    record_count: int = Field(ge=0)


class StageMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    staged: Literal[True] = True
    datasets: tuple[MetadataChangeSetDatasetCount, ...] = Field(
        min_length=1,
        max_length=16,
    )
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class GetMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    status: Literal[
        "active",
        "validated",
        "applied",
        "expired",
        "archived",
        "superseded",
    ]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    validation_outcome: dict[str, object] | None
    dataset_counts: tuple[MetadataChangeSetDatasetCount, ...] = Field(
        min_length=16,
        max_length=16,
    )
    dataset: ChangeSetDataset | None
    records: tuple[dict[str, object], ...] | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    validated_at: datetime | None
    applied_at: datetime | None
    terminal_at: datetime | None


class MetadataChangeSetValidationError(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    dataset: str = Field(min_length=1, max_length=100)
    record_number: int | None = Field(default=None, gt=0)
    fields: tuple[str, ...] = Field(max_length=24)
    message: str = Field(min_length=1, max_length=2_000)


class MetadataChangeSetActionKey(ContractModel):
    action: Literal["insert", "update", "deactivate", "reactivate", "no_change"]
    natural_key: dict[str, str | int | bool | None]


class MetadataChangeSetActionReview(ContractModel):
    dataset: ChangeSetDataset
    insert_count: int = Field(ge=0)
    update_count: int = Field(ge=0)
    deactivate_count: int = Field(ge=0)
    reactivate_count: int = Field(ge=0)
    no_change_count: int = Field(ge=0)
    keys: tuple[MetadataChangeSetActionKey, ...] = Field(max_length=100)
    keys_truncated: bool


class ValidateMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    valid: bool
    phase: str = Field(min_length=1, max_length=100)
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    staged_record_count: int = Field(ge=0)
    error_count: int = Field(ge=0, le=100)
    errors: tuple[MetadataChangeSetValidationError, ...] = Field(max_length=100)
    action_review: tuple[MetadataChangeSetActionReview, ...] = Field(max_length=16)
    validated_at: datetime | None
    expires_at: datetime


class ApplyMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    valid: bool
    applied: bool
    phase: str = Field(min_length=1, max_length=100)
    status: Literal["active", "applied"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    staged_record_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    error_count: int = Field(ge=0, le=100)
    errors: tuple[MetadataChangeSetValidationError, ...] = Field(max_length=100)
    action_review: tuple[MetadataChangeSetActionReview, ...] = Field(max_length=16)
    applied_at: datetime | None


class ArchiveMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    archived: Literal[True] = True
    status: Literal["archived"] = "archived"
    draft_revision: int = Field(gt=0)
    archived_at: datetime


class ImportMetadataWorkbookResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    metadata_change_set_id: UUID
    imported_sheet_count: int = Field(gt=0, le=16)
    staged: StageMetadataChangeSetResult
    validation: ValidateMetadataChangeSetResult


__all__ = [
    "ApplyMetadataChangeSetResult",
    "ArchiveMetadataChangeSetResult",
    "CreateMetadataChangeSetRequest",
    "CreateMetadataChangeSetResult",
    "ExpectedDraftRevisionRequest",
    "GetMetadataChangeSetResult",
    "ImportMetadataWorkbookResult",
    "MetadataChangeSetActionKey",
    "MetadataChangeSetActionReview",
    "MetadataChangeSetDatasetCount",
    "MetadataChangeSetValidationError",
    "StageMetadataChangeSetRequest",
    "StageMetadataChangeSetResult",
    "StageMetadataDatasetRequest",
    "ValidateMetadataChangeSetResult",
]
