-- GDS ETL Workbench Release 1: governed workflow execution and persistence.

-- Resolve the complete immutable physical input for one running Profiling Run.
-- Relation catalog ownership comes from core.object.source_tenant_id.
CREATE FUNCTION application.get_profiling_execution_context(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    requested_batch_id VARCHAR(500),
    selection_order INTEGER,
    source_tenant_id BIGINT,
    source_tenant_code VARCHAR(100),
    zone_code TEXT,
    source_connection_id BIGINT,
    gds_connection_id BIGINT,
    has_foreign_catalog BOOLEAN,
    foreign_catalog VARCHAR(255),
    object_schema VARCHAR(400),
    object_name VARCHAR(400),
    fc_object_schema VARCHAR(400),
    fc_object_name VARCHAR(400),
    relation_catalog VARCHAR(255),
    relation_schema VARCHAR(400),
    relation_object VARCHAR(400),
    system_id BIGINT,
    system_code VARCHAR(100),
    object_id BIGINT,
    batch_attribute_name VARCHAR(400),
    attribute_id BIGINT,
    attribute_name VARCHAR(400),
    fc_attribute_name VARCHAR(400),
    relation_attribute VARCHAR(400),
    attribute_data_type VARCHAR(100),
    attribute_ordinal_position INTEGER,
    is_batch_attribute BOOLEAN
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_profiling_execution_context$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_selected_scope_count INTEGER;
    v_eligible_object_count INTEGER;
    v_owned_object_count INTEGER;
    v_attribute_object_count INTEGER;
    v_attribute_count INTEGER;
BEGIN
    IF p_workflow_run_id IS NULL
       OR p_workflow_run_id < 1
       OR p_expected_model_revision IS NULL
       OR p_expected_model_revision < 1 THEN
        RAISE EXCEPTION
            'invalid_request: Profiling execution context input is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.model_workflow,
           run.workflow_run_state,
           run.requested_batch_id,
           run.selected_scope_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR SHARE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'profiling_run_not_found: Profiling Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'profiling_execution_denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION
            'workflow_run_owner_mismatch: Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'profiling'
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'profiling_run_not_running: A running Profiling Workflow Run is required';
    END IF;
    IF v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_selected_scope_count
      FROM application.workflow_run_object_selection AS selection
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_selected_scope_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_scope_incomplete: Workflow Run Selected Scope is incomplete';
    END IF;

    SELECT count(DISTINCT selection.object_id)::INTEGER
      INTO v_owned_object_count
      FROM application.workflow_run_object_selection AS selection
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.source_tenant_id = v_run.tenant_id
       AND object_record.is_active
      JOIN core.connection AS source_connection
        ON source_connection.connection_id = object_record.connection_id
       AND source_connection.is_active
      JOIN core.system AS system_record
        ON system_record.system_id = source_connection.system_id
       AND system_record.is_active
      JOIN reference.zone AS zone_record
        ON zone_record.zone_id = object_record.zone_id
       AND zone_record.is_active
       AND lower(btrim(zone_record.zone_code)) IN ('source', 'bronze')
      JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = object_record.source_tenant_id
       AND source_tenant.is_active
      JOIN core.connection AS gds_connection
        ON gds_connection.connection_id = source_tenant.gds_connection_id
       AND gds_connection.is_active
       AND gds_connection.is_global_data_store
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
       AND CASE lower(btrim(zone_record.zone_code))
               WHEN 'source' THEN
                   source_connection.has_foreign_catalog
                   AND reference.is_nonblank(source_connection.foreign_catalog)
                   AND reference.is_nonblank(object_record.fc_object_schema)
                   AND reference.is_nonblank(object_record.fc_object_name)
               WHEN 'bronze' THEN
                   source_connection.connection_id =
                       source_tenant.gds_connection_id
               ELSE FALSE
           END;
    IF v_owned_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_relation_unavailable: Every selected Object must be an eligible Source foreign-catalog or Bronze relation owned by the Model Tenant';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_eligible_object_count
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_object_eligibility(v_run.model_id) AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_model_input_eligible
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_eligible_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_scope_changed: Selected Model Input Scope membership has changed';
    END IF;

    SELECT count(DISTINCT eligible.object_id)::INTEGER,
           count(*)::INTEGER
      INTO v_attribute_object_count,
           v_attribute_count
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id) AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_model_input_eligible
      JOIN core.object AS selected_object
        ON selected_object.object_id = eligible.object_id
      JOIN reference.zone AS selected_zone
        ON selected_zone.zone_id = selected_object.zone_id
      JOIN core.attribute AS selected_attribute
        ON selected_attribute.attribute_id = eligible.attribute_id
       AND selected_attribute.object_id = eligible.object_id
       AND (
           lower(btrim(selected_zone.zone_code)) = 'bronze'
           OR reference.is_nonblank(selected_attribute.fc_attribute_name)
       )
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_attribute_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_attributes_missing: Every selected Object requires one active eligible Attribute';
    END IF;
    IF v_attribute_count > 50000 THEN
        RAISE EXCEPTION
            'profiling_context_too_large: Profiling execution exceeds 50000 Attributes';
    END IF;

    RETURN QUERY
    SELECT v_run.workflow_run_id,
           v_run.model_id,
           v_run.model_revision,
           v_run.requested_batch_id,
           selection.selection_order,
           source_tenant.tenant_id,
           source_tenant.tenant_code,
           lower(btrim(zone_record.zone_code)),
           source_connection.connection_id,
           gds_connection.connection_id,
           source_connection.has_foreign_catalog,
           source_connection.foreign_catalog,
           object_record.object_schema,
           object_record.object_name,
           object_record.fc_object_schema,
           object_record.fc_object_name,
           CASE lower(btrim(zone_record.zone_code))
               WHEN 'source' THEN source_connection.foreign_catalog
               ELSE source_tenant.tenant_catalog
           END,
           CASE lower(btrim(zone_record.zone_code))
               WHEN 'source' THEN object_record.fc_object_schema
               ELSE object_record.object_schema
           END,
           CASE lower(btrim(zone_record.zone_code))
               WHEN 'source' THEN object_record.fc_object_name
               ELSE object_record.object_name
           END,
           system_record.system_id,
           system_record.system_code,
           object_record.object_id,
           object_record.batch_attribute_name,
           eligible.attribute_id,
           eligible.attribute_name,
           attribute_record.fc_attribute_name,
           CASE lower(btrim(zone_record.zone_code))
               WHEN 'source' THEN attribute_record.fc_attribute_name
               ELSE attribute_record.attribute_name
           END,
           attribute_record.attribute_data_type,
           eligible.attribute_ordinal_position,
           object_record.batch_attribute_name IS NOT NULL
           AND lower(btrim(object_record.batch_attribute_name)) =
               lower(btrim(eligible.attribute_name))
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id) AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_model_input_eligible
      JOIN core.attribute AS attribute_record
        ON attribute_record.attribute_id = eligible.attribute_id
       AND attribute_record.object_id = eligible.object_id
       AND attribute_record.is_active
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.source_tenant_id = v_run.tenant_id
       AND object_record.is_active
      JOIN core.connection AS source_connection
        ON source_connection.connection_id = object_record.connection_id
       AND source_connection.is_active
      JOIN core.system AS system_record
        ON system_record.system_id = source_connection.system_id
       AND system_record.is_active
      JOIN reference.zone AS zone_record
        ON zone_record.zone_id = object_record.zone_id
       AND zone_record.is_active
       AND lower(btrim(zone_record.zone_code)) IN ('source', 'bronze')
      JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = object_record.source_tenant_id
       AND source_tenant.is_active
      JOIN core.connection AS gds_connection
        ON gds_connection.connection_id = source_tenant.gds_connection_id
       AND gds_connection.is_active
       AND gds_connection.is_global_data_store
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
       AND CASE lower(btrim(zone_record.zone_code))
               WHEN 'source' THEN
                   source_connection.has_foreign_catalog
                   AND reference.is_nonblank(source_connection.foreign_catalog)
                   AND reference.is_nonblank(object_record.fc_object_schema)
                   AND reference.is_nonblank(object_record.fc_object_name)
                   AND reference.is_nonblank(attribute_record.fc_attribute_name)
               WHEN 'bronze' THEN
                   source_connection.connection_id =
                       source_tenant.gds_connection_id
               ELSE FALSE
           END
     ORDER BY selection.selection_order,
              eligible.attribute_ordinal_position,
              eligible.attribute_id;
END;
$get_profiling_execution_context$;

REVOKE ALL ON FUNCTION application.get_profiling_execution_context(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) FROM PUBLIC;
-- Return one credential tuple per exact GDS Connection selected through the
-- validated execution context. Any configuration gap returns one fixed safe
-- failure row and no partial credential values.
CREATE FUNCTION application.get_profiling_connection_values(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    gds_connection_id BIGINT,
    environment_code VARCHAR(100),
    failure_code VARCHAR(50),
    failure_message VARCHAR(200),
    databricks_host_name TEXT,
    databricks_http_path TEXT,
    databricks_token TEXT
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_profiling_connection_values$
DECLARE
    v_workflow_run_id BIGINT;
    v_model_id BIGINT;
    v_model_revision BIGINT;
    v_gds_connection_ids BIGINT[];
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_connection_count INTEGER;
    v_complete_connection_count INTEGER;
    v_connection_snapshot JSONB;
BEGIN
    SELECT min(context.workflow_run_id),
           min(context.model_id),
           min(context.model_revision),
           array_agg(
               DISTINCT context.gds_connection_id
               ORDER BY context.gds_connection_id
           )
      INTO v_workflow_run_id,
           v_model_id,
           v_model_revision,
           v_gds_connection_ids
      FROM application.get_profiling_execution_context(
               p_entra_tenant_id,
               p_entra_object_id,
               p_expected_principal_type,
               p_workflow_run_id,
               p_expected_model_revision
           ) AS context;
    v_connection_count := cardinality(v_gds_connection_ids);

    IF p_environment_code IS NULL
       OR NOT reference.is_nonblank(p_environment_code)
       OR length(btrim(p_environment_code)) > 100 THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'invalid_request'::VARCHAR(50),
            'Profiling Environment input is invalid.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id,
           v_environment_code
     FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code))
     FOR SHARE OF environment_record;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'environment_not_found'::VARCHAR(50),
            'Profiling Environment is unavailable.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    -- Read every required value once. Completeness checks and returned secret
    -- tuples use this exact local snapshot, never a second table read.
    WITH requested_connection AS (
        SELECT connection_id
          FROM unnest(v_gds_connection_ids) AS requested(connection_id)
    ), connection_values AS MATERIALIZED (
        SELECT requested.connection_id,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_host_name'
               ) AS databricks_host_name,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_http_path'
               ) AS databricks_http_path,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_token'
               ) AS databricks_token
          FROM requested_connection AS requested
          JOIN core.connection AS gds_connection
            ON gds_connection.connection_id = requested.connection_id
           AND gds_connection.is_active
           AND gds_connection.is_global_data_store
          LEFT JOIN core.connection_value AS connection_value
            ON connection_value.connection_id = requested.connection_id
           AND connection_value.environment_id = v_environment_id
          LEFT JOIN reference.connection_parameter AS parameter
            ON parameter.connection_parameter_id =
               connection_value.connection_parameter_id
           AND parameter.is_active
           AND lower(btrim(parameter.connection_parameter_code)) IN (
                   'databricks_host_name',
                   'databricks_http_path',
                   'databricks_token'
               )
         GROUP BY requested.connection_id
    )
    SELECT jsonb_build_object(
               'complete_connection_count',
               count(*) FILTER (
                   WHERE values.databricks_host_name IS NOT NULL
                     AND values.databricks_http_path IS NOT NULL
                     AND values.databricks_token IS NOT NULL
               )::INTEGER,
               'rows', coalesce(
                   jsonb_agg(
                       jsonb_build_object(
                           'gds_connection_id', values.connection_id,
                           'databricks_host_name',
                           values.databricks_host_name,
                           'databricks_http_path',
                           values.databricks_http_path,
                           'databricks_token', values.databricks_token
                       )
                       ORDER BY values.connection_id
                   ),
                   '[]'::JSONB
               )
           )
      INTO v_connection_snapshot
      FROM connection_values AS values;
    v_complete_connection_count :=
        (v_connection_snapshot ->> 'complete_connection_count')::INTEGER;
    IF v_connection_count IS NULL
       OR v_connection_count < 1
       OR v_complete_connection_count <> v_connection_count THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            v_environment_code,
            'connection_values_missing'::VARCHAR(50),
            'Profiling GDS connection values are incomplete.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT v_workflow_run_id,
           v_model_id,
           v_model_revision,
           snapshot.gds_connection_id,
           v_environment_code,
           NULL::VARCHAR(50),
           NULL::VARCHAR(200),
           snapshot.databricks_host_name,
           snapshot.databricks_http_path,
           snapshot.databricks_token
      FROM jsonb_to_recordset(v_connection_snapshot -> 'rows') AS snapshot(
               gds_connection_id BIGINT,
               databricks_host_name TEXT,
               databricks_http_path TEXT,
               databricks_token TEXT
           )
     ORDER BY snapshot.gds_connection_id;
END;
$get_profiling_connection_values$;

REVOKE ALL ON FUNCTION application.get_profiling_connection_values(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

-- Resolve the complete immutable physical input for one running deterministic
-- Analysis validation Run. A relationship is eligible only when both endpoint
-- Objects are selected. Validation may refresh locked rows because it never
-- changes inference-owned or user-owned fields.
CREATE FUNCTION application.get_analysis_validation_execution_context(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    requested_batch_id VARCHAR(500),
    analysis_result_id BIGINT,
    relationship_kind VARCHAR(100),
    relationship_confidence VARCHAR(10),
    relationship_basis TEXT,
    analysis_result_status VARCHAR(20),
    analysis_result_is_locked BOOLEAN,
    gds_connection_id BIGINT,
    source_context_digest CHAR(64),
    from_relation_catalog VARCHAR(255),
    from_relation_schema VARCHAR(400),
    from_relation_object VARCHAR(400),
    from_object_id BIGINT,
    from_attribute_id BIGINT,
    from_attribute_name VARCHAR(400),
    from_attribute_data_type VARCHAR(100),
    from_batch_attribute_name VARCHAR(400),
    from_batch_attribute_data_type VARCHAR(100),
    to_relation_catalog VARCHAR(255),
    to_relation_schema VARCHAR(400),
    to_relation_object VARCHAR(400),
    to_object_id BIGINT,
    to_attribute_id BIGINT,
    to_attribute_name VARCHAR(400),
    to_attribute_data_type VARCHAR(100),
    to_batch_attribute_name VARCHAR(400),
    to_batch_attribute_data_type VARCHAR(100)
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_analysis_validation_execution_context$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_actor_entra_principal_identity_id BIGINT;
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_selected_scope_count INTEGER;
    v_partial_relationship_count INTEGER;
    v_relationship_count INTEGER;
    v_resolved_relationship_count INTEGER;
    v_cross_connection_count INTEGER;
    v_context_snapshot JSONB;
BEGIN
    IF p_workflow_run_id IS NULL
       OR p_workflow_run_id < 1
       OR p_expected_model_revision IS NULL
       OR p_expected_model_revision < 1
       OR p_environment_code IS NULL
       OR NOT reference.is_nonblank(p_environment_code)
       OR length(btrim(p_environment_code)) > 100 THEN
        RAISE EXCEPTION
            'invalid_request: Analysis validation execution context input is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.actor_entra_principal_identity_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.workflow_run_state,
           run.requested_batch_id,
           run.selected_scope_digest,
           run.selected_scope_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR SHARE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_found: Analysis Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'analysis_validation_execution_denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    SELECT identity.entra_principal_identity_id
      INTO v_actor_entra_principal_identity_id
      FROM security.entra_principal_identity AS identity
     WHERE identity.principal_id = v_decision.principal_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.is_active
     FOR SHARE OF identity;
    IF NOT FOUND
       OR v_run.actor_principal_id <> v_decision.principal_id
       OR v_run.actor_entra_principal_identity_id IS DISTINCT FROM
          v_actor_entra_principal_identity_id THEN
        RAISE EXCEPTION
            'workflow_run_owner_mismatch: Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'analysis'
       OR v_run.workflow_execution_mode IS NOT NULL
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_running: A running deterministic Analysis Workflow Run is required';
    END IF;
    IF v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id,
           v_environment_code
      FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code))
     FOR SHARE OF environment_record;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'analysis_validation_environment_not_found: Analysis validation Environment is unavailable';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_selected_scope_count
      FROM application.workflow_run_object_selection AS selection
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_selected_scope_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'analysis_validation_scope_incomplete: Workflow Run Selected Scope is incomplete';
    END IF;

    -- Resolve and serialize the complete relationship context in one SQL
    -- statement. All subsequent checks and returned rows use this exact local
    -- snapshot, so concurrent metadata changes cannot split validation from
    -- execution input.
    WITH relationship_membership AS MATERIALIZED (
        SELECT result.*,
               from_selection.object_id IS NOT NULL AS from_is_selected,
               to_selection.object_id IS NOT NULL AS to_is_selected
          FROM workflow.analysis_result AS result
          LEFT JOIN application.workflow_run_object_selection
               AS from_selection
            ON from_selection.workflow_run_id = p_workflow_run_id
           AND from_selection.model_id = result.model_id
           AND from_selection.object_id = result.from_object_id
          LEFT JOIN application.workflow_run_object_selection AS to_selection
            ON to_selection.workflow_run_id = p_workflow_run_id
           AND to_selection.model_id = result.model_id
           AND to_selection.object_id = result.to_object_id
         WHERE result.model_id = v_run.model_id
           AND result.analysis_result_status = 'active'
    ), selected_relationship AS MATERIALIZED (
        SELECT membership.*
          FROM relationship_membership AS membership
         WHERE membership.from_is_selected
           AND membership.to_is_selected
    ), resolved_relationship_input AS MATERIALIZED (
        SELECT result.analysis_result_id,
               result.relationship_kind,
               result.relationship_confidence,
               result.relationship_basis,
               result.analysis_result_status,
               result.analysis_result_is_locked,
               from_connection.connection_id AS from_connection_id,
               to_connection.connection_id AS to_connection_id,
               from_source_tenant.tenant_catalog AS from_relation_catalog,
               from_object.object_schema AS from_relation_schema,
               from_object.object_name AS from_relation_object,
               from_object.object_id AS from_object_id,
               from_attribute.attribute_id AS from_attribute_id,
               from_attribute.attribute_name AS from_attribute_name,
               from_attribute.attribute_data_type
                   AS from_attribute_data_type,
               from_batch_attribute.attribute_name
                   AS from_batch_attribute_name,
               from_batch_attribute.attribute_data_type
                   AS from_batch_attribute_data_type,
               to_source_tenant.tenant_catalog AS to_relation_catalog,
               to_object.object_schema AS to_relation_schema,
               to_object.object_name AS to_relation_object,
               to_object.object_id AS to_object_id,
               to_attribute.attribute_id AS to_attribute_id,
               to_attribute.attribute_name AS to_attribute_name,
               to_attribute.attribute_data_type AS to_attribute_data_type,
               to_batch_attribute.attribute_name
                   AS to_batch_attribute_name,
               to_batch_attribute.attribute_data_type
                   AS to_batch_attribute_data_type,
               v_environment_id AS environment_id,
               v_environment_code AS environment_code,
               host_value.connection_value_id AS host_connection_value_id,
               host_value.row_version AS host_connection_value_row_version,
               path_value.connection_value_id AS path_connection_value_id,
               path_value.row_version AS path_connection_value_row_version,
               token_value.connection_value_id AS token_connection_value_id,
               token_value.row_version AS token_connection_value_row_version
          FROM selected_relationship AS result
          JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
               AS from_eligible
            ON from_eligible.model_id = result.model_id
           AND from_eligible.object_id = result.from_object_id
           AND from_eligible.attribute_id = result.from_attribute_id
           AND from_eligible.is_model_input_eligible
          JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
               AS to_eligible
            ON to_eligible.model_id = result.model_id
           AND to_eligible.object_id = result.to_object_id
           AND to_eligible.attribute_id = result.to_attribute_id
           AND to_eligible.is_model_input_eligible
          JOIN core.object AS from_object
            ON from_object.object_id = result.from_object_id
           AND from_object.connection_id = from_eligible.connection_id
           AND from_object.source_tenant_id = v_run.tenant_id
           AND from_object.is_active
          JOIN core.object AS to_object
            ON to_object.object_id = result.to_object_id
           AND to_object.connection_id = to_eligible.connection_id
           AND to_object.source_tenant_id = v_run.tenant_id
           AND to_object.is_active
          JOIN core.connection AS from_connection
            ON from_connection.connection_id = from_object.connection_id
           AND from_connection.is_active
           AND from_connection.is_global_data_store
          JOIN core.connection AS to_connection
            ON to_connection.connection_id = to_object.connection_id
           AND to_connection.is_active
           AND to_connection.is_global_data_store
          JOIN core.attribute AS from_attribute
            ON from_attribute.attribute_id = result.from_attribute_id
           AND from_attribute.object_id = result.from_object_id
           AND from_attribute.is_active
          JOIN core.attribute AS to_attribute
            ON to_attribute.attribute_id = result.to_attribute_id
           AND to_attribute.object_id = result.to_object_id
           AND to_attribute.is_active
          JOIN core.tenant AS from_source_tenant
            ON from_source_tenant.tenant_id = from_object.source_tenant_id
           AND from_source_tenant.is_active
           AND reference.is_nonblank(from_source_tenant.tenant_catalog)
          JOIN core.tenant AS to_source_tenant
            ON to_source_tenant.tenant_id = to_object.source_tenant_id
           AND to_source_tenant.is_active
           AND reference.is_nonblank(to_source_tenant.tenant_catalog)
          LEFT JOIN core.attribute AS from_batch_attribute
            ON from_batch_attribute.object_id = from_object.object_id
           AND lower(btrim(from_batch_attribute.attribute_name)) =
               lower(btrim(from_object.batch_attribute_name))
           AND from_batch_attribute.is_active
          LEFT JOIN core.attribute AS to_batch_attribute
            ON to_batch_attribute.object_id = to_object.object_id
           AND lower(btrim(to_batch_attribute.attribute_name)) =
               lower(btrim(to_object.batch_attribute_name))
           AND to_batch_attribute.is_active
          LEFT JOIN LATERAL (
              SELECT connection_value.connection_value_id,
                     connection_value.xmin::TEXT AS row_version
                FROM core.connection_value AS connection_value
                JOIN reference.connection_parameter AS parameter
                  ON parameter.connection_parameter_id =
                     connection_value.connection_parameter_id
                 AND parameter.is_active
                 AND lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_host_name'
               WHERE connection_value.connection_id =
                     from_connection.connection_id
                 AND connection_value.environment_id = v_environment_id
          ) AS host_value ON TRUE
          LEFT JOIN LATERAL (
              SELECT connection_value.connection_value_id,
                     connection_value.xmin::TEXT AS row_version
                FROM core.connection_value AS connection_value
                JOIN reference.connection_parameter AS parameter
                  ON parameter.connection_parameter_id =
                     connection_value.connection_parameter_id
                 AND parameter.is_active
                 AND lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_http_path'
               WHERE connection_value.connection_id =
                     from_connection.connection_id
                 AND connection_value.environment_id = v_environment_id
          ) AS path_value ON TRUE
          LEFT JOIN LATERAL (
              SELECT connection_value.connection_value_id,
                     connection_value.xmin::TEXT AS row_version
                FROM core.connection_value AS connection_value
                JOIN reference.connection_parameter AS parameter
                  ON parameter.connection_parameter_id =
                     connection_value.connection_parameter_id
                 AND parameter.is_active
                 AND lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_token'
               WHERE connection_value.connection_id =
                     from_connection.connection_id
                 AND connection_value.environment_id = v_environment_id
          ) AS token_value ON TRUE
         WHERE reference.is_nonblank(from_attribute.attribute_data_type)
           AND reference.is_nonblank(to_attribute.attribute_data_type)
           AND (
                   from_object.batch_attribute_name IS NULL
                   OR (
                       from_batch_attribute.attribute_id IS NOT NULL
                       AND reference.is_nonblank(
                           from_batch_attribute.attribute_data_type
                       )
                   )
               )
           AND (
                   to_object.batch_attribute_name IS NULL
                   OR (
                       to_batch_attribute.attribute_id IS NOT NULL
                       AND reference.is_nonblank(
                           to_batch_attribute.attribute_data_type
                       )
                   )
               )
    ), resolved_relationship AS MATERIALIZED (
        SELECT input.*,
               encode(
                   sha256(
                       convert_to(
                           jsonb_build_object(
                               'schema_version', '1.0',
                               'workflow_run_id', v_run.workflow_run_id,
                               'model_id', v_run.model_id,
                               'selected_scope_digest',
                               v_run.selected_scope_digest,
                               'requested_batch_id', v_run.requested_batch_id,
                               'environment_id', input.environment_id,
                               'environment_code', input.environment_code,
                               'host_connection_value_id',
                               input.host_connection_value_id,
                               'host_connection_value_row_version',
                               input.host_connection_value_row_version,
                               'path_connection_value_id',
                               input.path_connection_value_id,
                               'path_connection_value_row_version',
                               input.path_connection_value_row_version,
                               'token_connection_value_id',
                               input.token_connection_value_id,
                               'token_connection_value_row_version',
                               input.token_connection_value_row_version,
                               'analysis_result_id',
                               input.analysis_result_id,
                               'relationship_kind', input.relationship_kind,
                               'from_gds_connection_id',
                               input.from_connection_id,
                               'to_gds_connection_id', input.to_connection_id,
                               'from_relation_catalog',
                               input.from_relation_catalog,
                               'from_relation_schema',
                               input.from_relation_schema,
                               'from_relation_object',
                               input.from_relation_object,
                               'from_object_id', input.from_object_id,
                               'from_attribute_id', input.from_attribute_id,
                               'from_attribute_name', input.from_attribute_name,
                               'from_attribute_data_type',
                               input.from_attribute_data_type,
                               'from_batch_attribute_name',
                               input.from_batch_attribute_name,
                               'from_batch_attribute_data_type',
                               input.from_batch_attribute_data_type,
                               'to_relation_catalog',
                               input.to_relation_catalog,
                               'to_relation_schema', input.to_relation_schema,
                               'to_relation_object', input.to_relation_object,
                               'to_object_id', input.to_object_id,
                               'to_attribute_id', input.to_attribute_id,
                               'to_attribute_name', input.to_attribute_name,
                               'to_attribute_data_type',
                               input.to_attribute_data_type,
                               'to_batch_attribute_name',
                               input.to_batch_attribute_name,
                               'to_batch_attribute_data_type',
                               input.to_batch_attribute_data_type
                           )::TEXT,
                           'UTF8'
                       )
                   ),
                   'hex'
               )::CHAR(64) AS source_context_digest
          FROM resolved_relationship_input AS input
    ), relationship_statistics AS (
        SELECT (
                   SELECT count(*)
                     FROM relationship_membership AS membership
                    WHERE membership.from_is_selected <>
                          membership.to_is_selected
               )::INTEGER AS partial_relationship_count,
               (
                   SELECT count(*)
                     FROM selected_relationship
               )::INTEGER AS relationship_count,
               (
                   SELECT count(DISTINCT resolved.analysis_result_id)
                     FROM resolved_relationship AS resolved
               )::INTEGER AS resolved_relationship_count,
               (
                   SELECT count(*)
                     FROM resolved_relationship AS resolved
                    WHERE resolved.from_connection_id <>
                          resolved.to_connection_id
               )::INTEGER AS cross_connection_count
    )
    SELECT jsonb_build_object(
               'partial_relationship_count',
               statistics.partial_relationship_count,
               'relationship_count', statistics.relationship_count,
               'resolved_relationship_count',
               statistics.resolved_relationship_count,
               'cross_connection_count', statistics.cross_connection_count,
               'rows', coalesce(
                   (
                       SELECT jsonb_agg(
                                  jsonb_build_object(
                                      'workflow_run_id', v_run.workflow_run_id,
                                      'model_id', v_run.model_id,
                                      'model_revision', v_run.model_revision,
                                      'requested_batch_id',
                                      v_run.requested_batch_id,
                                      'analysis_result_id',
                                      resolved.analysis_result_id,
                                      'relationship_kind',
                                      resolved.relationship_kind,
                                      'relationship_confidence',
                                      resolved.relationship_confidence,
                                      'relationship_basis',
                                      resolved.relationship_basis,
                                      'analysis_result_status',
                                      resolved.analysis_result_status,
                                      'analysis_result_is_locked',
                                      resolved.analysis_result_is_locked,
                                      'gds_connection_id',
                                      resolved.from_connection_id,
                                      'source_context_digest',
                                      resolved.source_context_digest,
                                      'from_relation_catalog',
                                      resolved.from_relation_catalog,
                                      'from_relation_schema',
                                      resolved.from_relation_schema,
                                      'from_relation_object',
                                      resolved.from_relation_object,
                                      'from_object_id', resolved.from_object_id,
                                      'from_attribute_id',
                                      resolved.from_attribute_id,
                                      'from_attribute_name',
                                      resolved.from_attribute_name,
                                      'from_attribute_data_type',
                                      resolved.from_attribute_data_type,
                                      'from_batch_attribute_name',
                                      resolved.from_batch_attribute_name,
                                      'from_batch_attribute_data_type',
                                      resolved.from_batch_attribute_data_type,
                                      'to_relation_catalog',
                                      resolved.to_relation_catalog,
                                      'to_relation_schema',
                                      resolved.to_relation_schema,
                                      'to_relation_object',
                                      resolved.to_relation_object,
                                      'to_object_id', resolved.to_object_id,
                                      'to_attribute_id',
                                      resolved.to_attribute_id,
                                      'to_attribute_name',
                                      resolved.to_attribute_name,
                                      'to_attribute_data_type',
                                      resolved.to_attribute_data_type,
                                      'to_batch_attribute_name',
                                      resolved.to_batch_attribute_name,
                                      'to_batch_attribute_data_type',
                                      resolved.to_batch_attribute_data_type
                                  )
                                  ORDER BY resolved.analysis_result_id
                              )
                         FROM resolved_relationship AS resolved
                   ),
                   '[]'::JSONB
               )
           )
      INTO v_context_snapshot
      FROM relationship_statistics AS statistics;

    v_partial_relationship_count :=
        (v_context_snapshot ->> 'partial_relationship_count')::INTEGER;
    v_relationship_count :=
        (v_context_snapshot ->> 'relationship_count')::INTEGER;
    v_resolved_relationship_count :=
        (v_context_snapshot ->> 'resolved_relationship_count')::INTEGER;
    v_cross_connection_count :=
        (v_context_snapshot ->> 'cross_connection_count')::INTEGER;

    IF v_partial_relationship_count > 0 THEN
        RAISE EXCEPTION
            'analysis_validation_endpoint_not_selected: Every eligible relationship requires both endpoint Objects';
    END IF;
    IF v_cross_connection_count > 0 THEN
        RAISE EXCEPTION
            'analysis_validation_cross_connection: Relationship endpoints must use one GDS Connection';
    END IF;
    IF v_resolved_relationship_count <> v_relationship_count THEN
        RAISE EXCEPTION
            'analysis_validation_context_changed: Relationship physical metadata is incomplete';
    END IF;
    IF v_relationship_count > 50000 THEN
        RAISE EXCEPTION
            'analysis_validation_context_too_large: Analysis validation exceeds 50000 relationships';
    END IF;
    IF octet_length(v_context_snapshot::TEXT) > 33554432 THEN
        RAISE EXCEPTION
            'analysis_validation_context_too_large: Analysis validation context exceeds 32 MiB';
    END IF;

    RETURN QUERY
    SELECT snapshot.*
      FROM jsonb_to_recordset(v_context_snapshot -> 'rows') AS snapshot(
               workflow_run_id BIGINT,
               model_id BIGINT,
               model_revision BIGINT,
               requested_batch_id VARCHAR(500),
               analysis_result_id BIGINT,
               relationship_kind VARCHAR(100),
               relationship_confidence VARCHAR(10),
               relationship_basis TEXT,
               analysis_result_status VARCHAR(20),
               analysis_result_is_locked BOOLEAN,
               gds_connection_id BIGINT,
               source_context_digest CHAR(64),
               from_relation_catalog VARCHAR(255),
               from_relation_schema VARCHAR(400),
               from_relation_object VARCHAR(400),
               from_object_id BIGINT,
               from_attribute_id BIGINT,
               from_attribute_name VARCHAR(400),
               from_attribute_data_type VARCHAR(100),
               from_batch_attribute_name VARCHAR(400),
               from_batch_attribute_data_type VARCHAR(100),
               to_relation_catalog VARCHAR(255),
               to_relation_schema VARCHAR(400),
               to_relation_object VARCHAR(400),
               to_object_id BIGINT,
               to_attribute_id BIGINT,
               to_attribute_name VARCHAR(400),
               to_attribute_data_type VARCHAR(100),
               to_batch_attribute_name VARCHAR(400),
               to_batch_attribute_data_type VARCHAR(100)
           )
     ORDER BY snapshot.analysis_result_id;
END;
$get_analysis_validation_execution_context$;

REVOKE ALL ON FUNCTION application.get_analysis_validation_execution_context(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

-- Return one complete credential tuple per exact GDS Connection resolved by
-- the validated relationship context. Configuration failures disclose no
-- partial credential values.
CREATE FUNCTION application.get_analysis_validation_connection_values(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    gds_connection_id BIGINT,
    environment_code VARCHAR(100),
    failure_code VARCHAR(50),
    failure_message VARCHAR(200),
    databricks_host_name TEXT,
    databricks_http_path TEXT,
    databricks_token TEXT
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_analysis_validation_connection_values$
DECLARE
    v_workflow_run_id BIGINT;
    v_model_id BIGINT;
    v_model_revision BIGINT;
    v_gds_connection_ids BIGINT[];
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_connection_count INTEGER;
    v_complete_connection_count INTEGER;
    v_connection_snapshot JSONB;
BEGIN
    SELECT min(context.workflow_run_id),
           min(context.model_id),
           min(context.model_revision),
           array_agg(
               DISTINCT context.gds_connection_id
               ORDER BY context.gds_connection_id
           )
      INTO v_workflow_run_id,
           v_model_id,
           v_model_revision,
           v_gds_connection_ids
      FROM application.get_analysis_validation_execution_context(
               p_entra_tenant_id,
               p_entra_object_id,
               p_expected_principal_type,
               p_workflow_run_id,
               p_expected_model_revision,
               p_environment_code
           ) AS context;
    v_connection_count := cardinality(v_gds_connection_ids);

    IF p_environment_code IS NULL
       OR NOT reference.is_nonblank(p_environment_code)
       OR length(btrim(p_environment_code)) > 100 THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'invalid_request'::VARCHAR(50),
            'Analysis validation Environment input is invalid.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id,
           v_environment_code
      FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code))
     FOR SHARE OF environment_record;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'environment_not_found'::VARCHAR(50),
            'Analysis validation Environment is unavailable.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    -- Read every required value once. Completeness checks and returned secret
    -- tuples use this exact local snapshot, never a second table read.
    WITH requested_connection AS (
        SELECT connection_id
          FROM unnest(v_gds_connection_ids) AS requested(connection_id)
    ), connection_values AS MATERIALIZED (
        SELECT requested.connection_id,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_host_name'
               ) AS databricks_host_name,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_http_path'
               ) AS databricks_http_path,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_token'
               ) AS databricks_token
          FROM requested_connection AS requested
          JOIN core.connection AS gds_connection
            ON gds_connection.connection_id = requested.connection_id
           AND gds_connection.is_active
           AND gds_connection.is_global_data_store
          LEFT JOIN core.connection_value AS connection_value
            ON connection_value.connection_id = requested.connection_id
           AND connection_value.environment_id = v_environment_id
          LEFT JOIN reference.connection_parameter AS parameter
            ON parameter.connection_parameter_id =
               connection_value.connection_parameter_id
           AND parameter.is_active
           AND lower(btrim(parameter.connection_parameter_code)) IN (
                   'databricks_host_name',
                   'databricks_http_path',
                   'databricks_token'
               )
         GROUP BY requested.connection_id
    )
    SELECT jsonb_build_object(
               'complete_connection_count',
               count(*) FILTER (
                   WHERE values.databricks_host_name IS NOT NULL
                     AND values.databricks_http_path IS NOT NULL
                     AND values.databricks_token IS NOT NULL
               )::INTEGER,
               'rows', coalesce(
                   jsonb_agg(
                       jsonb_build_object(
                           'gds_connection_id', values.connection_id,
                           'databricks_host_name',
                           values.databricks_host_name,
                           'databricks_http_path',
                           values.databricks_http_path,
                           'databricks_token', values.databricks_token
                       )
                       ORDER BY values.connection_id
                   ),
                   '[]'::JSONB
               )
           )
      INTO v_connection_snapshot
      FROM connection_values AS values;
    v_complete_connection_count :=
        (v_connection_snapshot ->> 'complete_connection_count')::INTEGER;
    IF v_connection_count IS NULL
       OR v_connection_count < 1
       OR v_complete_connection_count <> v_connection_count THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            v_environment_code,
            'connection_values_missing'::VARCHAR(50),
            'Analysis validation GDS connection values are incomplete.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT v_workflow_run_id,
           v_model_id,
           v_model_revision,
           snapshot.gds_connection_id,
           v_environment_code,
           NULL::VARCHAR(50),
           NULL::VARCHAR(200),
           snapshot.databricks_host_name,
           snapshot.databricks_http_path,
           snapshot.databricks_token
      FROM jsonb_to_recordset(v_connection_snapshot -> 'rows') AS snapshot(
               gds_connection_id BIGINT,
               databricks_host_name TEXT,
               databricks_http_path TEXT,
               databricks_token TEXT
           )
     ORDER BY snapshot.gds_connection_id;
END;
$get_analysis_validation_connection_values$;

REVOKE ALL ON FUNCTION application.get_analysis_validation_connection_values(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

-- Atomically replace only the validation-owned columns for the exact eligible
-- relationship set of one running deterministic Analysis Run. Inference,
-- status, and lock fields are never changed.
CREATE FUNCTION application.persist_analysis_validation_results(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100),
    p_validation_results JSONB
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    submitted_result_count INTEGER,
    changed_result_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $persist_analysis_validation_results$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_actor_entra_principal_identity_id BIGINT;
    v_result_count INTEGER;
    v_expected_result_ids BIGINT[];
    v_payload_result_ids BIGINT[];
    v_expected_context_digests JSONB;
    v_payload_context_digests JSONB;
    v_changed_result_count INTEGER;
    v_model_revision BIGINT;
BEGIN
    IF p_validation_results IS NULL
       OR jsonb_typeof(p_validation_results) <> 'array'
       OR octet_length(p_validation_results::TEXT) > 33554432 THEN
        RAISE EXCEPTION
            'Analysis validation results must be a JSON array no larger than 32 MiB';
    END IF;

    v_result_count := jsonb_array_length(p_validation_results);
    IF v_result_count NOT BETWEEN 0 AND 50000 THEN
        RAISE EXCEPTION
            'Analysis validation results must contain between 0 and 50000 Results';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_validation_results) AS result(value)
         WHERE jsonb_typeof(result.value) <> 'object'
            OR NOT result.value ?& ARRAY[
                   'analysis_result_id',
                   'source_context_digest',
                   'validation_policy_version',
                   'validation_policy_digest',
                   'validation_result',
                   'validation_source_non_null_count',
                   'validation_source_distinct_count',
                   'validation_target_non_null_count',
                   'validation_target_distinct_count',
                   'validation_source_missing_target_count',
                   'validation_unused_target_count',
                   'validation_duplicate_target_key_count'
               ]::TEXT[]
            OR (
                   SELECT count(*)
                     FROM jsonb_object_keys(result.value)
               ) <> 12
            OR jsonb_typeof(result.value -> 'analysis_result_id') <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'analysis_result_id')
                        ~ '^[1-9][0-9]*$'
                    AND length(
                            result.value ->> 'analysis_result_id'
                        ) <= 19
                   THEN (result.value ->> 'analysis_result_id')::NUMERIC <=
                        9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'source_context_digest'
               ) <> 'string'
            OR (result.value ->> 'source_context_digest')
               !~ '^[0-9a-f]{64}$'
            OR jsonb_typeof(
                   result.value -> 'validation_policy_version'
               ) <> 'string'
            OR (result.value ->> 'validation_policy_version')
               !~ '^[0-9]+\.[0-9]+\.[0-9]+$'
            OR octet_length(
                   result.value ->> 'validation_policy_version'
               ) > 50
            OR jsonb_typeof(
                   result.value -> 'validation_policy_digest'
               ) <> 'string'
            OR (result.value ->> 'validation_policy_digest')
               !~ '^[0-9a-f]{64}$'
            OR jsonb_typeof(result.value -> 'validation_result') <> 'string'
            OR (result.value ->> 'validation_result') NOT IN (
                   'supported', 'inconclusive', 'unsupported'
               )
            OR jsonb_typeof(
                   result.value -> 'validation_source_non_null_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_source_non_null_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_source_non_null_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_source_non_null_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_source_distinct_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_source_distinct_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_source_distinct_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_source_distinct_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_target_non_null_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_target_non_null_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_target_non_null_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_target_non_null_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_target_distinct_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_target_distinct_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_target_distinct_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_target_distinct_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value ->
                   'validation_source_missing_target_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (
                            result.value ->>
                            'validation_source_missing_target_count'
                        ) ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_source_missing_target_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_source_missing_target_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_unused_target_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_unused_target_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_unused_target_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_unused_target_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value ->
                   'validation_duplicate_target_key_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (
                            result.value ->>
                            'validation_duplicate_target_key_count'
                        ) ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_duplicate_target_key_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_duplicate_target_key_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
    ) THEN
        RAISE EXCEPTION 'Analysis validation result payload shape is invalid';
    END IF;

    IF v_result_count <> (
        SELECT count(DISTINCT result.analysis_result_id)
          FROM jsonb_to_recordset(p_validation_results) AS result(
                   analysis_result_id BIGINT
               )
    ) THEN
        RAISE EXCEPTION 'Analysis validation result IDs must be unique';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM jsonb_to_recordset(p_validation_results) AS result(
                   validation_result VARCHAR(30),
                   validation_source_non_null_count BIGINT,
                   validation_source_distinct_count BIGINT,
                   validation_target_non_null_count BIGINT,
                   validation_target_distinct_count BIGINT,
                   validation_source_missing_target_count BIGINT,
                   validation_unused_target_count BIGINT,
                   validation_duplicate_target_key_count BIGINT
               )
         WHERE result.validation_source_distinct_count >
               result.validation_source_non_null_count
            OR (result.validation_source_non_null_count = 0) <>
               (result.validation_source_distinct_count = 0)
            OR result.validation_target_distinct_count >
               result.validation_target_non_null_count
            OR (result.validation_target_non_null_count = 0) <>
               (result.validation_target_distinct_count = 0)
            OR result.validation_source_missing_target_count >
               result.validation_source_distinct_count
            OR result.validation_unused_target_count >
               result.validation_target_distinct_count
            OR result.validation_duplicate_target_key_count <>
               result.validation_target_non_null_count -
               result.validation_target_distinct_count
            OR result.validation_result <> CASE
                   WHEN result.validation_source_non_null_count = 0
                     OR result.validation_target_non_null_count = 0
                   THEN 'inconclusive'
                   WHEN result.validation_source_missing_target_count = 0
                    AND result.validation_duplicate_target_key_count = 0
                   THEN 'supported'
                   ELSE 'unsupported'
               END
    ) THEN
        RAISE EXCEPTION
            'Analysis validation result evidence is inconsistent';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.actor_entra_principal_identity_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.workflow_run_state,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_found: Analysis Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'analysis_validation_persistence_denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    SELECT identity.entra_principal_identity_id
      INTO v_actor_entra_principal_identity_id
      FROM security.entra_principal_identity AS identity
     WHERE identity.principal_id = v_decision.principal_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.is_active
     FOR SHARE OF identity;
    IF NOT FOUND
       OR v_run.actor_principal_id <> v_decision.principal_id
       OR v_run.actor_entra_principal_identity_id IS DISTINCT FROM
          v_actor_entra_principal_identity_id THEN
        RAISE EXCEPTION
            'workflow_run_owner_mismatch: Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'analysis'
       OR v_run.workflow_execution_mode IS NOT NULL
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_running: A running deterministic Analysis Workflow Run is required';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    -- Freeze all existing Analysis rows for this Model. The Model row lock also
    -- fences inserts through the Analysis Result foreign key until commit.
    PERFORM result.analysis_result_id
      FROM workflow.analysis_result AS result
     WHERE result.model_id = v_run.model_id
     ORDER BY result.analysis_result_id
     FOR UPDATE OF result;

    SELECT coalesce(
               array_agg(
                   context.analysis_result_id
                   ORDER BY context.analysis_result_id
               ),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               jsonb_object_agg(
                   context.analysis_result_id::TEXT,
                   context.source_context_digest
                   ORDER BY context.analysis_result_id
               ),
               '{}'::JSONB
           )
      INTO v_expected_result_ids,
           v_expected_context_digests
      FROM application.get_analysis_validation_execution_context(
               p_entra_tenant_id,
               p_entra_object_id,
               p_expected_principal_type,
               p_workflow_run_id,
               p_expected_model_revision,
               p_environment_code
           ) AS context;

    SELECT coalesce(
               array_agg(
                   result.analysis_result_id
                   ORDER BY result.analysis_result_id
               ),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               jsonb_object_agg(
                   result.analysis_result_id::TEXT,
                   result.source_context_digest
                   ORDER BY result.analysis_result_id
               ),
               '{}'::JSONB
           )
      INTO v_payload_result_ids,
           v_payload_context_digests
      FROM jsonb_to_recordset(p_validation_results) AS result(
               analysis_result_id BIGINT,
               source_context_digest CHAR(64)
           );
    IF v_payload_result_ids IS DISTINCT FROM v_expected_result_ids THEN
        RAISE EXCEPTION
            'Analysis validation results must exactly cover eligible Results';
    END IF;
    IF v_payload_context_digests IS DISTINCT FROM
       v_expected_context_digests THEN
        RAISE EXCEPTION
            'Analysis validation source context digest does not match current metadata';
    END IF;

    WITH result_payload AS MATERIALIZED (
        SELECT result.*
          FROM jsonb_to_recordset(p_validation_results) AS result(
                   analysis_result_id BIGINT,
                   source_context_digest CHAR(64),
                   validation_policy_version VARCHAR(50),
                   validation_policy_digest CHAR(64),
                   validation_result VARCHAR(30),
                   validation_source_non_null_count BIGINT,
                   validation_source_distinct_count BIGINT,
                   validation_target_non_null_count BIGINT,
                   validation_target_distinct_count BIGINT,
                   validation_source_missing_target_count BIGINT,
                   validation_unused_target_count BIGINT,
                   validation_duplicate_target_key_count BIGINT
               )
    ), changed_results AS (
        UPDATE workflow.analysis_result AS stored
           SET validation_workflow_run_id = p_workflow_run_id,
               validation_source_context_digest =
                   payload.source_context_digest,
               validation_policy_version =
                   payload.validation_policy_version,
               validation_policy_digest = payload.validation_policy_digest,
               validation_result = payload.validation_result,
               validation_source_non_null_count =
                   payload.validation_source_non_null_count,
               validation_source_distinct_count =
                   payload.validation_source_distinct_count,
               validation_target_non_null_count =
                   payload.validation_target_non_null_count,
               validation_target_distinct_count =
                   payload.validation_target_distinct_count,
               validation_source_missing_target_count =
                   payload.validation_source_missing_target_count,
               validation_unused_target_count =
                   payload.validation_unused_target_count,
               validation_duplicate_target_key_count =
                   payload.validation_duplicate_target_key_count,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
          FROM result_payload AS payload
         WHERE stored.model_id = v_run.model_id
           AND stored.analysis_result_id = payload.analysis_result_id
           AND ROW(
                   stored.validation_workflow_run_id,
                   stored.validation_source_context_digest,
                   stored.validation_policy_version,
                   stored.validation_policy_digest,
                   stored.validation_result,
                   stored.validation_source_non_null_count,
                   stored.validation_source_distinct_count,
                   stored.validation_target_non_null_count,
                   stored.validation_target_distinct_count,
                   stored.validation_source_missing_target_count,
                   stored.validation_unused_target_count,
                   stored.validation_duplicate_target_key_count
               ) IS DISTINCT FROM ROW(
                   p_workflow_run_id,
                   payload.source_context_digest,
                   payload.validation_policy_version,
                   payload.validation_policy_digest,
                   payload.validation_result,
                   payload.validation_source_non_null_count,
                   payload.validation_source_distinct_count,
                   payload.validation_target_non_null_count,
                   payload.validation_target_distinct_count,
                   payload.validation_source_missing_target_count,
                   payload.validation_unused_target_count,
                   payload.validation_duplicate_target_key_count
               )
        RETURNING 1
    )
    SELECT count(*)::INTEGER
      INTO v_changed_result_count
      FROM changed_results;

    IF v_changed_result_count > 0 THEN
        UPDATE model.model AS target_model
           SET model_revision = target_model.model_revision + 1,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
         WHERE target_model.model_id = v_run.model_id
        RETURNING target_model.model_revision INTO v_model_revision;

        INSERT INTO model.model_revision_transaction (
            model_id,
            change_kind
        ) VALUES (
            v_run.model_id,
            'web_analysis_validation_results_persist'
        );
    ELSE
        v_model_revision := v_run.model_revision;
    END IF;

    RETURN QUERY SELECT
        v_changed_result_count > 0,
        v_run.workflow_run_id::BIGINT,
        v_run.model_id::BIGINT,
        v_model_revision,
        v_result_count,
        v_changed_result_count;
END;
$persist_analysis_validation_results$;

REVOKE ALL ON FUNCTION application.persist_analysis_validation_results(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    JSONB
) FROM PUBLIC;

CREATE FUNCTION application.persist_profiling_results(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_profiles JSONB
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    submitted_profile_count INTEGER,
    changed_profile_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $persist_profiling_results$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_profile_count INTEGER;
    v_selected_scope_count INTEGER;
    v_eligible_selected_object_count INTEGER;
    v_expected_attribute_ids BIGINT[];
    v_expected_object_ids BIGINT[];
    v_expected_context_digests JSONB;
    v_payload_attribute_ids BIGINT[];
    v_payload_object_ids BIGINT[];
    v_payload_context_digests JSONB;
    v_removed_profile_count INTEGER;
    v_changed_profile_count INTEGER;
    v_model_revision BIGINT;
BEGIN
    IF p_profiles IS NULL
       OR jsonb_typeof(p_profiles) <> 'array'
       OR octet_length(p_profiles::TEXT) > 33554432 THEN
        RAISE EXCEPTION
            'Profiling results must be a JSON array no larger than 32 MiB';
    END IF;

    v_profile_count := jsonb_array_length(p_profiles);
    IF v_profile_count NOT BETWEEN 0 AND 50000 THEN
        RAISE EXCEPTION
            'Profiling results must contain between 0 and 50000 Profiles';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_profiles) AS profile(value)
         WHERE jsonb_typeof(profile.value) <> 'object'
            OR NOT profile.value ?& ARRAY[
                   'object_id',
                   'attribute_id',
                   'source_context_digest',
                   'row_count',
                   'non_null_count',
                   'null_count',
                   'blank_count',
                   'distinct_count',
                   'min_data_length',
                   'max_data_length',
                   'avg_data_length',
                   'percent_populated',
                   'percent_duplicates',
                   'percent_null',
                   'percent_blank',
                   'percent_distinct'
               ]::TEXT[]
            OR (
                   SELECT count(*)
                     FROM jsonb_object_keys(profile.value)
               ) <> 16
            OR jsonb_typeof(profile.value -> 'object_id') <> 'number'
            OR (profile.value ->> 'object_id') !~ '^[1-9][0-9]*$'
            OR jsonb_typeof(profile.value -> 'attribute_id') <> 'number'
            OR (profile.value ->> 'attribute_id') !~ '^[1-9][0-9]*$'
            OR jsonb_typeof(
                   profile.value -> 'source_context_digest'
               ) <> 'string'
            OR (profile.value ->> 'source_context_digest')
               !~ '^[0-9a-f]{64}$'
            OR jsonb_typeof(profile.value -> 'row_count') <> 'number'
            OR (profile.value ->> 'row_count') !~ '^(0|[1-9][0-9]*)$'
            OR jsonb_typeof(profile.value -> 'non_null_count') <> 'number'
            OR (profile.value ->> 'non_null_count')
               !~ '^(0|[1-9][0-9]*)$'
            OR jsonb_typeof(profile.value -> 'null_count') <> 'number'
            OR (profile.value ->> 'null_count') !~ '^(0|[1-9][0-9]*)$'
            OR jsonb_typeof(profile.value -> 'blank_count')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'blank_count') = 'number'
                   AND (profile.value ->> 'blank_count')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'distinct_count')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'distinct_count') = 'number'
                   AND (profile.value ->> 'distinct_count')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'min_data_length')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'min_data_length') = 'number'
                   AND (profile.value ->> 'min_data_length')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'max_data_length')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'max_data_length') = 'number'
                   AND (profile.value ->> 'max_data_length')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'avg_data_length')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_populated')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_duplicates')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_null')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_blank')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_distinct')
               NOT IN ('number', 'null')
    ) THEN
        RAISE EXCEPTION 'Profiling result payload shape is invalid';
    END IF;

    IF v_profile_count <> (
        SELECT count(DISTINCT profile.attribute_id)
          FROM jsonb_to_recordset(p_profiles) AS profile(
                   attribute_id BIGINT
               )
    ) THEN
        RAISE EXCEPTION 'Profiling result Attribute IDs must be unique';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_to_recordset(p_profiles) AS profile(
                   row_count BIGINT,
                   non_null_count BIGINT,
                   null_count BIGINT,
                   blank_count BIGINT,
                   distinct_count BIGINT,
                   min_data_length INTEGER,
                   max_data_length INTEGER,
                   percent_populated NUMERIC(7, 4),
                   percent_duplicates NUMERIC(7, 4),
                   percent_null NUMERIC(7, 4),
                   percent_blank NUMERIC(7, 4),
                   percent_distinct NUMERIC(7, 4)
               )
         WHERE profile.non_null_count::NUMERIC + profile.null_count <>
               profile.row_count
            OR profile.blank_count > profile.non_null_count
            OR profile.distinct_count > profile.non_null_count
            OR profile.min_data_length > profile.max_data_length
            OR profile.percent_populated IS DISTINCT FROM CASE
                   WHEN profile.row_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.non_null_count /
                       profile.row_count,
                       4
                   )
               END
            OR profile.percent_null IS DISTINCT FROM CASE
                   WHEN profile.row_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.null_count /
                       profile.row_count,
                       4
                   )
               END
            OR profile.percent_duplicates IS DISTINCT FROM CASE
                   WHEN profile.distinct_count IS NULL THEN NULL::NUMERIC
                   WHEN profile.non_null_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * (
                           profile.non_null_count - profile.distinct_count
                       ) / profile.non_null_count,
                       4
                   )
               END
            OR profile.percent_blank IS DISTINCT FROM CASE
                   WHEN profile.blank_count IS NULL THEN NULL::NUMERIC
                   WHEN profile.non_null_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.blank_count /
                       profile.non_null_count,
                       4
                   )
               END
            OR profile.percent_distinct IS DISTINCT FROM CASE
                   WHEN profile.distinct_count IS NULL THEN NULL::NUMERIC
                   WHEN profile.non_null_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.distinct_count /
                       profile.non_null_count,
                       4
                   )
               END
    ) THEN
        RAISE EXCEPTION 'Profiling result metrics do not reconcile';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.model_workflow,
           run.workflow_run_state,
           run.requested_batch_id,
           run.selected_scope_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Profiling Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Profiling result persistence denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'profiling'
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'A running Profiling Workflow Run is required';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_selected_scope_count
      FROM application.workflow_run_object_selection AS selection
     WHERE selection.workflow_run_id = p_workflow_run_id;
    IF v_selected_scope_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION 'Workflow Run Selected Scope is incomplete';
    END IF;

    -- Freeze selected physical membership for this transaction. Object locks
    -- fence new Attributes through their foreign key; Attribute locks fence
    -- activation and membership changes.
    PERFORM object_record.object_id
      FROM application.workflow_run_object_selection AS selection
      JOIN model.model_input_scope AS scope
        ON scope.model_id = selection.model_id
       AND scope.object_id = selection.object_id
       AND scope.is_active
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.source_tenant_id = v_run.tenant_id
       AND object_record.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = object_record.connection_id
       AND connection.is_active
      JOIN core.tenant AS object_tenant
        ON object_tenant.tenant_id = object_record.source_tenant_id
       AND object_tenant.is_active
      JOIN core.system AS system
        ON system.system_id = connection.system_id
       AND system.is_active
      JOIN reference.zone AS zone
        ON zone.zone_id = object_record.zone_id
       AND zone.is_active
       AND lower(btrim(zone.zone_code)) = 'bronze'
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
     ORDER BY object_record.object_id
     FOR UPDATE OF object_record
     FOR SHARE OF selection, scope, connection, object_tenant, system, zone;
    GET DIAGNOSTICS v_eligible_selected_object_count = ROW_COUNT;
    IF v_eligible_selected_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'Workflow Run Selected Scope membership has changed';
    END IF;

    PERFORM attribute.attribute_id
      FROM application.workflow_run_object_selection AS selection
      JOIN core.attribute AS attribute
        ON attribute.object_id = selection.object_id
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
     ORDER BY attribute.attribute_id
     FOR UPDATE OF attribute;

    SELECT coalesce(
               array_agg(
                   eligible.attribute_id
                   ORDER BY eligible.attribute_id
               ),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               array_agg(
                   eligible.object_id
                   ORDER BY eligible.attribute_id
               ),
               ARRAY[]::BIGINT[]
           )
      INTO v_expected_attribute_ids,
           v_expected_object_ids
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
           AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_model_input_eligible
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;

    SELECT coalesce(
               array_agg(profile.attribute_id ORDER BY profile.attribute_id),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               array_agg(profile.object_id ORDER BY profile.attribute_id),
               ARRAY[]::BIGINT[]
           )
      INTO v_payload_attribute_ids,
           v_payload_object_ids
      FROM jsonb_to_recordset(p_profiles) AS profile(
               object_id BIGINT,
               attribute_id BIGINT
           );
    IF v_payload_attribute_ids IS DISTINCT FROM v_expected_attribute_ids
       OR v_payload_object_ids IS DISTINCT FROM v_expected_object_ids THEN
        RAISE EXCEPTION
            'Profiling results must exactly cover the eligible Selected Scope Attributes';
    END IF;

    SELECT coalesce(
               jsonb_object_agg(
                   attribute.attribute_id::TEXT,
                   encode(
                       sha256(
                           convert_to(
                               '{"attribute_data_type":' ||
                               to_jsonb(attribute.attribute_data_type)::TEXT ||
                               ',"attribute_id":' ||
                               attribute.attribute_id::TEXT ||
                               ',"attribute_name":' ||
                               to_jsonb(attribute.attribute_name)::TEXT ||
                               ',"batch_attribute_name":' ||
                               coalesce(
                                   to_jsonb(
                                       object_record.batch_attribute_name
                                   )::TEXT,
                                   'null'
                               ) ||
                               ',"catalog":' ||
                               to_jsonb(source_tenant.tenant_catalog)::TEXT ||
                               ',"object_id":' ||
                               object_record.object_id::TEXT ||
                               ',"requested_batch_id":' ||
                               coalesce(
                                   to_jsonb(v_run.requested_batch_id)::TEXT,
                                   'null'
                               ) ||
                               ',"schema":' ||
                               to_jsonb(object_record.object_schema)::TEXT ||
                               ',"table":' ||
                               to_jsonb(object_record.object_name)::TEXT ||
                               '}',
                               'UTF8'
                           )
                       ),
                       'hex'
                   )
                   ORDER BY attribute.attribute_id
               ),
               '{}'::JSONB
           )
      INTO v_expected_context_digests
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
           AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_model_input_eligible
      JOIN core.attribute AS attribute
        ON attribute.attribute_id = eligible.attribute_id
       AND attribute.object_id = eligible.object_id
       AND attribute.is_active
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.source_tenant_id = v_run.tenant_id
       AND object_record.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = object_record.connection_id
       AND connection.is_active
      JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = object_record.source_tenant_id
       AND source_tenant.is_active
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;

    SELECT coalesce(
               jsonb_object_agg(
                   profile.attribute_id::TEXT,
                   profile.source_context_digest
                   ORDER BY profile.attribute_id
               ),
               '{}'::JSONB
           )
      INTO v_payload_context_digests
      FROM jsonb_to_recordset(p_profiles) AS profile(
               attribute_id BIGINT,
               source_context_digest TEXT
           );
    IF v_payload_context_digests IS DISTINCT FROM
       v_expected_context_digests THEN
        RAISE EXCEPTION 'Profiling result source context has changed';
    END IF;

    WITH profile_payload AS MATERIALIZED (
        SELECT profile.*
          FROM jsonb_to_recordset(p_profiles) AS profile(
                   object_id BIGINT,
                   attribute_id BIGINT,
                   source_context_digest TEXT,
                   row_count BIGINT,
                   non_null_count BIGINT,
                   null_count BIGINT,
                   blank_count BIGINT,
                   distinct_count BIGINT,
                   min_data_length INTEGER,
                   max_data_length INTEGER,
                   avg_data_length NUMERIC(20, 6),
                   percent_populated NUMERIC(7, 4),
                   percent_duplicates NUMERIC(7, 4),
                   percent_null NUMERIC(7, 4),
                   percent_blank NUMERIC(7, 4),
                   percent_distinct NUMERIC(7, 4)
               )
    ),
    removed_profiles AS (
        DELETE FROM workflow.attribute_profile AS stored
         USING application.workflow_run_object_selection AS selection
         WHERE selection.workflow_run_id = p_workflow_run_id
           AND selection.model_id = v_run.model_id
           AND stored.model_id = selection.model_id
           AND stored.object_id = selection.object_id
           AND NOT EXISTS (
                   SELECT 1
                     FROM profile_payload AS profile
                    WHERE profile.attribute_id = stored.attribute_id
                      AND profile.object_id = stored.object_id
               )
        RETURNING 1
    ),
    changed_profiles AS (
        INSERT INTO workflow.attribute_profile AS stored (
            model_id,
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
        SELECT v_run.model_id,
               profile.attribute_id,
               profile.object_id,
               NULL,
               p_workflow_run_id,
               profile.source_context_digest,
               profile.row_count,
               profile.non_null_count,
               profile.null_count,
               profile.blank_count,
               profile.distinct_count,
               profile.min_data_length,
               profile.max_data_length,
               profile.avg_data_length,
               profile.percent_populated,
               profile.percent_duplicates,
               profile.percent_null,
               profile.percent_blank,
               profile.percent_distinct
          FROM profile_payload AS profile
         ORDER BY profile.attribute_id
        ON CONFLICT ON CONSTRAINT attribute_profile_pkey DO UPDATE
           SET object_id = EXCLUDED.object_id,
               agent_run_id = EXCLUDED.agent_run_id,
               workflow_run_id = EXCLUDED.workflow_run_id,
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
         WHERE ROW(
                   stored.object_id,
                   stored.agent_run_id,
                   stored.workflow_run_id,
                   stored.source_context_digest,
                   stored.row_count,
                   stored.non_null_count,
                   stored.null_count,
                   stored.blank_count,
                   stored.distinct_count,
                   stored.min_data_length,
                   stored.max_data_length,
                   stored.avg_data_length,
                   stored.percent_populated,
                   stored.percent_duplicates,
                   stored.percent_null,
                   stored.percent_blank,
                   stored.percent_distinct
               ) IS DISTINCT FROM ROW(
                   EXCLUDED.object_id,
                   EXCLUDED.agent_run_id,
                   EXCLUDED.workflow_run_id,
                   EXCLUDED.source_context_digest,
                   EXCLUDED.row_count,
                   EXCLUDED.non_null_count,
                   EXCLUDED.null_count,
                   EXCLUDED.blank_count,
                   EXCLUDED.distinct_count,
                   EXCLUDED.min_data_length,
                   EXCLUDED.max_data_length,
                   EXCLUDED.avg_data_length,
                   EXCLUDED.percent_populated,
                   EXCLUDED.percent_duplicates,
                   EXCLUDED.percent_null,
                   EXCLUDED.percent_blank,
                   EXCLUDED.percent_distinct
               )
        RETURNING 1
    )
    SELECT (SELECT count(*) FROM removed_profiles)::INTEGER,
           (SELECT count(*) FROM changed_profiles)::INTEGER
      INTO v_removed_profile_count,
           v_changed_profile_count;
    v_changed_profile_count :=
        v_removed_profile_count + v_changed_profile_count;

    IF v_changed_profile_count > 0 THEN
        UPDATE model.model AS target_model
           SET model_revision = target_model.model_revision + 1,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
         WHERE target_model.model_id = v_run.model_id
        RETURNING target_model.model_revision INTO v_model_revision;

        INSERT INTO model.model_revision_transaction (
            model_id,
            change_kind
        ) VALUES (
            v_run.model_id,
            'web_profiling_results_persist'
        );
    ELSE
        v_model_revision := v_run.model_revision;
    END IF;

    RETURN QUERY SELECT
        v_changed_profile_count > 0,
        v_run.workflow_run_id::BIGINT,
        v_run.model_id::BIGINT,
        v_model_revision,
        v_profile_count,
        v_changed_profile_count;
END;
$persist_profiling_results$;

REVOKE ALL ON FUNCTION application.persist_profiling_results(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    JSONB
) FROM PUBLIC;
