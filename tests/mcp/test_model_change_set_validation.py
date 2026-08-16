from __future__ import annotations

from copy import deepcopy
from typing import cast

from gds_etl_workbench.domain.modeling_records import ConceptualObjectRecord
from gds_etl_workbench.tools.change_sets.model_validation import (
    PhysicalModelScope,
    validate_future_graph,
    validate_staged_records,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS_BY_NAME,
    AnalysisSection,
    AssertionSection,
    ConceptualSection,
    DimensionalSection,
    LogicalSection,
    MappingSection,
    ModelScopeSection,
    ModelSnapshot,
    ProfilingSection,
    build_model_dataset_schema,
)


def test_complete_model_graph_validates() -> None:
    staged = _complete_graph()

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents=staged,
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is True
    assert result.issues == ()
    assert set(result.records) == set(DATASETS_BY_NAME)
    assert result.phase == "complete"
    assert result.candidate_digest is not None
    assert len(result.candidate_digest) == 64
    assert len(result.action_review) == 19
    assert all(
        summary.insert_count
        + summary.update_count
        + summary.deactivate_count
        + summary.reactivate_count
        + summary.no_change_count
        > 0
        for summary in result.action_review
    )


def test_every_dataset_schema_excludes_database_and_audit_fields() -> None:
    forbidden = {
        "agent_run_id",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
    }

    for definition in DATASETS_BY_NAME.values():
        schema_text = str(build_model_dataset_schema(definition))
        assert all(field not in schema_text for field in forbidden)


def test_staged_dataset_rejects_case_insensitive_duplicate_natural_keys() -> None:
    first = _complete_graph()["conceptual_object"][0]
    duplicate = deepcopy(first)
    duplicate["conceptual_object_name"] = " customer "

    records, issues = validate_staged_records(
        "conceptual_object",
        [first, duplicate],
    )

    assert len(records) == 1
    assert issues[0].code == "duplicate_canonical_key"


def test_future_graph_reports_duplicate_keys_in_uniqueness_phase() -> None:
    first = _complete_graph()["conceptual_object"][0]
    duplicate = deepcopy(first)
    duplicate["conceptual_object_name"] = " customer "

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={"conceptual_object": [first, duplicate]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "uniqueness"
    assert result.action_review == ()


def test_future_graph_rejects_physical_reference_outside_model_scope() -> None:
    staged = _complete_graph()
    profile = staged["profiling_profile"][0]
    profile["object_name"] = "outside_scope"

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents=staged,
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert any(
        issue.dataset == "profiling_profile"
        and issue.code == "model_scope_reference_invalid"
        for issue in result.issues
    )


def test_future_graph_reports_missing_modeled_reference() -> None:
    staged = _complete_graph()
    staged["logical_entity"] = [staged["logical_entity"][0]]

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents=staged,
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.dataset == "logical_attribute" and issue.code == "reference_not_found"
        for issue in result.issues
    )


def test_future_graph_rejects_change_to_locked_applied_record() -> None:
    raw = _complete_graph()["conceptual_object"][0]
    locked = ConceptualObjectRecord.model_validate(
        {**raw, "conceptual_object_is_locked": True},
        strict=False,
    )
    snapshot = _empty_snapshot(
        conceptual=ConceptualSection(objects=(locked,), relationships=())
    )
    changed = deepcopy(raw)
    changed["conceptual_object_definition"] = "Changed definition"

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"conceptual_object": [changed]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "locks"
    assert result.issues[0].code == "record_locked"


def test_future_graph_rejects_change_to_locked_nested_record() -> None:
    raw = deepcopy(_complete_graph()["conceptual_object"][0])
    supports = cast(list[dict[str, object]], raw["supports"])
    supports[0]["support_is_locked"] = True
    applied = ConceptualObjectRecord.model_validate(
        raw,
        strict=False,
    )
    snapshot = _empty_snapshot(
        conceptual=ConceptualSection(objects=(applied,), relationships=())
    )
    changed = deepcopy(raw)
    changed_supports = cast(list[dict[str, object]], changed["supports"])
    changed_supports[0]["support_reason"] = "Changed reason"

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"conceptual_object": [changed]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.code == "record_locked" and issue.fields == ("supports",)
        for issue in result.issues
    )


def test_model_scope_archive_is_reviewed_as_deactivation() -> None:
    archived = deepcopy(_model_scope_records()[0])
    archived["is_active"] = False

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={"model_scope": [archived]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is True
    assert result.action_review[0].dataset == "model_scope"
    assert result.action_review[0].deactivate_count == 1


def test_model_scope_rejects_unavailable_object_addition() -> None:
    added = deepcopy(_model_scope_records()[0])
    added["object_name"] = "outside_scope"

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={"model_scope": [added]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert result.issues[0].dataset == "model_scope"


def test_model_scope_rejects_archiving_locked_membership() -> None:
    locked_records = _model_scope_records()
    locked_records[0]["model_scope_is_locked"] = True
    snapshot = _empty_snapshot()
    snapshot = snapshot.model_copy(
        update={
            "model_scope": ModelScopeSection.model_validate(
                {
                    "details": _model_details("Sales Model"),
                    "objects": locked_records,
                },
                strict=False,
            )
        }
    )
    archived = deepcopy(locked_records[0])
    archived["is_active"] = False

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"model_scope": [archived]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "locks"


def test_model_details_rejects_duplicate_tenant_model_name() -> None:
    physical_scope = _complete_physical_scope()
    physical_scope = PhysicalModelScope(
        model_tenant_code=physical_scope.model_tenant_code,
        active_system_codes=physical_scope.active_system_codes,
        objects=physical_scope.objects,
        attributes=physical_scope.attributes,
        other_model_names=frozenset({"updated sales model"}),
    )

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={"model_details": [_model_details("Updated Sales Model")]},
        physical_scope=physical_scope,
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert result.issues[0].code == "model_name_conflict"


def _empty_snapshot(
    *,
    conceptual: ConceptualSection | None = None,
) -> ModelSnapshot:
    return ModelSnapshot(
        model_id=1,
        model_name="Sales Model",
        model_revision=1,
        model_scope=ModelScopeSection.model_validate(
            {
                "details": _model_details("Sales Model"),
                "objects": _model_scope_records(),
            },
            strict=False,
        ),
        profiling=ProfilingSection(profiles=()),
        analysis=AnalysisSection(relationships=()),
        assertion=AssertionSection(documents=(), records=()),
        conceptual=conceptual or ConceptualSection(objects=(), relationships=()),
        logical=LogicalSection(
            submodels=(), entities=(), attributes=(), relationships=()
        ),
        dimensional=DimensionalSection(
            submodels=(), entities=(), attributes=(), relationships=()
        ),
        mapping=MappingSection(dependencies=(), objects=(), attributes=()),
    )


def _complete_physical_scope() -> PhysicalModelScope:
    objects = frozenset(
        {
            ("demo", "erp", "source", "sales", "orders"),
            ("demo", "erp", "source", "sales", "customers"),
        }
    )
    return PhysicalModelScope(
        model_tenant_code="DEMO",
        active_system_codes=frozenset({"erp"}),
        objects=objects,
        attributes=frozenset({(*key, "customer_id") for key in objects}),
    )


def _complete_graph() -> dict[str, list[dict[str, object]]]:
    physical_object = {
        "tenant_code": "DEMO",
        "system_code": "ERP",
        "connection_code": "SOURCE",
        "object_schema": "sales",
        "object_name": "orders",
    }
    physical_attribute = {**physical_object, "attribute_name": "customer_id"}
    return {
        "model_details": [_model_details("Updated Sales Model")],
        "model_scope": _model_scope_records(),
        "profiling_profile": [
            {
                **physical_attribute,
                "row_count": 10,
                "non_null_count": 9,
                "null_count": 1,
                "blank_count": 0,
                "distinct_count": 5,
                "min_data_length": 1,
                "max_data_length": 5,
                "avg_data_length": 2,
                "percent_populated": 90,
                "percent_duplicates": 44.4444,
                "percent_null": 10,
                "percent_blank": 0,
                "percent_distinct": 55.5556,
            }
        ],
        "analysis_result": [
            {
                "from_tenant_code": "DEMO",
                "from_system_code": "ERP",
                "from_connection_code": "SOURCE",
                "from_object_schema": "sales",
                "from_object_name": "orders",
                "from_attribute_name": "customer_id",
                "to_tenant_code": "DEMO",
                "to_system_code": "ERP",
                "to_connection_code": "SOURCE",
                "to_object_schema": "sales",
                "to_object_name": "customers",
                "to_attribute_name": "customer_id",
                "relationship_kind": "foreign_key_candidate",
                "relationship_confidence": "high",
                "relationship_basis": "Values overlap.",
                "validation_policy_version": "1.0.0",
                "validation_result": "supported",
                "validation_source_non_null_count": 9,
                "validation_source_distinct_count": 5,
                "validation_target_non_null_count": 5,
                "validation_target_distinct_count": 5,
                "validation_source_missing_target_count": 0,
                "validation_unused_target_count": 0,
                "validation_duplicate_target_key_count": 0,
                "analysis_result_status": "active",
                "analysis_result_is_locked": False,
            }
        ],
        "modeling_assertion_document": [
            {
                "modeling_assertion_document_name": "Business rules",
                "tenant_code": "DEMO",
                "system_code": "ERP",
                "modeling_assertion_file_pattern": None,
                "modeling_assertion_document_type": "requirements",
                "modeling_assertion_document_description": "Approved rules.",
                "modeling_assertion_document_metadata": {},
                "is_active": True,
            }
        ],
        "modeling_assertion_record": [
            {
                "modeling_assertion_record_key": "order.customer",
                "modeling_assertion_document_name": "Business rules",
                "modeling_assertion_record_type": "business_rule",
                "modeling_assertion_text": "Every order belongs to a customer.",
                "modeling_assertion_details": {},
                "modeling_assertion_source_location": None,
                "modeling_assertion_applicable_layers": [
                    "conceptual",
                    "logical",
                    "dimensional",
                ],
                "modeling_assertion_confidence": "high",
                "modeling_assertion_record_status": "active",
                "modeling_assertion_record_is_locked": False,
            }
        ],
        "conceptual_object": [
            {
                "conceptual_object_name": "Customer",
                "conceptual_object_definition": "A buyer.",
                "conceptual_object_type": "party",
                "conceptual_object_grain": "One customer.",
                "conceptual_object_aliases": ["Buyer"],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "supports": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {
                            "modeling_assertion_record_key": "order.customer"
                        },
                        "support_role": "definition",
                        "support_reason": "Business rule identifies the concept.",
                        "support_reason_detail": None,
                        "support_confidence": "high",
                        "support_status": "active",
                        "support_is_locked": False,
                    },
                    {
                        "support_source_type": "object",
                        "source_object": physical_object,
                        "support_role": "source",
                        "support_reason": "Orders identify participating customers.",
                        "support_reason_detail": None,
                        "support_confidence": "high",
                        "support_status": "active",
                        "support_is_locked": False,
                    },
                ],
            },
            {
                "conceptual_object_name": "Order",
                "conceptual_object_definition": "A purchase commitment.",
                "conceptual_object_type": "transaction",
                "conceptual_object_grain": "One order.",
                "conceptual_object_aliases": [],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "supports": [],
            },
        ],
        "conceptual_relationship": [
            {
                "from_conceptual_object_name": "Order",
                "to_conceptual_object_name": "Customer",
                "conceptual_relationship_name": "belongs to",
                "conceptual_relationship_type": "association",
                "conceptual_relationship_definition": "Order belongs to customer.",
                "conceptual_relationship_cardinality": "many_to_one",
                "conceptual_relationship_basis": "Business rule.",
                "conceptual_relationship_cardinality_basis": "Many orders per customer.",
                "conceptual_relationship_confidence": "high",
                "conceptual_relationship_status": "active",
                "conceptual_relationship_is_locked": False,
                "supports": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {
                            "modeling_assertion_record_key": "order.customer"
                        },
                        "support_role": "cardinality",
                        "support_reason": "Business rule defines the relationship.",
                        "support_reason_detail": None,
                        "support_confidence": "high",
                        "support_status": "active",
                        "support_is_locked": False,
                    }
                ],
            }
        ],
        "logical_submodel": [
            {
                "logical_submodel_name": "Sales",
                "logical_submodel_definition": "Sales domain.",
                "logical_submodel_status": "active",
                "logical_submodel_is_locked": False,
            }
        ],
        "logical_entity": [
            _logical_entity(
                "Order",
                "transaction",
                sources=[
                    {
                        "support_source_type": "object",
                        "source_object": physical_object,
                        "source_order": 1,
                        "rationale": "Orders are the primary source.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            ),
            _logical_entity("Customer", "core"),
        ],
        "logical_attribute": [
            _logical_attribute(
                "Order",
                "customer_id",
                1,
                sources=[
                    {
                        "support_source_type": "attribute",
                        "source_attribute": physical_attribute,
                        "source_order": 1,
                        "rationale": "Direct physical source.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            ),
            _logical_attribute("Customer", "customer_id", 1),
        ],
        "logical_relationship": [
            {
                "logical_relationship_name": "order customer",
                "logical_relationship_definition": "Order references customer.",
                "from_logical_entity_name": "Order",
                "from_logical_attribute_name": "customer_id",
                "to_logical_entity_name": "Customer",
                "to_logical_attribute_name": "customer_id",
                "logical_relationship_cardinality": "many_to_one",
                "logical_relationship_confidence": "high",
                "logical_relationship_basis": "Source values.",
                "logical_relationship_cardinality_basis": "Many orders per customer.",
                "logical_relationship_status": "active",
                "logical_relationship_is_locked": False,
            }
        ],
        "dimensional_submodel": [
            {
                "dimensional_submodel_name": "Sales Mart",
                "dimensional_submodel_definition": "Sales analytics.",
                "dimensional_submodel_status": "active",
                "dimensional_submodel_is_locked": False,
            }
        ],
        "dimensional_entity": [
            _dimensional_entity(
                "Sales Fact",
                "fact",
                "transaction",
                "One order.",
                sources=[
                    {
                        "support_source_type": "object",
                        "source_object": physical_object,
                        "source_role": "transaction_source",
                        "source_order": 1,
                        "rationale": "Orders define the fact grain.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            ),
            _dimensional_entity("Customer Dimension", "dimension", None, None),
        ],
        "dimensional_attribute": [
            _dimensional_attribute(
                "Sales Fact",
                "customer_key",
                sources=[
                    {
                        "support_source_type": "attribute",
                        "source_attribute": physical_attribute,
                        "source_order": 1,
                        "rationale": "Customer source key.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            ),
            _dimensional_attribute("Customer Dimension", "customer_key"),
        ],
        "dimensional_relationship": [
            {
                "dimensional_relationship_name": "sales customer",
                "dimensional_relationship_definition": "Fact joins customer.",
                "from_dimensional_entity_name": "Sales Fact",
                "from_dimensional_attribute_name": "customer_key",
                "to_dimensional_entity_name": "Customer Dimension",
                "to_dimensional_attribute_name": "customer_key",
                "dimensional_relationship_kind": "fact_dimension",
                "dimensional_relationship_cardinality": "many_to_one",
                "dimensional_relationship_role_name": None,
                "dimensional_relationship_confidence": "high",
                "dimensional_relationship_basis": "Star schema.",
                "dimensional_relationship_cardinality_basis": "Many facts per customer.",
                "dimensional_relationship_status": "active",
                "dimensional_relationship_is_locked": False,
            }
        ],
        "mapping_dependency": [
            {
                "modeled_entity_type": "logical_entity",
                "source_system_code": "ERP",
                "source_system_dependency_order": 0,
                "mapping_source_system_dependency_status": "active",
                "mapping_source_system_dependency_is_locked": False,
            }
        ],
        "mapping_object": [
            {
                **physical_object,
                "source_system_code": "ERP",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Order",
                "object_dependency_order": 0,
                "artifact_type": None,
                "artifact_generation_instructions": None,
                "mapping_profile_key": None,
                "mapping_profile_version": None,
                "mapping_package_document": None,
                "object_mapping_transformation_document": None,
                "object_mapping_status": "active",
                "object_mapping_is_locked": False,
            }
        ],
        "mapping_attribute": [
            {
                **physical_attribute,
                "source_system_code": "ERP",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Order",
                "modeled_attribute_name": "customer_id",
                "attribute_mapping_transformation_document": None,
                "attribute_mapping_status": "active",
                "attribute_mapping_is_locked": False,
            }
        ],
    }


def _model_details(model_name: str) -> dict[str, object]:
    return {
        "model_name": model_name,
        "model_description": "Sales analytics model.",
        "silver_model_naming_template": None,
        "silver_model_audit_columns_template": None,
        "gold_model_naming_template": None,
        "gold_model_technical_columns_template": None,
        "gold_model_audit_columns_template": None,
    }


def _model_scope_records() -> list[dict[str, object]]:
    return [
        {
            "tenant_code": "DEMO",
            "system_code": "ERP",
            "connection_code": "SOURCE",
            "object_schema": "sales",
            "object_name": object_name,
            "model_scope_is_locked": False,
            "is_active": True,
        }
        for object_name in ("orders", "customers")
    ]


def _logical_entity(
    name: str,
    entity_type: str,
    *,
    sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "logical_entity_name": name,
        "logical_entity_definition": f"{name} entity.",
        "logical_entity_type": entity_type,
        "logical_entity_type_detail": None,
        "logical_entity_grain": f"One {name.lower()}.",
        "logical_entity_dependency_order": 0,
        "logical_entity_confidence": "high",
        "logical_entity_status": "active",
        "logical_entity_is_locked": False,
        "submodels": [
            {
                "submodel_name": "Sales",
                "membership_status": "active",
                "membership_is_locked": False,
            }
        ],
        "sources": sources or [],
    }


def _logical_attribute(
    entity: str,
    name: str,
    ordinal: int,
    *,
    sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "logical_entity_name": entity,
        "logical_attribute_name": name,
        "logical_attribute_definition": f"{name} attribute.",
        "logical_attribute_data_type": "bigint",
        "logical_attribute_is_nullable": False,
        "logical_attribute_is_primary_key": entity == "Customer",
        "logical_attribute_is_natural_key": entity == "Customer",
        "logical_attribute_is_surrogate_key": False,
        "logical_attribute_ordinal_position": ordinal,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_status": "active",
        "logical_attribute_is_locked": False,
        "sources": sources or [],
    }


def _dimensional_entity(
    name: str,
    entity_type: str,
    fact_type: str | None,
    grain: str | None,
    *,
    sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "dimensional_entity_name": name,
        "dimensional_entity_definition": f"{name} entity.",
        "dimensional_entity_type": entity_type,
        "dimensional_fact_type": fact_type,
        "dimensional_entity_grain_definition": grain,
        "dimensional_entity_dependency_order": 0,
        "dimensional_entity_confidence": "high",
        "dimensional_entity_status": "active",
        "dimensional_entity_is_locked": False,
        "submodels": [
            {
                "submodel_name": "Sales Mart",
                "membership_status": "active",
                "membership_is_locked": False,
            }
        ],
        "sources": sources or [],
    }


def _dimensional_attribute(
    entity: str,
    name: str,
    *,
    sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "dimensional_entity_name": entity,
        "dimensional_attribute_name": name,
        "dimensional_attribute_definition": f"{name} attribute.",
        "dimensional_attribute_data_type": "bigint",
        "dimensional_attribute_is_nullable": False,
        "dimensional_attribute_ordinal_position": 1,
        "dimensional_attribute_role": "key",
        "dimensional_attribute_key_role": "foreign",
        "dimensional_attribute_is_grain_component": True,
        "dimensional_attribute_additivity": None,
        "dimensional_attribute_default_aggregation": None,
        "dimensional_attribute_aggregation_basis": None,
        "dimensional_attribute_change_behavior": None,
        "dimensional_attribute_is_audit_column": False,
        "dimensional_attribute_confidence": "high",
        "dimensional_attribute_status": "active",
        "dimensional_attribute_is_locked": False,
        "sources": sources or [],
    }
