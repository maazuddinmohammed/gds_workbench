from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import psycopg
import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


def test_output_template_has_stable_schema_identity_and_actor_audit(
    postgres_database: DisposablePostgres,
) -> None:
    schema_digest = hashlib.sha256(b"mapping-object-template-v1").hexdigest()

    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            )
            VALUES (
                'user',
                'Output Template Administrator',
                'output-template-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None

        template = connection.execute(
            """
            INSERT INTO application.output_template (
                output_template_code,
                output_template_name,
                output_template_description,
                output_template_target_type,
                output_template_schema_digest,
                created_by_principal_id,
                updated_by_principal_id
            )
            VALUES (
                'standard_mapping_object',
                'Standard Mapping Object',
                'Ordered fields for one Mapping Object output.',
                'mapping_object',
                %s,
                %s,
                %s
            )
            RETURNING output_template_id,
                      output_template_schema_digest,
                      created_by_principal_id,
                      updated_by_principal_id,
                      created_time,
                      updated_time
            """,
            (
                schema_digest,
                principal["principal_id"],
                principal["principal_id"],
            ),
        ).fetchone()
        assert template is not None

        connection.execute(
            """
            INSERT INTO application.output_template_field (
                output_template_id,
                output_template_field_name,
                output_template_field_description,
                output_template_field_data_type,
                output_template_field_array_item_type,
                output_template_field_is_required,
                output_template_field_order
            )
            VALUES
                (%s, 'target_grain', 'Target grain.', 'string', NULL, TRUE, 10),
                (%s, 'business_keys', 'Ordered business keys.',
                 'array', 'string', TRUE, 20)
            """,
            (template["output_template_id"], template["output_template_id"]),
        )
        fields = connection.execute(
            """
            SELECT output_template_field_name,
                   output_template_field_data_type,
                   output_template_field_order
              FROM application.output_template_field
             WHERE output_template_id = %s
             ORDER BY output_template_field_order
            """,
            (template["output_template_id"],),
        ).fetchall()

    assert template["output_template_schema_digest"] == schema_digest
    assert template["created_by_principal_id"] == principal["principal_id"]
    assert template["updated_by_principal_id"] == principal["principal_id"]
    assert template["created_time"] <= template["updated_time"]
    assert fields == [
        {
            "output_template_field_name": "target_grain",
            "output_template_field_data_type": "string",
            "output_template_field_order": 10,
        },
        {
            "output_template_field_name": "business_keys",
            "output_template_field_data_type": "array",
            "output_template_field_order": 20,
        },
    ]


def test_output_template_schema_digest_is_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    schema_digest = hashlib.sha256(b"immutable-mapping-object-template").hexdigest()

    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            )
            VALUES (
                'user',
                'Immutable Template Administrator',
                'immutable-template-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        template = connection.execute(
            """
            INSERT INTO application.output_template (
                output_template_code,
                output_template_name,
                output_template_target_type,
                output_template_schema_digest,
                created_by_principal_id,
                updated_by_principal_id
            )
            VALUES ('immutable_mapping_object', 'Immutable Mapping Object',
                    'mapping_object', %s, %s, %s)
            RETURNING output_template_id
            """,
            (
                schema_digest,
                principal["principal_id"],
                principal["principal_id"],
            ),
        ).fetchone()
        assert template is not None
        field = connection.execute(
            """
            INSERT INTO application.output_template_field (
                output_template_id,
                output_template_field_name,
                output_template_field_description,
                output_template_field_data_type,
                output_template_field_order
            )
            VALUES (%s, 'mapping_summary', 'Mapping summary.', 'string', 10)
            RETURNING output_template_field_id
            """,
            (template["output_template_id"],),
        ).fetchone()
        assert field is not None

    replacement_digest = hashlib.sha256(b"replacement-schema").hexdigest()
    with pytest.raises(psycopg.errors.RaiseException, match="schema is immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.output_template
                   SET output_template_schema_digest = %s
                 WHERE output_template_id = %s
                """,
                (replacement_digest, template["output_template_id"]),
            )

    with pytest.raises(psycopg.errors.RaiseException, match="fields are immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.output_template_field
                   SET output_template_field_description = 'Changed description.'
                 WHERE output_template_field_id = %s
                """,
                (field["output_template_field_id"],),
            )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="fields must be created atomically",
    ):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                INSERT INTO application.output_template_field (
                    output_template_id,
                    output_template_field_name,
                    output_template_field_description,
                    output_template_field_data_type,
                    output_template_field_order
                )
                VALUES (%s, 'late_field', 'Late field.', 'string', 20)
                """,
                (template["output_template_id"],),
            )

    with pytest.raises(psycopg.errors.RaiseException, match="fields cannot be deleted"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                DELETE FROM application.output_template_field
                 WHERE output_template_field_id = %s
                """,
                (field["output_template_field_id"],),
            )

    with pytest.raises(
        psycopg.errors.RaiseException, match="templates cannot be deleted"
    ):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                DELETE FROM application.output_template
                 WHERE output_template_id = %s
                """,
                (template["output_template_id"],),
            )


def test_mapping_remains_free_form_when_output_template_is_not_selected(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping_rows(connection, prefix="OUTPUT_TEMPLATE_FREEFORM")

    assert mapping["object_output_template_id"] is None
    assert mapping["attribute_output_template_id"] is None


def test_mapping_output_template_provenance_enforces_target_type(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping_rows(connection, prefix="OUTPUT_TEMPLATE_PROVENANCE")
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            )
            VALUES (
                'user',
                'Mapping Template Administrator',
                'mapping-template-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        object_template_id = _create_output_template(
            connection,
            code="mapping_object_provenance",
            target_type="mapping_object",
            principal_id=principal["principal_id"],
        )
        attribute_template_id = _create_output_template(
            connection,
            code="mapping_attribute_provenance",
            target_type="mapping_attribute",
            principal_id=principal["principal_id"],
        )
        selected = connection.execute(
            """
            UPDATE workflow.mapping_object
               SET output_template_id = %s,
                   artifact_type = 'sql_file',
                   artifact_generation_instructions = 'Generate SQL.',
                   mapping_profile_key = 'template.provenance',
                   mapping_profile_version = '1.0.0',
                   mapping_profile_schema_digest = repeat('d', 64),
                   mapping_package_document = '{"mapping":"direct"}'::JSONB,
                   mapping_package_digest = repeat('e', 64),
                   object_mapping_transformation_document =
                       '{"schema_version":"1.0",'
                       '"transformation_kind":"direct",'
                       '"mapping_summary":"Direct mapping."}'::JSONB
             WHERE mapping_object_id = %s
            RETURNING output_template_id
            """,
            (object_template_id, mapping["mapping_object_id"]),
        ).fetchone()
        assert selected == {"output_template_id": object_template_id}
        selected = connection.execute(
            """
            UPDATE workflow.mapping_attribute
               SET output_template_id = %s,
                   attribute_mapping_transformation_document =
                       '{"schema_version":"1.0",'
                       '"transformation_kind":"direct",'
                       '"mapping_summary":"Direct attribute mapping."}'::JSONB
             WHERE mapping_attribute_id = %s
            RETURNING output_template_id
            """,
            (attribute_template_id, mapping["mapping_attribute_id"]),
        ).fetchone()
        assert selected == {"output_template_id": attribute_template_id}

    with pytest.raises(psycopg.errors.RaiseException, match="requires mapping_object"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET output_template_id = %s
                 WHERE mapping_object_id = %s
                """,
                (attribute_template_id, mapping["mapping_object_id"]),
            )

    with pytest.raises(
        psycopg.errors.RaiseException, match="requires mapping_attribute"
    ):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_attribute
                   SET output_template_id = %s
                 WHERE mapping_attribute_id = %s
                """,
                (object_template_id, mapping["mapping_attribute_id"]),
            )


def test_selected_output_template_validates_the_mapping_document(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping_rows(connection, prefix="OUTPUT_TEMPLATE_VALIDATION")
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES (
                'user',
                'Structured Mapping Administrator',
                'structured-mapping-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        template_id = _create_output_template(
            connection,
            code="mapping_object_validation",
            target_type="mapping_object",
            principal_id=principal["principal_id"],
        )

    with pytest.raises(psycopg.errors.RaiseException, match="document is required"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET output_template_id = %s
                 WHERE mapping_object_id = %s
                """,
                (template_id, mapping["mapping_object_id"]),
            )

    with pytest.raises(psycopg.errors.RaiseException, match="mapping_summary.*string"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET output_template_id = %s,
                       artifact_type = 'sql_file',
                       artifact_generation_instructions = 'Generate SQL.',
                       mapping_profile_key = 'template.validation',
                       mapping_profile_version = '1.0.0',
                       mapping_profile_schema_digest = repeat('d', 64),
                       mapping_package_document =
                           '{"mapping":"validation"}'::JSONB,
                       mapping_package_digest = repeat('e', 64),
                       object_mapping_transformation_document =
                           '{"schema_version":"1.0",'
                           '"transformation_kind":"direct",'
                           '"mapping_summary":[]}'::JSONB
                 WHERE mapping_object_id = %s
                """,
                (template_id, mapping["mapping_object_id"]),
            )

    with pytest.raises(psycopg.errors.RaiseException, match="undeclared field"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET output_template_id = %s,
                       artifact_type = 'sql_file',
                       artifact_generation_instructions = 'Generate SQL.',
                       mapping_profile_key = 'template.validation',
                       mapping_profile_version = '1.0.0',
                       mapping_profile_schema_digest = repeat('d', 64),
                       mapping_package_document =
                           '{"mapping":"validation"}'::JSONB,
                       mapping_package_digest = repeat('e', 64),
                       object_mapping_transformation_document =
                           '{"schema_version":"1.0",'
                           '"transformation_kind":"direct",'
                           '"mapping_summary":"Direct mapping.",'
                           '"unexpected":"not declared"}'::JSONB
                 WHERE mapping_object_id = %s
                """,
                (template_id, mapping["mapping_object_id"]),
            )

    with postgres_database.connect_owner() as connection:
        selected = connection.execute(
            """
            UPDATE workflow.mapping_object
               SET output_template_id = %s,
                   artifact_type = 'sql_file',
                   artifact_generation_instructions = 'Generate SQL.',
                   mapping_profile_key = 'template.validation',
                   mapping_profile_version = '1.0.0',
                   mapping_profile_schema_digest = repeat('d', 64),
                   mapping_package_document =
                       '{"mapping":"validation"}'::JSONB,
                   mapping_package_digest = repeat('e', 64),
                   object_mapping_transformation_document =
                       '{"schema_version":"1.0",'
                       '"transformation_kind":"direct",'
                       '"mapping_summary":"Direct mapping."}'::JSONB
             WHERE mapping_object_id = %s
            RETURNING output_template_id
            """,
            (template_id, mapping["mapping_object_id"]),
        ).fetchone()

    assert selected == {"output_template_id": template_id}

    with pytest.raises(
        psycopg.errors.RaiseException, match="mapping_summary.*required"
    ):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET object_mapping_transformation_document =
                           '{"schema_version":"1.0",'
                           '"transformation_kind":"direct"}'::JSONB
                 WHERE mapping_object_id = %s
                """,
                (mapping["mapping_object_id"],),
            )


def test_selected_output_template_validates_for_gds_app_write(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping_rows(
            connection,
            prefix="OUTPUT_TEMPLATE_RUNTIME_ROLE",
        )
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES (
                'user',
                'Runtime Template Administrator',
                'runtime-template-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        template_id = _create_output_template(
            connection,
            code="mapping_object_runtime_role",
            target_type="mapping_object",
            principal_id=_required_id(principal, "principal_id"),
        )

    with postgres_database.connect_runtime() as connection:
        selected = _select_mapping_object_template(
            connection,
            mapping_object_id=_required_id(mapping, "mapping_object_id"),
            output_template_id=template_id,
            document={
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "mapping_summary": "Validated as the MCP runtime role.",
            },
        )

    assert selected == {
        "output_template_id": template_id,
        "current_role": "gds_app_write",
    }


def test_selected_output_template_requires_a_valid_reserved_envelope(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping_rows(
            connection,
            prefix="OUTPUT_TEMPLATE_RESERVED_ENVELOPE",
        )
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES (
                'user',
                'Reserved Envelope Administrator',
                'reserved-envelope-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        template_id = _create_output_template(
            connection,
            code="mapping_object_reserved_envelope",
            target_type="mapping_object",
            principal_id=_required_id(principal, "principal_id"),
        )

    invalid_documents: tuple[tuple[dict[str, object], str], ...] = (
        (
            {
                "transformation_kind": "direct",
                "mapping_summary": "Missing schema version.",
            },
            "schema_version",
        ),
        (
            {
                "schema_version": "2.0",
                "transformation_kind": "direct",
                "mapping_summary": "Wrong schema version.",
            },
            "schema_version",
        ),
        (
            {
                "schema_version": 1.0,
                "transformation_kind": "direct",
                "mapping_summary": "Schema version is not a string.",
            },
            "schema_version",
        ),
        (
            {
                "schema_version": "1.0",
                "mapping_summary": "Missing transformation kind.",
            },
            "transformation_kind",
        ),
        (
            {
                "schema_version": "1.0",
                "transformation_kind": "expression",
                "mapping_summary": "Wrong transformation kind.",
            },
            "transformation_kind",
        ),
        (
            {
                "schema_version": "1.0",
                "transformation_kind": ["direct"],
                "mapping_summary": "Transformation kind is not a string.",
            },
            "transformation_kind",
        ),
    )
    for document, message in invalid_documents:
        with pytest.raises(psycopg.errors.RaiseException, match=message):
            with postgres_database.connect_owner() as connection:
                _select_mapping_object_template(
                    connection,
                    mapping_object_id=_required_id(mapping, "mapping_object_id"),
                    output_template_id=template_id,
                    document=document,
                )


def test_selected_output_template_accepts_integral_json_numbers(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        mapping = _seed_mapping_rows(
            connection,
            prefix="OUTPUT_TEMPLATE_INTEGRAL_NUMBERS",
        )
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES (
                'user',
                'Integral Number Administrator',
                'integral-number-administrator@example.test',
                TRUE
            )
            RETURNING principal_id
            """
        ).fetchone()
        template_id = _create_output_template(
            connection,
            code="mapping_object_integral_numbers",
            target_type="mapping_object",
            principal_id=_required_id(principal, "principal_id"),
        )
        connection.execute(
            """
            INSERT INTO application.output_template_field (
                output_template_id,
                output_template_field_name,
                output_template_field_description,
                output_template_field_data_type,
                output_template_field_array_item_type,
                output_template_field_order
            ) VALUES
                (%s, 'row_count', 'Expected row count.', 'integer', NULL, 20),
                (%s, 'source_ordinals', 'Source ordinals.', 'array', 'integer', 30)
            """,
            (template_id, template_id),
        )

    with postgres_database.connect_owner() as connection:
        selected = _select_mapping_object_template(
            connection,
            mapping_object_id=_required_id(mapping, "mapping_object_id"),
            output_template_id=template_id,
            document={
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "mapping_summary": "Integral numeric values.",
                "row_count": 1.0,
                "source_ordinals": [1.0, 2.0],
            },
        )

    assert selected["output_template_id"] == template_id


def test_output_template_field_description_is_bounded(
    postgres_database: DisposablePostgres,
) -> None:
    with pytest.raises(psycopg.errors.StringDataRightTruncation):
        with postgres_database.connect_owner() as connection:
            principal = connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email,
                    is_super_admin
                )
                VALUES (
                    'user',
                    'Bounded Template Administrator',
                    'bounded-template-administrator@example.test',
                    TRUE
                )
                RETURNING principal_id
                """
            ).fetchone()
            assert principal is not None
            template = connection.execute(
                """
                INSERT INTO application.output_template (
                    output_template_code,
                    output_template_name,
                    output_template_target_type,
                    output_template_schema_digest,
                    created_by_principal_id,
                    updated_by_principal_id
                )
                VALUES ('bounded_mapping_object', 'Bounded Mapping Object',
                        'mapping_object', %s, %s, %s)
                RETURNING output_template_id
                """,
                (
                    hashlib.sha256(b"bounded-mapping-object").hexdigest(),
                    principal["principal_id"],
                    principal["principal_id"],
                ),
            ).fetchone()
            assert template is not None
            connection.execute(
                """
                INSERT INTO application.output_template_field (
                    output_template_id,
                    output_template_field_name,
                    output_template_field_description,
                    output_template_field_data_type,
                    output_template_field_order
                )
                VALUES (%s, 'too_long', %s, 'string', 10)
                """,
                (template["output_template_id"], "x" * 2001),
            )


def _create_output_template(
    connection: Connection[Any],
    *,
    code: str,
    target_type: str,
    principal_id: int,
) -> int:
    template = connection.execute(
        """
        INSERT INTO application.output_template (
            output_template_code,
            output_template_name,
            output_template_target_type,
            output_template_schema_digest,
            created_by_principal_id,
            updated_by_principal_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING output_template_id
        """,
        (
            code,
            code.replace("_", " ").title(),
            target_type,
            hashlib.sha256(code.encode("ascii")).hexdigest(),
            principal_id,
            principal_id,
        ),
    ).fetchone()
    assert template is not None
    connection.execute(
        """
        INSERT INTO application.output_template_field (
            output_template_id,
            output_template_field_name,
            output_template_field_description,
            output_template_field_data_type,
            output_template_field_order
        )
        VALUES (%s, 'mapping_summary', 'Mapping summary.', 'string', 10)
        """,
        (template["output_template_id"],),
    )
    return _required_id(template, "output_template_id")


def _select_mapping_object_template(
    connection: Connection[Any],
    *,
    mapping_object_id: int,
    output_template_id: int,
    document: dict[str, object],
) -> dict[str, Any]:
    selected = connection.execute(
        """
        UPDATE workflow.mapping_object
           SET output_template_id = %s,
               artifact_type = 'sql_file',
               artifact_generation_instructions = 'Generate SQL.',
               mapping_profile_key = 'template.validation',
               mapping_profile_version = '1.0.0',
               mapping_profile_schema_digest = repeat('d', 64),
               mapping_package_document = '{"mapping":"validation"}'::JSONB,
               mapping_package_digest = repeat('e', 64),
               object_mapping_transformation_document = %s::JSONB
         WHERE mapping_object_id = %s
        RETURNING output_template_id, CURRENT_USER AS current_role
        """,
        (output_template_id, json.dumps(document), mapping_object_id),
    ).fetchone()
    assert selected is not None
    return selected


def _seed_mapping_rows(
    connection: Connection[Any],
    *,
    prefix: str,
) -> dict[str, int | None]:
    system_type_id = _required_id(
        connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES (%s, %s)
            RETURNING system_type_id
            """,
            (f"{prefix}_DATABASE", f"{prefix} Database"),
        ).fetchone(),
        "system_type_id",
    )
    connection_type_id = _required_id(
        connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code,
                connection_type_name
            )
            VALUES (%s, %s)
            RETURNING connection_type_id
            """,
            (f"{prefix}_CONNECTION", f"{prefix} Connection"),
        ).fetchone(),
        "connection_type_id",
    )
    object_type_id = _required_id(
        connection.execute(
            """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES (%s, %s)
            RETURNING object_type_id
            """,
            (f"{prefix}_TABLE", f"{prefix} Table"),
        ).fetchone(),
        "object_type_id",
    )
    zone_id = _required_id(
        connection.execute(
            """
            INSERT INTO reference.zone (zone_code, zone_name)
            VALUES (%s, %s)
            RETURNING zone_id
            """,
            (f"ot_{prefix[-20:].lower()}", f"{prefix} Silver"),
        ).fetchone(),
        "zone_id",
    )
    project_id = _required_id(
        connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
            (f"{prefix}_PROJECT", f"{prefix} Project"),
        ).fetchone(),
        "project_id",
    )
    tenant_id = _required_id(
        connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
            (
                project_id,
                f"{prefix}_TENANT",
                f"{prefix} Tenant",
                prefix.lower(),
                f"{prefix.lower()}_admin",
            ),
        ).fetchone(),
        "tenant_id",
    )
    system_id = _required_id(
        connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES (%s, %s, %s)
            RETURNING system_id
            """,
            (f"{prefix}_SYSTEM", f"{prefix} System", system_type_id),
        ).fetchone(),
        "system_id",
    )
    connection_id = _required_id(
        connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING connection_id
            """,
            (
                tenant_id,
                system_id,
                f"{prefix}_SOURCE",
                f"{prefix} Source",
                connection_type_id,
            ),
        ).fetchone(),
        "connection_id",
    )
    object_id = _required_id(
        connection.execute(
            """
            INSERT INTO core.object (
                connection_id,
                object_schema,
                object_name,
                object_type_id,
                zone_id
            )
            VALUES (%s, 'silver_test', 'customer', %s, %s)
            RETURNING object_id
            """,
            (connection_id, object_type_id, zone_id),
        ).fetchone(),
        "object_id",
    )
    attribute_id = _required_id(
        connection.execute(
            """
            INSERT INTO core.attribute (
                object_id,
                attribute_name,
                attribute_ordinal_position,
                attribute_data_type,
                attribute_nullability
            )
            VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
            RETURNING attribute_id
            """,
            (object_id,),
        ).fetchone(),
        "attribute_id",
    )
    model_id = _required_id(
        connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id
            """,
            (tenant_id, f"{prefix} Model"),
        ).fetchone(),
        "model_id",
    )
    connection.execute(
        """
        INSERT INTO model.model_scope (model_id, object_id)
        VALUES (%s, %s)
        """,
        (model_id, object_id),
    )
    logical_entity_id = _required_id(
        connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                model_id,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            )
            VALUES (%s, 'Customer', 'One governed Customer.', 'core', 'One Customer')
            RETURNING logical_entity_id
            """,
            (model_id,),
        ).fetchone(),
        "logical_entity_id",
    )
    logical_attribute_id = _required_id(
        connection.execute(
            """
            INSERT INTO workflow.logical_attribute (
                model_id,
                logical_entity_id,
                logical_attribute_name,
                logical_attribute_definition,
                logical_attribute_data_type,
                logical_attribute_is_nullable,
                logical_attribute_ordinal_position
            )
            VALUES (%s, %s, 'Customer ID', 'Customer identifier.',
                    'bigint', FALSE, 1)
            RETURNING logical_attribute_id
            """,
            (model_id, logical_entity_id),
        ).fetchone(),
        "logical_attribute_id",
    )
    connection.execute(
        """
        INSERT INTO workflow.mapping_source_system_dependency (
            model_id,
            modeled_entity_type,
            source_system_id
        )
        VALUES (%s, 'logical_entity', %s)
        """,
        (model_id, system_id),
    )
    mapping_object = connection.execute(
        """
        INSERT INTO workflow.mapping_object (
            model_id,
            object_id,
            source_system_id,
            modeled_entity_type,
            logical_entity_id
        )
        VALUES (%s, %s, %s, 'logical_entity', %s)
        RETURNING mapping_object_id, output_template_id
        """,
        (model_id, object_id, system_id, logical_entity_id),
    ).fetchone()
    assert mapping_object is not None
    mapping_attribute = connection.execute(
        """
        INSERT INTO workflow.mapping_attribute (
            model_id,
            object_id,
            attribute_id,
            mapping_object_id,
            modeled_entity_type,
            logical_attribute_id
        )
        VALUES (%s, %s, %s, %s, 'logical_entity', %s)
        RETURNING mapping_attribute_id, output_template_id
        """,
        (
            model_id,
            object_id,
            attribute_id,
            mapping_object["mapping_object_id"],
            logical_attribute_id,
        ),
    ).fetchone()
    assert mapping_attribute is not None

    return {
        "model_id": model_id,
        "mapping_object_id": mapping_object["mapping_object_id"],
        "mapping_attribute_id": mapping_attribute["mapping_attribute_id"],
        "object_output_template_id": mapping_object["output_template_id"],
        "attribute_output_template_id": mapping_attribute["output_template_id"],
    }


def _required_id(row: dict[str, Any] | None, field: str) -> int:
    assert row is not None
    value = row[field]
    assert type(value) is int
    return value
