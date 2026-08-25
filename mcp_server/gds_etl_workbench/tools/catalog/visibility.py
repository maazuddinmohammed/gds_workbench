"""Canonical server-owned Object visibility closure for interactive reads."""

from typing import LiteralString

VISIBLE_OBJECTS_CTE: LiteralString = """
WITH RECURSIVE requested_tenant AS (
    SELECT tenant_id, gds_connection_id
      FROM core.tenant
     WHERE tenant_id = %s
       AND is_active
),
visible_objects AS (
    SELECT visible_object.*
      FROM requested_tenant
      CROSS JOIN LATERAL workflow.list_tenant_visible_objects(
          requested_tenant.tenant_id
      ) AS visible_object
)
"""
