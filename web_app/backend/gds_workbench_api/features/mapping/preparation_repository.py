"""PostgreSQL Mapping Run plan and context repositories."""

from __future__ import annotations

from typing import LiteralString

from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import ValidationError

from gds_workbench_api.features.mapping.preparation_contracts import (
    CommonAgentPlanRepository,
    ExistingMappingHeader,
    MappingRunContext,
    MappingRunContextUnavailableError,
    MappingRunPlan,
    MappingRunPlanUnavailableError,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    PostgresAgentRunPlanRepository,
)

_MAPPING_RUN_PLAN_SQL: LiteralString = """
SELECT run.workflow_run_id,
       run.model_id,
       run.correlation_id,
       run.actor_principal_id,
       target_model.model_revision,
       run.modeled_entity_type,
       run.mapping_operation,
       run.mapping_coverage_mode,
       run.mapping_artifact_type,
       run.mapping_route,
       run.mapping_profile_key,
       run.mapping_profile_version,
       run.mapping_profile_schema_digest,
       run.mapping_object_output_template_id,
       run.mapping_object_output_template_schema_digest,
       run.mapping_attribute_output_template_id,
       run.mapping_attribute_output_template_schema_digest,
       selection.object_id AS target_object_id,
       selection.source_system_id,
       selection.selection_order
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
  JOIN application.workflow_run_mapping_target_selection AS selection
    ON selection.workflow_run_id = run.workflow_run_id
   AND selection.model_id = run.model_id
   AND selection.selection_order = 1
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND target_model.model_revision = %s
   AND run.actor_principal_id = %s
   AND run.model_workflow = 'mapping'
   AND run.workflow_run_state = 'running'
   AND run.selected_scope_count = 1
   AND run.mapping_coverage_mode = 'selected_targets'
   AND run.mapping_route = CASE run.modeled_entity_type
       WHEN 'logical_entity' THEN 'logical_to_silver'
       WHEN 'dimensional_entity' THEN 'dimensional_to_gold'
   END
   AND NOT EXISTS (
       SELECT 1
         FROM application.workflow_run_mapping_target_selection AS extra
        WHERE extra.workflow_run_id = run.workflow_run_id
          AND extra.workflow_run_mapping_target_selection_id <>
              selection.workflow_run_mapping_target_selection_id
   )
"""

_MAPPING_CONTEXT_ANCHOR_SQL: LiteralString = """
SELECT run.workflow_run_id,
       run.model_id,
       target_model.model_revision,
       run.correlation_id,
       run.actor_principal_id,
       selection.object_id AS target_object_id,
       selection.source_system_id,
       run.modeled_entity_type,
       run.mapping_route,
       run.mapping_operation,
       run.mapping_artifact_type,
       run.mapping_profile_key,
       run.mapping_profile_version,
       run.mapping_profile_schema_digest,
       run.mapping_object_output_template_id,
       run.mapping_object_output_template_schema_digest,
       run.mapping_attribute_output_template_id,
       run.mapping_attribute_output_template_schema_digest,
       jsonb_build_object(
           'system_id', source_system.system_id,
           'system_code', source_system.system_code,
           'system_name', source_system.system_name,
           'system_description', source_system.system_description,
           'is_active', source_system.is_active
       ) AS source_system,
       jsonb_build_object(
           'mapping_source_system_dependency_id',
               dependency.mapping_source_system_dependency_id,
           'dependency_order', dependency.source_system_dependency_order,
           'status', dependency.mapping_source_system_dependency_status,
           'is_locked', dependency.mapping_source_system_dependency_is_locked
       ) AS dependency,
       jsonb_build_object(
           'model_name', target_model.model_name,
           'naming_instructions', CASE run.modeled_entity_type
               WHEN 'logical_entity'
                   THEN target_model.silver_model_naming_instructions
               ELSE target_model.gold_model_naming_instructions
           END,
           'audit_columns_template', CASE run.modeled_entity_type
               WHEN 'logical_entity'
                   THEN target_model.silver_model_audit_columns_template
               ELSE target_model.gold_model_audit_columns_template
           END,
           'technical_columns_template', CASE run.modeled_entity_type
               WHEN 'logical_entity' THEN NULL
               ELSE target_model.gold_model_technical_columns_template
           END
       ) AS authoring
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
  JOIN application.workflow_run_mapping_target_selection AS selection
    ON selection.workflow_run_id = run.workflow_run_id
   AND selection.model_id = run.model_id
   AND selection.selection_order = 1
  JOIN workflow.mapping_source_system_dependency AS dependency
    ON dependency.model_id = run.model_id
   AND dependency.modeled_entity_type = run.modeled_entity_type
   AND dependency.source_system_id = selection.source_system_id
  JOIN core.system AS source_system
    ON source_system.system_id = dependency.source_system_id
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND target_model.model_revision = %s
   AND run.actor_principal_id = %s
   AND run.correlation_id = %s
   AND selection.object_id = %s
   AND selection.source_system_id = %s
   AND run.modeled_entity_type = %s
   AND run.mapping_route = %s
   AND run.mapping_operation = %s
   AND run.mapping_artifact_type = %s
   AND run.mapping_profile_key = %s
   AND run.mapping_profile_version = %s
   AND run.mapping_profile_schema_digest = %s
   AND run.mapping_object_output_template_id IS NOT DISTINCT FROM %s
   AND run.mapping_object_output_template_schema_digest IS NOT DISTINCT FROM %s
   AND run.mapping_attribute_output_template_id IS NOT DISTINCT FROM %s
   AND run.mapping_attribute_output_template_schema_digest IS NOT DISTINCT FROM %s
   AND run.model_workflow = 'mapping'
   AND run.workflow_run_state = 'running'
   AND run.selected_scope_count = 1
   AND run.mapping_coverage_mode = 'selected_targets'
   AND NOT EXISTS (
       SELECT 1
         FROM application.workflow_run_mapping_target_selection AS extra
        WHERE extra.workflow_run_id = run.workflow_run_id
          AND extra.workflow_run_mapping_target_selection_id <>
              selection.workflow_run_mapping_target_selection_id
   )
"""

_MAPPING_DEPENDENCY_GRAPH_SQL: LiteralString = """
WITH target_model AS MATERIALIZED (
    SELECT model_id
      FROM model.model
     WHERE tenant_id = %s
       AND model_id = %s
       AND model_revision = %s
       AND is_active
), dependency_node AS MATERIALIZED (
    SELECT dependency.mapping_source_system_dependency_id,
           dependency.source_system_id,
           dependency.source_system_dependency_order,
           dependency.mapping_source_system_dependency_status,
           dependency.mapping_source_system_dependency_is_locked
      FROM target_model
      JOIN workflow.mapping_source_system_dependency AS dependency
        ON dependency.model_id = target_model.model_id
     WHERE dependency.modeled_entity_type = %s
       AND dependency.mapping_source_system_dependency_status = 'active'
     ORDER BY dependency.source_system_id
     LIMIT 1001
), authored_package AS MATERIALIZED (
    SELECT DISTINCT mapping.source_system_id AS successor_source_system_id,
           mapping.mapping_package_document -> 'source_system_dependencies'
               AS dependency_references
      FROM target_model
      JOIN workflow.mapping_object AS mapping
        ON mapping.model_id = target_model.model_id
     WHERE mapping.modeled_entity_type = %s
       AND mapping.object_mapping_status = 'active'
       AND mapping.mapping_package_document IS NOT NULL
), reference_item AS MATERIALIZED (
    SELECT package.successor_source_system_id,
           reference.value,
           reference.value ->> 'predecessor_source_system_id'
               AS predecessor_text,
           jsonb_typeof(reference.value) = 'object'
           AND jsonb_typeof(
               reference.value -> 'predecessor_source_system_id'
           ) = 'number'
           AND (reference.value ->> 'predecessor_source_system_id')
               ~ '^[1-9][0-9]{0,18}$' AS has_numeric_shape
      FROM authored_package AS package
     CROSS JOIN LATERAL jsonb_array_elements(
           CASE
               WHEN jsonb_typeof(package.dependency_references) = 'array'
                   THEN package.dependency_references
               ELSE '[]'::JSONB
           END
       ) AS reference(value)
), checked_reference AS MATERIALIZED (
    SELECT successor_source_system_id,
           CASE
               WHEN has_numeric_shape THEN CASE
                   WHEN predecessor_text::NUMERIC <= 9223372036854775807
                       THEN predecessor_text::BIGINT
                   ELSE NULL
               END
               ELSE NULL
           END AS predecessor_source_system_id,
           NOT CASE
               WHEN has_numeric_shape
                   THEN predecessor_text::NUMERIC <= 9223372036854775807
               ELSE FALSE
           END AS is_malformed
      FROM reference_item
), graph_edge AS MATERIALIZED (
    SELECT DISTINCT successor_source_system_id,
                    predecessor_source_system_id
      FROM checked_reference
     WHERE NOT is_malformed
     ORDER BY successor_source_system_id,
              predecessor_source_system_id
     LIMIT 10001
), malformed_reference AS (
    SELECT count(*)::INTEGER AS item_count
      FROM checked_reference
     WHERE is_malformed
     UNION ALL
    SELECT count(*)::INTEGER
      FROM authored_package
     WHERE jsonb_typeof(dependency_references) IS DISTINCT FROM 'array'
)
SELECT jsonb_build_object(
           'nodes', coalesce(
               (
                   SELECT jsonb_agg(
                              jsonb_build_object(
                                  'mapping_source_system_dependency_id',
                                      node.mapping_source_system_dependency_id,
                                  'source_system_id', node.source_system_id,
                                  'dependency_order',
                                      node.source_system_dependency_order,
                                  'status',
                                      node.mapping_source_system_dependency_status,
                                  'is_locked',
                                      node.mapping_source_system_dependency_is_locked
                              ) ORDER BY node.source_system_id
                          )
                     FROM dependency_node AS node
               ),
               '[]'::JSONB
           ),
           'edges', coalesce(
               (
                   SELECT jsonb_agg(
                              jsonb_build_object(
                                  'predecessor_source_system_id',
                                      edge.predecessor_source_system_id,
                                  'successor_source_system_id',
                                      edge.successor_source_system_id
                              ) ORDER BY edge.successor_source_system_id,
                                         edge.predecessor_source_system_id
                          )
                     FROM graph_edge AS edge
               ),
               '[]'::JSONB
           ),
           'malformed_reference_count', least(
               coalesce((SELECT sum(item_count) FROM malformed_reference), 0),
               10001
           )
       ) AS dependency_graph
"""

_MAPPING_TARGET_DEPENDENCY_GRAPH_SQL: LiteralString = """
WITH target_model AS MATERIALIZED (
    SELECT model_id
      FROM model.model
     WHERE tenant_id = %s
       AND model_id = %s
       AND model_revision = %s
       AND is_active
), target_summary AS MATERIALIZED (
    SELECT mapping.object_id AS target_object_id,
           min(mapping.object_dependency_order) AS dependency_order,
           count(DISTINCT mapping.object_dependency_order) AS order_count,
           bool_or(mapping.object_mapping_is_locked) AS has_locked_headers,
           bool_or(NOT mapping.object_mapping_is_locked) AS has_unlocked_headers
      FROM target_model
      JOIN workflow.mapping_object AS mapping
        ON mapping.model_id = target_model.model_id
     WHERE mapping.modeled_entity_type = %s
       AND mapping.object_mapping_status = 'active'
     GROUP BY mapping.object_id
), target_node AS MATERIALIZED (
    SELECT *
      FROM target_summary
     ORDER BY target_object_id
     LIMIT 1001
), authored_package AS MATERIALIZED (
    SELECT DISTINCT mapping.object_id AS successor_target_object_id,
           mapping.mapping_package_document -> 'target_dependencies'
               AS dependency_references
      FROM target_model
      JOIN workflow.mapping_object AS mapping
        ON mapping.model_id = target_model.model_id
     WHERE mapping.modeled_entity_type = %s
       AND mapping.object_mapping_status = 'active'
       AND mapping.mapping_package_document IS NOT NULL
), reference_item AS MATERIALIZED (
    SELECT package.successor_target_object_id,
           reference.value ->> 'predecessor_target_object_id'
               AS predecessor_text,
           jsonb_typeof(reference.value) = 'object'
           AND jsonb_typeof(
               reference.value -> 'predecessor_target_object_id'
           ) = 'number'
           AND (reference.value ->> 'predecessor_target_object_id')
               ~ '^[1-9][0-9]{0,18}$' AS has_numeric_shape
      FROM authored_package AS package
     CROSS JOIN LATERAL jsonb_array_elements(
           CASE
               WHEN jsonb_typeof(package.dependency_references) = 'array'
                   THEN package.dependency_references
               ELSE '[]'::JSONB
           END
       ) AS reference(value)
), checked_reference AS MATERIALIZED (
    SELECT successor_target_object_id,
           CASE
               WHEN has_numeric_shape THEN CASE
                   WHEN predecessor_text::NUMERIC <= 9223372036854775807
                       THEN predecessor_text::BIGINT
                   ELSE NULL
               END
               ELSE NULL
           END AS predecessor_target_object_id,
           NOT CASE
               WHEN has_numeric_shape
                   THEN predecessor_text::NUMERIC <= 9223372036854775807
               ELSE FALSE
           END AS is_malformed
      FROM reference_item
), graph_edge AS MATERIALIZED (
    SELECT DISTINCT successor_target_object_id,
                    predecessor_target_object_id
      FROM checked_reference
     WHERE NOT is_malformed
     ORDER BY successor_target_object_id,
              predecessor_target_object_id
     LIMIT 10001
), malformed_reference AS (
    SELECT count(*)::INTEGER AS item_count
      FROM checked_reference
     WHERE is_malformed
     UNION ALL
    SELECT count(*)::INTEGER
      FROM authored_package
     WHERE jsonb_typeof(dependency_references) IS DISTINCT FROM 'array'
)
SELECT jsonb_build_object(
           'nodes', coalesce(
               (
                   SELECT jsonb_agg(
                              jsonb_build_object(
                                  'target_object_id', node.target_object_id,
                                  'dependency_order', node.dependency_order,
                                  'status', 'active',
                                  'has_locked_headers',
                                      node.has_locked_headers,
                                  'has_unlocked_headers',
                                      node.has_unlocked_headers
                              ) ORDER BY node.target_object_id
                          )
                     FROM target_node AS node
               ),
               '[]'::JSONB
           ),
           'edges', coalesce(
               (
                   SELECT jsonb_agg(
                              jsonb_build_object(
                                  'predecessor_target_object_id',
                                      edge.predecessor_target_object_id,
                                  'successor_target_object_id',
                                      edge.successor_target_object_id
                              ) ORDER BY edge.successor_target_object_id,
                                         edge.predecessor_target_object_id
                          )
                     FROM graph_edge AS edge
               ),
               '[]'::JSONB
           ),
           'malformed_reference_count', least(
               coalesce((SELECT sum(item_count) FROM malformed_reference), 0),
               10001
           ),
           'mixed_order_target_count', least(
               (SELECT count(*) FROM target_summary WHERE order_count > 1),
               1001
           )
       ) AS target_dependency_graph
"""

_MAPPING_TARGET_CONTEXT_SQL: LiteralString = """
SELECT jsonb_build_object(
           'object_id', target_object.object_id,
           'tenant_id', object_tenant.tenant_id,
           'tenant_code', object_tenant.tenant_code,
           'tenant_catalog', object_tenant.tenant_catalog,
           'tenant_is_active', object_tenant.is_active,
           'system_id', target_system.system_id,
           'system_code', target_system.system_code,
           'system_is_active', target_system.is_active,
           'connection_id', target_connection.connection_id,
           'connection_code', target_connection.connection_code,
           'connection_is_active', target_connection.is_active,
           'is_global_data_store', target_connection.is_global_data_store,
           'object_schema', target_object.object_schema,
           'object_name', target_object.object_name,
           'object_description', target_object.object_description,
           'batch_attribute_name', target_object.batch_attribute_name,
           'zone_code', lower(btrim(target_zone.zone_code)),
           'scope_is_locked', target_scope.model_scope_is_locked,
           'scope_is_active', target_scope.is_active,
           'is_locked', target_object.is_locked,
           'is_active', target_object.is_active,
           'attributes', attribute_document.items
       ) AS target
  FROM model.model AS target_model
  JOIN model.model_scope AS target_scope
    ON target_scope.model_id = target_model.model_id
  JOIN core.object AS target_object
    ON target_object.object_id = target_scope.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS object_tenant
    ON object_tenant.tenant_id = CASE
           WHEN target_connection.is_global_data_store
               THEN target_model.tenant_id
           ELSE target_connection.tenant_id
       END
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN reference.zone AS target_zone
    ON target_zone.zone_id = target_object.zone_id
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(attribute_item.document
                            ORDER BY attribute_item.ordinal_position),
                  '[]'::JSONB
              ) AS items
         FROM (
             SELECT attribute.attribute_ordinal_position AS ordinal_position,
                    jsonb_build_object(
                        'attribute_id', attribute.attribute_id,
                        'attribute_name', attribute.attribute_name,
                        'attribute_data_type', attribute.attribute_data_type,
                        'attribute_nullability', attribute.attribute_nullability,
                        'attribute_ordinal_position',
                            attribute.attribute_ordinal_position,
                        'attribute_description', attribute.attribute_description,
                        'is_active', attribute.is_active
                    ) AS document
               FROM core.attribute AS attribute
              WHERE attribute.object_id = target_object.object_id
              ORDER BY attribute.attribute_ordinal_position,
                       attribute.attribute_id
              LIMIT 5001
         ) AS attribute_item
  ) AS attribute_document
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.model_revision = %s
   AND target_model.is_active
   AND target_object.object_id = %s
"""

_MAPPING_HEADER_CONTEXT_SQL: LiteralString = """
WITH package_header AS MATERIALIZED (
    SELECT mapping.*
      FROM model.model AS target_model
      JOIN workflow.mapping_object AS mapping
        ON mapping.model_id = target_model.model_id
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.model_revision = %s
       AND target_model.is_active
       AND mapping.object_id = %s
       AND mapping.source_system_id = %s
       AND mapping.modeled_entity_type = %s
     ORDER BY mapping.mapping_object_id
     LIMIT 65
)
SELECT jsonb_build_object(
           'mapping_object_id', header.mapping_object_id,
           'modeled_entity', jsonb_build_object(
               'entity_id', CASE header.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_id
                   ELSE dimensional_entity.dimensional_entity_id
               END,
               'entity_name', CASE header.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_name
                   ELSE dimensional_entity.dimensional_entity_name
               END,
               'entity_definition', CASE header.modeled_entity_type
                   WHEN 'logical_entity'
                       THEN logical_entity.logical_entity_definition
                   ELSE dimensional_entity.dimensional_entity_definition
               END,
               'entity_kind', CASE header.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_type
                   ELSE dimensional_entity.dimensional_entity_type
               END,
               'grain', CASE header.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_grain
                   ELSE dimensional_entity.dimensional_entity_grain_definition
               END,
               'dependency_order', CASE header.modeled_entity_type
                   WHEN 'logical_entity'
                       THEN logical_entity.logical_entity_dependency_order
                   ELSE dimensional_entity.dimensional_entity_dependency_order
               END,
               'status', CASE header.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_status
                   ELSE dimensional_entity.dimensional_entity_status
               END,
               'is_locked', CASE header.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_is_locked
                   ELSE dimensional_entity.dimensional_entity_is_locked
               END,
               'attributes', modeled_attribute_document.items
           ),
           'object_dependency_order', header.object_dependency_order,
           'artifact_type', header.artifact_type,
           'artifact_generation_instructions',
               header.artifact_generation_instructions,
           'profile', CASE
               WHEN header.mapping_profile_key IS NULL THEN NULL
               ELSE jsonb_build_object(
                   'key', header.mapping_profile_key,
                   'version', header.mapping_profile_version,
                   'schema_digest', header.mapping_profile_schema_digest
               )
           END,
           'mapping_package_document', header.mapping_package_document,
           'mapping_package_digest', header.mapping_package_digest,
           'transformation_document',
               header.object_mapping_transformation_document,
           'status', header.object_mapping_status,
           'is_locked', header.object_mapping_is_locked,
           'agent_run_id', header.agent_run_id,
           'workflow_run_id', header.workflow_run_id,
           'output_template_id', header.output_template_id,
           'attribute_mappings', mapping_attribute_document.items
       ) AS header
  FROM package_header AS header
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON header.modeled_entity_type = 'logical_entity'
   AND logical_entity.model_id = header.model_id
   AND logical_entity.logical_entity_id = header.logical_entity_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON header.modeled_entity_type = 'dimensional_entity'
   AND dimensional_entity.model_id = header.model_id
   AND dimensional_entity.dimensional_entity_id = header.dimensional_entity_id
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(item.document ORDER BY item.ordinal_position),
                  '[]'::JSONB
              ) AS items
         FROM (
             SELECT logical_attribute.logical_attribute_ordinal_position
                        AS ordinal_position,
                    jsonb_build_object(
                        'attribute_id', logical_attribute.logical_attribute_id,
                        'attribute_name', logical_attribute.logical_attribute_name,
                        'attribute_definition',
                            logical_attribute.logical_attribute_definition,
                        'attribute_data_type',
                            logical_attribute.logical_attribute_data_type,
                        'is_nullable',
                            logical_attribute.logical_attribute_is_nullable,
                        'ordinal_position',
                            logical_attribute.logical_attribute_ordinal_position,
                        'is_audit_column',
                            logical_attribute.logical_attribute_is_audit_column,
                        'status', logical_attribute.logical_attribute_status,
                        'is_locked',
                            logical_attribute.logical_attribute_is_locked
                    ) AS document
               FROM workflow.logical_attribute AS logical_attribute
              WHERE header.modeled_entity_type = 'logical_entity'
                AND logical_attribute.model_id = header.model_id
                AND logical_attribute.logical_entity_id =
                    header.logical_entity_id
             UNION ALL
             SELECT dimensional_attribute.dimensional_attribute_ordinal_position,
                    jsonb_build_object(
                        'attribute_id',
                            dimensional_attribute.dimensional_attribute_id,
                        'attribute_name',
                            dimensional_attribute.dimensional_attribute_name,
                        'attribute_definition',
                            dimensional_attribute.dimensional_attribute_definition,
                        'attribute_data_type',
                            dimensional_attribute.dimensional_attribute_data_type,
                        'is_nullable',
                            dimensional_attribute.dimensional_attribute_is_nullable,
                        'ordinal_position',
                            dimensional_attribute.dimensional_attribute_ordinal_position,
                        'is_audit_column',
                            dimensional_attribute.dimensional_attribute_is_audit_column,
                        'status',
                            dimensional_attribute.dimensional_attribute_status,
                        'is_locked',
                            dimensional_attribute.dimensional_attribute_is_locked
                    ) AS document
               FROM workflow.dimensional_attribute AS dimensional_attribute
              WHERE header.modeled_entity_type = 'dimensional_entity'
                AND dimensional_attribute.model_id = header.model_id
                AND dimensional_attribute.dimensional_entity_id =
                    header.dimensional_entity_id
              ORDER BY ordinal_position
              LIMIT 5001
         ) AS item
  ) AS modeled_attribute_document
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(item.document ORDER BY item.mapping_attribute_id),
                  '[]'::JSONB
              ) AS items
         FROM (
             SELECT mapping_attribute.mapping_attribute_id,
                    jsonb_build_object(
                        'mapping_attribute_id',
                            mapping_attribute.mapping_attribute_id,
                        'modeled_attribute_id', CASE header.modeled_entity_type
                            WHEN 'logical_entity'
                                THEN mapping_attribute.logical_attribute_id
                            ELSE mapping_attribute.dimensional_attribute_id
                        END,
                        'target_attribute_id', mapping_attribute.attribute_id,
                        'transformation_document',
                            mapping_attribute.attribute_mapping_transformation_document,
                        'status', mapping_attribute.attribute_mapping_status,
                        'is_locked',
                            mapping_attribute.attribute_mapping_is_locked,
                        'agent_run_id', mapping_attribute.agent_run_id,
                        'workflow_run_id', mapping_attribute.workflow_run_id,
                        'output_template_id', mapping_attribute.output_template_id
                    ) AS document
               FROM workflow.mapping_attribute AS mapping_attribute
              WHERE mapping_attribute.model_id = header.model_id
                AND mapping_attribute.mapping_object_id =
                    header.mapping_object_id
                AND mapping_attribute.modeled_entity_type =
                    header.modeled_entity_type
                AND mapping_attribute.object_id = header.object_id
              ORDER BY mapping_attribute.mapping_attribute_id
              LIMIT 20001
         ) AS item
  ) AS mapping_attribute_document
 ORDER BY header.mapping_object_id
"""

_MAPPING_SOURCE_CONTEXT_SQL: LiteralString = """
WITH package_header AS MATERIALIZED (
    SELECT mapping.*
      FROM model.model AS target_model
      JOIN workflow.mapping_object AS mapping
        ON mapping.model_id = target_model.model_id
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.model_revision = %s
       AND target_model.is_active
       AND mapping.object_id = %s
       AND mapping.source_system_id = %s
       AND mapping.modeled_entity_type = %s
), source_binding AS MATERIALIZED (
    SELECT source.logical_entity_source_mapping_id AS source_mapping_id,
           header.logical_entity_id AS modeled_entity_id,
           'support'::TEXT AS role,
           source.logical_entity_source_mapping_rationale AS rationale,
           source.logical_entity_source_mapping_order AS mapping_order,
           source.logical_entity_source_mapping_is_locked AS is_locked,
           source.source_object_id,
           header.modeled_entity_type,
           header.source_system_id
      FROM package_header AS header
      JOIN workflow.logical_entity_source_mapping AS source
        ON header.modeled_entity_type = 'logical_entity'
       AND source.model_id = header.model_id
       AND source.logical_entity_id = header.logical_entity_id
       AND source.support_source_type = 'object'
       AND source.logical_entity_source_mapping_status = 'active'
     UNION ALL
    SELECT source.dimensional_entity_source_mapping_id,
           header.dimensional_entity_id,
           source.dimensional_entity_source_role,
           source.dimensional_entity_source_mapping_rationale,
           source.dimensional_entity_source_mapping_order,
           source.dimensional_entity_source_mapping_is_locked,
           source.source_object_id,
           header.modeled_entity_type,
           header.source_system_id
      FROM package_header AS header
      JOIN workflow.dimensional_entity_source_mapping AS source
        ON header.modeled_entity_type = 'dimensional_entity'
       AND source.model_id = header.model_id
       AND source.dimensional_entity_id = header.dimensional_entity_id
       AND source.support_source_type = 'object'
       AND source.dimensional_entity_source_mapping_status = 'active'
)
SELECT jsonb_build_object(
           'source_mapping_id', binding.source_mapping_id,
           'modeled_entity_id', binding.modeled_entity_id,
           'role', binding.role,
           'rationale', binding.rationale,
           'mapping_order', binding.mapping_order,
           'is_locked', binding.is_locked,
           'object', jsonb_build_object(
               'object_id', source_object.object_id,
               'tenant_id', object_tenant.tenant_id,
               'tenant_code', object_tenant.tenant_code,
               'tenant_catalog', object_tenant.tenant_catalog,
               'tenant_is_active', object_tenant.is_active,
               'system_id', source_system.system_id,
               'system_code', source_system.system_code,
               'system_is_active', source_system.is_active,
               'connection_id', source_connection.connection_id,
               'connection_code', source_connection.connection_code,
               'connection_is_active', source_connection.is_active,
               'is_global_data_store',
                   source_connection.is_global_data_store,
               'object_schema', source_object.object_schema,
               'object_name', source_object.object_name,
               'object_description', source_object.object_description,
               'batch_attribute_name', source_object.batch_attribute_name,
               'zone_code', lower(btrim(source_zone.zone_code)),
               'scope_is_locked', source_scope.model_scope_is_locked,
               'scope_is_active', source_scope.is_active,
               'is_locked', source_object.is_locked,
               'is_active', source_object.is_active,
               'attributes', attribute_document.items
           )
       ) AS source
  FROM source_binding AS binding
  JOIN model.model AS target_model
    ON target_model.model_id = %s
   AND target_model.tenant_id = %s
   AND target_model.model_revision = %s
   AND target_model.is_active
  JOIN model.model_scope AS source_scope
    ON source_scope.model_id = target_model.model_id
   AND source_scope.object_id = binding.source_object_id
   AND source_scope.is_active
  JOIN core.object AS source_object
    ON source_object.object_id = binding.source_object_id
   AND source_object.is_active
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
   AND source_connection.is_active
  JOIN core.tenant AS object_tenant
    ON object_tenant.tenant_id = CASE
           WHEN source_connection.is_global_data_store
               THEN target_model.tenant_id
           ELSE source_connection.tenant_id
       END
   AND object_tenant.is_active
  JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
   AND source_system.is_active
  JOIN reference.zone AS source_zone
    ON source_zone.zone_id = source_object.zone_id
   AND source_zone.is_active
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(attribute_item.document
                            ORDER BY attribute_item.ordinal_position),
                  '[]'::JSONB
              ) AS items
         FROM (
             SELECT attribute.attribute_ordinal_position AS ordinal_position,
                    jsonb_build_object(
                        'attribute_id', attribute.attribute_id,
                        'attribute_name', attribute.attribute_name,
                        'attribute_data_type', attribute.attribute_data_type,
                        'attribute_nullability', attribute.attribute_nullability,
                        'attribute_ordinal_position',
                            attribute.attribute_ordinal_position,
                        'attribute_description', attribute.attribute_description,
                        'is_active', attribute.is_active
                    ) AS document
               FROM core.attribute AS attribute
              WHERE attribute.object_id = source_object.object_id
                AND attribute.is_active
              ORDER BY attribute.attribute_ordinal_position,
                       attribute.attribute_id
              LIMIT 5001
         ) AS attribute_item
  ) AS attribute_document
 WHERE (
       binding.modeled_entity_type = 'logical_entity'
       AND lower(btrim(source_zone.zone_code)) = 'bronze'
       AND (
           source_connection.system_id = binding.source_system_id
           OR EXISTS (
               SELECT 1
                 FROM core.ingestion_object_mapping AS ingestion
                 JOIN core.object AS original_object
                   ON original_object.object_id = ingestion.source_object_id
                  AND original_object.is_active
                 JOIN core.connection AS original_connection
                   ON original_connection.connection_id =
                      original_object.connection_id
                  AND original_connection.is_active
                WHERE ingestion.target_object_id = source_object.object_id
                  AND ingestion.is_active
                  AND original_connection.system_id =
                      binding.source_system_id
           )
       )
   ) OR (
       binding.modeled_entity_type = 'dimensional_entity'
       AND lower(btrim(source_zone.zone_code)) = 'silver'
       AND EXISTS (
           SELECT 1
             FROM workflow.mapping_object AS prior_mapping
             JOIN workflow.mapping_source_system_dependency AS prior_dependency
               ON prior_dependency.model_id = prior_mapping.model_id
              AND prior_dependency.modeled_entity_type =
                  prior_mapping.modeled_entity_type
              AND prior_dependency.source_system_id =
                  prior_mapping.source_system_id
              AND prior_dependency.mapping_source_system_dependency_status =
                  'active'
            WHERE prior_mapping.model_id = target_model.model_id
              AND prior_mapping.modeled_entity_type = 'logical_entity'
              AND prior_mapping.object_id = source_object.object_id
              AND prior_mapping.source_system_id = binding.source_system_id
              AND prior_mapping.object_mapping_status = 'active'
              AND prior_mapping.mapping_package_document IS NOT NULL
              AND prior_mapping.object_mapping_transformation_document IS NOT NULL
       )
   )
 ORDER BY binding.source_mapping_id
 LIMIT 129
"""

_MAPPING_OUTPUT_TEMPLATE_CONTEXT_SQL: LiteralString = """
SELECT jsonb_build_object(
           'output_template_id', template.output_template_id,
           'code', template.output_template_code,
           'name', template.output_template_name,
           'description', template.output_template_description,
           'target_type', template.output_template_target_type,
           'schema_digest', template.output_template_schema_digest,
           'schema_digest_is_valid',
               template.output_template_schema_digest = encode(
                   sha256(
                       convert_to(
                           jsonb_build_object(
                               'output_template_target_type',
                                   template.output_template_target_type,
                               'fields', field_document.digest_items
                           )::TEXT,
                           'UTF8'
                       )
                   ),
                   'hex'
               ),
           'is_active', template.is_active,
           'fields', field_document.items
       ) AS output_template
  FROM application.output_template AS template
 CROSS JOIN LATERAL (
       SELECT count(*) AS item_count,
              jsonb_agg(
                  jsonb_build_object(
                      'name', item.output_template_field_name,
                      'description', item.output_template_field_description,
                      'data_type', item.output_template_field_data_type,
                      'array_item_type',
                          item.output_template_field_array_item_type,
                      'example', item.output_template_field_example,
                      'is_required', item.output_template_field_is_required,
                      'order', item.output_template_field_order
                  ) ORDER BY item.output_template_field_order
              ) AS items,
              jsonb_agg(
                  jsonb_build_object(
                      'output_template_field_name',
                          item.output_template_field_name,
                      'output_template_field_description',
                          item.output_template_field_description,
                      'output_template_field_data_type',
                          item.output_template_field_data_type,
                      'output_template_field_array_item_type',
                          item.output_template_field_array_item_type,
                      'output_template_field_example', coalesce(
                          item.output_template_field_example,
                          'null'::JSONB
                      ),
                      'output_template_field_is_required',
                          item.output_template_field_is_required,
                      'output_template_field_order',
                          item.output_template_field_order
                  ) ORDER BY item.output_template_field_order
              ) AS digest_items
         FROM (
             SELECT field.output_template_field_name,
                    field.output_template_field_description,
                    field.output_template_field_data_type,
                    field.output_template_field_array_item_type,
                    field.output_template_field_example,
                    field.output_template_field_is_required,
                    field.output_template_field_order
               FROM application.output_template_field AS field
              WHERE field.output_template_id = template.output_template_id
              ORDER BY field.output_template_field_order
              LIMIT 501
         ) AS item
  ) AS field_document
 WHERE template.output_template_id = ANY(%s::BIGINT[])
   AND field_document.item_count BETWEEN 1 AND 500
 ORDER BY template.output_template_id
 LIMIT 20067
"""


class PostgresMappingRunPlanRepository:
    """Load Mapping-only request fields after the common prompt plan."""

    def __init__(
        self,
        *,
        agent_plan_repository: CommonAgentPlanRepository | None = None,
    ) -> None:
        self._agent_plan_repository = agent_plan_repository or PostgresAgentRunPlanRepository()

    async def load(
        self,
        transaction: ReadTransaction,
        *,
        actor_principal_id: int,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> MappingRunPlan:
        row = await transaction.fetch_one(
            _MAPPING_RUN_PLAN_SQL,
            (
                tenant_id,
                model_id,
                workflow_run_id,
                expected_model_revision,
                actor_principal_id,
            ),
        )
        if row is None:
            raise MappingRunPlanUnavailableError()
        common = await self._agent_plan_repository.load(
            transaction,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
        )
        try:
            if (
                row.get("workflow_run_id") != common.workflow_run_id
                or row.get("model_id") != common.model_id
                or row.get("correlation_id") != common.correlation_id
                or row.get("actor_principal_id") != actor_principal_id
                or row.get("model_revision") != common.model_revision
                or common.model_revision != expected_model_revision
                or row.get("modeled_entity_type") != common.modeled_entity_type
                or row.get("selection_order") != 1
            ):
                raise MappingRunPlanUnavailableError()
            return MappingRunPlan.model_validate(
                {
                    "agent_plan": common,
                    "actor_principal_id": row.get("actor_principal_id"),
                    "pair": {
                        "target_object_id": row.get("target_object_id"),
                        "source_system_id": row.get("source_system_id"),
                    },
                    "operation": row.get("mapping_operation"),
                    "coverage_mode": row.get("mapping_coverage_mode"),
                    "artifact_type": row.get("mapping_artifact_type"),
                    "route": row.get("mapping_route"),
                    "profile": {
                        "key": row.get("mapping_profile_key"),
                        "version": row.get("mapping_profile_version"),
                        "schema_digest": row.get("mapping_profile_schema_digest"),
                    },
                    "output_template_selections": {
                        "mapping_object": (
                            None
                            if row.get("mapping_object_output_template_id") is None
                            else {
                                "output_template_id": row.get("mapping_object_output_template_id"),
                                "schema_digest": row.get(
                                    "mapping_object_output_template_schema_digest"
                                ),
                            }
                        ),
                        "mapping_attribute": (
                            None
                            if row.get("mapping_attribute_output_template_id") is None
                            else {
                                "output_template_id": row.get(
                                    "mapping_attribute_output_template_id"
                                ),
                                "schema_digest": row.get(
                                    "mapping_attribute_output_template_schema_digest"
                                ),
                            }
                        ),
                    },
                }
            )
        except MappingRunPlanUnavailableError:
            raise
        except (TypeError, ValueError, ValidationError):
            raise MappingRunPlanUnavailableError() from None


class PostgresMappingRunContextRepository:
    """Load one bounded Mapping package from a repeatable-read snapshot."""

    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: MappingRunPlan,
    ) -> MappingRunContext:
        anchor = await transaction.fetch_one(
            _MAPPING_CONTEXT_ANCHOR_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.workflow_run_id,
                plan.model_revision,
                plan.actor_principal_id,
                plan.correlation_id,
                plan.pair.target_object_id,
                plan.pair.source_system_id,
                plan.modeled_entity_type,
                plan.route,
                plan.operation,
                plan.artifact_type,
                plan.profile.key,
                plan.profile.version,
                plan.profile.schema_digest,
                (
                    plan.output_template_selections.mapping_object.output_template_id
                    if plan.output_template_selections.mapping_object is not None
                    else None
                ),
                (
                    plan.output_template_selections.mapping_object.schema_digest
                    if plan.output_template_selections.mapping_object is not None
                    else None
                ),
                (
                    plan.output_template_selections.mapping_attribute.output_template_id
                    if plan.output_template_selections.mapping_attribute is not None
                    else None
                ),
                (
                    plan.output_template_selections.mapping_attribute.schema_digest
                    if plan.output_template_selections.mapping_attribute is not None
                    else None
                ),
            ),
        )
        if anchor is None or (
            anchor.get("workflow_run_id"),
            anchor.get("model_id"),
            anchor.get("model_revision"),
            anchor.get("correlation_id"),
            anchor.get("actor_principal_id"),
            anchor.get("target_object_id"),
            anchor.get("source_system_id"),
            anchor.get("modeled_entity_type"),
            anchor.get("mapping_route"),
            anchor.get("mapping_operation"),
            anchor.get("mapping_artifact_type"),
            anchor.get("mapping_profile_key"),
            anchor.get("mapping_profile_version"),
            anchor.get("mapping_profile_schema_digest"),
            anchor.get("mapping_object_output_template_id"),
            anchor.get("mapping_object_output_template_schema_digest"),
            anchor.get("mapping_attribute_output_template_id"),
            anchor.get("mapping_attribute_output_template_schema_digest"),
        ) != (
            plan.workflow_run_id,
            plan.model_id,
            plan.model_revision,
            plan.correlation_id,
            plan.actor_principal_id,
            plan.pair.target_object_id,
            plan.pair.source_system_id,
            plan.modeled_entity_type,
            plan.route,
            plan.operation,
            plan.artifact_type,
            plan.profile.key,
            plan.profile.version,
            plan.profile.schema_digest,
            (
                plan.output_template_selections.mapping_object.output_template_id
                if plan.output_template_selections.mapping_object is not None
                else None
            ),
            (
                plan.output_template_selections.mapping_object.schema_digest
                if plan.output_template_selections.mapping_object is not None
                else None
            ),
            (
                plan.output_template_selections.mapping_attribute.output_template_id
                if plan.output_template_selections.mapping_attribute is not None
                else None
            ),
            (
                plan.output_template_selections.mapping_attribute.schema_digest
                if plan.output_template_selections.mapping_attribute is not None
                else None
            ),
        ):
            raise MappingRunContextUnavailableError()

        graph_row = await transaction.fetch_one(
            _MAPPING_DEPENDENCY_GRAPH_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.model_revision,
                plan.modeled_entity_type,
                plan.modeled_entity_type,
            ),
        )
        if graph_row is None:
            raise MappingRunContextUnavailableError()
        target_graph_row = await transaction.fetch_one(
            _MAPPING_TARGET_DEPENDENCY_GRAPH_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.model_revision,
                plan.modeled_entity_type,
                plan.modeled_entity_type,
            ),
        )
        if target_graph_row is None:
            raise MappingRunContextUnavailableError()
        target_row = await transaction.fetch_one(
            _MAPPING_TARGET_CONTEXT_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.model_revision,
                plan.pair.target_object_id,
            ),
        )
        if target_row is None:
            raise MappingRunContextUnavailableError()
        header_rows = await transaction.fetch_all(
            _MAPPING_HEADER_CONTEXT_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.model_revision,
                plan.pair.target_object_id,
                plan.pair.source_system_id,
                plan.modeled_entity_type,
            ),
        )
        source_rows = await transaction.fetch_all(
            _MAPPING_SOURCE_CONTEXT_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.model_revision,
                plan.pair.target_object_id,
                plan.pair.source_system_id,
                plan.modeled_entity_type,
                plan.model_id,
                tenant_id,
                plan.model_revision,
            ),
        )
        try:
            headers = tuple(
                ExistingMappingHeader.model_validate(
                    row.get("header"),
                    strict=False,
                )
                for row in header_rows
            )
            referenced_template_ids = {
                template_id
                for header in headers
                for template_id in (
                    header.output_template_id,
                    *(child.output_template_id for child in header.attribute_mappings),
                )
                if template_id is not None
            }
            referenced_template_ids.update(
                selection.output_template_id
                for selection in (
                    plan.output_template_selections.mapping_object,
                    plan.output_template_selections.mapping_attribute,
                )
                if selection is not None
            )
            template_rows = (
                await transaction.fetch_all(
                    _MAPPING_OUTPUT_TEMPLATE_CONTEXT_SQL,
                    (sorted(referenced_template_ids),),
                )
                if referenced_template_ids
                else []
            )
            context = MappingRunContext.model_validate(
                {
                    "workflow_run_id": anchor.get("workflow_run_id"),
                    "model_id": anchor.get("model_id"),
                    "model_revision": anchor.get("model_revision"),
                    "correlation_id": anchor.get("correlation_id"),
                    "pair": {
                        "target_object_id": anchor.get("target_object_id"),
                        "source_system_id": anchor.get("source_system_id"),
                    },
                    "modeled_entity_type": anchor.get("modeled_entity_type"),
                    "route": anchor.get("mapping_route"),
                    "output_template_selections": (plan.output_template_selections),
                    "source_system": anchor.get("source_system"),
                    "dependency": anchor.get("dependency"),
                    "dependency_graph": graph_row.get("dependency_graph"),
                    "target_dependency_graph": target_graph_row.get("target_dependency_graph"),
                    "output_templates": {
                        "ids": sorted(referenced_template_ids),
                        "definitions": [row.get("output_template") for row in template_rows],
                    },
                    "target": target_row.get("target"),
                    "sources": [row.get("source") for row in source_rows],
                    "headers": headers,
                    "authoring": anchor.get("authoring"),
                },
                strict=False,
            )
            if context.target.tenant_id != tenant_id or any(
                source.object.tenant_id != tenant_id for source in context.sources
            ):
                raise MappingRunContextUnavailableError()
            return context
        except MappingRunContextUnavailableError:
            raise
        except (TypeError, ValueError, ValidationError):
            raise MappingRunContextUnavailableError() from None
