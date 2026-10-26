from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Literal

import pytest
from pydantic import ValidationError

from gds_etl_workbench.application.change_sets.project import (
    StageProjectChange,
    project_validation_outcome,
    validate_project_change_set_document_bounds,
    validate_project_stage_changes,
)
from gds_etl_workbench.application.change_sets.project_validation import (
    CodeGenerationTargetContext,
    ProjectValidationIssue,
    PhysicalProjectCatalog,
    ValidatedProjectChangeSet,
    validate_future_graph,
    validate_staged_records,
    validation_code_context_digest,
    validation_mapping_context_digest,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.project import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    ProjectChangeSetDataset,
    ProjectSnapshot,
    build_project_dataset_schema,
)
from tests.mcp.project_test_fixtures import (
    GOLD_SALES_FACT,
    SILVER_ORDER,
    SOURCE_ORDERS,
    complete_project_graph,
    complete_physical_scope,
    empty_project_snapshot,
    project_details,
    snapshot_from_graph,
)


def test_complete_22_dataset_project_graph_validates() -> None:
    graph = complete_project_graph(include_enrichment=True)

    result = validate_future_graph(
        snapshot=snapshot_from_graph(
            {"project_input_scope": graph["project_input_scope"]}
        ),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is True
    assert result.phase == "complete"
    assert result.issues == ()
    assert set(result.records) == set(CHANGE_SET_DATASETS_BY_NAME)
    assert len(result.action_review) == 22
    assert all(
        summary.insert_count + summary.no_change_count > 0
        for summary in result.action_review
    )
    assert result.candidate_digest is not None
    assert len(result.candidate_digest) == 64


@pytest.mark.parametrize("legacy_layers", [[], ["analysis"]])
def test_context_rejects_removed_layer_flags(
    legacy_layers: list[str],
) -> None:
    graph = complete_project_graph()
    for record in graph["context_record"]:
        record["modeling_assertion_applicable_layers"] = legacy_layers
    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid
    assert result.issues[0].fields == ("modeling_assertion_applicable_layers",)


def test_schema_failure_reports_a_bounded_repair_path() -> None:
    record = deepcopy(complete_project_graph()["logical_attribute"][0])
    del record["logical_attribute_definition"]

    records, issues = validate_staged_records("logical_attribute", [record])

    assert records == ()
    assert issues[0].code == "record_schema_invalid"
    assert issues[0].record_number == 1
    assert issues[0].fields == ("logical_attribute_definition",)
    assert "Field required" in issues[0].message


def test_project_validation_outcome_groups_errors_and_bounds_agent_examples() -> None:
    validation = ValidatedProjectChangeSet(
        records={},
        phase="references",
        candidate_digest="a" * 64,
        issues=tuple(
            ProjectValidationIssue(
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

    outcome = project_validation_outcome(validation)

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
    first = complete_project_graph()["subject_area"][0]
    duplicate = {**first, "subject_area_name": " sales "}

    records, issues = validate_staged_records(
        "subject_area",
        [first, duplicate],
    )

    assert len(records) == 1
    assert issues[0].code == "duplicate_canonical_key"


def test_project_input_scope_accepts_only_eligible_source_or_bronze_objects() -> None:
    graph = complete_project_graph()
    scope = replace(complete_physical_scope(), project_input_objects=frozenset())

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents={"project_input_scope": graph["project_input_scope"]},
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.phase == "project_input_scope"
    assert {issue.dataset for issue in result.issues} == {"project_input_scope"}


@pytest.mark.parametrize(
    "dataset",
    ["profiling_profile", "analysis_result", "subject_area_table", "logical_entity"],
)
def test_source_work_uses_active_project_input_scope(
    dataset: ProjectChangeSetDataset,
) -> None:
    graph = complete_project_graph()
    graph["project_input_scope"] = []

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents={
            "project_details": graph["project_details"],
            "project_input_scope": graph["project_input_scope"],
            dataset: graph[dataset],
        },
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "project_input_scope"
    assert any(issue.dataset == dataset for issue in result.issues)


def _project_layer_graph(
    layer: Literal["subject_area", "logical", "dimensional"],
) -> dict[ProjectChangeSetDataset, list[dict[str, object]]]:
    return {
        dataset: records
        for dataset, records in complete_project_graph().items()
        if dataset == layer
        or dataset.startswith(f"{layer}_")
        or dataset
        in {
            "project_details",
            "project_input_scope",
            "context_group",
            "context_record",
        }
    }


@pytest.mark.parametrize("action", ["deactivate_parent", "reactivate_child"])
def test_active_subject_area_table_requires_an_active_area(action: str) -> None:
    graph = _project_layer_graph("subject_area")
    area = graph["subject_area"][0]
    membership = graph["subject_area_table"][0]
    # Canonical references are case/space insensitive, including lifecycle checks.
    membership["subject_area_name"] = f" {str(area['subject_area_name']).upper()} "
    if action == "reactivate_child":
        area["subject_area_is_active"] = False
        for record in graph["subject_area_table"]:
            record["subject_area_table_is_active"] = False
    snapshot = snapshot_from_graph(graph)
    baseline = validate_future_graph(
        snapshot=snapshot,
        staged_documents={},
        physical_scope=complete_physical_scope(),
    )
    assert baseline.valid
    changes: dict[ProjectChangeSetDataset, list[dict[str, object]]] = (
        {"subject_area": [{**area, "subject_area_is_active": False}]}
        if action == "deactivate_parent"
        else {"subject_area_table": [{**membership, "subject_area_table_is_active": True}]}
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
        and issue.dataset == "subject_area_table"
        and issue.fields == ("subject_area_name",)
        for issue in result.issues
    )


def test_subject_area_table_requires_a_saved_or_staged_area() -> None:
    graph = _project_layer_graph("subject_area")
    orphan = {**graph["subject_area_table"][0], "subject_area_name": "Unknown"}

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"subject_area_table": [orphan]},
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.dataset == "subject_area_table" and issue.fields == ("subject_area_name",)
        for issue in result.issues
    )


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize("action", ["deactivate_parent", "reactivate_child"])
def test_active_modeled_attribute_requires_active_parent_entity(
    layer: Literal["logical", "dimensional"],
    action: str,
) -> None:
    graph = _project_layer_graph(layer)
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
        parent[f"{layer}_entity_is_active"] = False
        for child in children:
            child[f"{layer}_attribute_is_active"] = False
    snapshot = snapshot_from_graph(graph)
    baseline = validate_future_graph(
        snapshot=snapshot,
        staged_documents={},
        physical_scope=complete_physical_scope(),
    )
    assert baseline.valid
    if action == "deactivate_parent":
        changes = {entity_dataset: [{**parent, f"{layer}_entity_is_active": False}]}
    else:
        changes = {
            attribute_dataset: [{**children[0], f"{layer}_attribute_is_active": True}]
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
    graph = _project_layer_graph(layer)
    relationship_dataset = (
        "logical_relationship" if layer == "logical" else "dimensional_relationship"
    )
    relationship = graph[relationship_dataset][0]
    entity_name = str(relationship[f"{side}_{layer}_entity_name"])
    attribute_name = str(relationship[f"{side}_{layer}_attribute_name"])
    relationship[f"{side}_{layer}_entity_name"] = f" {entity_name.upper()} "
    relationship[f"{side}_{layer}_attribute_name"] = f" {attribute_name.upper()} "
    dataset: ProjectChangeSetDataset = (
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
        endpoint[f"{layer}_{inactive_record}_is_active"] = False
        relationship[f"{layer}_relationship_is_active"] = False
        if inactive_record == "entity":
            attribute_dataset = (
                "logical_attribute" if layer == "logical" else "dimensional_attribute"
            )
            for attribute in graph[attribute_dataset]:
                if attribute[f"{layer}_entity_name"] == entity_name:
                    attribute[f"{layer}_attribute_is_active"] = False
    snapshot = snapshot_from_graph(graph)
    baseline = validate_future_graph(
        snapshot=snapshot,
        staged_documents={},
        physical_scope=complete_physical_scope(),
    )
    assert baseline.valid
    changes: dict[ProjectChangeSetDataset, list[dict[str, object]]] = (
        {dataset: [{**endpoint, f"{layer}_{inactive_record}_is_active": False}]}
        if action == "deactivate_endpoint"
        else {
            relationship_dataset: [
                {**relationship, f"{layer}_relationship_is_active": True}
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


def _retire_type_codes(snapshot: ProjectSnapshot, *codes: str) -> ProjectSnapshot:
    """Retire label codes the way the reference lists do: the rows stay, inactive."""
    logical = snapshot.logical.model_copy(
        update={
            "entity_types": tuple(
                row.model_copy(
                    update={
                        "logical_entity_type_is_active": row.logical_entity_type_code not in codes
                    }
                )
                for row in snapshot.logical.entity_types
            )
        }
    )
    dimensional = snapshot.dimensional.model_copy(
        update={
            "fact_types": tuple(
                row.model_copy(
                    update={
                        "dimensional_fact_type_is_active": row.dimensional_fact_type_code
                        not in codes
                    }
                )
                for row in snapshot.dimensional.fact_types
            )
        }
    )
    return snapshot.model_copy(update={"logical": logical, "dimensional": dimensional})


@pytest.mark.parametrize(
    ("dataset", "field", "code"),
    [
        ("logical_entity", "logical_entity_type", "snapshot"),
        ("logical_entity", "logical_entity_type", "bridge"),
        ("dimensional_entity", "dimensional_fact_type", "factless"),
        ("dimensional_entity", "dimensional_fact_type", "aggregate"),
    ],
)
def test_new_records_need_an_active_reference_type_code(
    dataset: ProjectChangeSetDataset, field: str, code: str
) -> None:
    graph = complete_project_graph()
    graph[dataset][0][field] = code

    result = validate_future_graph(
        snapshot=_retire_type_codes(empty_project_snapshot(), "snapshot", "factless"),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "references"
    assert [(issue.code, issue.dataset, issue.fields) for issue in result.issues] == [
        ("reference_code_invalid", dataset, (field,))
    ]


def test_unchanged_applied_records_keep_a_retired_type_code() -> None:
    graph = complete_project_graph()
    graph["logical_entity"][0]["logical_entity_type"] = "snapshot"
    graph["dimensional_entity"][0]["dimensional_fact_type"] = "factless"
    snapshot = _retire_type_codes(snapshot_from_graph(graph), "snapshot", "factless")
    order = graph["logical_entity"][0]
    fact = graph["dimensional_entity"][0]

    def check(
        changes: dict[ProjectChangeSetDataset, list[dict[str, object]]],
    ) -> ValidatedProjectChangeSet:
        return validate_future_graph(
            snapshot=snapshot,
            staged_documents=changes,
            physical_scope=complete_physical_scope(),
        )

    assert check({}).valid
    assert check({"logical_entity": [{**order, "logical_entity_is_locked": True}]}).valid
    edited = check(
        {
            "logical_entity": [{**order, "logical_entity_definition": "Edited Order."}],
            "dimensional_entity": [{**fact, "dimensional_entity_definition": "Edited fact."}],
        }
    )
    assert [(issue.code, issue.fields) for issue in edited.issues] == [
        ("reference_code_invalid", ("logical_entity_type",)),
        ("reference_code_invalid", ("dimensional_fact_type",)),
    ]
    assert check({"logical_entity": [{**order, "logical_entity_type": "transaction"}]}).valid


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
def test_relationship_identity_is_its_foreign_key_attribute(
    layer: Literal["logical", "dimensional"],
) -> None:
    graph = complete_project_graph()
    dataset: ProjectChangeSetDataset = (
        "logical_relationship" if layer == "logical" else "dimensional_relationship"
    )
    relationship = graph[dataset][0]
    foreign_key = str(relationship[f"from_{layer}_attribute_name"])
    own_key = "OrderID" if layer == "logical" else "SalesKey"
    # The same foreign-key Attribute, however it is spelled, cannot name a second parent.
    second_parent = {
        **relationship,
        f"from_{layer}_attribute_name": f" {foreign_key.upper()} ",
        f"to_{layer}_entity_name": relationship[f"from_{layer}_entity_name"],
        f"to_{layer}_attribute_name": own_key,
    }

    records, issues = validate_staged_records(dataset, [relationship, second_parent])

    assert len(records) == 1
    assert [(issue.code, issue.record_number) for issue in issues] == [
        ("duplicate_canonical_key", 2)
    ]
    repointed = {**second_parent, f"from_{layer}_attribute_name": foreign_key}
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [repointed]},
        physical_scope=complete_physical_scope(),
    )
    assert result.valid, result.issues
    assert (result.action_review[0].insert_count, result.action_review[0].update_count) == (0, 1)


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize("parent", ["missing", "not_key", "inactive_not_key"])
def test_relationship_points_at_an_existing_parent_key(
    layer: Literal["logical", "dimensional"],
    parent: str,
) -> None:
    graph = complete_project_graph()
    attribute_dataset: ProjectChangeSetDataset = (
        "logical_attribute" if layer == "logical" else "dimensional_attribute"
    )
    relationship_dataset: ProjectChangeSetDataset = (
        "logical_relationship" if layer == "logical" else "dimensional_relationship"
    )
    relationship = graph[relationship_dataset][0]
    key = next(
        record
        for record in graph[attribute_dataset]
        if record[f"{layer}_entity_name"] == relationship[f"to_{layer}_entity_name"]
    )
    graph[attribute_dataset].append(
        {
            **key,
            f"{layer}_attribute_name": "CustomerName",
            f"{layer}_attribute_data_type": "string",
            f"{layer}_attribute_ordinal_position": 2,
            f"{layer}_attribute_is_natural_key": False,
            f"{layer}_attribute_is_surrogate_key": False,
        }
    )
    relationship[f"to_{layer}_attribute_name"] = (
        "Missing" if parent == "missing" else "CustomerName"
    )
    relationship[f"{layer}_relationship_is_active"] = parent != "inactive_not_key"

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    issues = {(issue.code, issue.dataset, issue.fields) for issue in result.issues}
    if parent == "missing":
        assert ("reference_not_found", relationship_dataset, (f"{layer}_attribute_name",)) in issues
    elif parent == "not_key":
        assert issues == {
            (
                "relationship_target_not_key",
                relationship_dataset,
                (f"to_{layer}_attribute_name",),
            )
        }
    else:
        assert result.valid, result.issues


@pytest.mark.parametrize("layer", ["subject_area", "logical", "dimensional"])
@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize("active", [True, False])
def test_project_layer_activity_is_independent_of_locks(
    layer: Literal["subject_area", "logical", "dimensional"],
    locked: bool,
    active: bool,
) -> None:
    graph = _project_layer_graph(layer)
    for dataset, records in graph.items():
        if dataset == layer or dataset.startswith(f"{layer}_"):
            for record in records:
                record[f"{dataset}_is_active"] = active
                record[f"{dataset}_is_locked"] = locked

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid


def _with_inactive_physical_record(
    object_key: tuple[str, str, str, str, str],
    attribute_name: str | None = None,
) -> PhysicalProjectCatalog:
    """Existing owned keys remain; only execution/authoring eligibility changes."""
    scope = complete_physical_scope()
    normalized_object = tuple(value.casefold() for value in object_key)
    fields = (
        "project_input_objects",
        "project_input_attributes",
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
def test_retained_project_history_survives_physical_deactivation(
    physical_object: tuple[str, str, str, str, str],
    attribute_only: bool,
) -> None:
    graph = complete_project_graph()
    attribute = {
        SOURCE_ORDERS: "order_id",
        SILVER_ORDER: "OrderID",
        GOLD_SALES_FACT: "SalesKey",
    }[physical_object]
    scope = _with_inactive_physical_record(
        physical_object, attribute if attribute_only else None
    )
    snapshot = snapshot_from_graph(graph)
    changed_project = {
        **graph["project_details"][0],
        "project_description": "Updated Project purpose.",
    }

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"project_details": [changed_project]},
        physical_scope=scope,
    )

    assert result.valid
    assert result.phase == "complete"
    assert set(result.records) == {"project_details"}


@pytest.mark.parametrize(
    "dataset", ["project_input_scope", "analysis_result", "logical_attribute"]
)
def test_lifecycle_review_preserves_inactive_physical_history(
    dataset: ProjectChangeSetDataset,
) -> None:
    graph = complete_project_graph()
    changed = deepcopy(graph[dataset][0])
    if dataset == "project_input_scope":
        changed["project_input_scope_is_locked"] = True
        changed["is_active"] = False
    elif dataset == "analysis_result":
        changed["analysis_result_status"] = "inactive"
    else:
        sources = changed["sources"]
        assert isinstance(sources, list)
        sources[0]["is_active"] = False
        sources[0]["is_locked"] = True

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=_with_inactive_physical_record(SOURCE_ORDERS),
    )

    assert result.valid


@pytest.mark.parametrize("change", ["new_area", "new_inactive", "reactivate"])
def test_authoring_cannot_claim_retained_physical_history(change: str) -> None:
    graph = _project_layer_graph("subject_area")
    existing = next(
        record
        for record in graph["subject_area_table"]
        if record["object_name"] == SOURCE_ORDERS[4]
    )
    if change == "reactivate":
        existing["subject_area_table_is_active"] = False
    changes: dict[ProjectChangeSetDataset, list[dict[str, object]]]
    if change == "reactivate":
        changes = {"subject_area_table": [{**existing, "subject_area_table_is_active": True}]}
    else:
        # The same retained table placed in another area is new authored evidence.
        area = {**graph["subject_area"][0], "subject_area_name": "Billing"}
        membership = {**existing, "subject_area_name": "Billing"}
        if change == "new_inactive":
            membership["subject_area_table_is_active"] = False
        changes = {"subject_area": [area], "subject_area_table": [membership]}

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents=changes,
        physical_scope=_with_inactive_physical_record(SOURCE_ORDERS),
    )

    assert result.valid is False
    assert result.phase == "project_input_scope"
    assert any(issue.dataset == "subject_area_table" for issue in result.issues)


def test_new_inactive_scope_cannot_claim_existing_physical_history() -> None:
    graph = complete_project_graph()
    new_scope = graph["project_input_scope"].pop(0)
    new_scope["is_active"] = False
    # The existing graph's history is not evidence for a new Scope record.
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"project_input_scope": [new_scope]},
        physical_scope=_with_inactive_physical_record(SOURCE_ORDERS),
    )

    assert result.valid is False
    assert any(issue.dataset == "project_input_scope" for issue in result.issues)


@pytest.mark.parametrize("missing", ["object", "attribute"])
def test_retained_history_still_requires_owned_existing_physical_records(
    missing: str,
) -> None:
    graph = complete_project_graph()
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
    assert result.phase == "project_input_scope"


@pytest.mark.parametrize("source_type", ["logical_entity", "logical_attribute"])
def test_dimensional_design_uses_active_logical_sources_without_registration(
    source_type: str,
) -> None:
    graph = complete_project_graph()
    dataset = (
        "dimensional_entity"
        if source_type == "logical_entity"
        else "dimensional_attribute"
    )
    logical_key = {
        "logical_entity_schema_name": "silver",
        "logical_entity_name": "Order",
    }
    source = {
        "support_source_type": source_type,
        "rationale": "Applied Logical source.",
        "is_active": True,
        "is_locked": False,
    }
    if source_type == "logical_entity":
        source.update(source_logical_entity=logical_key)
    else:
        source["source_logical_attribute"] = {
            **logical_key,
            "logical_attribute_name": "OrderID",
        }
        graph["dimensional_entity"][0]["sources"] = [
            {
                "support_source_type": "logical_entity",
                "source_logical_entity": logical_key,
                "rationale": None,
                "is_active": True,
                "is_locked": False,
            }
        ]
    graph[dataset][0]["sources"] = [source]
    assert validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    ).valid
    graph["logical_entity"][0]["logical_entity_is_active"] = False
    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid


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
def test_authored_content_is_independent_of_physical_target_registration(
    dataset: ProjectChangeSetDataset,
    field: str,
    value: object,
) -> None:
    graph = complete_project_graph()
    changed = {**graph[dataset][0], field: value}

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=_with_inactive_physical_record(SILVER_ORDER),
    )

    assert result.valid


def test_new_inactive_authored_records_can_reference_current_entities() -> None:
    graph = complete_project_graph()
    for dataset in ("validation_group", "validation_check"):
        for record in graph[dataset]:
            record["is_active"] = False
    for dataset, status_field in (
        ("mapping_object", "object_mapping_status"),
        ("mapping_attribute", "attribute_mapping_status"),
        ("generated_code", "generated_code_status"),
        ("generated_code_source_system", "generated_code_source_system_status"),
    ):
        for record in graph[dataset]:
            record[status_field] = "inactive"

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid


@pytest.mark.parametrize(
    "partial", ["object_only", "attribute_only", "blank_attribute"]
)
def test_code_authoring_accepts_available_mapping_transformations(partial: str) -> None:
    graph = complete_project_graph()
    if partial == "object_only":
        graph["mapping_attribute"] = []
    elif partial == "attribute_only":
        graph["mapping_object"][0]["mapping_transformation_document"] = None
        graph["mapping_attribute"] = graph["mapping_attribute"][:1]
    else:
        graph["mapping_attribute"][0]["attribute_mapping_transformation_document"] = (
            None
        )

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid


def test_cleared_saved_pair_does_not_require_a_new_code_assignment() -> None:
    graph = complete_project_graph()
    empty_mapping = {
        **graph["mapping_object"][0],
        "source_system_code": "GDS",
        "mapping_transformation_document": None,
    }
    graph["mapping_object"].append(empty_mapping)
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={
            "generated_code": [
                {**graph["generated_code"][0], "generated_code_content": "SELECT 2"}
            ],
        },
        physical_scope=complete_physical_scope(),
    )

    assert result.valid


def test_code_authoring_rejects_an_entity_with_only_cleared_saved_pairs() -> None:
    graph = complete_project_graph()
    graph["mapping_object"][0]["mapping_transformation_document"] = None
    for record in graph["mapping_attribute"]:
        record["attribute_mapping_transformation_document"] = None
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"generated_code": [graph["generated_code"][0]]},
        physical_scope=complete_physical_scope(),
    )

    assert not result.valid
    assert any(issue.dataset == "generated_code" for issue in result.issues)


def test_cleared_pair_still_rejects_duplicate_active_code_assignments() -> None:
    graph = complete_project_graph()
    graph["mapping_object"].append(
        {
            **graph["mapping_object"][0],
            "source_system_code": "GDS",
            "mapping_transformation_document": None,
        }
    )
    for name in ("GdsFirst.sql", "GdsSecond.sql"):
        graph["generated_code"].append(
            {**graph["generated_code"][0], "artifact_name": name}
        )
        graph["generated_code_source_system"].append(
            {
                **graph["generated_code_source_system"][0],
                "artifact_name": name,
                "source_system_code": "GDS",
            }
        )
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"generated_code": [graph["generated_code"][0]]},
        physical_scope=complete_physical_scope(),
    )

    assert not result.valid
    assert any(
        issue.dataset == "generated_code_source_system" for issue in result.issues
    )


@pytest.mark.parametrize(
    "partial", ["object_only", "attribute_only", "blank_attribute"]
)
def test_mapping_can_store_partial_transformations_without_authoring_code(
    partial: str,
) -> None:
    graph = complete_project_graph()
    graph["generated_code"] = []
    graph["generated_code_source_system"] = []
    if partial == "object_only":
        graph["mapping_attribute"] = []
    elif partial == "attribute_only":
        graph["mapping_object"][0]["mapping_transformation_document"] = None
        graph["mapping_attribute"] = graph["mapping_attribute"][:1]
    else:
        graph["mapping_attribute"][0]["attribute_mapping_transformation_document"] = (
            None
        )

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid
    assert [
        record.model_dump(mode="json") for record in result.records["mapping_object"]
    ] == (graph["mapping_object"])
    assert [
        record.model_dump(mode="json") for record in result.records["mapping_attribute"]
    ] == (graph["mapping_attribute"])


@pytest.mark.parametrize("attributes", ["absent", "blank", "inactive"])
def test_active_mapping_pair_needs_at_least_one_transformation(attributes: str) -> None:
    graph = complete_project_graph()
    graph["generated_code"] = []
    graph["generated_code_source_system"] = []
    graph["mapping_object"][0]["mapping_transformation_document"] = None
    if attributes == "absent":
        graph["mapping_attribute"] = []
    else:
        for record in graph["mapping_attribute"]:
            if attributes == "blank":
                record["attribute_mapping_transformation_document"] = None
            else:
                record["attribute_mapping_status"] = "inactive"

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert not result.valid
    assert any(
        issue.dataset == "mapping_object" and issue.code == "active_dependency_invalid"
        for issue in result.issues
    )


@pytest.mark.parametrize("dataset", ["mapping_object", "mapping_attribute"])
def test_partial_mapping_cannot_blank_locked_transformations(
    dataset: ProjectChangeSetDataset,
) -> None:
    graph = complete_project_graph()
    lock_field = (
        "object_mapping_is_locked"
        if dataset == "mapping_object"
        else "attribute_mapping_is_locked"
    )
    document_field = (
        "mapping_transformation_document"
        if dataset == "mapping_object"
        else "attribute_mapping_transformation_document"
    )
    graph[dataset][0][lock_field] = True
    changed = deepcopy(graph[dataset][0])
    changed[document_field] = None

    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=complete_physical_scope(),
    )

    assert not result.valid
    assert result.phase == "locks"
    assert any(issue.code == "record_locked" for issue in result.issues)


def test_existing_mapping_can_clear_all_unlocked_transformations_without_losing_identity() -> (
    None
):
    graph = complete_project_graph()
    changed_object = {
        **graph["mapping_object"][0],
        "mapping_transformation_document": None,
    }
    changed_attributes = [
        {**record, "attribute_mapping_transformation_document": None}
        for record in graph["mapping_attribute"]
    ]
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={
            "mapping_object": [changed_object],
            "mapping_attribute": changed_attributes,
        },
        physical_scope=complete_physical_scope(),
    )

    assert result.valid
    assert len(result.records["mapping_object"]) == 1
    assert len(result.records["mapping_attribute"]) == len(changed_attributes)
    assert all(summary.insert_count == 0 for summary in result.action_review)
    assert sum(summary.update_count for summary in result.action_review) == 1 + len(
        changed_attributes
    )


@pytest.mark.parametrize("assignment_count", [0, 2])
def test_each_mapped_system_is_assigned_to_exactly_one_active_code_artifact(
    assignment_count: int,
) -> None:
    graph = complete_project_graph()
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
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(
        issue.code == "active_dependency_invalid"
        and issue.dataset == "generated_code_source_system"
        for issue in result.issues
    )


def test_generated_code_uses_schema_entity_identity_and_artifact_name_only() -> None:
    schema = build_project_dataset_schema(DATASETS_BY_NAME["generated_code"])

    assert set(schema["properties"]) == {
        "modeled_entity_type",
        "modeled_entity_schema_name",
        "modeled_entity_name",
        "artifact_name",
        "artifact_type",
        "code_storage_type",
        "code_repository_url",
        "code_commit_path",
        "code_entry_point",
        "code_parameters",
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
    record = deepcopy(complete_project_graph()["generated_code"][0])
    record["artifact_name"] = "sql/Order.sql"

    records, issues = validate_staged_records("generated_code", [record])

    assert records == ()
    assert issues[0].code == "record_schema_invalid"
    assert issues[0].fields == () or "artifact_name" in issues[0].fields


def test_validation_records_do_not_accept_digests_or_execution_results() -> None:
    group_schema = build_project_dataset_schema(DATASETS_BY_NAME["validation_group"])
    check_schema = build_project_dataset_schema(DATASETS_BY_NAME["validation_check"])

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
    graph = complete_project_graph()
    graph["validation_check"][0]["validation_query_sql"] = (
        "DELETE FROM main.silver.Order"
    )

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert any(issue.code == "validation_query_invalid" for issue in result.issues)


def test_inactive_validation_can_retire_legacy_unsafe_sql() -> None:
    graph = complete_project_graph()
    graph["validation_check"][0]["validation_query_sql"] = "DELETE FROM old_table"
    graph["validation_check"][0]["is_active"] = False

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is True


def test_active_validation_check_requires_active_group() -> None:
    graph = complete_project_graph()
    graph["validation_group"][0]["is_active"] = False

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
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
    graph = complete_project_graph()
    graph["validation_group"][0]["system_code"] = "GDS"
    graph["validation_check"][0]["system_code"] = "GDS"

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
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
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
        modeled_entity_name="Order",
        source_system_codes=frozenset({"ERP"}),
        code_input_digest="a" * 64,
    )
    code = SimpleNamespace(
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("code_storage_type", "table"),
        ("code_repository_url", "any repo"),
        ("code_commit_path", "anything"),
        ("code_entry_point", "run"),
        ("code_parameters", ["--full", {"batch": 42}]),
    ],
)
def test_storage_metadata_changes_validation_code_freshness(
    field: str, value: object
) -> None:
    context = CodeGenerationTargetContext(
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
        modeled_entity_name="Order",
        source_system_codes=frozenset({"ERP"}),
        code_input_digest="a" * 64,
    )
    code = SimpleNamespace(
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
        modeled_entity_name="Order",
        artifact_name="Order.sql",
        artifact_type="sql_file",
        code_storage_type="git",
        generated_code_content=None,
        generated_code_status="active",
    )
    original = validation_code_context_digest((context,), (code,), "erp")
    assert original is not None
    setattr(code, field, value)
    assert validation_code_context_digest((context,), (code,), "erp") != original


def test_locked_applied_record_cannot_change() -> None:
    graph = complete_project_graph()
    graph["subject_area"][0]["subject_area_is_locked"] = True
    snapshot = snapshot_from_graph(graph)
    changed = deepcopy(graph["subject_area"][0])
    changed["subject_area_definition"] = "Changed definition."

    result = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"subject_area": [changed]},
        physical_scope=complete_physical_scope(),
    )

    assert result.valid is False
    assert result.phase == "locks"
    assert result.issues[0].code == "record_locked"


def test_project_name_conflict_is_tenant_scoped() -> None:
    scope = replace(
        complete_physical_scope(), other_project_names=frozenset({"salesproject"})
    )

    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents={"project_details": [project_details()]},
        physical_scope=scope,
    )

    assert result.valid is False
    assert result.issues[0].code == "project_name_conflict"


def test_stage_rejects_raw_prompt_content_without_reflecting_it() -> None:
    record = deepcopy(complete_project_graph()["context_record"][0])
    record["modeling_assertion_details"] = {
        "review": {"raw_prompt": "sensitive prompt value"}
    }

    with pytest.raises(InvalidRequestError) as captured:
        validate_project_stage_changes(
            [StageProjectChange(dataset="context_record", records=[record])]
        )

    assert "Extra inputs are not permitted" in captured.value.message
    assert "sensitive prompt value" not in captured.value.message


def test_context_section_is_bounded_at_four_mib() -> None:
    documents: dict[str, dict[str, list[dict[str, object]]]] = {
        "context": {
            "context_record": [{"context_text": "x" * 262_144} for _ in range(17)]
        }
    }

    with pytest.raises(InvalidRequestError, match="Context section exceeds 4 MiB"):
        validate_project_change_set_document_bounds(documents)


def test_adding_mapping_system_keeps_prior_code_as_stale_until_regenerated() -> None:
    graph = complete_project_graph()
    snapshot = snapshot_from_graph(graph)
    scope = replace(
        complete_physical_scope(), active_system_codes=frozenset({"erp", "crm"})
    )
    new_mapping = {
        dataset: [{**record, "source_system_code": "CRM"} for record in graph[dataset]]
        for dataset in ("mapping_object", "mapping_attribute")
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


def test_mapping_and_code_work_without_orchestration_dependency_dataset() -> None:
    graph = complete_project_graph()
    assert "mapping_dependency" not in graph
    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )
    assert result.valid, [(issue.dataset, issue.code) for issue in result.issues]


@pytest.mark.parametrize("parent_state", ["missing", "inactive"])
def test_dimensional_attribute_requires_matching_active_parent_support(
    parent_state: str,
) -> None:
    graph = complete_project_graph()
    logical_key = {
        "logical_entity_schema_name": "silver",
        "logical_entity_name": "Order",
    }
    graph["dimensional_entity"][0]["sources"] = (
        []
        if parent_state == "missing"
        else [
            {
                "support_source_type": "logical_entity",
                "source_logical_entity": logical_key,
                "rationale": "Parent source.",
                "is_active": False,
                "is_locked": False,
            }
        ]
    )
    graph["dimensional_attribute"][0]["sources"] = [
        {
            "support_source_type": "logical_attribute",
            "source_logical_attribute": {
                **logical_key,
                "logical_attribute_name": "OrderID",
            },
            "rationale": "Attribute source.",
            "is_active": True,
            "is_locked": False,
        }
    ]
    result = validate_future_graph(
        snapshot=empty_project_snapshot(),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid
    assert any(
        issue.dataset == "dimensional_attribute"
        and issue.code in {"reference_not_found", "active_dependency_invalid"}
        for issue in result.issues
    )


def test_project_stage_rejects_removed_mapping_dependency_dataset() -> None:
    with pytest.raises(ValidationError) as error:
        StageProjectChange.model_validate(
            {
                "dataset": "mapping_dependency",
                "records": [
                    {"source_system_code": "ERP", "source_system_dependency_order": 0}
                ],
            }
        )
    assert any(item["loc"] == ("dataset",) for item in error.value.errors())


@pytest.mark.parametrize("name", ["Other", "sales", " Sales "])
def test_project_identity_cannot_be_renamed(name: str) -> None:
    details = {**project_details(), "project_name": "Sales"}
    result = validate_future_graph(
        snapshot=snapshot_from_graph({"project_details": [details]}),
        staged_documents={"project_details": [{**details, "project_name": name}]},
        physical_scope=complete_physical_scope(),
    )
    assert any(issue.code == "project_identity_read_only" for issue in result.issues)


@pytest.mark.parametrize(
    "code,valid", [("ERP", True), (" erp ", True), (None, True), ("UNKNOWN", False)]
)
def test_default_mapping_source_uses_registered_system_code(
    code: str | None, valid: bool
) -> None:
    details = project_details()
    result = validate_future_graph(
        snapshot=snapshot_from_graph({"project_details": [details]}),
        staged_documents={
            "project_details": [{**details, "default_mapping_source_system_code": code}]
        },
        physical_scope=complete_physical_scope(),
    )
    assert result.valid is valid
