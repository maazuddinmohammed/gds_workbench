"""Active Model Input Scope read authorization and persistence."""

import json
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
)

from gds_workbench_api.features.model_input_scope.contracts import (
    ModelInputScopeCandidate,
    ModelInputScopeCandidatePage,
    ModelInputScopeDetail,
    ModelInputScopeObject,
    ModelInputScopeObjectNotFoundError,
    ModelInputScopePage,
)
from gds_workbench_api.features.models import ModelNotFoundError

_MODEL_INPUT_SCOPE_HEADER_SQL = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_MODEL_INPUT_SCOPE_SQL = """
SELECT model_input_scope.model_input_scope_id,
       eligible_object.object_id,
       eligible_object.connection_id,
       eligible_object.system_id,
       system.system_code,
       system.system_name,
       eligible_object.object_tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       eligible_object.object_schema,
       eligible_object.object_name,
       eligible_object.zone_code,
       object.batch_attribute_name,
       attribute_count.attribute_count,
       eligible_object.is_model_input_eligible,
       eligible_object.is_dimensional_source_eligible,
       eligible_object.is_logical_mapping_target_eligible,
       eligible_object.is_dimensional_mapping_target_eligible,
       model_input_scope.created_time AS created_at,
       model_input_scope.updated_time AS updated_at
  FROM model.model AS target_model
  JOIN workflow.list_model_object_eligibility(target_model.model_id)
       AS eligible_object
    ON eligible_object.model_id = target_model.model_id
  JOIN model.model_input_scope AS model_input_scope
    ON model_input_scope.model_id = target_model.model_id
   AND model_input_scope.object_id = eligible_object.object_id
   AND model_input_scope.is_active
  JOIN core.object AS object
    ON object.object_id = eligible_object.object_id
  JOIN core.system AS system
    ON system.system_id = eligible_object.system_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = eligible_object.object_tenant_id
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS attribute_count
         FROM core.attribute AS attribute
        WHERE attribute.object_id = eligible_object.object_id
          AND attribute.is_active
  ) AS attribute_count
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::TEXT IS NULL OR eligible_object.zone_code = %s)
   AND (%s::TEXT IS NULL OR lower(system.system_code) = %s)
   AND (%s::TEXT IS NULL OR lower(source_tenant.tenant_code) = %s)
   AND (
       %s::TEXT IS NULL
       OR strpos(lower(btrim(eligible_object.object_name)), %s) > 0
   )
 ORDER BY lower(source_tenant.tenant_code),
          lower(system.system_code),
          lower(eligible_object.object_schema),
          lower(eligible_object.object_name),
          eligible_object.object_id
 LIMIT %s OFFSET %s
"""

_MODEL_INPUT_SCOPE_DETAIL_SQL = """
SELECT model_input_scope.model_input_scope_id,
       eligible_object.object_id,
       eligible_object.connection_id,
       eligible_object.system_id,
       system.system_code,
       system.system_name,
       eligible_object.object_tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       eligible_object.object_schema,
       eligible_object.object_name,
       eligible_object.zone_code,
       object.batch_attribute_name,
       attribute_count.attribute_count,
       eligible_object.is_model_input_eligible,
       eligible_object.is_dimensional_source_eligible,
       eligible_object.is_logical_mapping_target_eligible,
       eligible_object.is_dimensional_mapping_target_eligible,
       model_input_scope.created_time AS created_at,
       model_input_scope.updated_time AS updated_at
  FROM model.model AS target_model
  JOIN workflow.list_model_object_eligibility(target_model.model_id)
       AS eligible_object
    ON eligible_object.model_id = target_model.model_id
  JOIN model.model_input_scope AS model_input_scope
    ON model_input_scope.model_id = target_model.model_id
   AND model_input_scope.object_id = eligible_object.object_id
   AND model_input_scope.is_active
  JOIN core.object AS object
    ON object.object_id = eligible_object.object_id
  JOIN core.system AS system
    ON system.system_id = eligible_object.system_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = eligible_object.object_tenant_id
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS attribute_count
         FROM core.attribute AS attribute
        WHERE attribute.object_id = eligible_object.object_id
          AND attribute.is_active
  ) AS attribute_count
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND eligible_object.object_id = %s
   AND target_model.is_active
"""

_MODEL_INPUT_SCOPE_ATTRIBUTES_SQL = """
SELECT attribute.attribute_id,
       attribute.attribute_name,
       attribute.attribute_ordinal_position,
       left(attribute.attribute_description, 2000) AS attribute_description,
       attribute.attribute_data_type,
       attribute.attribute_nullability,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
       attribute.is_active
  FROM core.attribute AS attribute
 WHERE attribute.object_id = %s
   AND attribute.is_active
 ORDER BY attribute.attribute_ordinal_position,
          lower(attribute.attribute_name),
          attribute.attribute_id
LIMIT 2000
"""

_MODEL_INPUT_SCOPE_CANDIDATES_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       connection.connection_id,
       system.system_id,
       system.system_code,
       system.system_name,
       visible_objects.object_tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       object.object_schema,
       object.object_name,
       lower(btrim(zone.zone_code)) AS zone_code,
       object.batch_attribute_name,
       attribute_count.attribute_count,
       EXISTS (
           SELECT 1
             FROM model.model_input_scope AS active_scope
            WHERE active_scope.model_id = target_model.model_id
              AND active_scope.object_id = object.object_id
              AND active_scope.is_active
       ) AS is_in_active_scope
  FROM requested_tenant
  JOIN model.model AS target_model
    ON target_model.tenant_id = requested_tenant.tenant_id
   AND target_model.model_id = %s
   AND target_model.is_active
  JOIN visible_objects
    ON TRUE
  JOIN core.object AS object
    ON object.object_id = visible_objects.object_id
   AND object.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
   AND connection.is_active
  JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible_objects.object_tenant_id
   AND source_tenant.is_active
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
   AND zone.is_active
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS attribute_count
         FROM core.attribute AS attribute
        WHERE attribute.object_id = object.object_id
          AND attribute.is_active
  ) AS attribute_count
 WHERE (%s::TEXT IS NULL OR lower(btrim(zone.zone_code)) = %s)
   AND lower(btrim(zone.zone_code)) IN ('source', 'bronze')
   AND (%s::TEXT IS NULL OR lower(btrim(system.system_code)) = %s)
   AND (%s::TEXT IS NULL OR lower(btrim(source_tenant.tenant_code)) = %s)
   AND (
       %s::TEXT IS NULL
       OR strpos(lower(btrim(object.object_name)), %s) > 0
   )
 ORDER BY lower(btrim(source_tenant.tenant_code)),
          lower(btrim(system.system_code)),
          lower(btrim(object.object_schema)),
          lower(btrim(object.object_name)),
          object.object_id
 LIMIT %s OFFSET %s
"""


class ModelInputScopeService(Protocol):
    async def list_candidates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        zone_code: str | None,
        system_code: str | None,
        source_tenant_code: str | None,
        object_name: str | None,
        page_size: int,
        cursor: str | None,
    ) -> ModelInputScopeCandidatePage: ...

    async def list_input_scope(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        zone_code: str | None,
        system_code: str | None,
        source_tenant_code: str | None,
        object_name: str | None,
        page_size: int,
        cursor: str | None,
    ) -> ModelInputScopePage: ...

    async def read_input_scope_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        object_id: int,
    ) -> ModelInputScopeDetail: ...


class ModelInputScopeReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseModelInputScopeService:
    def __init__(
        self,
        *,
        database: ModelInputScopeReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_candidates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        zone_code: str | None,
        system_code: str | None,
        source_tenant_code: str | None,
        object_name: str | None,
        page_size: int,
        cursor: str | None,
    ) -> ModelInputScopeCandidatePage:
        filters = {
            "model_id": model_id,
            "object_name": object_name,
            "source_tenant_code": source_tenant_code,
            "system_code": system_code,
            "tenant_id": tenant_id,
            "zone_code": zone_code,
        }
        filter_digest = sha256(
            json.dumps(filters, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        collection = f"web_model_input_scope_candidates:{filter_digest}:{page_size}"
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
            header = await transaction.fetch_one(
                _MODEL_INPUT_SCOPE_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _MODEL_INPUT_SCOPE_CANDIDATES_SQL,
                (
                    tenant_id,
                    model_id,
                    zone_code,
                    zone_code,
                    system_code,
                    system_code,
                    source_tenant_code,
                    source_tenant_code,
                    object_name,
                    object_name,
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
        return ModelInputScopeCandidatePage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(ModelInputScopeCandidate.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def list_input_scope(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        zone_code: str | None,
        system_code: str | None,
        source_tenant_code: str | None,
        object_name: str | None,
        page_size: int,
        cursor: str | None,
    ) -> ModelInputScopePage:
        filters = {
            "model_id": model_id,
            "object_name": object_name,
            "source_tenant_code": source_tenant_code,
            "system_code": system_code,
            "tenant_id": tenant_id,
            "zone_code": zone_code,
        }
        filter_digest = sha256(
            json.dumps(filters, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        collection = f"web_model_input_scope:{filter_digest}:{page_size}"
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
            header = await transaction.fetch_one(
                _MODEL_INPUT_SCOPE_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _MODEL_INPUT_SCOPE_SQL,
                (
                    tenant_id,
                    model_id,
                    zone_code,
                    zone_code,
                    system_code,
                    system_code,
                    source_tenant_code,
                    source_tenant_code,
                    object_name,
                    object_name,
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
        return ModelInputScopePage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(ModelInputScopeObject.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_input_scope_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        object_id: int,
    ) -> ModelInputScopeDetail:
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
                _MODEL_INPUT_SCOPE_DETAIL_SQL,
                (tenant_id, model_id, object_id),
            )
            if row is None:
                raise ModelInputScopeObjectNotFoundError()
            attributes = await transaction.fetch_all(
                _MODEL_INPUT_SCOPE_ATTRIBUTES_SQL,
                (object_id,),
            )
        return ModelInputScopeDetail.model_validate({**row, "attributes": attributes})
