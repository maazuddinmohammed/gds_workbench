"""Read-only, Tenant-scoped Model Workflow Overview contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type LedgerWorkflow = Literal[
    "scope",
    "profiling",
    "analysis",
    "assertions",
    "conceptual",
    "logical",
    "dimensional",
]
type OverviewWorkflow = (
    LedgerWorkflow | Literal["metadata_enrichment", "mapping", "code_generation", "validation"]
)
type ModelSection = Literal[
    "overview",
    "settings",
    "scope",
    "metadata-enrichment",
    "profiling",
    "assertions",
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code-generation",
    "validation",
]
type ModelSectionState = Literal[
    "available",
    "ready",
    "empty",
    "not_run",
    "queued",
    "running",
    "completed",
    "failed",
    "results_available",
]
type WorkflowRunState = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_repair",
    "failed",
]
type WorkflowLedgerState = Literal[
    "empty",
    "ready",
    "not_started",
    "queued",
    "running",
    "results_available",
    "completed_no_results",
    "failed",
]
type QualityWarningCode = Literal[
    "scope_empty",
    "profiling_results_unavailable",
    "conceptual_results_unavailable",
    "logical_results_unavailable",
]


class WorkflowMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    workflow: OverviewWorkflow
    result_count: int = Field(ge=0)
    locked_count: int = Field(ge=0)
    latest_run_id: int | None = Field(default=None, gt=0)
    latest_run_state: WorkflowRunState | None = None
    latest_run_created_at: datetime | None = None
    latest_run_completed_at: datetime | None = None
    latest_result_updated_at: datetime | None = None


class ModelSectionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section: ModelSection
    state: ModelSectionState


class WorkflowLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow: LedgerWorkflow
    result_count: int = Field(ge=0)
    locked_count: int = Field(ge=0)
    latest_run_id: int | None = Field(default=None, gt=0)
    latest_run_state: WorkflowRunState | None = None
    latest_run_created_at: datetime | None = None
    state: WorkflowLedgerState
    quality_warning_codes: tuple[QualityWarningCode, ...] = Field(max_length=4)


class ModelWorkflowOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[WorkflowLedgerEntry, ...] = Field(min_length=7, max_length=7)
    section_states: tuple[ModelSectionStatus, ...] = Field(default=(), max_length=13)
