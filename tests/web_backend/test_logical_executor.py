from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
    validate_future_graph,
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import PhysicalObjectKey
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_workbench_api.capabilities import AgentRunSelection
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
    modeled_layer_dependencies,
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
    AgentCandidateValidationError,
    AgentContextPolicy,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from pydantic import JsonValue

from tests.mcp.model_test_fixtures import snapshot_from_graph
from tests.web_backend.workflow_recovery_fixtures import RetainingHandoff

_CLAIM_TOKEN = UUID("44444444-4444-4444-8444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _plan(*, mode: str = "one_shot", retry_count: int = 1) -> AgentRunPlan:
    stage_codes = ("candidate_authoring",)
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
        if stage_code in {"candidate_authoring"}:
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
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
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
                "attribute_inferred_data_type": None,
                "is_locked": False,
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


def _validation_context(
    bundle: AgentContextBundle,
    *,
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]] | None = None,
) -> AgentContextBundle:
    context = bundle.context
    objects = [
        PhysicalObjectKey.model_validate(item.object.model_dump(), extra="ignore")
        for item in context.selected_objects
    ]
    ordered_source_keys = tuple(
        tuple(str(value).casefold() for value in item.model_dump().values()) for item in objects
    )
    source_objects = frozenset(ordered_source_keys)
    source_attributes = frozenset(
        (*key, attribute.attribute_name.casefold())
        for key, selected in zip(ordered_source_keys, context.selected_objects, strict=True)
        for attribute in selected.attributes
    )
    records: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        **(graph or {}),
        "model_details": [context.model_details.model_dump(mode="json")],
        "model_input_scope": [
            {
                **item.model_dump(mode="json"),
                "model_input_scope_is_locked": False,
                "is_active": True,
            }
            for item in objects
        ],
        "modeling_assertion_document": [
            item.model_dump(mode="json") for item in context.assertion.documents
        ],
        "modeling_assertion_record": [
            item.model_dump(mode="json") for item in context.assertion.records
        ],
    }
    snapshot = snapshot_from_graph(records).model_copy(
        update={"model_id": context.model_id, "model_revision": context.model_revision}
    )
    target_objects = frozenset(
        tuple(
            str(value).casefold()
            for value in PhysicalObjectKey.model_validate(item, extra="ignore")
            .model_dump()
            .values()
        )
        for item in records.get("model_object_binding", [])
    )
    target_attributes = frozenset(
        (*key, str(attribute["attribute_name"]).casefold())
        for key in target_objects
        for attribute in records.get("model_attribute_binding", [])
    )
    physical_scope = PhysicalModelCatalog(
        model_tenant_code="NWA",
        active_system_codes=frozenset({"crm"}),
        objects=cast(Any, source_objects | target_objects),
        attributes=cast(Any, source_attributes | target_attributes),
        model_input_objects=cast(Any, source_objects),
        model_input_attributes=cast(Any, source_attributes),
        dimensional_source_objects=frozenset(),
        dimensional_source_attributes=frozenset(),
        logical_mapping_target_objects=cast(Any, target_objects),
        logical_mapping_target_attributes=cast(Any, target_attributes),
        dimensional_mapping_target_objects=frozenset(),
        dimensional_mapping_target_attributes=frozenset(),
    )
    return replace(bundle, snapshot=snapshot, physical_scope=physical_scope)


def _bound_context_bundle(mode: str) -> AgentContextBundle:
    bundle = _context_bundle(mode=mode)
    bundle = replace(
        bundle,
        context=bundle.context.model_copy(
            update={
                "model_details": bundle.context.model_details.model_copy(
                    update={"silver_model_audit_columns_template": None}
                ),
            }
        ),
    )
    candidate = cast(dict[str, list[dict[str, object]]], _candidate())
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        "logical_submodel": candidate["submodels"],
        "logical_entity": candidate["entities"],
        "logical_attribute": candidate["attributes"],
        "model_object_binding": [
            {
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "TARGET",
                "object_schema": "silver",
                "object_name": "customer",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Customer",
                "model_object_binding_status": "active",
                "model_object_binding_is_locked": False,
            }
        ],
        "model_attribute_binding": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Customer",
                "modeled_attribute_name": "Customer Id",
                "attribute_name": "customer_id",
                "model_attribute_binding_status": "active",
                "model_attribute_binding_is_locked": False,
            }
        ],
    }
    bundle = _validation_context(bundle, graph=graph)
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    assert validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={},
        physical_scope=bundle.physical_scope,
    ).valid
    context = bundle.context.model_copy(
        update={
            "applied": bundle.context.applied.model_copy(
                update={"logical": bundle.snapshot.logical}
            ),
            "read_only_dependencies": modeled_layer_dependencies(
                bundle.snapshot, modeled_entity_type="logical_entity"
            ),
        }
    )
    catalog = (
        InMemoryAgentContextToolCatalog(
            context=context,
            max_result_bytes=128 * 1024,
            max_catalog_bytes=128 * 1024,
            max_page_records=20,
        )
        if mode == "tool_assisted"
        else None
    )
    return replace(
        bundle,
        context=context,
        tool_catalog=catalog,
        embedded_context=catalog.manifest
        if catalog is not None
        else cast(JsonValue, context.model_dump(mode="json")),
    )


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
        return self.bundle if self.bundle.snapshot is not None else _validation_context(self.bundle)


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
                "completed_with_repair" if request.final_event.attempt > 1 else "completed"
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
    events: list[AgentWorkflowEvent] = field(default_factory=lambda: list[AgentWorkflowEvent]())
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
                or _context_bundle(mode=selected_plan.workflow_execution_mode or "one_shot")
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
    assert [record["logical_attribute_name"] for record in attribute_change.records] == [
        "Created At",
        "Customer Id",
    ]
    assert handoff.final_events[-1].finding_count == 4
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.stage) for event in (*lifecycle.events, *handoff.final_events)
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
        agent=_AgentExecutor(responses=[cast(JsonValue, {"invalid": True}), _empty_candidate()]),
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
    agent = _AgentExecutor(responses=[_candidate(source_name="outside_selection"), _candidate()])
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
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_full_graph_binding_failure_is_repaired_before_handoff(mode: str) -> None:
    bundle = _bound_context_bundle(mode)
    invalid = cast(dict[str, list[dict[str, object]]], _candidate())
    invalid["entities"][0]["logical_entity_status"] = "inactive"
    corrected = cast(dict[str, list[dict[str, object]]], _candidate())
    corrected["entities"][0]["logical_entity_definition"] = (
        "One customer identified by the CRM business key."
    )
    agent = _AgentExecutor(responses=cast(list[JsonValue | Exception], [invalid, corrected]))
    service, _, _, handoff, lifecycle = _service(
        agent=agent, plan=_plan(mode=mode), context_bundle=bundle
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert len(agent.requests) == 2
    repaired = cast(dict[str, Any], agent.requests[1].context)
    assert (
        repaired["original_context"]
        == cast(dict[str, Any], agent.requests[0].context)["original_context"]
    )
    assert repaired["repair"]["validation_issues"] == [
        {
            "code": "candidate.active_dependency_invalid",
            "path": ["logical_attribute", "logical_entity_name"],
            "message": "Active Logical Attribute requires an active parent Entity.",
        },
        {
            "code": "candidate.active_dependency_invalid",
            "path": ["model_object_binding", "modeled_entity_name"],
            "message": "Active Object Binding requires an active modeled Entity.",
        },
    ]
    if mode == "tool_assisted":
        assert bundle.tool_catalog is not None
        page = cast(
            dict[str, Any],
            bundle.tool_catalog.invoke(
                "get_agent_context_dataset",
                {
                    "dataset": "read_only_model_object_binding",
                    "offset": 0,
                    "limit": 1,
                },
            ),
        )
        assert page["items"][0]["modeled_entity_name"] == "Customer"
    else:
        assert (
            repaired["original_context"]["read_only_dependencies"][0]["record"][
                "modeled_entity_name"
            ]
            == "Customer"
        )
    assert len(handoff.calls) == 1
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    assert validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={change.dataset: change.records for change in handoff.calls[0]},
        physical_scope=bundle.physical_scope,
    ).valid
    entity_change = next(
        change for change in handoff.calls[0] if change.dataset == "logical_entity"
    )
    assert (
        entity_change.records[0]["logical_entity_definition"]
        == corrected["entities"][0]["logical_entity_definition"]
    )
    assert handoff.final_events[-1].attempt == 2
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_post_policy_graph_failure_retains_canonical_rejected_draft() -> None:
    bundle = _bound_context_bundle("one_shot")
    assert bundle.snapshot is not None
    details = _context_bundle().context.model_details
    context = bundle.context.model_copy(update={"model_details": details})
    snapshot = bundle.snapshot.model_copy(
        update={
            "model_input_scope": bundle.snapshot.model_input_scope.model_copy(
                update={"details": details}
            ),
        }
    )
    bundle = replace(
        bundle,
        context=context,
        snapshot=snapshot,
        embedded_context=cast(JsonValue, context.model_dump(mode="json")),
    )
    agent = _AgentExecutor(responses=[_candidate(), _candidate()])
    service, _, _, handoff, lifecycle = _service(agent=agent, context_bundle=bundle)

    with pytest.raises(AgentCandidateValidationError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert len(agent.requests) == 2
    issues = cast(dict[str, Any], agent.requests[1].context)["repair"]["validation_issues"]
    assert any(issue["path"][0] == "model_attribute_binding" for issue in issues)
    assert handoff.calls == []
    assert len(handoff.retained) == 1
    retained = handoff.retained[0]
    assert retained["failure_code"] == "agent_candidate_validation_failed"
    assert retained["issues"][0].dataset == "model_attribute_binding"
    attributes = next(
        change for change in retained["changes"] if change.dataset == "logical_attribute"
    )
    assert any(record["logical_attribute_name"] == "Created At" for record in attributes.records)
    assert lifecycle.failed is None


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
