"""Usage owner diagnostics need catalog access only and reveal no role or Run data."""

# pyright: reportPrivateUsage=false
from collections.abc import Iterator
from pathlib import Path
from typing import Any, LiteralString, cast

import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.web_backend.test_database_workflow_compatibility_check import _check

INSPECT_SQL = (
    Path(__file__).parents[2] / "deployment/databricks_ui/inspect_workflow_startup_access.sql"
).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def startup_access_database() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        with database.connect_owner() as connection:
            connection.execute("CREATE ROLE fixture_startup_catalog_reader NOLOGIN")
            connection.execute(
                "GRANT USAGE ON SCHEMA application, project, security "
                "TO fixture_startup_catalog_reader"
            )
        yield database


def _inspect(database: DisposablePostgres) -> dict[str, dict[str, Any]]:
    with database.connect_owner() as connection:
        connection.execute("SET ROLE fixture_startup_catalog_reader")
        assert connection.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM pg_proc AS proc "
            "JOIN pg_namespace AS namespace ON namespace.oid=proc.pronamespace "
            "WHERE namespace.nspname='application' "
            "AND has_function_privilege(current_user,proc.oid,'EXECUTE')) AS no_functions, "
            "NOT has_table_privilege(current_user,'application.workflow_run','SELECT') "
            "AS no_run_read"
        ).fetchone() == {"no_functions": True, "no_run_read": True}
        connection.commit()
        connection.autocommit = True
        cursor = connection.execute(cast(LiteralString, INSPECT_SQL), prepare=False)
        results: dict[str, dict[str, Any]] = {}
        while True:
            if cursor.description is not None:
                for row in cursor.fetchall():
                    assert set(row) == {"function_name", "access_ok", "failed_checks"}
                    assert isinstance(row["access_ok"], bool)
                    results[row["function_name"]] = row
            if not cursor.nextset():
                break
        assert connection.info.transaction_status is TransactionStatus.IDLE
        assert set(results) == {"begin_usage", "usage_binding"}
        return results


def test_current_usage_owners_pass_without_application_execution_or_data_access(
    startup_access_database: DisposablePostgres,
) -> None:
    results = _inspect(startup_access_database)
    assert all(row["access_ok"] and row["failed_checks"] == [] for row in results.values())


@pytest.mark.parametrize(
    ("function_name", "function_sql", "failed_checks"),
    [
        (
            "begin_usage",
            "application.begin_workflow_run_usage",
            ["nested_execute", "usage_update"],
        ),
        (
            "usage_binding",
            "application.assert_workflow_run_usage_binding",
            ["project_row_lock"],
        ),
    ],
)
def test_owner_fault_is_detected_when_existing_workflow_checks_pass(
    startup_access_database: DisposablePostgres,
    function_name: str,
    function_sql: LiteralString,
    failed_checks: list[str],
) -> None:
    signature = function_sql + "(uuid,uuid,character varying,bigint,bigint,uuid)"
    with startup_access_database.connect_owner() as connection:
        original = connection.execute(
            "SELECT owner.rolname FROM pg_proc AS proc "
            "JOIN pg_roles AS owner ON owner.oid=proc.proowner "
            "WHERE proc.oid=to_regprocedure(%s)",
            (signature,),
        ).fetchone()
        assert original is not None
        owner = "gds_web_write"
        if function_name == "usage_binding":
            owner = "fixture_usage_definer_without_lock"
            connection.execute("CREATE ROLE fixture_usage_definer_without_lock NOLOGIN")
            connection.execute(
                "GRANT USAGE ON SCHEMA application, project, security "
                "TO fixture_usage_definer_without_lock"
            )
            connection.execute(
                "GRANT SELECT ON application.workflow_run TO fixture_usage_definer_without_lock"
            )
            connection.execute(
                "GRANT SELECT (project_id, tenant_id, is_active, project_revision) "
                "ON project.project TO fixture_usage_definer_without_lock"
            )
            connection.execute(
                "GRANT EXECUTE ON FUNCTION application.assert_workflow_run_claim(bigint,uuid), "
                "security.authorize_tenant_operation(uuid,uuid,character varying,bigint,"
                "character varying) TO fixture_usage_definer_without_lock"
            )
        connection.execute(
            sql.SQL("ALTER FUNCTION {} OWNER TO {}").format(
                sql.SQL(signature), sql.Identifier(owner)
            )
        )
    try:
        assert _check(startup_access_database) == {"workflow_sql_checks": "PASS"}
        results = _inspect(startup_access_database)
        assert results[function_name] == {
            "function_name": function_name,
            "access_ok": False,
            "failed_checks": failed_checks,
        }
        assert all(row["access_ok"] for name, row in results.items() if name != function_name)
    finally:
        with startup_access_database.connect_owner() as connection:
            connection.execute(
                sql.SQL("ALTER FUNCTION {} OWNER TO {}").format(
                    sql.SQL(signature), sql.Identifier(original["rolname"])
                )
            )
            if function_name == "begin_usage":
                connection.execute(
                    sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(
                        sql.SQL(signature)
                    )
                )
