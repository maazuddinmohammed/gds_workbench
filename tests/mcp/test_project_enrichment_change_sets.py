"""Project enrichment uses the same draft, locks and scope as other Project evidence."""

import json
from copy import deepcopy

import pytest
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
    validate_staged_records,
)
from gds_etl_workbench.domain.snapshots.project import (
    DATASETS_BY_NAME,
    build_project_dataset_schema,
)
from jsonschema import Draft202012Validator

from tests.mcp.project_test_fixtures import (
    complete_project_graph,
    complete_physical_scope,
    project_details,
    snapshot_from_graph,
)


def test_local_enrichment_and_analysis_validate_in_one_draft() -> None:
    graph = complete_project_graph(include_enrichment=True)
    baseline = {
        "project_details": graph["project_details"],
        "project_input_scope": graph["project_input_scope"],
    }
    pending = {
        name: graph[name]
        for name in ("object_enrichment", "attribute_enrichment", "analysis_result")
    }
    result = validate_future_graph(
        snapshot=snapshot_from_graph(baseline),
        staged_documents=pending,
        physical_scope=complete_physical_scope(),
    )
    assert result.valid
    assert set(result.records) == set(pending)
    assert result.records["attribute_enrichment"][0].is_pii is None


@pytest.mark.parametrize("dataset", ["object_enrichment", "attribute_enrichment"])
def test_enrichment_cannot_toggle_locks_or_modify_locked_records(dataset: str) -> None:
    graph = complete_project_graph(include_enrichment=True)
    for locked in (False, True):
        graph[dataset][0]["is_locked"] = locked
        candidate = deepcopy(graph[dataset][0])
        candidate["is_locked"] = not locked
        result = validate_future_graph(
            snapshot=snapshot_from_graph(graph),
            staged_documents={dataset: [candidate]},
            physical_scope=complete_physical_scope(),
        )
        assert any(issue.code == "enrichment_lock_read_only" for issue in result.issues)
    candidate = deepcopy(graph[dataset][0])
    candidate[f"{dataset.split('_')[0]}_description"] = "Updated meaning."
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [candidate]},
        physical_scope=complete_physical_scope(),
    )
    assert any(issue.code == "record_locked" for issue in result.issues)


def test_locked_object_protects_attribute_enrichment() -> None:
    graph = complete_project_graph(include_enrichment=True)
    graph["object_enrichment"][0]["is_locked"] = True
    candidate = {**graph["attribute_enrichment"][0], "is_pii": True}
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"attribute_enrichment": [candidate]},
        physical_scope=complete_physical_scope(),
    )
    assert any(issue.code == "enrichment_parent_locked" for issue in result.issues)


def test_enrichment_rejects_unselected_source_and_never_changes_physical_metadata() -> (
    None
):
    graph = complete_project_graph(include_enrichment=True)
    baseline = {
        **graph,
        "project_input_scope": [],
        "object_enrichment": [],
        "attribute_enrichment": [],
    }
    result = validate_future_graph(
        snapshot=snapshot_from_graph(baseline),
        staged_documents={"object_enrichment": graph["object_enrichment"]},
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid
    assert {issue.dataset for issue in result.issues} >= {"object_enrichment"}


@pytest.mark.parametrize("text", ["é" * 1001, "unsafe\x00text", "unsafe\x7ftext"])
def test_enrichment_description_bounds(text: str) -> None:
    record = {
        **complete_project_graph(include_enrichment=True)["object_enrichment"][0],
        "object_description": text,
    }
    _, issues = validate_staged_records("object_enrichment", [record])
    assert issues


@pytest.mark.parametrize(
    "template,valid",
    [
        (None, True),
        ({"schema_version": "1.0", "columns": []}, True),
        (
            {
                "schema_version": "1.0",
                "columns": [
                    {
                        "semantic_name": "CreatedDate",
                        "data_type": "TIMESTAMP",
                        "nullable": True,
                        "definition": None,
                    }
                ],
            },
            True,
        ),
        ({"columns": [{"name": "CreatedDate", "type": "TIMESTAMP"}]}, False),
        ({"schema_version": "2.0", "columns": []}, False),
        ({"columns": [], "unknown": True}, False),
    ],
)
def test_audit_template_contract_matches_published_json_schema(
    template: object, valid: bool
) -> None:
    details = {**project_details(), "silver_model_audit_columns_template": template}
    _, issues = validate_staged_records("project_details", [details])
    assert (not issues) is valid
    schema = build_project_dataset_schema(DATASETS_BY_NAME["project_details"])
    Draft202012Validator.check_schema(schema)
    assert (
        Draft202012Validator(schema).is_valid(json.loads(json.dumps(details))) is valid
    )


@pytest.mark.parametrize("dataset", ["object_enrichment", "attribute_enrichment"])
@pytest.mark.parametrize("expected", [None, "a" * 64])
def test_enrichment_rejects_stale_or_missing_saved_revision(
    dataset: str, expected: str | None
) -> None:
    graph = complete_project_graph(include_enrichment=True)
    graph[dataset][0]["expected_revision"] = "b" * 64
    candidate = {**graph[dataset][0], "expected_revision": expected}
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [candidate]},
        physical_scope=complete_physical_scope(),
    )
    assert any(issue.code == "enrichment_revision_conflict" for issue in result.issues)
