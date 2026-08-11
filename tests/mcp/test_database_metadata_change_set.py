from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import psycopg
import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


DOCUMENT_COLUMNS = (
    "source_object_document",
    "source_attribute_document",
    "bronze_object_document",
    "bronze_attribute_document",
    "silver_object_document",
    "silver_attribute_document",
    "gold_object_document",
    "gold_attribute_document",
    "ingestion_object_mapping_document",
    "ingestion_attribute_mapping_document",
    "copy_group_document",
    "member_group_document",
    "copy_group_control_document",
    "copy_document",
    "process_group_document",
    "process_document",
)

NEW_SECTION_NAMES = (
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "member_group",
    "copy_group_control",
)


def test_metadata_change_set_has_exact_sixteen_documents(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
              FROM information_schema.columns
             WHERE table_schema = 'mcp'
               AND table_name = 'metadata_change_set'
               AND column_name LIKE '%_document'
             ORDER BY ordinal_position
            """
        ).fetchall()
        document_check = connection.execute(
            """
            SELECT pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conrelid = 'mcp.metadata_change_set'::REGCLASS
               AND conname = 'ck_metadata_change_set_documents'
            """
        ).fetchone()
        event_section_check = connection.execute(
            """
            SELECT pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conrelid = 'mcp.metadata_change_set_event'::REGCLASS
               AND conname = 'ck_metadata_change_set_event_section'
            """
        ).fetchone()

    assert tuple(column["column_name"] for column in columns) == DOCUMENT_COLUMNS
    assert all(
        column["data_type"] == "jsonb"
        and column["is_nullable"] == "NO"
        and column["column_default"] == "'{}'::jsonb"
        for column in columns
    )
    assert document_check is not None
    assert event_section_check is not None
    for column_name in DOCUMENT_COLUMNS:
        assert f"jsonb_typeof({column_name})" in document_check["definition"]
        assert f"octet_length(({column_name})::text) <= 16777216" in document_check["definition"]
    for section_name in NEW_SECTION_NAMES:
        assert section_name in event_section_check["definition"]


def test_metadata_change_set_enforces_new_document_and_event_contract(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(connection)
        change_set_id = uuid4()
        correlation_id = uuid4()
        documents = connection.execute(
            """
            INSERT INTO mcp.metadata_change_set (
                metadata_change_set_id,
                tenant_id,
                base_metadata_digest,
                created_by_principal_id,
                correlation_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING ingestion_object_mapping_document,
                      ingestion_attribute_mapping_document,
                      member_group_document,
                      copy_group_control_document
            """,
            (change_set_id, tenant_id, "a" * 64, principal_id, correlation_id),
        ).fetchone()

        assert documents == {
            "ingestion_object_mapping_document": {},
            "ingestion_attribute_mapping_document": {},
            "member_group_document": {},
            "copy_group_control_document": {},
        }

        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """
                    UPDATE mcp.metadata_change_set
                       SET ingestion_object_mapping_document = '[]'::JSONB
                     WHERE metadata_change_set_id = %s
                    """,
                (change_set_id,),
            )

        for event_sequence, section_name in enumerate(NEW_SECTION_NAMES, start=1):
            connection.execute(
                """
                INSERT INTO mcp.metadata_change_set_event (
                    metadata_change_set_id,
                    tenant_id,
                    event_sequence,
                    event_type,
                    draft_revision,
                    section_name,
                    outcome,
                    correlation_id
                )
                VALUES (%s, %s, %s, 'section_put', 1, %s, 'accepted', %s)
                """,
                (
                    change_set_id,
                    tenant_id,
                    event_sequence,
                    section_name,
                    correlation_id,
                ),
            )


def _seed_change_set_parents(connection: Connection[Any]) -> tuple[int, int]:
    project = connection.execute(
        """
        INSERT INTO core.project (project_code, project_name)
        VALUES ('CHANGE_SET_PROJECT', 'Change Set Project')
        RETURNING project_id
        """
    ).fetchone()
    assert project is not None
    tenant = connection.execute(
        """
        INSERT INTO core.tenant (
            project_id,
            tenant_code,
            tenant_name,
            tenant_catalog,
            gds_admin_catalog
        )
        VALUES (%s, 'CHANGE_SET_TENANT', 'Change Set Tenant',
                'change_set_catalog', 'change_set_admin')
        RETURNING tenant_id
        """,
        (project["project_id"],),
    ).fetchone()
    assert tenant is not None
    principal = connection.execute(
        """
        INSERT INTO security.principal (
            principal_type,
            principal_display_name,
            principal_email
        )
        VALUES ('user', 'Change Set User', 'change-set@example.test')
        RETURNING principal_id
        """
    ).fetchone()
    assert principal is not None
    return tenant["tenant_id"], principal["principal_id"]
