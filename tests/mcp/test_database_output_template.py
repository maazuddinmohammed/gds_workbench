from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, LiteralString, cast
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, RaiseException

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


def _seed_mapping(connection: Any) -> dict[str, int]:
    _seed_demo_if_needed(connection)
    tenant = connection.execute(
        "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
    ).fetchone()
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
    source_system = connection.execute(
        "SELECT system_id FROM core.system WHERE system_code = 'DEMO_CUSTOMER_SYSTEM'"
    ).fetchone()
    assert tenant is not None and target is not None and source_system is not None
    model = connection.execute(
        """
        INSERT INTO model.model (tenant_id, model_name)
        VALUES (%s, %s)
        RETURNING model_id
        """,
        (tenant["tenant_id"], f"Output Template {uuid4().hex}"),
    ).fetchone()
    assert model is not None
    entity = connection.execute(
        """
        INSERT INTO workflow.logical_entity (
            model_id, logical_entity_name, logical_entity_definition,
            logical_entity_type, logical_entity_grain
        ) VALUES (%s, 'Customer', 'Customer.', 'core', 'One customer')
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
        ) VALUES (%s, %s, 'CustomerID', 'Customer ID.', 'bigint', 1)
        RETURNING logical_attribute_id
        """,
        (model["model_id"], entity["logical_entity_id"]),
    ).fetchone()
    assert logical_attribute is not None
    object_binding = connection.execute(
        """
        INSERT INTO workflow.model_object_binding (
            model_id, object_id, modeled_entity_type, logical_entity_id
        ) VALUES (%s, %s, 'logical_entity', %s)
        RETURNING model_object_binding_id
        """,
        (model["model_id"], target["object_id"], entity["logical_entity_id"]),
    ).fetchone()
    assert object_binding is not None
    attribute_binding = connection.execute(
        """
        INSERT INTO workflow.model_attribute_binding (
            model_object_binding_id, logical_attribute_id, attribute_id
        ) VALUES (%s, %s, %s)
        RETURNING model_attribute_binding_id
        """,
        (
            object_binding["model_object_binding_id"],
            logical_attribute["logical_attribute_id"],
            target["attribute_id"],
        ),
    ).fetchone()
    assert attribute_binding is not None
    connection.execute(
        """
        INSERT INTO workflow.mapping_source_system_dependency (
            model_id, modeled_entity_type, source_system_id
        ) VALUES (%s, 'logical_entity', %s)
        """,
        (model["model_id"], source_system["system_id"]),
    )
    mapping_object = connection.execute(
        """
        INSERT INTO workflow.mapping_object (
            model_id, model_object_binding_id, source_system_id,
            mapping_transformation_document
        ) VALUES (%s, %s, %s, '{"kind":"direct"}'::JSONB)
        RETURNING mapping_object_id
        """,
        (
            model["model_id"],
            object_binding["model_object_binding_id"],
            source_system["system_id"],
        ),
    ).fetchone()
    assert mapping_object is not None
    mapping_attribute = connection.execute(
        """
        INSERT INTO workflow.mapping_attribute (
            mapping_object_id, model_attribute_binding_id,
            attribute_mapping_transformation_document
        ) VALUES (%s, %s, '{"expression":"CustomerID"}'::JSONB)
        RETURNING mapping_attribute_id
        """,
        (
            mapping_object["mapping_object_id"],
            attribute_binding["model_attribute_binding_id"],
        ),
    ).fetchone()
    assert mapping_attribute is not None
    return {
        "mapping_object_id": mapping_object["mapping_object_id"],
        "mapping_attribute_id": mapping_attribute["mapping_attribute_id"],
    }


def _create_output_template(connection: Any) -> int:
    principal = connection.execute(
        """
        INSERT INTO security.principal (
            principal_type, principal_display_name, principal_email, is_super_admin
        ) VALUES ('user', 'Template Administrator', %s, TRUE)
        RETURNING principal_id
        """,
        (f"template-{uuid4().hex}@example.test",),
    ).fetchone()
    assert principal is not None
    code = f"mapping_object_{uuid4().hex}"
    template = connection.execute(
        """
        INSERT INTO application.output_template (
            output_template_code, output_template_name,
            output_template_target_type, output_template_schema_digest,
            created_by_principal_id, updated_by_principal_id
        ) VALUES (%s, 'Mapping Object', 'mapping_object', %s, %s, %s)
        RETURNING output_template_id
        """,
        (
            code,
            hashlib.sha256(code.encode()).hexdigest(),
            principal["principal_id"],
            principal["principal_id"],
        ),
    ).fetchone()
    assert template is not None
    connection.execute(
        """
        INSERT INTO application.output_template_field (
            output_template_id, output_template_field_name,
            output_template_field_description, output_template_field_data_type,
            output_template_field_is_required, output_template_field_order
        ) VALUES (%s, 'mapping_summary', 'Required mapping summary.', 'string', TRUE, 1)
        """,
        (template["output_template_id"],),
    )
    return template["output_template_id"]


def test_output_template_schema_identity_remains_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        template_id = _create_output_template(connection)

    with pytest.raises(RaiseException, match="schema is immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.output_template
                   SET output_template_schema_digest = %s
                 WHERE output_template_id = %s
                """,
                ("a" * 64, template_id),
            )


def test_mapping_document_is_free_form_and_template_is_advisory(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping(connection)
        template_id = _create_output_template(connection)
        selected = connection.execute(
            """
            UPDATE workflow.mapping_object
               SET output_template_id = %s,
                   mapping_transformation_document =
                       '{"agent_selected_structure":"allowed"}'::JSONB
             WHERE mapping_object_id = %s
            RETURNING output_template_id, mapping_transformation_document
            """,
            (template_id, mapping["mapping_object_id"]),
        ).fetchone()

    assert selected == {
        "output_template_id": template_id,
        "mapping_transformation_document": {"agent_selected_structure": "allowed"},
    }


def test_mapping_documents_must_be_json_objects(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping(connection)
        with pytest.raises(CheckViolation), connection.transaction():
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET mapping_transformation_document = '[]'::JSONB
                 WHERE mapping_object_id = %s
                """,
                (mapping["mapping_object_id"],),
            )
        with pytest.raises(CheckViolation), connection.transaction():
            connection.execute(
                """
                UPDATE workflow.mapping_attribute
                   SET attribute_mapping_transformation_document = '"value"'::JSONB
                 WHERE mapping_attribute_id = %s
                """,
                (mapping["mapping_attribute_id"],),
            )


def test_selected_output_template_must_exist(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping(connection)
        with pytest.raises(ForeignKeyViolation):
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET output_template_id = -1
                 WHERE mapping_object_id = %s
                """,
                (mapping["mapping_object_id"],),
            )
