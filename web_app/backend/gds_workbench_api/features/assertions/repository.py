"""Fixed PostgreSQL reads for Modeling Assertion review."""

from collections.abc import Sequence
from typing import LiteralString, Protocol, cast

from gds_etl_workbench.infrastructure.postgres import ReadTransaction

from gds_workbench_api.features.assertions.contracts import (
    AssertionDocumentDetail,
    AssertionDocumentFilters,
    AssertionDocumentNotFoundError,
    AssertionDocumentSummary,
    AssertionPayloadNotSafeError,
    AssertionRecordDetail,
    AssertionRecordFilters,
    AssertionRecordNotFoundError,
    AssertionRecordSummary,
    JsonObject,
    validate_safe_json,
)

_MODEL_REVISION_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_ASSERTION_DOCUMENTS_SQL: LiteralString = """
SELECT document.modeling_assertion_document_id,
       document.workflow_run_id,
       document.modeling_assertion_document_name,
       document.modeling_assertion_document_type,
       CASE WHEN source_tenant.tenant_id IS NULL THEN NULL
            ELSE jsonb_build_object(
                'tenant_id', source_tenant.tenant_id,
                'tenant_code', source_tenant.tenant_code,
                'tenant_name', source_tenant.tenant_name
            )
       END AS source_tenant,
       CASE WHEN source_system.system_id IS NULL THEN NULL
            ELSE jsonb_build_object(
                'system_id', source_system.system_id,
                'system_code', source_system.system_code,
                'system_name', source_system.system_name
            )
       END AS source_system,
       document.is_active,
       count(record.modeling_assertion_record_id)::INTEGER AS record_count,
       count(record.modeling_assertion_record_id) FILTER (
           WHERE record.modeling_assertion_record_status = 'active'
       )::INTEGER AS active_record_count,
       count(record.modeling_assertion_record_id) FILTER (
           WHERE record.modeling_assertion_record_is_locked
       )::INTEGER AS locked_record_count,
       document.updated_time AS updated_at
  FROM model.modeling_assertion_document AS document
  JOIN model.model AS target_model
    ON target_model.model_id = document.model_id
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = document.tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = document.system_id
  LEFT JOIN model.modeling_assertion_record AS record
    ON record.model_id = document.model_id
   AND record.modeling_assertion_document_id
       = document.modeling_assertion_document_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(source_system.system_code)) = %s
   )
   AND (%s::BOOLEAN IS NULL OR document.is_active = %s)
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(document.modeling_assertion_document_name)),
           char_length(%s)
       ) = %s
   )
 GROUP BY document.modeling_assertion_document_id,
          source_tenant.tenant_id,
          source_system.system_id
 ORDER BY lower(btrim(document.modeling_assertion_document_name)),
          document.modeling_assertion_document_id
 LIMIT %s OFFSET %s
"""

_ASSERTION_DOCUMENT_DETAIL_SQL: LiteralString = """
SELECT document.modeling_assertion_document_id,
       document.workflow_run_id,
       document.modeling_assertion_document_name,
       document.modeling_assertion_file_pattern,
       document.modeling_assertion_document_type,
       document.modeling_assertion_document_description,
       CASE WHEN octet_length(
                    document.modeling_assertion_document_metadata::TEXT
                ) <= 65536
            THEN document.modeling_assertion_document_metadata
            ELSE NULL
       END AS modeling_assertion_document_metadata,
       octet_length(document.modeling_assertion_document_metadata::TEXT) > 65536
           AS metadata_is_oversized,
       CASE WHEN source_tenant.tenant_id IS NULL THEN NULL
            ELSE jsonb_build_object(
                'tenant_id', source_tenant.tenant_id,
                'tenant_code', source_tenant.tenant_code,
                'tenant_name', source_tenant.tenant_name
            )
       END AS source_tenant,
       CASE WHEN source_system.system_id IS NULL THEN NULL
            ELSE jsonb_build_object(
                'system_id', source_system.system_id,
                'system_code', source_system.system_code,
                'system_name', source_system.system_name
            )
       END AS source_system,
       document.is_active,
       counts.record_count,
       counts.active_record_count,
       counts.locked_record_count,
       document.agent_run_id,
       document.created_time AS created_at,
       document.updated_time AS updated_at
  FROM model.modeling_assertion_document AS document
  JOIN model.model AS target_model
    ON target_model.model_id = document.model_id
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = document.tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = document.system_id
  CROSS JOIN LATERAL (
      SELECT count(record.modeling_assertion_record_id)::INTEGER
                 AS record_count,
             count(record.modeling_assertion_record_id) FILTER (
                 WHERE record.modeling_assertion_record_status = 'active'
             )::INTEGER AS active_record_count,
             count(record.modeling_assertion_record_id) FILTER (
                 WHERE record.modeling_assertion_record_is_locked
             )::INTEGER AS locked_record_count
        FROM model.modeling_assertion_record AS record
       WHERE record.model_id = document.model_id
         AND record.modeling_assertion_document_id
             = document.modeling_assertion_document_id
  ) AS counts
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND document.modeling_assertion_document_id = %s
"""

_ASSERTION_RECORDS_SQL: LiteralString = """
SELECT record.modeling_assertion_record_id,
       record.workflow_run_id,
       jsonb_build_object(
           'modeling_assertion_document_id',
               document.modeling_assertion_document_id,
           'modeling_assertion_document_name',
               document.modeling_assertion_document_name,
           'modeling_assertion_document_type',
               document.modeling_assertion_document_type,
           'source_tenant', CASE WHEN source_tenant.tenant_id IS NULL THEN NULL
               ELSE jsonb_build_object(
                   'tenant_id', source_tenant.tenant_id,
                   'tenant_code', source_tenant.tenant_code,
                   'tenant_name', source_tenant.tenant_name
               ) END,
           'source_system', CASE WHEN source_system.system_id IS NULL THEN NULL
               ELSE jsonb_build_object(
                   'system_id', source_system.system_id,
                   'system_code', source_system.system_code,
                   'system_name', source_system.system_name
               ) END,
           'is_active', document.is_active
       ) AS document,
       record.modeling_assertion_record_key,
       record.modeling_assertion_record_type,
       ARRAY(
           SELECT canonical.layer_name
             FROM unnest(ARRAY[
                 'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
             ]::TEXT[]) WITH ORDINALITY
                 AS canonical(layer_name, layer_order)
            WHERE canonical.layer_name
                  = ANY(record.modeling_assertion_applicable_layers)
            ORDER BY canonical.layer_order
       ) AS modeling_assertion_applicable_layers,
       record.modeling_assertion_confidence,
       record.modeling_assertion_record_status,
       record.modeling_assertion_record_is_locked,
       record.updated_time AS updated_at
  FROM model.modeling_assertion_record AS record
  JOIN model.modeling_assertion_document AS document
    ON document.modeling_assertion_document_id
       = record.modeling_assertion_document_id
   AND document.model_id = record.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = record.model_id
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = document.tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = document.system_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (
       %s::BIGINT IS NULL
       OR document.modeling_assertion_document_id = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(document.modeling_assertion_document_name)) = %s
   )
   AND (%s::BIGINT IS NULL OR source_system.system_id = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(source_system.system_code)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR record.modeling_assertion_record_status = %s
   )
   AND (
       %s::BOOLEAN IS NULL
       OR record.modeling_assertion_record_is_locked = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR %s = ANY(record.modeling_assertion_applicable_layers)
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(record.modeling_assertion_record_key)),
           char_length(%s)
       ) = %s
   )
 ORDER BY lower(btrim(record.modeling_assertion_record_key)),
          record.modeling_assertion_record_id
 LIMIT %s OFFSET %s
"""

_ASSERTION_RECORD_DETAIL_SQL: LiteralString = """
SELECT record.modeling_assertion_record_id,
       record.workflow_run_id,
       jsonb_build_object(
           'modeling_assertion_document_id',
               document.modeling_assertion_document_id,
           'modeling_assertion_document_name',
               document.modeling_assertion_document_name,
           'modeling_assertion_document_type',
               document.modeling_assertion_document_type,
           'source_tenant', CASE WHEN source_tenant.tenant_id IS NULL THEN NULL
               ELSE jsonb_build_object(
                   'tenant_id', source_tenant.tenant_id,
                   'tenant_code', source_tenant.tenant_code,
                   'tenant_name', source_tenant.tenant_name
               ) END,
           'source_system', CASE WHEN source_system.system_id IS NULL THEN NULL
               ELSE jsonb_build_object(
                   'system_id', source_system.system_id,
                   'system_code', source_system.system_code,
                   'system_name', source_system.system_name
               ) END,
           'is_active', document.is_active
       ) AS document,
       record.modeling_assertion_record_key,
       record.modeling_assertion_record_type,
       CASE WHEN char_length(record.modeling_assertion_text) <= 262144
            THEN record.modeling_assertion_text
            ELSE NULL
       END AS modeling_assertion_text,
       char_length(record.modeling_assertion_text) > 262144 AS text_is_oversized,
       CASE WHEN octet_length(record.modeling_assertion_details::TEXT) <= 262144
            THEN record.modeling_assertion_details
            ELSE NULL
       END AS modeling_assertion_details,
       octet_length(record.modeling_assertion_details::TEXT) > 262144
           AS details_are_oversized,
       CASE
           WHEN record.modeling_assertion_source_location IS NULL THEN NULL
           WHEN octet_length(record.modeling_assertion_source_location::TEXT) <= 65536
               THEN record.modeling_assertion_source_location
           ELSE NULL
       END AS modeling_assertion_source_location,
       coalesce(
           octet_length(record.modeling_assertion_source_location::TEXT) > 65536,
           FALSE
       ) AS source_location_is_oversized,
       ARRAY(
           SELECT canonical.layer_name
             FROM unnest(ARRAY[
                 'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
             ]::TEXT[]) WITH ORDINALITY
                 AS canonical(layer_name, layer_order)
            WHERE canonical.layer_name
                  = ANY(record.modeling_assertion_applicable_layers)
            ORDER BY canonical.layer_order
       ) AS modeling_assertion_applicable_layers,
       record.modeling_assertion_confidence,
       record.modeling_assertion_record_status,
       record.modeling_assertion_record_is_locked,
       record.agent_run_id,
       record.created_time AS created_at,
       record.updated_time AS updated_at
  FROM model.modeling_assertion_record AS record
  JOIN model.modeling_assertion_document AS document
    ON document.modeling_assertion_document_id
       = record.modeling_assertion_document_id
   AND document.model_id = record.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = record.model_id
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = document.tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = document.system_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND record.modeling_assertion_record_id = %s
"""


class AssertionsRepository(Protocol):
    async def read_model_revision(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
    ) -> int | None: ...

    async def list_documents(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionDocumentFilters,
        limit: int,
        offset: int,
    ) -> Sequence[AssertionDocumentSummary]: ...

    async def read_document(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        document_id: int,
    ) -> AssertionDocumentDetail: ...

    async def list_records(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionRecordFilters,
        limit: int,
        offset: int,
    ) -> Sequence[AssertionRecordSummary]: ...

    async def read_record(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        record_id: int,
    ) -> AssertionRecordDetail: ...


class PostgresAssertionsRepository:
    async def read_model_revision(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
    ) -> int | None:
        row = await transaction.fetch_one(_MODEL_REVISION_SQL, (tenant_id, model_id))
        return None if row is None else int(row["model_revision"])

    async def list_documents(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionDocumentFilters,
        limit: int,
        offset: int,
    ) -> Sequence[AssertionDocumentSummary]:
        rows = await transaction.fetch_all(
            _ASSERTION_DOCUMENTS_SQL,
            (
                tenant_id,
                model_id,
                filters.source_system_id,
                filters.source_system_id,
                filters.source_system_code,
                filters.source_system_code,
                filters.active,
                filters.active,
                filters.name_prefix,
                filters.name_prefix,
                filters.name_prefix,
                limit,
                offset,
            ),
        )
        return tuple(AssertionDocumentSummary.model_validate(row, strict=False) for row in rows)

    async def read_document(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        document_id: int,
    ) -> AssertionDocumentDetail:
        row = await transaction.fetch_one(
            _ASSERTION_DOCUMENT_DETAIL_SQL,
            (tenant_id, model_id, document_id),
        )
        if row is None:
            raise AssertionDocumentNotFoundError()
        if row["metadata_is_oversized"]:
            raise AssertionPayloadNotSafeError()
        normalized = dict(row)
        normalized.pop("metadata_is_oversized")
        _require_safe_json(
            normalized["modeling_assertion_document_metadata"],
            maximum_bytes=65_536,
            label="Assertion Document metadata",
        )
        return AssertionDocumentDetail.model_validate(normalized, strict=False)

    async def list_records(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionRecordFilters,
        limit: int,
        offset: int,
    ) -> Sequence[AssertionRecordSummary]:
        rows = await transaction.fetch_all(
            _ASSERTION_RECORDS_SQL,
            (
                tenant_id,
                model_id,
                filters.document_id,
                filters.document_id,
                filters.document_name,
                filters.document_name,
                filters.source_system_id,
                filters.source_system_id,
                filters.source_system_code,
                filters.source_system_code,
                filters.status,
                filters.status,
                filters.locked,
                filters.locked,
                filters.applicable_layer,
                filters.applicable_layer,
                filters.key_prefix,
                filters.key_prefix,
                filters.key_prefix,
                limit,
                offset,
            ),
        )
        return tuple(AssertionRecordSummary.model_validate(row, strict=False) for row in rows)

    async def read_record(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        record_id: int,
    ) -> AssertionRecordDetail:
        row = await transaction.fetch_one(
            _ASSERTION_RECORD_DETAIL_SQL,
            (tenant_id, model_id, record_id),
        )
        if row is None:
            raise AssertionRecordNotFoundError()
        if (
            row["text_is_oversized"]
            or row["details_are_oversized"]
            or row["source_location_is_oversized"]
        ):
            raise AssertionPayloadNotSafeError()
        normalized = dict(row)
        normalized.pop("text_is_oversized")
        normalized.pop("details_are_oversized")
        normalized.pop("source_location_is_oversized")
        _require_safe_json(
            normalized["modeling_assertion_details"],
            maximum_bytes=262_144,
            label="Assertion Record details",
        )
        source_location = normalized["modeling_assertion_source_location"]
        if source_location is not None:
            _require_safe_json(
                source_location,
                maximum_bytes=65_536,
                label="Assertion Record source location",
            )
        return AssertionRecordDetail.model_validate(normalized, strict=False)


def _require_safe_json(value: object, *, maximum_bytes: int, label: str) -> None:
    if not isinstance(value, dict):
        raise AssertionPayloadNotSafeError()
    try:
        validate_safe_json(
            cast(JsonObject, value),
            maximum_bytes=maximum_bytes,
            label=label,
        )
    except ValueError as error:
        raise AssertionPayloadNotSafeError() from error
