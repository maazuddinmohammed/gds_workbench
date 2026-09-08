from __future__ import annotations

import json
from typing import Any, Literal, LiteralString, cast
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    MappingDependencyRecord,
    MappingObjectRecord,
    ModelAttributeBindingRecord,
    ModelObjectBindingRecord,
    ObjectSupportRecord,
)
from gds_etl_workbench.domain.snapshots.model import ModelSnapshot
from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextLimits,
    AgentContextToolRequestError,
    InMemoryAgentContextToolCatalog,
    PostgresAgentContextRepository,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates


def _plan(
    *,
    execution_mode: Literal["one_shot", "tool_assisted"] = "one_shot",
    model_workflow: Literal["conceptual", "logical", "dimensional"] = "conceptual",
    selected_object_ids: tuple[int, ...] = (501,),
    max_turns: int = 8,
) -> AgentRunPlan:
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "model_revision": 7,
            "model_workflow": model_workflow,
            "workflow_execution_mode": execution_mode,
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": selected_object_ids,
            "selection": AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                reasoning_effort_code="medium",
                max_turns=max_turns,
                validation_retry_count=2,
            ),
            "stages": (
                FrozenAgentStage(
                    workflow_stage_id=31,
                    stage_code="candidate_authoring",
                    stage_order=10,
                    prompt_template_version_id=81,
                    prompt_template_digest="b" * 64,
                    templates=PromptComponentTemplates(
                        system="private system prompt",
                        instruction="private instruction prompt",
                        tool_instruction=None,
                    ),
                    variables=(),
                ),
            ),
        },
        strict=False,
    )


def _object_key(name: str, *, tenant_code: str = "SOURCE") -> dict[str, object]:
    return {
        "tenant_code": tenant_code,
        "system_code": "ERP",
        "connection_code": "GDS",
        "object_schema": "bronze_sales",
        "object_name": name,
    }


def _profile(name: str, *, tenant_code: str = "SOURCE") -> dict[str, object]:
    return {
        **_object_key(name, tenant_code=tenant_code),
        "attribute_name": "customer_id",
        "row_count": 10,
        "non_null_count": 10,
        "null_count": 0,
        "blank_count": 0,
        "distinct_count": 10,
        "min_data_length": 1,
        "max_data_length": 5,
        "avg_data_length": "3.000000",
        "percent_populated": "100.0000",
        "percent_duplicates": "0.0000",
        "percent_null": "0.0000",
        "percent_blank": "0.0000",
        "percent_distinct": "100.0000",
    }


def _analysis(*, from_name: str, from_tenant: str = "SOURCE") -> dict[str, object]:
    return {
        "from_tenant_code": from_tenant,
        "from_system_code": "ERP",
        "from_connection_code": "GDS",
        "from_object_schema": "bronze_sales",
        "from_object_name": from_name,
        "from_attribute_name": "customer_id",
        "to_tenant_code": "SOURCE",
        "to_system_code": "ERP",
        "to_connection_code": "GDS",
        "to_object_schema": "bronze_sales",
        "to_object_name": "orders",
        "to_attribute_name": "customer_id",
        "relationship_kind": "foreign_key",
        "relationship_confidence": "high",
        "relationship_basis": "Profile evidence.",
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
    }


def _snapshot() -> ModelSnapshot:
    return ModelSnapshot.model_validate(
        {
            "model_id": 18,
            "model_name": "Customer Model",
            "model_revision": 7,
            "model_input_scope": {
                "details": {
                    "model_name": "Customer Model",
                    "model_description": None,
                    "silver_model_naming_instructions": None,
                    "silver_model_audit_columns_template": None,
                    "gold_model_naming_instructions": None,
                    "gold_model_technical_columns_template": None,
                    "gold_model_audit_columns_template": None,
                },
                "objects": (
                    {
                        **_object_key("customers"),
                        "model_input_scope_is_locked": False,
                        "is_active": True,
                    },
                    {
                        **_object_key("orders"),
                        "model_input_scope_is_locked": False,
                        "is_active": True,
                    },
                ),
            },
            "profiling": {
                "profiles": (
                    _profile("customers"),
                    _profile("orders"),
                    _profile("customers", tenant_code="CONNECTION_OWNER"),
                )
            },
            "analysis": {
                "relationships": (
                    _analysis(from_name="customers"),
                    _analysis(from_name="customers", from_tenant="CONNECTION_OWNER"),
                )
            },
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
                        "modeling_assertion_record_key": "customer-meaning",
                        "modeling_assertion_document_name": "requirements.md",
                        "modeling_assertion_record_type": "business_rule",
                        "modeling_assertion_text": "Customer means a purchasing party.",
                        "modeling_assertion_details": {},
                        "modeling_assertion_source_location": None,
                        "modeling_assertion_applicable_layers": ("conceptual",),
                        "modeling_assertion_confidence": "high",
                        "modeling_assertion_record_status": "active",
                        "modeling_assertion_record_is_locked": True,
                    },
                    {
                        "modeling_assertion_record_key": "logical-only",
                        "modeling_assertion_document_name": "requirements.md",
                        "modeling_assertion_record_type": "business_rule",
                        "modeling_assertion_text": "Only for Logical authoring.",
                        "modeling_assertion_details": {},
                        "modeling_assertion_source_location": None,
                        "modeling_assertion_applicable_layers": ("logical",),
                        "modeling_assertion_confidence": "medium",
                        "modeling_assertion_record_status": "active",
                        "modeling_assertion_record_is_locked": False,
                    },
                ),
            },
            "conceptual": {
                "objects": (
                    {
                        "conceptual_object_name": "Legacy Customer",
                        "conceptual_object_definition": "Existing authored baseline.",
                        "conceptual_object_type": "entity",
                        "conceptual_object_grain": "One legacy customer.",
                        "conceptual_object_aliases": (),
                        "conceptual_object_confidence": "high",
                        "conceptual_object_status": "inactive",
                        "conceptual_object_is_locked": True,
                        "supports": (),
                    },
                ),
                "relationships": (),
            },
            "logical": {
                "submodels": (),
                "entities": (),
                "attributes": (),
                "relationships": (),
            },
            "dimensional": {
                "submodels": (),
                "entities": (),
                "attributes": (),
                "relationships": (),
            },
            "model_binding": {"objects": (), "attributes": ()},
            "mapping": {"dependencies": (), "objects": (), "attributes": ()},
        },
        strict=False,
    )


def _snapshot_with_large_assertion(text: str) -> ModelSnapshot:
    snapshot = _snapshot()
    assertion = snapshot.assertion.model_copy(
        update={
            "records": (
                snapshot.assertion.records[0].model_copy(update={"modeling_assertion_text": text}),
            )
        }
    )
    return snapshot.model_copy(update={"assertion": assertion})


def _dimensional_snapshot() -> ModelSnapshot:
    snapshot = _snapshot()
    silver_binding = ModelObjectBindingRecord.model_validate(
        {
            **_object_key("silver_customers"),
            "object_schema": "silver_sales",
            "modeled_entity_type": "logical_entity",
            "modeled_entity_name": "Customer",
            "model_object_binding_status": "active",
            "model_object_binding_is_locked": False,
        },
        strict=False,
    )
    dependency = MappingDependencyRecord.model_validate(
        {
            "modeled_entity_type": "logical_entity",
            "source_system_code": "ERP",
            "source_system_dependency_order": 0,
            "mapping_source_system_dependency_status": "active",
            "mapping_source_system_dependency_is_locked": False,
        },
        strict=False,
    )
    mapping = MappingObjectRecord.model_validate(
        {
            "modeled_entity_type": "logical_entity",
            "modeled_entity_name": "Customer",
            "source_system_code": "ERP",
            "output_template_code": None,
            "object_dependency_order": 0,
            "mapping_transformation_document": {},
            "object_mapping_status": "active",
            "object_mapping_is_locked": False,
        },
        strict=False,
    )
    return snapshot.model_copy(
        update={
            "model_binding": snapshot.model_binding.model_copy(
                update={
                    "objects": (silver_binding,),
                    "attributes": (
                        ModelAttributeBindingRecord(
                            modeled_entity_type="logical_entity",
                            modeled_entity_name="Customer",
                            modeled_attribute_name="CustomerID",
                            attribute_name="customer_id",
                            model_attribute_binding_status="active",
                            model_attribute_binding_is_locked=False,
                        ),
                    ),
                }
            ),
            "mapping": snapshot.mapping.model_copy(
                update={"dependencies": (dependency,), "objects": (mapping,)}
            ),
        }
    )


async def _load_physical_scope(
    transaction: object, model: ModelReadContext
) -> PhysicalModelCatalog:
    del transaction
    assert model.model_id == 18 and model.model_revision == 7
    return PhysicalModelCatalog(
        model_tenant_code="SOURCE",
        active_system_codes=frozenset({"ERP"}),
        objects=frozenset(),
        attributes=frozenset(),
        model_input_objects=frozenset(),
        model_input_attributes=frozenset(),
        dimensional_source_objects=frozenset(),
        dimensional_source_attributes=frozenset(),
        logical_mapping_target_objects=frozenset(),
        logical_mapping_target_attributes=frozenset(),
        dimensional_mapping_target_objects=frozenset(),
        dimensional_mapping_target_attributes=frozenset(),
    )


class ContextTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert "model_revision" in query
        assert parameters == (7, 18, 7)
        return {
            "model_id": 18,
            "tenant_id": 7,
            "model_name": "Customer Model",
            "model_revision": 7,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if "source_zone_description" in query:
            assert parameters == ([501], 7)
            return [
                {
                    "object_id": 501,
                    "zone_description": "Bronze",
                    "source_object_schema": "sales",
                    "source_object_name": "customers",
                    "source_object_description": "Source customers",
                    "tenant_code": "SOURCE",
                    "tenant_description": None,
                    "system_code": "ERP",
                    "system_description": None,
                    "system_type_code": "erp",
                    "system_type_description": None,
                    "connection_code": "SOURCE",
                    "connection_description": "Source application",
                    "connection_type_code": "sql",
                    "connection_type_description": None,
                    "source_zone_description": "Source",
                }
            ]
        if "profile.updated_time AS profiled_at" in query:
            assert parameters == (18, [501])
            return []
        if "attribute_ordinal_position" not in query:
            assert parameters == ([501], 18, "conceptual")
            return [
                {
                    "selection_order": 1,
                    "object_id": 501,
                    **_object_key("customers"),
                    "source_tenant_code": "SOURCE",
                    "fc_object_schema": None,
                    "fc_object_name": None,
                    "object_transformation": None,
                    "object_description": "sensitive physical description",
                    "batch_attribute_name": None,
                    "object_type_code": "table",
                    "zone_code": "bronze",
                    "is_locked": False,
                    "is_active": True,
                }
            ]
        assert parameters == ([501], 18, "conceptual", 101)
        return [
            {
                "object_id": 501,
                "attribute_id": 601,
                **_object_key("customers"),
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
            }
        ]


class DimensionalContextTransaction(ContextTransaction):
    def __init__(self, *, object_is_eligible: bool = True) -> None:
        self.object_is_eligible = object_is_eligible
        self.object_query_filtered = False
        self.attribute_query_filtered = False

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if "source_zone_description" in query:
            assert parameters == ([701], 7)
            return [
                {
                    "object_id": 701,
                    "zone_description": "Silver",
                    "tenant_code": None,
                    "source_object_name": None,
                }
            ]
        if "profile.updated_time AS profiled_at" in query:
            assert parameters == (18, [701])
            return []
        compact_query = " ".join(query.split())
        dimensional_filter = (
            "WHERE %s <> 'dimensional' OR eligibility.is_dimensional_source_eligible"
        )
        if "attribute_ordinal_position" not in query:
            self.object_query_filtered = dimensional_filter in compact_query
            expected_parameters = ([701], 18, "dimensional")
            if self.object_query_filtered:
                assert parameters == expected_parameters
                if not self.object_is_eligible:
                    return []
            else:
                assert parameters == expected_parameters[:2]
            return [
                {
                    "selection_order": 1,
                    "object_id": 701,
                    **_object_key("silver_customers"),
                    "source_tenant_code": "SOURCE",
                    "object_schema": "silver_sales",
                    "fc_object_schema": None,
                    "fc_object_name": None,
                    "object_transformation": None,
                    "object_description": "Mapped Silver customer Object.",
                    "batch_attribute_name": None,
                    "object_type_code": "table",
                    "zone_code": "silver",
                    "is_locked": False,
                    "is_active": True,
                }
            ]

        self.attribute_query_filtered = dimensional_filter in compact_query and compact_query.index(
            dimensional_filter
        ) < compact_query.index("LIMIT %s")
        expected_parameters = ([701], 18, "dimensional", 2)
        if self.attribute_query_filtered:
            assert parameters == expected_parameters
        else:
            assert parameters == (expected_parameters[0], expected_parameters[1], 2)
        common = {
            "selection_order": 1,
            "object_id": 701,
            **_object_key("silver_customers"),
            "object_schema": "silver_sales",
            "fc_attribute_name": None,
            "attribute_description": None,
            "attribute_data_type": "bigint",
            "attribute_inferred_data_type": None,
            "is_locked": False,
            "attribute_nullability": False,
            "attribute_custom_code": None,
            "is_surrogate_key": False,
            "is_natural_key": False,
            "is_meta_data": False,
            "is_masking_required": False,
            "is_purge": False,
            "is_active": True,
        }
        mapped = {
            **common,
            "attribute_id": 801,
            "attribute_name": "customer_id",
            "attribute_ordinal_position": 1,
            "is_mapped": True,
        }
        unmapped = {
            **common,
            "attribute_id": 802,
            "attribute_name": "unmapped_note",
            "attribute_ordinal_position": 2,
            "is_mapped": False,
        }
        return [mapped] if self.attribute_query_filtered else [mapped, unmapped]


class LogicalContextTransaction(ContextTransaction):
    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if len(parameters) == 2:
            return await super().fetch_all(query, parameters)
        assert parameters[2] == "logical"
        return await super().fetch_all(query, (*parameters[:2], "conceptual", *parameters[3:]))


@pytest.mark.asyncio
@pytest.mark.parametrize("model_workflow", ("conceptual", "logical"))
@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted"))
async def test_full_validation_state_stays_private_while_dependencies_are_readable(
    model_workflow: Literal["conceptual", "logical"],
    execution_mode: Literal["one_shot", "tool_assisted"],
) -> None:
    snapshot = _dimensional_snapshot()
    bindings = snapshot.model_binding.objects
    snapshot = snapshot.model_copy(
        update={
            "model_tenant_code": "PRIVATE_CATALOG_TENANT",
            "model_binding": snapshot.model_binding.model_copy(
                update={
                    "objects": (
                        *bindings,
                        bindings[0].model_copy(
                            update={
                                "modeled_entity_name": "Customer History",
                                "object_name": "history",
                            }
                        ),
                    )
                }
            ),
            "mapping": snapshot.mapping.model_copy(
                update={
                    "objects": (
                        snapshot.mapping.objects[0].model_copy(
                            update={
                                "mapping_transformation_document": {
                                    "expression": "PRIVATE_MAPPING_BODY"
                                },
                            }
                        ),
                    )
                }
            ),
            "code_generation": snapshot.code_generation.model_copy(
                update={
                    "artifacts": (
                        GeneratedCodeRecord(
                            generated_code_is_locked=False,
                            modeled_entity_type="logical_entity",
                            modeled_entity_name="Customer",
                            artifact_name="customers.sql",
                            artifact_type="sql_file",
                            generated_code_content="SELECT 'PRIVATE_CODE_BODY'",
                            generated_code_status="active",
                        ),
                    )
                }
            ),
        }
    )
    physical_scope = PhysicalModelCatalog(
        model_tenant_code="PRIVATE_CATALOG_TENANT",
        active_system_codes=frozenset({"ERP"}),
        objects=frozenset(),
        attributes=frozenset(),
        model_input_objects=frozenset(),
        model_input_attributes=frozenset(),
        dimensional_source_objects=frozenset(),
        dimensional_source_attributes=frozenset(),
        logical_mapping_target_objects=frozenset(),
        logical_mapping_target_attributes=frozenset(),
        dimensional_mapping_target_objects=frozenset(),
        dimensional_mapping_target_attributes=frozenset(),
    )
    transaction = (
        LogicalContextTransaction() if model_workflow == "logical" else ContextTransaction()
    )
    loaded: list[str] = []

    async def load_snapshot(actual_transaction: object, model: ModelReadContext) -> ModelSnapshot:
        assert actual_transaction is transaction
        assert model.model_revision == 7
        loaded.append("snapshot")
        return snapshot

    async def load_physical_scope(
        actual_transaction: object,
        model: ModelReadContext,
    ) -> PhysicalModelCatalog:
        assert actual_transaction is transaction
        assert model.model_revision == 7
        loaded.append("physical_scope")
        return physical_scope

    result = await PostgresAgentContextRepository(
        snapshot_loader=load_snapshot,
        physical_scope_loader=load_physical_scope,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1_000_000,
            stage_max_context_bytes=1_000_000,
            max_tool_result_bytes=1_000_000,
            max_tool_page_records=1,
        ),
    ).load(
        transaction,
        tenant_id=7,
        plan=_plan(
            model_workflow=model_workflow,
            execution_mode=execution_mode,
        ),
    )

    assert result.snapshot is snapshot
    assert result.snapshot is not None
    assert len(result.snapshot.model_input_scope.objects) == 2
    assert len(result.context.selected_objects) == 1
    assert result.physical_scope is physical_scope
    assert loaded == ["snapshot", "physical_scope"]
    provider_text = json.dumps(result.context.model_dump(mode="json")) + json.dumps(
        result.embedded_context
    )
    assert "PRIVATE_CATALOG_TENANT" not in provider_text + repr(result)
    assert "PRIVATE_MAPPING_BODY" not in provider_text + repr(result)
    assert "PRIVATE_CODE_BODY" not in provider_text + repr(result)
    if model_workflow == "logical":
        assert {item.dataset for item in result.context.read_only_dependencies} == {
            "model_object_binding",
            "model_attribute_binding",
            "mapping_dependency",
            "mapping_object",
            "generated_code",
        }
        if execution_mode == "tool_assisted":
            catalog = result.tool_catalog
            assert catalog is not None
            first = catalog.invoke(
                "get_agent_context_dataset",
                {
                    "dataset": "read_only_model_object_binding",
                    "offset": 0,
                    "limit": 1,
                },
            )
            assert isinstance(first, dict)
            assert first["next_offset"] == 1
            second = catalog.invoke(
                "get_agent_context_dataset",
                {
                    "dataset": "read_only_model_object_binding",
                    "offset": 1,
                    "limit": 1,
                },
            )
            assert isinstance(second, dict)
            assert second["next_offset"] is None
            assert first["items"] != second["items"]
            code = catalog.invoke(
                "get_agent_context_dataset",
                {
                    "dataset": "read_only_generated_code",
                    "offset": 0,
                    "limit": 1,
                },
            )
            assert "customers.sql" in json.dumps(code)
            assert "PRIVATE_CODE_BODY" not in json.dumps(code)
    else:
        assert result.context.read_only_dependencies == ()


async def _load_snapshot(*_: object) -> ModelSnapshot:
    return _snapshot()


def _snapshot_with_policy_json(value: dict[str, object]) -> ModelSnapshot:
    snapshot = _snapshot()
    details = snapshot.model_input_scope.details.model_copy(
        update={"silver_model_audit_columns_template": value}
    )
    model_input_scope = snapshot.model_input_scope.model_copy(update={"details": details})
    return snapshot.model_copy(update={"model_input_scope": model_input_scope})


def _snapshot_with_nested_supports(count: int) -> ModelSnapshot:
    snapshot = _snapshot()
    supports = tuple(
        ObjectSupportRecord.model_validate(
            {
                "support_source_type": "object",
                "source_object": _object_key(f"source_{index}"),
                "support_role": None,
                "support_reason": "Existing evidence.",
                "support_reason_detail": None,
                "support_confidence": "high",
                "support_status": "inactive",
                "support_is_locked": True,
            },
            strict=False,
        )
        for index in range(count)
    )
    conceptual_object = snapshot.conceptual.objects[0].model_copy(update={"supports": supports})
    conceptual = snapshot.conceptual.model_copy(update={"objects": (conceptual_object,)})
    return snapshot.model_copy(update={"conceptual": conceptual})


def _json_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        return set(mapping) | {
            nested_key for nested in mapping.values() for nested_key in _json_keys(nested)
        }
    if isinstance(value, list):
        items = cast(list[object], value)
        return {nested_key for nested in items for nested_key in _json_keys(nested)}
    return set()


@pytest.mark.asyncio
async def test_load_builds_selected_canonical_evidence_and_reconciliation_baseline() -> None:
    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1_000_000,
            stage_max_context_bytes=1_000_000,
            max_tool_result_bytes=1_000_000,
        ),
    ).load(ContextTransaction(), tenant_id=7, plan=_plan())

    context = result.context
    assert [item.object.object_name for item in context.selected_objects] == ["customers"]
    assert context.selected_objects[0].object.tenant_code == "SOURCE"
    assert [item.attribute_name for item in context.selected_objects[0].attributes] == [
        "customer_id"
    ]
    assert [item.object_name for item in context.profiles] == ["customers"]
    assert len(context.analysis_relationships) == 1
    assert [item.modeling_assertion_record_key for item in context.assertion.records] == [
        "customer-meaning"
    ]
    assert context.applied.conceptual is not None
    assert context.applied.conceptual.objects[0].conceptual_object_status == "inactive"
    assert context.applied.conceptual.objects[0].conceptual_object_is_locked is True
    assert context.applied.logical is None
    assert result.tool_catalog is None
    assert isinstance(result.embedded_context, dict)
    assert result.embedded_context["model_revision"] == 7
    assert "workflow_run_id" not in result.embedded_context
    assert "model_id" not in result.embedded_context
    assert not {key for key in _json_keys(result.embedded_context) if key.endswith("_id")}
    assert "sensitive physical description" not in repr(result)
    assert "private system prompt" not in repr(result)


@pytest.mark.asyncio
async def test_dimensional_context_keeps_only_eligible_mapped_silver_attributes() -> None:
    transaction = DimensionalContextTransaction()
    snapshot = _dimensional_snapshot()
    physical_scope: PhysicalModelCatalog | None = None
    bound = snapshot.model_binding.objects[0].model_copy(
        update={
            "modeled_entity_type": "dimensional_entity",
            "modeled_entity_name": "Customer Dimension",
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "model_binding": snapshot.model_binding.model_copy(
                update={"objects": (*snapshot.model_binding.objects, bound)}
            )
        }
    )
    scope_loaded = False

    async def load_dimensional_snapshot(*_: object) -> ModelSnapshot:
        return snapshot

    async def load_dimensional_scope(
        transaction: object, model: ModelReadContext
    ) -> PhysicalModelCatalog:
        nonlocal scope_loaded, physical_scope
        scope_loaded = True
        physical_scope = await _load_physical_scope(transaction, model)
        return physical_scope

    result = await PostgresAgentContextRepository(
        physical_scope_loader=load_dimensional_scope,
        snapshot_loader=load_dimensional_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=1,
            max_total_records=1_000,
            one_shot_max_context_bytes=1_000_000,
            stage_max_context_bytes=1_000_000,
            max_tool_result_bytes=1_000_000,
        ),
    ).load(
        transaction,
        tenant_id=7,
        plan=_plan(model_workflow="dimensional", selected_object_ids=(701,)),
    )

    assert transaction.object_query_filtered is True
    assert transaction.attribute_query_filtered is True
    assert result.context.selected_objects[0].object.zone_code == "silver"
    assert [
        attribute.attribute_name for attribute in result.context.selected_objects[0].attributes
    ] == ["customer_id"]
    assert result.context.selected_objects[0].attributes[0].is_mapped is True
    assert scope_loaded and result.snapshot is snapshot and result.physical_scope is physical_scope
    assert [(item.dataset, item.record) for item in result.context.read_only_dependencies] == [
        ("model_object_binding", bound.model_dump(mode="json")),
    ]


@pytest.mark.asyncio
async def test_dimensional_context_rejects_an_ineligible_selected_object() -> None:
    transaction = DimensionalContextTransaction(object_is_eligible=False)

    async def load_ineligible_dimensional_snapshot(*_: object) -> ModelSnapshot:
        return _dimensional_snapshot()

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=load_ineligible_dimensional_snapshot,
            limits=AgentContextLimits(
                max_selected_objects=10,
                max_selected_attributes=10,
                max_total_records=1_000,
                one_shot_max_context_bytes=1_000_000,
                stage_max_context_bytes=1_000_000,
                max_tool_result_bytes=1_000_000,
            ),
        ).load(
            transaction,
            tenant_id=7,
            plan=_plan(model_workflow="dimensional", selected_object_ids=(701,)),
        )

    assert captured.value.code == "agent_context_unavailable"
    assert transaction.object_query_filtered is True


@pytest.mark.asyncio
async def test_tool_assisted_mode_embeds_manifest_and_pages_only_local_records() -> None:
    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1_000_000,
            stage_max_context_bytes=1_000_000,
            max_tool_result_bytes=1_000_000,
            max_tool_page_records=1,
        ),
    ).load(
        ContextTransaction(),
        tenant_id=7,
        plan=_plan(execution_mode="tool_assisted"),
    )

    assert result.tool_catalog is not None
    manifest = result.embedded_context
    assert isinstance(manifest, dict)
    assert manifest["selected_objects"] == [
        {
            "selection_order": 1,
            **_object_key("customers"),
            "zone_code": "bronze",
            "attribute_count": 1,
        }
    ]
    dataset_counts = manifest["dataset_counts"]
    assert isinstance(dataset_counts, dict)
    assert dataset_counts.get("profiling_profile") == 1
    assert "profiles" not in manifest
    assert "workflow_run_id" not in manifest
    assert "model_id" not in manifest
    assert len(result.tool_catalog.allowed_tool_names) == 10
    assert "get_object_details" in result.tool_catalog.allowed_tool_names
    assert "get_agent_context_dataset" not in result.tool_catalog.allowed_tool_names

    page = result.tool_catalog.invoke(
        "get_agent_context_dataset",
        {"dataset": "profiling_profile", "offset": 0, "limit": 1},
    )
    assert isinstance(page, dict)
    assert page["total_count"] == 1
    assert page["items"] == [_profile("customers")]
    assert page["next_offset"] is None

    with pytest.raises(AgentContextToolRequestError):
        result.tool_catalog.invoke("read_database", {})
    assert "sensitive physical description" not in repr(result.tool_catalog)


@pytest.mark.asyncio
async def test_tool_result_budget_reserves_half_the_stage_for_all_turns() -> None:
    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1,
            stage_max_context_bytes=80_000,
            max_tool_result_bytes=80_000,
            max_tool_catalog_bytes=1_000_000,
        ),
    ).load(
        ContextTransaction(),
        tenant_id=7,
        plan=_plan(execution_mode="tool_assisted", max_turns=8),
    )

    assert result.tool_catalog is not None
    assert result.tool_catalog.max_result_bytes == 5_000
    assert result.tool_catalog.max_cumulative_result_bytes == 40_000
    manifest = result.tool_catalog.invoke("get_agent_context_manifest", {})
    assert (
        len(
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        <= result.tool_catalog.max_result_bytes
    )


@pytest.mark.asyncio
async def test_tool_manifest_compacts_selected_objects_to_stay_within_result_bound() -> None:
    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1_000_000,
            stage_max_context_bytes=1_000_000,
            max_tool_result_bytes=1_000_000,
            max_tool_catalog_bytes=1_000_000,
        ),
    ).load(ContextTransaction(), tenant_id=7, plan=_plan())
    generous = InMemoryAgentContextToolCatalog(
        context=result.context,
        max_result_bytes=1_000_000,
        max_catalog_bytes=1_000_000,
        max_page_records=200,
    )
    full_manifest_bytes = len(
        json.dumps(
            generous.manifest,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )

    compact = InMemoryAgentContextToolCatalog(
        context=result.context,
        max_result_bytes=full_manifest_bytes - 1,
        max_catalog_bytes=1_000_000,
        max_page_records=200,
    )
    manifest = cast(dict[str, object], compact.manifest)
    assert "selected_objects" not in manifest
    assert manifest["selected_objects_dataset"] == "selected_object"
    assert (
        len(
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        <= compact.max_result_bytes
    )


@pytest.mark.asyncio
async def test_tool_pages_byte_pack_and_reassemble_one_oversized_record() -> None:
    assertion_text = 'Policy says "retain" λ\\n' * 2_000

    async def load_large_snapshot(*_: object) -> ModelSnapshot:
        return _snapshot_with_large_assertion(assertion_text)

    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=load_large_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1,
            stage_max_context_bytes=256_000,
            max_tool_result_bytes=8_000,
            max_tool_catalog_bytes=1_000_000,
            max_tool_page_records=100,
        ),
    ).load(
        ContextTransaction(),
        tenant_id=7,
        plan=_plan(execution_mode="tool_assisted", max_turns=8),
    )

    catalog = result.tool_catalog
    assert catalog is not None
    manifest = cast(dict[str, object], catalog.manifest)
    page_counts = cast(dict[str, int], manifest["dataset_counts"])
    record_counts = cast(dict[str, int], manifest["dataset_record_counts"])
    dataset = "modeling_assertion_record"
    assert record_counts[dataset] == 1
    assert page_counts[dataset] > record_counts[dataset]
    count_semantics = cast(dict[str, str], manifest["dataset_count_semantics"])
    assert count_semantics == {
        "dataset_counts": "retrieval_items_and_page_total_count",
        "dataset_record_counts": "source_records",
    }
    fragment_contract = cast(dict[str, object], manifest["fragment_contract"])
    assert fragment_contract["fragment_marker_field"] == "__gds_context_fragment__"
    assert fragment_contract["encoding"] == "canonical_json"
    manifest_result = catalog.invoke("get_agent_context_manifest", {})
    assert (
        len(
            json.dumps(
                manifest_result,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        <= catalog.max_result_bytes
    )

    offset = 0
    fragments: list[dict[str, object]] = []
    first_page = True
    while offset < page_counts[dataset]:
        requested_limit = min(10, page_counts[dataset] - offset)
        page = cast(
            dict[str, object],
            catalog.invoke(
                "get_agent_context_dataset",
                {"dataset": dataset, "offset": offset, "limit": requested_limit},
            ),
        )
        page_bytes = len(
            json.dumps(
                page,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        assert page_bytes <= catalog.max_result_bytes
        items = cast(list[dict[str, object]], page["items"])
        assert items
        next_offset = page["next_offset"]
        expected_next = offset + len(items)
        assert next_offset == (expected_next if expected_next < page_counts[dataset] else None)
        if first_page:
            assert len(items) < requested_limit
            first_page = False
        fragments.extend(items)
        offset = expected_next

    metadata = [cast(dict[str, object], item["__gds_context_fragment__"]) for item in fragments]
    assert [item["fragment_index"] for item in metadata] == list(range(len(fragments)))
    assert {item["fragment_count"] for item in metadata} == {len(fragments)}
    assert {item["encoding"] for item in metadata} == {"canonical_json"}
    reconstructed = json.loads("".join(cast(str, item["json_text"]) for item in fragments))
    assert reconstructed == _snapshot_with_large_assertion(assertion_text).assertion.records[
        0
    ].model_dump(mode="json")


class UnavailableFenceTransaction(ContextTransaction):
    def __init__(self) -> None:
        self.selected_read_attempted = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        del query, parameters
        return None

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        del query, parameters
        self.selected_read_attempted = True
        return []


@pytest.mark.asyncio
async def test_revision_or_tenant_fence_fails_before_any_context_rows_are_read() -> None:
    transaction = UnavailableFenceTransaction()

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            snapshot_loader=_load_snapshot, physical_scope_loader=_load_physical_scope
        ).load(
            transaction,
            tenant_id=999,
            plan=_plan(),
        )

    assert captured.value.code == "agent_context_unavailable"
    assert transaction.selected_read_attempted is False


@pytest.mark.asyncio
async def test_embedded_mode_fails_on_json_bound_without_tool_fallback() -> None:
    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=_load_snapshot,
            limits=AgentContextLimits(
                max_selected_objects=10,
                max_selected_attributes=100,
                max_total_records=1_000,
                one_shot_max_context_bytes=100,
                stage_max_context_bytes=1_000_000,
                max_tool_result_bytes=1_000_000,
            ),
        ).load(ContextTransaction(), tenant_id=7, plan=_plan())

    assert captured.value.code == "agent_context_too_large"


@pytest.mark.asyncio
async def test_tool_mode_rejects_a_bound_too_small_for_its_manifest() -> None:
    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=_load_snapshot,
            limits=AgentContextLimits(
                max_selected_objects=10,
                max_selected_attributes=100,
                max_total_records=1_000,
                one_shot_max_context_bytes=1,
                stage_max_context_bytes=1_000_000,
                max_tool_result_bytes=100,
                max_tool_catalog_bytes=1_000_000,
            ),
        ).load(
            ContextTransaction(),
            tenant_id=7,
            plan=_plan(execution_mode="tool_assisted"),
        )

    assert captured.value.code == "agent_context_too_large"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_json",
    (
        {"object_id": 501},
        {"api_key": "prohibited-provider-value"},
    ),
)
async def test_provider_projection_rejects_unsafe_nested_json(
    unsafe_json: dict[str, object],
) -> None:
    async def load_unsafe_snapshot(*_: object) -> ModelSnapshot:
        return _snapshot_with_policy_json(unsafe_json)

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=load_unsafe_snapshot,
            limits=AgentContextLimits(
                max_selected_objects=10,
                max_selected_attributes=100,
                max_total_records=1_000,
                one_shot_max_context_bytes=1_000_000,
                stage_max_context_bytes=1_000_000,
                max_tool_result_bytes=1_000_000,
            ),
        ).load(ContextTransaction(), tenant_id=7, plan=_plan())

    assert captured.value.code == "agent_context_unavailable"
    assert "prohibited-provider-value" not in str(captured.value)


@pytest.mark.asyncio
async def test_nested_authored_records_count_toward_hard_record_bound() -> None:
    async def load_nested_snapshot(*_: object) -> ModelSnapshot:
        return _snapshot_with_nested_supports(25)

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=load_nested_snapshot,
            limits=AgentContextLimits(
                max_selected_objects=10,
                max_selected_attributes=100,
                max_total_records=20,
                one_shot_max_context_bytes=1_000_000,
                stage_max_context_bytes=1_000_000,
                max_tool_result_bytes=1_000_000,
            ),
        ).load(ContextTransaction(), tenant_id=7, plan=_plan())

    assert captured.value.code == "agent_context_too_large"


@pytest.mark.asyncio
async def test_tool_catalog_cap_measures_the_exact_stored_projection() -> None:
    generous = AgentContextLimits(
        max_selected_objects=10,
        max_selected_attributes=100,
        max_total_records=1_000,
        one_shot_max_context_bytes=1,
        stage_max_context_bytes=1_000_000,
        max_tool_result_bytes=1_000_000,
        max_tool_catalog_bytes=1_000_000,
    )
    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
        limits=generous,
    ).load(
        ContextTransaction(),
        tenant_id=7,
        plan=_plan(execution_mode="tool_assisted"),
    )

    assert result.tool_catalog is not None
    expected_payload = {
        "manifest": result.tool_catalog.manifest,
        "datasets": {},
        "prompt_values": result.tool_catalog.prompt_values,
    }
    datasets = cast(dict[str, object], expected_payload["datasets"])
    manifest = cast(dict[str, object], result.tool_catalog.manifest)
    dataset_counts = cast(dict[str, int], manifest["dataset_counts"])
    for dataset, count in dataset_counts.items():
        page = result.tool_catalog.invoke(
            "get_agent_context_dataset",
            {"dataset": dataset, "offset": 0, "limit": max(1, count)},
        )
        datasets[dataset] = cast(dict[str, object], page)["items"]
    expected_bytes = len(
        json.dumps(
            expected_payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    assert result.tool_catalog.serialized_size_bytes == expected_bytes

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=_load_snapshot,
            limits=generous.model_copy(update={"max_tool_catalog_bytes": expected_bytes - 1}),
        ).load(
            ContextTransaction(),
            tenant_id=7,
            plan=_plan(execution_mode="tool_assisted"),
        )

    assert captured.value.code == "agent_context_too_large"


class ChangingRevisionFenceTransaction(ContextTransaction):
    def __init__(self) -> None:
        self.fence_read_count = 0

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.fence_read_count += 1
        if self.fence_read_count == 1:
            return await super().fetch_one(query, parameters)
        return None


@pytest.mark.asyncio
async def test_read_committed_revision_change_fails_the_final_fence() -> None:
    transaction = ChangingRevisionFenceTransaction()

    with pytest.raises(WorkbenchError) as captured:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=_load_snapshot,
            limits=AgentContextLimits(
                max_selected_objects=10,
                max_selected_attributes=100,
                max_total_records=1_000,
                one_shot_max_context_bytes=1_000_000,
                stage_max_context_bytes=1_000_000,
                max_tool_result_bytes=1_000_000,
            ),
        ).load(
            transaction,
            tenant_id=7,
            plan=_plan(),
        )

    assert captured.value.code == "agent_context_unavailable"
    assert transaction.fence_read_count == 2


@pytest.mark.asyncio
async def test_projected_inputs_keep_actual_keys_profiles_and_scoped_relationships() -> None:
    from gds_workbench_api.features.workflows.authoring.context_contracts import (
        workflow_input_contracts,
    )
    from gds_workbench_api.features.workflows.authoring.context_inputs import (
        project_context_inputs,
    )
    from jsonschema import Draft202012Validator

    result = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
        limits=AgentContextLimits(
            max_selected_objects=10,
            max_selected_attributes=100,
            max_total_records=1_000,
            one_shot_max_context_bytes=1_000_000,
            stage_max_context_bytes=1_000_000,
            max_tool_result_bytes=1_000_000,
        ),
    ).load(ContextTransaction(), tenant_id=7, plan=_plan())
    values = project_context_inputs(result.context.model_dump(mode="json"))
    for name, spec in workflow_input_contracts("conceptual").items():
        assert cast(Any, Draft202012Validator(spec["schema"])).is_valid(values[name])
    assert values["source_context"][0]["connection_description"] == "Source application"
    assert values["object_context"][0]["connection_code"] == "GDS"
    assert values["ingestion_mapping"][0]["source"]["connection_code"] == "SOURCE"
    group = values["object_attribute_context"][0]
    assert group["selected_attribute_names"] == ["customer_id"]
    assert group["attributes"][0]["profile"]["row_count"] == 10
    assert group["attributes"][0]["profile"]["avg_data_length"] == 3.0
    assert group["attributes"][0]["profile"]["profiled_at"] is None
    # The saved endpoint outside this run's selection cannot enter the agent's result context.
    assert values["object_relationship_context"][0]["outgoing_relationships"] == []
    assert "read_only_dependencies" not in values
