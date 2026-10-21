"""The operator's catalog-only diagnostic runs inside a read-only transaction."""

from collections.abc import Iterator
from pathlib import Path
from typing import Literal, LiteralString, cast

import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus

from tests.mcp.conftest import DisposablePostgres, disposable_postgres

CHECK_SQL = (
    Path(__file__).parents[2] / "deployment/databricks_ui/check_workflow_compatibility.sql"
).read_text(encoding="utf-8")
RENEW_SIGNATURE = "application.renew_workflow_run_claim(bigint,uuid,integer)"
PROFILING_EXECUTION_SIGNATURES: tuple[LiteralString, ...] = (
    "application.get_profiling_connection_values("
    "uuid,uuid,character varying,bigint,bigint,character varying)",
    "application.append_workflow_run_event("
    "uuid,uuid,character varying,bigint,bigint,bigint,integer,"
    "character varying,character varying,character varying,integer,integer,integer)",
    "application.persist_profiling_results(uuid,uuid,character varying,bigint,bigint,jsonb)",
    "application.complete_workflow_run(uuid,uuid,character varying,bigint,bigint,integer)",
)


@pytest.fixture(scope="module")
def compatibility_database() -> Iterator[DisposablePostgres]:
    yield from disposable_postgres()


def _check(database: DisposablePostgres, *, web_role: bool = False) -> dict[str, str]:
    with database.connect_owner() as connection:
        if web_role:
            connection.execute("SET ROLE gds_web_write")
        connection.commit()
        connection.autocommit = True
        cursor = connection.execute(cast(LiteralString, CHECK_SQL), prepare=False)
        results: dict[str, str] = {}
        while True:
            if cursor.description is not None:
                results.update((row["check_name"], row["status"]) for row in cursor.fetchall())
            if not cursor.nextset():
                break
        assert connection.info.transaction_status is TransactionStatus.IDLE
        return results


@pytest.mark.parametrize("web_role", [False, True])
def test_operator_check_accepts_current_workflow_contracts(
    compatibility_database: DisposablePostgres, web_role: bool
) -> None:
    assert _check(compatibility_database, web_role=web_role) == {"workflow_sql_checks": "PASS"}


@pytest.mark.parametrize(
    "signature", PROFILING_EXECUTION_SIGNATURES, ids=["connection", "event", "persist", "complete"]
)
@pytest.mark.parametrize("fault", ["missing", "grant", "security"])
def test_operator_check_requires_each_profiling_execution_function(
    compatibility_database: DisposablePostgres,
    signature: LiteralString,
    fault: Literal["missing", "grant", "security"],
) -> None:
    if fault == "missing":
        change = sql.SQL("ALTER FUNCTION {} RENAME TO fixture_renamed_profiling_function").format(
            sql.SQL(signature)
        )
        name, arguments = signature.split("(", 1)
        restore = sql.SQL(
            "ALTER FUNCTION application.fixture_renamed_profiling_function({} RENAME TO {}"
        ).format(sql.SQL(arguments), sql.Identifier(name.split(".")[1]))
        check = "function_exists"
    elif fault == "grant":
        change = sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(
            sql.SQL(signature)
        )
        restore = sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(
            sql.SQL(signature)
        )
        check = "web_execute_required"
    else:
        change = sql.SQL("ALTER FUNCTION {} SECURITY INVOKER").format(sql.SQL(signature))
        restore = sql.SQL("ALTER FUNCTION {} SECURITY DEFINER").format(sql.SQL(signature))
        check = "security_definer_and_safe_search_path"
    # Only mutate the fixture's disposable installation; never call these functions.
    with compatibility_database.connect_owner() as connection:
        connection.execute(change)
    try:
        results = _check(compatibility_database)
        assert results["workflow_sql_checks"] == "FAIL"
        assert results[signature + ": " + check] == "FAIL"
        assert all(value == "FAIL" for value in results.values())
    finally:
        with compatibility_database.connect_owner() as connection:
            connection.execute(restore)


def test_operator_check_names_stale_renewal_without_returning_definition(
    compatibility_database: DisposablePostgres,
) -> None:
    with compatibility_database.connect_owner() as connection:
        row = connection.execute(
            "SELECT pg_get_functiondef(to_regprocedure(%s)) AS definition", (RENEW_SIGNATURE,)
        ).fetchone()
        assert row is not None
        definition = row["definition"]
        assert "FOR NO KEY UPDATE OF run" in definition
        connection.execute(
            cast(LiteralString, definition.replace("FOR NO KEY UPDATE OF run", "FOR UPDATE OF run"))
        )
    try:
        assert _check(compatibility_database) == {
            "workflow_sql_checks": "FAIL",
            RENEW_SIGNATURE + ": required_workflow_fixes": "FAIL",
        }
    finally:
        with compatibility_database.connect_owner() as connection:
            connection.execute(cast(LiteralString, definition))


def test_operator_check_names_missing_runtime_permission(
    compatibility_database: DisposablePostgres,
) -> None:
    with compatibility_database.connect_owner() as connection:
        connection.execute(
            "REVOKE EXECUTE ON FUNCTION application.renew_workflow_run_claim(bigint,uuid,integer) "
            "FROM gds_web_write"
        )
    try:
        assert _check(compatibility_database) == {
            "workflow_sql_checks": "FAIL",
            RENEW_SIGNATURE + ": web_execute_required": "FAIL",
        }
    finally:
        with compatibility_database.connect_owner() as connection:
            connection.execute(
                "GRANT EXECUTE ON FUNCTION "
                "application.renew_workflow_run_claim(bigint,uuid,integer) "
                "TO gds_web_write"
            )


def test_operator_check_handles_a_missing_function_without_calling_it(
    compatibility_database: DisposablePostgres,
) -> None:
    with compatibility_database.connect_owner() as connection:
        connection.execute(
            "ALTER FUNCTION application.renew_workflow_run_claim(bigint,uuid,integer) "
            "RENAME TO fixture_renamed_renewal"
        )
    try:
        results = _check(compatibility_database)
        assert results["workflow_sql_checks"] == "FAIL"
        assert results[RENEW_SIGNATURE + ": function_exists"] == "FAIL"
        assert all(value == "FAIL" for value in results.values())
    finally:
        with compatibility_database.connect_owner() as connection:
            connection.execute(
                "ALTER FUNCTION application.fixture_renamed_renewal(bigint,uuid,integer) "
                "RENAME TO renew_workflow_run_claim"
            )


def test_operator_check_handles_missing_runtime_role(
    compatibility_database: DisposablePostgres,
) -> None:
    with compatibility_database.connect_owner() as connection:
        connection.execute("ALTER ROLE gds_web_write RENAME TO fixture_renamed_web_role")
    try:
        results = _check(compatibility_database)
        assert results["workflow_sql_checks"] == "FAIL"
        assert results["gds_web_write_role_exists"] == "FAIL"
    finally:
        with compatibility_database.connect_owner() as connection:
            connection.execute("ALTER ROLE fixture_renamed_web_role RENAME TO gds_web_write")


def test_operator_check_detects_missing_usage_column(
    compatibility_database: DisposablePostgres,
) -> None:
    with compatibility_database.connect_owner() as connection:
        connection.execute(
            "ALTER TABLE application.workflow_run_model_request "
            "RENAME COLUMN pricing_basis TO fixture_renamed_pricing_basis"
        )
    try:
        assert _check(compatibility_database) == {
            "workflow_sql_checks": "FAIL",
            "application.workflow_run_model_request.pricing_basis: expected_column_type": "FAIL",
        }
    finally:
        with compatibility_database.connect_owner() as connection:
            connection.execute(
                "ALTER TABLE application.workflow_run_model_request "
                "RENAME COLUMN fixture_renamed_pricing_basis TO pricing_basis"
            )
