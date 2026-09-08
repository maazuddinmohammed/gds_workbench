"""HTTP requests and the canonical Model Change Set result contracts."""

from typing import Annotated, Literal, Self
from uuid import UUID

from gds_etl_workbench.application.change_sets.contracts import (
    MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS,
    MAX_MODEL_STAGE_PAYLOAD_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
)
from gds_etl_workbench.application.change_sets.model import (
    ApplyModelChangeSetResult,
    ArchiveModelChangeSetResult,
    BeginModelStageBatchResult,
    CommitModelStageBatchResult,
    CreateModelChangeSetResult,
    GetModelChangeSetResult,
    ModelStagePayloadMode,
    PutModelStageChunkResult,
    StageModelChange,
    StageModelChangeSetResult,
    ValidateModelChangeSetResult,
)
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .review import ModelReviewDataset


class CreateModelChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class ReviewModelRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: Literal["analysis_result"] | ModelReviewDataset
    record_ids: Annotated[list[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=200)]
    action: Literal["lock", "unlock", "deactivate", "reactivate"]
    expected_model_revision: int = Field(gt=0)

    expected_plan_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("Select each record once.")
        return self


class ReviewModelRecordsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_id: int
    model_change_set_id: UUID
    model_revision: int
    action_count: int


class PreviewModelRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ModelReviewDataset
    record_ids: Annotated[list[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=200)]
    action: Literal["lock", "unlock", "deactivate", "reactivate"]
    expected_model_revision: int = Field(gt=0)
    expected_plan_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("Select each record once.")
        return self


class ModelRecordReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ModelReviewDataset
    record_id: int = Field(gt=0)
    label: str
    selected: bool
    reason: str
    is_locked: bool
    desired_locked: bool
    status: Literal["active", "inactive", "deprecated"]
    desired_status: Literal["active", "inactive", "deprecated"]
    changed: bool


class ModelRecordReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str
    dataset: str
    message: str


class PreviewModelRecordsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    plan_digest: str = Field(pattern=SHA256_PATTERN)
    can_apply: bool
    action_count: int = Field(ge=0)
    additional_change_count: int = Field(ge=0)
    total_record_count: int = Field(ge=0)
    items: tuple[ModelRecordReviewItem, ...] = Field(max_length=200)
    issues: tuple[ModelRecordReviewIssue, ...] = Field(max_length=20)
    issue_count: int = Field(ge=0)
    page: int = Field(gt=0)
    next_page: int | None = Field(default=None, gt=0)


class ModelRecordHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_id: int = Field(gt=0)
    label: str
    is_locked: bool
    status: Literal["active", "inactive", "deprecated"]


class ModelRecordHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    dataset: ModelReviewDataset
    items: tuple[ModelRecordHistoryItem, ...] = Field(max_length=200)
    next_page: int | None = Field(default=None, gt=0)


class StageModelChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)
    changes: Annotated[list[StageModelChange], Field(min_length=1, max_length=21)]


class BeginModelStageBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)
    dataset: ModelChangeSetDataset
    total_record_count: int = Field(gt=0, le=20_000)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    batch_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_mode: ModelStagePayloadMode = "records"
    total_payload_bytes: int | None = Field(
        default=None,
        gt=0,
        le=MAX_MODEL_STAGE_PAYLOAD_BYTES,
    )

    @model_validator(mode="after")
    def validate_payload_manifest(self) -> Self:
        if self.payload_mode == "records":
            if self.total_payload_bytes is not None:
                raise ValueError("Record Stage Batches cannot declare payload bytes")
        elif self.dataset != "generated_code" or self.total_payload_bytes is None:
            raise ValueError("JSON fragments are available only for generated_code")
        return self


class PutModelStageChunkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ModelChangeSetDataset
    records: Annotated[
        list[dict[str, object]] | None,
        Field(max_length=MAX_STAGE_CHUNK_RECORDS),
    ] = None
    chunk_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_mode: ModelStagePayloadMode = "records"
    payload_fragment_base64: str | None = Field(
        default=None,
        max_length=MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS,
    )

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.payload_mode == "records":
            if not self.records or self.payload_fragment_base64 is not None:
                raise ValueError("Record Stage chunks require only records")
        elif (
            self.dataset != "generated_code"
            or self.records is not None
            or self.payload_fragment_base64 is None
        ):
            raise ValueError("JSON fragment Stage chunks require only one Code fragment")
        return self


class ExpectedDraftRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)


__all__ = [
    "ApplyModelChangeSetResult",
    "ArchiveModelChangeSetResult",
    "BeginModelStageBatchRequest",
    "BeginModelStageBatchResult",
    "CommitModelStageBatchResult",
    "CreateModelChangeSetRequest",
    "CreateModelChangeSetResult",
    "ExpectedDraftRevisionRequest",
    "GetModelChangeSetResult",
    "PutModelStageChunkRequest",
    "PutModelStageChunkResult",
    "StageModelChangeSetRequest",
    "StageModelChangeSetResult",
    "ValidateModelChangeSetResult",
]
