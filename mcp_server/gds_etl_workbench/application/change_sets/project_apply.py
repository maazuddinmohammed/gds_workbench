"""Atomic materialization of validated ID-free Project records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, LiteralString, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from gds_etl_workbench.application.modeling.modeled_layer import (
    DIMENSIONAL,
    LOGICAL,
    LayerConfig,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, MappingBranchUnavailableError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ContextGroupRecord,
    ContextRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    MappingAttributeRecord,
    MappingObjectRecord,
    ModelingRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ProfilingProfileRecord,
    ProjectDetailsRecord,
    ProjectInputScopeRecord,
    SubjectAreaRecord,
    SubjectAreaTableRecord,
    ValidationCheckRecord,
    ValidationGroupRecord,
    normalize_project_key_value,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction

_UPDATE_PROJECT_DETAILS_SQL: LiteralString = """
UPDATE project.project
   SET project_description = %s,
       logical_schemas = %s,
       dimensional_schemas = %s,
       silver_model_naming_instructions = %s,
       silver_model_audit_columns_template = %s,
       gold_model_naming_instructions = %s,
       gold_model_technical_columns_template = %s,
       gold_model_audit_columns_template = %s,
       logical_entity_scd_type = %s,
       dimensional_entity_scd_type = %s,
       logical_coverage_threshold_percent = %s,
       dimensional_coverage_threshold_percent = %s,
       logical_enforce_coverage_threshold = %s,
       dimensional_enforce_coverage_threshold = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE project_id = %s
   AND project_name = %s
   AND is_active
RETURNING project_id
"""

_UPSERT_PROJECT_INPUT_SCOPE_SQL: LiteralString = """
INSERT INTO project.project_input_scope (
    project_id,
    object_id,
    project_input_scope_is_locked,
    is_active
)
VALUES (%s, %s, %s, %s)
ON CONFLICT (project_id, object_id) DO UPDATE
   SET project_input_scope_is_locked = EXCLUDED.project_input_scope_is_locked,
       is_active = EXCLUDED.is_active,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
RETURNING project_input_scope_id
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
  JOIN project.project AS target_project
    ON target_project.project_id = %s
   AND target_project.is_active
 WHERE lower(btrim(system.system_code)) = lower(btrim(%s))
   AND lower(btrim(connection.connection_code)) = lower(btrim(%s))
   AND lower(btrim(object.object_schema)) = lower(btrim(%s))
   AND lower(btrim(object.object_name)) = lower(btrim(%s))
   AND connection.is_active
   AND system.is_active
   AND (object.source_tenant_id = target_project.tenant_id OR (
       object.source_tenant_id = ANY(%s::BIGINT[]) AND EXISTS (
       SELECT 1 FROM reference.zone AS input_zone
        WHERE input_zone.zone_id = object.zone_id
          AND lower(btrim(input_zone.zone_code)) IN ('source', 'bronze')
   )))
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
  JOIN project.project AS target_project
    ON target_project.project_id = %s
   AND target_project.is_active
 WHERE lower(btrim(system.system_code)) = lower(btrim(%s))
   AND lower(btrim(connection.connection_code)) = lower(btrim(%s))
   AND lower(btrim(object.object_schema)) = lower(btrim(%s))
   AND lower(btrim(object.object_name)) = lower(btrim(%s))
   AND lower(btrim(attribute.attribute_name)) = lower(btrim(%s))
   AND connection.is_active
   AND system.is_active
   AND (object.source_tenant_id = target_project.tenant_id OR (
       object.source_tenant_id = ANY(%s::BIGINT[]) AND EXISTS (
       SELECT 1 FROM reference.zone AS input_zone
        WHERE input_zone.zone_id = object.zone_id
          AND lower(btrim(input_zone.zone_code)) IN ('source', 'bronze')
   )))
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
    project_id,
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
ON CONFLICT (project_id, attribute_id) DO UPDATE
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
    project_id,
    agent_run_id,
    inference_workflow_run_id,
    validation_workflow_run_id,
    validation_source_context_digest,
    from_object_id,
    from_attribute_id,
    to_object_id,
    to_attribute_id,
    relationship_kind,
    inferred_cardinality,
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
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
       inferred_cardinality = EXCLUDED.inferred_cardinality,
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

_FIND_CONTEXT_GROUP_SQL: LiteralString = """
SELECT context_group_id FROM project.context_group
 WHERE project_id = %s AND lower(btrim(name)) = lower(btrim(%s))
"""

_INSERT_CONTEXT_GROUP_SQL: LiteralString = """
INSERT INTO project.context_group (
    project_id, context_type_id, source_system_id, name, description, is_active
)
VALUES (%s, %s, %s, %s, %s, %s)
RETURNING context_group_id
"""

_UPDATE_CONTEXT_GROUP_SQL: LiteralString = """
UPDATE project.context_group
   SET context_type_id = %s, source_system_id = %s, name = %s, description = %s, is_active = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
 WHERE context_group_id = %s AND project_id = %s
RETURNING context_group_id
"""

_UPSERT_CONTEXT_RECORD_SQL: LiteralString = """
INSERT INTO project.context_record (
    project_id, context_group_id, context_record_id, context_text,
    source_reference, status, is_locked
) VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (context_record_id, project_id) DO UPDATE
   SET context_group_id = EXCLUDED.context_group_id,
       context_text = EXCLUDED.context_text,
       source_reference = EXCLUDED.source_reference,
       status = EXCLUDED.status,
       is_locked = EXCLUDED.is_locked,
       updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
RETURNING context_record_id::TEXT
"""

_FIND_SUBJECT_AREA_SQL: LiteralString = """
SELECT subject_area_id
  FROM workflow.subject_area
 WHERE project_id = %s
   AND lower(btrim(subject_area_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_SUBJECT_AREA_SQL: LiteralString = """
INSERT INTO workflow.subject_area (
    project_id,
    workflow_run_id,
    subject_area_name,
    subject_area_definition,
    subject_area_is_active,
    subject_area_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s)
RETURNING subject_area_id
"""

# Model tables keep updated_time only; they have no updated_by column.
_UPDATE_SUBJECT_AREA_SQL: LiteralString = """
UPDATE workflow.subject_area
   SET workflow_run_id = %s,
       subject_area_name = %s,
       subject_area_definition = %s,
       subject_area_is_active = %s,
       subject_area_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP
 WHERE subject_area_id = %s
RETURNING subject_area_id
"""

_UPSERT_SUBJECT_AREA_TABLE_SQL: LiteralString = """
INSERT INTO workflow.subject_area_table (
    project_id,
    workflow_run_id,
    subject_area_id,
    object_id,
    subject_area_table_is_active,
    subject_area_table_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_subject_area_table_member DO UPDATE
   SET workflow_run_id = EXCLUDED.workflow_run_id,
       subject_area_table_is_active = EXCLUDED.subject_area_table_is_active,
       subject_area_table_is_locked = EXCLUDED.subject_area_table_is_locked,
       updated_time = CURRENT_TIMESTAMP
RETURNING subject_area_table_id
"""

_RESOLVE_OUTPUT_TEMPLATE_SQL: LiteralString = """
SELECT output_template_id
  FROM application.output_template
 WHERE lower(btrim(output_template_code)) = lower(btrim(%s))
   AND output_template_target_type = %s
   AND (output_template_modeled_entity_type IS NULL
        OR output_template_modeled_entity_type = %s)
   AND is_active
"""

_FIND_MAPPING_OBJECT_SQL: LiteralString = """
SELECT mapping_object_id, object_mapping_status
  FROM workflow.mapping_object
 WHERE project_id = %s
   AND modeled_entity_type = %s
   AND coalesce(logical_entity_id, dimensional_entity_id) = %s
   AND source_system_id = %s
 FOR UPDATE
"""

_MAPPING_BRANCHES_SQL: LiteralString = """
SELECT modeled_entity_id, source_system_id
  FROM workflow.list_mapping_branches(%s, %s)
"""

_INSERT_MAPPING_OBJECT_SQL: LiteralString = """
INSERT INTO workflow.mapping_object (
    project_id,
    modeled_entity_type,
    logical_entity_id,
    dimensional_entity_id,
    source_system_id,
    output_template_id,
    object_dependency_order,
    mapping_transformation_document,
    agent_run_id,
    workflow_run_id,
    object_mapping_status,
    object_mapping_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
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
   AND coalesce(logical_attribute_id, dimensional_attribute_id) = %s
 FOR UPDATE
"""

_INSERT_MAPPING_ATTRIBUTE_SQL: LiteralString = """
INSERT INTO workflow.mapping_attribute (
    mapping_object_id,
    project_id,
    modeled_entity_type,
    logical_entity_id,
    dimensional_entity_id,
    logical_attribute_id,
    dimensional_attribute_id,
    output_template_id,
    attribute_mapping_transformation_document,
    agent_run_id,
    workflow_run_id,
    attribute_mapping_status,
    attribute_mapping_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
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
 WHERE context.modeled_entity_id = %s
   AND lower(btrim(context.modeled_entity_schema_name)) = lower(btrim(%s))
   AND lower(btrim(context.modeled_entity_name)) = lower(btrim(%s))
"""

_FIND_GENERATED_CODE_SQL: LiteralString = """
SELECT generated_code_id
  FROM workflow.generated_code
 WHERE project_id = %s
   AND modeled_entity_type = %s
   AND coalesce(logical_entity_id, dimensional_entity_id) = %s
   AND lower(btrim(artifact_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_GENERATED_CODE_SQL: LiteralString = """
INSERT INTO workflow.generated_code (
    project_id,
    modeled_entity_type,
    logical_entity_id,
    dimensional_entity_id,
    artifact_name,
    artifact_type,
    generated_code_content,
    code_storage_type,
    code_repository_url,
    code_commit_path,
    code_entry_point,
    code_parameters,
    code_input_digest,
    agent_run_id,
    workflow_run_id,
    generated_code_status,
    generated_code_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
RETURNING generated_code_id
"""

_UPDATE_GENERATED_CODE_SQL: LiteralString = """
UPDATE workflow.generated_code
   SET artifact_name = %s,
       artifact_type = %s,
       generated_code_content = %s,
       code_storage_type = %s,
       code_repository_url = %s,
       code_commit_path = %s,
       code_entry_point = %s,
       code_parameters = %s,
       code_input_digest = %s,
       agent_run_id = NULL,
       workflow_run_id = %s,
       generated_code_status = %s,
       generated_code_is_locked = %s,
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
    generated_code_source_system_status,
    generated_code_source_system_is_locked
)
VALUES (%s, %s, NULL, %s, %s, %s)
RETURNING generated_code_source_system_id
"""

_UPDATE_GENERATED_CODE_SOURCE_SYSTEM_SQL: LiteralString = """
UPDATE workflow.generated_code_source_system
   SET agent_run_id = NULL,
       workflow_run_id = %s,
       generated_code_source_system_status = %s,
       generated_code_source_system_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE generated_code_source_system_id = %s
RETURNING generated_code_source_system_id
"""

_VALIDATION_TARGET_CONTEXT_SQL: LiteralString = """
SELECT context.modeled_entity_type,
       context.modeled_entity_schema_name,
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
       context.modeled_entity_schema_name,
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
SELECT entity.modeled_entity_type,
       entity.modeled_entity_schema_name,
       entity.modeled_entity_name,
       generated.artifact_name,
       generated.artifact_type,
       generated.generated_code_digest,
       generated.code_storage_type,
       generated.code_repository_url,
       generated.code_commit_path,
       generated.code_entry_point,
       generated.code_parameters,
       btrim(generated.code_input_digest::TEXT) AS code_input_digest,
       generated.generated_code_status,
       coalesce(array_agg(system.system_code ORDER BY lower(system.system_code))
           FILTER (WHERE assignment.generated_code_source_system_status = 'active'
                     AND system.is_active), ARRAY[]::VARCHAR[]) AS source_system_codes
  FROM workflow.generated_code AS generated
  JOIN workflow.modeled_entity AS entity
    ON entity.project_id = generated.project_id
   AND entity.modeled_entity_type = generated.modeled_entity_type
   AND entity.modeled_entity_id = coalesce(
       generated.logical_entity_id, generated.dimensional_entity_id
   )
  LEFT JOIN workflow.generated_code_source_system AS assignment
    ON assignment.generated_code_id = generated.generated_code_id
  LEFT JOIN core.system AS system ON system.system_id = assignment.source_system_id
 WHERE generated.project_id = %s
 GROUP BY entity.modeled_entity_type, entity.modeled_entity_schema_name,
          entity.modeled_entity_name, generated.generated_code_id
"""

_FIND_VALIDATION_GROUP_SQL: LiteralString = """
SELECT validation_group_id
  FROM workflow.validation_group
 WHERE project_id = %s
   AND tenant_id = %s
   AND system_id = %s
   AND lower(btrim(validation_group_name)) = lower(btrim(%s))
 FOR UPDATE
"""

_INSERT_VALIDATION_GROUP_SQL: LiteralString = """
INSERT INTO workflow.validation_group (
    project_id,
    tenant_id,
    system_id,
    agent_run_id,
    workflow_run_id,
    validation_group_name,
    validation_group_description,
    mapping_context_digest,
    code_context_digest,
    is_active,
    is_locked
)
VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s)
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
       is_locked = %s,
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
    is_active,
    is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
       is_locked = %s,
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
class ProjectMaterializer:
    transaction: WriteTransaction
    project_id: int
    source_context_digest: str
    workflow_run_id: int | None = None
    readable_source_tenant_ids: tuple[int, ...] = ()
    change_set_id: UUID | None = None
    request_principal: RequestPrincipal | None = None
    draft_revision: int | None = None
    candidate_digest: str | None = None
    _project_workflow: str | None = None
    _mapping_policy: _MappingMaterializationPolicy | None = None
    _object_ids: dict[tuple[str, ...], tuple[int, int]] = field(
        default_factory=dict[tuple[str, ...], tuple[int, int]]
    )
    _attribute_ids: dict[tuple[str, ...], tuple[int, int, int]] = field(
        default_factory=dict[tuple[str, ...], tuple[int, int, int]]
    )
    _system_ids: dict[str, int] = field(default_factory=dict[str, int])
    _tenant_ids: dict[str, int] = field(default_factory=dict[str, int])
    _context_group_ids: dict[str, int] = field(default_factory=dict[str, int])
    _context_record_ids: dict[str, str] = field(default_factory=dict[str, str])
    _subject_area_ids: dict[str, int] = field(default_factory=dict[str, int])
    _logical_entity_ids: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
    )
    _logical_attribute_ids: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
    )
    _dimensional_entity_ids: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
    )
    _dimensional_attribute_ids: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
    )
    _mapping_object_ids: dict[tuple[str, str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str, str], int]
    )
    _generated_code_ids: dict[tuple[str, str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str, str], int]
    )
    _output_template_ids: dict[tuple[str, str, str], int] = field(
        default_factory=dict[tuple[str, str, str], int]
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
        project_id: int,
        source_context_digest: str,
        workflow_run_id: int,
        project_workflow: str,
        mapping_object_output_template_id: int | None,
        mapping_attribute_output_template_id: int | None,
    ) -> ProjectMaterializer:
        if workflow_run_id <= 0 or any(
            template_id is not None and template_id <= 0
            for template_id in (
                mapping_object_output_template_id,
                mapping_attribute_output_template_id,
            )
        ):
            raise InvalidRequestError("Workflow Mapping materialization policy is invalid.")
        policy = None
        if project_workflow == "mapping":
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
            project_id=project_id,
            source_context_digest=source_context_digest,
            workflow_run_id=workflow_run_id,
            _project_workflow=project_workflow,
            _mapping_policy=policy,
        )

    async def apply(
        self,
        records: dict[str, tuple[ModelingRecord, ...]],
    ) -> int:
        """Materialize in dependency order inside the caller's transaction."""
        action_count = 0
        if records.get("object_enrichment") or records.get("attribute_enrichment"):
            if (
                self.change_set_id is None
                or self.request_principal is None
                or self.draft_revision is None
                or self.candidate_digest is None
            ):
                raise InvalidRequestError(
                    "Enrichment requires the owned validated Change Set Apply context."
                )
            result = await self.transaction.fetch_one(
                "SELECT mcp.apply_project_enrichment_change_set(%s,%s,%s,%s,%s,%s,%s) "
                "AS action_count",
                (
                    self.request_principal.entra_tenant_id,
                    self.request_principal.entra_object_id,
                    "service_principal"
                    if self.request_principal.actor_kind == ActorKind.WORKLOAD
                    else "user",
                    self.project_id,
                    self.change_set_id,
                    self.draft_revision,
                    self.candidate_digest,
                ),
            )
            if result is None:
                raise InvalidRequestError("Enrichment Change Set could not be applied.")
            action_count += int(result["action_count"])
        action_count += await self._apply_project_details(records.get("project_details", ()))
        action_count += await self._apply_project_input_scope(
            records.get("project_input_scope", ())
        )
        action_count += await self._apply_context_groups(records.get("context_group", ()))
        action_count += await self._apply_context_records(records.get("context_record", ()))
        action_count += await self._apply_profiles(records.get("profiling_profile", ()))
        action_count += await self._apply_analysis(records.get("analysis_result", ()))
        action_count += await self._apply_subject_areas(records.get("subject_area", ()))
        action_count += await self._apply_subject_area_tables(records.get("subject_area_table", ()))
        action_count += await self._apply_logical(records)
        action_count += await self._apply_dimensional(records)
        action_count += await self._apply_mapping(records)
        action_count += await self._apply_generated_code(records.get("generated_code", ()))
        action_count += await self._apply_generated_code_source_systems(
            records.get("generated_code_source_system", ())
        )
        action_count += await self._apply_validation_groups(records.get("validation_group", ()))
        action_count += await self._apply_validation_checks(records.get("validation_check", ()))
        return action_count

    async def _apply_project_details(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ProjectDetailsRecord)
            row = await self.transaction.fetch_one(
                _UPDATE_PROJECT_DETAILS_SQL,
                (
                    record.project_description,
                    Jsonb([item.model_dump(mode="json") for item in record.logical_schemas]),
                    Jsonb([item.model_dump(mode="json") for item in record.dimensional_schemas]),
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
                    record.logical_entity_scd_type,
                    record.dimensional_entity_scd_type,
                    record.logical_coverage_threshold_percent,
                    record.dimensional_coverage_threshold_percent,
                    record.logical_enforce_coverage_threshold,
                    record.dimensional_enforce_coverage_threshold,
                    self.project_id,
                    record.project_name,
                ),
            )
            if row is None:
                raise InvalidRequestError("Project details could not be updated.")
        return len(records)

    async def _apply_project_input_scope(
        self,
        records: tuple[ModelingRecord, ...],
    ) -> int:
        for raw in records:
            record = _as(raw, ProjectInputScopeRecord)
            object_id, _ = await self.resolve_object(record)
            row = await self.transaction.fetch_one(
                _UPSERT_PROJECT_INPUT_SCOPE_SQL,
                (
                    self.project_id,
                    object_id,
                    record.project_input_scope_is_locked,
                    record.is_active,
                ),
            )
            if row is None:
                raise InvalidRequestError("Project Input Scope could not be materialized.")
        return len(records)

    async def _apply_profiles(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ProfilingProfileRecord)
            object_id, attribute_id, _ = await self.resolve_attribute(record)
            await self.transaction.fetch_one(
                _UPSERT_PROFILE_SQL,
                (
                    self.project_id,
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
                    self.project_id,
                    self.workflow_run_id,
                    from_object_id,
                    from_attribute_id,
                    to_object_id,
                    to_attribute_id,
                    record.relationship_kind,
                    record.inferred_cardinality,
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

    async def _apply_context_groups(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ContextGroupRecord)
            context_type = await self.transaction.fetch_one(
                "SELECT context_type_id FROM reference.context_type "
                "WHERE lower(btrim(name)) = lower(btrim(%s))",
                (record.context_type_name,),
            )
            if context_type is None:
                raise InvalidRequestError("A referenced Context Type was not found.")
            system_id = (
                None
                if record.source_system_code is None
                else await self.resolve_system(record.source_system_code)
            )
            existing = await self.transaction.fetch_one(
                _FIND_CONTEXT_GROUP_SQL, (self.project_id, record.context_group_name)
            )
            values = (
                context_type["context_type_id"],
                system_id,
                record.context_group_name,
                record.context_group_description,
                record.is_active,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_CONTEXT_GROUP_SQL, (self.project_id, *values)
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_CONTEXT_GROUP_SQL,
                    (*values, existing["context_group_id"], self.project_id),
                )
            assert row is not None
            self._context_group_ids[normalize_project_key_value(record.context_group_name)] = row[
                "context_group_id"
            ]
        return len(records)

    async def _apply_context_records(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, ContextRecord)
            group_id = await self.resolve_context_group(record.context_group_name)
            row = await self.transaction.fetch_one(
                _UPSERT_CONTEXT_RECORD_SQL,
                (
                    self.project_id,
                    group_id,
                    record.context_record_id,
                    record.context_text,
                    record.source_reference,
                    record.status,
                    record.is_locked,
                ),
            )
            assert row is not None
            self._context_record_ids[record.context_record_id] = row["context_record_id"]
        return len(records)

    async def resolve_object(self, key: PhysicalObjectKey) -> tuple[int, int]:
        natural_key = (
            normalize_project_key_value(key.tenant_code),
            normalize_project_key_value(key.system_code),
            normalize_project_key_value(key.connection_code),
            normalize_project_key_value(key.object_schema),
            normalize_project_key_value(key.object_name),
        )
        cached = self._object_ids.get(natural_key)
        if cached is not None:
            return cached
        parameters = (
            natural_key[0],
            self.project_id,
            *natural_key[1:],
            list(self.readable_source_tenant_ids),
        )
        row = await self.transaction.fetch_one(_RESOLVE_OBJECT_SQL, parameters)
        if row is None:
            raise InvalidRequestError("A referenced physical Object was not found.")
        resolved = (row["object_id"], row["system_id"])
        self._object_ids[natural_key] = resolved
        return resolved

    async def resolve_attribute(self, key: PhysicalAttributeKey) -> tuple[int, int, int]:
        natural_key = (
            normalize_project_key_value(key.tenant_code),
            normalize_project_key_value(key.system_code),
            normalize_project_key_value(key.connection_code),
            normalize_project_key_value(key.object_schema),
            normalize_project_key_value(key.object_name),
            normalize_project_key_value(key.attribute_name),
        )
        cached = self._attribute_ids.get(natural_key)
        if cached is not None:
            return cached
        parameters = (
            natural_key[0],
            self.project_id,
            *natural_key[1:],
            list(self.readable_source_tenant_ids),
        )
        row = await self.transaction.fetch_one(_RESOLVE_ATTRIBUTE_SQL, parameters)
        if row is None:
            raise InvalidRequestError("A referenced physical Attribute was not found.")
        resolved = (row["object_id"], row["attribute_id"], row["system_id"])
        self._attribute_ids[natural_key] = resolved
        return resolved

    async def resolve_system(self, code: str) -> int:
        normalized = normalize_project_key_value(code)
        cached = self._system_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(_RESOLVE_SYSTEM_SQL, (normalized,))
        if row is None:
            raise InvalidRequestError("A referenced System was not found.")
        self._system_ids[normalized] = row["system_id"]
        return row["system_id"]

    async def resolve_tenant(self, code: str) -> int:
        normalized = normalize_project_key_value(code)
        cached = self._tenant_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(_RESOLVE_TENANT_SQL, (normalized,))
        if row is None:
            raise InvalidRequestError("A referenced Tenant was not found.")
        self._tenant_ids[normalized] = row["tenant_id"]
        return row["tenant_id"]

    async def resolve_context_group(self, name: str) -> int:
        normalized = normalize_project_key_value(name)
        cached = self._context_group_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            _FIND_CONTEXT_GROUP_SQL,
            (self.project_id, name),
        )
        if row is None:
            raise InvalidRequestError("A referenced Context Group was not found.")
        self._context_group_ids[normalized] = row["context_group_id"]
        return row["context_group_id"]

    async def resolve_context_record(self, key: str) -> str:
        normalized = normalize_project_key_value(key)
        cached = self._context_record_ids.get(normalized)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            """
SELECT context_record_id::TEXT
  FROM project.context_record
 WHERE project_id = %s
   AND context_record_id = %s::UUID
""",
            (self.project_id, key),
        )
        if row is None:
            raise InvalidRequestError("A referenced Context Record was not found.")
        self._context_record_ids[normalized] = row["context_record_id"]
        return row["context_record_id"]

    async def _apply_subject_areas(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, SubjectAreaRecord)
            existing = await self.transaction.fetch_one(
                _FIND_SUBJECT_AREA_SQL,
                (self.project_id, record.subject_area_name),
            )
            values = (
                record.subject_area_name,
                record.subject_area_definition,
                record.subject_area_is_active,
                record.subject_area_is_locked,
            )
            row = await self.transaction.fetch_one(
                *(
                    (_INSERT_SUBJECT_AREA_SQL, (self.project_id, self.workflow_run_id, *values))
                    if existing is None
                    else (
                        _UPDATE_SUBJECT_AREA_SQL,
                        (self.workflow_run_id, *values, existing["subject_area_id"]),
                    )
                )
            )
            assert row is not None
            self._subject_area_ids[normalize_project_key_value(record.subject_area_name)] = row[
                "subject_area_id"
            ]
        return len(records)

    async def _apply_subject_area_tables(self, records: tuple[ModelingRecord, ...]) -> int:
        for raw in records:
            record = _as(raw, SubjectAreaTableRecord)
            name = normalize_project_key_value(record.subject_area_name)
            area_id = self._subject_area_ids.get(name)
            if area_id is None:
                row = await self.transaction.fetch_one(
                    _FIND_SUBJECT_AREA_SQL,
                    (self.project_id, record.subject_area_name),
                )
                if row is None:
                    raise InvalidRequestError("A referenced Subject Area was not found.")
                area_id = self._subject_area_ids[name] = row["subject_area_id"]
            object_id, _ = await self.resolve_object(
                PhysicalObjectKey(
                    tenant_code=record.tenant_code,
                    system_code=record.system_code,
                    connection_code=record.connection_code,
                    object_schema=record.object_schema,
                    object_name=record.object_name,
                )
            )
            await self.transaction.fetch_one(
                _UPSERT_SUBJECT_AREA_TABLE_SQL,
                (
                    self.project_id,
                    self.workflow_run_id,
                    area_id,
                    object_id,
                    record.subject_area_table_is_active,
                    record.subject_area_table_is_locked,
                ),
            )
        return len(records)

    async def _apply_logical(self, records: dict[str, tuple[ModelingRecord, ...]]) -> int:
        return await self._apply_layer(
            config=LOGICAL,
            entity_records=records.get("logical_entity", ()),
            attribute_records=records.get("logical_attribute", ()),
            relationship_records=records.get("logical_relationship", ()),
            entity_type=LogicalEntityRecord,
            attribute_type=LogicalAttributeRecord,
            relationship_type=LogicalRelationshipRecord,
        )

    async def _apply_dimensional(self, records: dict[str, tuple[ModelingRecord, ...]]) -> int:
        return await self._apply_layer(
            config=DIMENSIONAL,
            entity_records=records.get("dimensional_entity", ()),
            attribute_records=records.get("dimensional_attribute", ()),
            relationship_records=records.get("dimensional_relationship", ()),
            entity_type=DimensionalEntityRecord,
            attribute_type=DimensionalAttributeRecord,
            relationship_type=DimensionalRelationshipRecord,
        )

    async def _apply_layer(
        self,
        *,
        config: LayerConfig,
        entity_records: tuple[ModelingRecord, ...],
        attribute_records: tuple[ModelingRecord, ...],
        relationship_records: tuple[ModelingRecord, ...],
        entity_type: type[ModelingRecord],
        attribute_type: type[ModelingRecord],
        relationship_type: type[ModelingRecord],
    ) -> int:
        action_count = 0
        for raw in entity_records:
            record = _as_runtime(raw, entity_type)
            entity_id = await self._upsert_entity(config, record)
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

    # Model tables keep updated_time only; they have no updated_by column.
    async def _upsert_entity(self, config: LayerConfig, record: Any) -> int:
        name_field = f"{config.layer}_entity_name"
        name = getattr(record, name_field)
        schema_name = getattr(record, f"{config.layer}_entity_schema_name")
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.entity_id}
  FROM {config.entity_table}
 WHERE project_id = %s
   AND lower(btrim({config.layer}_entity_schema_name)) = lower(btrim(%s))
   AND lower(btrim({name_field})) = lower(btrim(%s))
 FOR UPDATE
""",
            ),
            (self.project_id, schema_name, name),
        )
        fields = config.entity_fields
        values = tuple(getattr(record, field) for field in fields)
        if existing is None:
            placeholders = ", ".join("%s" for _ in range(len(fields) + 2))
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.entity_table} (project_id, workflow_run_id, {", ".join(fields)})
VALUES ({placeholders})
RETURNING {config.entity_id}
""",
                ),
                (self.project_id, self.workflow_run_id, *values),
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
       updated_time = CURRENT_TIMESTAMP
 WHERE {config.entity_id} = %s
RETURNING {config.entity_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.entity_id]),
            )
        assert row is not None
        self._entity_cache(config)[
            (normalize_project_key_value(schema_name), normalize_project_key_value(name))
        ] = row[config.entity_id]
        return row[config.entity_id]

    async def _upsert_entity_source(self, config: LayerConfig, entity_id: int, source: Any) -> int:
        # The row stores no source type: the filled id is the source, either an Object
        # (Logical), a Logical Entity (Dimensional) or a Context Record.
        source_column = (
            "source_object_id" if config.layer == "logical" else "source_logical_entity_id"
        )
        if source.support_source_type == "logical_entity":
            key = source.source_logical_entity
            source_id = await self.resolve_entity(
                LOGICAL, key.logical_entity_schema_name, key.logical_entity_name
            )
            context_record_id = None
        elif source.support_source_type == "object":
            source_id, _ = await self.resolve_object(source.source_object)
            context_record_id = None
        else:
            source_id = None
            context_record_id = await self.resolve_context_record(
                source.context_record.context_record_id
            )
        match_column, match_value = (
            (source_column, source_id)
            if context_record_id is None
            else ("context_record_id", context_record_id)
        )
        id_field = f"{config.layer}_entity_source_mapping_id"
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.entity_source_table}
 WHERE project_id = %s
   AND {config.entity_id} = %s
   AND {match_column} = %s
 ORDER BY {id_field}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (self.project_id, entity_id, match_value),
        )
        prefix = f"{config.layer}_entity_source_mapping"
        values = (source.rationale, source.is_active, source.is_locked)
        if existing is None:
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.entity_source_table} (
    project_id,
    workflow_run_id,
    {config.entity_id},
    {source_column},
    context_record_id,
    {prefix}_rationale,
    {prefix}_is_active,
    {prefix}_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
RETURNING {id_field}
""",
                ),
                (
                    self.project_id,
                    self.workflow_run_id,
                    entity_id,
                    source_id,
                    context_record_id,
                    *values,
                ),
            )
        else:
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.entity_source_table}
   SET workflow_run_id = %s,
       {prefix}_rationale = %s,
       {prefix}_is_active = %s,
       {prefix}_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP
 WHERE {id_field} = %s
RETURNING {id_field}
""",
                ),
                (self.workflow_run_id, *values, existing[id_field]),
            )
        assert row is not None
        return row[id_field]

    async def _upsert_attribute(self, config: LayerConfig, record: Any) -> tuple[int, int]:
        entity_name = getattr(record, f"{config.layer}_entity_name")
        schema_name = getattr(record, f"{config.layer}_entity_schema_name")
        attribute_name = getattr(record, f"{config.layer}_attribute_name")
        entity_id = await self.resolve_entity(config, schema_name, entity_name)
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.attribute_id}
  FROM {config.attribute_table}
 WHERE project_id = %s
   AND {config.entity_id} = %s
   AND lower(btrim({config.layer}_attribute_name)) = lower(btrim(%s))
 ORDER BY {config.attribute_id}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (self.project_id, entity_id, attribute_name),
        )
        fields = config.attribute_fields
        values = tuple(getattr(record, field) for field in fields)
        if existing is None:
            columns = ("project_id", "workflow_run_id", config.entity_id, *fields)
            row = await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.attribute_table} ({", ".join(columns)})
VALUES ({", ".join("%s" for _ in columns)})
RETURNING {config.attribute_id}
""",
                ),
                (self.project_id, self.workflow_run_id, entity_id, *values),
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
       updated_time = CURRENT_TIMESTAMP
 WHERE {config.attribute_id} = %s
RETURNING {config.attribute_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.attribute_id]),
            )
        assert row is not None
        self._attribute_cache(config)[
            (
                normalize_project_key_value(schema_name),
                normalize_project_key_value(entity_name),
                normalize_project_key_value(attribute_name),
            )
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
        object_column = (
            "source_object_id" if config.layer == "logical" else "source_logical_entity_id"
        )
        attribute_column = (
            "source_attribute_id" if config.layer == "logical" else "source_logical_attribute_id"
        )
        entity_source_mapping_id = None
        if source.support_source_type == "logical_attribute":
            key = source.source_logical_attribute
            source_object_id = await self.resolve_entity(
                LOGICAL, key.logical_entity_schema_name, key.logical_entity_name
            )
            source_attribute_id = await self.resolve_modeled_attribute(
                LOGICAL,
                key.logical_entity_schema_name,
                key.logical_entity_name,
                key.logical_attribute_name,
            )
            entity_source_mapping_id = await self._find_entity_source(
                config, entity_id, source_object_id
            )
            context_record_id = None
        elif source.support_source_type == "attribute":
            source_object_id, source_attribute_id, _ = await self.resolve_attribute(
                source.source_attribute
            )
            entity_source_mapping_id = await self._find_entity_source(
                config, entity_id, source_object_id
            )
            context_record_id = None
        else:
            source_object_id = None
            source_attribute_id = None
            context_record_id = await self.resolve_context_record(
                source.context_record.context_record_id
            )
        match_column, match_value = (
            (attribute_column, source_attribute_id)
            if context_record_id is None
            else ("context_record_id", context_record_id)
        )
        id_field = f"{config.layer}_attribute_source_mapping_id"
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.attribute_source_table}
 WHERE project_id = %s
   AND {config.attribute_id} = %s
   AND {match_column} = %s
 ORDER BY {id_field}
 LIMIT 1
 FOR UPDATE
""",
            ),
            (self.project_id, attribute_id, match_value),
        )
        prefix = f"{config.layer}_attribute_source_mapping"
        values = (source.rationale, source.is_active, source.is_locked)
        if existing is None:
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.attribute_source_table} (
    project_id,
    workflow_run_id,
    {config.layer}_entity_source_mapping_id,
    {config.entity_id},
    {config.attribute_id},
    {object_column},
    {attribute_column},
    context_record_id,
    {prefix}_rationale,
    {prefix}_is_active,
    {prefix}_is_locked
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING {id_field}
""",
                ),
                (
                    self.project_id,
                    self.workflow_run_id,
                    entity_source_mapping_id,
                    entity_id,
                    attribute_id,
                    source_object_id,
                    source_attribute_id,
                    context_record_id,
                    *values,
                ),
            )
        else:
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
UPDATE {config.attribute_source_table}
   SET workflow_run_id = %s,
       {prefix}_rationale = %s,
       {prefix}_is_active = %s,
       {prefix}_is_locked = %s,
       updated_time = CURRENT_TIMESTAMP
 WHERE {id_field} = %s
RETURNING {id_field}
""",
                ),
                (self.workflow_run_id, *values, existing[id_field]),
            )

    async def _find_entity_source(
        self, config: LayerConfig, entity_id: int, source_object_id: int
    ) -> int:
        id_field = f"{config.layer}_entity_source_mapping_id"
        source_column = (
            "source_object_id" if config.layer == "logical" else "source_logical_entity_id"
        )
        row = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {id_field}
  FROM {config.entity_source_table}
 WHERE project_id = %s
   AND {config.entity_id} = %s
   AND {source_column} = %s
 ORDER BY {id_field}
 LIMIT 1
""",
            ),
            (self.project_id, entity_id, source_object_id),
        )
        if row is None:
            raise InvalidRequestError("An Attribute source requires its parent Entity source.")
        return row[id_field]

    async def _upsert_layer_relationship(self, config: LayerConfig, record: Any) -> None:
        from_entity_name = getattr(record, f"from_{config.layer}_entity_name")
        from_attribute_name = getattr(record, f"from_{config.layer}_attribute_name")
        to_entity_name = getattr(record, f"to_{config.layer}_entity_name")
        to_attribute_name = getattr(record, f"to_{config.layer}_attribute_name")
        from_schema = getattr(record, f"from_{config.layer}_entity_schema_name")
        to_schema = getattr(record, f"to_{config.layer}_entity_schema_name")
        from_entity_id = await self.resolve_entity(config, from_schema, from_entity_name)
        to_entity_id = await self.resolve_entity(config, to_schema, to_entity_name)
        from_attribute_id = await self.resolve_modeled_attribute(
            config, from_schema, from_entity_name, from_attribute_name
        )
        to_attribute_id = await self.resolve_modeled_attribute(
            config, to_schema, to_entity_name, to_attribute_name
        )
        # Child -> parent: the table allows one relationship per foreign-key (from) Attribute,
        # so that Attribute is the identity; Apply may repoint its parent endpoint.
        existing = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.relationship_id}
  FROM {config.relationship_table}
 WHERE project_id = %s
   AND {config.layer}_relationship_from_attribute_id = %s
 FOR UPDATE
""",
            ),
            (self.project_id, from_attribute_id),
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
            columns = ("project_id", "workflow_run_id", *fields)
            await self.transaction.fetch_one(
                cast(
                    LiteralString,
                    f"""
INSERT INTO {config.relationship_table} ({", ".join(columns)})
VALUES ({", ".join("%s" for _ in columns)})
RETURNING {config.relationship_id}
""",
                ),
                (self.project_id, self.workflow_run_id, *values),
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
       updated_time = CURRENT_TIMESTAMP
 WHERE {config.relationship_id} = %s
RETURNING {config.relationship_id}
""",
                ),
                (self.workflow_run_id, *values, existing[config.relationship_id]),
            )

    async def resolve_entity(self, config: LayerConfig, schema_name: str, name: str) -> int:
        cache = self._entity_cache(config)
        normalized = (normalize_project_key_value(schema_name), normalize_project_key_value(name))
        if normalized in cache:
            return cache[normalized]
        row = await self.transaction.fetch_one(
            cast(
                LiteralString,
                f"""
SELECT {config.entity_id}
  FROM {config.entity_table}
 WHERE project_id = %s
   AND lower(btrim({config.layer}_entity_schema_name)) = lower(btrim(%s))
   AND lower(btrim({config.layer}_entity_name)) = lower(btrim(%s))
 ORDER BY {config.entity_id}
 LIMIT 1
""",
            ),
            (self.project_id, schema_name, name),
        )
        if row is None:
            raise InvalidRequestError(f"A referenced {config.layer} Entity was not found.")
        cache[normalized] = row[config.entity_id]
        return row[config.entity_id]

    async def resolve_modeled_attribute(
        self, config: LayerConfig, schema_name: str, entity_name: str, attribute_name: str
    ) -> int:
        cache = self._attribute_cache(config)
        key = (
            normalize_project_key_value(schema_name),
            normalize_project_key_value(entity_name),
            normalize_project_key_value(attribute_name),
        )
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
   AND entity.project_id = attribute.project_id
 WHERE attribute.project_id = %s
   AND lower(btrim(entity.{config.layer}_entity_schema_name)) = lower(btrim(%s))
   AND lower(btrim(entity.{config.layer}_entity_name)) = lower(btrim(%s))
   AND lower(btrim(attribute.{config.layer}_attribute_name)) = lower(btrim(%s))
 ORDER BY attribute.{config.attribute_id}
 LIMIT 1
""",
            ),
            (self.project_id, schema_name, entity_name, attribute_name),
        )
        if row is None:
            raise InvalidRequestError(f"A referenced {config.layer} Attribute was not found.")
        cache[key] = row[config.attribute_id]
        return row[config.attribute_id]

    def _entity_cache(self, config: LayerConfig) -> dict[tuple[str, str], int]:
        return (
            self._logical_entity_ids if config.layer == "logical" else self._dimensional_entity_ids
        )

    def _attribute_cache(self, config: LayerConfig) -> dict[tuple[str, str, str], int]:
        return (
            self._logical_attribute_ids
            if config.layer == "logical"
            else self._dimensional_attribute_ids
        )

    async def resolve_output_template(
        self,
        code: str | None,
        target_type: str,
        modeled_entity_type: str,
    ) -> int | None:
        if code is None:
            return None
        key = (target_type, modeled_entity_type, normalize_project_key_value(code))
        cached = self._output_template_ids.get(key)
        if cached is not None:
            return cached
        row = await self.transaction.fetch_one(
            _RESOLVE_OUTPUT_TEMPLATE_SQL,
            (code, target_type, modeled_entity_type),
        )
        if row is None:
            raise InvalidRequestError("A referenced Output Template was not found.")
        self._output_template_ids[key] = row["output_template_id"]
        return row["output_template_id"]

    async def _apply_mapping(self, records: dict[str, tuple[ModelingRecord, ...]]) -> int:
        action_count = 0
        opened: dict[int, tuple[str, int, int]] = {}
        for record_number, raw in enumerate(records.get("mapping_object", ()), start=1):
            record = _as(raw, MappingObjectRecord)
            pair = await self._upsert_mapping_object(record)
            if pair is not None:
                opened[record_number] = pair
            action_count += 1
        for raw in records.get("mapping_attribute", ()):
            record = _as(raw, MappingAttributeRecord)
            await self._upsert_mapping_attribute(record)
            action_count += 1
        # A pair this Change Set makes active must be a Mapping branch; already active pairs
        # stay editable. Checked last, so the Change Set's own sources and Mapping count: a
        # Dimensional branch needs its Logical source's complete Mapping.
        branches: dict[str, set[tuple[int, int]]] = {}
        for record_number, (entity_type, entity_id, source_system_id) in opened.items():
            if entity_type not in branches:
                rows = await self.transaction.fetch_all(
                    _MAPPING_BRANCHES_SQL, (self.project_id, entity_type)
                )
                branches[entity_type] = {
                    (row["modeled_entity_id"], row["source_system_id"]) for row in rows
                }
            if (entity_id, source_system_id) not in branches[entity_type]:
                raise MappingBranchUnavailableError(record_number)
        return action_count

    async def _apply_generated_code(self, records: tuple[ModelingRecord, ...]) -> int:
        code_workflow_run_id = (
            self.workflow_run_id if self._project_workflow == "code_generation" else None
        )
        for raw in records:
            record = _as(raw, GeneratedCodeRecord)
            config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
            entity_id = await self.resolve_entity(
                config, record.modeled_entity_schema_name, record.modeled_entity_name
            )
            context = await self.transaction.fetch_one(
                _RESOLVE_CODE_INPUT_SQL,
                (
                    self.project_id,
                    record.modeled_entity_type,
                    record.artifact_type,
                    entity_id,
                    record.modeled_entity_schema_name,
                    record.modeled_entity_name,
                ),
            )
            if context is None:
                raise InvalidRequestError(
                    "Generated Code requires an active Object or Attribute transformation "
                    "for its Entity."
                )
            existing = await self.transaction.fetch_one(
                _FIND_GENERATED_CODE_SQL,
                (self.project_id, record.modeled_entity_type, entity_id, record.artifact_name),
            )
            values = (
                record.artifact_name,
                record.artifact_type,
                record.generated_code_content,
                record.code_storage_type,
                record.code_repository_url,
                record.code_commit_path,
                record.code_entry_point,
                Jsonb(record.code_parameters) if record.code_parameters is not None else None,
                str(context["code_input_digest"]).strip(),
                code_workflow_run_id,
                record.generated_code_status,
                record.generated_code_is_locked,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_GENERATED_CODE_SQL,
                    (
                        self.project_id,
                        record.modeled_entity_type,
                        entity_id if config.layer == "logical" else None,
                        entity_id if config.layer == "dimensional" else None,
                        *values,
                    ),
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
            self.workflow_run_id if self._project_workflow == "code_generation" else None
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
                        record.generated_code_source_system_is_locked,
                    ),
                )
            else:
                row = await self.transaction.fetch_one(
                    _UPDATE_GENERATED_CODE_SOURCE_SYSTEM_SQL,
                    (
                        code_workflow_run_id,
                        record.generated_code_source_system_status,
                        record.generated_code_source_system_is_locked,
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
        config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
        entity_id = await self.resolve_entity(
            config, record.modeled_entity_schema_name, record.modeled_entity_name
        )
        row = await self.transaction.fetch_one(
            _FIND_GENERATED_CODE_SQL,
            (self.project_id, record.modeled_entity_type, entity_id, record.artifact_name),
        )
        if row is None:
            raise InvalidRequestError("A referenced Generated Code artifact was not found.")
        self._generated_code_ids[key] = row["generated_code_id"]
        return row["generated_code_id"]

    async def resolve_validation_context_digests(
        self,
        source_system_code: str,
    ) -> tuple[str, str | None]:
        normalized_system = normalize_project_key_value(source_system_code)
        cached = self._validation_context_digests.get(normalized_system)
        if cached is not None:
            return cached
        if self._validation_target_context_rows is None:
            rows = await self.transaction.fetch_all(
                _VALIDATION_TARGET_CONTEXT_SQL,
                (self.project_id, self.project_id),
            )
            self._validation_target_context_rows = tuple(rows)
        if self._validation_generated_code_rows is None:
            rows = await self.transaction.fetch_all(
                _VALIDATION_GENERATED_CODE_SQL,
                (self.project_id,),
            )
            self._validation_generated_code_rows = tuple(rows)

        contexts: dict[tuple[str, str, str], dict[str, object]] = {}
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
                    system_codes.add(normalize_project_key_value(str(system_code)))
            if normalized_system not in system_codes:
                continue
            entity_type = str(row["modeled_entity_type"])
            entity_name = normalize_project_key_value(str(row["modeled_entity_name"]))
            schema_name = normalize_project_key_value(str(row["modeled_entity_schema_name"]))
            code_input_digest = str(row["code_input_digest"]).strip()
            entry: dict[str, object] = {
                "modeled_entity_type": entity_type,
                "modeled_entity_name": entity_name,
                "modeled_entity_schema_name": schema_name,
                "code_input_digest": code_input_digest,
            }
            contexts[(entity_type, schema_name, entity_name)] = entry
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
                normalize_project_key_value(str(code))
                for code in row.get("source_system_codes", ())
            }
            if normalized_system not in source_codes:
                continue
            entity_key = (
                str(row["modeled_entity_type"]),
                normalize_project_key_value(str(row["modeled_entity_schema_name"])),
                normalize_project_key_value(str(row["modeled_entity_name"])),
            )
            context = contexts.get(entity_key)
            if context is None or row.get("code_input_digest") != context["code_input_digest"]:
                # Match authoring and ledger reads: stale Code is not Validation evidence.
                continue
            code_entries.append(
                {
                    **context,
                    "artifact_name": str(row["artifact_name"]),
                    "artifact_type": str(row["artifact_type"]),
                    "generated_code_digest": str(row["generated_code_digest"]).strip(),
                    "code_storage_type": row.get("code_storage_type", "table"),
                    "code_repository_url": row.get("code_repository_url"),
                    "code_commit_path": row.get("code_commit_path"),
                    "code_entry_point": row.get("code_entry_point"),
                    "code_parameters": row.get("code_parameters"),
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
            self.workflow_run_id if self._project_workflow == "validation" else None
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
                    self.project_id,
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
                record.is_locked,
            )
            if existing is None:
                row = await self.transaction.fetch_one(
                    _INSERT_VALIDATION_GROUP_SQL,
                    (
                        self.project_id,
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
                record.is_locked,
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
                self.project_id,
                tenant_id,
                system_id,
                record.validation_group_name,
            ),
        )
        if row is None:
            raise InvalidRequestError("A referenced Validation Group was not found.")
        self._validation_group_ids[key] = row["validation_group_id"]
        return row["validation_group_id"]

    async def _upsert_mapping_object(
        self, record: MappingObjectRecord
    ) -> tuple[str, int, int] | None:
        """Upsert one pair; return it when this makes it active, as it must then be a branch."""
        config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
        entity_id = await self.resolve_entity(
            config, record.modeled_entity_schema_name, record.modeled_entity_name
        )
        source_system_id = await self.resolve_system(record.source_system_code)
        if self._mapping_policy is None:
            output_template_id = await self.resolve_output_template(
                record.output_template_code,
                "mapping_object",
                record.modeled_entity_type,
            )
            mapping_workflow_run_id = None
        else:
            output_template_id = self._mapping_policy.object_output_template_id
            mapping_workflow_run_id = self._mapping_policy.workflow_run_id
        existing = await self.transaction.fetch_one(
            _FIND_MAPPING_OBJECT_SQL,
            (self.project_id, record.modeled_entity_type, entity_id, source_system_id),
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
                    self.project_id,
                    record.modeled_entity_type,
                    entity_id if config.layer == "logical" else None,
                    entity_id if config.layer == "dimensional" else None,
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
        opens = record.object_mapping_status == "active" and (
            existing is None or existing["object_mapping_status"] != "active"
        )
        return (record.modeled_entity_type, entity_id, source_system_id) if opens else None

    async def _upsert_mapping_attribute(self, record: MappingAttributeRecord) -> int:
        mapping_object_id = await self.resolve_mapping_object(record)
        config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
        entity_id = await self.resolve_entity(
            config, record.modeled_entity_schema_name, record.modeled_entity_name
        )
        attribute_id = await self.resolve_modeled_attribute(
            config,
            record.modeled_entity_schema_name,
            record.modeled_entity_name,
            record.modeled_attribute_name,
        )
        if self._mapping_policy is None:
            output_template_id = await self.resolve_output_template(
                record.output_template_code,
                "mapping_attribute",
                record.modeled_entity_type,
            )
            mapping_workflow_run_id = None
        else:
            output_template_id = self._mapping_policy.attribute_output_template_id
            mapping_workflow_run_id = self._mapping_policy.workflow_run_id
        existing = await self.transaction.fetch_one(
            _FIND_MAPPING_ATTRIBUTE_SQL,
            (mapping_object_id, attribute_id),
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
                    self.project_id,
                    record.modeled_entity_type,
                    entity_id if config.layer == "logical" else None,
                    entity_id if config.layer == "dimensional" else None,
                    attribute_id if config.layer == "logical" else None,
                    attribute_id if config.layer == "dimensional" else None,
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
        config = LOGICAL if record.modeled_entity_type == "logical_entity" else DIMENSIONAL
        entity_id = await self.resolve_entity(
            config, record.modeled_entity_schema_name, record.modeled_entity_name
        )
        source_system_id = await self.resolve_system(record.source_system_code)
        row = await self.transaction.fetch_one(
            _FIND_MAPPING_OBJECT_SQL,
            (
                self.project_id,
                record.modeled_entity_type,
                entity_id,
                source_system_id,
            ),
        )
        if row is None:
            raise InvalidRequestError("A referenced Mapping Object was not found.")
        self._mapping_object_ids[key] = row["mapping_object_id"]
        return row["mapping_object_id"]


def _as[T: ModelingRecord](record: ModelingRecord, expected: type[T]) -> T:
    if not isinstance(record, expected):
        raise InvalidRequestError("Validated Project record type is inconsistent.")
    return record


def _as_runtime(record: ModelingRecord, expected: type[ModelingRecord]) -> Any:
    if not isinstance(record, expected):
        raise InvalidRequestError("Validated Project record type is inconsistent.")
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


def _mapping_key(
    record: MappingObjectRecord | MappingAttributeRecord,
) -> tuple[str, str, str, str]:
    return (
        record.modeled_entity_type,
        normalize_project_key_value(record.modeled_entity_schema_name),
        normalize_project_key_value(record.modeled_entity_name),
        normalize_project_key_value(record.source_system_code),
    )


def _artifact_key(
    record: GeneratedCodeRecord | GeneratedCodeSourceSystemRecord,
) -> tuple[str, str, str, str]:
    return (
        record.modeled_entity_type,
        normalize_project_key_value(record.modeled_entity_schema_name),
        normalize_project_key_value(record.modeled_entity_name),
        normalize_project_key_value(record.artifact_name),
    )


def _context_entries_digest(entries: list[dict[str, object]]) -> str | None:
    if not entries:
        return None
    entries.sort(key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")))
    return _digest(entries)


def _validation_group_key(
    record: ValidationGroupRecord | ValidationCheckRecord,
) -> tuple[str, str, str]:
    return (
        normalize_project_key_value(record.tenant_code),
        normalize_project_key_value(record.system_code),
        normalize_project_key_value(record.validation_group_name),
    )
