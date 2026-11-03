"""Applied Subject Area and membership queries."""

from __future__ import annotations

from typing import LiteralString

SUBJECT_AREAS_SQL: LiteralString = """
SELECT area.subject_area_id,
       area.subject_area_name,
       area.subject_area_definition,
       area.subject_area_is_active,
       area.subject_area_is_locked
  FROM workflow.subject_area AS area
 WHERE area.project_id = %s
 ORDER BY lower(area.subject_area_name), area.subject_area_id
 LIMIT %s OFFSET %s
"""

# Each membership names its Scope table by the placement Tenant, System and Connection,
# like every other physical reference. Only readable Source Tenants' tables appear.
_MEMBERSHIP_SELECT: LiteralString = """
SELECT membership.subject_area_table_id,
       area.subject_area_name,
       placement_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       membership.subject_area_table_is_active,
       membership.subject_area_table_is_locked
  FROM workflow.subject_area_table AS membership
  JOIN project.project AS project
    ON project.project_id = membership.project_id
  JOIN workflow.subject_area AS area
    ON area.subject_area_id = membership.subject_area_id
   AND area.project_id = membership.project_id
  JOIN core.object AS object_record
    ON object_record.object_id = membership.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object_record.connection_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
"""

_MEMBERSHIP_FILTER: LiteralString = """
 WHERE membership.project_id = %s
   AND (
       object_record.source_tenant_id = project.tenant_id
       OR object_record.source_tenant_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(area.subject_area_name),
          lower(placement_tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(object_record.object_schema),
          lower(object_record.object_name),
          membership.subject_area_table_id
 LIMIT %s OFFSET %s
"""

# Complete snapshots keep every owned membership as history, even after its table
# leaves Scope. Params: project_id, readable Source Tenant ids, limit, offset.
SUBJECT_AREA_TABLES_SQL: LiteralString = _MEMBERSHIP_SELECT + _MEMBERSHIP_FILTER

# Focused reads show only tables still in active, eligible Input Scope.
# Params: project_id (twice for the Scope), then the same as above.
CURRENT_SUBJECT_AREA_TABLES_SQL: LiteralString = (
    """
WITH current_scope AS MATERIALIZED (
    SELECT scope.object_id
      FROM project.project_input_scope AS scope
      JOIN workflow.list_project_object_eligibility(%s) AS eligibility
        ON eligibility.object_id = scope.object_id
       AND eligibility.is_project_input_eligible
     WHERE scope.project_id = %s
       AND scope.is_active
)"""
    + _MEMBERSHIP_SELECT
    + """  JOIN current_scope
    ON current_scope.object_id = membership.object_id"""
    + _MEMBERSHIP_FILTER
)
