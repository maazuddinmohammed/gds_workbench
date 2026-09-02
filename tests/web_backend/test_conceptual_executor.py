from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.assertion_safety import (
    ASSERTION_RECORD_TEXT_MAX_CHARACTERS,
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    WriteTransaction,
)
from gds_etl_workbench.domain.modeling_records import (
    ConceptualObjectRecord,
    PhysicalObjectKey,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.conceptual.detailed import (
    DetailedConsolidatedEntity,
    DetailedEntityConsolidation,
    DetailedEntityProposal,
    DetailedObjectContribution,
)
from gds_workbench_api.features.conceptual.service import (
    _compact_proposal,  # pyright: ignore[reportPrivateUsage]
    _merge_consolidations,  # pyright: ignore[reportPrivateUsage]
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
                provider_code="databricks",
                model_code="databricks-primary",
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
                        "source_tenant_code": "NWA",
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


def _conceptual_contribution(
    *,
    contribution_ref: str,
    source_name: str,
    name: str,
    definition: str,
    grain: str,
    aliases: tuple[str, ...] = (),
) -> DetailedObjectContribution:
    raw = _candidate_object(source_name=source_name)
    raw["conceptual_object_name"] = name
    raw["conceptual_object_definition"] = definition
    raw["conceptual_object_grain"] = grain
    raw["conceptual_object_aliases"] = list(aliases)
    record = ConceptualObjectRecord.model_validate_json(json.dumps(raw), strict=True)
    source = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=source_name,
    )
    return DetailedObjectContribution(
        contribution_ref=contribution_ref,
        source_object=source,
        disposition="represented",
        rationale="The source supports this business concept.",
        proposals=(
            DetailedEntityProposal(local_entity_ref="candidate", object=record),
        ),
    )


def _single_entity_consolidation(
    contribution: DetailedObjectContribution,
) -> DetailedEntityConsolidation:
    proposal = contribution.proposals[0]
    return DetailedEntityConsolidation(
        entities=(
            DetailedConsolidatedEntity(
                canonical_entity_ref=contribution.contribution_ref,
                contribution_refs=(contribution.proposal_refs[0],),
                candidate_names=(proposal.object.conceptual_object_name,),
            ),
        ),
        discarded_contribution_refs=(),
    )


def test_compact_conceptual_proposal_preserves_business_semantics() -> None:
    contribution = _conceptual_contribution(
        contribution_ref="object_1",
        source_name="customer_raw",
        name="Customer",
        definition="A party that receives products or services.",
        grain="One recognized customer party.",
        aliases=("Client", "Account Holder"),
    )

    compact = cast(
        dict[str, JsonValue],
        _compact_proposal(contribution.proposal_refs[0], contribution.proposals[0]),
    )

    assert compact["candidate_definition"] == (
        "A party that receives products or services."
    )
    assert compact["candidate_grain"] == "One recognized customer party."
    assert compact["candidate_aliases"] == ["Client", "Account Holder"]
    assert compact["candidate_alias_count"] == 2


def test_cross_page_consolidation_keeps_same_name_with_different_grain_separate() -> (
    None
):
    person = _conceptual_contribution(
        contribution_ref="object_1",
        source_name="customer_person_raw",
        name="Customer",
        definition="A party that receives products or services.",
        grain="One individual customer.",
    )
    household = _conceptual_contribution(
        contribution_ref="object_2",
        source_name="customer_household_raw",
        name="Customer",
        definition="A party that receives products or services.",
        grain="One customer household.",
    )

    merged = _merge_consolidations(
        parts=(
            _single_entity_consolidation(person),
            _single_entity_consolidation(household),
        ),
        contributions=(person, household),
    )

    assert len(merged.entities) == 2
    assert {entity.contribution_refs for entity in merged.entities} == {
        ("object_1.candidate",),
        ("object_2.candidate",),
    }


def test_cross_page_consolidation_merges_synonyms_with_same_meaning_and_grain() -> None:
    customer = _conceptual_contribution(
        contribution_ref="object_1",
        source_name="customer_raw",
        name="Customer",
        definition="A party that receives products or services.",
        grain="One recognized customer party.",
        aliases=("Client",),
    )
    client = _conceptual_contribution(
        contribution_ref="object_2",
        source_name="client_raw",
        name="Client",
        definition="  a party that receives products or services.  ",
        grain="one recognized customer party.",
        aliases=("Customer",),
    )

    merged = _merge_consolidations(
        parts=(
            _single_entity_consolidation(customer),
            _single_entity_consolidation(client),
        ),
        contributions=(customer, client),
    )

    assert len(merged.entities) == 1
    assert merged.entities[0].contribution_refs == (
        "object_1.candidate",
        "object_2.candidate",
    )
    assert set(merged.entities[0].candidate_names) == {"Customer", "Client"}


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
    bundle: AgentContextBundle | None = None,
    context_policy: AgentContextPolicy | None = None,
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
                bundle=bundle
                or _context_bundle(
                    mode=selected_plan.workflow_execution_mode or "one_shot"
                ),
            ),
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
                    "reviewed_input_contribution_refs": ["object_1"],
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
    [("context_only", "running"), ("blocked", "warning")],
)
async def test_detailed_empty_coverage_completes_with_true_no_op_event(
    disposition: Literal["context_only", "blocked"],
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
                    "reviewed_input_contribution_refs": ["object_1"],
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


@dataclass
class _PagingAgent:
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        wrapped = cast(dict[str, JsonValue], request.context)
        context = cast(dict[str, JsonValue], wrapped["original_context"])
        if request.stage == "object_contribution":
            source = cast(dict[str, JsonValue], context["source_object"])
            source_name = cast(str, source["object_name"])
            name = "Customer" if source_name == "customer_raw" else "Order"
            candidate: JsonValue = {
                "contribution_ref": context["contribution_ref"],
                "source_object": source,
                "disposition": "represented",
                "rationale": "This byte-bounded page supports one entity.",
                "proposals": [
                    {
                        "local_entity_ref": name.casefold(),
                        "object": _object_with_sources(name, source_name),
                    }
                ],
            }
        elif request.stage == "entity_consolidation":
            proposals = context.get("contribution_proposals")
            if isinstance(proposals, list):
                proposal_rows = proposals
            else:
                proposal_rows = [
                    {
                        "proposal_ref": (
                            f"{contribution['contribution_ref']}.{proposal['local_entity_ref']}"
                        ),
                        "candidate_name": proposal["object"]["conceptual_object_name"],
                    }
                    for contribution in cast(
                        list[dict[str, Any]], context["contributions"]
                    )
                    for proposal in contribution["proposals"]
                ]
            grouped: dict[str, list[str]] = {}
            names: dict[str, str] = {}
            for proposal in cast(list[dict[str, JsonValue]], proposal_rows):
                name = cast(str, proposal["candidate_name"])
                key = name.casefold()
                grouped.setdefault(key, []).append(cast(str, proposal["proposal_ref"]))
                names[key] = name
            candidate = cast(
                JsonValue,
                {
                    "entities": [
                        {
                            "canonical_entity_ref": key,
                            "contribution_refs": refs,
                            "candidate_names": [names[key]],
                        }
                        for key, refs in grouped.items()
                    ],
                    "discarded_contribution_refs": [],
                },
            )
        elif request.stage == "entity_attribute_detail":
            entity = cast(dict[str, JsonValue], context["entity"])
            entity_ref = cast(str, entity["canonical_entity_ref"])
            candidate_names = cast(list[str] | None, entity.get("candidate_names"))
            candidate_name = (
                candidate_names[0]
                if candidate_names is not None
                else cast(str, entity["preferred_candidate_name"])
            )
            compact = context.get("contribution_proposals")
            if isinstance(compact, list):
                source_names = sorted(
                    {
                        cast(
                            str,
                            cast(dict[str, JsonValue], support["source_object"])[
                                "object_name"
                            ],
                        )
                        for proposal in cast(list[dict[str, JsonValue]], compact)
                        for support in cast(
                            list[dict[str, JsonValue]],
                            proposal["physical_support_sources"],
                        )
                        if support["support_source_type"] == "object"
                    }
                )
            else:
                source_names = sorted(
                    {
                        cast(
                            str,
                            cast(dict[str, JsonValue], support["source_object"])[
                                "object_name"
                            ],
                        )
                        for contribution in cast(
                            list[dict[str, JsonValue]],
                            context["contributions"],
                        )
                        for proposal in cast(
                            list[dict[str, JsonValue]],
                            contribution["proposals"],
                        )
                        for support in cast(
                            list[dict[str, JsonValue]],
                            cast(dict[str, JsonValue], proposal["object"])["supports"],
                        )
                    }
                )
            candidate = {
                "canonical_entity_ref": entity_ref,
                "object": _object_with_sources(candidate_name, *source_names),
            }
        elif request.stage == "relationship_cardinality_refinement":
            package = cast(dict[str, JsonValue], context["relationship_package"])
            candidate = {
                "package_ref": package["package_ref"],
                "disposition": "no_relationship",
                "rationale": "Matching names alone do not establish a relationship.",
                "relationship": None,
            }
        elif request.stage == "whole_model_reconciliation":
            work_items = context.get("reconciliation_work_items")
            if isinstance(work_items, list):
                entity_rows = [
                    cast(dict[str, JsonValue], item["entity_detail"])
                    for item in cast(list[dict[str, JsonValue]], work_items)
                    if item["work_item_type"] == "entity_detail"
                ]
                objects = [
                    _object_with_sources(
                        cast(str, row["conceptual_object_name"]),
                        *[
                            cast(
                                str,
                                cast(dict[str, JsonValue], support["source_object"])[
                                    "object_name"
                                ],
                            )
                            for support in cast(
                                list[dict[str, JsonValue]],
                                row["support_sources"],
                            )
                            if support["support_source_type"] == "object"
                        ],
                    )
                    for row in entity_rows
                ]
                coverage = [
                    {
                        "canonical_entity_ref": item["entity_ref"],
                        "conceptual_object_name": cast(
                            dict[str, JsonValue], item["entity_detail"]
                        )["conceptual_object_name"],
                    }
                    for item in cast(list[dict[str, JsonValue]], work_items)
                    if item["work_item_type"] == "entity_detail"
                ]
                package_refs = cast(
                    list[str],
                    context["required_relationship_package_refs"],
                )
                input_refs = cast(
                    list[str], context["required_input_contribution_refs"]
                )
                applied_refs = cast(list[str], context["required_applied_review_refs"])
            else:
                details = cast(list[dict[str, JsonValue]], context["entity_details"])
                objects = [
                    cast(dict[str, JsonValue], item["object"]) for item in details
                ]
                coverage = [
                    {
                        "canonical_entity_ref": item["canonical_entity_ref"],
                        "conceptual_object_name": cast(
                            dict[str, JsonValue], item["object"]
                        )["conceptual_object_name"],
                    }
                    for item in details
                ]
                package_refs = [
                    cast(str, item["package_ref"])
                    for item in cast(
                        list[dict[str, JsonValue]],
                        context["relationship_packages"],
                    )
                ]
                input_refs = cast(
                    list[str], context["required_input_contribution_refs"]
                )
                applied_refs = cast(list[str], context["required_applied_record_refs"])
            candidate = cast(
                JsonValue,
                {
                    "objects": objects,
                    "relationships": [],
                    "entity_coverage": coverage,
                    "reviewed_input_contribution_refs": input_refs,
                    "reviewed_relationship_package_refs": package_refs,
                    "reviewed_applied_record_refs": applied_refs,
                },
            )
        else:
            raise AssertionError(request.stage)
        return AgentExecutionResult(
            candidate=candidate, turn_count=1, tool_call_count=0
        )


def _object_with_sources(name: str, *source_names: str) -> dict[str, JsonValue]:
    value = _candidate_object(source_name=source_names[0])
    value["conceptual_object_name"] = name
    value["conceptual_object_definition"] = f"A governed {name}."
    value["conceptual_object_grain"] = f"One {name}."
    value["supports"] = [
        cast(list[JsonValue], _candidate_object(source_name=source_name)["supports"])[0]
        for source_name in source_names
    ]
    return value


def _maximal_assertion_bundle() -> AgentContextBundle:
    raw = _context_bundle(mode="detailed_coverage").context.model_dump(mode="json")
    selected = cast(list[dict[str, JsonValue]], raw["selected_objects"])
    second = json.loads(json.dumps(selected[0]))
    second["selection_order"] = 2
    cast(dict[str, JsonValue], second["object"])["object_name"] = "order_raw"
    selected.append(second)
    for item in selected:
        object_name = cast(
            str, cast(dict[str, JsonValue], item["object"])["object_name"]
        )
        item["attributes"] = [
            {
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "SOURCE",
                "object_schema": "bronze",
                "object_name": object_name,
                "attribute_name": "customer_id",
                "fc_attribute_name": None,
                "attribute_ordinal_position": 1,
                "attribute_description": None,
                "attribute_data_type": "bigint",
                "attribute_nullability": False,
                "attribute_custom_code": None,
                "is_surrogate_key": False,
                "is_natural_key": True,
                "is_meta_data": False,
                "is_masking_required": False,
                "is_mapped": False,
                "is_purge": False,
                "is_active": True,
            }
        ]
    raw["assertion"] = {
        "documents": [],
        "records": [
            {
                "modeling_assertion_record_key": "maximal.conceptual.assertion",
                "modeling_assertion_document_name": "Conceptual policy",
                "modeling_assertion_record_type": "business_rule",
                "modeling_assertion_text": "🧠" * ASSERTION_RECORD_TEXT_MAX_CHARACTERS,
                "modeling_assertion_details": {},
                "modeling_assertion_source_location": None,
                "modeling_assertion_applicable_layers": ["conceptual"],
                "modeling_assertion_confidence": "high",
                "modeling_assertion_record_status": "active",
                "modeling_assertion_record_is_locked": False,
            }
        ],
    }
    applied = _object_with_sources("Legacy Customer", "customer_raw")
    applied["conceptual_object_definition"] = "a" * (96 * 1024)
    cast(dict[str, JsonValue], raw["applied"])["conceptual"] = {
        "objects": [applied],
        "relationships": [],
    }
    parsed = AgentAuthoringContext.model_validate_json(
        json.dumps(raw, ensure_ascii=False),
        strict=True,
    )
    return AgentContextBundle(
        context=parsed,
        embedded_context=cast(JsonValue, parsed.model_dump(mode="json")),
    )


@pytest.mark.asyncio
async def test_detailed_maximal_assertion_and_multiple_objects_are_byte_bounded() -> (
    None
):
    policy = AgentContextPolicy(
        one_shot_max_context_bytes=128 * 1024,
        stage_max_context_bytes=128 * 1024,
        max_candidate_bytes=128 * 1024,
        max_validation_issues=20,
    )
    bundle = _maximal_assertion_bundle()
    agent = _PagingAgent()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=cast(Any, agent),
        plan=_plan(mode="detailed_coverage"),
        bundle=bundle,
        context_policy=policy,
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
    assert len(handoff.calls) == 1
    assert {
        cast(str, cast(dict[str, JsonValue], record)["conceptual_object_name"])
        for record in handoff.calls[0][0].records
    } == {"Customer", "Order"}
    assert all(
        len(
            json.dumps(
                request.context,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        < policy.stage_max_context_bytes
        for request in agent.requests
    )
    assert all(
        len(
            json.dumps(
                cast(dict[str, JsonValue], request.context)["original_context"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        <= policy.stage_max_context_bytes // 8
        for request in agent.requests
    )
    evidence_fragments = [
        fragment
        for request in agent.requests
        if request.stage == "object_contribution"
        for fragment in cast(
            list[dict[str, JsonValue]],
            cast(
                dict[str, JsonValue],
                cast(dict[str, JsonValue], request.context)["original_context"],
            ).get("evidence_fragments", []),
        )
    ]
    fragment_keys = [
        (
            fragment["dataset"],
            fragment["record_ref"],
            fragment["fragment_index"],
        )
        for fragment in evidence_fragments
    ]
    assert len(fragment_keys) == len(set(fragment_keys))
    assertion_text = "".join(
        cast(str, fragment["json_text"])
        for fragment in sorted(
            (
                item
                for item in evidence_fragments
                if item["dataset"] == "assertion_record"
            ),
            key=lambda item: cast(int, item["fragment_index"]),
        )
    )
    expected_assertion = bundle.context.assertion.records[0].model_dump(mode="json")
    assert json.loads(assertion_text) == expected_assertion
    selected_records = {
        cast(str, fragment["record_ref"])
        for fragment in evidence_fragments
        if fragment["dataset"] == "selected_object"
    }
    assert selected_records == {"object_1", "object_2"}
    for selected in bundle.context.selected_objects:
        selected_text = "".join(
            cast(str, fragment["json_text"])
            for fragment in sorted(
                (
                    item
                    for item in evidence_fragments
                    if item["dataset"] == "selected_object"
                    and item["record_ref"] == f"object_{selected.selection_order}"
                ),
                key=lambda item: cast(int, item["fragment_index"]),
            )
        )
        assert json.loads(selected_text) == selected.model_dump(mode="json")
    relationship_requests = [
        request
        for request in agent.requests
        if request.stage == "relationship_cardinality_refinement"
    ]
    assert relationship_requests == []
    assert all(
        len(
            cast(
                list[JsonValue],
                cast(
                    dict[str, JsonValue],
                    cast(dict[str, JsonValue], request.context)["original_context"],
                )["endpoint_entity_details"],
            )
        )
        == 2
        for request in relationship_requests
    )
    assert all(
        "entity_details"
        not in cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], request.context)["original_context"],
        )
        for request in relationship_requests
    )
    applied_fragments = [
        fragment
        for request in agent.requests
        if request.stage == "whole_model_reconciliation"
        for fragment in cast(
            list[dict[str, JsonValue]],
            cast(
                dict[str, JsonValue],
                cast(dict[str, JsonValue], request.context)["original_context"],
            ).get("reconciliation_work_items", []),
        )
        if fragment.get("work_item_type") == "applied_evidence_fragment"
    ]
    assert applied_fragments
    assert len(
        {
            (
                fragment["record_ref"],
                fragment["fragment_index"],
            )
            for fragment in applied_fragments
        }
    ) == len(applied_fragments)
    applied_text = "".join(
        cast(str, fragment["json_text"])
        for fragment in sorted(
            applied_fragments,
            key=lambda item: cast(int, item["fragment_index"]),
        )
    )
    applied_section = bundle.context.applied.conceptual
    assert applied_section is not None
    assert json.loads(applied_text) == applied_section.objects[0].model_dump(
        mode="json"
    )
