"""Project applied model records into the existing Metadata import contract."""

from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.model_read import authorize_model_read
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.metadata import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction
from openpyxl.utils.exceptions import IllegalCharacterError

from gds_workbench_api.features.metadata.contracts import MetadataWorkbookDownload
from gds_workbench_api.features.metadata.workbook import (
    MetadataWorkbookSheet,
    build_metadata_workbook,
)
from gds_workbench_api.features.models import ModelNotFoundError, ModelRevisionConflictError

from .contracts import (
    ExportModelDdlRequest,
    ExportModelTargetsRequest,
    ModelTargetOptions,
    TargetLayer,
    TargetPlacement,
)
from .ddl import build_model_ddl

_PLACEMENT_SQL: LiteralString = """
SELECT placement.tenant_code, system.system_code, connection.connection_code,
       owner.tenant_code AS source_tenant_code, connection.connection_id
  FROM core.tenant AS owner
  JOIN core.connection AS connection ON connection.connection_id = owner.gds_connection_id
  JOIN core.tenant AS placement ON placement.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
 WHERE owner.tenant_id = %s AND owner.is_active AND connection.is_active
   AND connection.is_global_data_store AND placement.is_active AND system.is_active
"""
_OBJECT_TYPES_SQL: LiteralString = """
SELECT object_type_code AS code, object_type_name AS name
  FROM reference.object_type WHERE is_active ORDER BY object_type_code
"""
_ENTITY_QUERIES: dict[TargetLayer, LiteralString] = {
    "logical": """
SELECT logical_entity_id AS entity_id, logical_entity_name AS entity_name,
       logical_entity_schema_name AS entity_schema_name,
       logical_entity_definition AS definition
  FROM workflow.logical_entity
 WHERE model_id = %s AND (%s::BIGINT[] IS NULL OR logical_entity_id = ANY(%s::BIGINT[]))
   AND logical_entity_status = 'active'
 ORDER BY logical_entity_dependency_order, logical_entity_id LIMIT 201
""",
    "dimensional": """
SELECT dimensional_entity_id AS entity_id, dimensional_entity_name AS entity_name,
       dimensional_entity_schema_name AS entity_schema_name,
       dimensional_entity_definition AS definition
  FROM workflow.dimensional_entity
 WHERE model_id = %s AND (%s::BIGINT[] IS NULL OR dimensional_entity_id = ANY(%s::BIGINT[]))
   AND dimensional_entity_status = 'active'
 ORDER BY dimensional_entity_dependency_order, dimensional_entity_id LIMIT 201
""",
}
_LOGICAL_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.logical_entity_id AS entity_id,
       attribute.logical_attribute_name AS attribute_name,
       attribute.logical_attribute_definition AS definition,
       attribute.logical_attribute_data_type AS data_type,
       attribute.logical_attribute_is_nullable AS is_nullable,
       attribute.logical_attribute_is_natural_key AS is_natural_key,
       attribute.logical_attribute_is_surrogate_key AS is_surrogate_key,
       attribute.logical_attribute_is_audit_column AS is_audit_column,
       attribute.logical_attribute_ordinal_position AS ordinal_position,
       EXISTS (
           SELECT 1 FROM workflow.logical_attribute_source_mapping AS source
           JOIN core.attribute AS physical ON physical.attribute_id = source.source_attribute_id
            WHERE source.model_id = attribute.model_id
              AND source.logical_attribute_id = attribute.logical_attribute_id
              AND source.logical_attribute_source_mapping_status = 'active'
              AND physical.is_masking_required
       ) AS is_masking_required
  FROM workflow.logical_attribute AS attribute
 WHERE attribute.model_id = %s AND attribute.logical_entity_id = ANY(%s::BIGINT[])
   AND attribute.logical_attribute_status = 'active'
 ORDER BY attribute.logical_entity_id, attribute.logical_attribute_ordinal_position,
          attribute.logical_attribute_id
 LIMIT 5001
"""
# Only these two static schemas can be queried. Dimensional key roles have their own semantics.
_ATTRIBUTE_QUERIES: dict[TargetLayer, LiteralString] = {
    "logical": _LOGICAL_ATTRIBUTES_SQL,
    "dimensional": (
        _LOGICAL_ATTRIBUTES_SQL.replace("logical", "dimensional")
        .replace(
            "attribute.dimensional_attribute_is_natural_key",
            "(attribute.dimensional_attribute_key_role = 'business')",
        )
        .replace(
            "attribute.dimensional_attribute_is_surrogate_key",
            "(attribute.dimensional_attribute_key_role = 'surrogate')",
        )
        .replace(
            "JOIN core.attribute AS physical ON physical.attribute_id = source.source_attribute_id",
            "JOIN workflow.logical_attribute_source_mapping AS logical_source "
            "ON logical_source.model_id = source.model_id "
            "AND logical_source.logical_attribute_id = source.source_logical_attribute_id "
            "AND logical_source.logical_attribute_source_mapping_status = 'active' "
            "JOIN core.attribute AS physical "
            "ON physical.attribute_id = logical_source.source_attribute_id",
        )
    ),
}


_CONCEPTUAL_DDL_SQL: LiteralString = """
SELECT conceptual_object_id AS entity_id, conceptual_object_name AS entity_name,
       'conceptual' AS entity_schema_name, conceptual_object_definition AS definition
  FROM workflow.conceptual_object
 WHERE model_id = %s AND (%s::BIGINT[] IS NULL OR conceptual_object_id = ANY(%s::BIGINT[]))
   AND conceptual_object_status = 'active'
 ORDER BY conceptual_object_id LIMIT 201
"""
_LOGICAL_DDL_RELATIONSHIPS: LiteralString = """
SELECT relation.logical_relationship_from_entity_id AS from_entity_id,
       relation.logical_relationship_to_entity_id AS to_entity_id,
       source.logical_attribute_name AS from_attribute_name,
       target.logical_attribute_name AS to_attribute_name
  FROM workflow.logical_relationship AS relation
  JOIN workflow.logical_attribute AS source ON source.model_id = relation.model_id
   AND source.logical_attribute_id = relation.logical_relationship_from_attribute_id
   AND source.logical_attribute_status = 'active'
  JOIN workflow.logical_attribute AS target ON target.model_id = relation.model_id
   AND target.logical_attribute_id = relation.logical_relationship_to_attribute_id
   AND target.logical_attribute_status = 'active'
 WHERE relation.model_id = %s AND relation.logical_relationship_status = 'active'
   AND (relation.logical_relationship_from_entity_id = ANY(%s::BIGINT[])
        OR relation.logical_relationship_to_entity_id = ANY(%s::BIGINT[]))
 ORDER BY relation.logical_relationship_id LIMIT 5001
"""
_DDL_RELATIONSHIPS: dict[TargetLayer, LiteralString] = {
    "logical": _LOGICAL_DDL_RELATIONSHIPS,
    "dimensional": _LOGICAL_DDL_RELATIONSHIPS.replace("logical", "dimensional"),
}


class ModelTargetsDatabase(Protocol):
    def read_transaction(
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


def registration_workbook(
    *,
    tenant_id: int,
    placement: TargetPlacement,
    command: ExportModelTargetsRequest,
    entities: Sequence[Mapping[str, Any]],
    attributes: Sequence[Mapping[str, Any]],
) -> bytes:
    """Preserve the applied design; no inferred fields or invented Attributes."""
    if command.entity_ids is None or command.object_type_code is None:
        raise InvalidRequestError("Resolve the export Entities and Table type first.")
    if {row["entity_id"] for row in entities} != set(command.entity_ids) or len(entities) != len(
        command.entity_ids
    ):
        raise InvalidRequestError("An Entity is missing, inactive, or outside this Model.")
    if len(attributes) > 5000:
        raise InvalidRequestError("Select fewer Entities; the export exceeds 5,000 Attributes.")
    zone = "silver" if command.layer == "logical" else "gold"
    identity = placement.model_dump(exclude={"source_tenant_code"})
    objects: list[Mapping[str, object]] = []
    columns: list[Mapping[str, object]] = []
    for entity in entities:
        members = [row for row in attributes if row["entity_id"] == entity["entity_id"]]
        if not members:
            raise InvalidRequestError("Every exported Entity must have active Attributes.")
        key = {
            **identity,
            "object_schema": entity["entity_schema_name"],
            "object_name": entity["entity_name"],
        }
        objects.append(
            {
                **key,
                "source_tenant_code": placement.source_tenant_code,
                "fc_object_schema": None,
                "fc_object_name": None,
                "object_transformation": None,
                "object_description": entity["definition"],
                "batch_attribute_name": None,
                "object_type_code": command.object_type_code,
                "zone_code": zone,
                "is_locked": False,
                "is_active": True,
            }
        )
        # Metadata requires unique physical ordinals. Model designs can contain ties;
        # the query's declared-position/record-ID ordering makes their export stable.
        tied_positions = len({row["ordinal_position"] for row in members}) != len(members)
        for position, attribute in enumerate(members, start=1):
            columns.append(
                {
                    **key,
                    "attribute_name": attribute["attribute_name"],
                    "fc_attribute_name": None,
                    "attribute_ordinal_position": position
                    if tied_positions
                    else attribute["ordinal_position"],
                    "attribute_description": attribute["definition"],
                    "attribute_data_type": attribute["data_type"],
                    "attribute_inferred_data_type": None,
                    "attribute_nullability": attribute["is_nullable"],
                    "attribute_custom_code": None,
                    "is_natural_key": attribute["is_natural_key"],
                    "is_surrogate_key": attribute["is_surrogate_key"],
                    "is_meta_data": attribute["is_audit_column"],
                    "is_masking_required": attribute["is_masking_required"],
                    "is_mapped": False,
                    "is_purge": False,
                    "is_locked": False,
                    "is_active": True,
                }
            )
    sheets: list[MetadataWorkbookSheet] = []
    try:
        for code, rows in ((f"{zone}_object", objects), (f"{zone}_attribute", columns)):
            definition = DATASETS_BY_NAME[code]
            canonical = tuple(
                definition.row_model.model_validate(row, strict=True).model_dump(mode="json")
                for row in rows
            )
            sheets.append(
                MetadataWorkbookSheet(
                    code=code,
                    name=definition.label,
                    columns=tuple(definition.row_model.model_fields),
                    canonical_key=definition.canonical_key,
                    row_schema=definition.row_model.model_json_schema(),
                    rows=canonical,
                )
            )
        return build_metadata_workbook(tenant_id=tenant_id, sheets=tuple(sheets))
    except (ValueError, IllegalCharacterError) as error:
        raise InvalidRequestError(
            "The model records cannot be represented in the Metadata workbook."
        ) from error


class DatabaseModelTargetsService:
    def __init__(self, *, database: ModelTargetsDatabase, authorizer: AuthorizationService) -> None:
        self._database = database
        self._authorizer = authorizer

    async def options(
        self, principal: RequestPrincipal, *, tenant_id: int, model_id: int
    ) -> ModelTargetOptions:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            model = await authorize_model_read(
                transaction, authorizer=self._authorizer, principal=principal, model_id=model_id
            )
            if model.tenant_id != tenant_id:
                raise ModelNotFoundError()
            placement = await transaction.fetch_one(_PLACEMENT_SQL, (tenant_id,))
        return ModelTargetOptions(
            model_id=model_id,
            model_revision=model.model_revision,
            placement=TargetPlacement.model_validate(
                {field: placement[field] for field in TargetPlacement.model_fields}
            )
            if placement
            else None,
        )

    async def export(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: ExportModelTargetsRequest,
    ) -> MetadataWorkbookDownload:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            model = await authorize_model_read(
                transaction, authorizer=self._authorizer, principal=principal, model_id=model_id
            )
            if model.tenant_id != tenant_id:
                raise ModelNotFoundError()
            if model.model_revision != command.expected_model_revision:
                raise ModelRevisionConflictError()
            placement = await transaction.fetch_one(_PLACEMENT_SQL, (tenant_id,))
            if placement is None:
                raise InvalidRequestError(
                    "Configure an active GDS Connection for this Tenant before export."
                )
            types = await transaction.fetch_all(_OBJECT_TYPES_SQL, ())
            if command.object_type_code is None:
                table_types = [
                    row
                    for row in types
                    if str(row["code"]).strip().casefold() == "table"
                    or str(row["name"]).strip().casefold() == "table"
                ]
                if not table_types and len(types) == 1:
                    table_types = list(types)
                if len(table_types) != 1:
                    raise InvalidRequestError(
                        "Configure one active Table Object Type before export."
                    )
                command = command.model_copy(update={"object_type_code": table_types[0]["code"]})
            if command.object_type_code not in {row["code"] for row in types}:
                raise InvalidRequestError("Choose an active registered Object Type.")
            entities = await transaction.fetch_all(
                _ENTITY_QUERIES[command.layer], (model_id, command.entity_ids, command.entity_ids)
            )
            if not entities:
                raise InvalidRequestError("Apply active Entities before export.")
            if len(entities) > 200:
                raise InvalidRequestError("Select at most 200 Entities per workbook.")
            if command.entity_ids is None:
                command = command.model_copy(
                    update={"entity_ids": [row["entity_id"] for row in entities]}
                )
            attributes = await transaction.fetch_all(
                _ATTRIBUTE_QUERIES[command.layer], (model_id, command.entity_ids)
            )
            content = registration_workbook(
                tenant_id=tenant_id,
                placement=TargetPlacement.model_validate(
                    {field: placement[field] for field in TargetPlacement.model_fields}
                ),
                command=command,
                entities=entities,
                attributes=attributes,
            )
        zone = "silver" if command.layer == "logical" else "gold"
        return MetadataWorkbookDownload(
            content=content,
            filename=f"gds_{zone}_registration__model_{model_id}__r{model.model_revision}.xlsx",
            sheet_count=2,
        )

    async def export_ddl(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: ExportModelDdlRequest,
    ) -> str:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            model = await authorize_model_read(
                transaction, authorizer=self._authorizer, principal=principal, model_id=model_id
            )
            if model.tenant_id != tenant_id:
                raise ModelNotFoundError()
            if model.model_revision != command.expected_model_revision:
                raise ModelRevisionConflictError()
            entities = await transaction.fetch_all(
                _CONCEPTUAL_DDL_SQL
                if command.layer == "conceptual"
                else _ENTITY_QUERIES[command.layer],
                (model_id, command.entity_ids, command.entity_ids),
            )
            if command.entity_ids is not None and {row["entity_id"] for row in entities} != set(
                command.entity_ids
            ):
                raise InvalidRequestError(
                    "Some selected Entities are no longer active or available."
                )
            ids = [row["entity_id"] for row in entities]
            attributes = (
                await transaction.fetch_all(_ATTRIBUTE_QUERIES[command.layer], (model_id, ids))
                if command.layer != "conceptual"
                else []
            )
            relationships = (
                await transaction.fetch_all(_DDL_RELATIONSHIPS[command.layer], (model_id, ids, ids))
                if command.layer != "conceptual"
                else []
            )
            if len(relationships) > 5000:
                raise InvalidRequestError(
                    "Select fewer Entities to stay within the relationship limit."
                )
        return build_model_ddl(
            entities=entities,
            attributes=attributes,
            relationships=relationships,
            conceptual=command.layer == "conceptual",
        )
