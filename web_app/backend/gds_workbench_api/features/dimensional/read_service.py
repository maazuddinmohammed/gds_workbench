"""Tenant-owned normalized Dimensional model review persistence."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.dimensional.read_contracts import (
    MAX_DETAIL_ROWS,
    DimensionalAssertionSource,
    DimensionalAttributeAssertionSource,
    DimensionalAttributeDetail,
    DimensionalAttributeFilters,
    DimensionalAttributeNotFoundError,
    DimensionalAttributePage,
    DimensionalAttributePhysicalSource,
    DimensionalAttributeSource,
    DimensionalAttributeSummary,
    DimensionalDetailLimitExceededError,
    DimensionalObjectDetail,
    DimensionalObjectNotFoundError,
    DimensionalObjectPage,
    DimensionalObjectSource,
    DimensionalObjectSummary,
    DimensionalPhysicalObjectSource,
    DimensionalRelationshipDetail,
    DimensionalRelationshipFilters,
    DimensionalRelationshipNotFoundError,
    DimensionalRelationshipPage,
    DimensionalRelationshipSummary,
    DimensionalSubmodelMembership,
)
from gds_workbench_api.features.logical import ModeledFilters
from gds_workbench_api.features.models import ModelNotFoundError

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_DIMENSIONAL_OBJECTS_SQL: LiteralString = """
SELECT entity.dimensional_entity_id,
       entity.workflow_run_id,
       entity.dimensional_entity_name,
       entity.dimensional_entity_type,
       entity.dimensional_fact_type,
       entity.dimensional_entity_dependency_order,
       entity.dimensional_entity_confidence,
       entity.dimensional_entity_status,
       entity.dimensional_entity_is_locked,
       entity.updated_time AS updated_at
  FROM workflow.dimensional_entity AS entity
  JOIN model.model AS target_model
    ON target_model.model_id = entity.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR entity.dimensional_entity_status = %s)
   AND (%s::BOOLEAN IS NULL OR entity.dimensional_entity_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(entity.dimensional_entity_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(entity.dimensional_entity_name)),
           char_length(%s)
       ) = %s
   )
 ORDER BY entity.dimensional_entity_dependency_order,
          lower(btrim(entity.dimensional_entity_name)),
          entity.dimensional_entity_id
 LIMIT %s OFFSET %s
"""

_DIMENSIONAL_OBJECT_DETAIL_SQL: LiteralString = """
SELECT entity.dimensional_entity_id,
       entity.workflow_run_id,
       entity.dimensional_entity_name,
       entity.dimensional_entity_definition,
       entity.dimensional_entity_type,
       entity.dimensional_fact_type,
       entity.dimensional_entity_grain_definition,
       entity.dimensional_entity_dependency_order,
       entity.dimensional_entity_confidence,
       entity.dimensional_entity_status,
       entity.dimensional_entity_is_locked,
       entity.created_time AS created_at,
       entity.updated_time AS updated_at
  FROM workflow.dimensional_entity AS entity
  JOIN model.model AS target_model
    ON target_model.model_id = entity.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND entity.dimensional_entity_id = %s
"""

_DIMENSIONAL_OBJECT_SUBMODELS_SQL: LiteralString = """
SELECT membership.dimensional_entity_submodel_id,
       membership.workflow_run_id,
       submodel.dimensional_submodel_id,
       submodel.dimensional_submodel_name,
       membership.dimensional_entity_submodel_status AS membership_status,
       membership.dimensional_entity_submodel_is_locked AS membership_is_locked,
       membership.created_time AS created_at,
       membership.updated_time AS updated_at
  FROM workflow.dimensional_entity_submodel AS membership
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = membership.dimensional_entity_id
   AND entity.model_id = membership.model_id
  JOIN workflow.dimensional_submodel AS submodel
    ON submodel.dimensional_submodel_id = membership.dimensional_submodel_id
   AND submodel.model_id = membership.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = membership.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND membership.dimensional_entity_id = %s
 ORDER BY lower(btrim(submodel.dimensional_submodel_name)),
          membership.dimensional_entity_submodel_id
 LIMIT %s
"""

DIMENSIONAL_OBJECT_SOURCES_SQL: LiteralString = """
SELECT source.dimensional_entity_source_mapping_id,
       source.workflow_run_id,
       source.support_source_type,
       source.dimensional_entity_source_role AS source_role,
       source.dimensional_entity_source_mapping_order AS source_order,
       source.dimensional_entity_source_mapping_rationale AS rationale,
       source.dimensional_entity_source_mapping_status AS status,
       source.dimensional_entity_source_mapping_is_locked AS is_locked,
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
  FROM workflow.dimensional_entity_source_mapping AS source
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = source.dimensional_entity_id
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
   AND source_eligibility.is_dimensional_source_eligible
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
   AND source.dimensional_entity_id = %s
   AND (
       source.support_source_type <> 'object'
       OR source_eligibility.object_id IS NOT NULL
   )
 ORDER BY source.dimensional_entity_source_mapping_id
 LIMIT %s
"""

_DIMENSIONAL_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.dimensional_attribute_id,
       attribute.workflow_run_id,
       attribute.dimensional_entity_id,
       entity.dimensional_entity_name,
       attribute.dimensional_attribute_name,
       attribute.dimensional_attribute_data_type,
       attribute.dimensional_attribute_is_nullable,
       attribute.dimensional_attribute_ordinal_position,
       attribute.dimensional_attribute_role,
       attribute.dimensional_attribute_key_role,
       attribute.dimensional_attribute_is_grain_component,
       attribute.dimensional_attribute_additivity,
       attribute.dimensional_attribute_default_aggregation,
       attribute.dimensional_attribute_change_behavior,
       attribute.dimensional_attribute_is_audit_column,
       attribute.dimensional_attribute_confidence,
       attribute.dimensional_attribute_status,
       attribute.dimensional_attribute_is_locked,
       attribute.updated_time AS updated_at
  FROM workflow.dimensional_attribute AS attribute
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = attribute.dimensional_entity_id
   AND entity.model_id = attribute.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = attribute.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR attribute.dimensional_attribute_status = %s)
   AND (%s::BOOLEAN IS NULL OR attribute.dimensional_attribute_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(attribute.dimensional_attribute_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(attribute.dimensional_attribute_name)),
           char_length(%s)
       ) = %s
   )
   AND (%s::BIGINT IS NULL OR attribute.dimensional_entity_id = %s)
 ORDER BY lower(btrim(entity.dimensional_entity_name)),
          attribute.dimensional_attribute_ordinal_position,
          attribute.dimensional_attribute_id
 LIMIT %s OFFSET %s
"""

_DIMENSIONAL_ATTRIBUTE_DETAIL_SQL: LiteralString = """
SELECT attribute.dimensional_attribute_id,
       attribute.workflow_run_id,
       attribute.dimensional_entity_id,
       entity.dimensional_entity_name,
       attribute.dimensional_attribute_name,
       attribute.dimensional_attribute_definition,
       attribute.dimensional_attribute_data_type,
       attribute.dimensional_attribute_is_nullable,
       attribute.dimensional_attribute_ordinal_position,
       attribute.dimensional_attribute_role,
       attribute.dimensional_attribute_key_role,
       attribute.dimensional_attribute_is_grain_component,
       attribute.dimensional_attribute_additivity,
       attribute.dimensional_attribute_default_aggregation,
       attribute.dimensional_attribute_aggregation_basis,
       attribute.dimensional_attribute_change_behavior,
       attribute.dimensional_attribute_is_audit_column,
       attribute.dimensional_attribute_confidence,
       attribute.dimensional_attribute_status,
       attribute.dimensional_attribute_is_locked,
       attribute.created_time AS created_at,
       attribute.updated_time AS updated_at
  FROM workflow.dimensional_attribute AS attribute
  JOIN workflow.dimensional_entity AS entity
    ON entity.dimensional_entity_id = attribute.dimensional_entity_id
   AND entity.model_id = attribute.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = attribute.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND attribute.dimensional_attribute_id = %s
"""

DIMENSIONAL_ATTRIBUTE_SOURCES_SQL: LiteralString = """
SELECT source.dimensional_attribute_source_mapping_id,
       source.workflow_run_id,
       source.dimensional_entity_source_mapping_id,
       source.support_source_type,
       source.dimensional_attribute_source_mapping_order AS source_order,
       source.dimensional_attribute_source_mapping_rationale AS rationale,
       source.dimensional_attribute_source_mapping_status AS status,
       source.dimensional_attribute_source_mapping_is_locked AS is_locked,
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
  FROM workflow.dimensional_attribute_source_mapping AS source
  JOIN workflow.dimensional_attribute AS attribute
    ON attribute.dimensional_attribute_id = source.dimensional_attribute_id
   AND attribute.dimensional_entity_id = source.dimensional_entity_id
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
   AND source_eligibility.is_dimensional_source_eligible
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
   AND source.dimensional_attribute_id = %s
   AND (
       source.support_source_type <> 'attribute'
       OR source_eligibility.attribute_id IS NOT NULL
   )
 ORDER BY source.dimensional_attribute_source_mapping_id
 LIMIT %s
"""

_DIMENSIONAL_RELATIONSHIPS_SQL: LiteralString = """
SELECT relationship.dimensional_relationship_id,
       relationship.workflow_run_id,
       relationship.dimensional_relationship_from_entity_id
           AS from_dimensional_entity_id,
       from_entity.dimensional_entity_name AS from_dimensional_entity_name,
       relationship.dimensional_relationship_from_attribute_id
           AS from_dimensional_attribute_id,
       from_attribute.dimensional_attribute_name
           AS from_dimensional_attribute_name,
       relationship.dimensional_relationship_to_entity_id
           AS to_dimensional_entity_id,
       to_entity.dimensional_entity_name AS to_dimensional_entity_name,
       relationship.dimensional_relationship_to_attribute_id
           AS to_dimensional_attribute_id,
       to_attribute.dimensional_attribute_name AS to_dimensional_attribute_name,
       relationship.dimensional_relationship_name,
       relationship.dimensional_relationship_kind,
       relationship.dimensional_relationship_cardinality,
       relationship.dimensional_relationship_is_optional,
       relationship.dimensional_relationship_role_name,
       relationship.dimensional_relationship_confidence,
       relationship.dimensional_relationship_status,
       relationship.dimensional_relationship_is_locked,
       relationship.updated_time AS updated_at
  FROM workflow.dimensional_relationship AS relationship
  JOIN workflow.dimensional_entity AS from_entity
    ON from_entity.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_entity.model_id = relationship.model_id
  JOIN workflow.dimensional_attribute AS from_attribute
    ON from_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_from_attribute_id
   AND from_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_attribute.model_id = relationship.model_id
  JOIN workflow.dimensional_entity AS to_entity
    ON to_entity.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_entity.model_id = relationship.model_id
  JOIN workflow.dimensional_attribute AS to_attribute
    ON to_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_to_attribute_id
   AND to_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_attribute.model_id = relationship.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = relationship.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND (%s::VARCHAR IS NULL OR relationship.dimensional_relationship_status = %s)
   AND (%s::BOOLEAN IS NULL OR relationship.dimensional_relationship_is_locked = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(relationship.dimensional_relationship_name)) = %s
   )
   AND (
       %s::VARCHAR IS NULL
       OR left(
           lower(btrim(relationship.dimensional_relationship_name)),
           char_length(%s)
       ) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR relationship.dimensional_relationship_from_entity_id = %s
       OR relationship.dimensional_relationship_to_entity_id = %s
   )
 ORDER BY lower(btrim(relationship.dimensional_relationship_name)),
          relationship.dimensional_relationship_id
 LIMIT %s OFFSET %s
"""

_DIMENSIONAL_RELATIONSHIP_DETAIL_SQL: LiteralString = """
SELECT relationship.dimensional_relationship_id,
       relationship.workflow_run_id,
       relationship.dimensional_relationship_from_entity_id
           AS from_dimensional_entity_id,
       from_entity.dimensional_entity_name AS from_dimensional_entity_name,
       relationship.dimensional_relationship_from_attribute_id
           AS from_dimensional_attribute_id,
       from_attribute.dimensional_attribute_name
           AS from_dimensional_attribute_name,
       relationship.dimensional_relationship_to_entity_id
           AS to_dimensional_entity_id,
       to_entity.dimensional_entity_name AS to_dimensional_entity_name,
       relationship.dimensional_relationship_to_attribute_id
           AS to_dimensional_attribute_id,
       to_attribute.dimensional_attribute_name AS to_dimensional_attribute_name,
       relationship.dimensional_relationship_name,
       relationship.dimensional_relationship_definition,
       relationship.dimensional_relationship_kind,
       relationship.dimensional_relationship_cardinality,
       relationship.dimensional_relationship_is_optional,
       relationship.dimensional_relationship_role_name,
       relationship.dimensional_relationship_confidence,
       relationship.dimensional_relationship_basis,
       relationship.dimensional_relationship_cardinality_basis,
       relationship.dimensional_relationship_status,
       relationship.dimensional_relationship_is_locked,
       relationship.created_time AS created_at,
       relationship.updated_time AS updated_at
  FROM workflow.dimensional_relationship AS relationship
  JOIN workflow.dimensional_entity AS from_entity
    ON from_entity.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_entity.model_id = relationship.model_id
  JOIN workflow.dimensional_attribute AS from_attribute
    ON from_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_from_attribute_id
   AND from_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_from_entity_id
   AND from_attribute.model_id = relationship.model_id
  JOIN workflow.dimensional_entity AS to_entity
    ON to_entity.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_entity.model_id = relationship.model_id
  JOIN workflow.dimensional_attribute AS to_attribute
    ON to_attribute.dimensional_attribute_id
       = relationship.dimensional_relationship_to_attribute_id
   AND to_attribute.dimensional_entity_id
       = relationship.dimensional_relationship_to_entity_id
   AND to_attribute.model_id = relationship.model_id
  JOIN model.model AS target_model
    ON target_model.model_id = relationship.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
   AND relationship.dimensional_relationship_id = %s
"""


class DimensionalService(Protocol):
    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ModeledFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalObjectPage: ...

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_entity_id: int,
    ) -> DimensionalObjectDetail: ...

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: DimensionalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalAttributePage: ...

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_attribute_id: int,
    ) -> DimensionalAttributeDetail: ...

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: DimensionalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalRelationshipPage: ...

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_relationship_id: int,
    ) -> DimensionalRelationshipDetail: ...


class DimensionalReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseDimensionalService:
    def __init__(
        self,
        *,
        database: DimensionalReadDatabase,
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
        filters: ModeledFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalObjectPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_dimensional_objects:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
                _DIMENSIONAL_OBJECTS_SQL,
                _list_parameters(tenant_id, model_id, filters, page_size, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return DimensionalObjectPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(DimensionalObjectSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_entity_id: int,
    ) -> DimensionalObjectDetail:
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
                _DIMENSIONAL_OBJECT_DETAIL_SQL,
                (tenant_id, model_id, dimensional_entity_id),
            )
            if row is None:
                raise DimensionalObjectNotFoundError()
            submodel_rows = await transaction.fetch_all(
                _DIMENSIONAL_OBJECT_SUBMODELS_SQL,
                (tenant_id, model_id, dimensional_entity_id, MAX_DETAIL_ROWS + 1),
            )
            source_rows = await transaction.fetch_all(
                DIMENSIONAL_OBJECT_SOURCES_SQL,
                (tenant_id, model_id, dimensional_entity_id, MAX_DETAIL_ROWS + 1),
            )
        if len(submodel_rows) > MAX_DETAIL_ROWS or len(source_rows) > MAX_DETAIL_ROWS:
            raise DimensionalDetailLimitExceededError()
        return DimensionalObjectDetail.model_validate(
            {
                **row,
                "submodels": tuple(
                    DimensionalSubmodelMembership.model_validate(item) for item in submodel_rows
                ),
                "sources": tuple(_normalize_object_source(item) for item in source_rows),
            },
            strict=False,
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: DimensionalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalAttributePage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_dimensional_attributes:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _DIMENSIONAL_ATTRIBUTES_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        model_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.dimensional_entity_id,
                    filters.dimensional_entity_id,
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
        return DimensionalAttributePage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                DimensionalAttributeSummary.model_validate(row) for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_attribute_id: int,
    ) -> DimensionalAttributeDetail:
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
                _DIMENSIONAL_ATTRIBUTE_DETAIL_SQL,
                (tenant_id, model_id, dimensional_attribute_id),
            )
            if row is None:
                raise DimensionalAttributeNotFoundError()
            source_rows = await transaction.fetch_all(
                DIMENSIONAL_ATTRIBUTE_SOURCES_SQL,
                (tenant_id, model_id, dimensional_attribute_id, MAX_DETAIL_ROWS + 1),
            )
        if len(source_rows) > MAX_DETAIL_ROWS:
            raise DimensionalDetailLimitExceededError()
        return DimensionalAttributeDetail.model_validate(
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
        filters: DimensionalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalRelationshipPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_dimensional_relationships:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
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
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _DIMENSIONAL_RELATIONSHIPS_SQL,
                (
                    *_list_parameters(
                        tenant_id,
                        model_id,
                        filters,
                        page_size,
                        offset,
                    )[:-2],
                    filters.dimensional_entity_id,
                    filters.dimensional_entity_id,
                    filters.dimensional_entity_id,
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
        return DimensionalRelationshipPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                DimensionalRelationshipSummary.model_validate(row) for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_relationship_id: int,
    ) -> DimensionalRelationshipDetail:
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
                _DIMENSIONAL_RELATIONSHIP_DETAIL_SQL,
                (tenant_id, model_id, dimensional_relationship_id),
            )
        if row is None:
            raise DimensionalRelationshipNotFoundError()
        return DimensionalRelationshipDetail.model_validate(row)


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


def _normalize_object_source(row: Mapping[str, object]) -> DimensionalObjectSource:
    common = {
        "dimensional_entity_source_mapping_id": row["dimensional_entity_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "source_role": row["source_role"],
        "source_order": row["source_order"],
        "rationale": row["rationale"],
        "status": row["status"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "object":
        return DimensionalPhysicalObjectSource.model_validate(
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
        raise ValueError("Dimensional Object Source has an unsupported source type")
    return DimensionalAssertionSource.model_validate(
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


def _normalize_attribute_source(row: Mapping[str, object]) -> DimensionalAttributeSource:
    common = {
        "dimensional_attribute_source_mapping_id": row["dimensional_attribute_source_mapping_id"],
        "workflow_run_id": row["workflow_run_id"],
        "source_order": row["source_order"],
        "rationale": row["rationale"],
        "status": row["status"],
        "is_locked": row["is_locked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["support_source_type"] == "attribute":
        return DimensionalAttributePhysicalSource.model_validate(
            {
                **common,
                "dimensional_entity_source_mapping_id": row["dimensional_entity_source_mapping_id"],
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
        raise ValueError("Dimensional Attribute Source has an unsupported source type")
    return DimensionalAttributeAssertionSource.model_validate(
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
