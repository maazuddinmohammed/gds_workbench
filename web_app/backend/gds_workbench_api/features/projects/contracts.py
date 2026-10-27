"""Tenant-owned Project read HTTP contracts."""

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import ProjectSchemaDefinition
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_workbench_api.capabilities import MAX_AGENT_TURNS, MAX_VALIDATION_RETRIES

type ProjectStatus = Literal["active", "archived"]
type ProjectWorkflow = Literal[
    "profiling",
    "analysis",
    "subject_area",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "validation",
    "metadata_enrichment",
]


class ProjectLedgerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: int = Field(gt=0)
    project_name: str = Field(min_length=1, max_length=255)
    project_description: str | None = Field(default=None, max_length=2000)
    project_revision: int = Field(gt=0)
    is_locked: bool = False
    project_input_scope_object_count: int = Field(ge=0)
    latest_workflow: ProjectWorkflow | None = None
    latest_run_status: str | None = Field(default=None, min_length=1, max_length=30)
    updated_at: datetime


class ProjectCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ProjectLedgerRecord, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ProjectDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    project_name: str = Field(min_length=1, max_length=255)
    project_description: str | None = Field(default=None, max_length=2000)
    project_revision: int = Field(gt=0)
    is_locked: bool = False
    project_input_scope_object_count: int = Field(ge=0)
    logical_schemas: tuple[ProjectSchemaDefinition, ...] = ()
    dimensional_schemas: tuple[ProjectSchemaDefinition, ...] = ()
    logical_entity_scd_type: Literal["type_1", "type_2"] | None = None
    dimensional_entity_scd_type: Literal["type_1", "type_2"] | None = None
    logical_coverage_threshold_percent: int = Field(default=70, ge=1, le=100, strict=True)
    dimensional_coverage_threshold_percent: int = Field(default=60, ge=1, le=100, strict=True)
    logical_enforce_coverage_threshold: bool = Field(default=False, strict=True)
    dimensional_enforce_coverage_threshold: bool = Field(default=False, strict=True)
    silver_model_naming_instructions: str | None = None
    silver_model_audit_columns_template: JsonValue | None = None
    gold_model_naming_instructions: str | None = None
    gold_model_technical_columns_template: JsonValue | None = None
    gold_model_audit_columns_template: JsonValue | None = None
    default_agent_sdk_code: str | None = Field(default=None, max_length=100)
    default_agent_provider_code: str | None = Field(default=None, max_length=100)
    default_agent_model_code: str | None = Field(default=None, max_length=200)
    default_reasoning_effort_code: str | None = Field(default=None, max_length=50)
    default_max_turns: int | None = Field(default=None, ge=1, le=MAX_AGENT_TURNS)
    default_validation_retry_count: int | None = Field(
        default=None, ge=0, le=MAX_VALIDATION_RETRIES
    )
    is_active: bool
    updated_at: datetime


class ProjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="project_not_found",
            message="The requested Project was not found.",
        )
