from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gds_etl_workbench.tools.databricks.validation import validate_databricks_sql


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPOSITORY_ROOT / "plugins" / "gds" / "skills" / "profile-gds-data"
GENERATOR = SKILL_ROOT / "scripts" / "build-profile-sql.js"
RESULT_COLUMNS = (
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
    "attribute_name",
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
)


def _spec() -> dict[str, Any]:
    return {
        "connection_id": 41,
        "environment_code": "TEST",
        "physical_key": {
            "tenant_code": "TENANT",
            "system_code": "ERP",
            "connection_code": "SOURCE",
            "object_schema": "sales",
            "object_name": "orders",
        },
        "relation": {
            "catalog": "gds-test",
            "schema": "sales",
            "table": "orders",
        },
        "columns": [
            {"name": "order_id", "data_type": "BIGINT"},
            {"name": "status", "data_type": "STRING"},
        ],
        "batch": {
            "column": "batch_id",
            "data_type": "BIGINT",
            "mode": "incremental",
            "ids": ["1002", "1001"],
        },
    }


def _run_generator(
    tmp_path: Path,
    spec: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    spec_path = tmp_path / "profile-spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return subprocess.run(
        ["node", str(GENERATOR), "--spec", str(spec_path)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_generator_builds_governed_batch_profile_sql(tmp_path: Path) -> None:
    result = _run_generator(tmp_path, _spec())

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan == {
        **{key: plan[key] for key in plan if key == "chunks"},
        "schema_version": "1.0",
        "connection_id": 41,
        "environment_code": "TEST",
        "batch_mode": "incremental",
        "batch_value_count": 2,
        "profile_record_count": 2,
        "chunk_count": 1,
    }
    chunk = plan["chunks"][0]
    assert chunk["attribute_names"] == ["order_id", "status"]
    sql = chunk["sql"]
    assert len(sql) <= 100_000
    assert "`gds-test`.`sales`.`orders`" in sql
    assert "WHERE `batch_id` IN (1001, 1002)" in sql
    assert "SELECT *" not in sql.upper()
    assert "LIMIT" not in sql.upper()
    assert "TRIM(`status`)" in sql
    assert "CAST(NULL AS BIGINT) AS blank_count" in sql
    assert "raw" not in sql.casefold()
    for column in RESULT_COLUMNS:
        assert f" AS {column}" in sql
    validated = validate_databricks_sql(sql)
    assert len(validated.statements) == 1
    assert validated.final_returns_rows is True


def test_generator_chunks_profiles_at_the_tool_row_limit(tmp_path: Path) -> None:
    spec = _spec()
    spec["columns"] = [
        {"name": f"attribute_{index}", "data_type": "BIGINT"} for index in range(1, 52)
    ]
    spec["batch"] = None

    result = _run_generator(tmp_path, spec)

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["profile_record_count"] == 51
    assert plan["chunk_count"] == 2
    assert [len(chunk["attribute_names"]) for chunk in plan["chunks"]] == [50, 1]
    assert plan["batch_mode"] is None
    assert plan["batch_value_count"] == 0
    for chunk in plan["chunks"]:
        assert len(chunk["sql"]) <= 100_000
        validate_databricks_sql(chunk["sql"])


def test_generator_treats_empty_incremental_batch_as_noop(tmp_path: Path) -> None:
    spec = _spec()
    spec["batch"]["ids"] = []

    result = _run_generator(tmp_path, spec)

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["batch_mode"] == "incremental"
    assert plan["batch_value_count"] == 0
    assert plan["profile_record_count"] == 0
    assert plan["chunk_count"] == 0
    assert plan["chunks"] == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda spec: spec["batch"].update(mode="initial", ids=[1, 2]),
            "initial batch mode requires exactly one ID",
        ),
        (
            lambda spec: spec["batch"].update(data_type="TINYINT", ids=[128]),
            "does not fit batch.data_type",
        ),
        (
            lambda spec: spec["columns"].append(
                {"name": "batch_id", "data_type": "BIGINT"}
            ),
            "batch Attribute must not be included",
        ),
        (
            lambda spec: spec["relation"].update(table="other_orders"),
            "must exactly match the registered physical Object key",
        ),
    ],
)
def test_generator_rejects_invalid_batch_specs(
    tmp_path: Path,
    change: Any,
    message: str,
) -> None:
    spec = _spec()
    change(spec)

    result = _run_generator(tmp_path, spec)

    assert result.returncode == 2
    assert message in result.stderr
    assert result.stdout == ""


def test_skill_documents_the_governed_profile_boundary() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_ROOT / "references" / "profiling-contract.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(f"{skill}\n{contract}".split())

    for required in (
        "`execute_databricks_sql`",
        "`profiling_profile`",
        "`batch_attribute_name`",
        "source `connection_id`",
        "`environment_code`",
        "catalog.schema.table",
        "Never silently remove the batch predicate",
        "schema/table to exactly match the registered Object key",
        "no SQL and no Profile records",
        "not an authoritative Profiling Run receipt",
        "`rows_truncated=true`",
        "`cells_truncated=true`",
    ):
        assert required in normalized
    assert "raw physical rows" in normalized
    assert "sample-value" in normalized
