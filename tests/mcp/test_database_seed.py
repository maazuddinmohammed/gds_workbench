from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import UUID

import psycopg
import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres


SEED_ROOT = Path(__file__).parents[2] / "database" / "seed"
DEMO_SEED = SEED_ROOT / "01_metadata_snapshot_demo.sql"
HUMAN_SEED_TEMPLATE = SEED_ROOT / "02_human_principal_access.template.sql"
LOCAL_SUPER_ADMIN_SEED_TEMPLATE = SEED_ROOT / "03_local_super_admin.template.sql"


def test_local_super_admin_seed_is_safe_and_resolves_the_configured_identity(
    postgres_database: DisposablePostgres,
) -> None:
    template = LOCAL_SUPER_ADMIN_SEED_TEMPLATE.read_text(encoding="utf-8")
    connection = postgres_database.connect_owner()
    try:
        with pytest.raises(psycopg.errors.RaiseException), connection.transaction():
            connection.execute(cast(LiteralString, template))

        rendered = (
            template.replace(
                "__REPLACE_WITH_EXPECTED_DATABASE_NAME__",
                postgres_database.database,
            )
            .replace(
                "__REPLACE_WITH_ENTRA_TENANT_ID__",
                "73000000-0000-0000-0000-000000000001",
            )
            .replace(
                "__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__",
                "74000000-0000-0000-0000-000000000001",
            )
        )
        assert "__REPLACE_WITH_EXPECTED_DATABASE_NAME__" not in rendered
        assert "__REPLACE_WITH_ENTRA_TENANT_ID__" not in rendered
        assert "__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__" not in rendered

        connection.execute(cast(LiteralString, rendered))
        row = connection.execute(
            """
            SELECT principal.principal_display_name,
                   principal.principal_email,
                   principal.is_super_admin,
                   principal.is_active,
                   identity.entra_tenant_id,
                   identity.entra_object_id,
                   identity.is_active AS identity_is_active
              FROM security.principal AS principal
              JOIN security.entra_principal_identity AS identity
                ON identity.principal_id = principal.principal_id
             WHERE principal.principal_email = 'local.developer@local.invalid'
            """
        ).fetchone()
    finally:
        connection.rollback()
        connection.close()

    assert row == {
        "principal_display_name": "Local Developer",
        "principal_email": "local.developer@local.invalid",
        "is_super_admin": True,
        "is_active": True,
        "entra_tenant_id": UUID("73000000-0000-0000-0000-000000000001"),
        "entra_object_id": UUID("74000000-0000-0000-0000-000000000001"),
        "identity_is_active": True,
    }


def test_demo_and_human_access_seeds_are_safe_and_complete(
    postgres_database: DisposablePostgres,
) -> None:
    template = HUMAN_SEED_TEMPLATE.read_text(encoding="utf-8")
    connection = postgres_database.connect_owner()
    try:
        connection.execute(cast(LiteralString, DEMO_SEED.read_text(encoding="utf-8")))

        with pytest.raises(psycopg.errors.RaiseException), connection.transaction():
            connection.execute(cast(LiteralString, template))

        rendered = template
        replacements = {
            "__REPLACE_WITH_ENTRA_TENANT_ID__": "71000000-0000-0000-0000-000000000001",
            "__REPLACE_WITH_ENTRA_OBJECT_ID__": "72000000-0000-0000-0000-000000000001",
            "__REPLACE_WITH_DISPLAY_NAME__": "Metadata Snapshot Tester",
            "__REPLACE_WITH_LOGIN_EMAIL__": "metadata.snapshot.tester@example.test",
            "__REPLACE_WITH_TENANT_CODE__": "DEMO_TENANT",
        }
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value)
        assert all(placeholder not in rendered for placeholder in replacements)

        connection.execute(cast(LiteralString, rendered))

        row = connection.execute(
            """
            SELECT tenant.tenant_id,
                   count(DISTINCT object.object_id) AS object_count,
                   count(DISTINCT attribute.attribute_id) AS attribute_count,
                   (
                       SELECT count(*)
                         FROM core.ingestion_object_mapping AS mapping
                         JOIN core.object AS source_object
                           ON source_object.object_id = mapping.source_object_id
                        WHERE source_object.object_schema IN (
                                  'source_demo',
                                  'bronze_demo',
                                  'silver_demo'
                              )
                   ) AS object_mapping_count,
                   (
                       SELECT count(*)
                         FROM core.ingestion_attribute_mapping AS mapping
                         JOIN core.object AS source_object
                           ON source_object.object_id = mapping.source_object_id
                        WHERE source_object.object_schema IN (
                                  'source_demo',
                                  'bronze_demo',
                                  'silver_demo'
                              )
                   ) AS attribute_mapping_count,
                   (
                       SELECT count(*)
                         FROM core.tenant_metadata_discovery_scope AS scope
                        WHERE scope.tenant_id = tenant.tenant_id
                   ) AS discovery_scope_count
              FROM core.tenant AS tenant
              JOIN core.connection AS connection
                ON connection.tenant_id IN (
                       tenant.tenant_id,
                       (
                           SELECT global_tenant.tenant_id
                             FROM core.tenant AS global_tenant
                            WHERE global_tenant.tenant_code = 'DEMO_GDS_TENANT'
                       )
                   )
              JOIN core.object AS object
                ON object.connection_id = connection.connection_id
              JOIN core.attribute AS attribute
                ON attribute.object_id = object.object_id
             WHERE tenant.tenant_code = 'DEMO_TENANT'
             GROUP BY tenant.tenant_id
            """
        ).fetchone()
        assert row is not None
        assert row["object_count"] == 4
        assert row["attribute_count"] == 8
        assert row["object_mapping_count"] == 3
        assert row["attribute_mapping_count"] == 6
        assert row["discovery_scope_count"] == 3
        tenant_id = row["tenant_id"]
        decision = connection.execute(
            """
            SELECT authorized, effective_role, denial_code
              FROM security.authorize_tenant_operation(%s, %s, %s, %s, %s)
            """,
            (
                UUID("71000000-0000-0000-0000-000000000001"),
                UUID("72000000-0000-0000-0000-000000000001"),
                "user",
                tenant_id,
                "tenant_read",
            ),
        ).fetchone()
    finally:
        connection.rollback()
        connection.close()

    assert decision == {
        "authorized": True,
        "effective_role": "viewer",
        "denial_code": None,
    }
