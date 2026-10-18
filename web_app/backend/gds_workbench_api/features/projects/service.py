"""Tenant-owned Project read authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
)

from gds_workbench_api.features.projects.contracts import (
    ProjectCollection,
    ProjectDetail,
    ProjectLedgerRecord,
    ProjectNotFoundError,
    ProjectStatus,
)
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates

_PROJECTS_SQL = """
SELECT project.project_id,
       project.project_name,
       left(project.project_description, 2000) AS project_description,
       project.project_revision,
       project.is_locked,
       scope.project_input_scope_object_count,
       latest_run.project_workflow AS latest_workflow,
       CASE WHEN mapping_outcome.has_incomplete_pairs THEN 'partial_results'
            ELSE latest_run.workflow_run_state END AS latest_run_status,
       project.updated_time AS updated_at
  FROM project.project AS project
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS project_input_scope_object_count
         FROM project.project_input_scope AS project_input_scope
        WHERE project_input_scope.project_id = project.project_id
          AND project_input_scope.is_active
  ) AS scope
  LEFT JOIN LATERAL (
       SELECT workflow_run.workflow_run_id,
              workflow_run.project_workflow,
              workflow_run.workflow_run_state
         FROM application.workflow_run AS workflow_run
        WHERE workflow_run.project_id = project.project_id
        ORDER BY workflow_run.created_time DESC,
                 workflow_run.workflow_run_id DESC
        LIMIT 1
  ) AS latest_run ON TRUE
  LEFT JOIN LATERAL (
       -- Match the Run read projection: typed events, one-based frozen ordinal,
       -- exact target count, and only the latest terminal outcome for each pair.
       SELECT EXISTS (
           SELECT 1
             FROM (
                 SELECT row_number() OVER (ORDER BY selection.selection_order) AS ordinal,
                        count(*) OVER () AS pair_count
                   FROM application.workflow_run_mapping_target_selection AS selection
                  WHERE selection.workflow_run_id = latest_run.workflow_run_id
                    AND selection.project_id = project.project_id
             ) AS pair
             CROSS JOIN LATERAL (
                 SELECT event.project_event_log_stage AS stage
                   FROM project.project_event_log AS event
                  WHERE event.workflow_run_id = latest_run.workflow_run_id
                    AND event.project_id = project.project_id
                    AND event.project_event_log_current = pair.ordinal
                    AND event.project_event_log_total = pair.pair_count
                    AND event.project_event_log_stage IN (
                        'mapping.pair_completed', 'mapping.pair_preserved',
                        'mapping.pair_no_source', 'mapping.pair_failed',
                        'mapping.pair_partial', 'mapping.pair_empty'
                    )
                  ORDER BY event.project_event_log_sequence DESC
                  LIMIT 1
             ) AS outcome
            WHERE outcome.stage IN ('mapping.pair_failed', 'mapping.pair_partial')
       ) AS has_incomplete_pairs
  ) AS mapping_outcome ON latest_run.project_workflow = 'mapping'
       AND latest_run.workflow_run_state IN ('completed', 'completed_with_repair')
 WHERE project.tenant_id = %s
   AND project.is_active = %s
 ORDER BY lower(project.project_name), project.project_id
 LIMIT %s OFFSET %s
"""

_PROJECT_DETAIL_SQL = """
SELECT project.project_id,
       project.tenant_id,
       project.project_name,
       project.project_description,
       project.project_revision,
       project.is_locked,
       scope.project_input_scope_object_count,
       project.logical_schemas,
       project.dimensional_schemas,
       project.default_mapping_source_system_id,
       project.logical_entity_scd_type,
       project.dimensional_entity_scd_type,
       project.logical_coverage_threshold_percent,
       project.dimensional_coverage_threshold_percent,
       project.logical_enforce_coverage_threshold,
       project.dimensional_enforce_coverage_threshold,
       project.silver_model_naming_instructions,
       project.silver_model_audit_columns_template,
       project.gold_model_naming_instructions,
       project.gold_model_technical_columns_template,
       project.gold_model_audit_columns_template,
       project.default_agent_sdk_code,
       project.default_agent_provider_code,
       project.default_agent_model_code,
       project.default_reasoning_effort_code,
       project.default_max_turns,
       project.default_validation_retry_count,
       project.is_active,
       project.updated_time AS updated_at
  FROM project.project AS project
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS project_input_scope_object_count
         FROM project.project_input_scope AS project_input_scope
        WHERE project_input_scope.project_id = project.project_id
          AND project_input_scope.is_active
  ) AS scope
 WHERE project.tenant_id = %s
   AND project.project_id = %s
"""


class ProjectService(Protocol):
    async def list_projects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_status: ProjectStatus,
        page_size: int,
        cursor: str | None,
    ) -> ProjectCollection: ...

    async def read_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> ProjectDetail: ...


class ProjectReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseProjectService:
    def __init__(
        self,
        *,
        database: ProjectReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_projects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_status: ProjectStatus,
        page_size: int,
        cursor: str | None,
    ) -> ProjectCollection:
        is_active = project_status == "active"
        collection = f"web_projects:{tenant_id}:{project_status}:{page_size}"
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
            rows = await transaction.fetch_all(
                _PROJECTS_SQL,
                (tenant_id, is_active, page_size + 1, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return ProjectCollection(
            items=tuple(ProjectLedgerRecord.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> ProjectDetail:
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
                _PROJECT_DETAIL_SQL,
                (tenant_id, project_id),
            )
        if row is None:
            raise ProjectNotFoundError()
        detail = ProjectDetail.model_validate(row)
        if (
            detail.gold_model_technical_columns_template is not None
            or detail.gold_model_audit_columns_template is not None
        ):
            technical, audit = effective_gold_templates(
                cast(dict[str, object] | None, detail.gold_model_technical_columns_template),
                cast(dict[str, object] | None, detail.gold_model_audit_columns_template),
            )
            detail = detail.model_copy(
                update={
                    "gold_model_audit_columns_template": {**technical, **audit},
                    "gold_model_technical_columns_template": None,
                }
            )
        return detail
