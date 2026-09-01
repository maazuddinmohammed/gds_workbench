"""Complete Model record selection shared by snapshots and Change Set validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import LiteralString, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    ModelingRecord,
    QAAuthoringContextRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from gds_etl_workbench.tools.change_sets.model_validation import (
    CodeGenerationTargetContext,
    qa_code_context_digest,
    qa_current_code_records,
    qa_mapping_context_digest,
)
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
_MAX_QA_TARGET_SYSTEM_ASSOCIATIONS = 50_000
type _QACodeTargetKey = tuple[str, str, str, str, str, str]

_MODEL_DETAILS_SQL: LiteralString = """
SELECT model_name,
       model_description,
       silver_model_naming_instructions,
       silver_model_audit_columns_template,
       gold_model_naming_instructions,
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
       eligibility.object_schema,
       eligibility.object_name,
       eligibility.zone_code,
       eligibility.is_bronze_source_eligible,
       eligibility.is_dimensional_source_eligible,
       eligibility.is_logical_mapping_target_eligible,
       eligibility.is_dimensional_mapping_target_eligible,
       model_scope.model_scope_is_locked,
       TRUE AS is_active
  FROM workflow.list_model_object_eligibility(%s) AS eligibility
  JOIN model.model_scope AS model_scope
    ON model_scope.model_id = eligibility.model_id
   AND model_scope.object_id = eligibility.object_id
   AND model_scope.is_active
  JOIN core.object AS object
    ON object.object_id = eligibility.object_id
   AND object.connection_id = eligibility.connection_id
   AND object.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = eligibility.connection_id
   AND connection.system_id = eligibility.system_id
   AND connection.is_active
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligibility.object_tenant_id
   AND tenant.is_active
  JOIN core.system AS system
    ON system.system_id = eligibility.system_id
   AND system.is_active
 ORDER BY lower(tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(eligibility.object_schema),
          lower(eligibility.object_name)
 LIMIT %s
"""

_GENERATED_CODE_SQL: LiteralString = """
WITH eligible_object AS MATERIALIZED (
    SELECT *
      FROM workflow.list_model_object_eligibility(%s)
)
SELECT generated.generated_code_id,
       tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       generated.modeled_entity_type,
       generated.artifact_type,
       generated.generated_code_content,
       generated.mapping_context_digest,
       generated.source_context_digest,
       generated.generated_code_digest,
       generated.generated_code_status,
       generated.generated_code_is_locked
  FROM workflow.generated_code AS generated
  JOIN eligible_object AS eligibility
    ON eligibility.model_id = generated.model_id
   AND eligibility.object_id = generated.object_id
  JOIN core.object AS object
    ON object.object_id = generated.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligibility.object_tenant_id
 ORDER BY lower(tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(object.object_schema),
          lower(object.object_name)
LIMIT %s
"""

_QA_AUTHORING_CONTEXT_SQL: LiteralString = """
SELECT context.modeled_entity_type,
       context.object_id,
       context.source_system_count,
       context.mapping_context_digest,
       context.source_context_digest,
       context.source_context
  FROM workflow.list_code_generation_target_context(
           %s,
           'logical_entity',
           NULL
       ) AS context
UNION ALL
SELECT context.modeled_entity_type,
       context.object_id,
       context.source_system_count,
       context.mapping_context_digest,
       context.source_context_digest,
       context.source_context
  FROM workflow.list_code_generation_target_context(
           %s,
           'dimensional_entity',
           NULL
       ) AS context
 ORDER BY modeled_entity_type,
          object_id
 LIMIT %s
"""

_VALIDATION_GROUP_SQL: LiteralString = """
SELECT validation_group.validation_group_id,
       tenant.tenant_code,
       system.system_code,
       validation_group.validation_group_name,
       validation_group.validation_group_description,
       validation_group.mapping_context_digest,
       validation_group.code_context_digest,
       validation_group.is_active
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
       validation_check.is_active
  FROM workflow.validation_check AS validation_check
  JOIN workflow.validation_group AS validation_group
    ON validation_group.validation_group_id =
       validation_check.validation_group_id
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
        "from_conceptual_object_id",
        "from_dimensional_attribute_id",
        "from_dimensional_entity_id",
        "from_logical_attribute_id",
        "from_logical_entity_id",
        "from_object_id",
        "from_attribute_id",
        "generated_code_id",
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
        "validation_check_id",
        "validation_group_id",
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
    rows["generated_code"] = await _fetch(
        transaction,
        "generated_code",
        _GENERATED_CODE_SQL,
        (model.model_id, limit),
    )
    qa_target_context_rows = await _fetch(
        transaction,
        "qa_authoring_context",
        _QA_AUTHORING_CONTEXT_SQL,
        (model.model_id, model.model_id, limit),
    )
    rows["validation_group"] = await _fetch(
        transaction,
        "validation_group",
        _VALIDATION_GROUP_SQL,
        (model.model_id, limit),
    )
    rows["validation_check"] = await _fetch(
        transaction,
        "validation_check",
        _VALIDATION_CHECK_SQL,
        (model.model_id, limit),
    )

    records = {
        name: _validate_records(DATASETS_BY_NAME[name], dataset_rows)
        for name, dataset_rows in rows.items()
    }
    generated_code_records = cast(
        tuple[GeneratedCodeRecord, ...],
        records["generated_code"],
    )
    records["qa_authoring_context"] = _build_qa_authoring_context_records(
        qa_target_context_rows,
        generated_code_records,
    )
    if sum(len(dataset_records) for dataset_records in records.values()) > _MAX_TOTAL_ROWS:
        raise InvalidRequestError(
            "The Model Snapshot exceeds the bounded row count; use focused reads."
        )
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
            "code_generation": {"artifacts": records["generated_code"]},
            "qa": {
                "authoring_contexts": records["qa_authoring_context"],
                "groups": records["validation_group"],
                "checks": records["validation_check"],
            },
        }
    )


def _build_qa_authoring_context_records(
    rows: list[dict[str, object]],
    generated_code_records: tuple[GeneratedCodeRecord, ...],
) -> tuple[QAAuthoringContextRecord, ...]:
    contexts_by_system: dict[str, list[CodeGenerationTargetContext]] = {}
    exact_system_keys: dict[str, tuple[str, str]] = {}
    seen_targets: set[tuple[object, ...]] = set()
    association_count = 0
    model_tenant_code: str | None = None

    for row in rows:
        modeled_entity_type = row.get("modeled_entity_type")
        if not isinstance(modeled_entity_type, str) or modeled_entity_type not in {
            "logical_entity",
            "dimensional_entity",
        }:
            raise InvalidRequestError("A QA authoring target has an invalid modeled layer.")
        source_context = row.get("source_context")
        if not isinstance(source_context, Mapping):
            raise InvalidRequestError("A QA authoring target has no source context.")
        source_context_document = cast(Mapping[object, object], source_context)
        target = source_context_document.get("target")
        source_systems = source_context_document.get("source_systems")
        if not isinstance(target, Mapping) or not isinstance(source_systems, list):
            raise InvalidRequestError("A QA authoring target has an invalid source context.")
        target_document = cast(Mapping[object, object], target)
        object_key = cast(
            tuple[str, str, str, str, str],
            tuple(
                _required_qa_context_string(target_document, field)
                for field in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                )
            ),
        )
        if model_tenant_code is None:
            model_tenant_code = object_key[0]
        elif model_tenant_code != object_key[0]:
            raise InvalidRequestError("QA authoring contexts span multiple exact Tenants.")

        mapping_context_digest = _required_qa_context_digest(row.get("mapping_context_digest"))
        source_context_digest = _required_qa_context_digest(row.get("source_context_digest"))
        source_system_codes: list[str] = []
        for source_system in cast(list[object], source_systems):
            if not isinstance(source_system, Mapping):
                raise InvalidRequestError("A QA authoring target has an invalid source System.")
            source_system_codes.append(
                _required_qa_context_string(
                    cast(Mapping[object, object], source_system),
                    "system_code",
                )
            )
        source_system_count = row.get("source_system_count")
        if (
            type(source_system_count) is not int
            or source_system_count < 1
            or source_system_count != len(source_system_codes)
        ):
            raise InvalidRequestError("A QA authoring target has an invalid source System count.")
        normalized_source_codes = {normalize_model_key_value(code) for code in source_system_codes}
        if len(normalized_source_codes) != len(source_system_codes):
            raise InvalidRequestError("A QA authoring target has duplicate source System codes.")

        target_key = (
            *(normalize_model_key_value(value) for value in object_key),
            modeled_entity_type,
        )
        if target_key in seen_targets:
            raise InvalidRequestError("QA authoring contexts contain a duplicate target.")
        seen_targets.add(target_key)
        context = CodeGenerationTargetContext(
            object_key=object_key,
            modeled_entity_type=modeled_entity_type,
            source_system_codes=frozenset(source_system_codes),
            mapping_context_digest=mapping_context_digest,
            source_context_digest=source_context_digest,
        )
        association_count += len(source_system_codes)
        if association_count > _MAX_QA_TARGET_SYSTEM_ASSOCIATIONS:
            raise InvalidRequestError(
                "The QA authoring context exceeds its bounded target/System count."
            )
        for source_system_code in source_system_codes:
            normalized_system = normalize_model_key_value(source_system_code)
            exact_key = (object_key[0], source_system_code)
            existing_key = exact_system_keys.setdefault(normalized_system, exact_key)
            if existing_key != exact_key:
                raise InvalidRequestError(
                    "QA authoring contexts contain inconsistent exact System codes."
                )
            contexts_by_system.setdefault(normalized_system, []).append(context)
    if len(contexts_by_system) > _MAX_DATASET_ROWS:
        raise InvalidRequestError(
            "The qa_authoring_context Snapshot dataset exceeds its bounded row count."
        )

    generated_by_target: dict[_QACodeTargetKey, GeneratedCodeRecord] = {
        (
            normalize_model_key_value(record.tenant_code),
            normalize_model_key_value(record.system_code),
            normalize_model_key_value(record.connection_code),
            normalize_model_key_value(record.object_schema),
            normalize_model_key_value(record.object_name),
            record.modeled_entity_type,
        ): record
        for record in generated_code_records
    }
    authoring_rows: list[dict[str, object]] = []
    for normalized_system, relevant_contexts_list in contexts_by_system.items():
        relevant_contexts = tuple(relevant_contexts_list)
        exact_tenant_code, exact_system_code = exact_system_keys[normalized_system]
        candidate_code_list: list[GeneratedCodeRecord] = []
        for context in relevant_contexts:
            normalized_object_key = cast(
                tuple[str, str, str, str, str],
                tuple(normalize_model_key_value(value) for value in context.object_key),
            )
            record = generated_by_target.get((*normalized_object_key, context.modeled_entity_type))
            if record is not None:
                candidate_code_list.append(record)
        candidate_code = tuple(candidate_code_list)
        current_code = cast(
            tuple[GeneratedCodeRecord, ...],
            qa_current_code_records(
                relevant_contexts,
                candidate_code,
                exact_system_code,
            ),
        )
        mapping_digest = qa_mapping_context_digest(
            relevant_contexts,
            exact_system_code,
        )
        if mapping_digest is None:
            raise InvalidRequestError("A QA authoring System has no Mapping context.")
        authoring_rows.append(
            {
                "tenant_code": exact_tenant_code,
                "system_code": exact_system_code,
                "mapping_context_digest": mapping_digest,
                "code_context_digest": qa_code_context_digest(
                    relevant_contexts,
                    candidate_code,
                    exact_system_code,
                ),
                "mapping_target_count": len(relevant_contexts),
                "current_code_target_count": len(current_code),
                "current_code_references": [
                    {
                        "tenant_code": record.tenant_code,
                        "system_code": record.system_code,
                        "connection_code": record.connection_code,
                        "object_schema": record.object_schema,
                        "object_name": record.object_name,
                        "modeled_entity_type": record.modeled_entity_type,
                        "artifact_type": record.artifact_type,
                        "generated_code_digest": record.generated_code_digest,
                    }
                    for record in current_code
                ],
            }
        )
    return cast(
        tuple[QAAuthoringContextRecord, ...],
        _validate_records(
            DATASETS_BY_NAME["qa_authoring_context"],
            authoring_rows,
        ),
    )


def _required_qa_context_string(
    document: Mapping[object, object],
    field: str,
) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > 400:
        raise InvalidRequestError("A QA authoring context has an invalid natural key.")
    return value


def _required_qa_context_digest(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidRequestError("A QA authoring context has an invalid digest.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise InvalidRequestError("A QA authoring context has an invalid digest.")
    return normalized


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
