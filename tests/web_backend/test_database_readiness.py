from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from gds_etl_workbench.infrastructure.postgres import ReadinessRecord
from gds_workbench_api.database import WebPostgresDatabase
from psycopg import sql
from psycopg.errors import InsufficientPrivilege

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.web_backend.test_database_workflow_compatibility_check import (
    _check,  # pyright: ignore[reportPrivateUsage]
)
from tests.web_backend.test_database_workflow_usage import (
    _run,  # pyright: ignore[reportPrivateUsage]
)

APPLICATION_REFERENCE_SEED = (
    Path(__file__).parents[2] / "database" / "seed" / "04_application_reference.sql"
)


@pytest.fixture(scope="module")
def readiness_postgres() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        with database.connect_owner() as connection:
            connection.execute(
                cast(
                    LiteralString,
                    APPLICATION_REFERENCE_SEED.read_text(encoding="utf-8"),
                )
            )
        yield database


@asynccontextmanager
async def _database(
    postgres_database: DisposablePostgres,
) -> AsyncGenerator[WebPostgresDatabase]:
    database = WebPostgresDatabase(
        dsn=postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        yield database
    finally:
        await database.close()


async def _readiness(postgres_database: DisposablePostgres) -> ReadinessRecord:
    async with _database(postgres_database) as database:
        return await database.readiness()


@pytest.mark.asyncio
async def test_readiness_accepts_a_random_fixture_login_with_exact_web_posture(
    readiness_postgres: DisposablePostgres,
) -> None:
    assert readiness_postgres.web_runtime_user != "gds_web_runtime"

    readiness = await _readiness(readiness_postgres)

    assert readiness == ReadinessRecord(ready=True, code="ready")


@pytest.mark.parametrize(
    "owner_posture",
    ["runtime_role", "column_privileges", "no_schema", "missing_select", "no_update"],
)
async def test_claim_definer_readiness_matches_real_row_lock_permissions(
    readiness_postgres: DisposablePostgres,
    owner_posture: str,
) -> None:
    _, claim, runtime = _run(readiness_postgres, workflow="profiling")
    role = sql.Identifier(
        "gds_web_write" if owner_posture == "runtime_role" else f"fixture_definer_{uuid4().hex}"
    )
    with readiness_postgres.connect_owner() as connection:
        row = connection.execute(
            "SELECT owner.rolname FROM pg_proc AS proc "
            "JOIN pg_roles AS owner ON owner.oid=proc.proowner "
            "WHERE proc.oid='application.assert_workflow_run_claim(bigint,uuid)'::regprocedure"
        ).fetchone()
        assert row is not None
        original_owner = sql.Identifier(str(row["rolname"]))
        if owner_posture != "runtime_role":
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(role))
            if owner_posture != "no_schema":
                connection.execute(sql.SQL("GRANT USAGE ON SCHEMA application TO {}").format(role))
            connection.execute(
                sql.SQL(
                    "GRANT SELECT (workflow_run_id, workflow_run_state, "
                    "workflow_run_claim_token_digest) ON application.workflow_run TO {}"
                ).format(role)
            )
            if owner_posture != "missing_select":
                connection.execute(
                    sql.SQL(
                        "GRANT SELECT (workflow_run_claim_expires_time) "
                        "ON application.workflow_run TO {}"
                    ).format(role)
                )
            if owner_posture != "no_update":
                # PostgreSQL permits FOR UPDATE with UPDATE on any one column,
                # including a column not referenced by the locking SELECT.
                connection.execute(
                    sql.SQL("GRANT UPDATE (created_by) ON application.workflow_run TO {}").format(
                        role
                    )
                )
        connection.execute(
            sql.SQL(
                "ALTER FUNCTION application.assert_workflow_run_claim(bigint,uuid) OWNER TO {}"
            ).format(role)
        )
    try:
        await runtime.open()
        ready = owner_posture == "column_privileges"
        readiness = await runtime.readiness()
        checks = _check(readiness_postgres)
        assert readiness == ReadinessRecord(
            ready=ready, code="ready" if ready else "database_role_invalid"
        )
        assert checks == (
            {"workflow_sql_checks": "PASS"}
            if ready
            else {
                "workflow_sql_checks": "FAIL",
                "application.assert_workflow_run_claim(bigint,uuid): definer_claim_access": "FAIL",
            }
        )
        # Test the same SQL row lock directly under the actual web role, without
        # changing Run data. The disposable connection rolls its lock back.
        with readiness_postgres.connect_owner() as connection:
            connection.execute("SET LOCAL ROLE gds_web_write")
            if ready:
                connection.execute(
                    "SELECT application.assert_workflow_run_claim(%s,%s)",
                    (claim.workflow_run_id, claim.workflow_run_claim_token),
                )
            else:
                with pytest.raises(InsufficientPrivilege):
                    connection.execute(
                        "SELECT application.assert_workflow_run_claim(%s,%s)",
                        (claim.workflow_run_id, claim.workflow_run_claim_token),
                    )
            connection.rollback()
    finally:
        await runtime.close()
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL(
                    "ALTER FUNCTION application.assert_workflow_run_claim(bigint,uuid) OWNER TO {}"
                ).format(original_owner)
            )
            # Restoring ownership from the runtime role removes its owner ACL.
            connection.execute(
                "GRANT EXECUTE ON FUNCTION application.assert_workflow_run_claim(bigint,uuid) "
                "TO gds_web_write"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signature",
    [
        "application.claim_next_workflow_run(integer)",
        "application.renew_workflow_run_claim(bigint,uuid,integer)",
        "application.release_workflow_run_claim(bigint,uuid)",
        "application.assert_workflow_run_claim(bigint,uuid)",
        "application.fail_workflow_run(uuid,uuid,character varying,bigint,bigint,"
        "character varying,character varying)",
    ],
)
async def test_readiness_requires_workflow_worker_execution_grants(
    readiness_postgres: DisposablePostgres,
    signature: LiteralString,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(sql.SQL(signature))
        )
    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(sql.SQL(signature))
            )
    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("signature", "current", "stale"),
    [
        (
            "application.renew_workflow_run_claim(bigint,uuid,integer)",
            "FOR NO KEY UPDATE OF run",
            "FOR UPDATE OF run",
        ),
        (
            "application.release_workflow_run_claim(bigint,uuid)",
            "PERFORM project.assert_writable(v_project_id);\n"
            "    v_released_time := clock_timestamp();",
            "v_released_time := clock_timestamp();\n"
            "    PERFORM project.assert_writable(v_project_id);",
        ),
        *[
            (
                "application." + name + "(uuid,uuid,character varying,bigint,bigint" + tail + ")",
                "FOR KEY SHARE OF run FOR SHARE OF target_project",
                "FOR SHARE OF run, target_project",
            )
            for name, tail in (
                ("get_profiling_execution_context", ""),
                ("get_analysis_validation_execution_context", ",character varying"),
                ("get_metadata_enrichment_execution_context", ""),
            )
        ],
    ],
)
async def test_readiness_rejects_installed_workflow_functions_without_lease_fixes(
    readiness_postgres: DisposablePostgres,
    signature: str,
    current: str,
    stale: str,
) -> None:
    # Alter only this fixture's disposable installation; restore its exact definition.
    with readiness_postgres.connect_owner() as connection:
        row = connection.execute(
            "SELECT pg_get_functiondef(to_regprocedure(%s)) AS definition", (signature,)
        ).fetchone()
        assert row is not None
        definition = row["definition"]
        assert isinstance(definition, str) and current in definition
        connection.execute(cast(LiteralString, definition.replace(current, stale)))
    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(cast(LiteralString, definition))
    assert readiness == ReadinessRecord(ready=False, code="database_schema_unavailable")


@pytest.mark.asyncio
async def test_readiness_rejects_an_unsafe_session_login_posture(
    readiness_postgres: DisposablePostgres,
) -> None:
    role = sql.Identifier(readiness_postgres.web_runtime_user)
    with readiness_postgres.connect_owner() as connection:
        connection.execute(sql.SQL("ALTER ROLE {} INHERIT").format(role))

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(sql.SQL("ALTER ROLE {} NOINHERIT").format(role))

    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
async def test_readiness_rejects_an_additional_session_login_membership(
    readiness_postgres: DisposablePostgres,
) -> None:
    role = sql.Identifier(readiness_postgres.web_runtime_user)
    with readiness_postgres.connect_owner() as connection:
        connection.execute(sql.SQL("GRANT gds_app_write TO {}").format(role))

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(sql.SQL("REVOKE gds_app_write FROM {}").format(role))

    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "argument_types"),
    [
        ("list_tenant_visible_objects", ("BIGINT",)),
        ("list_project_object_eligibility", ("BIGINT",)),
        ("list_project_attribute_eligibility", ("BIGINT",)),
        ("list_mapping_branches", ("BIGINT", "VARCHAR")),
        (
            "list_code_generation_target_context",
            ("BIGINT", "VARCHAR", "VARCHAR"),
        ),
    ],
)
async def test_readiness_rejects_a_missing_workflow_eligibility_grant(
    readiness_postgres: DisposablePostgres,
    function_name: str,
    argument_types: tuple[LiteralString, ...],
) -> None:
    signature = sql.SQL("workflow.{}({})").format(
        sql.Identifier(function_name),
        sql.SQL(", ").join(sql.SQL(value) for value in argument_types),
    )
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(
                signature
            )
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(
                    signature
                )
            )

    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
async def test_readiness_requires_governed_project_review_function(
    readiness_postgres: DisposablePostgres,
) -> None:
    assert (await _readiness(readiness_postgres)).ready
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            "REVOKE EXECUTE ON FUNCTION application.authorize_project_record_review("
            "UUID,UUID,VARCHAR,BIGINT,BIGINT) FROM gds_web_write"
        )
    try:
        readiness = await _readiness(readiness_postgres)
        assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                "GRANT EXECUTE ON FUNCTION application.authorize_project_record_review("
                "UUID,UUID,VARCHAR,BIGINT,BIGINT) TO gds_web_write"
            )
    assert (await _readiness(readiness_postgres)).ready


@pytest.mark.asyncio
async def test_readiness_rejects_a_missing_profiling_context_grant(
    readiness_postgres: DisposablePostgres,
) -> None:
    signature = "application.get_profiling_execution_context(UUID, UUID, VARCHAR, BIGINT, BIGINT)"
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(
                sql.SQL(cast(LiteralString, signature))
            )
        )

    try:
        readiness = await _readiness(readiness_postgres)

        with (
            psycopg.connect(readiness_postgres.web_runtime_dsn()) as connection,
            pytest.raises(InsufficientPrivilege),
            connection.transaction(),
        ):
            connection.execute("SET LOCAL ROLE gds_web_write")
            connection.execute(
                "SELECT * FROM application.get_profiling_execution_context(%s, %s, %s, %s, %s)",
                (
                    UUID("00000000-0000-0000-0000-000000000001"),
                    UUID("00000000-0000-0000-0000-000000000002"),
                    "service_principal",
                    1,
                    1,
                ),
            ).fetchall()
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(
                    sql.SQL(cast(LiteralString, signature))
                )
            )

    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function_signature",
    [
        "mcp.create_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, UUID)",
        "mcp.stage_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, JSONB, UUID)",
        "mcp.get_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID)",
        "mcp.record_metadata_change_set_validation("
        "UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, BOOLEAN, CHAR, JSONB, UUID, UUID)",
        "mcp.apply_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, CHAR, UUID)",
        "mcp.archive_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, UUID)",
    ],
)
async def test_readiness_rejects_a_missing_governed_metadata_grant(
    readiness_postgres: DisposablePostgres,
    function_signature: str,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(
                sql.SQL(cast(LiteralString, function_signature))
            )
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(
                    sql.SQL(cast(LiteralString, function_signature))
                )
            )

    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function_signature",
    [
        "mcp.get_databricks_sql_connection_values(BIGINT, TEXT)",
        "mcp.runtime_readiness()",
    ],
)
async def test_readiness_rejects_unlisted_web_mcp_function_access(
    readiness_postgres: DisposablePostgres,
    function_signature: str,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION {} TO gds_web_write").format(
                sql.SQL(cast(LiteralString, function_signature))
            )
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(
                    sql.SQL(cast(LiteralString, function_signature))
                )
            )

    assert readiness == ReadinessRecord(ready=False, code="database_role_invalid")


@pytest.mark.asyncio
async def test_readiness_rejects_a_nullable_workflow_run_tenant_witness(
    readiness_postgres: DisposablePostgres,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            "ALTER TABLE application.workflow_run ALTER COLUMN tenant_id DROP NOT NULL"
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                "ALTER TABLE application.workflow_run ALTER COLUMN tenant_id SET NOT NULL"
            )

    assert readiness == ReadinessRecord(
        ready=False,
        code="database_schema_unavailable",
    )


@pytest.mark.asyncio
async def test_readiness_rejects_a_stale_workflow_run_project_foreign_key(
    readiness_postgres: DisposablePostgres,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            "ALTER TABLE application.workflow_run "
            "RENAME CONSTRAINT fk_workflow_run_project "
            "TO stale_fk_workflow_run_project"
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                "ALTER TABLE application.workflow_run "
                "RENAME CONSTRAINT stale_fk_workflow_run_project "
                "TO fk_workflow_run_project"
            )

    assert readiness == ReadinessRecord(
        ready=False,
        code="database_schema_unavailable",
    )


@pytest.mark.asyncio
async def test_readiness_rejects_a_stale_tenant_running_workflow_index(
    readiness_postgres: DisposablePostgres,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            "ALTER INDEX application.uq_workflow_run_running_tenant "
            "RENAME TO stale_uq_workflow_run_running_tenant"
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                "ALTER INDEX application.stale_uq_workflow_run_running_tenant "
                "RENAME TO uq_workflow_run_running_tenant"
            )

    assert readiness == ReadinessRecord(
        ready=False,
        code="database_schema_unavailable",
    )


@pytest.mark.asyncio
async def test_readiness_rejects_a_stale_workflow_start_function(
    readiness_postgres: DisposablePostgres,
) -> None:
    signature = "(UUID, UUID, VARCHAR, BIGINT, BIGINT)"
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            "ALTER FUNCTION application.start_workflow_run"
            f"{signature} RENAME TO stale_start_workflow_run"
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                "ALTER FUNCTION application.stale_start_workflow_run"
                f"{signature} RENAME TO start_workflow_run"
            )

    assert readiness == ReadinessRecord(
        ready=False,
        code="database_schema_unavailable",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("table_name", "identity_column"),
    [
        ("workflow_stage", "workflow_stage_id"),
        ("workflow_stage_variable", "workflow_stage_variable_id"),
    ],
)
async def test_readiness_rejects_inactive_required_application_reference_data(
    readiness_postgres: DisposablePostgres,
    table_name: str,
    identity_column: str,
) -> None:
    table = sql.Identifier("application", table_name)
    identity = sql.Identifier(identity_column)
    with readiness_postgres.connect_owner() as connection:
        row = connection.execute(
            sql.SQL(
                "UPDATE {} SET is_active = FALSE WHERE {} = (SELECT min({}) FROM {}) RETURNING {}"
            ).format(table, identity, identity, table, identity)
        ).fetchone()
    assert row is not None

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET is_active = TRUE WHERE {} = %s").format(
                    table,
                    identity,
                ),
                (row[identity_column],),
            )

    assert readiness == ReadinessRecord(
        ready=False,
        code="database_schema_unavailable",
    )
