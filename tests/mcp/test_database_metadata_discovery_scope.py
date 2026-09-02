from __future__ import annotations

from typing import TYPE_CHECKING, Any

import psycopg
import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


def test_object_has_mandatory_source_tenant_ownership(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        column = connection.execute(
            """
            SELECT data_type, is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'core'
               AND table_name = 'object'
               AND column_name = 'source_tenant_id'
            """
        ).fetchone()
        foreign_key = connection.execute(
            """
            SELECT pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conrelid = 'core.object'::REGCLASS
               AND conname = 'fk_object_source_tenant'
               AND contype = 'f'
            """
        ).fetchone()
        ownership_index = connection.execute(
            """
            SELECT indexdef
              FROM pg_indexes
             WHERE schemaname = 'core'
               AND indexname = 'ix_object_source_tenant_zone_active'
            """
        ).fetchone()

    assert column == {"data_type": "bigint", "is_nullable": "NO"}
    assert foreign_key == {
        "definition": "FOREIGN KEY (source_tenant_id) REFERENCES core.tenant(tenant_id)"
    }
    assert ownership_index is not None
    assert "(source_tenant_id, zone_id) WHERE is_active" in ownership_index["indexdef"]


def test_discovery_scope_table_is_removed(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            "SELECT to_regclass('core.tenant_metadata_discovery_scope') AS relation"
        ).fetchone()

    assert row == {"relation": None}


def test_global_connection_object_stores_the_data_tenant_directly(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        data_tenant_id, connection_id, zone_id, object_type_id = _seed_object_parents(
            connection
        )
        row = connection.execute(
            """
            INSERT INTO core.object (
                connection_id,
                source_tenant_id,
                object_schema,
                object_name,
                object_type_id,
                zone_id
            ) VALUES (%s, %s, 'bronze_data', 'customer', %s, %s)
            RETURNING source_tenant_id
            """,
            (connection_id, data_tenant_id, object_type_id, zone_id),
        ).fetchone()

        assert row == {"source_tenant_id": data_tenant_id}

        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            connection.transaction(),
        ):
            connection.execute(
                """
                INSERT INTO core.object (
                    connection_id,
                    source_tenant_id,
                    object_schema,
                    object_name,
                    object_type_id,
                    zone_id
                ) VALUES (%s, 9223372036854775807, 'bronze_data', 'invalid', %s, %s)
                """,
                (connection_id, object_type_id, zone_id),
            )

        connection.rollback()


def _seed_object_parents(connection: Connection[Any]) -> tuple[int, int, int, int]:
    project_id = connection.execute(
        """
        INSERT INTO core.project (project_code, project_name)
        VALUES ('OBJECT_OWNER_PROJECT', 'Object Owner Project')
        RETURNING project_id
        """
    ).fetchone()["project_id"]
    data_tenant_id = connection.execute(
        """
        INSERT INTO core.tenant (
            project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog
        ) VALUES (%s, 'OBJECT_DATA_TENANT', 'Object Data Tenant', 'data', 'data_admin')
        RETURNING tenant_id
        """,
        (project_id,),
    ).fetchone()["tenant_id"]
    gds_tenant_id = connection.execute(
        """
        INSERT INTO core.tenant (
            project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog
        ) VALUES (%s, 'OBJECT_GDS_TENANT', 'Object GDS Tenant', 'gds', 'gds_admin')
        RETURNING tenant_id
        """,
        (project_id,),
    ).fetchone()["tenant_id"]
    system_type_id = connection.execute(
        """
        INSERT INTO reference.system_type (system_type_code, system_type_name)
        VALUES ('OBJECT_OWNER_TYPE', 'Object Owner Type')
        RETURNING system_type_id
        """
    ).fetchone()["system_type_id"]
    system_id = connection.execute(
        """
        INSERT INTO core.system (system_code, system_name, system_type_id)
        VALUES ('OBJECT_OWNER_SYSTEM', 'Object Owner System', %s)
        RETURNING system_id
        """,
        (system_type_id,),
    ).fetchone()["system_id"]
    connection_type_id = connection.execute(
        """
        INSERT INTO reference.connection_type (
            connection_type_code, connection_type_name
        ) VALUES ('OBJECT_OWNER_CONNECTION', 'Object Owner Connection')
        RETURNING connection_type_id
        """
    ).fetchone()["connection_type_id"]
    connection_id = connection.execute(
        """
        INSERT INTO core.connection (
            tenant_id, system_id, connection_code, connection_name,
            connection_type_id, is_global_data_store
        ) VALUES (%s, %s, 'OBJECT_GDS', 'Object GDS', %s, TRUE)
        RETURNING connection_id
        """,
        (gds_tenant_id, system_id, connection_type_id),
    ).fetchone()["connection_id"]
    zone_id = connection.execute(
        """
        INSERT INTO reference.zone (zone_code, zone_name)
        VALUES ('object_owner_bronze', 'Object Owner Bronze')
        RETURNING zone_id
        """
    ).fetchone()["zone_id"]
    object_type_id = connection.execute(
        """
        INSERT INTO reference.object_type (object_type_code, object_type_name)
        VALUES ('OBJECT_OWNER_TABLE', 'Object Owner Table')
        RETURNING object_type_id
        """
    ).fetchone()["object_type_id"]
    return data_tenant_id, connection_id, zone_id, object_type_id
