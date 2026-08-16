from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import psycopg
import pytest
from mcp import Client

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.configuration import AuthMode, Environment, RuntimeSettings
from gds_etl_workbench.domain.authorization import ActorKind, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ToolCallLogRecord

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@pytest.mark.asyncio
async def test_list_tenants_call_appends_audit_row_end_to_end(
    postgres_database: DisposablePostgres,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = RuntimeSettings(
        environment=Environment.LOCAL,
        auth_mode=AuthMode.DEV,
        database_dsn="postgresql://unused.invalid/workbench",
        cursor_signing_key=b"development-only-key-32-bytes-long",
        allowed_hosts=("testserver",),
        mcp_public_url="https://workbench.example.test/mcp",
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_api_client_id=UUID("22222222-2222-2222-2222-222222222222"),
        require_https=False,
        schema_version="1.0.0",
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
        metadata_snapshot_storage_account_url=(
            "https://snapshot.blob.core.windows.net"
        ),
        metadata_snapshot_storage_container="snapshots",
        metadata_snapshot_download_ttl_seconds=900,
        metadata_snapshot_retention_hours=24,
        metadata_snapshot_max_archive_bytes=268435456,
        metadata_snapshot_managed_identity_client_id=None,
    )
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        result = await client.call_tool("list_tenants", {"page_size": 137})

    assert result.is_error is False
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT principal_id,
                   principal_display_name,
                   actor_kind,
                   tool_name,
                   tool_policy,
                   input_metadata,
                   tool_call_status,
                   failure_code
              FROM mcp.tool_call_log
             WHERE actor_kind = 'development'
               AND input_metadata = '{"schema_version":"1.0","page_size":137,
                                      "cursor_provided":false}'::JSONB
             ORDER BY tool_call_time DESC
             LIMIT 1
            """
        ).fetchone()

    assert row == {
        "principal_id": None,
        "principal_display_name": "Local Developer",
        "actor_kind": "development",
        "tool_name": "list_tenants",
        "tool_policy": "tenant_read",
        "input_metadata": {
            "schema_version": "1.0",
            "page_size": 137,
            "cursor_provided": False,
        },
        "tool_call_status": "succeeded",
        "failure_code": None,
    }


@pytest.mark.asyncio
async def test_runtime_adapter_can_append_a_tool_call_log(
    postgres_database: DisposablePostgres,
) -> None:
    tool_call_id = UUID("40000000-0000-0000-0000-000000000001")
    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Tool Log Human', 'tool.log.human@example.test')
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        await database.append_tool_call_log(
            ToolCallLogRecord(
                tool_call_id=tool_call_id,
                principal_id=principal["principal_id"],
                principal_display_name="Tool Log Human",
                actor_kind=ActorKind.HUMAN,
                tool_name="list_tenants",
                tool_policy=ToolPolicy.TENANT_READ,
                tenant_id=None,
                input_metadata={"page_size": 50},
                status="succeeded",
                failure_code=None,
            )
        )
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT principal_id,
                   principal_display_name,
                   actor_kind,
                   tool_name,
                   tool_policy,
                   tenant_id,
                   input_metadata,
                   tool_call_status,
                   failure_code,
                   tool_call_time IS NOT NULL AS has_timestamp
              FROM mcp.tool_call_log
             WHERE tool_call_id = %s
            """,
            (tool_call_id,),
        ).fetchone()
        privileges = connection.execute(
            """
            SELECT has_table_privilege(
                       'gds_app_write',
                       'mcp.tool_call_log',
                       'INSERT'
                   ) AS can_insert,
                   has_table_privilege(
                       'gds_app_write',
                       'mcp.tool_call_log',
                       'UPDATE'
                   )
                   OR has_table_privilege(
                       'gds_app_write',
                       'mcp.tool_call_log',
                       'DELETE'
                   )
                   OR has_table_privilege(
                       'gds_app_write',
                       'mcp.tool_call_log',
                       'TRUNCATE'
                   ) AS can_mutate
            """
        ).fetchone()

    assert row == {
        "principal_id": principal["principal_id"],
        "principal_display_name": "Tool Log Human",
        "actor_kind": "human",
        "tool_name": "list_tenants",
        "tool_policy": "tenant_read",
        "tenant_id": None,
        "input_metadata": {"page_size": 50},
        "tool_call_status": "succeeded",
        "failure_code": None,
        "has_timestamp": True,
    }
    assert privileges == {"can_insert": True, "can_mutate": False}


@pytest.mark.asyncio
async def test_runtime_adapter_retains_complete_databricks_sql(
    postgres_database: DisposablePostgres,
) -> None:
    tool_call_id = UUID("40000000-0000-0000-0000-000000000004")
    sql = "SELECT '" + ("x" * 99_991) + "'"
    assert len(sql) == 100_000

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        await database.append_tool_call_log(
            ToolCallLogRecord(
                tool_call_id=tool_call_id,
                principal_id=None,
                principal_display_name="Local Developer",
                actor_kind=ActorKind.DEVELOPMENT,
                tool_name="execute_databricks_sql",
                tool_policy=ToolPolicy.TENANT_READ,
                tenant_id=None,
                input_metadata={
                    "schema_version": "1.0",
                    "connection_id": 42,
                    "sql": sql,
                    "sql_character_count": len(sql),
                },
                status="succeeded",
                failure_code=None,
            )
        )
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT input_metadata
              FROM mcp.tool_call_log
             WHERE tool_call_id = %s
            """,
            (tool_call_id,),
        ).fetchone()

    assert row is not None
    assert row["input_metadata"]["sql"] == sql
    assert row["input_metadata"]["sql_character_count"] == 100_000


def test_tool_call_log_rejects_update_and_delete(
    postgres_database: DisposablePostgres,
) -> None:
    tool_call_id = UUID("40000000-0000-0000-0000-000000000002")
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            INSERT INTO mcp.tool_call_log (
                tool_call_id,
                principal_display_name,
                actor_kind,
                tool_name,
                tool_policy,
                tool_call_status
            )
            VALUES (
                %s,
                'Local Developer',
                'development',
                'list_tenants',
                'tenant_read',
                'succeeded'
            )
            """,
            (tool_call_id,),
        )

    with (
        pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState,
            match="append-only",
        ),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            """
            UPDATE mcp.tool_call_log
               SET tool_call_status = 'failed'
             WHERE tool_call_id = %s
            """,
            (tool_call_id,),
        )

    with (
        pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState,
            match="append-only",
        ),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            "DELETE FROM mcp.tool_call_log WHERE tool_call_id = %s",
            (tool_call_id,),
        )


def test_tool_call_log_requires_an_object_without_a_byte_ceiling(
    postgres_database: DisposablePostgres,
) -> None:
    large_value = "x" * 1_100_000
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            """
            INSERT INTO mcp.tool_call_log (
                tool_call_id,
                principal_display_name,
                actor_kind,
                tool_name,
                tool_policy,
                input_metadata,
                tool_call_status
            )
            VALUES (
                '40000000-0000-0000-0000-000000000003',
                'Local Developer',
                'development',
                'list_tenants',
                'tenant_read',
                '[]'::JSONB,
                'succeeded'
            )
            """
        )

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            INSERT INTO mcp.tool_call_log (
                tool_call_id,
                principal_display_name,
                actor_kind,
                tool_name,
                tool_policy,
                input_metadata,
                tool_call_status
            )
            VALUES (
                '40000000-0000-0000-0000-000000000005',
                'Local Developer',
                'development',
                'list_tenants',
                'tenant_read',
                jsonb_build_object('value', %s::TEXT),
                'succeeded'
            )
            """,
            (large_value,),
        )
        row = connection.execute(
            """
            SELECT input_metadata ->> 'value' AS value
              FROM mcp.tool_call_log
             WHERE tool_call_id = '40000000-0000-0000-0000-000000000005'
            """
        ).fetchone()

    assert row == {"value": large_value}
