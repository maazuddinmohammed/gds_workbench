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
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.application.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.logical.detailed import (
    logical_json_bytes,
    logical_json_digest,
)
from gds_workbench_api.features.logical.service import (
    DatabaseLogicalExecutor,
    LogicalExecutionFailedError,
    LogicalFinalizationFailedError,
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
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    agent_request_envelope_bytes,
)
from gds_workbench_api.integrations.agents.fake_logical import (
    detailed_logical_candidate,
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
    stage_codes = (
        (
            "topology_builder",
            "topology_reconciler",
            "entity_detail_builder",
            "whole_model_reconciliation",
            "validator_worker",
            "validator_lead",
        )
        if mode == "detailed_coverage"
        else ("candidate_authoring",)
    )
    stages: list[FrozenAgentStage] = []
    for position, stage_code in enumerate(stage_codes, start=1):
        variables = [
            PromptVariableDefinition(
                name="stage_context",
                resolver_key=f"workflow.logical.{mode}.{stage_code}.context",
                data_type="json",
                is_required=True,
            )
        ]
        instruction = "Use {{stage_context}}."
        if stage_code in {
            "candidate_authoring",
            "topology_builder",
            "topology_reconciler",
            "entity_detail_builder",
            "whole_model_reconciliation",
        }:
            variables.append(
                PromptVariableDefinition(
                    name="naming_instructions",
                    resolver_key="model.naming_instructions",
                    data_type="text",
                    is_required=False,
                )
            )
            instruction += " Follow {{naming_instructions}}."
        if stage_code in {"candidate_authoring", "whole_model_reconciliation"}:
            variables.append(
                PromptVariableDefinition(
                    name="validation_failures",
                    resolver_key="workflow.validation_failures",
                    data_type="json",
                    is_required=False,
                )
            )
            instruction += " Repair {{validation_failures}}."
        stages.append(
            FrozenAgentStage(
                workflow_stage_id=40 + position,
                stage_code=stage_code,
                stage_order=position * 10,
                prompt_template_version_id=90 + position,
                prompt_template_digest=f"{position:x}" * 64,
                templates=PromptComponentTemplates(
                    system="Author one governed Logical stage candidate.",
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
            "model_workflow": "logical",
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


def _selected_object() -> dict[str, object]:
    return {
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
        "attributes": (
            {
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "SOURCE",
                "object_schema": "bronze",
                "object_name": "customer_raw",
                "attribute_name": "customer_id",
                "fc_attribute_name": None,
                "attribute_ordinal_position": 1,
                "attribute_description": "Customer identifier.",
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
            },
        ),
    }


def _context_bundle(
    *,
    mode: str = "one_shot",
    assertion: dict[str, object] | None = None,
) -> AgentContextBundle:
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_name": "Customer Model",
            "model_revision": 7,
            "model_workflow": "logical",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "model_details": {
                "model_name": "Customer Model",
                "model_description": None,
                "silver_model_naming_instructions": "Use business language.",
                "silver_model_audit_columns_template": {
                    "schema_version": "1.0",
                    "columns": [
                        {
                            "semantic_name": "Created At",
                            "data_type": "timestamp",
                            "nullable": False,
                            "definition": "Creation time.",
                        }
                    ],
                },
                "gold_model_naming_instructions": None,
                "gold_model_technical_columns_template": None,
                "gold_model_audit_columns_template": None,
            },
            "selected_objects": (_selected_object(),),
            "profiles": (),
            "analysis_relationships": (),
            "assertion": assertion or {"documents": (), "records": ()},
            "applied": {
                "conceptual": None,
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


def _candidate(*, source_name: str = "customer_raw") -> JsonValue:
    object_key = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": source_name,
    }
    return cast(
        JsonValue,
        {
            "submodels": [
                {
                    "logical_submodel_name": "Customer Domain",
                    "logical_submodel_definition": "Customer data.",
                    "logical_submodel_status": "active",
                    "logical_submodel_is_locked": False,
                }
            ],
            "entities": [
                {
                    "logical_entity_name": "Customer",
                    "logical_entity_definition": "One customer.",
                    "logical_entity_type": "core",
                    "logical_entity_type_detail": None,
                    "logical_entity_grain": "One row per customer.",
                    "logical_entity_dependency_order": 0,
                    "logical_entity_confidence": "high",
                    "logical_entity_status": "active",
                    "logical_entity_is_locked": False,
                    "submodels": [
                        {
                            "submodel_name": "Customer Domain",
                            "membership_status": "active",
                            "membership_is_locked": False,
                        }
                    ],
                    "sources": [
                        {
                            "support_source_type": "object",
                            "source_object": object_key,
                            "source_order": 1,
                            "rationale": "Primary customer source.",
                            "status": "active",
                            "is_locked": False,
                        }
                    ],
                }
            ],
            "attributes": [
                {
                    "logical_entity_name": "Customer",
                    "logical_attribute_name": "Customer Id",
                    "logical_attribute_definition": "Customer identifier.",
                    "logical_attribute_data_type": "bigint",
                    "logical_attribute_is_nullable": False,
                    "logical_attribute_is_primary_key": True,
                    "logical_attribute_is_natural_key": True,
                    "logical_attribute_is_surrogate_key": False,
                    "logical_attribute_ordinal_position": 1,
                    "logical_attribute_is_audit_column": False,
                    "logical_attribute_status": "active",
                    "logical_attribute_is_locked": False,
                    "sources": [
                        {
                            "support_source_type": "attribute",
                            "source_attribute": {
                                **object_key,
                                "attribute_name": "customer_id",
                            },
                            "source_order": 1,
                            "rationale": "Primary customer key.",
                            "status": "active",
                            "is_locked": False,
                        }
                    ],
                }
            ],
            "relationships": [],
        },
    )


def _empty_candidate() -> JsonValue:
    return cast(
        JsonValue,
        {
            "submodels": [],
            "entities": [],
            "attributes": [],
            "relationships": [],
        },
    )


def _detailed_candidates(*, blocking_first: bool = False) -> list[JsonValue]:
    full = cast(dict[str, JsonValue], _candidate())
    submodel = cast(list[JsonValue], full["submodels"])[0]
    entity = cast(list[JsonValue], full["entities"])[0]
    attribute = cast(list[JsonValue], full["attributes"])[0]
    object_key = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": "customer_raw",
    }
    source_attribute = {**object_key, "attribute_name": "customer_id"}
    contribution = cast(
        JsonValue,
        {
            "contribution_ref": "object_00001",
            "source_object": object_key,
            "disposition": "represented",
            "rationale": "Represents Customer.",
            "proposals": [
                {
                    "local_entity_ref": "customer",
                    "candidate_entity_name": "Customer",
                    "candidate_entity_type": "core",
                    "candidate_entity_grain": "One row per Customer.",
                    "candidate_submodel_names": ["Customer Domain"],
                    "source_attributes": [source_attribute],
                }
            ],
        },
    )
    topology = cast(
        JsonValue,
        {
            "submodels": [
                {
                    "canonical_submodel_ref": "customer_domain",
                    "submodel": submodel,
                }
            ],
            "entities": [
                {
                    "canonical_entity_ref": "customer",
                    "logical_entity_name": "Customer",
                    "contribution_refs": ["object_00001.customer"],
                    "submodel_refs": ["customer_domain"],
                }
            ],
            "discarded_contribution_refs": [],
        },
    )
    detail = cast(
        JsonValue,
        {
            "canonical_entity_ref": "customer",
            "entity": entity,
            "attributes": [attribute],
        },
    )
    reconciliation = cast(
        JsonValue,
        {
            "submodels": [submodel],
            "entities": [entity],
            "attributes": [attribute],
            "relationships": [],
            "reviewed_submodel_refs": ["customer_domain"],
            "reviewed_entity_refs": ["customer"],
            "reviewed_relationship_signal_refs": [],
            "reviewed_applied_record_refs": [],
        },
    )
    clean_worker = cast(
        JsonValue,
        {
            "package_ref": "validation_00001",
            "reviewed_record_refs": [
                "submodel:customer domain",
                "entity:customer",
                "attribute:customer|customer id",
            ],
            "findings": [],
        },
    )
    clean_lead = cast(
        JsonValue,
        {
            "reviewed_package_refs": ["validation_00001"],
            "reviewed_finding_refs": [],
            "blocking_finding_refs": [],
            "repair_brief": None,
        },
    )
    base = [contribution, topology, detail, reconciliation]
    if not blocking_first:
        return [*base, clean_worker, clean_lead]
    finding = {
        "finding_ref": "validation_00001.finding_00001",
        "severity": "error",
        "code": "logical.review_required",
        "message": "Repair one blocking model concern.",
        "record_refs": ["entity:customer"],
    }
    blocking_worker = cast(
        JsonValue,
        {
            "package_ref": "validation_00001",
            "reviewed_record_refs": [
                "submodel:customer domain",
                "entity:customer",
                "attribute:customer|customer id",
            ],
            "findings": [finding],
        },
    )
    blocking_lead = cast(
        JsonValue,
        {
            "reviewed_package_refs": ["validation_00001"],
            "reviewed_finding_refs": ["validation_00001.finding_00001"],
            "blocking_finding_refs": ["validation_00001.finding_00001"],
            "repair_brief": "Repair the blocking concern.",
        },
    )
    return [
        *base,
        blocking_worker,
        blocking_lead,
        reconciliation,
        clean_worker,
        clean_lead,
    ]


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
        _transaction: object,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        policy: ToolPolicy,
    ) -> object:
        assert principal == _principal()
        self.calls.append((tenant_id, policy))
        return object()


@dataclass
class _PlanRepository:
    plan: AgentRunPlan

    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan:
        del transaction, tenant_id, model_id, workflow_run_id
        return self.plan


@dataclass
class _ContextRepository:
    bundle: AgentContextBundle

    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle:
        del transaction, tenant_id, plan
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
class _LocalFakeAgent:
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return AgentExecutionResult(
            candidate=detailed_logical_candidate(request),
            turn_count=1,
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
    agent: _AgentExecutor | _LocalFakeAgent,
    plan: AgentRunPlan | None = None,
    no_op: _NoOp | None = None,
    context_bundle: AgentContextBundle | None = None,
) -> tuple[DatabaseLogicalExecutor, _Database, _Authorizer, _Handoff, _Lifecycle]:
    selected_plan = plan or _plan()
    database = _Database()
    authorizer = _Authorizer()
    handoff = _Handoff()
    lifecycle = _Lifecycle()
    return (
        DatabaseLogicalExecutor(
            database=database,
            authorizer=cast(Any, authorizer),
            agent_executor=agent,
            handoff=handoff,
            no_op=no_op or _NoOp(),
            lifecycle=lifecycle,
            plan_repository=_PlanRepository(selected_plan),
            context_repository=_ContextRepository(
                context_bundle
                or _context_bundle(
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
async def test_one_shot_projects_audit_columns_then_hands_off_once() -> None:
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
    assert result.staged_record_count == 4
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_MODEL_WRITE)]
    request = agent.requests[0]
    assert request.workflow == "logical"
    assert request.stage == "candidate_authoring"
    assert request.execution_mode == "one_shot"
    assert request.allowed_tool_names == ()
    assert "Use business language." in request.instruction_prompt
    assert request.context == {
        "original_context": _context_bundle().embedded_context,
        "repair": None,
    }
    assert len(handoff.calls) == 1
    attribute_change = next(
        change for change in handoff.calls[0] if change.dataset == "logical_attribute"
    )
    assert [
        record["logical_attribute_name"] for record in attribute_change.records
    ] == [
        "Created At",
        "Customer Id",
    ]
    assert handoff.final_events[-1].finding_count == 4
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.stage)
        for event in (*lifecycle.events, *handoff.final_events)
    ] == [
        (2, "logical.candidate_authoring"),
        (3, "logical.backend_validation"),
    ]


@pytest.mark.asyncio
async def test_empty_candidate_completes_with_atomic_no_op_receipt() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[_empty_candidate()]),
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
        stage="logical.backend_validation",
        status="running",
        message="Logical authoring completed with no effective change.",
        current=1,
        total=1,
        finding_count=0,
    )


@pytest.mark.asyncio
async def test_repaired_empty_candidate_preserves_attempt_and_warning() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(
            responses=[cast(JsonValue, {"invalid": True}), _empty_candidate()]
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
        agent=_AgentExecutor(responses=[_empty_candidate()]),
        no_op=no_op,
    )

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(LogicalFinalizationFailedError) as raised,
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
    assert "Logical Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_tool_assisted_uses_local_catalog_and_same_change_contract() -> None:
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
    catalog = request.local_tool_catalog
    assert isinstance(catalog, InMemoryAgentContextToolCatalog)
    assert request.allowed_tool_names == catalog.allowed_tool_names
    assert request.context == {"original_context": catalog.manifest, "repair": None}
    assert [change.dataset for change in handoff.calls[0]] == [
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
    ]
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_validation_repair_keeps_original_context_then_hands_off_once() -> None:
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
    first = cast(dict[str, JsonValue], agent.requests[0].context)
    repaired = cast(dict[str, JsonValue], agent.requests[1].context)
    assert repaired["original_context"] == first["original_context"]
    repair = cast(dict[str, JsonValue], repaired["repair"])
    assert repair["validation_issues"]
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].status == "warning"


@pytest.mark.asyncio
async def test_failure_is_safe_and_never_hands_off_partial_output() -> None:
    diagnostic = "token=secret; raw prompt and provider trace"
    agent = _AgentExecutor(responses=[RuntimeError(diagnostic)])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(LogicalExecutionFailedError) as raised:
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
        "logical_execution_failed",
        "Logical authoring failed before a validated draft was committed.",
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
        pytest.raises(LogicalFinalizationFailedError) as raised,
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
    assert "Logical Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_fixed_plan_mismatch_is_rejected_before_agent_execution() -> None:
    bad_plan = _plan().model_copy(update={"model_workflow": "conceptual"})
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=bad_plan,
    )

    with pytest.raises(InvalidRequestError):
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
    assert lifecycle.failed is not None


@pytest.mark.asyncio
async def test_detailed_coverage_runs_fixed_loops_then_one_atomic_handoff() -> None:
    agent = _AgentExecutor(
        responses=cast(list[JsonValue | Exception], _detailed_candidates())
    )
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
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
    assert [request.stage for request in agent.requests] == [
        "topology_builder",
        "topology_reconciler",
        "entity_detail_builder",
        "whole_model_reconciliation",
        "validator_worker",
        "validator_lead",
    ]
    assert all(
        request.execution_mode == "detailed_coverage" for request in agent.requests
    )
    assert all(request.allowed_tool_names == () for request in agent.requests)
    assert len(handoff.calls) == 1
    assert result.staged_record_count == 4
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_detailed_coverage_projects_maximal_supporting_assertion_without_losing_sources() -> (
    None
):
    assertion_text = "é" * 200_000
    assertion_record = {
        "modeling_assertion_record_key": "Customer.Rule.1",
        "modeling_assertion_document_name": "Customer Rules",
        "modeling_assertion_record_type": "business_rule",
        "modeling_assertion_text": assertion_text,
        "modeling_assertion_details": {"rule_kind": "identity"},
        "modeling_assertion_source_location": {"page": 1},
        "modeling_assertion_applicable_layers": ("logical",),
        "modeling_assertion_confidence": "high",
        "modeling_assertion_record_status": "active",
        "modeling_assertion_record_is_locked": False,
    }
    bundle = _context_bundle(
        mode="detailed_coverage",
        assertion={
            "documents": (
                {
                    "modeling_assertion_document_name": "Customer Rules",
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "modeling_assertion_file_pattern": None,
                    "modeling_assertion_document_type": "policy",
                    "modeling_assertion_document_description": "Customer policy.",
                    "modeling_assertion_document_metadata": {},
                    "is_active": True,
                },
            ),
            "records": (assertion_record,),
        },
    )
    agent = _AgentExecutor(
        responses=cast(list[JsonValue | Exception], _detailed_candidates())
    )
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
        context_bundle=bundle,
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
    assert lifecycle.failed is None
    assert len(handoff.calls) == 1
    assert all(
        agent_request_envelope_bytes(request) <= 128 * 1024
        for request in agent.requests
    )
    original_context = cast(dict[str, JsonValue], agent.requests[0].context)[
        "original_context"
    ]
    projected = cast(dict[str, JsonValue], original_context)
    manifest = cast(dict[str, JsonValue], projected["batch_manifest"])
    selected = cast(dict[str, JsonValue], projected["selected_object"])
    assertions = cast(dict[str, JsonValue], projected["assertions"])
    record_section = cast(dict[str, JsonValue], assertions["records"])
    record_projection = cast(
        dict[str, JsonValue],
        cast(list[JsonValue], record_section["records"])[0],
    )
    assert manifest["records_are_lossless"] is True
    assert (
        cast(dict[str, JsonValue], selected["object"])["object_name"] == "customer_raw"
    )
    assert len(cast(list[JsonValue], selected["attributes"])) == 1
    assert record_projection["projection_kind"] == "bounded_semantic_projection"
    assert record_projection["canonical_utf8_bytes"] == logical_json_bytes(
        cast(JsonValue, assertion_record)
    )
    assert record_projection["canonical_sha256"] == logical_json_digest(
        cast(JsonValue, assertion_record)
    )


@pytest.mark.asyncio
async def test_detailed_coverage_fails_closed_when_one_authoritative_object_cannot_fit() -> (
    None
):
    base = _context_bundle(mode="detailed_coverage")
    selected = base.context.selected_objects[0]
    oversized_object = selected.object.model_copy(
        update={"object_description": "x" * 200_000}
    )
    oversized_context = base.context.model_copy(
        update={
            "selected_objects": (
                selected.model_copy(update={"object": oversized_object}),
            )
        }
    )
    bundle = AgentContextBundle(
        context=oversized_context,
        embedded_context=cast(JsonValue, oversized_context.model_dump(mode="json")),
    )
    agent = _AgentExecutor(responses=[])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
        context_bundle=bundle,
    )

    with pytest.raises(InvalidRequestError, match="authoritative|selected Logical"):
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
    assert lifecycle.failed is not None


def test_detailed_topology_pages_maximum_legal_selected_attribute_count_exactly() -> (
    None
):
    bundle = _context_bundle(mode="detailed_coverage")
    selected = bundle.context.selected_objects[0]
    source_attribute = selected.attributes[0]
    attributes = tuple(
        source_attribute.model_copy(
            update={
                "attribute_name": f"source_attribute_{position:05d}",
                "attribute_ordinal_position": position,
                "attribute_description": "Bounded source Attribute.",
            }
        )
        for position in range(1, 20_001)
    )
    selected = selected.model_copy(update={"attributes": attributes})
    service, *_ = _service(
        agent=_LocalFakeAgent(),
        plan=_plan(mode="detailed_coverage"),
        context_bundle=bundle,
    )

    batches = service._topology_builder_batches(  # pyright: ignore[reportPrivateUsage]
        plan=_plan(mode="detailed_coverage"),
        context=bundle,
        selected=selected,
    )

    assert len(batches) > 1
    assert len({batch.contribution_ref for batch in batches}) == len(batches)
    assert tuple(
        attribute.attribute_name
        for batch in batches
        for attribute in batch.source_attributes
    ) == tuple(attribute.attribute_name for attribute in attributes)
    for batch in batches:
        stage_context = cast(dict[str, JsonValue], batch.context)
        selected_slice = cast(dict[str, JsonValue], stage_context["selected_object"])
        attribute_values = cast(list[JsonValue], selected_slice["attributes"])
        manifest = cast(dict[str, JsonValue], stage_context["batch_manifest"])
        assert manifest["record_count"] == len(attribute_values)
        assert manifest["ordered_record_digest"] == logical_json_digest(
            cast(JsonValue, attribute_values)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("attribute_count", [24, 50, 100, 200])
async def test_detailed_coverage_byte_pages_many_attributes_without_source_loss(
    attribute_count: int,
) -> None:
    base = _context_bundle(mode="detailed_coverage")
    selected = base.context.selected_objects[0]
    source_attribute = selected.attributes[0]
    attributes = tuple(
        source_attribute.model_copy(
            update={
                "attribute_name": f"source_attribute_{position:03d}",
                "attribute_ordinal_position": position,
                "attribute_description": f"Source Attribute {position}.",
            }
        )
        for position in range(1, attribute_count + 1)
    )
    paged_context = base.context.model_copy(
        update={
            "selected_objects": (
                selected.model_copy(update={"attributes": attributes}),
            )
        }
    )
    bundle = AgentContextBundle(
        context=paged_context,
        embedded_context=cast(JsonValue, paged_context.model_dump(mode="json")),
    )
    agent = _LocalFakeAgent()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
        context_bundle=bundle,
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
    assert lifecycle.failed is None
    assert len(handoff.calls) == 1
    if attribute_count >= 100:
        assert (
            sum(request.stage == "topology_builder" for request in agent.requests) > 1
        )
    assert (
        sum(request.stage == "entity_detail_builder" for request in agent.requests) > 1
    )
    if attribute_count >= 50:
        assert (
            sum(
                request.stage == "whole_model_reconciliation"
                for request in agent.requests
            )
            > 1
        )
    assert all(
        agent_request_envelope_bytes(request) <= 128 * 1024
        for request in agent.requests
    )
    assert all(
        cast(dict[str, JsonValue], request.context)["repair"] is None
        for request in agent.requests
    )
    attribute_change = next(
        change for change in handoff.calls[0] if change.dataset == "logical_attribute"
    )
    represented_sources = {
        cast(str, source_attribute["attribute_name"])
        for record in attribute_change.records
        for source in cast(list[dict[str, JsonValue]], record["sources"])
        if source.get("support_source_type") == "attribute"
        for source_attribute in [cast(dict[str, JsonValue], source["source_attribute"])]
    }
    assert represented_sources == {
        f"source_attribute_{position:03d}" for position in range(1, attribute_count + 1)
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "expected_status"),
    [("not_logical", "running"), ("needs_review", "warning")],
)
async def test_detailed_empty_coverage_completes_with_true_no_op_event(
    disposition: Literal["not_logical", "needs_review"],
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
                    "contribution_ref": "object_00001",
                    "source_object": source,
                    "disposition": disposition,
                    "rationale": "The source has no represented Logical entity.",
                    "proposals": [],
                },
                {
                    "submodels": [],
                    "entities": [],
                    "discarded_contribution_refs": [],
                },
                {
                    "submodels": [],
                    "entities": [],
                    "attributes": [],
                    "relationships": [],
                    "reviewed_submodel_refs": [],
                    "reviewed_entity_refs": [],
                    "reviewed_relationship_signal_refs": [],
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
        "topology_builder",
        "topology_reconciler",
        "whole_model_reconciliation",
    ]
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert no_op.requests[0].final_event.sequence == 7
    assert no_op.requests[0].final_event.attempt == 1
    assert no_op.requests[0].final_event.status == expected_status


@pytest.mark.asyncio
async def test_detailed_blocker_repairs_only_whole_model_from_immutable_context() -> (
    None
):
    agent = _AgentExecutor(
        responses=cast(
            list[JsonValue | Exception],
            _detailed_candidates(blocking_first=True),
        )
    )
    service, _database, _authorizer, handoff, _lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage", retry_count=1),
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
        "topology_builder",
        "topology_reconciler",
        "entity_detail_builder",
        "whole_model_reconciliation",
        "validator_worker",
        "validator_lead",
        "whole_model_reconciliation",
        "validator_worker",
        "validator_lead",
    ]
    first = cast(dict[str, JsonValue], agent.requests[3].context)
    repaired = cast(dict[str, JsonValue], agent.requests[6].context)
    assert repaired["original_context"] == first["original_context"]
    assert "logical.review_required" in agent.requests[6].instruction_prompt
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].status == "warning"
