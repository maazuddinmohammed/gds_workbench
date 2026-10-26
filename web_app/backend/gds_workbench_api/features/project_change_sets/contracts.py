"""HTTP requests and the canonical Project Change Set result contracts."""

from typing import Annotated, Literal, Self
from uuid import UUID

from gds_etl_workbench.application.change_sets.contracts import (
    MAX_PROJECT_STAGE_FRAGMENT_BASE64_CHARACTERS,
    MAX_PROJECT_STAGE_PAYLOAD_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
)
from gds_etl_workbench.application.change_sets.project import (
    ApplyProjectChangeSetResult,
    ArchiveProjectChangeSetResult,
    BeginProjectStageBatchResult,
    CommitProjectStageBatchResult,
    CreateProjectChangeSetResult,
    GetProjectChangeSetResult,
    ProjectStagePayloadMode,
    PutProjectStageChunkResult,
    StageProjectChange,
    StageProjectChangeSetResult,
    ValidateProjectChangeSetResult,
)
from gds_etl_workbench.domain.modeling_records import ContextRecordId, NonblankText
from gds_etl_workbench.domain.snapshots.project import ProjectChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .review import ProjectReviewDataset

type ProjectRecordId = Annotated[int, Field(gt=0)] | ContextRecordId


class CreateProjectChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_project_revision: int = Field(gt=0)


class ReviewProjectRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: Literal["analysis_result"] | ProjectReviewDataset
    record_ids: Annotated[list[ProjectRecordId], Field(max_length=200)]
    action: Literal["lock", "unlock", "deactivate", "reactivate", "delete"]
    layer: Literal["subject_area", "logical", "dimensional"] | None = None
    expected_project_revision: int = Field(gt=0)

    expected_plan_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        _validate_review_selection(self.dataset, self.record_ids, self.action, self.layer)
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("Select each record once.")
        return self


class SaveSubjectAreaRequest(BaseModel):
    """One human change to one Subject Area: create, rename, define, add or remove tables."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_project_revision: int = Field(gt=0)
    subject_area_id: int | None = Field(default=None, gt=0)
    subject_area_name: (
        Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")] | None
    ) = None
    subject_area_definition: NonblankText | None = None
    add_object_ids: Annotated[list[Annotated[int, Field(gt=0)]], Field(max_length=5_000)] = []
    remove_object_ids: Annotated[list[Annotated[int, Field(gt=0)]], Field(max_length=5_000)] = []

    @model_validator(mode="after")
    def validate_change(self) -> Self:
        if self.subject_area_id is None:
            if self.subject_area_name is None or self.subject_area_definition is None:
                raise ValueError("A new Subject Area needs a name and a definition.")
            if self.remove_object_ids:
                raise ValueError("A new Subject Area has no tables to remove.")
        elif (
            self.subject_area_name is None
            and self.subject_area_definition is None
            and not self.add_object_ids
            and not self.remove_object_ids
        ):
            raise ValueError("Change the name, the definition or the tables.")
        added, removed = set(self.add_object_ids), set(self.remove_object_ids)
        if (
            len(added) != len(self.add_object_ids)
            or len(removed) != len(self.remove_object_ids)
            or added & removed
        ):
            raise ValueError("Add or remove each table once.")
        return self


class ReviewProjectRecordsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: int
    project_change_set_id: UUID
    project_revision: int
    action_count: int


class PreviewProjectRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ProjectReviewDataset
    record_ids: Annotated[list[ProjectRecordId], Field(max_length=200)]
    action: Literal["lock", "unlock", "deactivate", "reactivate", "delete"]
    layer: Literal["subject_area", "logical", "dimensional"] | None = None
    expected_project_revision: int = Field(gt=0)
    expected_plan_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        _validate_review_selection(self.dataset, self.record_ids, self.action, self.layer)
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("Select each record once.")
        return self


def _validate_review_selection(
    dataset: str, record_ids: list[int | str], action: str, layer: str | None
) -> None:
    if dataset == "context_record":
        if any(not isinstance(record_id, str) for record_id in record_ids):
            raise ValueError("Context Records require UUID identities.")
    elif any(type(record_id) is not int for record_id in record_ids):
        raise ValueError("This dataset requires numeric record identities.")
    if action == "delete" and dataset not in {
        "subject_area",
        "subject_area_table",
        "logical_entity",
        "logical_attribute",
        "logical_relationship",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
    }:
        raise ValueError("Permanent deletion is available only for modeled records.")
    if layer is None:
        if not record_ids:
            raise ValueError("Select at least one record.")
    elif (
        record_ids
        or action not in {"deactivate", "delete"}
        or dataset != ("subject_area" if layer == "subject_area" else f"{layer}_entity")
    ):
        raise ValueError(
            "Clear layer requires its primary dataset, no record IDs, and a removal action."
        )


class ProjectRecordReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: str
    record_id: ProjectRecordId
    label: str
    selected: bool
    reason: str
    is_locked: bool
    desired_locked: bool
    can_unlock: bool = True
    status: Literal["active", "inactive", "deprecated"]
    desired_status: Literal["active", "inactive", "deprecated", "deleted"]
    changed: bool


class ProjectRecordReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str
    dataset: str
    message: str


class PreviewProjectRecordsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    plan_digest: str = Field(pattern=SHA256_PATTERN)
    can_apply: bool
    action_count: int = Field(ge=0)
    additional_change_count: int = Field(ge=0)
    total_record_count: int = Field(ge=0)
    changes_by_dataset: dict[str, int] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    items: tuple[ProjectRecordReviewItem, ...] = Field(max_length=200)
    issues: tuple[ProjectRecordReviewIssue, ...] = Field(max_length=20)
    issue_count: int = Field(ge=0)
    page: int = Field(gt=0)
    next_page: int | None = Field(default=None, gt=0)


class ProjectRecordHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_id: ProjectRecordId
    label: str
    is_locked: bool
    status: Literal["active", "inactive", "deprecated"]


class ProjectRecordHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    dataset: ProjectReviewDataset
    items: tuple[ProjectRecordHistoryItem, ...] = Field(max_length=200)
    next_page: int | None = Field(default=None, gt=0)


class StageProjectChangeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)
    changes: Annotated[list[StageProjectChange], Field(min_length=1, max_length=21)]


class BeginProjectStageBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_draft_revision: int = Field(gt=0)
    dataset: ProjectChangeSetDataset
    total_record_count: int = Field(gt=0, le=20_000)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    batch_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_mode: ProjectStagePayloadMode = "records"
    total_payload_bytes: int | None = Field(
        default=None,
        gt=0,
        le=MAX_PROJECT_STAGE_PAYLOAD_BYTES,
    )

    @model_validator(mode="after")
    def validate_payload_manifest(self) -> Self:
        if self.payload_mode == "records":
            if self.total_payload_bytes is not None:
                raise ValueError("Record Stage Batches cannot declare payload bytes")
        elif self.dataset != "generated_code" or self.total_payload_bytes is None:
            raise ValueError("JSON fragments are available only for generated_code")
        return self


class PutProjectStageChunkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ProjectChangeSetDataset
    records: Annotated[
        list[dict[str, object]] | None,
        Field(max_length=MAX_STAGE_CHUNK_RECORDS),
    ] = None
    chunk_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_mode: ProjectStagePayloadMode = "records"
    payload_fragment_base64: str | None = Field(
        default=None,
        max_length=MAX_PROJECT_STAGE_FRAGMENT_BASE64_CHARACTERS,
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
    "ApplyProjectChangeSetResult",
    "ArchiveProjectChangeSetResult",
    "BeginProjectStageBatchRequest",
    "BeginProjectStageBatchResult",
    "CommitProjectStageBatchResult",
    "CreateProjectChangeSetRequest",
    "CreateProjectChangeSetResult",
    "ExpectedDraftRevisionRequest",
    "GetProjectChangeSetResult",
    "PutProjectStageChunkRequest",
    "PutProjectStageChunkResult",
    "StageProjectChangeSetRequest",
    "StageProjectChangeSetResult",
    "ValidateProjectChangeSetResult",
]
