"""Seed Project enrichment baselines from synthetic metadata inside disposable fixtures."""

from typing import Any

from psycopg import Connection


def seed_project_enrichment(
    connection: Connection[dict[str, Any]], project_id: int
) -> None:
    # These rows are fixture inputs, not a migration or an application fallback.
    connection.execute(
        """
        INSERT INTO workflow.object_enrichment (project_id, object_id, object_description, is_locked)
        SELECT scope.project_id, object.object_id, object.object_description, object.is_locked
        FROM project.project_input_scope AS scope JOIN core.object AS object USING (object_id)
        WHERE scope.project_id = %s
        ON CONFLICT (project_id, object_id) DO UPDATE SET
            object_description = EXCLUDED.object_description, is_locked = EXCLUDED.is_locked
        """,
        (project_id,),
    )
    connection.execute(
        """
        INSERT INTO workflow.attribute_enrichment (project_id, object_id, attribute_id,
            attribute_description, attribute_inferred_data_type, is_locked)
        SELECT scope.project_id, attribute.object_id, attribute.attribute_id,
            attribute.attribute_description, attribute.attribute_inferred_data_type, attribute.is_locked
        FROM project.project_input_scope AS scope JOIN core.attribute AS attribute USING (object_id)
        WHERE scope.project_id = %s
        ON CONFLICT (project_id, attribute_id) DO UPDATE SET
            attribute_description = EXCLUDED.attribute_description,
            attribute_inferred_data_type = EXCLUDED.attribute_inferred_data_type,
            is_locked = EXCLUDED.is_locked
        """,
        (project_id,),
    )
