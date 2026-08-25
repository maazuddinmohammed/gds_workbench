"""Tenant-owned normalized Logical model review persistence."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.logical.read_contracts import (
    MAX_DETAIL_ROWS,
    LogicalAssertionSource,
    LogicalAttributeAssertionSource,
    LogicalAttributeDetail,
    LogicalAttributeFilters,
    LogicalAttributeNotFoundError,
    LogicalAttributePage,
    LogicalAttributePhysicalSource,
    LogicalAttributeSource,
    LogicalAttributeSummary,
    LogicalDetailLimitExceededError,
    LogicalEntityDetail,
    LogicalEntityFilters,
    LogicalEntityNotFoundError,
    LogicalEntityPage,
    LogicalEntitySource,
    LogicalEntitySummary,
    LogicalObjectSource,
    LogicalRelationshipDetail,
    LogicalRelationshipFilters,
    LogicalRelationshipNotFoundError,
    LogicalRelationshipPage,
    LogicalRelationshipSummary,
    LogicalSubmodelDetail,
    LogicalSubmodelEntityMembership,
    LogicalSubmodelMembership,
    LogicalSubmodelNotFoundError,
    LogicalSubmodelPage,
    LogicalSubmodelSummary,
    ModeledFilters,
)
from gds_workbench_api.features.models import ModelNotFoundError

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_LOGICAL_ENTITIES_SQL: LiteralString = """
SELECT entity.logical_entity_id,
       entity.workflow_run_id,
       entity.logical_entity_name,
       entity.logical_entity_type,
       entity.logical_entity_dependency_order,
       entity.logical_entity_confidence,
       entity.logical_entity_status,
       entity.logical_entity_is_locked,
       entity.updated_time AS updated_at
  FROM workflow.logical_entity AS entity
  JOIN model.model AS target_model
    ON target_model.model_id = entity.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR entity.logical_entity_status = %s)
   AND (%s::BOOLEAN IS NULL OR entity.logical_entity_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(entity.logical_entity_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(entity.logical_entity_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR EXISTS (
           SELECT 1
             FROM workflow.logical_entity_submodel AS membership
            WHERE membership.model_id = entity.model_id
              AND membership.logical_entity_id = entity.logical_entity_id
              AND membership.logical_submodel_id = %s
              AND membership.logical_entity_submodel_status
                  IN ('active', 'needs_review')
       )
   )
 ORDER BY entity.logical_entity_dependency_order,
          lower(btrim(entity.logical_entity_name)),
          entity.logical_entity_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_ENTITY_DETAIL_SQL: LiteralString = """
SELECT entity.logical_entity_id,
       entity.workflow_run_id,
       entity.logical_entity_name,
       entity.logical_entity_definition,
       entity.logical_entity_type,
       entity.logical_entity_type_detail,
       entity.logical_entity_grain,
       entity.logical_entity_dependency_order,
       entity.logical_entity_confidence,
       entity.logical_entity_status,
       entity.logical_entity_is_locked,
       entity.created_time AS created_at,
       entity.updated_time AS updated_at
  FROM workflow.logical_entity AS entity
  JOIN model.model AS target_model
    ON target_model.model_id = entity.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND entity.logical_entity_id = %s
"""

_LOGICAL_ENTITY_SUBMODELS_SQL: LiteralString = """
SELECT membership.logical_entity_submodel_id,
       membership.workflow_run_id,
       submodel.logical_submodel_id,
       submodel.logical_submodel_name,
       membership.logical_entity_submodel_status AS membership_status,
       membership.logical_entity_submodel_is_locked AS membership_is_locked,
       membership.created_time AS created_at,
       membership.updated_time AS updated_at
  FROM workflow.logical_entity_submodel AS membership
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = membership.logical_entity_id
   AND entity.model_id = membership.model_id
  JOIN workflow.logical_submodel AS submodel
    ON submodel.logical_submodel_id = membership.logical_submodel_id
   AND submodel.model_id = membership.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = membership.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND membership.logical_entity_id = %s
 ORDER BY lower(btrim(submodel.logical_submodel_name)),
          membership.logical_entity_submodel_id
 LIMIT %s
"""

LOGICAL_ENTITY_SOURCES_SQL: LiteralString = """
SELECT source.logical_entity_source_mapping_id,
       source.workflow_run_id,
       source.support_source_type,
       source.logical_entity_source_mapping_order AS source_order,
       source.logical_entity_source_mapping_rationale AS rationale,
       source.logical_entity_source_mapping_status AS status,
       source.logical_entity_source_mapping_is_locked AS is_locked,
       source.created_time AS created_at,
       source.updated_time AS updated_at,
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
  FROM workflow.logical_entity_source_mapping AS source
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = source.logical_entity_id
   AND entity.model_id = source.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = source.model_id
  LEFT JOIN core.object AS source_object
    ON source_object.object_id = source.source_object_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  LEFT JOIN LATERAL workflow.list_model_object_eligibility(
      source.model_id
  ) AS source_eligibility
    ON source_eligibility.object_id = source.source_object_id
   AND source_eligibility.is_bronze_source_eligible
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_eligibility.object_tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  LEFT JOIN model.modeling_assertion_record AS assertion_record
    ON assertion_record.modeling_assertion_record_id
       = source.modeling_assertion_record_id
   AND assertion_record.model_id = source.model_id
  LEFT JOIN model.modeling_assertion_document AS assertion_document
    ON assertion_document.modeling_assertion_document_id
       = assertion_record.modeling_assertion_document_id
   AND assertion_document.model_id = assertion_record.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND source.logical_entity_id = %s
   AND (
       source.support_source_type <> 'object'
       OR source_eligibility.object_id IS NOT NULL
   )
 ORDER BY source.logical_entity_source_mapping_id
 LIMIT %s
"""

_LOGICAL_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.logical_attribute_id,
       attribute.workflow_run_id,
       attribute.logical_entity_id,
       entity.logical_entity_name,
       attribute.logical_attribute_name,
       attribute.logical_attribute_data_type,
       attribute.logical_attribute_is_nullable,
       attribute.logical_attribute_is_primary_key,
       attribute.logical_attribute_is_natural_key,
       attribute.logical_attribute_is_surrogate_key,
       attribute.logical_attribute_ordinal_position,
       attribute.logical_attribute_is_audit_column,
       attribute.logical_attribute_status,
       attribute.logical_attribute_is_locked,
       attribute.updated_time AS updated_at
  FROM workflow.logical_attribute AS attribute
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = attribute.logical_entity_id
   AND entity.model_id = attribute.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = attribute.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR attribute.logical_attribute_status = %s)
   AND (%s::BOOLEAN IS NULL OR attribute.logical_attribute_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(attribute.logical_attribute_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(attribute.logical_attribute_name)),
           char_length(%s)
       ) = %s
   )
   AND (%s::BIGINT IS NULL OR attribute.logical_entity_id = %s)
 ORDER BY lower(btrim(entity.logical_entity_name)),
          attribute.logical_attribute_ordinal_position,
          attribute.logical_attribute_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_ATTRIBUTE_DETAIL_SQL: LiteralString = """
SELECT attribute.logical_attribute_id,
       attribute.workflow_run_id,
       attribute.logical_entity_id,
       entity.logical_entity_name,
       attribute.logical_attribute_name,
       attribute.logical_attribute_definition,
       attribute.logical_attribute_data_type,
       attribute.logical_attribute_is_nullable,
       attribute.logical_attribute_is_primary_key,
       attribute.logical_attribute_is_natural_key,
       attribute.logical_attribute_is_surrogate_key,
       attribute.logical_attribute_ordinal_position,
       attribute.logical_attribute_is_audit_column,
       attribute.logical_attribute_status,
       attribute.logical_attribute_is_locked,
       attribute.created_time AS created_at,
       attribute.updated_time AS updated_at
  FROM workflow.logical_attribute AS attribute
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = attribute.logical_entity_id
   AND entity.model_id = attribute.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = attribute.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND attribute.logical_attribute_id = %s
"""

LOGICAL_ATTRIBUTE_SOURCES_SQL: LiteralString = """
SELECT source.logical_attribute_source_mapping_id,
       source.workflow_run_id,
       source.logical_entity_source_mapping_id,
       source.support_source_type,
       source.logical_attribute_source_mapping_order AS source_order,
       source.logical_attribute_source_mapping_rationale AS rationale,
       source.logical_attribute_source_mapping_status AS status,
       source.logical_attribute_source_mapping_is_locked AS is_locked,
       source.created_time AS created_at,
       source.updated_time AS updated_at,
       source_object.object_id AS source_object_id,
       source_attribute.attribute_id AS source_attribute_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_system.system_code AS source_system_code,
       source_connection.connection_code AS source_connection_code,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_attribute.attribute_name AS source_attribute_name,
       assertion_record.modeling_assertion_record_id,
       assertion_record.modeling_assertion_record_key,
       assertion_document.modeling_assertion_document_name,
       assertion_record.modeling_assertion_record_type,
       assertion_record.modeling_assertion_text,
       assertion_record.modeling_assertion_confidence,
       assertion_record.modeling_assertion_record_status
  FROM workflow.logical_attribute_source_mapping AS source
  JOIN workflow.logical_attribute AS attribute
    ON attribute.logical_attribute_id = source.logical_attribute_id
   AND attribute.logical_entity_id = source.logical_entity_id
   AND attribute.model_id = source.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = source.model_id
  LEFT JOIN core.object AS source_object
    ON source_object.object_id = source.source_object_id
  LEFT JOIN core.attribute AS source_attribute
    ON source_attribute.attribute_id = source.source_attribute_id
   AND source_attribute.object_id = source.source_object_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  LEFT JOIN LATERAL workflow.list_model_attribute_eligibility(
      source.model_id
  ) AS source_eligibility
    ON source_eligibility.object_id = source.source_object_id
   AND source_eligibility.attribute_id = source.source_attribute_id
   AND source_eligibility.is_bronze_source_eligible
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_eligibility.object_tenant_id
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  LEFT JOIN model.modeling_assertion_record AS assertion_record
    ON assertion_record.modeling_assertion_record_id
       = source.modeling_assertion_record_id
   AND assertion_record.model_id = source.model_id
  LEFT JOIN model.modeling_assertion_document AS assertion_document
    ON assertion_document.modeling_assertion_document_id
       = assertion_record.modeling_assertion_document_id
   AND assertion_document.model_id = assertion_record.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND source.logical_attribute_id = %s
   AND (
       source.support_source_type <> 'attribute'
       OR source_eligibility.attribute_id IS NOT NULL
   )
 ORDER BY source.logical_attribute_source_mapping_id
 LIMIT %s
"""

_LOGICAL_RELATIONSHIPS_SQL: LiteralString = """
SELECT relationship.logical_relationship_id,
       relationship.workflow_run_id,
       relationship.logical_relationship_from_entity_id
           AS from_logical_entity_id,
       from_entity.logical_entity_name AS from_logical_entity_name,
       relationship.logical_relationship_from_attribute_id
           AS from_logical_attribute_id,
       from_attribute.logical_attribute_name AS from_logical_attribute_name,
       relationship.logical_relationship_to_entity_id
           AS to_logical_entity_id,
       to_entity.logical_entity_name AS to_logical_entity_name,
       relationship.logical_relationship_to_attribute_id
           AS to_logical_attribute_id,
       to_attribute.logical_attribute_name AS to_logical_attribute_name,
       relationship.logical_relationship_name,
       relationship.logical_relationship_cardinality,
       relationship.logical_relationship_confidence,
       relationship.logical_relationship_status,
       relationship.logical_relationship_is_locked,
       relationship.updated_time AS updated_at
  FROM workflow.logical_relationship AS relationship
  JOIN workflow.logical_entity AS from_entity
    ON from_entity.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_entity.model_id = relationship.model_id
  JOIN workflow.logical_attribute AS from_attribute
    ON from_attribute.logical_attribute_id
       = relationship.logical_relationship_from_attribute_id
   AND from_attribute.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_attribute.model_id = relationship.model_id
  JOIN workflow.logical_entity AS to_entity
    ON to_entity.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_entity.model_id = relationship.model_id
  JOIN workflow.logical_attribute AS to_attribute
    ON to_attribute.logical_attribute_id
       = relationship.logical_relationship_to_attribute_id
   AND to_attribute.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_attribute.model_id = relationship.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = relationship.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR relationship.logical_relationship_status = %s)
   AND (%s::BOOLEAN IS NULL OR relationship.logical_relationship_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(relationship.logical_relationship_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(relationship.logical_relationship_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR relationship.logical_relationship_from_entity_id = %s
       OR relationship.logical_relationship_to_entity_id = %s
   )
 ORDER BY lower(btrim(relationship.logical_relationship_name)),
          relationship.logical_relationship_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_RELATIONSHIP_DETAIL_SQL: LiteralString = """
SELECT relationship.logical_relationship_id,
       relationship.workflow_run_id,
       relationship.logical_relationship_from_entity_id
           AS from_logical_entity_id,
       from_entity.logical_entity_name AS from_logical_entity_name,
       relationship.logical_relationship_from_attribute_id
           AS from_logical_attribute_id,
       from_attribute.logical_attribute_name AS from_logical_attribute_name,
       relationship.logical_relationship_to_entity_id
           AS to_logical_entity_id,
       to_entity.logical_entity_name AS to_logical_entity_name,
       relationship.logical_relationship_to_attribute_id
           AS to_logical_attribute_id,
       to_attribute.logical_attribute_name AS to_logical_attribute_name,
       relationship.logical_relationship_name,
       relationship.logical_relationship_definition,
       relationship.logical_relationship_cardinality,
       relationship.logical_relationship_confidence,
       relationship.logical_relationship_basis,
       relationship.logical_relationship_cardinality_basis,
       relationship.logical_relationship_status,
       relationship.logical_relationship_is_locked,
       relationship.created_time AS created_at,
       relationship.updated_time AS updated_at
  FROM workflow.logical_relationship AS relationship
  JOIN workflow.logical_entity AS from_entity
    ON from_entity.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_entity.model_id = relationship.model_id
  JOIN workflow.logical_attribute AS from_attribute
    ON from_attribute.logical_attribute_id
       = relationship.logical_relationship_from_attribute_id
   AND from_attribute.logical_entity_id
       = relationship.logical_relationship_from_entity_id
   AND from_attribute.model_id = relationship.model_id
  JOIN workflow.logical_entity AS to_entity
    ON to_entity.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_entity.model_id = relationship.model_id
  JOIN workflow.logical_attribute AS to_attribute
    ON to_attribute.logical_attribute_id
       = relationship.logical_relationship_to_attribute_id
   AND to_attribute.logical_entity_id
       = relationship.logical_relationship_to_entity_id
   AND to_attribute.model_id = relationship.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = relationship.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND relationship.logical_relationship_id = %s
"""

_LOGICAL_SUBMODELS_SQL: LiteralString = """
SELECT submodel.logical_submodel_id,
       submodel.workflow_run_id,
       submodel.logical_submodel_name,
       submodel.logical_submodel_status,
       submodel.logical_submodel_is_locked,
       count(DISTINCT membership.logical_entity_id) FILTER (
           WHERE membership.logical_entity_submodel_status
               IN ('active', 'needs_review')
       )::INTEGER AS entity_count,
       submodel.updated_time AS updated_at
  FROM workflow.logical_submodel AS submodel
  JOIN model.model AS target_model
    ON target_model.model_id = submodel.model_id
  LEFT JOIN workflow.logical_entity_submodel AS membership
    ON membership.model_id = submodel.model_id
   AND membership.logical_submodel_id = submodel.logical_submodel_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR submodel.logical_submodel_status = %s)
   AND (%s::BOOLEAN IS NULL OR submodel.logical_submodel_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(submodel.logical_submodel_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(submodel.logical_submodel_name)),
           char_length(%s)
       ) = %s
   )
 GROUP BY submodel.logical_submodel_id
 ORDER BY lower(btrim(submodel.logical_submodel_name)),
          submodel.logical_submodel_id
 LIMIT %s OFFSET %s
"""

_LOGICAL_SUBMODEL_DETAIL_SQL: LiteralString = """
SELECT submodel.logical_submodel_id,
       submodel.workflow_run_id,
       submodel.logical_submodel_name,
       submodel.logical_submodel_definition,
       submodel.logical_submodel_status,
       submodel.logical_submodel_is_locked,
       (
           SELECT count(DISTINCT membership.logical_entity_id)::INTEGER
             FROM workflow.logical_entity_submodel AS membership
            WHERE membership.model_id = submodel.model_id
              AND membership.logical_submodel_id = submodel.logical_submodel_id
              AND membership.logical_entity_submodel_status
                  IN ('active', 'needs_review')
       ) AS entity_count,
       submodel.created_time AS created_at,
       submodel.updated_time AS updated_at
  FROM workflow.logical_submodel AS submodel
  JOIN model.model AS target_model
    ON target_model.model_id = submodel.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND submodel.logical_submodel_id = %s
"""

_LOGICAL_SUBMODEL_ENTITIES_SQL: LiteralString = """
SELECT membership.logical_entity_submodel_id,
       membership.workflow_run_id,
       entity.logical_entity_id,
       entity.logical_entity_name,
       entity.logical_entity_type,
       entity.logical_entity_status,
       membership.logical_entity_submodel_status AS membership_status,
       membership.logical_entity_submodel_is_locked AS membership_is_locked,
       membership.created_time AS created_at,
       membership.updated_time AS updated_at
  FROM workflow.logical_entity_submodel AS membership
  JOIN workflow.logical_submodel AS submodel
    ON submodel.logical_submodel_id = membership.logical_submodel_id
   AND submodel.model_id = membership.model_id
  JOIN workflow.logical_entity AS entity
    ON entity.logical_entity_id = membership.logical_entity_id
   AND entity.model_id = membership.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = membership.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND membership.logical_submodel_id = %s
 ORDER BY entity.logical_entity_dependency_order,
          lower(btrim(entity.logical_entity_name)),
          membership.logical_entity_submodel_id
 LIMIT %s
"""


class LogicalService(Protocol):
    async def list_entities(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalEntityFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalEntityPage: ...

    async def read_entity(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_entity_id: int,
    ) -> LogicalEntityDetail: ...

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalAttributePage: ...

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_attribute_id: int,
    ) -> LogicalAttributeDetail: ...

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalRelationshipPage: ...

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_relationship_id: int,
    ) -> LogicalRelationshipDetail: ...

    async def list_submodels(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ModeledFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalSubmodelPage: ...

    async def read_submodel(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_submodel_id: int,
    ) -> LogicalSubmodelDetail: ...


class LogicalReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseLogicalService:
    def __init__(
        self,
        *,
        database: LogicalReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_entities(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalEntityFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalEntityPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_logical_entities:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _LOGICAL_ENTITIES_SQL,
                _entity_list_parameters(tenant_id, model_id, filters, page_size, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return LogicalEntityPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(LogicalEntitySummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_entity(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_entity_id: int,
    ) -> LogicalEntityDetail:
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
                _LOGICAL_ENTITY_DETAIL_SQL,
                (tenant_id, model_id, logical_entity_id),
            )
            if row is None:
                raise LogicalEntityNotFoundError()
            submodel_rows = await transaction.fetch_all(
                _LOGICAL_ENTITY_SUBMODELS_SQL,
                (tenant_id, model_id, logical_entity_id, MAX_DETAIL_ROWS + 1),
            )
            source_rows = await transaction.fetch_all(
                LOGICAL_ENTITY_SOURCES_SQL,
                (tenant_id, model_id, logical_entity_id, MAX_DETAIL_ROWS + 1),
            )
        if len(submodel_rows) > MAX_DETAIL_ROWS or len(source_rows) > MAX_DETAIL_ROWS:
            raise LogicalDetailLimitExceededError()
        return LogicalEntityDetail.model_validate(
            {
                **row,
                "submodels": tuple(
                    LogicalSubmodelMembership.model_validate(item) for item in submodel_rows
                ),
                "sources": tuple(_normalize_entity_source(item) for item in source_rows),
            },
            strict=False,
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalAttributePage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_logical_attributes:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _LOGICAL_ATTRIBUTES_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        model_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.logical_entity_id,
                    filters.logical_entity_id,
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
        return LogicalAttributePage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(LogicalAttributeSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_attribute_id: int,
    ) -> LogicalAttributeDetail:
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
                _LOGICAL_ATTRIBUTE_DETAIL_SQL,
                (tenant_id, model_id, logical_attribute_id),
            )
            if row is None:
                raise LogicalAttributeNotFoundError()
            source_rows = await transaction.fetch_all(
                LOGICAL_ATTRIBUTE_SOURCES_SQL,
                (tenant_id, model_id, logical_attribute_id, MAX_DETAIL_ROWS + 1),
            )
        if len(source_rows) > MAX_DETAIL_ROWS:
            raise LogicalDetailLimitExceededError()
        return LogicalAttributeDetail.model_validate(
            {
                **row,
                "sources": tuple(_normalize_attribute_source(item) for item in source_rows),
            },
            strict=False,
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalRelationshipPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_logical_relationships:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _LOGICAL_RELATIONSHIPS_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        model_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.logical_entity_id,
                    filters.logical_entity_id,
                    filters.logical_entity_id,
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
        return LogicalRelationshipPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(LogicalRelationshipSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_relationship_id: int,
    ) -> LogicalRelationshipDetail:
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
                _LOGICAL_RELATIONSHIP_DETAIL_SQL,
                (tenant_id, model_id, logical_relationship_id),
            )
        if row is None:
            raise LogicalRelationshipNotFoundError()
        return LogicalRelationshipDetail.model_validate(row)

    async def list_submodels(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ModeledFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalSubmodelPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_logical_submodels:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _LOGICAL_SUBMODELS_SQL,
                _list_parameters(tenant_id, model_id, filters, page_size, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return LogicalSubmodelPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(LogicalSubmodelSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_submodel(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_submodel_id: int,
    ) -> LogicalSubmodelDetail:
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
                _LOGICAL_SUBMODEL_DETAIL_SQL,
                (tenant_id, model_id, logical_submodel_id),
            )
            if row is None:
                raise LogicalSubmodelNotFoundError()
            entity_rows = await transaction.fetch_all(
                _LOGICAL_SUBMODEL_ENTITIES_SQL,
                (tenant_id, model_id, logical_submodel_id, MAX_DETAIL_ROWS + 1),
            )
        if len(entity_rows) > MAX_DETAIL_ROWS:
            raise LogicalDetailLimitExceededError()
        return LogicalSubmodelDetail.model_validate(
            {
                **row,
                "entities": tuple(
                    LogicalSubmodelEntityMembership.model_validate(item) for item in entity_rows
                ),
            },
            strict=False,
        )


def _list_parameters(
    tenant_id: int,
    model_id: int,
    filters: ModeledFilters,
    page_size: int,
    offset: int,
) -> tuple[object, ...]:
    return (
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
    )


def _entity_list_parameters(
    tenant_id: int,
    model_id: int,
    filters: LogicalEntityFilters,
    page_size: int,
    offset: int,
) -> tuple[object, ...]:
    common = _list_parameters(tenant_id, model_id, filters, page_size, offset)
    return (
        *common[:-2],
        filters.logical_submodel_id,
        filters.logical_submodel_id,
        *common[-2:],
    )


def _normalize_entity_source(row: Mapping[str, object]) -> LogicalEntitySource:
    common = {
        "logical_entity_source_mapping_id": row["logical_entity_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "source_order": row["source_order"],
        "rationale": row["rationale"],
        "status": row["status"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "object":
        return LogicalObjectSource.model_validate(
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
        raise ValueError("Logical Entity Source has an unsupported source type")
    return LogicalAssertionSource.model_validate(
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


def _normalize_attribute_source(row: Mapping[str, object]) -> LogicalAttributeSource:
    common = {
        "logical_attribute_source_mapping_id": row["logical_attribute_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "source_order": row["source_order"],
        "rationale": row["rationale"],
        "status": row["status"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "attribute":
        return LogicalAttributePhysicalSource.model_validate(
            {
                **common,
                "logical_entity_source_mapping_id": row["logical_entity_source_mapping_id"],
                "support_source_type": "attribute",
                "source_attribute": {
                    "object_id": row["source_object_id"],
                    "attribute_id": row["source_attribute_id"],
                    "tenant_code": row["source_tenant_code"],
                    "system_code": row["source_system_code"],
                    "connection_code": row["source_connection_code"],
                    "object_schema": row["source_object_schema"],
                    "object_name": row["source_object_name"],
                    "attribute_name": row["source_attribute_name"],
                },
            },
            strict=False,
        )
    if row["support_source_type"] != "assertion":
        raise ValueError("Logical Attribute Source has an unsupported source type")
    return LogicalAttributeAssertionSource.model_validate(
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
