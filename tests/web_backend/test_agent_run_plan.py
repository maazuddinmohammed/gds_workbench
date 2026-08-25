from __future__ import annotations

from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError

from gds_workbench_api.features.workflows.authoring.plan import (
    PostgresAgentRunPlanRepository,
)


def _stage_row(
    *,
    variable_id: int | None,
    variable_name: str | None = None,
) -> dict[str, Any]:
    return {
        "workflow_run_id": 1048,
        "model_id": 18,
        "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
        "model_revision": 7,
        "model_workflow": "conceptual",
        "workflow_execution_mode": "one_shot",
        "modeled_entity_type": None,
        "selected_scope_digest": "a" * 64,
        "selected_scope_count": 2,
        "agent_sdk_code": "langchain_create_agent",
        "agent_provider_code": "microsoft_foundry",
        "agent_model_code": "gpt-5.6",
        "reasoning_effort_code": "medium",
        "max_turns": 8,
        "validation_retry_count": 2,
        "workflow_stage_id": 31,
        "workflow_stage_code": "candidate_authoring",
        "workflow_stage_order": 10,
        "prompt_template_version_id": 81,
        "prompt_template_digest": "b" * 64,
        "system_prompt_template": "sensitive system {{model_name}}",
        "instruction_prompt_template": "sensitive instruction {{stage_context}}",
        "tool_instruction_prompt_template": None,
        "expected_stage_count": 1,
        "workflow_stage_variable_id": variable_id,
        "workflow_stage_variable_name": variable_name,
        "workflow_stage_variable_resolver_key": (
            None if variable_id is None else f"context.{variable_name}"
        ),
        "workflow_stage_variable_data_type": (None if variable_id is None else "json"),
        "workflow_stage_variable_is_required": variable_id is not None,
        "workflow_stage_variable_order": variable_id,
    }


class PlanTransaction:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        selection: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows = (
            rows
            if rows is not None
            else [
                _stage_row(variable_id=1, variable_name="model_name"),
                _stage_row(variable_id=2, variable_name="stage_context"),
            ]
        )
        self.selection = (
            selection
            if selection is not None
            else [
                {"object_id": 501, "selection_order": 1},
                {"object_id": 502, "selection_order": 2},
            ]
        )

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert parameters == (7, 18, 1048)
        if "workflow_run_object_selection" in query:
            return self.selection
        assert "workflow_run_prompt_snapshot" in query
        assert "run.workflow_run_state = 'running'" in query
        return self.rows


@pytest.mark.asyncio
async def test_repository_loads_frozen_prompts_variables_and_exact_selection() -> None:
    plan = await PostgresAgentRunPlanRepository().load(
        PlanTransaction(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
    )

    assert plan.workflow_run_id == 1048
    assert plan.correlation_id == UUID("33333333-3333-3333-3333-333333333333")
    assert plan.model_revision == 7
    assert plan.selected_object_ids == (501, 502)
    assert plan.selection.model_code == "gpt-5.6"
    assert [stage.stage_code for stage in plan.stages] == ["candidate_authoring"]
    assert [variable.name for variable in plan.stages[0].variables] == [
        "model_name",
        "stage_context",
    ]
    representation = repr(plan)
    assert "sensitive system" not in representation
    assert "sensitive instruction" not in representation


@pytest.mark.asyncio
async def test_repository_rejects_incomplete_prompt_stage_coverage_safely() -> None:
    rows = [_stage_row(variable_id=None)]
    rows[0]["expected_stage_count"] = 2

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentRunPlanRepository().load(
            PlanTransaction(rows=rows),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
        )

    assert captured.value.code == "agent_run_plan_unavailable"
    assert "sensitive" not in str(captured.value)


@pytest.mark.asyncio
async def test_repository_rejects_changed_or_incomplete_object_selection() -> None:
    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentRunPlanRepository().load(
            PlanTransaction(selection=[{"object_id": 501, "selection_order": 1}]),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
        )

    assert captured.value.code == "agent_run_plan_unavailable"


@pytest.mark.asyncio
async def test_repository_rejects_inconsistent_frozen_correlation() -> None:
    rows = [
        _stage_row(variable_id=1, variable_name="model_name"),
        _stage_row(variable_id=2, variable_name="stage_context"),
    ]
    rows[1]["correlation_id"] = UUID("44444444-4444-4444-4444-444444444444")

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentRunPlanRepository().load(
            PlanTransaction(rows=rows),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
        )

    assert captured.value.code == "agent_run_plan_unavailable"
