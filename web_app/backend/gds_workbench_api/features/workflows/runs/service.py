"""Common, bounded Workflow Run read persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.models import ModelNotFoundError
from gds_workbench_api.features.workflows.runs.contracts import (
    ModelWorkflow,
    RunEventCollection,
    RunEventRecord,
    RunState,
    WorkflowRunCollection,
    WorkflowRunDetail,
    WorkflowRunLedgerRecord,
    WorkflowRunNotFoundError,
)

_MODEL_EXISTS_SQL = """
SELECT model.model_id
  FROM model.model AS model
 WHERE model.tenant_id = %s
   AND model.model_id = %s
   AND model.is_active
"""

_RUNS_SQL = """
SELECT run.workflow_run_id,
       run.model_workflow,
       run.workflow_execution_mode,
       run.modeled_entity_type,
       run.selected_scope_count,
       run.requested_batch_id,
       run.workflow_run_state,
       actor.principal_display_name AS actor_display_name,
       run.created_time AS created_at,
       run.started_time AS started_at,
       run.completed_time AS completed_at
  FROM application.workflow_run AS run
  JOIN model.model AS model
    ON model.model_id = run.model_id
   AND model.tenant_id = %s
  JOIN security.principal AS actor
    ON actor.principal_id = run.actor_principal_id
 WHERE run.model_id = %s
   AND (%s::VARCHAR IS NULL OR run.model_workflow = %s)
   AND (%s::VARCHAR IS NULL OR run.workflow_run_state = %s)
 ORDER BY run.created_time DESC, run.workflow_run_id DESC
 LIMIT %s OFFSET %s
"""

_RUN_DETAIL_SQL = """
SELECT run.workflow_run_id,
       run.model_workflow,
       run.workflow_execution_mode,
       run.modeled_entity_type,
       run.selected_scope_count,
       run.requested_batch_id,
       run.workflow_run_state,
       actor.principal_display_name AS actor_display_name,
       run.created_time AS created_at,
       run.started_time AS started_at,
       run.completed_time AS completed_at,
       run.correlation_id,
       run.agent_sdk_code,
       run.agent_provider_code,
       run.agent_model_code,
       run.reasoning_effort_code,
       run.max_turns,
       run.validation_retry_count,
       run.failure_code,
       run.failure_message,
       change_set.model_change_set_id,
       change_set.model_change_set_status,
       change_set.draft_revision,
       change_set.candidate_digest,
       change_set.validated_time AS validated_at
  FROM application.workflow_run AS run
  JOIN model.model AS model
    ON model.model_id = run.model_id
   AND model.tenant_id = %s
  JOIN security.principal AS actor
    ON actor.principal_id = run.actor_principal_id
  LEFT JOIN mcp.model_change_set AS change_set
    ON change_set.workflow_run_id = run.workflow_run_id
   AND change_set.model_id = run.model_id
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
"""

_RUN_EXISTS_SQL = """
SELECT run.workflow_run_id
  FROM application.workflow_run AS run
  JOIN model.model AS model
    ON model.model_id = run.model_id
   AND model.tenant_id = %s
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
"""

_RUN_EVENTS_SQL = """
SELECT event.model_event_log_sequence AS sequence,
       event.model_event_log_attempt AS attempt,
       event.model_event_log_stage AS stage,
       event.model_event_log_status AS status,
       event.model_event_log_message AS message,
       event.model_event_log_current AS current,
       event.model_event_log_total AS total,
       event.model_event_log_percent AS percent,
       event.finding_count,
       event.created_time AS created_at
  FROM model.model_event_log AS event
  JOIN application.workflow_run AS run
    ON run.workflow_run_id = event.workflow_run_id
   AND run.model_id = event.model_id
  JOIN model.model AS model
    ON model.model_id = run.model_id
   AND model.tenant_id = %s
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND event.model_event_log_sequence > %s
 ORDER BY event.model_event_log_sequence
 LIMIT %s
"""


class WorkflowRunService(Protocol):
    async def list_runs(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow: ModelWorkflow | None,
        run_state: RunState | None,
        page_size: int,
        cursor: str | None,
    ) -> WorkflowRunCollection: ...

    async def read_run(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> WorkflowRunDetail: ...

    async def list_events(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        after_sequence: int,
        page_size: int,
    ) -> RunEventCollection: ...


class WorkflowRunDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseWorkflowRunService:
    def __init__(
        self,
        *,
        database: WorkflowRunDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_runs(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow: ModelWorkflow | None,
        run_state: RunState | None,
        page_size: int,
        cursor: str | None,
    ) -> WorkflowRunCollection:
        collection = f"web_workflow_runs:{tenant_id}:{model_id}:{workflow}:{run_state}:{page_size}"
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
            model = await transaction.fetch_one(
                _MODEL_EXISTS_SQL,
                (tenant_id, model_id),
            )
            if model is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _RUNS_SQL,
                (
                    tenant_id,
                    model_id,
                    workflow,
                    workflow,
                    run_state,
                    run_state,
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
        return WorkflowRunCollection(
            items=tuple(WorkflowRunLedgerRecord.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_run(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> WorkflowRunDetail:
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
                _RUN_DETAIL_SQL,
                (tenant_id, model_id, workflow_run_id),
            )
        if row is None:
            raise WorkflowRunNotFoundError()
        return WorkflowRunDetail.model_validate(row)

    async def list_events(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        after_sequence: int,
        page_size: int,
    ) -> RunEventCollection:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            run = await transaction.fetch_one(
                _RUN_EXISTS_SQL,
                (tenant_id, model_id, workflow_run_id),
            )
            if run is None:
                raise WorkflowRunNotFoundError()
            rows = await transaction.fetch_all(
                _RUN_EVENTS_SQL,
                (tenant_id, model_id, workflow_run_id, after_sequence, page_size),
            )
        items = tuple(RunEventRecord.model_validate(row) for row in rows)
        next_after_sequence = items[-1].sequence if items else after_sequence
        return RunEventCollection(
            items=items,
            next_after_sequence=next_after_sequence,
        )
