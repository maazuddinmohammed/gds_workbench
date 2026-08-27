"""Read contracts for Analysis findings and validation evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReviewContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


type AnalysisStatus = Literal["active", "needs_review", "inactive", "deprecated"]
type AnalysisValidationState = Literal["validated", "unvalidated"]
type AnalysisValidationResult = Literal["supported", "inconclusive", "unsupported"]


class AnalysisFindingFilters(ReviewContract):
    object_id: int | None = Field(default=None, gt=0)
    from_object_id: int | None = Field(default=None, gt=0)
    to_object_id: int | None = Field(default=None, gt=0)
    validation_state: AnalysisValidationState | None = None
    status: AnalysisStatus | None = None
    locked: bool | None = None
    show_inactive: bool = False

    @field_validator("validation_state", "status", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> object:
        return value.strip(" ").lower() if isinstance(value, str) else value


class AnalysisEndpoint(ReviewContract):
    object_id: int = Field(gt=0)
    attribute_id: int = Field(gt=0)
    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_data_type: str = Field(min_length=1, max_length=100)


class AnalysisFindingSummary(ReviewContract):
    analysis_result_id: int = Field(gt=0)
    from_endpoint: AnalysisEndpoint
    to_endpoint: AnalysisEndpoint
    relationship_kind: str = Field(min_length=1, max_length=100)
    relationship_confidence: Literal["low", "medium", "high"]
    validation_state: AnalysisValidationState
    validation_result: AnalysisValidationResult | None = None
    status: AnalysisStatus
    is_locked: bool
    updated_at: datetime

    @model_validator(mode="after")
    def validate_validation_state(self) -> AnalysisFindingSummary:
        if (self.validation_result is None) != (self.validation_state == "unvalidated"):
            raise ValueError("validation state must match the validation result")
        return self


class AnalysisFindingPage(ReviewContract):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[AnalysisFindingSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class AnalysisEvidence(ReviewContract):
    validation_policy_version: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    )
    validation_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: AnalysisValidationResult
    source_non_null_count: int = Field(ge=0)
    source_distinct_count: int = Field(ge=0)
    target_non_null_count: int = Field(ge=0)
    target_distinct_count: int = Field(ge=0)
    source_missing_target_count: int = Field(ge=0)
    unused_target_count: int = Field(ge=0)
    duplicate_target_key_count: int = Field(ge=0)


class AnalysisWorkflowProvenance(ReviewContract):
    agent_run_id: str | None = Field(default=None, max_length=500)
    inference_workflow_run_id: int | None = Field(default=None, gt=0)
    validation_workflow_run_id: int | None = Field(default=None, gt=0)


class AnalysisFindingDetail(AnalysisFindingSummary):
    relationship_basis: str = Field(min_length=1, max_length=8000)
    relationship_basis_truncated: bool = False
    evidence: AnalysisEvidence | None = None
    provenance: AnalysisWorkflowProvenance
    created_at: datetime

    @model_validator(mode="after")
    def validate_evidence(self) -> AnalysisFindingDetail:
        if (self.evidence is None) != (self.validation_state == "unvalidated"):
            raise ValueError("validation state must match the evidence")
        if self.evidence is not None and self.evidence.result != self.validation_result:
            raise ValueError("evidence result must match the finding validation result")
        return self


class AnalysisFindingNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_finding_not_found",
            message="The requested Analysis finding was not found in the active Model.",
        )
