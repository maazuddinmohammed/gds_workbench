from __future__ import annotations

import pytest

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.tools.databricks.validation import (
    DatabricksStatementKind,
    validate_databricks_sql,
)


def test_validation_accepts_multistatement_read_and_temporary_objects() -> None:
    result = validate_databricks_sql(
        """
        CREATE OR REPLACE TEMP VIEW recent_orders AS
        SELECT * FROM catalog.sales.orders WHERE note = 'keep;inside';
        CREATE TEMP TABLE order_totals AS
        SELECT customer_id, sum(amount) AS amount
          FROM recent_orders
         GROUP BY customer_id;
        WITH ranked AS (
            SELECT *, row_number() OVER (ORDER BY amount DESC) AS position
              FROM order_totals
        )
        SELECT * FROM ranked WHERE position <= 50;
        """
    )

    assert [statement.kind for statement in result.statements] == [
        DatabricksStatementKind.TEMPORARY_DDL,
        DatabricksStatementKind.TEMPORARY_DDL,
        DatabricksStatementKind.READ,
    ]
    assert "'keep;inside'" in result.statements[0].sql
    assert result.final_returns_rows is True


def test_validation_preserves_comments_and_ignores_their_semicolons() -> None:
    result = validate_databricks_sql(
        "SELECT 1; -- this ; stays in the comment\nSELECT 2 /* and ; this one */;"
    )

    assert len(result.statements) == 2
    assert result.statements[1].sql.startswith("-- this ; stays in the comment")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "VALUES (1), (2)",
        "SHOW TABLES",
        "DESCRIBE TABLE catalog.schema.orders",
        "SELECT 1 UNION ALL SELECT 2",
    ],
)
def test_validation_accepts_read_statements(sql: str) -> None:
    result = validate_databricks_sql(sql)

    assert result.statements[0].kind is DatabricksStatementKind.READ
    assert result.final_returns_rows is True


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "SELECT * FROM sales.orders",
        "DESCRIBE TABLE sales.orders",
        ("CREATE TEMP VIEW recent_orders AS SELECT * FROM sales.orders"),
    ],
)
def test_validation_rejects_unqualified_physical_relations(sql: str) -> None:
    with pytest.raises(
        InvalidRequestError,
        match="Statement 1 must fully qualify physical relations",
    ):
        validate_databricks_sql(sql)


def test_validation_allows_unqualified_ctes_and_batch_temporary_relations() -> None:
    result = validate_databricks_sql(
        """
        CREATE TEMP VIEW recent_orders AS
        SELECT * FROM catalog.sales.orders;
        WITH ranked AS (
            SELECT * FROM recent_orders
        )
        SELECT * FROM ranked;
        """
    )

    assert len(result.statements) == 2


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET status = 'done'",
        "DELETE FROM orders",
        "MERGE INTO orders USING updates ON orders.id = updates.id WHEN MATCHED THEN UPDATE SET *",
        "COPY INTO orders FROM '/Volumes/files'",
        "INSERT INTO temporary_orders VALUES (1)",
    ],
)
def test_validation_rejects_all_dml(sql: str) -> None:
    with pytest.raises(InvalidRequestError, match="Statement 1 is not allowed"):
        validate_databricks_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE orders AS SELECT 1",
        "CREATE OR REPLACE VIEW orders AS SELECT 1",
        "DROP TABLE orders",
        "DROP TEMP VIEW recent_orders",
        "ALTER TABLE orders ADD COLUMN note STRING",
        "TRUNCATE TABLE orders",
    ],
)
def test_validation_rejects_persistent_and_other_ddl(sql: str) -> None:
    with pytest.raises(InvalidRequestError, match="Statement 1 is not allowed"):
        validate_databricks_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TEMP VIEW catalog.schema.recent_orders AS SELECT 1",
        "CREATE TEMP TABLE schema.recent_orders AS SELECT 1",
        "CREATE GLOBAL TEMP VIEW recent_orders AS SELECT 1",
        "CREATE TEMP FUNCTION normalize AS 'example.Class'",
        "CREATE TEMP TABLE recent_orders USING CSV LOCATION '/tmp/orders' AS SELECT 1",
    ],
)
def test_validation_rejects_unsafe_temporary_objects(sql: str) -> None:
    with pytest.raises(InvalidRequestError, match="Statement 1"):
        validate_databricks_sql(sql)


def test_validation_rejects_select_into() -> None:
    with pytest.raises(InvalidRequestError, match="Statement 1 is not allowed"):
        validate_databricks_sql("SELECT * INTO copied_orders FROM orders")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT secret('scope', 'key')",
        "SELECT try_secret('scope', 'key')",
        "CREATE TEMP VIEW exposed AS SELECT secret('scope', 'key')",
    ],
)
def test_validation_rejects_secret_returning_functions(sql: str) -> None:
    with pytest.raises(InvalidRequestError, match="Statement 1 is not allowed"):
        validate_databricks_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "USE CATALOG production",
        "SET spark.sql.ansi.enabled = false",
        "CALL system.example()",
        "GRANT SELECT ON TABLE orders TO user@example.com",
        "EXPLAIN SELECT 1",
    ],
)
def test_validation_rejects_non_read_commands(sql: str) -> None:
    with pytest.raises(InvalidRequestError, match="Statement 1 is not allowed"):
        validate_databricks_sql(sql)


@pytest.mark.parametrize("sql", ["", "  ; -- comment only\n ; "])
def test_validation_rejects_empty_batches(sql: str) -> None:
    with pytest.raises(InvalidRequestError, match="at least one SQL statement"):
        validate_databricks_sql(sql)


def test_validation_rejects_more_than_25_statements() -> None:
    sql = ";".join("SELECT 1" for _ in range(26))

    with pytest.raises(InvalidRequestError, match="at most 25 SQL statements"):
        validate_databricks_sql(sql)


def test_validation_returns_safe_syntax_location() -> None:
    with pytest.raises(
        InvalidRequestError,
        match=r"Statement 1 has invalid Databricks SQL syntax near line 1, column \d+",
    ) as failure:
        validate_databricks_sql("SELECT FROM")

    assert "SELECT FROM" not in str(failure.value)


def test_validation_never_logs_submitted_sql(caplog: pytest.LogCaptureFixture) -> None:
    submitted_sql = "CREATE UNSUPPORTED secret_bearing_name"

    with pytest.raises(InvalidRequestError):
        validate_databricks_sql(submitted_sql)

    assert submitted_sql not in caplog.text
    assert "secret_bearing_name" not in caplog.text


def test_validation_does_not_reserialize_temporary_table_sql() -> None:
    sql = "CREATE OR REPLACE TEMP TABLE recent_orders AS SELECT 1"

    result = validate_databricks_sql(sql)

    assert result.statements[0].sql == sql
    assert result.final_returns_rows is False
