"""Execute the planner's GROUP BY/NOT EXISTS core in a guarded disposable database."""

from __future__ import annotations

import re
from typing import LiteralString, cast

from gds_etl_workbench.domain.databricks_sql import (
    DatabricksStatementKind,
    validate_databricks_sql,
)
from gds_etl_workbench.domain.modeling_records import AnalysisValidationEvidence

from tests.mcp.conftest import DisposablePostgres, TestRow
from tests.plugin_v2.test_analysis_plan_helper import analysis_fixture, plan_queries


def test_analysis_probes_pass_governed_sql_read_policy() -> None:
    for probe in plan_queries(analysis_fixture()):
        validated = validate_databricks_sql(probe["sql"])
        assert len(validated.statements) == 1
        assert validated.statements[0].kind is DatabricksStatementKind.READ
        assert validated.final_returns_rows


def test_analysis_probe_sql_measures_tuples_nulls_and_orphans(
    postgres_database: DisposablePostgres,
) -> None:
    fixture = analysis_fixture(postgres_database.database, "pg_temp")
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "CREATE TEMP TABLE analysis_source "
            "(customer_id text, region text, name text, line text)"
        )
        connection.execute("CREATE TEMP TABLE analysis_target (LIKE analysis_source)")
        connection.execute("CREATE TEMP TABLE analysis_empty (LIKE analysis_source)")
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO analysis_source VALUES (%s, %s, %s, %s)",
                [
                    ("A", "US", "Alpha", "1"), ("A", "US", "Alpha", "2"),
                    ("A", "EU", "Alfa", "1"), ("B", "US", "Beta", "1"),
                    ("B", "US", None, "2"), ("C", "US", "Gamma", "1"),
                    (None, "US", "Unknown", "1"), ("Z", None, "Unknown", "1"),
                    ("x|y", "z", "CollisionA", "1"), ("x", "y|z", "CollisionB", "1"),
                ],
            )
            cursor.executemany(
                "INSERT INTO analysis_target VALUES (%s, %s, %s, %s)",
                [
                    ("A", "US", "Alpha", "1"), ("A", "EU", "Alfa", "1"),
                    ("B", "US", "Beta", "1"), ("B", "US", "Beta copy", "2"),
                    ("D", "US", "Unused", "1"), (None, "US", "Unknown", "1"),
                    ("x|y", "z", "CollisionA", "1"), ("x", "y|z", "CollisionB", "1"),
                ],
            )
        for empty in (False, True):
            if empty:
                fixture["metadata"]["source_object"][0]["fc_object_name"] = "analysis_empty"
            results: list[TestRow] = []
            for query in plan_queries(fixture):
                # Only the quoted-identifier dialect changes. SQL operations remain exact.
                sql = re.sub(r"`((?:``|[^`])*)`", lambda match: '"' +
                             match[1].replace("``", "`").replace('"', '""') + '"', query["sql"])
                rows = connection.execute(cast(LiteralString, sql)).fetchall()
                assert len(rows) == 1
                results.append(rows[0])
            key, dependency, join = results
            assert key == {
                "row_count": 0 if empty else 10, "null_key_row_count": 0 if empty else 2,
                "distinct_complete_key_count": 0 if empty else 6,
                "duplicate_complete_key_row_count": 0 if empty else 2,
            }
            assert dependency == {
                "row_count": 0 if empty else 10,
                "null_determinant_row_count": 0 if empty else 2,
                "complete_determinant_group_count": 0 if empty else 6,
                "conflicting_determinant_group_count": 0 if empty else 1,
            }
            assert join == {
                "validation_source_non_null_count": 0 if empty else 8,
                "validation_source_distinct_count": 0 if empty else 6,
                "validation_target_non_null_count": 7, "validation_target_distinct_count": 6,
                "validation_source_missing_target_count": 0 if empty else 1,
                "validation_unused_target_count": 6 if empty else 1,
                "validation_duplicate_target_key_count": 1,
                "source_null_key_row_count": 0 if empty else 2,
                "target_null_key_row_count": 1,
                "validation_result": "inconclusive" if empty else "unsupported",
            }
            AnalysisValidationEvidence.model_validate(
                {name: join[name] for name in AnalysisValidationEvidence.model_fields}
            )
