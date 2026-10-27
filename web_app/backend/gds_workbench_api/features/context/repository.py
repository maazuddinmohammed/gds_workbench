"""Authorized, bounded PostgreSQL reads for Project Context."""

from collections.abc import Sequence
from typing import LiteralString, Protocol

from gds_etl_workbench.infrastructure.postgres import ReadTransaction

from .contracts import (
    ContextGroupDetail,
    ContextGroupFilters,
    ContextGroupNotFoundError,
    ContextGroupSummary,
    ContextPayloadNotSafeError,
    ContextRecordDetail,
    ContextRecordFilters,
    ContextRecordNotFoundError,
    ContextRecordSummary,
    ContextType,
    SourceSystemReference,
)

_PROJECT_REVISION_SQL = """
SELECT project_revision FROM project.project
 WHERE tenant_id = %s AND project_id = %s AND is_active
"""
_CONTEXT_TYPES_SQL = """
SELECT context_type.context_type_id, context_type.name AS context_type_name,
       context_type.description AS context_type_description,
       ARRAY(
           SELECT routing.project_workflow::TEXT
             FROM reference.context_type_workflow AS routing
            WHERE routing.context_type_id = context_type.context_type_id
            ORDER BY routing.project_workflow
       ) AS context_type_workflows
  FROM reference.context_type
 ORDER BY lower(btrim(context_type.name)), context_type.context_type_id
"""
_SOURCE_SYSTEMS_SQL = """
SELECT system_id, system_code, system_name
  FROM core.system
 WHERE is_active
 ORDER BY lower(btrim(system_code)), system_id
 LIMIT %s OFFSET %s
"""
_TYPE_JSON: LiteralString = """jsonb_build_object(
    'context_type_id', context_type.context_type_id,
    'context_type_name', context_type.name,
    'context_type_description', context_type.description
)"""
_SYSTEM_JSON: LiteralString = """CASE WHEN source_system.system_id IS NULL THEN NULL ELSE
jsonb_build_object('system_id', source_system.system_id,
                  'system_code', source_system.system_code,
                  'system_name', source_system.system_name) END"""
_GROUP_JSON: LiteralString = f"""jsonb_build_object(
    'context_group_id', context_group.context_group_id,
    'context_group_name', context_group.name,
    'context_type', {_TYPE_JSON},
    'source_system', {_SYSTEM_JSON},
    'is_active', context_group.is_active
)"""
_GROUP_FROM: LiteralString = """
  FROM project.context_group AS context_group
  JOIN project.project AS owned_project
    ON owned_project.project_id = context_group.project_id
  JOIN reference.context_type AS context_type
    ON context_type.context_type_id = context_group.context_type_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = context_group.source_system_id
"""
_GROUP_COUNTS: LiteralString = """
  LEFT JOIN LATERAL (
    SELECT count(*)::INTEGER AS record_count,
           count(*) FILTER (WHERE record.status = 'active')::INTEGER AS active_record_count,
           count(*) FILTER (WHERE record.is_locked)::INTEGER AS locked_record_count
      FROM project.context_record AS record
     WHERE record.project_id = context_group.project_id
       AND record.context_group_id = context_group.context_group_id
  ) AS counts ON TRUE
"""
_GROUP_COLUMNS: LiteralString = f"""
SELECT context_group.context_group_id, context_group.name AS context_group_name,
       {_TYPE_JSON} AS context_type, {_SYSTEM_JSON} AS source_system,
       context_group.is_active, counts.record_count, counts.active_record_count,
       counts.locked_record_count, context_group.updated_time AS updated_at
"""
_GROUPS_SQL: LiteralString = f"""
{_GROUP_COLUMNS}
{_GROUP_FROM}
{_GROUP_COUNTS}
 WHERE owned_project.tenant_id = %s AND owned_project.project_id = %s
   AND owned_project.is_active
   AND (%s::BIGINT IS NULL OR context_group.context_type_id = %s)
   AND (%s::BIGINT IS NULL OR context_group.source_system_id = %s)
   AND (%s::BOOLEAN IS NULL OR context_group.is_active = %s)
   AND (%s::VARCHAR IS NULL OR starts_with(lower(btrim(context_group.name)), %s))
 ORDER BY lower(btrim(context_group.name)), context_group.context_group_id
 LIMIT %s OFFSET %s
"""
_GROUP_DETAIL_SQL: LiteralString = f"""
{_GROUP_COLUMNS}, context_group.description AS context_group_description,
context_group.created_time AS created_at
{_GROUP_FROM}
{_GROUP_COUNTS}
 WHERE owned_project.tenant_id = %s AND owned_project.project_id = %s
   AND owned_project.is_active AND context_group.context_group_id = %s
"""
_RECORD_COLUMNS: LiteralString = f"""
SELECT record.context_record_id::TEXT AS context_record_id,
       {_GROUP_JSON} AS "group", left(record.context_text, 500) AS context_text_preview,
       char_length(record.context_text) > 500 AS text_truncated,
       left(record.source_reference, 500) AS source_reference_preview,
       coalesce(char_length(record.source_reference) > 500, FALSE) AS source_reference_truncated,
       record.status, record.is_locked, record.updated_time AS updated_at
"""
_RECORD_FROM: LiteralString = """
  FROM project.context_record AS record
  JOIN project.context_group AS context_group
    ON context_group.project_id = record.project_id
   AND context_group.context_group_id = record.context_group_id
  JOIN project.project AS owned_project ON owned_project.project_id = record.project_id
  JOIN reference.context_type AS context_type
    ON context_type.context_type_id = context_group.context_type_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = context_group.source_system_id
"""
_RECORDS_SQL: LiteralString = f"""
{_RECORD_COLUMNS}
{_RECORD_FROM}
 WHERE owned_project.tenant_id = %s AND owned_project.project_id = %s
   AND owned_project.is_active
   AND (%s::BIGINT IS NULL OR record.context_group_id = %s)
   AND (%s::BIGINT IS NULL OR context_group.context_type_id = %s)
   AND (%s::BIGINT IS NULL OR context_group.source_system_id = %s)
   AND (%s::VARCHAR IS NULL OR record.status = %s)
   AND (%s::BOOLEAN IS NULL OR record.is_locked = %s)
   AND (%s::VARCHAR IS NULL OR strpos(lower(record.context_text), %s) > 0)
 ORDER BY context_group.name, record.created_time, record.context_record_id
 LIMIT %s OFFSET %s
"""
_RECORD_DETAIL_SQL: LiteralString = f"""
{_RECORD_COLUMNS}, record.created_time AS created_at,
       CASE WHEN char_length(record.context_text) <= 262144
            THEN record.context_text ELSE NULL END AS context_text,
       char_length(record.context_text) > 262144 AS text_is_oversized,
       CASE WHEN octet_length(record.source_reference) <= 65536
            THEN record.source_reference ELSE NULL END AS source_reference,
       coalesce(octet_length(record.source_reference) > 65536, FALSE) AS source_is_oversized
{_RECORD_FROM}
 WHERE owned_project.tenant_id = %s AND owned_project.project_id = %s
   AND owned_project.is_active AND record.context_record_id = %s::UUID
"""


class ContextRepository(Protocol):
    async def read_project_revision(
        self, transaction: ReadTransaction, *, tenant_id: int, project_id: int
    ) -> int | None: ...
    async def list_types(self, transaction: ReadTransaction) -> Sequence[ContextType]: ...
    async def list_source_systems(
        self, transaction: ReadTransaction, *, limit: int, offset: int
    ) -> Sequence[SourceSystemReference]: ...
    async def list_groups(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextGroupFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ContextGroupSummary]: ...
    async def read_group(
        self, transaction: ReadTransaction, *, tenant_id: int, project_id: int, group_id: int
    ) -> ContextGroupDetail: ...
    async def list_records(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextRecordFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ContextRecordSummary]: ...
    async def read_record(
        self, transaction: ReadTransaction, *, tenant_id: int, project_id: int, record_id: str
    ) -> ContextRecordDetail: ...


class PostgresContextRepository:
    async def read_project_revision(
        self, transaction: ReadTransaction, *, tenant_id: int, project_id: int
    ) -> int | None:
        row = await transaction.fetch_one(_PROJECT_REVISION_SQL, (tenant_id, project_id))
        return None if row is None else int(row["project_revision"])

    async def list_types(self, transaction: ReadTransaction) -> Sequence[ContextType]:
        rows = await transaction.fetch_all(_CONTEXT_TYPES_SQL, ())
        return tuple(ContextType.model_validate(row, strict=False) for row in rows)

    async def list_source_systems(
        self, transaction: ReadTransaction, *, limit: int, offset: int
    ) -> Sequence[SourceSystemReference]:
        rows = await transaction.fetch_all(_SOURCE_SYSTEMS_SQL, (limit, offset))
        return tuple(SourceSystemReference.model_validate(row, strict=False) for row in rows)

    async def list_groups(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextGroupFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ContextGroupSummary]:
        rows = await transaction.fetch_all(
            _GROUPS_SQL,
            (
                tenant_id,
                project_id,
                filters.context_type_id,
                filters.context_type_id,
                filters.source_system_id,
                filters.source_system_id,
                filters.active,
                filters.active,
                filters.name_prefix,
                filters.name_prefix,
                limit,
                offset,
            ),
        )
        return tuple(ContextGroupSummary.model_validate(row, strict=False) for row in rows)

    async def read_group(
        self, transaction: ReadTransaction, *, tenant_id: int, project_id: int, group_id: int
    ) -> ContextGroupDetail:
        row = await transaction.fetch_one(_GROUP_DETAIL_SQL, (tenant_id, project_id, group_id))
        if row is None:
            raise ContextGroupNotFoundError()
        return ContextGroupDetail.model_validate(row, strict=False)

    async def list_records(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextRecordFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ContextRecordSummary]:
        rows = await transaction.fetch_all(
            _RECORDS_SQL,
            (
                tenant_id,
                project_id,
                filters.group_id,
                filters.group_id,
                filters.context_type_id,
                filters.context_type_id,
                filters.source_system_id,
                filters.source_system_id,
                filters.status,
                filters.status,
                filters.locked,
                filters.locked,
                filters.text_search,
                filters.text_search,
                limit,
                offset,
            ),
        )
        return tuple(ContextRecordSummary.model_validate(row, strict=False) for row in rows)

    async def read_record(
        self, transaction: ReadTransaction, *, tenant_id: int, project_id: int, record_id: str
    ) -> ContextRecordDetail:
        row = await transaction.fetch_one(_RECORD_DETAIL_SQL, (tenant_id, project_id, record_id))
        if row is None:
            raise ContextRecordNotFoundError()
        values = dict(row)
        if values.pop("text_is_oversized") or values.pop("source_is_oversized"):
            raise ContextPayloadNotSafeError()
        return ContextRecordDetail.model_validate(values, strict=False)
