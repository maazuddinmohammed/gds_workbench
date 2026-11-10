"""Execute maintained synthetic Mapping rules and SQL without external services."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest
from atlas_platform.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)
from pydantic import JsonValue
from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel

SCENARIOS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures/code_orchestration_contracts.json").read_text()
)


def execute_fixture_sql(
    sql: str, sources: dict[str, Any]
) -> tuple[list[str], list[tuple[Any, ...]]]:
    statements = parse(sql, read="databricks", error_level=ErrorLevel.RAISE)
    assert statements and isinstance(statements[-1], exp.Query)
    with sqlite3.connect(":memory:") as connection:
        for name, source in sources.items():
            table = exp.to_identifier(name.replace(".", "__"), quoted=True).sql()
            source_columns = cast(list[str], source["columns"])
            columns = ", ".join(
                exp.to_identifier(name, quoted=True).sql() for name in source_columns
            )
            connection.execute(f"CREATE TABLE {table} ({columns})")
            placeholders = ", ".join("?" for _ in source_columns)
            connection.executemany(
                f"INSERT INTO {table} VALUES ({placeholders})", source["rows"]
            )
        for statement in statements:
            assert statement is not None
            for table in statement.find_all(exp.Table):
                assert not table.catalog
                if table.db:
                    # SQLite has no runtime catalog. Resolve each fixture's
                    # schema.table identity to a distinct memory-only table.
                    table.set("this", exp.to_identifier(f"{table.db}__{table.name}"))
                    table.set("db", None)
            if isinstance(statement, exp.Create):
                assert statement.kind == "VIEW"
                # SQLite needs plain CREATE VIEW AS SELECT. The fixture starts empty
                # and Databricks' optional outer parentheses do not change the query.
                statement.set("replace", False)
                if isinstance(statement.expression, exp.Subquery):
                    statement.set("expression", statement.expression.unnest())
                connection.execute(statement.sql(dialect="sqlite"))
        final = statements[-1]
        assert isinstance(final, exp.Query)
        cursor = connection.execute(final.sql(dialect="sqlite"))
        return (
            [column[0] for column in cursor.description],
            sorted(cursor.fetchall(), key=repr),
        )


@pytest.mark.parametrize("scenario", ("rollup", "temporal"))
async def test_complex_mapping_and_generated_sql_preserve_expected_rows(scenario: str) -> None:
    case = SCENARIOS[scenario]
    sql = case["generated_sql"]
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                modeled_entity_id=1,
                source_system_codes=(case["source_system_code"],),
                file_layout="per_system",
            ),
        )
    )
    candidate: JsonValue = {
        "issues": [],
        "artifacts": [
            {
                "target_ref": "target_1",
                "artifact_name": "transformation.sql",
                "artifact_role": "target_transformation",
                "source_system_codes": [case["source_system_code"]],
                "generated_sql": sql,
            }
        ],
    }
    assert not (await validator.validate(candidate)).issues
    assert len(validator.parse_validated(candidate)) == 1
    statements = parse(sql, read="databricks", error_level=ErrorLevel.RAISE)
    assert isinstance(statements[0], exp.Create)
    assert isinstance(statements[-1], exp.Query)
    expected = case["expected"]
    assert [field["name"] for field in case["mapping"]["fields"]] == expected["columns"]

    # Modern Object instructions describe the rowset and filters separately; the
    # legacy sample contains a full projection. Only the Code artifact is executed.
    obj = case["mapping"]
    if scenario == "rollup":
        join_plan, steps = obj["sample_query"].split("\n\n-- Object-level transformations\n")
        assert join_plan.startswith("-- Join plan\nFROM ")
        assert "detail_totals" in join_plan and "detail_totals" in steps
        assert "SELECT " not in obj["sample_query"].upper()
        assert "'wid_gdsbatchid'" in obj["filter_criteria"]
    else:
        assert obj["sample_query"].startswith("SELECT ")
        assert "<SHIP System ID>" in obj["sample_query"]
        assert "MAX(GDSBatchID)" in obj["filter_criteria"]
        assert "'WID_GDSBatchID'" in obj["filter_criteria"]
    assert "'wid_gdsbatchid'" in sql
    bound = sql.replace("'wid_gdsbatchid'", str(case["batch_value"]))
    columns, rows = execute_fixture_sql(bound, case["sources"])
    assert columns == expected["columns"]
    assert rows == sorted((tuple(row) for row in expected["rows"]), key=repr)
