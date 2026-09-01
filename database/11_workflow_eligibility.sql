-- One Tenant-visible Object closure shared by read candidates and secure writes.
CREATE FUNCTION workflow.list_tenant_visible_objects(
    p_tenant_id BIGINT
)
RETURNS TABLE (
    object_id BIGINT,
    object_tenant_id BIGINT,
    is_owned_by_tenant BOOLEAN,
    is_discovered_by_scope BOOLEAN,
    is_copy_referenced BOOLEAN,
    is_process_referenced BOOLEAN,
    is_model_scope_referenced BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_tenant_visible_objects$
    WITH RECURSIVE requested_tenant AS (
        SELECT tenant_id, gds_connection_id
          FROM core.tenant
         WHERE tenant_id = p_tenant_id
           AND is_active
    ),
    resolved_object_tenants AS (
        SELECT object.object_id,
               CASE
                   WHEN connection.is_global_data_store
                   THEN discovery_tenant.tenant_id
                   ELSE connection_tenant.tenant_id
               END AS object_tenant_id
          FROM core.object AS object
          JOIN core.connection AS connection
            ON connection.connection_id = object.connection_id
          LEFT JOIN core.tenant AS connection_tenant
            ON NOT connection.is_global_data_store
           AND connection_tenant.tenant_id = connection.tenant_id
           AND connection_tenant.is_active
          LEFT JOIN core.tenant_metadata_discovery_scope AS discovery_scope
            ON connection.is_global_data_store
           AND discovery_scope.gds_connection_id = connection.connection_id
           AND discovery_scope.zone_id = object.zone_id
           AND lower(btrim(discovery_scope.object_schema)) =
               lower(btrim(object.object_schema))
           AND discovery_scope.is_active
          LEFT JOIN core.tenant AS discovery_tenant
            ON discovery_tenant.tenant_id = discovery_scope.tenant_id
           AND discovery_tenant.is_active
         WHERE (
                   NOT connection.is_global_data_store
                   AND connection_tenant.tenant_id IS NOT NULL
               )
            OR (
                   connection.is_global_data_store
                   AND discovery_tenant.tenant_id IS NOT NULL
               )
    ),
    owned_objects AS (
        SELECT object.object_id
          FROM requested_tenant
          JOIN core.connection AS connection
            ON connection.tenant_id = requested_tenant.tenant_id
           AND NOT connection.is_global_data_store
          JOIN core.object AS object
            ON object.connection_id = connection.connection_id
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = object.object_id
    ),
    discovery_objects AS (
        SELECT object.object_id
          FROM requested_tenant
          JOIN core.tenant_metadata_discovery_scope AS scope
            ON scope.tenant_id = requested_tenant.tenant_id
           AND scope.is_active
          JOIN core.connection AS connection
            ON connection.connection_id = scope.gds_connection_id
           AND connection.is_active
           AND connection.is_global_data_store
          JOIN reference.zone AS zone
            ON zone.zone_id = scope.zone_id
           AND zone.is_active
           AND zone.zone_code IN ('bronze', 'silver', 'gold')
          JOIN core.object AS object
            ON object.connection_id = scope.gds_connection_id
           AND object.zone_id = scope.zone_id
           AND lower(btrim(object.object_schema)) = lower(btrim(scope.object_schema))
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = object.object_id
           AND resolved.object_tenant_id = requested_tenant.tenant_id
    ),
    copy_objects AS (
        SELECT mapping.source_object_id AS object_id
          FROM requested_tenant
          JOIN core.copy_group AS copy_group
            ON copy_group.tenant_id = requested_tenant.tenant_id
          JOIN core.copy AS copy
            ON copy.copy_group_id = copy_group.copy_group_id
          JOIN core.ingestion_object_mapping AS mapping
            ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = mapping.source_object_id
        UNION
        SELECT mapping.target_object_id
          FROM requested_tenant
          JOIN core.copy_group AS copy_group
            ON copy_group.tenant_id = requested_tenant.tenant_id
          JOIN core.copy AS copy
            ON copy.copy_group_id = copy_group.copy_group_id
          JOIN core.ingestion_object_mapping AS mapping
            ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = mapping.target_object_id
    ),
    process_objects AS (
        SELECT process.object_id
          FROM requested_tenant
          JOIN core.copy_group AS copy_group
            ON copy_group.tenant_id = requested_tenant.tenant_id
          JOIN core.process_group AS process_group
            ON process_group.copy_group_id = copy_group.copy_group_id
           AND process_group.tenant_id = copy_group.tenant_id
           AND process_group.system_id = copy_group.system_id
          JOIN core.process AS process
            ON process.process_group_id = process_group.process_group_id
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = process.object_id
    ),
    model_scope_objects AS (
        SELECT scope.object_id
          FROM requested_tenant
          JOIN model.model AS model
            ON model.tenant_id = requested_tenant.tenant_id
           AND model.is_active
          JOIN model.model_scope AS scope
            ON scope.model_id = model.model_id
           AND scope.is_active
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = scope.object_id
    ),
    seed_objects AS (
        SELECT object_id FROM owned_objects
        UNION
        SELECT object_id FROM discovery_objects
        UNION
        SELECT object_id FROM copy_objects
        UNION
        SELECT object_id FROM process_objects
        UNION
        SELECT object_id FROM model_scope_objects
    ),
    connected_objects (object_id) AS (
        SELECT object_id FROM seed_objects
        UNION
        SELECT resolved.object_id
          FROM connected_objects
          JOIN core.ingestion_object_mapping AS mapping
            ON mapping.is_active
           AND (
               mapping.source_object_id = connected_objects.object_id
               OR mapping.target_object_id = connected_objects.object_id
           )
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = CASE
                   WHEN mapping.source_object_id = connected_objects.object_id
                   THEN mapping.target_object_id
                   ELSE mapping.source_object_id
               END
    ),
    visible_objects AS (
        SELECT connected_objects.object_id,
               resolved.object_tenant_id,
               EXISTS (
                   SELECT 1 FROM owned_objects
                    WHERE owned_objects.object_id = connected_objects.object_id
               ) AS is_owned_by_tenant,
               EXISTS (
                   SELECT 1 FROM discovery_objects
                    WHERE discovery_objects.object_id = connected_objects.object_id
               ) AS is_discovered_by_scope,
               EXISTS (
                   SELECT 1 FROM copy_objects
                    WHERE copy_objects.object_id = connected_objects.object_id
               ) AS is_copy_referenced,
               EXISTS (
                   SELECT 1 FROM process_objects
                    WHERE process_objects.object_id = connected_objects.object_id
               ) AS is_process_referenced,
               EXISTS (
                   SELECT 1 FROM model_scope_objects
                    WHERE model_scope_objects.object_id = connected_objects.object_id
               ) AS is_model_scope_referenced
          FROM connected_objects
          JOIN resolved_object_tenants AS resolved
            ON resolved.object_id = connected_objects.object_id
    )
    SELECT visible_objects.object_id,
           visible_objects.object_tenant_id,
           visible_objects.is_owned_by_tenant,
           visible_objects.is_discovered_by_scope,
           visible_objects.is_copy_referenced,
           visible_objects.is_process_referenced,
           visible_objects.is_model_scope_referenced
      FROM visible_objects;
$list_tenant_visible_objects$;

REVOKE ALL ON FUNCTION workflow.list_tenant_visible_objects(BIGINT)
FROM PUBLIC;

-- Canonical read-only Model workflow eligibility. Registration, Model Scope,
-- Mapping, and code generation remain separate explicit operations.

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
    is_bronze_source_eligible BOOLEAN,
    is_dimensional_source_eligible BOOLEAN,
    is_logical_mapping_target_eligible BOOLEAN,
    is_dimensional_mapping_target_eligible BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $list_model_object_eligibility$
    SELECT target_model.model_id,
           object.object_id,
           connection.connection_id,
           system.system_id,
           CASE
               WHEN connection.is_global_data_store
               THEN scoped_tenant.tenant_id
               ELSE connection_tenant.tenant_id
           END AS object_tenant_id,
           object.object_schema,
           object.object_name,
           lower(btrim(zone.zone_code)) AS zone_code,
           lower(btrim(zone.zone_code)) = 'bronze'
               AS is_bronze_source_eligible,
           lower(btrim(zone.zone_code)) = 'silver'
           AND EXISTS (
               SELECT 1
                 FROM workflow.mapping_object AS mapping_object
                 JOIN workflow.mapping_source_system_dependency AS dependency
                   ON dependency.model_id = mapping_object.model_id
                  AND dependency.modeled_entity_type =
                      mapping_object.modeled_entity_type
                  AND dependency.source_system_id =
                      mapping_object.source_system_id
                 JOIN workflow.logical_entity AS logical_entity
                   ON logical_entity.logical_entity_id =
                      mapping_object.logical_entity_id
                  AND logical_entity.model_id = mapping_object.model_id
                 JOIN core.system AS source_system
                   ON source_system.system_id = mapping_object.source_system_id
                  AND source_system.is_active
                WHERE mapping_object.model_id = target_model.model_id
                  AND mapping_object.object_id = object.object_id
                  AND mapping_object.modeled_entity_type = 'logical_entity'
                  AND mapping_object.object_mapping_status = 'active'
                  AND dependency.mapping_source_system_dependency_status =
                      'active'
                  AND logical_entity.logical_entity_status = 'active'
           ) AS is_dimensional_source_eligible,
           lower(btrim(zone.zone_code)) = 'silver'
               AS is_logical_mapping_target_eligible,
           lower(btrim(zone.zone_code)) = 'gold'
               AS is_dimensional_mapping_target_eligible
      FROM model.model AS target_model
      JOIN core.tenant AS model_tenant
        ON model_tenant.tenant_id = target_model.tenant_id
       AND model_tenant.is_active
      JOIN model.model_scope AS scope
        ON scope.model_id = target_model.model_id
       AND scope.is_active
      JOIN core.object AS object
        ON object.object_id = scope.object_id
       AND object.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = object.connection_id
       AND connection.is_active
      LEFT JOIN core.tenant AS connection_tenant
        ON NOT connection.is_global_data_store
       AND connection_tenant.tenant_id = connection.tenant_id
       AND connection_tenant.is_active
      JOIN core.system AS system
        ON system.system_id = connection.system_id
       AND system.is_active
      JOIN reference.zone AS zone
        ON zone.zone_id = object.zone_id
       AND zone.is_active
      LEFT JOIN core.tenant_metadata_discovery_scope AS discovery_scope
        ON connection.is_global_data_store
       AND discovery_scope.gds_connection_id = connection.connection_id
       AND discovery_scope.zone_id = object.zone_id
       AND lower(btrim(discovery_scope.object_schema)) =
           lower(btrim(object.object_schema))
       AND discovery_scope.is_active
      LEFT JOIN core.tenant AS scoped_tenant
        ON scoped_tenant.tenant_id = discovery_scope.tenant_id
       AND scoped_tenant.is_active
     WHERE target_model.model_id = p_model_id
       AND target_model.is_active
       AND (
               (
                   NOT connection.is_global_data_store
                   AND connection_tenant.tenant_id IS NOT NULL
               )
               OR (
                   connection.is_global_data_store
                   AND scoped_tenant.tenant_id IS NOT NULL
               )
           )
     ORDER BY lower(
                  btrim(
                      CASE
                          WHEN connection.is_global_data_store
                          THEN scoped_tenant.tenant_code
                          ELSE connection_tenant.tenant_code
                      END
                  )
              ),
              lower(btrim(system.system_code)),
              lower(btrim(object.object_schema)),
              lower(btrim(object.object_name)),
              object.object_id;
$list_model_object_eligibility$;

REVOKE ALL ON FUNCTION workflow.list_model_object_eligibility(BIGINT)
FROM PUBLIC;

CREATE FUNCTION workflow.list_code_generation_target_context(
    p_model_id BIGINT,
    p_modeled_entity_type VARCHAR(30),
    p_required_artifact_type VARCHAR(30) DEFAULT 'sql_file'
)
RETURNS TABLE (
    model_id BIGINT,
    modeled_entity_type VARCHAR(30),
    object_id BIGINT,
    source_system_count INTEGER,
    mapping_context_digest CHAR(64),
    source_context_digest CHAR(64),
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
               eligible.zone_code
          FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
         WHERE p_modeled_entity_type IN (
                   'logical_entity', 'dimensional_entity'
               )
           AND CASE p_modeled_entity_type
                   WHEN 'logical_entity' THEN
                       eligible.is_logical_mapping_target_eligible
                   WHEN 'dimensional_entity' THEN
                       eligible.is_dimensional_mapping_target_eligible
                   ELSE FALSE
               END
    ), active_mapping AS MATERIALIZED (
        SELECT mapping.model_id,
               mapping.modeled_entity_type,
               mapping.object_id,
               mapping.mapping_object_id,
               mapping.source_system_id,
               dependency.source_system_dependency_order,
               mapping.object_dependency_order,
               mapping.artifact_type,
               mapping.artifact_generation_instructions,
               mapping.mapping_profile_key,
               mapping.mapping_profile_version,
               mapping.mapping_profile_schema_digest,
               mapping.mapping_package_document,
               mapping.mapping_package_digest,
               mapping.object_mapping_transformation_document,
               source_system.system_code AS source_system_code,
               source_system.system_name AS source_system_name,
               CASE mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN mapping.logical_entity_id
                   ELSE mapping.dimensional_entity_id
               END AS modeled_entity_id,
               CASE mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_name
                   ELSE dimensional_entity.dimensional_entity_name
               END AS modeled_entity_name,
               CASE mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN
                       logical_entity.logical_entity_definition
                   ELSE dimensional_entity.dimensional_entity_definition
               END AS modeled_entity_definition,
               CASE mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_type
                   ELSE dimensional_entity.dimensional_entity_type
               END AS modeled_entity_classification,
               CASE mapping.modeled_entity_type
                   WHEN 'logical_entity' THEN logical_entity.logical_entity_grain
                   ELSE dimensional_entity.dimensional_entity_grain_definition
               END AS modeled_entity_grain,
               (
                   (
                       p_required_artifact_type IS NULL
                       OR mapping.artifact_type = p_required_artifact_type
                   )
                   AND mapping.artifact_generation_instructions IS NOT NULL
                   AND mapping.mapping_profile_key IS NOT NULL
                   AND mapping.mapping_profile_version IS NOT NULL
                   AND mapping.mapping_profile_schema_digest IS NOT NULL
                   AND mapping.mapping_package_document IS NOT NULL
                   AND mapping.mapping_package_digest IS NOT NULL
                   AND mapping.object_mapping_transformation_document IS NOT NULL
                   AND dependency.mapping_source_system_dependency_status = 'active'
                   AND source_system.is_active
                   AND (
                       (
                           mapping.modeled_entity_type = 'logical_entity'
                           AND logical_entity.logical_entity_id IS NOT NULL
                           AND logical_entity.logical_entity_status = 'active'
                       ) OR (
                           mapping.modeled_entity_type = 'dimensional_entity'
                           AND dimensional_entity.dimensional_entity_id IS NOT NULL
                           AND dimensional_entity.dimensional_entity_status = 'active'
                       )
                   )
                   AND NOT EXISTS (
                       SELECT 1
                         FROM workflow.mapping_attribute AS child
                         LEFT JOIN core.attribute AS target_attribute
                           ON target_attribute.attribute_id = child.attribute_id
                          AND target_attribute.object_id = child.object_id
                          AND target_attribute.is_active
                         LEFT JOIN workflow.logical_attribute AS logical_attribute
                           ON logical_attribute.logical_attribute_id =
                              child.logical_attribute_id
                          AND logical_attribute.model_id = child.model_id
                          AND logical_attribute.logical_entity_id =
                              mapping.logical_entity_id
                          AND logical_attribute.logical_attribute_status = 'active'
                         LEFT JOIN workflow.dimensional_attribute
                                   AS dimensional_attribute
                           ON dimensional_attribute.dimensional_attribute_id =
                              child.dimensional_attribute_id
                          AND dimensional_attribute.model_id = child.model_id
                          AND dimensional_attribute.dimensional_entity_id =
                              mapping.dimensional_entity_id
                          AND dimensional_attribute.dimensional_attribute_status =
                              'active'
                        WHERE child.mapping_object_id = mapping.mapping_object_id
                          AND child.model_id = mapping.model_id
                          AND child.object_id = mapping.object_id
                          AND child.modeled_entity_type =
                              mapping.modeled_entity_type
                          AND child.attribute_mapping_status = 'active'
                          AND (
                              child.attribute_mapping_transformation_document
                                  IS NULL
                              OR target_attribute.attribute_id IS NULL
                              OR (
                                  child.modeled_entity_type = 'logical_entity'
                                  AND logical_attribute.logical_attribute_id IS NULL
                              )
                              OR (
                                  child.modeled_entity_type = 'dimensional_entity'
                                  AND dimensional_attribute.dimensional_attribute_id
                                      IS NULL
                              )
                          )
                   )
               ) AS is_complete
          FROM eligible_target AS target
          JOIN workflow.mapping_object AS mapping
            ON mapping.model_id = target.model_id
           AND mapping.object_id = target.object_id
           AND mapping.modeled_entity_type = p_modeled_entity_type
           AND mapping.object_mapping_status = 'active'
          JOIN workflow.mapping_source_system_dependency AS dependency
            ON dependency.model_id = mapping.model_id
           AND dependency.modeled_entity_type = mapping.modeled_entity_type
           AND dependency.source_system_id = mapping.source_system_id
          JOIN core.system AS source_system
            ON source_system.system_id = mapping.source_system_id
          LEFT JOIN workflow.logical_entity AS logical_entity
            ON logical_entity.logical_entity_id = mapping.logical_entity_id
           AND logical_entity.model_id = mapping.model_id
          LEFT JOIN workflow.dimensional_entity AS dimensional_entity
            ON dimensional_entity.dimensional_entity_id =
               mapping.dimensional_entity_id
           AND dimensional_entity.model_id = mapping.model_id
    ), complete_target AS MATERIALIZED (
        SELECT mapping.model_id,
               mapping.modeled_entity_type,
               mapping.object_id
          FROM active_mapping AS mapping
         GROUP BY mapping.model_id,
                  mapping.modeled_entity_type,
                  mapping.object_id
        HAVING count(*) > 0
           AND bool_and(mapping.is_complete)
    ), assembled AS MATERIALIZED (
        SELECT target.model_id,
               complete.modeled_entity_type,
               target.object_id,
               source_systems.source_system_count,
               jsonb_build_object(
                   'source_systems', source_systems.documents,
                   'object_mappings', object_mappings.documents,
                   'attribute_mappings', attribute_mappings.documents
               ) AS mapping_context,
               jsonb_build_object(
                   'target', jsonb_build_object(
                       'tenant_id', tenant.tenant_id,
                       'tenant_code', tenant.tenant_code,
                       'tenant_name', tenant.tenant_name,
                       'system_id', target_system.system_id,
                       'system_code', target_system.system_code,
                       'system_name', target_system.system_name,
                       'connection_id', connection.connection_id,
                       'connection_code', connection.connection_code,
                       'object_id', target.object_id,
                       'object_schema', target.object_schema,
                       'object_name', target.object_name,
                       'zone_code', target.zone_code
                   ),
                   'source_systems', source_systems.documents,
                   'object_mappings', object_mappings.documents,
                   'attribute_mappings', attribute_mappings.documents
               ) AS source_context
          FROM complete_target AS complete
          JOIN eligible_target AS target
            ON target.model_id = complete.model_id
           AND target.object_id = complete.object_id
          JOIN core.tenant AS tenant
            ON tenant.tenant_id = target.object_tenant_id
           AND tenant.is_active
          JOIN core.connection AS connection
            ON connection.connection_id = target.connection_id
           AND connection.is_active
          JOIN core.system AS target_system
            ON target_system.system_id = target.system_id
           AND target_system.is_active
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
                       AND mapping.modeled_entity_type =
                           complete.modeled_entity_type
                       AND mapping.object_id = complete.object_id
                ) AS system_document
          ) AS source_systems ON TRUE
          JOIN LATERAL (
              SELECT jsonb_agg(
                         jsonb_build_object(
                             'mapping_object_id', mapping.mapping_object_id,
                             'source_system', jsonb_build_object(
                                 'source_system_id', mapping.source_system_id,
                                 'system_code', mapping.source_system_code,
                                 'system_name', mapping.source_system_name,
                                 'dependency_order',
                                     mapping.source_system_dependency_order
                             ),
                             'object_dependency_order',
                                 mapping.object_dependency_order,
                             'entity', jsonb_build_object(
                                 'entity_type', mapping.modeled_entity_type,
                                 'entity_id', mapping.modeled_entity_id,
                                 'entity_name', mapping.modeled_entity_name,
                                 'definition', mapping.modeled_entity_definition,
                                 'classification',
                                     mapping.modeled_entity_classification,
                                 'grain', mapping.modeled_entity_grain,
                                 'supports', CASE mapping.modeled_entity_type
                                     WHEN 'logical_entity' THEN (
                                         SELECT coalesce(
                                             jsonb_agg(
                                                 jsonb_build_object(
                                                     'support_source_type',
                                                         support.support_source_type,
                                                     'source_object_id',
                                                         support.source_object_id,
                                                     'modeling_assertion_record_id',
                                                         support.modeling_assertion_record_id,
                                                     'support_order',
                                                         support.logical_entity_source_mapping_order,
                                                     'rationale',
                                                         support.logical_entity_source_mapping_rationale
                                                 ) ORDER BY
                                                     support.logical_entity_source_mapping_order
                                                         NULLS LAST,
                                                     support.logical_entity_source_mapping_id
                                             ),
                                             '[]'::JSONB
                                         )
                                           FROM workflow.logical_entity_source_mapping
                                                AS support
                                          WHERE support.model_id = mapping.model_id
                                            AND support.logical_entity_id =
                                                mapping.modeled_entity_id
                                            AND support.logical_entity_source_mapping_status =
                                                'active'
                                     )
                                     ELSE (
                                         SELECT coalesce(
                                             jsonb_agg(
                                                 jsonb_build_object(
                                                     'support_source_type',
                                                         support.support_source_type,
                                                     'source_object_id',
                                                         support.source_object_id,
                                                     'modeling_assertion_record_id',
                                                         support.modeling_assertion_record_id,
                                                     'support_order',
                                                         support.dimensional_entity_source_mapping_order,
                                                     'rationale',
                                                         support.dimensional_entity_source_mapping_rationale
                                                 ) ORDER BY
                                                     support.dimensional_entity_source_mapping_order
                                                         NULLS LAST,
                                                     support.dimensional_entity_source_mapping_id
                                             ),
                                             '[]'::JSONB
                                         )
                                           FROM workflow.dimensional_entity_source_mapping
                                                AS support
                                          WHERE support.model_id = mapping.model_id
                                            AND support.dimensional_entity_id =
                                                mapping.modeled_entity_id
                                            AND support.dimensional_entity_source_mapping_status =
                                                'active'
                                     )
                                 END
                             ),
                             'artifact_generation_instructions',
                                 mapping.artifact_generation_instructions,
                             'mapping_profile_key', mapping.mapping_profile_key,
                             'mapping_profile_version',
                                 mapping.mapping_profile_version,
                             'mapping_profile_schema_digest',
                                 mapping.mapping_profile_schema_digest,
                             'mapping_package',
                                 mapping.mapping_package_document,
                             'mapping_package_digest',
                                 mapping.mapping_package_digest,
                             'transformation',
                                 mapping.object_mapping_transformation_document
                         ) ORDER BY
                             mapping.source_system_dependency_order,
                             lower(btrim(mapping.source_system_code)),
                             mapping.source_system_id,
                             mapping.object_dependency_order,
                             mapping.mapping_object_id
                     ) AS documents
                FROM active_mapping AS mapping
               WHERE mapping.model_id = complete.model_id
                 AND mapping.modeled_entity_type = complete.modeled_entity_type
                 AND mapping.object_id = complete.object_id
          ) AS object_mappings ON TRUE
          JOIN LATERAL (
              SELECT coalesce(
                         jsonb_agg(
                             jsonb_build_object(
                                 'mapping_attribute_id', child.mapping_attribute_id,
                                 'mapping_object_id', mapping.mapping_object_id,
                                 'source_system', jsonb_build_object(
                                     'source_system_id', mapping.source_system_id,
                                     'system_code', mapping.source_system_code,
                                     'system_name', mapping.source_system_name,
                                     'dependency_order',
                                         mapping.source_system_dependency_order
                                 ),
                                 'entity_id', mapping.modeled_entity_id,
                                 'entity_name', mapping.modeled_entity_name,
                                 'modeled_attribute_id',
                                     CASE child.modeled_entity_type
                                         WHEN 'logical_entity' THEN
                                             child.logical_attribute_id
                                         ELSE child.dimensional_attribute_id
                                     END,
                                 'modeled_attribute_name',
                                     CASE child.modeled_entity_type
                                         WHEN 'logical_entity' THEN
                                             logical_attribute.logical_attribute_name
                                         ELSE dimensional_attribute.dimensional_attribute_name
                                     END,
                                 'target_attribute_id', target_attribute.attribute_id,
                                 'target_attribute_name', target_attribute.attribute_name,
                                 'target_attribute_ordinal_position',
                                     target_attribute.attribute_ordinal_position,
                                 'transformation',
                                     child.attribute_mapping_transformation_document
                             ) ORDER BY
                                 mapping.source_system_dependency_order,
                                 lower(btrim(mapping.source_system_code)),
                                 mapping.source_system_id,
                                 mapping.object_dependency_order,
                                 mapping.mapping_object_id,
                                 target_attribute.attribute_ordinal_position,
                                 target_attribute.attribute_id,
                                 child.mapping_attribute_id
                         ),
                         '[]'::JSONB
                     ) AS documents
                FROM active_mapping AS mapping
                JOIN workflow.mapping_attribute AS child
                  ON child.mapping_object_id = mapping.mapping_object_id
                 AND child.model_id = mapping.model_id
                 AND child.object_id = mapping.object_id
                 AND child.modeled_entity_type = mapping.modeled_entity_type
                 AND child.attribute_mapping_status = 'active'
                JOIN core.attribute AS target_attribute
                  ON target_attribute.attribute_id = child.attribute_id
                 AND target_attribute.object_id = child.object_id
                 AND target_attribute.is_active
                LEFT JOIN workflow.logical_attribute AS logical_attribute
                  ON logical_attribute.logical_attribute_id =
                     child.logical_attribute_id
                 AND logical_attribute.model_id = child.model_id
                 AND logical_attribute.logical_attribute_status = 'active'
                LEFT JOIN workflow.dimensional_attribute
                          AS dimensional_attribute
                  ON dimensional_attribute.dimensional_attribute_id =
                     child.dimensional_attribute_id
                 AND dimensional_attribute.model_id = child.model_id
                 AND dimensional_attribute.dimensional_attribute_status = 'active'
               WHERE mapping.model_id = complete.model_id
                 AND mapping.modeled_entity_type = complete.modeled_entity_type
                 AND mapping.object_id = complete.object_id
          ) AS attribute_mappings ON TRUE
    )
    SELECT assembled.model_id,
           assembled.modeled_entity_type,
           assembled.object_id,
           assembled.source_system_count,
           encode(
               sha256(convert_to(assembled.mapping_context::TEXT, 'UTF8')),
               'hex'
           )::CHAR(64) AS mapping_context_digest,
           encode(
               sha256(convert_to(assembled.source_context::TEXT, 'UTF8')),
               'hex'
           )::CHAR(64) AS source_context_digest,
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
    is_bronze_source_eligible BOOLEAN,
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
           eligible_object.is_bronze_source_eligible,
           eligible_object.zone_code = 'silver'
           AND EXISTS (
               SELECT 1
                 FROM workflow.mapping_attribute AS mapping_attribute
                 JOIN workflow.mapping_object AS mapping_object
                   ON mapping_object.mapping_object_id =
                      mapping_attribute.mapping_object_id
                  AND mapping_object.model_id = mapping_attribute.model_id
                  AND mapping_object.modeled_entity_type =
                      mapping_attribute.modeled_entity_type
                  AND mapping_object.object_id = mapping_attribute.object_id
                 JOIN workflow.mapping_source_system_dependency AS dependency
                   ON dependency.model_id = mapping_object.model_id
                  AND dependency.modeled_entity_type =
                      mapping_object.modeled_entity_type
                  AND dependency.source_system_id =
                      mapping_object.source_system_id
                 JOIN workflow.logical_entity AS logical_entity
                   ON logical_entity.logical_entity_id =
                      mapping_object.logical_entity_id
                  AND logical_entity.model_id = mapping_object.model_id
                 JOIN workflow.logical_attribute AS logical_attribute
                   ON logical_attribute.logical_attribute_id =
                      mapping_attribute.logical_attribute_id
                  AND logical_attribute.model_id = mapping_attribute.model_id
                  AND logical_attribute.logical_entity_id =
                      logical_entity.logical_entity_id
                 JOIN core.system AS source_system
                   ON source_system.system_id = mapping_object.source_system_id
                  AND source_system.is_active
                WHERE mapping_attribute.model_id = eligible_object.model_id
                  AND mapping_attribute.object_id = eligible_object.object_id
                  AND mapping_attribute.attribute_id = attribute.attribute_id
                  AND mapping_attribute.modeled_entity_type = 'logical_entity'
                  AND mapping_attribute.attribute_mapping_status = 'active'
                  AND mapping_object.object_mapping_status = 'active'
                  AND dependency.mapping_source_system_dependency_status =
                      'active'
                  AND logical_entity.logical_entity_status = 'active'
                  AND logical_attribute.logical_attribute_status = 'active'
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
