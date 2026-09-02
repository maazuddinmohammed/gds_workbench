"""Authorized read behavior for Analysis findings."""

import json
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Literal, LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction
from pydantic import Field

from gds_workbench_api.features.analysis.read_contracts import (
    AnalysisEndpoint,
    AnalysisEvidence,
    AnalysisFindingDetail,
    AnalysisFindingFilters,
    AnalysisFindingNotFoundError,
    AnalysisFindingPage,
    AnalysisFindingSummary,
    AnalysisWorkflowProvenance,
    ReviewContract,
)
from gds_workbench_api.features.models import ModelNotFoundError

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_id,
       target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_ANALYSIS_FINDINGS_SQL: LiteralString = """

WITH RECURSIVE requested_tenant AS (
    SELECT tenant_id, gds_connection_id
      FROM core.tenant
     WHERE tenant_id = %s
       AND is_active
),
visible_objects AS (
    SELECT visible_object.*
      FROM requested_tenant
      CROSS JOIN LATERAL workflow.list_tenant_visible_objects(
          requested_tenant.tenant_id
      ) AS visible_object
)
,
target_model AS (
    SELECT target_model.model_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
)
SELECT result.analysis_result_id,
       result.from_object_id,
       result.from_attribute_id,
       from_source_tenant.tenant_id AS from_source_tenant_id,
       from_source_tenant.tenant_code AS from_source_tenant_code,
       from_source_tenant.tenant_name AS from_source_tenant_name,
       from_system.system_id AS from_system_id,
       from_system.system_code AS from_system_code,
       from_system.system_name AS from_system_name,
       from_connection.connection_id AS from_connection_id,
       from_connection.connection_code AS from_connection_code,
       from_object.object_schema AS from_object_schema,
       from_object.object_name AS from_object_name,
       from_attribute.attribute_name AS from_attribute_name,
       from_attribute.attribute_data_type AS from_attribute_data_type,
       result.to_object_id,
       result.to_attribute_id,
       to_source_tenant.tenant_id AS to_source_tenant_id,
       to_source_tenant.tenant_code AS to_source_tenant_code,
       to_source_tenant.tenant_name AS to_source_tenant_name,
       to_system.system_id AS to_system_id,
       to_system.system_code AS to_system_code,
       to_system.system_name AS to_system_name,
       to_connection.connection_id AS to_connection_id,
       to_connection.connection_code AS to_connection_code,
       to_object.object_schema AS to_object_schema,
       to_object.object_name AS to_object_name,
       to_attribute.attribute_name AS to_attribute_name,
       to_attribute.attribute_data_type AS to_attribute_data_type,
       result.relationship_kind,
       result.relationship_confidence,
       CASE
           WHEN result.validation_result IS NULL THEN 'unvalidated'
           ELSE 'validated'
       END AS validation_state,
       result.validation_result,
       result.analysis_result_status AS status,
       result.analysis_result_is_locked AS is_locked,
       result.updated_time AS updated_at
  FROM target_model
  JOIN workflow.analysis_result AS result
    ON result.model_id = target_model.model_id
  JOIN model.model_input_scope AS from_scope
    ON from_scope.model_id = target_model.model_id
   AND from_scope.object_id = result.from_object_id
   AND from_scope.is_active
  JOIN model.model_input_scope AS to_scope
    ON to_scope.model_id = target_model.model_id
   AND to_scope.object_id = result.to_object_id
   AND to_scope.is_active
  JOIN visible_objects AS from_visible
    ON from_visible.object_id = result.from_object_id
  JOIN visible_objects AS to_visible
    ON to_visible.object_id = result.to_object_id
  JOIN core.object AS from_object
    ON from_object.object_id = result.from_object_id
   AND from_object.is_active
  JOIN core.connection AS from_connection
    ON from_connection.connection_id = from_object.connection_id
  JOIN core.system AS from_system
    ON from_system.system_id = from_connection.system_id
  JOIN core.tenant AS from_source_tenant
    ON from_source_tenant.tenant_id = from_visible.object_tenant_id
  JOIN core.attribute AS from_attribute
    ON from_attribute.attribute_id = result.from_attribute_id
   AND from_attribute.object_id = result.from_object_id
   AND from_attribute.is_active
  JOIN core.object AS to_object
    ON to_object.object_id = result.to_object_id
   AND to_object.is_active
  JOIN core.connection AS to_connection
    ON to_connection.connection_id = to_object.connection_id
  JOIN core.system AS to_system
    ON to_system.system_id = to_connection.system_id
  JOIN core.tenant AS to_source_tenant
    ON to_source_tenant.tenant_id = to_visible.object_tenant_id
  JOIN core.attribute AS to_attribute
    ON to_attribute.attribute_id = result.to_attribute_id
   AND to_attribute.object_id = result.to_object_id
   AND to_attribute.is_active
 WHERE (
       %s::BIGINT IS NULL
       OR result.from_object_id = %s
       OR result.to_object_id = %s
   )
   AND (%s::BIGINT IS NULL OR result.from_object_id = %s)
   AND (%s::BIGINT IS NULL OR result.to_object_id = %s)
   AND (
       %s::TEXT IS NULL
       OR CASE %s
           WHEN 'validated' THEN result.validation_result IS NOT NULL
           WHEN 'unvalidated' THEN result.validation_result IS NULL
           ELSE FALSE
       END
   )
   AND (
       (%s::TEXT IS NOT NULL AND result.analysis_result_status = %s)
       OR (
           %s::TEXT IS NULL
           AND (
               %s
               OR result.analysis_result_status = 'active'
           )
       )
   )
   AND (%s::BOOLEAN IS NULL OR result.analysis_result_is_locked = %s)
 ORDER BY result.from_object_id,
          result.from_attribute_id,
          result.to_object_id,
          result.to_attribute_id,
          lower(result.relationship_kind),
          result.analysis_result_id
 LIMIT %s OFFSET %s
"""

_ANALYSIS_FINDING_DETAIL_SQL: LiteralString = """

WITH RECURSIVE requested_tenant AS (
    SELECT tenant_id, gds_connection_id
      FROM core.tenant
     WHERE tenant_id = %s
       AND is_active
),
visible_objects AS (
    SELECT visible_object.*
      FROM requested_tenant
      CROSS JOIN LATERAL workflow.list_tenant_visible_objects(
          requested_tenant.tenant_id
      ) AS visible_object
)
,
target_model AS (
    SELECT target_model.model_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
)
SELECT result.analysis_result_id,
       result.from_object_id,
       result.from_attribute_id,
       from_source_tenant.tenant_id AS from_source_tenant_id,
       from_source_tenant.tenant_code AS from_source_tenant_code,
       from_source_tenant.tenant_name AS from_source_tenant_name,
       from_system.system_id AS from_system_id,
       from_system.system_code AS from_system_code,
       from_system.system_name AS from_system_name,
       from_connection.connection_id AS from_connection_id,
       from_connection.connection_code AS from_connection_code,
       from_object.object_schema AS from_object_schema,
       from_object.object_name AS from_object_name,
       from_attribute.attribute_name AS from_attribute_name,
       from_attribute.attribute_data_type AS from_attribute_data_type,
       result.to_object_id,
       result.to_attribute_id,
       to_source_tenant.tenant_id AS to_source_tenant_id,
       to_source_tenant.tenant_code AS to_source_tenant_code,
       to_source_tenant.tenant_name AS to_source_tenant_name,
       to_system.system_id AS to_system_id,
       to_system.system_code AS to_system_code,
       to_system.system_name AS to_system_name,
       to_connection.connection_id AS to_connection_id,
       to_connection.connection_code AS to_connection_code,
       to_object.object_schema AS to_object_schema,
       to_object.object_name AS to_object_name,
       to_attribute.attribute_name AS to_attribute_name,
       to_attribute.attribute_data_type AS to_attribute_data_type,
       result.relationship_kind,
       result.relationship_confidence,
       left(result.relationship_basis, 8000) AS relationship_basis,
       char_length(result.relationship_basis) > 8000 AS relationship_basis_truncated,
       CASE
           WHEN result.validation_result IS NULL THEN 'unvalidated'
           ELSE 'validated'
       END AS validation_state,
       result.validation_policy_version,
       result.validation_policy_digest,
       result.validation_result,
       result.validation_source_non_null_count,
       result.validation_source_distinct_count,
       result.validation_target_non_null_count,
       result.validation_target_distinct_count,
       result.validation_source_missing_target_count,
       result.validation_unused_target_count,
       result.validation_duplicate_target_key_count,
       result.agent_run_id,
       result.inference_workflow_run_id,
       result.validation_workflow_run_id,
       result.analysis_result_status AS status,
       result.analysis_result_is_locked AS is_locked,
       result.created_time AS created_at,
       result.updated_time AS updated_at
  FROM target_model
  JOIN workflow.analysis_result AS result
    ON result.model_id = target_model.model_id
  JOIN model.model_input_scope AS from_scope
    ON from_scope.model_id = target_model.model_id
   AND from_scope.object_id = result.from_object_id
   AND from_scope.is_active
  JOIN model.model_input_scope AS to_scope
    ON to_scope.model_id = target_model.model_id
   AND to_scope.object_id = result.to_object_id
   AND to_scope.is_active
  JOIN visible_objects AS from_visible
    ON from_visible.object_id = result.from_object_id
  JOIN visible_objects AS to_visible
    ON to_visible.object_id = result.to_object_id
  JOIN core.object AS from_object
    ON from_object.object_id = result.from_object_id
   AND from_object.is_active
  JOIN core.connection AS from_connection
    ON from_connection.connection_id = from_object.connection_id
  JOIN core.system AS from_system
    ON from_system.system_id = from_connection.system_id
  JOIN core.tenant AS from_source_tenant
    ON from_source_tenant.tenant_id = from_visible.object_tenant_id
  JOIN core.attribute AS from_attribute
    ON from_attribute.attribute_id = result.from_attribute_id
   AND from_attribute.object_id = result.from_object_id
   AND from_attribute.is_active
  JOIN core.object AS to_object
    ON to_object.object_id = result.to_object_id
   AND to_object.is_active
  JOIN core.connection AS to_connection
    ON to_connection.connection_id = to_object.connection_id
  JOIN core.system AS to_system
    ON to_system.system_id = to_connection.system_id
  JOIN core.tenant AS to_source_tenant
    ON to_source_tenant.tenant_id = to_visible.object_tenant_id
  JOIN core.attribute AS to_attribute
    ON to_attribute.attribute_id = result.to_attribute_id
   AND to_attribute.object_id = result.to_object_id
   AND to_attribute.is_active
 WHERE result.analysis_result_id = %s
"""

_ANALYSIS_ENDPOINT_FIELDS = (
    "object_id",
    "attribute_id",
    "source_tenant_id",
    "source_tenant_code",
    "source_tenant_name",
    "system_id",
    "system_code",
    "system_name",
    "connection_id",
    "connection_code",
    "object_schema",
    "object_name",
    "attribute_name",
    "attribute_data_type",
)


class AnalysisReviewService(Protocol):
    async def list_analysis_findings(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AnalysisFindingFilters,
        page_size: int,
        cursor: str | None,
    ) -> AnalysisFindingPage: ...

    async def read_analysis_finding(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        analysis_result_id: int,
    ) -> AnalysisFindingDetail: ...


class AnalysisReviewDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class _ModelHeader(ReviewContract):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)


class DatabaseAnalysisReviewService:
    def __init__(
        self,
        *,
        database: AnalysisReviewDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_analysis_findings(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AnalysisFindingFilters,
        page_size: int,
        cursor: str | None,
    ) -> AnalysisFindingPage:
        filter_digest = sha256(
            json.dumps(
                {
                    "filters": filters.model_dump(mode="json"),
                    "model_id": model_id,
                    "tenant_id": tenant_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        collection = f"web_analysis_findings:{filter_digest}:{page_size}"
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
            header_row = await transaction.fetch_one(
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header_row is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _ANALYSIS_FINDINGS_SQL,
                (
                    tenant_id,
                    tenant_id,
                    model_id,
                    filters.object_id,
                    filters.object_id,
                    filters.object_id,
                    filters.from_object_id,
                    filters.from_object_id,
                    filters.to_object_id,
                    filters.to_object_id,
                    filters.validation_state,
                    filters.validation_state,
                    filters.status,
                    filters.status,
                    filters.status,
                    filters.show_inactive,
                    filters.locked,
                    filters.locked,
                    page_size + 1,
                    offset,
                ),
            )

        header = _ModelHeader.model_validate(header_row)
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return AnalysisFindingPage(
            model_id=header.model_id,
            model_revision=header.model_revision,
            items=tuple(_normalize_analysis_summary(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_analysis_finding(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        analysis_result_id: int,
    ) -> AnalysisFindingDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header_row = await transaction.fetch_one(
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header_row is None:
                raise ModelNotFoundError()
            row = await transaction.fetch_one(
                _ANALYSIS_FINDING_DETAIL_SQL,
                (tenant_id, tenant_id, model_id, analysis_result_id),
            )
        if row is None:
            raise AnalysisFindingNotFoundError()
        return _normalize_analysis_detail(row)


def _normalize_analysis_endpoint(
    row: dict[str, object],
    prefix: Literal["from", "to"],
) -> AnalysisEndpoint:
    return AnalysisEndpoint.model_validate(
        {field: row[f"{prefix}_{field}"] for field in _ANALYSIS_ENDPOINT_FIELDS}
    )


def _normalize_analysis_summary(row: dict[str, object]) -> AnalysisFindingSummary:
    return AnalysisFindingSummary.model_validate(
        {
            "analysis_result_id": row["analysis_result_id"],
            "from_endpoint": _normalize_analysis_endpoint(row, "from"),
            "to_endpoint": _normalize_analysis_endpoint(row, "to"),
            "relationship_kind": row["relationship_kind"],
            "relationship_confidence": row["relationship_confidence"],
            "validation_state": row["validation_state"],
            "validation_result": row["validation_result"],
            "status": row["status"],
            "is_locked": row["is_locked"],
            "updated_at": row["updated_at"],
        }
    )


def _normalize_analysis_detail(row: dict[str, object]) -> AnalysisFindingDetail:
    summary = _normalize_analysis_summary(row)
    evidence = None
    if row["validation_result"] is not None:
        evidence = AnalysisEvidence.model_validate(
            {
                "validation_policy_version": row["validation_policy_version"],
                "validation_policy_digest": row["validation_policy_digest"],
                "result": row["validation_result"],
                "source_non_null_count": row["validation_source_non_null_count"],
                "source_distinct_count": row["validation_source_distinct_count"],
                "target_non_null_count": row["validation_target_non_null_count"],
                "target_distinct_count": row["validation_target_distinct_count"],
                "source_missing_target_count": row["validation_source_missing_target_count"],
                "unused_target_count": row["validation_unused_target_count"],
                "duplicate_target_key_count": row["validation_duplicate_target_key_count"],
            }
        )
    provenance = AnalysisWorkflowProvenance.model_validate(
        {
            "agent_run_id": row["agent_run_id"],
            "inference_workflow_run_id": row["inference_workflow_run_id"],
            "validation_workflow_run_id": row["validation_workflow_run_id"],
        }
    )
    return AnalysisFindingDetail.model_validate(
        {
            **summary.model_dump(),
            "relationship_basis": row["relationship_basis"],
            "relationship_basis_truncated": row["relationship_basis_truncated"],
            "evidence": evidence,
            "provenance": provenance,
            "created_at": row["created_at"],
        }
    )
