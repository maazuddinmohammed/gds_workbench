"""Paginated physical Object summaries for one authorized Tenant and Zone."""

from __future__ import annotations

from typing import Literal, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE

type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_LIST_OBJECTS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       object.object_schema,
       object.object_name,
       left(object.object_description, 2000) AS object_description,
       object_type.object_type_code,
       object_type.object_type_name,
       zone.zone_code AS zone,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       connection.foreign_catalog,
       connection_tenant.tenant_id AS connection_tenant_id,
       connection_tenant.tenant_code AS connection_tenant_code,
       connection_tenant.tenant_name AS connection_tenant_name,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       system.system_id,
       system.system_code,
       system.system_name,
       (
           SELECT count(*)
             FROM core.attribute
            WHERE attribute.object_id = object.object_id
       ) AS attribute_count,
       EXISTS (
           SELECT 1
             FROM core.ingestion_object_mapping AS mapping
             JOIN visible_objects AS source_visible
               ON source_visible.object_id = mapping.source_object_id
             JOIN visible_objects AS target_visible
               ON target_visible.object_id = mapping.target_object_id
            WHERE mapping.source_object_id = object.object_id
               OR mapping.target_object_id = object.object_id
       ) AS has_ingestion_mapping,
       visible_objects.is_owned_by_tenant,
       visible_objects.is_on_global_connection,
       visible_objects.is_copy_referenced,
       visible_objects.is_process_referenced,
       visible_objects.is_model_input_scope_referenced,
       object.is_active
  FROM visible_objects
  JOIN core.object AS object ON object.object_id = visible_objects.object_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.tenant AS connection_tenant
    ON connection_tenant.tenant_id = connection.tenant_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = object.source_tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
 WHERE zone.zone_code = %s
   AND (%s::BIGINT IS NULL OR connection.connection_id = %s)
   AND (
       %s = 'all'
       OR (%s = 'active' AND object.is_active)
       OR (%s = 'inactive' AND NOT object.is_active)
   )
 ORDER BY lower(object.object_schema), lower(object.object_name), object.object_id
 LIMIT %s OFFSET %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObjectSummary(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_description: str | None = Field(default=None, max_length=2000)
    object_type_code: str = Field(min_length=1, max_length=100)
    object_type_name: str = Field(min_length=1, max_length=200)
    zone: ZoneCode
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    foreign_catalog: str | None = Field(default=None, min_length=1, max_length=400)
    connection_tenant_id: int = Field(gt=0)
    connection_tenant_code: str = Field(min_length=1, max_length=100)
    connection_tenant_name: str = Field(min_length=1, max_length=200)
    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    attribute_count: int = Field(ge=0)
    has_ingestion_mapping: bool
    is_owned_by_tenant: bool
    is_on_global_connection: bool
    is_copy_referenced: bool
    is_process_referenced: bool
    is_model_input_scope_referenced: bool
    is_active: bool
