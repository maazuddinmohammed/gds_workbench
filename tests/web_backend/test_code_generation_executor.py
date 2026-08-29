from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import (
    DependencyUnavailableError,
    InvalidRequestError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.code_generation.context import (
    CodeGenerationExecutionContext,
)
from gds_workbench_api.features.code_generation.service import (
    CodeGenerationExecutionFailedError,
    DatabaseCodeGenerationExecutor,
)
from gds_workbench_api.features.code_generation.storage import (
    CodeGenerationArtifactContext,
    GeneratedSqlStorageResult,
    StoredGeneratedSqlArtifact,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.features.workflows.authoring.repair import AgentContextPolicy
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from pydantic import JsonValue

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _plan(*, retry_count: int = 1) -> AgentRunPlan:
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="code_generation",
        workflow_execution_mode=None,
        modeled_entity_type="logical_entity",
        code_generation_coverage_mode="selected_targets",
        sql_generation_guide_id=90,
        sql_generation_guide_version_id=91,
        sql_generation_guide_digest="9" * 64,
        selected_scope_digest="a" * 64,
        selected_object_ids=(501, 502),
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-primary",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=retry_count,
        ),
        stages=(
            FrozenAgentStage(
                workflow_stage_id=31,
                stage_code="sql_generation",
                stage_order=10,
                prompt_template_version_id=81,
                prompt_template_digest="b" * 64,
                templates=PromptComponentTemplates(
                    system="Generate SQL only.",
                    instruction=(
                        "Use {{stage_context}} and guide {{sql_generation_guide}}."
                    ),
                ),
                variables=(
                    PromptVariableDefinition(
                        name="stage_context",
                        resolver_key=(
                            "workflow.code_generation.common.sql_generation.context"
                        ),
                        data_type="json",
                        is_required=True,
                    ),
                    PromptVariableDefinition(
                        name="sql_generation_guide",
                        resolver_key="workflow.code_generation.sql_generation_guide",
                        data_type="text",
                        is_required=True,
                    ),
                ),
            ),
        ),
    )


def _execution_context() -> CodeGenerationExecutionContext:
    return CodeGenerationExecutionContext(
        targets=(
            CodeGenerationArtifactContext(
                target_ref="target_1",
                object_id=501,
                mapping_context_digest="c" * 64,
                source_context_digest="d" * 64,
                sql_generation_guide_version_id=91,
            ),
            CodeGenerationArtifactContext(
                target_ref="target_2",
                object_id=502,
                mapping_context_digest="e" * 64,
                source_context_digest="f" * 64,
                sql_generation_guide_version_id=91,
            ),
        ),
        agent_context=cast(
            JsonValue,
            {
                "targets": [
                    {
                        "target_ref": "target_1",
                        "context": {
                            "guide": {"content": "Use deterministic MERGE SQL."},
                            "object_mappings": [{"kind": "direct"}],
                        },
                    },
                    {
                        "target_ref": "target_2",
                        "context": {
                            "guide": {"content": "Use deterministic MERGE SQL."},
                            "object_mappings": [{"kind": "join"}],
                        },
                    },
                ]
            },
        ),
    )


@dataclass
class _Authorizer:
    calls: list[tuple[int, ToolPolicy]] = field(
        default_factory=lambda: list[tuple[int, ToolPolicy]]()
    )

    async def authorize_tenant(
        self,
        transaction: object,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        policy: ToolPolicy,
    ) -> object:
        del transaction
        assert principal == _principal()
        self.calls.append((tenant_id, policy))
        return object()


@dataclass
class _Database:
    transaction: object = field(default_factory=object)
    write_isolations: list[ReadIsolation] = field(
        default_factory=lambda: list[ReadIsolation]()
    )

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[WriteTransaction]:
        self.write_isolations.append(isolation)
        yield cast(WriteTransaction, self.transaction)


@dataclass
class _PlanRepository:
    plan: AgentRunPlan = field(default_factory=_plan)
    calls: list[tuple[int, int, int]] = field(
        default_factory=lambda: list[tuple[int, int, int]]()
    )

    async def load(
        self,
        transaction: object,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan:
        del transaction
        self.calls.append((tenant_id, model_id, workflow_run_id))
        return self.plan


@dataclass
class _ContextRepository:
    context: CodeGenerationExecutionContext = field(default_factory=_execution_context)
    calls: list[tuple[int, int]] = field(
        default_factory=lambda: list[tuple[int, int]]()
    )

    async def load(
        self,
        transaction: object,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> CodeGenerationExecutionContext:
        del transaction
        self.calls.append((tenant_id, plan.workflow_run_id))
        return self.context


@dataclass
class _AgentExecutor:
    responses: list[JsonValue | Exception]
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return AgentExecutionResult(
            candidate=response,
            turn_count=2,
            tool_call_count=0,
        )


@dataclass
class _Storage:
    state: str = "completed"
    calls: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())

    async def store(
        self, principal: RequestPrincipal, **values: Any
    ) -> GeneratedSqlStorageResult:
        assert principal == _principal()
        self.calls.append(values)
        artifacts = values["artifacts"]
        return GeneratedSqlStorageResult(
            workflow_run_id=values["workflow_run_id"],
            workflow_run_state=cast(Any, self.state),
            artifact_count=len(artifacts),
            items=tuple(
                StoredGeneratedSqlArtifact(
                    generated_sql_artifact_id=900 + index,
                    object_id=artifact.object_id,
                    generated_sql_digest="9" * 64,
                )
                for index, artifact in enumerate(artifacts, start=1)
            ),
        )


@dataclass
class _Lifecycle:
    events: list[AgentWorkflowEvent] = field(
        default_factory=lambda: list[AgentWorkflowEvent]()
    )
    failed: tuple[str, str] | None = None
    claim_tokens: list[UUID] = field(default_factory=lambda: list[UUID]())
    fail_error: Exception | None = None

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None:
        assert principal == _principal()
        assert (workflow_run_id, expected_model_revision) == (1048, 7)
        self.claim_tokens.append(workflow_run_claim_token)
        self.events.append(event)

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> AgentWorkflowTerminalResult:
        assert principal == _principal()
        assert (workflow_run_id, expected_model_revision) == (1048, 7)
        self.claim_tokens.append(workflow_run_claim_token)
        self.failed = (failure_code, safe_failure_message)
        if self.fail_error is not None:
            raise self.fail_error
        return AgentWorkflowTerminalResult(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="failed",
            completed_at=datetime.now(UTC),
        )


def _service(
    *,
    executor: _AgentExecutor,
    storage: _Storage | None = None,
    lifecycle: _Lifecycle | None = None,
    plan_repository: _PlanRepository | None = None,
) -> tuple[
    DatabaseCodeGenerationExecutor,
    _Database,
    _Authorizer,
    _Storage,
    _Lifecycle,
]:
    database = _Database()
    authorizer = _Authorizer()
    selected_storage = storage or _Storage()
    selected_lifecycle = lifecycle or _Lifecycle()
    return (
        DatabaseCodeGenerationExecutor(
            database=database,
            authorizer=cast(Any, authorizer),
            agent_executor=executor,
            storage=selected_storage,
            lifecycle=selected_lifecycle,
            plan_repository=plan_repository or _PlanRepository(),
            context_repository=_ContextRepository(),
            context_policy=AgentContextPolicy(
                one_shot_max_context_bytes=64 * 1024,
                stage_max_context_bytes=64 * 1024,
                max_candidate_bytes=64 * 1024,
                max_validation_issues=20,
            ),
        ),
        database,
        authorizer,
        selected_storage,
        selected_lifecycle,
    )


@pytest.mark.asyncio
async def test_executor_renders_selected_guide_into_each_agent_instruction() -> None:
    plan = _plan()
    stage = plan.stages[0]
    seeded_stage = stage.model_copy(
        update={
            "templates": stage.templates.model_copy(
                update={
                    "instruction": (
                        "Follow the selected SQL generation guide.\n"
                        "{{ sql_generation_guide }}"
                    )
                }
            )
        }
    )
    agent = _AgentExecutor(
        responses=[
            cast(
                JsonValue,
                {
                    "artifacts": [
                        {
                            "target_ref": f"target_{position}",
                            "generated_sql": f"SELECT {position};",
                        }
                    ]
                },
            )
            for position in (1, 2)
        ]
    )
    service, *_ = _service(
        executor=agent,
        plan_repository=_PlanRepository(
            plan=plan.model_copy(update={"stages": (seeded_stage,)})
        ),
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    agent_context = cast(dict[str, Any], _execution_context().agent_context)
    targets = cast(list[dict[str, Any]], agent_context["targets"])
    target_context = cast(dict[str, Any], targets[0]["context"])
    guide = cast(dict[str, Any], target_context["guide"])["content"]
    rendering_checks = tuple(
        (
            request.instruction_prompt.count(guide),
            "{{ sql_generation_guide }}" in request.instruction_prompt,
        )
        for request in agent.requests
    )

    assert rendering_checks == ((1, False), (1, False))


@pytest.mark.asyncio
async def test_executor_uses_frozen_plan_exact_context_and_atomic_storage() -> None:
    agent = _AgentExecutor(
        responses=[
            cast(
                JsonValue,
                {
                    "artifacts": [
                        {"target_ref": "target_1", "generated_sql": "SELECT 1;"}
                    ]
                },
            ),
            cast(
                JsonValue,
                {
                    "artifacts": [
                        {"target_ref": "target_2", "generated_sql": "SELECT 2;"}
                    ]
                },
            ),
        ]
    )
    service, database, authorizer, storage, lifecycle = _service(executor=agent)

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert database.write_isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_MODEL_WRITE)]
    assert len(agent.requests) == 2
    request = agent.requests[0]
    assert request.workflow == "code_generation"
    assert request.execution_mode == "one_shot"
    assert request.selection == _plan().selection
    assert request.allowed_tool_names == ()
    assert "Use deterministic MERGE SQL." in request.instruction_prompt
    execution_context = _execution_context().agent_context
    assert isinstance(execution_context, dict)
    execution_targets = execution_context.get("targets")
    assert isinstance(execution_targets, list)
    assert request.context == {
        "original_context": {"targets": [execution_targets[0]]},
        "repair": None,
    }
    assert len(storage.calls) == 1
    assert storage.calls[0]["modeled_entity_type"] == "logical_entity"
    assert [item.target_ref for item in storage.calls[0]["artifacts"]] == [
        "target_1",
        "target_2",
    ]
    assert storage.calls[0]["contexts"] == _execution_context().targets
    assert storage.calls[0]["workflow_run_claim_token"] == _CLAIM_TOKEN
    assert result.artifact_count == 2
    assert "SELECT" not in repr(result)
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.attempt, event.stage) for event in lifecycle.events
    ] == [
        (2, 1, "code_generation.sql_generation"),
        (3, 1, "code_generation.sql_generation"),
        (4, 1, "code_generation.sql_generation"),
    ]
    assert lifecycle.claim_tokens == [_CLAIM_TOKEN, _CLAIM_TOKEN, _CLAIM_TOKEN]


@pytest.mark.asyncio
async def test_executor_uses_common_validation_repair_before_one_atomic_store() -> None:
    wrong_target = cast(
        JsonValue,
        {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 1;"}]},
    )
    first_complete = cast(
        JsonValue,
        {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]},
    )
    second_complete = cast(
        JsonValue,
        {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]},
    )
    storage = _Storage(state="completed_with_repair")
    lifecycle = _Lifecycle()
    service, _database, _authorizer, storage, lifecycle = _service(
        executor=_AgentExecutor(
            responses=[wrong_target, first_complete, second_complete]
        ),
        storage=storage,
        lifecycle=lifecycle,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert result.workflow_run_state == "completed_with_repair"
    assert len(storage.calls) == 1
    assert any(
        event.attempt == 2 and event.status == "warning" for event in lifecycle.events
    )


@pytest.mark.asyncio
async def test_executor_records_only_safe_failure_and_never_stores_partial_output() -> (
    None
):
    diagnostic = "token=secret; prompt=raw; SQL=DROP TABLE x; provider trace"
    lifecycle = _Lifecycle()
    storage = _Storage()
    service, _database, _authorizer, storage, lifecycle = _service(
        executor=_AgentExecutor(responses=[RuntimeError(diagnostic)]),
        storage=storage,
        lifecycle=lifecycle,
    )

    with pytest.raises(CodeGenerationExecutionFailedError) as raised:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert storage.calls == []
    assert lifecycle.failed == (
        "code_generation_execution_failed",
        "Code Generation failed before SQL artifacts could be committed.",
    )
    assert lifecycle.claim_tokens == [_CLAIM_TOKEN, _CLAIM_TOKEN]
    assert diagnostic not in str(raised.value)
    assert diagnostic not in repr(raised.value)


@pytest.mark.asyncio
async def test_executor_rejects_noncanonical_mode_without_provider_fallback() -> None:
    invalid = _plan().model_copy(update={"workflow_execution_mode": "tool_assisted"})
    agent = _AgentExecutor(responses=[])
    lifecycle = _Lifecycle()
    storage = _Storage()
    service, _database, _authorizer, storage, lifecycle = _service(
        executor=agent,
        storage=storage,
        lifecycle=lifecycle,
        plan_repository=_PlanRepository(plan=invalid),
    )

    with pytest.raises(WorkbenchError, match="fixed execution path"):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert agent.requests == []
    assert storage.calls == []
    assert lifecycle.failed is not None


@pytest.mark.asyncio
async def test_executor_propagates_a_bounded_terminal_failure_persistence_error() -> (
    None
):
    lifecycle = _Lifecycle(fail_error=DependencyUnavailableError())
    storage = _Storage()
    service, _database, _authorizer, storage, lifecycle = _service(
        executor=_AgentExecutor(
            responses=[InvalidRequestError("Original safe execution failure.")]
        ),
        storage=storage,
        lifecycle=lifecycle,
    )

    with pytest.raises(DependencyUnavailableError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert storage.calls == []
    assert lifecycle.failed == (
        "invalid_request",
        "Original safe execution failure.",
    )
    assert lifecycle.claim_tokens == [_CLAIM_TOKEN, _CLAIM_TOKEN]
