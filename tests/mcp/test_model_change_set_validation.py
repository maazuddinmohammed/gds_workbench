from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.application.change_sets.model import (
    StageModelChange,
    validate_model_change_set_document_bounds,
    validate_model_stage_changes,
)
from gds_etl_workbench.application.change_sets.model_validation import (
    CodeGenerationTargetContext,
    validation_code_context_digest,
    validation_mapping_context_digest,
    validate_future_graph,
    validate_staged_records,
)
from gds_etl_workbench.domain.snapshots.model import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    ModelChangeSetDataset,
    build_model_dataset_schema,
)
from tests.mcp.model_test_fixtures import (
    SILVER_ORDER,
    complete_model_graph,
    complete_physical_scope,
    empty_model_snapshot,
    model_details,
    snapshot_from_graph,
)


def test_complete_25_dataset_model_graph_validates() -> None:
    graph = complete_model_graph()

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is True
    assert result.phase == "complete"
    assert result.issues == ()
    assert set(result.records) == set(CHANGE_SET_DATASETS_BY_NAME)
    assert len(result.action_review) == 25
    assert all(
        summary.insert_count + summary.no_change_count > 0
        for summary in result.action_review
    )
    assert result.candidate_digest is not None
    assert len(result.candidate_digest) == 64


def test_schema_failure_reports_a_bounded_repair_path() -> None:
    record = deepcopy(complete_model_graph()["logical_attribute"][0])
    del record["logical_attribute_definition"]

    records, issues = validate_staged_records("logical_attribute", [record])

    assert records == ()
    assert issues[0].code == "record_schema_invalid"
    assert issues[0].record_number == 1
    assert issues[0].fields == ("logical_attribute_definition",)
    assert "Field required" in issues[0].message


def test_duplicate_natural_keys_are_case_and_space_insensitive() -> None:
    first = complete_model_graph()["conceptual_object"][0]
    duplicate = {**first, "conceptual_object_name": " order "}

    records, issues = validate_staged_records(
        "conceptual_object",
        [first, duplicate],
    )

    assert len(records) == 1
    assert issues[0].code == "duplicate_canonical_key"


def test_model_input_scope_accepts_only_eligible_source_or_bronze_objects() -> None:
    graph = complete_model_graph()
    scope = replace(complete_physical_scope(), model_input_objects=frozenset())

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents={"model_input_scope": graph["model_input_scope"]},
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert {issue.dataset for issue in result.issues} == {"model_input_scope"}


@pytest.mark.parametrize(
    "dataset",
    ["profiling_profile", "analysis_result", "conceptual_object", "logical_entity"],
)
def test_source_work_uses_active_model_input_scope(
    dataset: ModelChangeSetDataset,
) -> None:
    graph = complete_model_graph()
    graph["model_input_scope"] = []

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents={
            "model_details": graph["model_details"],
            "model_input_scope": graph["model_input_scope"],
            dataset: graph[dataset],
        },
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(issue.dataset == dataset for issue in result.issues)


def test_binding_target_must_be_eligible_for_its_modeled_layer() -> None:
    graph = complete_model_graph()
    scope = replace(
        complete_physical_scope(), logical_mapping_target_objects=frozenset()
    )

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(issue.dataset == "model_object_binding" for issue in result.issues)


def test_active_attribute_binding_requires_active_object_binding() -> None:
    graph = complete_model_graph()
    graph["model_object_binding"][0]["model_object_binding_status"] = "inactive"

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(
        issue.code == "inactive_parent" and issue.dataset == "model_attribute_binding"
        for issue in result.issues
    )


def test_active_object_binding_requires_every_active_modeled_attribute() -> None:
    graph = complete_model_graph()
    graph["model_attribute_binding"] = [
        record
        for record in graph["model_attribute_binding"]
        if not (
            record["modeled_entity_type"] == "logical_entity"
            and record["modeled_entity_name"] == "Order"
            and record["modeled_attribute_name"] == "CustomerID"
        )
    ]
    scope = complete_physical_scope()
    missing_target = (*tuple(part.casefold() for part in SILVER_ORDER), "customerid")
    scope = replace(
        scope,
        attributes=scope.attributes - {missing_target},
        logical_mapping_target_attributes=(
            scope.logical_mapping_target_attributes - {missing_target}
        ),
    )

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(
        issue.code == "binding_coverage_missing"
        and issue.fields == ("modeled_attribute_name",)
        for issue in result.issues
    )
    assert not any(
        issue.code == "binding_coverage_missing" and issue.fields == ("attribute_name",)
        for issue in result.issues
    )


def test_active_object_binding_requires_every_physical_target_attribute() -> None:
    graph = complete_model_graph()
    scope = complete_physical_scope()
    unbound_target = (
        *tuple(part.casefold() for part in SILVER_ORDER),
        "audittimestamp",
    )
    scope = replace(
        scope,
        attributes=scope.attributes | {unbound_target},
        logical_mapping_target_attributes=(
            scope.logical_mapping_target_attributes | {unbound_target}
        ),
    )

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(
        issue.code == "binding_coverage_missing" and issue.fields == ("attribute_name",)
        for issue in result.issues
    )
    assert not any(
        issue.code == "binding_coverage_missing"
        and issue.fields == ("modeled_attribute_name",)
        for issue in result.issues
    )


def test_active_mapping_requires_every_bound_target_attribute_per_source_system() -> (
    None
):
    graph = complete_model_graph()
    graph["mapping_attribute"] = graph["mapping_attribute"][:1]

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "mapping_attribute"
        for issue in result.issues
    )


def test_active_mapping_requires_binding_dependency_and_transformation() -> None:
    graph = complete_model_graph()
    graph["mapping_object"][0]["mapping_transformation_document"] = None

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.code == "active_dependency_invalid" and issue.dataset == "mapping_object"
        for issue in result.issues
    )


@pytest.mark.parametrize("assignment_count", [0, 2])
def test_each_mapped_system_is_assigned_to_exactly_one_active_code_artifact(
    assignment_count: int,
) -> None:
    graph = complete_model_graph()
    assignment = graph["generated_code_source_system"][0]
    graph["generated_code_source_system"] = [deepcopy(assignment)] * assignment_count
    if assignment_count == 2:
        graph["generated_code"].append(
            {
                **graph["generated_code"][0],
                "artifact_name": "OrderSecond.sql",
            }
        )
        graph["generated_code_source_system"][1] = {
            **graph["generated_code_source_system"][1],
            "artifact_name": "OrderSecond.sql",
        }

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "generated_code_source_system"
        for issue in result.issues
    )


def test_generated_code_uses_binding_identity_and_artifact_name_only() -> None:
    schema = build_model_dataset_schema(DATASETS_BY_NAME["generated_code"])

    assert set(schema["properties"]) == {
        "modeled_entity_type",
        "modeled_entity_name",
        "artifact_name",
        "artifact_type",
        "generated_code_content",
        "generated_code_status",
    }
    forbidden = {
        "tenant_code",
        "object_name",
        "mapping_context_digest",
        "source_context_digest",
        "generated_code_digest",
        "generated_code_is_locked",
        "is_logged",
    }
    assert forbidden.isdisjoint(schema["properties"])


def test_generated_code_rejects_an_artifact_path() -> None:
    record = deepcopy(complete_model_graph()["generated_code"][0])
    record["artifact_name"] = "sql/Order.sql"

    records, issues = validate_staged_records("generated_code", [record])

    assert records == ()
    assert issues[0].code == "record_schema_invalid"
    assert issues[0].fields == () or "artifact_name" in issues[0].fields


def test_validation_records_do_not_accept_digests_or_execution_results() -> None:
    group_schema = build_model_dataset_schema(DATASETS_BY_NAME["validation_group"])
    check_schema = build_model_dataset_schema(DATASETS_BY_NAME["validation_check"])

    assert "mapping_context_digest" not in group_schema["properties"]
    assert "code_context_digest" not in group_schema["properties"]
    forbidden_results = {
        "execution_status",
        "execution_result",
        "actual_value",
        "passed",
    }
    assert forbidden_results.isdisjoint(check_schema["properties"])


def test_active_validation_rejects_unsafe_sql() -> None:
    graph = complete_model_graph()
    graph["validation_check"][0]["validation_query_sql"] = (
        "DELETE FROM main.silver.Order"
    )

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(issue.code == "validation_query_invalid" for issue in result.issues)


def test_inactive_validation_can_retire_legacy_unsafe_sql() -> None:
    graph = complete_model_graph()
    graph["validation_check"][0]["validation_query_sql"] = "DELETE FROM old_table"
    graph["validation_check"][0]["is_active"] = False

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is True


def test_active_validation_check_requires_active_group() -> None:
    graph = complete_model_graph()
    graph["validation_group"][0]["is_active"] = False

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "validation_check"
        for issue in result.issues
    )


def test_active_validation_group_requires_mapping_for_its_source_system() -> None:
    graph = complete_model_graph()
    graph["validation_group"][0]["system_code"] = "GDS"
    graph["validation_check"][0]["system_code"] = "GDS"

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "validation_group"
        and issue.fields == ("system_code",)
        for issue in result.issues
    )


def test_server_derived_validation_context_digests_are_stable() -> None:
    context = CodeGenerationTargetContext(
        object_key=tuple(part.casefold() for part in SILVER_ORDER),
        modeled_entity_type="logical_entity",
        modeled_entity_name="Order",
        source_system_codes=frozenset({"ERP"}),
        code_input_digest="a" * 64,
    )
    code = SimpleNamespace(
        modeled_entity_type="logical_entity",
        modeled_entity_name="Order",
        artifact_name="Order.sql",
        artifact_type="sql_file",
        generated_code_content="SELECT 1",
        generated_code_status="active",
    )

    mapping_digest = validation_mapping_context_digest((context,), "erp")
    code_digest = validation_code_context_digest((context,), (code,), "erp")

    assert mapping_digest is not None and len(mapping_digest) == 64
    assert code_digest is not None and len(code_digest) == 64
    assert mapping_digest != code_digest


def test_locked_applied_record_cannot_change() -> None:
    graph = complete_model_graph()
    graph["conceptual_object"][0]["conceptual_object_is_locked"] = True
    snapshot = snapshot_from_graph(graph)
    changed = deepcopy(graph["conceptual_object"][0])
    changed["conceptual_object_definition"] = "Changed definition."

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"conceptual_object": [changed]},
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "locks"
    assert result.issues[0].code == "record_locked"


def test_model_name_conflict_is_tenant_scoped() -> None:
    scope = replace(
        complete_physical_scope(), other_model_names=frozenset({"salesmodel"})
    )

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents={"model_details": [model_details()]},
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.issues[0].code == "model_name_conflict"


def test_stage_rejects_raw_prompt_content_without_reflecting_it() -> None:
    record = deepcopy(complete_model_graph()["modeling_assertion_record"][0])
    record["modeling_assertion_details"] = {
        "review": {"raw_prompt": "sensitive prompt value"}
    }

    with pytest.raises(InvalidRequestError) as captured:
        validate_model_stage_changes(
            [StageModelChange(dataset="modeling_assertion_record", records=[record])]
        )

    assert "prohibited raw content" in captured.value.message
    assert "sensitive prompt value" not in captured.value.message


def test_assertion_section_is_bounded_at_four_mib() -> None:
    documents: dict[str, dict[str, list[dict[str, object]]]] = {
        "assertion": {
            "modeling_assertion_record": [
                {"modeling_assertion_text": "x" * 262_144} for _ in range(17)
            ]
        }
    }

    with pytest.raises(InvalidRequestError, match="Assertion Section exceeds 4 MiB"):
        validate_model_change_set_document_bounds(documents)
