# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ModelingAssertionDocumentRecord,
    ModelingAssertionRecordRecord,
    PhysicalAttributeKey,
    ProfilingProfileRecord,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.analysis import service as analysis_service
from gds_workbench_api.features.analysis.candidate import AnalysisInferenceRelationship
from gds_workbench_api.features.analysis.detailed import (
    DetailedAnalysisCandidateFinderResult,
    DetailedAnalysisEndpointCandidate,
    DetailedAnalysisEvidenceSignal,
    DetailedAnalysisResolutionDecision,
    DetailedAnalysisSliceCoverage,
)
from gds_workbench_api.features.analysis.service import (
    AnalysisInferenceExecutionFailedError,
    AnalysisInferenceFinalizationFailedError,
    DatabaseAnalysisInferenceExecutor,
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
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    agent_request_envelope_bytes,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentExecutor as RepairAgentExecutor,
)
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


def _plan(
    *,
    mode: WorkflowExecutionMode = "one_shot",
    retry_count: int = 1,
    stage_code: str = "relationship_inference",
) -> AgentRunPlan:
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "model_revision": 7,
            "model_workflow": "analysis",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (501, 502),
            "selection": AgentRunSelection(
                sdk_code="langchain_create_agent",
                provider_code="databricks",
                model_code="databricks-primary",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=retry_count,
            ),
            "stages": (
                FrozenAgentStage(
                    workflow_stage_id=21,
                    stage_code=stage_code,
                    stage_order=10,
                    prompt_template_version_id=71,
                    prompt_template_digest="b" * 64,
                    templates=PromptComponentTemplates(
                        system="Infer Analysis relationships.",
                        instruction=(
                            "Use {{stage_context}}. Repair {{validation_failures}}."
                        ),
                    ),
                    variables=(
                        PromptVariableDefinition(
                            name="stage_context",
                            resolver_key=(
                                f"workflow.analysis.{mode}.relationship_inference.context"
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


def _detailed_plan() -> AgentRunPlan:
    stage_codes = (
        "candidate_finder",
        "relationship_resolver",
        "whole_slice_reconciler",
        "analysis_reviewer",
    )
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "model_revision": 7,
            "model_workflow": "analysis",
            "workflow_execution_mode": "detailed_coverage",
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (501, 502),
            "selection": AgentRunSelection(
                sdk_code="langchain_create_agent",
                provider_code="databricks",
                model_code="databricks-primary",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=1,
            ),
            "stages": tuple(
                FrozenAgentStage(
                    workflow_stage_id=21 + position,
                    stage_code=stage_code,
                    stage_order=position * 10,
                    prompt_template_version_id=71 + position,
                    prompt_template_digest=f"{position:x}" * 64,
                    templates=PromptComponentTemplates(
                        system="Infer bounded Analysis relationships.",
                        instruction=(
                            f"Use {{{{stage_context}}}} for {stage_code}. "
                            "Repair {{validation_failures}}."
                        ),
                    ),
                    variables=(
                        PromptVariableDefinition(
                            name="stage_context",
                            resolver_key=(
                                f"workflow.analysis.detailed_coverage.{stage_code}.context"
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
                )
                for position, stage_code in enumerate(stage_codes, start=1)
            ),
        },
        strict=False,
    )


def _selected_object(name: str, order: int) -> dict[str, object]:
    return {
        "selection_order": order,
        "object": {
            "tenant_code": "NWA",
            "source_tenant_code": "NWA",
            "system_code": "CRM",
            "connection_code": "SOURCE",
            "object_schema": "bronze",
            "object_name": name,
            "fc_object_schema": None,
            "fc_object_name": None,
            "object_transformation": None,
            "object_description": None,
            "batch_attribute_name": None,
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
                "object_name": name,
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
            },
        ),
    }


def _context_bundle(
    *,
    mode: WorkflowExecutionMode = "one_shot",
) -> AgentContextBundle:
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_name": "Customer Model",
            "model_revision": 7,
            "model_workflow": "analysis",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "model_details": {
                "model_name": "Customer Model",
                "model_description": None,
                "silver_model_naming_instructions": None,
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": None,
                "gold_model_technical_columns_template": None,
                "gold_model_audit_columns_template": None,
            },
            "selected_objects": (
                _selected_object("order_raw", 1),
                _selected_object("customer_raw", 2),
            ),
            "profiles": (),
            "analysis_relationships": (),
            "assertion": {"documents": (), "records": ()},
            "applied": {
                "conceptual": None,
                "logical": None,
                "dimensional": None,
                "mapping": None,
            },
        },
        strict=False,
    )
    tool_catalog = None
    embedded_context = cast(JsonValue, context.model_dump(mode="json"))
    if mode == "tool_assisted":
        tool_catalog = InMemoryAgentContextToolCatalog(
            context=context,
            max_result_bytes=128 * 1024,
            max_catalog_bytes=128 * 1024,
            max_page_records=1,
        )
        embedded_context = tool_catalog.manifest
    elif mode == "detailed_coverage":
        embedded_context = None
    return AgentContextBundle(
        context=context,
        embedded_context=embedded_context,
        tool_catalog=tool_catalog,
    )


def _candidate(*, to_name: str = "customer_raw") -> JsonValue:
    return cast(
        JsonValue,
        {
            "relationships": [
                {
                    "from_tenant_code": "NWA",
                    "from_system_code": "CRM",
                    "from_connection_code": "SOURCE",
                    "from_object_schema": "bronze",
                    "from_object_name": "order_raw",
                    "from_attribute_name": "customer_id",
                    "to_tenant_code": "NWA",
                    "to_system_code": "CRM",
                    "to_connection_code": "SOURCE",
                    "to_object_schema": "bronze",
                    "to_object_name": to_name,
                    "to_attribute_name": "customer_id",
                    "relationship_kind": "reference",
                    "relationship_confidence": "high",
                    "relationship_basis": "Metadata and profile evidence.",
                }
            ]
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
    bundle: AgentContextBundle | None = None

    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle:
        del transaction, tenant_id
        if self.bundle is not None:
            return self.bundle
        return _context_bundle(
            mode=cast(WorkflowExecutionMode, plan.workflow_execution_mode)
        )


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
        return AgentExecutionResult(candidate=response, turn_count=1, tool_call_count=0)


@dataclass
class _AdaptiveDetailedAgent:
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )
    repaired_once: bool = False
    emitted_candidate: bool = False

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        attempt = cast(dict[str, JsonValue], request.context)
        original = cast(dict[str, JsonValue], attempt["original_context"])
        if request.stage == "candidate_finder":
            slice_ref = cast(str, original["slice_ref"])
            if not self.repaired_once:
                self.repaired_once = True
                candidate = cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "coverage": {
                            "slice_ref": "wrong_slice",
                            "disposition": "no_candidate",
                        },
                        "candidates": [],
                    },
                )
            else:
                selected_objects = cast(
                    list[dict[str, JsonValue]], original["selected_objects"]
                )
                should_emit = len(selected_objects) == 2 and not self.emitted_candidate
                candidates: list[JsonValue] = []
                if should_emit:
                    self.emitted_candidate = True
                    left = cast(list[JsonValue], selected_objects[0]["attributes"])[0]
                    right = cast(list[JsonValue], selected_objects[1]["attributes"])[0]
                    candidates.append(
                        cast(
                            JsonValue,
                            {
                                "candidate_ref": f"{slice_ref}_candidate_00001",
                                "left_attribute": left,
                                "right_attribute": right,
                                "evidence_signals": [
                                    {
                                        "signal_type": "name",
                                        "signal_detail": "Bounded evidence supports review.",
                                    }
                                ],
                            },
                        )
                    )
                candidate = cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "coverage": {
                            "slice_ref": slice_ref,
                            "disposition": (
                                "candidates_found" if candidates else "no_candidate"
                            ),
                        },
                        "candidates": candidates,
                    },
                )
        elif request.stage == "relationship_resolver":
            finder = cast(dict[str, JsonValue], original["candidate_finder_result"])
            decisions: list[JsonValue] = []
            for raw_candidate in cast(list[JsonValue], finder["candidates"]):
                source = cast(dict[str, JsonValue], raw_candidate)
                left = cast(dict[str, JsonValue], source["left_attribute"])
                right = cast(dict[str, JsonValue], source["right_attribute"])
                decisions.append(
                    cast(
                        JsonValue,
                        {
                            "candidate_ref": source["candidate_ref"],
                            "disposition": "relationship",
                            "relationship": {
                                **{
                                    f"from_{name}": left[name]
                                    for name in (
                                        "tenant_code",
                                        "system_code",
                                        "connection_code",
                                        "object_schema",
                                        "object_name",
                                        "attribute_name",
                                    )
                                },
                                **{
                                    f"to_{name}": right[name]
                                    for name in (
                                        "tenant_code",
                                        "system_code",
                                        "connection_code",
                                        "object_schema",
                                        "object_name",
                                        "attribute_name",
                                    )
                                },
                                "relationship_kind": "inferred_reference",
                                "relationship_confidence": "high",
                                "relationship_basis": "Complete fragmented evidence.",
                            },
                            "rationale": "Every supplied fragment remains represented.",
                        },
                    )
                )
            candidate = cast(
                JsonValue,
                {"schema_version": "1.0", "decisions": decisions},
            )
        elif request.stage == "whole_slice_reconciler":
            candidate_coverage: list[JsonValue] = []
            applied_coverage: list[JsonValue] = []
            relationships: list[JsonValue] = []
            for raw_item in cast(
                list[JsonValue], original["reconciliation_work_items"]
            ):
                item = cast(dict[str, JsonValue], raw_item)
                reference = cast(str, item["review_ref"])
                if item["work_item_type"] == "resolution_fragment":
                    candidate_coverage.append(
                        cast(
                            JsonValue,
                            {"candidate_ref": reference, "disposition": "accepted"},
                        )
                    )
                    summary = cast(
                        dict[str, JsonValue],
                        cast(dict[str, JsonValue], item["decision_summary"])[
                            "relationship"
                        ],
                    )
                    relationships.append(
                        cast(
                            JsonValue,
                            {
                                **{
                                    name: summary[name]
                                    for name in (
                                        "from_tenant_code",
                                        "from_system_code",
                                        "from_connection_code",
                                        "from_object_schema",
                                        "from_object_name",
                                        "from_attribute_name",
                                        "to_tenant_code",
                                        "to_system_code",
                                        "to_connection_code",
                                        "to_object_schema",
                                        "to_object_name",
                                        "to_attribute_name",
                                        "relationship_kind",
                                        "relationship_confidence",
                                    )
                                },
                                "relationship_basis": "Complete fragmented evidence.",
                            },
                        )
                    )
                else:
                    applied_coverage.append(
                        cast(
                            JsonValue,
                            {
                                "applied_record_ref": reference,
                                "disposition": "preserved",
                            },
                        )
                    )
            candidate = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "candidate_coverage": candidate_coverage,
                    "applied_record_coverage": applied_coverage,
                    "relationships": relationships,
                },
            )
        elif request.stage == "analysis_reviewer":
            relationship_refs: list[str] = []
            applied_refs: list[str] = []
            for raw_item in cast(list[JsonValue], original["review_work_items"]):
                item = cast(dict[str, JsonValue], raw_item)
                reference = cast(str, item["review_ref"])
                if item["work_item_type"] == "relationship_fragment":
                    relationship_refs.append(reference)
                else:
                    applied_refs.append(reference)
            candidate = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "reviewed_relationship_refs": relationship_refs,
                    "reviewed_applied_record_refs": applied_refs,
                    "findings": [],
                },
            )
        else:
            raise AssertionError(f"Unexpected Analysis stage: {request.stage}")
        return AgentExecutionResult(
            candidate=candidate, turn_count=1, tool_call_count=0
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
        workflow_run_claim_token: UUID,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
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
    finding_count: int | None = None
    failed: tuple[str, str] | None = None

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
        **_: object,
    ) -> None:
        assert principal == _principal()
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.events.append(event)

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        finding_count: int,
        **_: object,
    ) -> AgentWorkflowTerminalResult:
        assert principal == _principal()
        self.finding_count = finding_count
        return AgentWorkflowTerminalResult(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="completed",
            completed_at=datetime.now(UTC),
        )

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
    agent: RepairAgentExecutor,
    plan: AgentRunPlan | None = None,
    no_op: _NoOp | None = None,
    context_bundle: AgentContextBundle | None = None,
    context_policy: AgentContextPolicy | None = None,
) -> tuple[
    DatabaseAnalysisInferenceExecutor, _Database, _Authorizer, _Handoff, _Lifecycle
]:
    database = _Database()
    authorizer = _Authorizer()
    handoff = _Handoff()
    lifecycle = _Lifecycle()
    selected_plan = plan or _plan()
    service = DatabaseAnalysisInferenceExecutor(
        database=database,
        authorizer=cast(Any, authorizer),
        agent_executor=agent,
        handoff=handoff,
        no_op=no_op or _NoOp(),
        lifecycle=lifecycle,
        plan_repository=_PlanRepository(selected_plan),
        context_repository=_ContextRepository(context_bundle),
        context_policy=context_policy
        or AgentContextPolicy(
            one_shot_max_context_bytes=128 * 1024,
            stage_max_context_bytes=128 * 1024,
            max_candidate_bytes=128 * 1024,
            max_validation_issues=20,
        ),
    )
    return service, database, authorizer, handoff, lifecycle


def _reconstruct_request_fragments(
    requests: list[AgentExecutionRequest],
    *,
    stage: str,
    item_key: str,
) -> dict[tuple[str, str, str], JsonValue]:
    grouped: dict[tuple[str, str, str], dict[int, dict[str, JsonValue]]] = {}
    for request in requests:
        if request.stage != stage:
            continue
        attempt = cast(dict[str, JsonValue], request.context)
        original = cast(dict[str, JsonValue], attempt["original_context"])
        for raw_item in cast(list[JsonValue], original[item_key]):
            item = cast(dict[str, JsonValue], raw_item)
            dataset = cast(str, item["dataset"])
            record_ref = cast(str, item["record_ref"])
            digest = cast(str, item["record_sha256"])
            index = cast(int, item["fragment_index"])
            key = (dataset, record_ref, digest)
            existing = grouped.setdefault(key, {}).get(index)
            if existing is not None:
                assert existing == item
            grouped[key][index] = item

    reconstructed: dict[tuple[str, str, str], JsonValue] = {}
    for key, fragments in grouped.items():
        first = fragments[min(fragments)]
        fragment_count = cast(int, first["fragment_count"])
        assert tuple(sorted(fragments)) == tuple(range(1, fragment_count + 1))
        assert all(
            cast(int, item["fragment_count"]) == fragment_count
            and item["record_byte_count"] == first["record_byte_count"]
            and item["record_sha256"] == first["record_sha256"]
            for item in fragments.values()
        )
        encoded = "".join(
            cast(str, fragments[index]["json_text"])
            for index in range(1, fragment_count + 1)
        ).encode("utf-8")
        assert len(encoded) == first["record_byte_count"]
        assert sha256(encoded).hexdigest() == first["record_sha256"]
        reconstructed[key] = cast(JsonValue, json.loads(encoded))
    return reconstructed


@pytest.mark.asyncio
@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted"))
async def test_analysis_inference_hands_off_one_validated_draft(
    execution_mode: WorkflowExecutionMode,
) -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, database, authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode=execution_mode),
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert result is not None
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_MODEL_WRITE)]
    request = agent.requests[0]
    assert (request.workflow, request.stage, request.execution_mode) == (
        "analysis_inference",
        "relationship_inference",
        execution_mode,
    )
    if execution_mode == "tool_assisted":
        assert request.local_tool_catalog is not None
        tool_catalog = cast(InMemoryAgentContextToolCatalog, request.local_tool_catalog)
        assert request.allowed_tool_names == (
            "get_agent_context_manifest",
            "get_agent_context_dataset",
        )
        assert request.context == {
            "original_context": tool_catalog.manifest,
            "repair": None,
        }
    else:
        assert request.allowed_tool_names == ()
        assert request.local_tool_catalog is None
    assert len(handoff.calls) == 1
    assert handoff.calls[0][0].dataset == "analysis_result"
    assert handoff.calls[0][0].records[0]["analysis_result_status"] == "active"
    assert handoff.final_events[-1].finding_count == 1
    assert lifecycle.failed is None
    assert [
        (event.sequence, event.stage)
        for event in (*lifecycle.events, *handoff.final_events)
    ] == [
        (2, "analysis.relationship_inference"),
        (3, "analysis.backend_validation"),
    ]


@pytest.mark.asyncio
async def test_detailed_analysis_runs_bounded_slices_then_reconciles_and_reviews() -> (
    None
):
    raw_relationships = cast(dict[str, JsonValue], _candidate())["relationships"]
    assert isinstance(raw_relationships, list)
    relationship = cast(dict[str, JsonValue], raw_relationships[0])
    agent = _AgentExecutor(
        responses=[
            {
                "schema_version": "1.0",
                "coverage": {
                    "slice_ref": "slice_00001",
                    "disposition": "no_candidate",
                },
                "candidates": [],
            },
            {
                "schema_version": "1.0",
                "coverage": {
                    "slice_ref": "slice_00002",
                    "disposition": "candidates_found",
                },
                "candidates": [
                    {
                        "candidate_ref": "slice_00002_candidate_00001",
                        "left_attribute": {
                            "tenant_code": "NWA",
                            "system_code": "CRM",
                            "connection_code": "SOURCE",
                            "object_schema": "bronze",
                            "object_name": "order_raw",
                            "attribute_name": "customer_id",
                        },
                        "right_attribute": {
                            "tenant_code": "NWA",
                            "system_code": "CRM",
                            "connection_code": "SOURCE",
                            "object_schema": "bronze",
                            "object_name": "customer_raw",
                            "attribute_name": "customer_id",
                        },
                        "evidence_signals": [
                            {
                                "signal_type": "name",
                                "signal_detail": "Normalized Attribute names match.",
                            }
                        ],
                    }
                ],
            },
            {
                "schema_version": "1.0",
                "coverage": {
                    "slice_ref": "slice_00003",
                    "disposition": "no_candidate",
                },
                "candidates": [],
            },
            {
                "schema_version": "1.0",
                "decisions": [
                    {
                        "candidate_ref": "slice_00002_candidate_00001",
                        "disposition": "relationship",
                        "relationship": relationship,
                        "rationale": "The bounded evidence supports a reference.",
                    }
                ],
            },
            {
                "schema_version": "1.0",
                "candidate_coverage": [
                    {
                        "candidate_ref": "slice_00002_candidate_00001",
                        "disposition": "accepted",
                    }
                ],
                "applied_record_coverage": [],
                "relationships": [relationship],
            },
            {
                "schema_version": "1.0",
                "reviewed_relationship_refs": ["relationship_00001"],
                "reviewed_applied_record_refs": [],
                "findings": [],
            },
        ]
    )
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_detailed_plan(),
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert result is not None
    assert [request.stage for request in agent.requests] == [
        "candidate_finder",
        "candidate_finder",
        "candidate_finder",
        "relationship_resolver",
        "whole_slice_reconciler",
        "analysis_reviewer",
    ]
    assert all(
        request.execution_mode == "detailed_coverage" for request in agent.requests
    )
    assert all(request.local_tool_catalog is None for request in agent.requests)
    assert len(handoff.calls) == 1
    assert handoff.calls[0][0].dataset == "analysis_result"
    assert [
        (event.sequence, event.stage)
        for event in (*lifecycle.events, *handoff.final_events)
    ] == [
        (2, "analysis.candidate_finder"),
        (3, "analysis.relationship_resolver"),
        (4, "analysis.whole_slice_reconciler"),
        (5, "analysis.analysis_reviewer"),
        (6, "analysis.backend_validation"),
    ]


@pytest.mark.asyncio
async def test_detailed_analysis_preserves_maximal_multibyte_evidence_with_bounded_requests() -> (
    None
):
    wide_code = "é" * 100
    wide_schema = "é" * 400
    object_names = ("é" * 399 + "A", "é" * 399 + "B")
    attribute_names = ("é" * 399 + "X", "é" * 399 + "Y")
    selected_objects: list[dict[str, object]] = []
    profiles: list[ProfilingProfileRecord] = []
    for order, (object_name, attribute_name) in enumerate(
        zip(object_names, attribute_names, strict=True),
        start=1,
    ):
        selected = _selected_object(object_name, order)
        object_record = cast(dict[str, object], selected["object"])
        object_record.update(
            {
                "tenant_code": wide_code,
                "system_code": wide_code,
                "connection_code": wide_code,
                "object_schema": wide_schema,
                "object_description": "é" * 20_000,
                "object_transformation": "é" * 20_000,
            }
        )
        attribute = cast(tuple[dict[str, object], ...], selected["attributes"])[0]
        attribute.update(
            {
                "tenant_code": wide_code,
                "system_code": wide_code,
                "connection_code": wide_code,
                "object_schema": wide_schema,
                "attribute_name": attribute_name,
                "attribute_description": "é" * 20_000,
                "attribute_custom_code": "é" * 20_000,
            }
        )
        selected_objects.append(selected)
        profiles.append(
            ProfilingProfileRecord(
                tenant_code=wide_code,
                system_code=wide_code,
                connection_code=wide_code,
                object_schema=wide_schema,
                object_name=object_name,
                attribute_name=attribute_name,
                row_count=100,
                non_null_count=90,
                null_count=10,
                blank_count=0,
                distinct_count=80,
            )
        )

    assertion_document = ModelingAssertionDocumentRecord(
        modeling_assertion_document_name="requirements.md",
        tenant_code=wide_code,
        system_code=wide_code,
        modeling_assertion_file_pattern="*.md",
        modeling_assertion_document_type="requirements",
        modeling_assertion_document_description="é" * 2_000,
        modeling_assertion_document_metadata={"note": "é" * 30_000},
        is_active=True,
    )
    assertion_record = ModelingAssertionRecordRecord(
        modeling_assertion_record_key="analysis.maximal.multibyte",
        modeling_assertion_document_name="requirements.md",
        modeling_assertion_record_type="business_rule",
        modeling_assertion_text="é" * 262_144,
        modeling_assertion_details={
            "detail_a": "é" * 32_768,
            "detail_b": "é" * 32_768,
            "detail_c": "é" * 32_768,
        },
        modeling_assertion_source_location={"locator": "é" * 30_000},
        modeling_assertion_applicable_layers=("analysis",),
        modeling_assertion_confidence="high",
        modeling_assertion_record_status="active",
        modeling_assertion_record_is_locked=False,
    )
    applied = AnalysisResultRecord(
        from_tenant_code=wide_code,
        from_system_code=wide_code,
        from_connection_code=wide_code,
        from_object_schema=wide_schema,
        from_object_name=object_names[0],
        from_attribute_name=attribute_names[0],
        to_tenant_code=wide_code,
        to_system_code=wide_code,
        to_connection_code=wide_code,
        to_object_schema=wide_schema,
        to_object_name=object_names[1],
        to_attribute_name=attribute_names[1],
        relationship_kind="reference",
        relationship_confidence="high",
        relationship_basis="é" * 262_144,
        analysis_result_status="active",
        analysis_result_is_locked=False,
    )
    raw_context = _context_bundle(mode="detailed_coverage").context.model_dump(
        mode="json"
    )
    raw_context.update(
        {
            "selected_objects": selected_objects,
            "profiles": [profile.model_dump(mode="json") for profile in profiles],
            "analysis_relationships": [applied.model_dump(mode="json")],
            "assertion": {
                "documents": [assertion_document.model_dump(mode="json")],
                "records": [assertion_record.model_dump(mode="json")],
            },
        }
    )
    context = AgentAuthoringContext.model_validate(raw_context, strict=False)
    bundle = AgentContextBundle(context=context, embedded_context=None)
    policy = AgentContextPolicy(
        one_shot_max_context_bytes=512 * 1_024,
        stage_max_context_bytes=512 * 1_024,
        max_candidate_bytes=512 * 1_024,
        max_validation_issues=20,
    )
    agent = _AdaptiveDetailedAgent()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_detailed_plan(),
        context_bundle=bundle,
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

    assert result is not None
    assert lifecycle.failed is None
    assert agent.repaired_once
    assert any(
        cast(dict[str, JsonValue], request.context)["repair"] is not None
        for request in agent.requests
    )
    assert all(
        agent_request_envelope_bytes(request) <= policy.stage_max_context_bytes
        for request in agent.requests
    )
    detailed_limit = analysis_service._detailed_stage_context_limit(policy)
    assert all(
        analysis_service._json_bytes(
            cast(dict[str, JsonValue], request.context)["original_context"]
        )
        <= (
            detailed_limit // 2
            if request.stage == "candidate_finder"
            else detailed_limit
        )
        for request in agent.requests
    )

    finder_records = _reconstruct_request_fragments(
        agent.requests,
        stage="candidate_finder",
        item_key="evidence_fragments",
    )
    finder_values = list(finder_records.values())
    assert assertion_document.model_dump(mode="json") in finder_values
    assert assertion_record.model_dump(mode="json") in finder_values
    assert all(profile.model_dump(mode="json") in finder_values for profile in profiles)
    assert applied.model_dump(mode="json") in finder_values
    for selected in context.selected_objects:
        assert selected.object.model_dump(mode="json") in finder_values
        assert all(
            attribute.model_dump(mode="json") in finder_values
            for attribute in selected.attributes
        )

    reconciliation_records = _reconstruct_request_fragments(
        agent.requests,
        stage="whole_slice_reconciler",
        item_key="reconciliation_work_items",
    )
    review_records = _reconstruct_request_fragments(
        agent.requests,
        stage="analysis_reviewer",
        item_key="review_work_items",
    )
    assert applied.model_dump(mode="json") in reconciliation_records.values()
    assert applied.model_dump(mode="json") in review_records.values()
    assert len(handoff.calls) == 1
    assert len(handoff.calls[0][0].records) == 1
    assert handoff.calls[0][0].records[0]["relationship_kind"] == "inferred_reference"


def test_detailed_analysis_pages_every_assertion_for_each_attribute_slice() -> None:
    bundle = _context_bundle(mode="detailed_coverage")
    records = tuple(
        ModelingAssertionRecordRecord(
            modeling_assertion_record_key=f"analysis-rule-{position}",
            modeling_assertion_document_name="requirements.md",
            modeling_assertion_record_type="business_rule",
            modeling_assertion_text=f"Rule {position}: " + "x" * 1_800,
            modeling_assertion_details={},
            modeling_assertion_source_location=None,
            modeling_assertion_applicable_layers=("analysis",),
            modeling_assertion_confidence="high",
            modeling_assertion_record_status="active",
            modeling_assertion_record_is_locked=False,
        )
        for position in range(1, 7)
    )
    context = bundle.context.model_copy(
        update={
            "assertion": bundle.context.assertion.model_copy(
                update={"records": records}
            )
        }
    )
    slices = tuple(
        analysis_service._candidate_finder_slices(
            AgentContextBundle(context=context, embedded_context=None),
            maximum_context_bytes=8_192,
        )
    )
    order_one_self_slices = [
        item
        for item in slices
        if len(
            cast(
                list[JsonValue],
                cast(dict[str, JsonValue], item.context)["selected_objects"],
            )
        )
        == 1
        and cast(
            dict[str, JsonValue],
            cast(
                list[JsonValue],
                cast(dict[str, JsonValue], item.context)["selected_objects"],
            )[0],
        )["selection_order"]
        == 1
    ]
    fragments_by_record: dict[str, list[dict[str, JsonValue]]] = {}
    for item in order_one_self_slices:
        raw_fragments = cast(
            list[JsonValue],
            cast(dict[str, JsonValue], item.context)["evidence_fragments"],
        )
        for raw_fragment in raw_fragments:
            fragment = cast(dict[str, JsonValue], raw_fragment)
            if fragment["dataset"] == "modeling_assertion_record":
                fragments_by_record.setdefault(
                    cast(str, fragment["record_ref"]), []
                ).append(fragment)
    reconstructed = [
        cast(
            dict[str, JsonValue],
            json.loads(
                "".join(
                    cast(str, fragment["json_text"])
                    for fragment in sorted(
                        fragments,
                        key=lambda value: cast(int, value["fragment_index"]),
                    )
                )
            ),
        )
        for _, fragments in sorted(fragments_by_record.items())
    ]
    covered_keys = [item["modeling_assertion_record_key"] for item in reconstructed]

    assert covered_keys == [record.modeling_assertion_record_key for record in records]
    assert reconstructed == [record.model_dump(mode="json") for record in records]
    assert all(analysis_service._json_bytes(item.context) <= 8_192 for item in slices)


def test_detailed_analysis_emits_slices_for_object_without_attributes() -> None:
    bundle = _context_bundle(mode="detailed_coverage")
    selected = bundle.context.selected_objects
    context = bundle.context.model_copy(
        update={
            "selected_objects": (
                selected[0],
                selected[1].model_copy(update={"attributes": ()}),
            )
        }
    )
    slices = tuple(
        analysis_service._candidate_finder_slices(
            AgentContextBundle(context=context, embedded_context=None),
            maximum_context_bytes=64 * 1_024,
        )
    )

    assert [
        (bool(item.left_attributes), bool(item.right_attributes)) for item in slices
    ] == [
        (True, True),
        (True, False),
        (False, False),
    ]


def test_detailed_analysis_resolver_batches_fit_input_and_minimum_output_bounds() -> (
    None
):
    left_attributes = tuple(
        PhysicalAttributeKey(
            tenant_code="NWA",
            system_code="CRM",
            connection_code="SOURCE",
            object_schema="bronze",
            object_name="order_raw",
            attribute_name=f"column_{position:05d}",
        )
        for position in range(400)
    )
    right_attributes = tuple(
        item.model_copy(update={"object_name": "customer_raw"})
        for item in left_attributes
    )
    candidates = tuple(
        DetailedAnalysisEndpointCandidate(
            candidate_ref=f"slice_00001_candidate_{position + 1:05d}",
            left_attribute=left,
            right_attribute=right,
            evidence_signals=(
                DetailedAnalysisEvidenceSignal(signal_type="name", signal_detail="x"),
            ),
        )
        for position, (left, right) in enumerate(
            zip(left_attributes, right_attributes, strict=True)
        )
    )
    finder = DetailedAnalysisCandidateFinderResult(
        coverage=DetailedAnalysisSliceCoverage(
            slice_ref="slice_00001",
            disposition="candidates_found",
        ),
        candidates=candidates,
    )
    finder_slice = analysis_service._DetailedFinderSlice(
        slice_ref="slice_00001",
        context={"schema_version": "1.0", "evidence": "bounded"},
        left_attributes=left_attributes,
        right_attributes=right_attributes,
    )
    batches = tuple(
        analysis_service._resolver_batches(
            finder_slice=finder_slice,
            finder=finder,
            applied_by_ref={},
            maximum_context_bytes=128 * 1_024,
            maximum_result_bytes=128 * 1_024,
        )
    )

    assert len(batches) > 1
    assert tuple(item.candidate_ref for _, batch in batches for item in batch) == tuple(
        item.candidate_ref for item in candidates
    )
    assert all(
        analysis_service._json_bytes(context) <= 128 * 1_024
        and analysis_service._json_bytes(
            analysis_service._minimum_resolution_result(batch)
        )
        <= 128 * 1_024
        for context, batch in batches
    )


def test_detailed_analysis_fragments_matching_applied_record_without_loss() -> None:
    relationship = AnalysisInferenceRelationship.model_validate(
        cast(
            list[JsonValue], cast(dict[str, JsonValue], _candidate())["relationships"]
        )[0],
        strict=True,
    )
    applied = AnalysisResultRecord.model_validate(
        {
            **relationship.model_dump(mode="json"),
            "validation_policy_version": None,
            "validation_result": None,
            "validation_source_non_null_count": None,
            "validation_source_distinct_count": None,
            "validation_target_non_null_count": None,
            "validation_target_distinct_count": None,
            "validation_source_missing_target_count": None,
            "validation_unused_target_count": None,
            "validation_duplicate_target_key_count": None,
            "analysis_result_status": "active",
            "analysis_result_is_locked": False,
        },
        strict=False,
    )
    decisions = tuple(
        DetailedAnalysisResolutionDecision(
            candidate_ref=f"slice_00001_candidate_{position:05d}",
            disposition="relationship",
            relationship=(
                relationship
                if position == 8
                else relationship.model_copy(
                    update={
                        "from_attribute_name": f"from_{position}",
                        "to_attribute_name": f"to_{position}",
                    }
                )
            ),
            rationale="x",
        )
        for position in range(1, 9)
    )
    batches = tuple(
        analysis_service._reconciliation_batches(
            _context_bundle(mode="detailed_coverage"),
            decisions=decisions,
            applied_by_ref={"applied_00001": applied},
            maximum_context_bytes=4_096,
        )
    )
    work_items = [
        cast(dict[str, JsonValue], item)
        for context, _, _ in batches
        for item in cast(
            list[JsonValue],
            cast(dict[str, JsonValue], context)["reconciliation_work_items"],
        )
    ]
    decision_fragments = [
        item for item in work_items if item["record_ref"] == decisions[-1].candidate_ref
    ]
    applied_fragments = [
        item for item in work_items if item["record_ref"] == "applied_00001"
    ]

    assert json.loads(
        "".join(
            cast(str, item["json_text"])
            for item in sorted(
                decision_fragments,
                key=lambda value: cast(int, value["fragment_index"]),
            )
        )
    ) == decisions[-1].model_dump(mode="json")
    assert json.loads(
        "".join(
            cast(str, item["json_text"])
            for item in sorted(
                applied_fragments,
                key=lambda value: cast(int, value["fragment_index"]),
            )
        )
    ) == applied.model_dump(mode="json")
    assert all(
        analysis_service._json_bytes(context) <= 4_096 for context, _, _ in batches
    )


def test_detailed_analysis_relationship_merge_is_order_independent() -> None:
    first = AnalysisInferenceRelationship.model_validate(
        cast(
            list[JsonValue], cast(dict[str, JsonValue], _candidate())["relationships"]
        )[0],
        strict=True,
    )
    second = first.model_copy(
        update={
            "relationship_confidence": "low",
            "relationship_basis": "Alternative complete-fragment interpretation.",
        }
    )

    forward = analysis_service._merge_inference_relationships(first, second)
    reverse = analysis_service._merge_inference_relationships(second, first)

    assert forward == reverse
    assert forward in (first, second)


@pytest.mark.asyncio
@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted"))
async def test_empty_analysis_inference_completes_without_a_change_set(
    execution_mode: WorkflowExecutionMode,
) -> None:
    agent = _AgentExecutor(responses=[{"relationships": []}])
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode=execution_mode),
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

    assert result is None
    assert handoff.calls == []
    assert lifecycle.finding_count is None
    assert len(no_op.requests) == 1
    request = no_op.requests[0]
    assert request.expected_execution_mode == execution_mode
    assert request.candidate_digest == authoring_no_op_candidate_digest(
        _plan(mode=execution_mode)
    )
    assert request.final_event == AgentWorkflowEvent(
        sequence=3,
        attempt=1,
        stage="analysis.backend_validation",
        status="running",
        message="Analysis inference completed without effective changes.",
        current=1,
        total=1,
        finding_count=0,
    )


@pytest.mark.asyncio
async def test_analysis_no_op_error_never_marks_the_run_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = "token=secret; no-op commit acknowledgement unavailable"
    no_op = _NoOp(completion_error=RuntimeError(diagnostic))
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=_AgentExecutor(responses=[{"relationships": []}]),
        no_op=no_op,
    )

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(AnalysisInferenceFinalizationFailedError) as raised,
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
    assert "Analysis Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_analysis_inference_repairs_against_immutable_context() -> None:
    agent = _AgentExecutor(responses=[_candidate(to_name="outside_raw"), _candidate()])
    service, _database, _authorizer, handoff, _lifecycle = _service(agent=agent)

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    first = cast(dict[str, JsonValue], agent.requests[0].context)
    repaired = cast(dict[str, JsonValue], agent.requests[1].context)
    assert repaired["original_context"] == first["original_context"]
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].status == "warning"


@pytest.mark.asyncio
async def test_analysis_inference_fails_safely_without_partial_handoff() -> None:
    diagnostic = "token=secret; raw provider output"
    agent = _AgentExecutor(responses=[RuntimeError(diagnostic)])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(AnalysisInferenceExecutionFailedError) as raised:
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
        "analysis_inference_execution_failed",
        "Analysis inference failed before a validated draft was committed.",
    )
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_analysis_finalizer_error_never_marks_the_run_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = "token=secret; commit acknowledgement unavailable"
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)
    handoff.finalization_error = RuntimeError(diagnostic)

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(AnalysisInferenceFinalizationFailedError) as raised,
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
    assert "Analysis Workflow Run finalization remains pending." in caplog.messages
    assert diagnostic not in caplog.text
    assert diagnostic not in str(raised.value)


@pytest.mark.asyncio
async def test_analysis_inference_rejects_the_wrong_stage_path() -> None:
    agent = _AgentExecutor(responses=[])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(stage_code="unsupported_stage"),
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
    assert lifecycle.failed is not None
