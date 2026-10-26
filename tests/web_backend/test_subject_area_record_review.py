"""Subject Area lifecycle plans keep each membership consistent with its area."""

from copy import deepcopy

import pytest
from gds_etl_workbench.application.project_snapshot import ProjectReviewSnapshot
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.snapshots.project import ProjectChangeSetDataset
from tests.mcp.project_test_fixtures import complete_project_graph, snapshot_from_graph

from gds_workbench_api.features.project_change_sets.review import (
    ProjectReviewDataset,
    RecordReviewAction,
    plan_project_record_review,
)


def _review(
    graph: dict[ProjectChangeSetDataset, list[dict[str, object]]],
) -> ProjectReviewSnapshot:
    """Areas get ids 1, 2, ...; memberships 91, 92, ... (Sales/orders, Sales/customers)."""
    snapshot = snapshot_from_graph(graph)
    return ProjectReviewSnapshot(
        snapshot=snapshot,
        records_by_id={
            "subject_area": dict(enumerate(snapshot.subject_area.areas, start=1)),
            "subject_area_table": dict(enumerate(snapshot.subject_area.tables, start=91)),
        },
    )


def test_area_retirement_preserves_content_and_retires_only_its_active_tables() -> None:
    graph = complete_project_graph()
    graph["subject_area_table"][1]["subject_area_table_is_active"] = False
    review = _review(graph)
    before = deepcopy(review)

    decisions = plan_project_record_review(
        review, dataset="subject_area", record_ids=[1], action="deactivate"
    )

    assert [(item.dataset, item.record_id, item.selected) for item in decisions] == [
        ("subject_area", 1, True),
        ("subject_area_table", 91, False),
    ]
    for item in decisions:
        old = item.original.model_dump(mode="json")
        new = item.reviewed.model_dump(mode="json")
        assert {key for key in old if old[key] != new[key]} == {f"{item.dataset}_is_active"}
        assert new[f"{item.dataset}_is_active"] is False
    assert review == before
    for action in ("lock", "unlock"):
        result = plan_project_record_review(
            review, dataset="subject_area", record_ids=[1], action=action
        )
        assert [(item.dataset, item.record_id) for item in result] == [("subject_area", 1)]
    # Deleting an area plans every membership, active or not.
    deleted = plan_project_record_review(
        review, dataset="subject_area", record_ids=[1], action="delete"
    )
    assert {(item.dataset, item.record_id) for item in deleted} == {
        ("subject_area", 1),
        ("subject_area_table", 91),
        ("subject_area_table", 92),
    }


def test_membership_reactivation_also_reactivates_its_inactive_area() -> None:
    graph = complete_project_graph()
    graph["subject_area"][0]["subject_area_is_active"] = False
    for membership in graph["subject_area_table"]:
        membership["subject_area_table_is_active"] = False
    review = _review(graph)

    decisions = plan_project_record_review(
        review, dataset="subject_area_table", record_ids=[91], action="reactivate"
    )

    assert [(item.dataset, item.record_id, item.selected) for item in decisions] == [
        ("subject_area_table", 91, True),
        ("subject_area", 1, False),
    ]
    assert all(item.reviewed.model_dump()[f"{item.dataset}_is_active"] for item in decisions)
    # Reopening an area alone never reopens its historical memberships.
    assert [
        (item.dataset, item.record_id)
        for item in plan_project_record_review(
            review, dataset="subject_area", record_ids=[1], action="reactivate"
        )
    ] == [("subject_area", 1)]
    with pytest.raises(WorkbenchError, match="unavailable"):
        plan_project_record_review(
            review, dataset="subject_area_table", record_ids=[999], action="reactivate"
        )


def test_layer_clear_covers_every_area_and_membership() -> None:
    graph = complete_project_graph()
    graph["subject_area"].append(
        {
            "subject_area_name": "Billing",
            "subject_area_definition": "Invoices for orders.",
            "subject_area_is_active": False,
            "subject_area_is_locked": False,
        }
    )
    review = _review(graph)

    retired = plan_project_record_review(
        review, dataset="subject_area", record_ids=[], action="deactivate", layer="subject_area"
    )
    deleted = plan_project_record_review(
        review, dataset="subject_area", record_ids=[], action="delete", layer="subject_area"
    )

    # Retiring skips the already inactive Billing area; deleting includes it.
    assert [(item.dataset, item.record_id, item.selected) for item in retired] == [
        ("subject_area", 1, True),
        ("subject_area_table", 91, True),
        ("subject_area_table", 92, True),
    ]
    assert {(item.dataset, item.record_id) for item in deleted} == {
        ("subject_area", 1),
        ("subject_area", 2),
        ("subject_area_table", 91),
        ("subject_area_table", 92),
    }
    invalid: tuple[tuple[ProjectReviewDataset, list[int | str], RecordReviewAction], ...] = (
        ("subject_area_table", [], "deactivate"),
        ("subject_area", [1], "deactivate"),
        ("subject_area", [], "lock"),
    )
    for dataset, record_ids, action in invalid:
        with pytest.raises(WorkbenchError, match="layer review request is invalid"):
            plan_project_record_review(
                review, dataset=dataset, record_ids=record_ids, action=action, layer="subject_area"
            )
