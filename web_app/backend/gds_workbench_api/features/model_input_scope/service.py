"""Active Model Input Scope read authorization and persistence."""

import json
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
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
    ScopeLocation,
    ScopeSearchOptions,
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
       left(object.object_description, 2000) AS object_description,
       coalesce(length(object.object_description) > 2000, FALSE) AS description_truncated,
       object.is_locked,
       NULL::TEXT AS review_revision,
       object.batch_attribute_name,
       attribute_count.attribute_count,
       eligible_object.is_model_input_eligible,
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
       OR strpos(
           lower(btrim(eligible_object.object_schema) || '.' || btrim(eligible_object.object_name)),
           %s
       ) > 0
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
       left(object.object_description, 2000) AS object_description,
       coalesce(length(object.object_description) > 2000, FALSE) AS description_truncated,
       object.is_locked,
       NULL::TEXT AS review_revision,
       object.batch_attribute_name,
       attribute_count.attribute_count,
       attribute_count.total_attribute_count,
       eligible_object.is_model_input_eligible,
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
       SELECT (count(*) FILTER (WHERE attribute.is_active))::INTEGER AS attribute_count,
              count(*)::INTEGER AS total_attribute_count
         FROM core.attribute AS attribute
        WHERE attribute.object_id = eligible_object.object_id
  ) AS attribute_count
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND eligible_object.object_id = %s
   AND target_model.is_active
"""

_MODEL_INPUT_SCOPE_ATTRIBUTES_SQL = """
SELECT attribute.attribute_id,
       NULL::TEXT AS review_revision,
       attribute.attribute_name,
       attribute.attribute_ordinal_position,
       left(attribute.attribute_description, 2000) AS attribute_description,
       coalesce(length(attribute.attribute_description) > 2000, FALSE) AS description_truncated,
       attribute.attribute_data_type,
       attribute.attribute_inferred_data_type,
       attribute.attribute_nullability,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
       attribute.is_locked,
       attribute.is_active
  FROM core.attribute AS attribute
  JOIN core.object AS object
    ON object.object_id = attribute.object_id
 WHERE attribute.object_id = %s
   AND attribute.is_active
 ORDER BY attribute.attribute_ordinal_position,
          lower(attribute.attribute_name),
          attribute.attribute_id
"""

# Enrichment reuses the authorized scope ledger, with Model-owned values and witnesses.
_ENRICHMENT_OBJECT_SQL: tuple[LiteralString, ...] = tuple(
    (
        statement.replace("object.object_description", "enrichment.object_description")
        .replace("object.is_locked,", "coalesce(enrichment.is_locked, FALSE) AS is_locked,")
        .replace(
            "NULL::TEXT AS review_revision",
            "workflow.enrichment_review_revision(target_model.model_id, object.object_id) "
            "AS review_revision",
        )
        .replace(
            "  JOIN core.system AS system",
            """
  LEFT JOIN workflow.object_enrichment AS enrichment
    ON enrichment.model_id = target_model.model_id AND enrichment.object_id = object.object_id
  JOIN core.system AS system""",
        )
    )
    for statement in (_MODEL_INPUT_SCOPE_SQL, _MODEL_INPUT_SCOPE_DETAIL_SQL)
)
_ENRICHMENT_ATTRIBUTES_SQL: LiteralString = (
    "WITH requested_model AS (SELECT %s::BIGINT AS model_id) "
    + _MODEL_INPUT_SCOPE_ATTRIBUTES_SQL.replace(
        "NULL::TEXT AS review_revision",
        "workflow.enrichment_review_revision("
        "requested_model.model_id, object.object_id, attribute.attribute_id) AS review_revision",
    )
    .replace("attribute.attribute_description", "enrichment.attribute_description")
    .replace("attribute.attribute_inferred_data_type,", "enrichment.attribute_inferred_data_type,")
    .replace("attribute.is_locked,", "coalesce(enrichment.is_locked, FALSE) AS is_locked,")
    .replace(
        "attribute.is_active\n",
        """attribute.is_active,
       jsonb_build_object('is_natural_key', enrichment.is_natural_key,
           'is_primary_key', enrichment.is_primary_key, 'is_nullable', enrichment.is_nullable,
           'is_pii', enrichment.is_pii) AS enrichment,
       CASE WHEN profile.attribute_id IS NOT NULL THEN
           (to_jsonb(profile) - ARRAY['model_id', 'attribute_id', 'object_id', 'created_by',
               'updated_by', 'created_time', 'agent_run_id', 'source_context_digest']) ||
           jsonb_build_object('row_scope', CASE WHEN profile_run.workflow_run_id IS NULL THEN NULL
               WHEN profile_run.requested_batch_id IS NULL THEN 'all_rows' ELSE 'batch' END,
               'batch_id', profile_run.requested_batch_id)
       END AS profile
""",
        1,
    )
    .replace(
        "  FROM core.attribute AS attribute",
        """  FROM core.attribute AS attribute
 CROSS JOIN requested_model
  LEFT JOIN workflow.attribute_enrichment AS enrichment
    ON enrichment.model_id = requested_model.model_id
   AND enrichment.attribute_id = attribute.attribute_id
  LEFT JOIN workflow.attribute_profile AS profile
    ON profile.model_id = requested_model.model_id AND profile.attribute_id = attribute.attribute_id
  LEFT JOIN application.workflow_run AS profile_run
    ON profile_run.workflow_run_id = profile.workflow_run_id
   AND profile_run.model_id = profile.model_id""",
    )
)

_SCOPE_VISIBLE_OBJECTS_CTE = """
WITH requested_tenant AS (
    SELECT tenant_id FROM core.tenant WHERE tenant_id = %s AND is_active
), visible_objects AS (
    SELECT object.object_id, object.source_tenant_id AS object_tenant_id
      FROM core.object AS object
      JOIN core.tenant AS owner ON owner.tenant_id = object.source_tenant_id AND owner.is_active
     WHERE object.source_tenant_id = ANY(%s::BIGINT[])
)
"""

_MODEL_INPUT_SCOPE_CANDIDATES_SQL: LiteralString = f"""
{_SCOPE_VISIBLE_OBJECTS_CTE}
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
       OR strpos(lower(btrim(object.object_schema) || '.' || btrim(object.object_name)), %s) > 0
   )
   AND (%s::BIGINT IS NULL OR connection.tenant_id = %s)
 ORDER BY lower(btrim(source_tenant.tenant_code)),
          lower(btrim(system.system_code)),
          lower(btrim(object.object_schema)),
          lower(btrim(object.object_name)),
          object.object_id
 LIMIT %s OFFSET %s
"""


_SCOPE_SEARCH_OPTIONS_SQL: LiteralString = f"""
{_SCOPE_VISIBLE_OBJECTS_CTE}
SELECT DISTINCT source_tenant.tenant_id, source_tenant.tenant_code, source_tenant.tenant_name,
       system.system_code, system.system_name, lower(btrim(zone.zone_code)) AS zone_code
  FROM visible_objects AS visible
  JOIN core.object AS object ON object.object_id = visible.object_id AND object.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id AND connection.is_active
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = visible.object_tenant_id AND source_tenant.is_active
  JOIN core.system AS system ON system.system_id = connection.system_id AND system.is_active
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id AND zone.is_active
 WHERE lower(btrim(zone.zone_code)) IN ('source', 'bronze')
 ORDER BY source_tenant.tenant_name, source_tenant.tenant_id,
          system.system_name, system.system_code, zone_code
"""


class ModelInputScopeService(Protocol):
    async def search_options(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ScopeSearchOptions: ...

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
        placement_tenant_id: int | None = None,
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
        enrichment: bool = False,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)
        self._enrichment = enrichment

    async def search_options(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ScopeSearchOptions:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                model_id=model_id,
            )
            source_tenants = authorization.readable_source_tenant_ids
            header = await transaction.fetch_one(
                _MODEL_INPUT_SCOPE_HEADER_SQL, (tenant_id, model_id)
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _SCOPE_SEARCH_OPTIONS_SQL, (tenant_id, list(source_tenants))
            )
        return ScopeSearchOptions(
            model_revision=header["model_revision"],
            locations=tuple(ScopeLocation.model_validate(row) for row in rows),
        )

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
        placement_tenant_id: int | None = None,
    ) -> ModelInputScopeCandidatePage:
        filters = {
            "model_id": model_id,
            "placement_tenant_id": placement_tenant_id,
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
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                model_id=model_id,
            )
            source_tenants = authorization.readable_source_tenant_ids
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
                    list(source_tenants),
                    model_id,
                    zone_code,
                    zone_code,
                    system_code,
                    system_code,
                    source_tenant_code,
                    source_tenant_code,
                    object_name,
                    object_name,
                    placement_tenant_id,
                    placement_tenant_id,
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
                model_id=model_id,
            )
            header = await transaction.fetch_one(
                _MODEL_INPUT_SCOPE_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _ENRICHMENT_OBJECT_SQL[0] if self._enrichment else _MODEL_INPUT_SCOPE_SQL,
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
                model_id=model_id,
            )
            row = await transaction.fetch_one(
                _ENRICHMENT_OBJECT_SQL[1] if self._enrichment else _MODEL_INPUT_SCOPE_DETAIL_SQL,
                (tenant_id, model_id, object_id),
            )
            if row is None:
                raise ModelInputScopeObjectNotFoundError()
            attributes = await transaction.fetch_all(
                _ENRICHMENT_ATTRIBUTES_SQL
                if self._enrichment
                else _MODEL_INPUT_SCOPE_ATTRIBUTES_SQL,
                (model_id, object_id) if self._enrichment else (object_id,),
            )
        return ModelInputScopeDetail.model_validate({**row, "attributes": attributes})
