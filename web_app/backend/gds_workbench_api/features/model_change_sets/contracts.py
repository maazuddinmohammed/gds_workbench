"""HTTP requests and the canonical Model Change Set result contracts."""

from typing import Annotated, Self

from gds_etl_workbench.tools.change_sets.common import (
    MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS,
    MAX_MODEL_STAGE_PAYLOAD_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
)
from gds_etl_workbench.tools.change_sets.model import (
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
from gds_etl_workbench.tools.snapshots.model.contracts import ModelChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateModelChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


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
