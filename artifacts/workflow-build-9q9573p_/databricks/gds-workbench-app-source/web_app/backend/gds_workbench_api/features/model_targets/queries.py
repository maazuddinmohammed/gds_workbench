"""Shared, read-only target placement and current Binding lookups."""

from typing import LiteralString

from .contracts import TargetLayer

TARGETS_FROM: LiteralString = """
  FROM core.object AS object
  JOIN core.connection AS connection ON connection.connection_id = object.connection_id
  JOIN core.tenant AS owner ON owner.gds_connection_id = connection.connection_id
  JOIN core.tenant AS placement ON placement.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
 WHERE owner.tenant_id = %s AND object.source_tenant_id = %s
   AND owner.is_active AND connection.is_active AND connection.is_global_data_store
   AND placement.is_active AND system.is_active AND object.is_active
   AND zone.is_active
"""

BINDING_ENTITIES_SQL: dict[TargetLayer, LiteralString] = {
    "logical": """
SELECT entity.logical_entity_id AS entity_id, entity.logical_entity_name AS entity_name,
       binding.model_object_binding_id AS binding_id, binding.object_id,
       object.object_schema, object.object_name,
       coalesce(binding.model_object_binding_is_locked, FALSE) AS is_locked
  FROM workflow.logical_entity AS entity
  LEFT JOIN workflow.model_object_binding AS binding ON binding.model_id = entity.model_id
       AND binding.logical_entity_id = entity.logical_entity_id
       AND binding.model_object_binding_status = 'active'
  LEFT JOIN core.object AS object ON object.object_id = binding.object_id
 WHERE entity.model_id = %s AND entity.logical_entity_status = 'active'
   AND entity.logical_entity_id > %s
 ORDER BY entity.logical_entity_id LIMIT 201
""",
}
BINDING_ENTITIES_SQL["dimensional"] = BINDING_ENTITIES_SQL["logical"].replace(
    "logical", "dimensional"
)
