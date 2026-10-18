"""Applied Context queries for one governed Project."""

from typing import LiteralString

TYPES_SQL: LiteralString = """
SELECT context_type_id, name AS context_type_name,
       description AS context_type_description
  FROM reference.context_type
 ORDER BY lower(name), context_type_id
 LIMIT %s OFFSET %s
"""

GROUPS_SQL: LiteralString = """
SELECT context_group.context_group_id,
       context_group.name AS context_group_name,
       context_type.name AS context_type_name,
       context_group.description AS context_group_description,
       system.system_code AS source_system_code,
       context_group.is_active
  FROM project.context_group
  JOIN reference.context_type USING (context_type_id)
  LEFT JOIN core.system AS system
    ON system.system_id = context_group.source_system_id
 WHERE context_group.project_id = %s
 ORDER BY lower(context_group.name), context_group.context_group_id
 LIMIT %s OFFSET %s
"""

RECORDS_SQL: LiteralString = """
SELECT record.context_record_id::TEXT,
       record.context_group_id,
       context_group.name AS context_group_name,
       record.context_text,
       record.source_reference,
       record.status,
       record.is_locked
  FROM project.context_record AS record
  JOIN project.context_group
    ON context_group.context_group_id = record.context_group_id
   AND context_group.project_id = record.project_id
 WHERE record.project_id = %s
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR record.context_group_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(context_group.name), record.context_record_id
 LIMIT %s OFFSET %s
"""
