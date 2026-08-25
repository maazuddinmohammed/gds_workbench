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
    "needs_review",
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
    workflow: LedgerWorkflow
    result_count: int = Field(ge=0)
    needs_review_count: int = Field(ge=0)
    locked_count: int = Field(ge=0)
    latest_run_id: int | None = Field(default=None, gt=0)
    latest_run_state: WorkflowRunState | None = None
    latest_run_created_at: datetime | None = None


class WorkflowLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow: LedgerWorkflow
    result_count: int = Field(ge=0)
    needs_review_count: int = Field(ge=0)
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
