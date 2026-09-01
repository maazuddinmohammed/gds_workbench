"""Governed Workflow Run creation contracts."""

import json
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.runs import (
    ExecutionMode,
    ModeledEntityType,
    ModelWorkflow,
    RunState,
)

_MAX_PROMPT_OVERRIDES_BYTES = 32 * 1024


class CreateWorkflowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: ExecutionMode | None = None
    selected_object_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        max_length=50_000,
    )
    selected_system_codes: list[
        Annotated[str, Field(min_length=1, max_length=100, strict=True)]
    ] = Field(default_factory=list, max_length=1_000)
    modeled_entity_type: ModeledEntityType | None = None
    requested_batch_id: str | None = Field(default=None, min_length=1, max_length=500)
    mapping_operation: Literal["build", "extend"] | None = None
    mapping_coverage_mode: Literal["selected_targets"] | None = None
    mapping_artifact_type: (
        Literal[
            "sql_file",
            "python_file",
            "python_notebook",
        ]
        | None
    ) = None
    mapping_source_system_id: int | None = Field(default=None, gt=0)
    mapping_object_output_template_id: int | None = Field(default=None, gt=0)
    mapping_attribute_output_template_id: int | None = Field(default=None, gt=0)
    code_generation_coverage_mode: (
        Literal[
            "selected_targets",
            "all_eligible_targets",
        ]
        | None
    ) = None
    sql_generation_guide_version_id: int | None = Field(default=None, gt=0)
    agent: AgentRunSelection | None = None
    prompt_overrides: dict[str, Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=dict,
        max_length=200,
    )

    @field_validator("requested_batch_id")
    @classmethod
    def normalize_batch_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("requested_batch_id must be nonblank")
        return normalized

    @field_validator("selected_system_codes")
    @classmethod
    def normalize_selected_system_codes(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or "\x00" in item for item in normalized):
            raise ValueError("Selected System Codes must be nonblank")
        return normalized

    @field_validator("prompt_overrides")
    @classmethod
    def validate_prompt_overrides(
        cls,
        value: dict[str, int],
    ) -> dict[str, int]:
        if any(not key.isascii() or not key.isdigit() or key.startswith("0") for key in value):
            raise ValueError("Prompt override keys must be positive Workflow Stage IDs")
        if (
            len(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())
            > _MAX_PROMPT_OVERRIDES_BYTES
        ):
            raise ValueError("Prompt overrides are too large")
        return value

    @model_validator(mode="after")
    def validate_workflow_shape(self) -> Self:
        if len(self.selected_object_ids) != len(set(self.selected_object_ids)):
            raise ValueError("Selected Object IDs must be unique")
        normalized_system_codes = [value.casefold() for value in self.selected_system_codes]
        if len(normalized_system_codes) != len(set(normalized_system_codes)):
            raise ValueError("Selected System Codes must be unique")
        if self.model_workflow == "qa":
            if self.selected_object_ids or not self.selected_system_codes:
                raise ValueError("QA requires only an explicit System selection")
            if (
                self.code_generation_coverage_mode is not None
                or self.sql_generation_guide_version_id is not None
            ):
                raise ValueError("Code Generation inputs are unavailable for this workflow")
        elif self.selected_system_codes:
            raise ValueError("System selection is available only for QA")
        elif self.model_workflow == "code_generation":
            if (
                (
                    self.code_generation_coverage_mode == "selected_targets"
                    and not self.selected_object_ids
                )
                or (
                    self.code_generation_coverage_mode == "all_eligible_targets"
                    and self.selected_object_ids
                )
                or self.code_generation_coverage_mode is None
            ):
                raise ValueError("Code Generation coverage is invalid")
        else:
            if not self.selected_object_ids:
                raise ValueError("Selected Object IDs are required")
            if (
                self.code_generation_coverage_mode is not None
                or self.sql_generation_guide_version_id is not None
            ):
                raise ValueError("Code Generation inputs are unavailable for this workflow")

        agentic = self.model_workflow in {"code_generation", "qa"} or (
            self.workflow_execution_mode is not None
        )
        requires_mode = self.model_workflow in {
            "conceptual",
            "logical",
            "dimensional",
            "mapping",
        }
        if requires_mode and self.workflow_execution_mode is None:
            raise ValueError("This workflow requires an explicit execution mode")
        if self.model_workflow in {"profiling", "code_generation", "qa"} and (
            self.workflow_execution_mode is not None
        ):
            raise ValueError("This workflow does not accept an execution mode")
        if not agentic and (self.agent is not None or self.prompt_overrides):
            raise ValueError("Deterministic workflows cannot use agent inputs")

        if self.model_workflow == "code_generation" and (self.modeled_entity_type is None):
            raise ValueError("Code Generation requires a modeled Entity type")
        if self.model_workflow != "code_generation" and (self.modeled_entity_type is not None):
            raise ValueError("Modeled Entity type is unavailable for this workflow")

        required_mapping_inputs = (
            self.mapping_operation,
            self.mapping_coverage_mode,
            self.mapping_artifact_type,
            self.mapping_source_system_id,
        )
        mapping_inputs = required_mapping_inputs + (
            self.mapping_object_output_template_id,
            self.mapping_attribute_output_template_id,
        )
        if self.model_workflow == "mapping":
            if any(value is None for value in required_mapping_inputs):
                raise ValueError("Mapping requires one complete target selection")
            if len(self.selected_object_ids) != 1:
                raise ValueError("Mapping selected coverage requires one target Object")
        elif any(value is not None for value in mapping_inputs):
            raise ValueError("Mapping inputs are unavailable for this workflow")
        if self.requested_batch_id is not None and self.model_workflow not in {
            "profiling",
            "analysis",
        }:
            raise ValueError("Batch ID is available only for Profiling and Analysis")
        return self


class WorkflowRunCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    created: bool
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: RunState
    correlation_id: UUID
    prompt_snapshot_count: int = Field(ge=0)
    model_revision: int = Field(gt=0)
    selected_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_scope_count: int = Field(gt=0, le=50_000)
    code_generation_coverage_mode: (
        Literal[
            "selected_targets",
            "all_eligible_targets",
        ]
        | None
    )
    sql_generation_guide_id: int | None = Field(default=None, gt=0)
    sql_generation_guide_version_id: int | None = Field(default=None, gt=0)
    sql_generation_guide_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    created_at: datetime

    @model_validator(mode="after")
    def validate_code_generation_snapshot(self) -> Self:
        guide_values = (
            self.sql_generation_guide_id,
            self.sql_generation_guide_version_id,
            self.sql_generation_guide_digest,
        )
        if self.code_generation_coverage_mode is None:
            if any(value is not None for value in guide_values):
                raise ValueError("Code Generation guide snapshot is invalid")
        elif any(value is None for value in guide_values):
            raise ValueError("Code Generation guide snapshot is invalid")
        return self
