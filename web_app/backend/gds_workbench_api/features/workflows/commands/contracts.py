"""Governed Workflow Run creation and cancellation contracts."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.mapping.contracts import MappingTargetSelection
from gds_workbench_api.features.metadata_enrichment.contracts import EnrichmentDescriptionTarget
from gds_workbench_api.features.workflows.runs import (
    ExecutionMode,
    ModeledEntityType,
    ProjectWorkflow,
    RunState,
)


class CreateWorkflowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_project_revision: int = Field(gt=0)
    project_workflow: ProjectWorkflow
    workflow_execution_mode: ExecutionMode | None = None
    selected_object_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list[int]
    )
    selected_entity_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list[int]
    )
    selected_system_codes: list[
        Annotated[str, Field(min_length=1, max_length=100, strict=True)]
    ] = Field(default_factory=list)
    modeled_entity_type: ModeledEntityType | None = None
    # Logical and Dimensional: Build the ordered Subject Areas, or Optimize the whole model.
    workflow_operation: Literal["build", "optimize"] | None = None
    subject_area_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list[int], max_length=1_000
    )
    requested_batch_id: str | None = Field(default=None, min_length=1, max_length=500)
    mapping_operation: Literal["build", "extend", "generate"] | None = None
    mapping_targets: list[MappingTargetSelection] | None = Field(default=None, min_length=1)
    mapping_coverage_mode: Literal["selected_targets"] | None = None
    mapping_source_system_id: int | None = Field(default=None, gt=0)
    mapping_object_output_template_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Null or omitted selects the global default Object template for the Mapping Run."
        ),
    )
    mapping_attribute_output_template_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Null or omitted selects the global default Attribute template for the Mapping Run."
        ),
    )
    code_generation_coverage_mode: (
        Literal[
            "selected_targets",
            "all_eligible_targets",
        ]
        | None
    ) = None
    code_generation_file_layout: Literal["combined", "per_system"] | None = None
    agent: AgentRunSelection | None = None
    description_targets: list[EnrichmentDescriptionTarget] | None = Field(
        default=None, min_length=1
    )
    prompt_overrides: dict[str, Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=dict,
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
        return value

    @model_validator(mode="after")
    def validate_workflow_shape(self) -> Self:
        modeling = self.project_workflow in {"logical", "dimensional"}
        if modeling:
            # The backend derives the selection from the areas or the applied model.
            if (
                self.workflow_operation is None
                or self.selected_object_ids
                or self.selected_entity_ids
                or (self.workflow_operation == "build") != bool(self.subject_area_ids)
                or len(self.subject_area_ids) != len(set(self.subject_area_ids))
            ):
                raise ValueError("Build needs unique selected Subject Areas; Optimize takes none")
        elif self.workflow_operation is not None or self.subject_area_ids:
            raise ValueError("Build and Optimize are available only for Logical and Dimensional")
        entity_workflow = self.project_workflow in {"dimensional", "mapping", "code_generation"}
        selected_ids = self.selected_entity_ids if entity_workflow else self.selected_object_ids
        if (entity_workflow and self.selected_object_ids) or (
            not entity_workflow and self.selected_entity_ids
        ):
            raise ValueError(
                "Select modeled Entities only for Dimensional, Mapping, and Code Generation"
            )
        if len(self.selected_entity_ids) != len(set(self.selected_entity_ids)):
            raise ValueError("Selected Entity IDs must be unique")
        if self.project_workflow == "dimensional" and self.modeled_entity_type != "logical_entity":
            raise ValueError("Dimensional input requires Logical Entities")
        if self.description_targets is not None:
            targets = self.description_targets
            objects = {target.object_id for target in targets}
            attributes = {target.attribute_id is not None for target in targets}
            identities = {(target.object_id, target.attribute_id) for target in targets}
            if (
                self.project_workflow != "metadata_enrichment"
                or objects != set(selected_ids)
                or len(attributes) != 1
                or len(identities) != len(targets)
            ):
                raise ValueError("Select unique Object descriptions or unique Attributes")
        if len(self.selected_object_ids) != len(set(self.selected_object_ids)):
            raise ValueError("Selected Object IDs must be unique")
        normalized_system_codes = [value.casefold() for value in self.selected_system_codes]
        if len(normalized_system_codes) != len(set(normalized_system_codes)):
            raise ValueError("Selected System Codes must be unique")
        if self.project_workflow == "validation":
            if self.selected_object_ids or not self.selected_system_codes:
                raise ValueError("Validation requires only an explicit System selection")
            if self.code_generation_coverage_mode is not None:
                raise ValueError("Code Generation inputs are unavailable for this workflow")
        elif self.project_workflow == "code_generation":
            if self.code_generation_file_layout is None:
                object.__setattr__(self, "code_generation_file_layout", "combined")
            if (
                (self.code_generation_coverage_mode == "selected_targets" and not selected_ids)
                or (self.code_generation_coverage_mode == "all_eligible_targets" and selected_ids)
                or self.code_generation_coverage_mode is None
            ):
                raise ValueError("Code Generation coverage is invalid")
        else:
            if self.selected_system_codes:
                raise ValueError(
                    "System selection is available only for Validation or Code Generation"
                )
            if not selected_ids and not modeling:
                raise ValueError("Selected Object IDs are required")
            if self.code_generation_coverage_mode is not None:
                raise ValueError("Code Generation inputs are unavailable for this workflow")

        if (
            self.code_generation_file_layout is not None
            and self.project_workflow != "code_generation"
        ):
            raise ValueError("File layout is available only for Code Generation")
        if self.project_workflow == "metadata_enrichment" and (
            self.workflow_execution_mode != "one_shot"
        ):
            raise ValueError("Metadata enrichment requires one-shot execution")
        agentic = self.project_workflow in {"code_generation", "validation"} or (
            self.workflow_execution_mode is not None
        )
        requires_mode = self.project_workflow in {
            "subject_area",
            "logical",
            "dimensional",
            "mapping",
        }
        if requires_mode and self.workflow_execution_mode is None:
            raise ValueError("This workflow requires an explicit execution mode")
        if self.project_workflow in {"profiling", "code_generation", "validation"} and (
            self.workflow_execution_mode is not None
        ):
            raise ValueError("This workflow does not accept an execution mode")
        if not agentic and (self.agent is not None or self.prompt_overrides):
            raise ValueError("Deterministic workflows cannot use agent inputs")

        if entity_workflow and (self.modeled_entity_type is None):
            raise ValueError("Code Generation requires a modeled Entity type")
        if self.project_workflow not in {
            "dimensional",
            "mapping",
            "code_generation",
            "validation",
        } and (self.modeled_entity_type is not None):
            raise ValueError("Modeled Entity type is unavailable for this workflow")

        required_mapping_inputs = (
            self.mapping_operation,
            self.mapping_coverage_mode,
            self.mapping_source_system_id,
        )
        mapping_inputs = required_mapping_inputs + (
            self.mapping_object_output_template_id,
            self.mapping_attribute_output_template_id,
        )
        if self.project_workflow == "mapping":
            if self.mapping_targets is not None:
                pairs = {
                    (item.modeled_entity_id, item.source_system_id) for item in self.mapping_targets
                }
                if (
                    self.mapping_operation != "generate"
                    or self.mapping_coverage_mode != "selected_targets"
                    or self.mapping_source_system_id is not None
                    or len(pairs) != len(self.mapping_targets)
                    or {item.modeled_entity_id for item in self.mapping_targets}
                    != set(selected_ids)
                ):
                    raise ValueError(
                        "Mapping requires unique targets matching the selected Objects"
                    )
            elif any(value is None for value in required_mapping_inputs) or len(selected_ids) != 1:
                raise ValueError("Mapping requires one complete target selection")
        elif self.mapping_targets is not None or any(value is not None for value in mapping_inputs):
            raise ValueError("Mapping inputs are unavailable for this workflow")
        if self.requested_batch_id is not None and self.project_workflow not in {
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
    project_revision: int = Field(gt=0)
    selected_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_scope_count: int = Field(gt=0)
    code_generation_coverage_mode: (
        Literal[
            "selected_targets",
            "all_eligible_targets",
        ]
        | None
    )
    created_at: datetime


class WorkflowRunCancellationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: Literal["cancelled"]
    completed_at: datetime
