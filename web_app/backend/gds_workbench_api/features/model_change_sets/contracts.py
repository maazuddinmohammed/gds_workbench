"""HTTP requests and the canonical Model Change Set result contracts."""

from typing import Annotated

from gds_etl_workbench.tools.change_sets.common import (
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
    PutModelStageChunkResult,
    StageModelChange,
    StageModelChangeSetResult,
    ValidateModelChangeSetResult,
)
from gds_etl_workbench.tools.snapshots.model.contracts import ModelChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field


class CreateModelChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class StageModelChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)
    changes: Annotated[list[StageModelChange], Field(min_length=1, max_length=18)]


class BeginModelStageBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)
    dataset: ModelChangeSetDataset
    total_record_count: int = Field(gt=0, le=20_000)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    batch_sha256: str = Field(pattern=SHA256_PATTERN)


class PutModelStageChunkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ModelChangeSetDataset
    records: Annotated[
        list[dict[str, object]],
        Field(min_length=1, max_length=MAX_STAGE_CHUNK_RECORDS),
    ]
    chunk_sha256: str = Field(pattern=SHA256_PATTERN)


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
