-- Atomic application of one validated, ID-free Metadata Change Set.

CREATE FUNCTION mcp.apply_metadata_change_set(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_expected_draft_revision BIGINT,
    p_expected_candidate_digest CHAR(64),
    p_correlation_id UUID
)
RETURNS TABLE (
    applied BOOLEAN,
    denial_code VARCHAR(50),
    metadata_change_set_status VARCHAR(20),
    draft_revision BIGINT,
    applied_time TIMESTAMPTZ,
    action_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core, reference
AS $apply_metadata_change_set$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_touched_object RECORD;
    v_actor VARCHAR(255);
    v_expected_count INTEGER;
    v_affected_count INTEGER;
    v_action_count INTEGER := 0;
    v_applied_time TIMESTAMPTZ;
    v_event_sequence BIGINT;
BEGIN
    IF p_expected_draft_revision < 1
       OR p_expected_candidate_digest IS NULL
       OR p_expected_candidate_digest !~ '^[0-9a-f]{64}$' THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::VARCHAR(20),
            NULL::BIGINT, NULL::TIMESTAMPTZ, NULL::INTEGER;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::VARCHAR(20), NULL::BIGINT, NULL::TIMESTAMPTZ, NULL::INTEGER;
        RETURN;
    END IF;

    SELECT change_set.*
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50),
            NULL::VARCHAR(20), NULL::BIGINT, NULL::TIMESTAMPTZ, NULL::INTEGER;
        RETURN;
    END IF;
    IF v_change_set.metadata_change_set_status <> 'validated' THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_validated'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.applied_time::TIMESTAMPTZ,
            0::INTEGER;
        RETURN;
    END IF;
    IF v_change_set.draft_revision <> p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.applied_time::TIMESTAMPTZ,
            0::INTEGER;
        RETURN;
    END IF;
    IF v_change_set.candidate_digest <> p_expected_candidate_digest THEN
        RETURN QUERY SELECT
            FALSE, 'candidate_digest_conflict'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.applied_time::TIMESTAMPTZ,
            0::INTEGER;
        RETURN;
    END IF;

    FOR v_touched_object IN
        WITH staged_object_keys AS (
            SELECT tenant_code,
                   system_code,
                   connection_code,
                   object_schema,
                   object_name
              FROM jsonb_to_recordset(
                  v_change_set.source_object_document
                  || v_change_set.bronze_object_document
                  || v_change_set.silver_object_document
                  || v_change_set.gold_object_document
              ) AS record (
                  tenant_code VARCHAR(100),
                  system_code VARCHAR(100),
                  connection_code VARCHAR(100),
                  object_schema VARCHAR(400),
                  object_name VARCHAR(400)
              )
        ),
        staged_attribute_object_keys AS (
            SELECT tenant_code,
                   system_code,
                   connection_code,
                   object_schema,
                   object_name
              FROM jsonb_to_recordset(
                  v_change_set.source_attribute_document
                  || v_change_set.bronze_attribute_document
                  || v_change_set.silver_attribute_document
                  || v_change_set.gold_attribute_document
              ) AS record (
                  tenant_code VARCHAR(100),
                  system_code VARCHAR(100),
                  connection_code VARCHAR(100),
                  object_schema VARCHAR(400),
                  object_name VARCHAR(400)
              )
        ),
        touched_object_keys AS (
            SELECT * FROM staged_object_keys
            UNION
            SELECT * FROM staged_attribute_object_keys
        )
        SELECT object.object_id,
               object.is_locked
          FROM touched_object_keys AS touched
          JOIN core.tenant AS tenant
            ON lower(btrim(tenant.tenant_code)) = lower(btrim(touched.tenant_code))
          JOIN core.system AS system
            ON lower(btrim(system.system_code)) = lower(btrim(touched.system_code))
          JOIN core.connection AS connection
            ON connection.system_id = system.system_id
           AND lower(btrim(connection.connection_code))
             = lower(btrim(touched.connection_code))
          JOIN core.object AS object
            ON object.connection_id = connection.connection_id
           AND lower(btrim(object.object_schema)) = lower(btrim(touched.object_schema))
           AND lower(btrim(object.object_name)) = lower(btrim(touched.object_name))
         WHERE (
               NOT connection.is_global_data_store
               AND connection.tenant_id = tenant.tenant_id
           ) OR (
               connection.is_global_data_store
               AND EXISTS (
                   SELECT 1
                     FROM core.tenant_metadata_discovery_scope AS scope
                    WHERE scope.tenant_id = tenant.tenant_id
                      AND scope.gds_connection_id = connection.connection_id
                      AND scope.zone_id = object.zone_id
                      AND lower(btrim(scope.object_schema)) =
                          lower(btrim(touched.object_schema))
                      AND scope.is_active
               )
           )
         FOR UPDATE OF object
    LOOP
        IF v_touched_object.is_locked THEN
            RETURN QUERY SELECT
                FALSE,
                'object_locked'::VARCHAR(50),
                v_change_set.metadata_change_set_status::VARCHAR(20),
                v_change_set.draft_revision::BIGINT,
                v_change_set.applied_time::TIMESTAMPTZ,
                0::INTEGER;
            RETURN;
        END IF;
    END LOOP;

    v_actor := ('principal:' || v_decision.principal_id::TEXT)::VARCHAR(255);
    SET CONSTRAINTS
        core.uq_attribute_object_ordinal,
        core.uq_copy_group_order
    DEFERRED;

    v_expected_count :=
        jsonb_array_length(v_change_set.source_object_document)
        + jsonb_array_length(v_change_set.bronze_object_document)
        + jsonb_array_length(v_change_set.silver_object_document)
        + jsonb_array_length(v_change_set.gold_object_document);
    WITH records AS (
        SELECT *
          FROM jsonb_to_recordset(
              v_change_set.source_object_document
              || v_change_set.bronze_object_document
              || v_change_set.silver_object_document
              || v_change_set.gold_object_document
          ) AS record (
              tenant_code VARCHAR(100),
              system_code VARCHAR(100),
              connection_code VARCHAR(100),
              object_schema VARCHAR(400),
              object_name VARCHAR(400),
              fc_object_schema VARCHAR(400),
              fc_object_name VARCHAR(400),
              object_transformation TEXT,
              object_description TEXT,
              batch_attribute_name VARCHAR(400),
              object_type_code VARCHAR(100),
              zone_code VARCHAR(30),
              is_locked BOOLEAN,
              is_active BOOLEAN
          )
    )
    INSERT INTO core.object AS target (
        connection_id, object_schema, object_name, fc_object_schema,
        fc_object_name, object_transformation, object_description,
        batch_attribute_name, object_type_id, zone_id, is_locked, is_active,
        created_by, updated_by
    )
    SELECT connection.connection_id,
           records.object_schema,
           records.object_name,
           records.fc_object_schema,
           records.fc_object_name,
           records.object_transformation,
           records.object_description,
           records.batch_attribute_name,
           object_type.object_type_id,
           zone.zone_id,
           records.is_locked,
           records.is_active,
           v_actor,
           v_actor
      FROM records
      JOIN core.tenant AS tenant
        ON lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
      JOIN core.system AS system
        ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
      JOIN core.connection AS connection
        ON connection.system_id = system.system_id
       AND lower(btrim(connection.connection_code)) = lower(btrim(records.connection_code))
      JOIN reference.object_type AS object_type
        ON lower(btrim(object_type.object_type_code))
         = lower(btrim(records.object_type_code))
      JOIN reference.zone AS zone
        ON lower(btrim(zone.zone_code)) = lower(btrim(records.zone_code))
     WHERE ((
            NOT connection.is_global_data_store
            AND connection.tenant_id = tenant.tenant_id
       ) OR (
            connection.is_global_data_store
            AND EXISTS (
                SELECT 1
                  FROM core.tenant_metadata_discovery_scope AS scope
                 WHERE scope.tenant_id = tenant.tenant_id
                   AND scope.gds_connection_id = connection.connection_id
                   AND scope.zone_id = zone.zone_id
                   AND lower(btrim(scope.object_schema))
                     = lower(btrim(records.object_schema))
                   AND scope.is_active
            )
        ))
       AND (
            tenant.tenant_id = p_tenant_id
            OR EXISTS (
                SELECT 1
                  FROM core.tenant_metadata_discovery_scope AS authorized_scope
                 WHERE authorized_scope.tenant_id = p_tenant_id
                   AND authorized_scope.gds_connection_id = connection.connection_id
                   AND authorized_scope.zone_id = zone.zone_id
                   AND lower(btrim(authorized_scope.object_schema)) =
                       lower(btrim(records.object_schema))
                   AND authorized_scope.is_active
            )
       )
    ON CONFLICT (
        connection_id,
        (lower(btrim(object_schema))),
        (lower(btrim(object_name)))
    ) DO UPDATE SET
        fc_object_schema = EXCLUDED.fc_object_schema,
        fc_object_name = EXCLUDED.fc_object_name,
        object_transformation = EXCLUDED.object_transformation,
        object_description = EXCLUDED.object_description,
        batch_attribute_name = EXCLUDED.batch_attribute_name,
        object_type_id = EXCLUDED.object_type_id,
        zone_id = EXCLUDED.zone_id,
        is_locked = EXCLUDED.is_locked,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Object natural-key dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count :=
        jsonb_array_length(v_change_set.source_attribute_document)
        + jsonb_array_length(v_change_set.bronze_attribute_document)
        + jsonb_array_length(v_change_set.silver_attribute_document)
        + jsonb_array_length(v_change_set.gold_attribute_document);
    WITH records AS (
        SELECT *
          FROM jsonb_to_recordset(
              v_change_set.source_attribute_document
              || v_change_set.bronze_attribute_document
              || v_change_set.silver_attribute_document
              || v_change_set.gold_attribute_document
          ) AS record (
              tenant_code VARCHAR(100), system_code VARCHAR(100),
              connection_code VARCHAR(100), object_schema VARCHAR(400),
              object_name VARCHAR(400), attribute_name VARCHAR(400),
              fc_attribute_name VARCHAR(400), attribute_ordinal_position INTEGER,
              attribute_description TEXT, attribute_data_type VARCHAR(100),
              attribute_nullability BOOLEAN, attribute_custom_code TEXT,
              is_surrogate_key BOOLEAN, is_natural_key BOOLEAN,
              is_meta_data BOOLEAN, is_masking_required BOOLEAN,
              is_mapped BOOLEAN, is_purge BOOLEAN, is_active BOOLEAN
          )
    )
    INSERT INTO core.attribute AS target (
        object_id, attribute_name, fc_attribute_name, attribute_ordinal_position,
        attribute_description, attribute_data_type, attribute_nullability,
        attribute_custom_code, is_surrogate_key, is_natural_key, is_meta_data,
        is_masking_required, is_mapped, is_purge, is_active,
        created_by, updated_by
    )
    SELECT object.object_id,
           records.attribute_name,
           records.fc_attribute_name,
           records.attribute_ordinal_position,
           records.attribute_description,
           records.attribute_data_type,
           records.attribute_nullability,
           records.attribute_custom_code,
           records.is_surrogate_key,
           records.is_natural_key,
           records.is_meta_data,
           records.is_masking_required,
           records.is_mapped,
           records.is_purge,
           records.is_active,
           v_actor,
           v_actor
      FROM records
      JOIN core.tenant AS tenant
        ON lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
      JOIN core.system AS system
        ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
      JOIN core.connection AS connection
        ON connection.system_id = system.system_id
       AND lower(btrim(connection.connection_code)) = lower(btrim(records.connection_code))
      JOIN core.object AS object
        ON object.connection_id = connection.connection_id
       AND lower(btrim(object.object_schema)) = lower(btrim(records.object_schema))
       AND lower(btrim(object.object_name)) = lower(btrim(records.object_name))
     WHERE ((
            NOT connection.is_global_data_store
            AND connection.tenant_id = tenant.tenant_id
       ) OR (
            connection.is_global_data_store
            AND EXISTS (
                SELECT 1
                  FROM core.tenant_metadata_discovery_scope AS scope
                 WHERE scope.tenant_id = tenant.tenant_id
                   AND scope.gds_connection_id = connection.connection_id
                   AND scope.zone_id = object.zone_id
                   AND lower(btrim(scope.object_schema))
                     = lower(btrim(records.object_schema))
                   AND scope.is_active
            )
        ))
       AND (
            tenant.tenant_id = p_tenant_id
            OR EXISTS (
                SELECT 1
                  FROM core.tenant_metadata_discovery_scope AS authorized_scope
                 WHERE authorized_scope.tenant_id = p_tenant_id
                   AND authorized_scope.gds_connection_id = connection.connection_id
                   AND authorized_scope.zone_id = object.zone_id
                   AND lower(btrim(authorized_scope.object_schema)) =
                       lower(btrim(records.object_schema))
                   AND authorized_scope.is_active
            )
       )
    ON CONFLICT (object_id, (lower(btrim(attribute_name)))) DO UPDATE SET
        fc_attribute_name = EXCLUDED.fc_attribute_name,
        attribute_ordinal_position = EXCLUDED.attribute_ordinal_position,
        attribute_description = EXCLUDED.attribute_description,
        attribute_data_type = EXCLUDED.attribute_data_type,
        attribute_nullability = EXCLUDED.attribute_nullability,
        attribute_custom_code = EXCLUDED.attribute_custom_code,
        is_surrogate_key = EXCLUDED.is_surrogate_key,
        is_natural_key = EXCLUDED.is_natural_key,
        is_meta_data = EXCLUDED.is_meta_data,
        is_masking_required = EXCLUDED.is_masking_required,
        is_mapped = EXCLUDED.is_mapped,
        is_purge = EXCLUDED.is_purge,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Attribute natural-key dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(
        v_change_set.ingestion_object_mapping_document
    );
    WITH records AS (
        SELECT *
          FROM jsonb_to_recordset(v_change_set.ingestion_object_mapping_document)
          AS record (
              source_tenant_code VARCHAR(100), source_system_code VARCHAR(100),
              source_connection_code VARCHAR(100), source_object_schema VARCHAR(400),
              source_object_name VARCHAR(400), target_tenant_code VARCHAR(100),
              target_system_code VARCHAR(100), target_connection_code VARCHAR(100),
              target_object_schema VARCHAR(400), target_object_name VARCHAR(400),
              is_active BOOLEAN
          )
    ), resolved AS (
        SELECT source_object.object_id AS source_object_id,
               target_object.object_id AS target_object_id,
               records.is_active
          FROM records
          JOIN core.tenant AS source_tenant
            ON lower(btrim(source_tenant.tenant_code))
             = lower(btrim(records.source_tenant_code))
          JOIN core.system AS source_system
            ON lower(btrim(source_system.system_code))
             = lower(btrim(records.source_system_code))
          JOIN core.connection AS source_connection
            ON source_connection.system_id = source_system.system_id
           AND lower(btrim(source_connection.connection_code))
             = lower(btrim(records.source_connection_code))
          JOIN core.object AS source_object
            ON source_object.connection_id = source_connection.connection_id
           AND lower(btrim(source_object.object_schema))
             = lower(btrim(records.source_object_schema))
           AND lower(btrim(source_object.object_name))
             = lower(btrim(records.source_object_name))
          JOIN core.tenant AS target_tenant
            ON lower(btrim(target_tenant.tenant_code))
             = lower(btrim(records.target_tenant_code))
          JOIN core.system AS target_system
            ON lower(btrim(target_system.system_code))
             = lower(btrim(records.target_system_code))
          JOIN core.connection AS target_connection
            ON target_connection.system_id = target_system.system_id
           AND lower(btrim(target_connection.connection_code))
             = lower(btrim(records.target_connection_code))
          JOIN core.object AS target_object
            ON target_object.connection_id = target_connection.connection_id
           AND lower(btrim(target_object.object_schema))
             = lower(btrim(records.target_object_schema))
           AND lower(btrim(target_object.object_name))
             = lower(btrim(records.target_object_name))
         WHERE (
               (
                   NOT source_connection.is_global_data_store
                   AND source_connection.tenant_id = source_tenant.tenant_id
               ) OR (
                   source_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS source_scope
                        WHERE source_scope.tenant_id = source_tenant.tenant_id
                          AND source_scope.gds_connection_id =
                              source_connection.connection_id
                          AND source_scope.zone_id = source_object.zone_id
                          AND lower(btrim(source_scope.object_schema)) =
                              lower(btrim(records.source_object_schema))
                          AND source_scope.is_active
                   )
               )
           )
           AND (
               (
                   NOT target_connection.is_global_data_store
                   AND target_connection.tenant_id = target_tenant.tenant_id
               ) OR (
                   target_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS target_scope
                        WHERE target_scope.tenant_id = target_tenant.tenant_id
                          AND target_scope.gds_connection_id =
                              target_connection.connection_id
                          AND target_scope.zone_id = target_object.zone_id
                          AND lower(btrim(target_scope.object_schema)) =
                              lower(btrim(records.target_object_schema))
                          AND target_scope.is_active
                   )
               )
           )
           AND (
               target_tenant.tenant_id = p_tenant_id
               OR (
                target_connection.is_global_data_store
                AND EXISTS (
                    SELECT 1
                      FROM core.tenant_metadata_discovery_scope AS scope
                     WHERE scope.tenant_id = p_tenant_id
                       AND scope.gds_connection_id = target_connection.connection_id
                       AND scope.zone_id = target_object.zone_id
                       AND lower(btrim(scope.object_schema))
                         = lower(btrim(records.target_object_schema))
                       AND scope.is_active
                )
               )
           )
    )
    INSERT INTO core.ingestion_object_mapping AS target (
        source_object_id, target_object_id, is_active, created_by, updated_by
    )
    SELECT source_object_id, target_object_id, is_active, v_actor, v_actor
      FROM resolved
    ON CONFLICT ON CONSTRAINT uq_ingestion_object_source_target DO UPDATE SET
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Ingestion Object Mapping dependency changed'
            USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(
        v_change_set.ingestion_attribute_mapping_document
    );
    WITH records AS (
        SELECT *
          FROM jsonb_to_recordset(v_change_set.ingestion_attribute_mapping_document)
          AS record (
              source_tenant_code VARCHAR(100), source_system_code VARCHAR(100),
              source_connection_code VARCHAR(100), source_object_schema VARCHAR(400),
              source_object_name VARCHAR(400), source_attribute_name VARCHAR(400),
              target_tenant_code VARCHAR(100), target_system_code VARCHAR(100),
              target_connection_code VARCHAR(100), target_object_schema VARCHAR(400),
              target_object_name VARCHAR(400), target_attribute_name VARCHAR(400),
              is_active BOOLEAN
          )
    ), resolved AS (
        SELECT parent.ingestion_object_mapping_id,
               source_object.object_id AS source_object_id,
               target_object.object_id AS target_object_id,
               source_attribute.attribute_id AS source_attribute_id,
               target_attribute.attribute_id AS target_attribute_id,
               records.is_active
          FROM records
          JOIN core.tenant AS source_tenant
            ON lower(btrim(source_tenant.tenant_code))
             = lower(btrim(records.source_tenant_code))
          JOIN core.system AS source_system
            ON lower(btrim(source_system.system_code))
             = lower(btrim(records.source_system_code))
          JOIN core.connection AS source_connection
            ON source_connection.system_id = source_system.system_id
           AND lower(btrim(source_connection.connection_code))
             = lower(btrim(records.source_connection_code))
          JOIN core.object AS source_object
            ON source_object.connection_id = source_connection.connection_id
           AND lower(btrim(source_object.object_schema))
             = lower(btrim(records.source_object_schema))
           AND lower(btrim(source_object.object_name))
             = lower(btrim(records.source_object_name))
          JOIN core.attribute AS source_attribute
            ON source_attribute.object_id = source_object.object_id
           AND lower(btrim(source_attribute.attribute_name))
             = lower(btrim(records.source_attribute_name))
          JOIN core.tenant AS target_tenant
            ON lower(btrim(target_tenant.tenant_code))
             = lower(btrim(records.target_tenant_code))
          JOIN core.system AS target_system
            ON lower(btrim(target_system.system_code))
             = lower(btrim(records.target_system_code))
          JOIN core.connection AS target_connection
            ON target_connection.system_id = target_system.system_id
           AND lower(btrim(target_connection.connection_code))
             = lower(btrim(records.target_connection_code))
          JOIN core.object AS target_object
            ON target_object.connection_id = target_connection.connection_id
           AND lower(btrim(target_object.object_schema))
             = lower(btrim(records.target_object_schema))
           AND lower(btrim(target_object.object_name))
             = lower(btrim(records.target_object_name))
          JOIN core.attribute AS target_attribute
            ON target_attribute.object_id = target_object.object_id
           AND lower(btrim(target_attribute.attribute_name))
             = lower(btrim(records.target_attribute_name))
          JOIN core.ingestion_object_mapping AS parent
            ON parent.source_object_id = source_object.object_id
           AND parent.target_object_id = target_object.object_id
         WHERE (
               (
                   NOT source_connection.is_global_data_store
                   AND source_connection.tenant_id = source_tenant.tenant_id
               ) OR (
                   source_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS source_scope
                        WHERE source_scope.tenant_id = source_tenant.tenant_id
                          AND source_scope.gds_connection_id =
                              source_connection.connection_id
                          AND source_scope.zone_id = source_object.zone_id
                          AND lower(btrim(source_scope.object_schema)) =
                              lower(btrim(records.source_object_schema))
                          AND source_scope.is_active
                   )
               )
           )
           AND (
               (
                   NOT target_connection.is_global_data_store
                   AND target_connection.tenant_id = target_tenant.tenant_id
               ) OR (
                   target_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS target_scope
                        WHERE target_scope.tenant_id = target_tenant.tenant_id
                          AND target_scope.gds_connection_id =
                              target_connection.connection_id
                          AND target_scope.zone_id = target_object.zone_id
                          AND lower(btrim(target_scope.object_schema)) =
                              lower(btrim(records.target_object_schema))
                          AND target_scope.is_active
                   )
               )
           )
           AND (
               target_tenant.tenant_id = p_tenant_id
               OR (
                target_connection.is_global_data_store
                AND EXISTS (
                    SELECT 1
                      FROM core.tenant_metadata_discovery_scope AS scope
                     WHERE scope.tenant_id = p_tenant_id
                       AND scope.gds_connection_id = target_connection.connection_id
                       AND scope.zone_id = target_object.zone_id
                       AND lower(btrim(scope.object_schema))
                         = lower(btrim(records.target_object_schema))
                       AND scope.is_active
                )
               )
           )
    )
    INSERT INTO core.ingestion_attribute_mapping AS target (
        ingestion_object_mapping_id, source_object_id, target_object_id,
        source_attribute_id, target_attribute_id, is_active, created_by, updated_by
    )
    SELECT ingestion_object_mapping_id, source_object_id, target_object_id,
           source_attribute_id, target_attribute_id, is_active, v_actor, v_actor
      FROM resolved
    ON CONFLICT ON CONSTRAINT uq_ingestion_attribute_source_target DO UPDATE SET
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Ingestion Attribute Mapping dependency changed'
            USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(v_change_set.copy_group_document);
    WITH records AS (
        SELECT * FROM jsonb_to_recordset(v_change_set.copy_group_document)
        AS record (
            tenant_code VARCHAR(100), system_code VARCHAR(100),
            copy_group_name VARCHAR(200), copy_group_description TEXT,
            is_member_group_required BOOLEAN, is_active BOOLEAN
        )
    )
    INSERT INTO core.copy_group AS target (
        tenant_id, system_id, copy_group_name, copy_group_description,
        is_member_group_required, is_active, created_by, updated_by
    )
    SELECT tenant.tenant_id, system.system_id, records.copy_group_name,
           records.copy_group_description, records.is_member_group_required,
           records.is_active, v_actor, v_actor
      FROM records
      JOIN core.tenant AS tenant
        ON tenant.tenant_id = p_tenant_id
       AND lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
      JOIN core.system AS system
        ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
    ON CONFLICT (
        tenant_id, system_id, (lower(btrim(copy_group_name)))
    ) DO UPDATE SET
        copy_group_description = EXCLUDED.copy_group_description,
        is_member_group_required = EXCLUDED.is_member_group_required,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Copy Group natural-key dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(v_change_set.member_group_document);
    WITH records AS (
        SELECT * FROM jsonb_to_recordset(v_change_set.member_group_document)
        AS record (
            tenant_code VARCHAR(100), system_code VARCHAR(100),
            member_group_name VARCHAR(200), member_group_description TEXT,
            member_group_initial_load_date DATE, is_active BOOLEAN
        )
    )
    INSERT INTO core.member_group AS target (
        tenant_id, system_id, member_group_name, member_group_description,
        member_group_initial_load_date, is_active, created_by, updated_by
    )
    SELECT tenant.tenant_id, system.system_id, records.member_group_name,
           records.member_group_description, records.member_group_initial_load_date,
           records.is_active, v_actor, v_actor
      FROM records
      JOIN core.tenant AS tenant
        ON tenant.tenant_id = p_tenant_id
       AND lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
      JOIN core.system AS system
        ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
    ON CONFLICT (
        tenant_id, system_id, (lower(btrim(member_group_name)))
    ) DO UPDATE SET
        member_group_description = EXCLUDED.member_group_description,
        member_group_initial_load_date = EXCLUDED.member_group_initial_load_date,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Member Group natural-key dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(v_change_set.copy_group_control_document);
    WITH records AS (
        SELECT * FROM jsonb_to_recordset(v_change_set.copy_group_control_document)
        AS record (
            tenant_code VARCHAR(100), system_code VARCHAR(100),
            copy_group_name VARCHAR(200), member_group_name VARCHAR(200),
            copy_group_control_initial_load_date DATE,
            copy_group_control_last_run_time TIMESTAMPTZ,
            copy_group_control_last_run_value TEXT
        )
    ), resolved AS (
        SELECT copy_group.copy_group_id,
               member_group.member_group_id,
               tenant.tenant_id,
               system.system_id,
               records.copy_group_control_initial_load_date,
               records.copy_group_control_last_run_time,
               records.copy_group_control_last_run_value
          FROM records
          JOIN core.tenant AS tenant
            ON tenant.tenant_id = p_tenant_id
           AND lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
          JOIN core.system AS system
            ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
          JOIN core.copy_group AS copy_group
            ON copy_group.tenant_id = tenant.tenant_id
           AND copy_group.system_id = system.system_id
           AND lower(btrim(copy_group.copy_group_name))
             = lower(btrim(records.copy_group_name))
          LEFT JOIN core.member_group AS member_group
            ON records.member_group_name IS NOT NULL
           AND member_group.tenant_id = tenant.tenant_id
           AND member_group.system_id = system.system_id
           AND lower(btrim(member_group.member_group_name))
             = lower(btrim(records.member_group_name))
         WHERE records.member_group_name IS NULL OR member_group.member_group_id IS NOT NULL
    )
    INSERT INTO core.copy_group_control AS target (
        copy_group_id, member_group_id, tenant_id, system_id,
        copy_group_control_initial_load_date, copy_group_control_last_run_time,
        copy_group_control_last_run_value, created_by, updated_by
    )
    SELECT copy_group_id, member_group_id, tenant_id, system_id,
           copy_group_control_initial_load_date, copy_group_control_last_run_time,
           copy_group_control_last_run_value, v_actor, v_actor
      FROM resolved
    ON CONFLICT ON CONSTRAINT uq_copy_group_control DO UPDATE SET
        copy_group_control_initial_load_date
            = EXCLUDED.copy_group_control_initial_load_date,
        copy_group_control_last_run_time = EXCLUDED.copy_group_control_last_run_time,
        copy_group_control_last_run_value = EXCLUDED.copy_group_control_last_run_value,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Copy Group Control dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(v_change_set.copy_document);
    WITH records AS (
        SELECT * FROM jsonb_to_recordset(v_change_set.copy_document)
        AS record (
            tenant_code VARCHAR(100), system_code VARCHAR(100),
            copy_group_name VARCHAR(200), source_tenant_code VARCHAR(100),
            source_system_code VARCHAR(100), source_connection_code VARCHAR(100),
            source_object_schema VARCHAR(400), source_object_name VARCHAR(400),
            target_tenant_code VARCHAR(100), target_system_code VARCHAR(100),
            target_connection_code VARCHAR(100), target_object_schema VARCHAR(400),
            target_object_name VARCHAR(400), copy_source_record_limit TEXT,
            copy_source_record_limit_attribute VARCHAR(400), chunk_type_name VARCHAR(200),
            copy_source_initial_sql_script TEXT, copy_source_incremental_sql_script TEXT,
            copy_source_file_name TEXT, copy_source_file_pattern TEXT,
            copy_source_file_delimiter VARCHAR(20), source_file_type_name VARCHAR(200),
            copy_source_order INTEGER, source_data_operation_name VARCHAR(200),
            target_data_operation_name VARCHAR(200), is_active BOOLEAN
        )
    ), resolved AS (
        SELECT copy_group.copy_group_id,
               mapping.ingestion_object_mapping_id,
               records.copy_source_record_limit,
               records.copy_source_record_limit_attribute,
               chunk_type.chunk_type_id,
               records.copy_source_initial_sql_script,
               records.copy_source_incremental_sql_script,
               records.copy_source_file_name,
               records.copy_source_file_pattern,
               records.copy_source_file_delimiter,
               file_type.file_type_id AS source_file_type_id,
               records.copy_source_order,
               source_operation.data_operation_id AS source_data_operation_id,
               target_operation.data_operation_id AS target_data_operation_id,
               records.is_active
          FROM records
          JOIN core.tenant AS tenant
            ON tenant.tenant_id = p_tenant_id
           AND lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
          JOIN core.system AS system
            ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
          JOIN core.copy_group AS copy_group
            ON copy_group.tenant_id = tenant.tenant_id
           AND copy_group.system_id = system.system_id
           AND lower(btrim(copy_group.copy_group_name))
             = lower(btrim(records.copy_group_name))
          JOIN core.tenant AS source_tenant
            ON lower(btrim(source_tenant.tenant_code))
             = lower(btrim(records.source_tenant_code))
          JOIN core.system AS source_system
            ON lower(btrim(source_system.system_code))
             = lower(btrim(records.source_system_code))
          JOIN core.connection AS source_connection
            ON source_connection.system_id = source_system.system_id
           AND lower(btrim(source_connection.connection_code))
             = lower(btrim(records.source_connection_code))
          JOIN core.object AS source_object
            ON source_object.connection_id = source_connection.connection_id
           AND lower(btrim(source_object.object_schema))
             = lower(btrim(records.source_object_schema))
           AND lower(btrim(source_object.object_name))
             = lower(btrim(records.source_object_name))
          JOIN core.tenant AS target_tenant
            ON lower(btrim(target_tenant.tenant_code))
             = lower(btrim(records.target_tenant_code))
          JOIN core.system AS target_system
            ON lower(btrim(target_system.system_code))
             = lower(btrim(records.target_system_code))
          JOIN core.connection AS target_connection
            ON target_connection.system_id = target_system.system_id
           AND lower(btrim(target_connection.connection_code))
             = lower(btrim(records.target_connection_code))
          JOIN core.object AS target_object
            ON target_object.connection_id = target_connection.connection_id
           AND lower(btrim(target_object.object_schema))
             = lower(btrim(records.target_object_schema))
           AND lower(btrim(target_object.object_name))
             = lower(btrim(records.target_object_name))
          JOIN core.ingestion_object_mapping AS mapping
            ON mapping.source_object_id = source_object.object_id
           AND mapping.target_object_id = target_object.object_id
          LEFT JOIN reference.chunk_type AS chunk_type
            ON records.chunk_type_name IS NOT NULL
           AND lower(btrim(chunk_type.chunk_type_name))
             = lower(btrim(records.chunk_type_name))
          LEFT JOIN reference.file_type AS file_type
            ON records.source_file_type_name IS NOT NULL
           AND lower(btrim(file_type.file_type_name))
             = lower(btrim(records.source_file_type_name))
          JOIN reference.data_operation AS source_operation
            ON lower(btrim(source_operation.data_operation_name))
             = lower(btrim(records.source_data_operation_name))
          JOIN reference.data_operation AS target_operation
            ON lower(btrim(target_operation.data_operation_name))
             = lower(btrim(records.target_data_operation_name))
         WHERE (
               (
                   NOT source_connection.is_global_data_store
                   AND source_connection.tenant_id = source_tenant.tenant_id
               ) OR (
                   source_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS source_scope
                        WHERE source_scope.tenant_id = source_tenant.tenant_id
                          AND source_scope.gds_connection_id =
                              source_connection.connection_id
                          AND source_scope.zone_id = source_object.zone_id
                          AND lower(btrim(source_scope.object_schema)) =
                              lower(btrim(records.source_object_schema))
                          AND source_scope.is_active
                   )
               )
           )
           AND (
               (
                   NOT target_connection.is_global_data_store
                   AND target_connection.tenant_id = target_tenant.tenant_id
               ) OR (
                   target_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS target_scope
                        WHERE target_scope.tenant_id = target_tenant.tenant_id
                          AND target_scope.gds_connection_id =
                              target_connection.connection_id
                          AND target_scope.zone_id = target_object.zone_id
                          AND lower(btrim(target_scope.object_schema)) =
                              lower(btrim(records.target_object_schema))
                          AND target_scope.is_active
                   )
               )
           )
           AND (records.chunk_type_name IS NULL OR chunk_type.chunk_type_id IS NOT NULL)
           AND (records.source_file_type_name IS NULL OR file_type.file_type_id IS NOT NULL)
           AND (
               target_tenant.tenant_id = p_tenant_id
               OR (
                   target_connection.is_global_data_store
                   AND EXISTS (
                       SELECT 1
                         FROM core.tenant_metadata_discovery_scope AS scope
                        WHERE scope.tenant_id = p_tenant_id
                          AND scope.gds_connection_id = target_connection.connection_id
                          AND scope.zone_id = target_object.zone_id
                          AND lower(btrim(scope.object_schema))
                            = lower(btrim(records.target_object_schema))
                          AND scope.is_active
                   )
               )
           )
    )
    INSERT INTO core.copy AS target (
        copy_group_id, ingestion_object_mapping_id, copy_source_record_limit,
        copy_source_record_limit_attribute, chunk_type_id,
        copy_source_initial_sql_script, copy_source_incremental_sql_script,
        copy_source_file_name, copy_source_file_pattern, copy_source_file_delimiter,
        source_file_type_id, copy_source_order, source_data_operation_id,
        target_data_operation_id, is_active, created_by, updated_by
    )
    SELECT copy_group_id,
           ingestion_object_mapping_id,
           NULLIF(copy_source_record_limit, '')::BIGINT,
           copy_source_record_limit_attribute,
           chunk_type_id,
           copy_source_initial_sql_script,
           copy_source_incremental_sql_script,
           copy_source_file_name,
           copy_source_file_pattern,
           copy_source_file_delimiter,
           source_file_type_id,
           copy_source_order,
           source_data_operation_id,
           target_data_operation_id,
           is_active,
           v_actor,
           v_actor
      FROM resolved
    ON CONFLICT ON CONSTRAINT uq_copy_group_mapping DO UPDATE SET
        copy_source_record_limit = EXCLUDED.copy_source_record_limit,
        copy_source_record_limit_attribute = EXCLUDED.copy_source_record_limit_attribute,
        chunk_type_id = EXCLUDED.chunk_type_id,
        copy_source_initial_sql_script = EXCLUDED.copy_source_initial_sql_script,
        copy_source_incremental_sql_script = EXCLUDED.copy_source_incremental_sql_script,
        copy_source_file_name = EXCLUDED.copy_source_file_name,
        copy_source_file_pattern = EXCLUDED.copy_source_file_pattern,
        copy_source_file_delimiter = EXCLUDED.copy_source_file_delimiter,
        source_file_type_id = EXCLUDED.source_file_type_id,
        copy_source_order = EXCLUDED.copy_source_order,
        source_data_operation_id = EXCLUDED.source_data_operation_id,
        target_data_operation_id = EXCLUDED.target_data_operation_id,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Copy dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(v_change_set.process_group_document);
    WITH records AS (
        SELECT * FROM jsonb_to_recordset(v_change_set.process_group_document)
        AS record (
            tenant_code VARCHAR(100), system_code VARCHAR(100), zone_code VARCHAR(30),
            process_group_name VARCHAR(200), process_group_description TEXT,
            copy_group_name VARCHAR(200), is_active BOOLEAN
        )
    )
    INSERT INTO core.process_group AS target (
        tenant_id, system_id, zone_id, process_group_name,
        process_group_description, copy_group_id, is_active, created_by, updated_by
    )
    SELECT tenant.tenant_id, system.system_id, zone.zone_id,
           records.process_group_name, records.process_group_description,
           copy_group.copy_group_id, records.is_active, v_actor, v_actor
      FROM records
      JOIN core.tenant AS tenant
        ON tenant.tenant_id = p_tenant_id
       AND lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
      JOIN core.system AS system
        ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
      JOIN reference.zone AS zone
        ON lower(btrim(zone.zone_code)) = lower(btrim(records.zone_code))
      JOIN core.copy_group AS copy_group
        ON copy_group.tenant_id = tenant.tenant_id
       AND copy_group.system_id = system.system_id
       AND lower(btrim(copy_group.copy_group_name))
         = lower(btrim(records.copy_group_name))
    ON CONFLICT (
        tenant_id, system_id, zone_id, (lower(btrim(process_group_name)))
    ) DO UPDATE SET
        process_group_description = EXCLUDED.process_group_description,
        copy_group_id = EXCLUDED.copy_group_id,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Process Group natural-key dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    v_expected_count := jsonb_array_length(v_change_set.process_document);
    WITH records AS (
        SELECT * FROM jsonb_to_recordset(v_change_set.process_document)
        AS record (
            tenant_code VARCHAR(100), system_code VARCHAR(100), zone_code VARCHAR(30),
            process_group_name VARCHAR(200), process_execution_order INTEGER,
            process_location TEXT, process_executable TEXT,
            object_tenant_code VARCHAR(100), object_system_code VARCHAR(100),
            object_connection_code VARCHAR(100), object_schema VARCHAR(400),
            object_name VARCHAR(400), process_type_name VARCHAR(200), is_active BOOLEAN
        )
    ), resolved AS (
        SELECT process_group.process_group_id,
               object_connection.connection_id,
               object.object_id,
               records.process_execution_order,
               records.process_location,
               records.process_executable,
               process_type.process_type_id,
               records.is_active
          FROM records
          JOIN core.tenant AS tenant
            ON tenant.tenant_id = p_tenant_id
           AND lower(btrim(tenant.tenant_code)) = lower(btrim(records.tenant_code))
          JOIN core.system AS system
            ON lower(btrim(system.system_code)) = lower(btrim(records.system_code))
          JOIN reference.zone AS zone
            ON lower(btrim(zone.zone_code)) = lower(btrim(records.zone_code))
          JOIN core.process_group AS process_group
            ON process_group.tenant_id = tenant.tenant_id
           AND process_group.system_id = system.system_id
           AND process_group.zone_id = zone.zone_id
           AND lower(btrim(process_group.process_group_name))
             = lower(btrim(records.process_group_name))
          JOIN core.tenant AS object_tenant
            ON lower(btrim(object_tenant.tenant_code))
             = lower(btrim(records.object_tenant_code))
          JOIN core.system AS object_system
            ON lower(btrim(object_system.system_code))
             = lower(btrim(records.object_system_code))
          JOIN core.connection AS object_connection
            ON object_connection.system_id = object_system.system_id
           AND lower(btrim(object_connection.connection_code))
             = lower(btrim(records.object_connection_code))
          JOIN core.object AS object
            ON object.connection_id = object_connection.connection_id
           AND lower(btrim(object.object_schema)) = lower(btrim(records.object_schema))
           AND lower(btrim(object.object_name)) = lower(btrim(records.object_name))
          JOIN reference.process_type AS process_type
            ON lower(btrim(process_type.process_type_name))
             = lower(btrim(records.process_type_name))
         WHERE (
               NOT object_connection.is_global_data_store
               AND object_connection.tenant_id = object_tenant.tenant_id
           ) OR (
               object_connection.is_global_data_store
               AND EXISTS (
                   SELECT 1
                     FROM core.tenant_metadata_discovery_scope AS object_scope
                    WHERE object_scope.tenant_id = object_tenant.tenant_id
                      AND object_scope.gds_connection_id =
                          object_connection.connection_id
                      AND object_scope.zone_id = object.zone_id
                      AND lower(btrim(object_scope.object_schema)) =
                          lower(btrim(records.object_schema))
                      AND object_scope.is_active
               )
           )
    )
    INSERT INTO core.process AS target (
        connection_id, object_id, process_execution_order, process_location,
        process_executable, process_type_id, process_group_id, is_active,
        created_by, updated_by
    )
    SELECT connection_id, object_id, process_execution_order, process_location,
           process_executable, process_type_id, process_group_id, is_active,
           v_actor, v_actor
      FROM resolved
    ON CONFLICT ON CONSTRAINT uq_process_group_order DO UPDATE SET
        connection_id = EXCLUDED.connection_id,
        object_id = EXCLUDED.object_id,
        process_type_id = EXCLUDED.process_type_id,
        is_active = EXCLUDED.is_active,
        updated_time = CURRENT_TIMESTAMP,
        updated_by = EXCLUDED.updated_by;
    GET DIAGNOSTICS v_affected_count = ROW_COUNT;
    IF v_affected_count <> v_expected_count THEN
        RAISE EXCEPTION 'Process dependency changed' USING ERRCODE = '40001';
    END IF;
    v_action_count := v_action_count + v_affected_count;

    UPDATE mcp.metadata_change_set AS change_set
       SET metadata_change_set_status = 'applied',
           applied_time = CURRENT_TIMESTAMP,
           terminal_time = CURRENT_TIMESTAMP,
           last_activity_time = CURRENT_TIMESTAMP,
           expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
    RETURNING change_set.applied_time INTO v_applied_time;

    SELECT coalesce(max(event.event_sequence), 0) + 1
      INTO v_event_sequence
      FROM mcp.metadata_change_set_event AS event
     WHERE event.metadata_change_set_id = p_metadata_change_set_id;
    INSERT INTO mcp.metadata_change_set_event (
        metadata_change_set_id, tenant_id, event_sequence, event_type,
        draft_revision, action_count, outcome, correlation_id
    ) VALUES (
        p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'applied',
        v_change_set.draft_revision, v_action_count, 'applied', p_correlation_id
    );

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        'applied'::VARCHAR(20),
        v_change_set.draft_revision::BIGINT,
        v_applied_time,
        v_action_count;
END;
$apply_metadata_change_set$;
