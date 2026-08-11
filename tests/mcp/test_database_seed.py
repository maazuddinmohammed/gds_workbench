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


def test_demo_and_human_access_seeds_are_safe_and_complete(
    postgres_database: DisposablePostgres,
) -> None:
    template = HUMAN_SEED_TEMPLATE.read_text(encoding="utf-8")
    with postgres_database.connect_owner() as connection:
        with connection.transaction():
            connection.execute(
                cast(LiteralString, DEMO_SEED.read_text(encoding="utf-8"))
            )

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

        with connection.transaction():
            connection.execute(cast(LiteralString, rendered))

        row = connection.execute(
            """
            SELECT tenant.tenant_id,
                   count(DISTINCT object.object_id) AS object_count,
                   count(DISTINCT attribute.attribute_id) AS attribute_count,
                   (
                       SELECT count(*)
                         FROM core.ingestion_object_mapping
                   ) AS object_mapping_count,
                   (
                       SELECT count(*)
                         FROM core.ingestion_attribute_mapping
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

    with postgres_database.connect_runtime() as connection:
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

    assert decision == {
        "authorized": True,
        "effective_role": "viewer",
        "denial_code": None,
    }
