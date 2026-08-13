from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

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
        base_digest_column = connection.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'mcp'
               AND table_name = 'metadata_change_set'
               AND column_name = 'base_metadata_digest'
            """
        ).fetchone()

    assert tuple(column["column_name"] for column in columns) == DOCUMENT_COLUMNS
    assert all(
        column["data_type"] == "jsonb"
        and column["is_nullable"] == "NO"
        and column["column_default"] == "'[]'::jsonb"
        for column in columns
    )
    assert base_digest_column is None
    assert document_check is not None
    assert event_section_check is not None
    for column_name in DOCUMENT_COLUMNS:
        assert f"jsonb_typeof({column_name})" in document_check["definition"]
        assert f"octet_length(({column_name})::text) <= 16777216" in document_check["definition"]
    for section_name in NEW_SECTION_NAMES:
        assert section_name in event_section_check["definition"]


def test_runtime_can_only_mutate_metadata_change_sets_through_governed_functions(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT has_table_privilege(
                       'gds_app_write', 'mcp.metadata_change_set', 'SELECT'
                   ) AS direct_select,
                   has_table_privilege(
                       'gds_app_write', 'mcp.metadata_change_set', 'INSERT,UPDATE,DELETE'
                   ) AS direct_mutation,
                   has_table_privilege(
                       'gds_app_write', 'mcp.metadata_change_set_event', 'INSERT'
                   ) AS direct_event_insert,
                   has_function_privilege(
                       'gds_app_write',
                       'mcp.create_metadata_change_set(uuid,uuid,varchar,bigint,uuid,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.stage_metadata_change_set(uuid,uuid,varchar,bigint,uuid,bigint,varchar,jsonb,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.get_metadata_change_set(uuid,uuid,varchar,bigint,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.record_metadata_change_set_validation(uuid,uuid,varchar,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.apply_metadata_change_set(uuid,uuid,varchar,bigint,uuid,bigint,character,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.archive_metadata_change_set(uuid,uuid,varchar,bigint,uuid,bigint,uuid)',
                       'EXECUTE'
                   ) AS governed_execute
            """
        ).fetchone()

    assert row == {
        "direct_select": False,
        "direct_mutation": False,
        "direct_event_insert": False,
        "governed_execute": True,
    }


def test_metadata_change_set_enforces_new_document_and_event_contract(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(connection, suffix="DOCUMENTS")
        change_set_id = uuid4()
        correlation_id = uuid4()
        documents = connection.execute(
            """
            INSERT INTO mcp.metadata_change_set (
                metadata_change_set_id,
                tenant_id,
                created_by_principal_id,
                correlation_id
            )
            VALUES (%s, %s, %s, %s)
            RETURNING ingestion_object_mapping_document,
                      ingestion_attribute_mapping_document,
                      member_group_document,
                      copy_group_control_document
            """,
            (change_set_id, tenant_id, principal_id, correlation_id),
        ).fetchone()

        assert documents == {
            "ingestion_object_mapping_document": [],
            "ingestion_attribute_mapping_document": [],
            "member_group_document": [],
            "copy_group_control_document": [],
        }

        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """
                    UPDATE mcp.metadata_change_set
                       SET ingestion_object_mapping_document = '{}'::JSONB
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


def test_metadata_change_set_allows_one_ongoing_draft_per_tenant_and_principal(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(connection, suffix="ONGOING")
        first_change_set_id = uuid4()
        connection.execute(
            """
            INSERT INTO mcp.metadata_change_set (
                metadata_change_set_id,
                tenant_id,
                created_by_principal_id,
                correlation_id
            )
            VALUES (%s, %s, %s, %s)
            """,
            (first_change_set_id, tenant_id, principal_id, uuid4()),
        )

        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO mcp.metadata_change_set (
                    metadata_change_set_id,
                    tenant_id,
                    created_by_principal_id,
                    correlation_id
                )
                VALUES (%s, %s, %s, %s)
                """,
                (uuid4(), tenant_id, principal_id, uuid4()),
            )

        connection.execute(
            """
            UPDATE mcp.metadata_change_set
               SET metadata_change_set_status = 'archived',
                   terminal_time = CURRENT_TIMESTAMP
             WHERE metadata_change_set_id = %s
            """,
            (first_change_set_id,),
        )
        connection.execute(
            """
            INSERT INTO mcp.metadata_change_set (
                metadata_change_set_id,
                tenant_id,
                created_by_principal_id,
                correlation_id
            )
            VALUES (%s, %s, %s, %s)
            """,
            (uuid4(), tenant_id, principal_id, uuid4()),
        )


def test_create_metadata_change_set_requires_owned_lock_and_reuses_ongoing_draft(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000040")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000040")
    with postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(connection, suffix="CREATE")
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
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
            )
            VALUES (%s, %s, 'developer', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )

    first_id = uuid4()
    with postgres_database.connect_runtime() as connection:
        denied = connection.execute(
            """
            SELECT created, denial_code, metadata_change_set_id
              FROM mcp.create_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, first_id, uuid4()),
        ).fetchone()
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  60::INTEGER, 'Metadata change set'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        created = connection.execute(
            """
            SELECT created, denial_code, metadata_change_set_id, draft_revision
              FROM mcp.create_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, first_id, uuid4()),
        ).fetchone()
        reused = connection.execute(
            """
            SELECT created, denial_code, metadata_change_set_id, draft_revision
              FROM mcp.create_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, uuid4(), uuid4()),
        ).fetchone()

    assert denied == {
        "created": False,
        "denial_code": "tenant_lock_required",
        "metadata_change_set_id": None,
    }
    assert acquired == {"acquired": True}
    assert created == {
        "created": True,
        "denial_code": None,
        "metadata_change_set_id": first_id,
        "draft_revision": 1,
    }
    assert reused == {
        "created": False,
        "denial_code": "metadata_change_set_exists",
        "metadata_change_set_id": first_id,
        "draft_revision": 1,
    }


def test_stage_metadata_change_set_replaces_one_document_and_checks_revision(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000041")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000041")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="STAGE",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    records = [
        {
            "tenant_code": "CHANGE_SET_TENANT_STAGE",
            "system_code": "CRM",
            "copy_group_name": "CUSTOMERS",
            "copy_group_description": None,
            "is_member_group_required": False,
            "is_active": True,
        }
    ]

    with postgres_database.connect_runtime() as connection:
        staged = connection.execute(
            """
            SELECT staged, denial_code, draft_revision, record_count
              FROM mcp.stage_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, 'copy_group'::VARCHAR,
                  %s::JSONB, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                Jsonb(records),
                uuid4(),
            ),
        ).fetchone()
        conflict = connection.execute(
            """
            SELECT staged, denial_code, draft_revision, record_count
              FROM mcp.stage_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, 'copy_group'::VARCHAR,
                  '[]'::JSONB, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, change_set_id, uuid4()),
        ).fetchone()
    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT copy_group_document
              FROM mcp.metadata_change_set
             WHERE metadata_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()

    assert staged == {
        "staged": True,
        "denial_code": None,
        "draft_revision": 2,
        "record_count": 1,
    }
    assert conflict == {
        "staged": False,
        "denial_code": "draft_revision_conflict",
        "draft_revision": 2,
        "record_count": 1,
    }
    assert stored == {"copy_group_document": records}


def test_get_metadata_change_set_requires_ownership_but_not_current_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000042")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000042")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="GET",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    with postgres_database.connect_runtime() as connection:
        released = connection.execute(
            """
            SELECT released
              FROM security.release_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        result = connection.execute(
            """
            SELECT found,
                   denial_code,
                   metadata_change_set_status,
                   draft_revision,
                   jsonb_array_length(copy_group_document) AS copy_group_count
              FROM mcp.get_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, change_set_id),
        ).fetchone()

    assert released == {"released": True}
    assert result == {
        "found": True,
        "denial_code": None,
        "metadata_change_set_status": "active",
        "draft_revision": 1,
        "copy_group_count": 0,
    }


def test_record_metadata_change_set_validation_seals_or_reopens_draft(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000043")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000043")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="VALIDATE",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    digest = "a" * 64

    with postgres_database.connect_runtime() as connection:
        valid = connection.execute(
            """
            SELECT recorded, denial_code, metadata_change_set_status,
                   draft_revision, candidate_digest
              FROM mcp.record_metadata_change_set_validation(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, TRUE, %s::CHAR(64),
                  '{"valid": true}'::JSONB, %s::UUID, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                digest,
                uuid4(),
                uuid4(),
            ),
        ).fetchone()
        invalid = connection.execute(
            """
            SELECT recorded, denial_code, metadata_change_set_status,
                   draft_revision, candidate_digest
              FROM mcp.record_metadata_change_set_validation(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, FALSE, NULL::CHAR(64),
                  '{"valid": false}'::JSONB, %s::UUID, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                uuid4(),
                uuid4(),
            ),
        ).fetchone()

    assert valid == {
        "recorded": True,
        "denial_code": None,
        "metadata_change_set_status": "validated",
        "draft_revision": 1,
        "candidate_digest": digest,
    }
    assert invalid == {
        "recorded": True,
        "denial_code": None,
        "metadata_change_set_status": "active",
        "draft_revision": 1,
        "candidate_digest": None,
    }


def test_apply_metadata_change_set_checks_seal_and_upserts_natural_key_record(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000044")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000044")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="APPLY",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    digest = "b" * 64
    record = {
        "tenant_code": "CHANGE_SET_TENANT_APPLY",
        "system_code": "CRM_APPLY",
        "copy_group_name": "CUSTOMERS",
        "copy_group_description": "Customer ingestion",
        "is_member_group_required": False,
        "is_active": True,
    }
    with postgres_database.connect_owner() as connection:
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (
                system_type_code, system_type_name
            ) VALUES ('DATABASE_APPLY', 'Database Apply')
            RETURNING system_type_id
            """
        ).fetchone()
        assert system_type is not None
        connection.execute(
            """
            INSERT INTO core.system (
                system_code, system_name, system_type_id
            ) VALUES ('CRM_APPLY', 'CRM Apply', %s)
            """,
            (system_type["system_type_id"],),
        )
        connection.execute(
            """
            UPDATE mcp.metadata_change_set
               SET copy_group_document = %s::JSONB,
                   metadata_change_set_status = 'validated',
                   candidate_digest = %s,
                   validation_outcome = '{"valid": true}'::JSONB,
                   validated_time = CURRENT_TIMESTAMP
             WHERE metadata_change_set_id = %s
            """,
            (Jsonb([record]), digest, change_set_id),
        )

    with postgres_database.connect_runtime() as connection:
        conflict = connection.execute(
            """
            SELECT applied, denial_code, metadata_change_set_status, action_count
              FROM mcp.apply_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                "c" * 64,
                uuid4(),
            ),
        ).fetchone()
        applied = connection.execute(
            """
            SELECT applied, denial_code, metadata_change_set_status, action_count
              FROM mcp.apply_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                digest,
                uuid4(),
            ),
        ).fetchone()
        stored = connection.execute(
            """
            SELECT copy_group.copy_group_name,
                   copy_group.copy_group_description,
                   copy_group.is_active
              FROM core.copy_group AS copy_group
             WHERE copy_group.tenant_id = %s
            """,
            (tenant_id,),
        ).fetchone()

    assert conflict == {
        "applied": False,
        "denial_code": "candidate_digest_conflict",
        "metadata_change_set_status": "validated",
        "action_count": 0,
    }
    assert applied == {
        "applied": True,
        "denial_code": None,
        "metadata_change_set_status": "applied",
        "action_count": 1,
    }
    assert stored == {
        "copy_group_name": "CUSTOMERS",
        "copy_group_description": "Customer ingestion",
        "is_active": True,
    }


@pytest.mark.parametrize(
    ("suffix", "entra_tenant_id", "entra_object_id", "stage_attribute"),
    (
        (
            "LOCKED_OBJECT_APPLY",
            UUID("10000000-0000-0000-0000-000000000048"),
            UUID("20000000-0000-0000-0000-000000000048"),
            False,
        ),
        (
            "LOCKED_ATTRIBUTE_APPLY",
            UUID("10000000-0000-0000-0000-000000000049"),
            UUID("20000000-0000-0000-0000-000000000049"),
            True,
        ),
    ),
)
def test_apply_rechecks_object_lock_before_object_or_attribute_write(
    postgres_database: DisposablePostgres,
    suffix: str,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
    *,
    stage_attribute: bool,
) -> None:
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=suffix,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    digest = "f" * 64
    tenant_code = f"CHANGE_SET_TENANT_{suffix}"
    system_code = f"CRM_{suffix}"
    zone_code = f"bronze_{suffix.lower()}"
    object_record = {
        "tenant_code": tenant_code,
        "system_code": system_code,
        "connection_code": "MAIN",
        "object_schema": "public",
        "object_name": "customers",
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": "Changed",
        "batch_attribute_name": None,
        "object_type_code": f"TABLE_{suffix}",
        "zone_code": zone_code,
        "is_locked": False,
        "is_active": True,
    }
    attribute_record = {
        "tenant_code": tenant_code,
        "system_code": system_code,
        "connection_code": "MAIN",
        "object_schema": "public",
        "object_name": "customers",
        "attribute_name": "customer_id",
        "fc_attribute_name": None,
        "attribute_ordinal_position": 1,
        "attribute_description": "Changed",
        "attribute_data_type": "bigint",
        "attribute_nullability": False,
        "attribute_custom_code": None,
        "is_surrogate_key": False,
        "is_natural_key": True,
        "is_meta_data": False,
        "is_masking_required": False,
        "is_mapped": True,
        "is_purge": False,
        "is_active": True,
    }

    with postgres_database.connect_owner() as connection:
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES (%s, %s)
            RETURNING system_type_id
            """,
            (f"DATABASE_{suffix}", f"Database {suffix}"),
        ).fetchone()
        assert system_type is not None
        system_type_id = system_type["system_type_id"]
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code, connection_type_name
            ) VALUES (%s, %s)
            RETURNING connection_type_id
            """,
            (f"POSTGRES_{suffix}", f"Postgres {suffix}"),
        ).fetchone()
        assert connection_type is not None
        connection_type_id = connection_type["connection_type_id"]
        object_type = connection.execute(
            """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES (%s, %s)
            RETURNING object_type_id
            """,
            (f"TABLE_{suffix}", f"Table {suffix}"),
        ).fetchone()
        assert object_type is not None
        object_type_id = object_type["object_type_id"]
        zone = connection.execute(
            """
            INSERT INTO reference.zone (zone_code, zone_name)
            VALUES (%s, %s)
            RETURNING zone_id
            """,
            (zone_code, f"Bronze {suffix}"),
        ).fetchone()
        assert zone is not None
        zone_id = zone["zone_id"]
        system = connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES (%s, %s, %s)
            RETURNING system_id
            """,
            (system_code, f"CRM {suffix}", system_type_id),
        ).fetchone()
        assert system is not None
        system_id = system["system_id"]
        connection_row = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id
            ) VALUES (%s, %s, 'MAIN', 'Main', %s)
            RETURNING connection_id
            """,
            (tenant_id, system_id, connection_type_id),
        ).fetchone()
        assert connection_row is not None
        connection_id = connection_row["connection_id"]
        object_row = connection.execute(
            """
            INSERT INTO core.object (
                connection_id, object_schema, object_name, object_description,
                object_type_id, zone_id, is_locked
            ) VALUES (%s, 'public', 'customers', 'Original', %s, %s, TRUE)
            RETURNING object_id
            """,
            (connection_id, object_type_id, zone_id),
        ).fetchone()
        assert object_row is not None
        object_id = object_row["object_id"]
        connection.execute(
            """
            INSERT INTO core.attribute (
                object_id, attribute_name, attribute_ordinal_position,
                attribute_description, attribute_data_type
            ) VALUES (%s, 'customer_id', 1, 'Original', 'bigint')
            """,
            (object_id,),
        )
        if stage_attribute:
            connection.execute(
                """
                UPDATE mcp.metadata_change_set
                   SET bronze_attribute_document = %s::JSONB,
                       metadata_change_set_status = 'validated',
                       candidate_digest = %s,
                       validation_outcome = '{"valid": true}'::JSONB,
                       validated_time = CURRENT_TIMESTAMP
                 WHERE metadata_change_set_id = %s
                """,
                (Jsonb([attribute_record]), digest, change_set_id),
            )
        else:
            connection.execute(
                """
                UPDATE mcp.metadata_change_set
                   SET bronze_object_document = %s::JSONB,
                       metadata_change_set_status = 'validated',
                       candidate_digest = %s,
                       validation_outcome = '{"valid": true}'::JSONB,
                       validated_time = CURRENT_TIMESTAMP
                 WHERE metadata_change_set_id = %s
                """,
                (Jsonb([object_record]), digest, change_set_id),
            )

    with postgres_database.connect_runtime() as connection:
        applied = connection.execute(
            """
            SELECT applied, denial_code, metadata_change_set_status, action_count
              FROM mcp.apply_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                digest,
                uuid4(),
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT object.object_description,
                   attribute.attribute_description
              FROM core.object AS object
              JOIN core.attribute AS attribute
                ON attribute.object_id = object.object_id
             WHERE object.object_id = %s
            """,
            (object_id,),
        ).fetchone()

    assert applied == {
        "applied": False,
        "denial_code": "object_locked",
        "metadata_change_set_status": "validated",
        "action_count": 0,
    }
    assert stored == {
        "object_description": "Original",
        "attribute_description": "Original",
    }


def test_late_copy_failure_rolls_back_earlier_object_insert(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000050")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000050")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="ATOMIC_ROLLBACK",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    digest = "a" * 64
    tenant_code = "CHANGE_SET_TENANT_ATOMIC_ROLLBACK"
    object_record = {
        "tenant_code": tenant_code,
        "system_code": "CRM_ATOMIC_ROLLBACK",
        "connection_code": "MAIN",
        "object_schema": "public",
        "object_name": "rollback_probe",
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": "Must roll back",
        "batch_attribute_name": None,
        "object_type_code": "TABLE_ATOMIC_ROLLBACK",
        "zone_code": "bronze_atomic_rollback",
        "is_locked": False,
        "is_active": True,
    }
    invalid_copy_record = {
        "tenant_code": tenant_code,
        "system_code": "CRM_ATOMIC_ROLLBACK",
        "copy_group_name": "MISSING",
        "source_tenant_code": tenant_code,
        "source_system_code": "CRM_ATOMIC_ROLLBACK",
        "source_connection_code": "MAIN",
        "source_object_schema": "public",
        "source_object_name": "rollback_probe",
        "target_tenant_code": tenant_code,
        "target_system_code": "CRM_ATOMIC_ROLLBACK",
        "target_connection_code": "MAIN",
        "target_object_schema": "public",
        "target_object_name": "rollback_probe",
        "copy_source_record_limit": None,
        "copy_source_record_limit_attribute": None,
        "chunk_type_name": None,
        "copy_source_initial_sql_script": None,
        "copy_source_incremental_sql_script": None,
        "copy_source_file_name": None,
        "copy_source_file_pattern": None,
        "copy_source_file_delimiter": None,
        "source_file_type_name": None,
        "copy_source_order": 1,
        "source_data_operation_name": "MISSING",
        "target_data_operation_name": "MISSING",
        "is_active": True,
    }

    with postgres_database.connect_owner() as connection:
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES ('DATABASE_ATOMIC_ROLLBACK', 'Database Atomic Rollback')
            RETURNING system_type_id
            """
        ).fetchone()
        assert system_type is not None
        system_type_id = system_type["system_type_id"]
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code, connection_type_name
            ) VALUES ('POSTGRES_ATOMIC_ROLLBACK', 'Postgres Atomic Rollback')
            RETURNING connection_type_id
            """
        ).fetchone()
        assert connection_type is not None
        connection_type_id = connection_type["connection_type_id"]
        object_type = connection.execute(
            """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES ('TABLE_ATOMIC_ROLLBACK', 'Table Atomic Rollback')
            RETURNING object_type_id
            """
        ).fetchone()
        assert object_type is not None
        object_type_id = object_type["object_type_id"]
        zone = connection.execute(
            """
            INSERT INTO reference.zone (zone_code, zone_name)
            VALUES ('bronze_atomic_rollback', 'Bronze Atomic Rollback')
            RETURNING zone_id
            """
        ).fetchone()
        assert zone is not None
        zone_id = zone["zone_id"]
        system = connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES ('CRM_ATOMIC_ROLLBACK', 'CRM Atomic Rollback', %s)
            RETURNING system_id
            """,
            (system_type_id,),
        ).fetchone()
        assert system is not None
        system_id = system["system_id"]
        connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id
            ) VALUES (%s, %s, 'MAIN', 'Main', %s)
            """,
            (tenant_id, system_id, connection_type_id),
        )
        assert object_type_id > 0 and zone_id > 0
        connection.execute(
            """
            UPDATE mcp.metadata_change_set
               SET bronze_object_document = %s::JSONB,
                   copy_document = %s::JSONB,
                   metadata_change_set_status = 'validated',
                   candidate_digest = %s,
                   validation_outcome = '{"valid": true}'::JSONB,
                   validated_time = CURRENT_TIMESTAMP
             WHERE metadata_change_set_id = %s
            """,
            (
                Jsonb([object_record]),
                Jsonb([invalid_copy_record]),
                digest,
                change_set_id,
            ),
        )

    with pytest.raises(psycopg.errors.SerializationFailure, match="Copy dependency changed"):
        with postgres_database.connect_runtime() as connection:
            connection.execute(
                """
                SELECT applied
                  FROM mcp.apply_metadata_change_set(
                      %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                      %s::UUID, 1::BIGINT, %s::CHAR(64), %s::UUID
                  )
                """,
                (
                    entra_tenant_id,
                    entra_object_id,
                    tenant_id,
                    change_set_id,
                    digest,
                    uuid4(),
                ),
            ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT count(*) AS object_count
              FROM core.object AS object
              JOIN core.connection AS connection
                ON connection.connection_id = object.connection_id
             WHERE connection.tenant_id = %s
               AND object.object_name = 'rollback_probe'
            """,
            (tenant_id,),
        ).fetchone()
        status = connection.execute(
            """
            SELECT metadata_change_set_status
              FROM mcp.metadata_change_set
             WHERE metadata_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()

    assert stored == {"object_count": 0}
    assert status == {"metadata_change_set_status": "validated"}


def test_archive_metadata_change_set_requires_ownership_but_not_current_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000045")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000045")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="ARCHIVE",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    with postgres_database.connect_runtime() as connection:
        connection.execute(
            """
            SELECT released
              FROM security.release_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        )
        archived = connection.execute(
            """
            SELECT archived, denial_code, metadata_change_set_status, draft_revision
              FROM mcp.archive_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                uuid4(),
            ),
        ).fetchone()

    assert archived == {
        "archived": True,
        "denial_code": None,
        "metadata_change_set_status": "archived",
        "draft_revision": 1,
    }


def test_apply_metadata_change_set_writes_all_sixteen_datasets(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000046")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000046")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="ALL_APPLY",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    tenant_code = "CHANGE_SET_TENANT_ALL_APPLY"
    documents = _all_apply_documents(tenant_code)
    digest = "d" * 64

    with postgres_database.connect_owner() as connection:
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES ('DATABASE_ALL_APPLY', 'Database All Apply')
            RETURNING system_type_id
            """
        ).fetchone()
        assert system_type is not None
        system_type_id = system_type["system_type_id"]
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code, connection_type_name
            ) VALUES ('POSTGRES_ALL_APPLY', 'Postgres All Apply')
            RETURNING connection_type_id
            """
        ).fetchone()
        assert connection_type is not None
        connection_type_id = connection_type["connection_type_id"]
        connection.execute(
            """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES ('TABLE_ALL_APPLY', 'Table All Apply')
            RETURNING object_type_id
            """
        )
        for zone_code, zone_name in (
            ("source_all_apply", "Source All Apply"),
            ("bronze_all_apply", "Bronze All Apply"),
            ("silver_all_apply", "Silver All Apply"),
            ("gold_all_apply", "Gold All Apply"),
        ):
            connection.execute(
                "INSERT INTO reference.zone (zone_code, zone_name) VALUES (%s, %s)",
                (zone_code, zone_name),
            )
        connection.execute(
            """
            INSERT INTO reference.data_operation (
                data_operation_name, data_operation_description
            ) VALUES ('UPSERT_ALL_APPLY', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO reference.process_type (
                process_type_name, process_type_description
            ) VALUES ('NOTEBOOK_ALL_APPLY', NULL)
            """
        )
        system = connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES ('CRM_ALL_APPLY', 'CRM All Apply', %s)
            RETURNING system_id
            """,
            (system_type_id,),
        ).fetchone()
        assert system is not None
        system_id = system["system_id"]
        connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id
            ) VALUES (%s, %s, 'MAIN', 'Main', %s)
            """,
            (tenant_id, system_id, connection_type_id),
        )
        connection.execute(
            """
            UPDATE mcp.metadata_change_set
               SET source_object_document = %s::JSONB,
                   source_attribute_document = %s::JSONB,
                   bronze_object_document = %s::JSONB,
                   bronze_attribute_document = %s::JSONB,
                   silver_object_document = %s::JSONB,
                   silver_attribute_document = %s::JSONB,
                   gold_object_document = %s::JSONB,
                   gold_attribute_document = %s::JSONB,
                   ingestion_object_mapping_document = %s::JSONB,
                   ingestion_attribute_mapping_document = %s::JSONB,
                   copy_group_document = %s::JSONB,
                   member_group_document = %s::JSONB,
                   copy_group_control_document = %s::JSONB,
                   copy_document = %s::JSONB,
                   process_group_document = %s::JSONB,
                   process_document = %s::JSONB,
                   metadata_change_set_status = 'validated',
                   candidate_digest = %s,
                   validation_outcome = '{"valid": true}'::JSONB,
                   validated_time = CURRENT_TIMESTAMP
             WHERE metadata_change_set_id = %s
            """,
            (
                *(Jsonb(documents[name]) for name in (
                    "source_object",
                    "source_attribute",
                    "bronze_object",
                    "bronze_attribute",
                    "silver_object",
                    "silver_attribute",
                    "gold_object",
                    "gold_attribute",
                    "ingestion_object_mapping",
                    "ingestion_attribute_mapping",
                    "copy_group",
                    "member_group",
                    "copy_group_control",
                    "copy",
                    "process_group",
                    "process",
                )),
                digest,
                change_set_id,
            ),
        )

    with postgres_database.connect_runtime() as connection:
        applied = connection.execute(
            """
            SELECT applied, denial_code, action_count
              FROM mcp.apply_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                digest,
                uuid4(),
            ),
        ).fetchone()
        counts = connection.execute(
            """
            SELECT (
                       SELECT count(*) FROM core.object AS object
                       JOIN core.connection AS connection
                         ON connection.connection_id = object.connection_id
                      WHERE connection.tenant_id = %s
                   ) AS objects,
                   (
                       SELECT count(*) FROM core.attribute AS attribute
                       JOIN core.object AS object
                         ON object.object_id = attribute.object_id
                       JOIN core.connection AS connection
                         ON connection.connection_id = object.connection_id
                      WHERE connection.tenant_id = %s
                   ) AS attributes,
                   (SELECT count(*) FROM core.ingestion_object_mapping) AS object_mappings,
                   (SELECT count(*) FROM core.ingestion_attribute_mapping) AS attribute_mappings,
                   (SELECT count(*) FROM core.copy_group WHERE tenant_id = %s) AS copy_groups,
                   (SELECT count(*) FROM core.member_group WHERE tenant_id = %s) AS member_groups,
                   (SELECT count(*) FROM core.copy_group_control WHERE tenant_id = %s) AS controls,
                   (
                       SELECT count(*) FROM core.copy AS copy
                       JOIN core.copy_group AS copy_group
                         ON copy_group.copy_group_id = copy.copy_group_id
                      WHERE copy_group.tenant_id = %s
                   ) AS copies,
                   (SELECT count(*) FROM core.process_group WHERE tenant_id = %s) AS process_groups,
                   (
                       SELECT count(*) FROM core.process AS process
                       JOIN core.process_group AS process_group
                         ON process_group.process_group_id = process.process_group_id
                      WHERE process_group.tenant_id = %s
                   ) AS processes
            """,
            (
                tenant_id,
                tenant_id,
                tenant_id,
                tenant_id,
                tenant_id,
                tenant_id,
                tenant_id,
                tenant_id,
            ),
        ).fetchone()
        connection.rollback()

    assert applied == {"applied": True, "denial_code": None, "action_count": 16}
    assert counts == {
        "objects": 4,
        "attributes": 4,
        "object_mappings": 1,
        "attribute_mappings": 1,
        "copy_groups": 1,
        "member_groups": 1,
        "controls": 1,
        "copies": 1,
        "process_groups": 1,
        "processes": 1,
    }


def test_apply_allows_global_object_inside_tenant_discovery_scope(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000047")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000047")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="SCOPED_APPLY",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    digest = "e" * 64
    record = {
        "tenant_code": "GLOBAL_SCOPED_APPLY",
        "system_code": "CRM_SCOPED_APPLY",
        "connection_code": "GDS",
        "object_schema": "demo",
        "object_name": "customers",
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": None,
        "batch_attribute_name": None,
        "object_type_code": "TABLE_SCOPED_APPLY",
        "zone_code": "bronze_scoped_apply",
        "is_locked": False,
        "is_active": True,
    }

    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            "SELECT project_id FROM core.tenant WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        assert project is not None
        project_id = project["project_id"]
        global_tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id, tenant_code, tenant_name, tenant_catalog,
                gds_admin_catalog, tenant_visibility
            ) VALUES (
                %s, 'GLOBAL_SCOPED_APPLY', 'Global Scoped Apply',
                'global_scoped_apply', 'global_scoped_apply_admin', 'global'
            )
            RETURNING tenant_id
            """,
            (project_id,),
        ).fetchone()
        assert global_tenant is not None
        global_tenant_id = global_tenant["tenant_id"]
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES ('DATABASE_SCOPED_APPLY', 'Database Scoped Apply')
            RETURNING system_type_id
            """
        ).fetchone()
        assert system_type is not None
        system_type_id = system_type["system_type_id"]
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code, connection_type_name
            ) VALUES ('POSTGRES_SCOPED_APPLY', 'Postgres Scoped Apply')
            RETURNING connection_type_id
            """
        ).fetchone()
        assert connection_type is not None
        connection_type_id = connection_type["connection_type_id"]
        object_type = connection.execute(
            """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES ('TABLE_SCOPED_APPLY', 'Table Scoped Apply')
            RETURNING object_type_id
            """
        ).fetchone()
        assert object_type is not None
        object_type_id = object_type["object_type_id"]
        zone = connection.execute(
            """
            SELECT zone_id
              FROM reference.zone
             WHERE lower(btrim(zone_code)) = 'bronze_scoped_apply'
            """
        ).fetchone()
        if zone is None:
            zone = connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES ('bronze_scoped_apply', 'Bronze Scoped Apply')
                RETURNING zone_id
                """
            ).fetchone()
        assert zone is not None
        zone_id = zone["zone_id"]
        system = connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES ('CRM_SCOPED_APPLY', 'CRM Scoped Apply', %s)
            RETURNING system_id
            """,
            (system_type_id,),
        ).fetchone()
        assert system is not None
        system_id = system["system_id"]
        connection_row = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id, is_global_data_store
            ) VALUES (%s, %s, 'GDS', 'GDS', %s, TRUE)
            RETURNING connection_id
            """,
            (global_tenant_id, system_id, connection_type_id),
        ).fetchone()
        assert connection_row is not None
        connection_id = connection_row["connection_id"]
        connection.execute(
            """
            INSERT INTO core.tenant_metadata_discovery_scope (
                tenant_id, gds_connection_id, zone_id, object_schema
            ) VALUES (%s, %s, %s, 'demo')
            """,
            (tenant_id, connection_id, zone_id),
        )
        connection.execute(
            """
            UPDATE mcp.metadata_change_set
               SET bronze_object_document = %s::JSONB,
                   metadata_change_set_status = 'validated',
                   candidate_digest = %s,
                   validation_outcome = '{"valid": true}'::JSONB,
                   validated_time = CURRENT_TIMESTAMP
             WHERE metadata_change_set_id = %s
            """,
            (Jsonb([record]), digest, change_set_id),
        )

    with postgres_database.connect_runtime() as connection:
        applied = connection.execute(
            """
            SELECT applied, denial_code, action_count
              FROM mcp.apply_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                digest,
                uuid4(),
            ),
        ).fetchone()
        stored = connection.execute(
            """
            SELECT object.object_name
              FROM core.object AS object
             WHERE object.connection_id = %s
            """,
            (connection_id,),
        ).fetchone()
        connection.rollback()

    assert object_type_id > 0
    assert applied == {"applied": True, "denial_code": None, "action_count": 1}
    assert stored == {"object_name": "customers"}


def _all_apply_documents(
    tenant_code: str,
) -> dict[str, list[dict[str, object]]]:
    system_code = "CRM_ALL_APPLY"
    object_records: dict[str, dict[str, object]] = {}
    attribute_records: dict[str, dict[str, object]] = {}
    for zone_code in ("source", "bronze", "silver", "gold"):
        object_name = f"{zone_code}_customers"
        object_records[zone_code] = {
            "tenant_code": tenant_code,
            "system_code": system_code,
            "connection_code": "MAIN",
            "object_schema": "public",
            "object_name": object_name,
            "fc_object_schema": None,
            "fc_object_name": None,
            "object_transformation": None,
            "object_description": f"{zone_code} customers",
            "batch_attribute_name": None,
            "object_type_code": "TABLE_ALL_APPLY",
            "zone_code": f"{zone_code}_all_apply",
            "is_locked": False,
            "is_active": True,
        }
        attribute_records[zone_code] = {
            "tenant_code": tenant_code,
            "system_code": system_code,
            "connection_code": "MAIN",
            "object_schema": "public",
            "object_name": object_name,
            "attribute_name": "customer_id",
            "fc_attribute_name": None,
            "attribute_ordinal_position": 1,
            "attribute_description": None,
            "attribute_data_type": "bigint",
            "attribute_nullability": False,
            "attribute_custom_code": None,
            "is_surrogate_key": False,
            "is_natural_key": True,
            "is_meta_data": False,
            "is_masking_required": False,
            "is_mapped": True,
            "is_purge": False,
            "is_active": True,
        }

    object_mapping = {
        "source_tenant_code": tenant_code,
        "source_system_code": system_code,
        "source_connection_code": "MAIN",
        "source_object_schema": "public",
        "source_object_name": "source_customers",
        "target_tenant_code": tenant_code,
        "target_system_code": system_code,
        "target_connection_code": "MAIN",
        "target_object_schema": "public",
        "target_object_name": "bronze_customers",
        "is_active": True,
    }
    return {
        "source_object": [object_records["source"]],
        "source_attribute": [attribute_records["source"]],
        "bronze_object": [object_records["bronze"]],
        "bronze_attribute": [attribute_records["bronze"]],
        "silver_object": [object_records["silver"]],
        "silver_attribute": [attribute_records["silver"]],
        "gold_object": [object_records["gold"]],
        "gold_attribute": [attribute_records["gold"]],
        "ingestion_object_mapping": [object_mapping],
        "ingestion_attribute_mapping": [
            {
                **{
                    key: value
                    for key, value in object_mapping.items()
                    if key != "is_active"
                },
                "source_attribute_name": "customer_id",
                "target_attribute_name": "customer_id",
                "is_active": True,
            }
        ],
        "copy_group": [
            {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "copy_group_name": "CUSTOMERS",
                "copy_group_description": "Customers",
                "is_member_group_required": True,
                "is_active": True,
            }
        ],
        "member_group": [
            {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "member_group_name": "DAILY",
                "member_group_description": "Daily",
                "member_group_initial_load_date": "2026-01-01",
                "is_active": True,
            }
        ],
        "copy_group_control": [
            {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "copy_group_name": "CUSTOMERS",
                "member_group_name": "DAILY",
                "copy_group_control_initial_load_date": "2026-01-01",
                "copy_group_control_last_run_time": "2026-01-02T00:00:00+00:00",
                "copy_group_control_last_run_value": "100",
            }
        ],
        "copy": [
            {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "copy_group_name": "CUSTOMERS",
                **{
                    key: value
                    for key, value in object_mapping.items()
                    if key != "is_active"
                },
                "copy_source_record_limit": "100",
                "copy_source_record_limit_attribute": None,
                "chunk_type_name": None,
                "copy_source_initial_sql_script": None,
                "copy_source_incremental_sql_script": None,
                "copy_source_file_name": None,
                "copy_source_file_pattern": None,
                "copy_source_file_delimiter": None,
                "source_file_type_name": None,
                "copy_source_order": 1,
                "source_data_operation_name": "UPSERT_ALL_APPLY",
                "target_data_operation_name": "UPSERT_ALL_APPLY",
                "is_active": True,
            }
        ],
        "process_group": [
            {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "zone_code": "bronze_all_apply",
                "process_group_name": "CUSTOMER_PROCESS",
                "process_group_description": "Customer process",
                "copy_group_name": "CUSTOMERS",
                "is_active": True,
            }
        ],
        "process": [
            {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "zone_code": "bronze_all_apply",
                "process_group_name": "CUSTOMER_PROCESS",
                "process_execution_order": 1,
                "process_location": "/Workspace/customer",
                "process_executable": "load_customer",
                "object_tenant_code": tenant_code,
                "object_system_code": system_code,
                "object_connection_code": "MAIN",
                "object_schema": "public",
                "object_name": "bronze_customers",
                "process_type_name": "NOTEBOOK_ALL_APPLY",
                "is_active": True,
            }
        ],
    }


def _seed_change_set_parents(
    connection: Connection[Any],
    *,
    suffix: str,
) -> tuple[int, int]:
    project = connection.execute(
        """
        INSERT INTO core.project (project_code, project_name)
        VALUES (%s, %s)
        RETURNING project_id
        """,
        (f"CHANGE_SET_PROJECT_{suffix}", f"Change Set Project {suffix}"),
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
        VALUES (%s, %s, %s, %s, %s)
        RETURNING tenant_id
        """,
        (
            project["project_id"],
            f"CHANGE_SET_TENANT_{suffix}",
            f"Change Set Tenant {suffix}",
            f"change_set_catalog_{suffix.lower()}",
            f"change_set_admin_{suffix.lower()}",
        ),
    ).fetchone()
    assert tenant is not None
    principal = connection.execute(
        """
        INSERT INTO security.principal (
            principal_type,
            principal_display_name,
            principal_email
        )
        VALUES ('user', %s, %s)
        RETURNING principal_id
        """,
        (f"Change Set User {suffix}", f"change-set-{suffix.lower()}@example.test"),
    ).fetchone()
    assert principal is not None
    return tenant["tenant_id"], principal["principal_id"]


def _seed_locked_change_set(
    postgres_database: DisposablePostgres,
    *,
    suffix: str,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
) -> tuple[UUID, int]:
    with postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(connection, suffix=suffix)
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id, principal_type, entra_tenant_id, entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            )
            VALUES (%s, %s, 'developer', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )

    change_set_id = uuid4()
    with postgres_database.connect_runtime() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  60::INTEGER, 'Metadata change set'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        created = connection.execute(
            """
            SELECT created
              FROM mcp.create_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                uuid4(),
            ),
        ).fetchone()
    assert acquired == {"acquired": True}
    assert created == {"created": True}
    return change_set_id, tenant_id
