from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from copy import deepcopy
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
from gds_etl_workbench.domain.modeling_records import PhysicalObjectKey
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.snapshots.model.contracts import DimensionalSection
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.dimensional.policy import (
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
)
from gds_workbench_api.features.dimensional.detailed import (
    DetailedDimensionalTopologyContributionValidator,
)
from gds_workbench_api.features.dimensional.service import (
    DatabaseDimensionalExecutor,
    DimensionalExecutionFailedError,
    DimensionalFinalizationFailedError,
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


def _plan(
    *,
    mode: Literal["one_shot", "tool_assisted", "detailed_coverage"] = "one_shot",
    retry_count: int = 1,
) -> AgentRunPlan:
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
                resolver_key=f"workflow.dimensional.{mode}.{stage_code}.context",
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
                workflow_stage_id=140 + position,
                stage_code=stage_code,
                stage_order=position * 10,
                prompt_template_version_id=190 + position,
                prompt_template_digest=f"{position:x}" * 64,
                templates=PromptComponentTemplates(
                    system="Author one governed Dimensional stage candidate.",
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
            "model_workflow": "dimensional",
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
    attributes: list[dict[str, object]] = []
    for position, name in enumerate(("customer_id", "sale_customer_id"), start=1):
        attributes.append(
            {
                "tenant_code": "NWA",
                "system_code": "GDS",
                "connection_code": "PRIMARY",
                "object_schema": "silver_nwa",
                "object_name": "sales_customer",
                "attribute_name": name,
                "fc_attribute_name": None,
                "attribute_ordinal_position": position,
                "attribute_description": f"{name} source value.",
                "attribute_data_type": "bigint",
                "attribute_nullability": False,
                "attribute_custom_code": None,
                "is_surrogate_key": False,
                "is_natural_key": True,
                "is_meta_data": False,
                "is_masking_required": False,
                "is_mapped": True,
                "is_purge": False,
                "is_active": True,
            }
        )
    return {
        "selection_order": 1,
        "object": {
            "tenant_code": "NWA",
            "system_code": "GDS",
            "connection_code": "PRIMARY",
            "object_schema": "silver_nwa",
            "object_name": "sales_customer",
            "fc_object_schema": None,
            "fc_object_name": None,
            "object_transformation": None,
            "object_description": "Eligible Silver dimensional contribution.",
            "batch_attribute_name": None,
            "object_type_code": "table",
            "zone_code": "silver",
            "is_locked": False,
            "is_active": True,
        },
        "attributes": tuple(attributes),
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
    mode: Literal["one_shot", "tool_assisted", "detailed_coverage"] = "one_shot",
) -> AgentContextBundle:
    context = AgentAuthoringContext.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_name": "Sales Model",
            "model_revision": 7,
            "model_workflow": "dimensional",
            "workflow_execution_mode": mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "model_details": {
                "model_name": "Sales Model",
                "model_description": None,
                "silver_model_naming_instructions": None,
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": "Use business-facing Gold names.",
                "gold_model_technical_columns_template": _technical_template(),
                "gold_model_audit_columns_template": _audit_template(),
            },
            "selected_objects": (_selected_object(),),
            "profiles": (),
            "analysis_relationships": (),
            "assertion": {
                "documents": (
                    {
                        "modeling_assertion_document_name": "requirements.md",
                        "tenant_code": None,
                        "system_code": None,
                        "modeling_assertion_file_pattern": None,
                        "modeling_assertion_document_type": "requirements",
                        "modeling_assertion_document_description": None,
                        "modeling_assertion_document_metadata": {},
                        "is_active": True,
                    },
                ),
                "records": (
                    {
                        "modeling_assertion_record_key": "assertion.customer_segment",
                        "modeling_assertion_document_name": "requirements.md",
                        "modeling_assertion_record_type": "business_rule",
                        "modeling_assertion_text": "Customer segment is modeled in Gold.",
                        "modeling_assertion_details": {},
                        "modeling_assertion_source_location": None,
                        "modeling_assertion_applicable_layers": ("dimensional",),
                        "modeling_assertion_confidence": "high",
                        "modeling_assertion_record_status": "active",
                        "modeling_assertion_record_is_locked": False,
                    },
                ),
            },
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


def _object_key(*, object_name: str = "sales_customer") -> dict[str, object]:
    return {
        "tenant_code": "NWA",
        "system_code": "GDS",
        "connection_code": "PRIMARY",
        "object_schema": "silver_nwa",
        "object_name": object_name,
    }


def _source(attribute_name: str) -> list[dict[str, object]]:
    return [
        {
            "support_source_type": "attribute",
            "source_attribute": {
                **_object_key(),
                "attribute_name": attribute_name,
            },
            "source_order": 1,
            "rationale": "Eligible Silver contribution.",
            "status": "active",
            "is_locked": False,
        }
    ]


def _candidate(
    *,
    source_name: str = "sales_customer",
    relationship_optional: bool = True,
) -> JsonValue:
    source_object = _object_key(object_name=source_name)
    entity_source = [
        {
            "support_source_type": "object",
            "source_object": source_object,
            "source_order": 1,
            "rationale": "Eligible Silver contribution.",
            "status": "active",
            "is_locked": False,
            "source_role": "primary",
        }
    ]
    return cast(
        JsonValue,
        {
            "submodels": [
                {
                    "dimensional_submodel_name": "Sales Analytics",
                    "dimensional_submodel_definition": "Sales analysis.",
                    "dimensional_submodel_status": "active",
                    "dimensional_submodel_is_locked": False,
                }
            ],
            "entities": [
                {
                    "dimensional_entity_name": "Customer Dimension",
                    "dimensional_entity_definition": "One customer.",
                    "dimensional_entity_type": "dimension",
                    "dimensional_fact_type": None,
                    "dimensional_entity_grain_definition": None,
                    "dimensional_entity_dependency_order": 0,
                    "dimensional_entity_confidence": "high",
                    "dimensional_entity_status": "active",
                    "dimensional_entity_is_locked": False,
                    "submodels": [
                        {
                            "submodel_name": "Sales Analytics",
                            "membership_status": "active",
                            "membership_is_locked": False,
                        }
                    ],
                    "sources": entity_source,
                },
                {
                    "dimensional_entity_name": "Sales Fact",
                    "dimensional_entity_definition": "One sale.",
                    "dimensional_entity_type": "fact",
                    "dimensional_fact_type": "transaction",
                    "dimensional_entity_grain_definition": "One sale per customer.",
                    "dimensional_entity_dependency_order": 1,
                    "dimensional_entity_confidence": "high",
                    "dimensional_entity_status": "active",
                    "dimensional_entity_is_locked": False,
                    "submodels": [
                        {
                            "submodel_name": "Sales Analytics",
                            "membership_status": "active",
                            "membership_is_locked": False,
                        }
                    ],
                    "sources": entity_source,
                },
            ],
            "attributes": [
                {
                    "dimensional_entity_name": "Customer Dimension",
                    "dimensional_attribute_name": "Customer ID",
                    "dimensional_attribute_definition": "Customer identifier.",
                    "dimensional_attribute_data_type": "bigint",
                    "dimensional_attribute_is_nullable": False,
                    "dimensional_attribute_ordinal_position": 1,
                    "dimensional_attribute_role": "key",
                    "dimensional_attribute_key_role": "business",
                    "dimensional_attribute_is_grain_component": True,
                    "dimensional_attribute_additivity": None,
                    "dimensional_attribute_default_aggregation": None,
                    "dimensional_attribute_aggregation_basis": None,
                    "dimensional_attribute_change_behavior": "fixed",
                    "dimensional_attribute_is_audit_column": False,
                    "dimensional_attribute_confidence": "high",
                    "dimensional_attribute_status": "active",
                    "dimensional_attribute_is_locked": False,
                    "sources": _source("customer_id"),
                },
                {
                    "dimensional_entity_name": "Sales Fact",
                    "dimensional_attribute_name": "Source Customer ID",
                    "dimensional_attribute_definition": "Sale customer identifier.",
                    "dimensional_attribute_data_type": "bigint",
                    "dimensional_attribute_is_nullable": relationship_optional,
                    "dimensional_attribute_ordinal_position": 1,
                    "dimensional_attribute_role": "key",
                    "dimensional_attribute_key_role": "business",
                    "dimensional_attribute_is_grain_component": True,
                    "dimensional_attribute_additivity": None,
                    "dimensional_attribute_default_aggregation": None,
                    "dimensional_attribute_aggregation_basis": None,
                    "dimensional_attribute_change_behavior": None,
                    "dimensional_attribute_is_audit_column": False,
                    "dimensional_attribute_confidence": "high",
                    "dimensional_attribute_status": "active",
                    "dimensional_attribute_is_locked": False,
                    "sources": _source("sale_customer_id"),
                },
            ],
            "relationships": [
                {
                    "dimensional_relationship_name": "Sales to customer",
                    "dimensional_relationship_definition": "Each sale references a customer.",
                    "from_dimensional_entity_name": "Sales Fact",
                    "from_dimensional_attribute_name": "Source Customer ID",
                    "to_dimensional_entity_name": "Customer Dimension",
                    "to_dimensional_attribute_name": "Customer ID",
                    "dimensional_relationship_kind": "foreign_key",
                    "dimensional_relationship_cardinality": "many_to_one",
                    "dimensional_relationship_is_optional": relationship_optional,
                    "dimensional_relationship_role_name": "Bill To Customer",
                    "dimensional_relationship_confidence": "high",
                    "dimensional_relationship_basis": "Sales customer evidence.",
                    "dimensional_relationship_cardinality_basis": (
                        "Many sales reference one customer."
                    ),
                    "dimensional_relationship_status": "active",
                    "dimensional_relationship_is_locked": False,
                }
            ],
        },
    )


def _applied_dimensional_section() -> DimensionalSection:
    raw = cast(dict[str, list[dict[str, object]]], _candidate())
    changes = (
        StageModelChange(
            dataset="dimensional_submodel",
            records=raw["submodels"],
        ),
        StageModelChange(
            dataset="dimensional_entity",
            records=raw["entities"],
        ),
        StageModelChange(
            dataset="dimensional_attribute",
            records=raw["attributes"],
        ),
        StageModelChange(
            dataset="dimensional_relationship",
            records=raw["relationships"],
        ),
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
            "submodels": tuple(by_dataset["dimensional_submodel"]),
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
    context = bundle.context.model_copy(update={"applied": applied})
    return AgentContextBundle(
        context=context,
        embedded_context=cast(JsonValue, context.model_dump(mode="json")),
    )


def _no_op_candidate() -> JsonValue:
    candidate = cast(dict[str, JsonValue], deepcopy(_candidate()))
    relationship = cast(list[dict[str, JsonValue]], candidate["relationships"])[0]
    relationship["from_dimensional_attribute_name"] = "Bill To Customer key"
    relationship["to_dimensional_attribute_name"] = "Customer Dimension key"
    return cast(JsonValue, candidate)


def _detailed_model_candidate() -> dict[str, JsonValue]:
    full = cast(dict[str, JsonValue], deepcopy(_candidate()))
    submodel = cast(list[JsonValue], full["submodels"])[0]
    entity = cast(list[JsonValue], full["entities"])[0]
    attributes = cast(list[dict[str, JsonValue]], full["attributes"])
    customer_id = attributes[0]
    sale_customer_id = attributes[1]
    sale_customer_id.update(
        {
            "dimensional_entity_name": "Customer Dimension",
            "dimensional_attribute_name": "Sale Customer ID",
            "dimensional_attribute_definition": "Sale-side customer identifier.",
            "dimensional_attribute_is_nullable": False,
            "dimensional_attribute_ordinal_position": 2,
            "dimensional_attribute_change_behavior": "fixed",
        }
    )
    customer_segment = deepcopy(customer_id)
    customer_segment.update(
        {
            "dimensional_attribute_name": "Customer Segment",
            "dimensional_attribute_definition": "Governed customer segment.",
            "dimensional_attribute_is_nullable": True,
            "dimensional_attribute_ordinal_position": 3,
            "dimensional_attribute_role": "descriptor",
            "dimensional_attribute_key_role": "none",
            "dimensional_attribute_is_grain_component": False,
            "dimensional_attribute_change_behavior": "overwrite",
            "sources": [
                {
                    "support_source_type": "assertion",
                    "assertion_record": {
                        "modeling_assertion_record_key": "assertion.customer_segment"
                    },
                    "source_order": 1,
                    "rationale": "Governed customer-segmentation assertion.",
                    "status": "active",
                    "is_locked": False,
                }
            ],
        }
    )
    return {
        "submodels": [submodel],
        "entities": [entity],
        "attributes": [customer_id, sale_customer_id, customer_segment],
        "relationships": [],
    }


type _AgentResponse = (
    JsonValue | Exception | Callable[[AgentExecutionRequest], JsonValue]
)


def _detailed_reconciliation_receipt(request: AgentExecutionRequest) -> JsonValue:
    wrapped = cast(dict[str, JsonValue], request.context)
    context = cast(dict[str, JsonValue], wrapped["original_context"])
    signals = cast(list[dict[str, JsonValue]], context["relationship_signals"])
    return cast(
        JsonValue,
        {
            "partition_ref": context["partition_ref"],
            "manifest": context["review_manifest"],
            "reviewed_relationship_signal_refs": [
                item["signal_ref"] for item in signals
            ],
            "relationships": [],
        },
    )


def _detailed_candidates(*, blocking_first: bool = False) -> list[_AgentResponse]:
    full = _detailed_model_candidate()
    submodel = cast(list[JsonValue], full["submodels"])[0]
    entity = cast(list[JsonValue], full["entities"])[0]
    attributes = cast(list[JsonValue], full["attributes"])
    contribution = cast(
        JsonValue,
        {
            "contribution_ref": "object_00001",
            "source_object": _object_key(),
            "disposition": "represented",
            "rationale": "Represents the customer dimension.",
            "proposals": [
                {
                    "local_entity_ref": "customer_dimension",
                    "candidate_entity_name": "Customer Dimension",
                    "candidate_entity_type": "dimension",
                    "candidate_fact_type": None,
                    "candidate_entity_grain_definition": None,
                    "candidate_submodel_names": ["Sales Analytics"],
                    "source_attributes": [
                        {**_object_key(), "attribute_name": "customer_id"},
                        {**_object_key(), "attribute_name": "sale_customer_id"},
                    ],
                }
            ],
        },
    )
    topology = cast(
        JsonValue,
        {
            "submodels": [
                {
                    "canonical_submodel_ref": "sales_analytics",
                    "submodel": submodel,
                }
            ],
            "entities": [
                {
                    "canonical_entity_ref": "customer_dimension",
                    "dimensional_entity_name": "Customer Dimension",
                    "contribution_refs": ["object_00001.customer_dimension"],
                    "submodel_refs": ["sales_analytics"],
                }
            ],
            "discarded_contribution_refs": [],
        },
    )
    detail = cast(
        JsonValue,
        {
            "canonical_entity_ref": "entity_00001",
            "entity": entity,
            "attributes": attributes,
        },
    )
    record_refs = [
        "submodel:sales analytics",
        "entity:customer dimension",
        'attribute:["customer dimension","customer id"]',
        'attribute:["customer dimension","customer dimension key"]',
        'attribute:["customer dimension","customer segment"]',
        'attribute:["customer dimension","loaded at"]',
        'attribute:["customer dimension","sale customer id"]',
    ]
    clean_worker = cast(
        JsonValue,
        {
            "package_ref": "validation_00001",
            "reviewed_record_refs": record_refs,
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
    base: list[_AgentResponse] = [
        contribution,
        topology,
        detail,
        _detailed_reconciliation_receipt,
    ]
    if not blocking_first:
        return [*base, clean_worker, clean_lead]
    finding = {
        "finding_ref": "validation_00001.finding_00001",
        "severity": "error",
        "code": "dimensional.review_required",
        "message": "Repair one blocking dimensional concern.",
        "record_refs": ["entity:customer dimension"],
    }
    blocking_worker = cast(
        JsonValue,
        {
            "package_ref": "validation_00001",
            "reviewed_record_refs": record_refs,
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
        _detailed_reconciliation_receipt,
        clean_worker,
        clean_lead,
    ]


def _non_dimensional_candidates(
    *,
    disposition: Literal["not_dimensional", "needs_review"],
) -> list[JsonValue]:
    return [
        cast(
            JsonValue,
            {
                "contribution_ref": "object_00001",
                "source_object": _object_key(),
                "disposition": disposition,
                "rationale": "No Gold structure is proposed for this Silver Object.",
                "proposals": [],
            },
        ),
        cast(
            JsonValue,
            {
                "submodels": [],
                "entities": [],
                "discarded_contribution_refs": [],
            },
        ),
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
class _Handoff:
    calls: list[tuple[StageModelChange, ...]] = field(
        default_factory=lambda: list[tuple[StageModelChange, ...]]()
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
        changes: tuple[StageModelChange, ...],
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
            model_id=18,
            workflow_run_id=1048,
            model_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
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
    events: list[AgentWorkflowEvent] = field(
        default_factory=lambda: list[AgentWorkflowEvent]()
    )
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


def _service(
    *,
    agent: _AgentExecutor,
    plan: AgentRunPlan | None = None,
    context: AgentContextBundle | None = None,
    lifecycle: _Lifecycle | None = None,
    handoff: _Handoff | None = None,
    no_op: _NoOp | None = None,
) -> tuple[DatabaseDimensionalExecutor, _Database, _Authorizer, _Handoff, _Lifecycle]:
    selected_plan = plan or _plan()
    database = _Database()
    authorizer = _Authorizer()
    selected_handoff = handoff or _Handoff()
    selected_no_op = no_op or _NoOp()
    selected_lifecycle = lifecycle or _Lifecycle()
    return (
        DatabaseDimensionalExecutor(
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


@pytest.mark.asyncio
async def test_missing_gold_policy_blocks_before_agent_execution() -> None:
    context = _context_bundle()
    model_details = context.context.model_details.model_copy(
        update={"gold_model_audit_columns_template": None}
    )
    authoring_context = context.context.model_copy(
        update={"model_details": model_details}
    )
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        context=AgentContextBundle(
            context=authoring_context,
            embedded_context=context.embedded_context,
            tool_catalog=context.tool_catalog,
        ),
    )

    with pytest.raises(InvalidRequestError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            expected_model_revision=7,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.failed is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("relationship_optional", [False, True])
async def test_one_shot_projects_gold_policy_then_foreign_key_once(
    relationship_optional: bool,
) -> None:
    agent = _AgentExecutor(
        responses=[_candidate(relationship_optional=relationship_optional)]
    )
    service, database, authorizer, handoff, lifecycle = _service(agent=agent)

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 10
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
    assert authorizer.calls == [(7, ToolPolicy.TENANT_MODEL_WRITE)]
    request = agent.requests[0]
    assert request.workflow == "dimensional"
    assert request.stage == "candidate_authoring"
    assert request.execution_mode == "one_shot"
    assert request.allowed_tool_names == ()
    assert "Use business-facing Gold names." in request.instruction_prompt
    assert request.context == {
        "original_context": _context_bundle().embedded_context,
        "repair": None,
    }
    assert handoff.workflows == ["dimensional"]
    assert len(handoff.calls) == 1
    attribute_change = next(
        change
        for change in handoff.calls[0]
        if change.dataset == "dimensional_attribute"
    )
    foreign_key = next(
        record
        for record in attribute_change.records
        if record["dimensional_attribute_key_role"] == "foreign"
    )
    assert foreign_key["dimensional_attribute_name"] == "Bill To Customer key"
    assert foreign_key["dimensional_attribute_is_nullable"] is relationship_optional
    relationship_change = next(
        change
        for change in handoff.calls[0]
        if change.dataset == "dimensional_relationship"
    )
    assert relationship_change.records[0]["from_dimensional_attribute_name"] == (
        "Bill To Customer key"
    )
    assert relationship_change.records[0]["to_dimensional_attribute_name"] == (
        "Customer Dimension key"
    )
    assert handoff.final_events[-1].finding_count == 10
    assert lifecycle.failed is None


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
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    request = agent.requests[0]
    catalog = request.local_tool_catalog
    assert isinstance(catalog, InMemoryAgentContextToolCatalog)
    assert request.allowed_tool_names == catalog.allowed_tool_names
    assert request.context == {"original_context": catalog.manifest, "repair": None}
    assert [change.dataset for change in handoff.calls[0]] == [
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
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
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
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

    with pytest.raises(DimensionalExecutionFailedError) as raised:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            expected_model_revision=7,
        )

    assert handoff.calls == []
    assert lifecycle.failed == (
        "dimensional_execution_failed",
        "Dimensional authoring failed before a validated draft was committed.",
    )
    assert diagnostic not in str(raised.value)
    assert diagnostic not in repr(raised.value)


@pytest.mark.asyncio
async def test_wrong_claim_token_is_rejected_before_agent_or_handoff() -> None:
    agent = _AgentExecutor(responses=[_candidate()])
    service, _database, _authorizer, handoff, lifecycle = _service(agent=agent)

    with pytest.raises(DimensionalExecutionFailedError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=UUID("55555555-5555-5555-5555-555555555555"),
            expected_model_revision=7,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.events == []
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_valid_unchanged_candidate_completes_as_no_op() -> None:
    agent = _AgentExecutor(responses=[_no_op_candidate()])
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        context=_no_op_context_bundle(),
        no_op=no_op,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed"
    assert handoff.calls == []
    assert len(no_op.requests) == 1
    assert no_op.requests[0].final_event.message == (
        "Dimensional authoring completed with no effective change."
    )
    assert no_op.requests[0].final_event.attempt == 1
    assert no_op.requests[0].candidate_digest == result.candidate_digest
    assert lifecycle.finding_count is None
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_repaired_unchanged_candidate_preserves_attempt_in_no_op_receipt() -> (
    None
):
    agent = _AgentExecutor(
        responses=[cast(JsonValue, {"invalid": True}), _no_op_candidate()]
    )
    no_op = _NoOp()
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        context=_no_op_context_bundle(),
        no_op=no_op,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed_with_repair"
    assert no_op.requests[0].final_event.attempt == 2
    assert no_op.requests[0].final_event.status == "warning"
    assert handoff.calls == []
    assert lifecycle.failed is None


@pytest.mark.asyncio
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
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            expected_model_revision=7,
        )

    assert len(handoff.calls) == 1
    assert returned_lifecycle.failed is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_plan",
    [
        _plan().model_copy(update={"model_workflow": "logical"}),
        _plan().model_copy(update={"modeled_entity_type": "dimensional_entity"}),
    ],
)
async def test_fixed_plan_identity_mismatch_is_rejected_before_agent_execution(
    bad_plan: AgentRunPlan,
) -> None:
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
            workflow_run_claim_token=_CLAIM_TOKEN,
            expected_model_revision=7,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.failed is not None


@pytest.mark.asyncio
async def test_detailed_coverage_runs_fixed_stages_then_one_atomic_handoff() -> None:
    agent = _AgentExecutor(responses=_detailed_candidates())
    service, _database, _authorizer, handoff, lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage"),
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

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
    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 7
    worker_request = next(
        request for request in agent.requests if request.stage == "validator_worker"
    )
    worker_context = cast(dict[str, JsonValue], worker_request.context)
    original_context = cast(dict[str, JsonValue], worker_context["original_context"])
    package = cast(dict[str, JsonValue], original_context["validation_package"])
    records = cast(list[dict[str, JsonValue]], package["records"])
    projected_names: set[str] = set()
    for record in records:
        if record["dataset"] != "dimensional_attribute":
            continue
        name = cast(dict[str, JsonValue], record["record"])[
            "dimensional_attribute_name"
        ]
        if isinstance(name, str):
            projected_names.add(name)
    assert {"Customer Dimension key", "Loaded At"} <= projected_names
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_detailed_blocker_retries_only_reconciliation_worker_and_lead() -> None:
    agent = _AgentExecutor(responses=_detailed_candidates(blocking_first=True))
    service, _database, _authorizer, handoff, _lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage", retry_count=1),
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
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
    first_original = cast(dict[str, JsonValue], first["original_context"])
    repaired_original = cast(dict[str, JsonValue], repaired["original_context"])
    assert repaired_original["review_manifest"] == first_original["review_manifest"]
    assert (
        cast(dict[str, JsonValue], repaired_original["validation_failure_summary"])[
            "finding_count"
        ]
        == 1
    )
    assert "dimensional.review_required" in agent.requests[6].instruction_prompt
    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].status == "warning"


@pytest.mark.asyncio
async def test_detailed_internal_repair_marks_terminal_attempt() -> None:
    responses = _detailed_candidates()
    agent = _AgentExecutor(responses=[cast(JsonValue, {"invalid": True}), *responses])
    service, _database, _authorizer, handoff, _lifecycle = _service(
        agent=agent,
        plan=_plan(mode="detailed_coverage", retry_count=1),
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert len(handoff.calls) == 1
    assert handoff.final_events[-1].attempt == 2
    assert handoff.final_events[-1].status == "warning"


def test_maximum_legal_dimensional_attributes_are_exactly_byte_batched() -> None:
    base = _context_bundle(mode="detailed_coverage")
    selected = base.context.selected_objects[0]
    template = selected.attributes[0]
    excluded_description = "界" * 2_000
    attributes = tuple(
        template.model_copy(
            update={
                "attribute_name": f"attribute_{position:05d}",
                "attribute_ordinal_position": position,
                "attribute_description": excluded_description,
            }
        )
        for position in range(1, 20_001)
    )
    wide_selected = selected.model_copy(update={"attributes": attributes})
    authoring_context = base.context.model_copy(
        update={"selected_objects": (wide_selected,)}
    )
    context = AgentContextBundle(
        context=authoring_context,
        embedded_context=base.embedded_context,
    )
    plan = _plan(mode="detailed_coverage")
    service, *_unused = _service(
        agent=_AgentExecutor(responses=[]),
        plan=plan,
        context=context,
    )

    batches = service._topology_builder_batches(  # pyright: ignore[reportPrivateUsage]
        plan=plan,
        context=context,
        selected=wide_selected,
    )

    covered = tuple(
        key.attribute_name for batch in batches for key in batch.source_attributes
    )
    assert covered == tuple(item.attribute_name for item in attributes)
    assert len(batches) > 1
    assert all(1 <= len(batch.source_attributes) <= 32 for batch in batches)
    assert all(
        excluded_description not in json.dumps(batch.context, ensure_ascii=False)
        for batch in batches
    )
    source_object = PhysicalObjectKey.model_validate(_object_key())
    assert all(
        service._detailed_stage_fits(  # pyright: ignore[reportPrivateUsage]
            plan=plan,
            context=context,
            stage_code="topology_builder",
            stage_context=batch.context,
            output_schema=DetailedDimensionalTopologyContributionValidator(
                contribution_ref=batch.contribution_ref,
                source_object=source_object,
                source_attributes=batch.source_attributes,
                max_result_bytes=service._detailed_result_limit,  # pyright: ignore[reportPrivateUsage]
            ).output_schema(),
        )
        for batch in batches
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "expected_status"),
    [("not_dimensional", "running"), ("needs_review", "warning")],
)
async def test_detailed_empty_topology_completes_as_no_op(
    disposition: Literal["not_dimensional", "needs_review"],
    expected_status: Literal["running", "warning"],
) -> None:
    agent = _AgentExecutor(
        responses=cast(
            list[_AgentResponse],
            _non_dimensional_candidates(disposition=disposition),
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
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert isinstance(result, AuthoringNoOpReceipt)
    assert result.workflow_run_state == "completed"
    assert [request.stage for request in agent.requests] == [
        "topology_builder",
        "topology_reconciler",
    ]
    assert handoff.calls == []
    assert no_op.requests[0].final_event.status == expected_status
    assert lifecycle.finding_count is None
