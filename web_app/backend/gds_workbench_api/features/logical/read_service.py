"""Tenant-owned normalized Logical model review persistence."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Literal, LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.logical.read_contracts import (
    MAX_DETAIL_ROWS,
    LogicalAttributeContextSource,
    LogicalAttributeDetail,
    LogicalAttributeFilters,
    LogicalAttributeNotFoundError,
    LogicalAttributePage,
    LogicalAttributePhysicalSource,
    LogicalAttributeSource,
    LogicalAttributeSummary,
    LogicalContextSource,
    LogicalDetailLimitExceededError,
    LogicalEntityDetail,
    LogicalEntityFilters,
    LogicalEntityNotFoundError,
    LogicalEntityPage,
    LogicalEntitySource,
    LogicalEntitySummary,
    LogicalObjectSource,
    LogicalRelationshipDetail,
    LogicalRelationshipFilters,
    LogicalRelationshipNotFoundError,
    LogicalRelationshipPage,
    LogicalRelationshipSummary,
    ModeledFilters,
    ModelSubjectArea,
    ModelSubjectAreaPage,
    SubjectAreaBuild,
    WaitingDraft,
)
from gds_workbench_api.features.projects import ProjectNotFoundError

_PROJECT_HEADER_SQL: LiteralString = """
SELECT target_project.project_revision
  FROM project.project AS target_project
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
"""

_LOGICAL_ENTITIES_SQL: LiteralString = """
SELECT entity.logical_entity_id,
       entity.workflow_run_id,
       entity.logical_entity_schema_name,
       entity.logical_entity_name,
       entity.logical_entity_type,
       entity.logical_entity_dependency_order,
       entity.logical_entity_is_active,
       entity.logical_entity_is_locked,
       entity.updated_time AS updated_at
  FROM workflow.logical_entity AS entity
  JOIN project.project AS target_project
    ON target_project.project_id = entity.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BOOLEAN IS NULL OR entity.logical_entity_is_active = %s)
   AND (%s::BOOLEAN IS NULL OR entity.logical_entity_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(entity.logical_entity_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(entity.logical_entity_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR EXISTS (
           SELECT 1
             FROM workflow.logical_entity_source_mapping AS source
             JOIN workflow.subject_area_table AS member
               ON member.project_id = source.project_id
              AND member.object_id = source.source_object_id
              AND member.subject_area_table_is_active
            WHERE source.project_id = entity.project_id
              AND source.logical_entity_id = entity.logical_entity_id
              AND source.logical_entity_source_mapping_is_active
              AND member.subject_area_id = %s
       )
   )
 ORDER BY entity.logical_entity_dependency_order,
          lower(btrim(entity.logical_entity_name)),
          entity.logical_entity_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_ENTITY_DETAIL_SQL: LiteralString = """
SELECT entity.logical_entity_id,
       entity.workflow_run_id,
       entity.logical_entity_schema_name,
       entity.logical_entity_name,
       entity.logical_entity_definition,
       entity.logical_entity_type,
       entity.logical_entity_grain,
       entity.logical_entity_dependency_order,
       entity.logical_entity_is_active,
       entity.logical_entity_is_locked,
       entity.created_time AS created_at,
       entity.updated_time AS updated_at
  FROM workflow.logical_entity AS entity
  JOIN project.project AS target_project
    ON target_project.project_id = entity.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND entity.logical_entity_id = %s
"""

# Active Subject Areas with their active Objects, how many of those are shared with another
# active area or modeled by an active Entity, and the active Entities sourced from them.
_LOGICAL_SUBJECT_AREAS_SQL: LiteralString = """
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
             FROM workflow.subject_area_table AS member
            WHERE member.project_id = area.project_id
              AND member.subject_area_id = area.subject_area_id
              AND member.subject_area_table_is_active
              AND EXISTS (
                  SELECT 1
                    FROM workflow.subject_area_table AS other_member
                    JOIN workflow.subject_area AS other_area
                      ON other_area.project_id = other_member.project_id
                     AND other_area.subject_area_id = other_member.subject_area_id
                     AND other_area.subject_area_is_active
                   WHERE other_member.project_id = member.project_id
                     AND other_member.object_id = member.object_id
                     AND other_member.subject_area_id <> member.subject_area_id
                     AND other_member.subject_area_table_is_active
              )
       ) AS shared_table_count,
       (
           SELECT count(*)
             FROM workflow.subject_area_table AS member
            WHERE member.project_id = area.project_id
              AND member.subject_area_id = area.subject_area_id
              AND member.subject_area_table_is_active
              AND EXISTS (
                  SELECT 1
                    FROM workflow.logical_entity_source_mapping AS source
                    JOIN workflow.logical_entity AS entity
                      ON entity.project_id = source.project_id
                     AND entity.logical_entity_id = source.logical_entity_id
                     AND entity.logical_entity_is_active
                   WHERE source.project_id = member.project_id
                     AND source.source_object_id = member.object_id
                     AND source.logical_entity_source_mapping_is_active
              )
       ) AS modeled_table_count,
       (
           SELECT count(*)
             FROM workflow.logical_entity AS entity
            WHERE entity.project_id = area.project_id
              AND entity.logical_entity_is_active
              AND EXISTS (
                  SELECT 1
                    FROM workflow.logical_entity_source_mapping AS source
                    JOIN workflow.subject_area_table AS member
                      ON member.project_id = source.project_id
                     AND member.object_id = source.source_object_id
                     AND member.subject_area_table_is_active
                   WHERE source.project_id = entity.project_id
                     AND source.logical_entity_id = entity.logical_entity_id
                     AND source.logical_entity_source_mapping_is_active
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

# Per area, the newest Build Run of one layer that decides its state. A cancelled Run, or a
# completed one whose draft was discarded, superseded or expired, is skipped so the Run
# before it decides.
_SUBJECT_AREA_BUILDS_SQL: LiteralString = """
SELECT DISTINCT ON (selection.subject_area_id)
       selection.subject_area_id,
       run.workflow_run_id,
       run.workflow_run_state,
       coalesce(run.started_time, run.created_time) AS started_time,
       run.completed_time,
       change_set.project_change_set_status,
       change_set.validated_time,
       change_set.applied_time
  FROM application.workflow_run_subject_area_selection AS selection
  JOIN application.workflow_run AS run
    ON run.workflow_run_id = selection.workflow_run_id
   AND run.project_id = selection.project_id
  LEFT JOIN mcp.project_change_set AS change_set
    ON change_set.workflow_run_id = run.workflow_run_id
   AND change_set.project_id = run.project_id
 WHERE run.tenant_id = %s
   AND run.project_id = %s
   AND run.project_workflow = %s
   AND run.workflow_operation = 'build'
   AND run.workflow_run_state <> 'cancelled'
   AND NOT (
       run.workflow_run_state IN ('completed', 'completed_with_repair')
       AND change_set.project_change_set_id IS NOT NULL
       AND change_set.project_change_set_status <> 'applied'
       AND NOT (
           change_set.project_change_set_status = 'validated'
           AND change_set.expires_time > clock_timestamp()
       )
   )
 ORDER BY selection.subject_area_id, run.workflow_run_id DESC
"""

# The layer's newest unexpired draft still waiting for Apply, from a Build or an Optimize.
_WAITING_DRAFT_SQL: LiteralString = """
SELECT run.workflow_run_id,
       run.workflow_operation
  FROM application.workflow_run AS run
  JOIN mcp.project_change_set AS change_set
    ON change_set.workflow_run_id = run.workflow_run_id
   AND change_set.project_id = run.project_id
 WHERE run.tenant_id = %s
   AND run.project_id = %s
   AND run.project_workflow = %s
   AND run.workflow_run_state IN ('completed', 'completed_with_repair')
   AND change_set.project_change_set_status = 'validated'
   AND change_set.expires_time > clock_timestamp()
 ORDER BY run.workflow_run_id DESC
 LIMIT 1
"""

# An Entity's Subject Areas are worked out from its active Object sources, never stored.
_LOGICAL_ENTITY_SUBJECT_AREAS_SQL: LiteralString = """
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
         FROM workflow.subject_area_table AS member
         JOIN workflow.logical_entity_source_mapping AS source
           ON source.project_id = member.project_id
          AND source.source_object_id = member.object_id
          AND source.logical_entity_source_mapping_is_active
        WHERE member.project_id = area.project_id
          AND member.subject_area_id = area.subject_area_id
          AND member.subject_area_table_is_active
          AND source.logical_entity_id = %s
   )
 ORDER BY lower(btrim(area.subject_area_name)),
          area.subject_area_id
 LIMIT %s
"""

LOGICAL_ENTITY_SOURCES_SQL: LiteralString = """
SELECT source.logical_entity_source_mapping_id,
       source.workflow_run_id,
       CASE WHEN source.source_object_id IS NOT NULL THEN 'object'
            ELSE 'context_record'
       END AS support_source_type,
       source.logical_entity_source_mapping_rationale AS rationale,
       source.logical_entity_source_mapping_is_active AS is_active,
       source.logical_entity_source_mapping_is_locked AS is_locked,
       source.created_time AS created_at,
       source.updated_time AS updated_at,
       source_object.object_id AS source_object_id,
       source_placement_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       context_record.context_record_id::TEXT AS context_record_id,
       context_group.name AS context_group_name,
       context_type.name AS context_type_name,
       context_record.context_text,
       context_record.source_reference,
       context_record.status AS context_record_status
  FROM workflow.logical_entity_source_mapping AS source
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = source.logical_entity_id
   AND entity.project_id = source.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = source.project_id
  LEFT JOIN core.object AS source_object
    ON source_object.object_id = source.source_object_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  LEFT JOIN LATERAL workflow.list_project_object_eligibility(
      source.project_id
  ) AS source_eligibility
    ON source_eligibility.object_id = source.source_object_id
   AND source_eligibility.is_project_input_eligible
  LEFT JOIN core.tenant AS source_placement_tenant
    ON source_placement_tenant.tenant_id = source_connection.tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
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
   AND source.logical_entity_id = %s
   AND (
       source.source_object_id IS NULL
       OR source_eligibility.object_id IS NOT NULL
   )
 ORDER BY source.logical_entity_source_mapping_id
 LIMIT %s
"""

_LOGICAL_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.logical_attribute_id,
       attribute.workflow_run_id,
       attribute.logical_entity_id,
       entity.logical_entity_schema_name,
       entity.logical_entity_name,
       attribute.logical_attribute_name,
       attribute.logical_attribute_data_type,
       attribute.logical_attribute_is_nullable,
       attribute.logical_attribute_is_natural_key,
       attribute.logical_attribute_is_surrogate_key,
       attribute.logical_attribute_ordinal_position,
       attribute.logical_attribute_is_audit_column,
       attribute.logical_attribute_is_active,
       attribute.logical_attribute_is_locked,
       attribute.updated_time AS updated_at
  FROM workflow.logical_attribute AS attribute
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = attribute.logical_entity_id
   AND entity.project_id = attribute.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = attribute.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BOOLEAN IS NULL OR attribute.logical_attribute_is_active = %s)
   AND (%s::BOOLEAN IS NULL OR attribute.logical_attribute_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(attribute.logical_attribute_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(attribute.logical_attribute_name)),
           char_length(%s)
       ) = %s
   )
   AND (%s::BIGINT IS NULL OR attribute.logical_entity_id = %s)
 ORDER BY lower(btrim(entity.logical_entity_name)),
          attribute.logical_attribute_ordinal_position,
          attribute.logical_attribute_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_ATTRIBUTE_DETAIL_SQL: LiteralString = """
SELECT attribute.logical_attribute_id,
       attribute.workflow_run_id,
       attribute.logical_entity_id,
       entity.logical_entity_schema_name,
       entity.logical_entity_name,
       attribute.logical_attribute_name,
       attribute.logical_attribute_definition,
       attribute.logical_attribute_data_type,
       attribute.logical_attribute_is_nullable,
       attribute.logical_attribute_is_natural_key,
       attribute.logical_attribute_is_surrogate_key,
       attribute.logical_attribute_ordinal_position,
       attribute.logical_attribute_is_audit_column,
       attribute.logical_attribute_is_active,
       attribute.logical_attribute_is_locked,
       attribute.created_time AS created_at,
       attribute.updated_time AS updated_at
  FROM workflow.logical_attribute AS attribute
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = attribute.logical_entity_id
   AND entity.project_id = attribute.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = attribute.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND attribute.logical_attribute_id = %s
"""

LOGICAL_ATTRIBUTE_SOURCES_SQL: LiteralString = """
SELECT source.logical_attribute_source_mapping_id,
       source.workflow_run_id,
       source.logical_entity_source_mapping_id,
       CASE WHEN source.source_attribute_id IS NOT NULL THEN 'attribute'
            ELSE 'context_record'
       END AS support_source_type,
       source.logical_attribute_source_mapping_rationale AS rationale,
       source.logical_attribute_source_mapping_is_active AS is_active,
       source.logical_attribute_source_mapping_is_locked AS is_locked,
       source.created_time AS created_at,
       source.updated_time AS updated_at,
       source_object.object_id AS source_object_id,
       source_attribute.attribute_id AS source_attribute_id,
       source_placement_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_attribute.attribute_name AS source_attribute_name,
       context_record.context_record_id::TEXT AS context_record_id,
       context_group.name AS context_group_name,
       context_type.name AS context_type_name,
       context_record.context_text,
       context_record.source_reference,
       context_record.status AS context_record_status
  FROM workflow.logical_attribute_source_mapping AS source
  JOIN workflow.logical_attribute AS attribute
    ON attribute.logical_attribute_id = source.logical_attribute_id
   AND attribute.logical_entity_id = source.logical_entity_id
   AND attribute.project_id = source.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = source.project_id
  LEFT JOIN core.object AS source_object
    ON source_object.object_id = source.source_object_id
  LEFT JOIN core.attribute AS source_attribute
    ON source_attribute.attribute_id = source.source_attribute_id
   AND source_attribute.object_id = source.source_object_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  LEFT JOIN LATERAL workflow.list_project_attribute_eligibility(
      source.project_id
  ) AS source_eligibility
    ON source_eligibility.object_id = source.source_object_id
   AND source_eligibility.attribute_id = source.source_attribute_id
   AND source_eligibility.is_project_input_eligible
  LEFT JOIN core.tenant AS source_placement_tenant
    ON source_placement_tenant.tenant_id = source_connection.tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
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
   AND source.logical_attribute_id = %s
   AND (
       source.source_attribute_id IS NULL
       OR source_eligibility.attribute_id IS NOT NULL
   )
 ORDER BY source.logical_attribute_source_mapping_id
 LIMIT %s
"""

_LOGICAL_RELATIONSHIPS_SQL: LiteralString = """
SELECT relationship.logical_relationship_id,
       relationship.workflow_run_id,
       relationship.logical_relationship_from_entity_id
           AS from_logical_entity_id,
       from_entity.logical_entity_schema_name AS from_logical_entity_schema_name,
       from_entity.logical_entity_name AS from_logical_entity_name,
       relationship.logical_relationship_from_attribute_id
           AS from_logical_attribute_id,
       from_attribute.logical_attribute_name AS from_logical_attribute_name,
       relationship.logical_relationship_to_entity_id
           AS to_logical_entity_id,
       to_entity.logical_entity_schema_name AS to_logical_entity_schema_name,
       to_entity.logical_entity_name AS to_logical_entity_name,
       relationship.logical_relationship_to_attribute_id
           AS to_logical_attribute_id,
       to_attribute.logical_attribute_name AS to_logical_attribute_name,
       relationship.logical_relationship_cardinality,
       relationship.logical_relationship_is_active,
       relationship.logical_relationship_is_locked,
       relationship.updated_time AS updated_at
  FROM workflow.logical_relationship AS relationship
  JOIN workflow.logical_entity AS from_entity
    ON from_entity.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_entity.project_id = relationship.project_id
  JOIN workflow.logical_attribute AS from_attribute
    ON from_attribute.logical_attribute_id
       = relationship.logical_relationship_from_attribute_id
   AND from_attribute.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_attribute.project_id = relationship.project_id
  JOIN workflow.logical_entity AS to_entity
    ON to_entity.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_entity.project_id = relationship.project_id
  JOIN workflow.logical_attribute AS to_attribute
    ON to_attribute.logical_attribute_id
       = relationship.logical_relationship_to_attribute_id
   AND to_attribute.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_attribute.project_id = relationship.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = relationship.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BOOLEAN IS NULL OR relationship.logical_relationship_is_active = %s)
   AND (%s::BOOLEAN IS NULL OR relationship.logical_relationship_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(from_attribute.logical_attribute_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(from_attribute.logical_attribute_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR relationship.logical_relationship_from_entity_id = %s
       OR relationship.logical_relationship_to_entity_id = %s
   )
 ORDER BY lower(btrim(from_entity.logical_entity_name)),
          lower(btrim(from_attribute.logical_attribute_name)),
          relationship.logical_relationship_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_RELATIONSHIP_DETAIL_SQL: LiteralString = """
SELECT relationship.logical_relationship_id,
       relationship.workflow_run_id,
       relationship.logical_relationship_from_entity_id
           AS from_logical_entity_id,
       from_entity.logical_entity_schema_name AS from_logical_entity_schema_name,
       from_entity.logical_entity_name AS from_logical_entity_name,
       relationship.logical_relationship_from_attribute_id
           AS from_logical_attribute_id,
       from_attribute.logical_attribute_name AS from_logical_attribute_name,
       relationship.logical_relationship_to_entity_id
           AS to_logical_entity_id,
       to_entity.logical_entity_schema_name AS to_logical_entity_schema_name,
       to_entity.logical_entity_name AS to_logical_entity_name,
       relationship.logical_relationship_to_attribute_id
           AS to_logical_attribute_id,
       to_attribute.logical_attribute_name AS to_logical_attribute_name,
       relationship.logical_relationship_cardinality,
       relationship.logical_relationship_basis,
       relationship.logical_relationship_is_active,
       relationship.logical_relationship_is_locked,
       relationship.created_time AS created_at,
       relationship.updated_time AS updated_at
  FROM workflow.logical_relationship AS relationship
  JOIN workflow.logical_entity AS from_entity
    ON from_entity.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_entity.project_id = relationship.project_id
  JOIN workflow.logical_attribute AS from_attribute
    ON from_attribute.logical_attribute_id
       = relationship.logical_relationship_from_attribute_id
   AND from_attribute.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_attribute.project_id = relationship.project_id
  JOIN workflow.logical_entity AS to_entity
    ON to_entity.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_entity.project_id = relationship.project_id
  JOIN workflow.logical_attribute AS to_attribute
    ON to_attribute.logical_attribute_id
       = relationship.logical_relationship_to_attribute_id
   AND to_attribute.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_attribute.project_id = relationship.project_id
  JOIN project.project AS target_project
    ON target_project.project_id = relationship.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND relationship.logical_relationship_id = %s
"""


class LogicalService(Protocol):
    async def list_subject_areas(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> ModelSubjectAreaPage: ...

    async def list_entities(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: LogicalEntityFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalEntityPage: ...

    async def read_entity(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        logical_entity_id: int,
    ) -> LogicalEntityDetail: ...

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: LogicalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalAttributePage: ...

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        logical_attribute_id: int,
    ) -> LogicalAttributeDetail: ...

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: LogicalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalRelationshipPage: ...

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        logical_relationship_id: int,
    ) -> LogicalRelationshipDetail: ...


class LogicalReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseLogicalService:
    def __init__(
        self,
        *,
        database: LogicalReadDatabase,
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
            rows = await transaction.fetch_all(_LOGICAL_SUBJECT_AREAS_SQL, (tenant_id, project_id))
            builds, waiting_draft = await load_subject_area_builds(
                transaction, tenant_id=tenant_id, project_id=project_id, workflow="logical"
            )
        if len(rows) > 1_000:
            raise LogicalDetailLimitExceededError()
        return ModelSubjectAreaPage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(
                ModelSubjectArea.model_validate(
                    {**row, "build": builds.get(row["subject_area_id"], NOT_BUILT)}
                )
                for row in rows
            ),
            waiting_draft=waiting_draft,
        )

    async def list_entities(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: LogicalEntityFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalEntityPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_logical_entities:{tenant_id}:{project_id}:{page_size}:{filter_digest}"
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
                _LOGICAL_ENTITIES_SQL,
                _entity_list_parameters(tenant_id, project_id, filters, page_size, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return LogicalEntityPage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(LogicalEntitySummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_entity(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        logical_entity_id: int,
    ) -> LogicalEntityDetail:
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
                _LOGICAL_ENTITY_DETAIL_SQL,
                (tenant_id, project_id, logical_entity_id),
            )
            if row is None:
                raise LogicalEntityNotFoundError()
            area_rows = await transaction.fetch_all(
                _LOGICAL_ENTITY_SUBJECT_AREAS_SQL,
                (tenant_id, project_id, logical_entity_id, MAX_DETAIL_ROWS + 1),
            )
            source_rows = await transaction.fetch_all(
                LOGICAL_ENTITY_SOURCES_SQL,
                (tenant_id, project_id, logical_entity_id, MAX_DETAIL_ROWS + 1),
            )
        if len(area_rows) > MAX_DETAIL_ROWS or len(source_rows) > MAX_DETAIL_ROWS:
            raise LogicalDetailLimitExceededError()
        return LogicalEntityDetail.model_validate(
            {
                **row,
                "subject_areas": tuple(area_rows),
                "sources": tuple(_normalize_entity_source(item) for item in source_rows),
            },
            strict=False,
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: LogicalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalAttributePage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_logical_attributes:{tenant_id}:{project_id}:{page_size}:{filter_digest}"
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
                _LOGICAL_ATTRIBUTES_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        project_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.logical_entity_id,
                    filters.logical_entity_id,
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
        return LogicalAttributePage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(LogicalAttributeSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        logical_attribute_id: int,
    ) -> LogicalAttributeDetail:
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
                _LOGICAL_ATTRIBUTE_DETAIL_SQL,
                (tenant_id, project_id, logical_attribute_id),
            )
            if row is None:
                raise LogicalAttributeNotFoundError()
            source_rows = await transaction.fetch_all(
                LOGICAL_ATTRIBUTE_SOURCES_SQL,
                (tenant_id, project_id, logical_attribute_id, MAX_DETAIL_ROWS + 1),
            )
        if len(source_rows) > MAX_DETAIL_ROWS:
            raise LogicalDetailLimitExceededError()
        return LogicalAttributeDetail.model_validate(
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
        filters: LogicalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalRelationshipPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_logical_relationships:{tenant_id}:{project_id}:{page_size}:{filter_digest}"
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
                _LOGICAL_RELATIONSHIPS_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        project_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.logical_entity_id,
                    filters.logical_entity_id,
                    filters.logical_entity_id,
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
        return LogicalRelationshipPage(
            project_id=project_id,
            project_revision=header["project_revision"],
            items=tuple(LogicalRelationshipSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        logical_relationship_id: int,
    ) -> LogicalRelationshipDetail:
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
                _LOGICAL_RELATIONSHIP_DETAIL_SQL,
                (tenant_id, project_id, logical_relationship_id),
            )
        if row is None:
            raise LogicalRelationshipNotFoundError()
        return LogicalRelationshipDetail.model_validate(row)


NOT_BUILT = SubjectAreaBuild(state="not_built")


async def load_subject_area_builds(
    transaction: ReadTransaction,
    *,
    tenant_id: int,
    project_id: int,
    workflow: Literal["logical", "dimensional"],
) -> tuple[dict[int, SubjectAreaBuild], WaitingDraft | None]:
    """Each area's deciding Build in one layer, and the layer's draft waiting for Apply."""
    builds: dict[int, SubjectAreaBuild] = {}
    for row in await transaction.fetch_all(
        _SUBJECT_AREA_BUILDS_SQL, (tenant_id, project_id, workflow)
    ):
        run_id = row["workflow_run_id"]
        if row["workflow_run_state"] in ("queued", "running"):
            build = SubjectAreaBuild(
                state="running", workflow_run_id=run_id, at=row["started_time"]
            )
        elif row["workflow_run_state"] == "failed":
            build = SubjectAreaBuild(
                state="failed",
                workflow_run_id=run_id,
                at=row["completed_time"] or row["started_time"],
            )
        elif row["project_change_set_status"] == "validated":
            build = SubjectAreaBuild(
                state="draft_waiting",
                workflow_run_id=run_id,
                at=row["validated_time"] or row["completed_time"],
            )
        else:
            # Its draft was applied, or the Build needed no change.
            build = SubjectAreaBuild(
                state="applied",
                workflow_run_id=run_id,
                at=row["applied_time"] or row["completed_time"],
            )
        builds[row["subject_area_id"]] = build
    waiting = await transaction.fetch_one(_WAITING_DRAFT_SQL, (tenant_id, project_id, workflow))
    return builds, WaitingDraft.model_validate(waiting) if waiting else None


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


def _entity_list_parameters(
    tenant_id: int,
    project_id: int,
    filters: LogicalEntityFilters,
    page_size: int,
    offset: int,
) -> tuple[object, ...]:
    common = _list_parameters(tenant_id, project_id, filters, page_size, offset)
    return (
        *common[:-2],
        filters.subject_area_id,
        filters.subject_area_id,
        *common[-2:],
    )


def _normalize_entity_source(row: Mapping[str, object]) -> LogicalEntitySource:
    common = {
        "logical_entity_source_mapping_id": row["logical_entity_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "rationale": row["rationale"],
        "is_active": row["is_active"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "object":
        return LogicalObjectSource.model_validate(
            {
                **common,
                "support_source_type": "object",
                "source_object": {
                    "object_id": row["source_object_id"],
                    "tenant_code": row["source_tenant_code"],
                    "system_code": row["source_system_code"],
                    "connection_code": row["source_connection_code"],
                    "object_schema": row["source_object_schema"],
                    "object_name": row["source_object_name"],
                },
            },
            strict=False,
        )
    if row["support_source_type"] != "context_record":
        raise ValueError("Logical Entity Source has an unsupported source type")
    return LogicalContextSource.model_validate(
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


def _normalize_attribute_source(row: Mapping[str, object]) -> LogicalAttributeSource:
    common = {
        "logical_attribute_source_mapping_id": row["logical_attribute_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "rationale": row["rationale"],
        "is_active": row["is_active"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "attribute":
        return LogicalAttributePhysicalSource.model_validate(
            {
                **common,
                "logical_entity_source_mapping_id": row["logical_entity_source_mapping_id"],
                "support_source_type": "attribute",
                "source_attribute": {
                    "object_id": row["source_object_id"],
                    "attribute_id": row["source_attribute_id"],
                    "tenant_code": row["source_tenant_code"],
                    "system_code": row["source_system_code"],
                    "connection_code": row["source_connection_code"],
                    "object_schema": row["source_object_schema"],
                    "object_name": row["source_object_name"],
                    "attribute_name": row["source_attribute_name"],
                },
            },
            strict=False,
        )
    if row["support_source_type"] != "context_record":
        raise ValueError("Logical Attribute Source has an unsupported source type")
    return LogicalAttributeContextSource.model_validate(
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
