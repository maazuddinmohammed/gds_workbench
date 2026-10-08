"""Tenant-owned Model read authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
)

from gds_workbench_api.features.models.contracts import (
    ModelCollection,
    ModelDetail,
    ModelLedgerRecord,
    ModelNotFoundError,
    ModelStatus,
)
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates

_MODELS_SQL = """
SELECT model.model_id,
       model.model_name,
       left(model.model_description, 2000) AS model_description,
       model.model_revision,
       model.is_locked,
       scope.model_input_scope_object_count,
       latest_run.model_workflow AS latest_workflow,
       CASE WHEN mapping_outcome.has_incomplete_pairs THEN 'partial_results'
            ELSE latest_run.workflow_run_state END AS latest_run_status,
       model.updated_time AS updated_at
  FROM model.model AS model
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS model_input_scope_object_count
         FROM model.model_input_scope AS model_input_scope
        WHERE model_input_scope.model_id = model.model_id
          AND model_input_scope.is_active
  ) AS scope
  LEFT JOIN LATERAL (
       SELECT workflow_run.workflow_run_id,
              workflow_run.model_workflow,
              workflow_run.workflow_run_state
         FROM application.workflow_run AS workflow_run
        WHERE workflow_run.model_id = model.model_id
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
                    AND selection.model_id = model.model_id
             ) AS pair
             CROSS JOIN LATERAL (
                 SELECT event.model_event_log_stage AS stage
                   FROM model.model_event_log AS event
                  WHERE event.workflow_run_id = latest_run.workflow_run_id
                    AND event.model_id = model.model_id
                    AND event.model_event_log_current = pair.ordinal
                    AND event.model_event_log_total = pair.pair_count
                    AND event.model_event_log_stage IN (
                        'mapping.pair_completed', 'mapping.pair_preserved',
                        'mapping.pair_no_source', 'mapping.pair_failed',
                        'mapping.pair_partial', 'mapping.pair_empty'
                    )
                  ORDER BY event.model_event_log_sequence DESC
                  LIMIT 1
             ) AS outcome
            WHERE outcome.stage IN ('mapping.pair_failed', 'mapping.pair_partial')
       ) AS has_incomplete_pairs
  ) AS mapping_outcome ON latest_run.model_workflow = 'mapping'
       AND latest_run.workflow_run_state IN ('completed', 'completed_with_repair')
 WHERE model.tenant_id = %s
   AND model.is_active = %s
 ORDER BY lower(model.model_name), model.model_id
 LIMIT %s OFFSET %s
"""

_MODEL_DETAIL_SQL = """
SELECT model.model_id,
       model.tenant_id,
       model.model_name,
       model.model_description,
       model.model_revision,
       model.is_locked,
       scope.model_input_scope_object_count,
       model.logical_schemas,
       model.dimensional_schemas,
       model.default_mapping_source_system_id,
       model.logical_entity_scd_type,
       model.dimensional_entity_scd_type,
       model.logical_coverage_threshold_percent,
       model.dimensional_coverage_threshold_percent,
       model.silver_model_naming_instructions,
       model.silver_model_audit_columns_template,
       model.gold_model_naming_instructions,
       model.gold_model_technical_columns_template,
       model.gold_model_audit_columns_template,
       model.default_agent_sdk_code,
       model.default_agent_provider_code,
       model.default_agent_model_code,
       model.default_reasoning_effort_code,
       model.default_max_turns,
       model.default_validation_retry_count,
       model.is_active,
       model.updated_time AS updated_at
  FROM model.model AS model
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS model_input_scope_object_count
         FROM model.model_input_scope AS model_input_scope
        WHERE model_input_scope.model_id = model.model_id
          AND model_input_scope.is_active
  ) AS scope
 WHERE model.tenant_id = %s
   AND model.model_id = %s
"""


class ModelService(Protocol):
    async def list_models(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_status: ModelStatus,
        page_size: int,
        cursor: str | None,
    ) -> ModelCollection: ...

    async def read_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelDetail: ...


class ModelReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseModelService:
    def __init__(
        self,
        *,
        database: ModelReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_models(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_status: ModelStatus,
        page_size: int,
        cursor: str | None,
    ) -> ModelCollection:
        is_active = model_status == "active"
        collection = f"web_models:{tenant_id}:{model_status}:{page_size}"
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
                _MODELS_SQL,
                (tenant_id, is_active, page_size + 1, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return ModelCollection(
            items=tuple(ModelLedgerRecord.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelDetail:
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
            row = await transaction.fetch_one(
                _MODEL_DETAIL_SQL,
                (tenant_id, model_id),
            )
        if row is None:
            raise ModelNotFoundError()
        detail = ModelDetail.model_validate(row)
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
