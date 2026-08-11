from __future__ import annotations

from typing import TYPE_CHECKING, Any

import psycopg
import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


EXPECTED_COLUMNS = [
    "tenant_metadata_discovery_scope_id",
    "tenant_id",
    "connection_id",
    "zone_id",
    "object_schema",
    "is_active",
    "created_time",
    "created_by",
    "updated_time",
    "updated_by",
]


def test_metadata_discovery_scope_has_exact_structure_and_runtime_posture(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'core'
               AND table_name = 'tenant_metadata_discovery_scope'
             ORDER BY ordinal_position
            """
        ).fetchall()
        constraints = connection.execute(
            """
            SELECT conname, pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conrelid = 'core.tenant_metadata_discovery_scope'::REGCLASS
             ORDER BY conname
            """
        ).fetchall()
        indexes = connection.execute(
            """
            SELECT indexname, indexdef
              FROM pg_indexes
             WHERE schemaname = 'core'
               AND tablename = 'tenant_metadata_discovery_scope'
             ORDER BY indexname
            """
        ).fetchall()
        privileges = connection.execute(
            """
            SELECT has_table_privilege(
                       'gds_app_write',
                       'core.tenant_metadata_discovery_scope',
                       'SELECT'
                   ) AS can_select,
                   has_table_privilege(
                       'gds_app_write',
                       'core.tenant_metadata_discovery_scope',
                       'INSERT'
                   )
                   OR has_table_privilege(
                       'gds_app_write',
                       'core.tenant_metadata_discovery_scope',
                       'UPDATE'
                   )
                   OR has_table_privilege(
                       'gds_app_write',
                       'core.tenant_metadata_discovery_scope',
                       'DELETE'
                   )
                   OR has_table_privilege(
                       'gds_app_write',
                       'core.tenant_metadata_discovery_scope',
                       'TRUNCATE'
                   ) AS can_mutate
            """
        ).fetchone()

    assert [column["column_name"] for column in columns] == EXPECTED_COLUMNS
    assert {constraint["conname"]: constraint["definition"] for constraint in constraints} == {
        "ck_metadata_discovery_scope_schema": (
            "CHECK (reference.is_nonblank((object_schema)::text))"
        ),
        "fk_metadata_discovery_scope_connection": (
            "FOREIGN KEY (connection_id) REFERENCES core.connection(connection_id)"
        ),
        "fk_metadata_discovery_scope_tenant": (
            "FOREIGN KEY (tenant_id) REFERENCES core.tenant(tenant_id)"
        ),
        "fk_metadata_discovery_scope_zone": (
            "FOREIGN KEY (zone_id) REFERENCES reference.zone(zone_id)"
        ),
        "tenant_metadata_discovery_scope_pkey": (
            "PRIMARY KEY (tenant_metadata_discovery_scope_id)"
        ),
    }
    assert any(
        index["indexname"] == "ux_metadata_discovery_scope"
        and "UNIQUE INDEX" in index["indexdef"]
        and "lower(btrim((object_schema)::text))" in index["indexdef"]
        for index in indexes
    )
    assert privileges == {"can_select": True, "can_mutate": False}


def test_metadata_discovery_scope_uses_normalized_schema_identity(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        tenant_id, connection_id, zone_id = _seed_scope_parents(connection)
        row = connection.execute(
            """
            INSERT INTO core.tenant_metadata_discovery_scope (
                tenant_id,
                connection_id,
                zone_id,
                object_schema
            )
            VALUES (%s, %s, %s, 'risk_curated')
            RETURNING tenant_metadata_discovery_scope_id,
                      tenant_id,
                      connection_id,
                      zone_id,
                      object_schema,
                      is_active
            """,
            (tenant_id, connection_id, zone_id),
        ).fetchone()

        assert row is not None
        assert row["tenant_metadata_discovery_scope_id"] > 0
        assert row["tenant_id"] == tenant_id
        assert row["connection_id"] == connection_id
        assert row["zone_id"] == zone_id
        assert row["object_schema"] == "risk_curated"
        assert row["is_active"] is True

        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                """
                    INSERT INTO core.tenant_metadata_discovery_scope (
                        tenant_id,
                        connection_id,
                        zone_id,
                        object_schema
                    )
                    VALUES (%s, %s, %s, '  RISK_CURATED  ')
                    """,
                (tenant_id, connection_id, zone_id),
            )

        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """
                    INSERT INTO core.tenant_metadata_discovery_scope (
                        tenant_id,
                        connection_id,
                        zone_id,
                        object_schema
                    )
                    VALUES (%s, %s, %s, '   ')
                    """,
                (tenant_id, connection_id, zone_id),
            )


def _seed_scope_parents(connection: Connection[Any]) -> tuple[int, int, int]:
    project = connection.execute(
        """
        INSERT INTO core.project (project_code, project_name)
        VALUES ('DISCOVERY_PROJECT', 'Discovery Project')
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
        VALUES (%s, 'DISCOVERY_TENANT', 'Discovery Tenant',
                'discovery_catalog', 'discovery_admin')
        RETURNING tenant_id
        """,
        (project["project_id"],),
    ).fetchone()
    assert tenant is not None
    system_type = connection.execute(
        """
        INSERT INTO reference.system_type (system_type_code, system_type_name)
        VALUES ('DISCOVERY_TYPE', 'Discovery Type')
        RETURNING system_type_id
        """
    ).fetchone()
    assert system_type is not None
    system = connection.execute(
        """
        INSERT INTO core.system (system_code, system_name, system_type_id)
        VALUES ('DISCOVERY_SYSTEM', 'Discovery System', %s)
        RETURNING system_id
        """,
        (system_type["system_type_id"],),
    ).fetchone()
    assert system is not None
    connection_type = connection.execute(
        """
        INSERT INTO reference.connection_type (
            connection_type_code,
            connection_type_name
        )
        VALUES ('DISCOVERY_CONNECTION', 'Discovery Connection')
        RETURNING connection_type_id
        """
    ).fetchone()
    assert connection_type is not None
    global_connection = connection.execute(
        """
        INSERT INTO core.connection (
            tenant_id,
            system_id,
            connection_code,
            connection_name,
            connection_type_id,
            is_global_data_store
        )
        VALUES (%s, %s, 'DISCOVERY_GLOBAL', 'Discovery Global', %s, TRUE)
        RETURNING connection_id
        """,
        (
            tenant["tenant_id"],
            system["system_id"],
            connection_type["connection_type_id"],
        ),
    ).fetchone()
    assert global_connection is not None
    zone = connection.execute(
        """
        INSERT INTO reference.zone (zone_code, zone_name)
        VALUES ('bronze', 'Bronze')
        RETURNING zone_id
        """
    ).fetchone()
    assert zone is not None
    return tenant["tenant_id"], global_connection["connection_id"], zone["zone_id"]
