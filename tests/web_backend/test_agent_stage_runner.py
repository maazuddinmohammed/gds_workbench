from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
    LocalAgentToolDefinition,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentContextPolicy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)


def _plan(*, execution_mode: WorkflowExecutionMode = "one_shot") -> AgentRunPlan:
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="conceptual",
        workflow_execution_mode=execution_mode,
        modeled_entity_type=None,
        selected_scope_digest="a" * 64,
        selected_object_ids=(501, 502),
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-primary",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=1,
        ),
        stages=(
            FrozenAgentStage(
                workflow_stage_id=31,
                stage_code="candidate_authoring",
                stage_order=10,
                prompt_template_version_id=81,
                prompt_template_digest="b" * 64,
                templates=PromptComponentTemplates(
                    system="Model {{model_name}}; preserve {{unknown_rule}}",
                    instruction="Use {{stage_context}}",
                    tool_instruction=None,
                ),
                variables=(
                    PromptVariableDefinition(
                        name="model_name",
                        resolver_key="model.name",
                        data_type="text",
                        is_required=True,
                    ),
                    PromptVariableDefinition(
                        name="stage_context",
                        resolver_key="context.stage",
                        data_type="json",
                        is_required=True,
                    ),
                ),
            ),
        ),
    )


class Executor:
    def __init__(self) -> None:
        self.requests: list[AgentExecutionRequest] = []

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return AgentExecutionResult(
            candidate=cast(JsonValue, {"objects": [{"name": "customer"}]}),
            turn_count=2,
            tool_call_count=0,
        )


class Validator:
    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        assert candidate == {"objects": [{"name": "customer"}]}
        return AgentCandidateValidation(issues=())


class Catalog:
    definitions = (
        LocalAgentToolDefinition(
            name="get_agent_context_manifest",
            description="Return a bounded manifest.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
    )

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        assert tool_name == "get_agent_context_manifest"
        assert arguments == {}
        return {"dataset_counts": {"selected_object": 2}}


@pytest.mark.asyncio
async def test_stage_runner_uses_frozen_prompt_and_allowlisted_variables() -> None:
    executor = Executor()
    runner = AgentStageRunner(
        executor=executor,
        policy=AgentContextPolicy(
            one_shot_max_context_bytes=4096,
            stage_max_context_bytes=4096,
            max_candidate_bytes=4096,
            max_validation_issues=10,
        ),
    )

    outcome = await runner.run(
        plan=_plan(),
        stage_code="candidate_authoring",
        resolver_values={
            "model.name": "Customer 360",
            "context.stage": {"scope_count": 2},
        },
        context=cast(JsonValue, {"scope": [501, 502]}),
        output_schema={"type": "object"},
        allowed_tool_names=(),
        validator=Validator(),
    )

    request = executor.requests[0]
    assert request.workflow == "conceptual"
    assert request.system_prompt == "Model Customer 360; preserve {{unknown_rule}}"
    assert request.instruction_prompt == 'Use {"scope_count":2}'
    assert outcome.warning_codes == ("unknown_prompt_placeholder",)
    assert outcome.attempt_count == 1
    assert "customer" not in repr(outcome)


@pytest.mark.asyncio
async def test_stage_runner_rejects_unknown_stage_without_execution() -> None:
    executor = Executor()
    runner = AgentStageRunner(
        executor=executor,
        policy=AgentContextPolicy(
            one_shot_max_context_bytes=4096,
            stage_max_context_bytes=4096,
            max_candidate_bytes=4096,
            max_validation_issues=10,
        ),
    )

    with pytest.raises(InvalidRequestError, match="unavailable"):
        await runner.run(
            plan=_plan(),
            stage_code="other",
            resolver_values={},
            context=cast(JsonValue, {}),
            output_schema={},
            allowed_tool_names=(),
            validator=Validator(),
        )

    assert executor.requests == []


@pytest.mark.asyncio
async def test_stage_runner_keeps_the_exact_run_local_catalog() -> None:
    executor = Executor()
    runner = AgentStageRunner(
        executor=executor,
        policy=AgentContextPolicy(
            one_shot_max_context_bytes=4096,
            stage_max_context_bytes=4096,
            max_candidate_bytes=4096,
            max_validation_issues=10,
        ),
    )
    catalog = Catalog()

    await runner.run(
        plan=_plan(execution_mode="tool_assisted"),
        stage_code="candidate_authoring",
        resolver_values={
            "model.name": "Customer 360",
            "context.stage": {"dataset_counts": {"selected_object": 2}},
        },
        context={"dataset_counts": {"selected_object": 2}},
        output_schema={"type": "object"},
        allowed_tool_names=("get_agent_context_manifest",),
        local_tool_catalog=catalog,
        validator=Validator(),
    )

    request = executor.requests[0]
    assert request.execution_mode == "tool_assisted"
    assert request.local_tool_catalog is catalog
    assert request.allowed_tool_names == ("get_agent_context_manifest",)
