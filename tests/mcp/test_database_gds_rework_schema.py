from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, LiteralString, cast

import pytest
from psycopg.errors import CheckViolation, NotNullViolation

if TYPE_CHECKING:
    from conftest import DisposablePostgres


DATABASE_ROOT = Path(__file__).resolve().parents[2] / "database"


def _seed_demo_if_needed(connection: Any) -> None:
    if (
        connection.execute(
            "SELECT 1 FROM core.project WHERE project_code = 'DEMO_PROJECT'"
        ).fetchone()
        is None
    ):
        connection.execute(
            cast(
                LiteralString,
                (DATABASE_ROOT / "seed" / "01_metadata_snapshot_demo.sql").read_text(
                    encoding="utf-8"
                ),
            )
        )


def test_rework_tables_expose_only_the_approved_columns(
    postgres_database: DisposablePostgres,
) -> None:
    expected = {
        ("model", "model_input_scope"): (
            "model_input_scope_id",
            "model_id",
            "object_id",
            "model_input_scope_is_locked",
            "is_active",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
        ("workflow", "model_object_binding"): (
            "model_object_binding_id",
            "model_id",
            "object_id",
            "modeled_entity_type",
            "logical_entity_id",
            "dimensional_entity_id",
            "agent_run_id",
            "workflow_run_id",
            "model_object_binding_status",
            "model_object_binding_is_locked",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
        ("workflow", "model_attribute_binding"): (
            "model_attribute_binding_id",
            "model_object_binding_id",
            "logical_attribute_id",
            "dimensional_attribute_id",
            "attribute_id",
            "agent_run_id",
            "workflow_run_id",
            "model_attribute_binding_status",
            "model_attribute_binding_is_locked",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
        ("workflow", "mapping_object"): (
            "mapping_object_id",
            "model_id",
            "model_object_binding_id",
            "source_system_id",
            "output_template_id",
            "object_dependency_order",
            "mapping_transformation_document",
            "agent_run_id",
            "workflow_run_id",
            "object_mapping_status",
            "object_mapping_is_locked",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
        ("workflow", "mapping_attribute"): (
            "mapping_attribute_id",
            "mapping_object_id",
            "model_attribute_binding_id",
            "output_template_id",
            "attribute_mapping_transformation_document",
            "agent_run_id",
            "workflow_run_id",
            "attribute_mapping_status",
            "attribute_mapping_is_locked",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
        ("workflow", "generated_code"): (
            "generated_code_id",
            "model_object_binding_id",
            "artifact_name",
            "artifact_type",
            "generated_code_content",
            "code_input_digest",
            "generated_code_digest",
            "agent_run_id",
            "workflow_run_id",
            "generated_code_status",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
        ("workflow", "generated_code_source_system"): (
            "generated_code_source_system_id",
            "generated_code_id",
            "source_system_id",
            "agent_run_id",
            "workflow_run_id",
            "generated_code_source_system_status",
            "created_time",
            "created_by",
            "updated_time",
            "updated_by",
        ),
    }
    with postgres_database.connect_owner() as connection:
        for (schema_name, table_name), expected_columns in expected.items():
            rows = connection.execute(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = %s
                   AND table_name = %s
                 ORDER BY ordinal_position
                """,
                (schema_name, table_name),
            ).fetchall()
            assert tuple(row["column_name"] for row in rows) == expected_columns

        removed = connection.execute(
            """
            SELECT to_regclass('model.model_scope') AS model_scope,
                   to_regclass('core.tenant_metadata_discovery_scope')
                       AS discovery_scope,
                   to_regclass('application.generated_sql_artifact')
                       AS generated_sql_artifact,
                   to_regprocedure(
                       'application.replace_model_scope(uuid,uuid,character varying,bigint,bigint,bigint[])'
                   ) AS replace_model_scope,
                   to_regprocedure(
                       'application.store_generated_sql_artifact(uuid,uuid,character varying,bigint,bigint,bigint,character varying,character varying,text,character,character,character,bigint,uuid)'
                   ) AS store_generated_sql_artifact
            """
        ).fetchone()

    assert removed == {
        "model_scope": None,
        "discovery_scope": None,
        "generated_sql_artifact": None,
        "replace_model_scope": None,
        "store_generated_sql_artifact": None,
    }


def test_applied_schema_has_no_needs_review_status(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT namespace_record.nspname AS schema_name,
                   relation.relname AS table_name,
                   constraint_record.conname AS constraint_name
              FROM pg_catalog.pg_constraint AS constraint_record
              JOIN pg_catalog.pg_class AS relation
                ON relation.oid = constraint_record.conrelid
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname IN ('model', 'workflow')
               AND constraint_record.contype = 'c'
               AND pg_get_constraintdef(constraint_record.oid) ILIKE
                   '%needs_review%'
            """
        ).fetchall()

    assert rows == []


def test_generated_code_digest_is_server_derived_and_has_no_review_flags(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        context = connection.execute(
            """
            WITH inserted_model AS (
                INSERT INTO model.model (tenant_id, model_name)
                SELECT tenant_id, 'Generated Code Contract'
                  FROM core.tenant
                 WHERE tenant_code = 'DEMO_TENANT'
                RETURNING model_id
            ), inserted_entity AS (
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain
                )
                SELECT model_id, 'Customer', 'Customer', 'core', 'One customer'
                  FROM inserted_model
                RETURNING model_id, logical_entity_id
            )
            INSERT INTO workflow.model_object_binding (
                model_id,
                object_id,
                modeled_entity_type,
                logical_entity_id
            )
            SELECT inserted_entity.model_id,
                   object_record.object_id,
                   'logical_entity',
                   inserted_entity.logical_entity_id
              FROM inserted_entity
              JOIN core.object AS object_record
                ON object_record.object_schema = 'silver_demo'
            RETURNING model_object_binding_id
            """
        ).fetchone()
        assert context is not None
        content = "SELECT 1 AS CustomerID"
        stored = connection.execute(
            """
            INSERT INTO workflow.generated_code (
                model_object_binding_id,
                artifact_name,
                artifact_type,
                generated_code_content,
                code_input_digest
            ) VALUES (%s, 'Customer.sql', 'sql_file', %s, %s)
            RETURNING generated_code_digest
            """,
            (context["model_object_binding_id"], content, "a" * 64),
        ).fetchone()

    assert stored == {"generated_code_digest": sha256(content.encode()).hexdigest()}


def test_code_context_returns_one_server_derived_input_digest(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        assert tenant is not None
        model = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, 'Code Context Contract')
            RETURNING model_id
            """,
            (tenant["tenant_id"],),
        ).fetchone()
        assert model is not None
        entity = connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                model_id, logical_entity_name, logical_entity_definition,
                logical_entity_type, logical_entity_grain
            ) VALUES (%s, 'Customer', 'Customer', 'core', 'One customer')
            RETURNING logical_entity_id
            """,
            (model["model_id"],),
        ).fetchone()
        assert entity is not None
        logical_attribute = connection.execute(
            """
            INSERT INTO workflow.logical_attribute (
                model_id, logical_entity_id, logical_attribute_name,
                logical_attribute_definition, logical_attribute_data_type,
                logical_attribute_ordinal_position
            ) VALUES (%s, %s, 'CustomerID', 'Customer ID', 'bigint', 1)
            RETURNING logical_attribute_id
            """,
            (model["model_id"], entity["logical_entity_id"]),
        ).fetchone()
        assert logical_attribute is not None
        target = connection.execute(
            """
            SELECT object_record.object_id, attribute.attribute_id
              FROM core.object AS object_record
              JOIN core.attribute AS attribute
                ON attribute.object_id = object_record.object_id
             WHERE object_record.object_schema = 'silver_demo'
             ORDER BY attribute.attribute_ordinal_position
             LIMIT 1
            """
        ).fetchone()
        assert target is not None
        binding = connection.execute(
            """
            INSERT INTO workflow.model_object_binding (
                model_id, object_id, modeled_entity_type, logical_entity_id
            ) VALUES (%s, %s, 'logical_entity', %s)
            RETURNING model_object_binding_id
            """,
            (
                model["model_id"],
                target["object_id"],
                entity["logical_entity_id"],
            ),
        ).fetchone()
        assert binding is not None
        attribute_binding = connection.execute(
            """
            INSERT INTO workflow.model_attribute_binding (
                model_object_binding_id, logical_attribute_id, attribute_id
            ) VALUES (%s, %s, %s)
            RETURNING model_attribute_binding_id
            """,
            (
                binding["model_object_binding_id"],
                logical_attribute["logical_attribute_id"],
                target["attribute_id"],
            ),
        ).fetchone()
        assert attribute_binding is not None
        source_system = connection.execute(
            "SELECT system_id FROM core.system WHERE system_code = 'DEMO_CUSTOMER_SYSTEM'"
        ).fetchone()
        assert source_system is not None
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id, modeled_entity_type, source_system_id
            ) VALUES (%s, 'logical_entity', %s)
            """,
            (model["model_id"], source_system["system_id"]),
        )
        mapping = connection.execute(
            """
            INSERT INTO workflow.mapping_object (
                model_id, model_object_binding_id, source_system_id,
                mapping_transformation_document
            ) VALUES (%s, %s, %s, '{"kind":"direct"}'::JSONB)
            RETURNING mapping_object_id
            """,
            (
                model["model_id"],
                binding["model_object_binding_id"],
                source_system["system_id"],
            ),
        ).fetchone()
        assert mapping is not None
        connection.execute(
            """
            INSERT INTO workflow.mapping_attribute (
                mapping_object_id, model_attribute_binding_id,
                attribute_mapping_transformation_document
            ) VALUES (%s, %s, '{"expression":"CustomerID"}'::JSONB)
            """,
            (
                mapping["mapping_object_id"],
                attribute_binding["model_attribute_binding_id"],
            ),
        )
        first = connection.execute(
            """
            SELECT *
              FROM workflow.list_code_generation_target_context(
                  %s, 'logical_entity', 'sql_file'
              )
            """,
            (model["model_id"],),
        ).fetchone()
        assert first is not None
        connection.execute(
            """
            UPDATE workflow.mapping_object
               SET mapping_transformation_document =
                   '{"kind":"direct","filter":"IsActive"}'::JSONB
             WHERE mapping_object_id = %s
            """,
            (mapping["mapping_object_id"],),
        )
        second = connection.execute(
            """
            SELECT *
              FROM workflow.list_code_generation_target_context(
                  %s, 'logical_entity', 'sql_file'
              )
            """,
            (model["model_id"],),
        ).fetchone()

    assert second is not None
    assert first["modeled_entity_name"] == "Customer"
    assert first["source_system_count"] == 1
    assert len(first["code_input_digest"].strip()) == 64
    assert first["source_context"]["target"]["object_id"] == target["object_id"]
    assert first["source_context"]["target"]["source_tenant_id"] == tenant["tenant_id"]
    assert first["source_context"]["target"]["source_tenant_code"] == "DEMO_TENANT"
    assert first["source_context"]["target"]["tenant_code"] == "DEMO_GDS_TENANT"
    assert first["code_input_digest"] != second["code_input_digest"]


def test_object_source_tenant_is_required(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        physical = connection.execute(
            """
            SELECT connection_id, object_type_id, zone_id
              FROM core.object
             ORDER BY object_id
             LIMIT 1
            """
        ).fetchone()
        assert physical is not None
        with pytest.raises(NotNullViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO core.object (
                    connection_id, object_schema, object_name,
                    object_type_id, zone_id
                ) VALUES (%s, 'public', 'missing_owner', %s, %s)
                """,
                (
                    physical["connection_id"],
                    physical["object_type_id"],
                    physical["zone_id"],
                ),
            )


def test_index_set_omits_speculative_workflow_run_indexes(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        speculative = connection.execute(
            """
            SELECT schemaname, indexname
              FROM pg_catalog.pg_indexes
             WHERE schemaname IN ('model', 'workflow', 'application')
               AND indexname LIKE '%\\_workflow\\_run' ESCAPE '\\'
             ORDER BY schemaname, indexname
            """
        ).fetchall()
        retained = connection.execute(
            """
            SELECT indexname
              FROM pg_catalog.pg_indexes
             WHERE indexname = ANY(%s::TEXT[])
             ORDER BY indexname
            """,
            (
                [
                    "ix_mapping_object_model_wave",
                    "ix_mapping_source_dependency_wave",
                    "ix_object_source_tenant_zone_active",
                    "ix_workflow_run_claim_eligibility",
                ],
            ),
        ).fetchall()

    assert speculative == []
    assert [row["indexname"] for row in retained] == [
        "ix_mapping_object_model_wave",
        "ix_mapping_source_dependency_wave",
        "ix_object_source_tenant_zone_active",
        "ix_workflow_run_claim_eligibility",
    ]


def test_needs_review_is_rejected_by_an_applied_table(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        assert tenant is not None
        model = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, 'Status Contract')
            RETURNING model_id
            """,
            (tenant["tenant_id"],),
        ).fetchone()
        assert model is not None
        with pytest.raises(CheckViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id, logical_entity_name, logical_entity_definition,
                    logical_entity_type, logical_entity_grain,
                    logical_entity_status
                ) VALUES (%s, 'Customer', 'Customer', 'core', 'One', 'needs_review')
                """,
                (model["model_id"],),
            )
