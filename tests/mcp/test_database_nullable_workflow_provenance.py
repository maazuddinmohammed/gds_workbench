from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

from tests.mcp.database_test_support import require_row
from psycopg import Connection

if TYPE_CHECKING:
    from conftest import DisposablePostgres, TestRow


DATABASE_ROOT = Path(__file__).resolve().parents[2] / "database"


def _seed_demo_if_needed(connection: Connection[TestRow]) -> None:
    exists = connection.execute(
        "SELECT 1 FROM core.project WHERE project_code = 'DEMO_PROJECT'"
    ).fetchone()
    if exists is None:
        connection.execute(
            cast(
                LiteralString,
                (DATABASE_ROOT / "seed" / "01_metadata_snapshot_demo.sql").read_text(
                    encoding="utf-8"
                ),
            )
        )


def test_direct_model_writes_do_not_require_workflow_provenance(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant_id = require_row(
            connection.execute(
                "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
            ).fetchone()
        )["tenant_id"]
        model_id = require_row(
            connection.execute(
                """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, 'Nullable Workflow Provenance Model')
            RETURNING model_id
            """,
                (tenant_id,),
            ).fetchone()
        )["model_id"]
        bronze = connection.execute(
            """
            SELECT object.object_id,
                   array_agg(
                       attribute.attribute_id
                       ORDER BY attribute.attribute_ordinal_position
                   ) AS attribute_ids
              FROM core.object AS object
              JOIN core.attribute AS attribute
                ON attribute.object_id = object.object_id
             WHERE object.object_schema = 'bronze_demo'
             GROUP BY object.object_id
            """
        ).fetchone()
        silver = connection.execute(
            """
            SELECT object.object_id, connection.system_id
              FROM core.object AS object
              JOIN core.connection AS connection
                ON connection.connection_id = object.connection_id
             WHERE object.object_schema = 'silver_demo'
            """
        ).fetchone()
        assert bronze is not None
        assert silver is not None
        assert len(bronze["attribute_ids"]) >= 2
        connection.execute(
            """
            INSERT INTO model.model_scope (model_id, object_id)
            VALUES (%s, %s), (%s, %s)
            """,
            (model_id, bronze["object_id"], model_id, silver["object_id"]),
        )

        analysis_result_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.analysis_result (
                model_id,
                agent_run_id,
                inference_workflow_run_id,
                validation_workflow_run_id,
                from_object_id,
                from_attribute_id,
                to_object_id,
                to_attribute_id,
                relationship_kind,
                relationship_basis
            )
            VALUES (%s, NULL, NULL, NULL, %s, %s, %s, %s,
                    'reference', 'Direct MCP-authored relationship evidence.')
            RETURNING analysis_result_id
            """,
                (
                    model_id,
                    bronze["object_id"],
                    bronze["attribute_ids"][0],
                    bronze["object_id"],
                    bronze["attribute_ids"][1],
                ),
            ).fetchone()
        )["analysis_result_id"]
        conceptual_object_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.conceptual_object (
                model_id,
                agent_run_id,
                workflow_run_id,
                conceptual_object_name,
                conceptual_object_definition,
                conceptual_object_type,
                conceptual_object_grain
            )
            VALUES (%s, NULL, NULL, 'Customer', 'A customer concept.',
                    'business_object', 'One customer')
            RETURNING conceptual_object_id
            """,
                (model_id,),
            ).fetchone()
        )["conceptual_object_id"]
        logical_entity_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.logical_entity (
                model_id,
                agent_run_id,
                workflow_run_id,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            )
            VALUES (%s, NULL, NULL, 'customer', 'A logical customer.',
                    'core', 'One customer')
            RETURNING logical_entity_id
            """,
                (model_id,),
            ).fetchone()
        )["logical_entity_id"]
        dimensional_entity_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.dimensional_entity (
                model_id,
                agent_run_id,
                workflow_run_id,
                dimensional_entity_name,
                dimensional_entity_definition,
                dimensional_entity_type
            )
            VALUES (%s, NULL, NULL, 'dim_customer',
                    'A reusable customer Dimension.', 'dimension')
            RETURNING dimensional_entity_id
            """,
                (model_id,),
            ).fetchone()
        )["dimensional_entity_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id,
                agent_run_id,
                workflow_run_id,
                modeled_entity_type,
                source_system_id
            )
            VALUES (%s, NULL, NULL, 'logical_entity', %s)
            """,
            (model_id, silver["system_id"]),
        )
        mapping_object_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.mapping_object (
                model_id,
                agent_run_id,
                workflow_run_id,
                object_id,
                source_system_id,
                modeled_entity_type,
                logical_entity_id
            )
            VALUES (%s, NULL, NULL, %s, %s, 'logical_entity', %s)
            RETURNING mapping_object_id
            """,
                (
                    model_id,
                    silver["object_id"],
                    silver["system_id"],
                    logical_entity_id,
                ),
            ).fetchone()
        )["mapping_object_id"]

        provenance = connection.execute(
            """
            SELECT 'analysis' AS artifact_type,
                   agent_run_id,
                   inference_workflow_run_id AS workflow_run_id,
                   validation_workflow_run_id
              FROM workflow.analysis_result
             WHERE analysis_result_id = %s
            UNION ALL
            SELECT 'conceptual', agent_run_id, workflow_run_id, NULL
              FROM workflow.conceptual_object
             WHERE conceptual_object_id = %s
            UNION ALL
            SELECT 'logical', agent_run_id, workflow_run_id, NULL
              FROM workflow.logical_entity
             WHERE logical_entity_id = %s
            UNION ALL
            SELECT 'dimensional', agent_run_id, workflow_run_id, NULL
              FROM workflow.dimensional_entity
             WHERE dimensional_entity_id = %s
            UNION ALL
            SELECT 'mapping', agent_run_id, workflow_run_id, NULL
              FROM workflow.mapping_object
             WHERE mapping_object_id = %s
            ORDER BY artifact_type
            """,
            (
                analysis_result_id,
                conceptual_object_id,
                logical_entity_id,
                dimensional_entity_id,
                mapping_object_id,
            ),
        ).fetchall()

    assert [row["artifact_type"] for row in provenance] == [
        "analysis",
        "conceptual",
        "dimensional",
        "logical",
        "mapping",
    ]
    assert all(row["agent_run_id"] is None for row in provenance)
    assert all(row["workflow_run_id"] is None for row in provenance)
    assert all(row["validation_workflow_run_id"] is None for row in provenance)
