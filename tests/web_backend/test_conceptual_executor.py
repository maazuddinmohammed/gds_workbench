from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.conceptual.service import (
    ConceptualExecutionFailedError,
    ConceptualFinalizationFailedError,
    DatabaseConceptualExecutor,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentAuthoringContext,
    AgentContextBundle,
    InMemoryAgentContextToolCatalog,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpReceipt,
    AuthoringNoOpRequest,
    authoring_no_op_candidate_digest,
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

_CLAIM_TOKEN = UUID("44444444-4444-4444-8444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _plan(*, mode: str = "one_shot", retry_count: int = 1) -> AgentRunPlan:
    if mode == "detailed_coverage":
        stage_codes = (
            "object_contribution",
            "entity_consolidation",
            "entity_attribute_detail",
            "relationship_cardinality_refinement",
            "whole_model_reconciliation",
        )
    else:
        stage_codes = ("candidate_authoring",)
    stages: list[FrozenAgentStage] = []
    for position, stage_code in enumerate(stage_codes, start=1):
        variables = [
            PromptVariableDefinition(
                name="stage_context",
                resolver_key=f"workflow.conceptual.{mode}.{stage_code}.context",
                data_type="json",
                is_required=True,
            ),
            PromptVariableDefinition(
                name="naming_instructions",
                resolver_key="model.naming_instructions",
                data_type="text",
                is_required=False,
            ),
        ]
        instruction = "Use {{stage_context}} and {{naming_instructions}}."
        if stage_code in ("candidate_authoring", "whole_model_reconciliation"):
            instruction += " Repair {{validation_failures}}."
            variables.append(
                PromptVariableDefinition(
                    name="validation_failures",
                    resolver_key="workflow.validation_failures",
                    data_type="json",
                    is_required=False,
                )
            )
        stages.append(
            FrozenAgentStage(
                workflow_stage_id=30 + position,
                stage_code=stage_code,
                stage_order=position * 10,
                prompt_template_version_id=80 + position,
                prompt_template_digest=f"{position:x}" * 64,
                templates=PromptComponentTemplates(
                    system="Author a governed Conceptual stage candidate.",
                    instruction=instruction,
                ),
                variables=tuple(variables),
            )
        )
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "model_revision": 7,
            "model_workflow": "conceptual",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (501,),
            "selection": AgentRunSelection(
                sdk_code="langchain_create_agent",
                provider_code="microsoft_foundry",
                model_code="gpt-5.6",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=retry_count,
            ),
            "stages": tuple(stages),
        },
        strict=False,
    )


def _context_bundle(*, mode: str = "one_shot") -> AgentContextBundle:
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_name": "Customer Model",
            "model_revision": 7,
            "model_workflow": "conceptual",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "model_details": {
                "model_name": "Customer Model",
                "model_description": None,
                "silver_model_naming_instructions": "Use business language.",
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": None,
                "gold_model_technical_columns_template": None,
                "gold_model_audit_columns_template": None,
            },
            "selected_objects": (
                {
                    "selection_order": 1,
                    "object": {
                        "tenant_code": "NWA",
                        "system_code": "CRM",
                        "connection_code": "SOURCE",
                        "object_schema": "bronze",
                        "object_name": "customer_raw",
                        "fc_object_schema": None,
                        "fc_object_name": None,
                        "object_transformation": None,
                        "object_description": "Customer source metadata.",
                        "batch_attribute_name": "batch_id",
                        "object_type_code": "table",
                        "zone_code": "bronze",
                        "is_locked": False,
                        "is_active": True,
                    },
                    "attributes": (),
                },
            ),
            "profiles": (),
            "analysis_relationships": (),
            "assertion": {"documents": (), "records": ()},
            "applied": {
                "conceptual": {"objects": (), "relationships": ()},
                "logical": None,
                "dimensional": None,
                "mapping": None,
            },
        },
        strict=False,
    )
    if mode == "tool_assisted":
        catalog = InMemoryAgentContextToolCatalog(
            context=context,
            max_result_bytes=128 * 1024,
            max_catalog_bytes=128 * 1024,
            max_page_records=20,
        )
        return AgentContextBundle(
            context=context,
            embedded_context=catalog.manifest,
            tool_catalog=catalog,
        )
    return AgentContextBundle(
        context=context,
        embedded_context=cast(JsonValue, context.model_dump(mode="json")),
    )


def _candidate_object(*, source_name: str = "customer_raw") -> dict[str, JsonValue]:
    return {
        "conceptual_object_name": "Customer",
        "conceptual_object_definition": "A governed customer.",
        "conceptual_object_type": "party",
        "conceptual_object_grain": "One customer.",
        "conceptual_object_aliases": [],
        "conceptual_object_confidence": "high",
        "conceptual_object_status": "active",
        "conceptual_object_is_locked": False,
        "supports": [
            {
                "support_source_type": "object",
                "source_object": {
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "connection_code": "SOURCE",
                    "object_schema": "bronze",
                    "object_name": source_name,
                },
                "support_role": "source",
                "support_reason": "The source supports Customer.",
                "support_reason_detail": None,
                "support_confidence": "high",
                "support_status": "active",
                "support_is_locked": False,
            }
        ],
    }


def _candidate(*, source_name: str = "customer_raw") -> JsonValue:
    return cast(
        JsonValue,
        {"objects": [_candidate_object(source_name=source_name)], "relationships": []},
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


@dataclass
class _PlanRepository:
    plan: AgentRunPlan = field(default_factory=_plan)

    async def load(self, transaction: object, **_: object) -> AgentRunPlan:
        del transaction
        return self.plan


@dataclass
class _ContextRepository:
    bundle: AgentContextBundle = field(default_factory=_context_bundle)

    async def load(self, transaction: object, **_: object) -> AgentContextBundle:
        del transaction
        return self.bundle


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
class _Handoff:
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
                validated_at=datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
            ),
            completion=AgentWorkflowTerminalResult(
                changed=True,
                workflow_run_id=1048,
                workflow_run_state="completed",
                completed_at=datetime(2026, 8, 24, 10, 3, tzinfo=UTC),
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
        assert tenant_id == 7
        assert model_id == 18
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.requests.append(request)
        if self.completion_error is not None:
            raise self.completion_error
        return AuthoringNoOpReceipt(
            model_id=model_id,
            model_revision=request.expected_model_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_state=(
                "completed_with_repair"
                if request.final_event.attempt > 1
                else "completed"
            ),
            model_workflow=request.expected_workflow,
            workflow_execution_mode=request.expected_execution_mode,
            correlation_id=request.expected_correlation_id,
            candidate_digest=request.candidate_digest,
            replayed=False,
            final_event=request.final_event,
            completed_at=datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
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
        workflow_run_claim_token: UUID,
        **_: object,
    ) -> None:
        assert principal == _principal()
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.events.append(event)

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
        **_: object,
    ) -> AgentWorkflowTerminalResult:
        assert principal == _principal()
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.failed = (failure_code, safe_failure_message)
        return AgentWorkflowTerminalResult(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="failed",
            completed_at=datetime.now(UTC),
        )


def _service(
    *,
    agent: _AgentExecutor,
    plan: AgentRunPlan | None = None,
    no_op: _NoOp | None = None,
) -> tuple[
    DatabaseConceptualExecutor,
    _Database,
    _Authorizer,
    _Handoff,
    _Lifecycle,
]:
    database = _Database()
    authorizer = _Authorizer()
    handoff = _Handoff()
    lifecycle = _Lifecycle()
    selected_plan = plan or _plan()
    return (
        DatabaseConceptualExecutor(
            database=database,
            authorizer=cast(Any, authorizer),
            agent_executor=agent,
            handoff=handoff,
            no_op=no_op or _NoOp(),
            lifecycle=lifecycle,
            plan_repository=_PlanRepository(plan=selected_plan),
            context_repository=_ContextRepository(
                bundle=_context_bundle(
                    mode=selected_plan.workflow_execution_mode or "one_shot"
                )
            ),
            context_policy=AgentContextPolicy(
                one_shot_max_context_bytes=128 * 1024,
                stage_max_context_bytes=128 * 1024,
                max_candidate_bytes=128 * 1024,
                max_validation_issues=20,
            ),
        ),
        database,
        authorizer,
        handoff,
        lifecycle,
    )


@pytest.mark.asyncio
async def test_executor_authors_validated_draft_without_applying_model() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, database, authorizer, handoff, lifecycle = _service(agent=agent)

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.model_change_set_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_MODEL_WRITE)]
    request = agent.requests[0]
    assert request.workflow == "conceptual"
    assert request.stage == "candidate_authoring"
    assert request.execution_mode == "one_shot"
    assert request.allowed_tool_names == ()
    assert "Use business language." in request.instruction_prompt
    assert request.context == {
        "original_context": _context_bundle().embedded_context,
        "repair": None,
    }
    assert len(handoff.calls) == 1
    assert handoff.calls[0][0].dataset == "conceptual_object"
    assert handoff.final_events[-1].finding_count == 1
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.stage)
        for event in (*lifecycle.events, *handoff.final_events)
    ] == [
        (2, "conceptual.candidate_authoring"),
        (3, "conceptual.backend_validation"),
    ]


@pytest.mark.asyncio
async def test_empty_candidate_completes_with_atomic_no_op_receipt() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[{"objects": [], "relationships": []}]),
        no_op=no_op,
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
    assert lifecycle.failed is None
    assert len(no_op.requests) == 1
    request = no_op.requests[0]
    assert request.candidate_digest == authoring_no_op_candidate_digest(_plan())
    assert request.final_event == AgentWorkflowEvent(
        sequence=3,
        attempt=1,
        stage="conceptual.backend_validation",
        status="running",
        message="Conceptual authoring completed with no effective change.",
        current=1,
        total=1,
        finding_count=0,
    )


@pytest.mark.asyncio
async def test_repaired_empty_candidate_preserves_attempt_and_warning() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(
            responses=[{"invalid": True}, {"objects": [], "relationships": []}]
        ),
        no_op=no_op,
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
    assert result.workflow_run_state == "completed_with_repair"
    assert no_op.requests[0].final_event.attempt == 2
    assert no_op.requests[0].final_event.status == "warning"
    assert handoff.calls == []
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_no_op_error_never_marks_the_run_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = "token=secret; no-op commit acknowledgement unavailable"
    no_op = _NoOp(completion_error=RuntimeError(diagnostic))
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[{"objects": [], "relationships": []}]),
        no_op=no_op,
    )

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(ConceptualFinalizationFailedError) as raised,
    ):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert len(no_op.requests) == 1
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert "Conceptual Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_executor_repairs_invalid_candidate_before_single_handoff() -> None:
    agent = _AgentExecutor(
        responses=[_candidate(source_name="outside_selection"), _candidate()]
    )
    service, _database, _authorizer, handoff, _lifecycle = _service(agent=agent)

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert len(agent.requests) == 2
    first_context = cast(dict[str, JsonValue], agent.requests[0].context)
    repaired_context = cast(dict[str, JsonValue], agent.requests[1].context)
    assert repaired_context != first_context
    assert repaired_context["original_context"] == first_context["original_context"]
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].status == "warning"
    assert handoff.final_events[-1].attempt == 2


@pytest.mark.asyncio
async def test_executor_fails_safely_without_handoff_or_partial_output() -> None:
    diagnostic = "token=secret; raw prompt and provider trace"
    agent = _AgentExecutor(responses=[RuntimeError(diagnostic)])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(ConceptualExecutionFailedError) as raised:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert handoff.calls == []
    assert lifecycle.failed == (
        "conceptual_execution_failed",
        "Conceptual authoring failed before a validated draft was committed.",
    )
    assert diagnostic not in str(raised.value)
    assert diagnostic not in repr(raised.value)


@pytest.mark.asyncio
async def test_finalizer_error_never_marks_the_run_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = "token=secret; commit acknowledgement unavailable"
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)
    handoff.finalization_error = RuntimeError(diagnostic)

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(ConceptualFinalizationFailedError) as raised,
    ):
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
    assert "Conceptual Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_executor_tool_assisted_uses_local_catalog_and_same_handoff() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="tool_assisted"),
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    request = agent.requests[0]
    assert request.execution_mode == "tool_assisted"
    catalog = request.local_tool_catalog
    assert isinstance(catalog, InMemoryAgentContextToolCatalog)
    assert request.allowed_tool_names == catalog.allowed_tool_names
    assert request.context == {
        "original_context": catalog.manifest,
        "repair": None,
    }
    assert len(handoff.calls) == 1
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_executor_detailed_coverage_runs_each_ledger_then_one_handoff() -> None:
    source = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": "customer_raw",
    }
    object_record = _candidate_object()
    agent = _AgentExecutor(
        responses=cast(
            list[JsonValue | Exception],
            [
                {
                    "contribution_ref": "object_1",
                    "source_object": source,
                    "disposition": "represented",
                    "rationale": "The selected Object represents Customer.",
                    "proposals": [
                        {"local_entity_ref": "customer", "object": object_record}
                    ],
                },
                {
                    "entities": [
                        {
                            "canonical_entity_ref": "customer",
                            "contribution_refs": ["object_1.customer"],
                            "candidate_names": ["Customer"],
                        }
                    ],
                    "discarded_contribution_refs": [],
                },
                {"canonical_entity_ref": "customer", "object": object_record},
                {
                    "objects": [object_record],
                    "relationships": [],
                    "entity_coverage": [
                        {
                            "canonical_entity_ref": "customer",
                            "conceptual_object_name": "Customer",
                        }
                    ],
                    "reviewed_relationship_package_refs": [],
                    "reviewed_applied_record_refs": [],
                },
            ],
        )
    )
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert [request.stage for request in agent.requests] == [
        "object_contribution",
        "entity_consolidation",
        "entity_attribute_detail",
        "whole_model_reconciliation",
    ]
    assert all(
        request.execution_mode == "detailed_coverage" for request in agent.requests
    )
    assert all(request.allowed_tool_names == () for request in agent.requests)
    assert len(handoff.calls) == 1
    assert handoff.calls[0][0].dataset == "conceptual_object"
    assert lifecycle.failed is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "expected_status"),
    [("not_conceptual", "running"), ("needs_review", "warning")],
)
async def test_detailed_empty_coverage_completes_with_true_no_op_event(
    disposition: Literal["not_conceptual", "needs_review"],
    expected_status: Literal["running", "warning"],
) -> None:
    source = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": "customer_raw",
    }
    agent = _AgentExecutor(
        responses=cast(
            list[JsonValue | Exception],
            [
                {
                    "contribution_ref": "object_1",
                    "source_object": source,
                    "disposition": disposition,
                    "rationale": "The source has no represented Conceptual entity.",
                    "proposals": [],
                },
                {"entities": [], "discarded_contribution_refs": []},
                {
                    "objects": [],
                    "relationships": [],
                    "entity_coverage": [],
                    "reviewed_relationship_package_refs": [],
                    "reviewed_applied_record_refs": [],
                },
            ],
        )
    )
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
        no_op=no_op,
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
    assert [request.stage for request in agent.requests] == [
        "object_contribution",
        "entity_consolidation",
        "whole_model_reconciliation",
    ]
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert no_op.requests[0].final_event.sequence == 8
    assert no_op.requests[0].final_event.attempt == 1
    assert no_op.requests[0].final_event.status == expected_status


@pytest.mark.asyncio
async def test_executor_detailed_late_failure_never_hands_off_or_falls_back() -> None:
    agent = _AgentExecutor(
        responses=cast(
            list[JsonValue | Exception],
            [
                {
                    "contribution_ref": "object_1",
                    "source_object": {
                        "tenant_code": "NWA",
                        "system_code": "CRM",
                        "connection_code": "SOURCE",
                        "object_schema": "bronze",
                        "object_name": "customer_raw",
                    },
                    "disposition": "represented",
                    "rationale": "Customer evidence.",
                    "proposals": [
                        {
                            "local_entity_ref": "customer",
                            "object": _candidate_object(),
                        }
                    ],
                },
                {
                    "entities": [
                        {
                            "canonical_entity_ref": "customer",
                            "contribution_refs": ["object_1.customer"],
                            "candidate_names": ["Customer"],
                        }
                    ],
                    "discarded_contribution_refs": [],
                },
                RuntimeError("private provider diagnostic"),
            ],
        )
    )
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
    )

    with pytest.raises(ConceptualExecutionFailedError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert [request.stage for request in agent.requests] == [
        "object_contribution",
        "entity_consolidation",
        "entity_attribute_detail",
    ]
    assert handoff.calls == []
    assert lifecycle.failed is not None
