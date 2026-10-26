"""Tenant-owned normalized Dimensional model review persistence."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.dimensional.read_contracts import (
    MAX_DETAIL_ROWS,
    DimensionalAttributeContextSource,
    DimensionalAttributeDetail,
    DimensionalAttributeFilters,
    DimensionalAttributeLogicalSource,
    DimensionalAttributeNotFoundError,
    DimensionalAttributePage,
    DimensionalAttributeSource,
    DimensionalAttributeSummary,
    DimensionalContextSource,
    DimensionalDetailLimitExceededError,
    DimensionalLogicalEntitySource,
    DimensionalObjectDetail,
    DimensionalObjectFilters,
    DimensionalObjectNotFoundError,
    DimensionalObjectPage,
    DimensionalObjectSource,
    DimensionalObjectSummary,
    DimensionalRelationshipDetail,
    DimensionalRelationshipFilters,
    DimensionalRelationshipNotFoundError,
    DimensionalRelationshipPage,
    DimensionalRelationshipSummary,
)
from gds_workbench_api.features.logical import (
    ModeledFilters,
    ModelSubjectArea,
    ModelSubjectAreaPage,
)
from gds_workbench_api.features.projects import ProjectNotFoundError

_PROJECT_HEADER_SQL: LiteralString = """
SELECT target_project.project_revision
  FROM project.project AS target_project
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
"""

_DIMENSIONAL_OBJECTS_SQL: LiteralString = """
SELECT entity.dimensional_entity_id,
       entity.workflow_run_id,
       entity.dimensional_entity_schema_name,
       entity.dimensional_entity_name,
       entity.dimensional_entity_type,
       entity.dimensional_fact_type,
       entity.dimensional_entity_dependency_order,
       entity.dimensional_entity_is_active,
       entity.dimensional_entity_is_locked,
       entity.updated_time AS updated_at
  FROM workflow.dimensional_entity AS entity
  JOIN project.project AS target_project
    ON target_project.project_id = entity.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BOOLEAN IS NULL OR entity.dimensional_entity_is_active = %s)
   AND (%s::BOOLEAN IS NULL OR entity.dimensional_entity_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(entity.dimensional_entity_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(entity.dimensional_entity_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR EXISTS (
           SELECT 1
             FROM workflow.dimensional_entity_source_mapping AS dimensional_source
             JOIN workflow.logical_entity AS logical
               ON logical.project_id = dimensional_source.project_id
              AND logical.logical_entity_id = dimensional_source.source_logical_entity_id
              AND logical.logical_entity_is_active
             JOIN workflow.logical_entity_source_mapping AS logical_source
               ON logical_source.project_id = logical.project_id
              AND logical_source.logical_entity_id = logical.logical_entity_id
              AND logical_source.logical_entity_source_mapping_is_active
             JOIN workflow.subject_area_table AS member
               ON member.project_id = logical_source.project_id
              AND member.object_id = logical_source.source_object_id
              AND member.subject_area_table_is_active
            WHERE dimensional_source.project_id = entity.project_id
              AND dimensional_source.dimensional_entity_id = entity.dimensional_entity_id
              AND dimensional_source.dimensional_entity_source_mapping_is_active
              AND member.subject_area_id = %s
       )
   )
 ORDER BY entity.dimensional_entity_dependency_order,
          lower(btrim(entity.dimensional_entity_name)),
          entity.dimensional_entity_id
 LIMIT %s OFFSET %s
"""

_DIMENSIONAL_OBJECT_DETAIL_SQL: LiteralString = """
SELECT entity.dimensional_entity_id,
       entity.workflow_run_id,
       entity.dimensional_entity_schema_name,
       entity.dimensional_entity_name,
       entity.dimensional_entity_definition,
       entity.dimensional_entity_type,
       entity.dimensional_fact_type,
       entity.dimensional_entity_grain_definition,
       entity.dimensional_entity_dependency_order,
       entity.dimensional_entity_is_active,
       entity.dimensional_entity_is_locked,
       entity.created_time AS created_at,
       entity.updated_time AS updated_at
  FROM workflow.dimensional_entity AS entity
  JOIN project.project AS target_project
    ON target_project.project_id = entity.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND entity.dimensional_entity_id = %s
"""

# Active Subject Areas with their active Objects and the active Dimensional Entities that
# reach them through active Logical sources, as the Subject Area filter does.
_DIMENSIONAL_SUBJECT_AREAS_SQL: LiteralString = """
SELECT area.subject_area_id,
       area.subject_area_name,
       area.subject_area_definition,
       (
           SELECT count(*)
             FROM workflow.subject_area_table AS member
            WHERE member.project_id = area.project_id
              AND member.subject_area_id = area.subject_area_id
              AND member.subject_area_table_is_active
       ) AS table_count,
       (
           SELECT count(*)
             FROM workflow.dimensional_entity AS entity
            WHERE entity.project_id = area.project_id
              AND entity.dimensional_entity_is_active
              AND EXISTS (
                  SELECT 1
                    FROM workflow.dimensional_entity_source_mapping AS dimensional_source
                    JOIN workflow.logical_entity AS logical
                      ON logical.project_id = dimensional_source.project_id
                     AND logical.logical_entity_id = dimensional_source.source_logical_entity_id
                     AND logical.logical_entity_is_active
                    JOIN workflow.logical_entity_source_mapping AS logical_source
                      ON logical_source.project_id = logical.project_id
                     AND logical_source.logical_entity_id = logical.logical_entity_id
                     AND logical_source.logical_entity_source_mapping_is_active
                    JOIN workflow.subject_area_table AS member
                      ON member.project_id = logical_source.project_id
                     AND member.object_id = logical_source.source_object_id
                     AND member.subject_area_table_is_active
                   WHERE dimensional_source.project_id = entity.project_id
                     AND dimensional_source.dimensional_entity_id = entity.dimensional_entity_id
                     AND dimensional_source.dimensional_entity_source_mapping_is_active
                     AND member.subject_area_id = area.subject_area_id
              )
       ) AS entity_count
  FROM workflow.subject_area AS area
  JOIN project.project AS target_project
    ON target_project.project_id = area.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND area.subject_area_is_active
 ORDER BY lower(btrim(area.subject_area_name)),
          area.subject_area_id
 LIMIT 1001
"""

# Dimensional reuses the Project's Subject Areas through its active Logical sources.
_DIMENSIONAL_OBJECT_SUBJECT_AREAS_SQL: LiteralString = """
SELECT area.subject_area_id,
       area.subject_area_name
  FROM workflow.subject_area AS area
  JOIN project.project AS target_project
    ON target_project.project_id = area.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND area.subject_area_is_active
   AND EXISTS (
       SELECT 1
         FROM workflow.dimensional_entity_source_mapping AS dimensional_source
         JOIN workflow.logical_entity AS logical
           ON logical.project_id = dimensional_source.project_id
          AND logical.logical_entity_id = dimensional_source.source_logical_entity_id
          AND logical.logical_entity_is_active
         JOIN workflow.logical_entity_source_mapping AS logical_source
           ON logical_source.project_id = logical.project_id
          AND logical_source.logical_entity_id = logical.logical_entity_id
          AND logical_source.logical_entity_source_mapping_is_active
         JOIN workflow.subject_area_table AS member
           ON member.project_id = logical_source.project_id
          AND member.object_id = logical_source.source_object_id
          AND member.subject_area_table_is_active
        WHERE dimensional_source.project_id = area.project_id
          AND dimensional_source.dimensional_entity_id = %s
          AND dimensional_source.dimensional_entity_source_mapping_is_active
          AND member.subject_area_id = area.subject_area_id
   )
 ORDER BY lower(btrim(area.subject_area_name)),
          area.subject_area_id
 LIMIT %s
"""

DIMENSIONAL_OBJECT_SOURCES_SQL: LiteralString = """
SELECT source.dimensional_entity_source_mapping_id,
       source.workflow_run_id,
       CASE WHEN source.source_logical_entity_id IS NOT NULL THEN 'logical_entity'
            ELSE 'context_record'
       END AS support_source_type,
       source.dimensional_entity_source_mapping_rationale AS rationale,
       source.dimensional_entity_source_mapping_is_active AS is_active,
       source.dimensional_entity_source_mapping_is_locked AS is_locked,
       source.created_time AS created_at,
       source.updated_time AS updated_at,
       logical_source.logical_entity_id AS source_logical_entity_id,
       logical_source.logical_entity_schema_name AS source_logical_entity_schema_name,
       logical_source.logical_entity_name AS source_logical_entity_name,
       context_record.context_record_id::TEXT AS context_record_id,
       context_group.name AS context_group_name,
       context_type.name AS context_type_name,
       context_record.context_text,
       context_record.source_reference,
       context_record.status AS context_record_status
  FROM workflow.dimensional_entity_source_mapping AS source
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = source.dimensional_entity_id
   AND entity.project_id = source.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = source.project_id
  LEFT JOIN workflow.logical_entity AS logical_source
    ON logical_source.logical_entity_id = source.source_logical_entity_id
   AND logical_source.project_id = source.project_id
  LEFT JOIN project.context_record AS context_record
    ON context_record.context_record_id
       = source.context_record_id
   AND context_record.project_id = source.project_id
  LEFT JOIN project.context_group AS context_group
    ON context_group.context_group_id
       = context_record.context_group_id
   AND context_group.project_id = context_record.project_id
  LEFT JOIN reference.context_type AS context_type
    ON context_type.context_type_id = context_group.context_type_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND source.dimensional_entity_id = %s
 ORDER BY source.dimensional_entity_source_mapping_id
 LIMIT %s
"""

_DIMENSIONAL_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.dimensional_attribute_id,
       attribute.workflow_run_id,
       attribute.dimensional_entity_id,
       entity.dimensional_entity_schema_name,
       entity.dimensional_entity_name,
       attribute.dimensional_attribute_name,
       attribute.dimensional_attribute_data_type,
       attribute.dimensional_attribute_is_nullable,
       attribute.dimensional_attribute_ordinal_position,
       attribute.dimensional_attribute_is_natural_key,
       attribute.dimensional_attribute_is_surrogate_key,
       attribute.dimensional_attribute_is_audit_column,
       attribute.dimensional_attribute_is_active,
       attribute.dimensional_attribute_is_locked,
       attribute.updated_time AS updated_at
  FROM workflow.dimensional_attribute AS attribute
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = attribute.dimensional_entity_id
   AND entity.project_id = attribute.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = attribute.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BOOLEAN IS NULL OR attribute.dimensional_attribute_is_active = %s)
   AND (%s::BOOLEAN IS NULL OR attribute.dimensional_attribute_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(attribute.dimensional_attribute_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(attribute.dimensional_attribute_name)),
           char_length(%s)
       ) = %s
   )
   AND (%s::BIGINT IS NULL OR attribute.dimensional_entity_id = %s)
 ORDER BY lower(btrim(entity.dimensional_entity_name)),
          attribute.dimensional_attribute_ordinal_position,
          attribute.dimensional_attribute_id
 LIMIT %s OFFSET %s
"""

_DIMENSIONAL_ATTRIBUTE_DETAIL_SQL: LiteralString = """
SELECT attribute.dimensional_attribute_id,
       attribute.workflow_run_id,
       attribute.dimensional_entity_id,
       entity.dimensional_entity_schema_name,
       entity.dimensional_entity_name,
       attribute.dimensional_attribute_name,
       attribute.dimensional_attribute_definition,
       attribute.dimensional_attribute_data_type,
       attribute.dimensional_attribute_is_nullable,
       attribute.dimensional_attribute_ordinal_position,
       attribute.dimensional_attribute_is_natural_key,
       attribute.dimensional_attribute_is_surrogate_key,
       attribute.dimensional_attribute_is_audit_column,
       attribute.dimensional_attribute_is_active,
       attribute.dimensional_attribute_is_locked,
       attribute.created_time AS created_at,
       attribute.updated_time AS updated_at
  FROM workflow.dimensional_attribute AS attribute
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = attribute.dimensional_entity_id
   AND entity.project_id = attribute.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = attribute.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND attribute.dimensional_attribute_id = %s
"""

DIMENSIONAL_ATTRIBUTE_SOURCES_SQL: LiteralString = """
SELECT source.dimensional_attribute_source_mapping_id,
       source.workflow_run_id,
       source.dimensional_entity_source_mapping_id,
       CASE WHEN source.source_logical_attribute_id IS NOT NULL THEN 'logical_attribute'
            ELSE 'context_record'
       END AS support_source_type,
       source.dimensional_attribute_source_mapping_rationale AS rationale,
       source.dimensional_attribute_source_mapping_is_active AS is_active,
       source.dimensional_attribute_source_mapping_is_locked AS is_locked,
       source.created_time AS created_at,
       source.updated_time AS updated_at,
       logical_source.logical_entity_id AS source_logical_entity_id,
       logical_source.logical_entity_schema_name AS source_logical_entity_schema_name,
       logical_source.logical_entity_name AS source_logical_entity_name,
       logical_attribute.logical_attribute_id AS source_logical_attribute_id,
       logical_attribute.logical_attribute_name AS source_logical_attribute_name,
       context_record.context_record_id::TEXT AS context_record_id,
       context_group.name AS context_group_name,
       context_type.name AS context_type_name,
       context_record.context_text,
       context_record.source_reference,
       context_record.status AS context_record_status
  FROM workflow.dimensional_attribute_source_mapping AS source
  JOIN workflow.dimensional_attribute AS attribute
    ON attribute.dimensional_attribute_id = source.dimensional_attribute_id
   AND attribute.dimensional_entity_id = source.dimensional_entity_id
   AND attribute.project_id = source.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = source.project_id
  LEFT JOIN workflow.logical_entity AS logical_source
    ON logical_source.logical_entity_id = source.source_logical_entity_id
   AND logical_source.project_id = source.project_id
  LEFT JOIN workflow.logical_attribute AS logical_attribute
    ON logical_attribute.logical_attribute_id = source.source_logical_attribute_id
   AND logical_attribute.logical_entity_id = source.source_logical_entity_id
   AND logical_attribute.project_id = source.project_id
  LEFT JOIN project.context_record AS context_record
    ON context_record.context_record_id
       = source.context_record_id
   AND context_record.project_id = source.project_id
  LEFT JOIN project.context_group AS context_group
    ON context_group.context_group_id
       = context_record.context_group_id
   AND context_group.project_id = context_record.project_id
  LEFT JOIN reference.context_type AS context_type
    ON context_type.context_type_id = context_group.context_type_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND source.dimensional_attribute_id = %s
 ORDER BY source.dimensional_attribute_source_mapping_id
 LIMIT %s
"""

_DIMENSIONAL_RELATIONSHIPS_SQL: LiteralString = """
SELECT relationship.dimensional_relationship_id,
       relationship.workflow_run_id,
       relationship.dimensional_relationship_from_entity_id
           AS from_dimensional_entity_id,
       from_entity.dimensional_entity_schema_name AS from_dimensional_entity_schema_name,
       from_entity.dimensional_entity_name AS from_dimensional_entity_name,
       relationship.dimensional_relationship_from_attribute_id
           AS from_dimensional_attribute_id,
       from_attribute.dimensional_attribute_name
           AS from_dimensional_attribute_name,
       relationship.dimensional_relationship_to_entity_id
           AS to_dimensional_entity_id,
       to_entity.dimensional_entity_schema_name AS to_dimensional_entity_schema_name,
       to_entity.dimensional_entity_name AS to_dimensional_entity_name,
       relationship.dimensional_relationship_to_attribute_id
           AS to_dimensional_attribute_id,
       to_attribute.dimensional_attribute_name AS to_dimensional_attribute_name,
       relationship.dimensional_relationship_role_name,
       relationship.dimensional_relationship_is_active,
       relationship.dimensional_relationship_is_locked,
       relationship.updated_time AS updated_at
  FROM workflow.dimensional_relationship AS relationship
  JOIN workflow.dimensional_entity AS from_entity
    ON from_entity.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_entity.project_id = relationship.project_id
  JOIN workflow.dimensional_attribute AS from_attribute
    ON from_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_from_attribute_id
   AND from_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_attribute.project_id = relationship.project_id
  JOIN workflow.dimensional_entity AS to_entity
    ON to_entity.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_entity.project_id = relationship.project_id
  JOIN workflow.dimensional_attribute AS to_attribute
    ON to_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_to_attribute_id
   AND to_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_attribute.project_id = relationship.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = relationship.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BOOLEAN IS NULL OR relationship.dimensional_relationship_is_active = %s)
   AND (%s::BOOLEAN IS NULL OR relationship.dimensional_relationship_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(from_attribute.dimensional_attribute_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(from_attribute.dimensional_attribute_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR relationship.dimensional_relationship_from_entity_id = %s
       OR relationship.dimensional_relationship_to_entity_id = %s
   )
 ORDER BY lower(btrim(from_entity.dimensional_entity_name)),
          lower(btrim(from_attribute.dimensional_attribute_name)),
          relationship.dimensional_relationship_id
 LIMIT %s OFFSET %s
"""

_DIMENSIONAL_RELATIONSHIP_DETAIL_SQL: LiteralString = """
SELECT relationship.dimensional_relationship_id,
       relationship.workflow_run_id,
       relationship.dimensional_relationship_from_entity_id
           AS from_dimensional_entity_id,
       from_entity.dimensional_entity_schema_name AS from_dimensional_entity_schema_name,
       from_entity.dimensional_entity_name AS from_dimensional_entity_name,
       relationship.dimensional_relationship_from_attribute_id
           AS from_dimensional_attribute_id,
       from_attribute.dimensional_attribute_name
           AS from_dimensional_attribute_name,
       relationship.dimensional_relationship_to_entity_id
           AS to_dimensional_entity_id,
       to_entity.dimensional_entity_schema_name AS to_dimensional_entity_schema_name,
       to_entity.dimensional_entity_name AS to_dimensional_entity_name,
       relationship.dimensional_relationship_to_attribute_id
           AS to_dimensional_attribute_id,
       to_attribute.dimensional_attribute_name AS to_dimensional_attribute_name,
       relationship.dimensional_relationship_role_name,
       relationship.dimensional_relationship_basis,
       relationship.dimensional_relationship_is_active,
       relationship.dimensional_relationship_is_locked,
       relationship.created_time AS created_at,
       relationship.updated_time AS updated_at
  FROM workflow.dimensional_relationship AS relationship
  JOIN workflow.dimensional_entity AS from_entity
    ON from_entity.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_entity.project_id = relationship.project_id
  JOIN workflow.dimensional_attribute AS from_attribute
    ON from_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_from_attribute_id
   AND from_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_attribute.project_id = relationship.project_id
  JOIN workflow.dimensional_entity AS to_entity
    ON to_entity.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_entity.project_id = relationship.project_id
  JOIN workflow.dimensional_attribute AS to_attribute
    ON to_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_to_attribute_id
   AND to_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_attribute.project_id = relationship.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = relationship.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND relationship.dimensional_relationship_id = %s
"""


class DimensionalService(Protocol):
    async def list_subject_areas(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> ModelSubjectAreaPage: ...

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalObjectFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalObjectPage: ...

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_entity_id: int,
    ) -> DimensionalObjectDetail: ...

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalAttributePage: ...

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_attribute_id: int,
    ) -> DimensionalAttributeDetail: ...

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalRelationshipPage: ...

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_relationship_id: int,
    ) -> DimensionalRelationshipDetail: ...


class DimensionalReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseDimensionalService:
    def __init__(
        self,
        *,
        database: DimensionalReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_subject_areas(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> ModelSubjectAreaPage:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            header = await transaction.fetch_one(_PROJECT_HEADER_SQL, (tenant_id, project_id))
            if header is None:
                raise ProjectNotFoundError()
            rows = await transaction.fetch_all(
                _DIMENSIONAL_SUBJECT_AREAS_SQL, (tenant_id, project_id)
            )
        if len(rows) > 1_000:
            raise DimensionalDetailLimitExceededError()
        return ModelSubjectAreaPage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(ModelSubjectArea.model_validate(row) for row in rows),
        )

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalObjectFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalObjectPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_dimensional_objects:{tenant_id}:{project_id}:{page_size}:{filter_digest}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            header = await transaction.fetch_one(_PROJECT_HEADER_SQL, (tenant_id, project_id))
            if header is None:
                raise ProjectNotFoundError()
            rows = await transaction.fetch_all(
                _DIMENSIONAL_OBJECTS_SQL,
                (
                    *_list_parameters(tenant_id, project_id, filters, page_size, offset)[:-2],
                    filters.subject_area_id,
                    filters.subject_area_id,
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
        return DimensionalObjectPage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(DimensionalObjectSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_entity_id: int,
    ) -> DimensionalObjectDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            row = await transaction.fetch_one(
                _DIMENSIONAL_OBJECT_DETAIL_SQL,
                (tenant_id, project_id, dimensional_entity_id),
            )
            if row is None:
                raise DimensionalObjectNotFoundError()
            area_rows = await transaction.fetch_all(
                _DIMENSIONAL_OBJECT_SUBJECT_AREAS_SQL,
                (tenant_id, project_id, dimensional_entity_id, MAX_DETAIL_ROWS + 1),
            )
            source_rows = await transaction.fetch_all(
                DIMENSIONAL_OBJECT_SOURCES_SQL,
                (tenant_id, project_id, dimensional_entity_id, MAX_DETAIL_ROWS + 1),
            )
        if len(area_rows) > MAX_DETAIL_ROWS or len(source_rows) > MAX_DETAIL_ROWS:
            raise DimensionalDetailLimitExceededError()
        return DimensionalObjectDetail.model_validate(
            {
                **row,
                "subject_areas": tuple(area_rows),
                "sources": tuple(_normalize_object_source(item) for item in source_rows),
            },
            strict=False,
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalAttributePage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_dimensional_attributes:{tenant_id}:{project_id}:{page_size}:{filter_digest}"
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            header = await transaction.fetch_one(_PROJECT_HEADER_SQL, (tenant_id, project_id))
            if header is None:
                raise ProjectNotFoundError()
            rows = await transaction.fetch_all(
                _DIMENSIONAL_ATTRIBUTES_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        project_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.dimensional_entity_id,
                    filters.dimensional_entity_id,
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
        return DimensionalAttributePage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(
                DimensionalAttributeSummary.model_validate(row) for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_attribute_id: int,
    ) -> DimensionalAttributeDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            row = await transaction.fetch_one(
                _DIMENSIONAL_ATTRIBUTE_DETAIL_SQL,
                (tenant_id, project_id, dimensional_attribute_id),
            )
            if row is None:
                raise DimensionalAttributeNotFoundError()
            source_rows = await transaction.fetch_all(
                DIMENSIONAL_ATTRIBUTE_SOURCES_SQL,
                (tenant_id, project_id, dimensional_attribute_id, MAX_DETAIL_ROWS + 1),
            )
        if len(source_rows) > MAX_DETAIL_ROWS:
            raise DimensionalDetailLimitExceededError()
        return DimensionalAttributeDetail.model_validate(
            {
                **row,
                "sources": tuple(_normalize_attribute_source(item) for item in source_rows),
            },
            strict=False,
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalRelationshipPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_dimensional_relationships:{tenant_id}:{project_id}:{page_size}:{filter_digest}"
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            header = await transaction.fetch_one(_PROJECT_HEADER_SQL, (tenant_id, project_id))
            if header is None:
                raise ProjectNotFoundError()
            rows = await transaction.fetch_all(
                _DIMENSIONAL_RELATIONSHIPS_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        project_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.dimensional_entity_id,
                    filters.dimensional_entity_id,
                    filters.dimensional_entity_id,
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
        return DimensionalRelationshipPage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(
                DimensionalRelationshipSummary.model_validate(row) for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_relationship_id: int,
    ) -> DimensionalRelationshipDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            row = await transaction.fetch_one(
                _DIMENSIONAL_RELATIONSHIP_DETAIL_SQL,
                (tenant_id, project_id, dimensional_relationship_id),
            )
        if row is None:
            raise DimensionalRelationshipNotFoundError()
        return DimensionalRelationshipDetail.model_validate(row)


def _list_parameters(
    tenant_id: int,
    project_id: int,
    filters: ModeledFilters,
    page_size: int,
    offset: int,
) -> tuple[object, ...]:
    return (
        tenant_id,
        project_id,
        filters.active,
        filters.active,
        filters.locked,
        filters.locked,
        filters.name_exact,
        filters.name_exact,
        filters.name_prefix,
        filters.name_prefix,
        filters.name_prefix,
        page_size + 1,
        offset,
    )


def _normalize_object_source(row: Mapping[str, object]) -> DimensionalObjectSource:
    common = {
        "dimensional_entity_source_mapping_id": row["dimensional_entity_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "rationale": row["rationale"],
        "is_active": row["is_active"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "logical_entity":
        return DimensionalLogicalEntitySource.model_validate(
            {
                **common,
                "support_source_type": "logical_entity",
                "source_logical_entity": {
                    "logical_entity_id": row["source_logical_entity_id"],
                    "logical_entity_schema_name": row["source_logical_entity_schema_name"],
                    "logical_entity_name": row["source_logical_entity_name"],
                },
            },
            strict=False,
        )
    if row["support_source_type"] != "context_record":
        raise ValueError("Dimensional Object Source has an unsupported source type")
    return DimensionalContextSource.model_validate(
        {
            **common,
            "support_source_type": "context_record",
            "context_record": {
                "context_record_id": row["context_record_id"],
                "context_group_name": row["context_group_name"],
                "context_type_name": row["context_type_name"],
                "context_text": row["context_text"],
                "source_reference": row["source_reference"],
                "status": row["context_record_status"],
            },
        },
        strict=False,
    )


def _normalize_attribute_source(row: Mapping[str, object]) -> DimensionalAttributeSource:
    common = {
        "dimensional_attribute_source_mapping_id": row["dimensional_attribute_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "rationale": row["rationale"],
        "is_active": row["is_active"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "logical_attribute":
        return DimensionalAttributeLogicalSource.model_validate(
            {
                **common,
                "dimensional_entity_source_mapping_id": row["dimensional_entity_source_mapping_id"],
                "support_source_type": "logical_attribute",
                "source_logical_attribute": {
                    "logical_entity_id": row["source_logical_entity_id"],
                    "logical_entity_schema_name": row["source_logical_entity_schema_name"],
                    "logical_entity_name": row["source_logical_entity_name"],
                    "logical_attribute_id": row["source_logical_attribute_id"],
                    "logical_attribute_name": row["source_logical_attribute_name"],
                },
            },
            strict=False,
        )
    if row["support_source_type"] != "context_record":
        raise ValueError("Dimensional Attribute Source has an unsupported source type")
    return DimensionalAttributeContextSource.model_validate(
        {
            **common,
            "support_source_type": "context_record",
            "context_record": {
                "context_record_id": row["context_record_id"],
                "context_group_name": row["context_group_name"],
                "context_type_name": row["context_type_name"],
                "context_text": row["context_text"],
                "source_reference": row["source_reference"],
                "status": row["context_record_status"],
            },
        },
        strict=False,
    )
