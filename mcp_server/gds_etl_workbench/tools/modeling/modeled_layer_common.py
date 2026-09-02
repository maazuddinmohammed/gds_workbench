"""Shared SQL builders for Logical and Dimensional layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import LiteralString, cast


@dataclass(frozen=True, slots=True)
class LayerConfig:
    layer: str
    submodel_fields: tuple[str, ...]
    entity_fields: tuple[str, ...]
    attribute_fields: tuple[str, ...]
    relationship_fields: tuple[str, ...]
    entity_source_role_column: str | None

    @property
    def submodel_table(self) -> str:
        return f"workflow.{self.layer}_submodel"

    @property
    def entity_table(self) -> str:
        return f"workflow.{self.layer}_entity"

    @property
    def membership_table(self) -> str:
        return f"workflow.{self.layer}_entity_submodel"

    @property
    def attribute_table(self) -> str:
        return f"workflow.{self.layer}_attribute"

    @property
    def entity_source_table(self) -> str:
        return f"workflow.{self.layer}_entity_source_mapping"

    @property
    def attribute_source_table(self) -> str:
        return f"workflow.{self.layer}_attribute_source_mapping"

    @property
    def relationship_table(self) -> str:
        return f"workflow.{self.layer}_relationship"

    @property
    def submodel_id(self) -> str:
        return f"{self.layer}_submodel_id"

    @property
    def entity_id(self) -> str:
        return f"{self.layer}_entity_id"

    @property
    def attribute_id(self) -> str:
        return f"{self.layer}_attribute_id"

    @property
    def relationship_id(self) -> str:
        return f"{self.layer}_relationship_id"


LOGICAL = LayerConfig(
    layer="logical",
    submodel_fields=(
        "logical_submodel_name",
        "logical_submodel_definition",
        "logical_submodel_status",
        "logical_submodel_is_locked",
    ),
    entity_fields=(
        "logical_entity_name",
        "logical_entity_definition",
        "logical_entity_type",
        "logical_entity_type_detail",
        "logical_entity_grain",
        "logical_entity_dependency_order",
        "logical_entity_confidence",
        "logical_entity_status",
        "logical_entity_is_locked",
    ),
    attribute_fields=(
        "logical_attribute_name",
        "logical_attribute_definition",
        "logical_attribute_data_type",
        "logical_attribute_is_nullable",
        "logical_attribute_is_primary_key",
        "logical_attribute_is_natural_key",
        "logical_attribute_is_surrogate_key",
        "logical_attribute_ordinal_position",
        "logical_attribute_is_audit_column",
        "logical_attribute_status",
        "logical_attribute_is_locked",
    ),
    relationship_fields=(
        "logical_relationship_name",
        "logical_relationship_definition",
        "logical_relationship_cardinality",
        "logical_relationship_confidence",
        "logical_relationship_basis",
        "logical_relationship_cardinality_basis",
        "logical_relationship_status",
        "logical_relationship_is_locked",
    ),
    entity_source_role_column=None,
)

DIMENSIONAL = LayerConfig(
    layer="dimensional",
    submodel_fields=(
        "dimensional_submodel_name",
        "dimensional_submodel_definition",
        "dimensional_submodel_status",
        "dimensional_submodel_is_locked",
    ),
    entity_fields=(
        "dimensional_entity_name",
        "dimensional_entity_definition",
        "dimensional_entity_type",
        "dimensional_fact_type",
        "dimensional_entity_grain_definition",
        "dimensional_entity_dependency_order",
        "dimensional_entity_confidence",
        "dimensional_entity_status",
        "dimensional_entity_is_locked",
    ),
    attribute_fields=(
        "dimensional_attribute_name",
        "dimensional_attribute_definition",
        "dimensional_attribute_data_type",
        "dimensional_attribute_is_nullable",
        "dimensional_attribute_ordinal_position",
        "dimensional_attribute_role",
        "dimensional_attribute_key_role",
        "dimensional_attribute_is_grain_component",
        "dimensional_attribute_additivity",
        "dimensional_attribute_default_aggregation",
        "dimensional_attribute_aggregation_basis",
        "dimensional_attribute_change_behavior",
        "dimensional_attribute_is_audit_column",
        "dimensional_attribute_confidence",
        "dimensional_attribute_status",
        "dimensional_attribute_is_locked",
    ),
    relationship_fields=(
        "dimensional_relationship_name",
        "dimensional_relationship_definition",
        "dimensional_relationship_kind",
        "dimensional_relationship_cardinality",
        "dimensional_relationship_is_optional",
        "dimensional_relationship_role_name",
        "dimensional_relationship_confidence",
        "dimensional_relationship_basis",
        "dimensional_relationship_cardinality_basis",
        "dimensional_relationship_status",
        "dimensional_relationship_is_locked",
    ),
    entity_source_role_column="dimensional_entity_source_role",
)


def submodels_sql(config: LayerConfig) -> LiteralString:
    selected = _select_fields("submodel", config.submodel_fields)
    return cast(
        LiteralString,
        f"""
SELECT submodel.{config.submodel_id},
       {selected},
       count(DISTINCT membership.{config.entity_id}) FILTER (
           WHERE membership.{config.layer}_entity_submodel_status
               = 'active'
       ) AS entity_count
  FROM {config.submodel_table} AS submodel
  LEFT JOIN {config.membership_table} AS membership
    ON membership.model_id = submodel.model_id
   AND membership.{config.submodel_id} = submodel.{config.submodel_id}
 WHERE submodel.model_id = %s
 GROUP BY submodel.{config.submodel_id}
 ORDER BY lower(submodel.{config.layer}_submodel_name), submodel.{config.submodel_id}
 LIMIT %s OFFSET %s
""",
    )


def entities_sql(config: LayerConfig) -> LiteralString:
    selected = _select_fields("entity", config.entity_fields)
    eligibility_field = (
        "is_model_input_eligible" if config.layer == "logical" else "is_dimensional_source_eligible"
    )
    role_field = (
        f"'source_role', source.{config.entity_source_role_column},"
        if config.entity_source_role_column is not None
        else ""
    )
    return cast(
        LiteralString,
        f"""
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_objects AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_object_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT entity.{config.entity_id},
       {selected},
       COALESCE((
           SELECT jsonb_agg(jsonb_build_object(
                      'entity_submodel_id', membership.{config.layer}_entity_submodel_id,
                      'submodel_id', submodel.{config.submodel_id},
                      'submodel_name', submodel.{config.layer}_submodel_name,
                      'membership_status',
                          membership.{config.layer}_entity_submodel_status,
                      'membership_is_locked',
                          membership.{config.layer}_entity_submodel_is_locked
                  ) ORDER BY lower(submodel.{config.layer}_submodel_name))
             FROM {config.membership_table} AS membership
             JOIN {config.submodel_table} AS submodel
               ON submodel.model_id = membership.model_id
              AND submodel.{config.submodel_id} = membership.{config.submodel_id}
            WHERE membership.model_id = entity.model_id
              AND membership.{config.entity_id} = entity.{config.entity_id}
       ), '[]'::JSONB) AS submodels,
       COALESCE((
           SELECT jsonb_agg(
                      CASE source.support_source_type
                          WHEN 'object' THEN jsonb_build_object(
                              'entity_source_mapping_id',
                                  source.{config.layer}_entity_source_mapping_id,
                              'support_source_type', 'object',
                              'source_object', jsonb_build_object(
                                  'object_id', source_object.object_id,
                                  'tenant_code', source_tenant.tenant_code,
                                  'system_code', source_system.system_code,
                                  'connection_code', source_connection.connection_code,
                                  'object_schema', source_object.object_schema,
                                  'object_name', source_object.object_name
                              ),
                              {role_field}
                              'source_order',
                                  source.{config.layer}_entity_source_mapping_order,
                              'rationale',
                                  source.{config.layer}_entity_source_mapping_rationale,
                              'status',
                                  source.{config.layer}_entity_source_mapping_status,
                              'is_locked',
                                  source.{config.layer}_entity_source_mapping_is_locked
                          )
                          ELSE jsonb_build_object(
                              'entity_source_mapping_id',
                                  source.{config.layer}_entity_source_mapping_id,
                              'support_source_type', 'assertion',
                              'assertion_record', jsonb_build_object(
                                  'modeling_assertion_record_id',
                                      assertion_record.modeling_assertion_record_id,
                                  'modeling_assertion_record_key',
                                      assertion_record.modeling_assertion_record_key
                              ),
                              {role_field}
                              'source_order',
                                  source.{config.layer}_entity_source_mapping_order,
                              'rationale',
                                  source.{config.layer}_entity_source_mapping_rationale,
                              'status',
                                  source.{config.layer}_entity_source_mapping_status,
                              'is_locked',
                                  source.{config.layer}_entity_source_mapping_is_locked
                          )
                      END ORDER BY source.{config.layer}_entity_source_mapping_id
                  )
             FROM {config.entity_source_table} AS source
             LEFT JOIN core.object AS source_object
               ON source_object.object_id = source.source_object_id
             LEFT JOIN core.connection AS source_connection
               ON source_connection.connection_id = source_object.connection_id
             LEFT JOIN eligible_objects AS source_eligibility
               ON source_eligibility.object_id = source.source_object_id
              AND source_eligibility.model_id = source.model_id
              AND source_eligibility.{eligibility_field}
             LEFT JOIN core.tenant AS source_tenant
               ON source_tenant.tenant_id = source_connection.tenant_id
             LEFT JOIN core.system AS source_system
               ON source_system.system_id = source_connection.system_id
             LEFT JOIN model.modeling_assertion_record AS assertion_record
               ON assertion_record.modeling_assertion_record_id
                    = source.modeling_assertion_record_id
              AND assertion_record.model_id = source.model_id
            WHERE source.model_id = entity.model_id
              AND source.{config.entity_id} = entity.{config.entity_id}
              AND (
                  source.support_source_type <> 'object'
                  OR EXISTS (
                      SELECT 1
                        FROM eligible_objects AS eligibility
                       WHERE eligibility.object_id = source.source_object_id
                         AND eligibility.model_id = source.model_id
                         AND eligibility.{eligibility_field}
                  )
              )
       ), '[]'::JSONB) AS sources
  FROM {config.entity_table} AS entity
 WHERE entity.model_id = (SELECT model_id FROM requested_model)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR EXISTS (
           SELECT 1
             FROM {config.entity_source_table} AS selected_source
            WHERE selected_source.model_id = entity.model_id
              AND selected_source.{config.entity_id} = entity.{config.entity_id}
              AND selected_source.support_source_type = 'object'
              AND selected_source.source_object_id = ANY(%s::BIGINT[])
              AND EXISTS (
                  SELECT 1
                    FROM eligible_objects AS eligibility
                   WHERE eligibility.object_id = selected_source.source_object_id
                     AND eligibility.model_id = selected_source.model_id
                     AND eligibility.{eligibility_field}
              )
       )
   )
 ORDER BY entity.{config.layer}_entity_dependency_order,
          lower(entity.{config.layer}_entity_name),
          entity.{config.entity_id}
 LIMIT %s OFFSET %s
""",
    )


def attributes_sql(config: LayerConfig) -> LiteralString:
    selected = _select_fields("attribute", config.attribute_fields)
    eligibility_field = (
        "is_model_input_eligible" if config.layer == "logical" else "is_dimensional_source_eligible"
    )
    return cast(
        LiteralString,
        f"""
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_attribute_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT attribute.{config.attribute_id},
       attribute.{config.entity_id},
       entity.{config.layer}_entity_name,
       {selected},
       COALESCE((
           SELECT jsonb_agg(
                      CASE source.support_source_type
                          WHEN 'attribute' THEN jsonb_build_object(
                              'attribute_source_mapping_id',
                                  source.{config.layer}_attribute_source_mapping_id,
                              'entity_source_mapping_id',
                                  source.{config.layer}_entity_source_mapping_id,
                              'support_source_type', 'attribute',
                              'source_attribute', jsonb_build_object(
                                  'object_id', source_object.object_id,
                                  'attribute_id', source_attribute.attribute_id,
                                  'tenant_code', source_tenant.tenant_code,
                                  'system_code', source_system.system_code,
                                  'connection_code', source_connection.connection_code,
                                  'object_schema', source_object.object_schema,
                                  'object_name', source_object.object_name,
                                  'attribute_name', source_attribute.attribute_name
                              ),
                              'source_order',
                                  source.{config.layer}_attribute_source_mapping_order,
                              'rationale',
                                  source.{config.layer}_attribute_source_mapping_rationale,
                              'status',
                                  source.{config.layer}_attribute_source_mapping_status,
                              'is_locked',
                                  source.{config.layer}_attribute_source_mapping_is_locked
                          )
                          ELSE jsonb_build_object(
                              'attribute_source_mapping_id',
                                  source.{config.layer}_attribute_source_mapping_id,
                              'support_source_type', 'assertion',
                              'assertion_record', jsonb_build_object(
                                  'modeling_assertion_record_id',
                                      assertion_record.modeling_assertion_record_id,
                                  'modeling_assertion_record_key',
                                      assertion_record.modeling_assertion_record_key
                              ),
                              'source_order',
                                  source.{config.layer}_attribute_source_mapping_order,
                              'rationale',
                                  source.{config.layer}_attribute_source_mapping_rationale,
                              'status',
                                  source.{config.layer}_attribute_source_mapping_status,
                              'is_locked',
                                  source.{config.layer}_attribute_source_mapping_is_locked
                          )
                      END ORDER BY source.{config.layer}_attribute_source_mapping_id
                  )
             FROM {config.attribute_source_table} AS source
             LEFT JOIN core.object AS source_object
               ON source_object.object_id = source.source_object_id
             LEFT JOIN core.attribute AS source_attribute
               ON source_attribute.attribute_id = source.source_attribute_id
              AND source_attribute.object_id = source.source_object_id
             LEFT JOIN core.connection AS source_connection
               ON source_connection.connection_id = source_object.connection_id
             LEFT JOIN eligible_attributes AS source_eligibility
               ON source_eligibility.object_id = source.source_object_id
              AND source_eligibility.attribute_id = source.source_attribute_id
              AND source_eligibility.model_id = source.model_id
              AND source_eligibility.{eligibility_field}
             LEFT JOIN core.tenant AS source_tenant
               ON source_tenant.tenant_id = source_connection.tenant_id
             LEFT JOIN core.system AS source_system
               ON source_system.system_id = source_connection.system_id
             LEFT JOIN model.modeling_assertion_record AS assertion_record
               ON assertion_record.modeling_assertion_record_id
                    = source.modeling_assertion_record_id
              AND assertion_record.model_id = source.model_id
            WHERE source.model_id = attribute.model_id
              AND source.{config.attribute_id} = attribute.{config.attribute_id}
              AND (
                  source.support_source_type <> 'attribute'
                  OR EXISTS (
                      SELECT 1
                        FROM eligible_attributes AS eligibility
                       WHERE eligibility.object_id = source.source_object_id
                         AND eligibility.attribute_id = source.source_attribute_id
                         AND eligibility.model_id = source.model_id
                         AND eligibility.{eligibility_field}
                  )
              )
       ), '[]'::JSONB) AS sources
  FROM {config.attribute_table} AS attribute
  JOIN {config.entity_table} AS entity
    ON entity.{config.entity_id} = attribute.{config.entity_id}
   AND entity.model_id = attribute.model_id
 WHERE attribute.model_id = (SELECT model_id FROM requested_model)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR attribute.{config.entity_id} = ANY(%s::BIGINT[])
   )
 ORDER BY lower(entity.{config.layer}_entity_name),
          attribute.{config.layer}_attribute_ordinal_position,
          attribute.{config.attribute_id}
 LIMIT %s OFFSET %s
""",
    )


def relationships_sql(config: LayerConfig) -> LiteralString:
    selected = _select_fields("relationship", config.relationship_fields)
    return cast(
        LiteralString,
        f"""
SELECT relationship.{config.relationship_id},
       relationship.{config.layer}_relationship_from_entity_id
           AS from_{config.layer}_entity_id,
       from_entity.{config.layer}_entity_name AS from_{config.layer}_entity_name,
       relationship.{config.layer}_relationship_from_attribute_id
           AS from_{config.layer}_attribute_id,
       from_attribute.{config.layer}_attribute_name
           AS from_{config.layer}_attribute_name,
       relationship.{config.layer}_relationship_to_entity_id
           AS to_{config.layer}_entity_id,
       to_entity.{config.layer}_entity_name AS to_{config.layer}_entity_name,
       relationship.{config.layer}_relationship_to_attribute_id
           AS to_{config.layer}_attribute_id,
       to_attribute.{config.layer}_attribute_name AS to_{config.layer}_attribute_name,
       {selected}
  FROM {config.relationship_table} AS relationship
  JOIN {config.entity_table} AS from_entity
    ON from_entity.{config.entity_id}
        = relationship.{config.layer}_relationship_from_entity_id
   AND from_entity.model_id = relationship.model_id
  JOIN {config.attribute_table} AS from_attribute
    ON from_attribute.{config.attribute_id}
        = relationship.{config.layer}_relationship_from_attribute_id
   AND from_attribute.{config.entity_id}
        = relationship.{config.layer}_relationship_from_entity_id
   AND from_attribute.model_id = relationship.model_id
  JOIN {config.entity_table} AS to_entity
    ON to_entity.{config.entity_id}
        = relationship.{config.layer}_relationship_to_entity_id
   AND to_entity.model_id = relationship.model_id
  JOIN {config.attribute_table} AS to_attribute
    ON to_attribute.{config.attribute_id}
        = relationship.{config.layer}_relationship_to_attribute_id
   AND to_attribute.{config.entity_id}
        = relationship.{config.layer}_relationship_to_entity_id
   AND to_attribute.model_id = relationship.model_id
 WHERE relationship.model_id = %s
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR relationship.{config.layer}_relationship_from_entity_id = ANY(%s::BIGINT[])
       OR relationship.{config.layer}_relationship_to_entity_id = ANY(%s::BIGINT[])
   )
 ORDER BY relationship.{config.layer}_relationship_from_entity_id,
          relationship.{config.layer}_relationship_to_entity_id,
          lower(relationship.{config.layer}_relationship_name),
          relationship.{config.relationship_id}
 LIMIT %s OFFSET %s
""",
    )


def _select_fields(alias: str, fields: tuple[str, ...]) -> str:
    return ",\n       ".join(f"{alias}.{field}" for field in fields)
