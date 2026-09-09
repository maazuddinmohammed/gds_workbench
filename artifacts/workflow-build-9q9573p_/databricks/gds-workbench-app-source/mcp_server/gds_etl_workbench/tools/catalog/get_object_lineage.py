"""Direct configured ingestion lineage for one authorized physical Object."""

# The focused metadata reader reuses the private row mapper.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE

type EdgeDirection = Literal["upstream", "downstream"]
type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_LINEAGE_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT mapping.ingestion_object_mapping_id,
       mapping.is_active,
       CASE
           WHEN mapping.target_object_id = %s THEN 'upstream'
           ELSE 'downstream'
       END AS direction,
       source_object.object_id AS source_object_id,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_zone.zone_code AS source_zone,
       source_connection.connection_id AS source_connection_id,
       source_connection.connection_name AS source_connection_name,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_name AS source_tenant_name,
       target_object.object_id AS target_object_id,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       target_zone.zone_code AS target_zone,
       target_connection.connection_id AS target_connection_id,
       target_connection.connection_name AS target_connection_name,
       target_tenant.tenant_id AS target_tenant_id,
       target_tenant.tenant_name AS target_tenant_name,
       (
           SELECT count(*)
             FROM core.ingestion_attribute_mapping AS attribute_mapping
            WHERE attribute_mapping.ingestion_object_mapping_id =
                  mapping.ingestion_object_mapping_id
       ) AS attribute_mapping_count,
       (
           SELECT count(*)
             FROM core.copy
             JOIN core.copy_group
               ON copy_group.copy_group_id = copy.copy_group_id
            WHERE copy.ingestion_object_mapping_id = mapping.ingestion_object_mapping_id
              AND copy_group.tenant_id = (
                  SELECT requested_tenant.tenant_id FROM requested_tenant
              )
       ) AS copy_count
  FROM core.ingestion_object_mapping AS mapping
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object
    ON source_object.object_id = mapping.source_object_id
  JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_visible.object_tenant_id
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.target_object_id
  JOIN reference.zone AS target_zone ON target_zone.zone_id = target_object.zone_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_visible.object_tenant_id
 WHERE (
       (%s IN ('upstream', 'both') AND mapping.target_object_id = %s)
       OR (%s IN ('downstream', 'both') AND mapping.source_object_id = %s)
   )
 ORDER BY mapping.ingestion_object_mapping_id
 LIMIT 501
"""

_OBJECT_VISIBLE_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT EXISTS (
    SELECT 1 FROM visible_objects WHERE visible_objects.object_id = %s
) AS is_visible
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LineageObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: ZoneCode
    connection_id: int = Field(gt=0)
    connection_name: str = Field(min_length=1, max_length=200)
    source_tenant_id: int = Field(gt=0)
    source_tenant_name: str = Field(min_length=1, max_length=200)


class IngestionMappingSummary(ContractModel):
    ingestion_object_mapping_id: int = Field(gt=0)
    direction: EdgeDirection
    source_object: LineageObjectReference
    target_object: LineageObjectReference
    attribute_mapping_count: int = Field(ge=0)
    copy_count: int = Field(ge=0)
    is_active: bool


def _mapping(row: Mapping[str, Any]) -> IngestionMappingSummary:
    return IngestionMappingSummary(
        ingestion_object_mapping_id=row["ingestion_object_mapping_id"],
        direction=row["direction"],
        source_object=_object_reference(row, prefix="source"),
        target_object=_object_reference(row, prefix="target"),
        attribute_mapping_count=row["attribute_mapping_count"],
        copy_count=row["copy_count"],
        is_active=row["is_active"],
    )


def _object_reference(
    row: Mapping[str, Any], *, prefix: Literal["source", "target"]
) -> LineageObjectReference:
    return LineageObjectReference(
        object_id=row[f"{prefix}_object_id"],
        object_schema=row[f"{prefix}_object_schema"],
        object_name=row[f"{prefix}_object_name"],
        zone=row[f"{prefix}_zone"],
        connection_id=row[f"{prefix}_connection_id"],
        connection_name=row[f"{prefix}_connection_name"],
        source_tenant_id=row[f"{prefix}_tenant_id"],
        source_tenant_name=row[f"{prefix}_tenant_name"],
    )
