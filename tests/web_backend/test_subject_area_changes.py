"""Human Subject Area edits stage one validated change: nothing deleted, locks respected."""

from typing import Literal

import pytest
from gds_etl_workbench.application.project_snapshot import ProjectReviewSnapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.snapshots.project import ProjectChangeSetDataset
from tests.mcp.project_test_fixtures import (
    BRONZE_ORDERS,
    SOURCE_CUSTOMERS,
    SOURCE_ORDERS,
    complete_physical_scope,
    complete_project_graph,
    physical_object,
    snapshot_from_graph,
)

from gds_workbench_api.features.project_change_sets.contracts import SaveSubjectAreaRequest
from gds_workbench_api.features.project_change_sets.subject_areas import (
    prepare_subject_area_change,
)

type Graph = dict[ProjectChangeSetDataset, list[dict[str, object]]]
type Status = Literal["active", "inactive"]

# Input Scope rows by object id, as the service reads them. The fixture's saved Sales
# area holds 101 and 102; only active eligible Bronze tables (103) can be added.
SCOPE_TABLES: dict[int, dict[str, object]] = {
    101: {**physical_object(SOURCE_ORDERS), "is_addable": False},
    102: {**physical_object(SOURCE_CUSTOMERS), "is_addable": False},
    103: {**physical_object(BRONZE_ORDERS), "is_addable": True},
}
SALES_DEFINITION = "Customer orders and the customers who place them."


def _area(
    name: str = "Sales", *, definition: str = SALES_DEFINITION, status: Status = "active"
) -> dict[str, object]:
    return {
        "subject_area_name": name,
        "subject_area_definition": definition,
        "subject_area_status": status,
        "subject_area_is_locked": False,
    }


def _member(
    area: str,
    key: tuple[str, str, str, str, str],
    *,
    status: Status = "active",
    locked: bool = False,
) -> dict[str, object]:
    return {
        "subject_area_name": area,
        **physical_object(key),
        "subject_area_table_status": status,
        "subject_area_table_is_locked": locked,
    }


def _save(graph: Graph | None = None, **command: object) -> dict[str, list[dict[str, object]]]:
    """Return the staged records of one valid change; Sales has review id 1."""
    snapshot = snapshot_from_graph(graph or complete_project_graph())
    validation = prepare_subject_area_change(
        ProjectReviewSnapshot(
            snapshot=snapshot,
            records_by_id={"subject_area": dict(enumerate(snapshot.subject_area.areas, start=1))},
        ),
        SaveSubjectAreaRequest.model_validate({"expected_project_revision": 2, **command}),
        SCOPE_TABLES,
        complete_physical_scope(),
    )
    assert validation.valid and validation.candidate_digest is not None
    return {
        dataset: [record.model_dump(mode="json") for record in records]
        for dataset, records in validation.records.items()
    }


def _error_code(graph: Graph | None = None, **command: object) -> str:
    with pytest.raises(WorkbenchError) as raised:
        _save(graph, **command)
    return raised.value.code


def test_create_adds_an_area_with_its_tables() -> None:
    assert _save(
        subject_area_name="Billing",
        subject_area_definition="Invoices for orders.",
        add_object_ids=[103],
    ) == {
        "subject_area": [_area("Billing", definition="Invoices for orders.")],
        "subject_area_table": [_member("Billing", BRONZE_ORDERS)],
    }


def test_edit_changes_the_definition_or_tables_and_keeps_removed_tables_inactive() -> None:
    assert _save(subject_area_id=1, subject_area_definition="Orders and their buyers.") == {
        "subject_area": [_area(definition="Orders and their buyers.")],
        "subject_area_table": [],
    }
    # A table may leave an area after it stops being addable; nothing is deleted.
    assert _save(subject_area_id=1, add_object_ids=[103], remove_object_ids=[101]) == {
        "subject_area": [_area()],
        "subject_area_table": [
            _member("Sales", SOURCE_ORDERS, status="inactive"),
            _member("Sales", BRONZE_ORDERS),
        ],
    }


def test_rename_moves_active_tables_and_keeps_the_old_area_inactive() -> None:
    graph = complete_project_graph()
    graph["subject_area_table"][1]["subject_area_table_status"] = "inactive"

    # The inactive customers membership stays with the old area as history.
    assert _save(graph, subject_area_id=1, subject_area_name="Customer Orders") == {
        "subject_area": [_area("Customer Orders"), _area(status="inactive")],
        "subject_area_table": [
            _member("Sales", SOURCE_ORDERS, status="inactive"),
            _member("Customer Orders", SOURCE_ORDERS),
        ],
    }


def test_locks_protect_the_area_and_its_tables() -> None:
    locked_area = complete_project_graph()
    locked_area["subject_area"][0]["subject_area_is_locked"] = True
    locked_table = complete_project_graph()
    locked_table["subject_area_table"][0]["subject_area_table_is_locked"] = True
    locked_out = complete_project_graph()
    locked_out["subject_area_table"].append(
        _member("Sales", BRONZE_ORDERS, status="inactive", locked=True)
    )

    assert _error_code(locked_area, subject_area_id=1, subject_area_definition="New.") == (
        "record_locked"
    )
    assert _error_code(locked_table, subject_area_id=1, remove_object_ids=[101]) == "record_locked"
    assert _error_code(locked_table, subject_area_id=1, subject_area_name="Customer Orders") == (
        "record_locked"
    )
    # A locked removal cannot be undone by adding the table back, with or without a rename.
    assert _error_code(locked_out, subject_area_id=1, add_object_ids=[103]) == "record_locked"
    assert (
        _error_code(
            locked_out, subject_area_id=1, subject_area_name="Customer Orders", add_object_ids=[103]
        )
        == "record_locked"
    )


def test_saving_keeps_an_inactive_area_inactive_until_tables_are_added() -> None:
    graph = complete_project_graph()
    graph["subject_area"][0]["subject_area_status"] = "inactive"
    for member in graph["subject_area_table"]:
        member["subject_area_table_status"] = "inactive"

    assert _save(graph, subject_area_id=1, subject_area_definition="Retired orders.") == {
        "subject_area": [_area(definition="Retired orders.", status="inactive")],
        "subject_area_table": [],
    }
    assert _save(graph, subject_area_id=1, add_object_ids=[103]) == {
        "subject_area": [_area()],
        "subject_area_table": [_member("Sales", BRONZE_ORDERS)],
    }


def test_names_stay_unique_and_only_eligible_tables_change() -> None:
    graph = complete_project_graph()
    graph["subject_area"].append(_area("Archive", definition="Old tables.", status="inactive"))

    # Names compare trimmed and case-insensitively, inactive areas included.
    assert _error_code(graph, subject_area_name=" sales ", subject_area_definition="Again.") == (
        "subject_area_name_conflict"
    )
    assert _error_code(graph, subject_area_id=1, subject_area_name="ARCHIVE") == (
        "subject_area_name_conflict"
    )
    # A Source table, and an object outside Input Scope, cannot be added.
    for object_id in (101, 999):
        assert _error_code(graph, subject_area_id=1, add_object_ids=[object_id]) == (
            "subject_area_table_unavailable"
        )
    # Only the area's own tables can be removed.
    for object_id in (103, 999):
        with pytest.raises(InvalidRequestError, match="Remove only tables in this Subject Area"):
            _save(graph, subject_area_id=1, remove_object_ids=[object_id])
    assert _error_code(graph, subject_area_id=99, subject_area_definition="Missing.") == (
        "project_record_not_found"
    )
