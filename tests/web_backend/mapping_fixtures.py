from __future__ import annotations

from uuid import UUID

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.mapping import (
    MappingPreparation,
    MappingRunContext,
    MappingRunPlan,
    assess_mapping_readiness,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
    WorkflowExecutionMode,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates
from pydantic import JsonValue


def mapping_preparation(
    *,
    execution_mode: WorkflowExecutionMode = "one_shot",
    existing: bool = False,
    locked: bool = False,
) -> MappingPreparation:
    operation = "extend" if existing else "build"
    plan = MappingRunPlan.model_validate(
        {
            "agent_plan": AgentRunPlan(
                workflow_run_id=1048,
                model_id=18,
                correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
                model_revision=7,
                model_workflow="mapping",
                workflow_execution_mode=execution_mode,
                modeled_entity_type="logical_entity",
                selected_scope_digest="a" * 64,
                selected_object_ids=(501,),
                selection=AgentRunSelection(
                    sdk_code="langchain_create_agent",
                    provider_code="databricks",
                    model_code="databricks-primary",
                    reasoning_effort_code="medium",
                    max_turns=8,
                    validation_retry_count=1,
                ),
                stages=(
                    FrozenAgentStage(
                        workflow_stage_id=31,
                        stage_code="mapping_authoring",
                        stage_order=10,
                        prompt_template_version_id=81,
                        prompt_template_digest="b" * 64,
                        templates=PromptComponentTemplates(
                            system="Mapping system prompt.",
                            instruction="Mapping instruction prompt.",
                        ),
                        variables=(),
                    ),
                ),
            ),
            "actor_principal_id": 77,
            "pair": {"target_object_id": 501, "source_system_id": 31},
            "operation": operation,
            "coverage_mode": "selected_targets",
            "route": "logical_to_silver",
            "output_template_selections": {
                "mapping_object": None,
                "mapping_attribute": None,
            },
        },
        strict=False,
    )
    context = MappingRunContext.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_revision": 7,
            "correlation_id": "33333333-3333-3333-3333-333333333333",
            "pair": {"target_object_id": 501, "source_system_id": 31},
            "modeled_entity_type": "logical_entity",
            "route": "logical_to_silver",
            "output_template_selections": {
                "mapping_object": None,
                "mapping_attribute": None,
            },
            "source_system": {
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "CRM",
                "system_description": None,
                "is_active": True,
            },
            "dependency": {
                "mapping_source_system_dependency_id": 71,
                "dependency_order": 0,
                "status": "active",
                "is_locked": True,
            },
            "dependency_graph": {
                "nodes": [
                    {
                        "mapping_source_system_dependency_id": 71,
                        "source_system_id": 31,
                        "dependency_order": 0,
                        "status": "active",
                        "is_locked": True,
                    }
                ],
                "edges": [],
                "malformed_reference_count": 0,
            },
            "target_dependency_graph": {
                "nodes": [
                    {
                        "target_object_id": 501,
                        "dependency_order": 0,
                        "status": "active",
                        "has_locked_headers": locked,
                        "has_unlocked_headers": not locked,
                    }
                ],
                "edges": [],
                "malformed_reference_count": 0,
                "mixed_order_target_count": 0,
            },
            "output_templates": {"ids": [], "definitions": []},
            "target": physical_object(
                object_id=501,
                system_id=41,
                system_code="GDS",
                connection_id=61,
                connection_code="lakehouse",
                schema="silver_crm",
                name="Customer",
                zone="silver",
                attribute_id=901,
                attribute_name="CustomerID",
                global_store=True,
            ),
            "sources": [
                {
                    "source_mapping_id": 301,
                    "modeled_entity_id": 201,
                    "role": "support",
                    "rationale": "Authoritative CRM feed.",
                    "mapping_order": 1,
                    "is_locked": False,
                    "object": physical_object(
                        object_id=401,
                        system_id=31,
                        system_code="CRM",
                        connection_id=51,
                        connection_code="crm_bronze",
                        schema="bronze_crm",
                        name="customer",
                        zone="bronze",
                        attribute_id=801,
                        attribute_name="customer_id",
                        global_store=False,
                    ),
                }
            ],
            "headers": [
                {
                    "model_object_binding_id": 111,
                    "mapping_object_id": 101 if existing else None,
                    "modeled_entity": {
                        "entity_id": 201,
                        "entity_name": "Customer",
                        "entity_definition": "A customer.",
                        "entity_kind": "core",
                        "grain": "One row per customer.",
                        "dependency_order": 0,
                        "status": "active",
                        "is_locked": False,
                        "attributes": [
                            {
                                "attribute_id": 701,
                                "attribute_name": "CustomerID",
                                "attribute_definition": "Stable customer key.",
                                "attribute_data_type": "BIGINT",
                                "is_nullable": False,
                                "ordinal_position": 1,
                                "is_audit_column": False,
                                "status": "active",
                                "is_locked": False,
                            }
                        ],
                    },
                    "object_dependency_order": 0,
                    "transformation_document": (
                        {"kind": "direct", "logic": "existing"} if existing else None
                    ),
                    "status": "active",
                    "is_locked": locked,
                    "agent_run_id": None,
                    "workflow_run_id": None,
                    "output_template_id": None,
                    "attribute_mappings": [
                        {
                            "mapping_attribute_id": 601 if existing else None,
                            "modeled_attribute_id": 701,
                            "target_attribute_id": 901,
                            "transformation_document": (
                                {"kind": "direct", "logic": "existing"}
                                if existing
                                else None
                            ),
                            "status": "active",
                            "is_locked": locked,
                            "agent_run_id": None,
                            "workflow_run_id": None,
                            "output_template_id": None,
                        }
                    ],
                }
            ],
            "authoring": {
                "model_name": "Customer Model",
                "naming_instructions": "Use PascalCase names.",
                "audit_columns_template": None,
                "technical_columns_template": None,
            },
        },
        strict=False,
    )
    return MappingPreparation(
        plan=plan,
        context=context,
        readiness=assess_mapping_readiness(plan=plan, context=context),
    )


def mapping_candidate() -> dict[str, JsonValue]:
    return {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {
                "kind": "direct",
                "logic": "Select the CRM customer source.",
            },
        },
        "attribute_mappings": [
            {
                "modeled_attribute_name": "CustomerID",
                "attribute_mapping_transformation_document": {
                    "kind": "direct",
                    "logic": "Map customer_id.",
                },
            }
        ],
    }


def physical_object(
    *,
    object_id: int,
    system_id: int,
    system_code: str,
    connection_id: int,
    connection_code: str,
    schema: str,
    name: str,
    zone: str,
    attribute_id: int,
    attribute_name: str,
    global_store: bool,
) -> dict[str, object]:
    return {
        "object_id": object_id,
        "tenant_id": 7,
        "tenant_code": "NWA",
        "tenant_catalog": "northwind",
        "tenant_is_active": True,
        "system_id": system_id,
        "system_code": system_code,
        "system_is_active": True,
        "connection_id": connection_id,
        "connection_code": connection_code,
        "connection_is_active": True,
        "is_global_data_store": global_store,
        "object_schema": schema,
        "object_name": name,
        "object_description": None,
        "batch_attribute_name": None,
        "zone_code": zone,
        "scope_is_locked": False,
        "scope_is_active": True,
        "is_locked": False,
        "is_active": True,
        "attributes": [
            {
                "attribute_id": attribute_id,
                "attribute_name": attribute_name,
                "attribute_data_type": "BIGINT",
                "attribute_nullability": False,
                "attribute_ordinal_position": 1,
                "attribute_description": None,
                "is_active": True,
            }
        ],
    }
