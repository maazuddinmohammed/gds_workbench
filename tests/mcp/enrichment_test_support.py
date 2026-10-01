"""Seed Model enrichment baselines from synthetic metadata inside disposable fixtures."""

from typing import Any

from psycopg import Connection


def seed_model_enrichment(
    connection: Connection[dict[str, Any]], model_id: int
) -> None:
    # These rows are fixture inputs, not a migration or an application fallback.
    connection.execute(
        """
        INSERT INTO workflow.object_enrichment (model_id, object_id, object_description, is_locked)
        SELECT scope.model_id, object.object_id, object.object_description, object.is_locked
        FROM model.model_input_scope AS scope JOIN core.object AS object USING (object_id)
        WHERE scope.model_id = %s
        ON CONFLICT (model_id, object_id) DO UPDATE SET
            object_description = EXCLUDED.object_description, is_locked = EXCLUDED.is_locked
        """,
        (model_id,),
    )
    connection.execute(
        """
        INSERT INTO workflow.attribute_enrichment (model_id, object_id, attribute_id,
            attribute_description, attribute_inferred_data_type, is_locked)
        SELECT scope.model_id, attribute.object_id, attribute.attribute_id,
            attribute.attribute_description, attribute.attribute_inferred_data_type, attribute.is_locked
        FROM model.model_input_scope AS scope JOIN core.attribute AS attribute USING (object_id)
        WHERE scope.model_id = %s
        ON CONFLICT (model_id, attribute_id) DO UPDATE SET
            attribute_description = EXCLUDED.attribute_description,
            attribute_inferred_data_type = EXCLUDED.attribute_inferred_data_type,
            is_locked = EXCLUDED.is_locked
        """,
        (model_id,),
    )
