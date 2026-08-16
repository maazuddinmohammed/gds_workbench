"""Canonical server-owned Object visibility closure for interactive reads."""

from typing import LiteralString

VISIBLE_OBJECTS_CTE: LiteralString = """
WITH RECURSIVE requested_tenant AS (
    SELECT tenant_id, gds_connection_id
      FROM core.tenant
     WHERE tenant_id = %s
       AND is_active
),
owned_objects AS (
    SELECT object.object_id
      FROM requested_tenant
      JOIN core.connection AS connection
        ON connection.tenant_id = requested_tenant.tenant_id
      JOIN core.object AS object
        ON object.connection_id = connection.connection_id
),
discovery_objects AS (
    SELECT object.object_id
      FROM requested_tenant
      JOIN core.tenant_metadata_discovery_scope AS scope
        ON scope.tenant_id = requested_tenant.tenant_id
       AND scope.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = scope.gds_connection_id
       AND connection.is_active
       AND connection.is_global_data_store
      JOIN reference.zone AS zone
        ON zone.zone_id = scope.zone_id
       AND zone.is_active
       AND zone.zone_code IN ('bronze', 'silver', 'gold')
      JOIN core.object AS object
        ON object.connection_id = scope.gds_connection_id
       AND object.zone_id = scope.zone_id
       AND lower(btrim(object.object_schema)) = lower(btrim(scope.object_schema))
),
copy_objects AS (
    SELECT mapping.source_object_id AS object_id
      FROM requested_tenant
      JOIN core.copy_group AS copy_group
        ON copy_group.tenant_id = requested_tenant.tenant_id
      JOIN core.copy AS copy
        ON copy.copy_group_id = copy_group.copy_group_id
      JOIN core.ingestion_object_mapping AS mapping
        ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
    UNION
    SELECT mapping.target_object_id
      FROM requested_tenant
      JOIN core.copy_group AS copy_group
        ON copy_group.tenant_id = requested_tenant.tenant_id
      JOIN core.copy AS copy
        ON copy.copy_group_id = copy_group.copy_group_id
      JOIN core.ingestion_object_mapping AS mapping
        ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
),
process_objects AS (
    SELECT process.object_id
      FROM requested_tenant
      JOIN core.copy_group AS copy_group
        ON copy_group.tenant_id = requested_tenant.tenant_id
      JOIN core.process_group AS process_group
        ON process_group.copy_group_id = copy_group.copy_group_id
       AND process_group.tenant_id = copy_group.tenant_id
       AND process_group.system_id = copy_group.system_id
      JOIN core.process AS process
        ON process.process_group_id = process_group.process_group_id
),
model_scope_objects AS (
    SELECT scope.object_id
      FROM requested_tenant
      JOIN model.model AS model
        ON model.tenant_id = requested_tenant.tenant_id
       AND model.is_active
      JOIN model.model_scope AS scope
        ON scope.model_id = model.model_id
       AND scope.is_active
),
seed_objects AS (
    SELECT object_id FROM owned_objects
    UNION
    SELECT object_id FROM discovery_objects
    UNION
    SELECT object_id FROM copy_objects
    UNION
    SELECT object_id FROM process_objects
    UNION
    SELECT object_id FROM model_scope_objects
),
connected_objects (object_id) AS (
    SELECT object_id FROM seed_objects
    UNION
    SELECT CASE
               WHEN mapping.source_object_id = connected_objects.object_id
               THEN mapping.target_object_id
               ELSE mapping.source_object_id
           END
      FROM connected_objects
      JOIN core.ingestion_object_mapping AS mapping
        ON mapping.is_active
       AND (
           mapping.source_object_id = connected_objects.object_id
           OR mapping.target_object_id = connected_objects.object_id
       )
),
visible_objects AS (
    SELECT connected_objects.object_id,
           EXISTS (
               SELECT 1 FROM owned_objects
                WHERE owned_objects.object_id = connected_objects.object_id
           ) AS is_owned_by_tenant,
           EXISTS (
               SELECT 1 FROM discovery_objects
                WHERE discovery_objects.object_id = connected_objects.object_id
           ) AS is_discovered_by_scope,
           EXISTS (
               SELECT 1 FROM copy_objects
                WHERE copy_objects.object_id = connected_objects.object_id
           ) AS is_copy_referenced,
           EXISTS (
               SELECT 1 FROM process_objects
                WHERE process_objects.object_id = connected_objects.object_id
           ) AS is_process_referenced,
           EXISTS (
               SELECT 1 FROM model_scope_objects
                WHERE model_scope_objects.object_id = connected_objects.object_id
           ) AS is_model_scope_referenced
      FROM connected_objects
)
"""
