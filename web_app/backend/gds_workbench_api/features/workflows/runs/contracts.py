"""Common, bounded Workflow Run read contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field

type ModelWorkflow = Literal[
    "profiling",
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
]
type ExecutionMode = Literal["one_shot", "tool_assisted", "detailed_coverage"]
type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]
type RunState = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_repair",
    "failed",
]
type ModelChangeSetStatus = Literal[
    "active",
    "validated",
    "applied",
    "expired",
    "discarded",
    "superseded",
]
type EventStatus = Literal[
    "started",
    "running",
    "completed",
    "warning",
    "failed",
    "blocked",
]


class WorkflowRunLedgerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_run_id: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: ExecutionMode | None = None
    modeled_entity_type: ModeledEntityType | None = None
    selected_scope_count: int = Field(gt=0)
    requested_batch_id: str | None = Field(default=None, max_length=500)
    workflow_run_state: RunState
    actor_display_name: str = Field(min_length=1, max_length=255)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowRunDetail(WorkflowRunLedgerRecord):
    correlation_id: UUID
    agent_sdk_code: str | None = Field(default=None, max_length=100)
    agent_provider_code: str | None = Field(default=None, max_length=100)
    agent_model_code: str | None = Field(default=None, max_length=200)
    reasoning_effort_code: str | None = Field(default=None, max_length=50)
    max_turns: int | None = Field(default=None, ge=1, le=50)
    validation_retry_count: int | None = Field(default=None, ge=0, le=5)
    failure_code: str | None = Field(default=None, max_length=100)
    failure_message: str | None = Field(default=None, max_length=2000)
    model_change_set_id: UUID | None = None
    model_change_set_status: ModelChangeSetStatus | None = None
    draft_revision: int | None = Field(default=None, gt=0)
    candidate_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    validated_at: datetime | None = None


class WorkflowRunCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[WorkflowRunLedgerRecord, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class RunEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(gt=0)
    attempt: int = Field(gt=0)
    stage: str = Field(min_length=1, max_length=100)
    status: EventStatus
    message: str = Field(min_length=1, max_length=2000)
    current: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    percent: Decimal | None = Field(default=None, ge=0, le=100)
    finding_count: int = Field(ge=0)
    created_at: datetime


class RunEventCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[RunEventRecord, ...] = Field(max_length=200)
    next_after_sequence: int = Field(ge=0)


class WorkflowRunNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="workflow_run_not_found",
            message="The requested workflow run was not found.",
        )
