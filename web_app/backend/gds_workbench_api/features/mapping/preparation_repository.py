"""PostgreSQL Mapping Run plan and compact Entity context repositories."""

from __future__ import annotations

from typing import Any, LiteralString

from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import ValidationError

from gds_workbench_api.features.workflows.authoring.audit_policy import effective_audit_template
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates
from gds_workbench_api.features.workflows.authoring.naming import effective_naming_instructions
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlanRepository,
    PostgresAgentRunPlanRepository,
)

from .preparation_contracts import (
    ExistingMappingHeader,
    MappingAuthoringPolicy,
    MappingModeledEntity,
    MappingRunContext,
    MappingRunContextUnavailableError,
    MappingRunPlan,
    MappingRunPlanUnavailableError,
    MappingSource,
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
       entity_selection.modeled_entity_id AS modeled_entity_id,
       selection.source_system_id,
       selection.selection_order,
       selection.selected_attribute_ids
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
  JOIN application.workflow_run_mapping_target_selection AS selection
    ON selection.workflow_run_id = run.workflow_run_id
   AND selection.model_id = run.model_id
  JOIN application.workflow_run_entity_selection AS entity_selection
    ON entity_selection.workflow_run_entity_selection_id =
        selection.workflow_run_entity_selection_id
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND target_model.model_revision = %s
   AND run.actor_principal_id = %s
   AND run.model_workflow = 'mapping'
   AND run.workflow_run_state = 'running'
   AND run.mapping_coverage_mode = 'selected_targets'
   AND run.mapping_route = CASE run.modeled_entity_type
       WHEN 'logical_entity' THEN 'logical_to_silver'
       WHEN 'dimensional_entity' THEN 'dimensional_to_gold'
   END
 ORDER BY selection.selection_order
"""

_MAPPING_CONTEXT_ANCHOR_SQL: LiteralString = """
SELECT run.workflow_run_id,
       run.model_id,
       target_model.model_revision,
       run.correlation_id,
       run.actor_principal_id,
       entity_selection.modeled_entity_id AS modeled_entity_id,
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
           'is_active', source_system.is_active AND (NOT fallback.is_default OR EXISTS (
               SELECT 1 FROM core.connection AS owned_connection
                WHERE owned_connection.tenant_id = target_model.tenant_id
                  AND owned_connection.system_id = source_system.system_id
                  AND owned_connection.is_active
           )),
           'is_default', fallback.is_default
       ) AS source_system,
       jsonb_build_object(
           'model_name', target_model.model_name,
           'logical_entity_scd_type', target_model.logical_entity_scd_type,
           'dimensional_entity_scd_type', target_model.dimensional_entity_scd_type,
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
  JOIN application.workflow_run_entity_selection AS entity_selection
    ON entity_selection.workflow_run_entity_selection_id =
        selection.workflow_run_entity_selection_id
  JOIN core.system AS source_system
    ON source_system.system_id = selection.source_system_id
 CROSS JOIN LATERAL (
       SELECT coalesce(source_system.system_id =
           target_model.default_mapping_source_system_id, FALSE)
           AND workflow.is_assertion_only_mapping_target(run.model_id,
               entity_selection.modeled_entity_id, run.modeled_entity_type) AS is_default
 ) AS fallback
 WHERE run.workflow_run_id = %s
   AND run.model_id = %s
   AND run.actor_principal_id = %s
   AND run.correlation_id = %s
   AND entity_selection.modeled_entity_id = %s
   AND selection.source_system_id = %s
   AND run.modeled_entity_type = %s
   AND run.mapping_route = %s
   AND run.mapping_operation = %s
   AND run.model_workflow = 'mapping'
   AND run.workflow_run_state = 'running'
"""

_MAPPING_TARGET_NODES_SQL: LiteralString = """
SELECT jsonb_build_object('modeled_entity_id', entity.modeled_entity_id,
 'dependency_order', coalesce(min(mapping.object_dependency_order), entity.dependency_order),
 'status', entity.status,
 'has_locked_headers', coalesce(bool_or(mapping.object_mapping_is_locked), false),
 'has_unlocked_headers', coalesce(bool_or(NOT mapping.object_mapping_is_locked), false)) AS node
 FROM workflow.modeled_entity AS entity
 LEFT JOIN workflow.mapping_object AS mapping ON mapping.model_id = entity.model_id
  AND mapping.modeled_entity_type = entity.modeled_entity_type
  AND coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id) = entity.modeled_entity_id
  AND mapping.object_mapping_status = 'active'
 WHERE entity.model_id = %s AND entity.modeled_entity_type = %s AND entity.status = 'active'
 GROUP BY entity.modeled_entity_id, entity.dependency_order, entity.status
 ORDER BY entity.modeled_entity_id
"""

_MAPPING_ENTITY_CONTEXT_SQL: LiteralString = """
WITH selected_entity AS MATERIALIZED (
 SELECT * FROM workflow.modeled_entity WHERE model_id = %s AND modeled_entity_id = %s
  AND modeled_entity_type = %s AND status = 'active'
), selected_mapping AS MATERIALIZED (
 SELECT mapping.* FROM selected_entity AS entity
 JOIN workflow.mapping_object AS mapping ON mapping.model_id = entity.model_id
  AND mapping.modeled_entity_type = entity.modeled_entity_type
  AND coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id) = entity.modeled_entity_id
  AND mapping.source_system_id = %s
), attributes AS MATERIALIZED (
 SELECT attribute.* FROM selected_entity AS entity
 JOIN workflow.modeled_attribute AS attribute ON attribute.model_id = entity.model_id
  AND attribute.modeled_entity_type = entity.modeled_entity_type
  AND attribute.modeled_entity_id = entity.modeled_entity_id
 WHERE attribute.status = 'active'
)
SELECT jsonb_build_object('modeled_entity_id', entity.modeled_entity_id,
 'mapping_object_id', mapping.mapping_object_id, 'modeled_entity', jsonb_build_object(
 'entity_type', entity.modeled_entity_type, 'entity_id', entity.modeled_entity_id,
 'entity_schema_name', entity.modeled_entity_schema_name,
 'entity_name', entity.modeled_entity_name, 'entity_definition', entity.definition,
 'entity_kind', entity.classification, 'grain', entity.grain, 'dependency_order',
     entity.dependency_order,
 'status', entity.status, 'is_locked', entity.is_locked, 'attributes', modeled_attributes.items),
 'object_dependency_order', coalesce(mapping.object_dependency_order, entity.dependency_order),
 'transformation_document', mapping.mapping_transformation_document,
 'status', coalesce(mapping.object_mapping_status, 'active'),
 'is_locked', entity.is_locked OR coalesce(mapping.object_mapping_is_locked, false),
 'agent_run_id', mapping.agent_run_id, 'workflow_run_id', mapping.workflow_run_id,
 'output_template_id', mapping.output_template_id, 'attribute_mappings', mapping_attributes.items)
     AS header
 FROM selected_entity AS entity LEFT JOIN selected_mapping AS mapping ON true
 CROSS JOIN LATERAL (SELECT coalesce(jsonb_agg(jsonb_build_object(
 'attribute_id', item.modeled_attribute_id, 'attribute_name', item.attribute_name,
 'attribute_definition', item.definition, 'attribute_data_type', item.data_type,
 'is_nullable', item.is_nullable, 'ordinal_position', item.ordinal_position,
 'is_surrogate_key', item.is_surrogate_key,
 'is_audit_column', item.is_audit_column, 'status', item.status, 'is_locked', item.is_locked)
     ORDER BY item.ordinal_position, item.modeled_attribute_id), '[]'::JSONB) AS items FROM
     attributes AS item) AS modeled_attributes
 CROSS JOIN LATERAL (
 SELECT coalesce(jsonb_agg(jsonb_build_object(
  'mapping_attribute_id', child.mapping_attribute_id, 'modeled_attribute_id',
      item.modeled_attribute_id,
  'transformation_document', child.attribute_mapping_transformation_document,
  'status', coalesce(child.attribute_mapping_status, 'active'),
  'is_locked', item.is_locked OR coalesce(child.attribute_mapping_is_locked, false),
  'agent_run_id', child.agent_run_id, 'workflow_run_id', child.workflow_run_id,
      'output_template_id', child.output_template_id
 ) ORDER BY item.ordinal_position, item.modeled_attribute_id), '[]'::JSONB) AS items
 FROM attributes AS item
 LEFT JOIN workflow.mapping_attribute AS child ON child.mapping_object_id =
     mapping.mapping_object_id
  AND coalesce(child.logical_attribute_id, child.dimensional_attribute_id) =
      item.modeled_attribute_id
 ) AS mapping_attributes
"""

# Input Scope contains Source/Bronze. Silver sources instead require an applied
# Logical Entity and Mapping; Model ownership remains independent of physical placement.
_MAPPING_PHYSICAL_SOURCE_CONTEXT_SQL: LiteralString = """
SELECT jsonb_build_object(
           'source_mapping_id', source.source_mapping_id,
           'modeled_entity_id', source.modeled_entity_id,
           'role', source.role,
           'rationale', source.rationale,
           'mapping_order', source.mapping_order,
           'is_locked', source.is_locked,
           'object', jsonb_build_object(
               'object_id', source_object.object_id,
               'source_tenant_id', source_object.source_tenant_id,
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
               'object_description', object_enrichment.object_description,
               'batch_attribute_name', source_object.batch_attribute_name,
               'zone_code', lower(btrim(source_zone.zone_code)),
               'scope_is_locked', source.scope_is_locked,
               'scope_is_active', source.scope_is_active,
               'is_locked', source_object.is_locked,
               'is_active', source_object.is_active,
               'attributes', attributes.items
           )
       ) AS source
  FROM selected_sources AS source
  JOIN core.object AS source_object
    ON source_object.object_id = source.source_object_id
  LEFT JOIN workflow.object_enrichment AS object_enrichment
    ON object_enrichment.model_id = source.model_id
   AND object_enrichment.object_id = source_object.object_id
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
                          'attribute_inferred_data_type', enrichment.attribute_inferred_data_type,
                          'is_natural_key', enrichment.is_natural_key,
                          'is_primary_key', enrichment.is_primary_key,
                          'is_nullable', enrichment.is_nullable, 'is_pii', enrichment.is_pii,
                          'attribute_nullability', attribute.attribute_nullability,
                          'attribute_ordinal_position', attribute.attribute_ordinal_position,
                          'attribute_description', enrichment.attribute_description,
                          'is_active', attribute.is_active
                      ) ORDER BY attribute.attribute_ordinal_position
                  ),
                  '[]'::JSONB
              ) AS items
         FROM core.attribute AS attribute
         LEFT JOIN workflow.attribute_enrichment AS enrichment
           ON enrichment.model_id = source.model_id
          AND enrichment.attribute_id = attribute.attribute_id
        WHERE attribute.object_id = source_object.object_id
  ) AS attributes
 ORDER BY source.mapping_order NULLS LAST, source.source_mapping_id
"""

_MAPPING_MODELED_SOURCE_CONTEXT_SQL: LiteralString = """
SELECT jsonb_build_object(
 'source_mapping_id', source.source_mapping_id, 'modeled_entity_id', source.modeled_entity_id,
 'role', source.role, 'rationale', source.rationale, 'mapping_order', source.mapping_order,
 'is_locked', source.is_locked, 'object', jsonb_build_object(
 'entity_type', entity.modeled_entity_type, 'entity_id', entity.modeled_entity_id,
 'entity_schema_name', entity.modeled_entity_schema_name,
 'entity_name', entity.modeled_entity_name, 'entity_definition', entity.definition,
 'entity_kind', entity.classification, 'grain', entity.grain, 'dependency_order',
     entity.dependency_order,
 'status', entity.status, 'is_locked', entity.is_locked, 'attributes', attributes.items)) AS source
 FROM selected_sources AS source
 JOIN workflow.modeled_entity AS entity ON entity.modeled_entity_type = CASE
  WHEN source.source_dimensional_entity_id IS NOT NULL THEN 'dimensional_entity'
  ELSE 'logical_entity' END
  AND entity.modeled_entity_id = coalesce(source.source_logical_entity_id,
      source.source_dimensional_entity_id)
 CROSS JOIN LATERAL (
 SELECT coalesce(jsonb_agg(jsonb_build_object(
 'attribute_id', item.modeled_attribute_id, 'attribute_name', item.attribute_name,
 'attribute_definition', item.definition, 'attribute_data_type', item.data_type,
 'is_nullable', item.is_nullable, 'ordinal_position', item.ordinal_position,
 'is_surrogate_key', item.is_surrogate_key,
 'is_audit_column', item.is_audit_column, 'status', item.status, 'is_locked', item.is_locked
 ) ORDER BY item.ordinal_position, item.modeled_attribute_id), '[]'::JSONB) AS items
 FROM workflow.modeled_attribute AS item WHERE item.model_id = entity.model_id
  AND item.modeled_entity_type = entity.modeled_entity_type AND item.modeled_entity_id =
      entity.modeled_entity_id
  AND item.status = 'active'
 ) AS attributes
 ORDER BY source.mapping_order NULLS LAST, entity.modeled_entity_id
"""

MAPPING_SOURCE_CONTEXT_SQL: LiteralString = (
    "WITH selected_sources AS MATERIALIZED ("
    "SELECT owner.model_id, source.* FROM (SELECT %s::BIGINT AS model_id) AS owner "
    "CROSS JOIN LATERAL workflow.list_mapping_source_objects("
    "owner.model_id, %s, %s, %s) AS source) "
    "SELECT source FROM (("
    + _MAPPING_PHYSICAL_SOURCE_CONTEXT_SQL
    + ") UNION ALL ("
    + _MAPPING_MODELED_SOURCE_CONTEXT_SQL
    + ")) AS sources "
    "ORDER BY (source ->> 'mapping_order')::INTEGER NULLS LAST, "
    "source -> 'object' ->> 'entity_schema_name', source -> 'object' ->> 'entity_name', "
    "(source ->> 'source_mapping_id')::BIGINT"
)

_MAPPING_UPSTREAM_PHYSICAL_CONTEXT_SQL: LiteralString = (
    "WITH selected_sources AS MATERIALIZED ("
    "SELECT NULL::BIGINT AS source_mapping_id, %s::BIGINT AS modeled_entity_id, "
    "'evidence'::TEXT AS role, 'Upstream physical provenance, not a Gold input.'::TEXT "
    "AS rationale, NULL::INTEGER AS mapping_order, FALSE AS is_locked, "
    "input.object_id AS source_object_id, scope.model_input_scope_is_locked AS scope_is_locked, "
    "scope.is_active AS scope_is_active, scope.model_id "
    "FROM workflow.list_model_input_sources(%s) AS input "
    "JOIN model.model_input_scope AS scope ON scope.model_id = %s "
    "AND scope.object_id = input.object_id AND scope.is_active "
    "WHERE input.source_system_id = %s) " + _MAPPING_PHYSICAL_SOURCE_CONTEXT_SQL
)

_MAPPING_UPSTREAM_TEMPLATE_IDS_SQL: LiteralString = """
SELECT DISTINCT template_id AS output_template_id
  FROM workflow.mapping_object AS mapping
  LEFT JOIN workflow.mapping_attribute AS attribute
    ON attribute.mapping_object_id = mapping.mapping_object_id
   AND attribute.attribute_mapping_status = 'active'
 CROSS JOIN LATERAL unnest(ARRAY[mapping.output_template_id, attribute.output_template_id])
    AS template(template_id)
 WHERE mapping.model_id = %s AND mapping.modeled_entity_type = 'logical_entity'
   AND mapping.logical_entity_id = ANY(%s::BIGINT[])
   AND mapping.source_system_id = %s AND mapping.object_mapping_status = 'active'
   AND template_id IS NOT NULL
 ORDER BY template_id
"""

_MAPPING_OUTPUT_TEMPLATE_CONTEXT_SQL: LiteralString = """
SELECT jsonb_build_object(
           'output_template_id', template.output_template_id,
           'code', template.output_template_code,
           'name', template.output_template_name,
           'description', template.output_template_description,
           'target_type', template.output_template_target_type,
           'modeled_entity_type', template.output_template_modeled_entity_type,
           'schema_digest', template.output_template_schema_digest,
           'schema_digest_is_valid',
               template.output_template_schema_digest =
               encode(
                   sha256(
                       convert_to(
                           jsonb_build_object(
                               'output_template_target_type',
                                   template.output_template_target_type,
                               'output_template_modeled_entity_type',
                                   template.output_template_modeled_entity_type,
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
"""


class PostgresMappingRunPlanRepository:
    def __init__(
        self,
        *,
        agent_plan_repository: AgentRunPlanRepository | None = None,
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
    ) -> tuple[MappingRunPlan, ...]:
        rows = await transaction.fetch_all(
            _MAPPING_RUN_PLAN_SQL,
            (tenant_id, model_id, workflow_run_id, expected_model_revision, actor_principal_id),
        )
        if not rows:
            raise MappingRunPlanUnavailableError()
        common = await self._agent_plan_repository.load(
            transaction,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
        )
        try:
            plans: list[MappingRunPlan] = []
            for selection_ordinal, row in enumerate(rows, start=1):
                if (
                    row.get("workflow_run_id") != common.workflow_run_id
                    or row.get("model_id") != common.model_id
                    or row.get("correlation_id") != common.correlation_id
                    or row.get("actor_principal_id") != actor_principal_id
                    or row.get("model_revision") != expected_model_revision
                    or row.get("modeled_entity_type") != common.modeled_entity_type
                ):
                    raise MappingRunPlanUnavailableError()
                plans.append(
                    MappingRunPlan.model_validate(
                        {
                            "agent_plan": common.model_copy(
                                update={"selected_entity_ids": (row["modeled_entity_id"],)}
                            ),
                            "selected_attribute_ids": row.get("selected_attribute_ids"),
                            "actor_principal_id": actor_principal_id,
                            "selection_ordinal": selection_ordinal,
                            "pair": {
                                "modeled_entity_id": row.get("modeled_entity_id"),
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
                )
            return tuple(plans)
        except MappingRunPlanUnavailableError:
            raise
        except TypeError, ValueError, ValidationError:
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
                plan.pair.modeled_entity_id,
                plan.pair.source_system_id,
                plan.modeled_entity_type,
                plan.route,
                plan.operation,
            ),
        )
        if anchor is None:
            raise MappingRunContextUnavailableError()
        header = await transaction.fetch_one(
            _MAPPING_ENTITY_CONTEXT_SQL,
            (
                plan.model_id,
                plan.pair.modeled_entity_id,
                plan.modeled_entity_type,
                plan.pair.source_system_id,
            ),
        )
        if header is None:
            raise MappingRunContextUnavailableError()
        source_rows = await transaction.fetch_all(
            MAPPING_SOURCE_CONTEXT_SQL,
            (
                plan.model_id,
                plan.pair.modeled_entity_id,
                plan.modeled_entity_type,
                plan.pair.source_system_id,
            ),
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
            sources = tuple(
                MappingSource.model_validate(row.get("source"), strict=False) for row in source_rows
            )
            logical_ids = [
                source.object.entity_id
                for source in sources
                if isinstance(source.object, MappingModeledEntity)
                and source.object.entity_type == "logical_entity"
            ]
            upstream_physical_rows = (
                await transaction.fetch_all(
                    _MAPPING_UPSTREAM_PHYSICAL_CONTEXT_SQL,
                    (
                        plan.pair.modeled_entity_id,
                        plan.model_id,
                        plan.model_id,
                        plan.pair.source_system_id,
                    ),
                )
                if logical_ids and plan.route == "dimensional_to_gold"
                else []
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
            if logical_ids:
                upstream_template_rows = await transaction.fetch_all(
                    _MAPPING_UPSTREAM_TEMPLATE_IDS_SQL,
                    (plan.model_id, logical_ids, plan.pair.source_system_id),
                )
                referenced_template_ids.update(
                    row["output_template_id"] for row in upstream_template_rows
                )
            template_rows = (
                await transaction.fetch_all(
                    _MAPPING_OUTPUT_TEMPLATE_CONTEXT_SQL,
                    (sorted(referenced_template_ids),),
                )
                if referenced_template_ids
                else []
            )
            authoring: dict[str, Any] = MappingAuthoringPolicy.model_validate(
                anchor.get("authoring"), strict=False
            ).model_dump(mode="json")
            family = "logical" if plan.modeled_entity_type == "logical_entity" else "dimensional"
            authoring["naming_instructions"] = effective_naming_instructions(
                family, authoring["naming_instructions"]
            )
            authoring["audit_columns_template"] = effective_audit_template(
                authoring["audit_columns_template"]
            )
            if family == "dimensional":
                authoring["technical_columns_template"], _ = effective_gold_templates(
                    authoring["technical_columns_template"], authoring["audit_columns_template"]
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
                    "target": parsed_header.modeled_entity,
                    "sources": sources,
                    "upstream_physical_sources": [
                        row.get("source") for row in upstream_physical_rows
                    ],
                    "headers": [parsed_header],
                    "authoring": authoring,
                },
                strict=False,
            )
            return context
        except MappingRunContextUnavailableError:
            raise
        except TypeError, ValueError, ValidationError:
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
