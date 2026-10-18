"""Authorized read behavior for profiled Objects and Attribute Profiles."""

import json
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction
from pydantic import Field

from gds_workbench_api.features.profiling.read_contracts import (
    AttributeProfile,
    ProfileWorkflowProvenance,
    ProfilingObjectDetail,
    ProfilingObjectFilters,
    ProfilingObjectLedgerItem,
    ProfilingObjectNotFoundError,
    ProfilingObjectPage,
    ReviewContract,
)
from gds_workbench_api.features.projects import ProjectNotFoundError

_PROJECT_HEADER_SQL: LiteralString = """
SELECT target_project.project_id,
       target_project.project_revision
  FROM project.project AS target_project
 WHERE target_project.tenant_id = %s
   AND target_project.project_id = %s
   AND target_project.is_active
"""

_PROFILING_OBJECTS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE},
target_project AS (
    SELECT target_project.project_id
      FROM project.project AS target_project
     WHERE target_project.tenant_id = %s
       AND target_project.project_id = %s
       AND target_project.is_active
)
SELECT profile.object_id,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       system.system_id,
       system.system_code,
       system.system_name,
       connection.connection_id,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       count(profile.attribute_id)::INTEGER AS profiled_attribute_count,
       max(profile.updated_time) AS last_profiled_at
  FROM target_project
  JOIN workflow.attribute_profile AS profile
    ON profile.project_id = target_project.project_id
  JOIN project.project_input_scope AS project_input_scope
    ON project_input_scope.project_id = target_project.project_id
   AND project_input_scope.object_id = profile.object_id
   AND project_input_scope.is_active
  JOIN visible_objects AS visible_object
    ON visible_object.object_id = profile.object_id
  JOIN core.object AS object_record
    ON object_record.object_id = profile.object_id
   AND object_record.is_active
  JOIN core.attribute AS attribute
    ON attribute.attribute_id = profile.attribute_id
   AND attribute.object_id = profile.object_id
   AND attribute.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object_record.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible_object.object_tenant_id
 WHERE (%s::BIGINT IS NULL OR profile.object_id = %s)
   AND (%s::TEXT IS NULL OR lower(source_tenant.tenant_code) = %s)
   AND (%s::TEXT IS NULL OR lower(system.system_code) = %s)
   AND (%s::TEXT IS NULL OR lower(object_record.object_schema) = %s)
   AND (%s::TEXT IS NULL OR lower(object_record.object_name) = %s)
 GROUP BY profile.object_id,
          source_tenant.tenant_id,
          source_tenant.tenant_code,
          source_tenant.tenant_name,
          system.system_id,
          system.system_code,
          system.system_name,
          connection.connection_id,
          connection.connection_code,
          object_record.object_schema,
          object_record.object_name
 ORDER BY lower(source_tenant.tenant_code),
          lower(system.system_code),
          lower(object_record.object_schema),
          lower(object_record.object_name),
          profile.object_id
 LIMIT %s OFFSET %s
"""

_PROFILING_OBJECT_DETAIL_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE},
target_project AS (
    SELECT target_project.project_id
      FROM project.project AS target_project
     WHERE target_project.tenant_id = %s
       AND target_project.project_id = %s
       AND target_project.is_active
)
SELECT profile.object_id,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       system.system_id,
       system.system_code,
       system.system_name,
       connection.connection_id,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       left(object_record.object_description, 2000) AS object_description,
       count(profile.attribute_id)::INTEGER AS profiled_attribute_count,
       max(profile.updated_time) AS last_profiled_at
  FROM target_project
  JOIN workflow.attribute_profile AS profile
    ON profile.project_id = target_project.project_id
  JOIN project.project_input_scope AS project_input_scope
    ON project_input_scope.project_id = target_project.project_id
   AND project_input_scope.object_id = profile.object_id
   AND project_input_scope.is_active
  JOIN visible_objects AS visible_object
    ON visible_object.object_id = profile.object_id
  JOIN core.object AS object_record
    ON object_record.object_id = profile.object_id
   AND object_record.is_active
  JOIN core.attribute AS attribute
    ON attribute.attribute_id = profile.attribute_id
   AND attribute.object_id = profile.object_id
   AND attribute.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object_record.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible_object.object_tenant_id
 WHERE profile.object_id = %s
 GROUP BY profile.object_id,
          source_tenant.tenant_id,
          source_tenant.tenant_code,
          source_tenant.tenant_name,
          system.system_id,
          system.system_code,
          system.system_name,
          connection.connection_id,
          connection.connection_code,
          object_record.object_schema,
          object_record.object_name,
          object_record.object_description
"""

_ATTRIBUTE_PROFILES_SQL: LiteralString = """
WITH target_project AS (
    SELECT target_project.project_id
      FROM project.project AS target_project
     WHERE target_project.tenant_id = %s
       AND target_project.project_id = %s
       AND target_project.is_active
)
SELECT profile.attribute_id,
       attribute.attribute_name,
       attribute.attribute_ordinal_position,
       attribute.attribute_data_type,
       attribute.attribute_inferred_data_type,
       left(attribute.attribute_description, 2000) AS attribute_description,
       profile.agent_run_id,
       profile.workflow_run_id,
       profile.source_context_digest,
       profile.row_count,
       profile.non_null_count,
       profile.null_count,
       profile.blank_count,
       profile.distinct_count,
       profile.min_data_length,
       profile.max_data_length,
       profile.avg_data_length,
       profile.percent_populated,
       profile.percent_duplicates,
       profile.percent_null,
       profile.percent_blank,
       profile.percent_distinct,
       profile.created_time AS created_at,
       profile.updated_time AS updated_at
  FROM target_project
  JOIN workflow.attribute_profile AS profile
    ON profile.project_id = target_project.project_id
  JOIN project.project_input_scope AS project_input_scope
    ON project_input_scope.project_id = target_project.project_id
   AND project_input_scope.object_id = profile.object_id
   AND project_input_scope.is_active
  JOIN core.object AS object_record
    ON object_record.object_id = profile.object_id
   AND object_record.is_active
  JOIN core.attribute AS attribute
    ON attribute.attribute_id = profile.attribute_id
   AND attribute.object_id = profile.object_id
   AND attribute.is_active
 WHERE profile.object_id = %s
 ORDER BY attribute.attribute_ordinal_position,
          lower(attribute.attribute_name),
          profile.attribute_id
 LIMIT %s
"""


class ProfilingReviewService(Protocol):
    async def list_profiling_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: ProfilingObjectFilters,
        page_size: int,
        cursor: str | None,
    ) -> ProfilingObjectPage: ...

    async def read_profiling_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        object_id: int,
    ) -> ProfilingObjectDetail: ...


class ProfilingReviewDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class _ProjectHeader(ReviewContract):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)


class DatabaseProfilingReviewService:
    def __init__(
        self,
        *,
        database: ProfilingReviewDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_profiling_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: ProfilingObjectFilters,
        page_size: int,
        cursor: str | None,
    ) -> ProfilingObjectPage:
        filter_digest = sha256(
            json.dumps(
                {
                    "filters": filters.model_dump(mode="json"),
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        collection = f"web_profiling_objects:{filter_digest}:{page_size}"
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
            header_row = await transaction.fetch_one(
                _PROJECT_HEADER_SQL,
                (tenant_id, project_id),
            )
            if header_row is None:
                raise ProjectNotFoundError()
            rows = await transaction.fetch_all(
                _PROFILING_OBJECTS_SQL,
                (
                    tenant_id,
                    tenant_id,
                    project_id,
                    filters.object_id,
                    filters.object_id,
                    filters.source_tenant_code,
                    filters.source_tenant_code,
                    filters.system_code,
                    filters.system_code,
                    filters.object_schema,
                    filters.object_schema,
                    filters.object_name,
                    filters.object_name,
                    page_size + 1,
                    offset,
                ),
            )

        header = _ProjectHeader.model_validate(header_row)
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return ProfilingObjectPage(
            project_id=header.project_id,
            project_revision=header.project_revision,
            items=tuple(ProfilingObjectLedgerItem.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_profiling_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        object_id: int,
    ) -> ProfilingObjectDetail:
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
            header_row = await transaction.fetch_one(
                _PROJECT_HEADER_SQL,
                (tenant_id, project_id),
            )
            if header_row is None:
                raise ProjectNotFoundError()
            object_row = await transaction.fetch_one(
                _PROFILING_OBJECT_DETAIL_SQL,
                (tenant_id, tenant_id, project_id, object_id),
            )
            if object_row is None:
                raise ProfilingObjectNotFoundError()
            profile_rows = await transaction.fetch_all(
                _ATTRIBUTE_PROFILES_SQL,
                (tenant_id, project_id, object_id, 2001),
            )

        header = _ProjectHeader.model_validate(header_row)
        profiles = tuple(_normalize_attribute_profile(row) for row in profile_rows[:2000])
        return ProfilingObjectDetail.model_validate(
            {
                **object_row,
                "project_id": header.project_id,
                "project_revision": header.project_revision,
                "attribute_profiles": profiles,
                "profiles_truncated": len(profile_rows) > 2000,
            }
        )


def _normalize_attribute_profile(row: dict[str, object]) -> AttributeProfile:
    values = dict(row)
    provenance = ProfileWorkflowProvenance.model_validate(
        {
            "agent_run_id": values.pop("agent_run_id", None),
            "workflow_run_id": values.pop("workflow_run_id", None),
        }
    )
    return AttributeProfile.model_validate({**values, "provenance": provenance})
