from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import ConceptualObjectRecord
from gds_etl_workbench.tools.change_sets.model import (
    StageModelChange,
    validate_model_change_set_document_bounds,
    validate_model_stage_changes,
)
from gds_etl_workbench.tools.change_sets.model_validation import (
    PhysicalModelScope,
    validate_future_graph,
    validate_staged_records,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    AnalysisSection,
    AssertionSection,
    ConceptualSection,
    DimensionalSection,
    LogicalSection,
    MappingSection,
    ModelChangeSetDataset,
    ModelScopeSection,
    ModelSnapshot,
    ProfilingSection,
    build_model_dataset_schema,
)


def test_model_change_set_stage_rejects_raw_prompt_assertion_details() -> None:
    record = deepcopy(complete_graph()["modeling_assertion_record"][0])
    record["modeling_assertion_details"] = {"review": {"raw_prompt": "sensitive prompt value"}}

    with pytest.raises(InvalidRequestError) as captured:
        validate_model_stage_changes(
            [StageModelChange(dataset="modeling_assertion_record", records=[record])]
        )

    assert captured.value.message == (
        "Record does not match the exact modeling_assertion_record schema."
    )
    assert "sensitive prompt value" not in captured.value.message


@pytest.mark.parametrize(
    ("dataset", "field", "prohibited_key"),
    [
        ("modeling_assertion_document", "modeling_assertion_document_metadata", "raw_rows"),
        ("modeling_assertion_record", "modeling_assertion_details", "tool-output"),
        ("modeling_assertion_record", "modeling_assertion_source_location", "fileContent"),
        ("modeling_assertion_record", "modeling_assertion_details", "api_secret"),
    ],
)
def test_model_change_set_stage_rejects_prohibited_assertion_json_keys(
    dataset: ModelChangeSetDataset,
    field: str,
    prohibited_key: str,
) -> None:
    record = deepcopy(complete_graph()[dataset][0])
    record[field] = {"nested": {prohibited_key: "sensitive raw value"}}

    with pytest.raises(InvalidRequestError) as captured:
        validate_model_stage_changes([StageModelChange(dataset=dataset, records=[record])])

    assert captured.value.message == f"Record does not match the exact {dataset} schema."
    assert "sensitive raw value" not in captured.value.message


@pytest.mark.parametrize(
    ("dataset", "field", "oversized_value"),
    [
        (
            "modeling_assertion_document",
            "modeling_assertion_document_metadata",
            {"notes": ["x" * 32_000] * 3},
        ),
        (
            "modeling_assertion_record",
            "modeling_assertion_text",
            "x" * 262_145,
        ),
        (
            "modeling_assertion_record",
            "modeling_assertion_details",
            {"notes": ["x" * 32_000] * 9},
        ),
        (
            "modeling_assertion_record",
            "modeling_assertion_source_location",
            {"notes": ["x" * 16_000] * 5},
        ),
    ],
)
def test_model_change_set_stage_rejects_oversized_assertion_fields(
    dataset: ModelChangeSetDataset,
    field: str,
    oversized_value: object,
) -> None:
    record = deepcopy(complete_graph()[dataset][0])
    record[field] = oversized_value

    with pytest.raises(InvalidRequestError) as captured:
        validate_model_stage_changes([StageModelChange(dataset=dataset, records=[record])])

    assert captured.value.message == f"Record does not match the exact {dataset} schema."
    assert "x" * 100 not in captured.value.message


def test_model_change_set_stage_rejects_overly_complex_assertion_json() -> None:
    too_deep: object = "bounded value"
    for _ in range(13):
        too_deep = {"nested": too_deep}
    record = deepcopy(complete_graph()["modeling_assertion_record"][0])
    record["modeling_assertion_details"] = too_deep

    with pytest.raises(InvalidRequestError) as captured:
        validate_model_stage_changes(
            [StageModelChange(dataset="modeling_assertion_record", records=[record])]
        )

    assert captured.value.message == (
        "Record does not match the exact modeling_assertion_record schema."
    )
    assert "bounded value" not in captured.value.message


def test_model_change_set_stage_accepts_bounded_structured_assertions() -> None:
    graph = complete_graph()

    staged = validate_model_stage_changes(
        [
            StageModelChange(
                dataset="modeling_assertion_document",
                records=graph["modeling_assertion_document"],
            ),
            StageModelChange(
                dataset="modeling_assertion_record",
                records=graph["modeling_assertion_record"],
            ),
        ]
    )

    assert staged == {
        "modeling_assertion_document": graph["modeling_assertion_document"],
        "modeling_assertion_record": graph["modeling_assertion_record"],
    }


def test_model_change_set_bounds_the_complete_assertion_section_at_four_mib() -> None:
    documents: dict[str, dict[str, list[dict[str, object]]]] = {
        "assertion": {
            "modeling_assertion_record": [
                {"modeling_assertion_text": "x" * 262_144} for _ in range(17)
            ]
        }
    }

    with pytest.raises(InvalidRequestError, match="Assertion Section exceeds 4 MiB"):
        validate_model_change_set_document_bounds(documents)


def test_assertion_section_bound_does_not_reduce_other_section_limits() -> None:
    documents: dict[str, dict[str, list[dict[str, object]]]] = {
        "conceptual": {
            "conceptual_object": [{"conceptual_object_definition": "x" * (5 * 1024 * 1024)}]
        }
    }

    validate_model_change_set_document_bounds(documents)


def test_complete_model_graph_validates() -> None:
    staged = complete_graph()

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents=staged,
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is True
    assert result.issues == ()
    assert set(result.records) == set(CHANGE_SET_DATASETS_BY_NAME)
    assert result.phase == "complete"
    assert result.candidate_digest is not None
    assert len(result.candidate_digest) == 64
    assert len(result.action_review) == 18
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
    first = complete_graph()["conceptual_object"][0]
    duplicate = deepcopy(first)
    duplicate["conceptual_object_name"] = " customer "

    records, issues = validate_staged_records(
        "conceptual_object",
        [first, duplicate],
    )

    assert len(records) == 1
    assert issues[0].code == "duplicate_canonical_key"


def test_future_graph_reports_duplicate_keys_in_uniqueness_phase() -> None:
    first = complete_graph()["conceptual_object"][0]
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
    staged = complete_graph()
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
        issue.dataset == "profiling_profile" and issue.code == "model_scope_reference_invalid"
        for issue in result.issues
    )


def test_profile_requires_bronze_attribute_eligibility() -> None:
    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={"profiling_profile": complete_graph()["profiling_profile"]},
        physical_scope=replace(
            _complete_physical_scope(),
            bronze_source_attributes=frozenset(),
        ),
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert result.issues[0].dataset == "profiling_profile"
    assert result.issues[0].code == "model_scope_reference_invalid"


@pytest.mark.parametrize(
    "dataset",
    ["analysis_result", "conceptual_object", "logical_entity", "logical_attribute"],
)
def test_source_sections_require_bronze_physical_eligibility(
    dataset: ModelChangeSetDataset,
) -> None:
    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={dataset: complete_graph()[dataset]},
        physical_scope=replace(
            _complete_physical_scope(),
            bronze_source_objects=frozenset(),
            bronze_source_attributes=frozenset(),
        ),
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert any(issue.dataset == dataset for issue in result.issues)


@pytest.mark.parametrize("dataset", ["dimensional_entity", "dimensional_attribute"])
def test_dimensional_sources_require_applied_logical_mapping_eligibility(
    dataset: ModelChangeSetDataset,
) -> None:
    record = deepcopy(complete_graph()[dataset][0])
    silver_object = {
        "tenant_code": "DEMO",
        "system_code": "ERP",
        "connection_code": "SOURCE",
        "object_schema": "sales",
        "object_name": "silver_orders",
    }
    if dataset == "dimensional_entity":
        record["sources"] = [
            {
                "support_source_type": "object",
                "source_object": silver_object,
                "source_role": "transaction_source",
                "source_order": 1,
                "rationale": "Applied Logical Mapping contribution.",
                "status": "active",
                "is_locked": False,
            }
        ]
    else:
        record["sources"] = [
            {
                "support_source_type": "attribute",
                "source_attribute": {**silver_object, "attribute_name": "customer_id"},
                "source_order": 1,
                "rationale": "Applied Logical Mapping contribution.",
                "status": "active",
                "is_locked": False,
            }
        ]
    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={dataset: [record]},
        physical_scope=replace(
            _complete_physical_scope(),
            dimensional_source_objects=frozenset(),
            dimensional_source_attributes=frozenset(),
        ),
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert any(issue.dataset == dataset for issue in result.issues)


@pytest.mark.parametrize(
    (
        "modeled_entity_type",
        "entity_name",
        "modeled_attribute_name",
        "target_object_name",
        "object_field",
        "attribute_field",
    ),
    [
        (
            "logical_entity",
            "Order",
            "customer_id",
            "silver_orders",
            "logical_mapping_target_objects",
            "logical_mapping_target_attributes",
        ),
        (
            "dimensional_entity",
            "Sales Fact",
            "customer_key",
            "gold_sales",
            "dimensional_mapping_target_objects",
            "dimensional_mapping_target_attributes",
        ),
    ],
)
def test_mapping_targets_require_layer_zone_eligibility(
    modeled_entity_type: str,
    entity_name: str,
    modeled_attribute_name: str,
    target_object_name: str,
    object_field: str,
    attribute_field: str,
) -> None:
    mapping_object = deepcopy(complete_graph()["mapping_object"][0])
    mapping_object["modeled_entity_type"] = modeled_entity_type
    mapping_object["modeled_entity_name"] = entity_name
    mapping_object["object_name"] = target_object_name
    mapping_attribute = deepcopy(complete_graph()["mapping_attribute"][0])
    mapping_attribute["modeled_entity_type"] = modeled_entity_type
    mapping_attribute["modeled_entity_name"] = entity_name
    mapping_attribute["modeled_attribute_name"] = modeled_attribute_name
    mapping_attribute["object_name"] = target_object_name

    result = validate_future_graph(
        snapshot=_empty_snapshot(),
        staged_documents={
            "mapping_object": [mapping_object],
            "mapping_attribute": [mapping_attribute],
        },
        physical_scope=replace(
            _complete_physical_scope(),
            **{object_field: frozenset(), attribute_field: frozenset()},
        ),
    )

    assert result.valid is False
    assert result.phase == "model_scope"
    assert {issue.dataset for issue in result.issues} == {
        "mapping_object",
        "mapping_attribute",
    }


def test_future_graph_reports_missing_modeled_reference() -> None:
    staged = complete_graph()
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


@pytest.mark.parametrize("retired_status", ["inactive", "deprecated"])
def test_future_graph_rejects_active_mapping_for_retired_logical_entity(
    retired_status: str,
) -> None:
    graph = complete_graph()
    retired_entity = deepcopy(graph["logical_entity"][0])
    retired_entity["logical_entity_status"] = retired_status

    result = validate_future_graph(
        snapshot=_snapshot_from_graph(graph),
        staged_documents={"logical_entity": [retired_entity]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "mapping_object"
        and issue.fields == ("modeled_entity_name",)
        for issue in result.issues
    )


def test_future_graph_rejects_active_mapping_for_retired_logical_attribute() -> None:
    graph = complete_graph()
    retired_attribute = deepcopy(graph["logical_attribute"][0])
    retired_attribute["logical_attribute_status"] = "inactive"

    result = validate_future_graph(
        snapshot=_snapshot_from_graph(graph),
        staged_documents={"logical_attribute": [retired_attribute]},
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "mapping_attribute"
        and issue.fields == ("modeled_attribute_name",)
        for issue in result.issues
    )


def test_future_graph_rejects_active_dimensional_object_source_after_mapping_retirement() -> None:
    graph = complete_graph()
    dimensional_entity = deepcopy(graph["dimensional_entity"][0])
    dimensional_entity["sources"] = [_silver_object_source()]
    graph["dimensional_entity"][0] = dimensional_entity

    result = validate_future_graph(
        snapshot=_snapshot_from_graph(graph),
        staged_documents=_retire_order_logical_mapping(graph),
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "dimensional_entity"
        and issue.fields == ("sources",)
        for issue in result.issues
    )


def test_future_graph_rejects_active_dimensional_attribute_source_after_mapping_retirement() -> (
    None
):
    graph = complete_graph()
    dimensional_attribute = deepcopy(graph["dimensional_attribute"][0])
    dimensional_attribute["sources"] = [_silver_attribute_source()]
    graph["dimensional_attribute"][0] = dimensional_attribute
    retired_attribute = deepcopy(graph["logical_attribute"][0])
    retired_attribute["logical_attribute_status"] = "inactive"
    retired_relationship = deepcopy(graph["logical_relationship"][0])
    retired_relationship["logical_relationship_status"] = "inactive"
    retired_mapping_attribute = deepcopy(graph["mapping_attribute"][0])
    retired_mapping_attribute["attribute_mapping_status"] = "inactive"

    result = validate_future_graph(
        snapshot=_snapshot_from_graph(graph),
        staged_documents={
            "logical_attribute": [retired_attribute],
            "logical_relationship": [retired_relationship],
            "mapping_attribute": [retired_mapping_attribute],
        },
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "dimensional_attribute"
        and issue.fields == ("sources",)
        for issue in result.issues
    )


def test_future_graph_allows_complete_logical_mapping_and_dimensional_retirement() -> None:
    graph = complete_graph()
    dimensional_entity = deepcopy(graph["dimensional_entity"][0])
    dimensional_entity["sources"] = [_silver_object_source()]
    graph["dimensional_entity"][0] = dimensional_entity
    dimensional_attribute = deepcopy(graph["dimensional_attribute"][0])
    dimensional_attribute["sources"] = [_silver_attribute_source()]
    graph["dimensional_attribute"][0] = dimensional_attribute
    staged = _retire_order_logical_mapping(graph)
    retired_dimensional_entity = deepcopy(dimensional_entity)
    retired_dimensional_entity["dimensional_entity_status"] = "inactive"
    retired_dimensional_entity["sources"] = []
    retired_dimensional_attribute = deepcopy(dimensional_attribute)
    retired_dimensional_attribute["dimensional_attribute_status"] = "inactive"
    retired_dimensional_attribute["sources"] = []
    retired_dimensional_relationship = deepcopy(graph["dimensional_relationship"][0])
    retired_dimensional_relationship["dimensional_relationship_status"] = "inactive"
    staged.update(
        {
            "dimensional_entity": [retired_dimensional_entity],
            "dimensional_attribute": [retired_dimensional_attribute],
            "dimensional_relationship": [retired_dimensional_relationship],
        }
    )

    result = validate_future_graph(
        snapshot=_snapshot_from_graph(graph),
        staged_documents=staged,
        physical_scope=_complete_physical_scope(),
    )

    assert result.valid is True


def test_future_graph_rejects_change_to_locked_applied_record() -> None:
    raw = complete_graph()["conceptual_object"][0]
    locked = ConceptualObjectRecord.model_validate(
        {**raw, "conceptual_object_is_locked": True},
        strict=False,
    )
    snapshot = _empty_snapshot(conceptual=ConceptualSection(objects=(locked,), relationships=()))
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
    raw = deepcopy(complete_graph()["conceptual_object"][0])
    supports = cast(list[dict[str, object]], raw["supports"])
    supports[0]["support_is_locked"] = True
    applied = ConceptualObjectRecord.model_validate(
        raw,
        strict=False,
    )
    snapshot = _empty_snapshot(conceptual=ConceptualSection(objects=(applied,), relationships=()))
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
        issue.code == "record_locked" and issue.fields == ("supports",) for issue in result.issues
    )


def test_model_details_rejects_duplicate_tenant_model_name() -> None:
    physical_scope = _complete_physical_scope()
    physical_scope = replace(
        physical_scope,
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


def _snapshot_from_graph(
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]],
) -> ModelSnapshot:
    return ModelSnapshot.model_validate(
        {
            "model_id": 1,
            "model_name": "Sales Model",
            "model_revision": 1,
            "model_scope": {
                "details": graph["model_details"][0],
                "objects": model_scope_records(),
            },
            "profiling": {"profiles": graph["profiling_profile"]},
            "analysis": {"relationships": graph["analysis_result"]},
            "assertion": {
                "documents": graph["modeling_assertion_document"],
                "records": graph["modeling_assertion_record"],
            },
            "conceptual": {
                "objects": graph["conceptual_object"],
                "relationships": graph["conceptual_relationship"],
            },
            "logical": {
                "submodels": graph["logical_submodel"],
                "entities": graph["logical_entity"],
                "attributes": graph["logical_attribute"],
                "relationships": graph["logical_relationship"],
            },
            "dimensional": {
                "submodels": graph["dimensional_submodel"],
                "entities": graph["dimensional_entity"],
                "attributes": graph["dimensional_attribute"],
                "relationships": graph["dimensional_relationship"],
            },
            "mapping": {
                "dependencies": graph["mapping_dependency"],
                "objects": graph["mapping_object"],
                "attributes": graph["mapping_attribute"],
            },
        },
        strict=False,
    )


def _silver_object_source() -> dict[str, object]:
    return {
        "support_source_type": "object",
        "source_object": {
            "tenant_code": "DEMO",
            "system_code": "ERP",
            "connection_code": "SOURCE",
            "object_schema": "sales",
            "object_name": "silver_orders",
        },
        "source_role": "transaction_source",
        "source_order": 1,
        "rationale": "Applied Logical Mapping contribution.",
        "status": "active",
        "is_locked": False,
    }


def _silver_attribute_source() -> dict[str, object]:
    return {
        "support_source_type": "attribute",
        "source_attribute": {
            "tenant_code": "DEMO",
            "system_code": "ERP",
            "connection_code": "SOURCE",
            "object_schema": "sales",
            "object_name": "silver_orders",
            "attribute_name": "customer_id",
        },
        "source_order": 1,
        "rationale": "Applied Logical Mapping contribution.",
        "status": "active",
        "is_locked": False,
    }


def _retire_order_logical_mapping(
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]],
) -> dict[ModelChangeSetDataset, list[dict[str, object]]]:
    retired_entity = deepcopy(graph["logical_entity"][0])
    retired_entity["logical_entity_status"] = "inactive"
    retired_attribute = deepcopy(graph["logical_attribute"][0])
    retired_attribute["logical_attribute_status"] = "inactive"
    retired_relationship = deepcopy(graph["logical_relationship"][0])
    retired_relationship["logical_relationship_status"] = "inactive"
    retired_mapping_object = deepcopy(graph["mapping_object"][0])
    retired_mapping_object["object_mapping_status"] = "inactive"
    retired_mapping_attribute = deepcopy(graph["mapping_attribute"][0])
    retired_mapping_attribute["attribute_mapping_status"] = "inactive"
    return {
        "logical_entity": [retired_entity],
        "logical_attribute": [retired_attribute],
        "logical_relationship": [retired_relationship],
        "mapping_object": [retired_mapping_object],
        "mapping_attribute": [retired_mapping_attribute],
    }


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
                "objects": model_scope_records(),
            },
            strict=False,
        ),
        profiling=ProfilingSection(profiles=()),
        analysis=AnalysisSection(relationships=()),
        assertion=AssertionSection(documents=(), records=()),
        conceptual=conceptual or ConceptualSection(objects=(), relationships=()),
        logical=LogicalSection(submodels=(), entities=(), attributes=(), relationships=()),
        dimensional=DimensionalSection(submodels=(), entities=(), attributes=(), relationships=()),
        mapping=MappingSection(dependencies=(), objects=(), attributes=()),
    )


def _complete_physical_scope() -> PhysicalModelScope:
    bronze_objects = frozenset(
        {
            ("demo", "erp", "source", "sales", "orders"),
            ("demo", "erp", "source", "sales", "customers"),
        }
    )
    silver_objects = frozenset({("demo", "erp", "source", "sales", "silver_orders")})
    gold_objects = frozenset({("demo", "erp", "source", "sales", "gold_sales")})
    objects = bronze_objects | silver_objects | gold_objects
    attributes = frozenset({(*key, "customer_id") for key in objects})
    return PhysicalModelScope(
        model_tenant_code="DEMO",
        active_system_codes=frozenset({"erp"}),
        objects=objects,
        attributes=attributes,
        bronze_source_objects=bronze_objects,
        bronze_source_attributes=frozenset({(*key, "customer_id") for key in bronze_objects}),
        dimensional_source_objects=silver_objects,
        dimensional_source_attributes=frozenset({(*key, "customer_id") for key in silver_objects}),
        logical_mapping_target_objects=silver_objects,
        logical_mapping_target_attributes=frozenset(
            {(*key, "customer_id") for key in silver_objects}
        ),
        dimensional_mapping_target_objects=gold_objects,
        dimensional_mapping_target_attributes=frozenset(
            {(*key, "customer_id") for key in gold_objects}
        ),
    )


def complete_graph() -> dict[ModelChangeSetDataset, list[dict[str, object]]]:
    physical_object = {
        "tenant_code": "DEMO",
        "system_code": "ERP",
        "connection_code": "SOURCE",
        "object_schema": "sales",
        "object_name": "orders",
    }
    physical_attribute = {**physical_object, "attribute_name": "customer_id"}
    logical_target_object = {**physical_object, "object_name": "silver_orders"}
    logical_target_attribute = {
        **logical_target_object,
        "attribute_name": "customer_id",
    }
    return {
        "model_details": [_model_details("Updated Sales Model")],
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
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
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
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
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
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_role": "transaction_source",
                        "source_order": 1,
                        "rationale": "Business rule defines the fact grain.",
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
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_order": 1,
                        "rationale": "Business rule identifies the customer key.",
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
                "dimensional_relationship_is_optional": False,
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
                **logical_target_object,
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
                **logical_target_attribute,
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
        "silver_model_naming_instructions": "Use clear Silver business names.",
        "silver_model_audit_columns_template": None,
        "gold_model_naming_instructions": "Use clear Gold business names.",
        "gold_model_technical_columns_template": None,
        "gold_model_audit_columns_template": None,
    }


def model_scope_records() -> list[dict[str, object]]:
    return [
        {
            "tenant_code": "DEMO",
            "system_code": "ERP",
            "connection_code": "SOURCE",
            "object_schema": "sales",
            "object_name": object_name,
            "zone_code": (
                "Bronze"
                if object_name in ("orders", "customers")
                else "Silver"
                if object_name == "silver_orders"
                else "Gold"
            ),
            "is_bronze_source_eligible": object_name in ("orders", "customers"),
            "is_dimensional_source_eligible": object_name == "silver_orders",
            "is_logical_mapping_target_eligible": object_name == "silver_orders",
            "is_dimensional_mapping_target_eligible": object_name == "gold_sales",
            "model_scope_is_locked": False,
            "is_active": True,
        }
        for object_name in ("orders", "customers", "silver_orders", "gold_sales")
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
