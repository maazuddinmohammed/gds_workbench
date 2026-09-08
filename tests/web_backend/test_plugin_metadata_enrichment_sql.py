"""Offline plugin aggregate-only SQL probe; no Databricks or physical sample outputs.

SQLGlot translates the static template; PostgreSQL TRY_CAST is emulated with
pg_input_is_valid, and regexp_extract uses PostgreSQL's equivalent capture API.
The Java whitespace expression maps to PostgreSQL btrim with the same characters.
This probes aggregate logic, not every Databricks timestamp-parser behavior.
"""

from pathlib import Path
from typing import LiteralString, cast

import pytest
import sqlglot
from gds_etl_workbench.domain.databricks_sql import (
    DatabricksStatementKind,
    validate_databricks_sql,
)
from gds_workbench_api.features.metadata_enrichment.inference import infer_sample_data_type
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlglot import exp
from sqlglot.expressions.core import Expression

from tests.mcp.conftest import (
    DisposablePostgres,
)
from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.mcp.database_test_support import require_row

_TEMPLATE = (
    Path(__file__).parents[2]
    / "plugins/v2/gds/skills/gds/references/examples/metadata-enrichment-type-evidence.sql"
)


def _offline_statement() -> sql.SQL:
    expression = sqlglot.parse_one(_TEMPLATE.read_text(), read="databricks")

    def postgres_equivalent(node: Expression) -> Expression:
        if isinstance(node, exp.RegexpReplace) and "javaWhitespace" in node.expression.this:
            assert node.expression.this == (
                r"^[\p{javaWhitespace}\u0085\u00a0\u2007\u202f]+|"
                r"[\p{javaWhitespace}\u0085\u00a0\u2007\u202f]+$"
            )
            return exp.Anonymous(
                this="btrim",
                expressions=[
                    node.this.copy(),
                    exp.Literal.string(
                        "".join(chr(code) for code in range(0x3001) if chr(code).isspace())
                    ),
                ],
            )
        if isinstance(node, exp.TryCast):
            value = node.this.transform(postgres_equivalent)
            target = node.args["to"].copy()
            return (
                exp.Case()
                .when(
                    exp.Anonymous(
                        this="pg_input_is_valid",
                        expressions=[
                            value.copy(),
                            exp.Literal.string(target.sql(dialect="postgres")),
                        ],
                    ),
                    exp.Cast(this=value, to=target),
                )
                .else_(exp.Null())
            )
        if isinstance(node, exp.RegexpExtract):
            return exp.Anonymous(
                this="regexp_substr",
                expressions=[
                    node.this.copy(),
                    node.expression.copy(),
                    exp.Literal.number(1),
                    exp.Literal.number(1),
                    exp.Literal.string(""),
                    node.args["group"].copy(),
                ],
            )
        return node

    expression = expression.transform(postgres_equivalent)
    sample = next(cte for cte in expression.find_all(exp.CTE) if cte.alias_or_name == "sample")
    sample.set(
        "this",
        sqlglot.parse_one(
            "SELECT value FROM jsonb_array_elements_text(%s::JSONB) "
            "WITH ORDINALITY AS fixture(value, ordinal) "
            "WHERE value IS NOT NULL ORDER BY ordinal LIMIT 50",
            read="postgres",
        ),
    )
    # Only this static template and fixed emulation expressions supply SQL text.
    return sql.SQL(cast(LiteralString, expression.sql(dialect="postgres")))


def test_template_is_one_governed_read_with_only_type_and_count() -> None:
    text = _TEMPLATE.read_text()
    validated = validate_databricks_sql(text)
    assert validated.final_returns_rows
    assert len(validated.statements) == 1
    assert validated.statements[0].kind is DatabricksStatementKind.READ
    expression = sqlglot.parse_one(text, read="databricks")
    assert isinstance(expression, exp.Select)
    assert [column.alias_or_name for column in expression.expressions] == [
        "inferred_data_type",
        "sample_count",
    ]
    sample = next(cte for cte in expression.find_all(exp.CTE) if cte.alias_or_name == "sample")
    assert sample.this.args["limit"].expression.this == "50"
    assert len(list(sample.find_all(exp.Table))) == 1


@pytest.mark.parametrize(
    ("samples", "expected"),
    [
        pytest.param([], None, id="empty"),
        pytest.param([None, "", "   "], None, id="null_blank"),
        pytest.param(["\t\r\n"], None, id="control_whitespace_blank"),
        pytest.param(["\t7\r\n"], "BIGINT", id="control_whitespace_number"),
        pytest.param(["\u0085\u00a0\u20077\u202f\u3000"], "BIGINT", id="unicode_whitespace"),
        pytest.param([" 7 ", None, ""], "BIGINT", id="trim_null_blank"),
        pytest.param(["true", "FALSE"], "BOOLEAN", id="boolean_words"),
        pytest.param(["true", "1"], "STRING", id="boolean_numeric_mix"),
        pytest.param(["001", "2"], "STRING", id="leading_zero"),
        pytest.param(["-001"], "STRING", id="negative_leading_zero"),
        pytest.param(["00.1"], "STRING", id="decimal_leading_zero"),
        pytest.param(["0.1", ".2"], "DECIMAL(1,1)", id="decimal_fraction"),
        pytest.param(
            ["-9223372036854775808", "9223372036854775807"], "BIGINT", id="signed64_bounds"
        ),
        pytest.param(["9223372036854775808"], "DECIMAL(19,0)", id="signed64_overflow"),
        pytest.param(["9" * 38], "DECIMAL(38,0)", id="decimal38_integer"),
        pytest.param(["9" * 39], "STRING", id="decimal39_overflow"),
        pytest.param(["9" * 35 + ".123"], "DECIMAL(38,3)", id="decimal38_exact"),
        pytest.param(["9" * 35 + ".123", ".1234"], "STRING", id="decimal_union_overflow"),
        pytest.param(["999.1", ".123"], "DECIMAL(6,3)", id="decimal_union"),
        pytest.param(["0.00"], "DECIMAL(2,2)", id="decimal_zero_scale"),
        pytest.param(["100e-2"], "DECIMAL(3,2)", id="decimal_exponent_retained_scale"),
        pytest.param(["1e37"], "DECIMAL(38,0)", id="exponent38_precision"),
        pytest.param(["1e38"], "STRING", id="exponent39_precision_overflow"),
        pytest.param(["1e-38"], "DECIMAL(38,38)", id="exponent38_scale"),
        pytest.param(["1e-39"], "STRING", id="exponent39_scale_overflow"),
        pytest.param(["0.00001e39"], "DECIMAL(35,0)", id="large_exponent_small_mantissa"),
        pytest.param(["1e" + "9" * 30], "STRING", id="huge_exponent"),
        pytest.param(["NaN", "Infinity"], "STRING", id="nonfinite"),
        pytest.param(["12", "abc"], "STRING", id="mixed_values"),
        pytest.param(["2024-02-29", "2024-01-31"], "DATE", id="iso_dates"),
        pytest.param(["2023-02-29"], "STRING", id="invalid_leap_date"),
        pytest.param(["2024-13-01"], "STRING", id="invalid_month"),
        pytest.param(["01/02/2024"], "STRING", id="non_iso_date"),
        pytest.param(["2024-01-01T12:30:00.123456"], "TIMESTAMP_NTZ", id="naive_timestamp"),
        pytest.param(["2024-01-01", "2024-01-02 12:30:00"], "TIMESTAMP_NTZ", id="date_naive_union"),
        pytest.param(
            ["2024-01-01T12:30:00Z", "2024-01-01T12:30:00+05:30"], "TIMESTAMP", id="zoned_union"
        ),
        pytest.param(
            ["2024-01-01T12:30:00", "2024-01-01T12:30:00Z"], "STRING", id="naive_zoned_mix"
        ),
        pytest.param(["2024-01-01", "2024-01-01T12:30:00Z"], "STRING", id="date_zoned_mix"),
        pytest.param(["2024-01-01T99:30:00"], "STRING", id="invalid_timestamp"),
        pytest.param(["2024-01-01T24:00:00"], "STRING", id="timestamp_hour_rollover"),
        pytest.param(["2024-01-01T12:30:60"], "STRING", id="timestamp_second_rollover"),
        pytest.param(["2024-01-01T12:30:00.1234567"], "STRING", id="timestamp_precision_overflow"),
        pytest.param(["1"] * 50 + ["abc"], "BIGINT", id="sample_cap"),
    ],
)
def test_aggregate_type_matches_conservative_backend(
    bootstrap_postgres_database: DisposablePostgres,
    samples: list[str | None],
    expected: str | None,
) -> None:
    selected = [sample for sample in samples if sample is not None][:50]
    assert infer_sample_data_type(selected) == expected
    with bootstrap_postgres_database.connect_owner() as connection:
        result = require_row(connection.execute(_offline_statement(), (Jsonb(samples),)).fetchone())
    assert set(result) == {"inferred_data_type", "sample_count"}
    assert result["inferred_data_type"] == expected
    assert result["sample_count"] == len([sample for sample in selected if sample.strip()])
    assert result["sample_count"] <= 50
