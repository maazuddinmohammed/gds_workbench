"""Execute one frozen agent stage through the shared repair contract."""

from __future__ import annotations

from collections.abc import Mapping

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    LocalAgentToolCatalog,
)
from gds_workbench_api.prompt_rendering import render_prompt

from .plan import AgentRunPlan
from .prompt_inputs import project_prompt_input_values
from .repair import (
    AgentCandidateFinalValidation,
    AgentCandidateValidator,
    AgentContextPolicy,
    AgentExecutor,
    ValidationRepairRunner,
)
from .tool_configuration import configure_tools


class AgentStageOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate: JsonValue = Field(repr=False)
    warning_codes: tuple[str, ...] = Field(max_length=20)
    unknown_placeholders: tuple[str, ...] = Field(max_length=100)
    attempt_count: int = Field(ge=1, le=6)
    was_repaired: bool
    turn_count: int = Field(ge=1, le=300)
    tool_call_count: int = Field(ge=0, le=6_000)


class AgentStageRunner:
    """Render one snapshotted stage and return only a fully validated candidate."""

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        policy: AgentContextPolicy,
    ) -> None:
        self._repair = ValidationRepairRunner(executor=executor, policy=policy)

    async def run(
        self,
        *,
        plan: AgentRunPlan,
        stage_code: str,
        resolver_values: Mapping[str, object],
        context: JsonValue,
        output_schema: dict[str, JsonValue],
        allowed_tool_names: tuple[str, ...],
        validator: AgentCandidateValidator,
        local_tool_catalog: LocalAgentToolCatalog | None = None,
        max_candidate_bytes: int | None = None,
        final_validation: AgentCandidateFinalValidation | None = None,
        prompt_workflow: str | None = None,
    ) -> AgentStageOutcome:
        stage = next(
            (
                candidate
                for candidate in plan.stages
                if candidate.stage_code == stage_code
                and (prompt_workflow is None or candidate.prompt_workflow == prompt_workflow)
            ),
            None,
        )
        if stage is None:
            raise InvalidRequestError("The frozen agent stage is unavailable.")

        local_tool_catalog = configure_tools(
            local_tool_catalog,
            stage.agent_tool_names,
            workflow=stage.prompt_workflow or plan.model_workflow,
            execution_mode=plan.workflow_execution_mode,
        )
        if stage.agent_tool_names is not None and local_tool_catalog is not None:
            allowed_tool_names = tuple(tool.name for tool in local_tool_catalog.definitions)

        rendered = render_prompt(
            templates=stage.templates,
            variables=stage.variables,
            resolver_values=project_prompt_input_values(
                plan=plan,
                stage=stage,
                context=context,
                resolver_values=resolver_values,
                tool_definitions=local_tool_catalog.definitions if local_tool_catalog else (),
                precomputed_values=getattr(local_tool_catalog, "prompt_values", None),
            ),
        )
        workflow = (
            "analysis_inference" if plan.model_workflow == "analysis" else plan.model_workflow
        )
        result = await self._repair.run(
            request=AgentExecutionRequest(
                workflow_run_id=plan.workflow_run_id,
                workflow=workflow,
                stage=stage.stage_code,
                execution_mode=plan.workflow_execution_mode or "one_shot",
                selection=plan.selection,
                system_prompt=rendered.system,
                instruction_prompt=rendered.instruction,
                tool_instruction=rendered.tool_instruction,
                context=context,
                output_schema=output_schema,
                allowed_tool_names=allowed_tool_names,
                local_tool_catalog=local_tool_catalog,
            ),
            validator=validator,
            max_candidate_bytes=max_candidate_bytes,
            final_validation=final_validation,
        )
        return AgentStageOutcome(
            candidate=result.candidate,
            warning_codes=rendered.warning_codes,
            unknown_placeholders=rendered.unknown_placeholders,
            attempt_count=result.attempt_count,
            was_repaired=result.was_repaired,
            turn_count=result.turn_count,
            tool_call_count=result.tool_call_count,
        )
