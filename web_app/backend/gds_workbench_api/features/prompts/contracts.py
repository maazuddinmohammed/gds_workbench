"""Governed Prompt Library contracts."""

from datetime import datetime
from typing import Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

type ModelWorkflow = Literal[
    "profiling",
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
]
type WorkflowExecutionMode = Literal[
    "one_shot",
    "tool_assisted",
    "detailed_coverage",
]
type PromptVariableDataType = Literal[
    "text",
    "integer",
    "number",
    "boolean",
    "json",
]
type PromptOwnershipScope = Literal["global", "tenant"]
type PromptVersionStatus = Literal["draft", "published", "retired"]
type PromptAssignmentScope = Literal["global_default", "model_default"]
type EffectivePromptSource = Literal["global_default", "model_default", "none"]


class PromptContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PromptStageVariable(PromptContract):
    name: str = Field(min_length=1, max_length=100)
    resolver_key: str = Field(min_length=1, max_length=200)
    data_type: PromptVariableDataType
    is_required: bool
    description: str = Field(min_length=1, max_length=2000)
    example: JsonValue | None = None
    order: int = Field(gt=0)


class PromptStage(PromptContract):
    workflow_stage_id: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None = None
    workflow_stage_code: str = Field(min_length=1, max_length=100)
    workflow_stage_name: str = Field(min_length=1, max_length=200)
    workflow_stage_description: str | None = Field(default=None, max_length=2000)
    workflow_stage_order: int = Field(gt=0)
    allowed_variables: tuple[PromptStageVariable, ...] = Field(max_length=100)


class PromptStageCatalog(PromptContract):
    tenant_id: int = Field(gt=0)
    items: tuple[PromptStage, ...] = Field(max_length=200)


class PromptTemplateFilters(PromptContract):
    model_workflow: ModelWorkflow | None = None
    workflow_execution_mode: WorkflowExecutionMode | None = None
    workflow_stage_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]{0,99}$",
    )
    version_status: PromptVersionStatus | None = None

    @field_validator("workflow_stage_code", mode="before")
    @classmethod
    def normalize_stage_code(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class PromptTemplateSummary(PromptContract):
    prompt_template_id: int = Field(gt=0)
    workflow_stage_id: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None = None
    workflow_stage_code: str = Field(min_length=1, max_length=100)
    workflow_stage_name: str = Field(min_length=1, max_length=200)
    prompt_template_ownership_scope: PromptOwnershipScope
    owner_tenant_id: int | None = Field(default=None, gt=0)
    prompt_template_code: str = Field(min_length=1, max_length=100)
    prompt_template_name: str = Field(min_length=1, max_length=200)
    prompt_template_description: str | None = Field(default=None, max_length=2000)
    is_active: bool
    latest_version_id: int | None = Field(default=None, gt=0)
    latest_version_number: int | None = Field(default=None, gt=0)
    latest_version_status: PromptVersionStatus | None = None
    latest_version_digest: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    latest_version_updated_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_ownership_and_version_shape(self) -> Self:
        if (self.prompt_template_ownership_scope == "global") != (self.owner_tenant_id is None):
            raise ValueError("Prompt Template ownership is inconsistent")
        latest = (
            self.latest_version_id,
            self.latest_version_number,
            self.latest_version_status,
            self.latest_version_digest,
            self.latest_version_updated_at,
        )
        if any(value is None for value in latest) and not all(value is None for value in latest):
            raise ValueError("latest Prompt Template version fields are incomplete")
        return self


class PromptTemplatePage(PromptContract):
    tenant_id: int = Field(gt=0)
    items: tuple[PromptTemplateSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class PromptTemplateVersion(PromptContract):
    prompt_template_version_id: int = Field(gt=0)
    prompt_template_id: int = Field(gt=0)
    workflow_stage_id: int = Field(gt=0)
    prompt_template_version_number: int = Field(gt=0)
    system_prompt_template: str = Field(min_length=1, max_length=262144)
    instruction_prompt_template: str = Field(min_length=1, max_length=262144)
    tool_instruction_prompt_template: str | None = Field(
        default=None,
        min_length=1,
        max_length=262144,
    )
    prompt_template_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    prompt_template_version_status: PromptVersionStatus
    published_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PromptTemplateDetail(PromptContract):
    tenant_id: int = Field(gt=0)
    template: PromptTemplateSummary
    allowed_variables: tuple[PromptStageVariable, ...] = Field(max_length=100)
    versions: tuple[PromptTemplateVersion, ...] = Field(max_length=200)


class PromptTemplateNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="prompt_template_not_found",
            message="The requested Prompt Template was not found.",
        )


class PromptConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="prompt_conflict",
            message=(
                "Prompt Library state changed or is still in use; inspect the current "
                "state before retrying."
            ),
        )


class PromptAssignmentConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="prompt_assignment_conflict",
            message=("Prompt assignment state changed or the selected version is unavailable."),
        )


class PromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreatePromptTemplateRequest(PromptRequest):
    workflow_stage_id: int = Field(gt=0)
    prompt_template_ownership_scope: PromptOwnershipScope
    prompt_template_code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]{0,99}$",
    )
    prompt_template_name: str = Field(min_length=1, max_length=200)
    prompt_template_description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

    @field_validator("prompt_template_code", mode="before")
    @classmethod
    def normalize_template_code(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("prompt_template_name", "prompt_template_description", mode="before")
    @classmethod
    def normalize_bounded_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt Template text must be nonblank")
        return normalized


class UpdatePromptTemplateRequest(PromptRequest):
    prompt_template_name: str = Field(min_length=1, max_length=200)
    prompt_template_description: str | None = Field(default=None, max_length=2000)
    is_active: bool
    expected_updated_at: datetime

    @field_validator("prompt_template_name", "prompt_template_description", mode="before")
    @classmethod
    def normalize_bounded_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt Template text must be nonblank")
        return normalized


class SavePromptDraftRequest(PromptRequest):
    expected_prompt_template_version_id: int | None = Field(default=None, gt=0)
    expected_updated_at: datetime | None = None
    system_prompt_template: str = Field(min_length=1, max_length=262144)
    instruction_prompt_template: str = Field(min_length=1, max_length=262144)
    tool_instruction_prompt_template: str | None = Field(
        default=None,
        min_length=1,
        max_length=262144,
    )

    @field_validator(
        "system_prompt_template",
        "instruction_prompt_template",
        "tool_instruction_prompt_template",
    )
    @classmethod
    def validate_prompt_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Prompt Template body must be nonblank")
        if len(value.encode("utf-8")) > 262144:
            raise ValueError("Prompt Template body exceeds 262144 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def validate_fence_pair(self) -> Self:
        if (self.expected_prompt_template_version_id is None) != (self.expected_updated_at is None):
            raise ValueError("Draft version and timestamp fences must be supplied together")
        return self


class SetModelPromptAssignmentRequest(PromptRequest):
    prompt_template_version_id: int | None = Field(gt=0)
    expected_prompt_assignment_id: int | None = Field(default=None, gt=0)


class PromptTemplateHeader(PromptContract):
    prompt_template_id: int = Field(gt=0)
    workflow_stage_id: int = Field(gt=0)
    prompt_template_ownership_scope: PromptOwnershipScope
    owner_tenant_id: int | None = Field(default=None, gt=0)
    prompt_template_code: str = Field(min_length=1, max_length=100)
    prompt_template_name: str = Field(min_length=1, max_length=200)
    prompt_template_description: str | None = Field(default=None, max_length=2000)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_ownership(self) -> Self:
        if (self.prompt_template_ownership_scope == "global") != (self.owner_tenant_id is None):
            raise ValueError("Prompt Template ownership is inconsistent")
        return self


class PromptAssignmentTarget(PromptContract):
    prompt_assignment_id: int = Field(gt=0)
    prompt_assignment_scope: PromptAssignmentScope
    prompt_template_version_id: int = Field(gt=0)
    prompt_template_version_number: int = Field(gt=0)
    prompt_template_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    prompt_template_id: int = Field(gt=0)
    prompt_template_ownership_scope: PromptOwnershipScope
    owner_tenant_id: int | None = Field(default=None, gt=0)
    prompt_template_code: str = Field(min_length=1, max_length=100)
    prompt_template_name: str = Field(min_length=1, max_length=200)
    assigned_at: datetime

    @model_validator(mode="after")
    def validate_ownership(self) -> Self:
        if (self.prompt_template_ownership_scope == "global") != (self.owner_tenant_id is None):
            raise ValueError("Prompt assignment ownership is inconsistent")
        return self


class ModelPromptAssignmentState(PromptContract):
    workflow_stage_id: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None = None
    workflow_stage_code: str = Field(min_length=1, max_length=100)
    workflow_stage_name: str = Field(min_length=1, max_length=200)
    workflow_stage_order: int = Field(gt=0)
    model_assignment: PromptAssignmentTarget | None = None
    global_assignment: PromptAssignmentTarget | None = None
    effective_source: EffectivePromptSource
    effective_assignment: PromptAssignmentTarget | None = None

    @model_validator(mode="after")
    def validate_effective_assignment(self) -> Self:
        expected = (
            self.model_assignment
            if self.effective_source == "model_default"
            else self.global_assignment
            if self.effective_source == "global_default"
            else None
        )
        if self.effective_assignment != expected:
            raise ValueError("effective Prompt assignment is inconsistent")
        return self


class ModelPromptAssignments(PromptContract):
    tenant_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    items: tuple[ModelPromptAssignmentState, ...] = Field(max_length=200)


class PromptModelNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_not_found",
            message="The requested Model was not found.",
        )


class PromptTemplateMutationContext(PromptContract):
    prompt_template_id: int = Field(gt=0)
    workflow_stage_id: int = Field(gt=0)
    prompt_template_ownership_scope: PromptOwnershipScope
    owner_tenant_id: int | None = Field(default=None, gt=0)
    prompt_template_code: str = Field(min_length=1, max_length=100)
