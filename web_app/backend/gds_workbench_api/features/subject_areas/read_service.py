"""Tenant-owned Subject Area review reads."""

from contextlib import AbstractAsyncContextManager
from typing import Any, LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.projects import ProjectNotFoundError
from gds_workbench_api.features.subject_areas.read_contracts import (
    ScopeTable,
    ScopeTableLimitExceededError,
    ScopeTablePage,
    SubjectAreaDetail,
    SubjectAreaNotFoundError,
    SubjectAreaPage,
    SubjectAreaSummary,
)
from gds_workbench_api.features.workflows.authoring.subject_area_policy import (
    load_subject_area_policy,
)

_MAX_SCOPE_TABLES = 10_000

_PROJECT_HEADER_SQL: LiteralString = """
SELECT target_project.project_revision
  FROM project.project AS target_project
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
"""

# Active Bronze Input Scope tables (the tables Logical runs model), keyed like every
# physical reference, with their column counts and active area memberships.
_SCOPE_TABLES_SQL: LiteralString = """
WITH target_project AS (
    SELECT project.project_id
      FROM project.project AS project
     WHERE project.tenant_id = %s
       AND project.project_id = %s
       AND project.is_active
), eligible_objects AS MATERIALIZED (
    SELECT eligibility.*
      FROM target_project
     CROSS JOIN LATERAL workflow.list_project_object_eligibility(target_project.project_id)
           AS eligibility
), column_counts AS MATERIALIZED (
    SELECT eligibility.object_id, count(*)::INTEGER AS column_count
      FROM target_project
     CROSS JOIN LATERAL workflow.list_project_attribute_eligibility(target_project.project_id)
           AS eligibility
     GROUP BY eligibility.object_id
)
SELECT eligible_object.object_id,
       placement_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       eligible_object.object_schema,
       eligible_object.object_name,
       left(coalesce(enrichment.object_description, object_record.object_description), 2000)
           AS object_description,
       eligible_object.zone_code,
       coalesce(column_counts.column_count, 0) AS column_count,
       coalesce((
           SELECT jsonb_agg(jsonb_build_object(
                      'subject_area_id', area.subject_area_id,
                      'subject_area_name', area.subject_area_name,
                      'subject_area_table_id', membership.subject_area_table_id,
                      'subject_area_table_is_locked', membership.subject_area_table_is_locked
                  ) ORDER BY lower(area.subject_area_name), area.subject_area_id)
             FROM workflow.subject_area_table AS membership
             JOIN workflow.subject_area AS area
               ON area.subject_area_id = membership.subject_area_id
              AND area.project_id = membership.project_id
            WHERE membership.project_id = target_project.project_id
              AND membership.object_id = eligible_object.object_id
              AND membership.subject_area_table_status = 'active'
              AND area.subject_area_status = 'active'
       ), '[]'::JSONB) AS areas
  FROM target_project
  JOIN eligible_objects AS eligible_object
    ON eligible_object.project_id = target_project.project_id
   AND eligible_object.is_project_input_eligible
   AND eligible_object.zone_code = 'bronze'
  JOIN project.project_input_scope AS scope
    ON scope.project_id = target_project.project_id
   AND scope.object_id = eligible_object.object_id
   AND scope.is_active
  JOIN core.object AS object_record
    ON object_record.object_id = eligible_object.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object_record.connection_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  LEFT JOIN workflow.object_enrichment AS enrichment
    ON enrichment.project_id = target_project.project_id
   AND enrichment.object_id = eligible_object.object_id
  LEFT JOIN column_counts
    ON column_counts.object_id = eligible_object.object_id
 ORDER BY lower(eligible_object.object_schema),
          lower(eligible_object.object_name),
          lower(system.system_code),
          eligible_object.object_id
 LIMIT %s
"""

_SUBJECT_AREAS_SQL: LiteralString = """
SELECT area.subject_area_id,
       area.workflow_run_id,
       area.subject_area_name,
       area.subject_area_definition,
       area.subject_area_status,
       area.subject_area_is_locked,
       area.updated_time AS updated_at
  FROM workflow.subject_area AS area
  JOIN project.project AS target_project
    ON target_project.project_id = area.project_id
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
   AND (%s::BIGINT IS NULL OR area.subject_area_id = %s)
 ORDER BY lower(area.subject_area_name), area.subject_area_id
 LIMIT 1001
"""


class SubjectAreaService(Protocol):
    async def list_subject_areas(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> SubjectAreaPage: ...

    async def list_scope_tables(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> ScopeTablePage: ...

    async def read_subject_area(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int, subject_area_id: int
    ) -> SubjectAreaDetail: ...


class SubjectAreaReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseSubjectAreaService:
    """One consistent read of the areas and Scope tables behind each review screen."""

    def __init__(
        self,
        *,
        database: SubjectAreaReadDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def list_subject_areas(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> SubjectAreaPage:
        revision, areas, tables = await self._read(
            principal, tenant_id=tenant_id, project_id=project_id, subject_area_id=None
        )
        return SubjectAreaPage(
            project_id=project_id,
            project_revision=revision,
            max_subject_area_columns=load_subject_area_policy().max_subject_area_columns,
            scope_table_count=len(tables),
            unassigned_table_count=sum(not table.areas for table in tables),
            items=tuple(_summary(area, tables) for area in areas),
        )

    async def list_scope_tables(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> ScopeTablePage:
        revision, _, tables = await self._read(
            principal, tenant_id=tenant_id, project_id=project_id, subject_area_id=None
        )
        return ScopeTablePage(project_id=project_id, project_revision=revision, items=tables)

    async def read_subject_area(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int, subject_area_id: int
    ) -> SubjectAreaDetail:
        revision, areas, tables = await self._read(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            subject_area_id=subject_area_id,
        )
        if not areas:
            raise SubjectAreaNotFoundError()
        summary = _summary(areas[0], tables)
        return SubjectAreaDetail(
            **summary.model_dump(),
            project_id=project_id,
            project_revision=revision,
            max_subject_area_columns=load_subject_area_policy().max_subject_area_columns,
            tables=tuple(
                table
                for table in tables
                if any(area.subject_area_id == subject_area_id for area in table.areas)
            ),
        )

    async def _read(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        subject_area_id: int | None,
    ) -> tuple[int, list[dict[str, Any]], tuple[ScopeTable, ...]]:
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
            areas = await transaction.fetch_all(
                _SUBJECT_AREAS_SQL, (tenant_id, project_id, subject_area_id, subject_area_id)
            )
            rows = await transaction.fetch_all(
                _SCOPE_TABLES_SQL, (tenant_id, project_id, _MAX_SCOPE_TABLES + 1)
            )
        if len(rows) > _MAX_SCOPE_TABLES:
            raise ScopeTableLimitExceededError()
        return (
            header["project_revision"],
            areas,
            tuple(ScopeTable.model_validate(row, strict=False) for row in rows),
        )


def _summary(area: dict[str, Any], tables: tuple[ScopeTable, ...]) -> SubjectAreaSummary:
    members = [
        table
        for table in tables
        if any(item.subject_area_id == area["subject_area_id"] for item in table.areas)
    ]
    return SubjectAreaSummary.model_validate(
        {
            **area,
            "table_count": len(members),
            "column_count": sum(table.column_count for table in members),
        },
        strict=False,
    )


__all__ = [
    "DatabaseSubjectAreaService",
    "SubjectAreaReadDatabase",
    "SubjectAreaService",
]
