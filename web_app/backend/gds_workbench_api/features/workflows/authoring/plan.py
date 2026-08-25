"""Load one immutable, tenant-fenced agent run plan."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, LiteralString, Protocol, cast
from uuid import UUID

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)

type ModelWorkflow = Literal[
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
type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]


class AgentRunPlanTransaction(Protocol):
    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]: ...


_RUN_PLAN_SQL: LiteralString = """
SELECT run.workflow_run_id,
       run.model_id,
       run.correlation_id,
       run.model_revision,
       run.model_workflow,
       run.workflow_execution_mode,
       run.modeled_entity_type,
       run.code_generation_coverage_mode,
       run.sql_generation_guide_id,
       run.sql_generation_guide_version_id,
       run.sql_generation_guide_digest,
       run.selected_scope_digest,
       run.selected_scope_count,
       run.agent_sdk_code,
       run.agent_provider_code,
       run.agent_model_code,
       run.reasoning_effort_code,
       run.max_turns,
       run.validation_retry_count,
       stage.workflow_stage_id,
       stage.workflow_stage_code,
       stage.workflow_stage_order,
       version.prompt_template_version_id,
       snapshot.prompt_template_digest,
       version.system_prompt_template,
       version.instruction_prompt_template,
       version.tool_instruction_prompt_template,
       (
           SELECT count(*)::INTEGER
             FROM application.workflow_run_prompt_snapshot AS expected_snapshot
            WHERE expected_snapshot.workflow_run_id = run.workflow_run_id
       ) AS expected_stage_count,
       variable.workflow_stage_variable_id,
       variable.workflow_stage_variable_name,
       variable.workflow_stage_variable_resolver_key,
       variable.workflow_stage_variable_data_type,
       variable.workflow_stage_variable_is_required,
       variable.workflow_stage_variable_order
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
   AND target_model.model_revision = run.model_revision
  JOIN application.workflow_run_prompt_snapshot AS snapshot
    ON snapshot.workflow_run_id = run.workflow_run_id
   AND snapshot.model_id = run.model_id
  JOIN application.prompt_template_version AS version
    ON version.prompt_template_version_id = snapshot.prompt_template_version_id
   AND version.workflow_stage_id = snapshot.workflow_stage_id
   AND version.prompt_template_digest = snapshot.prompt_template_digest
  JOIN application.workflow_stage AS stage
    ON stage.workflow_stage_id = snapshot.workflow_stage_id
   AND stage.model_workflow = run.model_workflow
   AND stage.workflow_stage_is_agentic
   AND (
       stage.workflow_execution_mode = run.workflow_execution_mode
       OR (
           stage.workflow_execution_mode IS NULL
           AND run.workflow_execution_mode IS NULL
       )
   )
  LEFT JOIN application.workflow_stage_variable AS variable
    ON variable.workflow_stage_id = stage.workflow_stage_id
   AND variable.is_active
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND run.workflow_run_state = 'running'
 ORDER BY stage.workflow_stage_order,
          stage.workflow_stage_id,
          variable.workflow_stage_variable_order NULLS LAST,
          variable.workflow_stage_variable_id NULLS LAST
"""

_RUN_SELECTION_SQL: LiteralString = """
SELECT selection.object_id,
       selection.selection_order
  FROM application.workflow_run_object_selection AS selection
  JOIN application.workflow_run AS run
    ON run.workflow_run_id = selection.workflow_run_id
   AND run.model_id = selection.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
 WHERE selection.model_id = %s
   AND selection.workflow_run_id = %s
   AND run.workflow_run_state = 'running'
 ORDER BY selection.selection_order,
          selection.workflow_run_object_selection_id
"""


class AgentRunPlanUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_run_plan_unavailable",
            message="The frozen agent run plan is unavailable or incomplete.",
        )


class FrozenAgentStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workflow_stage_id: int = Field(gt=0)
    stage_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    stage_order: int = Field(gt=0)
    prompt_template_version_id: int = Field(gt=0)
    prompt_template_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    templates: PromptComponentTemplates = Field(repr=False)
    variables: tuple[PromptVariableDefinition, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_variables(self) -> FrozenAgentStage:
        names = [variable.name for variable in self.variables]
        resolvers = [variable.resolver_key for variable in self.variables]
        if len(names) != len(set(names)) or len(resolvers) != len(set(resolvers)):
            raise ValueError("Prompt variable definitions must be unique")
        return self


class AgentRunPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    correlation_id: UUID
    model_revision: int = Field(ge=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None
    modeled_entity_type: ModeledEntityType | None
    code_generation_coverage_mode: (
        Literal[
            "selected_targets",
            "all_eligible_targets",
        ]
        | None
    ) = None
    sql_generation_guide_id: int | None = Field(default=None, gt=0)
    sql_generation_guide_version_id: int | None = Field(default=None, gt=0)
    sql_generation_guide_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    selected_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_object_ids: tuple[int, ...] = Field(min_length=1)
    selection: AgentRunSelection
    stages: tuple[FrozenAgentStage, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_plan(self) -> AgentRunPlan:
        code_generation_snapshot = (
            self.code_generation_coverage_mode,
            self.sql_generation_guide_id,
            self.sql_generation_guide_version_id,
            self.sql_generation_guide_digest,
        )
        if self.model_workflow == "code_generation":
            if any(value is None for value in code_generation_snapshot):
                raise ValueError("Code Generation plan snapshot is incomplete")
        elif any(value is not None for value in code_generation_snapshot):
            raise ValueError("Code Generation plan snapshot is unavailable")
        if len(self.selected_object_ids) != len(set(self.selected_object_ids)):
            raise ValueError("Selected Objects must be unique")
        stage_ids = [stage.workflow_stage_id for stage in self.stages]
        stage_orders = [stage.stage_order for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)) or len(stage_orders) != len(set(stage_orders)):
            raise ValueError("Agent stages must be unique")
        return self


class PostgresAgentRunPlanRepository:
    """Read one frozen plan from fixed PostgreSQL queries or fail closed."""

    async def load(
        self,
        transaction: AgentRunPlanTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan:
        parameters = (tenant_id, model_id, workflow_run_id)
        rows = await transaction.fetch_all(_RUN_PLAN_SQL, parameters)
        selection_rows = await transaction.fetch_all(_RUN_SELECTION_SQL, parameters)
        try:
            return _assemble_plan(rows=rows, selection_rows=selection_rows)
        except AgentRunPlanUnavailableError:
            raise
        except Exception:
            raise AgentRunPlanUnavailableError() from None


def _assemble_plan(
    *,
    rows: Sequence[dict[str, Any]],
    selection_rows: Sequence[dict[str, Any]],
) -> AgentRunPlan:
    if not rows or not selection_rows:
        raise AgentRunPlanUnavailableError()

    first = rows[0]
    expected_stage_count = _required_int(first, "expected_stage_count")
    selected_scope_count = _required_int(first, "selected_scope_count")
    if expected_stage_count < 1 or selected_scope_count < 1:
        raise AgentRunPlanUnavailableError()

    selected_object_ids: list[int] = []
    for expected_order, row in enumerate(selection_rows, start=1):
        if _required_int(row, "selection_order") != expected_order:
            raise AgentRunPlanUnavailableError()
        selected_object_ids.append(_required_int(row, "object_id"))
    if len(selected_object_ids) != selected_scope_count or len(selected_object_ids) != len(
        set(selected_object_ids)
    ):
        raise AgentRunPlanUnavailableError()

    grouped: dict[int, list[dict[str, Any]]] = {}
    identity_keys = (
        "workflow_run_id",
        "model_id",
        "correlation_id",
        "model_revision",
        "model_workflow",
        "workflow_execution_mode",
        "modeled_entity_type",
        "code_generation_coverage_mode",
        "sql_generation_guide_id",
        "sql_generation_guide_version_id",
        "sql_generation_guide_digest",
        "selected_scope_digest",
        "selected_scope_count",
        "agent_sdk_code",
        "agent_provider_code",
        "agent_model_code",
        "reasoning_effort_code",
        "max_turns",
        "validation_retry_count",
        "expected_stage_count",
    )
    for row in rows:
        if any(row.get(key) != first.get(key) for key in identity_keys):
            raise AgentRunPlanUnavailableError()
        stage_id = _required_int(row, "workflow_stage_id")
        grouped.setdefault(stage_id, []).append(row)
    if len(grouped) != expected_stage_count:
        raise AgentRunPlanUnavailableError()

    stages: list[FrozenAgentStage] = []
    for stage_rows in grouped.values():
        stage_first = stage_rows[0]
        stage_identity_keys = (
            "workflow_stage_code",
            "workflow_stage_order",
            "prompt_template_version_id",
            "prompt_template_digest",
            "system_prompt_template",
            "instruction_prompt_template",
            "tool_instruction_prompt_template",
        )
        if any(
            row.get(key) != stage_first.get(key)
            for row in stage_rows
            for key in stage_identity_keys
        ):
            raise AgentRunPlanUnavailableError()

        variables: list[PromptVariableDefinition] = []
        variable_orders: list[int] = []
        for row in stage_rows:
            variable_id = row.get("workflow_stage_variable_id")
            if variable_id is None:
                if len(stage_rows) != 1:
                    raise AgentRunPlanUnavailableError()
                continue
            if isinstance(variable_id, bool) or not isinstance(variable_id, int):
                raise AgentRunPlanUnavailableError()
            variable_orders.append(_required_int(row, "workflow_stage_variable_order"))
            variables.append(
                PromptVariableDefinition(
                    name=_required_str(row, "workflow_stage_variable_name"),
                    resolver_key=_required_str(
                        row,
                        "workflow_stage_variable_resolver_key",
                    ),
                    data_type=cast(
                        Any,
                        _required_str(row, "workflow_stage_variable_data_type"),
                    ),
                    is_required=_required_bool(
                        row,
                        "workflow_stage_variable_is_required",
                    ),
                )
            )
        if variable_orders and variable_orders != sorted(variable_orders):
            raise AgentRunPlanUnavailableError()

        stages.append(
            FrozenAgentStage(
                workflow_stage_id=_required_int(stage_first, "workflow_stage_id"),
                stage_code=_required_str(stage_first, "workflow_stage_code"),
                stage_order=_required_int(stage_first, "workflow_stage_order"),
                prompt_template_version_id=_required_int(
                    stage_first,
                    "prompt_template_version_id",
                ),
                prompt_template_digest=_required_str(
                    stage_first,
                    "prompt_template_digest",
                ),
                templates=PromptComponentTemplates(
                    system=_required_str(stage_first, "system_prompt_template"),
                    instruction=_required_str(
                        stage_first,
                        "instruction_prompt_template",
                    ),
                    tool_instruction=_optional_str(
                        stage_first,
                        "tool_instruction_prompt_template",
                    ),
                ),
                variables=tuple(variables),
            )
        )
    stages.sort(key=lambda stage: (stage.stage_order, stage.workflow_stage_id))

    return AgentRunPlan(
        workflow_run_id=_required_int(first, "workflow_run_id"),
        model_id=_required_int(first, "model_id"),
        correlation_id=_required_uuid(first, "correlation_id"),
        model_revision=_required_int(first, "model_revision"),
        model_workflow=cast(ModelWorkflow, _required_str(first, "model_workflow")),
        workflow_execution_mode=cast(
            WorkflowExecutionMode | None,
            _optional_str(first, "workflow_execution_mode"),
        ),
        modeled_entity_type=cast(
            ModeledEntityType | None,
            _optional_str(first, "modeled_entity_type"),
        ),
        code_generation_coverage_mode=cast(
            Literal["selected_targets", "all_eligible_targets"] | None,
            _optional_str(first, "code_generation_coverage_mode"),
        ),
        sql_generation_guide_id=_optional_positive_int(
            first,
            "sql_generation_guide_id",
        ),
        sql_generation_guide_version_id=_optional_positive_int(
            first,
            "sql_generation_guide_version_id",
        ),
        sql_generation_guide_digest=_optional_str(
            first,
            "sql_generation_guide_digest",
        ),
        selected_scope_digest=_required_str(first, "selected_scope_digest"),
        selected_object_ids=tuple(selected_object_ids),
        selection=AgentRunSelection(
            sdk_code=_required_str(first, "agent_sdk_code"),
            provider_code=_required_str(first, "agent_provider_code"),
            model_code=_required_str(first, "agent_model_code"),
            reasoning_effort_code=_required_str(first, "reasoning_effort_code"),
            max_turns=_required_int(first, "max_turns"),
            validation_retry_count=_nonnegative_int(
                first,
                "validation_retry_count",
            ),
        ),
        stages=tuple(stages),
    )


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AgentRunPlanUnavailableError()
    return value


def _nonnegative_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentRunPlanUnavailableError()
    return value


def _optional_positive_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    return _required_int(row, key)


def _required_bool(row: dict[str, Any], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise AgentRunPlanUnavailableError()
    return value


def _required_uuid(row: dict[str, Any], key: str) -> UUID:
    value = row.get(key)
    if not isinstance(value, UUID):
        raise AgentRunPlanUnavailableError()
    return value


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AgentRunPlanUnavailableError()
    return value


def _optional_str(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return _required_str(row, key)
