"""Run the local review journey against the verified disposable install only."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.errors import RaiseException

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


SEED_ROOT = Path(__file__).parents[2] / "database" / "seed"


def test_local_workbench_seed_uses_the_simplified_workflow_schema(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    database = bootstrap_postgres_database
    review_seed = (SEED_ROOT / "07_local_workbench_review.sql").read_text()
    original_guard = "current_database() !~ '^gds_local_[0-9a-f]{12}$'"
    assert review_seed.count(original_guard) == 1

    # connect_owner verifies fixture ownership, server identity, and sentinel.
    # Verify the sentinel explicitly before adapting this local-only seed guard.
    with database.connect_owner() as connection:
        sentinel = require_row(
            connection.execute("SELECT marker FROM public.gds_test_sentinel").fetchone()
        )
        assert sentinel["marker"] == database.marker
        with (
            pytest.raises(RaiseException, match="requires a disposable gds_local database"),
            connection.transaction(),
        ):
            connection.execute(cast(LiteralString, review_seed))

        # Match install_database.sh's bootstrap order. All identities are per-run;
        # the connection comes exclusively from the disposable PostgreSQL fixture.
        for seed_name in (
            "01_metadata_snapshot_demo.sql",
            "04_application_reference.sql",
        ):
            connection.execute(cast(LiteralString, (SEED_ROOT / seed_name).read_text()))
        entra_tenant_id, principal_object_id = uuid4(), uuid4()
        identity_seed = (
            (SEED_ROOT / "03_local_super_admin.template.sql")
            .read_text()
            .replace("__REPLACE_WITH_EXPECTED_DATABASE_NAME__", database.database)
            .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(entra_tenant_id))
            .replace("__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__", str(principal_object_id))
        )
        connection.execute(cast(LiteralString, identity_seed))
        for seed_name in (
            "05_global_prompt_defaults.template.sql",
            "06_global_mapping_output_templates.template.sql",
        ):
            rendered = (
                (SEED_ROOT / seed_name)
                .read_text()
                .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(entra_tenant_id))
                .replace("__REPLACE_WITH_ENTRA_OBJECT_ID__", str(principal_object_id))
                .replace("__REPLACE_WITH_PRINCIPAL_TYPE__", "user")
            )
            connection.execute(cast(LiteralString, rendered))

        # Change only the exact production guard, in memory, to require this
        # verified fixture's exact database name. The checked-in guard stays intact.
        fixture_guard = (
            sql.SQL("current_database() <> {}")
            .format(sql.Literal(database.database))
            .as_string(connection)
        )
        fixture_seed = review_seed.replace(original_guard, fixture_guard, 1)
        connection.execute(cast(LiteralString, fixture_seed))

        project_id = require_row(
            connection.execute(
                """
                SELECT project.project_id
                  FROM project.project AS project
                  JOIN core.tenant AS tenant USING (tenant_id)
                 WHERE tenant.tenant_code = 'DEMO_TENANT'
                   AND project.project_name = 'Customer Orders 360'
                """
            ).fetchone()
        )["project_id"]
        for table, expected in (
            ("analysis_result", 1),
            ("subject_area", 1),
            ("subject_area_table", 2),
            ("logical_entity", 2),
            ("logical_attribute", 6),
            ("dimensional_entity", 2),
            ("dimensional_attribute", 6),
            ("dimensional_entity_source_mapping", 2),
            ("dimensional_attribute_source_mapping", 6),
            ("dimensional_relationship", 1),
        ):
            count = require_row(
                connection.execute(
                    sql.SQL(
                        "SELECT count(*) AS count FROM workflow.{} WHERE project_id = %s"
                    ).format(sql.Identifier(table)),
                    (project_id,),
                ).fetchone()
            )
            assert count["count"] == expected

        flags = require_row(
            connection.execute(
                """
                SELECT count(*) FILTER (WHERE dimensional_attribute_is_natural_key) AS natural,
                       count(*) FILTER (WHERE dimensional_attribute_is_surrogate_key) AS surrogate,
                       count(*) FILTER (WHERE dimensional_attribute_is_audit_column) AS audit,
                       count(*) FILTER (
                           WHERE dimensional_attribute_is_nullable
                             AND (dimensional_attribute_is_natural_key
                                  OR dimensional_attribute_is_surrogate_key)
                       ) AS nullable_keys
                  FROM workflow.dimensional_attribute
                 WHERE project_id = %s
                """,
                (project_id,),
            ).fetchone()
        )
        assert flags == {"natural": 0, "surrogate": 1, "audit": 0, "nullable_keys": 0}
        # Kind and optionality are not stored: kind follows the two Entity types and
        # optionality is the foreign-key Attribute's nullability.
        relationship = require_row(
            connection.execute(
                """
                SELECT CASE
                           WHEN from_entity.dimensional_entity_type = 'fact'
                            AND to_entity.dimensional_entity_type = 'dimension'
                           THEN 'fact_dimension'
                           WHEN from_entity.dimensional_entity_type = 'bridge'
                            AND to_entity.dimensional_entity_type = 'dimension'
                           THEN 'bridge_dimension'
                           WHEN from_entity.dimensional_entity_type = 'dimension'
                            AND to_entity.dimensional_entity_type = 'dimension'
                           THEN 'dimension_outrigger'
                           ELSE 'reference'
                       END AS kind,
                       source.dimensional_attribute_is_nullable AS optional,
                       relationship.dimensional_relationship_role_name AS role,
                       source.dimensional_attribute_is_surrogate_key AS source_surrogate,
                       target.dimensional_attribute_is_surrogate_key AS target_surrogate
                  FROM workflow.dimensional_relationship AS relationship
                  JOIN workflow.dimensional_entity AS from_entity
                    ON from_entity.dimensional_entity_id =
                       relationship.dimensional_relationship_from_entity_id
                  JOIN workflow.dimensional_entity AS to_entity
                    ON to_entity.dimensional_entity_id =
                       relationship.dimensional_relationship_to_entity_id
                  JOIN workflow.dimensional_attribute AS source
                    ON source.dimensional_attribute_id =
                       relationship.dimensional_relationship_from_attribute_id
                  JOIN workflow.dimensional_attribute AS target
                    ON target.dimensional_attribute_id =
                       relationship.dimensional_relationship_to_attribute_id
                 WHERE relationship.project_id = %s
                """,
                (project_id,),
            ).fetchone()
        )
        assert relationship == {
            "kind": "fact_dimension",
            "optional": False,
            "role": "ordering_customer",
            "source_surrogate": False,
            "target_surrogate": True,
        }
        columns = connection.execute(
            """
            SELECT table_name, column_name
              FROM information_schema.columns
             WHERE table_schema = 'workflow'
            """
        ).fetchall()
        assert not any(row["column_name"].endswith("confidence") for row in columns)
        attribute_columns = {
            row["column_name"] for row in columns if row["table_name"] == "dimensional_attribute"
        }
        assert {
            "dimensional_attribute_is_natural_key",
            "dimensional_attribute_is_surrogate_key",
            "dimensional_attribute_is_audit_column",
        } <= attribute_columns
        assert (
            not {
                "dimensional_attribute_role",
                "dimensional_attribute_key_role",
                "dimensional_attribute_is_grain_component",
                "dimensional_attribute_additivity",
                "dimensional_attribute_default_aggregation",
                "dimensional_attribute_aggregation_basis",
                "dimensional_attribute_change_behavior",
            }
            & attribute_columns
        )
        assert not any(
            row["table_name"] == "dimensional_entity_source_mapping"
            and row["column_name"] == "dimensional_entity_source_role"
            for row in columns
        )
