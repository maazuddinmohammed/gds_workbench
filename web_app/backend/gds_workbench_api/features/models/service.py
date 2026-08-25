"""Tenant-owned Model read authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

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

_MODELS_SQL = """
SELECT model.model_id,
       model.model_name,
       left(model.model_description, 2000) AS model_description,
       model.model_revision,
       scope.model_scope_object_count,
       latest_run.model_workflow AS latest_workflow,
       latest_run.workflow_run_state AS latest_run_status,
       model.updated_time AS updated_at
  FROM model.model AS model
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS model_scope_object_count
         FROM model.model_scope AS model_scope
        WHERE model_scope.model_id = model.model_id
          AND model_scope.is_active
  ) AS scope
  LEFT JOIN LATERAL (
       SELECT workflow_run.model_workflow,
              workflow_run.workflow_run_state
         FROM application.workflow_run AS workflow_run
        WHERE workflow_run.model_id = model.model_id
        ORDER BY workflow_run.created_time DESC,
                 workflow_run.workflow_run_id DESC
        LIMIT 1
  ) AS latest_run ON TRUE
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
       scope.model_scope_object_count,
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
       SELECT count(*)::INTEGER AS model_scope_object_count
         FROM model.model_scope AS model_scope
        WHERE model_scope.model_id = model.model_id
          AND model_scope.is_active
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
            )
            row = await transaction.fetch_one(
                _MODEL_DETAIL_SQL,
                (tenant_id, model_id),
            )
        if row is None:
            raise ModelNotFoundError()
        return ModelDetail.model_validate(row)
