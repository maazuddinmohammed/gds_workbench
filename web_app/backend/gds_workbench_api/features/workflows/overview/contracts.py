"""Read-only, Tenant-scoped Project Workflow Overview contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type LedgerWorkflow = Literal[
    "scope",
    "profiling",
    "analysis",
    "context",
    "subject_area",
    "logical",
    "dimensional",
]
type OverviewWorkflow = (
    LedgerWorkflow | Literal["metadata_enrichment", "mapping", "code_generation", "validation"]
)
type ProjectSection = Literal[
    "overview",
    "settings",
    "scope",
    "metadata-enrichment",
    "profiling",
    "context",
    "analysis",
    "subject-area",
    "logical",
    "dimensional",
    "mapping",
    "code-generation",
    "validation",
]
type ProjectSectionState = Literal[
    "available",
    "ready",
    "empty",
    "not_run",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "results_available",
]
type WorkflowRunState = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_repair",
    "failed",
    "cancelled",
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
    "cancelled",
]
type QualityWarningCode = Literal[
    "scope_empty",
    "profiling_results_unavailable",
    "logical_results_unavailable",
]


class WorkflowMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    workflow: OverviewWorkflow
    result_count: int = Field(ge=0)
    locked_count: int = Field(ge=0)
    latest_run_id: int | None = Field(default=None, gt=0)
    latest_run_state: WorkflowRunState | None = None
    latest_run_created_at: datetime | None = None
    latest_run_completed_at: datetime | None = None
    latest_result_updated_at: datetime | None = None


class ProjectSectionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section: ProjectSection
    state: ProjectSectionState


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


class ProjectWorkflowOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[WorkflowLedgerEntry, ...] = Field(min_length=7, max_length=7)
    section_states: tuple[ProjectSectionStatus, ...] = Field(default=(), max_length=13)
