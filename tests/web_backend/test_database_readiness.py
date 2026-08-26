from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import LiteralString, cast

import pytest
from gds_etl_workbench.infrastructure.postgres import ReadinessRecord
from psycopg import sql

from gds_workbench_api.database import WebPostgresDatabase
from tests.mcp.conftest import DisposablePostgres, disposable_postgres


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
        ("list_model_object_eligibility", ("BIGINT",)),
        ("list_model_attribute_eligibility", ("BIGINT",)),
        ("list_code_generation_target_context", ("BIGINT", "VARCHAR")),
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
@pytest.mark.parametrize(
    "function_signature",
    [
        "mcp.create_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, UUID)",
        "mcp.stage_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, JSONB, UUID)",
        "mcp.get_metadata_change_set(UUID, UUID, VARCHAR, BIGINT, UUID)",
        "mcp.record_metadata_change_set_validation(UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, BOOLEAN, CHAR, JSONB, UUID, UUID)",
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
async def test_readiness_rejects_a_stale_workflow_run_model_foreign_key(
    readiness_postgres: DisposablePostgres,
) -> None:
    with readiness_postgres.connect_owner() as connection:
        connection.execute(
            "ALTER TABLE application.workflow_run "
            "RENAME CONSTRAINT fk_workflow_run_model "
            "TO stale_fk_workflow_run_model"
        )

    try:
        readiness = await _readiness(readiness_postgres)
    finally:
        with readiness_postgres.connect_owner() as connection:
            connection.execute(
                "ALTER TABLE application.workflow_run "
                "RENAME CONSTRAINT stale_fk_workflow_run_model "
                "TO fk_workflow_run_model"
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
                "UPDATE {} SET is_active = FALSE "
                "WHERE {} = (SELECT min({}) FROM {}) RETURNING {}"
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
