"""Complete Model record selection shared by web workflows and MCP snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import LiteralString, cast

from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.modeling.assertions import DOCUMENTS_SQL, RECORDS_SQL
from gds_etl_workbench.application.modeling.conceptual import (
    HISTORICAL_CONCEPTUAL_OBJECTS_SQL,
    HISTORICAL_CONCEPTUAL_RELATIONSHIPS_SQL,
)
from gds_etl_workbench.application.modeling.modeled_layer import (
    DIMENSIONAL,
    LOGICAL,
    LayerConfig,
    attributes_sql,
    entities_sql,
    relationships_sql,
    submodels_sql,
)
from gds_etl_workbench.application.modeling.profiling_analysis import (
    HISTORICAL_ANALYSIS_SQL,
    HISTORICAL_PROFILING_SQL,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ModelingRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.domain.snapshots.model import (
    DATASETS_BY_NAME,
    ModelingDatasetDefinition,
    ModelSnapshot,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

_MAX_DATASET_ROWS = 20_000
_MAX_TOTAL_ROWS = 50_000

_MODEL_DETAILS_SQL: LiteralString = """
SELECT model_name,
       model_description,
       logical_schemas,
       dimensional_schemas,
       logical_entity_scd_type,
       dimensional_entity_scd_type,
       silver_model_naming_instructions,
       silver_model_audit_columns_template,
       gold_model_naming_instructions,
       gold_model_technical_columns_template,
       gold_model_audit_columns_template,
       (SELECT tenant_code FROM core.tenant WHERE tenant_id = target_model.tenant_id)
           AS model_tenant_code
  FROM model.model AS target_model
 WHERE model_id = %s
   AND is_active
"""

_MODEL_INPUT_SCOPE_SQL: LiteralString = """
SELECT placement_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       scope.model_input_scope_is_locked,
       scope.is_active
  FROM model.model_input_scope AS scope
  JOIN core.object AS object
    ON object.object_id = scope.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
 WHERE scope.model_id = %s
 ORDER BY lower(placement_tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(object.object_schema),
          lower(object.object_name)
 LIMIT %s
"""

_MAPPING_OBJECT_SQL: LiteralString = """
SELECT mapping.mapping_object_id,
       entity.modeled_entity_type, entity.modeled_entity_schema_name, entity.modeled_entity_name,
       source_system.system_code AS source_system_code,
       output_template.output_template_code,
       mapping.object_dependency_order, mapping.mapping_transformation_document,
       mapping.object_mapping_status, mapping.object_mapping_is_locked
  FROM workflow.mapping_object AS mapping
  JOIN workflow.modeled_entity AS entity
    ON entity.model_id = mapping.model_id
   AND entity.modeled_entity_type = mapping.modeled_entity_type
   AND entity.modeled_entity_id = COALESCE(mapping.logical_entity_id, mapping.dimensional_entity_id)
  JOIN core.system AS source_system ON source_system.system_id = mapping.source_system_id
  LEFT JOIN application.output_template USING (output_template_id)
 WHERE mapping.model_id = %s
 ORDER BY mapping.object_dependency_order, entity.modeled_entity_type,
          lower(entity.modeled_entity_schema_name), lower(entity.modeled_entity_name),
          lower(source_system.system_code)
 LIMIT %s
"""

_MAPPING_ATTRIBUTE_SQL: LiteralString = """
SELECT attribute.mapping_attribute_id,
       entity.modeled_entity_type, entity.modeled_entity_schema_name, entity.modeled_entity_name,
       modeled.modeled_attribute_name,
       source_system.system_code AS source_system_code,
       output_template.output_template_code,
       attribute.attribute_mapping_transformation_document,
       attribute.attribute_mapping_status, attribute.attribute_mapping_is_locked
  FROM workflow.mapping_attribute AS attribute
  JOIN workflow.mapping_object AS mapping USING (mapping_object_id, model_id)
  JOIN workflow.modeled_entity AS entity
    ON entity.model_id = mapping.model_id
   AND entity.modeled_entity_type = mapping.modeled_entity_type
   AND entity.modeled_entity_id = COALESCE(mapping.logical_entity_id, mapping.dimensional_entity_id)
  JOIN workflow.modeled_attribute AS modeled
    ON modeled.model_id = mapping.model_id
   AND modeled.modeled_entity_type = mapping.modeled_entity_type
   AND modeled.modeled_entity_id = entity.modeled_entity_id
   AND modeled.modeled_attribute_id = COALESCE(
       attribute.logical_attribute_id, attribute.dimensional_attribute_id)
  JOIN core.system AS source_system ON source_system.system_id = mapping.source_system_id
  LEFT JOIN application.output_template
    ON output_template.output_template_id = attribute.output_template_id
 WHERE mapping.model_id = %s
 ORDER BY entity.modeled_entity_type, lower(entity.modeled_entity_schema_name),
          lower(entity.modeled_entity_name), lower(source_system.system_code),
          lower(modeled.modeled_attribute_name)
 LIMIT %s
"""

_GENERATED_CODE_SQL: LiteralString = """
SELECT generated.generated_code_id,
       entity.modeled_entity_type, entity.modeled_entity_schema_name, entity.modeled_entity_name,
       generated.artifact_name, generated.artifact_type, generated.generated_code_content,
       generated.generated_code_status, generated.generated_code_is_locked
  FROM workflow.generated_code AS generated
  JOIN workflow.modeled_entity AS entity
    ON entity.model_id = generated.model_id
   AND entity.modeled_entity_type = generated.modeled_entity_type
   AND entity.modeled_entity_id = COALESCE(
       generated.logical_entity_id, generated.dimensional_entity_id)
 WHERE generated.model_id = %s
 ORDER BY entity.modeled_entity_type, lower(entity.modeled_entity_schema_name),
          lower(entity.modeled_entity_name), lower(generated.artifact_name)
 LIMIT %s
"""

_GENERATED_CODE_SOURCE_SYSTEM_SQL: LiteralString = """
SELECT association.generated_code_source_system_id,
       entity.modeled_entity_type, entity.modeled_entity_schema_name, entity.modeled_entity_name,
       generated.artifact_name, system.system_code AS source_system_code,
       association.generated_code_source_system_status,
       association.generated_code_source_system_is_locked
  FROM workflow.generated_code_source_system AS association
  JOIN workflow.generated_code AS generated USING (generated_code_id)
  JOIN workflow.modeled_entity AS entity
    ON entity.model_id = generated.model_id
   AND entity.modeled_entity_type = generated.modeled_entity_type
   AND entity.modeled_entity_id = COALESCE(
       generated.logical_entity_id, generated.dimensional_entity_id)
  JOIN core.system AS system ON system.system_id = association.source_system_id
 WHERE generated.model_id = %s
 ORDER BY entity.modeled_entity_type, lower(entity.modeled_entity_schema_name),
          lower(entity.modeled_entity_name), lower(generated.artifact_name),
          lower(system.system_code)
 LIMIT %s
"""

_VALIDATION_GROUP_SQL: LiteralString = """
SELECT validation_group.validation_group_id,
       tenant.tenant_code,
       system.system_code,
       validation_group.validation_group_name,
       validation_group.validation_group_description,
       validation_group.is_active,
       validation_group.is_locked
  FROM workflow.validation_group AS validation_group
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = validation_group.tenant_id
  JOIN core.system AS system
    ON system.system_id = validation_group.system_id
 WHERE validation_group.model_id = %s
 ORDER BY lower(tenant.tenant_code),
          lower(system.system_code),
          lower(validation_group.validation_group_name)
 LIMIT %s
"""

_VALIDATION_CHECK_SQL: LiteralString = """
SELECT validation_check.validation_check_id,
       validation_group.validation_group_id,
       tenant.tenant_code,
       system.system_code,
       validation_group.validation_group_name,
       validation_check.validation_check_name,
       validation_check.validation_check_description,
       validation_check.validation_category_code,
       validation_check.validation_severity,
       validation_check.validation_query_sql,
       validation_check.validation_comparison_query_sql,
       validation_check.validation_result_data_type,
       validation_check.validation_comparison_operator,
       validation_check.validation_comparison_value_type,
       validation_check.validation_comparison_value,
       validation_check.is_active,
       validation_check.is_locked
  FROM workflow.validation_check AS validation_check
  JOIN workflow.validation_group AS validation_group
    ON validation_group.validation_group_id = validation_check.validation_group_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = validation_group.tenant_id
  JOIN core.system AS system
    ON system.system_id = validation_group.system_id
 WHERE validation_group.model_id = %s
 ORDER BY lower(tenant.tenant_code),
          lower(system.system_code),
          lower(validation_group.validation_group_name),
          lower(validation_check.validation_check_name)
 LIMIT %s
"""

_INTERNAL_READ_FIELDS = frozenset(
    {
        "analysis_result_id",
        "attribute_id",
        "attribute_source_mapping_id",
        "conceptual_object_id",
        "conceptual_relationship_id",
        "conceptual_support_id",
        "dimensional_attribute_id",
        "dimensional_entity_id",
        "dimensional_relationship_id",
        "dimensional_submodel_id",
        "entity_count",
        "entity_source_mapping_id",
        "entity_submodel_id",
        "from_attribute_id",
        "from_conceptual_object_id",
        "from_dimensional_attribute_id",
        "from_dimensional_entity_id",
        "from_logical_attribute_id",
        "from_logical_entity_id",
        "from_object_id",
        "generated_code_id",
        "generated_code_source_system_id",
        "logical_attribute_id",
        "logical_entity_id",
        "logical_relationship_id",
        "logical_submodel_id",
        "mapping_attribute_id",
        "mapping_object_id",
        "model_tenant_code",
        "modeled_attribute_id",
        "modeled_entity_id",
        "modeling_assertion_document_id",
        "modeling_assertion_record_id",
        "object_id",
        "source_system_id",
        "source_system_name",
        "submodel_id",
        "to_attribute_id",
        "to_conceptual_object_id",
        "to_dimensional_attribute_id",
        "to_dimensional_entity_id",
        "to_logical_attribute_id",
        "to_logical_entity_id",
        "to_object_id",
        "validation_check_id",
        "validation_group_id",
    }
)
_OPAQUE_JSON_FIELDS = frozenset(
    {
        "attribute_mapping_transformation_document",
        "mapping_transformation_document",
        "modeling_assertion_details",
        "modeling_assertion_document_metadata",
        "modeling_assertion_source_location",
    }
)


@dataclass(frozen=True, slots=True)
class ModelReviewSnapshot:
    snapshot: ModelSnapshot = field(repr=False)
    records_by_id: dict[str, dict[int, ModelingRecord]] = field(repr=False)


async def build_model_snapshot(
    transaction: ReadTransaction,
    model: ModelReadContext,
    *,
    enforce_row_limits: bool = True,
) -> ModelSnapshot:
    return (
        await read_model_review_snapshot(transaction, model, enforce_row_limits=enforce_row_limits)
    ).snapshot


async def read_model_review_snapshot(
    transaction: ReadTransaction,
    model: ModelReadContext,
    *,
    enforce_row_limits: bool = True,
) -> ModelReviewSnapshot:
    """Validate the complete Model; MCP limits apply unless a backend caller opts out."""
    # PostgreSQL LIMIT NULL retains all rows for authorized web agent context.
    limit = _MAX_DATASET_ROWS + 1 if enforce_row_limits else None
    fetch = partial(_fetch, enforce_row_limits=enforce_row_limits)
    rows: dict[str, list[dict[str, object]]] = {}
    rows["model_details"] = await fetch(
        transaction,
        "model_details",
        _MODEL_DETAILS_SQL,
        (model.model_id,),
    )
    if len(rows["model_details"]) != 1:
        raise InvalidRequestError("Model details could not be resolved.")
    rows["model_input_scope"] = await fetch(
        transaction,
        "model_input_scope",
        _MODEL_INPUT_SCOPE_SQL,
        (model.model_id, limit),
    )
    rows["profiling_profile"] = await fetch(
        transaction,
        "profiling_profile",
        HISTORICAL_PROFILING_SQL,
        (model.model_id, list(model.readable_source_tenant_ids), [], [], limit, 0),
    )
    rows["analysis_result"] = await fetch(
        transaction,
        "analysis_result",
        HISTORICAL_ANALYSIS_SQL,
        (model.model_id, list(model.readable_source_tenant_ids), [], [], [], limit, 0),
    )
    rows["modeling_assertion_document"] = await fetch(
        transaction,
        "modeling_assertion_document",
        DOCUMENTS_SQL,
        (model.model_id, limit, 0),
    )
    rows["modeling_assertion_record"] = await fetch(
        transaction,
        "modeling_assertion_record",
        RECORDS_SQL,
        (model.model_id, [], [], limit, 0),
    )
    rows["conceptual_object"] = await fetch(
        transaction,
        "conceptual_object",
        HISTORICAL_CONCEPTUAL_OBJECTS_SQL,
        (model.model_id, list(model.readable_source_tenant_ids), [], [], limit, 0),
    )
    rows["conceptual_relationship"] = await fetch(
        transaction,
        "conceptual_relationship",
        HISTORICAL_CONCEPTUAL_RELATIONSHIPS_SQL,
        (model.model_id, list(model.readable_source_tenant_ids), [], [], [], limit, 0),
    )
    await _fetch_layer(transaction, model, LOGICAL, rows, limit)
    await _fetch_layer(transaction, model, DIMENSIONAL, rows, limit)
    downstream_queries: tuple[tuple[str, LiteralString], ...] = (
        ("mapping_object", _MAPPING_OBJECT_SQL),
        ("mapping_attribute", _MAPPING_ATTRIBUTE_SQL),
        ("generated_code", _GENERATED_CODE_SQL),
        ("generated_code_source_system", _GENERATED_CODE_SOURCE_SYSTEM_SQL),
        ("validation_group", _VALIDATION_GROUP_SQL),
        ("validation_check", _VALIDATION_CHECK_SQL),
    )
    for dataset, query in downstream_queries:
        rows[dataset] = await fetch(
            transaction,
            dataset,
            query,
            (model.model_id, limit),
        )

    records = {
        name: _validate_records(DATASETS_BY_NAME[name], dataset_rows)
        for name, dataset_rows in rows.items()
    }
    if (
        enforce_row_limits
        and sum(len(dataset_records) for dataset_records in records.values()) > _MAX_TOTAL_ROWS
    ):
        raise InvalidRequestError(
            "The Model Snapshot exceeds the bounded row count; use focused reads."
        )
    snapshot = ModelSnapshot.model_validate(
        {
            "model_id": model.model_id,
            "model_name": model.model_name,
            "model_revision": model.model_revision,
            "model_tenant_code": rows["model_details"][0].get(
                "model_tenant_code", model.tenant_code
            ),
            "other_active_model_names": model.other_active_model_names,
            "model_input_scope": {
                "details": records["model_details"][0],
                "objects": records["model_input_scope"],
            },
            "profiling": {"profiles": records["profiling_profile"]},
            "analysis": {"relationships": records["analysis_result"]},
            "assertion": {
                "documents": records["modeling_assertion_document"],
                "records": records["modeling_assertion_record"],
            },
            "conceptual": {
                "objects": records["conceptual_object"],
                "relationships": records["conceptual_relationship"],
            },
            "logical": {
                "submodels": records["logical_submodel"],
                "entities": records["logical_entity"],
                "attributes": records["logical_attribute"],
                "relationships": records["logical_relationship"],
            },
            "dimensional": {
                "submodels": records["dimensional_submodel"],
                "entities": records["dimensional_entity"],
                "attributes": records["dimensional_attribute"],
                "relationships": records["dimensional_relationship"],
            },
            "mapping": {
                "objects": records["mapping_object"],
                "attributes": records["mapping_attribute"],
            },
            "code_generation": {
                "artifacts": records["generated_code"],
                "source_systems": records["generated_code_source_system"],
            },
            "validation": {
                "groups": records["validation_group"],
                "checks": records["validation_check"],
            },
        }
    )

    # Reuse the same owned, history-preserving selection for lifecycle review.
    # Numeric IDs stay outside canonical snapshots, agent inputs and MCP exports.
    records_by_id: dict[str, dict[int, ModelingRecord]] = {}
    for dataset in (
        "modeling_assertion_record",
        "analysis_result",
        "conceptual_object",
        "conceptual_relationship",
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
        "logical_relationship",
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
        "mapping_object",
        "mapping_attribute",
        "generated_code",
        "generated_code_source_system",
        "validation_group",
        "validation_check",
    ):
        definition = DATASETS_BY_NAME[dataset]
        by_key = {
            tuple(
                normalize_model_key_value(getattr(record, name))
                for name in definition.canonical_key
            ): record
            for record in records[dataset]
        }
        id_field = dataset + "_id"
        indexed: dict[int, ModelingRecord] = {}
        for row in rows[dataset]:
            record_id = row.get(id_field)
            key = tuple(normalize_model_key_value(row[name]) for name in definition.canonical_key)
            if (
                not isinstance(record_id, int)
                or isinstance(record_id, bool)
                or record_id < 1
                or record_id in indexed
                or key not in by_key
            ):
                raise InvalidRequestError("The Model record identity could not be resolved.")
            indexed[record_id] = by_key[key]
        records_by_id[dataset] = indexed
    return ModelReviewSnapshot(snapshot=snapshot, records_by_id=records_by_id)


async def _fetch_layer(
    transaction: ReadTransaction,
    model: ModelReadContext,
    config: LayerConfig,
    rows: dict[str, list[dict[str, object]]],
    limit: int | None,
) -> None:
    fetch = partial(_fetch, enforce_row_limits=limit is not None)
    rows[f"{config.layer}_submodel"] = await fetch(
        transaction,
        f"{config.layer}_submodel",
        submodels_sql(config),
        (model.model_id, limit, 0),
    )
    rows[f"{config.layer}_entity"] = await fetch(
        transaction,
        f"{config.layer}_entity",
        entities_sql(config, historical=True),
        (
            model.model_id,
            *([list(model.readable_source_tenant_ids)] if config.layer == "logical" else []),
            [],
            [],
            limit,
            0,
        ),
    )
    rows[f"{config.layer}_attribute"] = await fetch(
        transaction,
        f"{config.layer}_attribute",
        attributes_sql(config, historical=True),
        (
            model.model_id,
            *([list(model.readable_source_tenant_ids)] if config.layer == "logical" else []),
            [],
            [],
            limit,
            0,
        ),
    )
    rows[f"{config.layer}_relationship"] = await fetch(
        transaction,
        f"{config.layer}_relationship",
        relationships_sql(config),
        (model.model_id, [], [], [], limit, 0),
    )


async def _fetch(
    transaction: ReadTransaction,
    dataset: str,
    query: LiteralString,
    parameters: tuple[object, ...],
    *,
    enforce_row_limits: bool = True,
) -> list[dict[str, object]]:
    rows = await transaction.fetch_all(query, parameters)
    if enforce_row_limits and len(rows) > _MAX_DATASET_ROWS:
        raise InvalidRequestError(f"The {dataset} Snapshot dataset exceeds its bounded row count.")
    return rows


def _validate_records(
    definition: ModelingDatasetDefinition,
    rows: list[dict[str, object]],
) -> tuple[ModelingRecord, ...]:
    validated: list[ModelingRecord] = []
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        cleaned = _remove_internal_fields(row)
        record = definition.row_model.model_validate(cleaned, strict=False)
        key = tuple(
            normalize_model_key_value(getattr(record, field)) for field in definition.canonical_key
        )
        if key in seen:
            raise InvalidRequestError(
                f"The {definition.name} Snapshot dataset has a duplicate canonical key."
            )
        seen.add(key)
        validated.append(record)
    validated.sort(
        key=lambda record: tuple(
            str(normalize_model_key_value(getattr(record, field)))
            for field in definition.canonical_key
        )
    )
    return tuple(validated)


def _remove_internal_fields(value: object, *, parent: str | None = None) -> object:
    if parent in _OPAQUE_JSON_FIELDS:
        return value
    if isinstance(value, Mapping):
        cleaned: dict[str, object] = {}
        for key, item in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise InvalidRequestError("A Snapshot record contains a non-string field name.")
            if key not in _INTERNAL_READ_FIELDS:
                cleaned[key] = _remove_internal_fields(item, parent=key)
        return cleaned
    if isinstance(value, list):
        return [_remove_internal_fields(item, parent=parent) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return tuple(
            _remove_internal_fields(item, parent=parent) for item in cast(tuple[object, ...], value)
        )
    return value
