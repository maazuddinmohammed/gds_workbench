"""PostgreSQL Mapping Run plan and compact binding context repositories."""

from __future__ import annotations

from typing import LiteralString

from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import ValidationError

from gds_workbench_api.features.workflows.authoring.plan import PostgresAgentRunPlanRepository

from .preparation_contracts import (
    CommonAgentPlanRepository,
    ExistingMappingHeader,
    MappingRunContext,
    MappingRunContextUnavailableError,
    MappingRunPlan,
    MappingRunPlanUnavailableError,
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
       run.mapping_route,
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
               WHEN 'logical_entity' THEN target_model.silver_model_naming_instructions
               ELSE target_model.gold_model_naming_instructions
           END,
           'audit_columns_template', CASE run.modeled_entity_type
               WHEN 'logical_entity' THEN target_model.silver_model_audit_columns_template
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
   AND target_model.model_revision = %s
   AND target_model.is_active
  JOIN application.workflow_run_mapping_target_selection AS selection
    ON selection.workflow_run_id = run.workflow_run_id
   AND selection.model_id = run.model_id
   AND selection.selection_order = 1
  JOIN core.system AS source_system
    ON source_system.system_id = selection.source_system_id
  JOIN workflow.mapping_source_system_dependency AS dependency
    ON dependency.model_id = run.model_id
   AND dependency.modeled_entity_type = run.modeled_entity_type
   AND dependency.source_system_id = selection.source_system_id
 WHERE run.workflow_run_id = %s
   AND run.model_id = %s
   AND run.actor_principal_id = %s
   AND run.correlation_id = %s
   AND selection.object_id = %s
   AND selection.source_system_id = %s
   AND run.modeled_entity_type = %s
   AND run.mapping_route = %s
   AND run.mapping_operation = %s
   AND run.model_workflow = 'mapping'
   AND run.workflow_run_state = 'running'
"""

_MAPPING_DEPENDENCY_NODES_SQL: LiteralString = """
SELECT jsonb_build_object(
           'mapping_source_system_dependency_id',
               dependency.mapping_source_system_dependency_id,
           'source_system_id', dependency.source_system_id,
           'dependency_order', dependency.source_system_dependency_order,
           'status', dependency.mapping_source_system_dependency_status,
           'is_locked', dependency.mapping_source_system_dependency_is_locked
       ) AS node
  FROM workflow.mapping_source_system_dependency AS dependency
 WHERE dependency.model_id = %s
   AND dependency.modeled_entity_type = %s
   AND dependency.mapping_source_system_dependency_status = 'active'
 ORDER BY dependency.source_system_id
 LIMIT 1001
"""

_MAPPING_TARGET_NODES_SQL: LiteralString = """
SELECT jsonb_build_object(
           'target_object_id', binding.object_id,
           'dependency_order', coalesce(min(mapping.object_dependency_order), 0),
           'status', binding.model_object_binding_status,
           'has_locked_headers', coalesce(bool_or(mapping.object_mapping_is_locked), false),
           'has_unlocked_headers', coalesce(bool_or(NOT mapping.object_mapping_is_locked), false)
       ) AS node
  FROM workflow.model_object_binding AS binding
  LEFT JOIN workflow.mapping_object AS mapping
    ON mapping.model_object_binding_id = binding.model_object_binding_id
   AND mapping.object_mapping_status = 'active'
 WHERE binding.model_id = %s
   AND binding.modeled_entity_type = %s
   AND binding.model_object_binding_status = 'active'
 GROUP BY binding.model_object_binding_id,
          binding.object_id,
          binding.model_object_binding_status
 ORDER BY binding.object_id
 LIMIT 1001
"""

_MAPPING_TARGET_CONTEXT_SQL: LiteralString = """
SELECT jsonb_build_object(
           'object_id', target_object.object_id,
           'tenant_id', target_tenant.tenant_id,
           'tenant_code', target_tenant.tenant_code,
           'tenant_catalog', target_tenant.tenant_catalog,
           'tenant_is_active', target_tenant.is_active,
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
           'scope_is_locked', binding.model_object_binding_is_locked,
           'scope_is_active', binding.model_object_binding_status = 'active',
           'is_locked', target_object.is_locked,
           'is_active', target_object.is_active,
           'attributes', attributes.items
       ) AS target
  FROM model.model AS target_model
  JOIN workflow.model_object_binding AS binding
    ON binding.model_id = target_model.model_id
   AND binding.object_id = %s
   AND binding.model_object_binding_status = 'active'
  JOIN core.object AS target_object
    ON target_object.object_id = binding.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN reference.zone AS target_zone
    ON target_zone.zone_id = target_object.zone_id
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(
                      jsonb_build_object(
                          'attribute_id', attribute.attribute_id,
                          'attribute_name', attribute.attribute_name,
                          'attribute_data_type', attribute.attribute_data_type,
                          'attribute_nullability', attribute.attribute_nullability,
                          'attribute_ordinal_position', attribute.attribute_ordinal_position,
                          'attribute_description', attribute.attribute_description,
                          'is_active', attribute.is_active
                      ) ORDER BY attribute.attribute_ordinal_position
                  ),
                  '[]'::JSONB
              ) AS items
         FROM core.attribute AS attribute
        WHERE attribute.object_id = target_object.object_id
  ) AS attributes
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.model_revision = %s
   AND target_model.is_active
"""

_MAPPING_BINDING_CONTEXT_SQL: LiteralString = """
WITH selected_binding AS MATERIALIZED (
    SELECT binding.*
      FROM workflow.model_object_binding AS binding
     WHERE binding.model_id = %s
       AND binding.object_id = %s
       AND binding.modeled_entity_type = %s
       AND binding.model_object_binding_status = 'active'
), selected_mapping AS MATERIALIZED (
    SELECT mapping.*
      FROM selected_binding AS binding
      LEFT JOIN workflow.mapping_object AS mapping
        ON mapping.model_object_binding_id = binding.model_object_binding_id
       AND mapping.source_system_id = %s
       AND mapping.object_mapping_status IN ('active', 'inactive', 'deprecated')
), modeled_attribute AS MATERIALIZED (
    SELECT attribute.logical_attribute_id AS modeled_attribute_id,
           attribute.logical_attribute_name AS attribute_name,
           attribute.logical_attribute_definition AS attribute_definition,
           attribute.logical_attribute_data_type AS attribute_data_type,
           attribute.logical_attribute_is_nullable AS is_nullable,
           attribute.logical_attribute_ordinal_position AS ordinal_position,
           attribute.logical_attribute_is_audit_column AS is_audit_column,
           attribute.logical_attribute_status AS status,
           attribute.logical_attribute_is_locked AS is_locked,
           target.model_attribute_binding_id,
           target.attribute_id AS target_attribute_id
      FROM selected_binding AS binding
      JOIN workflow.logical_attribute AS attribute
        ON binding.modeled_entity_type = 'logical_entity'
       AND attribute.model_id = binding.model_id
       AND attribute.logical_entity_id = binding.logical_entity_id
      JOIN workflow.model_attribute_binding AS target
        ON target.model_object_binding_id = binding.model_object_binding_id
       AND target.logical_attribute_id = attribute.logical_attribute_id
       AND target.model_attribute_binding_status = 'active'
     UNION ALL
    SELECT attribute.dimensional_attribute_id,
           attribute.dimensional_attribute_name,
           attribute.dimensional_attribute_definition,
           attribute.dimensional_attribute_data_type,
           attribute.dimensional_attribute_is_nullable,
           attribute.dimensional_attribute_ordinal_position,
           attribute.dimensional_attribute_is_audit_column,
           attribute.dimensional_attribute_status,
           attribute.dimensional_attribute_is_locked,
           target.model_attribute_binding_id,
           target.attribute_id
      FROM selected_binding AS binding
      JOIN workflow.dimensional_attribute AS attribute
        ON binding.modeled_entity_type = 'dimensional_entity'
       AND attribute.model_id = binding.model_id
       AND attribute.dimensional_entity_id = binding.dimensional_entity_id
      JOIN workflow.model_attribute_binding AS target
        ON target.model_object_binding_id = binding.model_object_binding_id
       AND target.dimensional_attribute_id = attribute.dimensional_attribute_id
       AND target.model_attribute_binding_status = 'active'
)
SELECT jsonb_build_object(
           'model_object_binding_id', binding.model_object_binding_id,
           'mapping_object_id', mapping.mapping_object_id,
           'modeled_entity', jsonb_build_object(
               'entity_id', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_id
                   ELSE dimensional_entity.dimensional_entity_id
               END,
               'entity_name', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_name
                   ELSE dimensional_entity.dimensional_entity_name
               END,
               'entity_definition', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_definition
                   ELSE dimensional_entity.dimensional_entity_definition
               END,
               'entity_kind', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_type
                   ELSE dimensional_entity.dimensional_entity_type
               END,
               'grain', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_grain
                   ELSE dimensional_entity.dimensional_entity_grain_definition
               END,
               'dependency_order', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_dependency_order
                   ELSE dimensional_entity.dimensional_entity_dependency_order
               END,
               'status', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_status
                   ELSE dimensional_entity.dimensional_entity_status
               END,
               'is_locked', CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_is_locked
                   ELSE dimensional_entity.dimensional_entity_is_locked
               END,
               'attributes', modeled_attributes.items
           ),
           'object_dependency_order', coalesce(
               mapping.object_dependency_order,
               CASE binding.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_dependency_order
                   ELSE dimensional_entity.dimensional_entity_dependency_order
               END
           ),
           'transformation_document', mapping.mapping_transformation_document,
           'status', coalesce(mapping.object_mapping_status, 'active'),
           'is_locked', coalesce(mapping.object_mapping_is_locked, false),
           'agent_run_id', mapping.agent_run_id,
           'workflow_run_id', mapping.workflow_run_id,
           'output_template_id', mapping.output_template_id,
           'attribute_mappings', mapping_attributes.items
       ) AS header
  FROM selected_binding AS binding
  LEFT JOIN selected_mapping AS mapping ON true
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON binding.modeled_entity_type = 'logical_entity'
   AND logical_entity.model_id = binding.model_id
   AND logical_entity.logical_entity_id = binding.logical_entity_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON binding.modeled_entity_type = 'dimensional_entity'
   AND dimensional_entity.model_id = binding.model_id
   AND dimensional_entity.dimensional_entity_id = binding.dimensional_entity_id
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(
                      jsonb_build_object(
                          'attribute_id', item.modeled_attribute_id,
                          'attribute_name', item.attribute_name,
                          'attribute_definition', item.attribute_definition,
                          'attribute_data_type', item.attribute_data_type,
                          'is_nullable', item.is_nullable,
                          'ordinal_position', item.ordinal_position,
                          'is_audit_column', item.is_audit_column,
                          'status', item.status,
                          'is_locked', item.is_locked
                      ) ORDER BY item.ordinal_position
                  ),
                  '[]'::JSONB
              ) AS items
         FROM modeled_attribute AS item
  ) AS modeled_attributes
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(
                      jsonb_build_object(
                          'mapping_attribute_id', child.mapping_attribute_id,
                          'modeled_attribute_id', item.modeled_attribute_id,
                          'target_attribute_id', item.target_attribute_id,
                          'transformation_document',
                              child.attribute_mapping_transformation_document,
                          'status', coalesce(child.attribute_mapping_status, 'active'),
                          'is_locked', coalesce(child.attribute_mapping_is_locked, false),
                          'agent_run_id', child.agent_run_id,
                          'workflow_run_id', child.workflow_run_id,
                          'output_template_id', child.output_template_id
                      ) ORDER BY item.ordinal_position
                  ),
                  '[]'::JSONB
              ) AS items
         FROM modeled_attribute AS item
         LEFT JOIN workflow.mapping_attribute AS child
           ON child.mapping_object_id = mapping.mapping_object_id
          AND child.model_attribute_binding_id = item.model_attribute_binding_id
  ) AS mapping_attributes
"""

_MAPPING_SOURCE_CONTEXT_SQL: LiteralString = """
WITH selected_binding AS MATERIALIZED (
    SELECT binding.*
      FROM workflow.model_object_binding AS binding
     WHERE binding.model_id = %s
       AND binding.object_id = %s
       AND binding.modeled_entity_type = %s
       AND binding.model_object_binding_status = 'active'
), source_reference AS MATERIALIZED (
    SELECT source.logical_entity_source_mapping_id AS source_mapping_id,
           source.logical_entity_id AS modeled_entity_id,
           'support'::TEXT AS role,
           source.logical_entity_source_mapping_rationale AS rationale,
           source.logical_entity_source_mapping_order AS mapping_order,
           source.logical_entity_source_mapping_is_locked AS is_locked,
           source.source_object_id
      FROM selected_binding AS binding
      JOIN workflow.logical_entity_source_mapping AS source
        ON binding.modeled_entity_type = 'logical_entity'
       AND source.model_id = binding.model_id
       AND source.logical_entity_id = binding.logical_entity_id
       AND source.support_source_type = 'object'
       AND source.logical_entity_source_mapping_status = 'active'
     UNION ALL
    SELECT source.dimensional_entity_source_mapping_id,
           source.dimensional_entity_id,
           source.dimensional_entity_source_role,
           source.dimensional_entity_source_mapping_rationale,
           source.dimensional_entity_source_mapping_order,
           source.dimensional_entity_source_mapping_is_locked,
           source.source_object_id
      FROM selected_binding AS binding
      JOIN workflow.dimensional_entity_source_mapping AS source
        ON binding.modeled_entity_type = 'dimensional_entity'
       AND source.model_id = binding.model_id
       AND source.dimensional_entity_id = binding.dimensional_entity_id
       AND source.support_source_type = 'object'
       AND source.dimensional_entity_source_mapping_status = 'active'
)
SELECT jsonb_build_object(
           'source_mapping_id', source.source_mapping_id,
           'modeled_entity_id', source.modeled_entity_id,
           'role', source.role,
           'rationale', source.rationale,
           'mapping_order', source.mapping_order,
           'is_locked', source.is_locked,
           'object', jsonb_build_object(
               'object_id', source_object.object_id,
               'tenant_id', source_placement_tenant.tenant_id,
               'tenant_code', source_placement_tenant.tenant_code,
               'tenant_catalog', source_placement_tenant.tenant_catalog,
               'tenant_is_active', source_placement_tenant.is_active,
               'system_id', source_system.system_id,
               'system_code', source_system.system_code,
               'system_is_active', source_system.is_active,
               'connection_id', source_connection.connection_id,
               'connection_code', source_connection.connection_code,
               'connection_is_active', source_connection.is_active,
               'is_global_data_store', source_connection.is_global_data_store,
               'object_schema', source_object.object_schema,
               'object_name', source_object.object_name,
               'object_description', source_object.object_description,
               'batch_attribute_name', source_object.batch_attribute_name,
               'zone_code', lower(btrim(source_zone.zone_code)),
               'scope_is_locked', source_scope.model_input_scope_is_locked,
               'scope_is_active', source_scope.is_active,
               'is_locked', source_object.is_locked,
               'is_active', source_object.is_active,
               'attributes', attributes.items
           )
       ) AS source
  FROM source_reference AS source
  JOIN core.object AS source_object
    ON source_object.object_id = source.source_object_id
  JOIN model.model_input_scope AS source_scope
    ON source_scope.model_id = %s
   AND source_scope.object_id = source_object.object_id
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  JOIN core.tenant AS source_placement_tenant
    ON source_placement_tenant.tenant_id = source_connection.tenant_id
  JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id
  JOIN reference.zone AS source_zone
    ON source_zone.zone_id = source_object.zone_id
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(
                      jsonb_build_object(
                          'attribute_id', attribute.attribute_id,
                          'attribute_name', attribute.attribute_name,
                          'attribute_data_type', attribute.attribute_data_type,
                          'attribute_nullability', attribute.attribute_nullability,
                          'attribute_ordinal_position', attribute.attribute_ordinal_position,
                          'attribute_description', attribute.attribute_description,
                          'is_active', attribute.is_active
                      ) ORDER BY attribute.attribute_ordinal_position
                  ),
                  '[]'::JSONB
              ) AS items
         FROM core.attribute AS attribute
        WHERE attribute.object_id = source_object.object_id
  ) AS attributes
 WHERE (
           lower(btrim(source_zone.zone_code)) = 'source'
           AND source_connection.system_id = %s
       )
    OR (
           lower(btrim(source_zone.zone_code)) = 'bronze'
           AND EXISTS (
               SELECT 1
                 FROM core.ingestion_object_mapping AS ingestion
                 JOIN core.object AS original
                   ON original.object_id = ingestion.source_object_id
                 JOIN core.connection AS original_connection
                   ON original_connection.connection_id = original.connection_id
                WHERE ingestion.target_object_id = source_object.object_id
                  AND ingestion.is_active
                  AND original_connection.system_id = %s
           )
       )
 ORDER BY source.mapping_order NULLS LAST, source.source_mapping_id
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
               template.output_template_schema_digest =
               encode(
                   sha256(
                       convert_to(
                           jsonb_build_object(
                               'output_template_target_type',
                                   template.output_template_target_type,
                               'fields', fields.digest_items
                           )::TEXT,
                           'UTF8'
                       )
                   ),
                   'hex'
               ),
           'is_active', template.is_active,
           'fields', fields.items
       ) AS output_template
  FROM application.output_template AS template
 CROSS JOIN LATERAL (
       SELECT coalesce(
                  jsonb_agg(
                      jsonb_build_object(
                          'name', field.output_template_field_name,
                          'description', field.output_template_field_description,
                          'data_type', field.output_template_field_data_type,
                          'array_item_type', field.output_template_field_array_item_type,
                          'example', field.output_template_field_example,
                          'is_required', field.output_template_field_is_required,
                          'order', field.output_template_field_order
                      ) ORDER BY field.output_template_field_order
                  ),
                  '[]'::JSONB
              ) AS items,
              coalesce(
                  jsonb_agg(
                      jsonb_build_object(
                          'output_template_field_name',
                              field.output_template_field_name,
                          'output_template_field_description',
                              field.output_template_field_description,
                          'output_template_field_data_type',
                              field.output_template_field_data_type,
                          'output_template_field_array_item_type',
                              field.output_template_field_array_item_type,
                          'output_template_field_example',
                              coalesce(
                                  field.output_template_field_example,
                                  'null'::JSONB
                              ),
                          'output_template_field_is_required',
                              field.output_template_field_is_required,
                          'output_template_field_order',
                              field.output_template_field_order
                      ) ORDER BY field.output_template_field_order
                  ),
                  '[]'::JSONB
              ) AS digest_items
         FROM application.output_template_field AS field
        WHERE field.output_template_id = template.output_template_id
  ) AS fields
 WHERE template.output_template_id = ANY(%s::BIGINT[])
 ORDER BY template.output_template_id
 LIMIT 20067
"""


class PostgresMappingRunPlanRepository:
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
            (tenant_id, model_id, workflow_run_id, expected_model_revision, actor_principal_id),
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
                or row.get("model_revision") != expected_model_revision
                or row.get("modeled_entity_type") != common.modeled_entity_type
                or row.get("selection_order") != 1
            ):
                raise MappingRunPlanUnavailableError()
            return MappingRunPlan.model_validate(
                {
                    "agent_plan": common,
                    "actor_principal_id": actor_principal_id,
                    "pair": {
                        "target_object_id": row.get("target_object_id"),
                        "source_system_id": row.get("source_system_id"),
                    },
                    "operation": row.get("mapping_operation"),
                    "coverage_mode": row.get("mapping_coverage_mode"),
                    "route": row.get("mapping_route"),
                    "output_template_selections": {
                        "mapping_object": _template_selection(row, "mapping_object"),
                        "mapping_attribute": _template_selection(row, "mapping_attribute"),
                    },
                },
                strict=False,
            )
        except MappingRunPlanUnavailableError:
            raise
        except (TypeError, ValueError, ValidationError):
            raise MappingRunPlanUnavailableError() from None


class PostgresMappingRunContextRepository:
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
                plan.model_revision,
                plan.workflow_run_id,
                plan.model_id,
                plan.actor_principal_id,
                plan.correlation_id,
                plan.pair.target_object_id,
                plan.pair.source_system_id,
                plan.modeled_entity_type,
                plan.route,
                plan.operation,
            ),
        )
        if anchor is None:
            raise MappingRunContextUnavailableError()
        target = await transaction.fetch_one(
            _MAPPING_TARGET_CONTEXT_SQL,
            (
                plan.pair.target_object_id,
                tenant_id,
                plan.model_id,
                plan.model_revision,
            ),
        )
        header = await transaction.fetch_one(
            _MAPPING_BINDING_CONTEXT_SQL,
            (
                plan.model_id,
                plan.pair.target_object_id,
                plan.modeled_entity_type,
                plan.pair.source_system_id,
            ),
        )
        if target is None or header is None:
            raise MappingRunContextUnavailableError()
        source_rows = await transaction.fetch_all(
            _MAPPING_SOURCE_CONTEXT_SQL,
            (
                plan.model_id,
                plan.pair.target_object_id,
                plan.modeled_entity_type,
                plan.model_id,
                plan.pair.source_system_id,
                plan.pair.source_system_id,
            ),
        )
        dependency_rows = await transaction.fetch_all(
            _MAPPING_DEPENDENCY_NODES_SQL,
            (plan.model_id, plan.modeled_entity_type),
        )
        target_node_rows = await transaction.fetch_all(
            _MAPPING_TARGET_NODES_SQL,
            (plan.model_id, plan.modeled_entity_type),
        )
        try:
            parsed_header = ExistingMappingHeader.model_validate(
                header.get("header"),
                strict=False,
            )
            referenced_template_ids = {
                selection.output_template_id
                for selection in (
                    plan.output_template_selections.mapping_object,
                    plan.output_template_selections.mapping_attribute,
                )
                if selection is not None
            }
            if parsed_header.output_template_id is not None:
                referenced_template_ids.add(parsed_header.output_template_id)
            referenced_template_ids.update(
                item.output_template_id
                for item in parsed_header.attribute_mappings
                if item.output_template_id is not None
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
                    "pair": plan.pair,
                    "modeled_entity_type": plan.modeled_entity_type,
                    "route": plan.route,
                    "output_template_selections": plan.output_template_selections,
                    "source_system": anchor.get("source_system"),
                    "dependency": anchor.get("dependency"),
                    "dependency_graph": {
                        "nodes": [row.get("node") for row in dependency_rows],
                        "edges": [],
                        "malformed_reference_count": 0,
                    },
                    "target_dependency_graph": {
                        "nodes": [row.get("node") for row in target_node_rows],
                        "edges": [],
                        "malformed_reference_count": 0,
                        "mixed_order_target_count": 0,
                    },
                    "output_templates": {
                        "ids": sorted(referenced_template_ids),
                        "definitions": [row.get("output_template") for row in template_rows],
                    },
                    "target": target.get("target"),
                    "sources": [row.get("source") for row in source_rows],
                    "headers": [parsed_header],
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


def _template_selection(row: object, prefix: str) -> dict[str, object] | None:
    if not hasattr(row, "get"):
        return None
    template_id = row.get(f"{prefix}_output_template_id")  # type: ignore[attr-defined]
    if template_id is None:
        return None
    return {
        "output_template_id": template_id,
        "schema_digest": row.get(f"{prefix}_output_template_schema_digest"),  # type: ignore[attr-defined]
    }
