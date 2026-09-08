"""Every result lifecycle plan remains a valid graph and preserves authored values."""

from dataclasses import replace
from typing import cast

import pytest
from gds_etl_workbench.application.model_snapshot import ModelReviewSnapshot
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset, model_snapshot_records
from gds_workbench_api.features.model_change_sets.review import (
    REVIEW_FIELDS,
    ModelReviewDataset,
    prepare_model_record_review,
    review_lifecycle,
)

from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    complete_physical_scope,
    snapshot_from_graph,
)


def review_graph(
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]],
) -> ModelReviewSnapshot:
    snapshot = snapshot_from_graph(graph)
    return ModelReviewSnapshot(
        snapshot=snapshot,
        records_by_id={
            dataset: {i + 1: row for i, row in enumerate(rows)}
            for dataset, rows in model_snapshot_records(snapshot).items()
            if dataset in REVIEW_FIELDS
        },
    )


@pytest.mark.parametrize("dataset", list(REVIEW_FIELDS))
def test_all_result_lifecycle_transitions_preserve_graph_and_content(
    dataset: ModelReviewDataset,
) -> None:
    graph = complete_model_graph()
    for action in ("lock", "unlock", "deactivate", "reactivate"):
        review = review_graph(graph)
        prepared = prepare_model_record_review(
            review,
            physical_scope=complete_physical_scope(),
            dataset=dataset,
            record_ids=[1],
            action=action,
        )
        assert prepared.validation.valid, [(i.code, i.dataset) for i in prepared.validation.issues]
        for decision in prepared.decisions:
            original, changed = (
                decision.original.model_dump(mode="json"),
                decision.reviewed.model_dump(mode="json"),
            )
            assert {field for field in original if original[field] != changed[field]} <= set(
                REVIEW_FIELDS[decision.dataset][:2]
            )
            graph[decision.dataset][decision.record_id - 1] = changed
        selected = prepared.decisions[0]
        assert selected.selected and selected.dataset == dataset
        locked, status = review_lifecycle(selected.reviewed, dataset)
        assert locked is (action == "lock")
        assert status == ("inactive" if action == "deactivate" else "active")


def test_bound_attribute_retirement_includes_binding_mapping_code_and_validation() -> None:
    review = review_graph(complete_model_graph())
    prepared = prepare_model_record_review(
        review,
        physical_scope=complete_physical_scope(),
        dataset="logical_attribute",
        record_ids=[2],
        action="deactivate",
    )
    assert prepared.validation.valid
    assert {d.dataset for d in prepared.decisions} >= {
        "logical_attribute",
        "logical_relationship",
        "model_object_binding",
        "model_attribute_binding",
        "mapping_object",
        "mapping_attribute",
        "generated_code",
        "generated_code_source_system",
        "validation_group",
        "validation_check",
    }
    assert all(
        d.selected or "Required" in d.reason or "last active Mapping" in d.reason
        for d in prepared.decisions
    )
    graph = complete_model_graph()
    graph["model_attribute_binding"][0]["model_attribute_binding_is_locked"] = True
    blocked = prepare_model_record_review(
        review_graph(graph),
        physical_scope=complete_physical_scope(),
        dataset="logical_attribute",
        record_ids=[2],
        action="deactivate",
    )
    assert not blocked.validation.valid and any(
        i.code == "record_locked" for i in blocked.validation.issues
    )


def test_stale_code_review_preserves_assignments_and_authoring_still_rejects() -> None:
    from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph

    graph = complete_model_graph()
    for dataset in ("mapping_dependency", "mapping_object", "mapping_attribute"):
        graph[cast(ModelChangeSetDataset, dataset)] += [
            {**row, "source_system_code": "CRM"}
            for row in graph[cast(ModelChangeSetDataset, dataset)]
        ]
    physical = replace(
        complete_physical_scope(), active_system_codes=frozenset({"erp", "crm", "gds"})
    )
    for action in ("lock", "unlock"):
        review = review_graph(graph)
        prepared = prepare_model_record_review(
            review, physical_scope=physical, dataset="generated_code", record_ids=[1], action=action
        )
        assert prepared.validation.valid
        graph["generated_code"][0] = prepared.decisions[0].reviewed.model_dump(mode="json")
    assert not validate_future_graph(
        snapshot=review_graph(graph).snapshot,
        physical_scope=physical,
        staged_documents={"generated_code": graph["generated_code"]},
    ).valid


def test_partial_code_retirement_previews_the_bundle_and_reactivation_requires_coverage() -> None:
    graph = complete_model_graph()
    for dataset in ("mapping_dependency", "mapping_object", "mapping_attribute"):
        name = cast(ModelChangeSetDataset, dataset)
        graph[name] += [{**row, "source_system_code": "CRM"} for row in graph[name]]
    graph["generated_code"].append({**graph["generated_code"][0], "artifact_name": "crm.sql"})
    graph["generated_code_source_system"].append(
        {
            **graph["generated_code_source_system"][0],
            "artifact_name": "crm.sql",
            "source_system_code": "CRM",
        }
    )
    physical = replace(
        complete_physical_scope(), active_system_codes=frozenset({"erp", "crm", "gds"})
    )
    retired = prepare_model_record_review(
        review_graph(graph),
        physical_scope=physical,
        dataset="generated_code",
        record_ids=[1],
        action="deactivate",
    )
    assert retired.validation.valid
    assert {(d.dataset, d.record_id) for d in retired.decisions} == {
        ("generated_code", 1),
        ("generated_code", 2),
        ("generated_code_source_system", 1),
        ("generated_code_source_system", 2),
    }
    for decision in retired.decisions:
        graph[decision.dataset][decision.record_id - 1] = decision.reviewed.model_dump(mode="json")
    partial = prepare_model_record_review(
        review_graph(graph),
        physical_scope=physical,
        dataset="generated_code",
        record_ids=[1],
        action="reactivate",
    )
    assert not partial.validation.valid
    complete = prepare_model_record_review(
        review_graph(graph),
        physical_scope=physical,
        dataset="generated_code",
        record_ids=[1, 2],
        action="reactivate",
    )
    assert complete.validation.valid
