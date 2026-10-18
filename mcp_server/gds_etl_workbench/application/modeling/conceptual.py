"""Applied Conceptual Object and Relationship queries."""

from __future__ import annotations

from typing import LiteralString

_ELIGIBLE_OBJECTS_CTE = """
WITH requested_project AS (
    SELECT %s::BIGINT AS project_id
),
eligible_objects AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_project
      CROSS JOIN LATERAL workflow.list_project_object_eligibility(
          requested_project.project_id
      ) AS eligibility
)
"""

# Complete snapshots retain owned inactive supports; workflow inputs stay eligible.
_HISTORICAL_OBJECTS_CTE = """
WITH requested_project AS (
    SELECT %s::BIGINT AS project_id
),
eligible_objects AS MATERIALIZED (
    SELECT project.project_id, object.object_id, TRUE AS is_project_input_eligible
      FROM requested_project
      JOIN project.project AS project USING (project_id)
      JOIN core.object AS object ON object.source_tenant_id = project.tenant_id
        OR (object.source_tenant_id = ANY(%s::BIGINT[])
            AND EXISTS (SELECT 1 FROM project.project_input_scope AS retained_scope
                         WHERE retained_scope.project_id = project.project_id
                           AND retained_scope.object_id = object.object_id))
)
"""

_SUPPORT_JSON_SQL = """
COALESCE((
    SELECT jsonb_agg(
               CASE support.support_source_type
                   WHEN 'object' THEN jsonb_build_object(
                       'conceptual_support_id', support.conceptual_support_id,
                       'support_source_type', 'object',
                       'source_object', jsonb_build_object(
                           'object_id', source_object.object_id,
                           'tenant_code', source_tenant.tenant_code,
                           'system_code', source_system.system_code,
                           'connection_code', source_connection.connection_code,
                           'object_schema', source_object.object_schema,
                           'object_name', source_object.object_name
                       ),
                       'support_role', support.conceptual_support_role,
                       'support_reason', support.conceptual_support_reason,
                       'support_reason_detail', support.conceptual_support_reason_detail,
                       'support_confidence', support.conceptual_support_confidence,
                       'support_status', support.conceptual_support_status,
                       'support_is_locked', support.conceptual_support_is_locked
                   )
                   ELSE jsonb_build_object(
                       'conceptual_support_id', support.conceptual_support_id,
                       'support_source_type', 'context_record',
                       'context_record', jsonb_build_object(
                           'context_record_id',
                               context_record.context_record_id
                       ),
                       'support_role', support.conceptual_support_role,
                       'support_reason', support.conceptual_support_reason,
                       'support_reason_detail', support.conceptual_support_reason_detail,
                       'support_confidence', support.conceptual_support_confidence,
                       'support_status', support.conceptual_support_status,
                       'support_is_locked', support.conceptual_support_is_locked
                   )
               END
               ORDER BY support.conceptual_support_id
           )
      FROM workflow.conceptual_support AS support
      LEFT JOIN core.object AS source_object
        ON source_object.object_id = support.source_object_id
      LEFT JOIN core.connection AS source_connection
        ON source_connection.connection_id = source_object.connection_id
      LEFT JOIN eligible_objects AS source_eligibility
        ON source_eligibility.object_id = support.source_object_id
       AND source_eligibility.project_id = support.project_id
       AND source_eligibility.is_project_input_eligible
      LEFT JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = source_connection.tenant_id
      LEFT JOIN core.system AS source_system
        ON source_system.system_id = source_connection.system_id
      LEFT JOIN project.context_record AS context_record
        ON context_record.context_record_id = support.context_record_id
       AND context_record.project_id = support.project_id
     WHERE support.project_id = parent.project_id
       AND support.supported_artifact_type = '{supported_artifact_type}'
       AND support.{parent_id_column} = parent.{parent_id_column}
       AND (
           support.support_source_type <> 'object'
           OR EXISTS (
               SELECT 1
                 FROM eligible_objects AS eligibility
                WHERE eligibility.object_id = support.source_object_id
                  AND eligibility.project_id = support.project_id
                  AND eligibility.is_project_input_eligible
           )
       )
), '[]'::JSONB) AS supports
"""

_CONCEPTUAL_OBJECTS_SELECT_SQL: LiteralString = f"""
SELECT parent.conceptual_object_id,
       parent.conceptual_object_name,
       parent.conceptual_object_definition,
       parent.conceptual_object_type,
       parent.conceptual_object_grain,
       parent.conceptual_object_aliases,
       parent.conceptual_object_confidence,
       parent.conceptual_object_status,
       parent.conceptual_object_is_locked,
       {
    _SUPPORT_JSON_SQL.format(
        supported_artifact_type="conceptual_object",
        parent_id_column="conceptual_object_id",
    )
}
  FROM workflow.conceptual_object AS parent
 WHERE parent.project_id = (SELECT project_id FROM requested_project)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR EXISTS (
           SELECT 1
             FROM workflow.conceptual_support AS selected_support
            WHERE selected_support.project_id = parent.project_id
              AND selected_support.conceptual_object_id = parent.conceptual_object_id
              AND selected_support.support_source_type = 'object'
              AND selected_support.source_object_id = ANY(%s::BIGINT[])
              AND EXISTS (
                  SELECT 1
                    FROM eligible_objects AS eligibility
                   WHERE eligibility.object_id = selected_support.source_object_id
                     AND eligibility.project_id = selected_support.project_id
                     AND eligibility.is_project_input_eligible
              )
       )
   )
 ORDER BY lower(parent.conceptual_object_name), parent.conceptual_object_id
 LIMIT %s OFFSET %s
"""

_CONCEPTUAL_RELATIONSHIPS_SELECT_SQL: LiteralString = f"""
SELECT parent.conceptual_relationship_id,
       parent.from_conceptual_object_id,
       from_object.conceptual_object_name AS from_conceptual_object_name,
       parent.to_conceptual_object_id,
       to_object.conceptual_object_name AS to_conceptual_object_name,
       parent.conceptual_relationship_name,
       parent.conceptual_relationship_type,
       parent.conceptual_relationship_definition,
       parent.conceptual_relationship_cardinality,
       parent.conceptual_relationship_basis,
       parent.conceptual_relationship_cardinality_basis,
       parent.conceptual_relationship_confidence,
       parent.conceptual_relationship_status,
       parent.conceptual_relationship_is_locked,
       {
    _SUPPORT_JSON_SQL.format(
        supported_artifact_type="conceptual_relationship",
        parent_id_column="conceptual_relationship_id",
    )
}
  FROM workflow.conceptual_relationship AS parent
  JOIN workflow.conceptual_object AS from_object
    ON from_object.conceptual_object_id = parent.from_conceptual_object_id
   AND from_object.project_id = parent.project_id
  JOIN workflow.conceptual_object AS to_object
    ON to_object.conceptual_object_id = parent.to_conceptual_object_id
   AND to_object.project_id = parent.project_id
 WHERE parent.project_id = (SELECT project_id FROM requested_project)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR parent.from_conceptual_object_id = ANY(%s::BIGINT[])
       OR parent.to_conceptual_object_id = ANY(%s::BIGINT[])
   )
 ORDER BY parent.from_conceptual_object_id,
          parent.to_conceptual_object_id,
          lower(parent.conceptual_relationship_name),
          parent.conceptual_relationship_id
 LIMIT %s OFFSET %s
"""

CONCEPTUAL_OBJECTS_SQL: LiteralString = _ELIGIBLE_OBJECTS_CTE + _CONCEPTUAL_OBJECTS_SELECT_SQL
CONCEPTUAL_RELATIONSHIPS_SQL: LiteralString = (
    _ELIGIBLE_OBJECTS_CTE + _CONCEPTUAL_RELATIONSHIPS_SELECT_SQL
)
HISTORICAL_CONCEPTUAL_OBJECTS_SQL: LiteralString = (
    _HISTORICAL_OBJECTS_CTE + _CONCEPTUAL_OBJECTS_SELECT_SQL
)
HISTORICAL_CONCEPTUAL_RELATIONSHIPS_SQL: LiteralString = (
    _HISTORICAL_OBJECTS_CTE + _CONCEPTUAL_RELATIONSHIPS_SELECT_SQL
)
