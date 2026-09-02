"""Bounded batch Object and Attribute details for one authorized Tenant."""

from __future__ import annotations

from typing import Literal, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from .visibility import VISIBLE_OBJECTS_CTE

type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_OBJECTS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       object.object_schema,
       object.object_name,
       object.fc_object_schema,
       object.fc_object_name,
       left(object.object_description, 2000) AS object_description,
       object.object_type_id,
       object_type.object_type_code,
       object_type.object_type_name,
       zone.zone_code AS zone,
       object.batch_attribute_name,
       object.is_locked,
       object.is_active,
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
       system.system_name
  FROM unnest(%s::BIGINT[]) WITH ORDINALITY AS requested(object_id, ordinal)
  JOIN visible_objects ON visible_objects.object_id = requested.object_id
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
 ORDER BY requested.ordinal
"""

_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.attribute_id,
       attribute.object_id,
       attribute.attribute_name,
       attribute.fc_attribute_name,
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
  FROM core.attribute AS attribute
 WHERE attribute.object_id = ANY(%s::BIGINT[])
 ORDER BY attribute.object_id,
          attribute.attribute_ordinal_position,
          attribute.attribute_id
 LIMIT %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttributeDetails(ContractModel):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    fc_attribute_name: str | None = Field(default=None, min_length=1, max_length=400)
    attribute_ordinal_position: int = Field(gt=0)
    attribute_description: str | None = Field(default=None, max_length=2000)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    attribute_nullability: bool
    is_surrogate_key: bool
    is_natural_key: bool
    is_meta_data: bool
    is_masking_required: bool
    is_mapped: bool
    is_purge: bool
    is_active: bool


class ObjectDetails(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    fc_object_schema: str | None = Field(default=None, min_length=1, max_length=400)
    fc_object_name: str | None = Field(default=None, min_length=1, max_length=400)
    object_description: str | None = Field(default=None, max_length=2000)
    object_type_id: int = Field(gt=0)
    object_type_code: str = Field(min_length=1, max_length=100)
    object_type_name: str = Field(min_length=1, max_length=200)
    zone: ZoneCode
    batch_attribute_name: str | None = Field(default=None, max_length=400)
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
    is_locked: bool
    is_active: bool
    attributes: tuple[AttributeDetails, ...]
