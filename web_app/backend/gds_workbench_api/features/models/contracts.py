"""Tenant-owned Model read HTTP contracts."""

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, JsonValue

type ModelStatus = Literal["active", "archived"]
type ModelWorkflow = Literal[
    "profiling",
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "qa",
]


class ModelLedgerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=255)
    model_description: str | None = Field(default=None, max_length=2000)
    model_revision: int = Field(gt=0)
    model_scope_object_count: int = Field(ge=0)
    latest_workflow: ModelWorkflow | None = None
    latest_run_status: str | None = Field(default=None, min_length=1, max_length=30)
    updated_at: datetime


class ModelCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ModelLedgerRecord, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ModelDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=255)
    model_description: str | None = Field(default=None, max_length=2000)
    model_revision: int = Field(gt=0)
    model_scope_object_count: int = Field(ge=0)
    silver_model_naming_instructions: str | None = None
    silver_model_audit_columns_template: JsonValue | None = None
    gold_model_naming_instructions: str | None = None
    gold_model_technical_columns_template: JsonValue | None = None
    gold_model_audit_columns_template: JsonValue | None = None
    default_agent_sdk_code: str | None = Field(default=None, max_length=100)
    default_agent_provider_code: str | None = Field(default=None, max_length=100)
    default_agent_model_code: str | None = Field(default=None, max_length=200)
    default_reasoning_effort_code: str | None = Field(default=None, max_length=50)
    default_max_turns: int | None = Field(default=None, ge=1, le=50)
    default_validation_retry_count: int | None = Field(default=None, ge=0, le=5)
    is_active: bool
    updated_at: datetime


class ModelNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_not_found",
            message="The requested Model was not found.",
        )
