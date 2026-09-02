"""Read-only, Tenant-scoped Model Workflow Overview persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.models import ModelNotFoundError
from gds_workbench_api.features.workflows.overview.contracts import (
    LedgerWorkflow,
    ModelWorkflowOverview,
    QualityWarningCode,
    WorkflowLedgerEntry,
    WorkflowLedgerState,
    WorkflowMetric,
)

_WORKFLOW_OVERVIEW_SQL = """
WITH target_model AS (
    SELECT model.model_id,
           model.model_revision
      FROM model.model AS model
     WHERE model.tenant_id = %s
       AND model.model_id = %s
       AND model.is_active
), metrics AS (
    SELECT 1 AS workflow_order,
           'scope'::TEXT AS workflow,
           count(scope.model_input_scope_id)::INTEGER AS result_count,
           count(scope.model_input_scope_id) FILTER (
               WHERE scope.model_input_scope_is_locked
           )::INTEGER AS locked_count
      FROM target_model
      LEFT JOIN model.model_input_scope AS scope
        ON scope.model_id = target_model.model_id
       AND scope.is_active
    UNION ALL
    SELECT 2,
           'profiling',
           count(DISTINCT profile.object_id)::INTEGER,
           0::INTEGER
      FROM target_model
      LEFT JOIN workflow.attribute_profile AS profile
        ON profile.model_id = target_model.model_id
    UNION ALL
    SELECT 3,
           'analysis',
           count(result.analysis_result_id) FILTER (
               WHERE result.analysis_result_status = 'active'
           )::INTEGER,
           count(result.analysis_result_id) FILTER (
               WHERE result.analysis_result_status = 'active'
                 AND result.analysis_result_is_locked
           )::INTEGER
      FROM target_model
      LEFT JOIN workflow.analysis_result AS result
        ON result.model_id = target_model.model_id
    UNION ALL
    SELECT 4,
           'assertions',
           count(assertion.modeling_assertion_record_id) FILTER (
               WHERE assertion.modeling_assertion_record_status
                     = 'active'
           )::INTEGER,
           count(assertion.modeling_assertion_record_id) FILTER (
               WHERE assertion.modeling_assertion_record_status
                     = 'active'
                 AND assertion.modeling_assertion_record_is_locked
           )::INTEGER
      FROM target_model
      LEFT JOIN model.modeling_assertion_record AS assertion
        ON assertion.model_id = target_model.model_id
    UNION ALL
    SELECT 5,
           'conceptual',
           count(conceptual.conceptual_object_id) FILTER (
               WHERE conceptual.conceptual_object_status = 'active'
           )::INTEGER,
           count(conceptual.conceptual_object_id) FILTER (
               WHERE conceptual.conceptual_object_status = 'active'
                 AND conceptual.conceptual_object_is_locked
           )::INTEGER
      FROM target_model
      LEFT JOIN workflow.conceptual_object AS conceptual
        ON conceptual.model_id = target_model.model_id
    UNION ALL
    SELECT 6,
           'logical',
           count(logical.logical_entity_id) FILTER (
               WHERE logical.logical_entity_status = 'active'
           )::INTEGER,
           count(logical.logical_entity_id) FILTER (
               WHERE logical.logical_entity_status = 'active'
                 AND logical.logical_entity_is_locked
           )::INTEGER
      FROM target_model
      LEFT JOIN workflow.logical_entity AS logical
        ON logical.model_id = target_model.model_id
    UNION ALL
    SELECT 7,
           'dimensional',
           count(dimensional.dimensional_entity_id) FILTER (
               WHERE dimensional.dimensional_entity_status = 'active'
           )::INTEGER,
           count(dimensional.dimensional_entity_id) FILTER (
               WHERE dimensional.dimensional_entity_status = 'active'
                 AND dimensional.dimensional_entity_is_locked
           )::INTEGER
      FROM target_model
      LEFT JOIN workflow.dimensional_entity AS dimensional
        ON dimensional.model_id = target_model.model_id
), latest_run AS (
    SELECT ranked.model_workflow,
           ranked.workflow_run_id,
           ranked.workflow_run_state,
           ranked.created_time
      FROM (
          SELECT run.model_workflow,
                 run.workflow_run_id,
                 run.workflow_run_state,
                 run.created_time,
                 row_number() OVER (
                     PARTITION BY run.model_workflow
                     ORDER BY run.created_time DESC, run.workflow_run_id DESC
                 ) AS run_order
            FROM application.workflow_run AS run
            JOIN target_model
              ON target_model.model_id = run.model_id
      ) AS ranked
     WHERE ranked.run_order = 1
)
SELECT target_model.model_id,
       target_model.model_revision,
       metrics.workflow,
       metrics.result_count,
       metrics.locked_count,
       latest_run.workflow_run_id AS latest_run_id,
       latest_run.workflow_run_state AS latest_run_state,
       latest_run.created_time AS latest_run_created_at
  FROM target_model
 CROSS JOIN metrics
  LEFT JOIN latest_run
    ON latest_run.model_workflow = metrics.workflow
 ORDER BY metrics.workflow_order
"""


class WorkflowOverviewService(Protocol):
    async def read_overview(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelWorkflowOverview: ...


class WorkflowOverviewDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


def _ledger_state(metric: WorkflowMetric) -> WorkflowLedgerState:
    if metric.workflow == "scope":
        return "ready" if metric.result_count else "empty"
    if metric.latest_run_state in ("queued", "running", "failed"):
        return metric.latest_run_state
    if metric.result_count:
        return "results_available"
    if metric.latest_run_state in ("completed", "completed_with_repair"):
        return "completed_no_results"
    return "not_started"


def _quality_warnings(
    metric: WorkflowMetric,
    result_counts: dict[LedgerWorkflow, int],
) -> tuple[QualityWarningCode, ...]:
    if metric.workflow == "profiling" and not result_counts["scope"]:
        return ("scope_empty",)
    if metric.workflow == "analysis" and not result_counts["profiling"]:
        return ("profiling_results_unavailable",)
    if metric.workflow == "logical" and not result_counts["conceptual"]:
        return ("conceptual_results_unavailable",)
    if metric.workflow == "dimensional" and not result_counts["logical"]:
        return ("logical_results_unavailable",)
    return ()


class DatabaseWorkflowOverviewService:
    def __init__(
        self,
        *,
        database: WorkflowOverviewDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def read_overview(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelWorkflowOverview:
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
                _WORKFLOW_OVERVIEW_SQL,
                (tenant_id, model_id),
            )
        if not rows:
            raise ModelNotFoundError()

        metrics = tuple(WorkflowMetric.model_validate(row) for row in rows)
        result_counts: dict[LedgerWorkflow, int] = {
            metric.workflow: metric.result_count for metric in metrics
        }
        items = tuple(
            WorkflowLedgerEntry(
                workflow=metric.workflow,
                result_count=metric.result_count,
                locked_count=metric.locked_count,
                latest_run_id=metric.latest_run_id,
                latest_run_state=metric.latest_run_state,
                latest_run_created_at=metric.latest_run_created_at,
                state=_ledger_state(metric),
                quality_warning_codes=_quality_warnings(metric, result_counts),
            )
            for metric in metrics
        )
        return ModelWorkflowOverview(
            model_id=metrics[0].model_id,
            model_revision=metrics[0].model_revision,
            items=items,
        )
