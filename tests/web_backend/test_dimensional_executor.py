from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
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
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import LogicalObjectSourceRecord
from gds_etl_workbench.domain.snapshots.project import (
    DimensionalSection,
    ProjectChangeSetDataset,
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
from gds_workbench_api.features.dimensional.policy import (
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
)
from gds_workbench_api.features.dimensional.service import (
    DimensionalExecutionFailedError,
    DimensionalFinalizationFailedError,
    DimensionalWorkflow,
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
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpReceipt,
    AuthoringNoOpRequest,
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

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")
_SALES = PlannedSubjectArea(
    subject_area_id=61,
    subject_area_name="Sales",
    subject_area_definition="Customer sales activity.",
)
_BILLING = PlannedSubjectArea(
    subject_area_id=62,
    subject_area_name="Billing",
    subject_area_definition="Customer invoices.",
)
_RETURNS = PlannedSubjectArea(
    subject_area_id=63,
    subject_area_name="Returns",
    subject_area_definition="Returned goods.",
)
# The bounds a Build applies to each focused Subject Area context.
_LIMITS = AgentContextLimits(
    max_tool_result_bytes=128 * 1024,
    max_tool_catalog_bytes=128 * 1024,
    max_tool_page_records=20,
)


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("retries", [0, 2])
@pytest.mark.parametrize("final_invalid", [False, True])
@pytest.mark.parametrize("enforce", [False, True])
async def test_coverage_shortfall_uses_every_attempt_but_never_waives_other_errors(
    mode: Literal["one_shot", "tool_assisted"],
    retries: int,
    final_invalid: bool,
    enforce: bool,
) -> None:
    bundle = _context_bundle(mode=mode)
    raw = bundle.context.model_dump(mode="json")
    raw["project_details"]["dimensional_enforce_coverage_threshold"] = enforce
    second = deepcopy(raw["selected_logical_entities"][0])
    second["entity"]["logical_entity_name"] = "other_customer"
    second["selection_order"] = 2
    second["attributes"] = []
    raw["selected_logical_entities"].append(second)
    bundle = replace(bundle, context=AgentAuthoringContext.model_validate(raw, strict=False))
    candidates = [_candidate() for _ in range(retries + 1)]
    if final_invalid:
        candidates[-1] = _candidate(source_name="unselected")
    else:
        # Verify the final attempt is returned, not a saved earlier candidate.
        cast(dict[str, Any], candidates[-1])["entities"][0]["dimensional_entity_definition"] = (
            "Final attempt definition."
        )
    agent = _AgentExecutor(responses=cast(list[_AgentResponse], candidates))
    service, _, _, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode=mode, retry_count=retries),
        context=bundle,
    )
    execution = service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    if final_invalid or enforce:
        with pytest.raises(AgentCandidateValidationError):
            await execution
        assert handoff.calls == []
        if enforce and not final_invalid:
            assert handoff.retained == []
            assert lifecycle.failed is not None
            assert lifecycle.failed[0] == "agent_candidate_validation_failed"
    else:
        await execution
        assert len(handoff.calls) == 1
        assert handoff.retained == [] and lifecycle.failed is None
        event = handoff.final_events[-1]
        assert event.attempt == retries + 1 and event.status == "warning"
        # A one-area Build reports its area's shortfall once, with no separate Run total.
        assert "Sales: Coverage 1/2 is below 60%" in event.message
        assert "Run selection" not in event.message
        entities = next(
            change for change in handoff.calls[0] if change.dataset == "dimensional_entity"
        )
        assert entities.records[0]["dimensional_entity_definition"] == "Final attempt definition."
    assert len(agent.requests) == retries + 1
    for request in agent.requests[1:]:
        repair = cast(dict[str, Any], request.context)["repair"]
        assert repair["validation_issues"][0]["source_refs"] == [
            {
                "logical_entity_schema_name": "silver_nwa",
                "logical_entity_name": "other_customer",
            }
        ]


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _plan(
    *,
    mode: Literal["one_shot", "tool_assisted"] = "one_shot",
    retry_count: int = 1,
    operation: Literal["build", "optimize"] = "build",
    subject_areas: tuple[PlannedSubjectArea, ...] = (_SALES,),
) -> AgentRunPlan:
    stage_code = f"{operation}_authoring"
    stage = FrozenAgentStage(
        workflow_stage_id=141,
        stage_code=stage_code,
        stage_order=10 if operation == "build" else 20,
        prompt_template_version_id=191,
        prompt_template_digest="1" * 64,
        templates=PromptComponentTemplates(
            system="Author one governed Dimensional stage candidate.",
            instruction=(
                "Use {{stage_context}}. Follow {{naming_instructions}}. "
                "Repair {{validation_failures}}."
            ),
        ),
        variables=(
            PromptVariableDefinition(
                name="stage_context",
                resolver_key=f"workflow.dimensional.{mode}.{stage_code}.context",
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
            "project_workflow": "dimensional",
            "workflow_execution_mode": mode,
            "workflow_operation": operation,
            "subject_areas": subject_areas if operation == "build" else (),
            "modeled_entity_type": "logical_entity",
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (),
            "selected_entity_ids": (501,),
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


def _table(name: str) -> dict[str, object]:
    return {
        "tenant_code": "nwa",
        "system_code": "gds",
        "connection_code": "lakehouse",
        "object_schema": "bronze_nwa",
        "object_name": name,
    }


def _subject_areas(*areas: tuple[PlannedSubjectArea, tuple[str, ...]]) -> dict[str, object]:
    """Saved Subject Areas and their active member tables, as the Run snapshot holds them."""
    return {
        "areas": [
            {
                "subject_area_name": area.subject_area_name,
                "subject_area_definition": area.subject_area_definition,
                "subject_area_is_active": True,
                "subject_area_is_locked": False,
            }
            for area, _ in areas
        ],
        "tables": [
            {
                "subject_area_name": area.subject_area_name,
                **_table(table),
                "subject_area_table_is_active": True,
                "subject_area_table_is_locked": False,
            }
            for area, tables in areas
            for table in tables
        ],
    }


def _selected_logical_entity(
    name: str = "sales_customer", *, table: str = "sales_customer", order: int = 1
) -> dict[str, object]:
    """A Logical Entity built from one table; the table's Subject Areas decide its Builds."""
    entity: dict[str, object] = {
        "logical_entity_schema_name": "silver_nwa",
        "logical_entity_name": name,
        "logical_entity_definition": "Customer",
        "logical_entity_type": "core",
        "logical_entity_grain": "One customer",
        "logical_entity_dependency_order": 0,
        "logical_entity_is_active": True,
        "logical_entity_is_locked": False,
        "sources": [
            {
                "support_source_type": "object",
                "source_object": _table(table),
                "rationale": None,
                "is_active": True,
                "is_locked": False,
            }
        ],
    }
    return {
        "selection_order": order,
        "entity": entity,
        "attributes": [
            {
                "logical_entity_schema_name": "silver_nwa",
                "logical_entity_name": name,
                "logical_attribute_name": attribute,
                "logical_attribute_definition": attribute,
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": ordinal,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_is_active": True,
                "logical_attribute_is_locked": False,
                "sources": [],
            }
            for ordinal, attribute in enumerate(("customer_id", "sale_customer_id"), start=1)
        ],
    }


def _technical_template() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dimension_surrogate_key": {
            "semantic_name_template": "{entity_name} key",
            "data_type": "bigint",
            "nullable": False,
            "definition_template": "Surrogate key for {entity_name}.",
        },
        "fact_bridge_foreign_key": {
            "with_role_semantic_name_template": "{role_name} key",
            "without_role_semantic_name_template": "{entity_name} key",
            "definition_template": "Foreign key to {entity_name}.",
        },
        "type_2": {
            "effective_from": {
                "semantic_name": "Effective From",
                "data_type": "TIMESTAMPTZ",
                "nullable": False,
                "definition": "Type 2 effective start.",
            },
            "effective_to": {
                "semantic_name": "Effective To",
                "data_type": "TIMESTAMPTZ",
                "nullable": True,
                "definition": "Type 2 effective end.",
            },
            "is_current": {
                "semantic_name": "Is Current",
                "data_type": "BOOLEAN",
                "nullable": False,
                "definition": "Current Type 2 row.",
            },
        },
    }


def _audit_template() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "columns": [
            {
                "semantic_name": "Loaded At",
                "data_type": "TIMESTAMPTZ",
                "nullable": False,
                "definition": "Warehouse load time.",
            }
        ],
    }


def _context_bundle(
    *,
    mode: Literal["one_shot", "tool_assisted"] = "one_shot",
    operation: Literal["build", "optimize"] = "build",
) -> AgentContextBundle:
    """The loaded Run context: one Logical Entity built from the Sales area's only table."""
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": 18,
            "project_name": "Sales Project",
            "project_revision": 7,
            "project_workflow": "dimensional",
            "workflow_execution_mode": mode,
            "workflow_operation": operation,
            "modeled_entity_type": "logical_entity",
            "selected_scope_digest": "a" * 64,
            "project_details": {
                "project_name": "Sales Project",
                "project_description": None,
                "logical_schemas": [{"schema_name": "silver_nwa", "description": None}],
                "dimensional_schemas": [{"schema_name": "gold_nwa", "description": None}],
                "silver_model_naming_instructions": None,
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": "Use business-facing Gold names.",
                "gold_model_technical_columns_template": _technical_template(),
                "gold_model_audit_columns_template": _audit_template(),
            },
            "selected_objects": (),
            "selected_logical_entities": (_selected_logical_entity(),),
            "profiles": (),
            "analysis_relationships": (),
            "context": {
                "records": (
                    {
                        "context_record_id": "1cdbab8d-73b2-5b3f-a650-6d5579728c83",
                        "context_group_name": "requirements.md",
                        "context_text": "Customer segment is modeled in Gold.",
                        "status": "active",
                        "is_locked": False,
                        "source_reference": None,
                    },
                ),
                "groups": (
                    {
                        "context_group_name": "requirements.md",
                        "context_type_name": "Business Requirement",
                        "context_group_description": None,
                        "is_active": True,
                        "source_system_code": None,
                    },
                ),
                "types": [
                    {
                        "context_type_name": "Business Requirement",
                        "context_type_description": "Required business outcomes.",
                    }
                ],
            },
            "applied": {
                "subject_area": _subject_areas((_SALES, ("sales_customer",))),
                "logical": None,
                "dimensional": None,
                "mapping": None,
            },
        },
        strict=False,
    )
    if operation == "build":
        # A Build is bounded and packaged per Subject Area by focus_subject_area.
        return AgentContextBundle(context=context, embedded_context={}, limits=_LIMITS)
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
            limits=_LIMITS,
        )
    return AgentContextBundle(
        context=context,
        embedded_context=cast(JsonValue, context.model_dump(mode="json")),
        limits=_LIMITS,
    )


def _object_key(*, object_name: str = "sales_customer") -> dict[str, object]:
    return {
        "logical_entity_schema_name": "silver_nwa",
        "logical_entity_name": object_name,
    }


def _source(attribute_name: str, *, object_name: str = "sales_customer") -> list[dict[str, object]]:
    return [
        {
            "support_source_type": "logical_attribute",
            "source_logical_attribute": {
                **_object_key(object_name=object_name),
                "logical_attribute_name": attribute_name,
            },
            "rationale": "Eligible Silver contribution.",
            "is_active": True,
            "is_locked": False,
        }
    ]


def _candidate(
    *,
    source_name: str = "sales_customer",
    customer_reference_nullable: bool = False,
) -> JsonValue:
    """A Customer Dimension and a Sales Fact whose customer reference may be unknown."""
    entity_source = [
        {
            "support_source_type": "logical_entity",
            "source_logical_entity": _object_key(object_name=source_name),
            "rationale": "Eligible Silver contribution.",
            "is_active": True,
            "is_locked": False,
        }
    ]
    return cast(
        JsonValue,
        {
            "entities": [
                {
                    "dimensional_entity_schema_name": "gold_nwa",
                    "dimensional_entity_name": "Customer Dimension",
                    "dimensional_entity_definition": "One customer.",
                    "dimensional_entity_type": "dimension",
                    "dimensional_fact_type": None,
                    "dimensional_entity_grain_definition": None,
                    "dimensional_entity_dependency_order": 0,
                    "dimensional_entity_is_active": True,
                    "dimensional_entity_is_locked": False,
                    "sources": entity_source,
                },
                {
                    "dimensional_entity_schema_name": "gold_nwa",
                    "dimensional_entity_name": "Sales Fact",
                    "dimensional_entity_definition": "One sale.",
                    "dimensional_entity_type": "fact",
                    "dimensional_fact_type": "transaction",
                    "dimensional_entity_grain_definition": "One sale per customer.",
                    "dimensional_entity_dependency_order": 1,
                    "dimensional_entity_is_active": True,
                    "dimensional_entity_is_locked": False,
                    "sources": entity_source,
                },
            ],
            "attributes": [
                {
                    "dimensional_entity_schema_name": "gold_nwa",
                    "dimensional_entity_name": "Customer Dimension",
                    "dimensional_attribute_name": "Customer ID",
                    "dimensional_attribute_definition": "Customer identifier.",
                    "dimensional_attribute_data_type": "bigint",
                    "dimensional_attribute_is_nullable": False,
                    "dimensional_attribute_ordinal_position": 1,
                    "dimensional_attribute_is_natural_key": True,
                    "dimensional_attribute_is_surrogate_key": False,
                    "dimensional_attribute_is_audit_column": False,
                    "dimensional_attribute_is_active": True,
                    "dimensional_attribute_is_locked": False,
                    "sources": _source("customer_id"),
                },
                {
                    "dimensional_entity_schema_name": "gold_nwa",
                    "dimensional_entity_name": "Sales Fact",
                    "dimensional_attribute_name": "Source Customer ID",
                    "dimensional_attribute_definition": "Sale customer identifier.",
                    "dimensional_attribute_data_type": "bigint",
                    "dimensional_attribute_is_nullable": customer_reference_nullable,
                    "dimensional_attribute_ordinal_position": 1,
                    "dimensional_attribute_is_natural_key": not customer_reference_nullable,
                    "dimensional_attribute_is_surrogate_key": False,
                    "dimensional_attribute_is_audit_column": False,
                    "dimensional_attribute_is_active": True,
                    "dimensional_attribute_is_locked": False,
                    "sources": _source("sale_customer_id"),
                },
            ],
            "relationships": [
                {
                    "from_dimensional_entity_schema_name": "gold_nwa",
                    "from_dimensional_entity_name": "Sales Fact",
                    "from_dimensional_attribute_name": "Source Customer ID",
                    "to_dimensional_entity_schema_name": "gold_nwa",
                    "to_dimensional_entity_name": "Customer Dimension",
                    "to_dimensional_attribute_name": "Customer ID",
                    "dimensional_relationship_role_name": "Bill To Customer",
                    "dimensional_relationship_basis": "Sales customer evidence.",
                    "dimensional_relationship_is_active": True,
                    "dimensional_relationship_is_locked": False,
                }
            ],
        },
    )


def _applied_dimensional_section() -> DimensionalSection:
    raw = cast(dict[str, list[dict[str, object]]], _candidate())
    changes = (
        StageProjectChange(dataset="dimensional_entity", records=raw["entities"]),
        StageProjectChange(dataset="dimensional_attribute", records=raw["attributes"]),
        StageProjectChange(dataset="dimensional_relationship", records=raw["relationships"]),
    )
    projected = project_dimensional_gold_policy(
        changes=changes,
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    projected = project_dimensional_foreign_key_policy(
        changes=projected,
        applied=None,
        raw_technical_template=_technical_template(),
    )
    by_dataset = {change.dataset: change.records for change in projected}
    return DimensionalSection.model_validate(
        {
            "entities": tuple(by_dataset["dimensional_entity"]),
            "attributes": tuple(by_dataset["dimensional_attribute"]),
            "relationships": tuple(by_dataset["dimensional_relationship"]),
        },
        strict=False,
    )


def _no_op_context_bundle() -> AgentContextBundle:
    bundle = _context_bundle()
    applied = bundle.context.applied.model_copy(
        update={"dimensional": _applied_dimensional_section()}
    )
    return replace(bundle, context=bundle.context.model_copy(update={"applied": applied}))


def _no_op_candidate() -> JsonValue:
    candidate = cast(dict[str, JsonValue], deepcopy(_candidate()))
    relationship = cast(list[dict[str, JsonValue]], candidate["relationships"])[0]
    relationship["from_dimensional_attribute_name"] = "Bill To Customer key"
    relationship["to_dimensional_attribute_name"] = "Customer Dimension key"
    return cast(JsonValue, candidate)


type _AgentResponse = JsonValue | Exception | Callable[[AgentExecutionRequest], JsonValue]


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
        if self.bundle.snapshot is not None:
            return self.bundle
        # The private validation snapshot holds what the context shows: its Subject Areas,
        # the selected Logical Entities with any saved Logical links, and the applied
        # Dimensional model.
        context = self.bundle.context
        graph: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
            "project_details": [context.project_details.model_dump(mode="json")],
            "context_group": [item.model_dump(mode="json") for item in context.context.groups],
            "context_record": [item.model_dump(mode="json") for item in context.context.records],
            "logical_entity": [
                item.entity.model_dump(mode="json") for item in context.selected_logical_entities
            ],
            "logical_attribute": [
                attribute.model_dump(mode="json")
                for item in context.selected_logical_entities
                for attribute in item.attributes
            ],
        }
        areas = context.applied.subject_area
        if areas is not None:
            graph["subject_area"] = [record.model_dump(mode="json") for record in areas.areas]
            graph["subject_area_table"] = [
                record.model_dump(mode="json") for record in areas.tables
            ]
        if context.applied.logical is not None:
            graph["logical_relationship"] = [
                record.model_dump(mode="json") for record in context.applied.logical.relationships
            ]
        applied = context.applied.dimensional
        if applied:
            graph["dimensional_entity"] = [r.model_dump(mode="json") for r in applied.entities]
            graph["dimensional_attribute"] = [
                record.model_dump(mode="json") for record in applied.attributes
            ]
            graph["dimensional_relationship"] = [
                record.model_dump(mode="json") for record in applied.relationships
            ]
        # Saved Subject Area tables and Logical lineage keep their registered Objects.
        objects = frozenset(
            (
                key.tenant_code.casefold(),
                key.system_code.casefold(),
                key.connection_code.casefold(),
                key.object_schema.casefold(),
                key.object_name.casefold(),
            )
            for key in (
                *(item.object for item in context.selected_objects),
                *(() if areas is None else areas.tables),
                *(
                    source.source_object
                    for item in context.selected_logical_entities
                    for source in item.entity.sources
                    if isinstance(source, LogicalObjectSourceRecord)
                ),
            )
        )
        attributes = frozenset(
            (
                attribute.tenant_code.casefold(),
                attribute.system_code.casefold(),
                attribute.connection_code.casefold(),
                attribute.object_schema.casefold(),
                attribute.object_name.casefold(),
                attribute.attribute_name.casefold(),
            )
            for item in context.selected_objects
            for attribute in item.attributes
        )
        scope = PhysicalProjectCatalog(
            project_tenant_code="nwa",
            active_system_codes=frozenset({"gds"}),
            objects=objects,
            attributes=attributes,
            project_input_objects=frozenset(),
            project_input_attributes=frozenset(),
        )
        return replace(self.bundle, snapshot=snapshot_from_graph(graph), physical_scope=scope)


@dataclass
class _AgentExecutor:
    responses: list[_AgentResponse]
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(request)
        return AgentExecutionResult(candidate=response, turn_count=2, tool_call_count=0)


@dataclass
class _Handoff(RetainingHandoff):
    calls: list[tuple[StageProjectChange, ...]] = field(
        default_factory=lambda: list[tuple[StageProjectChange, ...]]()
    )
    workflows: list[str] = field(default_factory=lambda: list[str]())
    final_events: list[AgentWorkflowEvent] = field(
        default_factory=lambda: list[AgentWorkflowEvent]()
    )
    fail_finalize: bool = False

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_claim_token: UUID,
        expected_workflow: str,
        changes: tuple[StageProjectChange, ...],
        final_event: AgentWorkflowEvent,
        **_: object,
    ) -> WorkflowChangeSetFinalizationResult:
        assert principal == _principal()
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.workflows.append(expected_workflow)
        self.calls.append(changes)
        self.final_events.append(final_event)
        if self.fail_finalize:
            raise RuntimeError("simulated finalization failure")
        handoff = WorkflowChangeSetHandoffResult(
            project_id=18,
            workflow_run_id=1048,
            project_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            replayed=False,
            draft_revision=2,
            candidate_digest="c" * 64,
            staged_record_count=sum(len(change.records) for change in changes),
            validated_at=datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
        )
        return WorkflowChangeSetFinalizationResult(
            handoff=handoff,
            completion=AgentWorkflowTerminalResult(
                changed=True,
                workflow_run_id=1048,
                workflow_run_state=(
                    "completed_with_repair" if final_event.attempt > 1 else "completed"
                ),
                completed_at=datetime(2026, 8, 24, 10, 2, tzinfo=UTC),
            ),
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
    finding_count: int | None = None
    failed: tuple[str, str] | None = None
    fail_event_sequence: int | None = None

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
        if event.sequence == self.fail_event_sequence:
            raise RuntimeError("simulated lifecycle failure")
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


@dataclass
class _NoOp:
    requests: list[AuthoringNoOpRequest] = field(
        default_factory=lambda: list[AuthoringNoOpRequest]()
    )

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


def _service(
    *,
    agent: _AgentExecutor,
    plan: AgentRunPlan | None = None,
    context: AgentContextBundle | None = None,
    lifecycle: _Lifecycle | None = None,
    handoff: _Handoff | None = None,
    no_op: _NoOp | None = None,
) -> tuple[DimensionalWorkflow, _Database, _Authorizer, _Handoff, _Lifecycle]:
    selected_plan = plan or _plan()
    database = _Database()
    authorizer = _Authorizer()
    selected_handoff = handoff or _Handoff()
    selected_no_op = no_op or _NoOp()
    selected_lifecycle = lifecycle or _Lifecycle()
    return (
        DimensionalWorkflow(
            database=database,
            authorizer=cast(Any, authorizer),
            agent_executor=agent,
            handoff=selected_handoff,
            no_op=selected_no_op,
            lifecycle=selected_lifecycle,
            plan_repository=_PlanRepository(selected_plan),
            context_repository=_ContextRepository(
                context
                or _context_bundle(
                    mode=selected_plan.workflow_execution_mode or "one_shot",
                    operation=cast(
                        Literal["build", "optimize"], selected_plan.workflow_operation or "build"
                    ),
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
        selected_handoff,
        selected_lifecycle,
    )


async def _execute(service: DimensionalWorkflow) -> object:
    return await service.execute_started(
        _principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_project_revision=7,
    )


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_start_binds_dimensional_workflow_without_executing(
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

    assert lifecycle.starts == [(principal, 7, 18, 1048, "dimensional", mode, 7)]
    assert result.workflow_run_id == 1048
    assert result.project_revision == 7
    assert database.isolations == []
    assert authorizer.calls == []
    assert handoff.calls == []
    assert agent.requests == []
    assert lifecycle.events == []
    assert lifecycle.failed is None


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("scd_type", [None, "type_1", "type_2"])
async def test_dimensional_runs_with_optional_gold_templates_unset(
    mode: Literal["one_shot", "tool_assisted"],
    scd_type: Literal["type_1", "type_2"] | None,
) -> None:
    bundle = _context_bundle(mode=mode)
    details = bundle.context.project_details.model_copy(
        update={
            "logical_entity_scd_type": "type_1",
            "dimensional_entity_scd_type": scd_type,
            "gold_model_naming_instructions": None,
            "gold_model_technical_columns_template": None,
            "gold_model_audit_columns_template": None,
        }
    )
    bundle = replace(bundle, context=bundle.context.model_copy(update={"project_details": details}))
    agent = _AgentExecutor(responses=[_candidate()])
    service, _, _, handoff, lifecycle = _service(agent=agent, context=bundle, plan=_plan(mode=mode))
    await _execute(service)
    assert agent.requests and handoff.calls
    assert lifecycle.failed is None
    attributes = [
        row
        for change in handoff.calls[0]
        if change.dataset == "dimensional_attribute"
        for row in change.records
    ]
    dimension = [
        row for row in attributes if row["dimensional_entity_name"] == "Customer Dimension"
    ]
    names = {row["dimensional_attribute_name"] for row in dimension}
    assert "Customer DimensionKey" in names
    assert {"RecordStartTime", "RecordEndTime", "IsCurrentRecord"}.issubset(names) is (
        scd_type == "type_2"
    )
    assert sum(bool(row["dimensional_attribute_is_audit_column"]) for row in dimension) == (
        13 if scd_type == "type_2" else 10
    )


async def test_invalid_gold_policy_blocks_before_agent_execution() -> None:
    bundle = _context_bundle()
    project_details = bundle.context.project_details.model_copy(
        update={"gold_model_audit_columns_template": {"schema_version": "invalid"}}
    )
    bundle = replace(
        bundle, context=bundle.context.model_copy(update={"project_details": project_details})
    )
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent, context=bundle)

    with pytest.raises(InvalidRequestError):
        await _execute(service)

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.failed is not None


@pytest.mark.parametrize("customer_reference_nullable", [False, True])
async def test_build_projects_gold_policy_and_foreign_key_once(
    customer_reference_nullable: bool,
) -> None:
    agent = _AgentExecutor(
        responses=[_candidate(customer_reference_nullable=customer_reference_nullable)]
    )
    service, database, authorizer, handoff, lifecycle = _service(agent=agent)

    result = await _execute(service)

    # Two Entities, seven Attributes (two keys, two business, one foreign key, two audit)
    # and one Relationship.
    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 10
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_PROJECT_WRITE)]
    request = agent.requests[0]
    assert request.workflow == "dimensional"
    assert request.stage == "build_authoring"
    assert request.execution_mode == "one_shot"
    assert request.allowed_tool_names == ()
    assert "Use business-facing Gold names." in request.instruction_prompt
    # The call sees its own Subject Area, never the saved Subject Area records.
    sent = cast(dict[str, Any], request.context)
    assert sent["repair"] is None
    original = sent["original_context"]
    assert original["build_subject_area"] == {
        "name": "Sales",
        "definition": "Customer sales activity.",
    }
    assert original["prompt_inputs"]["subject_area_context"] == {
        "name": "Sales",
        "definition": "Customer sales activity.",
        "input_count": 1,
    }
    assert original["applied"]["subject_area"] is None
    assert handoff.workflows == ["dimensional"]
    assert len(handoff.calls) == 1
    attribute_change = next(
        change for change in handoff.calls[0] if change.dataset == "dimensional_attribute"
    )
    foreign_key = next(
        record
        for record in attribute_change.records
        if record["dimensional_attribute_name"] == "Bill To Customer key"
    )
    # A foreign key may be null exactly when its business customer reference may be null.
    assert foreign_key["dimensional_entity_name"] == "Sales Fact"
    assert foreign_key["dimensional_attribute_is_nullable"] is customer_reference_nullable
    relationship_change = next(
        change for change in handoff.calls[0] if change.dataset == "dimensional_relationship"
    )
    assert relationship_change.records[0]["from_dimensional_attribute_name"] == (
        "Bill To Customer key"
    )
    assert relationship_change.records[0]["to_dimensional_attribute_name"] == (
        "Customer Dimension key"
    )
    assert handoff.final_events[-1].finding_count == 10
    assert handoff.final_events[-1].message == "Dimensional build is ready in a validated draft."
    assert [event.message for event in lifecycle.events] == [
        "Building Sales (1 of 1): 1 Logical Entity."
    ]
    assert lifecycle.failed is None


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
    assert catalog.prompt_values["subject_area_context"]["name"] == "Sales"
    assert [change.dataset for change in handoff.calls[0]] == [
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
    ]
    assert lifecycle.failed is None


async def test_validation_repair_keeps_original_context_then_hands_off_once() -> None:
    agent = _AgentExecutor(responses=[_candidate(source_name="outside_selection"), _candidate()])
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
    assert "Sales: repaired." in handoff.final_events[-1].message


async def test_build_makes_one_call_per_subject_area_over_the_model_built_so_far() -> None:
    bundle = _context_bundle()
    customer_link = {
        "from_logical_entity_schema_name": "silver_nwa",
        "from_logical_entity_name": "sales_invoice",
        "from_logical_attribute_name": "sale_customer_id",
        "to_logical_entity_schema_name": "silver_nwa",
        "to_logical_entity_name": "sales_customer",
        "to_logical_attribute_name": "customer_id",
        "logical_relationship_cardinality": "many_to_one",
        "logical_relationship_basis": "Each invoice bills one customer.",
        "logical_relationship_is_active": True,
        "logical_relationship_is_locked": False,
    }
    raw = bundle.context.model_dump(mode="json")
    raw["selected_logical_entities"].append(
        _selected_logical_entity("sales_invoice", table="sales_invoice", order=2)
    )
    raw["applied"]["subject_area"] = _subject_areas(
        (_SALES, ("sales_customer",)), (_BILLING, ("sales_invoice",))
    )
    raw["applied"]["logical"] = {"entities": [], "attributes": [], "relationships": [customer_link]}
    bundle = replace(bundle, context=AgentAuthoringContext.model_validate(raw, strict=False))
    invoice = cast(dict[str, Any], _candidate(source_name="sales_invoice"))
    # The Billing call reuses the Customer Dimension the Sales call created.
    invoice["entities"] = [
        {
            **invoice["entities"][1],
            "dimensional_entity_name": "Invoice Fact",
            "dimensional_entity_definition": "One invoice.",
            "dimensional_entity_grain_definition": "One invoice per customer.",
        }
    ]
    invoice["attributes"] = [
        {
            **invoice["attributes"][1],
            "dimensional_entity_name": "Invoice Fact",
            "sources": _source("sale_customer_id", object_name="sales_invoice"),
        }
    ]
    invoice["relationships"] = [
        {
            **invoice["relationships"][0],
            "from_dimensional_entity_name": "Invoice Fact",
            "to_dimensional_attribute_name": "Customer Dimension key",
            "dimensional_relationship_role_name": None,
        }
    ]
    agent = _AgentExecutor(responses=[_candidate(), cast(JsonValue, invoice)])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent, context=bundle, plan=_plan(subject_areas=(_SALES, _BILLING))
    )

    await _execute(service)

    sales, billing = [
        cast(dict[str, Any], request.context)["original_context"]["prompt_inputs"]
        for request in agent.requests
    ]
    assert sales["subject_area_context"] == {
        "name": "Sales",
        "definition": "Customer sales activity.",
        "input_count": 1,
    }
    assert [
        item["entity"]["logical_entity_name"] for item in sales["selected_logical_entities"]
    ] == ["sales_customer"]
    assert sales["entity_directory"] == []
    assert billing["subject_area_context"] == {
        "name": "Billing",
        "definition": "Customer invoices.",
        "input_count": 1,
    }
    assert [
        item["entity"]["logical_entity_name"] for item in billing["selected_logical_entities"]
    ] == ["sales_invoice"]
    assert billing["logical_links"] == [
        {
            "from": "silver_nwa.sales_invoice.sale_customer_id",
            "to": "silver_nwa.sales_customer",
            "cardinality": "many_to_one",
        }
    ]
    # Billing sees the model as the Sales call left it.
    assert billing["existing_entities"]["entities"] == []
    assert [item["name"] for item in billing["entity_directory"]] == [
        "Customer Dimension",
        "Sales Fact",
    ]
    assert [event.message for event in lifecycle.events] == [
        "Building Sales (1 of 2): 1 Logical Entity.",
        "Building Billing (2 of 2): 1 Logical Entity.",
    ]
    assert len(handoff.calls) == 1
    staged = {
        change.dataset: [
            (record.get("dimensional_entity_name"), record.get("from_dimensional_entity_name"))
            for record in change.records
        ]
        for change in handoff.calls[0]
    }
    assert [name for name, _ in staged["dimensional_entity"]] == [
        "Customer Dimension",
        "Sales Fact",
        "Invoice Fact",
    ]
    assert [name for _, name in staged["dimensional_relationship"]] == [
        "Sales Fact",
        "Invoice Fact",
    ]
    invoice_key = next(
        record
        for change in handoff.calls[0]
        if change.dataset == "dimensional_attribute"
        for record in change.records
        if record["dimensional_entity_name"] == "Invoice Fact"
        and record["dimensional_attribute_name"] == "Customer Dimension key"
    )
    assert invoice_key["dimensional_attribute_is_surrogate_key"] is False
    assert handoff.final_events[-1].current == handoff.final_events[-1].total == 2


async def test_area_without_logical_entities_is_skipped_with_a_warning() -> None:
    bundle = _context_bundle()
    raw = bundle.context.model_dump(mode="json")
    # Returns has a table, but no Logical Entity is built from it yet.
    raw["applied"]["subject_area"] = _subject_areas(
        (_SALES, ("sales_customer",)), (_RETURNS, ("sales_return",))
    )
    bundle = replace(bundle, context=AgentAuthoringContext.model_validate(raw, strict=False))
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent, context=bundle, plan=_plan(subject_areas=(_RETURNS, _SALES))
    )

    result = await _execute(service)

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert len(agent.requests) == 1
    assert [event.message for event in lifecycle.events] == [
        "Building Sales (2 of 2): 1 Logical Entity."
    ]
    final_event = handoff.final_events[-1]
    assert final_event.status == "warning"
    assert final_event.message == (
        "Dimensional build completed with notes. Returns: skipped, no Logical Entities."
    )
    assert lifecycle.failed is None


async def test_failed_area_keeps_earlier_areas_and_its_answer_as_a_rejected_draft() -> None:
    bundle = _context_bundle()
    raw = bundle.context.model_dump(mode="json")
    raw["selected_logical_entities"].append(
        _selected_logical_entity("sales_invoice", table="sales_invoice", order=2)
    )
    raw["applied"]["subject_area"] = _subject_areas(
        (_SALES, ("sales_customer",)), (_BILLING, ("sales_invoice",))
    )
    bundle = replace(bundle, context=AgentAuthoringContext.model_validate(raw, strict=False))
    invoice = cast(dict[str, Any], _candidate(source_name="sales_invoice"))
    # An inactive Fact keeps an active Attribute, which the complete graph rejects.
    invoice["entities"] = [
        {
            **invoice["entities"][1],
            "dimensional_entity_name": "Invoice Fact",
            "dimensional_entity_is_active": False,
        }
    ]
    invoice["attributes"] = [
        {
            **invoice["attributes"][1],
            "dimensional_entity_name": "Invoice Fact",
            "sources": _source("sale_customer_id", object_name="sales_invoice"),
        }
    ]
    invoice["relationships"] = []
    agent = _AgentExecutor(responses=[_candidate(), cast(JsonValue, invoice), deepcopy(invoice)])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent, context=bundle, plan=_plan(subject_areas=(_SALES, _BILLING))
    )

    with pytest.raises(AgentCandidateValidationError):
        await _execute(service)

    assert len(agent.requests) == 3
    assert handoff.calls == []
    (retained,) = handoff.retained
    # The inactive Fact covers nothing, so the area's coverage issue is kept as well.
    assert {issue.code for issue in retained["issues"]} == {
        "active_dependency_invalid",
        "entity_coverage_incomplete",
    }
    entities = next(
        change for change in retained["changes"] if change.dataset == "dimensional_entity"
    )
    assert [record["dimensional_entity_name"] for record in entities.records] == [
        "Customer Dimension",
        "Sales Fact",
        "Invoice Fact",
    ]
    assert lifecycle.failed is None


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_optimize_is_one_whole_model_call_without_coverage(
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    bundle = _context_bundle(mode=mode, operation="optimize")
    no_op = _NoOp()
    # An empty answer means no change; Optimize never asks for more coverage.
    agent = _AgentExecutor(
        responses=[cast(JsonValue, {"entities": [], "attributes": [], "relationships": []})]
    )
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent, plan=_plan(mode=mode, operation="optimize"), context=bundle, no_op=no_op
    )

    result = await _execute(service)

    (request,) = agent.requests
    assert request.stage == "optimize_authoring"
    assert request.context == {"original_context": bundle.embedded_context, "repair": None}
    assert [event.message for event in lifecycle.events] == [
        "Optimizing the whole Dimensional model."
    ]
    assert isinstance(result, AuthoringNoOpReceipt)
    final_event = no_op.requests[0].final_event
    assert final_event.status == "running"
    assert final_event.message == "Dimensional optimize produced no effective change."
    assert handoff.calls == []
    assert lifecycle.failed is None


async def test_failure_is_safe_and_never_hands_off_partial_output() -> None:
    diagnostic = "token=secret; raw prompt and provider trace"
    agent = _AgentExecutor(responses=[RuntimeError(diagnostic)])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(DimensionalExecutionFailedError) as raised:
        await _execute(service)

    assert handoff.calls == []
    assert lifecycle.failed == (
        "dimensional_execution_failed",
        "Dimensional authoring failed before a validated draft was committed.",
    )
    assert diagnostic not in str(raised.value)
    assert diagnostic not in repr(raised.value)


async def test_wrong_claim_token_is_rejected_before_agent_or_handoff() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(DimensionalExecutionFailedError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            project_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=UUID("55555555-5555-5555-5555-555555555555"),
            expected_project_revision=7,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.events == []
    assert lifecycle.failed is None


async def test_valid_unchanged_candidate_completes_as_no_op() -> None:
    agent = _AgentExecutor(responses=[_no_op_candidate()])
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        context=_no_op_context_bundle(),
        no_op=no_op,
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed"
    assert handoff.calls == []
    assert len(no_op.requests) == 1
    final_event = no_op.requests[0].final_event
    assert final_event.message == "Dimensional build produced no effective change."
    assert final_event.status == "running"
    assert final_event.attempt == 1
    assert no_op.requests[0].candidate_digest == result.candidate_digest
    assert lifecycle.finding_count is None
    assert lifecycle.failed is None


async def test_empty_build_answer_over_a_covering_model_is_no_change() -> None:
    agent = _AgentExecutor(
        responses=[cast(JsonValue, {"entities": [], "attributes": [], "relationships": []})]
    )
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent, context=_no_op_context_bundle(), no_op=no_op
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert len(agent.requests) == 1 and handoff.calls == []
    assert no_op.requests[0].final_event.status == "running"
    assert lifecycle.failed is None


async def test_repaired_unchanged_candidate_preserves_attempt_in_no_op_receipt() -> None:
    agent = _AgentExecutor(responses=[cast(JsonValue, {"invalid": True}), _no_op_candidate()])
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        context=_no_op_context_bundle(),
        no_op=no_op,
    )

    result = await _execute(service)

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed_with_repair"
    assert no_op.requests[0].final_event.attempt == 2
    assert no_op.requests[0].final_event.status == "warning"
    assert handoff.calls == []
    assert lifecycle.failed is None


async def test_post_handoff_failure_does_not_mark_validated_draft_failed() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    lifecycle = _Lifecycle()
    finalizer = _Handoff(fail_finalize=True)
    service, _database, _authorizer, handoff, returned_lifecycle = _service(
        agent=agent,
        lifecycle=lifecycle,
        handoff=finalizer,
    )

    with pytest.raises(DimensionalFinalizationFailedError):
        await _execute(service)

    assert len(handoff.calls) == 1
    assert returned_lifecycle.failed is None


@pytest.mark.parametrize(
    "bad_plan",
    [
        _plan().model_copy(update={"project_workflow": "logical"}),
        _plan().model_copy(update={"modeled_entity_type": "dimensional_entity"}),
        # A Build plan must run the Build stage, and an Optimize plan the Optimize stage.
        _plan().model_copy(update={"workflow_operation": "optimize"}),
        _plan(operation="optimize").model_copy(update={"workflow_operation": "build"}),
    ],
)
async def test_fixed_plan_identity_mismatch_is_rejected_before_agent_execution(
    bad_plan: AgentRunPlan,
) -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent, plan=bad_plan)

    with pytest.raises(InvalidRequestError):
        await _execute(service)

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.failed is not None
