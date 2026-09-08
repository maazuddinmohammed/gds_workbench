from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Literal

import pytest

from gds_etl_workbench.application.change_sets.model import (
    StageModelChange,
    model_validation_outcome,
    validate_model_change_set_document_bounds,
    validate_model_stage_changes,
)
from gds_etl_workbench.application.change_sets.model_validation import (
    CodeGenerationTargetContext,
    ModelValidationIssue,
    PhysicalModelCatalog,
    ValidatedModelChangeSet,
    validate_future_graph,
    validate_staged_records,
    validation_code_context_digest,
    validation_mapping_context_digest,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.model import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    ModelChangeSetDataset,
    build_model_dataset_schema,
)
from tests.mcp.model_test_fixtures import (
    GOLD_SALES_FACT,
    SILVER_ORDER,
    SOURCE_ORDERS,
    complete_model_graph,
    complete_physical_scope,
    empty_model_snapshot,
    model_details,
    physical_attribute,
    physical_object,
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


def test_model_validation_outcome_groups_errors_and_bounds_agent_examples() -> None:
    validation = ValidatedModelChangeSet(
        records={},
        phase="references",
        candidate_digest="a" * 64,
        issues=tuple(
            ModelValidationIssue(
                code="reference_not_found",
                dataset="mapping_attribute",
                record_number=None,
                fields=("modeled_attribute_name",),
                message="Referenced record is missing.",
            )
            for _ in range(30)
        ),
        action_review=(),
    )

    outcome = model_validation_outcome(validation)

    assert outcome["error_count"] == 30
    assert outcome["error_groups"] == [
        {
            "dataset": "mapping_attribute",
            "code": "reference_not_found",
            "count": 30,
        }
    ]
    assert len(outcome["errors"]) == 25
    assert outcome["errors_truncated"] is True


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


def _model_layer_graph(
    layer: Literal["conceptual", "logical", "dimensional"],
) -> dict[ModelChangeSetDataset, list[dict[str, object]]]:
    return {
        dataset: records
        for dataset, records in complete_model_graph().items()
        if dataset.startswith(f"{layer}_")
        or dataset
        in {
            "model_details",
            "model_input_scope",
            "modeling_assertion_document",
            "modeling_assertion_record",
        }
    }


@pytest.mark.parametrize("side", ["from", "to"])
@pytest.mark.parametrize("action", ["deactivate_parent", "reactivate_child"])
def test_active_conceptual_relationship_requires_both_active_objects(
    side: str,
    action: str,
) -> None:
    graph = _model_layer_graph("conceptual")
    relationship = graph["conceptual_relationship"][0]
    endpoint = str(relationship[f"{side}_conceptual_object_name"])
    # Canonical references are case/space insensitive, including lifecycle checks.
    relationship[f"{side}_conceptual_object_name"] = f" {endpoint.upper()} "
    parent = next(
        record
        for record in graph["conceptual_object"]
        if record["conceptual_object_name"] == endpoint
    )
    if action == "reactivate_child":
        parent["conceptual_object_status"] = "inactive"
        relationship["conceptual_relationship_status"] = "inactive"
    snapshot = snapshot_from_graph(graph)
    baseline = validate_future_graph(
        snapshot=snapshot,
        staged_documents={},
        physical_scope=complete_physical_scope(),
    )
    assert baseline.valid
    if action == "deactivate_parent":
        changed = {**parent, "conceptual_object_status": "inactive"}
        changes: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
            "conceptual_object": [changed],
        }
    else:
        changed = {**relationship, "conceptual_relationship_status": "active"}
        changes = {"conceptual_relationship": [changed]}

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents=changes,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "conceptual_relationship"
        and issue.fields == ("conceptual_object_name",)
        for issue in result.issues
    )


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize("action", ["deactivate_parent", "reactivate_child"])
def test_active_modeled_attribute_requires_active_parent_entity(
    layer: Literal["logical", "dimensional"],
    action: str,
) -> None:
    graph = _model_layer_graph(layer)
    entity_dataset = "logical_entity" if layer == "logical" else "dimensional_entity"
    attribute_dataset = (
        "logical_attribute" if layer == "logical" else "dimensional_attribute"
    )
    relationship_dataset = (
        "logical_relationship" if layer == "logical" else "dimensional_relationship"
    )
    graph[relationship_dataset] = []
    parent = graph[entity_dataset][0]
    parent_name = str(parent[f"{layer}_entity_name"])
    children = [
        record
        for record in graph[attribute_dataset]
        if record[f"{layer}_entity_name"] == parent_name
    ]
    assert children
    for child in children:
        child[f"{layer}_entity_name"] = f" {parent_name.upper()} "
    if action == "reactivate_child":
        parent[f"{layer}_entity_status"] = "inactive"
        for child in children:
            child[f"{layer}_attribute_status"] = "inactive"
    snapshot = snapshot_from_graph(graph)
    baseline = validate_future_graph(
        snapshot=snapshot,
        staged_documents={},
        physical_scope=complete_physical_scope(),
    )
    assert baseline.valid
    if action == "deactivate_parent":
        changes = {entity_dataset: [{**parent, f"{layer}_entity_status": "inactive"}]}
    else:
        changes = {
            attribute_dataset: [{**children[0], f"{layer}_attribute_status": "active"}]
        }

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents=changes,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == attribute_dataset
        and issue.fields == (f"{layer}_entity_name",)
        for issue in result.issues
    )


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize("side", ["from", "to"])
@pytest.mark.parametrize("inactive_record", ["entity", "attribute"])
@pytest.mark.parametrize("action", ["deactivate_endpoint", "reactivate_relationship"])
def test_active_modeled_relationship_requires_active_attributes_and_entities(
    layer: Literal["logical", "dimensional"],
    side: str,
    inactive_record: str,
    action: str,
) -> None:
    graph = _model_layer_graph(layer)
    relationship_dataset = (
        "logical_relationship" if layer == "logical" else "dimensional_relationship"
    )
    relationship = graph[relationship_dataset][0]
    entity_name = str(relationship[f"{side}_{layer}_entity_name"])
    attribute_name = str(relationship[f"{side}_{layer}_attribute_name"])
    relationship[f"{side}_{layer}_entity_name"] = f" {entity_name.upper()} "
    relationship[f"{side}_{layer}_attribute_name"] = f" {attribute_name.upper()} "
    dataset: ModelChangeSetDataset = (
        ("logical_entity" if layer == "logical" else "dimensional_entity")
        if inactive_record == "entity"
        else ("logical_attribute" if layer == "logical" else "dimensional_attribute")
    )
    endpoint = next(
        record
        for record in graph[dataset]
        if record[f"{layer}_entity_name"] == entity_name
        and (
            inactive_record == "entity"
            or record[f"{layer}_attribute_name"] == attribute_name
        )
    )
    if action == "reactivate_relationship":
        endpoint[f"{layer}_{inactive_record}_status"] = "inactive"
        relationship[f"{layer}_relationship_status"] = "inactive"
        if inactive_record == "entity":
            attribute_dataset = (
                "logical_attribute" if layer == "logical" else "dimensional_attribute"
            )
            for attribute in graph[attribute_dataset]:
                if attribute[f"{layer}_entity_name"] == entity_name:
                    attribute[f"{layer}_attribute_status"] = "inactive"
    snapshot = snapshot_from_graph(graph)
    baseline = validate_future_graph(
        snapshot=snapshot,
        staged_documents={},
        physical_scope=complete_physical_scope(),
    )
    assert baseline.valid
    changes: dict[ModelChangeSetDataset, list[dict[str, object]]] = (
        {dataset: [{**endpoint, f"{layer}_{inactive_record}_status": "inactive"}]}
        if action == "deactivate_endpoint"
        else {
            relationship_dataset: [
                {**relationship, f"{layer}_relationship_status": "active"}
            ]
        }
    )

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents=changes,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == relationship_dataset
        and issue.fields == (f"{layer}_attribute_name",)
        for issue in result.issues
    )


@pytest.mark.parametrize("layer", ["conceptual", "logical", "dimensional"])
@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize("status", ["active", "inactive"])
def test_model_layer_activity_is_independent_of_locks(
    layer: Literal["conceptual", "logical", "dimensional"],
    locked: bool,
    status: str,
) -> None:
    graph = _model_layer_graph(layer)
    for dataset, records in graph.items():
        if dataset.startswith(f"{layer}_"):
            for record in records:
                record[f"{dataset}_status"] = status
                record[f"{dataset}_is_locked"] = locked

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid


def _with_inactive_physical_record(
    object_key: tuple[str, str, str, str, str],
    attribute_name: str | None = None,
) -> PhysicalModelCatalog:
    """Existing owned keys remain; only execution/authoring eligibility changes."""
    scope = complete_physical_scope()
    normalized_object = tuple(value.casefold() for value in object_key)
    fields = (
        "model_input_objects",
        "dimensional_source_objects",
        "logical_mapping_target_objects",
        "dimensional_mapping_target_objects",
        "model_input_attributes",
        "dimensional_source_attributes",
        "logical_mapping_target_attributes",
        "dimensional_mapping_target_attributes",
    )
    filtered = {}
    for field in fields:
        values = getattr(scope, field)
        if attribute_name is None:
            filtered[field] = frozenset(
                key for key in values if key[:5] != normalized_object
            )
        elif field.endswith("_attributes"):
            filtered[field] = values - {(*normalized_object, attribute_name.casefold())}
    return replace(scope, **filtered)


@pytest.mark.parametrize(
    "physical_object", [SOURCE_ORDERS, SILVER_ORDER, GOLD_SALES_FACT]
)
@pytest.mark.parametrize("attribute_only", [False, True])
def test_retained_model_history_survives_physical_deactivation(
    physical_object: tuple[str, str, str, str, str],
    attribute_only: bool,
) -> None:
    graph = complete_model_graph()
    attribute = {
        SOURCE_ORDERS: "order_id",
        SILVER_ORDER: "OrderID",
        GOLD_SALES_FACT: "SalesKey",
    }[physical_object]
    scope = _with_inactive_physical_record(
        physical_object, attribute if attribute_only else None
    )
    snapshot = snapshot_from_graph(graph)
    changed_model = {
        **graph["model_details"][0],
        "model_description": "Updated Model purpose.",
    }

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"model_details": [changed_model]},
        physical_scope=scope,
    )

    assert result.valid
    assert result.phase == "complete"
    assert set(result.records) == {"model_details"}


@pytest.mark.parametrize(
    "dataset", ["model_input_scope", "analysis_result", "logical_attribute"]
)
def test_lifecycle_review_preserves_inactive_physical_history(
    dataset: ModelChangeSetDataset,
) -> None:
    graph = complete_model_graph()
    changed = deepcopy(graph[dataset][0])
    if dataset == "model_input_scope":
        changed["model_input_scope_is_locked"] = True
        changed["is_active"] = False
    elif dataset == "analysis_result":
        changed["analysis_result_status"] = "inactive"
    else:
        sources = changed["sources"]
        assert isinstance(sources, list)
        sources[0]["status"] = "inactive"
        sources[0]["is_locked"] = True

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=_with_inactive_physical_record(SOURCE_ORDERS),
    )

    assert result.valid


@pytest.mark.parametrize(
    "change", ["definition", "new_inactive", "reactivate", "new_nested_source"]
)
def test_authoring_cannot_claim_retained_physical_history(change: str) -> None:
    graph = _model_layer_graph("conceptual")
    existing = graph["conceptual_object"][0]
    if change == "reactivate":
        existing["conceptual_object_status"] = "inactive"
        for relationship in graph["conceptual_relationship"]:
            relationship["conceptual_relationship_status"] = "inactive"
    changed = deepcopy(existing)
    if change == "definition":
        changed["conceptual_object_definition"] = "A newly authored definition."
    elif change == "new_inactive":
        changed["conceptual_object_name"] = "Another order concept"
        changed["conceptual_object_status"] = "inactive"
    elif change == "reactivate":
        changed["conceptual_object_status"] = "active"
    else:
        supports = changed["supports"]
        assert isinstance(supports, list)
        additional = deepcopy(graph["conceptual_object"][1]["supports"][0])
        additional["support_status"] = "inactive"
        supports.append(additional)

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"conceptual_object": [changed]},
        physical_scope=_with_inactive_physical_record(SOURCE_ORDERS),
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(issue.dataset == "conceptual_object" for issue in result.issues)


def test_new_inactive_scope_cannot_claim_existing_physical_history() -> None:
    graph = complete_model_graph()
    new_scope = graph["model_input_scope"].pop(0)
    new_scope["is_active"] = False
    # The existing graph's history is not evidence for a new Scope record.
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"model_input_scope": [new_scope]},
        physical_scope=_with_inactive_physical_record(SOURCE_ORDERS),
    )

    assert result.valid is False
    assert any(issue.dataset == "model_input_scope" for issue in result.issues)


@pytest.mark.parametrize("missing", ["object", "attribute"])
def test_retained_history_still_requires_owned_existing_physical_records(
    missing: str,
) -> None:
    graph = complete_model_graph()
    scope = _with_inactive_physical_record(SOURCE_ORDERS)
    key = tuple(value.casefold() for value in SOURCE_ORDERS)
    if missing == "object":
        scope = replace(scope, objects=scope.objects - {key})
    else:
        scope = replace(scope, attributes=scope.attributes - {(*key, "order_id")})

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={},
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"


@pytest.mark.parametrize("change", ["physical_attribute", "physical_object"])
def test_new_dimensional_sources_cannot_inherit_inactive_silver_mapping(
    change: str,
) -> None:
    graph = complete_model_graph()
    dataset: ModelChangeSetDataset = (
        "dimensional_attribute"
        if change == "physical_attribute"
        else "dimensional_entity"
    )
    source: dict[str, object] = {
        "source_order": 1,
        "rationale": "Applied Logical mapping contribution.",
        "status": "active",
        "is_locked": False,
    }
    if change == "physical_attribute":
        source.update(
            {
                "support_source_type": "attribute",
                "source_attribute": physical_attribute(SILVER_ORDER, "OrderID"),
            }
        )
    else:
        source.update(
            {
                "support_source_type": "object",
                "source_role": "transaction",
                "source_object": physical_object(SILVER_ORDER),
            }
        )
    graph[dataset][0]["sources"] = [source]
    assert validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    ).valid
    changed = deepcopy(graph[dataset][0])
    changed[f"{dataset}_definition"] = (
        "New dimensional definition from retained Silver evidence."
    )

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=_with_inactive_physical_record(
            SILVER_ORDER,
            "OrderID" if change == "physical_attribute" else None,
        ),
    )

    assert result.valid is False
    assert any(issue.dataset == dataset for issue in result.issues)


def test_attribute_binding_history_cannot_follow_a_rebound_parent() -> None:
    graph = complete_model_graph()
    scope = complete_physical_scope()
    rebound = {**graph["model_object_binding"][0], "object_name": "MovedOrder"}
    target = (*tuple(value.casefold() for value in SILVER_ORDER[:4]), "movedorder")
    inactive_attribute = (*target, "orderid")
    active_attribute = (*target, "customerid")
    scope = replace(
        scope,
        objects=scope.objects | {target},
        attributes=scope.attributes | {inactive_attribute, active_attribute},
        logical_mapping_target_objects=scope.logical_mapping_target_objects | {target},
        logical_mapping_target_attributes=(
            scope.logical_mapping_target_attributes | {active_attribute}
        ),
    )

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"model_object_binding": [rebound]},
        physical_scope=scope,
    )

    assert result.valid is False
    assert any(
        issue.code == "model_input_reference_invalid"
        and issue.dataset == "model_attribute_binding"
        for issue in result.issues
    )


@pytest.mark.parametrize(
    ("dataset", "field", "value"),
    [
        ("mapping_object", "mapping_transformation_document", {"is_active": False}),
        (
            "mapping_attribute",
            "attribute_mapping_transformation_document",
            {"status": "inactive"},
        ),
        ("generated_code", "generated_code_content", "SELECT 2"),
    ],
)
def test_new_authored_content_cannot_inherit_inactive_bound_targets(
    dataset: ModelChangeSetDataset,
    field: str,
    value: object,
) -> None:
    graph = complete_model_graph()
    changed = {**graph[dataset][0], field: value}

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=_with_inactive_physical_record(SILVER_ORDER),
    )

    assert result.valid is False
    assert result.phase == "model_input_scope"
    assert any(issue.dataset == dataset for issue in result.issues)


def test_new_inactive_authored_records_can_reference_current_physical_targets() -> None:
    graph = complete_model_graph()
    for dataset in ("validation_group", "validation_check"):
        for record in graph[dataset]:
            record["is_active"] = False
    for dataset, status_field in (
        ("model_object_binding", "model_object_binding_status"),
        ("model_attribute_binding", "model_attribute_binding_status"),
        ("mapping_object", "object_mapping_status"),
        ("mapping_attribute", "attribute_mapping_status"),
        ("generated_code", "generated_code_status"),
        ("generated_code_source_system", "generated_code_source_system_status"),
    ):
        for record in graph[dataset]:
            record[status_field] = "inactive"

    result = validate_future_graph(
        snapshot=empty_model_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid


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
        "generated_code_is_locked",
    }
    forbidden = {
        "tenant_code",
        "object_name",
        "mapping_context_digest",
        "source_context_digest",
        "generated_code_digest",
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


def test_adding_mapping_system_keeps_prior_code_as_stale_until_regenerated() -> None:
    graph = complete_model_graph()
    snapshot = snapshot_from_graph(graph)
    scope = replace(
        complete_physical_scope(), active_system_codes=frozenset({"erp", "crm"})
    )
    new_mapping = {
        dataset: [{**record, "source_system_code": "CRM"} for record in graph[dataset]]
        for dataset in ("mapping_dependency", "mapping_object", "mapping_attribute")
    }
    checked = validate_future_graph(
        snapshot=snapshot,
        staged_documents=new_mapping,
        physical_scope=scope,
    )
    assert checked.valid
    applied = deepcopy(graph)
    for dataset, records in new_mapping.items():
        applied[dataset].extend(records)
    assert validate_future_graph(
        snapshot=snapshot_from_graph(applied),
        staged_documents={},
        physical_scope=scope,
    ).valid
    # Authoring Code still requires complete, unique System coverage.
    checked_code = validate_future_graph(
        snapshot=snapshot,
        staged_documents={**new_mapping, "generated_code": graph["generated_code"]},
        physical_scope=scope,
    )
    assert any(
        issue.dataset == "generated_code_source_system" for issue in checked_code.issues
    )
