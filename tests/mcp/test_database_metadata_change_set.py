from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
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

REQUIRED_METADATA_ARGUMENTS = {
    "create_metadata_change_set": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "new_metadata_change_set_id",
        "correlation_id",
    ),
    "stage_metadata_change_set": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "expected_draft_revision",
        "documents",
        "correlation_id",
    ),
    "begin_metadata_stage_batch": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "expected_draft_revision",
        "new_stage_batch_id",
        "dataset_name",
        "total_record_count",
        "total_chunk_count",
        "batch_sha256",
        "correlation_id",
    ),
    "put_metadata_stage_chunk": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "stage_batch_id",
        "dataset_name",
        "chunk_index",
        "chunk_sha256",
        "records",
    ),
    "commit_metadata_stage_batch": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "stage_batch_id",
        "expected_draft_revision",
        "correlation_id",
    ),
    "get_metadata_change_set": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
    ),
    "record_metadata_change_set_validation": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "expected_draft_revision",
        "validation_succeeded",
        "candidate_digest",
        "validation_outcome",
        "correlation_id",
    ),
    "archive_metadata_change_set": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "expected_draft_revision",
        "correlation_id",
    ),
    "apply_metadata_change_set": (
        "entra_tenant_id",
        "entra_object_id",
        "expected_principal_type",
        "tenant_id",
        "metadata_change_set_id",
        "expected_draft_revision",
        "candidate_digest",
        "correlation_id",
    ),
}


def _required_metadata_argument_cases() -> tuple[tuple[str, str], ...]:
    return tuple(
        (function_name, argument_name)
        for function_name, argument_names in REQUIRED_METADATA_ARGUMENTS.items()
        for argument_name in argument_names
    )


def _metadata_call_arguments(
    function_name: str,
) -> list[tuple[str, str, object]]:
    common = [
        ("entra_tenant_id", "UUID", uuid4()),
        ("entra_object_id", "UUID", uuid4()),
        ("expected_principal_type", "VARCHAR", "user"),
        ("tenant_id", "BIGINT", 1),
    ]
    specific = {
        "create_metadata_change_set": [
            ("new_metadata_change_set_id", "UUID", uuid4()),
            ("correlation_id", "UUID", uuid4()),
        ],
        "stage_metadata_change_set": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("expected_draft_revision", "BIGINT", 1),
            ("documents", "JSONB", Jsonb({"copy_group": []})),
            ("correlation_id", "UUID", uuid4()),
        ],
        "begin_metadata_stage_batch": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("expected_draft_revision", "BIGINT", 1),
            ("new_stage_batch_id", "UUID", uuid4()),
            ("dataset_name", "VARCHAR", "copy_group"),
            ("total_record_count", "INTEGER", 1),
            ("total_chunk_count", "INTEGER", 1),
            ("batch_sha256", "CHAR(64)", "a" * 64),
            ("correlation_id", "UUID", uuid4()),
        ],
        "put_metadata_stage_chunk": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("stage_batch_id", "UUID", uuid4()),
            ("dataset_name", "VARCHAR", "copy_group"),
            ("chunk_index", "INTEGER", 1),
            ("chunk_sha256", "CHAR(64)", "a" * 64),
            ("records", "JSONB", Jsonb([{}])),
        ],
        "commit_metadata_stage_batch": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("stage_batch_id", "UUID", uuid4()),
            ("expected_draft_revision", "BIGINT", 1),
            ("correlation_id", "UUID", uuid4()),
        ],
        "get_metadata_change_set": [
            ("metadata_change_set_id", "UUID", uuid4()),
        ],
        "record_metadata_change_set_validation": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("expected_draft_revision", "BIGINT", 1),
            ("validation_succeeded", "BOOLEAN", True),
            ("candidate_digest", "CHAR(64)", "a" * 64),
            ("validation_outcome", "JSONB", Jsonb({"valid": True})),
            ("validation_report_id", "UUID", uuid4()),
            ("correlation_id", "UUID", uuid4()),
        ],
        "archive_metadata_change_set": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("expected_draft_revision", "BIGINT", 1),
            ("correlation_id", "UUID", uuid4()),
        ],
        "apply_metadata_change_set": [
            ("metadata_change_set_id", "UUID", uuid4()),
            ("expected_draft_revision", "BIGINT", 1),
            ("candidate_digest", "CHAR(64)", "a" * 64),
            ("correlation_id", "UUID", uuid4()),
        ],
    }
    return [*common, *specific[function_name]]


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
        assert (
            f"octet_length(({column_name})::text) <= 16777216"
            in document_check["definition"]
        )
    for section_name in NEW_SECTION_NAMES:
        assert section_name in event_section_check["definition"]


def test_metadata_stage_batch_storage_is_bounded_and_not_directly_accessible(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        relations = connection.execute(
            """
            SELECT to_regclass('mcp.metadata_stage_batch') AS batch,
                   to_regclass('mcp.metadata_stage_chunk') AS chunk,
                   has_table_privilege(
                       'gds_app_write', 'mcp.metadata_stage_batch', 'SELECT,INSERT,UPDATE,DELETE'
                   ) AS batch_access,
                   has_table_privilege(
                       'gds_app_write', 'mcp.metadata_stage_chunk', 'SELECT,INSERT,UPDATE,DELETE'
                   ) AS chunk_access
            """
        ).fetchone()
        batch_checks = connection.execute(
            """
            SELECT conname, pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conrelid = 'mcp.metadata_stage_batch'::REGCLASS
               AND conname LIKE 'ck_metadata_stage_batch_%'
             ORDER BY conname
            """
        ).fetchall()
        chunk_check = connection.execute(
            """
            SELECT pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conrelid = 'mcp.metadata_stage_chunk'::REGCLASS
               AND conname = 'ck_metadata_stage_chunk_content'
            """
        ).fetchone()

    assert relations == {
        "batch": "mcp.metadata_stage_batch",
        "chunk": "mcp.metadata_stage_chunk",
        "batch_access": False,
        "chunk_access": False,
    }
    definitions = " ".join(row["definition"] for row in batch_checks)
    assert "total_record_count >= 1" in definitions
    assert "total_record_count <= 50000" in definitions
    assert "total_chunk_count >= 1" in definitions
    assert "total_chunk_count <= 64" in definitions
    assert (
        "active" in definitions
        and "committed" in definitions
        and "expired" in definitions
    )
    assert chunk_check is not None
    assert "jsonb_typeof(records_document) = 'array'" in chunk_check["definition"]
    assert (
        "octet_length((records_document)::text) <= 524288" in chunk_check["definition"]
    )


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
                       'mcp.stage_metadata_change_set(uuid,uuid,varchar,bigint,uuid,bigint,jsonb,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.begin_metadata_stage_batch(uuid,uuid,varchar,bigint,uuid,bigint,uuid,varchar,integer,integer,character,uuid)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.put_metadata_stage_chunk(uuid,uuid,varchar,bigint,uuid,uuid,varchar,integer,character,jsonb)',
                       'EXECUTE'
                   )
                   AND has_function_privilege(
                       'gds_app_write',
                       'mcp.commit_metadata_stage_batch(uuid,uuid,varchar,bigint,uuid,uuid,bigint,uuid)',
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
                   ) AS governed_execute,
                   to_regprocedure(
                       'mcp.stage_metadata_change_set(uuid,uuid,varchar,bigint,uuid,bigint,jsonb,uuid)'
                   ) IS NOT NULL AS multi_dataset_stage_exists,
                   to_regprocedure(
                       'mcp.stage_metadata_change_set(uuid,uuid,varchar,bigint,uuid,bigint,varchar,jsonb,uuid)'
                   ) IS NULL AS single_dataset_stage_removed
            """
        ).fetchone()

    assert row == {
        "direct_select": False,
        "direct_mutation": False,
        "direct_event_insert": False,
        "governed_execute": True,
        "multi_dataset_stage_exists": True,
        "single_dataset_stage_removed": True,
    }


@pytest.mark.parametrize(
    ("function_name", "null_argument"),
    _required_metadata_argument_cases(),
)
def test_metadata_entrypoints_reject_every_required_null_argument(
    postgres_database: DisposablePostgres,
    function_name: str,
    null_argument: str,
) -> None:
    arguments = _metadata_call_arguments(function_name)
    assert sum(name == null_argument for name, _, _ in arguments) == 1
    placeholders = ", ".join(f"%s::{sql_type}" for _, sql_type, _ in arguments)
    values = [None if name == null_argument else value for name, _, value in arguments]

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            f"SELECT denial_code FROM mcp.{function_name}({placeholders})",
            values,
        ).fetchone()

    assert result == {"denial_code": "invalid_request"}


def test_metadata_change_set_enforces_new_document_and_event_contract(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(
            connection, suffix="DOCUMENTS"
        )
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


def test_create_metadata_change_set_expires_stale_draft_once_and_creates_new(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    stale_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    new_id = uuid4()
    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, stale_id)

    with postgres_database.connect_runtime() as connection:
        created = connection.execute(
            """
            SELECT created, denial_code, metadata_change_set_id
              FROM mcp.create_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, new_id, uuid4()),
        ).fetchone()
        blocked = connection.execute(
            """
            SELECT created, denial_code, metadata_change_set_id
              FROM mcp.create_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, uuid4(), uuid4()),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stale = connection.execute(
            """
            SELECT metadata_change_set_status, terminal_time IS NOT NULL AS terminal
              FROM mcp.metadata_change_set
             WHERE metadata_change_set_id = %s
            """,
            (stale_id,),
        ).fetchone()
        expired_events = connection.execute(
            """
            SELECT count(*) AS count, min(outcome) AS outcome,
                   min(action_count) AS action_count
              FROM mcp.metadata_change_set_event
             WHERE metadata_change_set_id = %s
               AND event_type = 'expired'
            """,
            (stale_id,),
        ).fetchone()

    assert created == {
        "created": True,
        "denial_code": None,
        "metadata_change_set_id": new_id,
    }
    assert blocked == {
        "created": False,
        "denial_code": "metadata_change_set_exists",
        "metadata_change_set_id": new_id,
    }
    assert stale == {"metadata_change_set_status": "expired", "terminal": True}
    assert expired_events == {"count": 1, "outcome": "expired", "action_count": 0}


def test_stage_metadata_change_set_replaces_multiple_documents_with_one_revision(
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
    copy_groups = [
        {
            "tenant_code": "CHANGE_SET_TENANT_STAGE",
            "system_code": "CRM",
            "copy_group_name": "CUSTOMERS",
            "copy_group_description": None,
            "is_member_group_required": False,
            "is_active": True,
        }
    ]
    process_groups = [
        {
            "tenant_code": "CHANGE_SET_TENANT_STAGE",
            "system_code": "CRM",
            "zone_code": "bronze",
            "process_group_name": "LOAD_CUSTOMERS",
            "process_group_description": None,
            "copy_group_name": "CUSTOMERS",
            "is_active": True,
        }
    ]
    documents = {
        "copy_group": copy_groups,
        "process_group": process_groups,
    }

    with postgres_database.connect_runtime() as connection:
        staged = connection.execute(
            """
            SELECT staged, denial_code, draft_revision, dataset_counts
              FROM mcp.stage_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::JSONB, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                Jsonb(documents),
                uuid4(),
            ),
        ).fetchone()
        conflict = connection.execute(
            """
            SELECT staged, denial_code, draft_revision, dataset_counts
              FROM mcp.stage_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT,
                  '{"copy_group": []}'::JSONB, %s::UUID
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id, change_set_id, uuid4()),
        ).fetchone()
    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT draft_revision, copy_group_document, process_group_document
              FROM mcp.metadata_change_set
             WHERE metadata_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()
        stage_events = connection.execute(
            """
            SELECT draft_revision, section_name, action_count, event_metadata
              FROM mcp.metadata_change_set_event
             WHERE metadata_change_set_id = %s
               AND event_type = 'section_put'
             ORDER BY event_sequence
            """,
            (change_set_id,),
        ).fetchall()

    assert staged == {
        "staged": True,
        "denial_code": None,
        "draft_revision": 2,
        "dataset_counts": {"copy_group": 1, "process_group": 1},
    }
    assert conflict == {
        "staged": False,
        "denial_code": "draft_revision_conflict",
        "draft_revision": 2,
        "dataset_counts": None,
    }
    assert stored == {
        "draft_revision": 2,
        "copy_group_document": copy_groups,
        "process_group_document": process_groups,
    }
    assert stage_events == [
        {
            "draft_revision": 2,
            "section_name": None,
            "action_count": 2,
            "event_metadata": {"dataset_counts": {"copy_group": 1, "process_group": 1}},
        }
    ]


def test_metadata_stage_batch_commits_complete_chunks_once_and_replays_safely(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000052")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000052")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="STAGE_BATCH",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    stage_batch_id = uuid4()
    chunks = [
        [
            {
                "tenant_code": "CHANGE_SET_TENANT_STAGE_BATCH",
                "system_code": "CRM",
                "copy_group_name": "CUSTOMERS",
                "copy_group_description": None,
                "is_member_group_required": False,
                "is_active": True,
            }
        ],
        [
            {
                "tenant_code": "CHANGE_SET_TENANT_STAGE_BATCH",
                "system_code": "CRM",
                "copy_group_name": "ORDERS",
                "copy_group_description": None,
                "is_member_group_required": False,
                "is_active": True,
            }
        ],
    ]
    chunk_sha256s = [
        hashlib.sha256(f"chunk-{index}".encode()).hexdigest() for index in (1, 2)
    ]
    batch_sha256 = hashlib.sha256("".join(chunk_sha256s).encode("ascii")).hexdigest()

    with postgres_database.connect_runtime() as connection:
        begun = connection.execute(
            """
            SELECT started, denial_code, stage_batch_id, created,
                   total_record_count, total_chunk_count, received_chunk_count
              FROM mcp.begin_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::UUID, 'copy_group'::VARCHAR,
                  2::INTEGER, 2::INTEGER, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                batch_sha256,
                uuid4(),
            ),
        ).fetchone()
        resumed = connection.execute(
            """
            SELECT started, denial_code, stage_batch_id, created, received_chunk_count
              FROM mcp.begin_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::UUID, 'copy_group'::VARCHAR,
                  2::INTEGER, 2::INTEGER, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                uuid4(),
                batch_sha256,
                uuid4(),
            ),
        ).fetchone()
        null_dataset = connection.execute(
            """
            SELECT accepted, denial_code
              FROM mcp.put_metadata_stage_chunk(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, NULL::VARCHAR,
                  1::INTEGER, %s::CHAR(64), %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                chunk_sha256s[0],
                Jsonb(chunks[0]),
            ),
        ).fetchone()
        first = connection.execute(
            """
            SELECT accepted, denial_code, duplicate, received_chunk_count
              FROM mcp.put_metadata_stage_chunk(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, %s::CHAR(64), %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                chunk_sha256s[0],
                Jsonb(chunks[0]),
            ),
        ).fetchone()
        first_replay = connection.execute(
            """
            SELECT accepted, denial_code, duplicate, received_chunk_count
              FROM mcp.put_metadata_stage_chunk(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, %s::CHAR(64), %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                chunk_sha256s[0],
                Jsonb(chunks[0]),
            ),
        ).fetchone()
        incomplete = connection.execute(
            """
            SELECT committed, denial_code, draft_revision
              FROM mcp.commit_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 1::BIGINT, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                uuid4(),
            ),
        ).fetchone()
        conflict = connection.execute(
            """
            SELECT accepted, denial_code
              FROM mcp.put_metadata_stage_chunk(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, %s::CHAR(64), %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                chunk_sha256s[1],
                Jsonb(chunks[1]),
            ),
        ).fetchone()
        second = connection.execute(
            """
            SELECT accepted, denial_code, duplicate, received_chunk_count
              FROM mcp.put_metadata_stage_chunk(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 'copy_group'::VARCHAR,
                  2::INTEGER, %s::CHAR(64), %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                chunk_sha256s[1],
                Jsonb(chunks[1]),
            ),
        ).fetchone()
        committed = connection.execute(
            """
            SELECT committed, denial_code, replayed, dataset_name,
                   record_count, draft_revision
              FROM mcp.commit_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 1::BIGINT, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                uuid4(),
            ),
        ).fetchone()
        replayed = connection.execute(
            """
            SELECT committed, denial_code, replayed, dataset_name,
                   record_count, draft_revision
              FROM mcp.commit_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 1::BIGINT, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                uuid4(),
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT draft_revision, copy_group_document
              FROM mcp.metadata_change_set
             WHERE metadata_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()
        batch = connection.execute(
            """
            SELECT stage_batch_status, committed_revision
              FROM mcp.metadata_stage_batch
             WHERE stage_batch_id = %s
            """,
            (stage_batch_id,),
        ).fetchone()
        event_count = connection.execute(
            """
            SELECT count(*) AS count
              FROM mcp.metadata_change_set_event
             WHERE metadata_change_set_id = %s
               AND event_type = 'section_put'
            """,
            (change_set_id,),
        ).fetchone()

    assert begun == {
        "started": True,
        "denial_code": None,
        "stage_batch_id": stage_batch_id,
        "created": True,
        "total_record_count": 2,
        "total_chunk_count": 2,
        "received_chunk_count": 0,
    }
    assert resumed == {
        "started": True,
        "denial_code": None,
        "stage_batch_id": stage_batch_id,
        "created": False,
        "received_chunk_count": 0,
    }
    assert null_dataset == {"accepted": False, "denial_code": "invalid_request"}
    assert first == {
        "accepted": True,
        "denial_code": None,
        "duplicate": False,
        "received_chunk_count": 1,
    }
    assert first_replay == {
        "accepted": True,
        "denial_code": None,
        "duplicate": True,
        "received_chunk_count": 1,
    }
    assert incomplete == {
        "committed": False,
        "denial_code": "stage_batch_incomplete",
        "draft_revision": None,
    }
    assert conflict == {"accepted": False, "denial_code": "stage_chunk_conflict"}
    assert second == {
        "accepted": True,
        "denial_code": None,
        "duplicate": False,
        "received_chunk_count": 2,
    }
    assert committed == {
        "committed": True,
        "denial_code": None,
        "replayed": False,
        "dataset_name": "copy_group",
        "record_count": 2,
        "draft_revision": 2,
    }
    assert replayed == {
        "committed": True,
        "denial_code": None,
        "replayed": True,
        "dataset_name": "copy_group",
        "record_count": 2,
        "draft_revision": 2,
    }
    assert stored == {"draft_revision": 2, "copy_group_document": chunks[0] + chunks[1]}
    assert batch == {"stage_batch_status": "committed", "committed_revision": 2}
    assert event_count == {"count": 1}


def test_metadata_stage_batches_reject_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_runtime() as connection:
        begun = connection.execute(
            """
            SELECT started, denial_code
              FROM mcp.begin_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, 1::BIGINT,
                  %s::UUID, NULL::BIGINT, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, 1::INTEGER, %s::CHAR(64), %s::UUID
              )
            """,
            (uuid4(), uuid4(), uuid4(), uuid4(), "a" * 64, uuid4()),
        ).fetchone()
        committed = connection.execute(
            """
            SELECT committed, denial_code
              FROM mcp.commit_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, 1::BIGINT,
                  %s::UUID, %s::UUID, NULL::BIGINT, %s::UUID
              )
            """,
            (uuid4(), uuid4(), uuid4(), uuid4(), uuid4()),
        ).fetchone()

    assert begun == {"started": False, "denial_code": "invalid_request"}
    assert committed == {"committed": False, "denial_code": "invalid_request"}


def test_begin_metadata_stage_batch_expires_stale_parent(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, change_set_id)

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT started, denial_code
              FROM mcp.begin_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, 1::INTEGER, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                uuid4(),
                "a" * 64,
                uuid4(),
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT change_set.metadata_change_set_status,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count,
                   count(batch.stage_batch_id) AS batch_count
              FROM mcp.metadata_change_set AS change_set
              LEFT JOIN mcp.metadata_change_set_event AS event
                ON event.metadata_change_set_id = change_set.metadata_change_set_id
              LEFT JOIN mcp.metadata_stage_batch AS batch
                ON batch.metadata_change_set_id = change_set.metadata_change_set_id
             WHERE change_set.metadata_change_set_id = %s
             GROUP BY change_set.metadata_change_set_id
            """,
            (change_set_id,),
        ).fetchone()

    assert result == {
        "started": False,
        "denial_code": "metadata_change_set_not_active",
    }
    assert stored == {
        "metadata_change_set_status": "expired",
        "expired_event_count": 1,
        "batch_count": 0,
    }


def test_put_and_commit_metadata_stage_batch_cannot_use_stale_parent(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    stage_batch_id = uuid4()
    chunk_sha256 = hashlib.sha256(b"expired-chunk").hexdigest()
    batch_sha256 = hashlib.sha256(chunk_sha256.encode("ascii")).hexdigest()
    with postgres_database.connect_runtime() as connection:
        begun = connection.execute(
            """
            SELECT started
              FROM mcp.begin_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, 1::INTEGER, %s::CHAR(64), %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                batch_sha256,
                uuid4(),
            ),
        ).fetchone()
    assert begun == {"started": True}

    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, change_set_id)
        _age_metadata_stage_batch_past_expiry(connection, stage_batch_id)

    with postgres_database.connect_runtime() as connection:
        put = connection.execute(
            """
            SELECT accepted, denial_code
              FROM mcp.put_metadata_stage_chunk(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 'copy_group'::VARCHAR,
                  1::INTEGER, %s::CHAR(64), '[{}]'::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                chunk_sha256,
            ),
        ).fetchone()
        committed = connection.execute(
            """
            SELECT committed, denial_code
              FROM mcp.commit_metadata_stage_batch(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::UUID, 1::BIGINT, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                stage_batch_id,
                uuid4(),
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT change_set.metadata_change_set_status,
                   batch.stage_batch_status,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count,
                   count(chunk.stage_batch_id) AS chunk_count
              FROM mcp.metadata_change_set AS change_set
              JOIN mcp.metadata_stage_batch AS batch
                ON batch.metadata_change_set_id = change_set.metadata_change_set_id
              LEFT JOIN mcp.metadata_change_set_event AS event
                ON event.metadata_change_set_id = change_set.metadata_change_set_id
              LEFT JOIN mcp.metadata_stage_chunk AS chunk
                ON chunk.stage_batch_id = batch.stage_batch_id
             WHERE change_set.metadata_change_set_id = %s
             GROUP BY change_set.metadata_change_set_id, batch.stage_batch_id
            """,
            (change_set_id,),
        ).fetchone()

    assert put == {
        "accepted": False,
        "denial_code": "metadata_change_set_not_active",
    }
    assert committed == {
        "committed": False,
        "denial_code": "metadata_change_set_not_active",
    }
    assert stored == {
        "metadata_change_set_status": "expired",
        "stage_batch_status": "expired",
        "expired_event_count": 1,
        "chunk_count": 0,
    }


def test_stage_metadata_change_set_rejects_the_whole_invalid_request(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000051")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000051")
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix="STAGE_INVALID",
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    documents: dict[str, list[object]] = {
        "copy_group": [],
        "not_a_dataset": [],
    }

    with postgres_database.connect_runtime() as connection:
        rejected = connection.execute(
            """
            SELECT staged, denial_code, draft_revision, dataset_counts
              FROM mcp.stage_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, 1::BIGINT, %s::JSONB, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                Jsonb(documents),
                uuid4(),
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT draft_revision, copy_group_document
              FROM mcp.metadata_change_set
             WHERE metadata_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()
        stage_event_count = connection.execute(
            """
            SELECT count(*) AS count
              FROM mcp.metadata_change_set_event
             WHERE metadata_change_set_id = %s
               AND event_type = 'section_put'
            """,
            (change_set_id,),
        ).fetchone()

    assert rejected == {
        "staged": False,
        "denial_code": "invalid_request",
        "draft_revision": None,
        "dataset_counts": None,
    }
    assert stored == {"draft_revision": 1, "copy_group_document": []}
    assert stage_event_count == {"count": 0}


def test_stage_metadata_change_set_rejects_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT staged, denial_code
              FROM mcp.stage_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, 1::BIGINT,
                  %s::UUID, NULL::BIGINT,
                  '{"copy_group": []}'::JSONB, %s::UUID
              )
            """,
            (uuid4(), uuid4(), uuid4(), uuid4()),
        ).fetchone()

    assert result == {"staged": False, "denial_code": "invalid_request"}


def test_stage_metadata_change_set_expires_stale_draft_once_without_mutating(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, change_set_id)

    results = []
    with postgres_database.connect_runtime() as connection:
        for _ in range(2):
            results.append(
                connection.execute(
                    """
                    SELECT staged, denial_code, draft_revision
                      FROM mcp.stage_metadata_change_set(
                          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                          %s::UUID, 1::BIGINT,
                          '{"copy_group": []}'::JSONB, %s::UUID
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
            )

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT change_set.metadata_change_set_status,
                   change_set.draft_revision,
                   change_set.copy_group_document,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count
              FROM mcp.metadata_change_set AS change_set
              LEFT JOIN mcp.metadata_change_set_event AS event
                ON event.metadata_change_set_id = change_set.metadata_change_set_id
             WHERE change_set.metadata_change_set_id = %s
             GROUP BY change_set.metadata_change_set_id
            """,
            (change_set_id,),
        ).fetchone()

    assert results == [
        {
            "staged": False,
            "denial_code": "metadata_change_set_not_active",
            "draft_revision": 1,
        },
        {
            "staged": False,
            "denial_code": "metadata_change_set_not_active",
            "draft_revision": 1,
        },
    ]
    assert stored == {
        "metadata_change_set_status": "expired",
        "draft_revision": 1,
        "copy_group_document": [],
        "expired_event_count": 1,
    }


def test_metadata_expiry_clock_is_captured_after_waiting_for_row_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    backend_pid: Queue[int] = Queue()

    def stage_after_lock_wait() -> dict[str, Any]:
        with postgres_database.connect_runtime() as connection:
            pid = connection.execute("SELECT pg_backend_pid() AS pid").fetchone()
            assert pid is not None
            backend_pid.put(pid["pid"])
            result = connection.execute(
                """
                SELECT staged, denial_code, draft_revision
                  FROM mcp.stage_metadata_change_set(
                      %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                      %s::UUID, 1::BIGINT,
                      '{"copy_group": []}'::JSONB, %s::UUID
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
            assert result is not None
            return result

    with ThreadPoolExecutor(max_workers=1) as executor:
        with postgres_database.connect_owner() as blocker:
            blocker.execute(
                """
                UPDATE mcp.metadata_change_set
                   SET created_time = clock_timestamp() - INTERVAL '2 hours',
                       last_activity_time = clock_timestamp() - INTERVAL '1 hour',
                       expires_time = clock_timestamp() + INTERVAL '1 second'
                 WHERE metadata_change_set_id = %s
                """,
                (change_set_id,),
            )
            future = executor.submit(stage_after_lock_wait)
            pid = backend_pid.get(timeout=2)

            deadline = time.monotonic() + 2
            while True:
                with postgres_database.connect_owner() as observer:
                    waiting = observer.execute(
                        """
                        SELECT wait_event_type = 'Lock' AS waiting
                          FROM pg_stat_activity
                         WHERE pid = %s
                        """,
                        (pid,),
                    ).fetchone()
                if waiting == {"waiting": True}:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "runtime did not wait for the change-set row lock"
                    )
                time.sleep(0.01)

            deadline = time.monotonic() + 2
            while True:
                expired = blocker.execute(
                    """
                    SELECT clock_timestamp() >= expires_time AS expired
                      FROM mcp.metadata_change_set
                     WHERE metadata_change_set_id = %s
                    """,
                    (change_set_id,),
                ).fetchone()
                if expired == {"expired": True}:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError("change set did not reach its expiry time")
                time.sleep(0.01)
            blocker.commit()

        result = future.result(timeout=2)

    assert result == {
        "staged": False,
        "denial_code": "metadata_change_set_not_active",
        "draft_revision": 1,
    }


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


def test_get_metadata_change_set_persists_expiration_once(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, change_set_id)

    results = []
    with postgres_database.connect_runtime() as connection:
        for _ in range(2):
            results.append(
                connection.execute(
                    """
                    SELECT found, denial_code, metadata_change_set_status,
                           terminal_time IS NOT NULL AS terminal
                      FROM mcp.get_metadata_change_set(
                          %s::UUID, %s::UUID, 'user'::VARCHAR,
                          %s::BIGINT, %s::UUID
                      )
                    """,
                    (
                        entra_tenant_id,
                        entra_object_id,
                        tenant_id,
                        change_set_id,
                    ),
                ).fetchone()
            )

    with postgres_database.connect_owner() as connection:
        expired_event_count = connection.execute(
            """
            SELECT count(*) AS count
              FROM mcp.metadata_change_set_event
             WHERE metadata_change_set_id = %s
               AND event_type = 'expired'
            """,
            (change_set_id,),
        ).fetchone()

    assert results == [
        {
            "found": True,
            "denial_code": None,
            "metadata_change_set_status": "expired",
            "terminal": True,
        },
        {
            "found": True,
            "denial_code": None,
            "metadata_change_set_status": "expired",
            "terminal": True,
        },
    ]
    assert expired_event_count == {"count": 1}


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


@pytest.mark.parametrize(
    ("expected_revision", "validation_succeeded", "validation_outcome"),
    (
        (None, True, {"valid": True}),
        (1, None, {"valid": False}),
        (1, True, None),
    ),
)
def test_metadata_validation_rejects_null_control_inputs(
    postgres_database: DisposablePostgres,
    expected_revision: int | None,
    validation_succeeded: bool | None,
    validation_outcome: dict[str, bool] | None,
) -> None:
    suffix = uuid4().hex.upper()
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=suffix,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT recorded, denial_code
              FROM mcp.record_metadata_change_set_validation(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  %s::UUID, %s::BIGINT, %s::BOOLEAN, %s::CHAR(64),
                  %s::JSONB, %s::UUID, %s::UUID
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                tenant_id,
                change_set_id,
                expected_revision,
                validation_succeeded,
                "a" * 64 if validation_succeeded is not False else None,
                Jsonb(validation_outcome) if validation_outcome is not None else None,
                uuid4(),
                uuid4(),
            ),
        ).fetchone()

    assert result == {"recorded": False, "denial_code": "invalid_request"}


def test_metadata_validation_expires_stale_draft_without_recording(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, change_set_id)

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT recorded, denial_code, metadata_change_set_status
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
                "a" * 64,
                uuid4(),
                uuid4(),
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT change_set.metadata_change_set_status,
                   change_set.candidate_digest,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'validated'
                   ) AS validated_event_count
              FROM mcp.metadata_change_set AS change_set
              LEFT JOIN mcp.metadata_change_set_event AS event
                ON event.metadata_change_set_id = change_set.metadata_change_set_id
             WHERE change_set.metadata_change_set_id = %s
             GROUP BY change_set.metadata_change_set_id
            """,
            (change_set_id,),
        ).fetchone()

    assert result == {
        "recorded": False,
        "denial_code": "metadata_change_set_not_active",
        "metadata_change_set_status": "expired",
    }
    assert stored == {
        "metadata_change_set_status": "expired",
        "candidate_digest": None,
        "expired_event_count": 1,
        "validated_event_count": 0,
    }


def test_apply_metadata_change_set_rejects_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT applied, denial_code
              FROM mcp.apply_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, 1::BIGINT,
                  %s::UUID, NULL::BIGINT, %s::CHAR(64), %s::UUID
              )
            """,
            (uuid4(), uuid4(), uuid4(), "a" * 64, uuid4()),
        ).fetchone()

    assert result == {"applied": False, "denial_code": "invalid_request"}


def test_apply_metadata_change_set_expires_stale_approval_once_without_applying(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    digest = "b" * 64
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE mcp.metadata_change_set
               SET metadata_change_set_status = 'validated',
                   candidate_digest = %s,
                   validation_outcome = '{"valid": true}'::JSONB,
                   validated_time = clock_timestamp() - INTERVAL '90 minutes'
             WHERE metadata_change_set_id = %s
            """,
            (digest, change_set_id),
        )
        _age_metadata_change_set_past_expiry(connection, change_set_id)

    results = []
    with postgres_database.connect_runtime() as connection:
        for _ in range(2):
            results.append(
                connection.execute(
                    """
                    SELECT applied, denial_code, metadata_change_set_status,
                           action_count
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
            )

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT change_set.metadata_change_set_status,
                   change_set.applied_time,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count,
                   count(event.metadata_change_set_event_id) FILTER (
                       WHERE event.event_type = 'applied'
                   ) AS applied_event_count
              FROM mcp.metadata_change_set AS change_set
              LEFT JOIN mcp.metadata_change_set_event AS event
                ON event.metadata_change_set_id = change_set.metadata_change_set_id
             WHERE change_set.metadata_change_set_id = %s
             GROUP BY change_set.metadata_change_set_id
            """,
            (change_set_id,),
        ).fetchone()

    assert results == [
        {
            "applied": False,
            "denial_code": "metadata_change_set_not_validated",
            "metadata_change_set_status": "expired",
            "action_count": 0,
        },
        {
            "applied": False,
            "denial_code": "metadata_change_set_not_validated",
            "metadata_change_set_status": "expired",
            "action_count": 0,
        },
    ]
    assert stored == {
        "metadata_change_set_status": "expired",
        "applied_time": None,
        "expired_event_count": 1,
        "applied_event_count": 0,
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
        system = connection.execute(
            """
            INSERT INTO core.system (
                system_code, system_name, system_type_id
            ) VALUES ('CRM_APPLY', 'CRM Apply', %s)
            RETURNING system_id
            """,
            (system_type["system_type_id"],),
        ).fetchone()
        assert system is not None
        connection.execute(
            """
            INSERT INTO core.copy_group (
                tenant_id, system_id, copy_group_name,
                copy_group_description, updated_time
            ) VALUES (
                %s, %s, 'CUSTOMERS', 'Existing description',
                clock_timestamp() - INTERVAL '1 day'
            )
            """,
            (tenant_id, system["system_id"]),
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
            SELECT applied, denial_code, metadata_change_set_status,
                   applied_time, action_count
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
                   copy_group.is_active,
                   copy_group.updated_time
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
        "applied_time": stored["updated_time"],
        "action_count": 1,
    }
    assert stored == {
        "copy_group_name": "CUSTOMERS",
        "copy_group_description": "Customer ingestion",
        "is_active": True,
        "updated_time": applied["applied_time"],
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
        "source_tenant_code": tenant_code,
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
                connection_id, source_tenant_id,
                object_schema, object_name, object_description,
                object_type_id, zone_id, is_locked
            ) VALUES (%s, %s, 'public', 'customers', 'Original', %s, %s, TRUE)
            RETURNING object_id
            """,
            (connection_id, tenant_id, object_type_id, zone_id),
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
        "source_tenant_code": tenant_code,
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
        "zone_code": "bronze",
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
            "SELECT zone_id FROM reference.zone WHERE lower(btrim(zone_code)) = 'bronze'"
        ).fetchone()
        if zone is None:
            zone = connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES ('bronze', 'Bronze')
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
        gds_connection = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id, is_global_data_store
            ) VALUES (%s, %s, 'MAIN', 'Main', %s, TRUE)
            RETURNING connection_id
            """,
            (tenant_id, system_id, connection_type_id),
        ).fetchone()
        assert gds_connection is not None
        connection.execute(
            "UPDATE core.tenant SET gds_connection_id = %s WHERE tenant_id = %s",
            (gds_connection["connection_id"], tenant_id),
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

    with pytest.raises(
        psycopg.errors.SerializationFailure, match="Copy dependency changed"
    ):
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


def test_archive_metadata_change_set_rejects_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT archived, denial_code
              FROM mcp.archive_metadata_change_set(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, 1::BIGINT,
                  %s::UUID, NULL::BIGINT, %s::UUID
              )
            """,
            (uuid4(), uuid4(), uuid4(), uuid4()),
        ).fetchone()

    assert result == {"archived": False, "denial_code": "invalid_request"}


def test_archive_metadata_change_set_expires_stale_draft_instead_of_archiving(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    change_set_id, tenant_id = _seed_locked_change_set(
        postgres_database,
        suffix=uuid4().hex.upper(),
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with postgres_database.connect_owner() as connection:
        _age_metadata_change_set_past_expiry(connection, change_set_id)

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT archived, denial_code, metadata_change_set_status
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

    with postgres_database.connect_owner() as connection:
        events = connection.execute(
            """
            SELECT event_type, outcome
              FROM mcp.metadata_change_set_event
             WHERE metadata_change_set_id = %s
               AND event_type IN ('expired', 'archived')
             ORDER BY event_sequence
            """,
            (change_set_id,),
        ).fetchall()

    assert result == {
        "archived": False,
        "denial_code": "metadata_change_set_not_active",
        "metadata_change_set_status": "expired",
    }
    assert events == [{"event_type": "expired", "outcome": "expired"}]


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
        for zone_code in ("source", "bronze", "silver", "gold"):
            if (
                connection.execute(
                    "SELECT 1 FROM reference.zone WHERE lower(btrim(zone_code)) = %s",
                    (zone_code,),
                ).fetchone()
                is None
            ):
                connection.execute(
                    "INSERT INTO reference.zone (zone_code, zone_name) VALUES (%s, %s)",
                    (zone_code, zone_code.title()),
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
                connection_type_id, has_foreign_catalog, foreign_catalog
            ) VALUES (%s, %s, 'SOURCE', 'Source', %s, TRUE, 'source_catalog')
            """,
            (tenant_id, system_id, connection_type_id),
        )
        gds_connection = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id, is_global_data_store
            ) VALUES (%s, %s, 'GDS', 'GDS', %s, TRUE)
            RETURNING connection_id
            """,
            (tenant_id, system_id, connection_type_id),
        ).fetchone()
        assert gds_connection is not None
        connection.execute(
            "UPDATE core.tenant SET gds_connection_id = %s WHERE tenant_id = %s",
            (gds_connection["connection_id"], tenant_id),
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
                *(
                    Jsonb(documents[name])
                    for name in (
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
                    )
                ),
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
                   (
                       SELECT count(*)
                         FROM core.ingestion_object_mapping AS mapping
                         JOIN core.object AS source_object
                           ON source_object.object_id = mapping.source_object_id
                         JOIN core.connection AS source_connection
                           ON source_connection.connection_id = source_object.connection_id
                        WHERE source_connection.tenant_id = %s
                   ) AS object_mappings,
                   (
                       SELECT count(*)
                         FROM core.ingestion_attribute_mapping AS mapping
                         JOIN core.attribute AS source_attribute
                           ON source_attribute.attribute_id = mapping.source_attribute_id
                         JOIN core.object AS source_object
                           ON source_object.object_id = source_attribute.object_id
                         JOIN core.connection AS source_connection
                           ON source_connection.connection_id = source_object.connection_id
                        WHERE source_connection.tenant_id = %s
                   ) AS attribute_mappings,
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


def test_apply_assigns_locked_tenant_to_object_on_global_connection(
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
        "source_tenant_code": "CHANGE_SET_TENANT_SCOPED_APPLY",
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
        "zone_code": "bronze",
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
             WHERE lower(btrim(zone_code)) = 'bronze'
            """
        ).fetchone()
        if zone is None:
            zone = connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES ('bronze', 'Bronze')
                RETURNING zone_id
                """
            ).fetchone()
        assert zone is not None
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
            "UPDATE core.tenant SET gds_connection_id = %s WHERE tenant_id = %s",
            (connection_id, tenant_id),
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
            SELECT object.object_name, object.source_tenant_id
              FROM core.object AS object
             WHERE object.connection_id = %s
            """,
            (connection_id,),
        ).fetchone()
        connection.rollback()

    assert object_type_id > 0
    assert applied == {"applied": True, "denial_code": None, "action_count": 1}
    assert stored == {
        "object_name": "customers",
        "source_tenant_id": tenant_id,
    }


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
            "source_tenant_code": tenant_code,
            "system_code": system_code,
            "connection_code": "SOURCE" if zone_code == "source" else "GDS",
            "object_schema": "public",
            "object_name": object_name,
            "fc_object_schema": "public" if zone_code == "source" else None,
            "fc_object_name": object_name if zone_code == "source" else None,
            "object_transformation": None,
            "object_description": f"{zone_code} customers",
            "batch_attribute_name": None,
            "object_type_code": "TABLE_ALL_APPLY",
            "zone_code": zone_code,
            "is_locked": False,
            "is_active": True,
        }
        attribute_records[zone_code] = {
            "tenant_code": tenant_code,
            "system_code": system_code,
            "connection_code": "SOURCE" if zone_code == "source" else "GDS",
            "object_schema": "public",
            "object_name": object_name,
            "attribute_name": "customer_id",
            "fc_attribute_name": "customer_id" if zone_code == "source" else None,
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

    object_mapping: dict[str, object] = {
        "source_tenant_code": tenant_code,
        "source_system_code": system_code,
        "source_connection_code": "SOURCE",
        "source_object_schema": "public",
        "source_object_name": "source_customers",
        "target_tenant_code": tenant_code,
        "target_system_code": system_code,
        "target_connection_code": "GDS",
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
                "zone_code": "bronze",
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
                "zone_code": "bronze",
                "process_group_name": "CUSTOMER_PROCESS",
                "process_execution_order": 1,
                "process_location": "/Workspace/customer",
                "process_executable": "load_customer",
                "object_tenant_code": tenant_code,
                "object_system_code": system_code,
                "object_connection_code": "GDS",
                "object_schema": "public",
                "object_name": "bronze_customers",
                "process_type_name": "NOTEBOOK_ALL_APPLY",
                "is_active": True,
            }
        ],
    }


def _age_metadata_change_set_past_expiry(
    connection: Connection[Any], change_set_id: UUID
) -> None:
    connection.execute(
        """
        UPDATE mcp.metadata_change_set
           SET created_time = clock_timestamp() - INTERVAL '3 hours',
               last_activity_time = clock_timestamp() - INTERVAL '2 hours',
               expires_time = clock_timestamp() - INTERVAL '1 hour'
         WHERE metadata_change_set_id = %s
        """,
        (change_set_id,),
    )


def _age_metadata_stage_batch_past_expiry(
    connection: Connection[Any], stage_batch_id: UUID
) -> None:
    connection.execute(
        """
        UPDATE mcp.metadata_stage_batch
           SET created_time = clock_timestamp() - INTERVAL '3 hours',
               last_activity_time = clock_timestamp() - INTERVAL '2 hours',
               expires_time = clock_timestamp() - INTERVAL '1 hour'
         WHERE stage_batch_id = %s
        """,
        (stage_batch_id,),
    )


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
