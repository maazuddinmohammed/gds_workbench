"""Atomic materialization of validated ID-free Model records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, LiteralString, cast

from psycopg.types.json import Jsonb

from gds_etl_workbench.application.modeling.modeled_layer import (
    DIMENSIONAL,
    LOGICAL,
    LayerConfig,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    DimensionalSubmodelRecord,
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    LogicalSubmodelRecord,
    MappingAttributeRecord,
    MappingDependencyRecord,
    MappingObjectRecord,
    ModelAttributeBindingRecord,
    ModelDetailsRecord,
    ModelingAssertionDocumentRecord,
    ModelingAssertionRecordRecord,
    ModelingRecord,
    ModelInputScopeRecord,
    ModelObjectBindingRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ProfilingProfileRecord,
    ValidationCheckRecord,
    ValidationGroupRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction

_UPDATE_MODEL_DETAILS_SQL: LiteralString = """
UPDATE model.model
   SET model_name = %s,
       model_description = %s,
       silver_model_naming_instructions = %s,
       silver_model_audit_columns_template = %s,
       gold_model_naming_instructions = %s,
       gold_model_technical_columns_template = %s,
       gold_model_audit_columns_template = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE model_id = %s
   AND is_active
RETURNING model_id
"""

_UPSERT_MODEL_INPUT_SCOPE_SQL: LiteralString = """
INSERT INTO model.model_input_scope (
    model_id,
    object_id,
    model_input_scope_is_locked,
    is_active
)
VALUES (%s, %s, %s, %s)
ON CONFLICT (model_id, object_id) DO UPDATE
   SET model_input_scope_is_locked = EXCLUDED.model_input_scope_is_locked,
       is_active = EXCLUDED.is_active,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING model_input_scope_id
"""

_RESOLVE_OBJECT_SQL: LiteralString = """
SELECT object.object_id,
       connection.system_id
  FROM core.object AS object
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
   AND lower(btrim(placement_tenant.tenant_code)) = lower(btrim(%s))
   AND placement_tenant.is_active
  JOIN model.model AS target_model
    ON target_model.model_id = %s
   AND target_model.is_active
 WHERE lower(btrim(system.system_code)) = lower(btrim(%s))
   AND lower(btrim(connection.connection_code)) = lower(btrim(%s))
   AND lower(btrim(object.object_schema)) = lower(btrim(%s))
   AND lower(btrim(object.object_name)) = lower(btrim(%s))
   AND connection.is_active
   AND object.is_active
   AND system.is_active
   AND object.source_tenant_id = target_model.tenant_id
"""

_RESOLVE_ATTRIBUTE_SQL: LiteralString = """
SELECT object.object_id,
       attribute.attribute_id,
       connection.system_id
  FROM core.object AS object
  JOIN core.attribute AS attribute
    ON attribute.object_id = object.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
   AND lower(btrim(placement_tenant.tenant_code)) = lower(btrim(%s))
   AND placement_tenant.is_active
  JOIN model.model AS target_model
    ON target_model.model_id = %s
   AND target_model.is_active
 WHERE lower(btrim(system.system_code)) = lower(btrim(%s))
   AND lower(btrim(connection.connection_code)) = lower(btrim(%s))
   AND lower(btrim(object.object_schema)) = lower(btrim(%s))
   AND lower(btrim(object.object_name)) = lower(btrim(%s))
   AND lower(btrim(attribute.attribute_name)) = lower(btrim(%s))
   AND connection.is_active
   AND object.is_active
   AND attribute.is_active
   AND system.is_active
   AND object.source_tenant_id = target_model.tenant_id
"""

_RESOLVE_SYSTEM_SQL: LiteralString = """
SELECT system_id
  FROM core.system
 WHERE lower(btrim(system_code)) = lower(btrim(%s))
   AND is_active
"""

_RESOLVE_TENANT_SQL: LiteralString = """
SELECT tenant_id
  FROM core.tenant
 WHERE lower(btrim(tenant_code)) = lower(btrim(%s))
   AND is_active
"""

_UPSERT_PROFILE_SQL: LiteralString = """
INSERT INTO workflow.attribute_profile (
    model_id,
    attribute_id,
    object_id,
    agent_run_id,
    workflow_run_id,
    source_context_digest,
    row_count,
    non_null_count,
    null_count,
    blank_count,
    distinct_count,
    min_data_length,
    max_data_length,
    avg_data_length,
    percent_populated,
    percent_duplicates,
    percent_null,
    percent_blank,
    percent_distinct
)
VALUES (
    %s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT (model_id, attribute_id) DO UPDATE
   SET object_id = EXCLUDED.object_id,
       agent_run_id = NULL,
       workflow_run_id = NULL,
       source_context_digest = EXCLUDED.source_context_digest,
       row_count = EXCLUDED.row_count,
       non_null_count = EXCLUDED.non_null_count,
       null_count = EXCLUDED.null_count,
       blank_count = EXCLUDED.blank_count,
       distinct_count = EXCLUDED.distinct_count,
       min_data_length = EXCLUDED.min_data_length,
       max_data_length = EXCLUDED.max_data_length,
       avg_data_length = EXCLUDED.avg_data_length,
       percent_populated = EXCLUDED.percent_populated,
       percent_duplicates = EXCLUDED.percent_duplicates,
       percent_null = EXCLUDED.percent_null,
       percent_blank = EXCLUDED.percent_blank,
       percent_distinct = EXCLUDED.percent_distinct,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING attribute_id
"""

_UPSERT_ANALYSIS_SQL: LiteralString = """
INSERT INTO workflow.analysis_result AS current_result (
    model_id,
    agent_run_id,
    inference_workflow_run_id,
    validation_workflow_run_id,
    validation_source_context_digest,
    from_object_id,
    from_attribute_id,
    to_object_id,
    to_attribute_id,
    relationship_kind,
    relationship_confidence,
    relationship_basis,
    validation_policy_version,
    validation_policy_digest,
    validation_result,
    validation_source_non_null_count,
    validation_source_distinct_count,
    validation_target_non_null_count,
    validation_target_distinct_count,
    validation_source_missing_target_count,
    validation_unused_target_count,
    validation_duplicate_target_key_count,
    analysis_result_status,
    analysis_result_is_locked
)
VALUES (
    %s, NULL, %s, NULL, NULL, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT ON CONSTRAINT uq_analysis_result_identity DO UPDATE
   SET agent_run_id = NULL,
       inference_workflow_run_id = EXCLUDED.inference_workflow_run_id,
       validation_workflow_run_id = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL THEN NULL
           ELSE current_result.validation_workflow_run_id
       END,
       validation_source_context_digest = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN NULL
           ELSE current_result.validation_source_context_digest
       END,
       from_object_id = EXCLUDED.from_object_id,
       to_object_id = EXCLUDED.to_object_id,
       relationship_confidence = EXCLUDED.relationship_confidence,
       relationship_basis = EXCLUDED.relationship_basis,
       validation_policy_version = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_policy_version
           ELSE current_result.validation_policy_version
       END,
       validation_policy_digest = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_policy_digest
           ELSE current_result.validation_policy_digest
       END,
       validation_result = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_result
           ELSE current_result.validation_result
       END,
       validation_source_non_null_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_source_non_null_count
           ELSE current_result.validation_source_non_null_count
       END,
       validation_source_distinct_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_source_distinct_count
           ELSE current_result.validation_source_distinct_count
       END,
       validation_target_non_null_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_target_non_null_count
           ELSE current_result.validation_target_non_null_count
       END,
       validation_target_distinct_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_target_distinct_count
           ELSE current_result.validation_target_distinct_count
       END,
       validation_source_missing_target_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_source_missing_target_count
           ELSE current_result.validation_source_missing_target_count
       END,
       validation_unused_target_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_unused_target_count
           ELSE current_result.validation_unused_target_count
       END,
       validation_duplicate_target_key_count = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.validation_duplicate_target_key_count
           ELSE current_result.validation_duplicate_target_key_count
       END,
       analysis_result_status = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.analysis_result_status
           ELSE current_result.analysis_result_status
       END,
       analysis_result_is_locked = CASE
           WHEN EXCLUDED.inference_workflow_run_id IS NULL
           THEN EXCLUDED.analysis_result_is_locked
           ELSE current_result.analysis_result_is_locked
       END,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING analysis_result_id
"""

_FIND_ASSERTION_DOCUMENT_SQL: LiteralString = """
SELECT modeling_assertion_document_id
  FROM model.modeling_assertion_document
 WHERE model_id = %s
   AND lower(btrim(modeling_assertion_document_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_ASSERTION_DOCUMENT_SQL: LiteralString = """
INSERT INTO model.modeling_assertion_document (
    model_id,
    tenant_id,
    system_id,
    modeling_assertion_document_name,
    modeling_assertion_file_pattern,
    modeling_assertion_document_type,
    modeling_assertion_document_description,
    modeling_assertion_document_metadata,
    is_active
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING modeling_assertion_document_id
"""

_UPDATE_ASSERTION_DOCUMENT_SQL: LiteralString = """
UPDATE model.modeling_assertion_document
   SET tenant_id = %s,
       system_id = %s,
       modeling_assertion_document_name = %s,
       modeling_assertion_file_pattern = %s,
       modeling_assertion_document_type = %s,
       modeling_assertion_document_description = %s,
       modeling_assertion_document_metadata = %s,
       is_active = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE modeling_assertion_document_id = %s
RETURNING modeling_assertion_document_id
"""

_UPSERT_ASSERTION_RECORD_SQL: LiteralString = """
INSERT INTO model.modeling_assertion_record (
    model_id,
    modeling_assertion_document_id,
    modeling_assertion_record_key,
    modeling_assertion_record_type,
    modeling_assertion_text,
    modeling_assertion_details,
    modeling_assertion_source_location,
    modeling_assertion_applicable_layers,
    modeling_assertion_confidence,
    modeling_assertion_record_status,
    modeling_assertion_record_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (model_id, lower(btrim(modeling_assertion_record_key))) DO UPDATE
   SET modeling_assertion_document_id = EXCLUDED.modeling_assertion_document_id,
       modeling_assertion_record_type = EXCLUDED.modeling_assertion_record_type,
       modeling_assertion_text = EXCLUDED.modeling_assertion_text,
       modeling_assertion_details = EXCLUDED.modeling_assertion_details,
       modeling_assertion_source_location = EXCLUDED.modeling_assertion_source_location,
       modeling_assertion_applicable_layers = EXCLUDED.modeling_assertion_applicable_layers,
       modeling_assertion_confidence = EXCLUDED.modeling_assertion_confidence,
       modeling_assertion_record_status = EXCLUDED.modeling_assertion_record_status,
       modeling_assertion_record_is_locked = EXCLUDED.modeling_assertion_record_is_locked,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING modeling_assertion_record_id
"""

_FIND_CONCEPTUAL_OBJECT_SQL: LiteralString = """
SELECT conceptual_object_id
  FROM workflow.conceptual_object
 WHERE model_id = %s
   AND lower(btrim(conceptual_object_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_CONCEPTUAL_OBJECT_SQL: LiteralString = """
INSERT INTO workflow.conceptual_object (
    model_id,
    workflow_run_id,
    conceptual_object_name,
    conceptual_object_definition,
    conceptual_object_type,
    conceptual_object_grain,
    conceptual_object_aliases,
    conceptual_object_confidence,
    conceptual_object_status,
    conceptual_object_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING conceptual_object_id
"""

_UPDATE_CONCEPTUAL_OBJECT_SQL: LiteralString = """
UPDATE workflow.conceptual_object
   SET workflow_run_id = %s,
       conceptual_object_name = %s,
       conceptual_object_definition = %s,
       conceptual_object_type = %s,
       conceptual_object_grain = %s,
       conceptual_object_aliases = %s,
       conceptual_object_confidence = %s,
       conceptual_object_status = %s,
       conceptual_object_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE conceptual_object_id = %s
RETURNING conceptual_object_id
"""

_FIND_CONCEPTUAL_RELATIONSHIP_SQL: LiteralString = """
SELECT conceptual_relationship_id
  FROM workflow.conceptual_relationship
 WHERE model_id = %s
   AND from_conceptual_object_id = %s
   AND to_conceptual_object_id = %s
   AND lower(btrim(conceptual_relationship_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_CONCEPTUAL_RELATIONSHIP_SQL: LiteralString = """
INSERT INTO workflow.conceptual_relationship (
    model_id,
    workflow_run_id,
    from_conceptual_object_id,
    to_conceptual_object_id,
    conceptual_relationship_name,
    conceptual_relationship_type,
    conceptual_relationship_definition,
    conceptual_relationship_cardinality,
    conceptual_relationship_basis,
    conceptual_relationship_cardinality_basis,
    conceptual_relationship_confidence,
    conceptual_relationship_status,
    conceptual_relationship_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING conceptual_relationship_id
"""

_UPDATE_CONCEPTUAL_RELATIONSHIP_SQL: LiteralString = """
UPDATE workflow.conceptual_relationship
   SET workflow_run_id = %s,
       conceptual_relationship_name = %s,
       conceptual_relationship_type = %s,
       conceptual_relationship_definition = %s,
       conceptual_relationship_cardinality = %s,
       conceptual_relationship_basis = %s,
       conceptual_relationship_cardinality_basis = %s,
       conceptual_relationship_confidence = %s,
       conceptual_relationship_status = %s,
       conceptual_relationship_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE conceptual_relationship_id = %s
RETURNING conceptual_relationship_id
"""

_FIND_CONCEPTUAL_SUPPORT_SQL: LiteralString = """
SELECT conceptual_support_id
  FROM workflow.conceptual_support
 WHERE model_id = %s
   AND supported_artifact_type = %s
   AND (
       (%s = 'conceptual_object' AND conceptual_object_id = %s)
       OR (%s = 'conceptual_relationship' AND conceptual_relationship_id = %s)
   )
   AND support_source_type = %s
   AND (
       (%s = 'object' AND source_object_id = %s)
       OR (%s = 'assertion' AND modeling_assertion_record_id = %s)
   )
 FOR UPDATE
"""

_INSERT_CONCEPTUAL_SUPPORT_SQL: LiteralString = """
INSERT INTO workflow.conceptual_support (
    model_id,
    workflow_run_id,
    supported_artifact_type,
    conceptual_object_id,
    conceptual_relationship_id,
    support_source_type,
    source_object_id,
    modeling_assertion_record_id,
    conceptual_support_role,
    conceptual_support_reason,
    conceptual_support_reason_detail,
    conceptual_support_confidence,
    conceptual_support_status,
    conceptual_support_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING conceptual_support_id
"""

_UPDATE_CONCEPTUAL_SUPPORT_SQL: LiteralString = """
UPDATE workflow.conceptual_support
   SET workflow_run_id = %s,
       conceptual_support_role = %s,
       conceptual_support_reason = %s,
       conceptual_support_reason_detail = %s,
       conceptual_support_confidence = %s,
       conceptual_support_status = %s,
       conceptual_support_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE conceptual_support_id = %s
RETURNING conceptual_support_id
"""

_UPSERT_MODEL_OBJECT_BINDING_SQL: LiteralString = """
INSERT INTO workflow.model_object_binding (
    model_id,
    object_id,
    modeled_entity_type,
    logical_entity_id,
    dimensional_entity_id,
    agent_run_id,
    workflow_run_id,
    model_object_binding_status,
    model_object_binding_is_locked
)
VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_model_object_binding_model_object DO UPDATE
   SET modeled_entity_type = EXCLUDED.modeled_entity_type,
       logical_entity_id = EXCLUDED.logical_entity_id,
       dimensional_entity_id = EXCLUDED.dimensional_entity_id,
       agent_run_id = NULL,
       workflow_run_id = EXCLUDED.workflow_run_id,
       model_object_binding_status = EXCLUDED.model_object_binding_status,
       model_object_binding_is_locked = EXCLUDED.model_object_binding_is_locked,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING model_object_binding_id,
          object_id
"""

_FIND_MODEL_OBJECT_BINDING_SQL: LiteralString = """
SELECT binding.model_object_binding_id,
       binding.object_id
  FROM workflow.model_object_binding AS binding
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = binding.logical_entity_id
   AND logical_entity.model_id = binding.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = binding.dimensional_entity_id
   AND dimensional_entity.model_id = binding.model_id
 WHERE binding.model_id = %s
   AND binding.modeled_entity_type = %s
   AND lower(btrim(
       CASE binding.modeled_entity_type
           WHEN 'logical_entity' THEN logical_entity.logical_entity_name
           ELSE dimensional_entity.dimensional_entity_name
       END
   )) = lower(btrim(%s))
 ORDER BY binding.model_object_binding_id
 LIMIT 1
 FOR UPDATE OF binding
"""

_RESOLVE_BOUND_ATTRIBUTE_SQL: LiteralString = """
SELECT attribute.attribute_id
  FROM workflow.model_object_binding AS binding
  JOIN core.attribute AS attribute
    ON attribute.object_id = binding.object_id
   AND lower(btrim(attribute.attribute_name)) = lower(btrim(%s))
   AND attribute.is_active
 WHERE binding.model_object_binding_id = %s
   AND binding.model_id = %s
"""

_UPSERT_MODEL_ATTRIBUTE_BINDING_SQL: LiteralString = """
INSERT INTO workflow.model_attribute_binding (
    model_object_binding_id,
    logical_attribute_id,
    dimensional_attribute_id,
    attribute_id,
    agent_run_id,
    workflow_run_id,
    model_attribute_binding_status,
    model_attribute_binding_is_locked
)
VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_model_attribute_binding_target DO UPDATE
   SET logical_attribute_id = EXCLUDED.logical_attribute_id,
       dimensional_attribute_id = EXCLUDED.dimensional_attribute_id,
       agent_run_id = NULL,
       workflow_run_id = EXCLUDED.workflow_run_id,
       model_attribute_binding_status = EXCLUDED.model_attribute_binding_status,
       model_attribute_binding_is_locked = EXCLUDED.model_attribute_binding_is_locked,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING model_attribute_binding_id
"""

_FIND_MODEL_ATTRIBUTE_BINDING_SQL: LiteralString = """
SELECT attribute_binding.model_attribute_binding_id
  FROM workflow.model_attribute_binding AS attribute_binding
  JOIN workflow.model_object_binding AS object_binding
    ON object_binding.model_object_binding_id =
       attribute_binding.model_object_binding_id
  LEFT JOIN workflow.logical_attribute AS logical_attribute
    ON logical_attribute.logical_attribute_id =
       attribute_binding.logical_attribute_id
  LEFT JOIN workflow.dimensional_attribute AS dimensional_attribute
    ON dimensional_attribute.dimensional_attribute_id =
       attribute_binding.dimensional_attribute_id
 WHERE object_binding.model_id = %s
   AND object_binding.modeled_entity_type = %s
   AND object_binding.model_object_binding_id = %s
   AND lower(btrim(
       CASE object_binding.modeled_entity_type
           WHEN 'logical_entity' THEN logical_attribute.logical_attribute_name
           ELSE dimensional_attribute.dimensional_attribute_name
       END
   )) = lower(btrim(%s))
 ORDER BY attribute_binding.model_attribute_binding_id
 LIMIT 1
 FOR UPDATE OF attribute_binding
"""

_RESOLVE_OUTPUT_TEMPLATE_SQL: LiteralString = """
SELECT output_template_id
  FROM application.output_template
 WHERE lower(btrim(output_template_code)) = lower(btrim(%s))
   AND output_template_target_type = %s
   AND is_active
"""

_UPSERT_MAPPING_DEPENDENCY_SQL: LiteralString = """
INSERT INTO workflow.mapping_source_system_dependency (
    model_id,
    modeled_entity_type,
    source_system_id,
    source_system_dependency_order,
    agent_run_id,
    workflow_run_id,
    mapping_source_system_dependency_status,
    mapping_source_system_dependency_is_locked
)
VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_mapping_source_dependency_binding DO UPDATE
   SET source_system_dependency_order = EXCLUDED.source_system_dependency_order,
       agent_run_id = NULL,
       workflow_run_id = EXCLUDED.workflow_run_id,
       mapping_source_system_dependency_status =
           EXCLUDED.mapping_source_system_dependency_status,
       mapping_source_system_dependency_is_locked =
           EXCLUDED.mapping_source_system_dependency_is_locked,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING mapping_source_system_dependency_id
"""

_FIND_MAPPING_OBJECT_SQL: LiteralString = """
SELECT mapping_object_id
  FROM workflow.mapping_object
 WHERE model_id = %s
   AND model_object_binding_id = %s
   AND source_system_id = %s
 FOR UPDATE
"""

_INSERT_MAPPING_OBJECT_SQL: LiteralString = """
INSERT INTO workflow.mapping_object (
    model_id,
    model_object_binding_id,
    source_system_id,
    output_template_id,
    object_dependency_order,
    mapping_transformation_document,
    agent_run_id,
    workflow_run_id,
    object_mapping_status,
    object_mapping_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
RETURNING mapping_object_id
"""

_UPDATE_MAPPING_OBJECT_SQL: LiteralString = """
UPDATE workflow.mapping_object
   SET output_template_id = %s,
       object_dependency_order = %s,
       mapping_transformation_document = %s,
       agent_run_id = NULL,
       workflow_run_id = %s,
       object_mapping_status = %s,
       object_mapping_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE mapping_object_id = %s
RETURNING mapping_object_id
"""

_FIND_MAPPING_ATTRIBUTE_SQL: LiteralString = """
SELECT mapping_attribute_id
  FROM workflow.mapping_attribute
 WHERE mapping_object_id = %s
   AND model_attribute_binding_id = %s
 FOR UPDATE
"""

_INSERT_MAPPING_ATTRIBUTE_SQL: LiteralString = """
INSERT INTO workflow.mapping_attribute (
    mapping_object_id,
    model_attribute_binding_id,
    output_template_id,
    attribute_mapping_transformation_document,
    agent_run_id,
    workflow_run_id,
    attribute_mapping_status,
    attribute_mapping_is_locked
)
VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
RETURNING mapping_attribute_id
"""

_UPDATE_MAPPING_ATTRIBUTE_SQL: LiteralString = """
UPDATE workflow.mapping_attribute
   SET output_template_id = %s,
       attribute_mapping_transformation_document = %s,
       agent_run_id = NULL,
       workflow_run_id = %s,
       attribute_mapping_status = %s,
       attribute_mapping_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE mapping_attribute_id = %s
RETURNING mapping_attribute_id
"""

_RESOLVE_CODE_INPUT_SQL: LiteralString = """
SELECT btrim(context.code_input_digest::TEXT) AS code_input_digest
  FROM workflow.list_code_generation_target_context(%s, %s, %s) AS context
 WHERE context.object_id = %s
   AND lower(btrim(context.modeled_entity_name)) = lower(btrim(%s))
"""

_FIND_GENERATED_CODE_SQL: LiteralString = """
SELECT generated_code_id
  FROM workflow.generated_code
 WHERE model_object_binding_id = %s
   AND lower(btrim(artifact_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_GENERATED_CODE_SQL: LiteralString = """
INSERT INTO workflow.generated_code (
    model_object_binding_id,
    artifact_name,
    artifact_type,
    generated_code_content,
    code_input_digest,
    agent_run_id,
    workflow_run_id,
    generated_code_status
)
VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
RETURNING generated_code_id
"""

_UPDATE_GENERATED_CODE_SQL: LiteralString = """
UPDATE workflow.generated_code
   SET artifact_name = %s,
       artifact_type = %s,
       generated_code_content = %s,
       code_input_digest = %s,
       agent_run_id = NULL,
       workflow_run_id = %s,
       generated_code_status = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE generated_code_id = %s
RETURNING generated_code_id
"""

_FIND_GENERATED_CODE_SOURCE_SYSTEM_SQL: LiteralString = """
SELECT generated_code_source_system_id
  FROM workflow.generated_code_source_system
 WHERE generated_code_id = %s
   AND source_system_id = %s
 FOR UPDATE
"""

_INSERT_GENERATED_CODE_SOURCE_SYSTEM_SQL: LiteralString = """
INSERT INTO workflow.generated_code_source_system (
    generated_code_id,
    source_system_id,
    agent_run_id,
    workflow_run_id,
    generated_code_source_system_status
)
VALUES (%s, %s, NULL, %s, %s)
RETURNING generated_code_source_system_id
"""

_UPDATE_GENERATED_CODE_SOURCE_SYSTEM_SQL: LiteralString = """
UPDATE workflow.generated_code_source_system
   SET agent_run_id = NULL,
       workflow_run_id = %s,
       generated_code_source_system_status = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE generated_code_source_system_id = %s
RETURNING generated_code_source_system_id
"""

_VALIDATION_TARGET_CONTEXT_SQL: LiteralString = """
SELECT context.modeled_entity_type,
       context.modeled_entity_name,
       btrim(context.code_input_digest::TEXT) AS code_input_digest,
       context.source_context
  FROM workflow.list_code_generation_target_context(
       %s,
       'logical_entity',
       NULL
  ) AS context
UNION ALL
SELECT context.modeled_entity_type,
       context.modeled_entity_name,
       btrim(context.code_input_digest::TEXT) AS code_input_digest,
       context.source_context
  FROM workflow.list_code_generation_target_context(
       %s,
       'dimensional_entity',
       NULL
  ) AS context
"""

_VALIDATION_GENERATED_CODE_SQL: LiteralString = """
SELECT binding.modeled_entity_type,
       CASE binding.modeled_entity_type
           WHEN 'logical_entity' THEN logical_entity.logical_entity_name
           ELSE dimensional_entity.dimensional_entity_name
       END AS modeled_entity_name,
       generated.artifact_name,
       generated.artifact_type,
       generated.generated_code_digest,
       generated.generated_code_status,
       coalesce(
           array_agg(system.system_code ORDER BY lower(system.system_code))
               FILTER (
                   WHERE assignment.generated_code_source_system_status = 'active'
                     AND system.is_active
               ),
           ARRAY[]::VARCHAR[]
       ) AS source_system_codes
  FROM workflow.generated_code AS generated
  JOIN workflow.model_object_binding AS binding
    ON binding.model_object_binding_id = generated.model_object_binding_id
   AND binding.model_id = %s
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = binding.logical_entity_id
   AND logical_entity.model_id = binding.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = binding.dimensional_entity_id
   AND dimensional_entity.model_id = binding.model_id
  LEFT JOIN workflow.generated_code_source_system AS assignment
    ON assignment.generated_code_id = generated.generated_code_id
  LEFT JOIN core.system AS system
    ON system.system_id = assignment.source_system_id
 GROUP BY binding.modeled_entity_type,
          logical_entity.logical_entity_name,
          dimensional_entity.dimensional_entity_name,
          generated.generated_code_id
"""

_FIND_VALIDATION_GROUP_SQL: LiteralString = """
SELECT validation_group_id
  FROM workflow.validation_group
 WHERE model_id = %s
   AND tenant_id = %s
   AND system_id = %s
   AND lower(btrim(validation_group_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_VALIDATION_GROUP_SQL: LiteralString = """
INSERT INTO workflow.validation_group (
    model_id,
    tenant_id,
    system_id,
    agent_run_id,
    workflow_run_id,
    validation_group_name,
    validation_group_description,
    mapping_context_digest,
    code_context_digest,
    is_active
)
VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s)
RETURNING validation_group_id
"""

_UPDATE_VALIDATION_GROUP_SQL: LiteralString = """
UPDATE workflow.validation_group
   SET agent_run_id = NULL,
       workflow_run_id = %s,
       validation_group_name = %s,
       validation_group_description = %s,
       mapping_context_digest = %s,
       code_context_digest = %s,
       is_active = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE validation_group_id = %s
RETURNING validation_group_id
"""

_FIND_VALIDATION_CHECK_SQL: LiteralString = """
SELECT validation_check_id
  FROM workflow.validation_check
 WHERE validation_group_id = %s
   AND lower(btrim(validation_check_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_VALIDATION_CHECK_SQL: LiteralString = """
INSERT INTO workflow.validation_check (
    validation_group_id,
    validation_check_name,
    validation_check_description,
    validation_category_code,
    validation_severity,
    validation_query_sql,
    validation_comparison_query_sql,
    validation_result_data_type,
    validation_comparison_operator,
    validation_comparison_value_type,
    validation_comparison_value,
    is_active
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING validation_check_id
"""

_UPDATE_VALIDATION_CHECK_SQL: LiteralString = """
UPDATE workflow.validation_check
   SET validation_check_name = %s,
       validation_check_description = %s,
       validation_category_code = %s,
       validation_severity = %s,
       validation_query_sql = %s,
       validation_comparison_query_sql = %s,
       validation_result_data_type = %s,
       validation_comparison_operator = %s,
       validation_comparison_value_type = %s,
       validation_comparison_value = %s,
       is_active = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE validation_check_id = %s
RETURNING validation_check_id
"""


@dataclass(frozen=True, slots=True)
class _MappingMaterializationPolicy:
    workflow_run_id: int
    object_output_template_id: int | None
    attribute_output_template_id: int | None


@dataclass(slots=True)
class ModelMaterializer:
    transaction: WriteTransaction
    model_id: int
    source_context_digest: str
    workflow_run_id: int | None = None
    _model_workflow: str | None = None
    _mapping_policy: _MappingMaterializationPolicy | None = None
    _object_ids: dict[tuple[str, ...], tuple[int, int]] = field(
        default_factory=dict[tuple[str, ...], tuple[int, int]]
    )
    _attribute_ids: dict[tuple[str, ...], tuple[int, int, int]] = field(
        default_factory=dict[tuple[str, ...], tuple[int, int, int]]
    )
    _system_ids: dict[str, int] = field(default_factory=dict[str, int])
    _tenant_ids: dict[str, int] = field(default_factory=dict[str, int])
    _assertion_document_ids: dict[str, int] = field(default_factory=dict[str, int])
    _assertion_record_ids: dict[str, int] = field(default_factory=dict[str, int])
    _conceptual_object_ids: dict[str, int] = field(default_factory=dict[str, int])
    _logical_submodel_ids: dict[str, int] = field(default_factory=dict[str, int])
    _logical_entity_ids: dict[str, int] = field(default_factory=dict[str, int])
    _logical_attribute_ids: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
    )
    _dimensional_submodel_ids: dict[str, int] = field(default_factory=dict[str, int])
    _dimensional_entity_ids: dict[str, int] = field(default_factory=dict[str, int])
    _dimensional_attribute_ids: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
    )
    _model_object_bindings: dict[tuple[str, str], tuple[int, int]] = field(
        default_factory=dict[tuple[str, str], tuple[int, int]]
    )
    _model_attribute_bindings: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
    )
    _mapping_object_ids: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
    )
    _generated_code_ids: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
    )
    _output_template_ids: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
    )
    _validation_context_digests: dict[str, tuple[str, str | None]] = field(
        default_factory=dict[str, tuple[str, str | None]]
    )
    _validation_target_context_rows: tuple[dict[str, Any], ...] | None = None
    _validation_generated_code_rows: tuple[dict[str, Any], ...] | None = None
    _validation_group_ids: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
    )

    @classmethod
    def for_workflow_apply(
        cls,
        *,
        transaction: WriteTransaction,
        model_id: int,
        source_context_digest: str,
        workflow_run_id: int,
        model_workflow: str,
        mapping_object_output_template_id: int | None,
        mapping_attribute_output_template_id: int | None,
    ) -> ModelMaterializer:
        if workflow_run_id <= 0 or any(
            template_id is not None and template_id <= 0
            for template_id in (
                mapping_object_output_template_id,
                mapping_attribute_output_template_id,
            )
        ):
            raise InvalidRequestError("Workflow Mapping materialization policy is invalid.")
        policy = None
        if model_workflow == "mapping":
            policy = _MappingMaterializationPolicy(
                workflow_run_id=workflow_run_id,
                object_output_template_id=mapping_object_output_template_id,
                attribute_output_template_id=mapping_attribute_output_template_id,
            )
        elif (
            mapping_object_output_template_id is not None
            or mapping_attribute_output_template_id is not None
        ):
            raise InvalidRequestError(
                "Mapping materialization policy is unavailable outside Mapping."
            )
        return cls(
            transaction=transaction,
            model_id=model_id,
            source_context_digest=source_context_digest,
            workflow_run_id=workflow_run_id,
            _model_workflow=model_workflow,
            _mapping_policy=policy,
        )

    async def apply(
        self,
        records: dict[str, tuple[ModelingRecord, ...]],
    ) -> int:
        """Materialize in dependency order inside the caller's transaction."""
        action_count = 0
        action_count += await self._apply_model_details(records.get("model_details", ()))
        action_count += await self._apply_model_input_scope(records.get("model_input_scope", ()))
        action_count += await self._apply_assertion_documents(
            records.get("modeling_assertion_document", ())
        )
        action_count += await self._apply_assertion_records(
            records.get("modeling_assertion_record", ())
        )
        action_count += await self._apply_profiles(records.get("profiling_profile", ()))
        action_count += await self._apply_analysis(records.get("analysis_result", ()))
        action_count += await self._apply_conceptual_objects(records.get("conceptual_object", ()))
        action_count += await self._apply_conceptual_relationships(
            records.get("conceptual_relationship", ())
        )
        action_count += await self._apply_logical(records)
        action_count += await self._apply_dimensional(records)
        action_count += await self._apply_model_object_bindings(
            records.get("model_object_binding", ())
        )
        action_count += await self._apply_model_attribute_bindings(
            records.get("model_attribute_binding", ())
        )
        action_count += await self._apply_mapping(records)
        action_count += await self._apply_generated_code(records.get("generated_code", ()))
        action_count += await self._apply_generated_code_source_systems(
            records.get("generated_code_source_system", ())
        )
        action_count += await self._apply_validation_groups(records.get("validation_group", ()))
        action_count += await self._apply_validation_checks(records.get("validation_check", ()))
        return action_count

    async def _apply_model_details(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ModelDetailsRecord)
            row = await self.transaction.fetch_one(
                _UPDATE_MODEL_DETAILS_SQL,
                (
                    record.model_name,
                    record.model_description,
                    record.silver_model_naming_instructions,
                    (
                        None
                        if record.silver_model_audit_columns_template is None
                        else Jsonb(record.silver_model_audit_columns_template)
                    ),
                    record.gold_model_naming_instructions,
                    (
                        None
                        if record.gold_model_technical_columns_template is None
                        else Jsonb(record.gold_model_technical_columns_template)
                    ),
                    (
                        None
                        if record.gold_model_audit_columns_template is None
                        else Jsonb(record.gold_model_audit_columns_template)
                    ),
                    self.model_id,
                ),
            )
            if row is None:
                raise InvalidRequestError("Model details could not be updated.")
        return len(records)

    async def _apply_model_input_scope(
        self,
        records: tuple[ModelingRecord, ...],
    ) -> int:
        for raw in records:
            record = _as(raw, ModelInputScopeRecord)
            object_id, _ = await self.resolve_object(record)
            row = await self.transaction.fetch_one(
                _UPSERT_MODEL_INPUT_SCOPE_SQL,
                (
                    self.model_id,
                    object_id,
                    record.model_input_scope_is_locked,
                    record.is_active,
                ),
            )
            if row is None:
                raise InvalidRequestError("Model Input Scope could not be materialized.")
        return len(records)

    async def _apply_profiles(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ProfilingProfileRecord)
            object_id, attribute_id, _ = await self.resolve_attribute(record)
            await self.transaction.fetch_one(
                _UPSERT_PROFILE_SQL,
                (
                    self.model_id,
                    attribute_id,
                    object_id,
                    self.source_context_digest,
                    record.row_count,
                    record.non_null_count,
                    record.null_count,
                    record.blank_count,
                    record.distinct_count,
                    record.min_data_length,
                    record.max_data_length,
                    record.avg_data_length,
                    record.percent_populated,
                    record.percent_duplicates,
                    record.percent_null,
                    record.percent_blank,
                    record.percent_distinct,
                ),
            )
        return len(records)

    async def _apply_analysis(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, AnalysisResultRecord)
            from_key = PhysicalAttributeKey(
                tenant_code=record.from_tenant_code,
                system_code=record.from_system_code,
                connection_code=record.from_connection_code,
                object_schema=record.from_object_schema,
                object_name=record.from_object_name,
                attribute_name=record.from_attribute_name,
            )
            to_key = PhysicalAttributeKey(
                tenant_code=record.to_tenant_code,
                system_code=record.to_system_code,
                connection_code=record.to_connection_code,
                object_schema=record.to_object_schema,
                object_name=record.to_object_name,
                attribute_name=record.to_attribute_name,
            )
            from_object_id, from_attribute_id, _ = await self.resolve_attribute(from_key)
            to_object_id, to_attribute_id, _ = await self.resolve_attribute(to_key)
            policy_digest = (
                None
                if record.validation_policy_version is None
                else _digest(
                    {
                        "version": record.validation_policy_version,
                        "result": record.validation_result,
                        "kind": record.relationship_kind,
                    }
                )
            )
            await self.transaction.fetch_one(
                _UPSERT_ANALYSIS_SQL,
                (
                    self.model_id,
                    self.workflow_run_id,
                    from_object_id,
                    from_attribute_id,
                    to_object_id,
                    to_attribute_id,
                    record.relationship_kind,
                    record.relationship_confidence,
                    record.relationship_basis,
                    record.validation_policy_version,
                    policy_digest,
                    record.validation_result,
                    record.validation_source_non_null_count,
                    record.validation_source_distinct_count,
                    record.validation_target_non_null_count,
                    record.validation_target_distinct_count,
                    record.validation_source_missing_target_count,
                    record.validation_unused_target_count,
                    record.validation_duplicate_target_key_count,
                    record.analysis_result_status,
                    record.analysis_result_is_locked,
                ),
            )
        return len(records)

    async def _apply_assertion_documents(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ModelingAssertionDocumentRecord)
            tenant_id = (
                None
                if record.tenant_code is None
                else await self.resolve_tenant(record.tenant_code)
            )
            system_id = (
                None
                if record.system_code is None
                else await self.resolve_system(record.system_code)
            )
            existing = await self.transaction.fetch_one(
                _FIND_ASSERTION_DOCUMENT_SQL,
                (self.model_id, record.modeling_assertion_document_name),
            )
            values = (
                tenant_id,
                system_id,
                record.modeling_assertion_document_name,
                record.modeling_assertion_file_pattern,
                record.modeling_assertion_document_type,
                record.modeling_assertion_document_description,
                Jsonb(record.modeling_assertion_document_metadata),
                record.is_active,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_ASSERTION_DOCUMENT_SQL,
                    (self.model_id, *values),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_ASSERTION_DOCUMENT_SQL,
                    (*values, existing["modeling_assertion_document_id"]),
                )
            assert row is not None
            self._assertion_document_ids[
                normalize_model_key_value(record.modeling_assertion_document_name)
            ] = row["modeling_assertion_document_id"]
        return len(records)

    async def _apply_assertion_records(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ModelingAssertionRecordRecord)
            document_id = await self.resolve_assertion_document(
                record.modeling_assertion_document_name
            )
            row = await self.transaction.fetch_one(
                _UPSERT_ASSERTION_RECORD_SQL,
                (
                    self.model_id,
                    document_id,
                    record.modeling_assertion_record_key,
                    record.modeling_assertion_record_type,
                    record.modeling_assertion_text,
                    Jsonb(record.modeling_assertion_details),
                    (
                        None
                        if record.modeling_assertion_source_location is None
                        else Jsonb(record.modeling_assertion_source_location)
                    ),
                    list(record.modeling_assertion_applicable_layers),
                    record.modeling_assertion_confidence,
                    record.modeling_assertion_record_status,
                    record.modeling_assertion_record_is_locked,
                ),
            )
            assert row is not None
            self._assertion_record_ids[
                normalize_model_key_value(record.modeling_assertion_record_key)
            ] = row["modeling_assertion_record_id"]
        return len(records)

    async def resolve_object(self, key: PhysicalObjectKey) -> tuple[int, int]:
        natural_key = (
            normalize_model_key_value(key.tenant_code),
            normalize_model_key_value(key.system_code),
            normalize_model_key_value(key.connection_code),
            normalize_model_key_value(key.object_schema),
            normalize_model_key_value(key.object_name),
        )
        cached = self._object_ids.get(natural_key)
        if cached is not None:
            return cached
        parameters = (natural_key[0], self.model_id, *natural_key[1:])
        row = await self.transaction.fetch_one(_RESOLVE_OBJECT_SQL, parameters)
        if row is None:
            raise InvalidRequestError("A referenced physical Object was not found.")
        resolved = (row["object_id"], row["system_id"])
        self._object_ids[natural_key] = resolved
        return resolved

    async def resolve_attribute(self, key: PhysicalAttributeKey) -> tuple[int, int, int]:
        natural_key = (
            normalize_model_key_value(key.tenant_code),
            normalize_model_key_value(key.system_code),
            normalize_model_key_value(key.connection_code),
            normalize_model_key_value(key.object_schema),
            normalize_model_key_value(key.object_name),
            normalize_model_key_value(key.attribute_name),
        )
        cached = self._attribute_ids.get(natural_key)
        if cached is not None:
            return cached
        parameters = (natural_key[0], self.model_id, *natural_key[1:])
        row = await self.transaction.fetch_one(_RESOLVE_ATTRIBUTE_SQL, parameters)
        if row is None:
            raise InvalidRequestError("A referenced physical Attribute was not found.")
        resolved = (row["object_id"], row["attribute_id"], row["system_id"])
        self._attribute_ids[natural_key] = resolved
        return resolved

    async def resolve_system(self, code: str) -> int:
        normalized = normalize_model_key_value(code)
        cached = self._system_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(_RESOLVE_SYSTEM_SQL, (normalized,))
        if row is None:
            raise InvalidRequestError("A referenced System was not found.")
        self._system_ids[normalized] = row["system_id"]
        return row["system_id"]

    async def resolve_tenant(self, code: str) -> int:
        normalized = normalize_model_key_value(code)
        cached = self._tenant_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(_RESOLVE_TENANT_SQL, (normalized,))
        if row is None:
            raise InvalidRequestError("A referenced Tenant was not found.")
        self._tenant_ids[normalized] = row["tenant_id"]
        return row["tenant_id"]

    async def resolve_assertion_document(self, name: str) -> int:
        normalized = normalize_model_key_value(name)
        cached = self._assertion_document_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            _FIND_ASSERTION_DOCUMENT_SQL,
            (self.model_id, name),
        )
        if row is None:
            raise InvalidRequestError("A referenced Assertion Document was not found.")
        self._assertion_document_ids[normalized] = row["modeling_assertion_document_id"]
        return row["modeling_assertion_document_id"]

    async def resolve_assertion_record(self, key: str) -> int:
        normalized = normalize_model_key_value(key)
        cached = self._assertion_record_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            """
SELECT modeling_assertion_record_id
  FROM model.modeling_assertion_record
 WHERE model_id = %s
   AND lower(btrim(modeling_assertion_record_key)) = lower(btrim(%s))
""",
            (self.model_id, key),
        )
        if row is None:
            raise InvalidRequestError("A referenced Assertion Record was not found.")
        self._assertion_record_ids[normalized] = row["modeling_assertion_record_id"]
        return row["modeling_assertion_record_id"]

    async def _apply_conceptual_objects(self, records: tuple[ModelingRecord, ...]) -> int:
        action_count = 0
        for raw in records:
            record = _as(raw, ConceptualObjectRecord)
            existing = await self.transaction.fetch_one(
                _FIND_CONCEPTUAL_OBJECT_SQL,
                (self.model_id, record.conceptual_object_name),
            )
            values = (
                record.conceptual_object_name,
                record.conceptual_object_definition,
                record.conceptual_object_type,
                record.conceptual_object_grain,
                list(record.conceptual_object_aliases),
                record.conceptual_object_confidence,
                record.conceptual_object_status,
                record.conceptual_object_is_locked,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_CONCEPTUAL_OBJECT_SQL,
                    (self.model_id, self.workflow_run_id, *values),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_CONCEPTUAL_OBJECT_SQL,
                    (self.workflow_run_id, *values, existing["conceptual_object_id"]),
                )
            assert row is not None
            object_id = row["conceptual_object_id"]
            self._conceptual_object_ids[
                normalize_model_key_value(record.conceptual_object_name)
            ] = object_id
            for support in record.supports:
                await self._upsert_conceptual_support(
                    parent_type="conceptual_object",
                    parent_id=object_id,
                    support=support,
                )
                action_count += 1
            action_count += 1
        return action_count

    async def _apply_conceptual_relationships(self, records: tuple[ModelingRecord, ...]) -> int:
        action_count = 0
        for raw in records:
            record = _as(raw, ConceptualRelationshipRecord)
            from_id = await self.resolve_conceptual_object(record.from_conceptual_object_name)
            to_id = await self.resolve_conceptual_object(record.to_conceptual_object_name)
            existing = await self.transaction.fetch_one(
                _FIND_CONCEPTUAL_RELATIONSHIP_SQL,
                (
                    self.model_id,
                    from_id,
                    to_id,
                    record.conceptual_relationship_name,
                ),
            )
            values = (
                record.conceptual_relationship_name,
                record.conceptual_relationship_type,
                record.conceptual_relationship_definition,
                record.conceptual_relationship_cardinality,
                record.conceptual_relationship_basis,
                record.conceptual_relationship_cardinality_basis,
                record.conceptual_relationship_confidence,
                record.conceptual_relationship_status,
                record.conceptual_relationship_is_locked,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_CONCEPTUAL_RELATIONSHIP_SQL,
                    (self.model_id, self.workflow_run_id, from_id, to_id, *values),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_CONCEPTUAL_RELATIONSHIP_SQL,
                    (
                        self.workflow_run_id,
                        *values,
                        existing["conceptual_relationship_id"],
                    ),
                )
            assert row is not None
            relationship_id = row["conceptual_relationship_id"]
            for support in record.supports:
                await self._upsert_conceptual_support(
                    parent_type="conceptual_relationship",
                    parent_id=relationship_id,
                    support=support,
                )
                action_count += 1
            action_count += 1
        return action_count

    async def _upsert_conceptual_support(
        self,
        *,
        parent_type: str,
        parent_id: int,
        support: Any,
    ) -> None:
        if support.support_source_type == "object":
            source_object_id, _ = await self.resolve_object(support.source_object)
            assertion_record_id = None
        else:
            source_object_id = None
            assertion_record_id = await self.resolve_assertion_record(
                support.assertion_record.modeling_assertion_record_key
            )
        conceptual_object_id = parent_id if parent_type == "conceptual_object" else None
        conceptual_relationship_id = parent_id if parent_type == "conceptual_relationship" else None
        existing = await self.transaction.fetch_one(
            _FIND_CONCEPTUAL_SUPPORT_SQL,
            (
                self.model_id,
                parent_type,
                parent_type,
                parent_id,
                parent_type,
                parent_id,
                support.support_source_type,
                support.support_source_type,
                source_object_id,
                support.support_source_type,
                assertion_record_id,
            ),
        )
        values = (
            support.support_role,
            support.support_reason,
            support.support_reason_detail,
            support.support_confidence,
            support.support_status,
            support.support_is_locked,
        )
        if existing is None:
            await self.transaction.fetch_one(
                _INSERT_CONCEPTUAL_SUPPORT_SQL,
                (
                    self.model_id,
                    self.workflow_run_id,
                    parent_type,
                    conceptual_object_id,
                    conceptual_relationship_id,
                    support.support_source_type,
                    source_object_id,
                    assertion_record_id,
                    *values,
                ),
            )
        else:
            await self.transaction.fetch_one(
                _UPDATE_CONCEPTUAL_SUPPORT_SQL,
                (self.workflow_run_id, *values, existing["conceptual_support_id"]),
            )

    async def resolve_conceptual_object(self, name: str) -> int:
        normalized = normalize_model_key_value(name)
        cached = self._conceptual_object_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            _FIND_CONCEPTUAL_OBJECT_SQL,
            (self.model_id, name),
        )
        if row is None:
            raise InvalidRequestError("A referenced Conceptual Object was not found.")
        self._conceptual_object_ids[normalized] = row["conceptual_object_id"]
        return row["conceptual_object_id"]

    async def _apply_logical(self, records: dict[str, tuple[ModelingRecord, ...]]) -> int:
        return await self._apply_layer(
            config=LOGICAL,
            submodel_records=records.get("logical_submodel", ()),
            entity_records=records.get("logical_entity", ()),
            attribute_records=records.get("logical_attribute", ()),
            relationship_records=records.get("logical_relationship", ()),
            submodel_type=LogicalSubmodelRecord,
            entity_type=LogicalEntityRecord,
            attribute_type=LogicalAttributeRecord,
            relationship_type=LogicalRelationshipRecord,
        )

    async def _apply_dimensional(self, records: dict[str, tuple[ModelingRecord, ...]]) -> int:
        return await self._apply_layer(
            config=DIMENSIONAL,
            submodel_records=records.get("dimensional_submodel", ()),
            entity_records=records.get("dimensional_entity", ()),
            attribute_records=records.get("dimensional_attribute", ()),
            relationship_records=records.get("dimensional_relationship", ()),
            submodel_type=DimensionalSubmodelRecord,
            entity_type=DimensionalEntityRecord,
            attribute_type=DimensionalAttributeRecord,
            relationship_type=DimensionalRelationshipRecord,
        )

    async def _apply_layer(
        self,
        *,
        config: LayerConfig,
        submodel_records: tuple[ModelingRecord, ...],
        entity_records: tuple[ModelingRecord, ...],
        attribute_records: tuple[ModelingRecord, ...],
        relationship_records: tuple[ModelingRecord, ...],
        submodel_type: type[ModelingRecord],
        entity_type: type[ModelingRecord],
        attribute_type: type[ModelingRecord],
        relationship_type: type[ModelingRecord],
    ) -> int:
        action_count = 0
        for raw in submodel_records:
            record = _as_runtime(raw, submodel_type)
            await self._upsert_submodel(config, record)
            action_count += 1
        for raw in entity_records:
            record = _as_runtime(raw, entity_type)
            entity_id = await self._upsert_entity(config, record)
            action_count += 1
            for membership in record.submodels:
                await self._upsert_membership(config, entity_id, membership)
                action_count += 1
            for source in record.sources:
                await self._upsert_entity_source(config, entity_id, source)
                action_count += 1
        for raw in attribute_records:
            record = _as_runtime(raw, attribute_type)
            attribute_id, entity_id = await self._upsert_attribute(config, record)
            action_count += 1
            for source in record.sources:
                await self._upsert_attribute_source(
                    config,
                    entity_id=entity_id,
                    attribute_id=attribute_id,
                    source=source,
                )
                action_count += 1
        for raw in relationship_records:
            record = _as_runtime(raw, relationship_type)
            await self._upsert_layer_relationship(config, record)
            action_count += 1
        return action_count

    async def _upsert_submodel(self, config: LayerConfig, record: Any) -> int:
        name_field = f"{config.layer}_submodel_name"
        definition_field = f"{config.layer}_submodel_definition"
        status_field = f"{config.layer}_submodel_status"
        locked_field = f"{config.layer}_submodel_is_locked"
        name = getattr(record, name_field)
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.submodel_id}
  FROM {config.submodel_table}
 WHERE model_id = %s
   AND lower(btrim({name_field})) = lower(btrim(%s))
 FOR UPDATE
""",
            ),
            (self.model_id, name),
        )
        values = (
            name,
            getattr(record, definition_field),
            getattr(record, status_field),
            getattr(record, locked_field),
        )
        if existing is None:
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.submodel_table} (
    model_id, workflow_run_id, {name_field}, {definition_field}, {status_field}, {locked_field}
)
VALUES (%s, %s, %s, %s, %s, %s)
RETURNING {config.submodel_id}
""",
                ),
                (self.model_id, self.workflow_run_id, *values),
            )
        else:
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.submodel_table}
   SET workflow_run_id = %s,
       {name_field} = %s,
       {definition_field} = %s,
       {status_field} = %s,
       {locked_field} = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {config.submodel_id} = %s
RETURNING {config.submodel_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.submodel_id]),
            )
        assert row is not None
        self._submodel_cache(config)[normalize_model_key_value(name)] = row[config.submodel_id]
        return row[config.submodel_id]

    async def _upsert_entity(self, config: LayerConfig, record: Any) -> int:
        name_field = f"{config.layer}_entity_name"
        name = getattr(record, name_field)
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.entity_id}
  FROM {config.entity_table}
 WHERE model_id = %s
   AND lower(btrim({name_field})) = lower(btrim(%s))
 FOR UPDATE
""",
            ),
            (self.model_id, name),
        )
        fields = config.entity_fields
        values = tuple(getattr(record, field) for field in fields)
        if existing is None:
            placeholders = ", ".join("%s" for _ in range(len(fields) + 2))
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.entity_table} (model_id, workflow_run_id, {", ".join(fields)})
VALUES ({placeholders})
RETURNING {config.entity_id}
""",
                ),
                (self.model_id, self.workflow_run_id, *values),
            )
        else:
            assignments = ",\n       ".join(f"{field} = %s" for field in fields)
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.entity_table}
   SET workflow_run_id = %s,
       {assignments},
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {config.entity_id} = %s
RETURNING {config.entity_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.entity_id]),
            )
        assert row is not None
        self._entity_cache(config)[normalize_model_key_value(name)] = row[config.entity_id]
        return row[config.entity_id]

    async def _upsert_membership(
        self, config: LayerConfig, entity_id: int, membership: Any
    ) -> None:
        submodel_id = await self.resolve_submodel(config, membership.submodel_name)
        id_field = f"{config.layer}_entity_submodel_id"
        status_field = f"{config.layer}_entity_submodel_status"
        locked_field = f"{config.layer}_entity_submodel_is_locked"
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.membership_table}
 WHERE model_id = %s
   AND {config.entity_id} = %s
   AND {config.submodel_id} = %s
 ORDER BY {id_field}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (self.model_id, entity_id, submodel_id),
        )
        if existing is None:
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.membership_table} (
    model_id, workflow_run_id, {config.entity_id}, {config.submodel_id},
    {status_field}, {locked_field}
)
VALUES (%s, %s, %s, %s, %s, %s)
RETURNING {id_field}
""",
                ),
                (
                    self.model_id,
                    self.workflow_run_id,
                    entity_id,
                    submodel_id,
                    membership.membership_status,
                    membership.membership_is_locked,
                ),
            )
        else:
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.membership_table}
   SET workflow_run_id = %s,
       {status_field} = %s,
       {locked_field} = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {id_field} = %s
RETURNING {id_field}
""",
                ),
                (
                    self.workflow_run_id,
                    membership.membership_status,
                    membership.membership_is_locked,
                    existing[id_field],
                ),
            )

    async def _upsert_entity_source(self, config: LayerConfig, entity_id: int, source: Any) -> int:
        if source.support_source_type == "object":
            source_object_id, _ = await self.resolve_object(source.source_object)
            assertion_record_id = None
        else:
            source_object_id = None
            assertion_record_id = await self.resolve_assertion_record(
                source.assertion_record.modeling_assertion_record_key
            )
        id_field = f"{config.layer}_entity_source_mapping_id"
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.entity_source_table}
 WHERE model_id = %s
   AND {config.entity_id} = %s
   AND support_source_type = %s
   AND (
       (%s = 'object' AND source_object_id = %s)
       OR (%s = 'assertion' AND modeling_assertion_record_id = %s)
   )
 ORDER BY {id_field}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (
                self.model_id,
                entity_id,
                source.support_source_type,
                source.support_source_type,
                source_object_id,
                source.support_source_type,
                assertion_record_id,
            ),
        )
        columns = [
            "model_id",
            "workflow_run_id",
            config.entity_id,
            "support_source_type",
            "source_object_id",
            "modeling_assertion_record_id",
        ]
        values: list[object] = [
            self.model_id,
            self.workflow_run_id,
            entity_id,
            source.support_source_type,
            source_object_id,
            assertion_record_id,
        ]
        update_fields: list[tuple[str, object]] = [("workflow_run_id", self.workflow_run_id)]
        if config.entity_source_role_column is not None:
            columns.append(config.entity_source_role_column)
            values.append(source.source_role)
            update_fields.append((config.entity_source_role_column, source.source_role))
        for suffix, value in (
            ("order", source.source_order),
            ("rationale", source.rationale),
            ("status", source.status),
            ("is_locked", source.is_locked),
        ):
            column = f"{config.layer}_entity_source_mapping_{suffix}"
            columns.append(column)
            values.append(value)
            update_fields.append((column, value))
        if existing is None:
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.entity_source_table} ({", ".join(columns)})
VALUES ({", ".join("%s" for _ in columns)})
RETURNING {id_field}
""",
                ),
                tuple(values),
            )
        else:
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.entity_source_table}
   SET {", ".join(f"{column} = %s" for column, _ in update_fields)},
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {id_field} = %s
RETURNING {id_field}
""",
                ),
                (*[value for _, value in update_fields], existing[id_field]),
            )
        assert row is not None
        return row[id_field]

    async def _upsert_attribute(self, config: LayerConfig, record: Any) -> tuple[int, int]:
        entity_name = getattr(record, f"{config.layer}_entity_name")
        attribute_name = getattr(record, f"{config.layer}_attribute_name")
        entity_id = await self.resolve_entity(config, entity_name)
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.attribute_id}
  FROM {config.attribute_table}
 WHERE model_id = %s
   AND {config.entity_id} = %s
   AND lower(btrim({config.layer}_attribute_name)) = lower(btrim(%s))
 ORDER BY {config.attribute_id}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (self.model_id, entity_id, attribute_name),
        )
        fields = config.attribute_fields
        values = tuple(getattr(record, field) for field in fields)
        if existing is None:
            columns = ("model_id", "workflow_run_id", config.entity_id, *fields)
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.attribute_table} ({", ".join(columns)})
VALUES ({", ".join("%s" for _ in columns)})
RETURNING {config.attribute_id}
""",
                ),
                (self.model_id, self.workflow_run_id, entity_id, *values),
            )
        else:
            assignments = ",\n       ".join(f"{field} = %s" for field in fields)
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.attribute_table}
   SET workflow_run_id = %s,
       {assignments},
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {config.attribute_id} = %s
RETURNING {config.attribute_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.attribute_id]),
            )
        assert row is not None
        self._attribute_cache(config)[
            (normalize_model_key_value(entity_name), normalize_model_key_value(attribute_name))
        ] = row[config.attribute_id]
        return row[config.attribute_id], entity_id

    async def _upsert_attribute_source(
        self,
        config: LayerConfig,
        *,
        entity_id: int,
        attribute_id: int,
        source: Any,
    ) -> None:
        entity_source_mapping_id = None
        if source.support_source_type == "attribute":
            source_object_id, source_attribute_id, _ = await self.resolve_attribute(
                source.source_attribute
            )
            entity_source_mapping_id = await self._find_entity_object_source(
                config, entity_id, source_object_id
            )
            assertion_record_id = None
        else:
            source_object_id = None
            source_attribute_id = None
            assertion_record_id = await self.resolve_assertion_record(
                source.assertion_record.modeling_assertion_record_key
            )
        id_field = f"{config.layer}_attribute_source_mapping_id"
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.attribute_source_table}
 WHERE model_id = %s
   AND {config.attribute_id} = %s
   AND support_source_type = %s
   AND (
       (%s = 'attribute' AND source_attribute_id = %s)
       OR (%s = 'assertion' AND modeling_assertion_record_id = %s)
   )
 ORDER BY {id_field}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (
                self.model_id,
                attribute_id,
                source.support_source_type,
                source.support_source_type,
                source_attribute_id,
                source.support_source_type,
                assertion_record_id,
            ),
        )
        order_field = f"{config.layer}_attribute_source_mapping_order"
        rationale_field = f"{config.layer}_attribute_source_mapping_rationale"
        status_field = f"{config.layer}_attribute_source_mapping_status"
        locked_field = f"{config.layer}_attribute_source_mapping_is_locked"
        if existing is None:
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.attribute_source_table} (
    model_id,
    workflow_run_id,
    {config.layer}_entity_source_mapping_id,
    {config.entity_id},
    {config.attribute_id},
    support_source_type,
    source_object_id,
    source_attribute_id,
    modeling_assertion_record_id,
    {order_field},
    {rationale_field},
    {status_field},
    {locked_field}
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING {id_field}
""",
                ),
                (
                    self.model_id,
                    self.workflow_run_id,
                    entity_source_mapping_id,
                    entity_id,
                    attribute_id,
                    source.support_source_type,
                    source_object_id,
                    source_attribute_id,
                    assertion_record_id,
                    source.source_order,
                    source.rationale,
                    source.status,
                    source.is_locked,
                ),
            )
        else:
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.attribute_source_table}
   SET workflow_run_id = %s,
       {order_field} = %s,
       {rationale_field} = %s,
       {status_field} = %s,
       {locked_field} = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {id_field} = %s
RETURNING {id_field}
""",
                ),
                (
                    self.workflow_run_id,
                    source.source_order,
                    source.rationale,
                    source.status,
                    source.is_locked,
                    existing[id_field],
                ),
            )

    async def _find_entity_object_source(
        self, config: LayerConfig, entity_id: int, source_object_id: int
    ) -> int:
        id_field = f"{config.layer}_entity_source_mapping_id"
        row = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.entity_source_table}
 WHERE model_id = %s
   AND {config.entity_id} = %s
   AND support_source_type = 'object'
   AND source_object_id = %s
 ORDER BY {id_field}
 LIMIT 1
""",
            ),
            (self.model_id, entity_id, source_object_id),
        )
        if row is None:
            raise InvalidRequestError(
                "A physical Attribute source requires its Entity Object source."
            )
        return row[id_field]

    async def _upsert_layer_relationship(self, config: LayerConfig, record: Any) -> None:
        from_entity_name = getattr(record, f"from_{config.layer}_entity_name")
        from_attribute_name = getattr(record, f"from_{config.layer}_attribute_name")
        to_entity_name = getattr(record, f"to_{config.layer}_entity_name")
        to_attribute_name = getattr(record, f"to_{config.layer}_attribute_name")
        from_entity_id = await self.resolve_entity(config, from_entity_name)
        to_entity_id = await self.resolve_entity(config, to_entity_name)
        from_attribute_id = await self.resolve_modeled_attribute(
            config, from_entity_name, from_attribute_name
        )
        to_attribute_id = await self.resolve_modeled_attribute(
            config, to_entity_name, to_attribute_name
        )
        relationship_name = getattr(record, f"{config.layer}_relationship_name")
        if config.layer == "logical":
            identity_predicate = (
                f"lower(btrim({config.layer}_relationship_name)) = lower(btrim(%s))"
            )
            identity_values = (relationship_name,)
        else:
            relationship_kind = record.dimensional_relationship_kind
            relationship_role = record.dimensional_relationship_role_name
            identity_predicate = """
lower(btrim(dimensional_relationship_kind)) = lower(btrim(%s))
   AND coalesce(lower(btrim(dimensional_relationship_role_name)), '') =
       coalesce(lower(btrim(%s::text)), '')
""".strip()
            identity_values = (relationship_kind, relationship_role)
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.relationship_id}
  FROM {config.relationship_table}
 WHERE model_id = %s
   AND {config.layer}_relationship_from_entity_id = %s
   AND {config.layer}_relationship_from_attribute_id = %s
   AND {config.layer}_relationship_to_entity_id = %s
   AND {config.layer}_relationship_to_attribute_id = %s
   AND {identity_predicate}
 ORDER BY {config.relationship_id}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (
                self.model_id,
                from_entity_id,
                from_attribute_id,
                to_entity_id,
                to_attribute_id,
                *identity_values,
            ),
        )
        endpoint_fields = (
            f"{config.layer}_relationship_from_entity_id",
            f"{config.layer}_relationship_from_attribute_id",
            f"{config.layer}_relationship_to_entity_id",
            f"{config.layer}_relationship_to_attribute_id",
        )
        fields = (*config.relationship_fields, *endpoint_fields)
        values = (
            *(getattr(record, field) for field in config.relationship_fields),
            from_entity_id,
            from_attribute_id,
            to_entity_id,
            to_attribute_id,
        )
        if existing is None:
            columns = ("model_id", "workflow_run_id", *fields)
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.relationship_table} ({", ".join(columns)})
VALUES ({", ".join("%s" for _ in columns)})
RETURNING {config.relationship_id}
""",
                ),
                (self.model_id, self.workflow_run_id, *values),
            )
        else:
            assignments = ",\n       ".join(f"{field} = %s" for field in fields)
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.relationship_table}
   SET workflow_run_id = %s,
       {assignments},
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE {config.relationship_id} = %s
RETURNING {config.relationship_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.relationship_id]),
            )

    async def resolve_submodel(self, config: LayerConfig, name: str) -> int:
        cache = self._submodel_cache(config)
        normalized = normalize_model_key_value(name)
        if normalized in cache:
            return cache[normalized]
        row = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.submodel_id}
  FROM {config.submodel_table}
 WHERE model_id = %s
   AND lower(btrim({config.layer}_submodel_name)) = lower(btrim(%s))
 ORDER BY {config.submodel_id}
 LIMIT 1
""",
            ),
            (self.model_id, name),
        )
        if row is None:
            raise InvalidRequestError(f"A referenced {config.layer} Submodel was not found.")
        cache[normalized] = row[config.submodel_id]
        return row[config.submodel_id]

    async def resolve_entity(self, config: LayerConfig, name: str) -> int:
        cache = self._entity_cache(config)
        normalized = normalize_model_key_value(name)
        if normalized in cache:
            return cache[normalized]
        row = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.entity_id}
  FROM {config.entity_table}
 WHERE model_id = %s
   AND lower(btrim({config.layer}_entity_name)) = lower(btrim(%s))
 ORDER BY {config.entity_id}
 LIMIT 1
""",
            ),
            (self.model_id, name),
        )
        if row is None:
            raise InvalidRequestError(f"A referenced {config.layer} Entity was not found.")
        cache[normalized] = row[config.entity_id]
        return row[config.entity_id]

    async def resolve_modeled_attribute(
        self, config: LayerConfig, entity_name: str, attribute_name: str
    ) -> int:
        cache = self._attribute_cache(config)
        key = (normalize_model_key_value(entity_name), normalize_model_key_value(attribute_name))
        if key in cache:
            return cache[key]
        row = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT attribute.{config.attribute_id}
  FROM {config.attribute_table} AS attribute
  JOIN {config.entity_table} AS entity
    ON entity.{config.entity_id} = attribute.{config.entity_id}
   AND entity.model_id = attribute.model_id
 WHERE attribute.model_id = %s
   AND lower(btrim(entity.{config.layer}_entity_name)) = lower(btrim(%s))
   AND lower(btrim(attribute.{config.layer}_attribute_name)) = lower(btrim(%s))
 ORDER BY attribute.{config.attribute_id}
 LIMIT 1
""",
            ),
            (self.model_id, entity_name, attribute_name),
        )
        if row is None:
            raise InvalidRequestError(f"A referenced {config.layer} Attribute was not found.")
        cache[key] = row[config.attribute_id]
        return row[config.attribute_id]

    def _submodel_cache(self, config: LayerConfig) -> dict[str, int]:
        return (
            self._logical_submodel_ids
            if config.layer == "logical"
            else self._dimensional_submodel_ids
        )

    def _entity_cache(self, config: LayerConfig) -> dict[str, int]:
        return (
            self._logical_entity_ids if config.layer == "logical" else self._dimensional_entity_ids
        )

    def _attribute_cache(self, config: LayerConfig) -> dict[tuple[str, str], int]:
        return (
            self._logical_attribute_ids
            if config.layer == "logical"
            else self._dimensional_attribute_ids
        )

    async def _apply_model_object_bindings(
        self,
        records: tuple[ModelingRecord, ...],
    ) -> int:
        for raw in records:
            record = _as(raw, ModelObjectBindingRecord)
            object_id, _ = await self.resolve_object(record)
            config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
            modeled_entity_id = await self.resolve_entity(config, record.modeled_entity_name)
            logical_entity_id = (
                modeled_entity_id if record.modeled_entity_type == "logical_entity" else None
            )
            dimensional_entity_id = (
                modeled_entity_id if record.modeled_entity_type == "dimensional_entity" else None
            )
            row = await self.transaction.fetch_one(
                _UPSERT_MODEL_OBJECT_BINDING_SQL,
                (
                    self.model_id,
                    object_id,
                    record.modeled_entity_type,
                    logical_entity_id,
                    dimensional_entity_id,
                    self.workflow_run_id,
                    record.model_object_binding_status,
                    record.model_object_binding_is_locked,
                ),
            )
            if row is None:
                raise InvalidRequestError("Model Object Binding could not be materialized.")
            self._model_object_bindings[_entity_binding_key(record)] = (
                row["model_object_binding_id"],
                row["object_id"],
            )
        return len(records)

    async def _apply_model_attribute_bindings(
        self,
        records: tuple[ModelingRecord, ...],
    ) -> int:
        for raw in records:
            record = _as(raw, ModelAttributeBindingRecord)
            model_object_binding_id, _ = await self.resolve_model_object_binding(record)
            config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
            modeled_attribute_id = await self.resolve_modeled_attribute(
                config,
                record.modeled_entity_name,
                record.modeled_attribute_name,
            )
            attribute_row = await self.transaction.fetch_one(
                _RESOLVE_BOUND_ATTRIBUTE_SQL,
                (record.attribute_name, model_object_binding_id, self.model_id),
            )
            if attribute_row is None:
                raise InvalidRequestError(
                    "A target Attribute for the Model Attribute Binding was not found."
                )
            logical_attribute_id = (
                modeled_attribute_id if record.modeled_entity_type == "logical_entity" else None
            )
            dimensional_attribute_id = (
                modeled_attribute_id if record.modeled_entity_type == "dimensional_entity" else None
            )
            row = await self.transaction.fetch_one(
                _UPSERT_MODEL_ATTRIBUTE_BINDING_SQL,
                (
                    model_object_binding_id,
                    logical_attribute_id,
                    dimensional_attribute_id,
                    attribute_row["attribute_id"],
                    self.workflow_run_id,
                    record.model_attribute_binding_status,
                    record.model_attribute_binding_is_locked,
                ),
            )
            if row is None:
                raise InvalidRequestError("Model Attribute Binding could not be materialized.")
            self._model_attribute_bindings[_attribute_binding_key(record)] = row[
                "model_attribute_binding_id"
            ]
        return len(records)

    async def resolve_model_object_binding(self, record: Any) -> tuple[int, int]:
        key = _entity_binding_key(record)
        cached = self._model_object_bindings.get(key)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            _FIND_MODEL_OBJECT_BINDING_SQL,
            (self.model_id, record.modeled_entity_type, record.modeled_entity_name),
        )
        if row is None:
            raise InvalidRequestError("A referenced Model Object Binding was not found.")
        resolved = (row["model_object_binding_id"], row["object_id"])
        self._model_object_bindings[key] = resolved
        return resolved

    async def resolve_model_attribute_binding(
        self,
        record: MappingAttributeRecord,
    ) -> int:
        key = _attribute_binding_key(record)
        cached = self._model_attribute_bindings.get(key)
        if cached is not None:
            return cached
        model_object_binding_id, _ = await self.resolve_model_object_binding(record)
        row = await self.transaction.fetch_one(
            _FIND_MODEL_ATTRIBUTE_BINDING_SQL,
            (
                self.model_id,
                record.modeled_entity_type,
                model_object_binding_id,
                record.modeled_attribute_name,
            ),
        )
        if row is None:
            raise InvalidRequestError("A referenced Model Attribute Binding was not found.")
        self._model_attribute_bindings[key] = row["model_attribute_binding_id"]
        return row["model_attribute_binding_id"]

    async def resolve_output_template(
        self,
        code: str | None,
        target_type: str,
    ) -> int | None:
        if code is None:
            return None
        key = (target_type, normalize_model_key_value(code))
        cached = self._output_template_ids.get(key)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            _RESOLVE_OUTPUT_TEMPLATE_SQL,
            (code, target_type),
        )
        if row is None:
            raise InvalidRequestError("A referenced Output Template was not found.")
        self._output_template_ids[key] = row["output_template_id"]
        return row["output_template_id"]

    async def _apply_mapping(self, records: dict[str, tuple[ModelingRecord, ...]]) -> int:
        action_count = 0
        mapping_workflow_run_id = (
            None if self._mapping_policy is None else self._mapping_policy.workflow_run_id
        )
        for raw in records.get("mapping_dependency", ()):
            record = _as(raw, MappingDependencyRecord)
            source_system_id = await self.resolve_system(record.source_system_code)
            await self.transaction.fetch_one(
                _UPSERT_MAPPING_DEPENDENCY_SQL,
                (
                    self.model_id,
                    record.modeled_entity_type,
                    source_system_id,
                    record.source_system_dependency_order,
                    mapping_workflow_run_id,
                    record.mapping_source_system_dependency_status,
                    record.mapping_source_system_dependency_is_locked,
                ),
            )
            action_count += 1
        for raw in records.get("mapping_object", ()):
            record = _as(raw, MappingObjectRecord)
            await self._upsert_mapping_object(record)
            action_count += 1
        for raw in records.get("mapping_attribute", ()):
            record = _as(raw, MappingAttributeRecord)
            await self._upsert_mapping_attribute(record)
            action_count += 1
        return action_count

    async def _apply_generated_code(self, records: tuple[ModelingRecord, ...]) -> int:
        code_workflow_run_id = (
            self.workflow_run_id if self._model_workflow == "code_generation" else None
        )
        for raw in records:
            record = _as(raw, GeneratedCodeRecord)
            model_object_binding_id, object_id = await self.resolve_model_object_binding(record)
            context = await self.transaction.fetch_one(
                _RESOLVE_CODE_INPUT_SQL,
                (
                    self.model_id,
                    record.modeled_entity_type,
                    record.artifact_type,
                    object_id,
                    record.modeled_entity_name,
                ),
            )
            if context is None:
                raise InvalidRequestError(
                    "Generated Code requires complete active Mapping for its Binding."
                )
            existing = await self.transaction.fetch_one(
                _FIND_GENERATED_CODE_SQL,
                (model_object_binding_id, record.artifact_name),
            )
            values = (
                record.artifact_name,
                record.artifact_type,
                record.generated_code_content,
                str(context["code_input_digest"]).strip(),
                code_workflow_run_id,
                record.generated_code_status,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_GENERATED_CODE_SQL,
                    (model_object_binding_id, *values),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_GENERATED_CODE_SQL,
                    (*values, existing["generated_code_id"]),
                )
            if row is None:
                raise InvalidRequestError("Generated Code could not be materialized.")
            self._generated_code_ids[_artifact_key(record)] = row["generated_code_id"]
        return len(records)

    async def _apply_generated_code_source_systems(
        self,
        records: tuple[ModelingRecord, ...],
    ) -> int:
        code_workflow_run_id = (
            self.workflow_run_id if self._model_workflow == "code_generation" else None
        )
        for raw in records:
            record = _as(raw, GeneratedCodeSourceSystemRecord)
            generated_code_id = await self.resolve_generated_code(record)
            source_system_id = await self.resolve_system(record.source_system_code)
            existing = await self.transaction.fetch_one(
                _FIND_GENERATED_CODE_SOURCE_SYSTEM_SQL,
                (generated_code_id, source_system_id),
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_GENERATED_CODE_SOURCE_SYSTEM_SQL,
                    (
                        generated_code_id,
                        source_system_id,
                        code_workflow_run_id,
                        record.generated_code_source_system_status,
                    ),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_GENERATED_CODE_SOURCE_SYSTEM_SQL,
                    (
                        code_workflow_run_id,
                        record.generated_code_source_system_status,
                        existing["generated_code_source_system_id"],
                    ),
                )
            if row is None:
                raise InvalidRequestError("Generated Code source System could not be materialized.")
        return len(records)

    async def resolve_generated_code(
        self,
        record: GeneratedCodeSourceSystemRecord,
    ) -> int:
        key = _artifact_key(record)
        cached = self._generated_code_ids.get(key)
        if cached is not None:
            return cached
        model_object_binding_id, _ = await self.resolve_model_object_binding(record)
        row = await self.transaction.fetch_one(
            _FIND_GENERATED_CODE_SQL,
            (model_object_binding_id, record.artifact_name),
        )
        if row is None:
            raise InvalidRequestError("A referenced Generated Code artifact was not found.")
        self._generated_code_ids[key] = row["generated_code_id"]
        return row["generated_code_id"]

    async def resolve_validation_context_digests(
        self,
        source_system_code: str,
    ) -> tuple[str, str | None]:
        normalized_system = normalize_model_key_value(source_system_code)
        cached = self._validation_context_digests.get(normalized_system)
        if cached is not None:
            return cached
        if self._validation_target_context_rows is None:
            rows = await self.transaction.fetch_all(
                _VALIDATION_TARGET_CONTEXT_SQL,
                (self.model_id, self.model_id),
            )
            self._validation_target_context_rows = tuple(rows)
        if self._validation_generated_code_rows is None:
            rows = await self.transaction.fetch_all(
                _VALIDATION_GENERATED_CODE_SQL,
                (self.model_id,),
            )
            self._validation_generated_code_rows = tuple(rows)

        contexts: dict[tuple[str, str], dict[str, object]] = {}
        mapping_entries: list[dict[str, object]] = []
        for row in self._validation_target_context_rows:
            source_context = row.get("source_context")
            if not isinstance(source_context, dict):
                raise InvalidRequestError("The server-derived Mapping context is invalid.")
            typed_source_context = cast(dict[str, object], source_context)
            raw_systems = typed_source_context.get("source_systems")
            if not isinstance(raw_systems, list):
                raise InvalidRequestError("The server-derived Mapping context is incomplete.")
            system_codes: set[str] = set()
            for item in cast(list[object], raw_systems):
                if not isinstance(item, dict):
                    continue
                typed_item = cast(dict[str, object], item)
                system_code = typed_item.get("system_code")
                if system_code is not None:
                    system_codes.add(normalize_model_key_value(str(system_code)))
            if normalized_system not in system_codes:
                continue
            entity_type = str(row["modeled_entity_type"])
            entity_name = normalize_model_key_value(str(row["modeled_entity_name"]))
            target = _normalized_target_document(typed_source_context.get("target"))
            code_input_digest = str(row["code_input_digest"]).strip()
            entry: dict[str, object] = {
                "modeled_entity_type": entity_type,
                "modeled_entity_name": entity_name,
                "target": target,
                "code_input_digest": code_input_digest,
            }
            contexts[(entity_type, entity_name)] = entry
            mapping_entries.append(entry)
        mapping_context_digest = _context_entries_digest(mapping_entries)
        if mapping_context_digest is None:
            raise InvalidRequestError(
                "Validation requires complete active Mapping for its source System."
            )

        code_entries: list[dict[str, object]] = []
        for row in self._validation_generated_code_rows:
            if row.get("generated_code_status") != "active":
                continue
            source_codes = {
                normalize_model_key_value(str(code)) for code in row.get("source_system_codes", ())
            }
            if normalized_system not in source_codes:
                continue
            entity_key = (
                str(row["modeled_entity_type"]),
                normalize_model_key_value(str(row["modeled_entity_name"])),
            )
            context = contexts.get(entity_key)
            if context is None:
                continue
            code_entries.append(
                {
                    **context,
                    "artifact_name": str(row["artifact_name"]),
                    "artifact_type": str(row["artifact_type"]),
                    "generated_code_digest": str(row["generated_code_digest"]).strip(),
                }
            )
        resolved = (
            mapping_context_digest,
            _context_entries_digest(code_entries),
        )
        self._validation_context_digests[normalized_system] = resolved
        return resolved

    async def _apply_validation_groups(self, records: tuple[ModelingRecord, ...]) -> int:
        validation_workflow_run_id = (
            self.workflow_run_id if self._model_workflow == "validation" else None
        )
        for raw in records:
            record = _as(raw, ValidationGroupRecord)
            tenant_id = await self.resolve_tenant(record.tenant_code)
            system_id = await self.resolve_system(record.system_code)
            (
                mapping_context_digest,
                code_context_digest,
            ) = await self.resolve_validation_context_digests(record.system_code)
            existing = await self.transaction.fetch_one(
                _FIND_VALIDATION_GROUP_SQL,
                (
                    self.model_id,
                    tenant_id,
                    system_id,
                    record.validation_group_name,
                ),
            )
            mutable_values = (
                record.validation_group_name,
                record.validation_group_description,
                mapping_context_digest,
                code_context_digest,
                record.is_active,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_VALIDATION_GROUP_SQL,
                    (
                        self.model_id,
                        tenant_id,
                        system_id,
                        validation_workflow_run_id,
                        *mutable_values,
                    ),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_VALIDATION_GROUP_SQL,
                    (
                        validation_workflow_run_id,
                        *mutable_values,
                        existing["validation_group_id"],
                    ),
                )
            assert row is not None
            self._validation_group_ids[_validation_group_key(record)] = row["validation_group_id"]
        return len(records)

    async def _apply_validation_checks(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ValidationCheckRecord)
            validation_group_id = await self.resolve_validation_group(record)
            existing = await self.transaction.fetch_one(
                _FIND_VALIDATION_CHECK_SQL,
                (validation_group_id, record.validation_check_name),
            )
            comparison_value = (
                None
                if record.validation_comparison_value is None
                else Jsonb(record.validation_comparison_value)
            )
            values = (
                record.validation_check_name,
                record.validation_check_description,
                record.validation_category_code,
                record.validation_severity,
                record.validation_query_sql,
                record.validation_comparison_query_sql,
                record.validation_result_data_type,
                record.validation_comparison_operator,
                record.validation_comparison_value_type,
                comparison_value,
                record.is_active,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_VALIDATION_CHECK_SQL,
                    (validation_group_id, *values),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_VALIDATION_CHECK_SQL,
                    (*values, existing["validation_check_id"]),
                )
            assert row is not None
        return len(records)

    async def resolve_validation_group(self, record: ValidationCheckRecord) -> int:
        key = _validation_group_key(record)
        cached = self._validation_group_ids.get(key)
        if cached is not None:
            return cached
        tenant_id = await self.resolve_tenant(record.tenant_code)
        system_id = await self.resolve_system(record.system_code)
        row = await self.transaction.fetch_one(
            _FIND_VALIDATION_GROUP_SQL,
            (
                self.model_id,
                tenant_id,
                system_id,
                record.validation_group_name,
            ),
        )
        if row is None:
            raise InvalidRequestError("A referenced Validation Group was not found.")
        self._validation_group_ids[key] = row["validation_group_id"]
        return row["validation_group_id"]

    async def _upsert_mapping_object(self, record: MappingObjectRecord) -> int:
        model_object_binding_id, _ = await self.resolve_model_object_binding(record)
        source_system_id = await self.resolve_system(record.source_system_code)
        if self._mapping_policy is None:
            output_template_id = await self.resolve_output_template(
                record.output_template_code,
                "mapping_object",
            )
            mapping_workflow_run_id = None
        else:
            output_template_id = self._mapping_policy.object_output_template_id
            mapping_workflow_run_id = self._mapping_policy.workflow_run_id
        existing = await self.transaction.fetch_one(
            _FIND_MAPPING_OBJECT_SQL,
            (self.model_id, model_object_binding_id, source_system_id),
        )
        transformation = (
            None
            if record.mapping_transformation_document is None
            else Jsonb(record.mapping_transformation_document)
        )
        if existing is None:
            row = await self.transaction.fetch_one(
                _INSERT_MAPPING_OBJECT_SQL,
                (
                    self.model_id,
                    model_object_binding_id,
                    source_system_id,
                    output_template_id,
                    record.object_dependency_order,
                    transformation,
                    mapping_workflow_run_id,
                    record.object_mapping_status,
                    record.object_mapping_is_locked,
                ),
            )
        else:
            row = await self.transaction.fetch_one(
                _UPDATE_MAPPING_OBJECT_SQL,
                (
                    output_template_id,
                    record.object_dependency_order,
                    transformation,
                    mapping_workflow_run_id,
                    record.object_mapping_status,
                    record.object_mapping_is_locked,
                    existing["mapping_object_id"],
                ),
            )
        if row is None:
            raise InvalidRequestError("Mapping Object could not be materialized.")
        key = _mapping_key(record)
        self._mapping_object_ids[key] = row["mapping_object_id"]
        return row["mapping_object_id"]

    async def _upsert_mapping_attribute(self, record: MappingAttributeRecord) -> int:
        mapping_object_id = await self.resolve_mapping_object(record)
        model_attribute_binding_id = await self.resolve_model_attribute_binding(record)
        if self._mapping_policy is None:
            output_template_id = await self.resolve_output_template(
                record.output_template_code,
                "mapping_attribute",
            )
            mapping_workflow_run_id = None
        else:
            output_template_id = self._mapping_policy.attribute_output_template_id
            mapping_workflow_run_id = self._mapping_policy.workflow_run_id
        existing = await self.transaction.fetch_one(
            _FIND_MAPPING_ATTRIBUTE_SQL,
            (mapping_object_id, model_attribute_binding_id),
        )
        transformation = (
            None
            if record.attribute_mapping_transformation_document is None
            else Jsonb(record.attribute_mapping_transformation_document)
        )
        if existing is None:
            row = await self.transaction.fetch_one(
                _INSERT_MAPPING_ATTRIBUTE_SQL,
                (
                    mapping_object_id,
                    model_attribute_binding_id,
                    output_template_id,
                    transformation,
                    mapping_workflow_run_id,
                    record.attribute_mapping_status,
                    record.attribute_mapping_is_locked,
                ),
            )
        else:
            row = await self.transaction.fetch_one(
                _UPDATE_MAPPING_ATTRIBUTE_SQL,
                (
                    output_template_id,
                    transformation,
                    mapping_workflow_run_id,
                    record.attribute_mapping_status,
                    record.attribute_mapping_is_locked,
                    existing["mapping_attribute_id"],
                ),
            )
        if row is None:
            raise InvalidRequestError("Mapping Attribute could not be materialized.")
        return row["mapping_attribute_id"]

    async def resolve_mapping_object(self, record: MappingAttributeRecord) -> int:
        key = _mapping_key(record)
        cached = self._mapping_object_ids.get(key)
        if cached is not None:
            return cached
        model_object_binding_id, _ = await self.resolve_model_object_binding(record)
        source_system_id = await self.resolve_system(record.source_system_code)
        row = await self.transaction.fetch_one(
            _FIND_MAPPING_OBJECT_SQL,
            (
                self.model_id,
                model_object_binding_id,
                source_system_id,
            ),
        )
        if row is None:
            raise InvalidRequestError("A referenced Mapping Object was not found.")
        self._mapping_object_ids[key] = row["mapping_object_id"]
        return row["mapping_object_id"]


def _as[T: ModelingRecord](record: ModelingRecord, expected: type[T]) -> T:
    if not isinstance(record, expected):
        raise InvalidRequestError("Validated Model record type is inconsistent.")
    return record


def _as_runtime(record: ModelingRecord, expected: type[ModelingRecord]) -> Any:
    if not isinstance(record, expected):
        raise InvalidRequestError("Validated Model record type is inconsistent.")
    return record


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _entity_binding_key(record: Any) -> tuple[str, str]:
    return (
        record.modeled_entity_type,
        normalize_model_key_value(record.modeled_entity_name),
    )


def _attribute_binding_key(record: Any) -> tuple[str, str, str]:
    return (
        record.modeled_entity_type,
        normalize_model_key_value(record.modeled_entity_name),
        normalize_model_key_value(record.modeled_attribute_name),
    )


def _mapping_key(
    record: MappingObjectRecord | MappingAttributeRecord,
) -> tuple[str, str, str]:
    return (
        record.modeled_entity_type,
        normalize_model_key_value(record.modeled_entity_name),
        normalize_model_key_value(record.source_system_code),
    )


def _artifact_key(
    record: GeneratedCodeRecord | GeneratedCodeSourceSystemRecord,
) -> tuple[str, str, str]:
    return (
        record.modeled_entity_type,
        normalize_model_key_value(record.modeled_entity_name),
        normalize_model_key_value(record.artifact_name),
    )


def _normalized_target_document(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise InvalidRequestError("The server-derived Mapping target is invalid.")
    document = cast(dict[str, object], raw)
    fields = (
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    )
    if any(not isinstance(document.get(field), str) for field in fields):
        raise InvalidRequestError("The server-derived Mapping target is incomplete.")
    return {field: normalize_model_key_value(cast(str, document[field])) for field in fields}


def _context_entries_digest(entries: list[dict[str, object]]) -> str | None:
    if not entries:
        return None
    entries.sort(key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")))
    return _digest(entries)


def _validation_group_key(
    record: ValidationGroupRecord | ValidationCheckRecord,
) -> tuple[str, str, str]:
    return (
        normalize_model_key_value(record.tenant_code),
        normalize_model_key_value(record.system_code),
        normalize_model_key_value(record.validation_group_name),
    )
