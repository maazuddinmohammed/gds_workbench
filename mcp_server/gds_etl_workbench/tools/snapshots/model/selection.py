"""Complete Model record selection shared by snapshots and Change Set validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import LiteralString, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ModelingRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from gds_etl_workbench.tools.modeling.assertions import DOCUMENTS_SQL, RECORDS_SQL
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from gds_etl_workbench.tools.modeling.conceptual import (
    CONCEPTUAL_OBJECTS_SQL,
    CONCEPTUAL_RELATIONSHIPS_SQL,
)
from gds_etl_workbench.tools.modeling.mapping import (
    MAPPING_ATTRIBUTES_SQL,
    MAPPING_DEPENDENCIES_SQL,
    MAPPING_OBJECTS_SQL,
)
from gds_etl_workbench.tools.modeling.modeled_layer_common import (
    DIMENSIONAL,
    LOGICAL,
    LayerConfig,
    attributes_sql,
    entities_sql,
    relationships_sql,
    submodels_sql,
)
from gds_etl_workbench.tools.modeling.profiling_analysis import (
    ANALYSIS_SQL,
    PROFILING_SQL,
)

from .contracts import DATASETS_BY_NAME, ModelingDatasetDefinition, ModelSnapshot

_MAX_DATASET_ROWS = 20_000
_MAX_TOTAL_ROWS = 50_000

_MODEL_DETAILS_SQL: LiteralString = """
SELECT model_name,
       model_description,
       silver_model_naming_template,
       silver_model_audit_columns_template,
       gold_model_naming_template,
       gold_model_technical_columns_template,
       gold_model_audit_columns_template
  FROM model.model
 WHERE model_id = %s
   AND is_active
"""

_MODEL_SCOPE_SQL: LiteralString = """
SELECT tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       model_scope.model_scope_is_locked,
       model_scope.is_active
  FROM model.model_scope AS model_scope
  JOIN core.object AS object
    ON object.object_id = model_scope.object_id
   AND object.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
   AND connection.is_active
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = connection.tenant_id
   AND tenant.is_active
  JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
 WHERE model_scope.model_id = %s
   AND model_scope.is_active
 ORDER BY lower(tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(object.object_schema),
          lower(object.object_name)
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
        "from_conceptual_object_id",
        "from_dimensional_attribute_id",
        "from_dimensional_entity_id",
        "from_logical_attribute_id",
        "from_logical_entity_id",
        "from_object_id",
        "from_attribute_id",
        "logical_attribute_id",
        "logical_entity_id",
        "logical_relationship_id",
        "logical_submodel_id",
        "mapping_attribute_id",
        "mapping_object_id",
        "mapping_source_system_dependency_id",
        "modeled_attribute_id",
        "modeled_entity_id",
        "modeling_assertion_document_id",
        "modeling_assertion_record_id",
        "object_id",
        "source_system_id",
        "source_system_name",
        "submodel_id",
        "to_conceptual_object_id",
        "to_dimensional_attribute_id",
        "to_dimensional_entity_id",
        "to_logical_attribute_id",
        "to_logical_entity_id",
        "to_object_id",
        "to_attribute_id",
    }
)
_OPAQUE_JSON_FIELDS = frozenset(
    {
        "attribute_mapping_transformation_document",
        "mapping_package_document",
        "modeling_assertion_details",
        "modeling_assertion_document_metadata",
        "modeling_assertion_source_location",
        "object_mapping_transformation_document",
    }
)


async def build_model_snapshot(
    transaction: ReadTransaction,
    model: ModelReadContext,
) -> ModelSnapshot:
    """Select, bound, clean, and validate one complete effective Model."""
    limit = _MAX_DATASET_ROWS + 1
    rows: dict[str, list[dict[str, object]]] = {}

    rows["model_details"] = await _fetch(
        transaction,
        "model_details",
        _MODEL_DETAILS_SQL,
        (model.model_id,),
    )
    if len(rows["model_details"]) != 1:
        raise InvalidRequestError("Model details could not be resolved.")
    rows["model_scope"] = await _fetch(
        transaction,
        "model_scope",
        _MODEL_SCOPE_SQL,
        (model.model_id, limit),
    )

    rows["profiling_profile"] = await _fetch(
        transaction,
        "profiling_profile",
        PROFILING_SQL,
        (model.model_id, [], [], limit, 0),
    )
    rows["analysis_result"] = await _fetch(
        transaction,
        "analysis_result",
        ANALYSIS_SQL,
        (model.model_id, [], [], [], limit, 0),
    )
    rows["modeling_assertion_document"] = await _fetch(
        transaction,
        "modeling_assertion_document",
        DOCUMENTS_SQL,
        (model.model_id, limit, 0),
    )
    rows["modeling_assertion_record"] = await _fetch(
        transaction,
        "modeling_assertion_record",
        RECORDS_SQL,
        (model.model_id, [], [], limit, 0),
    )
    rows["conceptual_object"] = await _fetch(
        transaction,
        "conceptual_object",
        CONCEPTUAL_OBJECTS_SQL,
        (model.model_id, [], [], limit, 0),
    )
    rows["conceptual_relationship"] = await _fetch(
        transaction,
        "conceptual_relationship",
        CONCEPTUAL_RELATIONSHIPS_SQL,
        (model.model_id, [], [], [], limit, 0),
    )
    await _fetch_layer(transaction, model.model_id, LOGICAL, rows, limit)
    await _fetch_layer(transaction, model.model_id, DIMENSIONAL, rows, limit)
    rows["mapping_dependency"] = await _fetch(
        transaction,
        "mapping_dependency",
        MAPPING_DEPENDENCIES_SQL,
        (model.model_id, limit, 0),
    )
    rows["mapping_object"] = await _fetch(
        transaction,
        "mapping_object",
        MAPPING_OBJECTS_SQL,
        (model.model_id, [], [], limit, 0),
    )
    rows["mapping_attribute"] = await _fetch(
        transaction,
        "mapping_attribute",
        MAPPING_ATTRIBUTES_SQL,
        (model.model_id, [], [], limit, 0),
    )

    if sum(len(dataset_rows) for dataset_rows in rows.values()) > _MAX_TOTAL_ROWS:
        raise InvalidRequestError(
            "The Model Snapshot exceeds the bounded row count; use focused reads."
        )
    records = {
        name: _validate_records(DATASETS_BY_NAME[name], dataset_rows)
        for name, dataset_rows in rows.items()
    }
    return ModelSnapshot.model_validate(
        {
            "model_id": model.model_id,
            "model_name": model.model_name,
            "model_revision": model.model_revision,
            "model_scope": {
                "details": records["model_details"][0],
                "objects": records["model_scope"],
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
                "dependencies": records["mapping_dependency"],
                "objects": records["mapping_object"],
                "attributes": records["mapping_attribute"],
            },
        }
    )


async def _fetch_layer(
    transaction: ReadTransaction,
    model_id: int,
    config: LayerConfig,
    rows: dict[str, list[dict[str, object]]],
    limit: int,
) -> None:
    rows[f"{config.layer}_submodel"] = await _fetch(
        transaction,
        f"{config.layer}_submodel",
        submodels_sql(config),
        (model_id, limit, 0),
    )
    rows[f"{config.layer}_entity"] = await _fetch(
        transaction,
        f"{config.layer}_entity",
        entities_sql(config),
        (model_id, [], [], limit, 0),
    )
    rows[f"{config.layer}_attribute"] = await _fetch(
        transaction,
        f"{config.layer}_attribute",
        attributes_sql(config),
        (model_id, [], [], limit, 0),
    )
    rows[f"{config.layer}_relationship"] = await _fetch(
        transaction,
        f"{config.layer}_relationship",
        relationships_sql(config),
        (model_id, [], [], [], limit, 0),
    )


async def _fetch(
    transaction: ReadTransaction,
    dataset: str,
    query: LiteralString,
    parameters: tuple[object, ...],
) -> list[dict[str, object]]:
    rows = await transaction.fetch_all(query, parameters)
    if len(rows) > _MAX_DATASET_ROWS:
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
