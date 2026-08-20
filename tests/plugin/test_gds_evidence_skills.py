from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ModelingAssertionDocumentRecord,
    ModelingAssertionRecordRecord,
)
from gds_etl_workbench.tools.databricks.validation import validate_databricks_sql


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPOSITORY_ROOT / "plugins" / "gds" / "skills"
ANALYSIS_ROOT = SKILLS_ROOT / "analyze-gds-relationships"
ASSERTION_ROOT = SKILLS_ROOT / "capture-modeling-assertions"
GENERATOR = ANALYSIS_ROOT / "scripts" / "build-relationship-sql.js"
RESULT_COLUMNS = [
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
    "validation_result",
]


def _endpoint(
    *,
    system: str,
    schema: str,
    table: str,
    attribute: str,
    batch: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "physical_key": {
            "tenant_code": "TENANT",
            "system_code": system,
            "connection_code": "SOURCE",
            "object_schema": schema,
            "object_name": table,
            "attribute_name": attribute,
        },
        "relation": {
            "catalog": "gds-test",
            "schema": schema,
            "table": table,
        },
        "data_type": "BIGINT",
        "batch": batch,
    }


def _spec() -> dict[str, Any]:
    return {
        "connection_id": 41,
        "environment_code": "TEST",
        "relationship_kind": "foreign_key_candidate",
        "comparison_type": None,
        "from": _endpoint(
            system="ERP",
            schema="sales",
            table="orders",
            attribute="customer_id",
            batch={
                "column": "batch_id",
                "data_type": "BIGINT",
                "mode": "incremental",
                "ids": [1002, 1001],
            },
        ),
        "to": _endpoint(
            system="CRM",
            schema="crm",
            table="customers",
            attribute="customer_id",
            batch=None,
        ),
    }


def _run_generator(
    tmp_path: Path,
    spec: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    spec_path = tmp_path / "analysis-spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return subprocess.run(
        ["node", str(GENERATOR), "--spec", str(spec_path)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_relationship_generator_builds_one_governed_aggregate_query(
    tmp_path: Path,
) -> None:
    result = _run_generator(tmp_path, _spec())

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "1.0"
    assert plan["validation_policy_version"] == "1.0.0"
    assert plan["connection_id"] == 41
    assert plan["environment_code"] == "TEST"
    assert plan["comparison_type"] is None
    assert plan["batch_modes"] == {"from": "incremental", "to": None}
    assert plan["batch_value_counts"] == {"from": 2, "to": 0}
    assert plan["no_op"] is False
    assert plan["result_columns"] == RESULT_COLUMNS
    assert plan["analysis_identity"]["from_attribute_name"] == "customer_id"
    assert plan["analysis_identity"]["to_object_name"] == "customers"
    assert plan["analysis_identity"]["relationship_kind"] == "foreign_key_candidate"

    record = AnalysisResultRecord.model_validate(
        {
            **plan["analysis_identity"],
            "relationship_confidence": "high",
            "relationship_basis": "Complete selected populations; no implicit cast.",
            "validation_policy_version": plan["validation_policy_version"],
            "validation_source_non_null_count": 100,
            "validation_source_distinct_count": 90,
            "validation_target_non_null_count": 120,
            "validation_target_distinct_count": 120,
            "validation_source_missing_target_count": 0,
            "validation_unused_target_count": 30,
            "validation_duplicate_target_key_count": 0,
            "validation_result": "supported",
            "analysis_result_status": "needs_review",
            "analysis_result_is_locked": False,
        },
        strict=True,
    )
    assert record.validation_result == "supported"

    sql = plan["sql"]
    assert len(sql) <= 100_000
    assert "`gds-test`.`sales`.`orders`" in sql
    assert "`gds-test`.`crm`.`customers`" in sql
    assert "`batch_id` IN (1001, 1002)" in sql
    assert "LEFT ANTI JOIN" in sql
    assert "SELECT *" not in sql.upper()
    assert "LIMIT" not in sql.upper()
    for column in RESULT_COLUMNS:
        assert f" AS {column}" in sql
    validated = validate_databricks_sql(sql)
    assert len(validated.statements) == 1
    assert validated.final_returns_rows is True


def test_relationship_generator_allows_only_explicit_cross_type_cast(
    tmp_path: Path,
) -> None:
    spec = _spec()
    spec["to"]["data_type"] = "INT"

    rejected = _run_generator(tmp_path, spec)

    assert rejected.returncode == 2
    assert "require an explicit comparison_type" in rejected.stderr

    spec["comparison_type"] = "BIGINT"
    accepted = _run_generator(tmp_path, spec)
    assert accepted.returncode == 0, accepted.stderr
    sql = json.loads(accepted.stdout)["sql"]
    assert "CAST(`customer_id` AS BIGINT)" in sql
    validate_databricks_sql(sql)


def test_relationship_generator_treats_empty_incremental_batch_as_noop(
    tmp_path: Path,
) -> None:
    spec = _spec()
    spec["from"]["batch"]["ids"] = []

    result = _run_generator(tmp_path, spec)

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["no_op"] is True
    assert plan["sql"] is None
    assert plan["batch_value_counts"] == {"from": 0, "to": 0}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda spec: spec["to"]["relation"].update(table="other_customers"),
            "must exactly match its registered physical Object key",
        ),
        (
            lambda spec: spec.update(to=spec["from"]),
            "from and to Attributes must be different",
        ),
        (
            lambda spec: spec["to"]["physical_key"].update(tenant_code="OTHER"),
            "must belong to the same Model Tenant",
        ),
        (
            lambda spec: spec.update(comparison_type="BIGINT); DROP TABLE x"),
            "must be a comparable scalar Databricks type",
        ),
    ],
)
def test_relationship_generator_rejects_unsafe_or_mismatched_specs(
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


def test_assertion_example_is_exact_and_contract_valid() -> None:
    example = json.loads(
        (ASSERTION_ROOT / "references" / "assertion-example.json").read_text(
            encoding="utf-8"
        )
    )

    document = ModelingAssertionDocumentRecord.model_validate_json(
        json.dumps(example["document"]), strict=True
    )
    records = tuple(
        ModelingAssertionRecordRecord.model_validate_json(
            json.dumps(record), strict=True
        )
        for record in example["records"]
    )

    assert (
        document.modeling_assertion_document_name
        == records[0].modeling_assertion_document_name
    )
    assert records[0].modeling_assertion_applicable_layers == (
        "conceptual",
        "logical",
        "dimensional",
    )
    assert "page" in (records[0].modeling_assertion_source_location or {})


def test_new_skill_resources_are_progressively_disclosed() -> None:
    analysis = (ANALYSIS_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assertions = (ASSERTION_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "references/analysis-contract.md" in analysis
    assert "scripts/build-relationship-sql.js" in analysis
    assert "references/assertion-contract.md" in assertions
    assert "references/assertion-example.json" in assertions
    assert "vector search index" in assertions
    assert "raw physical rows" in analysis
    assert "raw physical rows" in assertions
