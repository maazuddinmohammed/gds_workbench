from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
)
from gds_etl_workbench.domain.modeling_records import PhysicalObjectKey
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.mapping import (
    MappingPreparation,
    MappingRunContext,
    MappingRunPlan,
    assess_mapping_readiness,
)
from gds_workbench_api.features.mapping.preparation_contracts import ModeledEntityType
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
    WorkflowExecutionMode,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates
from pydantic import JsonValue

from tests.mcp.model_test_fixtures import (
    attribute_binding,
    dimensional_attribute,
    dimensional_entity,
    logical_attribute,
    logical_entity,
    model_details,
    object_binding,
    snapshot_from_graph,
)


def mapping_preparation(
    *,
    execution_mode: WorkflowExecutionMode = "one_shot",
    existing: bool = False,
    locked: bool = False,
    attribute_count: int = 1,
    modeled_entity_type: ModeledEntityType = "logical_entity",
) -> MappingPreparation:
    operation = "extend" if existing else "build"
    dimensional = modeled_entity_type == "dimensional_entity"
    route = "dimensional_to_gold" if dimensional else "logical_to_silver"
    plan = MappingRunPlan.model_validate(
        {
            "agent_plan": AgentRunPlan(
                workflow_run_id=1048,
                model_id=18,
                correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
                model_revision=7,
                model_workflow="mapping",
                workflow_execution_mode=execution_mode,
                modeled_entity_type=modeled_entity_type,
                selected_scope_digest="a" * 64,
                selected_object_ids=(501,),
                selection=AgentRunSelection(
                    sdk_code="openai_agents_sdk",
                    provider_code="microsoft_foundry",
                    model_code="foundry-primary",
                    reasoning_effort_code="medium",
                    max_turns=8,
                    validation_retry_count=1,
                ),
                stages=tuple(
                    FrozenAgentStage(
                        workflow_stage_id=31 + index,
                        stage_code=stage_code,
                        stage_order=10 * (index + 1),
                        prompt_template_version_id=81,
                        prompt_template_digest="b" * 64,
                        templates=PromptComponentTemplates(
                            system="Mapping system prompt.",
                            instruction="Mapping instruction prompt.",
                        ),
                        variables=(),
                    )
                    for index, stage_code in enumerate(("mapping_authoring",))
                ),
            ),
            "actor_principal_id": 77,
            "pair": {"target_object_id": 501, "source_system_id": 31},
            "operation": operation,
            "coverage_mode": "selected_targets",
            "route": route,
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
            "modeled_entity_type": modeled_entity_type,
            "route": route,
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
                schema="gold_crm" if dimensional else "silver_crm",
                name="Customer",
                zone="gold" if dimensional else "silver",
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
                        schema="silver_crm" if dimensional else "bronze_crm",
                        name="customer",
                        zone="silver" if dimensional else "bronze",
                        attribute_id=801,
                        attribute_name="customer_id",
                        global_store=dimensional,
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
    if attribute_count != 1:
        header = context.headers[0]
        modeled = header.modeled_entity.attributes[0]
        target = context.target.attributes[0]
        child = header.attribute_mappings[0]
        names = tuple(f"CustomerID{index}" for index in range(1, attribute_count + 1))
        context = context.model_copy(
            update={
                "target": context.target.model_copy(
                    update={
                        "attributes": tuple(
                            target.model_copy(
                                update={
                                    "attribute_id": 901 + index,
                                    "attribute_name": name,
                                    "attribute_ordinal_position": index + 1,
                                }
                            )
                            for index, name in enumerate(names)
                        )
                    }
                ),
                "headers": (
                    header.model_copy(
                        update={
                            "modeled_entity": header.modeled_entity.model_copy(
                                update={
                                    "attributes": tuple(
                                        modeled.model_copy(
                                            update={
                                                "attribute_id": 701 + index,
                                                "attribute_name": name,
                                                "ordinal_position": index + 1,
                                            }
                                        )
                                        for index, name in enumerate(names)
                                    )
                                }
                            ),
                            "attribute_mappings": tuple(
                                child.model_copy(
                                    update={
                                        "modeled_attribute_id": 701 + index,
                                        "target_attribute_id": 901 + index,
                                        "mapping_attribute_id": 601 + index
                                        if existing
                                        else None,
                                    }
                                )
                                for index in range(attribute_count)
                            ),
                        }
                    ),
                ),
            }
        )
    return mapping_validation_preparation(plan, context)


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
        "source_tenant_id": 7,
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
                "attribute_inferred_data_type": None,
                "attribute_nullability": False,
                "attribute_ordinal_position": 1,
                "attribute_description": None,
                "is_active": True,
            }
        ],
    }


def mapping_validation_preparation(
    plan: MappingRunPlan, context: MappingRunContext
) -> MappingPreparation:
    """Canonical frozen graph for the synthetic Mapping fixture, including bindings and history."""
    header = context.headers[0]
    entity = header.modeled_entity
    dimensional = plan.modeled_entity_type == "dimensional_entity"
    layer = "dimensional" if dimensional else "logical"
    source = context.sources[0].object
    source_key = PhysicalObjectKey.model_validate(
        source.model_dump(), extra="ignore"
    ).model_dump()
    target_key = PhysicalObjectKey.model_validate(
        context.target.model_dump(), extra="ignore"
    ).model_dump()
    target_tuple = tuple(target_key.values())
    source_attribute: dict[str, object] = {
        **source_key,
        "attribute_name": source.attributes[0].attribute_name,
    }
    entity_record = (
        dimensional_entity(entity.entity_name, "dimension")
        if dimensional
        else logical_entity(entity.entity_name, "core", source_key)
    )
    entity_record["submodels"] = []
    support: dict[str, Any] = {
        "support_source_type": "object",
        "source_object": source_key,
        "source_order": 1,
        "rationale": "Synthetic source.",
        "status": "active",
        "is_locked": False,
    }
    if dimensional:
        support["source_role"] = "support"
    entity_record["sources"] = [support]
    attributes: list[dict[str, object]] = []
    for index, attribute in enumerate(entity.attributes, start=1):
        record = (
            dimensional_attribute(
                entity.entity_name, attribute.attribute_name, key_role="business"
            )
            if dimensional
            else logical_attribute(
                entity.entity_name,
                attribute.attribute_name,
                index,
                source_attribute,
                primary=index == 1,
            )
        )
        record[layer + "_attribute_ordinal_position"] = index
        record["sources"] = [
            {
                "support_source_type": "attribute",
                "source_attribute": source_attribute,
                "source_order": 1,
                "rationale": "Synthetic source.",
                "status": "active",
                "is_locked": False,
            }
        ]
        attributes.append(record)
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        "model_details": [model_details(context.authoring.model_name)],
        "model_input_scope": []
        if dimensional
        else [{**source_key, "is_active": True, "model_input_scope_is_locked": False}],
        cast(ModelChangeSetDataset, layer + "_entity"): [entity_record],
        cast(ModelChangeSetDataset, layer + "_attribute"): attributes,
        "model_object_binding": [
            object_binding(
                plan.modeled_entity_type, entity.entity_name, cast(Any, target_tuple)
            )
        ],
        "model_attribute_binding": [
            attribute_binding(
                plan.modeled_entity_type,
                entity.entity_name,
                attribute.attribute_name,
                target.attribute_name,
            )
            for attribute, target in zip(
                entity.attributes, context.target.attributes, strict=True
            )
        ],
        "mapping_dependency": [
            {
                "modeled_entity_type": plan.modeled_entity_type,
                "source_system_code": context.source_system.system_code,
                "source_system_dependency_order": context.dependency.dependency_order,
                "mapping_source_system_dependency_status": context.dependency.status,
                "mapping_source_system_dependency_is_locked": context.dependency.is_locked,
            }
        ],
    }
    identity = {
        "modeled_entity_type": plan.modeled_entity_type,
        "modeled_entity_name": entity.entity_name,
        "source_system_code": context.source_system.system_code,
        "output_template_code": None,
    }
    if header.is_authored:
        graph["mapping_object"] = [
            {
                **identity,
                "object_dependency_order": header.object_dependency_order,
                "mapping_transformation_document": header.transformation_document,
                "object_mapping_status": header.status,
                "object_mapping_is_locked": header.is_locked,
            }
        ]
        graph["mapping_attribute"] = [
            {
                **identity,
                "modeled_attribute_name": attribute.attribute_name,
                "attribute_mapping_transformation_document": child.transformation_document,
                "attribute_mapping_status": child.status,
                "attribute_mapping_is_locked": child.is_locked,
            }
            for attribute, child in zip(
                entity.attributes, header.attribute_mappings, strict=True
            )
        ]
    snapshot = snapshot_from_graph(graph).model_copy(
        update={"model_id": plan.model_id, "model_revision": plan.model_revision}
    )
    source_objects = frozenset(
        {tuple(value.casefold() for value in source_key.values())}
    )
    target_objects = frozenset(
        {tuple(value.casefold() for value in target_key.values())}
    )
    source_attributes = frozenset(
        (*key, attribute.attribute_name.casefold())
        for key in source_objects
        for attribute in source.attributes
    )
    target_attributes = frozenset(
        (*key, attribute.attribute_name.casefold())
        for key in target_objects
        for attribute in context.target.attributes
    )
    scope = PhysicalModelCatalog(
        model_tenant_code="NWA",
        active_system_codes=frozenset({"crm", "gds"}),
        objects=cast(Any, source_objects | target_objects),
        attributes=cast(Any, source_attributes | target_attributes),
        model_input_objects=cast(Any, frozenset() if dimensional else source_objects),
        model_input_attributes=cast(
            Any, frozenset() if dimensional else source_attributes
        ),
        dimensional_source_objects=cast(
            Any, source_objects if dimensional else frozenset()
        ),
        dimensional_source_attributes=cast(
            Any, source_attributes if dimensional else frozenset()
        ),
        logical_mapping_target_objects=cast(
            Any, frozenset() if dimensional else target_objects
        ),
        logical_mapping_target_attributes=cast(
            Any, frozenset() if dimensional else target_attributes
        ),
        dimensional_mapping_target_objects=cast(
            Any, target_objects if dimensional else frozenset()
        ),
        dimensional_mapping_target_attributes=cast(
            Any, target_attributes if dimensional else frozenset()
        ),
    )
    return MappingPreparation(
        plan=plan,
        context=context,
        readiness=assess_mapping_readiness(plan=plan, context=context),
        snapshot=snapshot,
        physical_scope=scope,
    )
