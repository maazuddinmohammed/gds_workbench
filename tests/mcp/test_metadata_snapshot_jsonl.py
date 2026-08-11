from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    SnapshotContractError,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS, DatasetDefinition


def dataset(name: str) -> DatasetDefinition:
    return next(definition for definition in DATASETS if definition.name == name)


def audit_values(day: int = 1) -> dict[str, object]:
    timestamp = datetime(2026, 8, day, 12, 30, 45, 123456, tzinfo=UTC)
    return {
        "created_time": timestamp,
        "created_by": "fixture",
        "updated_time": timestamp,
        "updated_by": "fixture",
    }


def project_row(project_id: int, name: str) -> dict[str, object]:
    return {
        "project_id": project_id,
        "project_code": f"P{project_id}",
        "project_name": name,
        "project_description": None,
        "is_active": True,
        **audit_values(),
    }


def test_jsonl_is_numeric_pk_sorted_utf8_and_bigint_safe() -> None:
    encoded = encode_dataset(
        dataset("project"),
        [
            project_row(10, "Risk\nAnalytics 🚀"),
            project_row(2, "Finance"),
        ],
    )

    row_lines = encoded.rows_jsonl.decode().splitlines()
    index_lines = encoded.index_jsonl.decode().splitlines()
    assert [json.loads(line)["project_id"] for line in row_lines] == ["2", "10"]
    assert json.loads(row_lines[1])["project_name"] == "Risk\nAnalytics 🚀"
    assert "\\n" in row_lines[1]
    assert json.loads(index_lines[0]) == {
        "primary_key": {"project_id": "2"},
        "label": "P2 · Finance",
        "file": "rows.jsonl",
        "line": 1,
    }
    assert json.loads(index_lines[1])["label"] == "P10 · Risk Analytics 🚀"
    assert encoded.row_count == 2


def test_jsonl_preserves_arrays_dates_nulls_and_utc_timestamps() -> None:
    row = {
        "connection_id": 9007199254740993,
        "tenant_id": 2,
        "system_id": 3,
        "connection_code": "GDS",
        "connection_name": "Global Store",
        "connection_type_id": 4,
        "has_foreign_catalog": True,
        "foreign_catalog": None,
        "is_global_data_store": True,
        "test_initial_batch_id": 9007199254740995,
        "test_incremental_batch_ids": [9007199254740997, None],
        "is_active": True,
        "created_time": datetime(
            2026,
            8,
            1,
            8,
            0,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
        "created_by": "fixture",
        "updated_time": datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        "updated_by": "fixture",
    }
    encoded = encode_dataset(dataset("connection"), [row])
    payload = json.loads(encoded.rows_jsonl)

    assert payload["connection_id"] == "9007199254740993"
    assert payload["test_initial_batch_id"] == "9007199254740995"
    assert payload["test_incremental_batch_ids"] == ["9007199254740997", None]
    assert payload["foreign_catalog"] is None
    assert payload["created_time"] == "2026-08-01T12:00:00Z"

    control_row = {
        "copy_group_control_id": 1,
        "copy_group_id": 2,
        "member_group_id": None,
        "tenant_id": 3,
        "system_id": 4,
        "copy_group_control_initial_load_date": date(2026, 8, 1),
        "copy_group_control_last_run_time": None,
        "copy_group_control_last_run_value": None,
        **audit_values(),
    }
    control = json.loads(encode_dataset(dataset("copy_group_control"), [control_row]).rows_jsonl)
    assert control["copy_group_control_initial_load_date"] == "2026-08-01"


def test_jsonl_rejects_schema_drift_invalid_values_and_duplicate_keys() -> None:
    valid = project_row(1, "One")

    with pytest.raises(SnapshotContractError, match="fixed column contract"):
        encode_dataset(dataset("project"), [{**valid, "unexpected": "value"}])
    with pytest.raises(SnapshotContractError, match="cannot contain a null"):
        encode_dataset(dataset("project"), [{**valid, "project_code": None}])
    with pytest.raises(SnapshotContractError, match="must be a BIGINT"):
        encode_dataset(dataset("project"), [{**valid, "project_id": True}])
    with pytest.raises(SnapshotContractError, match="timezone-aware"):
        encode_dataset(
            dataset("project"),
            [{**valid, "created_time": datetime(2026, 8, 1, 12, 0)}],
        )
    with pytest.raises(SnapshotContractError, match="duplicate primary key"):
        encode_dataset(dataset("project"), [valid, project_row(1, "Duplicate")])


def test_jsonl_empty_dataset_is_two_empty_files() -> None:
    encoded = encode_dataset(dataset("project"), [])

    assert encoded.rows_jsonl == b""
    assert encoded.index_jsonl == b""
    assert encoded.row_count == 0
