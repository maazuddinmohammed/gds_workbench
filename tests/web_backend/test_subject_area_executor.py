"""Subject Area runs author one validated, unapplied draft only after worker claim."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.snapshots.project import SubjectAreaSection
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    WriteTransaction,
)
from pydantic import JsonValue
from tests.mcp.project_test_fixtures import snapshot_from_graph
from tests.web_backend.workflow_recovery_fixtures import RetainingHandoff

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.subject_areas.service import (
    SubjectAreaExecutionFailedError,
    SubjectAreaFinalizationFailedError,
    SubjectAreaWorkflow,
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
    AgentWorkflowRunStart,
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
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentExecutor,
)
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
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "project_revision": 7,
            "project_workflow": "subject_area",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (501, 502),
            "selection": AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=retry_count,
            ),
            "stages": (
                FrozenAgentStage(
                    workflow_stage_id=31,
                    stage_code="candidate_authoring",
                    stage_order=10,
                    prompt_template_version_id=81,
                    prompt_template_digest="1" * 64,
                    templates=PromptComponentTemplates(
                        system="Group the Input Scope into Subject Areas.",
                        instruction=(
                            "Use {{stage_context}} and {{table_index}}. "
                            "Repair {{validation_failures}}."
                        ),
                    ),
                    variables=(
                        PromptVariableDefinition(
                            name="stage_context",
                            resolver_key=f"workflow.subject_area.{mode}.candidate_authoring.context",
                            data_type="json",
                            is_required=True,
                        ),
                        PromptVariableDefinition(
                            name="table_index",
                            resolver_key=(
                                "workflow.subject_area.common.candidate_authoring.inputs."
                                "table_index"
                            ),
                            data_type="json",
                            is_required=True,
                        ),
                        PromptVariableDefinition(
                            name="validation_failures",
                            resolver_key="workflow.validation_failures",
                            data_type="json",
                            is_required=False,
                        ),
                    ),
                ),
            ),
        },
        strict=False,
    )


def _selected_object(order: int, name: str, *columns: str) -> dict[str, object]:
    key = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": name,
    }
    return {
        "selection_order": order,
        "object": {
            **key,
            "source_tenant_code": "NWA",
            "fc_object_schema": None,
            "fc_object_name": None,
            "object_transformation": None,
            "object_description": f"{name} source metadata.",
            "batch_attribute_name": None,
            "object_type_code": "table",
            "zone_code": "bronze",
            "is_locked": False,
            "is_active": True,
        },
        "attributes": tuple(
            {
                **key,
                "attribute_name": column,
                "fc_attribute_name": None,
                "attribute_ordinal_position": position,
                "attribute_description": None,
                "attribute_data_type": "string",
                "attribute_inferred_data_type": None,
                "is_locked": False,
                "attribute_nullability": position > 1,
                "attribute_custom_code": None,
                "is_surrogate_key": False,
                "is_natural_key": position == 1,
                "is_meta_data": False,
                "is_masking_required": False,
                "is_mapped": False,
                "is_purge": False,
                "is_active": True,
            }
            for position, column in enumerate(columns, start=1)
        ),
    }


def _context_bundle(
    *, mode: str = "one_shot", applied: SubjectAreaSection | None = None
) -> AgentContextBundle:
    # table_index numbers the selection in order: t1 customer_raw, t2 order_raw.
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": 18,
            "project_name": "Customer Project",
            "project_revision": 7,
            "project_workflow": "subject_area",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "project_details": {
                "project_name": "Customer Project",
                "project_description": None,
                "silver_model_naming_instructions": None,
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": None,
                "gold_model_technical_columns_template": None,
                "gold_model_audit_columns_template": None,
            },
            "selected_objects": (
                _selected_object(1, "customer_raw", "customer_id", "customer_name"),
                _selected_object(2, "order_raw", "order_id", "customer_id", "billing_customer_id"),
            ),
            "profiles": (),
            "analysis_relationships": (),
            "context": {
                "records": (),
                "groups": (),
                "types": [
                    {
                        "context_type_name": "Business Requirement",
                        "context_type_description": "Required business outcomes.",
                    }
                ],
            },
            "applied": {
                "subject_area": applied or SubjectAreaSection(areas=(), tables=()),
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
            context=context, embedded_context=catalog.manifest, tool_catalog=catalog
        )
    return AgentContextBundle(
        context=context, embedded_context=cast(JsonValue, context.model_dump(mode="json"))
    )


def _validation_bundle(bundle: AgentContextBundle) -> AgentContextBundle:
    """Add the private graph state the context repository loads for final validation."""
    context = bundle.context
    selected = [item.object for item in context.selected_objects]
    objects = frozenset(
        (
            item.tenant_code.casefold(),
            item.system_code.casefold(),
            item.connection_code.casefold(),
            item.object_schema.casefold(),
            item.object_name.casefold(),
        )
        for item in selected
    )
    applied = context.applied.subject_area or SubjectAreaSection(areas=(), tables=())
    snapshot = snapshot_from_graph(
        {
            "project_details": [context.project_details.model_dump(mode="json")],
            "project_input_scope": [
                {
                    "tenant_code": item.tenant_code,
                    "system_code": item.system_code,
                    "connection_code": item.connection_code,
                    "object_schema": item.object_schema,
                    "object_name": item.object_name,
                    "project_input_scope_is_locked": False,
                    "is_active": True,
                }
                for item in selected
            ],
            "subject_area": [record.model_dump(mode="json") for record in applied.areas],
            "subject_area_table": [record.model_dump(mode="json") for record in applied.tables],
        }
    ).model_copy(
        update={"project_id": context.project_id, "project_revision": context.project_revision}
    )
    return replace(
        bundle,
        snapshot=snapshot,
        physical_scope=PhysicalProjectCatalog(
            project_tenant_code="nwa",
            active_system_codes=frozenset({"crm"}),
            objects=objects,
            attributes=frozenset(),
            project_input_objects=objects,
            project_input_attributes=frozenset(),
        ),
    )


def _candidate(*, tables: tuple[str, ...] = ("t1", "t2")) -> JsonValue:
    return {
        "areas": [
            {
                "name": "Customer Orders",
                "definition": "Customers and the orders they place.",
                "tables": list(tables),
            }
        ],
        "unassigned": [],
        "retire": [],
    }


# Every table must be placed, so an answer without changes lists them as unassigned.
_UNCHANGED: JsonValue = {"areas": [], "unassigned": ["t1", "t2"], "retire": []}


@dataclass
class _Database:
    isolations: list[ReadIsolation] = field(default_factory=lambda: list[ReadIsolation]())

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
        project_id: int | None = None,
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
        return AgentExecutionResult(candidate=response, turn_count=2, tool_call_count=0)


@dataclass
class _Handoff(RetainingHandoff):
    calls: list[tuple[StageProjectChange, ...]] = field(
        default_factory=lambda: list[tuple[StageProjectChange, ...]]()
    )
    final_events: list[AgentWorkflowEvent] = field(
        default_factory=lambda: list[AgentWorkflowEvent]()
    )
    finalization_error: Exception | None = None

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        expected_workflow: str,
        changes: tuple[StageProjectChange, ...],
        final_event: AgentWorkflowEvent,
        workflow_run_claim_token: UUID,
        **_: object,
    ) -> WorkflowChangeSetFinalizationResult:
        assert principal == _principal()
        assert expected_workflow == "subject_area"
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.calls.append(changes)
        self.final_events.append(final_event)
        if self.finalization_error is not None:
            raise self.finalization_error
        return WorkflowChangeSetFinalizationResult(
            handoff=WorkflowChangeSetHandoffResult(
                project_id=18,
                workflow_run_id=1048,
                project_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
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
        project_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        request: AuthoringNoOpRequest,
    ) -> AuthoringNoOpReceipt:
        assert principal == _principal()
        assert (tenant_id, project_id) == (7, 18)
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.requests.append(request)
        if self.completion_error is not None:
            raise self.completion_error
        return AuthoringNoOpReceipt(
            project_id=project_id,
            project_revision=request.expected_project_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_state=(
                "completed_with_repair" if request.final_event.attempt > 1 else "completed"
            ),
            project_workflow=request.expected_workflow,
            workflow_execution_mode=request.expected_execution_mode,
            correlation_id=request.expected_correlation_id,
            candidate_digest=request.candidate_digest,
            replayed=False,
            final_event=request.final_event,
            completed_at=datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
        )


@dataclass
class _Lifecycle:
    starts: list[tuple[RequestPrincipal, int, int, int, str, str | None, int]] = field(
        default_factory=lambda: list[tuple[RequestPrincipal, int, int, int, str, str | None, int]]()
    )
    events: list[AgentWorkflowEvent] = field(default_factory=lambda: list[AgentWorkflowEvent]())
    failed: tuple[str, str] | None = None

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: str,
        expected_execution_mode: str | None,
        expected_project_revision: int,
    ) -> AgentWorkflowRunStart:
        self.starts.append(
            (
                principal,
                tenant_id,
                project_id,
                workflow_run_id,
                expected_workflow,
                expected_execution_mode,
                expected_project_revision,
            )
        )
        return AgentWorkflowRunStart(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
            project_revision=expected_project_revision,
        )

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
    agent: AgentExecutor,
    plan: AgentRunPlan | None = None,
    no_op: _NoOp | None = None,
    bundle: AgentContextBundle | None = None,
    context_policy: AgentContextPolicy | None = None,
) -> tuple[SubjectAreaWorkflow, _Database, _Authorizer, _Handoff, _Lifecycle]:
    database = _Database()
    authorizer = _Authorizer()
    handoff = _Handoff()
    lifecycle = _Lifecycle()
    selected_plan = plan or _plan()
    selected_bundle = bundle or _context_bundle(
        mode=selected_plan.workflow_execution_mode or "one_shot"
    )
    if selected_bundle.snapshot is None:
        selected_bundle = _validation_bundle(selected_bundle)
    return (
        SubjectAreaWorkflow(
            database=database,
            authorizer=cast(Any, authorizer),
            agent_executor=agent,
            handoff=handoff,
            no_op=no_op or _NoOp(),
            lifecycle=lifecycle,
            plan_repository=_PlanRepository(plan=selected_plan),
            context_repository=_ContextRepository(bundle=selected_bundle),
            context_policy=context_policy
            or AgentContextPolicy(
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


async def _execute(service: SubjectAreaWorkflow) -> object:
    return await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_start_binds_subject_area_workflow_without_executing(
    mode: WorkflowExecutionMode,
) -> None:
    agent = _AgentExecutor(responses=[])
    service, database, authorizer, handoff, lifecycle = _service(agent=agent)
    principal = _principal()

    result = await service.start(
        principal,
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_execution_mode=mode,
        expected_project_revision=7,
    )

    assert lifecycle.starts == [(principal, 7, 18, 1048, "subject_area", mode, 7)]
    assert (result.workflow_run_id, result.project_revision) == (1048, 7)
    assert database.isolations == []
    assert authorizer.calls == []
    assert handoff.calls == []
    assert agent.requests == []
    assert lifecycle.events == []
    assert lifecycle.failed is None


async def test_executor_authors_validated_draft_without_applying_project() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, database, authorizer, handoff, lifecycle = _service(agent=agent)

    result = await _execute(service)

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.project_change_set_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_PROJECT_WRITE)]
    request = agent.requests[0]
    assert (request.workflow, request.stage, request.execution_mode) == (
        "subject_area",
        "candidate_authoring",
        "one_shot",
    )
    assert request.allowed_tool_names == ()
    # The registered compact input resolves from the frozen context and packaged policy.
    assert '"table":"t2"' in request.instruction_prompt
    assert request.context == {
        "original_context": _context_bundle().embedded_context,
        "repair": None,
    }
    assert len(handoff.calls) == 1
    assert [(change.dataset, len(change.records)) for change in handoff.calls[0]] == [
        ("subject_area", 1),
        ("subject_area_table", 2),
    ]
    assert handoff.final_events[-1].finding_count == 3
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.stage) for event in (*lifecycle.events, *handoff.final_events)
    ] == [
        (2, "subject_area.candidate_authoring"),
        (3, "subject_area.backend_validation"),
    ]


async def test_unchanged_candidate_completes_with_atomic_no_op_receipt() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[_UNCHANGED]), no_op=no_op
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert len(no_op.requests) == 1
    request = no_op.requests[0]
    assert request.expected_workflow == "subject_area"
    assert request.candidate_digest == authoring_no_op_candidate_digest(_plan())
    assert request.final_event == AgentWorkflowEvent(
        sequence=3,
        attempt=1,
        stage="subject_area.backend_validation",
        status="running",
        message="Subject Area authoring completed with no effective change.",
        current=1,
        total=1,
        finding_count=0,
    )


async def test_repaired_unchanged_candidate_preserves_attempt_and_warning() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[{"invalid": True}, _UNCHANGED]), no_op=no_op
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed_with_repair"
    assert no_op.requests[0].final_event.attempt == 2
    assert no_op.requests[0].final_event.status == "warning"
    assert handoff.calls == []
    assert lifecycle.failed is None


async def test_no_op_error_never_marks_the_run_failed(caplog: pytest.LogCaptureFixture) -> None:
    diagnostic = "token=secret; no-op commit acknowledgement unavailable"
    no_op = _NoOp(completion_error=RuntimeError(diagnostic))
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[_UNCHANGED]), no_op=no_op
    )

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(SubjectAreaFinalizationFailedError) as raised,
    ):
        await _execute(service)

    assert len(no_op.requests) == 1
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert "Subject Area Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


async def test_executor_repairs_invalid_candidate_before_single_handoff() -> None:
    agent = _AgentExecutor(responses=[_candidate(tables=("t1", "t3")), _candidate()])
    service, _database, _authorizer, handoff, _lifecycle = _service(agent=agent)

    await _execute(service)

    assert len(agent.requests) == 2
    first_context = cast(dict[str, Any], agent.requests[0].context)
    repaired_context = cast(dict[str, Any], agent.requests[1].context)
    assert repaired_context["original_context"] == first_context["original_context"]
    assert [issue["code"] for issue in repaired_context["repair"]["validation_issues"]] == [
        "candidate.table_unknown",
        "candidate.table_unaccounted",
    ]
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].status == "warning"
    assert handoff.final_events[-1].attempt == 2


async def test_executor_fails_safely_without_handoff_or_partial_output() -> None:
    diagnostic = "token=secret; raw prompt and provider trace"
    agent = _AgentExecutor(responses=[RuntimeError(diagnostic)])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(SubjectAreaExecutionFailedError) as raised:
        await _execute(service)

    assert handoff.calls == []
    assert lifecycle.failed == (
        "subject_area_execution_failed",
        "Subject Area authoring failed before a validated draft was committed.",
    )
    assert diagnostic not in str(raised.value)
    assert diagnostic not in repr(raised.value)


async def test_finalizer_error_never_marks_the_run_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = "token=secret; commit acknowledgement unavailable"
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[_candidate()])
    )
    handoff.finalization_error = RuntimeError(diagnostic)

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(SubjectAreaFinalizationFailedError) as raised,
    ):
        await _execute(service)

    assert len(handoff.calls) == 1
    assert lifecycle.failed is None
    assert "Subject Area Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


async def test_executor_tool_assisted_uses_local_catalog_and_same_handoff() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent, plan=_plan(mode="tool_assisted")
    )

    await _execute(service)

    request = agent.requests[0]
    assert request.execution_mode == "tool_assisted"
    catalog = request.local_tool_catalog
    assert isinstance(catalog, InMemoryAgentContextToolCatalog)
    assert (
        request.allowed_tool_names
        == catalog.allowed_tool_names
        == (
            "get_source_context",
            "get_gds_context",
            "get_scope_tables",
            "get_table_links",
            "get_subject_areas",
            "get_context_records",
        )
    )
    assert '"table":"t2"' in request.instruction_prompt
    assert request.context == {"original_context": catalog.manifest, "repair": None}
    assert len(handoff.calls) == 1
    assert lifecycle.failed is None
