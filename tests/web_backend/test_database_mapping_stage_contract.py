"""Keep installed Mapping stages/prompts executable by the shared runtime."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.features.mapping.service import DatabaseMappingExecutor
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import AgentWorkflowTerminalResult
from gds_workbench_api.features.workflows.authoring.plan import (
    FrozenAgentStage,
    WorkflowExecutionMode,
)
from gds_workbench_api.integrations.agents import LocalFakeAgentAdapter
from gds_workbench_api.prompt_rendering import PromptComponentTemplates, PromptVariableDefinition
from mapping_fixtures import mapping_preparation

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)


@pytest.fixture(scope="module")
def mapping_seed_database() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
        _seed_super_admin(database)
        _apply_sql(database, _render_seed())
        yield database


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ('one_shot', 'tool_assisted'))
async def test_installed_mapping_stages_execute_one_complete_candidate(
    mapping_seed_database: DisposablePostgres,
    mode: WorkflowExecutionMode,
) -> None:
    with mapping_seed_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT stage.workflow_stage_id, stage.workflow_stage_code,
                   stage.workflow_stage_order, version.prompt_template_version_id,
                   version.prompt_template_digest, version.system_prompt_template,
                   version.instruction_prompt_template, version.tool_instruction_prompt_template
              FROM application.workflow_stage AS stage
              JOIN application.prompt_assignment AS assignment
                ON assignment.workflow_stage_id = stage.workflow_stage_id
               AND assignment.prompt_assignment_scope = 'global_default'
               AND assignment.is_active
              JOIN application.prompt_template_version AS version
                ON version.prompt_template_version_id = assignment.prompt_template_version_id
             WHERE stage.model_workflow = 'mapping'
               AND stage.workflow_execution_mode = %s
               AND stage.workflow_stage_is_agentic AND stage.is_active
             ORDER BY stage.workflow_stage_order
            """,
            (mode,),
        ).fetchall()
        stages: list[FrozenAgentStage] = []
        for row in rows:
            variables = connection.execute(
                """
                SELECT workflow_stage_variable_name AS name,
                       workflow_stage_variable_resolver_key AS resolver_key,
                       workflow_stage_variable_data_type AS data_type,
                       workflow_stage_variable_is_required AS is_required
                  FROM application.workflow_stage_variable
                 WHERE workflow_stage_id = %s AND is_active
                 ORDER BY workflow_stage_variable_order
                """,
                (row["workflow_stage_id"],),
            ).fetchall()
            stages.append(
                FrozenAgentStage(
                    workflow_stage_id=row["workflow_stage_id"],
                    stage_code=row["workflow_stage_code"],
                    stage_order=row["workflow_stage_order"],
                    prompt_template_version_id=row["prompt_template_version_id"],
                    prompt_template_digest=row["prompt_template_digest"],
                    templates=PromptComponentTemplates(
                        system=row["system_prompt_template"],
                        instruction=row["instruction_prompt_template"],
                        tool_instruction=row["tool_instruction_prompt_template"],
                    ),
                    variables=tuple(
                        PromptVariableDefinition.model_validate(item) for item in variables
                    ),
                )
            )

    preparation = mapping_preparation(execution_mode=mode)
    preparation = preparation.model_copy(
        update={
            "plan": preparation.plan.model_copy(
                update={
                    "agent_plan": preparation.plan.agent_plan.model_copy(
                        update={"stages": tuple(stages)}
                    ),
                }
            )
        }
    )
    preparation_service = AsyncMock()
    preparation_service.prepare.return_value = preparation
    adapter = LocalFakeAgentAdapter(sdk_code=preparation.plan.agent_plan.selection.sdk_code)
    agent = AsyncMock()
    agent.execute.side_effect = adapter.execute
    lifecycle = AsyncMock()
    handoff = AsyncMock()
    now = datetime.now(UTC)
    receipt = WorkflowChangeSetHandoffResult(
        model_id=18,
        workflow_run_id=1048,
        model_change_set_id=uuid4(),
        replayed=False,
        draft_revision=2,
        candidate_digest="a" * 64,
        staged_record_count=2,
        validated_at=now,
    )
    handoff.finalize.return_value = WorkflowChangeSetFinalizationResult(
        handoff=receipt,
        completion=AgentWorkflowTerminalResult(
            changed=True,
            workflow_run_id=1048,
            workflow_run_state="completed",
            completed_at=now,
        ),
    )
    executor = DatabaseMappingExecutor(
        preparation_service=preparation_service,
        agent_executor=agent,
        handoff=handoff,
        no_op=AsyncMock(),
        lifecycle=lifecycle,
    )
    result = await executor.execute_started(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN, entra_tenant_id=uuid4(), entra_object_id=uuid4()
        ),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=uuid4(),
        expected_model_revision=7,
    )

    assert result == receipt
    handoff.finalize.assert_awaited_once()
    lifecycle.fail.assert_not_awaited()
    called_stages = [call.args[0].stage for call in agent.execute.await_args_list]
    assert called_stages == (
        ["mapping_authoring"]
    )
    assert handoff.finalize.await_args is not None
    changes = handoff.finalize.await_args.kwargs["changes"]
    assert [change.dataset for change in changes] == ["mapping_object", "mapping_attribute"]
    assert changes[1].records[0]["modeled_attribute_name"] == "CustomerID"
