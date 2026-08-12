"""Fixed, parameterized SQL for Metadata Snapshot selection."""

from typing import LiteralString

OBJECT_CLOSURE_SQL: LiteralString = """
WITH RECURSIVE requested_tenant AS (
    SELECT tenant_id
      FROM core.tenant
     WHERE tenant_id = %s
       AND is_active
),
active_scope_config AS (
    SELECT scope.tenant_metadata_discovery_scope_id,
           scope.connection_id,
           scope.zone_id,
           scope.object_schema,
           connection.is_active AS connection_is_active,
           connection.is_global_data_store,
           zone.zone_code,
           zone.is_active AS zone_is_active
      FROM requested_tenant
      JOIN core.tenant_metadata_discovery_scope AS scope
        ON scope.tenant_id = requested_tenant.tenant_id
       AND scope.is_active
      LEFT JOIN core.connection AS connection
        ON connection.connection_id = scope.connection_id
      LEFT JOIN reference.zone AS zone
        ON zone.zone_id = scope.zone_id
),
invalid_scope_config AS (
    SELECT 1
      FROM active_scope_config
     WHERE connection_is_active IS DISTINCT FROM TRUE
        OR is_global_data_store IS DISTINCT FROM TRUE
        OR zone_is_active IS DISTINCT FROM TRUE
        OR zone_code NOT IN ('bronze', 'silver', 'gold')
     LIMIT 1
),
valid_scope_config AS (
    SELECT connection_id, zone_id, object_schema
      FROM active_scope_config
     WHERE connection_is_active
       AND is_global_data_store
       AND zone_is_active
       AND zone_code IN ('bronze', 'silver', 'gold')
),
owned_objects AS (
    SELECT object.object_id
      FROM requested_tenant
      JOIN core.connection AS connection
        ON connection.tenant_id = requested_tenant.tenant_id
      JOIN core.object AS object
        ON object.connection_id = connection.connection_id
),
scope_objects AS (
    SELECT object.object_id
      FROM valid_scope_config AS scope
      JOIN core.object AS object
        ON object.connection_id = scope.connection_id
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
      JOIN core.process_group AS process_group
        ON process_group.tenant_id = requested_tenant.tenant_id
      JOIN core.process AS process
        ON process.process_group_id = process_group.process_group_id
),
model_scope_objects AS (
    SELECT model_scope.object_id
      FROM requested_tenant
      JOIN model.model AS model
        ON model.tenant_id = requested_tenant.tenant_id
       AND model.is_active
      JOIN model.model_scope AS model_scope
        ON model_scope.model_id = model.model_id
),
seed_objects AS (
    SELECT object_id FROM owned_objects
    UNION
    SELECT object_id FROM scope_objects
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
)
SELECT requested_tenant.tenant_id,
       connected_objects.object_id,
       zone.zone_code AS snapshot_zone_code,
       zone.is_active AS snapshot_zone_is_active,
       EXISTS (SELECT 1 FROM invalid_scope_config) AS invalid_discovery_scope
  FROM requested_tenant
  LEFT JOIN connected_objects ON TRUE
  LEFT JOIN core.object AS object
    ON object.object_id = connected_objects.object_id
  LEFT JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
 ORDER BY connected_objects.object_id
"""

OBJECT_ROWS_SQL: LiteralString = """
SELECT object_id,
       connection_id,
       object_schema,
       object_name,
       fc_object_schema,
       fc_object_name,
       object_transformation,
       object_description,
       batch_attribute_name,
       object_type_id,
       zone_id,
       is_locked,
       is_active
  FROM core.object
 WHERE object_id = ANY(%s::BIGINT[])
 ORDER BY object_id
"""

ATTRIBUTE_ROWS_SQL: LiteralString = """
SELECT attribute_id,
       object_id,
       attribute_name,
       fc_attribute_name,
       attribute_ordinal_position,
       attribute_description,
       attribute_data_type,
       attribute_nullability,
       attribute_custom_code,
       is_surrogate_key,
       is_natural_key,
       is_meta_data,
       is_masking_required,
       is_mapped,
       is_purge,
       is_locked,
       is_active
  FROM core.attribute
 WHERE object_id = ANY(%s::BIGINT[])
 ORDER BY attribute_id
"""


INGESTION_OBJECT_MAPPING_ROWS_SQL: LiteralString = """
SELECT ingestion_object_mapping_id,
       source_object_id,
       target_object_id,
       is_active
  FROM core.ingestion_object_mapping
 WHERE source_object_id = ANY(%s::BIGINT[])
   AND target_object_id = ANY(%s::BIGINT[])
 ORDER BY ingestion_object_mapping_id
"""

INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL: LiteralString = """
SELECT ingestion_attribute_mapping_id,
       ingestion_object_mapping_id,
       source_object_id,
       target_object_id,
       source_attribute_id,
       target_attribute_id,
       is_active
  FROM core.ingestion_attribute_mapping
 WHERE ingestion_object_mapping_id = ANY(%s::BIGINT[])
 ORDER BY ingestion_attribute_mapping_id
"""

COPY_GROUP_ROWS_SQL: LiteralString = """
SELECT copy_group_id,
       tenant_id,
       system_id,
       copy_group_name,
       copy_group_description,
       is_member_group_required,
       is_active
  FROM core.copy_group
 WHERE tenant_id = %s
 ORDER BY copy_group_id
"""

MEMBER_GROUP_ROWS_SQL: LiteralString = """
SELECT member_group_id,
       tenant_id,
       system_id,
       member_group_name,
       member_group_description,
       member_group_initial_load_date,
       is_active
  FROM core.member_group
 WHERE tenant_id = %s
 ORDER BY member_group_id
"""

COPY_GROUP_CONTROL_ROWS_SQL: LiteralString = """
SELECT copy_group_control_id,
       copy_group_id,
       member_group_id,
       tenant_id,
       system_id,
       copy_group_control_initial_load_date,
       copy_group_control_last_run_time,
       copy_group_control_last_run_value
  FROM core.copy_group_control
 WHERE tenant_id = %s
 ORDER BY copy_group_control_id
"""

COPY_ROWS_SQL: LiteralString = """
SELECT copy.copy_id,
       copy.copy_group_id,
       copy.ingestion_object_mapping_id,
       copy.copy_source_record_limit,
       copy.copy_source_record_limit_attribute,
       copy.chunk_type_id,
       copy.copy_source_initial_sql_script,
       copy.copy_source_incremental_sql_script,
       copy.copy_source_file_name,
       copy.copy_source_file_pattern,
       copy.copy_source_file_delimiter,
       copy.source_file_type_id,
       copy.copy_source_order,
       copy.source_data_operation_id,
       copy.target_data_operation_id,
       copy.is_active
  FROM core.copy AS copy
  JOIN core.copy_group AS copy_group
    ON copy_group.copy_group_id = copy.copy_group_id
 WHERE copy_group.tenant_id = %s
 ORDER BY copy.copy_id
"""

PROCESS_GROUP_ROWS_SQL: LiteralString = """
SELECT process_group_id,
       tenant_id,
       system_id,
       zone_id,
       process_group_name,
       process_group_description,
       copy_group_id,
       is_active
  FROM core.process_group
 WHERE tenant_id = %s
 ORDER BY process_group_id
"""

PROCESS_ROWS_SQL: LiteralString = """
SELECT process.process_id,
       process.connection_id,
       process.object_id,
       process.process_execution_order,
       process.process_location,
       process.process_executable,
       process.process_type_id,
       process.process_group_id,
       process.is_active
  FROM core.process AS process
  JOIN core.process_group AS process_group
    ON process_group.process_group_id = process.process_group_id
 WHERE process_group.tenant_id = %s
 ORDER BY process.process_id
"""


DISCOVERY_SCOPE_ROWS_SQL: LiteralString = """
SELECT tenant_metadata_discovery_scope_id,
       tenant_id,
       connection_id,
       zone_id,
       object_schema,
       is_active
  FROM core.tenant_metadata_discovery_scope
 WHERE tenant_id = %s
 ORDER BY tenant_metadata_discovery_scope_id
"""

FOUNDATION_CONNECTION_ROWS_SQL: LiteralString = """
SELECT connection.connection_id,
       connection.tenant_id,
       connection.system_id,
       connection.connection_code,
       connection.connection_name,
       connection.connection_type_id,
       connection.has_foreign_catalog,
       connection.foreign_catalog,
       connection.is_global_data_store,
       connection.is_active
  FROM core.connection AS connection
 WHERE connection.tenant_id = %s
    OR connection.connection_id = ANY(%s::BIGINT[])
    OR connection.connection_id = (
           SELECT tenant.gds_connection_id
             FROM core.tenant AS tenant
            WHERE tenant.tenant_id = %s
       )
 ORDER BY connection.connection_id
"""

FOUNDATION_TENANT_ROWS_SQL: LiteralString = """
SELECT tenant_id,
       project_id,
       tenant_code,
       tenant_name,
       tenant_description,
       tenant_catalog,
       gds_admin_catalog,
       gds_connection_id,
       tenant_visibility,
       is_active
  FROM core.tenant
 WHERE tenant_id = %s
    OR tenant_id = ANY(%s::BIGINT[])
 ORDER BY tenant_id
"""

FOUNDATION_PROJECT_ROWS_SQL: LiteralString = """
SELECT project_id,
       project_code,
       project_name,
       project_description,
       is_active
  FROM core.project
 WHERE project_id = ANY(%s::BIGINT[])
 ORDER BY project_id
"""

FOUNDATION_SYSTEM_ROWS_SQL: LiteralString = """
SELECT system_id,
       system_code,
       system_name,
       system_description,
       system_type_id,
       is_active
  FROM core.system
 WHERE system_id = ANY(%s::BIGINT[])
 ORDER BY system_id
"""

SYSTEM_TYPE_ROWS_SQL: LiteralString = """
SELECT system_type_id,
       system_type_code,
       system_type_name,
       system_type_description,
       is_active
  FROM reference.system_type
 ORDER BY system_type_id
"""

CONNECTION_TYPE_ROWS_SQL: LiteralString = """
SELECT connection_type_id,
       connection_type_code,
       connection_type_name,
       connection_type_description,
       is_active
  FROM reference.connection_type
 ORDER BY connection_type_id
"""

OBJECT_TYPE_ROWS_SQL: LiteralString = """
SELECT object_type_id,
       object_type_code,
       object_type_name,
       object_type_description,
       is_active
  FROM reference.object_type
 ORDER BY object_type_id
"""

ZONE_ROWS_SQL: LiteralString = """
SELECT zone_id,
       zone_code,
       zone_name,
       zone_description,
       is_active
  FROM reference.zone
 ORDER BY zone_id
"""

CHUNK_TYPE_ROWS_SQL: LiteralString = """
SELECT chunk_type_id,
       chunk_type_name,
       chunk_type_description,
       is_active
  FROM reference.chunk_type
 ORDER BY chunk_type_id
"""

FILE_TYPE_ROWS_SQL: LiteralString = """
SELECT file_type_id,
       file_type_name,
       file_type_description,
       is_active
  FROM reference.file_type
 ORDER BY file_type_id
"""

DATA_OPERATION_ROWS_SQL: LiteralString = """
SELECT data_operation_id,
       data_operation_name,
       data_operation_description,
       is_active
  FROM reference.data_operation
 ORDER BY data_operation_id
"""

PROCESS_TYPE_ROWS_SQL: LiteralString = """
SELECT process_type_id,
       process_type_name,
       process_type_description,
       is_active
  FROM reference.process_type
 ORDER BY process_type_id
"""

REFERENCE_ROWS_SQL: dict[str, LiteralString] = {
    "system_type": SYSTEM_TYPE_ROWS_SQL,
    "connection_type": CONNECTION_TYPE_ROWS_SQL,
    "object_type": OBJECT_TYPE_ROWS_SQL,
    "zone": ZONE_ROWS_SQL,
    "chunk_type": CHUNK_TYPE_ROWS_SQL,
    "file_type": FILE_TYPE_ROWS_SQL,
    "data_operation": DATA_OPERATION_ROWS_SQL,
    "process_type": PROCESS_TYPE_ROWS_SQL,
}
