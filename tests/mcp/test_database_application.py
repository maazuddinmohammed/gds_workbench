from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from tests.mcp.database_test_support import require_row
from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    ObjectNotInPrerequisiteState,
    RaiseException,
    UniqueViolation,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


APPLICATION_TABLES = {
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
    "workflow_run_system_selection",
    "workflow_run_prompt_snapshot",
    "workflow_stage",
    "workflow_stage_variable",
}

WEB_PROVENANCE_COLUMNS = {
    ("model", "model_event_log", "workflow_run_id"),
    ("model", "modeling_assertion_document", "workflow_run_id"),
    ("model", "modeling_assertion_record", "workflow_run_id"),
    ("workflow", "attribute_profile", "workflow_run_id"),
    ("workflow", "analysis_result", "inference_workflow_run_id"),
    ("workflow", "analysis_result", "validation_workflow_run_id"),
    ("workflow", "generated_code", "workflow_run_id"),
    ("workflow", "conceptual_object", "workflow_run_id"),
    ("workflow", "conceptual_relationship", "workflow_run_id"),
    ("workflow", "conceptual_support", "workflow_run_id"),
    ("workflow", "logical_submodel", "workflow_run_id"),
    ("workflow", "logical_entity", "workflow_run_id"),
    ("workflow", "logical_entity_submodel", "workflow_run_id"),
    ("workflow", "logical_attribute", "workflow_run_id"),
    ("workflow", "logical_entity_source_mapping", "workflow_run_id"),
    ("workflow", "logical_attribute_source_mapping", "workflow_run_id"),
    ("workflow", "logical_relationship", "workflow_run_id"),
    ("workflow", "dimensional_submodel", "workflow_run_id"),
    ("workflow", "dimensional_entity", "workflow_run_id"),
    ("workflow", "dimensional_entity_submodel", "workflow_run_id"),
    ("workflow", "dimensional_attribute", "workflow_run_id"),
    ("workflow", "dimensional_entity_source_mapping", "workflow_run_id"),
    ("workflow", "dimensional_attribute_source_mapping", "workflow_run_id"),
    ("workflow", "dimensional_relationship", "workflow_run_id"),
    ("workflow", "mapping_source_system_dependency", "workflow_run_id"),
    ("workflow", "mapping_object", "workflow_run_id"),
    ("workflow", "mapping_attribute", "workflow_run_id"),
    ("workflow", "validation_group", "workflow_run_id"),
}

ANALYSIS_VALIDATION_COLUMNS = {
    "validation_source_context_digest",
    "validation_policy_version",
    "validation_policy_digest",
    "validation_result",
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
}


def _create_model_and_principal(
    postgres_database: DisposablePostgres,
) -> tuple[int, int]:
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        project_id = require_row(
            connection.execute(
                """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
                (f"project_{suffix}", f"Project {suffix}"),
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
                    f"tenant_{suffix}",
                    f"Tenant {suffix}",
                    f"catalog_{suffix}",
                    f"admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        model_id = require_row(
            connection.execute(
                """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id
            """,
                (tenant_id, f"Model {suffix}"),
            ).fetchone()
        )["model_id"]
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
                (f"User {suffix}", f"{suffix}@example.test"),
            ).fetchone()
        )["principal_id"]

    return model_id, principal_id


def _create_prompt_version(
    postgres_database: DisposablePostgres,
    *,
    workflow_stage_id: int,
    principal_id: int,
    ownership_scope: str,
    owner_tenant_id: int | None,
    published: bool,
) -> int:
    code = f"prompt_{uuid4().hex}"
    with postgres_database.connect_owner() as connection:
        digest = require_row(
            connection.execute(
                """
            SELECT encode(
                       sha256(
                           convert_to(
                               jsonb_build_object(
                                   'system_prompt_template',
                                       '{{ stage_context }}'::TEXT,
                                   'instruction_prompt_template',
                                       '{{ stage_context }}'::TEXT,
                                   'tool_instruction_prompt_template',
                                       NULL::TEXT
                               )::TEXT,
                               'UTF8'
                           )
                       ),
                       'hex'
                   ) AS digest
            """
            ).fetchone()
        )["digest"]
        template_id = require_row(
            connection.execute(
                """
            INSERT INTO application.prompt_template (
                workflow_stage_id,
                prompt_template_ownership_scope,
                owner_tenant_id,
                prompt_template_code,
                prompt_template_name,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING prompt_template_id
            """,
                (
                    workflow_stage_id,
                    ownership_scope,
                    owner_tenant_id,
                    code,
                    code,
                    principal_id,
                    principal_id,
                ),
            ).fetchone()
        )["prompt_template_id"]
        version_id = require_row(
            connection.execute(
                """
            INSERT INTO application.prompt_template_version (
                prompt_template_id,
                workflow_stage_id,
                prompt_template_version_number,
                system_prompt_template,
                instruction_prompt_template,
                prompt_template_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, %s, 1, '{{ stage_context }}',
                      '{{ stage_context }}', %s, %s, %s)
            RETURNING prompt_template_version_id
            """,
                (
                    template_id,
                    workflow_stage_id,
                    digest,
                    principal_id,
                    principal_id,
                ),
            ).fetchone()
        )["prompt_template_version_id"]
        if published:
            connection.execute(
                """
                UPDATE application.prompt_template_version
                   SET prompt_template_version_status = 'published',
                       published_time = CURRENT_TIMESTAMP,
                       published_by_principal_id = %s,
                       updated_by_principal_id = %s,
                       updated_time = CURRENT_TIMESTAMP
                 WHERE prompt_template_version_id = %s
                """,
                (principal_id, principal_id, version_id),
            )

    return version_id


def _create_agentic_workflow_run(
    postgres_database: DisposablePostgres,
    *,
    model_id: int,
    principal_id: int,
    model_workflow: str,
    workflow_execution_mode: str,
) -> int:
    with postgres_database.connect_owner() as connection:
        model = require_row(
            connection.execute(
                "SELECT tenant_id, model_revision FROM model.model WHERE model_id = %s",
                (model_id,),
            ).fetchone()
        )
        return require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_run (
                tenant_id,
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                agent_sdk_code,
                agent_provider_code,
                agent_model_code,
                reasoning_effort_code,
                max_turns,
                validation_retry_count,
                selected_scope_digest,
                selected_scope_count,
                correlation_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, 'openai_agents_sdk',
                'microsoft_foundry', 'model-1', 'medium', 12, 2,
                %s, 1, %s
            )
            RETURNING workflow_run_id
            """,
                (
                    model["tenant_id"],
                    model_id,
                    model["model_revision"],
                    model_workflow,
                    workflow_execution_mode,
                    principal_id,
                    "d" * 64,
                    uuid4(),
                ),
            ).fetchone()
        )["workflow_run_id"]


def test_application_schema_has_the_canonical_tables(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT table_name
              FROM information_schema.tables
             WHERE table_schema = 'application'
               AND table_type = 'BASE TABLE'
             ORDER BY table_name
            """
        ).fetchall()

    assert {row["table_name"] for row in rows} == APPLICATION_TABLES


def test_web_workflow_provenance_is_nullable_on_every_common_artifact(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT table_schema, table_name, column_name, is_nullable
              FROM information_schema.columns
             WHERE (table_schema, table_name, column_name) IN (
                       SELECT expected.table_schema,
                              expected.table_name,
                              expected.column_name
                         FROM (VALUES
                             ('model', 'model_event_log', 'workflow_run_id'),
                             ('model', 'modeling_assertion_document', 'workflow_run_id'),
                             ('model', 'modeling_assertion_record', 'workflow_run_id'),
                             ('workflow', 'attribute_profile', 'workflow_run_id'),
                             ('workflow', 'analysis_result', 'inference_workflow_run_id'),
                             ('workflow', 'analysis_result', 'validation_workflow_run_id'),
                             ('workflow', 'generated_code', 'workflow_run_id'),
                             ('workflow', 'conceptual_object', 'workflow_run_id'),
                             ('workflow', 'conceptual_relationship', 'workflow_run_id'),
                             ('workflow', 'conceptual_support', 'workflow_run_id'),
                             ('workflow', 'logical_submodel', 'workflow_run_id'),
                             ('workflow', 'logical_entity', 'workflow_run_id'),
                             ('workflow', 'logical_entity_submodel', 'workflow_run_id'),
                             ('workflow', 'logical_attribute', 'workflow_run_id'),
                             ('workflow', 'logical_entity_source_mapping', 'workflow_run_id'),
                             ('workflow', 'logical_attribute_source_mapping', 'workflow_run_id'),
                             ('workflow', 'logical_relationship', 'workflow_run_id'),
                             ('workflow', 'dimensional_submodel', 'workflow_run_id'),
                             ('workflow', 'dimensional_entity', 'workflow_run_id'),
                             ('workflow', 'dimensional_entity_submodel', 'workflow_run_id'),
                             ('workflow', 'dimensional_attribute', 'workflow_run_id'),
                             ('workflow', 'dimensional_entity_source_mapping', 'workflow_run_id'),
                             ('workflow', 'dimensional_attribute_source_mapping', 'workflow_run_id'),
                             ('workflow', 'dimensional_relationship', 'workflow_run_id'),
                             ('workflow', 'mapping_source_system_dependency', 'workflow_run_id'),
                             ('workflow', 'mapping_object', 'workflow_run_id'),
                             ('workflow', 'mapping_attribute', 'workflow_run_id'),
                             ('workflow', 'validation_group', 'workflow_run_id')
                         ) AS expected(table_schema, table_name, column_name)
                   )
            """
        ).fetchall()

    assert {
        (row["table_schema"], row["table_name"], row["column_name"]) for row in rows
    } == WEB_PROVENANCE_COLUMNS
    assert all(row["is_nullable"] == "YES" for row in rows)


def test_web_workflow_provenance_is_fenced_to_the_same_model(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT child_namespace.nspname AS table_schema,
                   child.relname AS table_name,
                   ARRAY(
                       SELECT attribute.attname
                         FROM unnest(constraint_row.conkey)
                              WITH ORDINALITY AS key(attnum, position)
                         JOIN pg_attribute AS attribute
                           ON attribute.attrelid = child.oid
                          AND attribute.attnum = key.attnum
                        ORDER BY key.position
                   ) AS child_columns,
                   parent_namespace.nspname AS parent_schema,
                   parent.relname AS parent_table,
                   ARRAY(
                       SELECT attribute.attname
                         FROM unnest(constraint_row.confkey)
                              WITH ORDINALITY AS key(attnum, position)
                         JOIN pg_attribute AS attribute
                           ON attribute.attrelid = parent.oid
                          AND attribute.attnum = key.attnum
                        ORDER BY key.position
                   ) AS parent_columns,
                   constraint_row.confdeltype
              FROM pg_constraint AS constraint_row
              JOIN pg_class AS child
                ON child.oid = constraint_row.conrelid
              JOIN pg_namespace AS child_namespace
                ON child_namespace.oid = child.relnamespace
              JOIN pg_class AS parent
                ON parent.oid = constraint_row.confrelid
              JOIN pg_namespace AS parent_namespace
                ON parent_namespace.oid = parent.relnamespace
             WHERE constraint_row.contype = 'f'
               AND parent_namespace.nspname = 'application'
               AND parent.relname = 'workflow_run'
               AND child_namespace.nspname IN ('model', 'workflow')
            """
        ).fetchall()

    actual = {
        (
            row["table_schema"],
            row["table_name"],
            tuple(row["child_columns"]),
        )
        for row in rows
    }
    expected = {
        (table_schema, table_name, (column_name, "model_id"))
        for table_schema, table_name, column_name in WEB_PROVENANCE_COLUMNS
    }

    assert actual == expected
    assert all(row["parent_schema"] == "application" for row in rows)
    assert all(row["parent_table"] == "workflow_run" for row in rows)
    assert all(
        tuple(row["parent_columns"]) == ("workflow_run_id", "model_id") for row in rows
    )
    assert all(row["confdeltype"] == "a" for row in rows)


def test_analysis_inference_can_exist_before_validation(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT column_name, is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'workflow'
               AND table_name = 'analysis_result'
               AND column_name = ANY(%s)
            """,
            (list(ANALYSIS_VALIDATION_COLUMNS),),
        ).fetchall()
        constraint_definition = connection.execute(
            """
            SELECT pg_get_constraintdef(constraint_row.oid) AS definition
              FROM pg_constraint AS constraint_row
              JOIN pg_class AS table_row
                ON table_row.oid = constraint_row.conrelid
              JOIN pg_namespace AS namespace_row
                ON namespace_row.oid = table_row.relnamespace
             WHERE namespace_row.nspname = 'workflow'
               AND table_row.relname = 'analysis_result'
               AND constraint_row.conname = 'ck_analysis_validation_payload'
            """
        ).fetchone()

    assert {row["column_name"] for row in columns} == ANALYSIS_VALIDATION_COLUMNS
    assert all(row["is_nullable"] == "YES" for row in columns)
    assert constraint_definition is not None
    assert "num_nonnulls" in constraint_definition["definition"].lower()


def test_model_event_stream_is_ordered_attempt_aware_and_append_only(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, _ = _create_model_and_principal(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        event_id = require_row(
            connection.execute(
                """
            INSERT INTO model.model_event_log (
                model_id,
                correlation_id,
                model_event_log_sequence,
                model_event_log_attempt,
                model_workflow,
                model_event_log_stage,
                model_event_log_status,
                model_event_log_message
            ) VALUES (%s, %s, 1, 1, 'code_generation', 'prepare', 'started', 'Started')
            RETURNING model_event_log_id
            """,
                (model_id, correlation_id),
            ).fetchone()
        )["model_event_log_id"]

    with pytest.raises(UniqueViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                INSERT INTO model.model_event_log (
                    model_id,
                    correlation_id,
                    model_event_log_sequence,
                    model_event_log_attempt,
                    model_workflow,
                    model_event_log_stage,
                    model_event_log_status,
                    model_event_log_message
                ) VALUES (%s, %s, 1, 1, 'code_generation', 'prepare', 'running', 'Running')
                """,
                (model_id, correlation_id),
            )

    for statement in (
        "UPDATE model.model_event_log SET model_event_log_message = 'Changed' WHERE model_event_log_id = %s",
        "DELETE FROM model.model_event_log WHERE model_event_log_id = %s",
    ):
        with pytest.raises(ObjectNotInPrerequisiteState, match="append-only"):
            with postgres_database.connect_owner() as connection:
                connection.execute(statement, (event_id,))


def test_workflow_run_uses_one_forward_only_state_machine(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, principal_id = _create_model_and_principal(postgres_database)
    workflow_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="conceptual",
        workflow_execution_mode="one_shot",
    )

    with pytest.raises(ObjectNotInPrerequisiteState, match="state transition"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.workflow_run
                   SET workflow_run_state = 'completed',
                       started_time = CURRENT_TIMESTAMP,
                       completed_time = CURRENT_TIMESTAMP
                 WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            )

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE application.workflow_run
               SET workflow_run_state = 'running',
                   started_time = CURRENT_TIMESTAMP
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        )
        connection.execute(
            """
            UPDATE application.workflow_run
               SET workflow_run_state = 'completed_with_repair',
                   completed_time = CURRENT_TIMESTAMP
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        )

    for statement in (
        "UPDATE application.workflow_run SET workflow_run_state = 'running', completed_time = NULL WHERE workflow_run_id = %s",
        "DELETE FROM application.workflow_run WHERE workflow_run_id = %s",
    ):
        with pytest.raises(ObjectNotInPrerequisiteState, match="terminal|deleted"):
            with postgres_database.connect_owner() as connection:
                connection.execute(statement, (workflow_run_id,))


def test_model_change_set_workflow_provenance_is_nullable_unique_and_model_fenced(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, principal_id = _create_model_and_principal(postgres_database)
    other_model_id, other_principal_id = _create_model_and_principal(postgres_database)
    workflow_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="conceptual",
        workflow_execution_mode="one_shot",
    )
    other_workflow_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="conceptual",
        workflow_execution_mode="one_shot",
    )
    insert_change_set = """
        INSERT INTO mcp.model_change_set (
            model_change_set_id,
            model_id,
            workflow_run_id,
            base_model_revision,
            base_source_context_digest,
            base_assertion_digest,
            base_policy_digest,
            created_by_principal_id,
            correlation_id
        ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s)
        RETURNING workflow_run_id
    """

    with postgres_database.connect_owner() as connection:
        nullable = connection.execute(
            """
            SELECT is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'mcp'
               AND table_name = 'model_change_set'
               AND column_name = 'workflow_run_id'
            """
        ).fetchone()
        manual = require_row(
            connection.execute(
                insert_change_set,
                (
                    uuid4(),
                    model_id,
                    None,
                    "a" * 64,
                    "b" * 64,
                    "c" * 64,
                    principal_id,
                    uuid4(),
                ),
            ).fetchone()
        )
        second_manual = require_row(
            connection.execute(
                insert_change_set,
                (
                    uuid4(),
                    model_id,
                    None,
                    "7" * 64,
                    "8" * 64,
                    "9" * 64,
                    principal_id,
                    uuid4(),
                ),
            ).fetchone()
        )
        linked = require_row(
            connection.execute(
                insert_change_set,
                (
                    uuid4(),
                    model_id,
                    workflow_run_id,
                    "d" * 64,
                    "e" * 64,
                    "f" * 64,
                    principal_id,
                    uuid4(),
                ),
            ).fetchone()
        )

    assert nullable is not None
    assert nullable["is_nullable"] == "YES"
    assert manual["workflow_run_id"] is None
    assert second_manual["workflow_run_id"] is None
    assert linked["workflow_run_id"] == workflow_run_id

    with pytest.raises(
        ObjectNotInPrerequisiteState,
        match="Workflow Run binding is immutable",
    ):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE mcp.model_change_set
                   SET workflow_run_id = NULL
                 WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            )

    with pytest.raises(UniqueViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                insert_change_set,
                (
                    uuid4(),
                    model_id,
                    workflow_run_id,
                    "1" * 64,
                    "2" * 64,
                    "3" * 64,
                    principal_id,
                    uuid4(),
                ),
            )

    with pytest.raises(ForeignKeyViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                insert_change_set,
                (
                    uuid4(),
                    other_model_id,
                    other_workflow_run_id,
                    "4" * 64,
                    "5" * 64,
                    "6" * 64,
                    other_principal_id,
                    uuid4(),
                ),
            )

    with pytest.raises(ForeignKeyViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                insert_change_set,
                (
                    uuid4(),
                    model_id,
                    9_999_999_999,
                    "0" * 64,
                    "a" * 64,
                    "b" * 64,
                    principal_id,
                    uuid4(),
                ),
            )


def test_principal_preference_uses_the_existing_audit_naming_convention(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'application'
               AND table_name = 'principal_preference'
             ORDER BY ordinal_position
            """
        ).fetchall()

    assert [row["column_name"] for row in columns] == [
        "principal_preference_id",
        "principal_id",
        "last_tenant_id",
        "last_accessed_time",
        "created_time",
        "created_by",
        "updated_time",
        "updated_by",
    ]


def test_application_schema_is_available_only_to_the_web_runtime(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        posture = connection.execute(
            """
            SELECT has_schema_privilege(
                       'public', 'application', 'USAGE'
                   ) AS public_schema_usage,
                   has_table_privilege(
                       'public',
                       'application.workflow_run',
                       'SELECT,INSERT,UPDATE,DELETE'
                   ) AS public_table_access,
                   has_schema_privilege(
                       'gds_app_write', 'application', 'USAGE'
                   ) AS mcp_schema_usage,
                   has_table_privilege(
                       'gds_app_write',
                       'application.workflow_run',
                       'SELECT,INSERT,UPDATE,DELETE'
                   ) AS mcp_table_access,
                   has_schema_privilege(
                       'gds_web_write', 'application', 'USAGE'
                   ) AS web_schema_usage,
                   has_table_privilege(
                       'gds_web_write',
                       'application.workflow_run',
                       'SELECT'
                   ) AS web_table_select,
                   has_table_privilege(
                       'gds_web_write',
                       'application.workflow_run',
                       'INSERT,UPDATE,DELETE'
                   ) AS web_table_mutation,
                   has_table_privilege(
                       'gds_web_write',
                       'application.workflow_run_prompt_snapshot',
                       'INSERT,UPDATE,DELETE'
                   ) AS web_direct_snapshot_mutation,
                   has_function_privilege(
                       'gds_web_write',
                       'application.snapshot_workflow_run_prompts(bigint,jsonb)',
                       'EXECUTE'
                   ) AS web_snapshot_function
            """
        ).fetchone()

    assert posture == {
        "public_schema_usage": False,
        "public_table_access": False,
        "mcp_schema_usage": False,
        "mcp_table_access": False,
        "web_schema_usage": True,
        "web_table_select": True,
        "web_table_mutation": False,
        "web_direct_snapshot_mutation": False,
        "web_snapshot_function": False,
    }


def test_workflow_run_requires_only_agentic_runs_to_have_agent_configuration(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, principal_id = _create_model_and_principal(postgres_database)
    digest = "a" * 64

    with postgres_database.connect_owner() as connection:
        model = require_row(
            connection.execute(
                "SELECT tenant_id, model_revision FROM model.model WHERE model_id = %s",
                (model_id,),
            ).fetchone()
        )
        tenant_id = model["tenant_id"]
        model_revision = model["model_revision"]
        deterministic_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_run (
                tenant_id,
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                selected_scope_digest,
                selected_scope_count,
                correlation_id
            ) VALUES (%s, %s, %s, 'profiling', NULL, %s, %s, 1, %s)
            RETURNING workflow_run_id
            """,
                (tenant_id, model_id, model_revision, principal_id, digest, uuid4()),
            ).fetchone()
        )["workflow_run_id"]
        agentic_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_run (
                tenant_id,
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                agent_sdk_code,
                agent_provider_code,
                agent_model_code,
                reasoning_effort_code,
                max_turns,
                validation_retry_count,
                selected_scope_digest,
                selected_scope_count,
                correlation_id
            ) VALUES (
                %s, %s, %s, 'conceptual', 'one_shot', %s,
                'openai_agents_sdk', 'microsoft_foundry', 'model-1',
                'medium', 50, 5, %s, 1, %s
            )
            RETURNING workflow_run_id
            """,
                (tenant_id, model_id, model_revision, principal_id, digest, uuid4()),
            ).fetchone()
        )["workflow_run_id"]

    assert deterministic_id > 0
    assert agentic_id > deterministic_id

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(CheckViolation),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_run (
                tenant_id,
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                selected_scope_digest,
                selected_scope_count,
                correlation_id
            ) VALUES (%s, %s, %s, 'logical', 'automatic', %s, %s, 1, %s)
            """,
            (tenant_id, model_id, model_revision, principal_id, digest, uuid4()),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(CheckViolation),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_run (
                tenant_id,
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                selected_scope_digest,
                selected_scope_count,
                correlation_id
            ) VALUES (%s, %s, %s, 'mapping', 'tool_assisted', %s, %s, 1, %s)
            """,
            (tenant_id, model_id, model_revision, principal_id, digest, uuid4()),
        )


def test_workflow_stage_has_bounded_modes_and_unique_order(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        stage_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'conceptual', 'one_shot', 'application_contract_stage',
                'Application contract stage', 910, TRUE
            )
            RETURNING workflow_stage_id
            """
            ).fetchone()
        )["workflow_stage_id"]
    assert stage_id > 0

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(CheckViolation),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'analysis', 'validation', 'relationship_validation',
                'Relationship validation', 10, FALSE
            )
            """
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(UniqueViolation, match="uq_workflow_stage_order"),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'conceptual', 'one_shot', 'duplicate_order',
                'Duplicate order', 910, TRUE
            )
            """
        )


def test_workflow_stage_variables_use_safe_prompt_types_and_unique_resolvers(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        stage_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'logical', 'tool_assisted', 'variable_contract_stage',
                'Variable contract stage', 910, TRUE
            )
            RETURNING workflow_stage_id
            """
            ).fetchone()
        )["workflow_stage_id"]
        context_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage_variable (
                workflow_stage_id,
                workflow_stage_variable_name,
                workflow_stage_variable_resolver_key,
                workflow_stage_variable_data_type,
                workflow_stage_variable_is_required,
                workflow_stage_variable_description,
                workflow_stage_variable_example,
                workflow_stage_variable_order
            ) VALUES (
                %s, 'stage_context', 'workflow.logical.context', 'json',
                TRUE, 'Bounded typed stage context.',
                '{"schema_version":"1.0","items":[]}'::JSONB, 10
            )
            RETURNING workflow_stage_variable_id
            """,
                (stage_id,),
            ).fetchone()
        )["workflow_stage_variable_id"]
        naming_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage_variable (
                workflow_stage_id,
                workflow_stage_variable_name,
                workflow_stage_variable_resolver_key,
                workflow_stage_variable_data_type,
                workflow_stage_variable_description,
                workflow_stage_variable_example,
                workflow_stage_variable_order
            ) VALUES (
                %s, 'naming_instructions', 'model.naming_instructions',
                'text', 'Model naming instructions.', '""'::JSONB, 20
            )
            RETURNING workflow_stage_variable_id
            """,
                (stage_id,),
            ).fetchone()
        )["workflow_stage_variable_id"]

    assert context_id > 0
    assert naming_id > context_id

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(UniqueViolation, match="uq_workflow_stage_variable_resolver"),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_stage_variable (
                workflow_stage_id,
                workflow_stage_variable_name,
                workflow_stage_variable_resolver_key,
                workflow_stage_variable_data_type,
                workflow_stage_variable_description,
                workflow_stage_variable_order
            ) VALUES (
                %s, 'duplicate_resolver', 'model.naming_instructions',
                'text', 'Duplicate resolver.', 30
            )
            """,
            (stage_id,),
        )


def test_published_prompt_versions_are_immutable_and_can_only_be_retired(
    postgres_database: DisposablePostgres,
) -> None:
    _, principal_id = _create_model_and_principal(postgres_database)
    with postgres_database.connect_owner() as connection:
        digest = require_row(
            connection.execute(
                """
            SELECT encode(
                       sha256(
                           convert_to(
                               jsonb_build_object(
                                   'system_prompt_template',
                                       '{{ stage_context }}'::TEXT,
                                   'instruction_prompt_template',
                                       '{{ stage_context }}'::TEXT,
                                   'tool_instruction_prompt_template',
                                       NULL::TEXT
                               )::TEXT,
                               'UTF8'
                           )
                       ),
                       'hex'
                   ) AS digest
            """
            ).fetchone()
        )["digest"]
        stage_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'analysis', 'one_shot', 'relationship_inference',
                'Relationship inference', 10, TRUE
            )
            RETURNING workflow_stage_id
            """
            ).fetchone()
        )["workflow_stage_id"]
        template_id = require_row(
            connection.execute(
                """
            INSERT INTO application.prompt_template (
                workflow_stage_id,
                prompt_template_ownership_scope,
                prompt_template_code,
                prompt_template_name,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, 'global', 'analysis_default', 'Analysis default', %s, %s)
            RETURNING prompt_template_id
            """,
                (stage_id, principal_id, principal_id),
            ).fetchone()
        )["prompt_template_id"]
        version_id = require_row(
            connection.execute(
                """
            INSERT INTO application.prompt_template_version (
                prompt_template_id,
                workflow_stage_id,
                prompt_template_version_number,
                system_prompt_template,
                instruction_prompt_template,
                prompt_template_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, %s, 1, '{{ stage_context }}',
                      '{{ stage_context }}', %s, %s, %s)
            RETURNING prompt_template_version_id
            """,
                (template_id, stage_id, digest, principal_id, principal_id),
            ).fetchone()
        )["prompt_template_version_id"]
        connection.execute(
            """
            UPDATE application.prompt_template_version
               SET prompt_template_version_status = 'published',
                   published_time = CURRENT_TIMESTAMP,
                   published_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE prompt_template_version_id = %s
            """,
            (principal_id, principal_id, version_id),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="published prompt version is immutable"),
        connection.transaction(),
    ):
        connection.execute(
            """
            UPDATE application.prompt_template_version
               SET instruction_prompt_template = 'Changed after publication',
                   prompt_template_digest = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE prompt_template_version_id = %s
            """,
            ("c" * 64, version_id),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="prompt versions cannot be deleted"),
        connection.transaction(),
    ):
        connection.execute(
            """
            DELETE FROM application.prompt_template_version
             WHERE prompt_template_version_id = %s
            """,
            (version_id,),
        )

    with postgres_database.connect_owner() as connection:
        retired_status = require_row(
            connection.execute(
                """
            UPDATE application.prompt_template_version
               SET prompt_template_version_status = 'retired',
                   retired_time = CURRENT_TIMESTAMP,
                   retired_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE prompt_template_version_id = %s
            RETURNING prompt_template_version_status
            """,
                (principal_id, principal_id, version_id),
            ).fetchone()
        )["prompt_template_version_status"]

    assert retired_status == "retired"


def test_prompt_versions_record_creator_and_updater_principals(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT column_name, is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'application'
               AND table_name = 'prompt_template_version'
               AND column_name IN (
                   'created_by_principal_id',
                   'updated_by_principal_id'
               )
            """
        ).fetchall()

    assert {row["column_name"] for row in columns} == {
        "created_by_principal_id",
        "updated_by_principal_id",
    }
    assert all(row["is_nullable"] == "NO" for row in columns)


def test_prompt_assignments_require_published_usable_owned_prompts(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, principal_id = _create_model_and_principal(postgres_database)
    other_model_id, other_principal_id = _create_model_and_principal(postgres_database)
    with postgres_database.connect_owner() as connection:
        tenants = connection.execute(
            """
            SELECT model_id, tenant_id
              FROM model.model
             WHERE model_id IN (%s, %s)
            """,
            (model_id, other_model_id),
        ).fetchall()
        tenant_by_model = {row["model_id"]: row["tenant_id"] for row in tenants}
        stage_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'mapping', 'one_shot', 'mapping_authoring',
                'Mapping authoring', 10, TRUE
            )
            RETURNING workflow_stage_id
            """
            ).fetchone()
        )["workflow_stage_id"]
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_by_model[model_id], principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_expires_time
            ) VALUES (
                %s, %s, 'Prompt assignment',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_by_model[model_id], principal_id),
        )

    draft_global = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=principal_id,
        ownership_scope="global",
        owner_tenant_id=None,
        published=False,
    )
    published_global = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=principal_id,
        ownership_scope="global",
        owner_tenant_id=None,
        published=True,
    )
    published_owned = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=principal_id,
        ownership_scope="tenant",
        owner_tenant_id=tenant_by_model[model_id],
        published=True,
    )
    published_other = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=other_principal_id,
        ownership_scope="tenant",
        owner_tenant_id=tenant_by_model[other_model_id],
        published=True,
    )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="published prompt version"),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                model_id,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'model_default', %s, %s)
            """,
            (stage_id, draft_global, model_id, principal_id),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="owner Tenant"),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                model_id,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'model_default', %s, %s)
            """,
            (stage_id, published_other, model_id, principal_id),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="global prompt"),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'global_default', %s)
            """,
            (stage_id, published_owned, principal_id),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="Super Admin"),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'global_default', %s)
            """,
            (stage_id, published_global, principal_id),
        )

    with postgres_database.connect_owner() as connection:
        model_assignment_id = require_row(
            connection.execute(
                """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                model_id,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'model_default', %s, %s)
            RETURNING prompt_assignment_id
            """,
                (stage_id, published_owned, model_id, principal_id),
            ).fetchone()
        )["prompt_assignment_id"]
        connection.execute(
            """
            UPDATE security.principal
               SET is_super_admin = TRUE,
                   updated_time = CURRENT_TIMESTAMP
             WHERE principal_id = %s
            """,
            (principal_id,),
        )
        global_assignment_id = require_row(
            connection.execute(
                """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'global_default', %s)
            RETURNING prompt_assignment_id
            """,
                (stage_id, published_global, principal_id),
            ).fetchone()
        )["prompt_assignment_id"]

    assert model_assignment_id > 0
    assert global_assignment_id > 0


def test_prompt_resolution_snapshots_override_then_model_then_global(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, principal_id = _create_model_and_principal(postgres_database)
    with postgres_database.connect_owner() as connection:
        tenant_id = require_row(
            connection.execute(
                "SELECT tenant_id FROM model.model WHERE model_id = %s",
                (model_id,),
            ).fetchone()
        )["tenant_id"]
        stage_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'dimensional', 'detailed_coverage', 'topology_builder',
                'Topology builder', 10, TRUE
            )
            RETURNING workflow_stage_id
            """
            ).fetchone()
        )["workflow_stage_id"]
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_expires_time
            ) VALUES (
                %s, %s, 'Prompt resolution',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_id, principal_id),
        )

    global_version_id = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=principal_id,
        ownership_scope="global",
        owner_tenant_id=None,
        published=True,
    )
    model_version_id = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=principal_id,
        ownership_scope="tenant",
        owner_tenant_id=tenant_id,
        published=True,
    )
    override_version_id = _create_prompt_version(
        postgres_database,
        workflow_stage_id=stage_id,
        principal_id=principal_id,
        ownership_scope="tenant",
        owner_tenant_id=tenant_id,
        published=True,
    )

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                model_id,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'model_default', %s, %s)
            """,
            (stage_id, model_version_id, model_id, principal_id),
        )
        connection.execute(
            """
            UPDATE security.principal
               SET is_super_admin = TRUE,
                   updated_time = CURRENT_TIMESTAMP
             WHERE principal_id = %s
            """,
            (principal_id,),
        )
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'global_default', %s)
            """,
            (stage_id, global_version_id, principal_id),
        )

    override_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="dimensional",
        workflow_execution_mode="detailed_coverage",
    )
    model_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="dimensional",
        workflow_execution_mode="detailed_coverage",
    )

    with postgres_database.connect_owner() as connection:
        override_count = require_row(
            connection.execute(
                """
            SELECT application.snapshot_workflow_run_prompts(
                %s,
                jsonb_build_object(%s::TEXT, %s)
            ) AS snapshot_count
            """,
                (override_run_id, stage_id, override_version_id),
            ).fetchone()
        )["snapshot_count"]
        model_count = require_row(
            connection.execute(
                """
            SELECT application.snapshot_workflow_run_prompts(
                %s,
                '{}'::JSONB
            ) AS snapshot_count
            """,
                (model_run_id,),
            ).fetchone()
        )["snapshot_count"]
        model_assignment_id = require_row(
            connection.execute(
                """
            UPDATE application.prompt_assignment
               SET is_active = FALSE,
                   deactivated_by_principal_id = %s,
                   deactivated_time = CURRENT_TIMESTAMP,
                   updated_time = CURRENT_TIMESTAMP
             WHERE model_id = %s
               AND workflow_stage_id = %s
               AND is_active
            RETURNING prompt_assignment_id
            """,
                (principal_id, model_id, stage_id),
            ).fetchone()
        )["prompt_assignment_id"]

    global_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="dimensional",
        workflow_execution_mode="detailed_coverage",
    )
    with postgres_database.connect_owner() as connection:
        global_count = require_row(
            connection.execute(
                """
            SELECT application.snapshot_workflow_run_prompts(
                %s,
                '{}'::JSONB
            ) AS snapshot_count
            """,
                (global_run_id,),
            ).fetchone()
        )["snapshot_count"]
        rows = connection.execute(
            """
            SELECT workflow_run_id,
                   prompt_template_version_id,
                   prompt_resolution_source
              FROM application.workflow_run_prompt_snapshot
             WHERE workflow_run_id IN (%s, %s, %s)
             ORDER BY workflow_run_id
            """,
            (override_run_id, model_run_id, global_run_id),
        ).fetchall()

    assert override_count == 1
    assert model_count == 1
    assert global_count == 1
    assert model_assignment_id > 0
    assert rows == [
        {
            "workflow_run_id": override_run_id,
            "prompt_template_version_id": override_version_id,
            "prompt_resolution_source": "run_override",
        },
        {
            "workflow_run_id": model_run_id,
            "prompt_template_version_id": model_version_id,
            "prompt_resolution_source": "model_default",
        },
        {
            "workflow_run_id": global_run_id,
            "prompt_template_version_id": global_version_id,
            "prompt_resolution_source": "global_default",
        },
    ]

    lie_run_id = _create_agentic_workflow_run(
        postgres_database,
        model_id=model_id,
        principal_id=principal_id,
        model_workflow="dimensional",
        workflow_execution_mode="detailed_coverage",
    )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(ForeignKeyViolation),
        connection.transaction(),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_run_prompt_snapshot (
                workflow_run_id,
                model_id,
                workflow_stage_id,
                prompt_template_version_id,
                prompt_resolution_source,
                prompt_template_digest
            ) VALUES (%s, %s, %s, %s, 'run_override', %s)
            """,
            (
                lie_run_id,
                model_id,
                stage_id,
                override_version_id,
                "f" * 64,
            ),
        )


def test_model_agent_defaults_are_optional_and_naming_is_not_coupled_to_audit(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, _ = _create_model_and_principal(postgres_database)

    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            UPDATE model.model
               SET silver_model_naming_instructions = 'Use clear business names.',
                   gold_model_audit_columns_template =
                       '[{"name":"created_time","type":"timestamp"}]'::JSONB,
                   default_agent_sdk_code = 'openai_agents_sdk',
                   default_agent_provider_code = 'microsoft_foundry',
                   default_agent_model_code = 'model-1',
                   default_reasoning_effort_code = 'medium',
                   default_max_turns = 50,
                   default_validation_retry_count = 5
             WHERE model_id = %s
            RETURNING silver_model_naming_instructions,
                      silver_model_audit_columns_template,
                      gold_model_audit_columns_template,
                      default_max_turns,
                      default_validation_retry_count
            """,
            (model_id,),
        ).fetchone()

    assert row == {
        "silver_model_naming_instructions": "Use clear business names.",
        "silver_model_audit_columns_template": None,
        "gold_model_audit_columns_template": [
            {"name": "created_time", "type": "timestamp"}
        ],
        "default_max_turns": 50,
        "default_validation_retry_count": 5,
    }

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(CheckViolation),
        connection.transaction(),
    ):
        connection.execute(
            """
            UPDATE model.model
               SET default_agent_model_code = NULL
             WHERE model_id = %s
            """,
            (model_id,),
        )
