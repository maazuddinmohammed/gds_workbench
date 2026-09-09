"""Process Group query contracts and row mapping."""

# The focused metadata reader reuses the private row mapper.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE

type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_LIST_SQL: LiteralString = """
SELECT process_group.process_group_id,
       process_group.process_group_name,
       left(process_group.process_group_description, 2000)
           AS process_group_description,
       process_group.copy_group_id,
       copy_group.copy_group_name,
       system.system_id,
       system.system_code,
       system.system_name,
       zone.zone_code AS declared_zone,
       process_group.is_active,
       (SELECT count(*) FROM core.process
         WHERE process.process_group_id = process_group.process_group_id)
           AS process_count
  FROM core.copy_group
  JOIN core.process_group
    ON process_group.copy_group_id = copy_group.copy_group_id
   AND process_group.tenant_id = copy_group.tenant_id
   AND process_group.system_id = copy_group.system_id
  JOIN core.system ON system.system_id = process_group.system_id
  JOIN reference.zone ON zone.zone_id = process_group.zone_id
 WHERE copy_group.tenant_id = %s
   AND (%s::BIGINT IS NULL OR process_group.system_id = %s)
   AND (%s::VARCHAR IS NULL OR zone.zone_code = %s)
   AND (
       %s = 'all'
       OR (%s = 'active' AND process_group.is_active)
       OR (%s = 'inactive' AND NOT process_group.is_active)
   )
 ORDER BY lower(process_group.process_group_name), process_group.process_group_id
 LIMIT %s OFFSET %s
"""

_GROUP_SQL: LiteralString = """
SELECT process_group.process_group_id,
       process_group.process_group_name,
       left(process_group.process_group_description, 2000)
           AS process_group_description,
       process_group.copy_group_id,
       copy_group.copy_group_name,
       system.system_id,
       system.system_code,
       system.system_name,
       zone.zone_code AS declared_zone,
       process_group.is_active,
       (SELECT count(*) FROM core.process
         WHERE process.process_group_id = process_group.process_group_id)
           AS process_count
  FROM core.copy_group
  JOIN core.process_group
    ON process_group.copy_group_id = copy_group.copy_group_id
   AND process_group.tenant_id = copy_group.tenant_id
   AND process_group.system_id = copy_group.system_id
  JOIN core.system ON system.system_id = process_group.system_id
  JOIN reference.zone ON zone.zone_id = process_group.zone_id
 WHERE copy_group.tenant_id = %s
   AND process_group.process_group_id = %s
"""

_PROCESSES_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT process.process_id,
       process.process_execution_order,
       process.is_active,
       process_type.process_type_name,
       object.object_id,
       object.object_schema,
       object.object_name,
       object_zone.zone_code AS zone,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_name AS source_tenant_name
  FROM core.copy_group
  JOIN core.process_group
    ON process_group.copy_group_id = copy_group.copy_group_id
   AND process_group.tenant_id = copy_group.tenant_id
   AND process_group.system_id = copy_group.system_id
  JOIN core.process ON process.process_group_id = process_group.process_group_id
  JOIN visible_objects
    ON visible_objects.object_id = process.object_id
  JOIN reference.process_type ON process_type.process_type_id = process.process_type_id
  JOIN core.object
    ON object.object_id = process.object_id
   AND object.connection_id = process.connection_id
  JOIN reference.zone AS object_zone ON object_zone.zone_id = object.zone_id
  JOIN core.connection ON connection.connection_id = process.connection_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible_objects.object_tenant_id
 WHERE copy_group.tenant_id = (SELECT tenant_id FROM requested_tenant)
   AND process_group.process_group_id = %s
 ORDER BY process.process_execution_order, process.process_id
 LIMIT 501
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProcessGroupSummary(ContractModel):
    process_group_id: int = Field(gt=0)
    process_group_name: str = Field(min_length=1, max_length=200)
    process_group_description: str | None = Field(default=None, max_length=2000)
    copy_group_id: int = Field(gt=0)
    copy_group_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    declared_zone: ZoneCode
    process_count: int = Field(ge=0)
    is_active: bool


class ProcessObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: ZoneCode
    source_tenant_id: int = Field(gt=0)
    source_tenant_name: str = Field(min_length=1, max_length=200)


class ProcessDetails(ContractModel):
    process_id: int = Field(gt=0)
    process_execution_order: int = Field(gt=0)
    process_type_name: str = Field(min_length=1, max_length=200)
    object: ProcessObjectReference
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    is_active: bool


def _process(row: Mapping[str, Any]) -> ProcessDetails:
    return ProcessDetails(
        process_id=row["process_id"],
        process_execution_order=row["process_execution_order"],
        process_type_name=row["process_type_name"],
        object=ProcessObjectReference(
            object_id=row["object_id"],
            object_schema=row["object_schema"],
            object_name=row["object_name"],
            zone=row["zone"],
            source_tenant_id=row["source_tenant_id"],
            source_tenant_name=row["source_tenant_name"],
        ),
        connection_id=row["connection_id"],
        connection_code=row["connection_code"],
        connection_name=row["connection_name"],
        is_active=row["is_active"],
    )
