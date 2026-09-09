"""Tenant-owned Copy Group query contracts and row mapping."""

# The focused metadata reader reuses the private row mapper.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE

type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_LIST_SQL: LiteralString = """
SELECT copy_group.copy_group_id,
       copy_group.copy_group_name,
       left(copy_group.copy_group_description, 2000) AS copy_group_description,
       copy_group.is_member_group_required,
       copy_group.is_active,
       system.system_id,
       system.system_code,
       system.system_name,
       (SELECT count(*) FROM core.copy
         WHERE copy.copy_group_id = copy_group.copy_group_id) AS copy_count,
       (SELECT count(*) FROM core.copy_group_control AS control
         WHERE control.copy_group_id = copy_group.copy_group_id) AS control_count,
       (SELECT count(*) FROM core.process_group
         WHERE process_group.copy_group_id = copy_group.copy_group_id
           AND process_group.tenant_id = copy_group.tenant_id
           AND process_group.system_id = copy_group.system_id) AS process_group_count
  FROM core.copy_group
  JOIN core.system ON system.system_id = copy_group.system_id
 WHERE copy_group.tenant_id = %s
   AND (%s::BIGINT IS NULL OR copy_group.system_id = %s)
   AND (
       %s = 'all'
       OR (%s = 'active' AND copy_group.is_active)
       OR (%s = 'inactive' AND NOT copy_group.is_active)
   )
 ORDER BY lower(copy_group.copy_group_name), copy_group.copy_group_id
 LIMIT %s OFFSET %s
"""

_GROUP_SQL: LiteralString = """
SELECT copy_group.copy_group_id,
       copy_group.copy_group_name,
       left(copy_group.copy_group_description, 2000) AS copy_group_description,
       copy_group.is_member_group_required,
       copy_group.is_active,
       system.system_id,
       system.system_code,
       system.system_name,
       (SELECT count(*) FROM core.copy
         WHERE copy.copy_group_id = copy_group.copy_group_id) AS copy_count,
       (SELECT count(*) FROM core.copy_group_control AS control
         WHERE control.copy_group_id = copy_group.copy_group_id) AS control_count,
       (SELECT count(*) FROM core.process_group
         WHERE process_group.copy_group_id = copy_group.copy_group_id
           AND process_group.tenant_id = copy_group.tenant_id
           AND process_group.system_id = copy_group.system_id) AS process_group_count
  FROM core.copy_group
  JOIN core.system ON system.system_id = copy_group.system_id
 WHERE copy_group.tenant_id = %s
   AND copy_group.copy_group_id = %s
"""

_COPIES_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT copy.copy_id,
       copy.copy_source_order,
       copy.copy_source_record_limit,
       copy.copy_source_record_limit_attribute,
       chunk_type.chunk_type_name,
       file_type.file_type_name,
       source_operation.data_operation_name AS source_data_operation_name,
       target_operation.data_operation_name AS target_data_operation_name,
       copy.copy_source_initial_sql_script IS NOT NULL AS has_initial_sql,
       copy.copy_source_incremental_sql_script IS NOT NULL AS has_incremental_sql,
       copy.copy_source_file_name IS NOT NULL AS has_file_source,
       copy.is_active,
       mapping.ingestion_object_mapping_id,
       source_object.object_id AS source_object_id,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_zone.zone_code AS source_zone,
       target_object.object_id AS target_object_id,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       target_zone.zone_code AS target_zone
  FROM core.copy
  JOIN core.copy_group
    ON copy_group.copy_group_id = copy.copy_group_id
   AND copy_group.tenant_id = %s
   AND copy_group.copy_group_id = %s
  JOIN core.ingestion_object_mapping AS mapping
    ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object ON source_object.object_id = mapping.source_object_id
  JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
  JOIN core.object AS target_object ON target_object.object_id = mapping.target_object_id
  JOIN reference.zone AS target_zone ON target_zone.zone_id = target_object.zone_id
  LEFT JOIN reference.chunk_type ON chunk_type.chunk_type_id = copy.chunk_type_id
  LEFT JOIN reference.file_type ON file_type.file_type_id = copy.source_file_type_id
  JOIN reference.data_operation AS source_operation
    ON source_operation.data_operation_id = copy.source_data_operation_id
  JOIN reference.data_operation AS target_operation
    ON target_operation.data_operation_id = copy.target_data_operation_id
 ORDER BY copy.copy_source_order, copy.copy_id
 LIMIT 201
"""

_CONTROLS_SQL: LiteralString = """
SELECT control.copy_group_control_id,
       control.member_group_id,
       member_group.member_group_name,
       left(member_group.member_group_description, 2000) AS member_group_description,
       member_group.member_group_initial_load_date,
       member_group.is_active AS member_group_is_active,
       control.copy_group_control_initial_load_date,
       control.copy_group_control_last_run_time,
       control.copy_group_control_last_run_value IS NOT NULL AS has_last_run_value
  FROM core.copy_group_control AS control
  JOIN core.copy_group
    ON copy_group.copy_group_id = control.copy_group_id
   AND copy_group.tenant_id = control.tenant_id
   AND copy_group.system_id = control.system_id
  LEFT JOIN core.member_group
    ON member_group.member_group_id = control.member_group_id
   AND member_group.tenant_id = control.tenant_id
   AND member_group.system_id = control.system_id
 WHERE copy_group.tenant_id = %s
   AND copy_group.copy_group_id = %s
 ORDER BY control.copy_group_control_id
 LIMIT 201
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CopyGroupSummary(ContractModel):
    copy_group_id: int = Field(gt=0)
    copy_group_name: str = Field(min_length=1, max_length=200)
    copy_group_description: str | None = Field(default=None, max_length=2000)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    is_member_group_required: bool
    copy_count: int = Field(ge=0)
    control_count: int = Field(ge=0)
    process_group_count: int = Field(ge=0)
    is_active: bool


class CopyObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: ZoneCode


class CopyDetails(ContractModel):
    copy_id: int = Field(gt=0)
    copy_source_order: int = Field(gt=0)
    ingestion_object_mapping_id: int = Field(gt=0)
    source_object: CopyObjectReference
    target_object: CopyObjectReference
    copy_source_record_limit: int | None = Field(default=None, ge=0)
    copy_source_record_limit_attribute: str | None = Field(default=None, max_length=400)
    chunk_type_name: str | None = Field(default=None, max_length=200)
    file_type_name: str | None = Field(default=None, max_length=200)
    source_data_operation_name: str = Field(min_length=1, max_length=200)
    target_data_operation_name: str = Field(min_length=1, max_length=200)
    has_initial_sql: bool
    has_incremental_sql: bool
    has_file_source: bool
    is_active: bool


class CopyGroupControlDetails(ContractModel):
    copy_group_control_id: int = Field(gt=0)
    member_group_id: int | None = Field(default=None, gt=0)
    member_group_name: str | None = Field(default=None, max_length=200)
    member_group_description: str | None = Field(default=None, max_length=2000)
    member_group_initial_load_date: date | None
    member_group_is_active: bool | None
    copy_group_control_initial_load_date: date | None
    copy_group_control_last_run_time: datetime | None
    has_last_run_value: bool


def _copy(row: Mapping[str, Any]) -> CopyDetails:
    return CopyDetails(
        copy_id=row["copy_id"],
        copy_source_order=row["copy_source_order"],
        ingestion_object_mapping_id=row["ingestion_object_mapping_id"],
        source_object=_copy_object(row, prefix="source"),
        target_object=_copy_object(row, prefix="target"),
        copy_source_record_limit=row["copy_source_record_limit"],
        copy_source_record_limit_attribute=row["copy_source_record_limit_attribute"],
        chunk_type_name=row["chunk_type_name"],
        file_type_name=row["file_type_name"],
        source_data_operation_name=row["source_data_operation_name"],
        target_data_operation_name=row["target_data_operation_name"],
        has_initial_sql=row["has_initial_sql"],
        has_incremental_sql=row["has_incremental_sql"],
        has_file_source=row["has_file_source"],
        is_active=row["is_active"],
    )


def _copy_object(
    row: Mapping[str, Any], *, prefix: Literal["source", "target"]
) -> CopyObjectReference:
    return CopyObjectReference(
        object_id=row[f"{prefix}_object_id"],
        object_schema=row[f"{prefix}_object_schema"],
        object_name=row[f"{prefix}_object_name"],
        zone=row[f"{prefix}_zone"],
    )
