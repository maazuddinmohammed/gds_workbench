"""Logical Build and Optimize executors over synthetic contexts; no provider or database calls."""

# Packages Optimize contexts with the repository's own private packaging.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
    validate_future_graph,
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import PhysicalObjectKey
from gds_etl_workbench.domain.snapshots.project import (
    ProjectChangeSetDataset,
    SubjectAreaSection,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from pydantic import JsonValue
from tests.mcp.project_test_fixtures import snapshot_from_graph
from tests.web_backend.workflow_recovery_fixtures import RetainingHandoff

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.logical.service import (
    LogicalExecutionFailedError,
    LogicalFinalizationFailedError,
    LogicalWorkflow,
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
    AgentContextLimits,
    InMemoryAgentContextToolCatalog,
    modeled_layer_dependencies,
)
from gds_workbench_api.features.workflows.authoring.context import (
    _context_bundle as package_context,
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
    PlannedSubjectArea,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
    AgentContextPolicy,
)
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)

_CLAIM_TOKEN = UUID("44444444-4444-4444-8444-444444444444")
# Byte limits stay open so each test controls only the evidence it needs.
_LIMITS = AgentContextLimits(max_tool_page_records=20)


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _plan(
    *,
    mode: str = "one_shot",
    retry_count: int = 1,
    operation: Literal["build", "optimize"] = "build",
    subject_areas: tuple[str, ...] = ("Customers",),
) -> AgentRunPlan:
    """A frozen Logical plan: one <operation>_authoring stage; Build lists its areas in order."""
    stage_code = f"{operation}_authoring"
    stage = FrozenAgentStage(
        workflow_stage_id=41 if operation == "build" else 42,
        stage_code=stage_code,
        stage_order=10 if operation == "build" else 20,
        prompt_template_version_id=91,
        prompt_template_digest="1" * 64,
        templates=PromptComponentTemplates(
            system="Author one governed Logical stage candidate.",
            instruction=(
                "Use {{stage_context}}. Follow {{naming_instructions}}. "
                "Repair {{validation_failures}}."
            ),
        ),
        variables=(
            PromptVariableDefinition(
                name="stage_context",
                resolver_key=f"workflow.logical.{mode}.{stage_code}.context",
                data_type="json",
                is_required=True,
            ),
            PromptVariableDefinition(
                name="naming_instructions",
                resolver_key="project.naming_instructions",
                data_type="text",
                is_required=False,
            ),
            PromptVariableDefinition(
                name="validation_failures",
                resolver_key="workflow.validation_failures",
                data_type="json",
                is_required=False,
            ),
        ),
    )
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "project_revision": 7,
            "project_workflow": "logical",
            "workflow_execution_mode": mode,
            "workflow_operation": operation,
            "subject_areas": tuple(
                PlannedSubjectArea(
                    subject_area_id=60 + position,
                    subject_area_name=name,
                    subject_area_definition=f"{name} business area.",
                )
                for position, name in enumerate(subject_areas, start=1)
            )
            if operation == "build"
            else (),
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
            "stages": (stage,),
        },
        strict=False,
    )


def _selected_object(
    *,
    selection_order: int = 1,
    object_name: str = "customer_raw",
    key_name: str = "customer_id",
) -> dict[str, object]:
    """One selected bronze CRM table with its business key column."""
    noun = object_name.removesuffix("_raw").replace("_", " ").capitalize()
    return {
        "selection_order": selection_order,
        "object": {
            "tenant_code": "NWA",
            "source_tenant_code": "NWA",
            "system_code": "CRM",
            "connection_code": "SOURCE",
            "object_schema": "bronze",
            "object_name": object_name,
            "fc_object_schema": None,
            "fc_object_name": None,
            "object_transformation": None,
            "object_description": f"{noun} source metadata.",
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
                "object_name": object_name,
                "attribute_name": key_name,
                "fc_attribute_name": None,
                "attribute_ordinal_position": 1,
                "attribute_description": f"{noun} identifier.",
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
    context_section: dict[str, object] | None = None,
    operation: Literal["build", "optimize"] = "build",
    selected_objects: Sequence[dict[str, object]] | None = None,
    subject_areas: dict[str, tuple[str, ...]] | None = None,
) -> AgentContextBundle:
    """The run's loaded context, before the private snapshot is added.

    Subject Areas map an area name to member Object names, all active CRM bronze tables. By
    default one Customers area holds every selected Object. Like the repository, a Build
    bundle carries no packaged context because each area call packages its own;
    _validation_context packages an Optimize context with its snapshot.
    """
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": 18,
            "project_name": "Customer Project",
            "project_revision": 7,
            "project_workflow": "logical",
            "workflow_execution_mode": mode,
            "workflow_operation": operation,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "project_details": {
                "project_name": "Customer Project",
                "project_description": None,
                "logical_schemas": [{"schema_name": "silver", "description": None}],
                "dimensional_schemas": [{"schema_name": "gold", "description": None}],
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
            "selected_objects": tuple(selected_objects or (_selected_object(),)),
            "profiles": (),
            "analysis_relationships": (),
            "context": context_section
            or {
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
                "subject_area": None,
                "logical": None,
                "dimensional": None,
                "mapping": None,
            },
        },
        strict=False,
    )
    members = subject_areas or {
        "Customers": tuple(item.object.object_name for item in context.selected_objects)
    }
    section: dict[str, object] = {
        "areas": [
            {
                "subject_area_name": name,
                "subject_area_definition": f"{name} business area.",
                "subject_area_is_active": True,
                "subject_area_is_locked": False,
            }
            for name in members
        ],
        "tables": [
            {
                "subject_area_name": name,
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "SOURCE",
                "object_schema": "bronze",
                "object_name": object_name,
                "subject_area_table_is_active": True,
                "subject_area_table_is_locked": False,
            }
            for name, object_names in members.items()
            for object_name in object_names
        ],
    }
    applied = context.applied.model_copy(
        update={"subject_area": SubjectAreaSection.model_validate(section, strict=False)}
    )
    return AgentContextBundle(
        context=context.model_copy(update={"applied": applied}),
        embedded_context={},
        limits=_LIMITS,
    )


def _candidate(*, table_id: str = "t1") -> JsonValue:
    """One compact Logical answer citing the selected Object by its table_index id."""
    return cast(
        JsonValue,
        {
            "entities": [
                {
                    "schema": "silver",
                    "name": "Customer",
                    "type": "core",
                    "definition": "One customer.",
                    "grain": "One row per customer.",
                    "sources": [table_id],
                    "attributes": [
                        {
                            "name": "Customer Id",
                            "type": "bigint",
                            "natural_key": True,
                            "from": f"{table_id}.customer_id",
                        }
                    ],
                }
            ],
            "relationships": [],
            "retire": [],
        },
    )


def _empty_candidate() -> JsonValue:
    return cast(JsonValue, {"entities": [], "relationships": [], "retire": []})


def _saved_customer() -> dict[ProjectChangeSetDataset, list[dict[str, object]]]:
    """The applied Customer Entity in complete saved-record form."""
    object_key: dict[str, object] = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": "customer_raw",
    }
    return {
        "logical_entity": [
            {
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Customer",
                "logical_entity_definition": "One customer.",
                "logical_entity_type": "core",
                "logical_entity_grain": "One row per customer.",
                "logical_entity_dependency_order": 0,
                "logical_entity_is_active": True,
                "logical_entity_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": object_key,
                        "rationale": "Primary customer source.",
                        "is_active": True,
                        "is_locked": False,
                    }
                ],
            }
        ],
        "logical_attribute": [
            {
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Customer",
                "logical_attribute_name": "Customer Id",
                "logical_attribute_definition": "Customer identifier.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 1,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_is_active": True,
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {**object_key, "attribute_name": "customer_id"},
                        "rationale": None,
                        "is_active": True,
                        "is_locked": False,
                    }
                ],
            }
        ],
    }


def _mapped_customer() -> dict[ProjectChangeSetDataset, list[dict[str, object]]]:
    """The saved Customer with active Mapping that depends on it."""
    return {
        **_saved_customer(),
        "mapping_object": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": "Customer",
                "source_system_code": "CRM",
                "output_template_code": None,
                "object_dependency_order": 0,
                "mapping_transformation_document": {"kind": "select"},
                "object_mapping_status": "active",
                "object_mapping_is_locked": False,
            }
        ],
        "mapping_attribute": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": "Customer",
                "modeled_attribute_name": "Customer Id",
                "source_system_code": "CRM",
                "output_template_code": None,
                "attribute_mapping_transformation_document": {"kind": "direct"},
                "attribute_mapping_status": "active",
                "attribute_mapping_is_locked": False,
            }
        ],
    }


def _validation_context(
    bundle: AgentContextBundle,
    *,
    graph: dict[ProjectChangeSetDataset, list[dict[str, object]]] | None = None,
) -> AgentContextBundle:
    """Add what the repository loads with a context: the private snapshot and physical scope.

    As in production the applied Logical model and its downstream dependencies come from the
    snapshot, and an Optimize context is packaged whole for its single call.
    """
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
    records: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
        **(graph or {}),
        "project_details": [context.project_details.model_dump(mode="json")],
        "project_input_scope": [
            {
                **item.model_dump(mode="json"),
                "project_input_scope_is_locked": False,
                "is_active": True,
            }
            for item in objects
        ],
        "context_group": [item.model_dump(mode="json") for item in context.context.groups],
        "context_record": [item.model_dump(mode="json") for item in context.context.records],
    }
    snapshot = snapshot_from_graph(records).model_copy(
        update={
            "project_id": context.project_id,
            "project_revision": context.project_revision,
        }
    )
    physical_scope = PhysicalProjectCatalog(
        project_tenant_code="NWA",
        active_system_codes=frozenset({"crm"}),
        objects=cast(Any, source_objects),
        attributes=cast(Any, source_attributes),
        project_input_objects=cast(Any, source_objects),
        project_input_attributes=cast(Any, source_attributes),
    )
    context = context.model_copy(
        update={
            "applied": context.applied.model_copy(update={"logical": snapshot.logical}),
            "read_only_dependencies": modeled_layer_dependencies(
                snapshot, modeled_entity_type="logical_entity"
            ),
        }
    )
    if context.workflow_operation == "optimize":
        return package_context(
            context,
            plan=_plan(mode=context.workflow_execution_mode or "one_shot", operation="optimize"),
            limits=_LIMITS,
            snapshot=snapshot,
            physical_scope=physical_scope,
        )
    return replace(bundle, context=context, snapshot=snapshot, physical_scope=physical_scope)


def _mapped_context_bundle(mode: str, *, include_audit_columns: bool = True) -> AgentContextBundle:
    """A valid applied graph: the saved Customer and Mapping that depends on it."""
    bundle = _context_bundle(mode=mode)
    context = bundle.context.model_copy(
        update={
            "project_details": bundle.context.project_details.model_copy(
                update={
                    "silver_model_audit_columns_template": None
                    if include_audit_columns
                    else {"schema_version": "1.0", "columns": []}
                }
            ),
        }
    )
    bundle = _validation_context(replace(bundle, context=context), graph=_mapped_customer())
    assert bundle.snapshot is not None and bundle.physical_scope is not None
    assert validate_future_graph(
        snapshot=bundle.snapshot,
        staged_documents={},
        physical_scope=bundle.physical_scope,
    ).valid
    return bundle


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
        project_id: int | None = None,
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
        project_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan:
        del transaction, tenant_id, project_id, workflow_run_id
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
        changes: tuple[StageProjectChange, ...],
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
        assert tenant_id == 7
        assert project_id == 18
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
    context_policy: AgentContextPolicy | None = None,
) -> tuple[LogicalWorkflow, _Database, _Authorizer, _Handoff, _Lifecycle]:
    selected_plan = plan or _plan()
    database = _Database()
    authorizer = _Authorizer()
    handoff = _Handoff()
    lifecycle = _Lifecycle()
    return (
        LogicalWorkflow(
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
                    mode=selected_plan.workflow_execution_mode or "one_shot",
                    operation=selected_plan.workflow_operation or "build",
                )
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


async def _execute(service: LogicalWorkflow) -> object:
    return await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )


def _original_context(request: AgentExecutionRequest) -> dict[str, Any]:
    return cast(dict[str, Any], request.context)["original_context"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_start_binds_logical_workflow_without_executing(
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

    assert lifecycle.starts == [(principal, 7, 18, 1048, "logical", mode, 7)]
    assert result.workflow_run_id == 1048
    assert result.project_revision == 7
    assert database.isolations == []
    assert authorizer.calls == []
    assert handoff.calls == []
    assert agent.requests == []
    assert lifecycle.events == []
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_build_projects_audit_columns_then_hands_off_once() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, database, authorizer, handoff, lifecycle = _service(agent=agent)

    result = await _execute(service)

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 4
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_PROJECT_WRITE)]
    request = agent.requests[0]
    assert request.workflow == "logical"
    assert request.stage == "build_authoring"
    assert request.execution_mode == "one_shot"
    assert request.allowed_tool_names == ()
    assert "Use business language." in request.instruction_prompt
    assert cast(dict[str, Any], request.context)["repair"] is None
    # The call sees its Subject Area, not the whole run.
    original = _original_context(request)
    assert original["build_subject_area"] == {
        "name": "Customers",
        "definition": "Customers business area.",
    }
    assert original["prompt_inputs"]["subject_area_context"] == {
        "name": "Customers",
        "definition": "Customers business area.",
        "input_count": 1,
    }
    assert [item["table"] for item in original["prompt_inputs"]["table_index"]] == ["t1"]
    assert len(handoff.calls) == 1
    attribute_change = next(
        change for change in handoff.calls[0] if change.dataset == "logical_attribute"
    )
    assert [record["logical_attribute_name"] for record in attribute_change.records] == [
        "Created At",
        "Customer Id",
        "CustomerID",
    ]
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.stage, event.message)
        for event in (*lifecycle.events, *handoff.final_events)
    ] == [
        (2, "logical.build_authoring", "Building Customers (1 of 1): 1 Object."),
        (3, "logical.backend_validation", "Logical build is ready in a validated draft."),
    ]
    assert handoff.final_events[-1].finding_count == 4


@pytest.mark.asyncio
async def test_build_calls_each_subject_area_in_plan_order_and_hands_off_one_draft() -> None:
    order: JsonValue = {
        "entities": [
            {
                "schema": "silver",
                "name": "Order",
                "type": "transaction",
                "definition": "One order.",
                "grain": "One row per order.",
                "sources": ["t2"],
                "attributes": [
                    {
                        "name": "Order Id",
                        "type": "bigint",
                        "natural_key": True,
                        "from": "t2.order_id",
                    }
                ],
            }
        ],
        "relationships": [],
        "retire": [],
    }
    agent = _AgentExecutor(responses=[_candidate(), order])
    bundle = _context_bundle(
        selected_objects=(
            _selected_object(),
            _selected_object(selection_order=2, object_name="order_raw", key_name="order_id"),
        ),
        # Orders shares customer_raw, so its call must reuse Customer, not recreate it.
        subject_areas={"Customers": ("customer_raw",), "Orders": ("customer_raw", "order_raw")},
    )
    service, _, _, handoff, lifecycle = _service(
        agent=agent, plan=_plan(subject_areas=("Customers", "Orders")), context_bundle=bundle
    )

    await _execute(service)

    assert [
        _original_context(request)["build_subject_area"]["name"] for request in agent.requests
    ] == ["Customers", "Orders"]
    second = _original_context(agent.requests[1])["prompt_inputs"]
    assert [item["object_name"] for item in second["table_index"]] == ["customer_raw", "order_raw"]
    existing = second["existing_entities"]["entities"]
    assert [(entity["name"], entity["sources"]) for entity in existing] == [("Customer", ["t1"])]
    assert [event.message for event in lifecycle.events] == [
        "Building Customers (1 of 2): 1 Object.",
        "Building Orders (2 of 2): 2 Objects.",
    ]
    assert [(event.current, event.total) for event in lifecycle.events] == [(0, 2), (1, 2)]
    assert len(handoff.calls) == 1
    entities = next(change for change in handoff.calls[0] if change.dataset == "logical_entity")
    assert [record["logical_entity_name"] for record in entities.records] == ["Customer", "Order"]
    assert handoff.final_events[-1].message == "Logical build is ready in a validated draft."
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_build_skips_a_subject_area_without_selected_objects_with_a_warning() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    bundle = _context_bundle(
        subject_areas={"Archive": ("customer_archive",), "Customers": ("customer_raw",)}
    )
    service, _, _, handoff, lifecycle = _service(
        agent=agent, plan=_plan(subject_areas=("Archive", "Customers")), context_bundle=bundle
    )

    await _execute(service)

    assert len(agent.requests) == 1
    assert [event.message for event in lifecycle.events] == [
        "Building Customers (2 of 2): 1 Object."
    ]
    assert len(handoff.calls) == 1
    final = handoff.final_events[-1]
    assert final.status == "warning"
    assert final.message == "Logical build completed with notes. Archive: skipped."


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_optimize_reviews_the_whole_model_in_one_call_without_coverage(
    mode: str,
) -> None:
    # Retiring the only Entity leaves the selection uncovered; Optimize only cleans up.
    retire: JsonValue = {
        "entities": [],
        "relationships": [],
        "retire": [{"schema": "silver", "entity": "Customer"}],
    }
    agent = _AgentExecutor(responses=[retire])
    bundle = _validation_context(
        _context_bundle(mode=mode, operation="optimize"), graph=_saved_customer()
    )
    service, _, _, handoff, lifecycle = _service(
        agent=agent, plan=_plan(mode=mode, operation="optimize"), context_bundle=bundle
    )

    await _execute(service)

    assert len(agent.requests) == 1
    request = agent.requests[0]
    assert request.stage == "optimize_authoring"
    assert request.context == {"original_context": bundle.embedded_context, "repair": None}
    if mode == "one_shot":
        summary = _original_context(request)["prompt_inputs"]["model_summary"]
        assert [entity["name"] for entity in summary["entities"]] == ["Customer"]
    else:
        assert request.local_tool_catalog is bundle.tool_catalog
    assert [(event.stage, event.message) for event in lifecycle.events] == [
        ("logical.optimize_authoring", "Optimizing the whole Logical model.")
    ]
    assert len(handoff.calls) == 1
    entity = next(change for change in handoff.calls[0] if change.dataset == "logical_entity")
    assert [
        (record["logical_entity_name"], record["logical_entity_is_active"])
        for record in entity.records
    ] == [("Customer", False)]
    final = handoff.final_events[-1]
    assert (final.status, final.message) == (
        "running",
        "Logical optimize is ready in a validated draft.",
    )
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_empty_candidate_completes_only_when_applied_sources_cover_selection() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[_empty_candidate()]),
        no_op=no_op,
        context_bundle=_mapped_context_bundle("one_shot", include_audit_columns=False),
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert handoff.calls == []
    assert lifecycle.failed is None
    assert len(no_op.requests) == 1
    request = no_op.requests[0]
    assert request.candidate_digest == authoring_no_op_candidate_digest(_plan())
    event = request.final_event
    assert (event.sequence, event.attempt, event.stage, event.status) == (
        3,
        1,
        "logical.backend_validation",
        "running",
    )
    assert event.message.rstrip() == "Logical build produced no effective change."
    assert (event.current, event.total, event.finding_count) == (1, 1, 0)


@pytest.mark.asyncio
async def test_repaired_empty_candidate_preserves_attempt_and_warning() -> None:
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[cast(JsonValue, {"invalid": True}), _empty_candidate()]),
        no_op=no_op,
        context_bundle=_mapped_context_bundle("one_shot", include_audit_columns=False),
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed_with_repair"
    assert no_op.requests[0].final_event.attempt == 2
    assert no_op.requests[0].final_event.status == "warning"
    assert "Customers: repaired." in no_op.requests[0].final_event.message
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
        context_bundle=_mapped_context_bundle("one_shot", include_audit_columns=False),
    )

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(LogicalFinalizationFailedError) as raised,
    ):
        await _execute(service)

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

    await _execute(service)

    request = agent.requests[0]
    catalog = request.local_tool_catalog
    assert isinstance(catalog, InMemoryAgentContextToolCatalog)
    assert request.allowed_tool_names == catalog.allowed_tool_names
    assert request.context == {"original_context": catalog.manifest, "repair": None}
    assert [change.dataset for change in handoff.calls[0]] == [
        "logical_entity",
        "logical_attribute",
    ]
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_validation_repair_keeps_original_context_then_hands_off_once() -> None:
    agent = _AgentExecutor(responses=[_candidate(table_id="t9"), _candidate()])
    service, _database, _authorizer, handoff, _lifecycle = _service(agent=agent)

    await _execute(service)

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
async def test_full_graph_mapping_failure_is_repaired_before_handoff(mode: str) -> None:
    bundle = _mapped_context_bundle(mode)
    # Retiring the mapped Entity also retires its Attributes; Mapping still uses both.
    invalid = cast(
        dict[str, list[dict[str, object]]],
        {
            "entities": [],
            "relationships": [],
            "retire": [{"schema": "silver", "entity": "Customer"}],
        },
    )
    corrected = cast(
        dict[str, list[dict[str, object]]],
        {
            "entities": [
                {
                    "schema": "silver",
                    "name": "Customer",
                    "definition": "One customer identified by the CRM business key.",
                }
            ],
            "relationships": [],
            "retire": [],
        },
    )
    agent = _AgentExecutor(responses=cast(list[JsonValue | Exception], [invalid, corrected]))
    service, _, _, handoff, lifecycle = _service(
        agent=agent, plan=_plan(mode=mode), context_bundle=bundle
    )

    await _execute(service)

    assert len(agent.requests) == 2
    assert _original_context(agent.requests[1]) == _original_context(agent.requests[0])
    repaired = cast(dict[str, Any], agent.requests[1].context)
    assert repaired["repair"]["validation_issues"][:2] == [
        {
            "code": "candidate.active_dependency_invalid",
            "path": ["mapping_object", "modeled_entity_name"],
            "message": "Active Mapping Object requires an active Entity.",
        },
        {
            "code": "candidate.active_dependency_invalid",
            "path": ["mapping_attribute", "modeled_attribute_name"],
            "message": "Active Mapping Attribute requires active Mapping and modeled Attribute.",
        },
    ]
    # The downstream Mapping that constrains the answer reaches the agent read-only.
    if mode == "tool_assisted":
        catalog = agent.requests[0].local_tool_catalog
        assert isinstance(catalog, InMemoryAgentContextToolCatalog)
        page = cast(
            dict[str, Any],
            catalog.invoke(
                "get_agent_context_dataset",
                {"dataset": "read_only_mapping_object", "offset": 0, "limit": 1},
            ),
        )
        assert page["items"][0]["modeled_entity_name"] == "Customer"
    else:
        dependencies = repaired["original_context"]["read_only_dependencies"]
        assert any(
            item["dataset"] == "mapping_object"
            and item["record"]["modeled_entity_name"] == "Customer"
            for item in dependencies
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
        == corrected["entities"][0]["definition"]
    )
    assert handoff.final_events[-1].attempt == 2
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_post_policy_graph_failure_retains_canonical_rejected_draft() -> None:
    bundle = _mapped_context_bundle("one_shot")
    assert bundle.snapshot is not None
    details = _context_bundle().context.project_details
    bundle = replace(
        bundle,
        context=bundle.context.model_copy(update={"project_details": details}),
        snapshot=bundle.snapshot.model_copy(
            update={
                "project_input_scope": bundle.snapshot.project_input_scope.model_copy(
                    update={"details": details}
                ),
            }
        ),
    )
    # Partial Mapping is valid; an active Mapping pointing at an inactive
    # modeled Attribute remains a real full-graph integrity violation.
    retire_mapped_attribute: JsonValue = {
        "entities": [],
        "relationships": [],
        "retire": [{"schema": "silver", "entity": "Customer", "attribute": "Customer Id"}],
    }
    candidates = [retire_mapped_attribute, deepcopy(retire_mapped_attribute)]
    agent = _AgentExecutor(responses=cast(list[JsonValue | Exception], candidates))
    service, _, _, handoff, lifecycle = _service(agent=agent, context_bundle=bundle)

    with pytest.raises(AgentCandidateValidationError):
        await _execute(service)

    assert len(agent.requests) == 2
    issues = cast(dict[str, Any], agent.requests[1].context)["repair"]["validation_issues"]
    assert any(issue["path"][0] == "mapping_attribute" for issue in issues)
    assert handoff.calls == []
    assert len(handoff.retained) == 1
    retained = handoff.retained[0]
    assert retained["failure_code"] == "agent_candidate_validation_failed"
    assert retained["issues"][0].dataset == "mapping_attribute"
    attributes = next(
        change for change in retained["changes"] if change.dataset == "logical_attribute"
    )
    assert any(record["logical_attribute_name"] == "Created At" for record in attributes.records)
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_failed_area_keeps_earlier_areas_and_its_answer_in_the_rejected_draft() -> None:
    bundle = _validation_context(
        _context_bundle(
            selected_objects=(
                _selected_object(),
                _selected_object(selection_order=2, object_name="order_raw", key_name="order_id"),
            ),
            subject_areas={"Orders": ("order_raw",), "Customers": ("customer_raw",)},
        ),
        graph=_mapped_customer(),
    )
    order: JsonValue = {
        "entities": [
            {
                "schema": "silver",
                "name": "Order",
                "type": "transaction",
                "definition": "One order.",
                "grain": "One row per order.",
                "sources": ["t1"],
                "attributes": [
                    {
                        "name": "Order Id",
                        "type": "bigint",
                        "natural_key": True,
                        "from": "t1.order_id",
                    }
                ],
            }
        ],
        "relationships": [],
        "retire": [],
    }
    # Mapping still uses Customer Id, so the Customers answer fails on every attempt.
    retire_mapped_attribute: JsonValue = {
        "entities": [],
        "relationships": [],
        "retire": [{"schema": "silver", "entity": "Customer", "attribute": "Customer Id"}],
    }
    agent = _AgentExecutor(
        responses=[order, retire_mapped_attribute, deepcopy(retire_mapped_attribute)]
    )
    service, _, _, handoff, lifecycle = _service(
        agent=agent, plan=_plan(subject_areas=("Orders", "Customers")), context_bundle=bundle
    )

    with pytest.raises(AgentCandidateValidationError):
        await _execute(service)

    assert len(agent.requests) == 3
    assert handoff.calls == []
    (retained,) = handoff.retained
    assert retained["failure_code"] == "agent_candidate_validation_failed"
    records = {
        change.dataset: [
            (
                record.get("logical_entity_name"),
                record.get("logical_attribute_name"),
                record.get("logical_attribute_is_active"),
            )
            for record in change.records
        ]
        for change in retained["changes"]
    }
    assert ("Order", None, None) in records["logical_entity"]
    assert ("Customer", "Customer Id", False) in records["logical_attribute"]
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_failure_is_safe_and_never_hands_off_partial_output() -> None:
    diagnostic = "token=secret; raw prompt and provider trace"
    agent = _AgentExecutor(responses=[RuntimeError(diagnostic)])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(LogicalExecutionFailedError) as raised:
        await _execute(service)

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
        await _execute(service)

    assert len(handoff.calls) == 1
    assert lifecycle.failed is None
    assert "Logical Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    [
        {"project_workflow": "subject_area"},
        # The single stage must be the operation's own: build_authoring for a Build.
        {"stages": _plan(operation="optimize").stages},
        {"stages": (_plan().stages[0].model_copy(update={"stage_code": "candidate_authoring"}),)},
        {"stages": (*_plan().stages, *_plan(operation="optimize").stages)},
    ],
)
async def test_fixed_plan_mismatch_is_rejected_before_agent_execution(
    mismatch: dict[str, object],
) -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan().model_copy(update=mismatch),
    )

    with pytest.raises(InvalidRequestError):
        await _execute(service)

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.failed is not None
