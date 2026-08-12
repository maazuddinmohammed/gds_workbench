from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    SnapshotContractError,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS,
    DatasetDefinition,
)


def dataset(name: str) -> DatasetDefinition:
    return next(definition for definition in DATASETS if definition.name == name)


def project_row(code: str, name: str) -> dict[str, object]:
    return {
        "project_code": code,
        "project_name": name,
        "project_description": None,
        "is_active": True,
    }


def object_row(name: str) -> dict[str, object]:
    return {
        "tenant_code": "TENANT",
        "system_code": "ERP",
        "connection_code": "SOURCE",
        "object_schema": "dbo",
        "object_name": name,
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": "select *\nfrom source",
        "object_description": None,
        "batch_attribute_name": None,
        "object_type_code": "TABLE",
        "zone_code": "source",
        "is_locked": False,
        "is_active": True,
    }


def test_snapshot_rows_are_flat_and_id_free() -> None:
    encoded = encode_dataset(dataset("project"), [project_row("P1", "Finance")])

    assert json.loads(encoded.rows_jsonl) == {
        "project_code": "P1",
        "project_name": "Finance",
        "project_description": None,
        "is_active": True,
    }
    assert encoded.lookup_jsonl is None


def test_rows_sort_by_normalized_natural_key_and_preserve_utf8() -> None:
    encoded = encode_dataset(
        dataset("project"),
        [
            project_row("risk", "Risk\nAnalytics 🚀"),
            project_row("FINANCE", "Finance"),
        ],
    )

    row_lines = encoded.rows_jsonl.decode().splitlines()
    assert [json.loads(line)["project_code"] for line in row_lines] == [
        "FINANCE",
        "risk",
    ]
    assert json.loads(row_lines[1])["project_name"] == "Risk\nAnalytics 🚀"
    assert "\\n" in row_lines[1]
    assert encoded.row_count == 2


def test_wide_dataset_lookup_contains_only_key_filters_and_line() -> None:
    encoded = encode_dataset(
        dataset("source_object"),
        [object_row("orders"), object_row("customers")],
    )

    assert encoded.lookup_jsonl is not None
    lookup_lines = [
        cast(dict[str, Any], json.loads(line))
        for line in encoded.lookup_jsonl.decode().splitlines()
    ]
    assert lookup_lines[0] == {
        "tenant_code": "TENANT",
        "system_code": "ERP",
        "connection_code": "SOURCE",
        "object_schema": "dbo",
        "object_name": "customers",
        "object_type_code": "TABLE",
        "zone_code": "source",
        "is_locked": False,
        "is_active": True,
        "line": 1,
    }
    assert "object_transformation" not in lookup_lines[0]


def test_jsonl_preserves_dates_timestamps_and_bigint_text() -> None:
    control_row = {
        "tenant_code": "TENANT",
        "system_code": "ERP",
        "copy_group_name": "daily",
        "member_group_name": None,
        "copy_group_control_initial_load_date": date(2026, 8, 1),
        "copy_group_control_last_run_time": datetime(2026, 8, 2, tzinfo=UTC),
        "copy_group_control_last_run_value": None,
    }
    control = json.loads(encode_dataset(dataset("copy_group_control"), [control_row]).rows_jsonl)
    assert control["copy_group_control_initial_load_date"] == "2026-08-01"
    assert control["copy_group_control_last_run_time"] == "2026-08-02T00:00:00Z"


def test_jsonl_rejects_schema_drift_invalid_values_and_normalized_duplicates() -> None:
    valid = project_row("P1", "One")

    with pytest.raises(SnapshotContractError, match="fixed schema"):
        encode_dataset(dataset("project"), [{**valid, "unexpected": "value"}])
    with pytest.raises(SnapshotContractError, match="fixed schema"):
        encode_dataset(dataset("project"), [{**valid, "project_code": None}])
    with pytest.raises(SnapshotContractError, match="duplicate unique key"):
        encode_dataset(
            dataset("project"),
            [valid, project_row(" p1 ", "Duplicate")],
        )
    with pytest.raises(SnapshotContractError, match="fixed dataset values"):
        encode_dataset(dataset("source_object"), [{**object_row("orders"), "zone_code": "gold"}])


def test_empty_dataset_writes_only_its_declared_files() -> None:
    project = encode_dataset(dataset("project"), [])
    source_object = encode_dataset(dataset("source_object"), [])

    assert project.rows_jsonl == b""
    assert project.lookup_jsonl is None
    assert source_object.rows_jsonl == b""
    assert source_object.lookup_jsonl == b""
