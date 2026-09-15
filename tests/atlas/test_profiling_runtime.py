"""Synthetic Snapshot -> deterministic plan -> aggregate-only Profile import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from gds_etl_workbench.domain.snapshots.model import (
    DATASETS,
    build_model_dataset_schema,
)

from tests.atlas.test_workspace import fixtures, run, workspace

IDENTITY = [
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
    "attribute_name",
]
METRICS = [
    "row_count",
    "non_null_count",
    "null_count",
    "blank_count",
    "distinct_count",
    "min_data_length",
    "max_data_length",
    "avg_data_length",
    "percent_populated",
    "percent_duplicates",
    "percent_null",
    "percent_blank",
    "percent_distinct",
]


def install_dataset(
    snapshot: Path,
    name: str,
    keys: list[str],
    rows: list[dict[str, Any]],
    schema: dict[str, Any] | None = None,
) -> None:
    catalog = json.loads((snapshot / "catalog.json").read_text())
    datasets = catalog["sections"][0]["datasets"]
    datasets[:] = [item for item in datasets if item["name"] != name]
    datasets.append(
        {
            "name": name,
            "record_type": name,
            "canonical_key": keys,
            "row_count": len(rows),
            "rows_file": f"data/{name}.jsonl",
            "schema_file": f"schemas/{name}.schema.json",
        }
    )
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    (snapshot / f"data/{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (snapshot / f"schemas/{name}.schema.json").write_text(
        json.dumps(schema or {"type": "object", "properties": {}, "additionalProperties": True})
    )


def planned_workspace(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    root = workspace(tmp_path)
    physical = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Customer",
    }
    metadata = root / "metadata/metadata-snapshot"
    source = {
        **physical,
        "zone_code": "Source",
        "source_tenant_code": "TENANT_A",
        "is_active": True,
        "batch_attribute_name": "BatchID",
        "fc_object_schema": "sales",
        "fc_object_name": "Customer",
    }
    attributes = [
        {
            **physical,
            "attribute_name": name,
            "fc_attribute_name": name,
            "attribute_ordinal_position": index + 1,
            "attribute_data_type": "BIGINT" if index == 0 else "STRING",
            "is_active": True,
            "is_masking_required": False,
        }
        for index, name in enumerate(["BatchID", *[f"Field{i}" for i in range(1, 51)]])
    ]
    install_dataset(metadata, "source_object", IDENTITY[:-1], [source])
    install_dataset(metadata, "source_attribute", IDENTITY, attributes)
    install_dataset(
        metadata,
        "tenant",
        ["tenant_code"],
        [
            {
                "tenant_code": "TENANT_A",
                "tenant_catalog": "tenant_catalog",
                "is_active": True,
            }
        ],
    )
    install_dataset(
        metadata,
        "connection",
        ["tenant_code", "system_code", "connection_code"],
        [
            {
                "tenant_code": "TENANT_A",
                "system_code": "CRM",
                "connection_code": "MAIN",
                "foreign_catalog": "crm_catalog",
                "is_active": True,
            }
        ],
    )
    fixtures.write_snapshot_manifest(metadata, kind="metadata", snapshot_id="profile-metadata")
    model = root / "model/model-snapshot"
    for name, rows in [
        (
            "model_input_scope",
            [{**physical, "model_input_scope_is_locked": False, "is_active": True}],
        ),
        ("profiling_profile", []),
    ]:
        definition = next(item for item in DATASETS if item.name == name)
        install_dataset(
            model,
            name,
            list(definition.canonical_key),
            rows,
            build_model_dataset_schema(definition),
        )
    fixtures.write_snapshot_manifest(
        model, kind="model", snapshot_id="profile-model", model_revision=8
    )
    run(
        "sql-policy",
        "--session",
        str(root),
        "--policy",
        "essential",
        "--environment",
        "dev",
    )
    planning = root / ".atlas/temp/planning.json"
    planning.parent.mkdir(exist_ok=True)
    planning.write_text(
        json.dumps(
            {
                "selections": {
                    "systems": [
                        {
                            "source_tenant_code": "TENANT_A",
                            "system_code": "CRM",
                            "batch_ids": ["10", "11"],
                        }
                    ]
                },
                "execution_connections": [
                    {
                        "connection_id": 99,
                        "is_global_data_store": False,
                        "source_tenant_codes": ["TENANT_A"],
                    }
                ],
            }
        )
    )
    result = run("profile-plan", "--session", str(root), "--plan-file", str(planning))
    plan_path = Path(result["manifest"])
    plan = json.loads(plan_path.read_text())
    results: list[dict[str, Any]] = []
    for query in plan["queries"]:
        rows = [
            {
                "attribute_index": item["attribute_index"],
                "row_count": 20,
                "non_null_count": 18,
                "null_count": 2,
                "blank_count": 0,
                "distinct_count": 9,
                "min_data_length": 1,
                "max_data_length": 4,
                "avg_data_length": "2.5",
                "percent_populated": "90",
                "percent_duplicates": "50",
                "percent_null": "10",
                "percent_blank": "0",
                "percent_distinct": "50",
            }
            for item in query["attributes"]
        ]
        for metric_row, attribute in zip(rows, query["attributes"], strict=True):
            if attribute["attribute_name"] == "BatchID":
                for field in [
                    "blank_count",
                    "min_data_length",
                    "max_data_length",
                    "avg_data_length",
                    "percent_blank",
                ]:
                    metric_row[field] = None
        results.append(
            {
                "file": query["file"],
                "connection_id": 99,
                "environment": "dev",
                "executed_at": "2026-09-15T12:00:00Z",
                "truncated": False,
                "rows": rows,
            }
        )
    return root, plan_path, plan, results


def import_results(
    root: Path, plan: Path, rows: list[dict[str, Any]], *, success: bool = True
) -> dict[str, Any]:
    result_path = root / ".atlas/temp/aggregate-results.json"
    result_path.write_text(json.dumps(rows))
    return run(
        "profile-results",
        "--session",
        str(root),
        "--plan-file",
        str(plan),
        "--results-file",
        str(result_path),
        "--expected-digest",
        "empty",
        success=success,
    )


def test_profile_runtime_groups_sql_and_imports_exact_record_contract(
    tmp_path: Path,
) -> None:
    root, plan_path, plan, results = planned_workspace(tmp_path)
    assert [query["expected_row_count"] for query in plan["queries"]] == [50, 1]
    assert len(plan["inputs"]) == 2
    for query in plan["queries"]:
        sql = (plan_path.parent / query["file"]).read_text()
        assert "`BatchID` IN (" in sql
        assert "`crm_catalog`.`sales`.`Customer`" in sql
    outcome = import_results(root, plan_path, results)
    assert outcome["profiles"] == 51
    records = json.loads((root / "model-change-set/profiling_profile.json").read_text())
    assert len(records) == 51
    assert all(set(record) == set(IDENTITY + METRICS) for record in records)
    assert len({record["attribute_name"] for record in records}) == 51
    evidence = json.loads((root / outcome["evidence"]).read_text())
    assert evidence["inputs"] == plan["inputs"]
    assert [entry["attribute_count"] for entry in evidence["coverage"]] == [50, 1]
    assert all(
        entry["batch_ids"] == ["10", "11"] and "rows" not in entry for entry in evidence["coverage"]
    )


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "truncated",
        "changed_sql",
        "changed_snapshot",
        "duplicate_index",
        "unknown_column",
        "wrong_connection",
        "inconsistent_counts",
        "missing_bindings",
        "wrong_percent",
        "nonstring_lengths",
    ],
)
def test_profile_runtime_rejects_incomplete_or_unbound_results_before_writing(
    tmp_path: Path, case: str
) -> None:
    root, plan_path, plan, results = planned_workspace(tmp_path)
    if case == "missing":
        results.pop()
    elif case == "truncated":
        results[0]["truncated"] = True
    elif case == "changed_sql":
        sql = plan_path.parent / plan["queries"][0]["file"]
        sql.write_text(sql.read_text() + "\n ")
    elif case == "changed_snapshot":
        manifest = root / "metadata/metadata-snapshot/manifest.json"
        manifest.write_text(manifest.read_text() + "\n ")
    elif case == "duplicate_index":
        results[0]["rows"][1]["attribute_index"] = results[0]["rows"][0]["attribute_index"]
    elif case == "unknown_column":
        results[0]["rows"][0]["sample_value"] = "not permitted"
    elif case == "wrong_connection":
        results[0]["connection_id"] = 100
    elif case == "inconsistent_counts":
        results[1]["rows"][0].update(row_count=30, non_null_count=28)
    elif case == "missing_bindings":
        plan["inputs"] = []
        plan_path.write_text(json.dumps(plan))
    elif case == "wrong_percent":
        results[0]["rows"][1]["percent_distinct"] = "49"
    elif case == "nonstring_lengths":
        results[0]["rows"][0]["min_data_length"] = 3
    import_results(root, plan_path, results, success=False)
    assert not (root / "model-change-set/profiling_profile.json").exists()
