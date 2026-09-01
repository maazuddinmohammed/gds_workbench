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
from gds_etl_workbench.domain.modeling_records import (
    ValidationCheckRecord,
    ValidationGroupRecord,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.qa.context import (
    QAExecutionContext,
    QASystemAuthoringContext,
)
from gds_workbench_api.features.qa.service import DatabaseQAExecutor
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
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
from gds_workbench_api.features.workflows.authoring.repair import AgentContextPolicy
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _plan() -> AgentRunPlan:
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="qa",
        workflow_execution_mode=None,
        modeled_entity_type=None,
        selected_scope_digest="a" * 64,
        selected_object_ids=(),
        selected_system_codes=("erp",),
        selection=AgentRunSelection(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="model-1",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=1,
        ),
        stages=(
            FrozenAgentStage(
                workflow_stage_id=31,
                stage_code="validation_generation",
                stage_order=1,
                prompt_template_version_id=81,
                prompt_template_digest="b" * 64,
                templates=PromptComponentTemplates(
                    system="Generate QA definitions.",
                    instruction="Use {{validation_context}}.",
                    tool_instruction=None,
                ),
                variables=(
                    PromptVariableDefinition(
                        name="validation_context",
                        resolver_key="workflow.qa.common.validation_context",
                        data_type="json",
                        is_required=True,
                    ),
                ),
            ),
        ),
    )


def _group() -> ValidationGroupRecord:
    return ValidationGroupRecord(
        tenant_code="acme",
        system_code="erp",
        validation_group_name="reconciliation",
        validation_group_description="Counts reconcile.",
        mapping_context_digest="c" * 64,
        code_context_digest=None,
        is_active=True,
    )


def _check() -> ValidationCheckRecord:
    return ValidationCheckRecord(
        tenant_code="acme",
        system_code="erp",
        validation_group_name="reconciliation",
        validation_check_name="row_count_nonnegative",
        validation_check_description=None,
        validation_category_code="technical.count",
        validation_severity="blocking",
        validation_query_sql="SELECT count(*) FROM catalog.gold.dim_customer",
        validation_comparison_query_sql=None,
        validation_result_data_type="integer",
        validation_comparison_operator="greater_than_or_equal",
        validation_comparison_value_type="literal",
        validation_comparison_value=0,
        is_active=True,
    )


def _context(*, applied: bool = False) -> QAExecutionContext:
    return QAExecutionContext(
        systems=(
            QASystemAuthoringContext(
                system_ref="system_1",
                tenant_code="acme",
                system_code="erp",
                mapping_context_digest="c" * 64,
                code_context_digest=None,
                applied_groups=(_group(),) if applied else (),
                applied_checks=(_check(),) if applied else (),
                agent_context={"scope": {"system_code": "erp"}},
            ),
        )
    )


def _candidate() -> JsonValue:
    return cast(
        JsonValue,
        {
            "system_ref": "system_1",
            "validation_groups": [
                {
                    "validation_group_name": "reconciliation",
                    "validation_group_description": "Counts reconcile.",
                    "validation_checks": [
                        {
                            "validation_check_name": "row_count_nonnegative",
                            "validation_check_description": None,
                            "validation_category_code": "technical.count",
                            "validation_severity": "blocking",
                            "validation_query_sql": (
                                "SELECT count(*) FROM catalog.gold.dim_customer"
                            ),
                            "validation_comparison_query_sql": None,
                            "validation_result_data_type": "integer",
                            "validation_comparison_operator": "greater_than_or_equal",
                            "validation_comparison_value_type": "literal",
                            "validation_comparison_value": 0,
                        }
                    ],
                }
            ],
        },
    )


@dataclass
class _Database:
    isolations: list[ReadIsolation] = field(
        default_factory=lambda: list[ReadIsolation]()
    )

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[WriteTransaction]:
        self.isolations.append(isolation)
        yield cast(WriteTransaction, object())


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


class _PlanRepository:
    async def load(self, transaction: object, **_: object) -> AgentRunPlan:
        del transaction
        return _plan()


@dataclass
class _ContextRepository:
    context: QAExecutionContext

    async def load(self, transaction: object, **_: object) -> QAExecutionContext:
        del transaction
        return self.context


@dataclass
class _AgentExecutor:
    response: JsonValue
    sdk_code: str = "openai_agents_sdk"
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return AgentExecutionResult(
            candidate=self.response,
            turn_count=1,
            tool_call_count=0,
        )


@dataclass
class _Handoff:
    calls: list[tuple[StageModelChange, ...]] = field(
        default_factory=lambda: list[tuple[StageModelChange, ...]]()
    )

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
        **_: object,
    ) -> WorkflowChangeSetFinalizationResult:
        assert principal == _principal()
        self.calls.append(changes)
        return WorkflowChangeSetFinalizationResult(
            handoff=WorkflowChangeSetHandoffResult(
                model_id=18,
                workflow_run_id=1048,
                model_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                replayed=False,
                draft_revision=2,
                candidate_digest="d" * 64,
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

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        model_id: int,
        workflow_run_id: int,
        request: AuthoringNoOpRequest,
        **_: object,
    ) -> AuthoringNoOpReceipt:
        assert principal == _principal()
        self.requests.append(request)
        return AuthoringNoOpReceipt(
            model_id=model_id,
            model_revision=request.expected_model_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_state="completed",
            model_workflow="qa",
            workflow_execution_mode=None,
            correlation_id=request.expected_correlation_id,
            candidate_digest=request.candidate_digest,
            replayed=False,
            final_event=request.final_event,
            completed_at=datetime(2026, 8, 31, 10, 2, tzinfo=UTC),
        )


@dataclass
class _Lifecycle:
    events: list[AgentWorkflowEvent] = field(
        default_factory=lambda: list[AgentWorkflowEvent]()
    )
    failed: tuple[str, str] | None = None

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        event: AgentWorkflowEvent,
        **_: object,
    ) -> None:
        assert principal == _principal()
        self.events.append(event)

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        failure_code: str,
        safe_failure_message: str,
        workflow_run_id: int,
        **_: object,
    ) -> AgentWorkflowTerminalResult:
        assert principal == _principal()
        self.failed = (failure_code, safe_failure_message)
        return AgentWorkflowTerminalResult(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="failed",
            completed_at=datetime(2026, 8, 31, 10, 3, tzinfo=UTC),
        )


def _service(
    *, context: QAExecutionContext
) -> tuple[
    DatabaseQAExecutor,
    _Database,
    _AgentExecutor,
    _Handoff,
    _NoOp,
    _Lifecycle,
]:
    database = _Database()
    agent = _AgentExecutor(response=_candidate())
    handoff = _Handoff()
    no_op = _NoOp()
    lifecycle = _Lifecycle()
    service = DatabaseQAExecutor(
        database=database,
        authorizer=cast(Any, _Authorizer()),
        agent_executor=agent,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
        plan_repository=_PlanRepository(),
        context_repository=_ContextRepository(context),
        context_policy=AgentContextPolicy(
            one_shot_max_context_bytes=64 * 1024,
            stage_max_context_bytes=64 * 1024,
            max_candidate_bytes=64 * 1024,
            max_validation_issues=20,
        ),
    )
    return service, database, agent, handoff, no_op, lifecycle


@pytest.mark.asyncio
async def test_executor_stages_qa_groups_and_checks_through_change_set_handoff() -> (
    None
):
    service, database, agent, handoff, no_op, lifecycle = _service(context=_context())

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 2
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert [change.dataset for change in handoff.calls[0]] == [
        "validation_group",
        "validation_check",
    ]
    assert no_op.requests == []
    assert agent.requests[0].workflow == "qa"
    assert agent.requests[0].execution_mode == "detailed_coverage"
    assert "{{validation_context}}" not in agent.requests[0].instruction_prompt
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_executor_completes_identical_candidate_as_no_op() -> None:
    service, _, _, handoff, no_op, _ = _service(context=_context(applied=True))

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.model_workflow == "qa"
    assert handoff.calls == []
    assert len(no_op.requests) == 1
    assert no_op.requests[0].expected_execution_mode is None
