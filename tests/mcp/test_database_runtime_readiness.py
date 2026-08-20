from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

import pytest
from psycopg.errors import RaiseException

if TYPE_CHECKING:
    from conftest import DisposablePostgres


RUNTIME_INTEGRITY_SQL = Path(__file__).parents[2] / "database" / "12_runtime_integrity.sql"
VERIFY_INSTALL_SQL = Path(__file__).parents[2] / "database" / "13_verify_install.sql"


def test_runtime_integrity_sql_can_repair_grants_and_recheck_an_install(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute("REVOKE USAGE ON SCHEMA model FROM gds_app_write")
        connection.execute(
            """
            GRANT gds_app_write TO gds_mcp_runtime
                WITH ADMIN TRUE, INHERIT TRUE, SET FALSE
            """
        )
        broken = connection.execute(
            """
            SELECT has_schema_privilege(
                       'gds_app_write', 'model', 'USAGE'
                   ) AS model_schema_usage,
                   membership.admin_option,
                   membership.inherit_option,
                   membership.set_option
              FROM pg_auth_members AS membership
              JOIN pg_roles AS member_role
                ON member_role.oid = membership.member
              JOIN pg_roles AS group_role
                ON group_role.oid = membership.roleid
             WHERE member_role.rolname = 'gds_mcp_runtime'
               AND group_role.rolname = 'gds_app_write'
            """
        ).fetchone()
        assert broken == {
            "model_schema_usage": False,
            "admin_option": True,
            "inherit_option": True,
            "set_option": False,
        }

        connection.execute(cast(LiteralString, RUNTIME_INTEGRITY_SQL.read_text(encoding="utf-8")))
        repaired = connection.execute(
            """
            SELECT has_schema_privilege(
                       'gds_app_write', 'model', 'USAGE'
                   ) AS model_schema_usage,
                   membership.admin_option,
                   membership.inherit_option,
                   membership.set_option
              FROM pg_auth_members AS membership
              JOIN pg_roles AS member_role
                ON member_role.oid = membership.member
              JOIN pg_roles AS group_role
                ON group_role.oid = membership.roleid
             WHERE member_role.rolname = 'gds_mcp_runtime'
               AND group_role.rolname = 'gds_app_write'
            """
        ).fetchone()

    assert repaired == {
        "model_schema_usage": True,
        "admin_option": False,
        "inherit_option": False,
        "set_option": True,
    }

    with postgres_database.connect_runtime() as connection:
        contract = connection.execute("SELECT * FROM mcp.runtime_readiness()").fetchone()

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
        contract = connection.execute("SELECT * FROM mcp.runtime_readiness()").fetchone()

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


@pytest.mark.asyncio
async def test_runtime_readiness_rejects_missing_runtime_schema_usage(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute("REVOKE USAGE ON SCHEMA model FROM gds_app_write")

    try:
        database = postgres_database.create_runtime_adapter()
        await database.open()
        try:
            readiness = await database.readiness()
        finally:
            await database.close()
    finally:
        with postgres_database.connect_owner() as connection:
            connection.execute("GRANT USAGE ON SCHEMA model TO gds_app_write")

    assert readiness.ready is False
    assert readiness.code == "database_role_invalid"


def test_verify_install_rejects_unsafe_runtime_membership_options(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="membership options"),
        connection.transaction(),
    ):
        connection.execute(
            """
            GRANT gds_app_write TO gds_mcp_runtime
                WITH ADMIN TRUE, INHERIT TRUE, SET TRUE
            """
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


def test_verify_install_rejects_missing_runtime_schema_usage(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="schema usage"),
        connection.transaction(),
    ):
        connection.execute("REVOKE USAGE ON SCHEMA model FROM gds_app_write")
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )
