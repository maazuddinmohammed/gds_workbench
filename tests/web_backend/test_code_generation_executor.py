from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_MODEL_STAGE_PAYLOAD_BYTES,
)
from gds_etl_workbench.application.change_sets.model import StageModelChange
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
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from gds_workbench_api.capabilities import (
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.features.code_generation.artifact_context import (
    CodeGenerationArtifactContext,
)
from gds_workbench_api.features.code_generation.context import (
    CodeGenerationExecutionContext,
)
from gds_workbench_api.features.code_generation.service import (
    CodeGenerationExecutionFailedError,
    CodeGenerationFinalizationFailedError,
    DatabaseCodeGenerationExecutor,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentExecutionRouter,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpReceipt,
    AuthoringNoOpRequest,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentContextTooLargeError,
    agent_request_envelope_bytes,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentExecutor as RepairAgentExecutor,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from pydantic import JsonValue

from tests.web_backend.workflow_recovery_fixtures import RetainingHandoff

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _source_context(
    *,
    guide_content: str = "Use deterministic MERGE SQL.",
    transformation_kind: str = "direct",
    mapping_expression: str | None = None,
    target_name: str = "Customer",
) -> dict[str, Any]:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "downstream_prompt_contexts.json").read_text()
    )
    context = deepcopy(fixture["code_generation"]["targets"][0]["context"])
    context["guide"]["content"] = guide_content
    context["target"]["object_name"] = target_name
    document = {"kind": transformation_kind}
    if mapping_expression is not None:
        document["expression"] = mapping_expression
    context["object_mappings"][0]["transformation"] = document
    context["attribute_mappings"][0]["transformation"] = deepcopy(document)
    return context


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
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-primary",
            reasoning_effort_code="none",
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
                    instruction=("Use {{stage_context}} and guide {{sql_generation_guide}}."),
                ),
                variables=(
                    PromptVariableDefinition(
                        name="stage_context",
                        resolver_key=("workflow.code_generation.common.sql_generation.context"),
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
                code_input_digest="c" * 64,
                sql_generation_guide_version_id=91,
                modeled_entity_type="logical_entity",
                modeled_entity_name="TargetOne",
                source_system_codes=("CRM",),
            ),
            CodeGenerationArtifactContext(
                target_ref="target_2",
                object_id=502,
                code_input_digest="e" * 64,
                sql_generation_guide_version_id=91,
                modeled_entity_type="logical_entity",
                modeled_entity_name="TargetTwo",
                source_system_codes=("CRM",),
            ),
        ),
        agent_context=cast(
            JsonValue,
            {
                "targets": [
                    {
                        "target_ref": "target_1",
                        "context": _source_context(),
                    },
                    {
                        "target_ref": "target_2",
                        "context": _source_context(transformation_kind="join"),
                    },
                ]
            },
        ),
    )


def _applied_execution_context() -> CodeGenerationExecutionContext:
    context = _execution_context()
    targets: list[CodeGenerationArtifactContext] = []
    for position, target in enumerate(context.targets, start=1):
        content = f"SELECT {position};"
        targets.append(
            target.model_copy(
                update={
                    "applied_generated_code": (
                        GeneratedCodeRecord(
                            generated_code_is_locked=False,
                            modeled_entity_type="logical_entity",
                            modeled_entity_name=target.modeled_entity_name,
                            artifact_name=f"target_{position}.sql",
                            artifact_type="sql_file",
                            generated_code_content=content,
                            generated_code_status="active",
                        ),
                    ),
                    "applied_generated_code_source_systems": (
                        GeneratedCodeSourceSystemRecord(
                            generated_code_source_system_is_locked=False,
                            modeled_entity_type="logical_entity",
                            modeled_entity_name=target.modeled_entity_name,
                            artifact_name=f"target_{position}.sql",
                            source_system_code="CRM",
                            generated_code_source_system_status="active",
                        ),
                    ),
                    "current_artifact_names": (f"target_{position}.sql",),
                }
            )
        )
    return context.model_copy(update={"targets": tuple(targets)})


def _execution_context_for_target_count(
    target_count: int,
) -> CodeGenerationExecutionContext:
    targets = tuple(
        CodeGenerationArtifactContext(
            target_ref=f"target_{position}",
            object_id=500 + position,
            code_input_digest="c" * 64,
            sql_generation_guide_version_id=91,
            modeled_entity_type="logical_entity",
            modeled_entity_name=f"Target{position}",
            source_system_codes=("CRM",),
        )
        for position in range(1, target_count + 1)
    )
    return CodeGenerationExecutionContext(
        targets=targets,
        agent_context=cast(
            JsonValue,
            {
                "targets": [
                    {
                        "target_ref": target.target_ref,
                        "context": _source_context(),
                    }
                    for target in targets
                ]
            },
        ),
    )


def _multibyte_execution_context(
    *,
    guide_content: str,
    mapping_expression: str,
) -> CodeGenerationExecutionContext:
    targets = tuple(
        CodeGenerationArtifactContext(
            target_ref=f"target_{position}",
            object_id=500 + position,
            code_input_digest=f"{position}" * 64,
            sql_generation_guide_version_id=91,
            modeled_entity_type="logical_entity",
            modeled_entity_name=f"Target{position}",
            source_system_codes=("CRM",),
        )
        for position in (1, 2)
    )
    return CodeGenerationExecutionContext(
        targets=targets,
        agent_context=cast(
            JsonValue,
            {
                "targets": [
                    {
                        "target_ref": target.target_ref,
                        "context": _source_context(
                            guide_content=guide_content,
                            transformation_kind="expression",
                            mapping_expression=mapping_expression,
                            target_name="é" * 399 + str(position),
                        ),
                    }
                    for position, target in enumerate(targets, start=1)
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
        model_id: int | None = None,
    ) -> object:
        del transaction
        assert principal == _principal()
        self.calls.append((tenant_id, policy))
        return object()


@dataclass
class _Database:
    transaction: object = field(default_factory=object)
    write_isolations: list[ReadIsolation] = field(default_factory=lambda: list[ReadIsolation]())

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
    calls: list[tuple[int, int, int]] = field(default_factory=lambda: list[tuple[int, int, int]]())

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
    calls: list[tuple[int, int]] = field(default_factory=lambda: list[tuple[int, int]]())

    async def load(
        self,
        transaction: object,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> CodeGenerationExecutionContext:
        del transaction
        self.calls.append((tenant_id, plan.workflow_run_id))
        return (
            self.context
            if self.context.snapshot is not None
            else code_validation_context(self.context)
        )


@dataclass
class _AgentExecutor:
    responses: list[JsonValue | Exception]
    sdk_code: str = "openai_agents_sdk"
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict) and isinstance(response.get("artifacts"), list):
            artifacts = cast(list[object], response["artifacts"])
            response = cast(
                JsonValue,
                {
                    **response,
                    "artifacts": [
                        {
                            "artifact_name": f"{artifact['target_ref']}.sql",
                            "artifact_role": "target_transformation",
                            "source_system_codes": ["CRM"],
                            **artifact,
                        }
                        for artifact in artifacts
                        if isinstance(artifact, dict)
                    ],
                },
            )
        return AgentExecutionResult(
            candidate=response,
            turn_count=2,
            tool_call_count=0,
        )


@dataclass
class _Handoff(RetainingHandoff):
    calls: list[tuple[StageModelChange, ...]] = field(
        default_factory=lambda: list[tuple[StageModelChange, ...]]()
    )
    final_events: list[AgentWorkflowEvent] = field(
        default_factory=lambda: list[AgentWorkflowEvent]()
    )
    finalization_error: Exception | None = None

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
        workflow_run_claim_token: UUID,
        **_: object,
    ) -> WorkflowChangeSetFinalizationResult:
        assert principal == _principal()
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.calls.append(changes)
        self.final_events.append(final_event)
        if self.finalization_error is not None:
            raise self.finalization_error
        return WorkflowChangeSetFinalizationResult(
            handoff=WorkflowChangeSetHandoffResult(
                model_id=18,
                workflow_run_id=1048,
                model_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                replayed=False,
                draft_revision=2,
                candidate_digest="c" * 64,
                staged_record_count=sum(len(change.records) for change in changes),
                validated_at=datetime(2026, 8, 31, 10, 2, tzinfo=UTC),
            ),
            completion=AgentWorkflowTerminalResult(
                changed=True,
                workflow_run_id=1048,
                workflow_run_state=(
                    "completed_with_repair" if final_event.attempt > 1 else "completed"
                ),
                completed_at=datetime(2026, 8, 31, 10, 3, tzinfo=UTC),
            ),
        )


@dataclass
class _NoOp:
    requests: list[AuthoringNoOpRequest] = field(
        default_factory=lambda: list[AuthoringNoOpRequest]()
    )
    completion_error: Exception | None = None

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        request: AuthoringNoOpRequest,
    ) -> AuthoringNoOpReceipt:
        assert principal == _principal()
        assert (tenant_id, model_id, workflow_run_id) == (7, 18, 1048)
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.requests.append(request)
        if self.completion_error is not None:
            raise self.completion_error
        return AuthoringNoOpReceipt(
            model_id=model_id,
            model_revision=request.expected_model_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_state=(
                "completed_with_repair" if request.final_event.attempt > 1 else "completed"
            ),
            model_workflow=request.expected_workflow,
            workflow_execution_mode=request.expected_execution_mode,
            correlation_id=request.expected_correlation_id,
            candidate_digest=request.candidate_digest,
            replayed=False,
            final_event=request.final_event,
            completed_at=datetime(2026, 8, 31, 10, 2, tzinfo=UTC),
        )


@dataclass
class _Lifecycle:
    events: list[AgentWorkflowEvent] = field(default_factory=lambda: list[AgentWorkflowEvent]())
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
    executor: RepairAgentExecutor,
    handoff: _Handoff | None = None,
    no_op: _NoOp | None = None,
    lifecycle: _Lifecycle | None = None,
    plan_repository: _PlanRepository | None = None,
    context: CodeGenerationExecutionContext | None = None,
    context_policy: AgentContextPolicy | None = None,
) -> tuple[
    DatabaseCodeGenerationExecutor,
    _Database,
    _Authorizer,
    _Handoff,
    _NoOp,
    _Lifecycle,
]:
    database = _Database()
    authorizer = _Authorizer()
    selected_handoff = handoff or _Handoff()
    selected_no_op = no_op or _NoOp()
    selected_lifecycle = lifecycle or _Lifecycle()
    return (
        DatabaseCodeGenerationExecutor(
            database=database,
            authorizer=cast(Any, authorizer),
            agent_executor=executor,
            handoff=selected_handoff,
            no_op=selected_no_op,
            lifecycle=selected_lifecycle,
            plan_repository=plan_repository or _PlanRepository(),
            context_repository=_ContextRepository(context or _execution_context()),
            context_policy=context_policy
            or AgentContextPolicy(
                one_shot_max_context_bytes=64 * 1024,
                stage_max_context_bytes=64 * 1024,
                max_candidate_bytes=64 * 1024,
                max_validation_issues=20,
            ),
        ),
        database,
        authorizer,
        selected_handoff,
        selected_no_op,
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
                        "Follow the selected SQL generation guide.\n{{ sql_generation_guide }}"
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
        plan_repository=_PlanRepository(plan=plan.model_copy(update={"stages": (seeded_stage,)})),
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
@pytest.mark.parametrize(
    ("provider_code", "model_code"),
    (("microsoft_foundry", "foundry-primary"),),
)
async def test_configured_code_generation_profile_accepts_internal_bounded_stage(
    provider_code: str,
    model_code: str,
) -> None:
    selection = AgentRunSelection(
        sdk_code="openai_agents_sdk",
        provider_code=provider_code,
        model_code=model_code,
        reasoning_effort_code="none",
        max_turns=8,
        validation_retry_count=1,
    )
    plan = _plan().model_copy(update={"selection": selection})
    registry = load_default_agent_capabilities()
    registry.validate_selection(selection, execution_mode="one_shot")
    adapter = _AgentExecutor(
        responses=[
            cast(
                JsonValue,
                {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]},
            ),
            cast(
                JsonValue,
                {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]},
            ),
        ]
    )
    router = AgentExecutionRouter(capabilities=registry, adapters=(adapter,))
    service, _database, _authorizer, _handoff, _no_op, lifecycle = _service(
        executor=router,
        plan_repository=_PlanRepository(plan=plan),
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 4
    assert lifecycle.failed is None
    assert [request.execution_mode for request in adapter.requests] == [
        "tool_assisted",
        "tool_assisted",
    ]


@pytest.mark.asyncio
async def test_executor_uses_frozen_plan_and_hands_off_one_atomic_draft() -> None:
    agent = _AgentExecutor(
        responses=[
            cast(
                JsonValue,
                {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]},
            ),
            cast(
                JsonValue,
                {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]},
            ),
        ]
    )
    service, database, authorizer, handoff, no_op, lifecycle = _service(executor=agent)

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
    assert request.execution_mode == "tool_assisted"
    assert request.selection == _plan().selection
    assert set(request.allowed_tool_names) == {
        "get_code_target",
        "get_code_sources",
        "get_code_source_systems",
        "get_object_transformations",
        "get_attribute_transformations",
    }
    assert "Use deterministic MERGE SQL." in request.instruction_prompt
    execution_context = _execution_context().agent_context
    assert isinstance(execution_context, dict)
    execution_targets = execution_context.get("targets")
    assert isinstance(execution_targets, list)
    expected_target = cast(dict[str, Any], execution_targets[0])
    target_context = cast(dict[str, Any], expected_target["context"])
    guide = cast(dict[str, Any], target_context["guide"])["content"]
    assert isinstance(guide, str)
    attempt_context = cast(dict[str, Any], request.context)
    original_context = cast(dict[str, Any], attempt_context["original_context"])
    delivered = cast(dict[str, Any], original_context["values"])
    assert attempt_context["repair"] is None
    assert delivered["target_ref"] == expected_target["target_ref"]
    assert (
        delivered["object_transformations"][0]["transformation"]
        == target_context["object_mappings"][0]["transformation"]
    )
    assert "mapping_object_id" not in delivered["object_transformations"][0]
    assert delivered["sql_generation_guide"] == guide
    assert request.instruction_prompt.count(guide) == 1
    assert "request_context_original_context" not in request.instruction_prompt
    assert len(handoff.calls) == 1
    assert no_op.requests == []
    assert [change.dataset for change in handoff.calls[0]] == [
        "generated_code",
        "generated_code_source_system",
    ]
    records = handoff.calls[0][0].records
    assert [record["artifact_name"] for record in records] == [
        "target_1.sql",
        "target_2.sql",
    ]
    assert [record["generated_code_content"] for record in records] == [
        "SELECT 1;",
        "SELECT 2;",
    ]
    assert all(record["modeled_entity_type"] == "logical_entity" for record in records)
    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 4
    assert "SELECT" not in repr(result)
    assert lifecycle.failed is None
    assert [(event.sequence, event.attempt, event.stage) for event in lifecycle.events] == [
        (2, 1, "code_generation.sql_generation"),
        (3, 1, "code_generation.sql_generation"),
    ]
    assert lifecycle.events[-1].current == 2
    assert lifecycle.events[-1].total == 2
    assert lifecycle.events[-1].finding_count == 0
    assert lifecycle.claim_tokens == [_CLAIM_TOKEN, _CLAIM_TOKEN]


@pytest.mark.asyncio
async def test_executor_allows_candidate_up_to_stage_batch_payload_envelope() -> None:
    large_sql = "SELECT '" + ("x" * (2 * 1024 * 1024)) + "';"
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                {
                    "target_ref": "target_1",
                    "generated_sql": large_sql,
                }
            ]
        },
    )
    candidate_bytes = len(
        json.dumps(
            candidate,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    default_policy = load_default_agent_context_policy()
    assert default_policy.max_candidate_bytes < candidate_bytes
    assert candidate_bytes < MAX_MODEL_STAGE_PAYLOAD_BYTES

    agent = _AgentExecutor(responses=[candidate])
    service, _database, _authorizer, handoff, _no_op, lifecycle = _service(
        executor=agent,
        context=_execution_context_for_target_count(1),
        context_policy=default_policy,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert handoff.calls[0][0].records[0]["generated_code_content"] == large_sql
    assert lifecycle.failed is None


@pytest.mark.asyncio
@pytest.mark.parametrize("locked", [False, True])
async def test_executor_completes_no_op_when_generated_code_is_unchanged(
    locked: bool,
) -> None:
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
    context = _applied_execution_context()
    if locked:
        context = context.model_copy(
            update={
                "targets": tuple(
                    target.model_copy(
                        update={
                            "applied_generated_code": tuple(
                                record.model_copy(update={"generated_code_is_locked": True})
                                for record in target.applied_generated_code
                            ),
                            "applied_generated_code_source_systems": tuple(
                                record.model_copy(
                                    update={"generated_code_source_system_is_locked": True}
                                )
                                for record in target.applied_generated_code_source_systems
                            ),
                        }
                    )
                    for target in context.targets
                )
            }
        )
    handoff = _Handoff()
    no_op = _NoOp()
    service, _database, _authorizer, handoff, no_op, lifecycle = _service(
        executor=agent,
        handoff=handoff,
        no_op=no_op,
        context=context,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, AuthoringNoOpReceipt)
    assert handoff.calls == []
    assert len(no_op.requests) == 1
    assert no_op.requests[0].expected_workflow == "code_generation"
    assert no_op.requests[0].expected_execution_mode is None
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_executor_does_not_mark_run_failed_after_uncertain_finalization() -> None:
    diagnostic = "secret SQL and provider trace"
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
    handoff = _Handoff(finalization_error=RuntimeError(diagnostic))
    service, _database, _authorizer, handoff, _no_op, lifecycle = _service(
        executor=agent,
        handoff=handoff,
    )

    with pytest.raises(CodeGenerationFinalizationFailedError) as raised:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert len(handoff.calls) == 1
    assert lifecycle.failed is None
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_executor_bounds_progress_events_for_large_target_sets() -> None:
    target_count = 80
    context = _execution_context_for_target_count(target_count)
    plan = _plan().model_copy(update={"selected_object_ids": tuple(range(501, 501 + target_count))})
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
            for position in range(1, target_count + 1)
        ]
    )
    service, _database, _authorizer, _handoff, _no_op, lifecycle = _service(
        executor=agent,
        plan_repository=_PlanRepository(plan=plan),
        context=context,
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert len(lifecycle.events) == 9
    assert [event.sequence for event in lifecycle.events] == list(range(2, 11))
    assert [event.current for event in lifecycle.events] == [
        0,
        10,
        20,
        30,
        40,
        50,
        60,
        70,
        80,
    ]
    assert all(event.total == target_count for event in lifecycle.events)
    assert all(event.finding_count == 0 for event in lifecycle.events)


@pytest.mark.asyncio
async def test_executor_keeps_maximal_multibyte_guide_and_mapping_in_bounded_requests() -> None:
    guide = "é" * 131_072
    mapping_expression = "é" * 40_000
    context = _multibyte_execution_context(
        guide_content=guide,
        mapping_expression=mapping_expression,
    )
    policy = AgentContextPolicy(
        one_shot_max_context_bytes=512 * 1_024,
        stage_max_context_bytes=512 * 1_024,
        max_candidate_bytes=512 * 1_024,
        max_validation_issues=100,
    )
    wrong_target = cast(
        JsonValue,
        {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 0;"}]},
    )
    agent = _AgentExecutor(
        responses=[
            wrong_target,
            cast(
                JsonValue,
                {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]},
            ),
            cast(
                JsonValue,
                {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]},
            ),
        ]
    )
    service, _database, _authorizer, handoff, no_op, lifecycle = _service(
        executor=AgentExecutionRouter(
            capabilities=load_default_agent_capabilities(),
            adapters=(agent,),
        ),
        context=context,
        context_policy=policy,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 4
    assert lifecycle.failed is None
    assert len(handoff.calls) == 1
    assert no_op.requests == []
    assert len(guide.encode("utf-8")) == 262_144
    assert all(
        agent_request_envelope_bytes(request) <= policy.stage_max_context_bytes
        for request in agent.requests
    )
    assert max(agent_request_envelope_bytes(request) for request in agent.requests) > 262_144
    assert all(request.execution_mode == "tool_assisted" for request in agent.requests)
    assert any(
        cast(dict[str, JsonValue], request.context)["repair"] is not None
        for request in agent.requests
    )
    for request in agent.requests:
        attempt = cast(dict[str, JsonValue], request.context)
        original = cast(dict[str, JsonValue], attempt["original_context"])
        encoded = json.dumps(
            original,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        assert mapping_expression in encoded.decode("utf-8")
        assert guide in encoded.decode("utf-8")
        assert request.instruction_prompt.count(guide) == 1
        assert "request_context_original_context" not in request.instruction_prompt


@pytest.mark.asyncio
async def test_executor_rejects_unrepresentable_target_before_provider_without_truncation() -> None:
    context = _multibyte_execution_context(
        guide_content="é" * 131_072,
        mapping_expression="é" * 90_000,
    )
    agent = _AgentExecutor(responses=[])
    handoff = _Handoff()
    no_op = _NoOp()
    lifecycle = _Lifecycle()
    plan = _plan()
    stage = plan.stages[0]
    additions = ("object_transformations", "attribute_transformations")
    stage = stage.model_copy(
        update={
            "templates": stage.templates.model_copy(
                update={
                    "instruction": stage.templates.instruction
                    + "\n{{ object_transformations }}\n{{ attribute_transformations }}"
                }
            ),
            "variables": (
                *stage.variables,
                *(
                    PromptVariableDefinition(
                        name=name,
                        resolver_key="workflow.code_generation.common.sql_generation.inputs."
                        + name,
                        data_type="json",
                        is_required=True,
                    )
                    for name in additions
                ),
            ),
        }
    )
    plan = plan.model_copy(update={"stages": (stage,)})
    service, _database, _authorizer, handoff, no_op, lifecycle = _service(
        executor=agent,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
        plan_repository=_PlanRepository(plan=plan),
        context=context,
        context_policy=AgentContextPolicy(
            one_shot_max_context_bytes=512 * 1_024,
            stage_max_context_bytes=512 * 1_024,
            max_candidate_bytes=512 * 1_024,
            max_validation_issues=100,
        ),
    )

    with pytest.raises(AgentContextTooLargeError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert no_op.requests == []
    assert lifecycle.failed == (
        "agent_context_too_large",
        ("The selected execution mode cannot accept this context. Choose another mode explicitly."),
    )


@pytest.mark.asyncio
async def test_executor_uses_common_validation_repair_before_one_atomic_handoff() -> None:
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
    handoff = _Handoff()
    lifecycle = _Lifecycle()
    service, _database, _authorizer, handoff, _no_op, lifecycle = _service(
        executor=_AgentExecutor(responses=[wrong_target, first_complete, second_complete]),
        handoff=handoff,
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

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 4
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].attempt == 2
    assert handoff.final_events[-1].status == "warning"
    assert any(event.attempt == 2 and event.status == "warning" for event in lifecycle.events)


@pytest.mark.asyncio
async def test_executor_records_only_safe_failure_and_never_stores_partial_output() -> None:
    diagnostic = "token=secret; prompt=raw; SQL=DROP TABLE x; provider trace"
    lifecycle = _Lifecycle()
    handoff = _Handoff()
    no_op = _NoOp()
    service, _database, _authorizer, handoff, no_op, lifecycle = _service(
        executor=_AgentExecutor(responses=[RuntimeError(diagnostic)]),
        handoff=handoff,
        no_op=no_op,
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

    assert handoff.calls == []
    assert no_op.requests == []
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
    handoff = _Handoff()
    no_op = _NoOp()
    service, _database, _authorizer, handoff, no_op, lifecycle = _service(
        executor=agent,
        handoff=handoff,
        no_op=no_op,
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
    assert handoff.calls == []
    assert no_op.requests == []
    assert lifecycle.failed is not None


@pytest.mark.asyncio
async def test_executor_propagates_a_bounded_terminal_failure_persistence_error() -> None:
    lifecycle = _Lifecycle(fail_error=DependencyUnavailableError())
    handoff = _Handoff()
    no_op = _NoOp()
    service, _database, _authorizer, handoff, no_op, lifecycle = _service(
        executor=_AgentExecutor(
            responses=[InvalidRequestError("Original safe execution failure.")]
        ),
        handoff=handoff,
        no_op=no_op,
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

    assert handoff.calls == []
    assert no_op.requests == []
    assert lifecycle.failed == (
        "invalid_request",
        "Original safe execution failure.",
    )
    assert lifecycle.claim_tokens == [_CLAIM_TOKEN, _CLAIM_TOKEN]


def code_validation_context(
    context: CodeGenerationExecutionContext,
) -> CodeGenerationExecutionContext:
    """Applied Mapping and physical bindings for synthetic Code targets."""
    from dataclasses import fields, replace

    from gds_etl_workbench.domain.modeling_records import (
        ModelingRecord,
        normalize_model_key_value,
    )
    from gds_etl_workbench.domain.snapshots.model import (
        DATASETS_BY_NAME,
        ModelChangeSetDataset,
        model_snapshot_records,
    )

    from tests.mcp.model_test_fixtures import snapshot_from_graph
    from tests.web_backend.mapping_fixtures import (
        mapping_preparation,
        mapping_validation_preparation,
    )

    records: dict[ModelChangeSetDataset, dict[tuple[object, ...], ModelingRecord]] = {}
    from gds_etl_workbench.application.change_sets.model_validation import (
        PhysicalModelCatalog,
    )

    scopes: list[PhysicalModelCatalog] = []
    for target in context.targets:
        prepared = mapping_preparation(
            existing=True, modeled_entity_type=target.modeled_entity_type
        )
        original = prepared.context
        header = original.headers[0]
        prepared = mapping_validation_preparation(
            prepared.plan,
            original.model_copy(
                update={
                    "target": original.target.model_copy(
                        update={"object_name": target.modeled_entity_name}
                    ),
                    "headers": (
                        header.model_copy(
                            update={
                                "modeled_entity": header.modeled_entity.model_copy(
                                    update={"entity_name": target.modeled_entity_name}
                                )
                            }
                        ),
                    ),
                }
            ),
        )
        assert prepared.snapshot is not None and prepared.physical_scope is not None
        scopes.append(prepared.physical_scope)
        for dataset_name, values in model_snapshot_records(prepared.snapshot).items():
            dataset = cast(ModelChangeSetDataset, dataset_name)
            if dataset in {"generated_code", "generated_code_source_system"}:
                values = (
                    target.applied_generated_code
                    if dataset == "generated_code"
                    else target.applied_generated_code_source_systems
                )
            if dataset in {"mapping_object", "mapping_attribute", "mapping_dependency"}:
                values = tuple(
                    record.model_copy(update={"source_system_code": code})
                    for record in values
                    for code in target.source_system_codes
                )
            by_key = records.setdefault(dataset, {})
            for record in values:
                key = tuple(
                    normalize_model_key_value(getattr(record, name))
                    for name in DATASETS_BY_NAME[dataset].canonical_key
                )
                by_key[key] = record
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        dataset: [record.model_dump(mode="json") for record in values.values()]
        for dataset, values in records.items()
    }
    snapshot = snapshot_from_graph(graph).model_copy(update={"model_id": 18, "model_revision": 7})
    scope = replace(
        scopes[0],
        **{
            field.name: frozenset().union(*(getattr(item, field.name) for item in scopes))
            for field in fields(scopes[0])
            if field.name != "model_tenant_code"
        },
    )
    scope = replace(
        scope,
        active_system_codes=scope.active_system_codes
        | frozenset(
            code.casefold() for target in context.targets for code in target.source_system_codes
        ),
    )
    return context.model_copy(update={"snapshot": snapshot, "physical_scope": scope})


@pytest.mark.asyncio
@pytest.mark.parametrize("selected_tools", [(), ("get_code_sources",)])
async def test_executor_honors_saved_optional_reader_selection(
    selected_tools: tuple[str, ...],
) -> None:
    plan = _plan()
    plan = plan.model_copy(
        update={"stages": (plan.stages[0].model_copy(update={"agent_tool_names": selected_tools}),)}
    )
    agent = _AgentExecutor(
        responses=[
            cast(
                JsonValue, {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]}
            ),
            cast(
                JsonValue, {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]}
            ),
        ]
    )
    service, _, _, _, _, lifecycle = _service(
        executor=agent, plan_repository=_PlanRepository(plan=plan)
    )
    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    assert lifecycle.failed is None
    for request in agent.requests:
        assert request.allowed_tool_names == selected_tools
        assert request.local_tool_catalog is not None
        with pytest.raises(InvalidRequestError):
            request.local_tool_catalog.invoke("get_code_target", {})
