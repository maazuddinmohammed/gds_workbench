from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

import pytest
from psycopg import sql
from psycopg.errors import RaiseException

if TYPE_CHECKING:
    from conftest import DisposablePostgres


RUNTIME_INTEGRITY_SQL = (
    Path(__file__).parents[2] / "database" / "12_runtime_integrity.sql"
)
VERIFY_INSTALL_SQL = Path(__file__).parents[2] / "database" / "13_verify_install.sql"


def test_runtime_integrity_sql_can_repair_grants_and_recheck_an_install(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute("REVOKE USAGE ON SCHEMA model FROM gds_app_write")
        connection.execute(
            """
            GRANT UPDATE (default_agent_sdk_code)
                ON model.model TO gds_app_write;
            GRANT INSERT (model_id, object_id)
                ON model.model_scope TO gds_app_write
            """
        )
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
                   membership.set_option,
                   has_column_privilege(
                       'gds_app_write', 'model.model',
                       'default_agent_sdk_code', 'UPDATE'
                   ) AS web_agent_default_update,
                   has_column_privilege(
                       'gds_app_write', 'model.model_scope',
                       'model_id', 'INSERT'
                   ) AS model_scope_insert
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
            "web_agent_default_update": True,
            "model_scope_insert": True,
        }

        connection.execute(
            cast(LiteralString, RUNTIME_INTEGRITY_SQL.read_text(encoding="utf-8"))
        )
        repaired = connection.execute(
            """
            SELECT has_schema_privilege(
                       'gds_app_write', 'model', 'USAGE'
                   ) AS model_schema_usage,
                   membership.admin_option,
                   membership.inherit_option,
                   membership.set_option,
                   has_column_privilege(
                       'gds_app_write', 'model.model',
                       'default_agent_sdk_code', 'UPDATE'
                   ) AS web_agent_default_update,
                   has_column_privilege(
                       'gds_app_write', 'model.model_scope',
                       'model_id', 'INSERT'
                   ) AS model_scope_insert
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
        "web_agent_default_update": False,
        "model_scope_insert": False,
    }

    with postgres_database.connect_runtime() as connection:
        contract = connection.execute(
            "SELECT * FROM mcp.runtime_readiness()"
        ).fetchone()

    assert contract is not None
    assert contract["runtime_role_ok"] is True
    assert contract["runtime_privileges_ok"] is True
    assert contract["runtime_query_contract_ok"] is True


def test_runtime_integrity_replaces_legacy_databricks_lookup_access(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            CREATE FUNCTION mcp.get_databricks_sql_connection_values(BIGINT)
            RETURNS TABLE (
                connection_tenant_id BIGINT,
                failure_code VARCHAR(50),
                databricks_host_name TEXT,
                databricks_http_path TEXT,
                databricks_token TEXT
            )
            LANGUAGE SQL
            STABLE
            SECURITY DEFINER
            SET search_path = pg_catalog
            AS $legacy_databricks_lookup$
                SELECT NULL::BIGINT, 'connection_not_found'::VARCHAR(50),
                       NULL::TEXT, NULL::TEXT, NULL::TEXT
            $legacy_databricks_lookup$
            """
        )
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION
                mcp.get_databricks_sql_connection_values(BIGINT)
            TO gds_app_write
            """
        )
        connection.execute(
            cast(
                LiteralString,
                RUNTIME_INTEGRITY_SQL.read_text(encoding="utf-8"),
            )
        )
        posture = connection.execute(
            """
            SELECT has_function_privilege(
                       'gds_app_write',
                       'mcp.get_databricks_sql_connection_values(bigint)',
                       'EXECUTE'
                   ) AS legacy_execute,
                   has_function_privilege(
                       'gds_app_write',
                       'mcp.get_databricks_sql_connection_values(bigint,text)',
                       'EXECUTE'
                   ) AS current_execute
            """
        ).fetchone()
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )

    assert posture == {"legacy_execute": False, "current_execute": True}


def test_runtime_integrity_revokes_web_databricks_secret_lookup(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION
                mcp.get_databricks_sql_connection_values(BIGINT, TEXT)
            TO gds_web_write
            """
        )
        connection.execute(
            cast(
                LiteralString,
                RUNTIME_INTEGRITY_SQL.read_text(encoding="utf-8"),
            )
        )
        posture = connection.execute(
            """
            SELECT has_function_privilege(
                       'gds_app_write',
                       'mcp.get_databricks_sql_connection_values(bigint,text)',
                       'EXECUTE'
                   ) AS mcp_execute,
                   has_function_privilege(
                       'gds_web_write',
                       'mcp.get_databricks_sql_connection_values(bigint,text)',
                       'EXECUTE'
                   ) AS web_execute
            """
        ).fetchone()

    assert posture == {"mcp_execute": True, "web_execute": False}


def test_runtime_integrity_revokes_an_unlisted_web_mcp_function(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "GRANT EXECUTE ON FUNCTION mcp.runtime_readiness() TO gds_web_write"
        )
        connection.execute(
            cast(
                LiteralString,
                RUNTIME_INTEGRITY_SQL.read_text(encoding="utf-8"),
            )
        )
        web_execute = connection.execute(
            """
            SELECT has_function_privilege(
                       'gds_web_write',
                       'mcp.runtime_readiness()',
                       'EXECUTE'
                   ) AS allowed
            """
        ).fetchone()

    assert web_execute == {"allowed": False}


def test_mcp_role_cannot_mutate_model_scope_or_web_agent_defaults(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        posture = connection.execute(
            """
            SELECT has_column_privilege(
                       'gds_app_write',
                       'model.model',
                       'silver_model_naming_instructions',
                       'UPDATE'
                   ) AS model_policy_update,
                   EXISTS (
                       SELECT 1
                         FROM unnest(ARRAY[
                                  'default_agent_sdk_code',
                                  'default_agent_provider_code',
                                  'default_agent_model_code',
                                  'default_reasoning_effort_code',
                                  'default_max_turns',
                                  'default_validation_retry_count'
                              ]) AS forbidden_column(name)
                        WHERE has_column_privilege(
                                  'gds_app_write',
                                  'model.model',
                                  forbidden_column.name,
                                  'UPDATE'
                              )
                   ) AS web_agent_default_update,
                   EXISTS (
                       SELECT 1
                         FROM pg_attribute AS attribute
                        WHERE attribute.attrelid = 'model.model_scope'::REGCLASS
                          AND attribute.attnum > 0
                          AND NOT attribute.attisdropped
                          AND (
                              has_column_privilege(
                                  'gds_app_write',
                                  'model.model_scope',
                                  attribute.attname,
                                  'INSERT'
                              )
                              OR has_column_privilege(
                                  'gds_app_write',
                                  'model.model_scope',
                                  attribute.attname,
                                  'UPDATE'
                              )
                          )
                   ) AS model_scope_mutation
            """
        ).fetchone()

    assert posture == {
        "model_policy_update": True,
        "web_agent_default_update": False,
        "model_scope_mutation": False,
    }


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
async def test_runtime_readiness_rejects_a_missing_canonical_model_policy_column(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            ALTER TABLE model.model
            RENAME COLUMN gold_model_audit_columns_template
            TO missing_gold_model_audit_columns_template
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
                ALTER TABLE model.model
                RENAME COLUMN missing_gold_model_audit_columns_template
                TO gold_model_audit_columns_template
                """
            )

    assert readiness.ready is False
    assert readiness.code == "database_schema_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schema_name", "relation_name"),
    [
        ("mcp", "model_change_set"),
        ("model", "modeling_assertion_record"),
        ("workflow", "mapping_object"),
    ],
)
async def test_runtime_readiness_rejects_a_missing_current_mcp_relation(
    postgres_database: DisposablePostgres,
    schema_name: str,
    relation_name: str,
) -> None:
    missing_name = f"missing_{relation_name}"
    relation = sql.Identifier(schema_name, relation_name)
    missing = sql.Identifier(schema_name, missing_name)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                relation,
                sql.Identifier(missing_name),
            )
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
                sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                    missing,
                    sql.Identifier(relation_name),
                )
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
async def test_runtime_readiness_rejects_an_unlisted_mcp_group_function(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION mcp.reject_tool_call_log_mutation()
            TO gds_app_write
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
                REVOKE EXECUTE ON FUNCTION mcp.reject_tool_call_log_mutation()
                FROM gds_app_write
                """
            )

    assert readiness.ready is False
    assert readiness.code == "database_role_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function_name",
    [
        "workflow.list_tenant_visible_objects",
        "workflow.list_model_object_eligibility",
        "workflow.list_model_attribute_eligibility",
    ],
)
async def test_runtime_readiness_rejects_a_missing_model_read_grant(
    postgres_database: DisposablePostgres,
    function_name: str,
) -> None:
    function_identifier = sql.Identifier(*function_name.split("."))
    with postgres_database.connect_owner() as connection:
        connection.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {}(BIGINT) FROM gds_app_write").format(
                function_identifier
            )
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
                sql.SQL("GRANT EXECUTE ON FUNCTION {}(BIGINT) TO gds_app_write").format(
                    function_identifier
                )
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


def test_verify_install_rejects_mcp_model_scope_column_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime table privileges"),
        connection.transaction(),
    ):
        connection.execute(
            """
            GRANT INSERT (model_id, object_id)
                ON model.model_scope TO gds_app_write
            """
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


def test_verify_install_rejects_a_missing_application_table(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="application table"),
        connection.transaction(),
    ):
        connection.execute(
            """
            ALTER TABLE application.prompt_assignment
            RENAME TO missing_prompt_assignment
            """
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


def test_verify_install_rejects_missing_application_schema_usage(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="schema usage"),
        connection.transaction(),
    ):
        connection.execute("REVOKE USAGE ON SCHEMA application FROM gds_web_write")
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


def test_verify_install_rejects_web_databricks_secret_lookup(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime function privileges"),
        connection.transaction(),
    ):
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION
                mcp.get_databricks_sql_connection_values(BIGINT, TEXT)
            TO gds_web_write
            """
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


def test_verify_install_rejects_an_unlisted_web_mcp_function(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime function privileges"),
        connection.transaction(),
    ):
        connection.execute(
            "GRANT EXECUTE ON FUNCTION mcp.runtime_readiness() TO gds_web_write"
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


def test_verify_install_rejects_an_unlisted_mcp_group_function(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime function privileges"),
        connection.transaction(),
    ):
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION mcp.reject_tool_call_log_mutation()
            TO gds_app_write
            """
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )


@pytest.mark.parametrize(
    "function_signature",
    [
        "workflow.list_tenant_visible_objects(bigint)",
        "workflow.list_model_object_eligibility(bigint)",
        "workflow.list_model_attribute_eligibility(bigint)",
        "workflow.list_code_generation_target_context(bigint,character varying)",
    ],
)
def test_verify_install_rejects_missing_web_workflow_read_grant(
    postgres_database: DisposablePostgres,
    function_signature: str,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime function privileges"),
        connection.transaction(),
    ):
        connection.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM gds_web_write").format(
                sql.SQL(function_signature)
            )
        )
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )
