from copy import deepcopy

import pytest
from gds_etl_workbench.application.model_snapshot import ModelReviewSnapshot
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.features.model_change_sets.review import plan_model_record_review

from tests.mcp.model_test_fixtures import complete_model_graph, snapshot_from_graph


def test_conceptual_retirement_preserves_content_and_plans_only_incident_relationships() -> None:
    snapshot = snapshot_from_graph(complete_model_graph())
    review = ModelReviewSnapshot(
        snapshot=snapshot,
        records_by_id={
            "conceptual_object": {
                index + 1: record for index, record in enumerate(snapshot.conceptual.objects)
            },
            "conceptual_relationship": {91: snapshot.conceptual.relationships[0]},
        },
    )
    before = deepcopy(review)
    decisions = plan_model_record_review(
        review, dataset="conceptual_object", record_ids=[1], action="deactivate"
    )
    assert {(item.dataset, item.record_id) for item in decisions} == {
        ("conceptual_object", 1),
        ("conceptual_relationship", 91),
    }
    for item in decisions:
        old, new = item.original.model_dump(mode="json"), item.reviewed.model_dump(mode="json")
        assert {key for key in old if old[key] != new[key]} == {item.dataset + "_status"}
        assert new[item.dataset + "_status"] == "inactive"
    assert decisions[0].selected and not decisions[1].selected
    assert review == before
    for action in ("lock", "unlock"):
        result = plan_model_record_review(
            review, dataset="conceptual_object", record_ids=[1], action=action
        )
        assert len(result) == 1 and result[0].record_id == 1


def test_conceptual_reactivation_adds_only_required_inactive_endpoints() -> None:
    graph = complete_model_graph()
    for obj in graph["conceptual_object"]:
        obj["conceptual_object_status"] = "inactive"
    graph["conceptual_relationship"][0]["conceptual_relationship_status"] = "inactive"
    snapshot = snapshot_from_graph(graph)
    review = ModelReviewSnapshot(
        snapshot=snapshot,
        records_by_id={
            "conceptual_object": {
                index + 1: record for index, record in enumerate(snapshot.conceptual.objects)
            },
            "conceptual_relationship": {91: snapshot.conceptual.relationships[0]},
        },
    )
    decisions = plan_model_record_review(
        review, dataset="conceptual_relationship", record_ids=[91], action="reactivate"
    )
    assert decisions[0].selected and decisions[0].record_id == 91
    assert len(decisions) == 3
    assert all(
        item.reviewed.model_dump()[item.dataset + "_status"] == "active" for item in decisions
    )
    # Reopening an Object alone never reopens historical Relationships.
    assert (
        len(
            plan_model_record_review(
                review, dataset="conceptual_object", record_ids=[1], action="reactivate"
            )
        )
        == 1
    )
    with pytest.raises(WorkbenchError, match="unavailable"):
        plan_model_record_review(
            review, dataset="conceptual_relationship", record_ids=[999], action="reactivate"
        )
