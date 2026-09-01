from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import uuid4

import psycopg
import pytest
from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres


DATABASE_ROOT = Path(__file__).resolve().parents[2] / "database"
VERIFY_FILE = DATABASE_ROOT / "20_verify_install.sql"


def _seed_demo_if_needed(postgres_database: DisposablePostgres) -> None:
    with postgres_database.connect_owner() as connection:
        exists = connection.execute(
            "SELECT 1 FROM core.project WHERE project_code = 'DEMO_PROJECT'"
        ).fetchone()
        if exists is None:
            connection.execute(
                cast(
                    LiteralString,
                    (
                        DATABASE_ROOT / "seed" / "01_metadata_snapshot_demo.sql"
                    ).read_text(encoding="utf-8"),
                )
            )


def _seed_complete_sql_mapping_target(
    postgres_database: DisposablePostgres,
    *,
    source_system_count: int = 1,
) -> dict[str, int]:
    _seed_demo_if_needed(postgres_database)
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        seed = require_row(
            connection.execute(
                """
            SELECT tenant.tenant_id,
                   object.object_id,
                   system.system_id,
                   system.system_type_id
              FROM core.tenant AS tenant
              CROSS JOIN LATERAL (
                  SELECT candidate.object_id, candidate.connection_id
                    FROM core.object AS candidate
                   WHERE candidate.object_schema = 'silver_demo'
                   LIMIT 1
              ) AS object
              JOIN core.connection AS connection
                ON connection.connection_id = object.connection_id
              JOIN core.system AS system
                ON system.system_id = connection.system_id
             WHERE tenant.tenant_code = 'DEMO_TENANT'
            """
            ).fetchone()
        )
        model_row = require_row(
            connection.execute(
                """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id, model_revision
            """,
                (seed["tenant_id"], f"SQL Mapping Context {suffix}"),
            ).fetchone()
        )
        model_id = model_row["model_id"]
        connection.execute(
            "INSERT INTO model.model_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id, seed["object_id"]),
        )

        source_system_ids = [seed["system_id"]]
        if source_system_count == 2:
            source_system_ids.append(
                require_row(
                    connection.execute(
                        """
                    INSERT INTO core.system (
                        system_code,
                        system_name,
                        system_type_id
                    ) VALUES (%s, %s, %s)
                    RETURNING system_id
                    """,
                        (
                            f"sql_source_{suffix}",
                            f"SQL Source {suffix}",
                            seed["system_type_id"],
                        ),
                    ).fetchone()
                )["system_id"]
            )

        for position, source_system_id in enumerate(source_system_ids, start=1):
            entity_id = require_row(
                connection.execute(
                    """
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain,
                    logical_entity_dependency_order
                ) VALUES (%s, %s, %s, 'core', %s, %s)
                RETURNING logical_entity_id
                """,
                    (
                        model_id,
                        f"sql_entity_{position}_{suffix}",
                        f"SQL entity {position} for canonical Mapping context.",
                        f"One SQL entity {position} row",
                        position,
                    ),
                ).fetchone()
            )["logical_entity_id"]
            connection.execute(
                """
                INSERT INTO workflow.mapping_source_system_dependency (
                    model_id,
                    modeled_entity_type,
                    source_system_id,
                    source_system_dependency_order
                ) VALUES (%s, 'logical_entity', %s, %s)
                """,
                (model_id, source_system_id, position),
            )
            connection.execute(
                """
                INSERT INTO workflow.mapping_object (
                    model_id,
                    object_id,
                    source_system_id,
                    modeled_entity_type,
                    logical_entity_id,
                    object_dependency_order,
                    artifact_type,
                    artifact_generation_instructions,
                    mapping_profile_key,
                    mapping_profile_version,
                    mapping_profile_schema_digest,
                    mapping_package_document,
                    mapping_package_digest,
                    object_mapping_transformation_document
                ) VALUES (
                    %s, %s, %s, 'logical_entity', %s, %s,
                    'sql_file', 'Generate SQL for the complete Mapping.',
                    'free_form', '1.0.0', repeat('c', 64),
                    jsonb_build_object(
                        'schema_version', '1.0',
                        'source_position', %s
                    ),
                    %s,
                    jsonb_build_object(
                        'schema_version', '1.0',
                        'transformation_kind', 'direct'
                    )
                )
                """,
                (
                    model_id,
                    seed["object_id"],
                    source_system_id,
                    entity_id,
                    position,
                    position,
                    f"{position:064x}",
                ),
            )

    return {
        "tenant_id": seed["tenant_id"],
        "model_id": model_id,
        "object_id": seed["object_id"],
        "source_system_count": source_system_count,
    }


def test_sql_generation_guide_versions_are_audited_and_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    digest = hashlib.sha256(b"Follow approved SQL conventions.").hexdigest()
    with postgres_database.connect_owner() as connection:
        principal_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES (
                'user',
                'SQL Guide Administrator',
                'sql-guide-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
            ).fetchone()
        )["principal_id"]
        guide_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide (
                sql_generation_guide_code,
                sql_generation_guide_name,
                sql_generation_guide_description,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (
                'default_web_sql',
                'Default Web SQL',
                'Default SQL-only web generation guidance.',
                %s,
                %s
            )
            RETURNING sql_generation_guide_id
            """,
                (principal_id, principal_id),
            ).fetchone()
        )["sql_generation_guide_id"]
        version_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide_version (
                sql_generation_guide_id,
                sql_generation_guide_version_number,
                sql_generation_guide_content,
                sql_generation_guide_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (
                %s,
                1,
                'Follow approved SQL conventions.',
                %s,
                %s,
                %s
            )
            RETURNING sql_generation_guide_version_id
            """,
                (guide_id, digest, principal_id, principal_id),
            ).fetchone()
        )["sql_generation_guide_version_id"]
        connection.execute(
            """
            UPDATE application.sql_generation_guide_version
               SET sql_generation_guide_version_status = 'published',
                   published_time = CURRENT_TIMESTAMP,
                   published_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE sql_generation_guide_version_id = %s
            """,
            (principal_id, principal_id, version_id),
        )

    with pytest.raises(psycopg.errors.RaiseException, match="published.*immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.sql_generation_guide_version
                   SET sql_generation_guide_content = 'Changed after publication.'
                 WHERE sql_generation_guide_version_id = %s
                """,
                (version_id,),
            )

    with postgres_database.connect_owner() as connection:
        retired = require_row(
            connection.execute(
                """
            UPDATE application.sql_generation_guide_version
               SET sql_generation_guide_version_status = 'retired',
                   retired_time = CURRENT_TIMESTAMP,
                   retired_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE sql_generation_guide_version_id = %s
            RETURNING sql_generation_guide_version_status
            """,
                (principal_id, principal_id, version_id),
            ).fetchone()
        )
    assert retired["sql_generation_guide_version_status"] == "retired"

    with pytest.raises(psycopg.errors.RaiseException, match="cannot be deleted"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                DELETE FROM application.sql_generation_guide_version
                 WHERE sql_generation_guide_version_id = %s
                """,
                (version_id,),
            )


def test_sql_generation_guide_lifecycle_actor_matches_the_update_actor(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        principals = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES
                ('user', 'Guide Publisher', 'guide-publisher@example.test', TRUE),
                ('user', 'Different Guide Actor',
                 'different-guide-actor@example.test', TRUE)
            RETURNING principal_id
            """
        ).fetchall()
        guide_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide (
                sql_generation_guide_code,
                sql_generation_guide_name,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES ('actor_checked_guide', 'Actor Checked Guide', %s, %s)
            RETURNING sql_generation_guide_id
            """,
                (principals[0]["principal_id"], principals[0]["principal_id"]),
            ).fetchone()
        )["sql_generation_guide_id"]
        version_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide_version (
                sql_generation_guide_id,
                sql_generation_guide_version_number,
                sql_generation_guide_content,
                sql_generation_guide_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, 1, 'Approved placeholder.', %s, %s, %s)
            RETURNING sql_generation_guide_version_id
            """,
                (
                    guide_id,
                    hashlib.sha256(b"Approved placeholder.").hexdigest(),
                    principals[0]["principal_id"],
                    principals[0]["principal_id"],
                ),
            ).fetchone()
        )["sql_generation_guide_version_id"]

    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.sql_generation_guide_version
                   SET sql_generation_guide_version_status = 'published',
                       published_time = CURRENT_TIMESTAMP,
                       published_by_principal_id = %s,
                       updated_by_principal_id = %s,
                       updated_time = CURRENT_TIMESTAMP
                 WHERE sql_generation_guide_version_id = %s
                """,
                (
                    principals[0]["principal_id"],
                    principals[1]["principal_id"],
                    version_id,
                ),
            )


def test_code_generation_tables_freeze_run_contract_and_use_target_only_artifacts(
    postgres_database: DisposablePostgres,
) -> None:
    expected_columns = [
        "generated_sql_artifact_id",
        "model_id",
        "model_revision",
        "modeled_entity_type",
        "object_id",
        "mapping_context_digest",
        "source_context_digest",
        "sql_generation_guide_id",
        "sql_generation_guide_version_id",
        "sql_generation_guide_digest",
        "workflow_run_id",
        "generator_code",
        "generator_version",
        "generated_by_principal_id",
        "generated_time",
        "generated_sql",
        "generated_sql_digest",
        "created_time",
        "created_by",
        "updated_time",
        "updated_by",
    ]
    with postgres_database.connect_owner() as connection:
        artifact_rows = connection.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'application'
               AND table_name = 'generated_sql_artifact'
             ORDER BY ordinal_position
            """
        ).fetchall()
        run_columns = connection.execute(
            """
            SELECT column_name, is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'application'
               AND table_name = 'workflow_run'
               AND column_name IN (
                   'model_revision',
                   'code_generation_coverage_mode',
                   'sql_generation_guide_id',
                   'sql_generation_guide_version_id',
                   'sql_generation_guide_digest'
               )
             ORDER BY column_name
            """
        ).fetchall()
        artifact_identity = require_row(
            connection.execute(
                """
            SELECT array_agg(attribute.attname ORDER BY key.position) AS columns
              FROM pg_catalog.pg_constraint AS constraint_record
              CROSS JOIN LATERAL unnest(constraint_record.conkey)
                   WITH ORDINALITY AS key(attnum, position)
              JOIN pg_catalog.pg_attribute AS attribute
                ON attribute.attrelid = constraint_record.conrelid
               AND attribute.attnum = key.attnum
             WHERE constraint_record.conrelid =
                   'application.generated_sql_artifact'::regclass
               AND constraint_record.conname =
                   'uq_generated_sql_artifact_identity'
             GROUP BY constraint_record.oid
            """
            ).fetchone()
        )["columns"]

    assert [row["column_name"] for row in artifact_rows] == expected_columns
    assert run_columns == [
        {"column_name": "code_generation_coverage_mode", "is_nullable": "YES"},
        {"column_name": "model_revision", "is_nullable": "NO"},
        {"column_name": "sql_generation_guide_digest", "is_nullable": "YES"},
        {"column_name": "sql_generation_guide_id", "is_nullable": "YES"},
        {"column_name": "sql_generation_guide_version_id", "is_nullable": "YES"},
    ]
    assert artifact_identity == ["model_id", "modeled_entity_type", "object_id"]


def test_install_verifier_rejects_legacy_source_system_artifact_identity(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        with connection.transaction(force_rollback=True):
            connection.execute(
                """
                ALTER TABLE application.generated_sql_artifact
                    ADD COLUMN source_system_id BIGINT
                """
            )
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="Code Generation database contract is invalid",
            ):
                connection.execute(
                    cast(
                        LiteralString,
                        VERIFY_FILE.read_text(encoding="utf-8"),
                    )
                )


def test_code_generation_target_context_aggregates_all_source_systems_once(
    postgres_database: DisposablePostgres,
) -> None:
    target = _seed_complete_sql_mapping_target(
        postgres_database,
        source_system_count=2,
    )

    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT context.object_id,
                   context.source_system_count,
                   context.mapping_context_digest,
                   context.source_context_digest,
                   jsonb_array_length(
                       context.source_context -> 'source_systems'
                   ) AS source_systems,
                   jsonb_array_length(
                       context.source_context -> 'object_mappings'
                   ) AS object_mappings,
                   jsonb_array_length(
                       context.source_context -> 'attribute_mappings'
                   ) AS attribute_mappings,
                   encode(
                       sha256(convert_to(context.source_context::TEXT, 'UTF8')),
                       'hex'
                   ) AS recomputed_source_digest
              FROM workflow.list_code_generation_target_context(
                       %s,
                       'logical_entity'
                   ) AS context
            """,
            (target["model_id"],),
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["object_id"] == target["object_id"]
    assert rows[0]["source_system_count"] == 2
    assert rows[0]["source_systems"] == 2
    assert rows[0]["object_mappings"] == 2
    assert rows[0]["attribute_mappings"] == 0
    assert len(rows[0]["mapping_context_digest"]) == 64
    assert rows[0]["source_context_digest"] == rows[0]["recomputed_source_digest"]


def test_target_context_keeps_code_generation_sql_only_and_qa_artifact_neutral(
    postgres_database: DisposablePostgres,
) -> None:
    target = _seed_complete_sql_mapping_target(postgres_database)

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE workflow.mapping_object
               SET artifact_type = 'python_file'
             WHERE model_id = %s
            """,
            (target["model_id"],),
        )
        code_generation_rows = connection.execute(
            """
            SELECT object_id
              FROM workflow.list_code_generation_target_context(
                       %s,
                       'logical_entity'
                   )
            """,
            (target["model_id"],),
        ).fetchall()
        qa_rows = connection.execute(
            """
            SELECT object_id
              FROM workflow.list_code_generation_target_context(
                       %s,
                       'logical_entity',
                       NULL
                   )
            """,
            (target["model_id"],),
        ).fetchall()

    assert code_generation_rows == []
    assert [row["object_id"] for row in qa_rows] == [target["object_id"]]


def test_generated_sql_storage_uses_a_web_only_function_boundary(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        function_privileges = require_row(
            connection.execute(
                """
            SELECT has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND procedure.proname = 'store_generated_sql_artifact'
            """
            ).fetchone()
        )
        table_privileges = require_row(
            connection.execute(
                """
            SELECT has_table_privilege(
                       'gds_web_write',
                       'application.generated_sql_artifact',
                       'SELECT'
                   ) AS web_can_select,
                   has_table_privilege(
                       'gds_web_write',
                       'application.generated_sql_artifact',
                       'INSERT'
                   ) AS web_can_insert,
                   has_table_privilege(
                       'gds_web_write',
                       'application.generated_sql_artifact',
                       'UPDATE'
                   ) AS web_can_update,
                   has_table_privilege(
                       'gds_web_write',
                       'application.generated_sql_artifact',
                       'DELETE'
                   ) AS web_can_delete
            """
            ).fetchone()
        )

    assert function_privileges == {
        "web_can_execute": True,
        "mcp_can_execute": False,
    }
    assert table_privileges == {
        "web_can_select": True,
        "web_can_insert": False,
        "web_can_update": False,
        "web_can_delete": False,
    }


def test_store_generated_sql_replaces_only_after_complete_validation(
    postgres_database: DisposablePostgres,
) -> None:
    _seed_demo_if_needed(postgres_database)
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    first_sql = "SELECT 1"
    second_sql = "SELECT 2"

    with postgres_database.connect_owner() as connection:
        tenant_id = require_row(
            connection.execute(
                "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
            ).fetchone()
        )["tenant_id"]
        target = require_row(
            connection.execute(
                """
            SELECT object.object_id, connection.system_id
              FROM core.object AS object
              JOIN core.connection AS connection
                ON connection.connection_id = object.connection_id
             WHERE object.object_schema = 'silver_demo'
            """
            ).fetchone()
        )
        model_id = require_row(
            connection.execute(
                """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, 'Generated SQL Model')
            RETURNING model_id, model_revision
            """,
                (tenant_id,),
            ).fetchone()
        )
        connection.execute(
            "INSERT INTO model.model_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id["model_id"], target["object_id"]),
        )
        logical_entity_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.logical_entity (
                model_id,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            ) VALUES (
                %s,
                'generated_sql_target',
                'Logical target used by the SQL artifact test.',
                'core',
                'One generated target row'
            )
            RETURNING logical_entity_id
            """,
                (model_id["model_id"],),
            ).fetchone()
        )["logical_entity_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id,
                modeled_entity_type,
                source_system_id
            ) VALUES (%s, 'logical_entity', %s)
            """,
            (model_id["model_id"], target["system_id"]),
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_object (
                model_id,
                object_id,
                source_system_id,
                modeled_entity_type,
                logical_entity_id,
                artifact_type,
                artifact_generation_instructions,
                mapping_profile_key,
                mapping_profile_version,
                mapping_profile_schema_digest,
                mapping_package_document,
                mapping_package_digest,
                object_mapping_transformation_document
            ) VALUES (
                %s,
                %s,
                %s,
                'logical_entity',
                %s,
                'sql_file',
                'Generate one SQL file for the selected target.',
                'free_form',
                '1.0.0',
                repeat('c', 64),
                '{"schema_version":"1.0","mapping":"test"}'::JSONB,
                repeat('a', 64),
                '{"schema_version":"1.0","transformation_kind":"direct"}'::JSONB
            )
            """,
            (
                model_id["model_id"],
                target["object_id"],
                target["system_id"],
                logical_entity_id,
            ),
        )
        principal_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            ) VALUES ('user', 'SQL Generator', 'sql-generator@example.test')
            RETURNING principal_id
            """
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
                %s,
                %s,
                'SQL generation test',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_id, principal_id),
        )
        guide_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide (
                sql_generation_guide_code,
                sql_generation_guide_name,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES ('artifact_guide', 'Artifact Guide', %s, %s)
            RETURNING sql_generation_guide_id
            """,
                (principal_id, principal_id),
            ).fetchone()
        )["sql_generation_guide_id"]
        guide_digest = hashlib.sha256(b"Approved placeholder.").hexdigest()
        guide_version_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide_version (
                sql_generation_guide_id,
                sql_generation_guide_version_number,
                sql_generation_guide_content,
                sql_generation_guide_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, 1, 'Approved placeholder.', %s, %s, %s)
            RETURNING sql_generation_guide_version_id
            """,
                (guide_id, guide_digest, principal_id, principal_id),
            ).fetchone()
        )["sql_generation_guide_version_id"]
        connection.execute(
            """
            UPDATE application.sql_generation_guide_version
               SET sql_generation_guide_version_status = 'published',
                   published_time = CURRENT_TIMESTAMP,
                   published_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE sql_generation_guide_version_id = %s
            """,
            (principal_id, guide_version_id),
        )
        target_context = require_row(
            connection.execute(
                """
                SELECT mapping_context_digest, source_context_digest
                  FROM workflow.list_code_generation_target_context(
                           %s,
                           'logical_entity'
                       )
                 WHERE object_id = %s
                """,
                (model_id["model_id"], target["object_id"]),
            ).fetchone()
        )

    call_sql = """
        SELECT *
          FROM application.store_generated_sql_artifact(
              %s::UUID, %s::UUID, 'user'::VARCHAR,
              %s::BIGINT, %s::BIGINT, 'logical_entity'::VARCHAR,
              %s::BIGINT,
              %s::CHAR(64), %s::CHAR(64), %s::BIGINT, NULL::BIGINT,
              'web_sql_generator'::VARCHAR, '1.0.0'::VARCHAR,
              %s::TEXT, %s::CHAR(64)
          )
    """
    common = (
        entra_tenant_id,
        entra_object_id,
        model_id["model_id"],
        model_id["model_revision"],
        target["object_id"],
        target_context["mapping_context_digest"],
        target_context["source_context_digest"],
        guide_version_id,
    )
    with postgres_database.connect_owner() as connection:
        first = require_row(
            connection.execute(
                call_sql,
                (*common, first_sql, hashlib.sha256(first_sql.encode()).hexdigest()),
            ).fetchone()
        )

    with pytest.raises(psycopg.errors.RaiseException, match="digest"):
        with postgres_database.connect_owner() as connection:
            connection.execute(call_sql, (*common, second_sql, "f" * 64))

    with postgres_database.connect_owner() as connection:
        preserved = require_row(
            connection.execute(
                """
            SELECT generated_sql_artifact_id, generated_sql
              FROM application.generated_sql_artifact
             WHERE generated_sql_artifact_id = %s
            """,
                (first["generated_sql_artifact_id"],),
            ).fetchone()
        )
        second = require_row(
            connection.execute(
                call_sql,
                (*common, second_sql, hashlib.sha256(second_sql.encode()).hexdigest()),
            ).fetchone()
        )

    assert preserved["generated_sql"] == first_sql
    assert second["generated_sql_artifact_id"] == first["generated_sql_artifact_id"]
    assert second["generated_sql"] == second_sql
