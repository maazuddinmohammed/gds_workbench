from __future__ import annotations

from copy import deepcopy

import pytest

from gds_etl_workbench.application.change_sets.model_validation import (
    validate_future_graph,
)
from gds_etl_workbench.domain.modeling_records import has_mapping_transformation_content
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    complete_physical_scope,
    empty_model_snapshot,
    snapshot_from_graph,
)

MAPPING_FIELDS: tuple[tuple[ModelChangeSetDataset, str, str], ...] = (
    ("mapping_object", "mapping_transformation_document", "object_mapping_status"),
    (
        "mapping_attribute",
        "attribute_mapping_transformation_document",
        "attribute_mapping_status",
    ),
)
EMPTY_DOCUMENTS: list[dict[str, object]] = [
    {},
    {"steps": [], "source_objects": []},
    {"nested": [None, {}, [], " \t\n"]},
]


@pytest.mark.parametrize(("dataset", "field", "status"), MAPPING_FIELDS)
@pytest.mark.parametrize("document", EMPTY_DOCUMENTS)
def test_new_or_changed_empty_mapping_requires_explicit_null(
    dataset: ModelChangeSetDataset, field: str, status: str, document: dict[str, object]
) -> None:
    graph = complete_model_graph()
    changed = deepcopy(graph[dataset][0])
    changed[field] = document
    for existing in (True, False):
        snapshot = snapshot_from_graph(graph) if existing else empty_model_snapshot()
        staged: dict[ModelChangeSetDataset, list[dict[str, object]]] = (
            {dataset: [changed]}
            if existing
            else {**graph, dataset: [changed, *graph[dataset][1:]]}
        )
        result = validate_future_graph(
            snapshot=snapshot,
            staged_documents=staged,
            physical_scope=complete_physical_scope(),
        )
        assert not result.valid
        assert any(
            issue.code == "mapping_document_empty" and issue.fields == (field,)
            for issue in result.issues
        )
        assert getattr(result.records[dataset][0], field) == document
    changed[status] = "inactive"
    graph[dataset][0] = deepcopy(changed)
    changed[status] = "active"
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=complete_physical_scope(),
    )
    assert any(issue.code == "mapping_document_empty" for issue in result.issues)


def test_unchanged_historical_empty_documents_keep_code_authoring_compatibility() -> (
    None
):
    graph = complete_model_graph()
    for dataset, field, _ in MAPPING_FIELDS:
        for record in graph[dataset]:
            record[field] = {"old_empty_template": [None, {}]}
    unchanged = deepcopy(graph)
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents=graph,
        physical_scope=complete_physical_scope(),
    )
    assert result.valid
    assert graph == unchanged
    assert all(summary.update_count == 0 for summary in result.action_review)


@pytest.mark.parametrize(
    "value", [False, 0, "\ufeff", {"nested": [False]}, {"nested": [0]}]
)
def test_false_zero_and_non_whitespace_content_are_not_missing(value: object) -> None:
    assert has_mapping_transformation_content(value)


@pytest.mark.parametrize("value", [None, "\u001c\u0085", *EMPTY_DOCUMENTS])
def test_recursive_empty_content_is_missing(value: object) -> None:
    assert not has_mapping_transformation_content(value)


@pytest.mark.parametrize(("dataset", "field", "status"), MAPPING_FIELDS)
@pytest.mark.parametrize("value", [False, 0])
def test_active_custom_mapping_can_keep_false_or_zero_rules(
    dataset: ModelChangeSetDataset, field: str, status: str, value: bool | int
) -> None:
    graph = complete_model_graph()
    changed = deepcopy(graph[dataset][0])
    changed[field] = {"custom_rule": value}
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=complete_physical_scope(),
    )
    assert result.valid
    assert getattr(result.records[dataset][0], field) == {"custom_rule": value}
    assert getattr(result.records[dataset][0], status) == "active"
