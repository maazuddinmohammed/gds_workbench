"""Authorized, revision-fenced XLSX projection of one System's saved Mappings."""

from __future__ import annotations

import json
from typing import Any, LiteralString, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.mapping_context import MAPPING_REFERENCE_TEMPLATE_CODES
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.metadata.contracts import MetadataWorkbookDownload
from gds_workbench_api.features.models import ModelNotFoundError, ModelRevisionConflictError

from .read_contracts import MappingEntityType, MappingReadDatabase
from .workbook import (
    MAX_MAPPING_ROWS,
    MAX_MAPPING_SHEETS,
    MAX_MAPPING_TEXT_CHARACTERS,
    MappingWorkbookAttribute,
    MappingWorkbookBuildError,
    MappingWorkbookEntity,
    build_mapping_workbook,
)

_HEADER_SQL: LiteralString = """
SELECT model.model_revision, model.model_name, tenant.tenant_name
  FROM model.model AS model JOIN core.tenant AS tenant USING (tenant_id)
 WHERE model.tenant_id = %s AND model.model_id = %s AND model.is_active
"""
_ENTITIES_SQL: LiteralString = """
SELECT mapping.mapping_object_id, entity.modeled_entity_id, entity.modeled_entity_schema_name,
       entity.modeled_entity_name, entity.definition, entity.classification,
       mapping.object_dependency_order, system.system_code,
       octet_length(mapping.mapping_transformation_document::text) AS document_bytes,
       template.output_template_code
  FROM workflow.mapping_object AS mapping
  JOIN model.model AS model ON model.model_id = mapping.model_id
  JOIN workflow.modeled_entity AS entity ON entity.model_id = model.model_id
   AND entity.modeled_entity_type = mapping.modeled_entity_type
   AND entity.modeled_entity_id = coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id)
  JOIN core.system AS system ON system.system_id = mapping.source_system_id
  LEFT JOIN application.output_template AS template
    ON template.output_template_id = mapping.output_template_id
 WHERE model.tenant_id = %s AND model.model_id = %s AND model.is_active
   AND entity.modeled_entity_type = %s AND lower(btrim(system.system_code)) = %s
   AND entity.status = 'active' AND mapping.object_mapping_status = 'active'
   AND (mapping.mapping_transformation_document IS NOT NULL OR EXISTS (
       SELECT 1 FROM workflow.mapping_attribute AS child
        WHERE child.mapping_object_id = mapping.mapping_object_id
          AND child.attribute_mapping_status = 'active'
          AND child.attribute_mapping_transformation_document IS NOT NULL))
 ORDER BY mapping.object_dependency_order, entity.modeled_entity_schema_name,
          entity.modeled_entity_name, mapping.mapping_object_id
 LIMIT %s
"""
_ATTRIBUTES_FROM: LiteralString = """
  FROM workflow.mapping_object AS mapping
  JOIN workflow.modeled_attribute AS attribute ON attribute.model_id = mapping.model_id
   AND attribute.modeled_entity_type = mapping.modeled_entity_type
   AND attribute.modeled_entity_id = coalesce(
       mapping.logical_entity_id, mapping.dimensional_entity_id)
   AND attribute.status = 'active'
  LEFT JOIN workflow.mapping_attribute AS child
    ON child.mapping_object_id = mapping.mapping_object_id
   AND coalesce(child.logical_attribute_id, child.dimensional_attribute_id) =
       attribute.modeled_attribute_id
   AND child.attribute_mapping_status = 'active'
  LEFT JOIN application.output_template AS template
    ON template.output_template_id = child.output_template_id
 WHERE mapping.model_id = %s AND mapping.mapping_object_id = ANY(%s::BIGINT[])
"""
_ATTRIBUTE_SIZE_SQL: LiteralString = (
    "SELECT count(*) AS rows, coalesce(sum(octet_length("
    "child.attribute_mapping_transformation_document::text)), 0) AS document_bytes"
    + _ATTRIBUTES_FROM
)
_ATTRIBUTES_SQL: LiteralString = (
    "SELECT mapping.mapping_object_id, attribute.ordinal_position, attribute.attribute_name, "
    "attribute.data_type, attribute.is_nullable, attribute.is_natural_key, "
    "attribute.is_surrogate_key, "
    "child.attribute_mapping_transformation_document AS document, template.output_template_code"
    + _ATTRIBUTES_FROM
    + " ORDER BY mapping.mapping_object_id, attribute.ordinal_position, "
    "attribute.modeled_attribute_id"
)
_DOCUMENTS_SQL: LiteralString = """
SELECT mapping_object_id, mapping_transformation_document AS document
  FROM workflow.mapping_object
 WHERE model_id = %s AND mapping_object_id = ANY(%s::BIGINT[])
"""


async def export_mapping_workbook(
    *,
    database: MappingReadDatabase,
    authorizer: AuthorizationService,
    principal: RequestPrincipal,
    tenant_id: int,
    model_id: int,
    entity_type: MappingEntityType,
    source_system_code: str,
    expected_model_revision: int,
) -> MetadataWorkbookDownload:
    async with database.read_transaction(isolation=ReadIsolation.REPEATABLE_READ) as transaction:
        await authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            policy=ToolPolicy.TENANT_READ,
        )
        header = await transaction.fetch_one(_HEADER_SQL, (tenant_id, model_id))
        if header is None:
            raise ModelNotFoundError()
        if header["model_revision"] != expected_model_revision:
            raise ModelRevisionConflictError()
        entities = await transaction.fetch_all(
            _ENTITIES_SQL,
            (
                tenant_id,
                model_id,
                entity_type,
                source_system_code.strip().lower(),
                MAX_MAPPING_SHEETS + 1,
            ),
        )
        if not entities:
            raise InvalidRequestError("No active saved Mappings for this System and layer.")
        if len(entities) > MAX_MAPPING_SHEETS:
            raise InvalidRequestError("Mapping workbook exceeds its sheet limit.")
        ids = [row["mapping_object_id"] for row in entities]
        size = await transaction.fetch_one(_ATTRIBUTE_SIZE_SQL, (model_id, ids))
        if size is None or size["rows"] + len(entities) * 14 > MAX_MAPPING_ROWS:
            raise InvalidRequestError("Mapping workbook exceeds its row limit.")
        if (
            size["document_bytes"] + sum(row["document_bytes"] or 0 for row in entities)
            > MAX_MAPPING_TEXT_CHARACTERS
        ):
            raise InvalidRequestError("Mapping workbook exceeds its text limit.")
        documents = {
            row["mapping_object_id"]: row["document"]
            for row in await transaction.fetch_all(_DOCUMENTS_SQL, (model_id, ids))
        }
        attributes = await transaction.fetch_all(_ATTRIBUTES_SQL, (model_id, ids))

    children: dict[int, list[MappingWorkbookAttribute]] = {key: [] for key in ids}
    for row in attributes:
        document = _standard_document(
            row["document"], row["output_template_code"], "mapping_attribute"
        )
        children[row["mapping_object_id"]].append(
            MappingWorkbookAttribute(
                ordinal_position=row["ordinal_position"],
                target_column=row["attribute_name"],
                data_type=row["data_type"],
                is_nullable=row["is_nullable"],
                is_natural_key=row["is_natural_key"],
                is_surrogate_key=row["is_surrogate_key"],
                transformation_logic=_cell(
                    document.get("transformation_logic", document.get("transformation"))
                ),
                default_record=_cell(document.get("default_record")),
                source_columns=tuple(
                    (*_source_table(reference), _attribute_name(reference))
                    for reference in _references(document, attribute=True)
                ),
            )
        )
    projected: list[MappingWorkbookEntity] = []
    for row in entities:
        document = _standard_document(
            documents[row["mapping_object_id"]], row["output_template_code"], "mapping_object"
        )
        projected.append(
            MappingWorkbookEntity(
                target_layer="Silver" if entity_type == "logical_entity" else "Gold",
                target_schema=row["modeled_entity_schema_name"],
                target_table_name=row["modeled_entity_name"],
                target_table_description=row["definition"],
                entity_type=row["classification"],
                dependency_order=row["object_dependency_order"],
                source_tables=tuple(
                    _source_table(reference) for reference in _references(document, attribute=False)
                ),
                filter_criteria=_cell(document.get("filter_criteria")),
                sample_query=_cell(
                    document.get(
                        "sample_query", document.get("transformation_steps", document.get("steps"))
                    )
                ),
                attributes=tuple(children[row["mapping_object_id"]]),
            )
        )
    try:
        content = build_mapping_workbook(
            model_name=header["model_name"],
            tenant_name=header["tenant_name"],
            system_code=entities[0]["system_code"],
            entities=tuple(projected),
        )
    except MappingWorkbookBuildError as error:
        raise InvalidRequestError(str(error)) from None
    return MetadataWorkbookDownload(
        content=content,
        sheet_count=len(projected),
        filename=f"gds_mapping_{entity_type.removesuffix('_entity')}__model_{model_id}__r{expected_model_revision}.xlsx",
    )


def _standard_document(value: Any, template: str | None, target: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or (
        template and template.casefold() not in MAPPING_REFERENCE_TEMPLATE_CODES[target]
    ):
        raise InvalidRequestError(
            "This workbook requires standard Mapping templates; "
            "custom documents cannot be projected safely."
        )
    return cast(dict[str, Any], value)


def _references(document: dict[str, Any], *, attribute: bool) -> list[dict[str, Any]]:
    fields = (
        (
            "source_columns",
            "source_attributes",
            "source_logical_attributes",
            "source_dimensional_attributes",
        )
        if attribute
        else (
            "source_tables",
            "source_objects",
            "source_logical_entities",
            "source_dimensional_entities",
        )
    )
    references: list[dict[str, Any]] = []
    for field in fields:
        value = document.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in cast(list[Any], value)
        ):
            raise InvalidRequestError(
                "A saved Mapping source reference cannot be represented in the workbook."
            )
        references.extend(cast(list[dict[str, Any]], value))
    return references


def _source_table(reference: dict[str, Any]) -> tuple[str, str]:
    for schema, name in (
        ("object_schema", "object_name"),
        ("entity_schema_name", "entity_name"),
        ("logical_entity_schema_name", "logical_entity_name"),
        ("dimensional_entity_schema_name", "dimensional_entity_name"),
    ):
        if isinstance(reference.get(schema), str) and isinstance(reference.get(name), str):
            return reference[schema], reference[name]
    raise InvalidRequestError("A saved Mapping source is missing its schema or table name.")


def _attribute_name(reference: dict[str, Any]) -> str:
    value = reference.get(
        "attribute_name",
        reference.get("logical_attribute_name", reference.get("dimensional_attribute_name")),
    )
    if not isinstance(value, str):
        raise InvalidRequestError("A saved Mapping source is missing its column name.")
    return value


def _cell(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)
