"""Fixed, bounded PostgreSQL queries for the complete Metadata catalog."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import LiteralString

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from gds_etl_workbench.tools.catalog.visibility import VISIBLE_OBJECTS_CTE
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS_BY_NAME,
    normalize_natural_key_value,
)

from gds_workbench_api.features.metadata.contracts import (
    MAX_METADATA_EXPORT_ROWS_PER_SHEET,
    METADATA_DATASETS,
    MetadataDataset,
    MetadataFilter,
    ObjectAttribute,
    ObjectCatalogDetail,
    ObjectCatalogFilters,
    ObjectCatalogSummary,
    OperationalDataset,
)

_MAX_DATABASE_ID = 9_223_372_036_854_775_807
_MAX_PAGE_OFFSET = 10_000_000

_SYSTEM_TYPE_ROWS_SQL: LiteralString = """
SELECT system_type.system_type_code,
       system_type.system_type_name,
       system_type.system_type_description,
       system_type.is_active
  FROM reference.system_type AS system_type
 WHERE TRUE
"""

_CONNECTION_TYPE_ROWS_SQL: LiteralString = """
SELECT connection_type.connection_type_code,
       connection_type.connection_type_name,
       connection_type.connection_type_description,
       connection_type.is_active
  FROM reference.connection_type AS connection_type
 WHERE TRUE
"""

_OBJECT_TYPE_ROWS_SQL: LiteralString = """
SELECT object_type.object_type_code,
       object_type.object_type_name,
       object_type.object_type_description,
       object_type.is_active
  FROM reference.object_type AS object_type
 WHERE TRUE
"""

_ZONE_ROWS_SQL: LiteralString = """
SELECT zone.zone_code,
       zone.zone_name,
       zone.zone_description,
       zone.is_active
  FROM reference.zone AS zone
 WHERE TRUE
"""

_CHUNK_TYPE_ROWS_SQL: LiteralString = """
SELECT chunk_type.chunk_type_name,
       chunk_type.chunk_type_description,
       chunk_type.is_active
  FROM reference.chunk_type AS chunk_type
 WHERE TRUE
"""

_FILE_TYPE_ROWS_SQL: LiteralString = """
SELECT file_type.file_type_name,
       file_type.file_type_description,
       file_type.is_active
  FROM reference.file_type AS file_type
 WHERE TRUE
"""

_DATA_OPERATION_ROWS_SQL: LiteralString = """
SELECT data_operation.data_operation_name,
       data_operation.data_operation_description,
       data_operation.is_active
  FROM reference.data_operation AS data_operation
 WHERE TRUE
"""

_PROCESS_TYPE_ROWS_SQL: LiteralString = """
SELECT process_type.process_type_name,
       process_type.process_type_description,
       process_type.is_active
  FROM reference.process_type AS process_type
 WHERE TRUE
"""

_FOUNDATIONAL_CLOSURE_CTE: LiteralString = f"""
{VISIBLE_OBJECTS_CTE},
visible_connection_ids AS (
    SELECT connection.connection_id
      FROM requested_tenant
      JOIN core.connection AS connection
        ON connection.tenant_id = requested_tenant.tenant_id
    UNION
    SELECT object.connection_id
      FROM visible_objects
      JOIN core.object AS object
        ON object.object_id = visible_objects.object_id
    UNION
    SELECT requested_tenant.gds_connection_id
      FROM requested_tenant
     WHERE requested_tenant.gds_connection_id IS NOT NULL
),
visible_tenant_ids AS (
    SELECT requested_tenant.tenant_id
      FROM requested_tenant
    UNION
    SELECT visible_objects.object_tenant_id
      FROM visible_objects
    UNION
    SELECT connection.tenant_id
      FROM visible_connection_ids
      JOIN core.connection AS connection
        ON connection.connection_id = visible_connection_ids.connection_id
),
visible_system_ids AS (
    SELECT connection.system_id
      FROM visible_connection_ids
      JOIN core.connection AS connection
        ON connection.connection_id = visible_connection_ids.connection_id
    UNION
    SELECT copy_group.system_id
      FROM requested_tenant
      JOIN core.copy_group AS copy_group
        ON copy_group.tenant_id = requested_tenant.tenant_id
    UNION
    SELECT member_group.system_id
      FROM requested_tenant
      JOIN core.member_group AS member_group
        ON member_group.tenant_id = requested_tenant.tenant_id
    UNION
    SELECT process_group.system_id
      FROM requested_tenant
      JOIN core.process_group AS process_group
        ON process_group.tenant_id = requested_tenant.tenant_id
),
visible_project_ids AS (
    SELECT DISTINCT tenant.project_id
      FROM visible_tenant_ids
      JOIN core.tenant AS tenant
        ON tenant.tenant_id = visible_tenant_ids.tenant_id
)
"""

_PROJECT_ROWS_SQL: LiteralString = f"""
{_FOUNDATIONAL_CLOSURE_CTE}
SELECT project.project_code,
       project.project_name,
       project.project_description,
       project.is_active
  FROM visible_project_ids
  JOIN core.project AS project
    ON project.project_id = visible_project_ids.project_id
 WHERE TRUE
"""

_TENANT_ROWS_SQL: LiteralString = f"""
{_FOUNDATIONAL_CLOSURE_CTE}
SELECT tenant.tenant_code,
       project.project_code,
       tenant.tenant_name,
       tenant.tenant_description,
       tenant.tenant_catalog,
       tenant.gds_admin_catalog,
       gds_tenant.tenant_code AS gds_connection_tenant_code,
       gds_system.system_code AS gds_connection_system_code,
       gds_connection.connection_code AS gds_connection_code,
       tenant.tenant_visibility,
       tenant.is_active
  FROM visible_tenant_ids
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = visible_tenant_ids.tenant_id
  JOIN core.project AS project
    ON project.project_id = tenant.project_id
  LEFT JOIN core.connection AS gds_connection
    ON gds_connection.connection_id = tenant.gds_connection_id
  LEFT JOIN core.tenant AS gds_tenant
    ON gds_tenant.tenant_id = gds_connection.tenant_id
  LEFT JOIN core.system AS gds_system
    ON gds_system.system_id = gds_connection.system_id
 WHERE TRUE
"""

_SYSTEM_ROWS_SQL: LiteralString = f"""
{_FOUNDATIONAL_CLOSURE_CTE}
SELECT system.system_code,
       system.system_name,
       system.system_description,
       system_type.system_type_code,
       system.is_active
  FROM visible_system_ids
  JOIN core.system AS system
    ON system.system_id = visible_system_ids.system_id
  JOIN reference.system_type AS system_type
    ON system_type.system_type_id = system.system_type_id
 WHERE TRUE
"""

_CONNECTION_ROWS_SQL: LiteralString = f"""
{_FOUNDATIONAL_CLOSURE_CTE}
SELECT tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       connection.connection_name,
       connection_type.connection_type_code,
       connection.has_foreign_catalog,
       connection.foreign_catalog,
       connection.is_global_data_store,
       connection.is_active
  FROM visible_connection_ids
  JOIN core.connection AS connection
    ON connection.connection_id = visible_connection_ids.connection_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN reference.connection_type AS connection_type
    ON connection_type.connection_type_id = connection.connection_type_id
 WHERE TRUE
"""

_OBJECT_ROWS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT placement_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       source_tenant.tenant_code AS source_tenant_code,
       object.object_schema,
       object.object_name,
       object.fc_object_schema,
       object.fc_object_name,
       object.object_transformation,
       object.object_description,
       object.batch_attribute_name,
       object_type.object_type_code,
       zone.zone_code,
       object.is_locked,
       object.is_active
  FROM visible_objects
  JOIN core.object AS object
    ON object.object_id = visible_objects.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = object.source_tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
 WHERE zone.zone_code = %s
"""

_ATTRIBUTE_ROWS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT placement_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       attribute.attribute_name,
       attribute.fc_attribute_name,
       attribute.attribute_ordinal_position,
       attribute.attribute_description,
       attribute.attribute_data_type,
       attribute.attribute_nullability,
       attribute.attribute_custom_code,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
       attribute.is_active
  FROM core.attribute AS attribute
  JOIN core.object AS object
    ON object.object_id = attribute.object_id
  JOIN visible_objects
    ON visible_objects.object_id = object.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
 WHERE zone.zone_code = %s
"""

_INGESTION_OBJECT_MAPPING_ROWS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT source_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       target_tenant.tenant_code AS target_tenant_code,
       target_system.system_code AS target_system_code,
       target_connection.connection_code AS target_connection_code,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       mapping.is_active
  FROM core.ingestion_object_mapping AS mapping
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object
    ON source_object.object_id = mapping.source_object_id
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_connection.tenant_id
  JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.target_object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
 WHERE TRUE
"""

_INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT source_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_attribute.attribute_name AS source_attribute_name,
       target_tenant.tenant_code AS target_tenant_code,
       target_system.system_code AS target_system_code,
       target_connection.connection_code AS target_connection_code,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       target_attribute.attribute_name AS target_attribute_name,
       mapping.is_active
  FROM core.ingestion_attribute_mapping AS mapping
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object
    ON source_object.object_id = mapping.source_object_id
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_connection.tenant_id
  JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  JOIN core.attribute AS source_attribute
    ON source_attribute.attribute_id = mapping.source_attribute_id
   AND source_attribute.object_id = source_object.object_id
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.target_object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN core.attribute AS target_attribute
    ON target_attribute.attribute_id = mapping.target_attribute_id
   AND target_attribute.object_id = target_object.object_id
 WHERE TRUE
"""

_COPY_GROUP_ROWS_SQL: LiteralString = """
SELECT tenant.tenant_code,
       system.system_code,
       copy_group.copy_group_name,
       copy_group.copy_group_description,
       copy_group.is_member_group_required,
       copy_group.is_active
  FROM core.copy_group AS copy_group
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = copy_group.tenant_id
  JOIN core.system AS system
    ON system.system_id = copy_group.system_id
 WHERE copy_group.tenant_id = %s
"""

_MEMBER_GROUP_ROWS_SQL: LiteralString = """
SELECT tenant.tenant_code,
       system.system_code,
       member_group.member_group_name,
       member_group.member_group_description,
       member_group.member_group_initial_load_date,
       member_group.is_active
  FROM core.member_group AS member_group
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = member_group.tenant_id
  JOIN core.system AS system
    ON system.system_id = member_group.system_id
 WHERE member_group.tenant_id = %s
"""

_COPY_GROUP_CONTROL_ROWS_SQL: LiteralString = """
SELECT tenant.tenant_code,
       system.system_code,
       copy_group.copy_group_name,
       member_group.member_group_name,
       control.copy_group_control_initial_load_date,
       control.copy_group_control_last_run_time,
       control.copy_group_control_last_run_value
  FROM core.copy_group_control AS control
  JOIN core.copy_group AS copy_group
    ON copy_group.copy_group_id = control.copy_group_id
   AND copy_group.tenant_id = control.tenant_id
   AND copy_group.system_id = control.system_id
  LEFT JOIN core.member_group AS member_group
    ON member_group.member_group_id = control.member_group_id
   AND member_group.tenant_id = control.tenant_id
   AND member_group.system_id = control.system_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = control.tenant_id
  JOIN core.system AS system
    ON system.system_id = control.system_id
 WHERE control.tenant_id = %s
"""

_COPY_ROWS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT tenant.tenant_code,
       copy_system.system_code,
       copy_group.copy_group_name,
       source_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       target_tenant.tenant_code AS target_tenant_code,
       target_system.system_code AS target_system_code,
       target_connection.connection_code AS target_connection_code,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       copy.copy_source_record_limit::TEXT AS copy_source_record_limit,
       copy.copy_source_record_limit_attribute,
       chunk_type.chunk_type_name,
       copy.copy_source_initial_sql_script,
       copy.copy_source_incremental_sql_script,
       copy.copy_source_file_name,
       copy.copy_source_file_pattern,
       copy.copy_source_file_delimiter,
       file_type.file_type_name AS source_file_type_name,
       copy.copy_source_order,
       source_operation.data_operation_name AS source_data_operation_name,
       target_operation.data_operation_name AS target_data_operation_name,
       copy.is_active
  FROM core.copy AS copy
  JOIN core.copy_group AS copy_group
    ON copy_group.copy_group_id = copy.copy_group_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = copy_group.tenant_id
  JOIN core.system AS copy_system
    ON copy_system.system_id = copy_group.system_id
  JOIN core.ingestion_object_mapping AS mapping
    ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object
    ON source_object.object_id = mapping.source_object_id
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_connection.tenant_id
  JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.target_object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  LEFT JOIN reference.chunk_type AS chunk_type
    ON chunk_type.chunk_type_id = copy.chunk_type_id
  LEFT JOIN reference.file_type AS file_type
    ON file_type.file_type_id = copy.source_file_type_id
  JOIN reference.data_operation AS source_operation
    ON source_operation.data_operation_id = copy.source_data_operation_id
  JOIN reference.data_operation AS target_operation
    ON target_operation.data_operation_id = copy.target_data_operation_id
 WHERE copy_group.tenant_id = (SELECT tenant_id FROM requested_tenant)
"""

_PROCESS_GROUP_ROWS_SQL: LiteralString = """
SELECT tenant.tenant_code,
       system.system_code,
       zone.zone_code,
       process_group.process_group_name,
       process_group.process_group_description,
       copy_group.copy_group_name,
       process_group.is_active
  FROM core.process_group AS process_group
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = process_group.tenant_id
  JOIN core.system AS system
    ON system.system_id = process_group.system_id
  JOIN reference.zone AS zone
    ON zone.zone_id = process_group.zone_id
  JOIN core.copy_group AS copy_group
    ON copy_group.copy_group_id = process_group.copy_group_id
   AND copy_group.tenant_id = process_group.tenant_id
   AND copy_group.system_id = process_group.system_id
 WHERE process_group.tenant_id = %s
"""

_PROCESS_ROWS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT tenant.tenant_code,
       system.system_code,
       zone.zone_code,
       process_group.process_group_name,
       process.process_execution_order,
       process.process_location,
       process.process_executable,
       object_tenant.tenant_code AS object_tenant_code,
       object_system.system_code AS object_system_code,
       object_connection.connection_code AS object_connection_code,
       object.object_schema,
       object.object_name,
       process_type.process_type_name,
       process.is_active
  FROM core.process AS process
  JOIN core.process_group AS process_group
    ON process_group.process_group_id = process.process_group_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = process_group.tenant_id
  JOIN core.system AS system
    ON system.system_id = process_group.system_id
  JOIN reference.zone AS zone
    ON zone.zone_id = process_group.zone_id
  JOIN core.object AS object
    ON object.object_id = process.object_id
   AND object.connection_id = process.connection_id
  JOIN visible_objects
    ON visible_objects.object_id = object.object_id
  JOIN core.connection AS object_connection
    ON object_connection.connection_id = object.connection_id
  JOIN core.tenant AS object_tenant
    ON object_tenant.tenant_id = object_connection.tenant_id
  JOIN core.system AS object_system
    ON object_system.system_id = object_connection.system_id
  JOIN reference.process_type AS process_type
    ON process_type.process_type_id = process.process_type_id
 WHERE process_group.tenant_id = (SELECT tenant_id FROM requested_tenant)
"""

_OBJECT_LIST_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       object.object_schema,
       object.object_name,
       object_type.object_type_code,
       zone.zone_code,
       connection.connection_id,
       connection.connection_code,
       system.system_id,
       system.system_code,
       system.system_name,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       (
           SELECT count(*)::INTEGER
             FROM core.attribute AS attribute
            WHERE attribute.object_id = object.object_id
       ) AS attribute_count,
       object.batch_attribute_name,
       object.is_active
  FROM visible_objects
  JOIN core.object AS object
    ON object.object_id = visible_objects.object_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible_objects.object_tenant_id
 WHERE (%s::TEXT IS NULL OR lower(btrim(zone.zone_code)) = %s)
   AND (%s::TEXT IS NULL OR lower(btrim(system.system_code)) = %s)
   AND (%s::TEXT IS NULL OR lower(btrim(source_tenant.tenant_code)) = %s)
   AND (%s = 'all' OR object.is_active = (%s = 'active'))
 ORDER BY object.object_id
LIMIT %s OFFSET %s
"""

_OBJECT_DETAIL_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       object.object_schema,
       object.object_name,
       object_type.object_type_code,
       object_type.object_type_name,
       left(object.object_description, 2000) AS object_description,
       zone.zone_code,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       system.system_id,
       system.system_code,
       system.system_name,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       (
           SELECT count(*)::INTEGER
             FROM core.attribute AS attribute
            WHERE attribute.object_id = object.object_id
       ) AS attribute_count,
       object.batch_attribute_name,
       object.is_locked,
       object.is_active
  FROM visible_objects
  JOIN core.object AS object
    ON object.object_id = visible_objects.object_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible_objects.object_tenant_id
 WHERE object.object_id = %s
"""

_OBJECT_ATTRIBUTES_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT attribute.attribute_id,
       attribute.attribute_name,
       attribute.attribute_ordinal_position,
       left(attribute.attribute_description, 2000) AS attribute_description,
       attribute.attribute_data_type,
       attribute.attribute_nullability,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
       attribute.is_active
  FROM visible_objects
  JOIN core.attribute AS attribute
    ON attribute.object_id = visible_objects.object_id
 WHERE visible_objects.object_id = %s
 ORDER BY attribute.attribute_ordinal_position,
          attribute.attribute_id
 LIMIT %s
"""

_OBJECT_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "tenant_code": "lower(btrim(placement_tenant.tenant_code))",
    "system_code": "lower(btrim(system.system_code))",
    "connection_code": "lower(btrim(connection.connection_code))",
    "object_schema": "lower(btrim(object.object_schema))",
    "object_name": "lower(btrim(object.object_name))",
    "object_type_code": "lower(btrim(object_type.object_type_code))",
    "zone_code": "lower(btrim(zone.zone_code))",
    "source_tenant_code": "lower(btrim(source_tenant.tenant_code))",
    "is_locked": "object.is_locked",
    "is_active": "object.is_active",
}
_ATTRIBUTE_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "tenant_code": "lower(btrim(placement_tenant.tenant_code))",
    "system_code": "lower(btrim(system.system_code))",
    "connection_code": "lower(btrim(connection.connection_code))",
    "object_schema": "lower(btrim(object.object_schema))",
    "object_name": "lower(btrim(object.object_name))",
    "attribute_name": "lower(btrim(attribute.attribute_name))",
    "attribute_data_type": "attribute.attribute_data_type",
    "is_natural_key": "attribute.is_natural_key",
    "is_active": "attribute.is_active",
}
_INGESTION_OBJECT_MAPPING_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "source_tenant_code": "lower(btrim(source_tenant.tenant_code))",
    "source_system_code": "lower(btrim(source_system.system_code))",
    "source_connection_code": "lower(btrim(source_connection.connection_code))",
    "source_object_schema": "lower(btrim(source_object.object_schema))",
    "source_object_name": "lower(btrim(source_object.object_name))",
    "target_tenant_code": "lower(btrim(target_tenant.tenant_code))",
    "target_system_code": "lower(btrim(target_system.system_code))",
    "target_connection_code": "lower(btrim(target_connection.connection_code))",
    "target_object_schema": "lower(btrim(target_object.object_schema))",
    "target_object_name": "lower(btrim(target_object.object_name))",
}
_INGESTION_ATTRIBUTE_MAPPING_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    **_INGESTION_OBJECT_MAPPING_FILTER_EXPRESSIONS,
    "source_attribute_name": "lower(btrim(source_attribute.attribute_name))",
    "target_attribute_name": "lower(btrim(target_attribute.attribute_name))",
}
_COPY_GROUP_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "tenant_code": "lower(btrim(tenant.tenant_code))",
    "system_code": "lower(btrim(system.system_code))",
    "copy_group_name": "lower(btrim(copy_group.copy_group_name))",
}
_MEMBER_GROUP_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "tenant_code": "lower(btrim(tenant.tenant_code))",
    "system_code": "lower(btrim(system.system_code))",
    "member_group_name": "lower(btrim(member_group.member_group_name))",
}
_COPY_GROUP_CONTROL_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    **_COPY_GROUP_FILTER_EXPRESSIONS,
    "member_group_name": "lower(btrim(member_group.member_group_name))",
    "copy_group_control_last_run_time": "control.copy_group_control_last_run_time",
}
_COPY_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "tenant_code": "lower(btrim(tenant.tenant_code))",
    "system_code": "lower(btrim(copy_system.system_code))",
    "copy_group_name": "lower(btrim(copy_group.copy_group_name))",
    **_INGESTION_OBJECT_MAPPING_FILTER_EXPRESSIONS,
    "copy_source_order": "copy.copy_source_order",
    "is_active": "copy.is_active",
}
_PROCESS_GROUP_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    "tenant_code": "lower(btrim(tenant.tenant_code))",
    "system_code": "lower(btrim(system.system_code))",
    "zone_code": "lower(btrim(zone.zone_code))",
    "process_group_name": "lower(btrim(process_group.process_group_name))",
}
_PROCESS_FILTER_EXPRESSIONS: dict[str, LiteralString] = {
    **_PROCESS_GROUP_FILTER_EXPRESSIONS,
    "process_execution_order": "process.process_execution_order",
    "process_location": "process.process_location",
    "process_executable": "process.process_executable",
}


@dataclass(frozen=True, slots=True)
class _DatasetQuery:
    sql: LiteralString
    filter_expressions: Mapping[str, LiteralString]
    order_expression: LiteralString
    fixed_parameters: tuple[object, ...] = ()
    tenant_scoped: bool = True


_DATASET_QUERIES: Mapping[MetadataDataset, _DatasetQuery] = MappingProxyType(
    {
        "project": _DatasetQuery(
            _PROJECT_ROWS_SQL,
            {"project_code": "lower(btrim(project.project_code))"},
            "project.project_id",
        ),
        "tenant": _DatasetQuery(
            _TENANT_ROWS_SQL,
            {"tenant_code": "lower(btrim(tenant.tenant_code))"},
            "tenant.tenant_id",
        ),
        "system": _DatasetQuery(
            _SYSTEM_ROWS_SQL,
            {"system_code": "lower(btrim(system.system_code))"},
            "system.system_id",
        ),
        "connection": _DatasetQuery(
            _CONNECTION_ROWS_SQL,
            {
                "tenant_code": "lower(btrim(tenant.tenant_code))",
                "system_code": "lower(btrim(system.system_code))",
                "connection_code": "lower(btrim(connection.connection_code))",
            },
            "connection.connection_id",
        ),
        "system_type": _DatasetQuery(
            _SYSTEM_TYPE_ROWS_SQL,
            {"system_type_code": "lower(btrim(system_type.system_type_code))"},
            "system_type.system_type_id",
            tenant_scoped=False,
        ),
        "connection_type": _DatasetQuery(
            _CONNECTION_TYPE_ROWS_SQL,
            {"connection_type_code": ("lower(btrim(connection_type.connection_type_code))")},
            "connection_type.connection_type_id",
            tenant_scoped=False,
        ),
        "object_type": _DatasetQuery(
            _OBJECT_TYPE_ROWS_SQL,
            {"object_type_code": "lower(btrim(object_type.object_type_code))"},
            "object_type.object_type_id",
            tenant_scoped=False,
        ),
        "zone": _DatasetQuery(
            _ZONE_ROWS_SQL,
            {"zone_code": "lower(btrim(zone.zone_code))"},
            "zone.zone_id",
            tenant_scoped=False,
        ),
        "chunk_type": _DatasetQuery(
            _CHUNK_TYPE_ROWS_SQL,
            {"chunk_type_name": "lower(btrim(chunk_type.chunk_type_name))"},
            "chunk_type.chunk_type_id",
            tenant_scoped=False,
        ),
        "file_type": _DatasetQuery(
            _FILE_TYPE_ROWS_SQL,
            {"file_type_name": "lower(btrim(file_type.file_type_name))"},
            "file_type.file_type_id",
            tenant_scoped=False,
        ),
        "data_operation": _DatasetQuery(
            _DATA_OPERATION_ROWS_SQL,
            {"data_operation_name": ("lower(btrim(data_operation.data_operation_name))")},
            "data_operation.data_operation_id",
            tenant_scoped=False,
        ),
        "process_type": _DatasetQuery(
            _PROCESS_TYPE_ROWS_SQL,
            {"process_type_name": "lower(btrim(process_type.process_type_name))"},
            "process_type.process_type_id",
            tenant_scoped=False,
        ),
        "source_object": _DatasetQuery(
            _OBJECT_ROWS_SQL,
            _OBJECT_FILTER_EXPRESSIONS,
            "object.object_id",
            ("source",),
        ),
        "source_attribute": _DatasetQuery(
            _ATTRIBUTE_ROWS_SQL,
            _ATTRIBUTE_FILTER_EXPRESSIONS,
            "attribute.attribute_id",
            ("source",),
        ),
        "bronze_object": _DatasetQuery(
            _OBJECT_ROWS_SQL,
            _OBJECT_FILTER_EXPRESSIONS,
            "object.object_id",
            ("bronze",),
        ),
        "bronze_attribute": _DatasetQuery(
            _ATTRIBUTE_ROWS_SQL,
            _ATTRIBUTE_FILTER_EXPRESSIONS,
            "attribute.attribute_id",
            ("bronze",),
        ),
        "silver_object": _DatasetQuery(
            _OBJECT_ROWS_SQL,
            _OBJECT_FILTER_EXPRESSIONS,
            "object.object_id",
            ("silver",),
        ),
        "silver_attribute": _DatasetQuery(
            _ATTRIBUTE_ROWS_SQL,
            _ATTRIBUTE_FILTER_EXPRESSIONS,
            "attribute.attribute_id",
            ("silver",),
        ),
        "gold_object": _DatasetQuery(
            _OBJECT_ROWS_SQL,
            _OBJECT_FILTER_EXPRESSIONS,
            "object.object_id",
            ("gold",),
        ),
        "gold_attribute": _DatasetQuery(
            _ATTRIBUTE_ROWS_SQL,
            _ATTRIBUTE_FILTER_EXPRESSIONS,
            "attribute.attribute_id",
            ("gold",),
        ),
        "ingestion_object_mapping": _DatasetQuery(
            _INGESTION_OBJECT_MAPPING_ROWS_SQL,
            _INGESTION_OBJECT_MAPPING_FILTER_EXPRESSIONS,
            "mapping.ingestion_object_mapping_id",
        ),
        "ingestion_attribute_mapping": _DatasetQuery(
            _INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL,
            _INGESTION_ATTRIBUTE_MAPPING_FILTER_EXPRESSIONS,
            "mapping.ingestion_attribute_mapping_id",
        ),
        "copy_group": _DatasetQuery(
            _COPY_GROUP_ROWS_SQL,
            _COPY_GROUP_FILTER_EXPRESSIONS,
            "copy_group.copy_group_id",
        ),
        "member_group": _DatasetQuery(
            _MEMBER_GROUP_ROWS_SQL,
            _MEMBER_GROUP_FILTER_EXPRESSIONS,
            "member_group.member_group_id",
        ),
        "copy_group_control": _DatasetQuery(
            _COPY_GROUP_CONTROL_ROWS_SQL,
            _COPY_GROUP_CONTROL_FILTER_EXPRESSIONS,
            "control.copy_group_control_id",
        ),
        "copy": _DatasetQuery(
            _COPY_ROWS_SQL,
            _COPY_FILTER_EXPRESSIONS,
            "copy.copy_id",
        ),
        "process_group": _DatasetQuery(
            _PROCESS_GROUP_ROWS_SQL,
            _PROCESS_GROUP_FILTER_EXPRESSIONS,
            "process_group.process_group_id",
        ),
        "process": _DatasetQuery(
            _PROCESS_ROWS_SQL,
            _PROCESS_FILTER_EXPRESSIONS,
            "process.process_id",
        ),
    }
)

if tuple(_DATASET_QUERIES) != METADATA_DATASETS:
    raise RuntimeError("web Metadata query registry is incomplete")


class PostgresMetadataRepository:
    """Read only from the closed 28-dataset Metadata query registry."""

    async def list_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        filters: tuple[MetadataFilter, ...],
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]:
        if (
            not 1 <= tenant_id <= _MAX_DATABASE_ID
            or not 1 <= limit <= 201
            or not 0 <= offset <= _MAX_PAGE_OFFSET
        ):
            raise InvalidRequestError("Metadata row paging is invalid.")
        definition = _DATASET_QUERIES.get(dataset)
        if definition is None:
            raise InvalidRequestError("Metadata dataset is not available.")
        query = definition.sql
        parameters = (
            (tenant_id, *definition.fixed_parameters)
            if definition.tenant_scoped
            else definition.fixed_parameters
        )
        filter_fields = tuple(filter_.field for filter_ in filters)
        allowed_fields = DATASETS_BY_NAME[dataset].search_fields
        if (
            filter_fields != tuple(sorted(filter_fields))
            or len(set(filter_fields)) != len(filter_fields)
            or any(field not in allowed_fields for field in filter_fields)
            or any(
                filter_.value != normalize_natural_key_value(filter_.field, filter_.value)
                for filter_ in filters
            )
        ):
            raise InvalidRequestError("Metadata filters do not match the selected dataset.")

        for filter_ in filters:
            expression = definition.filter_expressions.get(filter_.field)
            if expression is None:
                raise InvalidRequestError("Metadata filters do not match the selected dataset.")
            query += f" AND {expression} IS NOT DISTINCT FROM %s\n"
            parameters += (filter_.value,)
        query += f" ORDER BY {definition.order_expression}\n LIMIT %s OFFSET %s\n"
        return await transaction.fetch_all(
            query,
            (*parameters, limit, offset),
        )

    async def list_export_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: OperationalDataset,
        limit: int,
    ) -> Sequence[Mapping[str, object]]:
        if not 1 <= tenant_id <= _MAX_DATABASE_ID or not (
            1 <= limit <= MAX_METADATA_EXPORT_ROWS_PER_SHEET + 1
        ):
            raise InvalidRequestError("Metadata workbook row request is invalid.")
        definition = _DATASET_QUERIES.get(dataset)
        if definition is None:
            raise InvalidRequestError("Metadata dataset is not available.")
        query = definition.sql
        query += f" ORDER BY {definition.order_expression}\n LIMIT %s\n"
        return await transaction.fetch_all(
            query,
            (tenant_id, *definition.fixed_parameters, limit),
        )

    async def list_objects(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        filters: ObjectCatalogFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ObjectCatalogSummary]:
        if (
            not 1 <= tenant_id <= _MAX_DATABASE_ID
            or not 1 <= limit <= 201
            or not 0 <= offset <= _MAX_PAGE_OFFSET
        ):
            raise InvalidRequestError("Metadata Object paging is invalid.")
        parameters = (
            tenant_id,
            filters.zone,
            filters.zone,
            filters.system_code,
            filters.system_code,
            filters.source_tenant_code,
            filters.source_tenant_code,
            filters.active_state,
            filters.active_state,
            limit,
            offset,
        )
        rows = await transaction.fetch_all(_OBJECT_LIST_SQL, parameters)
        return tuple(ObjectCatalogSummary.model_validate(row, strict=True) for row in rows)

    async def get_object(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        object_id: int,
    ) -> ObjectCatalogDetail | None:
        if not 1 <= tenant_id <= _MAX_DATABASE_ID or not (1 <= object_id <= _MAX_DATABASE_ID):
            raise InvalidRequestError("Metadata Object lookup is invalid.")
        row = await transaction.fetch_one(
            _OBJECT_DETAIL_SQL,
            (tenant_id, object_id),
        )
        if row is None:
            return None
        attribute_count = row.get("attribute_count")
        if (
            isinstance(attribute_count, bool)
            or not isinstance(attribute_count, int)
            or not 0 <= attribute_count <= 2000
        ):
            raise InvalidRequestError("Metadata Object has too many Attributes.")
        attribute_rows = await transaction.fetch_all(
            _OBJECT_ATTRIBUTES_SQL,
            (tenant_id, object_id, 2001),
        )
        if len(attribute_rows) > 2000:
            raise InvalidRequestError("Metadata Object has too many Attributes.")
        attributes = tuple(
            ObjectAttribute.model_validate(attribute, strict=True) for attribute in attribute_rows
        )
        return ObjectCatalogDetail.model_validate(
            {**row, "attributes": attributes},
            strict=True,
        )
