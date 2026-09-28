"""Tenant-owned Mapping reads over the Entity-owned schema."""

from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Any, LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.models import ModelNotFoundError

from .read_contracts import (
    MappingAttributeDetail,
    MappingAttributeFilters,
    MappingAttributeNotFoundError,
    MappingAttributePage,
    MappingAttributeSummary,
    MappingEntityType,
    MappingFilters,
    MappingGenerationPage,
    MappingGenerationTarget,
    MappingObjectDetail,
    MappingObjectNotFoundError,
    MappingObjectPage,
    MappingObjectSummary,
)

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_MAPPING_TARGET_BASE_SQL: LiteralString = """
SELECT entity.modeled_entity_id AS entity_id, entity.modeled_entity_type AS entity_type,
       entity.modeled_entity_schema_name AS entity_schema_name, entity.modeled_entity_name AS
           entity_name
  FROM model.model AS target_model
  JOIN workflow.modeled_entity AS entity ON entity.model_id = target_model.model_id
 WHERE target_model.tenant_id = %s AND target_model.model_id = %s AND target_model.is_active
   AND entity.modeled_entity_type = %s AND entity.status = 'active'
"""


_MAPPING_GENERATION_TARGETS_SQL: LiteralString = (
    "WITH targets AS ("
    + _MAPPING_TARGET_BASE_SQL
    + """
)
SELECT targets.*, jsonb_build_object('system_id', source_system.system_id, 'system_code',
    source_system.system_code, 'system_name', source_system.system_name) AS source_system,
       mapping.mapping_object_id,
       coalesce(mapping.object_dependency_order, entity.dependency_order) AS object_order,
       entity.is_locked OR coalesce(mapping.object_mapping_is_locked, FALSE) AS is_locked,
       input.is_default OR EXISTS (
           SELECT 1 FROM workflow.list_mapping_source_objects(entity.model_id,
               entity.modeled_entity_id, entity.modeled_entity_type, source_system.system_id)
       ) AS has_sources,
       attributes.items AS attributes
  FROM targets
  JOIN model.model AS model ON model.tenant_id = %s AND model.model_id = %s AND model.is_active
  JOIN workflow.modeled_entity AS entity ON entity.model_id = model.model_id
   AND entity.modeled_entity_type = targets.entity_type AND entity.modeled_entity_id =
       targets.entity_id
 CROSS JOIN LATERAL (
     SELECT model.default_mapping_source_system_id IS NOT NULL
        AND workflow.is_assertion_only_mapping_target(model.model_id,
            entity.modeled_entity_id, entity.modeled_entity_type) AS uses_default
 ) AS fallback
 CROSS JOIN LATERAL (
     SELECT DISTINCT source_system_id, FALSE AS is_default
       FROM workflow.list_model_input_sources(model.model_id)
      WHERE NOT fallback.uses_default
     UNION
     SELECT model.default_mapping_source_system_id, TRUE WHERE fallback.uses_default
 ) AS input
  JOIN core.system AS source_system ON source_system.system_id = input.source_system_id
   AND source_system.is_active
   AND (NOT input.is_default OR EXISTS (
       SELECT 1 FROM core.connection AS owned_connection
        WHERE owned_connection.tenant_id = model.tenant_id
          AND owned_connection.system_id = source_system.system_id AND owned_connection.is_active
   ))
  LEFT JOIN workflow.mapping_object AS mapping ON mapping.model_id = entity.model_id
   AND mapping.modeled_entity_type = entity.modeled_entity_type
   AND coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id) = entity.modeled_entity_id
   AND mapping.source_system_id = source_system.system_id
 CROSS JOIN LATERAL (
   SELECT coalesce(jsonb_agg(jsonb_build_object(
       'attribute_id', attribute.modeled_attribute_id, 'attribute_name', attribute.attribute_name,
       'modeled_attribute_name', attribute.attribute_name, 'ordinal_position',
           attribute.ordinal_position,
       'is_locked', attribute.is_locked OR coalesce(child.attribute_mapping_is_locked, FALSE),
       'is_authored', child.attribute_mapping_transformation_document IS NOT NULL
   ) ORDER BY attribute.ordinal_position, attribute.modeled_attribute_id), '[]'::JSONB) AS items
     FROM workflow.modeled_attribute AS attribute
     LEFT JOIN workflow.mapping_attribute AS child ON child.mapping_object_id =
         mapping.mapping_object_id
      AND coalesce(child.logical_attribute_id, child.dimensional_attribute_id) =
          attribute.modeled_attribute_id
    WHERE attribute.model_id = entity.model_id AND attribute.modeled_entity_type =
        entity.modeled_entity_type
      AND attribute.modeled_entity_id = entity.modeled_entity_id AND attribute.status = 'active'
 ) AS attributes
 ORDER BY source_system.system_code, object_order, targets.entity_schema_name,
     targets.entity_name, targets.entity_id
 LIMIT %s OFFSET %s
"""
)

_OBJECT_COLUMNS = """
SELECT mapping.mapping_object_id, mapping.workflow_run_id, jsonb_build_object('entity_type',
    entity.modeled_entity_type, 'entity_id', entity.modeled_entity_id, 'entity_schema_name',
    entity.modeled_entity_schema_name, 'entity_name', entity.modeled_entity_name) AS target,
       jsonb_build_object('system_id', source_system.system_id, 'system_code',
           source_system.system_code, 'system_name', source_system.system_name) AS source_system,
       mapping.object_dependency_order AS dependency_order, mapping.object_mapping_status AS status,
       mapping.object_mapping_is_locked AS is_locked, mapping.updated_time AS updated_at
"""

_OBJECT_BASE_SQL = """
  FROM workflow.mapping_object AS mapping
  JOIN model.model AS target_model ON target_model.model_id = mapping.model_id
  JOIN workflow.modeled_entity AS entity ON entity.model_id = mapping.model_id
   AND entity.modeled_entity_type = mapping.modeled_entity_type
   AND entity.modeled_entity_id = coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id)
  JOIN core.system AS source_system ON source_system.system_id = mapping.source_system_id
"""

MAPPING_OBJECTS_SQL: LiteralString = (
    _OBJECT_COLUMNS
    + _OBJECT_BASE_SQL
    + """
 WHERE target_model.tenant_id = %s AND target_model.model_id = %s AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR entity.modeled_entity_type = %s)
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (%s::VARCHAR IS NULL OR lower(btrim(source_system.system_code)) = %s)

   AND (%s::VARCHAR IS NULL OR mapping.object_mapping_status = %s)
   AND (%s::BOOLEAN IS NULL OR mapping.object_mapping_is_locked = %s)
 ORDER BY mapping.object_dependency_order, entity.modeled_entity_type, mapping.mapping_object_id
 LIMIT %s OFFSET %s
"""
)

MAPPING_OBJECT_DETAIL_SQL: LiteralString = (
    _OBJECT_COLUMNS
    + """,
 mapping.mapping_transformation_document AS mapping_document,
 CASE WHEN output_template.output_template_id IS NULL THEN NULL ELSE jsonb_build_object(
 'output_template_id', output_template.output_template_id, 'output_template_code',
     output_template.output_template_code,
 'output_template_name', output_template.output_template_name, 'output_template_target_type',
     output_template.output_template_target_type,
 'output_template_schema_digest', output_template.output_template_schema_digest, 'is_active',
     output_template.is_active) END AS output_template, mapping.created_time AS created_at
"""
    + _OBJECT_BASE_SQL
    + """
 LEFT JOIN application.output_template AS output_template ON output_template.output_template_id =
     mapping.output_template_id
 WHERE target_model.tenant_id = %s AND target_model.model_id = %s AND target_model.is_active
   AND mapping.mapping_object_id = %s
"""
)

_ATTRIBUTE_COLUMNS = """
SELECT attribute_mapping.mapping_attribute_id, attribute_mapping.workflow_run_id,
    object_mapping.mapping_object_id,
 jsonb_build_object('entity', jsonb_build_object('entity_type', entity.modeled_entity_type,
     'entity_id', entity.modeled_entity_id, 'entity_schema_name',
     entity.modeled_entity_schema_name, 'entity_name', entity.modeled_entity_name),
     'attribute_id', attribute.modeled_attribute_id,
 'attribute_name', attribute.attribute_name, 'ordinal_position', attribute.ordinal_position,
     'data_type', attribute.data_type) AS target,
 jsonb_build_object('system_id', source_system.system_id, 'system_code',
     source_system.system_code, 'system_name', source_system.system_name) AS source_system,
 attribute_mapping.attribute_mapping_status AS status,
     attribute_mapping.attribute_mapping_is_locked AS is_locked,
 attribute_mapping.updated_time AS updated_at
"""

_ATTRIBUTE_BASE_SQL = """
  FROM workflow.mapping_attribute AS attribute_mapping
  JOIN workflow.mapping_object AS object_mapping ON object_mapping.mapping_object_id =
      attribute_mapping.mapping_object_id
  JOIN model.model AS target_model ON target_model.model_id = object_mapping.model_id
  JOIN workflow.modeled_entity AS entity ON entity.model_id = object_mapping.model_id
   AND entity.modeled_entity_type = object_mapping.modeled_entity_type
   AND entity.modeled_entity_id = coalesce(object_mapping.logical_entity_id,
       object_mapping.dimensional_entity_id)
  JOIN workflow.modeled_attribute AS attribute ON attribute.model_id = entity.model_id
   AND attribute.modeled_entity_type = entity.modeled_entity_type
   AND attribute.modeled_entity_id = entity.modeled_entity_id
   AND attribute.modeled_attribute_id = coalesce(attribute_mapping.logical_attribute_id,
       attribute_mapping.dimensional_attribute_id)
  JOIN core.system AS source_system ON source_system.system_id = object_mapping.source_system_id
"""

MAPPING_ATTRIBUTES_SQL: LiteralString = (
    _ATTRIBUTE_COLUMNS
    + _ATTRIBUTE_BASE_SQL
    + """
 WHERE target_model.tenant_id = %s AND target_model.model_id = %s AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR entity.modeled_entity_type = %s)
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (%s::VARCHAR IS NULL OR lower(btrim(source_system.system_code)) = %s)

 AND (%s::VARCHAR IS NULL OR attribute_mapping.attribute_mapping_status = %s)
 AND (%s::BOOLEAN IS NULL OR attribute_mapping.attribute_mapping_is_locked = %s)
 AND (%s::BIGINT IS NULL OR object_mapping.mapping_object_id = %s)
 ORDER BY object_mapping.object_dependency_order, attribute.ordinal_position,
     attribute_mapping.mapping_attribute_id
 LIMIT %s OFFSET %s
"""
)

MAPPING_ATTRIBUTE_DETAIL_SQL: LiteralString = (
    _ATTRIBUTE_COLUMNS
    + """,
 jsonb_build_object('mapping_object_id', object_mapping.mapping_object_id, 'dependency_order',
     object_mapping.object_dependency_order, 'status', object_mapping.object_mapping_status,
     'is_locked', object_mapping.object_mapping_is_locked) AS parent_object_mapping,
 attribute_mapping.attribute_mapping_transformation_document AS mapping_document, CASE WHEN
     output_template.output_template_id IS NULL THEN NULL ELSE jsonb_build_object(
 'output_template_id', output_template.output_template_id, 'output_template_code',
     output_template.output_template_code,
 'output_template_name', output_template.output_template_name, 'output_template_target_type',
     output_template.output_template_target_type,
 'output_template_schema_digest', output_template.output_template_schema_digest, 'is_active',
     output_template.is_active) END AS output_template, attribute_mapping.created_time AS created_at
"""
    + _ATTRIBUTE_BASE_SQL
    + """
 LEFT JOIN application.output_template AS output_template ON output_template.output_template_id =
     attribute_mapping.output_template_id
 WHERE target_model.tenant_id = %s AND target_model.model_id = %s AND target_model.is_active
   AND attribute_mapping.mapping_attribute_id = %s
"""
)


class MappingReviewService(Protocol):
    async def list_generation_targets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        entity_type: MappingEntityType,
        page_size: int,
        cursor: str | None,
    ) -> MappingGenerationPage: ...

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingObjectPage: ...
    async def read_object(
        self, principal: RequestPrincipal, *, tenant_id: int, model_id: int, mapping_object_id: int
    ) -> MappingObjectDetail: ...
    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingAttributeFilters,
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
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
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

    async def list_generation_targets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        entity_type: MappingEntityType,
        page_size: int,
        cursor: str | None,
    ) -> MappingGenerationPage:
        collection = f"web_mapping_generation:{tenant_id}:{model_id}:{entity_type}:{page_size}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                model_id=model_id,
            )
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _MAPPING_GENERATION_TARGETS_SQL,
                (tenant_id, model_id, entity_type, tenant_id, model_id, page_size + 1, offset),
            )
        next_cursor = (
            self._cursors.encode(collection=collection, offset=offset + page_size)
            if len(rows) > page_size
            else None
        )
        return MappingGenerationPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                MappingGenerationTarget.model_validate(row, strict=False)
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
        filters: MappingFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingObjectPage:
        header, rows, next_cursor = await self._list(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=page_size,
            cursor=cursor,
            kind="objects",
            sql=MAPPING_OBJECTS_SQL,
        )
        return MappingObjectPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(MappingObjectSummary.model_validate(row, strict=False) for row in rows),
            next_cursor=next_cursor,
        )

    async def read_object(
        self, principal: RequestPrincipal, *, tenant_id: int, model_id: int, mapping_object_id: int
    ) -> MappingObjectDetail:
        row = await self._read(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            record_id=mapping_object_id,
            sql=MAPPING_OBJECT_DETAIL_SQL,
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
        filters: MappingAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingAttributePage:
        header, rows, next_cursor = await self._list(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=page_size,
            cursor=cursor,
            kind="attributes",
            sql=MAPPING_ATTRIBUTES_SQL,
        )
        return MappingAttributePage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(MappingAttributeSummary.model_validate(row, strict=False) for row in rows),
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
        row = await self._read(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            record_id=mapping_attribute_id,
            sql=MAPPING_ATTRIBUTE_DETAIL_SQL,
        )
        if row is None:
            raise MappingAttributeNotFoundError()
        return MappingAttributeDetail.model_validate(row, strict=False)

    async def _list(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingFilters,
        page_size: int,
        cursor: str | None,
        kind: str,
        sql: LiteralString,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
        digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_mapping_{kind}:{tenant_id}:{model_id}:{page_size}:{digest}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                model_id=model_id,
            )
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                sql,
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
                    *(
                        (filters.mapping_object_id, filters.mapping_object_id)
                        if isinstance(filters, MappingAttributeFilters)
                        else ()
                    ),
                    page_size + 1,
                    offset,
                ),
            )
        next_cursor = (
            self._cursors.encode(collection=collection, offset=offset + page_size)
            if len(rows) > page_size
            else None
        )
        return header, list(rows[:page_size]), next_cursor

    async def _read(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        record_id: int,
        sql: LiteralString,
    ) -> dict[str, Any] | None:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                model_id=model_id,
            )
            return await transaction.fetch_one(sql, (tenant_id, model_id, record_id))
