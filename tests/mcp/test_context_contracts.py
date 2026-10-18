"""Context identity, reference vocabulary, bounds, and protected evidence."""

from copy import deepcopy

import pytest
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.domain.modeling_records import ContextRecord
from gds_etl_workbench.domain.snapshots.project import ProjectSnapshot
from pydantic import ValidationError

from tests.mcp.project_test_fixtures import (
    complete_physical_scope,
    complete_project_graph,
    snapshot_from_graph,
)


@pytest.mark.parametrize(
    "identity", ["order.customer", "123", "A0000000-0000-4000-8000-000000000001"]
)
def test_context_identity_requires_a_canonical_uuid(identity: str) -> None:
    row = deepcopy(complete_project_graph()["context_record"][0])
    row["context_record_id"] = identity
    with pytest.raises(ValidationError):
        ContextRecord.model_validate(row)


def test_context_source_reference_is_bounded_by_utf8_bytes() -> None:
    row = deepcopy(complete_project_graph()["context_record"][0])
    row["source_reference"] = "é" * 32768
    assert ContextRecord.model_validate(row).source_reference == row["source_reference"]
    row["source_reference"] += "é"
    with pytest.raises(ValidationError, match="too large"):
        ContextRecord.model_validate(row)


def test_context_type_is_read_only_and_legacy_snapshots_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StageProjectChange.model_validate({"dataset": "context_type", "records": []})
    snapshot = snapshot_from_graph(complete_project_graph()).model_dump(mode="json")
    snapshot["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        ProjectSnapshot.model_validate(snapshot)


def test_context_group_changes_cannot_reinterpret_locked_records() -> None:
    graph = complete_project_graph()
    graph["context_record"][0]["is_locked"] = True
    group = deepcopy(graph["context_group"][0])
    group["source_system_code"] = None
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"context_group": [group]},
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid
    assert any(issue.code == "context_group_child_locked" for issue in result.issues)


@pytest.mark.parametrize(
    "dataset,field,value",
    [
        ("context_group", "is_active", False),
        ("context_record", "status", "inactive"),
        ("context_record", "status", "deprecated"),
    ],
)
def test_active_support_cannot_lose_its_context(
    dataset: str, field: str, value: object
) -> None:
    graph = complete_project_graph()
    changed = deepcopy(graph[dataset][0])
    changed[field] = value
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={dataset: [changed]},
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid
    assert any(issue.code == "active_dependency_invalid" for issue in result.issues)


def test_context_group_must_resolve_a_global_type() -> None:
    graph = complete_project_graph()
    changed = deepcopy(graph["context_group"][0])
    changed["context_type_name"] = "Invented type"
    result = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={"context_group": [changed]},
        physical_scope=complete_physical_scope(),
    )
    assert not result.valid
    assert any(issue.fields == ("context_type_name",) for issue in result.issues)
