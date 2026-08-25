"""Tenant-owned Mapping review persistence."""

from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.mapping.read_contracts import (
    MappingAttributeDetail,
    MappingAttributeNotFoundError,
    MappingAttributePage,
    MappingAttributeSummary,
    MappingDependencyFilters,
    MappingDependencyPage,
    MappingDependencySummary,
    MappingObjectDetail,
    MappingObjectNotFoundError,
    MappingObjectPage,
    MappingObjectSummary,
)
from gds_workbench_api.features.models import ModelNotFoundError

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_MAPPING_DEPENDENCIES_SQL: LiteralString = """
SELECT dependency.mapping_source_system_dependency_id,
       dependency.workflow_run_id,
       dependency.modeled_entity_type AS entity_type,
       jsonb_build_object(
           'system_id', source_system.system_id,
           'system_code', source_system.system_code,
           'system_name', source_system.system_name
       ) AS source_system,
       dependency.source_system_dependency_order AS dependency_order,
       dependency.mapping_source_system_dependency_status AS status,
       dependency.mapping_source_system_dependency_is_locked AS is_locked,
       dependency.updated_time AS updated_at
  FROM workflow.mapping_source_system_dependency AS dependency
  JOIN model.model AS target_model
    ON target_model.model_id = dependency.model_id
  JOIN core.system AS source_system
    ON source_system.system_id = dependency.source_system_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR dependency.modeled_entity_type = %s)
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(source_system.system_code)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR dependency.mapping_source_system_dependency_status = %s
   )
   AND (
       %s::BOOLEAN IS NULL
       OR dependency.mapping_source_system_dependency_is_locked = %s
   )
 ORDER BY dependency.modeled_entity_type,
          dependency.source_system_dependency_order,
          lower(btrim(source_system.system_code)),
          dependency.mapping_source_system_dependency_id
 LIMIT %s OFFSET %s
"""

MAPPING_OBJECTS_SQL: LiteralString = """
WITH target_model AS (
    SELECT target_model.model_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
), eligible_objects AS MATERIALIZED (
    SELECT eligibility.*
      FROM target_model
      CROSS JOIN LATERAL workflow.list_model_object_eligibility(
          target_model.model_id
      ) AS eligibility
)
SELECT mapping.mapping_object_id,
       mapping.workflow_run_id,
       jsonb_build_object(
           'object_id', target_object.object_id,
           'tenant_id', target_tenant.tenant_id,
           'tenant_code', target_tenant.tenant_code,
           'tenant_name', target_tenant.tenant_name,
           'system_id', target_system.system_id,
           'system_code', target_system.system_code,
           'system_name', target_system.system_name,
           'connection_id', target_connection.connection_id,
           'connection_code', target_connection.connection_code,
           'object_schema', target_object.object_schema,
           'object_name', target_object.object_name,
           'zone_code', eligibility.zone_code
       ) AS target,
       jsonb_build_object(
           'entity_type', mapping.modeled_entity_type,
           'entity_id', CASE mapping.modeled_entity_type
               WHEN 'logical_entity' THEN mapping.logical_entity_id
               ELSE mapping.dimensional_entity_id
           END,
           'entity_name', CASE mapping.modeled_entity_type
               WHEN 'logical_entity' THEN logical_entity.logical_entity_name
               ELSE dimensional_entity.dimensional_entity_name
           END
       ) AS source,
       jsonb_build_object(
           'system_id', source_system.system_id,
           'system_code', source_system.system_code,
           'system_name', source_system.system_name
       ) AS source_system,
       mapping.object_dependency_order AS dependency_order,
       mapping.artifact_type,
       mapping.object_mapping_status AS status,
       mapping.object_mapping_is_locked AS is_locked,
       mapping.updated_time AS updated_at
  FROM target_model
  JOIN workflow.mapping_object AS mapping
    ON mapping.model_id = target_model.model_id
  JOIN eligible_objects AS eligibility
    ON eligibility.model_id = mapping.model_id
   AND eligibility.object_id = mapping.object_id
   AND (
       (
           mapping.modeled_entity_type = 'logical_entity'
           AND eligibility.is_logical_mapping_target_eligible
       ) OR (
           mapping.modeled_entity_type = 'dimensional_entity'
           AND eligibility.is_dimensional_mapping_target_eligible
       )
   )
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = eligibility.object_tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN core.system AS source_system
    ON source_system.system_id = mapping.source_system_id
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = mapping.logical_entity_id
   AND logical_entity.model_id = mapping.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = mapping.dimensional_entity_id
   AND dimensional_entity.model_id = mapping.model_id
 WHERE (%s::VARCHAR IS NULL OR mapping.modeled_entity_type = %s)
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(source_system.system_code)) = %s
   )
   AND (%s::VARCHAR IS NULL OR mapping.object_mapping_status = %s)
   AND (%s::BOOLEAN IS NULL OR mapping.object_mapping_is_locked = %s)
 ORDER BY lower(btrim(target_tenant.tenant_code)),
          lower(btrim(target_system.system_code)),
          lower(btrim(target_object.object_schema)),
          lower(btrim(target_object.object_name)),
          target_object.object_id,
          mapping.modeled_entity_type,
          lower(btrim(source_system.system_code)),
          mapping.mapping_object_id
 LIMIT %s OFFSET %s
"""

MAPPING_OBJECT_DETAIL_SQL: LiteralString = """
SELECT mapping.mapping_object_id,
       mapping.workflow_run_id,
       jsonb_build_object(
           'object_id', target_object.object_id,
           'tenant_id', target_tenant.tenant_id,
           'tenant_code', target_tenant.tenant_code,
           'tenant_name', target_tenant.tenant_name,
           'system_id', target_system.system_id,
           'system_code', target_system.system_code,
           'system_name', target_system.system_name,
           'connection_id', target_connection.connection_id,
           'connection_code', target_connection.connection_code,
           'object_schema', target_object.object_schema,
           'object_name', target_object.object_name,
           'zone_code', lower(btrim(target_zone.zone_code))
       ) AS target,
       jsonb_build_object(
           'entity_type', mapping.modeled_entity_type,
           'entity_id', CASE mapping.modeled_entity_type
               WHEN 'logical_entity' THEN mapping.logical_entity_id
               ELSE mapping.dimensional_entity_id
           END,
           'entity_name', CASE mapping.modeled_entity_type
               WHEN 'logical_entity' THEN logical_entity.logical_entity_name
               ELSE dimensional_entity.dimensional_entity_name
           END
       ) AS source,
       jsonb_build_object(
           'system_id', source_system.system_id,
           'system_code', source_system.system_code,
           'system_name', source_system.system_name
       ) AS source_system,
       mapping.object_dependency_order AS dependency_order,
       mapping.artifact_type,
       mapping.object_mapping_status AS status,
       mapping.object_mapping_is_locked AS is_locked,
       mapping.updated_time AS updated_at,
       mapping.artifact_generation_instructions,
       CASE
           WHEN mapping.mapping_profile_key IS NULL THEN NULL
           ELSE jsonb_build_object(
               'profile_key', mapping.mapping_profile_key,
               'profile_version', mapping.mapping_profile_version,
               'profile_schema_digest', mapping.mapping_profile_schema_digest,
               'package_digest', mapping.mapping_package_digest
           )
       END AS mapping_profile,
       mapping.mapping_package_document,
       CASE
           WHEN mapping.object_mapping_transformation_document IS NULL THEN NULL
           WHEN mapping.output_template_id IS NULL THEN 'free_form'
           ELSE 'structured'
       END AS mapping_document_format,
       mapping.object_mapping_transformation_document AS mapping_document,
       CASE
           WHEN output_template.output_template_id IS NULL THEN NULL
           ELSE jsonb_build_object(
               'output_template_id', output_template.output_template_id,
               'output_template_code', output_template.output_template_code,
               'output_template_name', output_template.output_template_name,
               'output_template_target_type',
                   output_template.output_template_target_type,
               'output_template_schema_digest',
                   output_template.output_template_schema_digest,
               'is_active', output_template.is_active
           )
       END AS output_template,
       mapping.created_time AS created_at
  FROM workflow.mapping_object AS mapping
  JOIN model.model AS target_model
    ON target_model.model_id = mapping.model_id
  JOIN LATERAL workflow.list_model_object_eligibility(mapping.model_id)
       AS target_eligibility
    ON target_eligibility.model_id = mapping.model_id
   AND target_eligibility.object_id = mapping.object_id
   AND (
       (
           mapping.modeled_entity_type = 'logical_entity'
           AND target_eligibility.is_logical_mapping_target_eligible
       ) OR (
           mapping.modeled_entity_type = 'dimensional_entity'
           AND target_eligibility.is_dimensional_mapping_target_eligible
       )
   )
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_eligibility.object_tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN reference.zone AS target_zone
    ON target_zone.zone_id = target_object.zone_id
  JOIN core.system AS source_system
    ON source_system.system_id = mapping.source_system_id
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = mapping.logical_entity_id
   AND logical_entity.model_id = mapping.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = mapping.dimensional_entity_id
   AND dimensional_entity.model_id = mapping.model_id
  LEFT JOIN application.output_template AS output_template
    ON output_template.output_template_id = mapping.output_template_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND mapping.mapping_object_id = %s
"""

MAPPING_ATTRIBUTES_SQL: LiteralString = """
WITH target_model AS (
    SELECT target_model.model_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
), eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM target_model
      CROSS JOIN LATERAL workflow.list_model_attribute_eligibility(
          target_model.model_id
      ) AS eligibility
)
SELECT attribute_mapping.mapping_attribute_id,
       attribute_mapping.workflow_run_id,
       attribute_mapping.mapping_object_id,
       jsonb_build_object(
           'object', jsonb_build_object(
               'object_id', target_object.object_id,
               'tenant_id', target_tenant.tenant_id,
               'tenant_code', target_tenant.tenant_code,
               'tenant_name', target_tenant.tenant_name,
               'system_id', target_system.system_id,
               'system_code', target_system.system_code,
               'system_name', target_system.system_name,
               'connection_id', target_connection.connection_id,
               'connection_code', target_connection.connection_code,
               'object_schema', target_object.object_schema,
               'object_name', target_object.object_name,
               'zone_code', eligibility.zone_code
           ),
           'attribute_id', target_attribute.attribute_id,
           'attribute_name', target_attribute.attribute_name,
           'attribute_ordinal_position',
               target_attribute.attribute_ordinal_position,
           'attribute_data_type', target_attribute.attribute_data_type
       ) AS target,
       jsonb_build_object(
           'entity', jsonb_build_object(
               'entity_type', attribute_mapping.modeled_entity_type,
               'entity_id', CASE attribute_mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN object_mapping.logical_entity_id
                   ELSE object_mapping.dimensional_entity_id
               END,
               'entity_name', CASE attribute_mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_name
                   ELSE dimensional_entity.dimensional_entity_name
               END
           ),
           'attribute_id', CASE attribute_mapping.modeled_entity_type
               WHEN 'logical_entity' THEN attribute_mapping.logical_attribute_id
               ELSE attribute_mapping.dimensional_attribute_id
           END,
           'attribute_name', CASE attribute_mapping.modeled_entity_type
               WHEN 'logical_entity' THEN logical_attribute.logical_attribute_name
               ELSE dimensional_attribute.dimensional_attribute_name
           END
       ) AS source,
       jsonb_build_object(
           'system_id', source_system.system_id,
           'system_code', source_system.system_code,
           'system_name', source_system.system_name
       ) AS source_system,
       attribute_mapping.attribute_mapping_status AS status,
       attribute_mapping.attribute_mapping_is_locked AS is_locked,
       attribute_mapping.updated_time AS updated_at
  FROM target_model
  JOIN workflow.mapping_attribute AS attribute_mapping
    ON attribute_mapping.model_id = target_model.model_id
  JOIN eligible_attributes AS eligibility
    ON eligibility.model_id = attribute_mapping.model_id
   AND eligibility.object_id = attribute_mapping.object_id
   AND eligibility.attribute_id = attribute_mapping.attribute_id
   AND (
       (
           attribute_mapping.modeled_entity_type = 'logical_entity'
           AND eligibility.is_logical_mapping_target_eligible
       ) OR (
           attribute_mapping.modeled_entity_type = 'dimensional_entity'
           AND eligibility.is_dimensional_mapping_target_eligible
       )
   )
  JOIN workflow.mapping_object AS object_mapping
    ON object_mapping.mapping_object_id = attribute_mapping.mapping_object_id
   AND object_mapping.model_id = attribute_mapping.model_id
   AND object_mapping.modeled_entity_type = attribute_mapping.modeled_entity_type
   AND object_mapping.object_id = attribute_mapping.object_id
  JOIN core.object AS target_object
    ON target_object.object_id = attribute_mapping.object_id
  JOIN core.attribute AS target_attribute
    ON target_attribute.attribute_id = attribute_mapping.attribute_id
   AND target_attribute.object_id = attribute_mapping.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = eligibility.object_tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN core.system AS source_system
    ON source_system.system_id = object_mapping.source_system_id
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = object_mapping.logical_entity_id
   AND logical_entity.model_id = object_mapping.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = object_mapping.dimensional_entity_id
   AND dimensional_entity.model_id = object_mapping.model_id
  LEFT JOIN workflow.logical_attribute AS logical_attribute
    ON logical_attribute.logical_attribute_id = attribute_mapping.logical_attribute_id
   AND logical_attribute.model_id = attribute_mapping.model_id
  LEFT JOIN workflow.dimensional_attribute AS dimensional_attribute
    ON dimensional_attribute.dimensional_attribute_id =
       attribute_mapping.dimensional_attribute_id
   AND dimensional_attribute.model_id = attribute_mapping.model_id
 WHERE (
       %s::VARCHAR IS NULL
       OR attribute_mapping.modeled_entity_type = %s
   )
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(source_system.system_code)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR attribute_mapping.attribute_mapping_status = %s
   )
   AND (
       %s::BOOLEAN IS NULL
       OR attribute_mapping.attribute_mapping_is_locked = %s
   )
 ORDER BY lower(btrim(target_tenant.tenant_code)),
          lower(btrim(target_system.system_code)),
          lower(btrim(target_object.object_schema)),
          lower(btrim(target_object.object_name)),
          target_object.object_id,
          target_attribute.attribute_ordinal_position,
          target_attribute.attribute_id,
          attribute_mapping.modeled_entity_type,
          lower(btrim(source_system.system_code)),
          attribute_mapping.mapping_attribute_id
 LIMIT %s OFFSET %s
"""

MAPPING_ATTRIBUTE_DETAIL_SQL: LiteralString = """
SELECT attribute_mapping.mapping_attribute_id,
       attribute_mapping.workflow_run_id,
       attribute_mapping.mapping_object_id,
       jsonb_build_object(
           'object', jsonb_build_object(
               'object_id', target_object.object_id,
               'tenant_id', target_tenant.tenant_id,
               'tenant_code', target_tenant.tenant_code,
               'tenant_name', target_tenant.tenant_name,
               'system_id', target_system.system_id,
               'system_code', target_system.system_code,
               'system_name', target_system.system_name,
               'connection_id', target_connection.connection_id,
               'connection_code', target_connection.connection_code,
               'object_schema', target_object.object_schema,
               'object_name', target_object.object_name,
               'zone_code', lower(btrim(target_zone.zone_code))
           ),
           'attribute_id', target_attribute.attribute_id,
           'attribute_name', target_attribute.attribute_name,
           'attribute_ordinal_position',
               target_attribute.attribute_ordinal_position,
           'attribute_data_type', target_attribute.attribute_data_type
       ) AS target,
       jsonb_build_object(
           'entity', jsonb_build_object(
               'entity_type', attribute_mapping.modeled_entity_type,
               'entity_id', CASE attribute_mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN object_mapping.logical_entity_id
                   ELSE object_mapping.dimensional_entity_id
               END,
               'entity_name', CASE attribute_mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_name
                   ELSE dimensional_entity.dimensional_entity_name
               END
           ),
           'attribute_id', CASE attribute_mapping.modeled_entity_type
               WHEN 'logical_entity' THEN attribute_mapping.logical_attribute_id
               ELSE attribute_mapping.dimensional_attribute_id
           END,
           'attribute_name', CASE attribute_mapping.modeled_entity_type
               WHEN 'logical_entity' THEN logical_attribute.logical_attribute_name
               ELSE dimensional_attribute.dimensional_attribute_name
           END
       ) AS source,
       jsonb_build_object(
           'system_id', source_system.system_id,
           'system_code', source_system.system_code,
           'system_name', source_system.system_name
       ) AS source_system,
       attribute_mapping.attribute_mapping_status AS status,
       attribute_mapping.attribute_mapping_is_locked AS is_locked,
       attribute_mapping.updated_time AS updated_at,
       jsonb_build_object(
           'mapping_object_id', object_mapping.mapping_object_id,
           'dependency_order', object_mapping.object_dependency_order,
           'artifact_type', object_mapping.artifact_type,
           'mapping_profile', CASE
               WHEN object_mapping.mapping_profile_key IS NULL THEN NULL
               ELSE jsonb_build_object(
                   'profile_key', object_mapping.mapping_profile_key,
                   'profile_version', object_mapping.mapping_profile_version,
                   'profile_schema_digest',
                       object_mapping.mapping_profile_schema_digest,
                   'package_digest', object_mapping.mapping_package_digest
               )
           END,
           'status', object_mapping.object_mapping_status,
           'is_locked', object_mapping.object_mapping_is_locked
       ) AS parent_object_mapping,
       CASE
           WHEN attribute_mapping.attribute_mapping_transformation_document IS NULL
               THEN NULL
           WHEN attribute_mapping.output_template_id IS NULL THEN 'free_form'
           ELSE 'structured'
       END AS mapping_document_format,
       attribute_mapping.attribute_mapping_transformation_document
           AS mapping_document,
       CASE
           WHEN output_template.output_template_id IS NULL THEN NULL
           ELSE jsonb_build_object(
               'output_template_id', output_template.output_template_id,
               'output_template_code', output_template.output_template_code,
               'output_template_name', output_template.output_template_name,
               'output_template_target_type',
                   output_template.output_template_target_type,
               'output_template_schema_digest',
                   output_template.output_template_schema_digest,
               'is_active', output_template.is_active
           )
       END AS output_template,
       attribute_mapping.created_time AS created_at
  FROM workflow.mapping_attribute AS attribute_mapping
  JOIN workflow.mapping_object AS object_mapping
    ON object_mapping.mapping_object_id = attribute_mapping.mapping_object_id
   AND object_mapping.model_id = attribute_mapping.model_id
   AND object_mapping.modeled_entity_type = attribute_mapping.modeled_entity_type
   AND object_mapping.object_id = attribute_mapping.object_id
  JOIN model.model AS target_model
    ON target_model.model_id = attribute_mapping.model_id
  JOIN LATERAL workflow.list_model_attribute_eligibility(
      attribute_mapping.model_id
  ) AS target_eligibility
    ON target_eligibility.model_id = attribute_mapping.model_id
   AND target_eligibility.object_id = attribute_mapping.object_id
   AND target_eligibility.attribute_id = attribute_mapping.attribute_id
   AND (
       (
           attribute_mapping.modeled_entity_type = 'logical_entity'
           AND target_eligibility.is_logical_mapping_target_eligible
       ) OR (
           attribute_mapping.modeled_entity_type = 'dimensional_entity'
           AND target_eligibility.is_dimensional_mapping_target_eligible
       )
   )
  JOIN core.object AS target_object
    ON target_object.object_id = attribute_mapping.object_id
  JOIN core.attribute AS target_attribute
    ON target_attribute.attribute_id = attribute_mapping.attribute_id
   AND target_attribute.object_id = attribute_mapping.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_eligibility.object_tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN reference.zone AS target_zone
    ON target_zone.zone_id = target_object.zone_id
  JOIN core.system AS source_system
    ON source_system.system_id = object_mapping.source_system_id
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = object_mapping.logical_entity_id
   AND logical_entity.model_id = object_mapping.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = object_mapping.dimensional_entity_id
   AND dimensional_entity.model_id = object_mapping.model_id
  LEFT JOIN workflow.logical_attribute AS logical_attribute
    ON logical_attribute.logical_attribute_id = attribute_mapping.logical_attribute_id
   AND logical_attribute.model_id = attribute_mapping.model_id
  LEFT JOIN workflow.dimensional_attribute AS dimensional_attribute
    ON dimensional_attribute.dimensional_attribute_id =
       attribute_mapping.dimensional_attribute_id
   AND dimensional_attribute.model_id = attribute_mapping.model_id
  LEFT JOIN application.output_template AS output_template
    ON output_template.output_template_id = attribute_mapping.output_template_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND attribute_mapping.mapping_attribute_id = %s
"""


class MappingReviewService(Protocol):
    async def list_dependencies(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingDependencyPage: ...

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingObjectPage: ...

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        mapping_object_id: int,
    ) -> MappingObjectDetail: ...

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingAttributePage: ...

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        mapping_attribute_id: int,
    ) -> MappingAttributeDetail: ...


class MappingReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseMappingReviewService:
    def __init__(
        self,
        *,
        database: MappingReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_dependencies(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingDependencyPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_mapping_dependencies:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header = await transaction.fetch_one(
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _MAPPING_DEPENDENCIES_SQL,
                (
                    tenant_id,
                    model_id,
                    filters.entity_type,
                    filters.entity_type,
                    filters.source_system_id,
                    filters.source_system_id,
                    filters.source_system_code,
                    filters.source_system_code,
                    filters.status,
                    filters.status,
                    filters.locked,
                    filters.locked,
                    page_size + 1,
                    offset,
                ),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return MappingDependencyPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                MappingDependencySummary.model_validate(row, strict=False)
                for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingObjectPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_mapping_objects:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header = await transaction.fetch_one(
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                MAPPING_OBJECTS_SQL,
                (
                    tenant_id,
                    model_id,
                    filters.entity_type,
                    filters.entity_type,
                    filters.source_system_id,
                    filters.source_system_id,
                    filters.source_system_code,
                    filters.source_system_code,
                    filters.status,
                    filters.status,
                    filters.locked,
                    filters.locked,
                    page_size + 1,
                    offset,
                ),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return MappingObjectPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                MappingObjectSummary.model_validate(row, strict=False) for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        mapping_object_id: int,
    ) -> MappingObjectDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await transaction.fetch_one(
                MAPPING_OBJECT_DETAIL_SQL,
                (tenant_id, model_id, mapping_object_id),
            )
        if row is None:
            raise MappingObjectNotFoundError()
        return MappingObjectDetail.model_validate(row, strict=False)

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingAttributePage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_mapping_attributes:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header = await transaction.fetch_one(
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                MAPPING_ATTRIBUTES_SQL,
                (
                    tenant_id,
                    model_id,
                    filters.entity_type,
                    filters.entity_type,
                    filters.source_system_id,
                    filters.source_system_id,
                    filters.source_system_code,
                    filters.source_system_code,
                    filters.status,
                    filters.status,
                    filters.locked,
                    filters.locked,
                    page_size + 1,
                    offset,
                ),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return MappingAttributePage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                MappingAttributeSummary.model_validate(row, strict=False)
                for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        mapping_attribute_id: int,
    ) -> MappingAttributeDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await transaction.fetch_one(
                MAPPING_ATTRIBUTE_DETAIL_SQL,
                (tenant_id, model_id, mapping_attribute_id),
            )
        if row is None:
            raise MappingAttributeNotFoundError()
        return MappingAttributeDetail.model_validate(row, strict=False)
