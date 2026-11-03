"""Shared SQL builders for Logical and Dimensional layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import LiteralString, cast


@dataclass(frozen=True, slots=True)
class LayerConfig:
    layer: str
    entity_fields: tuple[str, ...]
    attribute_fields: tuple[str, ...]
    relationship_fields: tuple[str, ...]

    @property
    def entity_table(self) -> str:
        return f"workflow.{self.layer}_entity"

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
    entity_fields=(
        "logical_entity_schema_name",
        "logical_entity_name",
        "logical_entity_definition",
        "logical_entity_type",
        "logical_entity_grain",
        "logical_entity_dependency_order",
        "logical_entity_is_active",
        "logical_entity_is_locked",
    ),
    attribute_fields=(
        "logical_attribute_name",
        "logical_attribute_definition",
        "logical_attribute_data_type",
        "logical_attribute_is_nullable",
        "logical_attribute_is_natural_key",
        "logical_attribute_is_surrogate_key",
        "logical_attribute_ordinal_position",
        "logical_attribute_is_audit_column",
        "logical_attribute_is_active",
        "logical_attribute_is_locked",
    ),
    relationship_fields=(
        "logical_relationship_cardinality",
        "logical_relationship_basis",
        "logical_relationship_is_active",
        "logical_relationship_is_locked",
    ),
)

DIMENSIONAL = LayerConfig(
    layer="dimensional",
    entity_fields=(
        "dimensional_entity_schema_name",
        "dimensional_entity_name",
        "dimensional_entity_definition",
        "dimensional_entity_type",
        "dimensional_fact_type",
        "dimensional_entity_grain_definition",
        "dimensional_entity_dependency_order",
        "dimensional_entity_is_active",
        "dimensional_entity_is_locked",
    ),
    attribute_fields=(
        "dimensional_attribute_name",
        "dimensional_attribute_definition",
        "dimensional_attribute_data_type",
        "dimensional_attribute_is_nullable",
        "dimensional_attribute_ordinal_position",
        "dimensional_attribute_is_natural_key",
        "dimensional_attribute_is_surrogate_key",
        "dimensional_attribute_is_audit_column",
        "dimensional_attribute_is_active",
        "dimensional_attribute_is_locked",
    ),
    relationship_fields=(
        "dimensional_relationship_role_name",
        "dimensional_relationship_basis",
        "dimensional_relationship_is_active",
        "dimensional_relationship_is_locked",
    ),
)

# Read-only label lists. Inactive codes stay listed so applied history still resolves;
# Change Set validation accepts only active codes for new or changed records.
LOGICAL_ENTITY_TYPES_SQL: LiteralString = """
SELECT logical_entity_type_code,
       logical_entity_type_description,
       logical_entity_type_is_active
  FROM reference.logical_entity_type
 ORDER BY logical_entity_type_code
 LIMIT %s OFFSET %s
"""

DIMENSIONAL_FACT_TYPES_SQL: LiteralString = """
SELECT dimensional_fact_type_code,
       dimensional_fact_type_description,
       dimensional_fact_type_is_active
  FROM reference.dimensional_fact_type
 ORDER BY dimensional_fact_type_code
 LIMIT %s OFFSET %s
"""


# Source mapping rows store no source type. The filled id says which kind a source is,
# so every query below derives the record's support_source_type from context_record_id.
def entities_sql(config: LayerConfig, *, historical: bool = False) -> LiteralString:
    if config.layer == "dimensional":
        return _dimensional_records_sql(attributes=False, historical=historical)
    selected = _select_fields("entity", config.entity_fields)
    eligibility_field = "is_project_input_eligible"
    # Snapshot evidence requires ownership and existence, independent of authoring eligibility.
    object_scope = (
        """
    SELECT project.project_id, object.object_id,
           TRUE AS is_project_input_eligible
      FROM requested_project
      JOIN project.project AS project USING (project_id)
      JOIN core.object AS object ON object.source_tenant_id = project.tenant_id
        OR (object.source_tenant_id = ANY(%s::BIGINT[])
            AND EXISTS (SELECT 1 FROM project.project_input_scope AS retained_scope
                         WHERE retained_scope.project_id = project.project_id
                           AND retained_scope.object_id = object.object_id))
"""
        if historical
        else """
    SELECT eligibility.*
      FROM requested_project
      CROSS JOIN LATERAL workflow.list_project_object_eligibility(
          requested_project.project_id
      ) AS eligibility
"""
    )
    return cast(
        LiteralString,
        f"""
WITH requested_project AS (
    SELECT %s::BIGINT AS project_id
),
eligible_objects AS MATERIALIZED (
    {object_scope}
)
SELECT entity.{config.entity_id},
       {selected},
       COALESCE((
           SELECT jsonb_agg(
                      jsonb_build_object(
                          'entity_source_mapping_id',
                              source.{config.layer}_entity_source_mapping_id,
                          'rationale', source.{config.layer}_entity_source_mapping_rationale,
                          'is_active', source.{config.layer}_entity_source_mapping_is_active,
                          'is_locked', source.{config.layer}_entity_source_mapping_is_locked
                      ) || CASE WHEN source.context_record_id IS NULL THEN jsonb_build_object(
                          'support_source_type', 'object',
                          'source_object', jsonb_build_object(
                              'object_id', source_object.object_id,
                              'tenant_code', source_tenant.tenant_code,
                              'system_code', source_system.system_code,
                              'connection_code', source_connection.connection_code,
                              'object_schema', source_object.object_schema,
                              'object_name', source_object.object_name
                          )
                      ) ELSE jsonb_build_object(
                          'support_source_type', 'context_record',
                          'context_record', jsonb_build_object(
                              'context_record_id', context_record.context_record_id
                          )
                      ) END ORDER BY source.{config.layer}_entity_source_mapping_id
                  )
             FROM {config.entity_source_table} AS source
             LEFT JOIN core.object AS source_object
               ON source_object.object_id = source.source_object_id
             LEFT JOIN core.connection AS source_connection
               ON source_connection.connection_id = source_object.connection_id
             LEFT JOIN eligible_objects AS source_eligibility
               ON source_eligibility.object_id = source.source_object_id
              AND source_eligibility.project_id = source.project_id
              AND source_eligibility.{eligibility_field}
             LEFT JOIN core.tenant AS source_tenant
               ON source_tenant.tenant_id = source_connection.tenant_id
             LEFT JOIN core.system AS source_system
               ON source_system.system_id = source_connection.system_id
             LEFT JOIN project.context_record AS context_record
               ON context_record.context_record_id
                    = source.context_record_id
              AND context_record.project_id = source.project_id
            WHERE source.project_id = entity.project_id
              AND source.{config.entity_id} = entity.{config.entity_id}
              AND (
                  source.source_object_id IS NULL
                  OR EXISTS (
                      SELECT 1
                        FROM eligible_objects AS eligibility
                       WHERE eligibility.object_id = source.source_object_id
                         AND eligibility.project_id = source.project_id
                         AND eligibility.{eligibility_field}
                  )
              )
       ), '[]'::JSONB) AS sources
  FROM {config.entity_table} AS entity
 WHERE entity.project_id = (SELECT project_id FROM requested_project)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR EXISTS (
           SELECT 1
             FROM {config.entity_source_table} AS selected_source
            WHERE selected_source.project_id = entity.project_id
              AND selected_source.{config.entity_id} = entity.{config.entity_id}
              AND selected_source.source_object_id = ANY(%s::BIGINT[])
              AND EXISTS (
                  SELECT 1
                    FROM eligible_objects AS eligibility
                   WHERE eligibility.object_id = selected_source.source_object_id
                     AND eligibility.project_id = selected_source.project_id
                     AND eligibility.{eligibility_field}
              )
       )
   )
 ORDER BY entity.{config.layer}_entity_dependency_order,
          lower(entity.{config.layer}_entity_schema_name),
          lower(entity.{config.layer}_entity_name),
          entity.{config.entity_id}
 LIMIT %s OFFSET %s
""",
    )


def attributes_sql(config: LayerConfig, *, historical: bool = False) -> LiteralString:
    if config.layer == "dimensional":
        return _dimensional_records_sql(attributes=True, historical=historical)
    selected = _select_fields("attribute", config.attribute_fields)
    eligibility_field = "is_project_input_eligible"
    attribute_scope = (
        """
    SELECT project.project_id, object.object_id, attribute.attribute_id,
           TRUE AS is_project_input_eligible
      FROM requested_project
      JOIN project.project AS project USING (project_id)
      JOIN core.object AS object ON object.source_tenant_id = project.tenant_id
        OR (object.source_tenant_id = ANY(%s::BIGINT[])
            AND EXISTS (SELECT 1 FROM project.project_input_scope AS retained_scope
                         WHERE retained_scope.project_id = project.project_id
                           AND retained_scope.object_id = object.object_id))
      JOIN core.attribute AS attribute ON attribute.object_id = object.object_id
"""
        if historical
        else """
    SELECT eligibility.*
      FROM requested_project
      CROSS JOIN LATERAL workflow.list_project_attribute_eligibility(
          requested_project.project_id
      ) AS eligibility
"""
    )
    return cast(
        LiteralString,
        f"""
WITH requested_project AS (
    SELECT %s::BIGINT AS project_id
),
eligible_attributes AS MATERIALIZED (
    {attribute_scope}
)
SELECT attribute.{config.attribute_id},
       attribute.{config.entity_id},
       entity.{config.layer}_entity_schema_name,
       entity.{config.layer}_entity_name,
       {selected},
       COALESCE((
           SELECT jsonb_agg(
                      jsonb_build_object(
                          'attribute_source_mapping_id',
                              source.{config.layer}_attribute_source_mapping_id,
                          'rationale', source.{config.layer}_attribute_source_mapping_rationale,
                          'is_active', source.{config.layer}_attribute_source_mapping_is_active,
                          'is_locked', source.{config.layer}_attribute_source_mapping_is_locked
                      ) || CASE WHEN source.context_record_id IS NULL THEN jsonb_build_object(
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
                          )
                      ) ELSE jsonb_build_object(
                          'support_source_type', 'context_record',
                          'context_record', jsonb_build_object(
                              'context_record_id', context_record.context_record_id
                          )
                      ) END ORDER BY source.{config.layer}_attribute_source_mapping_id
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
              AND source_eligibility.project_id = source.project_id
              AND source_eligibility.{eligibility_field}
             LEFT JOIN core.tenant AS source_tenant
               ON source_tenant.tenant_id = source_connection.tenant_id
             LEFT JOIN core.system AS source_system
               ON source_system.system_id = source_connection.system_id
             LEFT JOIN project.context_record AS context_record
               ON context_record.context_record_id
                    = source.context_record_id
              AND context_record.project_id = source.project_id
            WHERE source.project_id = attribute.project_id
              AND source.{config.attribute_id} = attribute.{config.attribute_id}
              AND (
                  source.source_attribute_id IS NULL
                  OR EXISTS (
                      SELECT 1
                        FROM eligible_attributes AS eligibility
                       WHERE eligibility.object_id = source.source_object_id
                         AND eligibility.attribute_id = source.source_attribute_id
                         AND eligibility.project_id = source.project_id
                         AND eligibility.{eligibility_field}
                  )
              )
       ), '[]'::JSONB) AS sources
  FROM {config.attribute_table} AS attribute
  JOIN {config.entity_table} AS entity
    ON entity.{config.entity_id} = attribute.{config.entity_id}
   AND entity.project_id = attribute.project_id
 WHERE attribute.project_id = (SELECT project_id FROM requested_project)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR attribute.{config.entity_id} = ANY(%s::BIGINT[])
   )
 ORDER BY lower(entity.{config.layer}_entity_schema_name),
          lower(entity.{config.layer}_entity_name),
          attribute.{config.layer}_attribute_ordinal_position,
          attribute.{config.attribute_id}
 LIMIT %s OFFSET %s
""",
    )


def relationships_sql(config: LayerConfig) -> LiteralString:
    """Child -> parent links; one per foreign-key (from) Attribute."""
    selected = _select_fields("relationship", config.relationship_fields)
    return cast(
        LiteralString,
        f"""
SELECT relationship.{config.relationship_id},
       relationship.{config.layer}_relationship_from_entity_id
           AS from_{config.layer}_entity_id,
       from_entity.{config.layer}_entity_schema_name AS from_{config.layer}_entity_schema_name,
       from_entity.{config.layer}_entity_name AS from_{config.layer}_entity_name,
       relationship.{config.layer}_relationship_from_attribute_id
           AS from_{config.layer}_attribute_id,
       from_attribute.{config.layer}_attribute_name
           AS from_{config.layer}_attribute_name,
       relationship.{config.layer}_relationship_to_entity_id
           AS to_{config.layer}_entity_id,
       to_entity.{config.layer}_entity_schema_name AS to_{config.layer}_entity_schema_name,
       to_entity.{config.layer}_entity_name AS to_{config.layer}_entity_name,
       relationship.{config.layer}_relationship_to_attribute_id
           AS to_{config.layer}_attribute_id,
       to_attribute.{config.layer}_attribute_name AS to_{config.layer}_attribute_name,
       {selected}
  FROM {config.relationship_table} AS relationship
  JOIN {config.entity_table} AS from_entity
    ON from_entity.{config.entity_id}
        = relationship.{config.layer}_relationship_from_entity_id
   AND from_entity.project_id = relationship.project_id
  JOIN {config.attribute_table} AS from_attribute
    ON from_attribute.{config.attribute_id}
        = relationship.{config.layer}_relationship_from_attribute_id
   AND from_attribute.{config.entity_id}
        = relationship.{config.layer}_relationship_from_entity_id
   AND from_attribute.project_id = relationship.project_id
  JOIN {config.entity_table} AS to_entity
    ON to_entity.{config.entity_id}
        = relationship.{config.layer}_relationship_to_entity_id
   AND to_entity.project_id = relationship.project_id
  JOIN {config.attribute_table} AS to_attribute
    ON to_attribute.{config.attribute_id}
        = relationship.{config.layer}_relationship_to_attribute_id
   AND to_attribute.{config.entity_id}
        = relationship.{config.layer}_relationship_to_entity_id
   AND to_attribute.project_id = relationship.project_id
 WHERE relationship.project_id = %s
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR relationship.{config.layer}_relationship_from_entity_id = ANY(%s::BIGINT[])
       OR relationship.{config.layer}_relationship_to_entity_id = ANY(%s::BIGINT[])
   )
 ORDER BY relationship.{config.layer}_relationship_from_entity_id,
          relationship.{config.layer}_relationship_from_attribute_id,
          relationship.{config.relationship_id}
 LIMIT %s OFFSET %s
""",
    )


def _dimensional_records_sql(*, attributes: bool, historical: bool) -> LiteralString:
    """Read modeled Logical lineage without requiring physical target registration."""
    kind = "attribute" if attributes else "entity"
    record = "attribute" if attributes else "entity"
    source_kind = "logical_attribute" if attributes else "logical_entity"
    fields = _select_fields(
        record, DIMENSIONAL.attribute_fields if attributes else DIMENSIONAL.entity_fields
    )
    identity = (
        "attribute.dimensional_attribute_id, attribute.dimensional_entity_id, "
        "entity.dimensional_entity_schema_name, entity.dimensional_entity_name,"
        if attributes
        else "entity.dimensional_entity_id,"
    )
    key_attribute = (
        ",'logical_attribute_id', logical_attribute.logical_attribute_id, "
        "'logical_attribute_name', logical_attribute.logical_attribute_name"
        if attributes
        else ""
    )
    source_attribute_join = (
        ""
        if not attributes
        else """
             LEFT JOIN workflow.logical_attribute AS logical_attribute
               ON logical_attribute.logical_attribute_id = source.source_logical_attribute_id
              AND logical_attribute.logical_entity_id = source.source_logical_entity_id
              AND logical_attribute.project_id = source.project_id
"""
    )
    active_source = (
        "TRUE"
        if historical
        else (
            "logical_entity.logical_entity_is_active"
            + (" AND logical_attribute.logical_attribute_is_active" if attributes else "")
        )
    )
    from_records = (
        "workflow.dimensional_attribute AS attribute JOIN workflow.dimensional_entity AS entity "
        "ON entity.dimensional_entity_id = attribute.dimensional_entity_id "
        "AND entity.project_id = attribute.project_id"
        if attributes
        else "workflow.dimensional_entity AS entity"
    )
    selection = (
        "attribute.dimensional_entity_id = ANY(%s::BIGINT[])"
        if attributes
        else """
       EXISTS (SELECT 1 FROM workflow.dimensional_entity_source_mapping AS selected_source
                WHERE selected_source.project_id = entity.project_id
                  AND selected_source.dimensional_entity_id = entity.dimensional_entity_id
                  AND selected_source.source_logical_entity_id = ANY(%s::BIGINT[]))
"""
    )
    order = (
        "lower(entity.dimensional_entity_schema_name), lower(entity.dimensional_entity_name), "
        "attribute.dimensional_attribute_ordinal_position, attribute.dimensional_attribute_id"
        if attributes
        else "entity.dimensional_entity_dependency_order, "
        "lower(entity.dimensional_entity_schema_name), "
        "lower(entity.dimensional_entity_name), entity.dimensional_entity_id"
    )
    return cast(
        LiteralString,
        f"""
SELECT {identity}
       {fields},
       COALESCE((
           SELECT jsonb_agg(
               jsonb_build_object(
                   '{kind}_source_mapping_id', source.dimensional_{kind}_source_mapping_id,
                   'rationale', source.dimensional_{kind}_source_mapping_rationale,
                   'is_active', source.dimensional_{kind}_source_mapping_is_active,
                   'is_locked', source.dimensional_{kind}_source_mapping_is_locked
               ) || CASE WHEN source.context_record_id IS NULL THEN jsonb_build_object(
                       'support_source_type', '{source_kind}',
                       'source_{source_kind}', jsonb_build_object(
                           'logical_entity_id', logical_entity.logical_entity_id,
                           'logical_entity_schema_name', logical_entity.logical_entity_schema_name,
                           'logical_entity_name', logical_entity.logical_entity_name
                           {key_attribute}
                       )
                   ) ELSE jsonb_build_object(
                       'support_source_type', 'context_record',
                       'context_record', jsonb_build_object(
                           'context_record_id',
                           context_record.context_record_id
                       )
                   ) END ORDER BY source.dimensional_{kind}_source_mapping_id
           )
             FROM workflow.dimensional_{kind}_source_mapping AS source
             LEFT JOIN workflow.logical_entity AS logical_entity
               ON logical_entity.logical_entity_id = source.source_logical_entity_id
              AND logical_entity.project_id = source.project_id
             {source_attribute_join}
             LEFT JOIN project.context_record AS context_record
               ON context_record.context_record_id =
                   source.context_record_id
              AND context_record.project_id = source.project_id
            WHERE source.project_id = {record}.project_id
              AND source.dimensional_{kind}_id = {record}.dimensional_{kind}_id
              AND (source.context_record_id IS NOT NULL OR ({active_source}))
       ), '[]'::JSONB) AS sources
  FROM {from_records}
 WHERE {record}.project_id = %s
   AND (cardinality(%s::BIGINT[]) = 0 OR {selection})
 ORDER BY {order}
 LIMIT %s OFFSET %s
""",
    )


def _select_fields(alias: str, fields: tuple[str, ...]) -> str:
    return ",\n       ".join(f"{alias}.{field}" for field in fields)
