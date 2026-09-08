-- Canonical Tenant-visible Object set. Source Tenant is authoritative even when
-- the physical Object is placed on a shared GDS Connection.
CREATE FUNCTION workflow.list_tenant_visible_objects(
    p_tenant_id BIGINT
)
RETURNS TABLE (
    object_id BIGINT,
    object_tenant_id BIGINT,
    is_owned_by_tenant BOOLEAN,
    is_on_global_connection BOOLEAN,
    is_copy_referenced BOOLEAN,
    is_process_referenced BOOLEAN,
    is_model_input_scope_referenced BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_tenant_visible_objects$
    WITH tenant_objects AS MATERIALIZED (
        SELECT object.object_id,
               object.source_tenant_id AS object_tenant_id,
               connection.is_global_data_store AS is_on_global_connection
          FROM core.tenant AS tenant
          JOIN core.object AS object
            ON object.source_tenant_id = tenant.tenant_id
          JOIN core.connection AS connection
            ON connection.connection_id = object.connection_id
         WHERE tenant.tenant_id = p_tenant_id
           AND tenant.is_active
    )
    SELECT tenant_object.object_id,
           tenant_object.object_tenant_id,
           TRUE AS is_owned_by_tenant,
           tenant_object.is_on_global_connection,
           EXISTS (
               SELECT 1
                 FROM core.copy_group AS copy_group
                 JOIN core.copy AS copy
                   ON copy.copy_group_id = copy_group.copy_group_id
                 JOIN core.ingestion_object_mapping AS mapping
                   ON mapping.ingestion_object_mapping_id =
                      copy.ingestion_object_mapping_id
                WHERE copy_group.tenant_id = p_tenant_id
                  AND tenant_object.object_id IN (
                      mapping.source_object_id,
                      mapping.target_object_id
                  )
           ) AS is_copy_referenced,
           EXISTS (
               SELECT 1
                 FROM core.process_group AS process_group
                 JOIN core.process AS process
                   ON process.process_group_id = process_group.process_group_id
                WHERE process_group.tenant_id = p_tenant_id
                  AND process.object_id = tenant_object.object_id
           ) AS is_process_referenced,
           EXISTS (
               SELECT 1
                 FROM model.model AS target_model
                 JOIN model.model_input_scope AS scope
                   ON scope.model_id = target_model.model_id
                  AND scope.is_active
                WHERE target_model.tenant_id = p_tenant_id
                  AND target_model.is_active
                  AND scope.object_id = tenant_object.object_id
           ) AS is_model_input_scope_referenced
      FROM tenant_objects AS tenant_object;
$list_tenant_visible_objects$;

REVOKE ALL ON FUNCTION workflow.list_tenant_visible_objects(BIGINT)
FROM PUBLIC;

-- Model Inputs are Source or Bronze Objects. Bound Silver and Gold Objects are
-- included separately as downstream targets and do not belong to Input Scope.
CREATE FUNCTION workflow.list_model_object_eligibility(
    p_model_id BIGINT
)
RETURNS TABLE (
    model_id BIGINT,
    object_id BIGINT,
    connection_id BIGINT,
    system_id BIGINT,
    object_tenant_id BIGINT,
    object_schema VARCHAR(400),
    object_name VARCHAR(400),
    zone_code TEXT,
    is_model_input_eligible BOOLEAN,
    is_dimensional_source_eligible BOOLEAN,
    is_logical_mapping_target_eligible BOOLEAN,
    is_dimensional_mapping_target_eligible BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_model_object_eligibility$
    WITH target_model AS MATERIALIZED (
        SELECT model.model_id,
               model.tenant_id
          FROM model.model AS model
          JOIN core.tenant AS tenant
            ON tenant.tenant_id = model.tenant_id
           AND tenant.is_active
         WHERE model.model_id = p_model_id
           AND model.is_active
    ), candidate_object AS MATERIALIZED (
        SELECT visible.object_id
          FROM target_model
          CROSS JOIN LATERAL workflow.list_tenant_visible_objects(
              target_model.tenant_id
          ) AS visible
    )
    SELECT target_model.model_id,
           object.object_id,
           connection.connection_id,
           system.system_id,
           object.source_tenant_id AS object_tenant_id,
           object.object_schema,
           object.object_name,
           lower(btrim(zone.zone_code)) AS zone_code,
           lower(btrim(zone.zone_code)) IN ('source', 'bronze')
               AS is_model_input_eligible,
           lower(btrim(zone.zone_code)) = 'silver'
           AND EXISTS (
               SELECT 1
                 FROM workflow.model_object_binding AS binding
                 JOIN workflow.mapping_object AS mapping
                   ON mapping.model_object_binding_id =
                      binding.model_object_binding_id
                  AND mapping.model_id = binding.model_id
                  AND mapping.object_mapping_status = 'active'
                  AND mapping.mapping_transformation_document IS NOT NULL
                 JOIN workflow.mapping_source_system_dependency AS dependency
                   ON dependency.model_id = mapping.model_id
                  AND dependency.modeled_entity_type =
                      binding.modeled_entity_type
                  AND dependency.source_system_id = mapping.source_system_id
                  AND dependency.mapping_source_system_dependency_status =
                      'active'
                 JOIN core.system AS source_system
                   ON source_system.system_id = mapping.source_system_id
                  AND source_system.is_active
                WHERE binding.model_id = target_model.model_id
                  AND binding.object_id = object.object_id
                  AND binding.modeled_entity_type = 'logical_entity'
                  AND binding.model_object_binding_status = 'active'
           ) AS is_dimensional_source_eligible,
           lower(btrim(zone.zone_code)) = 'silver'
               AS is_logical_mapping_target_eligible,
           lower(btrim(zone.zone_code)) = 'gold'
               AS is_dimensional_mapping_target_eligible
      FROM target_model
      JOIN candidate_object
        ON TRUE
      JOIN core.object AS object
        ON object.object_id = candidate_object.object_id
       AND object.source_tenant_id = target_model.tenant_id
       AND object.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = object.connection_id
       AND connection.is_active
      JOIN core.system AS system
        ON system.system_id = connection.system_id
       AND system.is_active
      JOIN reference.zone AS zone
        ON zone.zone_id = object.zone_id
       AND zone.is_active
     ORDER BY lower(btrim(system.system_code)),
              lower(btrim(object.object_schema)),
              lower(btrim(object.object_name)),
              object.object_id;
$list_model_object_eligibility$;

REVOKE ALL ON FUNCTION workflow.list_model_object_eligibility(BIGINT)
FROM PUBLIC;

-- Mapping and Code share the same executable physical-source selection. Scope
-- flags remain visible for readiness checks; callers own JSON assembly and bounds.
CREATE FUNCTION workflow.list_mapping_source_objects(
    p_model_id BIGINT,
    p_target_object_id BIGINT,
    p_modeled_entity_type VARCHAR(30),
    p_source_system_id BIGINT
)
RETURNS TABLE (
    source_mapping_id BIGINT,
    modeled_entity_id BIGINT,
    role TEXT,
    rationale TEXT,
    mapping_order INTEGER,
    is_locked BOOLEAN,
    source_object_id BIGINT,
    scope_is_locked BOOLEAN,
    scope_is_active BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_mapping_source_objects$
    WITH selected_binding AS MATERIALIZED (
        SELECT binding.*
          FROM workflow.model_object_binding AS binding
         WHERE binding.model_id = p_model_id
           AND binding.object_id = p_target_object_id
           AND binding.modeled_entity_type = p_modeled_entity_type
           AND binding.model_object_binding_status = 'active'
    ), source_reference AS MATERIALIZED (
        SELECT binding.model_id,
               binding.modeled_entity_type,
               source.logical_entity_source_mapping_id AS source_mapping_id,
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
        SELECT binding.model_id,
               binding.modeled_entity_type,
               source.dimensional_entity_source_mapping_id,
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
    SELECT source.source_mapping_id,
           source.modeled_entity_id,
           source.role,
           source.rationale,
           source.mapping_order,
           source.is_locked,
           source.source_object_id,
           CASE source.modeled_entity_type
               WHEN 'dimensional_entity' THEN
                   source_binding.model_object_binding_is_locked
               ELSE source_scope.model_input_scope_is_locked
           END AS scope_is_locked,
           CASE source.modeled_entity_type
               WHEN 'dimensional_entity' THEN
                   source_binding.model_object_binding_status = 'active'
               ELSE source_scope.is_active
           END AS scope_is_active
      FROM source_reference AS source
      JOIN core.object AS source_object
        ON source_object.object_id = source.source_object_id
      JOIN model.model AS source_model
        ON source_model.model_id = source.model_id
       AND source_object.source_tenant_id = source_model.tenant_id
      JOIN workflow.list_model_object_eligibility(p_model_id) AS eligibility
        ON eligibility.object_id = source_object.object_id
      LEFT JOIN model.model_input_scope AS source_scope
        ON source_scope.model_id = source.model_id
       AND source_scope.object_id = source_object.object_id
      LEFT JOIN workflow.model_object_binding AS source_binding
        ON source_binding.model_id = source.model_id
       AND source_binding.object_id = source_object.object_id
       AND source_binding.modeled_entity_type = 'logical_entity'
       AND source_binding.model_object_binding_status = 'active'
      JOIN core.connection AS source_connection
        ON source_connection.connection_id = source_object.connection_id
     WHERE (
               source.modeled_entity_type = 'logical_entity'
               AND source_scope.object_id IS NOT NULL
               AND eligibility.is_model_input_eligible
               AND (
                   (eligibility.zone_code = 'source'
                    AND source_connection.system_id = p_source_system_id)
                   OR (eligibility.zone_code = 'bronze' AND EXISTS (
                       SELECT 1
                         FROM core.ingestion_object_mapping AS ingestion
                         JOIN core.object AS original
                           ON original.object_id = ingestion.source_object_id
                         JOIN core.connection AS original_connection
                           ON original_connection.connection_id = original.connection_id
                        WHERE ingestion.target_object_id = source.source_object_id
                          AND ingestion.is_active
                          AND original_connection.system_id = p_source_system_id
                   ))
               )
           ) OR (
               source.modeled_entity_type = 'dimensional_entity'
               AND eligibility.is_dimensional_source_eligible
               AND source_binding.model_object_binding_id IS NOT NULL
               AND EXISTS (
                   SELECT 1
                     FROM workflow.mapping_object AS upstream
                     JOIN workflow.mapping_source_system_dependency AS dependency
                       ON dependency.model_id = upstream.model_id
                      AND dependency.modeled_entity_type = 'logical_entity'
                      AND dependency.source_system_id = upstream.source_system_id
                      AND dependency.mapping_source_system_dependency_status = 'active'
                     JOIN core.system AS upstream_system
                       ON upstream_system.system_id = upstream.source_system_id
                      AND upstream_system.is_active
                    WHERE upstream.model_id = source.model_id
                      AND upstream.model_object_binding_id =
                          source_binding.model_object_binding_id
                      AND upstream.source_system_id = p_source_system_id
                      AND upstream.object_mapping_status = 'active'
                      AND upstream.mapping_transformation_document IS NOT NULL
               )
           )
     ORDER BY source.mapping_order NULLS LAST, source.source_mapping_id;
$list_mapping_source_objects$;

REVOKE ALL ON FUNCTION workflow.list_mapping_source_objects(
    BIGINT, BIGINT, VARCHAR, BIGINT
) FROM PUBLIC;

CREATE FUNCTION workflow.list_code_generation_target_context(
    p_model_id BIGINT,
    p_modeled_entity_type VARCHAR(30),
    p_required_artifact_type VARCHAR(30) DEFAULT 'sql_file'
)
RETURNS TABLE (
    model_id BIGINT,
    modeled_entity_type VARCHAR(30),
    modeled_entity_name VARCHAR(255),
    object_id BIGINT,
    source_system_count INTEGER,
    code_input_digest CHAR(64),
    source_context JSONB
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_code_generation_target_context$
    WITH eligible_target AS MATERIALIZED (
        SELECT eligible.model_id,
               eligible.object_id,
               eligible.object_tenant_id,
               eligible.connection_id,
               eligible.system_id,
               eligible.object_schema,
               eligible.object_name,
               eligible.zone_code,
               binding.model_object_binding_id,
               binding.modeled_entity_type,
               binding.logical_entity_id,
               binding.dimensional_entity_id
          FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
          JOIN workflow.model_object_binding AS binding
            ON binding.model_id = eligible.model_id
           AND binding.object_id = eligible.object_id
           AND binding.modeled_entity_type = p_modeled_entity_type
           AND binding.model_object_binding_status = 'active'
         WHERE p_modeled_entity_type IN (
                   'logical_entity', 'dimensional_entity'
               )
           AND (
               p_required_artifact_type IS NULL
               OR p_required_artifact_type IN (
                   'sql_file', 'python_file', 'python_notebook'
               )
           )
           AND CASE p_modeled_entity_type
                   WHEN 'logical_entity' THEN
                       eligible.is_logical_mapping_target_eligible
                   WHEN 'dimensional_entity' THEN
                       eligible.is_dimensional_mapping_target_eligible
                   ELSE FALSE
               END
    ), active_mapping AS MATERIALIZED (
        SELECT target.*,
               mapping.mapping_object_id,
               mapping.source_system_id,
               dependency.source_system_dependency_order,
               mapping.object_dependency_order,
               mapping.mapping_transformation_document,
               source_system.system_code AS source_system_code,
               source_system.system_name AS source_system_name,
               CASE target.modeled_entity_type
                   WHEN 'logical_entity' THEN target.logical_entity_id
                   ELSE target.dimensional_entity_id
               END AS modeled_entity_id,
               CASE target.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_name
                   ELSE dimensional_entity.dimensional_entity_name
               END AS modeled_entity_name,
               CASE target.modeled_entity_type
                   WHEN 'logical_entity' THEN
                       logical_entity.logical_entity_definition
                   ELSE dimensional_entity.dimensional_entity_definition
               END AS modeled_entity_definition,
               CASE target.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_type
                   ELSE dimensional_entity.dimensional_entity_type
               END AS modeled_entity_classification,
               CASE target.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_grain
                   ELSE dimensional_entity.dimensional_entity_grain_definition
               END AS modeled_entity_grain,
               mapping.mapping_transformation_document IS NOT NULL
               AND dependency.mapping_source_system_dependency_status = 'active'
               AND source_system.is_active
               AND (
                   (
                       target.modeled_entity_type = 'logical_entity'
                       AND logical_entity.logical_entity_status = 'active'
                   ) OR (
                       target.modeled_entity_type = 'dimensional_entity'
                       AND dimensional_entity.dimensional_entity_status = 'active'
                   )
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM workflow.model_attribute_binding AS attribute_binding
                    WHERE attribute_binding.model_object_binding_id =
                          target.model_object_binding_id
                      AND attribute_binding.model_attribute_binding_status =
                          'active'
                      AND NOT EXISTS (
                          SELECT 1
                            FROM workflow.mapping_attribute AS child
                           WHERE child.mapping_object_id =
                                 mapping.mapping_object_id
                             AND child.model_attribute_binding_id =
                                 attribute_binding.model_attribute_binding_id
                             AND child.attribute_mapping_status = 'active'
                             AND child.attribute_mapping_transformation_document
                                 IS NOT NULL
                      )
               ) AS is_complete
          FROM eligible_target AS target
          JOIN workflow.mapping_object AS mapping
            ON mapping.model_id = target.model_id
           AND mapping.model_object_binding_id =
               target.model_object_binding_id
           AND mapping.object_mapping_status = 'active'
          JOIN workflow.mapping_source_system_dependency AS dependency
            ON dependency.model_id = mapping.model_id
           AND dependency.modeled_entity_type = target.modeled_entity_type
           AND dependency.source_system_id = mapping.source_system_id
          JOIN core.system AS source_system
            ON source_system.system_id = mapping.source_system_id
          LEFT JOIN workflow.logical_entity AS logical_entity
            ON logical_entity.logical_entity_id = target.logical_entity_id
           AND logical_entity.model_id = target.model_id
          LEFT JOIN workflow.dimensional_entity AS dimensional_entity
            ON dimensional_entity.dimensional_entity_id =
               target.dimensional_entity_id
           AND dimensional_entity.model_id = target.model_id
    ), complete_target AS MATERIALIZED (
        SELECT mapping.model_id,
               mapping.modeled_entity_type,
               min(mapping.modeled_entity_name)::VARCHAR(255)
                   AS modeled_entity_name,
               mapping.object_id,
               mapping.model_object_binding_id
          FROM active_mapping AS mapping
         GROUP BY mapping.model_id,
                  mapping.modeled_entity_type,
                  mapping.object_id,
                  mapping.model_object_binding_id
        HAVING count(*) > 0
           AND bool_and(mapping.is_complete)
    ), assembled AS MATERIALIZED (
        SELECT complete.model_id,
               complete.modeled_entity_type,
               complete.modeled_entity_name,
               target.object_id,
               source_systems.source_system_count,
               jsonb_build_object(
                   'model_object_binding_id', complete.model_object_binding_id,
                   'source_systems', source_systems.documents,
                   'object_mappings', object_mappings.documents,
                   'attribute_mappings', attribute_mappings.documents
               ) AS mapping_context,
               jsonb_build_object(
                   'target', jsonb_build_object(
                       'source_tenant_id', source_tenant.tenant_id,
                       'source_tenant_code', source_tenant.tenant_code,
                       'source_tenant_name', source_tenant.tenant_name,
                       'tenant_id', placement_tenant.tenant_id,
                       'tenant_code', placement_tenant.tenant_code,
                       'tenant_name', placement_tenant.tenant_name,
                       'tenant_catalog', placement_tenant.tenant_catalog,
                       'system_id', target_system.system_id,
                       'system_code', target_system.system_code,
                       'system_name', target_system.system_name,
                       'connection_id', connection.connection_id,
                       'connection_code', connection.connection_code,
                       'object_id', target.object_id,
                       'object_schema', target.object_schema,
                       'object_name', target.object_name,
                       'object_description', target_object.object_description,
                       'zone_code', target.zone_code,
                       'attributes', target_attributes.documents
                   ),
                   'physical_sources', physical_sources.documents,
                   'source_systems', source_systems.documents,
                   'object_mappings', object_mappings.documents,
                   'attribute_mappings', attribute_mappings.documents
               ) AS source_context
          FROM complete_target AS complete
          JOIN eligible_target AS target
            ON target.model_id = complete.model_id
           AND target.object_id = complete.object_id
          JOIN core.object AS target_object
            ON target_object.object_id = target.object_id
          JOIN core.connection AS connection
            ON connection.connection_id = target.connection_id
           AND connection.is_active
          JOIN core.tenant AS placement_tenant
            ON placement_tenant.tenant_id = connection.tenant_id
           AND placement_tenant.is_active
          JOIN core.tenant AS source_tenant
            ON source_tenant.tenant_id = target.object_tenant_id
           AND source_tenant.is_active
          JOIN core.system AS target_system
            ON target_system.system_id = target.system_id
           AND target_system.is_active
          CROSS JOIN LATERAL (
              SELECT coalesce(jsonb_agg(jsonb_build_object(
                         'attribute_id', attribute.attribute_id,
                         'attribute_name', attribute.attribute_name,
                         'attribute_ordinal_position', attribute.attribute_ordinal_position,
                         'attribute_data_type', attribute.attribute_data_type,
                         'attribute_inferred_data_type', attribute.attribute_inferred_data_type,
                         'attribute_nullability', attribute.attribute_nullability,
                         'attribute_description', attribute.attribute_description,
                         'is_active', attribute.is_active,
                         'is_locked', attribute.is_locked
                     ) ORDER BY attribute.attribute_ordinal_position, attribute.attribute_id),
                     '[]'::JSONB) AS documents
                FROM core.attribute AS attribute
               WHERE attribute.object_id = target.object_id
          ) AS target_attributes
          CROSS JOIN LATERAL (
              SELECT coalesce(jsonb_agg(jsonb_build_object(
                         'selected_source_system_id', mapping.source_system_id,
                         'source_mapping_id', source.source_mapping_id,
                         'role', source.role,
                         'rationale', source.rationale,
                         'mapping_order', source.mapping_order,
                         'is_locked', source.is_locked,
                         'object', jsonb_build_object(
                             'object_id', source_object.object_id,
                             'source_tenant_id', source_object.source_tenant_id,
                             'tenant_id', placement.tenant_id,
                             'tenant_code', placement.tenant_code,
                             'tenant_catalog', placement.tenant_catalog,
                             'system_id', source_system.system_id,
                             'system_code', source_system.system_code,
                             'connection_id', source_connection.connection_id,
                             'connection_code', source_connection.connection_code,
                             'object_schema', source_object.object_schema,
                             'object_name', source_object.object_name,
                             'object_description', source_object.object_description,
                             'zone_code', lower(btrim(zone.zone_code)),
                             'is_active', source_object.is_active,
                             'is_locked', source_object.is_locked,
                             'scope_is_active', source.scope_is_active,
                             'scope_is_locked', source.scope_is_locked,
                             'attributes', source_attributes.documents
                         )
                     ) ORDER BY mapping.source_system_dependency_order,
                                mapping.source_system_id,
                                source.mapping_order NULLS LAST,
                                source.source_mapping_id), '[]'::JSONB) AS documents
                FROM active_mapping AS mapping
                CROSS JOIN LATERAL workflow.list_mapping_source_objects(
                    mapping.model_id, mapping.object_id,
                    mapping.modeled_entity_type, mapping.source_system_id
                ) AS source
                JOIN core.object AS source_object
                  ON source_object.object_id = source.source_object_id
                JOIN core.connection AS source_connection
                  ON source_connection.connection_id = source_object.connection_id
                JOIN core.tenant AS placement
                  ON placement.tenant_id = source_connection.tenant_id
                JOIN core.system AS source_system
                  ON source_system.system_id = source_connection.system_id
                JOIN reference.zone AS zone ON zone.zone_id = source_object.zone_id
                CROSS JOIN LATERAL (
                    SELECT coalesce(jsonb_agg(jsonb_build_object(
                               'attribute_id', attribute.attribute_id,
                               'attribute_name', attribute.attribute_name,
                               'attribute_ordinal_position', attribute.attribute_ordinal_position,
                               'attribute_data_type', attribute.attribute_data_type,
                               'attribute_inferred_data_type', attribute.attribute_inferred_data_type,
                               'attribute_nullability', attribute.attribute_nullability,
                               'attribute_description', attribute.attribute_description,
                               'is_active', attribute.is_active,
                               'is_locked', attribute.is_locked
                           ) ORDER BY attribute.attribute_ordinal_position, attribute.attribute_id),
                           '[]'::JSONB) AS documents
                      FROM core.attribute AS attribute
                     WHERE attribute.object_id = source.source_object_id
                ) AS source_attributes
               WHERE mapping.model_id = complete.model_id
                 AND mapping.object_id = complete.object_id
          ) AS physical_sources
          JOIN LATERAL (
              SELECT count(*)::INTEGER AS source_system_count,
                     jsonb_agg(
                         system_document.document
                         ORDER BY system_document.dependency_order,
                                  lower(btrim(system_document.system_code)),
                                  system_document.source_system_id
                     ) AS documents
                FROM (
                    SELECT DISTINCT
                           mapping.source_system_dependency_order
                               AS dependency_order,
                           mapping.source_system_id,
                           mapping.source_system_code AS system_code,
                           jsonb_build_object(
                               'source_system_id', mapping.source_system_id,
                               'system_code', mapping.source_system_code,
                               'system_name', mapping.source_system_name,
                               'dependency_order',
                                   mapping.source_system_dependency_order
                           ) AS document
                      FROM active_mapping AS mapping
                     WHERE mapping.model_id = complete.model_id
                       AND mapping.object_id = complete.object_id
                ) AS system_document
          ) AS source_systems ON TRUE
          JOIN LATERAL (
              SELECT jsonb_agg(
                         jsonb_build_object(
                             'mapping_object_id', mapping.mapping_object_id,
                             'model_object_binding_id',
                                 mapping.model_object_binding_id,
                             'source_system_id', mapping.source_system_id,
                             'object_dependency_order',
                                 mapping.object_dependency_order,
                             'entity', jsonb_build_object(
                                 'entity_type', mapping.modeled_entity_type,
                                 'entity_id', mapping.modeled_entity_id,
                                 'entity_name', mapping.modeled_entity_name,
                                 'definition', mapping.modeled_entity_definition,
                                 'classification',
                                     mapping.modeled_entity_classification,
                                 'grain', mapping.modeled_entity_grain
                             ),
                             'transformation',
                                 mapping.mapping_transformation_document
                         ) ORDER BY
                             mapping.source_system_dependency_order,
                             mapping.object_dependency_order,
                             mapping.mapping_object_id
                     ) AS documents
                FROM active_mapping AS mapping
               WHERE mapping.model_id = complete.model_id
                 AND mapping.object_id = complete.object_id
          ) AS object_mappings ON TRUE
          JOIN LATERAL (
              SELECT coalesce(
                         jsonb_agg(
                             jsonb_build_object(
                                 'mapping_attribute_id',
                                     child.mapping_attribute_id,
                                 'mapping_object_id', mapping.mapping_object_id,
                                 'model_attribute_binding_id',
                                     attribute_binding.model_attribute_binding_id,
                                 'source_system_id', mapping.source_system_id,
                                 'modeled_attribute_id',
                                     coalesce(
                                         attribute_binding.logical_attribute_id,
                                         attribute_binding.dimensional_attribute_id
                                     ),
                                 'target_attribute_id', target_attribute.attribute_id,
                                 'target_attribute_name', target_attribute.attribute_name,
                                 'target_attribute_ordinal_position',
                                     target_attribute.attribute_ordinal_position,
                                 'transformation',
                                     child.attribute_mapping_transformation_document
                             ) ORDER BY
                                 mapping.source_system_dependency_order,
                                 mapping.object_dependency_order,
                                 target_attribute.attribute_ordinal_position,
                                 child.mapping_attribute_id
                         ),
                         '[]'::JSONB
                     ) AS documents
                FROM active_mapping AS mapping
                JOIN workflow.mapping_attribute AS child
                  ON child.mapping_object_id = mapping.mapping_object_id
                 AND child.attribute_mapping_status = 'active'
                JOIN workflow.model_attribute_binding AS attribute_binding
                  ON attribute_binding.model_attribute_binding_id =
                     child.model_attribute_binding_id
                 AND attribute_binding.model_object_binding_id =
                     mapping.model_object_binding_id
                 AND attribute_binding.model_attribute_binding_status = 'active'
                JOIN core.attribute AS target_attribute
                  ON target_attribute.attribute_id = attribute_binding.attribute_id
                 AND target_attribute.object_id = mapping.object_id
                 AND target_attribute.is_active
               WHERE mapping.model_id = complete.model_id
                 AND mapping.object_id = complete.object_id
          ) AS attribute_mappings ON TRUE
    )
    SELECT assembled.model_id,
           assembled.modeled_entity_type,
           assembled.modeled_entity_name,
           assembled.object_id,
           assembled.source_system_count,
           encode(
               sha256(
                   convert_to(
                       jsonb_build_object(
                           'mapping_context', assembled.mapping_context,
                           'source_context', assembled.source_context
                       )::TEXT,
                       'UTF8'
                   )
               ),
               'hex'
           )::CHAR(64) AS code_input_digest,
           assembled.source_context
      FROM assembled
     ORDER BY assembled.object_id;
$list_code_generation_target_context$;

REVOKE ALL ON FUNCTION workflow.list_code_generation_target_context(
    BIGINT,
    VARCHAR,
    VARCHAR
) FROM PUBLIC;

CREATE FUNCTION workflow.list_model_attribute_eligibility(
    p_model_id BIGINT
)
RETURNS TABLE (
    model_id BIGINT,
    object_id BIGINT,
    attribute_id BIGINT,
    connection_id BIGINT,
    system_id BIGINT,
    object_tenant_id BIGINT,
    object_schema VARCHAR(400),
    object_name VARCHAR(400),
    attribute_name VARCHAR(400),
    attribute_ordinal_position INTEGER,
    zone_code TEXT,
    is_model_input_eligible BOOLEAN,
    is_dimensional_source_eligible BOOLEAN,
    is_logical_mapping_target_eligible BOOLEAN,
    is_dimensional_mapping_target_eligible BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_model_attribute_eligibility$
    SELECT eligible_object.model_id,
           eligible_object.object_id,
           attribute.attribute_id,
           eligible_object.connection_id,
           eligible_object.system_id,
           eligible_object.object_tenant_id,
           eligible_object.object_schema,
           eligible_object.object_name,
           attribute.attribute_name,
           attribute.attribute_ordinal_position,
           eligible_object.zone_code,
           eligible_object.is_model_input_eligible,
           eligible_object.is_dimensional_source_eligible
           AND EXISTS (
               SELECT 1
                 FROM workflow.model_object_binding AS object_binding
                 JOIN workflow.model_attribute_binding AS attribute_binding
                   ON attribute_binding.model_object_binding_id =
                      object_binding.model_object_binding_id
                  AND attribute_binding.attribute_id = attribute.attribute_id
                  AND attribute_binding.model_attribute_binding_status = 'active'
                 JOIN workflow.mapping_object AS mapping_object
                   ON mapping_object.model_object_binding_id =
                      object_binding.model_object_binding_id
                  AND mapping_object.object_mapping_status = 'active'
                 JOIN workflow.mapping_attribute AS mapping_attribute
                   ON mapping_attribute.mapping_object_id =
                      mapping_object.mapping_object_id
                  AND mapping_attribute.model_attribute_binding_id =
                      attribute_binding.model_attribute_binding_id
                  AND mapping_attribute.attribute_mapping_status = 'active'
                  AND mapping_attribute.attribute_mapping_transformation_document
                      IS NOT NULL
                WHERE object_binding.model_id = eligible_object.model_id
                  AND object_binding.object_id = eligible_object.object_id
                  AND object_binding.modeled_entity_type = 'logical_entity'
                  AND object_binding.model_object_binding_status = 'active'
           ) AS is_dimensional_source_eligible,
           eligible_object.is_logical_mapping_target_eligible,
           eligible_object.is_dimensional_mapping_target_eligible
      FROM workflow.list_model_object_eligibility(p_model_id)
           AS eligible_object
      JOIN core.attribute AS attribute
        ON attribute.object_id = eligible_object.object_id
       AND attribute.is_active
     ORDER BY lower(btrim(eligible_object.object_schema)),
              lower(btrim(eligible_object.object_name)),
              attribute.attribute_ordinal_position,
              lower(btrim(attribute.attribute_name)),
              attribute.attribute_id;
$list_model_attribute_eligibility$;

REVOKE ALL ON FUNCTION workflow.list_model_attribute_eligibility(BIGINT)
FROM PUBLIC;
