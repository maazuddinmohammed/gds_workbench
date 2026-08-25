"""Tenant-owned Conceptual Object and Relationship review persistence."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.conceptual.read_contracts import (
    ConceptualAssertionSupport,
    ConceptualFilters,
    ConceptualObjectDetail,
    ConceptualObjectNotFoundError,
    ConceptualObjectPage,
    ConceptualObjectSummary,
    ConceptualObjectSupport,
    ConceptualRelationshipDetail,
    ConceptualRelationshipNotFoundError,
    ConceptualRelationshipPage,
    ConceptualRelationshipSummary,
    ConceptualSupport,
    ConceptualSupportLimitExceededError,
)
from gds_workbench_api.features.models import ModelNotFoundError

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_CONCEPTUAL_OBJECTS_SQL: LiteralString = """
SELECT object.conceptual_object_id,
       object.workflow_run_id,
       object.conceptual_object_name,
       object.conceptual_object_type,
       object.conceptual_object_confidence,
       object.conceptual_object_status,
       object.conceptual_object_is_locked,
       object.updated_time AS updated_at
  FROM workflow.conceptual_object AS object
  JOIN model.model AS target_model
    ON target_model.model_id = object.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR object.conceptual_object_status = %s)
   AND (%s::BOOLEAN IS NULL OR object.conceptual_object_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(object.conceptual_object_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(object.conceptual_object_name)),
           char_length(%s)
       ) = %s
   )
 ORDER BY lower(btrim(object.conceptual_object_name)),
          object.conceptual_object_id
 LIMIT %s OFFSET %s
"""

_CONCEPTUAL_RELATIONSHIPS_SQL: LiteralString = """
SELECT relationship.conceptual_relationship_id,
       relationship.workflow_run_id,
       relationship.from_conceptual_object_id,
       from_object.conceptual_object_name AS from_conceptual_object_name,
       relationship.to_conceptual_object_id,
       to_object.conceptual_object_name AS to_conceptual_object_name,
       relationship.conceptual_relationship_name,
       relationship.conceptual_relationship_type,
       relationship.conceptual_relationship_cardinality,
       relationship.conceptual_relationship_confidence,
       relationship.conceptual_relationship_status,
       relationship.conceptual_relationship_is_locked,
       relationship.updated_time AS updated_at
  FROM workflow.conceptual_relationship AS relationship
  JOIN workflow.conceptual_object AS from_object
    ON from_object.conceptual_object_id
       = relationship.from_conceptual_object_id
   AND from_object.model_id = relationship.model_id
  JOIN workflow.conceptual_object AS to_object
    ON to_object.conceptual_object_id = relationship.to_conceptual_object_id
   AND to_object.model_id = relationship.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = relationship.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (
       %s::VARCHAR IS NULL
       OR relationship.conceptual_relationship_status = %s
   )
   AND (
       %s::BOOLEAN IS NULL
       OR relationship.conceptual_relationship_is_locked = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(relationship.conceptual_relationship_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(relationship.conceptual_relationship_name)),
           char_length(%s)
       ) = %s
   )
 ORDER BY lower(btrim(relationship.conceptual_relationship_name)),
          relationship.conceptual_relationship_id
 LIMIT %s OFFSET %s
"""

_CONCEPTUAL_OBJECT_DETAIL_SQL: LiteralString = """
SELECT object.conceptual_object_id,
       object.workflow_run_id,
       object.conceptual_object_name,
       object.conceptual_object_definition,
       object.conceptual_object_type,
       object.conceptual_object_grain,
       object.conceptual_object_aliases,
       object.conceptual_object_confidence,
       object.conceptual_object_status,
       object.conceptual_object_is_locked,
       object.created_time AS created_at,
       object.updated_time AS updated_at
  FROM workflow.conceptual_object AS object
  JOIN model.model AS target_model
    ON target_model.model_id = object.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND object.conceptual_object_id = %s
"""

CONCEPTUAL_OBJECT_SUPPORT_SQL: LiteralString = """
SELECT support.conceptual_support_id,
       support.workflow_run_id,
       support.support_source_type,
       support.conceptual_support_role AS support_role,
       support.conceptual_support_reason AS support_reason,
       support.conceptual_support_reason_detail AS support_reason_detail,
       support.conceptual_support_confidence AS support_confidence,
       support.conceptual_support_status AS support_status,
       support.conceptual_support_is_locked AS support_is_locked,
       support.created_time AS created_at,
       support.updated_time AS updated_at,
       source_object.object_id AS source_object_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       assertion_record.modeling_assertion_record_id,
       assertion_record.modeling_assertion_record_key,
       assertion_document.modeling_assertion_document_name,
       assertion_record.modeling_assertion_record_type,
       assertion_record.modeling_assertion_text,
       assertion_record.modeling_assertion_confidence,
       assertion_record.modeling_assertion_record_status
  FROM workflow.conceptual_support AS support
  JOIN workflow.conceptual_object AS object
    ON object.conceptual_object_id = support.conceptual_object_id
   AND object.model_id = support.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = support.model_id
  LEFT JOIN core.object AS source_object
    ON source_object.object_id = support.source_object_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  LEFT JOIN LATERAL workflow.list_model_object_eligibility(
      support.model_id
  ) AS source_eligibility
    ON source_eligibility.object_id = support.source_object_id
   AND source_eligibility.is_bronze_source_eligible
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_eligibility.object_tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  LEFT JOIN model.modeling_assertion_record AS assertion_record
    ON assertion_record.modeling_assertion_record_id
       = support.modeling_assertion_record_id
   AND assertion_record.model_id = support.model_id
  LEFT JOIN model.modeling_assertion_document AS assertion_document
    ON assertion_document.modeling_assertion_document_id
       = assertion_record.modeling_assertion_document_id
   AND assertion_document.model_id = assertion_record.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND support.supported_artifact_type = 'conceptual_object'
   AND support.conceptual_object_id = %s
   AND (
       support.support_source_type <> 'object'
       OR source_eligibility.object_id IS NOT NULL
   )
 ORDER BY support.conceptual_support_id
 LIMIT %s
"""

_CONCEPTUAL_RELATIONSHIP_DETAIL_SQL: LiteralString = """
SELECT relationship.conceptual_relationship_id,
       relationship.workflow_run_id,
       relationship.from_conceptual_object_id,
       from_object.conceptual_object_name AS from_conceptual_object_name,
       relationship.to_conceptual_object_id,
       to_object.conceptual_object_name AS to_conceptual_object_name,
       relationship.conceptual_relationship_name,
       relationship.conceptual_relationship_type,
       relationship.conceptual_relationship_definition,
       relationship.conceptual_relationship_cardinality,
       relationship.conceptual_relationship_basis,
       relationship.conceptual_relationship_cardinality_basis,
       relationship.conceptual_relationship_confidence,
       relationship.conceptual_relationship_status,
       relationship.conceptual_relationship_is_locked,
       relationship.created_time AS created_at,
       relationship.updated_time AS updated_at
  FROM workflow.conceptual_relationship AS relationship
  JOIN workflow.conceptual_object AS from_object
    ON from_object.conceptual_object_id
       = relationship.from_conceptual_object_id
   AND from_object.model_id = relationship.model_id
  JOIN workflow.conceptual_object AS to_object
    ON to_object.conceptual_object_id = relationship.to_conceptual_object_id
   AND to_object.model_id = relationship.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = relationship.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND relationship.conceptual_relationship_id = %s
"""

CONCEPTUAL_RELATIONSHIP_SUPPORT_SQL: LiteralString = """
SELECT support.conceptual_support_id,
       support.workflow_run_id,
       support.support_source_type,
       support.conceptual_support_role AS support_role,
       support.conceptual_support_reason AS support_reason,
       support.conceptual_support_reason_detail AS support_reason_detail,
       support.conceptual_support_confidence AS support_confidence,
       support.conceptual_support_status AS support_status,
       support.conceptual_support_is_locked AS support_is_locked,
       support.created_time AS created_at,
       support.updated_time AS updated_at,
       source_object.object_id AS source_object_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       assertion_record.modeling_assertion_record_id,
       assertion_record.modeling_assertion_record_key,
       assertion_document.modeling_assertion_document_name,
       assertion_record.modeling_assertion_record_type,
       assertion_record.modeling_assertion_text,
       assertion_record.modeling_assertion_confidence,
       assertion_record.modeling_assertion_record_status
  FROM workflow.conceptual_support AS support
  JOIN workflow.conceptual_relationship AS relationship
    ON relationship.conceptual_relationship_id
       = support.conceptual_relationship_id
   AND relationship.model_id = support.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = support.model_id
  LEFT JOIN core.object AS source_object
    ON source_object.object_id = support.source_object_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  LEFT JOIN LATERAL workflow.list_model_object_eligibility(
      support.model_id
  ) AS source_eligibility
    ON source_eligibility.object_id = support.source_object_id
   AND source_eligibility.is_bronze_source_eligible
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_eligibility.object_tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  LEFT JOIN model.modeling_assertion_record AS assertion_record
    ON assertion_record.modeling_assertion_record_id
       = support.modeling_assertion_record_id
   AND assertion_record.model_id = support.model_id
  LEFT JOIN model.modeling_assertion_document AS assertion_document
    ON assertion_document.modeling_assertion_document_id
       = assertion_record.modeling_assertion_document_id
   AND assertion_document.model_id = assertion_record.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND support.supported_artifact_type = 'conceptual_relationship'
   AND support.conceptual_relationship_id = %s
   AND (
       support.support_source_type <> 'object'
       OR source_eligibility.object_id IS NOT NULL
   )
 ORDER BY support.conceptual_support_id
 LIMIT %s
"""

_MAX_SUPPORT_ROWS = 2000


class ConceptualService(Protocol):
    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ConceptualFilters,
        page_size: int,
        cursor: str | None,
    ) -> ConceptualObjectPage: ...

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        conceptual_object_id: int,
    ) -> ConceptualObjectDetail: ...

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ConceptualFilters,
        page_size: int,
        cursor: str | None,
    ) -> ConceptualRelationshipPage: ...

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        conceptual_relationship_id: int,
    ) -> ConceptualRelationshipDetail: ...


class ConceptualReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseConceptualService:
    def __init__(
        self,
        *,
        database: ConceptualReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ConceptualFilters,
        page_size: int,
        cursor: str | None,
    ) -> ConceptualObjectPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_conceptual_objects:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _CONCEPTUAL_OBJECTS_SQL,
                (
                    tenant_id,
                    model_id,
                    filters.status,
                    filters.status,
                    filters.locked,
                    filters.locked,
                    filters.name_exact,
                    filters.name_exact,
                    filters.name_prefix,
                    filters.name_prefix,
                    filters.name_prefix,
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
        return ConceptualObjectPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(ConceptualObjectSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        conceptual_object_id: int,
    ) -> ConceptualObjectDetail:
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
                _CONCEPTUAL_OBJECT_DETAIL_SQL,
                (tenant_id, model_id, conceptual_object_id),
            )
            if row is None:
                raise ConceptualObjectNotFoundError()
            support_rows = await transaction.fetch_all(
                CONCEPTUAL_OBJECT_SUPPORT_SQL,
                (
                    tenant_id,
                    model_id,
                    conceptual_object_id,
                    _MAX_SUPPORT_ROWS + 1,
                ),
            )
        if len(support_rows) > _MAX_SUPPORT_ROWS:
            raise ConceptualSupportLimitExceededError()
        return ConceptualObjectDetail.model_validate(
            {
                **row,
                "supports": tuple(_normalize_support(item) for item in support_rows),
            },
            strict=False,
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ConceptualFilters,
        page_size: int,
        cursor: str | None,
    ) -> ConceptualRelationshipPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_conceptual_relationships:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
        )
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
                _MODEL_HEADER_SQL,
                (tenant_id, model_id),
            )
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _CONCEPTUAL_RELATIONSHIPS_SQL,
                (
                    tenant_id,
                    model_id,
                    filters.status,
                    filters.status,
                    filters.locked,
                    filters.locked,
                    filters.name_exact,
                    filters.name_exact,
                    filters.name_prefix,
                    filters.name_prefix,
                    filters.name_prefix,
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
        return ConceptualRelationshipPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                ConceptualRelationshipSummary.model_validate(row) for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        conceptual_relationship_id: int,
    ) -> ConceptualRelationshipDetail:
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
                _CONCEPTUAL_RELATIONSHIP_DETAIL_SQL,
                (tenant_id, model_id, conceptual_relationship_id),
            )
            if row is None:
                raise ConceptualRelationshipNotFoundError()
            support_rows = await transaction.fetch_all(
                CONCEPTUAL_RELATIONSHIP_SUPPORT_SQL,
                (
                    tenant_id,
                    model_id,
                    conceptual_relationship_id,
                    _MAX_SUPPORT_ROWS + 1,
                ),
            )
        if len(support_rows) > _MAX_SUPPORT_ROWS:
            raise ConceptualSupportLimitExceededError()
        return ConceptualRelationshipDetail.model_validate(
            {
                **row,
                "supports": tuple(_normalize_support(item) for item in support_rows),
            },
            strict=False,
        )


def _normalize_support(row: Mapping[str, object]) -> ConceptualSupport:
    common = {
        "conceptual_support_id": row["conceptual_support_id"],
        "workflow_run_id": row["workflow_run_id"],
        "support_role": row["support_role"],
        "support_reason": row["support_reason"],
        "support_reason_detail": row["support_reason_detail"],
        "support_confidence": row["support_confidence"],
        "support_status": row["support_status"],
        "support_is_locked": row["support_is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "object":
        return ConceptualObjectSupport.model_validate(
            {
                **common,
                "support_source_type": "object",
                "source_object": {
                    "object_id": row["source_object_id"],
                    "tenant_code": row["source_tenant_code"],
                    "system_code": row["source_system_code"],
                    "connection_code": row["source_connection_code"],
                    "object_schema": row["source_object_schema"],
                    "object_name": row["source_object_name"],
                },
            },
            strict=False,
        )
    if row["support_source_type"] != "assertion":
        raise ValueError("Conceptual Support has an unsupported source type")
    return ConceptualAssertionSupport.model_validate(
        {
            **common,
            "support_source_type": "assertion",
            "assertion_record": {
                "modeling_assertion_record_id": row["modeling_assertion_record_id"],
                "modeling_assertion_record_key": row["modeling_assertion_record_key"],
                "modeling_assertion_document_name": row["modeling_assertion_document_name"],
                "modeling_assertion_record_type": row["modeling_assertion_record_type"],
                "modeling_assertion_text": row["modeling_assertion_text"],
                "modeling_assertion_confidence": row["modeling_assertion_confidence"],
                "modeling_assertion_record_status": row["modeling_assertion_record_status"],
            },
        },
        strict=False,
    )
