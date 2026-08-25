from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import uuid4

import pytest
from tests.mcp.database_test_support import require_row
from psycopg.errors import RaiseException

if TYPE_CHECKING:
    from conftest import DisposablePostgres


APPLICATION_TABLES = (
    "generated_sql_artifact",
    "output_template",
    "output_template_field",
    "principal_preference",
    "prompt_assignment",
    "prompt_template",
    "prompt_template_version",
    "sql_generation_guide",
    "sql_generation_guide_version",
    "workflow_run",
    "workflow_run_mapping_target_selection",
    "workflow_run_object_selection",
    "workflow_run_prompt_snapshot",
    "workflow_stage",
    "workflow_stage_variable",
)

APPLICATION_WEB_FUNCTIONS = (
    (
        "append_workflow_run_event",
        "uuid, uuid, character varying, bigint, bigint, bigint, integer, "
        "character varying, character varying, character varying, integer, integer, integer",
    ),
    (
        "archive_model",
        "uuid, uuid, character varying, bigint, bigint",
    ),
    (
        "assert_workflow_run_claim",
        "bigint, uuid",
    ),
    (
        "claim_next_workflow_run",
        "integer",
    ),
    (
        "complete_authoring_workflow_run_no_op",
        "uuid, uuid, character varying, bigint, bigint, bigint, character varying, "
        "character varying, uuid, bigint, character, bigint, integer, character varying, "
        "character varying, character varying, integer, integer, integer",
    ),
    (
        "complete_workflow_run",
        "uuid, uuid, character varying, bigint, bigint, integer",
    ),
    (
        "create_model",
        "uuid, uuid, character varying, bigint, character varying, character varying, "
        "text, jsonb, text, jsonb, jsonb, character varying, character varying, "
        "character varying, character varying, integer, integer",
    ),
    (
        "create_output_template",
        "uuid, uuid, character varying, character varying, character varying, "
        "character varying, character varying, jsonb",
    ),
    (
        "create_workflow_run",
        "uuid, uuid, character varying, bigint, bigint, character varying, "
        "character varying, character varying, character varying, character varying, "
        "character varying, integer, integer, bigint[], character varying, "
        "character varying, uuid, jsonb, character varying, character varying, "
        "character varying, bigint, bigint, bigint, character varying, bigint",
    ),
    (
        "fail_workflow_run",
        "uuid, uuid, character varying, bigint, bigint, character varying, character varying",
    ),
    (
        "get_analysis_validation_connection_values",
        "uuid, uuid, character varying, bigint, bigint, character varying",
    ),
    (
        "get_analysis_validation_execution_context",
        "uuid, uuid, character varying, bigint, bigint, character varying",
    ),
    (
        "get_profiling_connection_values",
        "uuid, uuid, character varying, bigint, bigint, character varying",
    ),
    (
        "get_profiling_execution_context",
        "uuid, uuid, character varying, bigint, bigint",
    ),
    (
        "lock_authoring_workflow_run",
        "bigint, bigint",
    ),
    (
        "persist_analysis_validation_results",
        "uuid, uuid, character varying, bigint, bigint, character varying, jsonb",
    ),
    (
        "persist_profiling_results",
        "uuid, uuid, character varying, bigint, bigint, jsonb",
    ),
    (
        "release_workflow_run_claim",
        "bigint, uuid",
    ),
    (
        "renew_workflow_run_claim",
        "bigint, uuid, integer",
    ),
    (
        "replace_model_scope",
        "uuid, uuid, character varying, bigint, bigint, bigint[]",
    ),
    (
        "save_prompt_template",
        "uuid, uuid, character varying, bigint, bigint, character varying, bigint, "
        "character varying, character varying, text, boolean, timestamp with time zone",
    ),
    (
        "save_prompt_template_draft",
        "uuid, uuid, character varying, bigint, bigint, text, text, text, timestamp with time zone",
    ),
    (
        "save_sql_generation_guide",
        "uuid, uuid, character varying, bigint, character varying, character varying, "
        "character varying, boolean, boolean, timestamp with time zone",
    ),
    (
        "save_sql_generation_guide_draft",
        "uuid, uuid, character varying, bigint, bigint, text, timestamp with time zone",
    ),
    (
        "set_principal_last_tenant",
        "uuid, uuid, character varying, bigint",
    ),
    (
        "set_prompt_assignment",
        "uuid, uuid, character varying, bigint, character varying, bigint, bigint, bigint",
    ),
    (
        "start_workflow_run",
        "uuid, uuid, character varying, bigint, bigint",
    ),
    (
        "store_generated_sql_artifact",
        "uuid, uuid, character varying, bigint, bigint, character varying, bigint, "
        "character, character, bigint, bigint, character varying, character varying, text, "
        "character",
    ),
    (
        "transition_prompt_template_version",
        "uuid, uuid, character varying, bigint, character varying, character varying",
    ),
    (
        "transition_sql_generation_guide_version",
        "uuid, uuid, character varying, bigint, character varying, character varying",
    ),
    (
        "update_model",
        "uuid, uuid, character varying, bigint, bigint, character varying, "
        "character varying, text, jsonb, text, jsonb, jsonb, character varying, "
        "character varying, character varying, character varying, integer, integer",
    ),
    (
        "update_output_template",
        "uuid, uuid, character varying, bigint, character varying, character varying, "
        "boolean, timestamp with time zone",
    ),
)
VERIFY_INSTALL_SQL = Path(__file__).parents[2] / "database" / "13_verify_install.sql"


def test_application_web_function_allowlist_is_exact_and_verified(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT procedure.proname AS function_name,
                   oidvectortypes(procedure.proargtypes) AS argument_types,
                   procedure.prosecdef AS is_security_definer,
                   EXISTS (
                       SELECT 1
                         FROM unnest(procedure.proconfig) AS setting(value)
                        WHERE setting.value LIKE 'search_path=pg_catalog%'
                   ) AS fixed_search_path,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public', procedure.oid, 'EXECUTE'
                   ) AS public_can_execute
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   )
             ORDER BY procedure.proname, oidvectortypes(procedure.proargtypes)
            """
        ).fetchall()

    assert len(APPLICATION_WEB_FUNCTIONS) == 32
    assert [(row["function_name"], row["argument_types"]) for row in rows] == list(
        APPLICATION_WEB_FUNCTIONS
    )
    assert all(row["is_security_definer"] for row in rows)
    assert all(row["fixed_search_path"] for row in rows)
    assert not any(row["mcp_can_execute"] for row in rows)
    assert not any(row["public_can_execute"] for row in rows)

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="application web function contract"),
        connection.transaction(),
    ):
        connection.execute(
            """
            GRANT EXECUTE ON FUNCTION application.snapshot_workflow_run_prompts(
                BIGINT,
                JSONB
            ) TO gds_web_write
            """
        )
        connection.execute(
            cast(LiteralString, VERIFY_INSTALL_SQL.read_text(encoding="utf-8"))
        )


def test_verify_install_rejects_direct_web_model_scope_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime table privileges"),
        connection.transaction(),
    ):
        connection.execute(
            "GRANT UPDATE (is_active) ON model.model_scope TO gds_web_write"
        )
        connection.execute(
            cast(LiteralString, VERIFY_INSTALL_SQL.read_text(encoding="utf-8"))
        )


def test_verify_install_rejects_direct_web_profile_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="runtime table privileges"),
        connection.transaction(),
    ):
        connection.execute(
            "GRANT INSERT ON workflow.attribute_profile TO gds_web_write"
        )
        connection.execute(
            cast(LiteralString, VERIFY_INSTALL_SQL.read_text(encoding="utf-8"))
        )


def test_verify_install_requires_unique_active_discovery_assignment(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="Discovery Scope assignment index"),
        connection.transaction(),
    ):
        connection.execute(
            """
            ALTER INDEX core.ux_active_metadata_discovery_scope_assignment
            RENAME TO invalid_discovery_assignment_index
            """
        )
        connection.execute(
            cast(LiteralString, VERIFY_INSTALL_SQL.read_text(encoding="utf-8"))
        )


def test_verify_install_requires_immutable_workflow_change_set_binding(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="Workflow Run binding contract"),
        connection.transaction(),
    ):
        connection.execute(
            """
            ALTER TABLE mcp.model_change_set
            DISABLE TRIGGER guard_model_change_set_workflow_binding
            """
        )
        connection.execute(
            cast(LiteralString, VERIFY_INSTALL_SQL.read_text(encoding="utf-8"))
        )


def test_last_tenant_preference_is_identity_derived_and_function_governed(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    suffix = uuid4().hex

    with postgres_database.connect_owner() as connection:
        project_id = require_row(
            connection.execute(
                """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
                (f"preference_project_{suffix}", f"Preference Project {suffix}"),
            ).fetchone()
        )["project_id"]
        tenant_id = require_row(
            connection.execute(
                """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
                (
                    project_id,
                    f"preference_tenant_{suffix}",
                    f"Preference Tenant {suffix}",
                    f"preference_catalog_{suffix}",
                    f"preference_admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        principal_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            ) VALUES ('user', %s, %s)
            RETURNING principal_id
            """,
                (f"Preference User {suffix}", f"preference_{suffix}@example.test"),
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'viewer', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        preference = require_row(
            connection.execute(
                """
            SELECT *
              FROM application.set_principal_last_tenant(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT
              )
            """,
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        )
        privileges = require_row(
            connection.execute(
                """
            SELECT has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_table_privilege(
                       'gds_web_write',
                       'application.principal_preference',
                       'INSERT'
                   ) AS web_can_insert,
                   has_table_privilege(
                       'gds_web_write',
                       'application.principal_preference',
                       'UPDATE'
                   ) AS web_can_update,
                   has_table_privilege(
                       'gds_web_write',
                       'application.principal_preference',
                       'DELETE'
                   ) AS web_can_delete
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND procedure.proname = 'set_principal_last_tenant'
            """
            ).fetchone()
        )

    assert preference["principal_id"] == principal_id
    assert preference["last_tenant_id"] == tenant_id
    assert privileges == {
        "web_can_execute": True,
        "mcp_can_execute": False,
        "web_can_insert": False,
        "web_can_update": False,
        "web_can_delete": False,
    }


def test_workflow_stage_registries_are_read_only_to_the_web_runtime(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT table_name,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'SELECT'
                   ) AS can_select,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'INSERT'
                   ) AS can_insert,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'UPDATE'
                   ) AS can_update,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'DELETE'
                   ) AS can_delete
              FROM unnest(
                       ARRAY[
                           'workflow_stage',
                           'workflow_stage_variable'
                       ]
                   ) AS registry(table_name)
             ORDER BY table_name
            """
        ).fetchall()

    assert rows == [
        {
            "table_name": "workflow_stage",
            "can_select": True,
            "can_insert": False,
            "can_update": False,
            "can_delete": False,
        },
        {
            "table_name": "workflow_stage_variable",
            "can_select": True,
            "can_insert": False,
            "can_update": False,
            "can_delete": False,
        },
    ]


def test_application_tables_are_read_only_and_sequences_are_unavailable_to_runtimes(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        table_rows = connection.execute(
            """
            SELECT table_name,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'SELECT'
                   ) AS web_can_select,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate,
                   has_table_privilege(
                       'gds_app_write',
                       'application.' || quote_ident(table_name),
                       'SELECT,INSERT,UPDATE,DELETE'
                   ) AS mcp_can_access
              FROM unnest(%s::TEXT[]) AS application_table(table_name)
             ORDER BY table_name
            """,
            (list(APPLICATION_TABLES),),
        ).fetchall()
        sequence_rows = connection.execute(
            """
            SELECT sequence_relation.relname AS sequence_name,
                   has_sequence_privilege(
                       'gds_web_write',
                       sequence_relation.oid,
                       'USAGE,SELECT'
                   ) AS web_can_use,
                   has_sequence_privilege(
                       'gds_app_write',
                       sequence_relation.oid,
                       'USAGE,SELECT'
                   ) AS mcp_can_use
              FROM pg_catalog.pg_class AS sequence_relation
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = sequence_relation.relnamespace
             WHERE namespace.nspname = 'application'
               AND sequence_relation.relkind = 'S'
             ORDER BY sequence_relation.relname
            """
        ).fetchall()
        posture = require_row(
            connection.execute(
                """
            SELECT has_schema_privilege(
                       'gds_app_write', 'application', 'USAGE'
                   ) AS mcp_schema_usage,
                   has_function_privilege(
                       'gds_web_write',
                       'application.snapshot_workflow_run_prompts(bigint,jsonb)',
                       'EXECUTE'
                   ) AS web_can_snapshot_directly,
                   has_function_privilege(
                       'gds_app_write',
                       'application.snapshot_workflow_run_prompts(bigint,jsonb)',
                       'EXECUTE'
                   ) AS mcp_can_snapshot
            """
            ).fetchone()
        )

    assert [row["table_name"] for row in table_rows] == sorted(APPLICATION_TABLES)
    assert all(row["web_can_select"] for row in table_rows)
    assert not any(row["web_can_mutate"] for row in table_rows)
    assert not any(row["mcp_can_access"] for row in table_rows)
    assert sequence_rows
    assert not any(row["web_can_use"] or row["mcp_can_use"] for row in sequence_rows)
    assert posture == {
        "mcp_schema_usage": False,
        "web_can_snapshot_directly": False,
        "mcp_can_snapshot": False,
    }
