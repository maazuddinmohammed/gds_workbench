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

-- Physical eligibility is restricted to Model input evidence. Modeled targets
-- and Dimensional sources are identified through workflow.modeled_entity.
CREATE FUNCTION workflow.list_model_object_eligibility(p_model_id BIGINT)
RETURNS TABLE (
    model_id BIGINT, object_id BIGINT, connection_id BIGINT, system_id BIGINT,
    object_tenant_id BIGINT, object_schema VARCHAR(400), object_name VARCHAR(400),
    zone_code TEXT, is_model_input_eligible BOOLEAN
)
LANGUAGE SQL STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $list_model_object_eligibility$
    SELECT target.model_id, object.object_id, connection.connection_id, system.system_id,
           object.source_tenant_id, object.object_schema, object.object_name,
           lower(btrim(zone.zone_code)), TRUE
      FROM model.model AS target
      JOIN core.tenant AS tenant ON tenant.tenant_id = target.tenant_id AND tenant.is_active
      JOIN core.object AS object ON object.is_active
      JOIN core.tenant AS owner ON owner.tenant_id = object.source_tenant_id AND owner.is_active
      JOIN core.connection AS connection ON connection.connection_id = object.connection_id
       AND connection.is_active
      JOIN core.system AS system ON system.system_id = connection.system_id AND system.is_active
      JOIN reference.zone AS zone ON zone.zone_id = object.zone_id AND zone.is_active
     WHERE target.model_id = p_model_id AND target.is_active
       AND lower(btrim(zone.zone_code)) IN ('source', 'bronze')
     ORDER BY lower(btrim(system.system_code)), lower(btrim(object.object_schema)),
              lower(btrim(object.object_name)), object.object_id;
$list_model_object_eligibility$;
REVOKE ALL ON FUNCTION workflow.list_model_object_eligibility(BIGINT) FROM PUBLIC;

-- Business Systems represented by active Input Scope. Bronze placement does not
-- identify its originating System; registered ingestion lineage does.
CREATE FUNCTION workflow.list_model_input_sources(p_model_id BIGINT)
RETURNS TABLE (object_id BIGINT, source_system_id BIGINT)
LANGUAGE SQL STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $list_model_input_sources$
    SELECT DISTINCT scope.object_id, origin.system_id
      FROM model.model_input_scope AS scope
      JOIN workflow.list_model_object_eligibility(p_model_id) AS eligible
        ON eligible.object_id = scope.object_id AND eligible.is_model_input_eligible
      JOIN core.object AS object ON object.object_id = scope.object_id
      JOIN core.tenant AS owner ON owner.tenant_id = object.source_tenant_id AND owner.is_active
      JOIN core.connection AS placement ON placement.connection_id = object.connection_id
      CROSS JOIN LATERAL (
          SELECT placement.system_id WHERE eligible.zone_code = 'source'
          UNION
          SELECT connection.system_id
            FROM core.ingestion_object_mapping AS ingestion
            JOIN core.object AS original ON original.object_id = ingestion.source_object_id
               AND original.is_active
            JOIN core.connection AS connection ON connection.connection_id = original.connection_id
               AND connection.is_active
            JOIN core.system AS system ON system.system_id = connection.system_id AND system.is_active
           WHERE eligible.zone_code = 'bronze' AND ingestion.target_object_id = scope.object_id
             AND ingestion.is_active
      ) AS origin
     WHERE scope.model_id = p_model_id AND scope.is_active;
$list_model_input_sources$;
REVOKE ALL ON FUNCTION workflow.list_model_input_sources(BIGINT) FROM PUBLIC;

-- Source evidence for an Entity/System pair. Logical inputs include physical
-- Objects and peer Logical lookups; Dimensional inputs are Logical Entities.
-- Modeled sources require an applied Mapping for the selected source System.
-- A configured default System may label Assertion-defined generated data, but
-- never replace a missing physical/Logical source or failed lineage prerequisite.
CREATE FUNCTION workflow.is_assertion_only_mapping_target(
    p_model_id BIGINT, p_target_entity_id BIGINT, p_modeled_entity_type VARCHAR(30)
)
RETURNS BOOLEAN
LANGUAGE SQL STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $is_assertion_only_mapping_target$
    WITH target AS MATERIALIZED (
        SELECT * FROM workflow.modeled_entity AS entity
         WHERE entity.model_id = p_model_id AND entity.modeled_entity_id = p_target_entity_id
           AND entity.modeled_entity_type = p_modeled_entity_type AND entity.status = 'active'
    ), support AS (
        SELECT source.support_source_type, source.modeling_assertion_record_id
          FROM target JOIN workflow.logical_entity_source_mapping AS source
            ON target.modeled_entity_type = 'logical_entity' AND source.model_id = target.model_id
           AND source.logical_entity_id = target.modeled_entity_id
         WHERE source.logical_entity_source_mapping_status = 'active'
        UNION ALL
        SELECT source.support_source_type, source.modeling_assertion_record_id
          FROM target JOIN workflow.logical_attribute_source_mapping AS source
            ON target.modeled_entity_type = 'logical_entity' AND source.model_id = target.model_id
           AND source.logical_entity_id = target.modeled_entity_id
          JOIN workflow.logical_attribute AS attribute
            ON attribute.logical_attribute_id = source.logical_attribute_id
           AND attribute.model_id = target.model_id AND attribute.logical_attribute_status = 'active'
         WHERE source.logical_attribute_source_mapping_status = 'active'
        UNION ALL
        SELECT source.support_source_type, source.modeling_assertion_record_id
          FROM target JOIN workflow.dimensional_entity_source_mapping AS source
            ON target.modeled_entity_type = 'dimensional_entity' AND source.model_id = target.model_id
           AND source.dimensional_entity_id = target.modeled_entity_id
         WHERE source.dimensional_entity_source_mapping_status = 'active'
        UNION ALL
        SELECT source.support_source_type, source.modeling_assertion_record_id
          FROM target JOIN workflow.dimensional_attribute_source_mapping AS source
            ON target.modeled_entity_type = 'dimensional_entity' AND source.model_id = target.model_id
           AND source.dimensional_entity_id = target.modeled_entity_id
          JOIN workflow.dimensional_attribute AS attribute
            ON attribute.dimensional_attribute_id = source.dimensional_attribute_id
           AND attribute.model_id = target.model_id
           AND attribute.dimensional_attribute_status = 'active'
         WHERE source.dimensional_attribute_source_mapping_status = 'active'
    ), assertions AS (
        SELECT (document.tenant_id IS NULL OR document.tenant_id = target_model.tenant_id)
           AND (document.system_id IS NULL OR document.system_id =
                target_model.default_mapping_source_system_id) AS matches_default
          FROM support
          JOIN model.modeling_assertion_record AS assertion
            ON assertion.model_id = p_model_id
           AND assertion.modeling_assertion_record_id = support.modeling_assertion_record_id
           AND assertion.modeling_assertion_record_status = 'active'
          JOIN model.modeling_assertion_document AS document
            ON document.modeling_assertion_document_id = assertion.modeling_assertion_document_id
           AND document.is_active
          JOIN model.model AS target_model ON target_model.model_id = p_model_id
         WHERE support.support_source_type = 'assertion'
    )
    SELECT EXISTS (SELECT 1 FROM assertions WHERE matches_default)
       AND NOT EXISTS (SELECT 1 FROM assertions WHERE matches_default IS NOT TRUE)
       AND NOT EXISTS (SELECT 1 FROM support WHERE support_source_type <> 'assertion');
$is_assertion_only_mapping_target$;
REVOKE ALL ON FUNCTION workflow.is_assertion_only_mapping_target(BIGINT, BIGINT, VARCHAR) FROM PUBLIC;

CREATE FUNCTION workflow.list_mapping_source_objects(
    p_model_id BIGINT, p_target_entity_id BIGINT,
    p_modeled_entity_type VARCHAR(30), p_source_system_id BIGINT
)
RETURNS TABLE (
    source_mapping_id BIGINT, modeled_entity_id BIGINT, role TEXT, rationale TEXT,
    mapping_order INTEGER, is_locked BOOLEAN, source_object_id BIGINT,
    source_logical_entity_id BIGINT, source_dimensional_entity_id BIGINT,
    scope_is_locked BOOLEAN, scope_is_active BOOLEAN
)
LANGUAGE SQL STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $list_mapping_source_objects$
    WITH target AS MATERIALIZED (
        SELECT * FROM workflow.modeled_entity AS entity
         WHERE entity.model_id = p_model_id
           AND entity.modeled_entity_type = p_modeled_entity_type
           AND entity.modeled_entity_id = p_target_entity_id AND entity.status = 'active'
           AND NOT EXISTS (
               SELECT 1 FROM model.model AS target_model
                WHERE target_model.model_id = p_model_id
                  AND target_model.default_mapping_source_system_id = p_source_system_id
                  AND workflow.is_assertion_only_mapping_target(
                      p_model_id, p_target_entity_id, p_modeled_entity_type)
           )
    )
    SELECT support.logical_entity_source_mapping_id, target.modeled_entity_id,
           CASE WHEN support.logical_entity_source_mapping_id IS NULL THEN 'candidate' ELSE 'support' END,
           coalesce(support.logical_entity_source_mapping_rationale,
                    'Available source candidate; relevance must be established from evidence.'),
           support.logical_entity_source_mapping_order,
           coalesce(support.logical_entity_source_mapping_is_locked, FALSE),
           input.object_id, NULL::BIGINT, NULL::BIGINT, scope.model_input_scope_is_locked, scope.is_active
      FROM target
      JOIN workflow.list_model_input_sources(p_model_id) AS input
        ON target.modeled_entity_type = 'logical_entity' AND input.source_system_id = p_source_system_id
      JOIN model.model_input_scope AS scope ON scope.model_id = p_model_id AND scope.object_id = input.object_id
      LEFT JOIN workflow.logical_entity_source_mapping AS support
        ON support.model_id = p_model_id AND support.logical_entity_id = target.modeled_entity_id
       AND support.source_object_id = input.object_id AND support.support_source_type = 'object'
       AND support.logical_entity_source_mapping_status = 'active'
    UNION ALL
    SELECT support.dimensional_entity_source_mapping_id, target.modeled_entity_id,
           CASE WHEN target.modeled_entity_type = 'logical_entity' THEN 'lookup'
                ELSE coalesce(support.dimensional_entity_source_role, 'candidate') END,
           CASE WHEN target.modeled_entity_type = 'logical_entity'
                THEN 'Available peer Logical lookup with applied Mapping for the selected source System.'
                ELSE coalesce(support.dimensional_entity_source_mapping_rationale,
                    'Available Logical source candidate; relevance must be established from evidence.') END,
           support.dimensional_entity_source_mapping_order,
           coalesce(support.dimensional_entity_source_mapping_is_locked, FALSE),
           NULL::BIGINT, source.logical_entity_id, NULL::BIGINT, source.logical_entity_is_locked, TRUE
      FROM target
      JOIN workflow.logical_entity AS source ON source.model_id = p_model_id
       AND source.logical_entity_status = 'active'
       AND (target.modeled_entity_type = 'dimensional_entity'
            OR source.logical_entity_id <> target.modeled_entity_id)
      LEFT JOIN workflow.dimensional_entity_source_mapping AS support
        ON target.modeled_entity_type = 'dimensional_entity'
       AND support.model_id = p_model_id AND support.dimensional_entity_id = target.modeled_entity_id
       AND support.source_logical_entity_id = source.logical_entity_id
       AND support.support_source_type = 'logical_entity'
       AND support.dimensional_entity_source_mapping_status = 'active'
     WHERE EXISTS (
         SELECT 1 FROM workflow.mapping_object AS mapping
         JOIN core.system AS system ON system.system_id = mapping.source_system_id AND system.is_active
          WHERE mapping.model_id = p_model_id AND mapping.logical_entity_id = source.logical_entity_id
            AND mapping.modeled_entity_type = 'logical_entity' AND mapping.source_system_id = p_source_system_id
            AND mapping.object_mapping_status = 'active' AND mapping.mapping_transformation_document IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM workflow.logical_attribute AS attribute
                 WHERE attribute.model_id = p_model_id
                   AND attribute.logical_entity_id = source.logical_entity_id
                   AND attribute.logical_attribute_status = 'active'
                   AND NOT EXISTS (
                       SELECT 1 FROM workflow.mapping_attribute AS mapped
                        WHERE mapped.mapping_object_id = mapping.mapping_object_id
                          AND mapped.logical_attribute_id = attribute.logical_attribute_id
                          AND mapped.attribute_mapping_status = 'active'
                          AND mapped.attribute_mapping_transformation_document IS NOT NULL
                   )
            )
     )
    UNION ALL
    SELECT NULL::BIGINT, target.modeled_entity_id, 'lookup'::TEXT,
           'Available peer Dimensional lookup with applied Mapping for the selected source System.'::TEXT,
           NULL::INTEGER, FALSE, NULL::BIGINT, NULL::BIGINT,
           source.dimensional_entity_id, source.dimensional_entity_is_locked, TRUE
      FROM target
      JOIN workflow.dimensional_entity AS source ON source.model_id = p_model_id
       AND source.dimensional_entity_status = 'active'
       AND target.modeled_entity_type = 'dimensional_entity'
       AND source.dimensional_entity_id <> target.modeled_entity_id
     WHERE EXISTS (
         SELECT 1 FROM workflow.mapping_object AS mapping
         JOIN core.system AS system ON system.system_id = mapping.source_system_id AND system.is_active
          WHERE mapping.model_id = p_model_id AND mapping.dimensional_entity_id = source.dimensional_entity_id
            AND mapping.modeled_entity_type = 'dimensional_entity' AND mapping.source_system_id = p_source_system_id
            AND mapping.object_mapping_status = 'active' AND mapping.mapping_transformation_document IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM workflow.dimensional_attribute AS attribute
                 WHERE attribute.model_id = p_model_id
                   AND attribute.dimensional_entity_id = source.dimensional_entity_id
                   AND attribute.dimensional_attribute_status = 'active'
                   AND NOT EXISTS (
                       SELECT 1 FROM workflow.mapping_attribute AS mapped
                        WHERE mapped.mapping_object_id = mapping.mapping_object_id
                          AND mapped.dimensional_attribute_id = attribute.dimensional_attribute_id
                          AND mapped.attribute_mapping_status = 'active'
                          AND mapped.attribute_mapping_transformation_document IS NOT NULL
                   )
            )
     );
$list_mapping_source_objects$;
REVOKE ALL ON FUNCTION workflow.list_mapping_source_objects(BIGINT, BIGINT, VARCHAR, BIGINT) FROM PUBLIC;

CREATE FUNCTION workflow.list_model_attribute_eligibility(p_model_id BIGINT)
RETURNS TABLE (
    model_id BIGINT, object_id BIGINT, attribute_id BIGINT, connection_id BIGINT,
    system_id BIGINT, object_tenant_id BIGINT, object_schema VARCHAR(400), object_name VARCHAR(400),
    attribute_name VARCHAR(400), attribute_ordinal_position INTEGER, zone_code TEXT,
    is_model_input_eligible BOOLEAN
)
LANGUAGE SQL STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $list_model_attribute_eligibility$
    SELECT o.model_id,o.object_id,a.attribute_id,o.connection_id,o.system_id,o.object_tenant_id,
           o.object_schema,o.object_name,a.attribute_name,a.attribute_ordinal_position,o.zone_code,
           o.is_model_input_eligible
      FROM workflow.list_model_object_eligibility(p_model_id) AS o
      JOIN core.attribute AS a ON a.object_id = o.object_id AND a.is_active
     ORDER BY lower(o.object_schema),lower(o.object_name),a.attribute_ordinal_position,lower(a.attribute_name),a.attribute_id;
$list_model_attribute_eligibility$;
REVOKE ALL ON FUNCTION workflow.list_model_attribute_eligibility(BIGINT) FROM PUBLIC;
