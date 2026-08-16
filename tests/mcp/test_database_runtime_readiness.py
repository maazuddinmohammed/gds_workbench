from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres


RUNTIME_INTEGRITY_SQL = (
    Path(__file__).parents[2] / "database" / "12_runtime_integrity.sql"
)


def test_runtime_integrity_sql_can_repair_grants_and_recheck_an_install(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            cast(LiteralString, RUNTIME_INTEGRITY_SQL.read_text(encoding="utf-8"))
        )

    with postgres_database.connect_runtime() as connection:
        contract = connection.execute(
            "SELECT * FROM mcp.runtime_readiness()"
        ).fetchone()

    assert contract is not None
    assert contract["runtime_role_ok"] is True
    assert contract["runtime_privileges_ok"] is True
    assert contract["runtime_query_contract_ok"] is True


@pytest.mark.asyncio
async def test_runtime_readiness_checks_the_complete_mcp_database_contract(
    postgres_database: DisposablePostgres,
) -> None:
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        readiness = await database.readiness()
    finally:
        await database.close()

    assert readiness.ready is True
    assert readiness.code == "ready"

    with postgres_database.connect_runtime() as connection:
        contract = connection.execute(
            "SELECT * FROM mcp.runtime_readiness()"
        ).fetchone()

    assert contract == {
        "schema_version": "1.0.0",
        "postgres_major": 18,
        "schema_shape_ok": True,
        "runtime_role_ok": True,
        "runtime_privileges_ok": True,
        "runtime_query_contract_ok": True,
    }


@pytest.mark.asyncio
async def test_runtime_readiness_rejects_the_old_discovery_connection_column(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            ALTER TABLE core.tenant_metadata_discovery_scope
            RENAME COLUMN gds_connection_id TO connection_id
            """
        )

    try:
        database = postgres_database.create_runtime_adapter()
        await database.open()
        try:
            readiness = await database.readiness()
        finally:
            await database.close()
    finally:
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                ALTER TABLE core.tenant_metadata_discovery_scope
                RENAME COLUMN connection_id TO gds_connection_id
                """
            )

    assert readiness.ready is False
    assert readiness.code == "database_schema_unavailable"


@pytest.mark.asyncio
async def test_runtime_readiness_rejects_a_missing_governed_function_grant(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            REVOKE EXECUTE ON FUNCTION security.check_tenant_lock(
                UUID, UUID, VARCHAR, BIGINT
            ) FROM gds_app_write
            """
        )

    try:
        database = postgres_database.create_runtime_adapter()
        await database.open()
        try:
            readiness = await database.readiness()
        finally:
            await database.close()
    finally:
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                GRANT EXECUTE ON FUNCTION security.check_tenant_lock(
                    UUID, UUID, VARCHAR, BIGINT
                ) TO gds_app_write
                """
            )

    assert readiness.ready is False
    assert readiness.code == "database_role_invalid"
