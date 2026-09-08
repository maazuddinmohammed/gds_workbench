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

-- Metadata enrichment deliberately tolerates missing physical relations. Registered
-- metadata remains useful when a foreign catalog or execution connection is absent.
CREATE FUNCTION application.get_metadata_enrichment_execution_context(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $get_metadata_enrichment_execution_context$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_objects JSONB;
    v_baseline JSONB;
    v_context JSONB;
    v_count INTEGER;
BEGIN
    SELECT run.*, target_model.model_revision AS current_model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model USING (model_id, tenant_id)
     WHERE run.workflow_run_id = p_workflow_run_id AND target_model.is_active
     FOR SHARE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'metadata_enrichment_run_unavailable';
    END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        v_run.tenant_id, 'tenant_model_write');
    IF NOT coalesce(v_decision.authorized, FALSE) THEN
        RAISE EXCEPTION 'metadata_enrichment_denied';
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'workflow_run_owner_mismatch';
    END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        v_run.tenant_id, 'tenant_metadata_write');
    IF NOT coalesce(v_decision.authorized, FALSE) THEN
        RAISE EXCEPTION 'metadata_enrichment_denied';
    END IF;
    IF v_run.model_workflow <> 'metadata_enrichment'
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION 'metadata_enrichment_run_not_running';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision
       OR v_run.current_model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;
    PERFORM 1 FROM core.object AS object
      JOIN application.workflow_run_object_selection AS selection USING (object_id)
     WHERE selection.workflow_run_id = p_workflow_run_id
     ORDER BY object.object_id FOR SHARE OF object;
    PERFORM 1 FROM model.model_input_scope AS scope
      JOIN application.workflow_run_object_selection AS selection USING (model_id, object_id)
     WHERE selection.workflow_run_id = p_workflow_run_id
     ORDER BY scope.object_id FOR SHARE OF scope;
    PERFORM 1 FROM core.tenant AS tenant WHERE tenant.tenant_id = v_run.tenant_id FOR SHARE;
    PERFORM 1 FROM core.connection AS connection WHERE connection.connection_id IN (
        SELECT object.connection_id FROM core.object AS object
          JOIN application.workflow_run_object_selection AS selection USING (object_id)
         WHERE selection.workflow_run_id = p_workflow_run_id
        UNION SELECT tenant.gds_connection_id FROM core.tenant AS tenant WHERE tenant.tenant_id = v_run.tenant_id
    ) ORDER BY connection.connection_id FOR SHARE;
    PERFORM 1 FROM core.system AS system WHERE system.system_id IN (
        SELECT connection.system_id FROM core.connection AS connection
        JOIN core.object AS object USING (connection_id)
        JOIN application.workflow_run_object_selection AS selection USING (object_id)
        WHERE selection.workflow_run_id = p_workflow_run_id
    ) ORDER BY system.system_id FOR SHARE;
    SELECT count(*) INTO v_count
      FROM application.workflow_run_object_selection AS selection
      JOIN model.model_input_scope AS scope USING (model_id, object_id)
      JOIN core.object AS object USING (object_id)
      JOIN core.connection AS connection USING (connection_id)
      JOIN core.system AS system USING (system_id)
      JOIN core.tenant AS tenant ON tenant.tenant_id = object.source_tenant_id
      JOIN reference.zone AS zone USING (zone_id)
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id AND scope.is_active
       AND object.is_active AND object.source_tenant_id = v_run.tenant_id
       AND connection.is_active AND system.is_active AND tenant.is_active
       AND zone.is_active AND lower(btrim(zone.zone_code)) IN ('source', 'bronze');
    IF v_count <> v_run.selected_scope_count OR v_count NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'metadata_enrichment_scope_changed';
    END IF;
    SELECT count(*) INTO v_count FROM core.attribute AS attribute
      JOIN application.workflow_run_object_selection AS selection USING (object_id)
     WHERE selection.workflow_run_id = p_workflow_run_id;
    IF v_count > 5000 THEN
        RAISE EXCEPTION 'metadata_enrichment_context_too_large';
    END IF;

    -- All mapped candidates (including ambiguous/inactive ones) participate in
    -- the baseline. Only one active, same-owner Source is exposed as evidence.
    WITH selected AS MATERIALIZED (
        SELECT object.* FROM core.object AS object
          JOIN application.workflow_run_object_selection AS selection USING (object_id)
         WHERE selection.workflow_run_id = p_workflow_run_id
    ), objects AS MATERIALIZED (
        SELECT object.*, lower(btrim(zone.zone_code)) AS zone_code,
               connection.tenant_id, tenant.tenant_catalog, system.system_code,
               jsonb_build_object('tenant_code', physical_tenant.tenant_code,
                   'system_code', system.system_code, 'connection_code', connection.connection_code,
                   'object_schema', object.object_schema, 'object_name', object.object_name) AS physical_key,
               jsonb_build_object('tenant_code', physical_tenant.tenant_code,
                   'tenant_description', physical_tenant.tenant_description,
                   'system_code', system.system_code, 'system_description', system.system_description,
                   'system_type_code', system_type.system_type_code,
                   'system_type_description', system_type.system_type_description,
                   'connection_code', connection.connection_code,
                   'connection_description', connection.connection_description,
                   'connection_type_code', connection_type.connection_type_code,
                   'connection_type_description', connection_type.connection_type_description,
                   'zone_code', lower(btrim(zone.zone_code)), 'zone_description', zone.zone_description
               ) AS source_connection_context,
               jsonb_build_object('tenant_code', physical_tenant.tenant_code,
                   'system_code', system.system_code, 'connection_code', connection.connection_code,
                   'zone_code', lower(btrim(zone.zone_code)), 'zone_description', zone.zone_description
               ) AS gds_context,
               CASE WHEN gds.connection_id IS NOT NULL AND gds.is_active
                              AND gds.is_global_data_store THEN
                   CASE WHEN lower(btrim(zone.zone_code)) = 'source'
                                  AND connection.has_foreign_catalog
                                  AND reference.is_nonblank(connection.foreign_catalog)
                                  AND reference.is_nonblank(object.fc_object_schema)
                                  AND reference.is_nonblank(object.fc_object_name)
                        THEN jsonb_build_object('connection_id', gds.connection_id,
                            'catalog', connection.foreign_catalog,
                            'schema', object.fc_object_schema, 'table', object.fc_object_name)
                        WHEN lower(btrim(zone.zone_code)) = 'bronze'
                                  AND connection.connection_id = gds.connection_id
                        THEN jsonb_build_object('connection_id', gds.connection_id,
                            'catalog', tenant.tenant_catalog,
                            'schema', object.object_schema, 'table', object.object_name)
                   END
               END AS relation,
               jsonb_build_object('object', to_jsonb(object),
                   'connection', to_jsonb(connection), 'tenant', to_jsonb(tenant),
                   'system', to_jsonb(system), 'zone', to_jsonb(zone),
                   'gds_connection', to_jsonb(gds), 'physical_tenant', to_jsonb(physical_tenant),
                   'system_type', to_jsonb(system_type), 'connection_type', to_jsonb(connection_type)) AS baseline
          FROM core.object AS object
          JOIN core.connection AS connection USING (connection_id)
          JOIN core.system AS system USING (system_id)
          JOIN core.tenant AS tenant ON tenant.tenant_id = object.source_tenant_id
          JOIN reference.zone AS zone USING (zone_id)
          JOIN core.tenant AS physical_tenant ON physical_tenant.tenant_id = connection.tenant_id
          JOIN reference.system_type AS system_type USING (system_type_id)
          JOIN reference.connection_type AS connection_type USING (connection_type_id)
          LEFT JOIN core.connection AS gds ON gds.connection_id = tenant.gds_connection_id
         WHERE object.object_id IN (SELECT object_id FROM selected)
            OR object.object_id IN (
                SELECT mapping.source_object_id FROM core.ingestion_object_mapping AS mapping
                 WHERE mapping.target_object_id IN (SELECT object_id FROM selected))
    ), candidates AS MATERIALIZED (
        SELECT attribute_mapping.target_attribute_id,
               source.attribute_id AS source_attribute_id,
               source_object.object_id AS source_object_id,
               object_mapping.is_active AND attribute_mapping.is_active
                   AND source.is_active AND source_object.is_active
                   AND source_object.source_tenant_id = v_run.tenant_id
                   AND source_object.zone_code = 'source'
                   AND (source_object.baseline #>> '{connection,is_active}')::BOOLEAN
                   AND (source_object.baseline #>> '{system,is_active}')::BOOLEAN
                   AND (source_object.baseline #>> '{tenant,is_active}')::BOOLEAN
                   AND (source_object.baseline #>> '{zone,is_active}')::BOOLEAN AS eligible,
               jsonb_build_object('object_mapping', to_jsonb(object_mapping),
                   'attribute_mapping', to_jsonb(attribute_mapping),
                   'source_attribute', to_jsonb(source)) AS baseline
          FROM core.ingestion_attribute_mapping AS attribute_mapping
          JOIN core.ingestion_object_mapping AS object_mapping USING (ingestion_object_mapping_id)
          JOIN core.attribute AS source ON source.attribute_id = attribute_mapping.source_attribute_id
          JOIN objects AS source_object ON source_object.object_id = source.object_id
         WHERE attribute_mapping.target_object_id IN (SELECT object_id FROM selected)
    ), attributes AS MATERIALIZED (
        SELECT attribute.*, object.zone_code,
               CASE WHEN profile.attribute_id IS NOT NULL THEN jsonb_build_object(
                   'profiled_at', profile.updated_time,
                   'row_scope', CASE WHEN profile_run.workflow_run_id IS NOT NULL
                       THEN CASE WHEN profile_run.requested_batch_id IS NULL THEN 'all_rows' ELSE 'batch' END END,
                   'batch_attribute_name', NULL, 'batch_id', profile_run.requested_batch_id,
                   'row_count', profile.row_count, 'non_null_count', profile.non_null_count,
                   'null_count', profile.null_count, 'blank_count', profile.blank_count,
                   'distinct_count', profile.distinct_count, 'min_data_length', profile.min_data_length,
                   'max_data_length', profile.max_data_length, 'avg_data_length', profile.avg_data_length,
                   'percent_populated', profile.percent_populated, 'percent_duplicates', profile.percent_duplicates,
                   'percent_null', profile.percent_null, 'percent_blank', profile.percent_blank,
                   'percent_distinct', profile.percent_distinct) END AS profile,
               CASE WHEN object.zone_code = 'source' THEN 1 ELSE evidence.count END AS source_candidate_count,
               CASE WHEN object.zone_code = 'source' THEN attribute.attribute_id
                    WHEN evidence.count = 1 THEN evidence.attribute_id END AS source_attribute_id,
               CASE WHEN object.zone_code = 'source'
                         THEN nullif(btrim(attribute.fc_attribute_name), '')
                    ELSE attribute.attribute_name END AS relation_column
          FROM core.attribute AS attribute JOIN objects AS object USING (object_id)
          LEFT JOIN workflow.attribute_profile AS profile ON profile.model_id = v_run.model_id
              AND profile.object_id = attribute.object_id AND profile.attribute_id = attribute.attribute_id
          LEFT JOIN application.workflow_run AS profile_run ON profile_run.workflow_run_id = profile.workflow_run_id
              AND profile_run.model_id = v_run.model_id AND profile_run.model_workflow = 'profiling'
          LEFT JOIN LATERAL (
              SELECT count(*) FILTER (WHERE candidate.eligible)::INTEGER AS count,
                     min(candidate.source_attribute_id) FILTER (WHERE candidate.eligible) AS attribute_id
                FROM candidates AS candidate WHERE candidate.target_attribute_id = attribute.attribute_id
          ) AS evidence ON TRUE
         WHERE attribute.object_id IN (SELECT object_id FROM selected)
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'object_id', object.object_id, 'object_name', object.object_name,
               'object_schema', object.object_schema, 'object_description', object.object_description,
               'is_active', object.is_active, 'is_locked', object.is_locked,
               'zone_code', object.zone_code, 'source_tenant_id', object.source_tenant_id,
               'tenant_id', object.tenant_id, 'tenant_catalog', object.tenant_catalog,
               'system_code', object.system_code, 'connection_id', object.connection_id,
               'prompt_inputs', jsonb_build_object(
                   'source_context', (
                       SELECT coalesce(jsonb_agg(DISTINCT source.source_connection_context
                           ORDER BY source.source_connection_context), '[]'::JSONB)
                       FROM objects AS source WHERE source.zone_code = 'source'
                           AND source.is_active AND source.source_tenant_id = v_run.tenant_id
                           AND (source.baseline #>> '{connection,is_active}')::BOOLEAN
                           AND (source.baseline #>> '{system,is_active}')::BOOLEAN
                           AND (source.baseline #>> '{physical_tenant,is_active}')::BOOLEAN
                           AND (source.object_id = object.object_id OR EXISTS (
                               SELECT 1 FROM core.ingestion_object_mapping AS mapping
                               WHERE mapping.target_object_id = object.object_id
                                   AND mapping.source_object_id = source.object_id AND mapping.is_active))),
                   'gds_context', CASE WHEN object.zone_code = 'source' THEN '[]'::JSONB
                       ELSE jsonb_build_array(object.gds_context) END,
                   'object_context', jsonb_build_array(object.physical_key || jsonb_build_object(
                       'object_description', object.object_description, 'zone_code', object.zone_code)),
                   'object_attribute_context', jsonb_build_array(object.physical_key || jsonb_build_object(
                       'selected_attribute_names', (SELECT coalesce(jsonb_agg(attribute.attribute_name
                           ORDER BY attribute.attribute_ordinal_position, attribute.attribute_id), '[]'::JSONB)
                           FROM attributes AS attribute WHERE attribute.object_id = object.object_id AND attribute.is_active),
                       'attributes', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                           'attribute_name', attribute.attribute_name,
                           'attribute_description', attribute.attribute_description,
                           'attribute_data_type', attribute.attribute_data_type,
                           'attribute_inferred_data_type', attribute.attribute_inferred_data_type,
                           'attribute_nullability', attribute.attribute_nullability,
                           'is_natural_key', attribute.is_natural_key,
                           'is_surrogate_key', attribute.is_surrogate_key,
                           'is_masking_required', attribute.is_masking_required,
                           'is_meta_data', attribute.is_meta_data, 'profile', attribute.profile
                       ) ORDER BY attribute.attribute_ordinal_position, attribute.attribute_id), '[]'::JSONB)
                           FROM attributes AS attribute WHERE attribute.object_id = object.object_id AND attribute.is_active))),
                   'ingestion_mapping', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                       'source', source.physical_key || jsonb_build_object('object_description', source.object_description),
                       'target', object.physical_key) ORDER BY mapping.ingestion_object_mapping_id), '[]'::JSONB)
                       FROM core.ingestion_object_mapping AS mapping JOIN objects AS source ON source.object_id = mapping.source_object_id
                       WHERE mapping.target_object_id = object.object_id AND mapping.is_active
                           AND source.zone_code = 'source' AND source.is_active
                           AND source.source_tenant_id = v_run.tenant_id
                           AND (source.baseline #>> '{connection,is_active}')::BOOLEAN
                           AND (source.baseline #>> '{system,is_active}')::BOOLEAN
                           AND (source.baseline #>> '{physical_tenant,is_active}')::BOOLEAN)
               ),
               'relation', object.relation, 'attributes', (
                   SELECT coalesce(jsonb_agg(jsonb_build_object(
                       'attribute_id', attribute.attribute_id, 'attribute_name', attribute.attribute_name,
                       'attribute_data_type', attribute.attribute_data_type,
                       'attribute_inferred_data_type', attribute.attribute_inferred_data_type,
                       'attribute_description', attribute.attribute_description,
                       'attribute_ordinal_position', attribute.attribute_ordinal_position,
                       'is_active', attribute.is_active, 'is_locked', attribute.is_locked,
                       'is_masking_required', attribute.is_masking_required,
                       'relation_column', attribute.relation_column,
                       'source_candidate_count', attribute.source_candidate_count,
                       'source', CASE WHEN source.attribute_id IS NOT NULL THEN jsonb_build_object(
                           'object_id', source_object.object_id, 'object_name', source_object.object_name,
                           'object_schema', source_object.object_schema,
                           'object_description', source_object.object_description,
                           'source_tenant_id', source_object.source_tenant_id,
                           'system_code', source_object.system_code,
                           'attribute_id', source.attribute_id, 'attribute_name', source.attribute_name,
                           'attribute_data_type', source.attribute_data_type,
                           'attribute_inferred_data_type', source.attribute_inferred_data_type,
                           'attribute_description', source.attribute_description,
                           'is_active', source.is_active AND source_object.is_active,
                           'is_masking_required', source.is_masking_required,
                           'relation', source_object.relation,
                           'relation_column', nullif(btrim(source.fc_attribute_name), '')
                       ) END
                   ) ORDER BY attribute.attribute_ordinal_position, attribute.attribute_id), '[]'::JSONB)
                     FROM attributes AS attribute
                     LEFT JOIN core.attribute AS source ON source.attribute_id = attribute.source_attribute_id
                     LEFT JOIN objects AS source_object ON source_object.object_id = source.object_id
                    WHERE attribute.object_id = object.object_id
               )) ORDER BY object.object_id), '[]'::JSONB),
           jsonb_build_object(
               'objects', (SELECT jsonb_agg(baseline ORDER BY object_id) FROM objects),
               'attributes', (SELECT jsonb_agg(to_jsonb(attribute) ORDER BY attribute_id) FROM attributes AS attribute),
               'candidates', (SELECT jsonb_agg(baseline ORDER BY target_attribute_id, source_attribute_id) FROM candidates),
               'object_mappings', (SELECT jsonb_agg(to_jsonb(mapping) ORDER BY ingestion_object_mapping_id)
                   FROM core.ingestion_object_mapping AS mapping
                   WHERE mapping.target_object_id IN (SELECT object_id FROM selected)))
      INTO v_objects, v_baseline
      FROM objects AS object WHERE object.object_id IN (SELECT object_id FROM selected);
    v_context := jsonb_build_object('workflow_run_id', p_workflow_run_id,
        'model_id', v_run.model_id, 'model_revision', p_expected_model_revision,
        'baseline_digest', encode(sha256(convert_to(v_baseline::TEXT, 'UTF8')), 'hex'),
        'objects', v_objects,
        'description_targets', v_run.metadata_enrichment_description_targets,
        'description_revision_matches', v_run.metadata_enrichment_description_targets IS NULL OR NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(v_run.metadata_enrichment_description_targets) AS target
            WHERE NOT EXISTS (
                SELECT 1 FROM core.object AS object
                LEFT JOIN core.attribute AS attribute ON attribute.object_id = object.object_id
                    AND attribute.attribute_id = (target->>'attribute_id')::BIGINT
                WHERE object.object_id = (target->>'object_id')::BIGINT
                  AND CASE WHEN target->>'attribute_id' IS NULL
                      THEN application.metadata_object_review_revision(object) = target->>'expected_revision'
                      ELSE application.metadata_attribute_review_revision(attribute, object) = target->>'expected_revision' END
            )
        ));
    IF octet_length(v_context::TEXT) > 16777216 OR octet_length(v_baseline::TEXT) > 16777216 THEN
        RAISE EXCEPTION 'metadata_enrichment_context_too_large';
    END IF;
    RETURN v_context;
END;
$get_metadata_enrichment_execution_context$;
REVOKE ALL ON FUNCTION application.get_metadata_enrichment_execution_context(UUID, UUID, VARCHAR, BIGINT, BIGINT) FROM PUBLIC;

CREATE FUNCTION application.get_metadata_enrichment_connection_values(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT, p_expected_model_revision BIGINT,
    p_connection_id BIGINT, p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT, model_id BIGINT, model_revision BIGINT,
    gds_connection_id BIGINT, environment_code VARCHAR(100),
    failure_code VARCHAR(50), failure_message VARCHAR(200),
    databricks_host_name TEXT, databricks_http_path TEXT, databricks_token TEXT
)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $get_metadata_enrichment_connection_values$
DECLARE
    v_context JSONB;
    v_environment RECORD;
    v_values RECORD;
BEGIN
    v_context := application.get_metadata_enrichment_execution_context(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        p_workflow_run_id, p_expected_model_revision);
    IF p_connection_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(v_context -> 'objects') AS object
         WHERE (object #>> '{relation,connection_id}')::BIGINT = p_connection_id
            OR EXISTS (
                SELECT 1 FROM jsonb_array_elements(object -> 'attributes') AS attribute
                 WHERE (attribute #>> '{source,relation,connection_id}')::BIGINT = p_connection_id
            )
    ) THEN
        RAISE EXCEPTION 'metadata_enrichment_connection_denied';
    END IF;
    SELECT environment_record.environment_id, environment_record.environment_code
      INTO v_environment FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) = lower(btrim(p_environment_code))
     FOR SHARE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT p_workflow_run_id, (v_context ->> 'model_id')::BIGINT,
            p_expected_model_revision, p_connection_id, NULL::VARCHAR(100),
            'environment_not_found'::VARCHAR(50), 'Enrichment Environment is unavailable.'::VARCHAR(200),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;
    SELECT max(value.connection_value) FILTER (WHERE lower(btrim(parameter.connection_parameter_code)) = 'databricks_host_name') AS host,
           max(value.connection_value) FILTER (WHERE lower(btrim(parameter.connection_parameter_code)) = 'databricks_http_path') AS path,
           max(value.connection_value) FILTER (WHERE lower(btrim(parameter.connection_parameter_code)) = 'databricks_token') AS token
      INTO v_values FROM core.connection_value AS value
      JOIN reference.connection_parameter AS parameter USING (connection_parameter_id)
     WHERE value.connection_id = p_connection_id
       AND value.environment_id = v_environment.environment_id AND parameter.is_active;
    IF v_values.host IS NULL OR v_values.path IS NULL OR v_values.token IS NULL THEN
        RETURN QUERY SELECT p_workflow_run_id, (v_context ->> 'model_id')::BIGINT,
            p_expected_model_revision, p_connection_id, v_environment.environment_code,
            'connection_values_missing'::VARCHAR(50), 'Enrichment connection values are incomplete.'::VARCHAR(200),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;
    RETURN QUERY SELECT p_workflow_run_id, (v_context ->> 'model_id')::BIGINT,
        p_expected_model_revision, p_connection_id, v_environment.environment_code,
        NULL::VARCHAR(50), NULL::VARCHAR(200), v_values.host, v_values.path, v_values.token;
END;
$get_metadata_enrichment_connection_values$;
REVOKE ALL ON FUNCTION application.get_metadata_enrichment_connection_values(UUID, UUID, VARCHAR, BIGINT, BIGINT, BIGINT, VARCHAR) FROM PUBLIC;

CREATE FUNCTION application.get_metadata_enrichment_results(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT, p_limit INTEGER, p_offset INTEGER
)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $get_metadata_enrichment_results$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_counts JSONB;
    v_applied_field_counts JSONB;
    v_results JSONB;
    v_total INTEGER;
    v_warnings INTEGER;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200
       OR p_offset IS NULL OR p_offset NOT BETWEEN 0 AND 10200 THEN
        RAISE EXCEPTION 'metadata_enrichment_invalid_page';
    END IF;
    SELECT run.* INTO v_run FROM application.workflow_run AS run
      JOIN model.model AS target USING (model_id, tenant_id)
     WHERE run.workflow_run_id = p_workflow_run_id AND target.is_active
       AND run.model_workflow = 'metadata_enrichment';
    IF NOT FOUND THEN RAISE EXCEPTION 'metadata_enrichment_run_unavailable'; END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        v_run.tenant_id, 'tenant_read');
    IF NOT coalesce(v_decision.authorized, FALSE) THEN
        RAISE EXCEPTION 'metadata_enrichment_denied';
    END IF;
    SELECT coalesce(jsonb_object_agg(status, count), '{}'::JSONB),
           coalesce(sum(count), 0)::INTEGER,
           coalesce(sum(count) FILTER (WHERE status IN ('changed', 'unavailable', 'inconclusive')), 0)::INTEGER
      INTO v_counts, v_total, v_warnings
      FROM (SELECT result.status, count(*) AS count FROM application.metadata_enrichment_result AS result
             WHERE result.workflow_run_id = p_workflow_run_id GROUP BY result.status) AS counts;
    SELECT jsonb_build_object(
        'object_description', count(*) FILTER (WHERE result.field_name = 'object_description'),
        'attribute_description', count(*) FILTER (WHERE result.field_name = 'attribute_description'),
        'attribute_inferred_data_type', count(*) FILTER (WHERE result.field_name = 'attribute_inferred_data_type')
    ) INTO v_applied_field_counts
      FROM application.metadata_enrichment_result AS result
     WHERE result.workflow_run_id = p_workflow_run_id AND result.status = 'applied';
    SELECT coalesce(jsonb_agg(
        (to_jsonb(result) - 'created_time' - 'workflow_run_id') || jsonb_build_object(
            'object_schema', object.object_schema, 'object_name', object.object_name,
            'attribute_name', attribute.attribute_name, 'storage_type', attribute.attribute_data_type
        ) ORDER BY result.result_id), '[]'::JSONB)
      INTO v_results FROM (SELECT * FROM application.metadata_enrichment_result AS result
          WHERE result.workflow_run_id = p_workflow_run_id ORDER BY result.result_id
          LIMIT p_limit OFFSET p_offset) AS result
      LEFT JOIN core.object AS object ON object.object_id = result.object_id
           AND object.source_tenant_id = v_run.tenant_id
      LEFT JOIN core.attribute AS attribute ON attribute.attribute_id = result.attribute_id
           AND attribute.object_id = object.object_id;
    RETURN jsonb_build_object('workflow_run_id', p_workflow_run_id, 'model_id', v_run.model_id,
        'tenant_id', v_run.tenant_id, 'model_revision', v_run.model_revision,
        'workflow_run_state', v_run.workflow_run_state,
        'total_count', v_total, 'result_count', v_total, 'warning_count', v_warnings,
        'counts', v_counts, 'applied_field_counts', v_applied_field_counts, 'results', v_results);
END;
$get_metadata_enrichment_results$;
REVOKE ALL ON FUNCTION application.get_metadata_enrichment_results(UUID, UUID, VARCHAR, BIGINT, INTEGER, INTEGER) FROM PUBLIC;

CREATE FUNCTION application.complete_metadata_enrichment(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT, p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID, p_expected_baseline_digest CHAR(64), p_results JSONB
)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $complete_metadata_enrichment$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_context JSONB;
    v_result JSONB;
    v_object RECORD;
    v_attribute RECORD;
    v_receipt_digest CHAR(64);
    v_status TEXT;
    v_field TEXT;
    v_value TEXT;
    v_current TEXT;
    v_object_id BIGINT;
    v_attribute_id BIGINT;
    v_sample_count INTEGER;
    v_drift BOOLEAN;
    v_warning_count INTEGER;
    v_summary JSONB;
BEGIN
    IF p_results IS NULL OR jsonb_typeof(p_results) <> 'array'
       OR jsonb_array_length(p_results) > 10200 OR octet_length(p_results::TEXT) > 25165824
       OR p_expected_baseline_digest IS NULL OR p_expected_baseline_digest !~ '^[0-9a-f]{64}$'
       OR p_workflow_run_claim_token IS NULL THEN
        RAISE EXCEPTION 'metadata_enrichment_invalid_results';
    END IF;
    v_receipt_digest := encode(sha256(convert_to(jsonb_build_object(
        'run', p_workflow_run_id, 'revision', p_expected_model_revision,
        'claim_digest', encode(sha256(convert_to(p_workflow_run_claim_token::TEXT, 'UTF8')), 'hex'),
        'baseline', p_expected_baseline_digest, 'results', p_results)::TEXT, 'UTF8')), 'hex');
    SELECT run.*, target.model_revision AS current_model_revision INTO v_run
      FROM application.workflow_run AS run JOIN model.model AS target USING (model_id, tenant_id)
     WHERE run.workflow_run_id = p_workflow_run_id AND target.is_active
     FOR UPDATE OF run, target;
    IF NOT FOUND THEN RAISE EXCEPTION 'metadata_enrichment_run_unavailable'; END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        v_run.tenant_id, 'tenant_model_write');
    IF NOT coalesce(v_decision.authorized, FALSE) THEN RAISE EXCEPTION 'metadata_enrichment_denied'; END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN RAISE EXCEPTION 'workflow_run_owner_mismatch'; END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        v_run.tenant_id, 'tenant_metadata_write');
    IF NOT coalesce(v_decision.authorized, FALSE) THEN RAISE EXCEPTION 'metadata_enrichment_denied'; END IF;
    IF v_run.model_workflow <> 'metadata_enrichment' THEN RAISE EXCEPTION 'metadata_enrichment_run_unavailable'; END IF;
    IF p_expected_model_revision IS NULL OR v_run.model_revision <> p_expected_model_revision
       OR v_run.current_model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;
    -- Completed replay precedes the live-claim check: completion clears claims.
    IF v_run.metadata_enrichment_receipt_digest IS NOT NULL THEN
        IF v_run.metadata_enrichment_receipt_digest <> v_receipt_digest
           OR v_run.workflow_run_state NOT IN ('completed', 'completed_with_repair') THEN
            RAISE EXCEPTION 'metadata_enrichment_completion_conflict';
        END IF;
        RETURN application.get_metadata_enrichment_results(p_entra_tenant_id, p_entra_object_id,
            p_expected_principal_type, p_workflow_run_id, 1, 0) - 'results' - 'total_count' - 'tenant_id' - 'applied_field_counts';
    END IF;
    PERFORM application.assert_workflow_run_claim(p_workflow_run_id, p_workflow_run_claim_token);

    -- Parent locks also fence new Attribute/mapping FK references. Existing
    -- mapping rows are held before resolving and locking Source evidence.
    PERFORM 1 FROM core.object AS object
      JOIN application.workflow_run_object_selection AS selection USING (object_id)
     WHERE selection.workflow_run_id = p_workflow_run_id ORDER BY object.object_id FOR UPDATE OF object;
    PERFORM 1 FROM core.ingestion_object_mapping AS mapping
      JOIN application.workflow_run_object_selection AS selection ON selection.object_id = mapping.target_object_id
     WHERE selection.workflow_run_id = p_workflow_run_id
     ORDER BY mapping.ingestion_object_mapping_id FOR UPDATE OF mapping;
    PERFORM 1 FROM core.ingestion_attribute_mapping AS mapping
      JOIN application.workflow_run_object_selection AS selection ON selection.object_id = mapping.target_object_id
     WHERE selection.workflow_run_id = p_workflow_run_id
     ORDER BY mapping.ingestion_attribute_mapping_id FOR SHARE OF mapping;
    PERFORM 1 FROM core.object AS object WHERE object.object_id IN (
        SELECT mapping.source_object_id FROM core.ingestion_object_mapping AS mapping
        JOIN application.workflow_run_object_selection AS selection ON selection.object_id = mapping.target_object_id
        WHERE selection.workflow_run_id = p_workflow_run_id
    ) ORDER BY object.object_id FOR UPDATE OF object;
    PERFORM 1 FROM core.attribute AS attribute WHERE attribute.object_id IN (
        SELECT selection.object_id FROM application.workflow_run_object_selection AS selection
         WHERE selection.workflow_run_id = p_workflow_run_id
        UNION SELECT mapping.source_object_id FROM core.ingestion_object_mapping AS mapping
        JOIN application.workflow_run_object_selection AS selection ON selection.object_id = mapping.target_object_id
        WHERE selection.workflow_run_id = p_workflow_run_id
    ) ORDER BY attribute.attribute_id FOR UPDATE OF attribute;
    -- Relation and ownership dependencies must remain stable through completion.
    PERFORM 1 FROM core.tenant AS tenant WHERE tenant.tenant_id = v_run.tenant_id FOR SHARE;
    PERFORM 1 FROM core.connection AS connection WHERE connection.connection_id IN (
        SELECT object.connection_id FROM core.object AS object WHERE object.source_tenant_id = v_run.tenant_id
        UNION SELECT tenant.gds_connection_id FROM core.tenant AS tenant WHERE tenant.tenant_id = v_run.tenant_id
    ) ORDER BY connection.connection_id FOR SHARE;
    PERFORM 1 FROM core.system AS system WHERE system.system_id IN (
        SELECT connection.system_id FROM core.connection AS connection
        JOIN core.object AS object USING (connection_id) WHERE object.source_tenant_id = v_run.tenant_id
    ) ORDER BY system.system_id FOR SHARE;
    PERFORM 1 FROM reference.zone AS zone ORDER BY zone.zone_id FOR SHARE;
    v_context := application.get_metadata_enrichment_execution_context(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type,
        p_workflow_run_id, p_expected_model_revision);
    v_drift := v_context ->> 'baseline_digest' <> p_expected_baseline_digest
        OR NOT (v_context->>'description_revision_matches')::BOOLEAN;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_results) AS result
        GROUP BY result ->> 'object_id', result ->> 'attribute_id', result ->> 'field_name' HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'metadata_enrichment_duplicate_result';
    END IF;
    IF v_run.metadata_enrichment_description_targets IS NOT NULL THEN
        IF jsonb_array_length(p_results) <> (SELECT sum(CASE WHEN target->>'attribute_id' IS NULL THEN 1 ELSE 2 END)
              FROM jsonb_array_elements(v_run.metadata_enrichment_description_targets) AS target)
           OR EXISTS (
               SELECT target->'object_id', target->'attribute_id', field.name
                 FROM jsonb_array_elements(v_run.metadata_enrichment_description_targets) AS target
                 CROSS JOIN LATERAL (SELECT CASE WHEN target->>'attribute_id' IS NULL THEN 'object_description' ELSE 'attribute_description' END AS name
                     UNION ALL SELECT 'attribute_inferred_data_type' WHERE target->>'attribute_id' IS NOT NULL) AS field
               EXCEPT
               SELECT result->'object_id', result->'attribute_id', result->>'field_name'
                 FROM jsonb_array_elements(p_results) AS result
           ) THEN
            RAISE EXCEPTION 'metadata_enrichment_result_coverage_incomplete';
        END IF;
    ELSIF NOT v_drift AND (jsonb_array_length(p_results) <> (
        SELECT count(*) FROM (
            SELECT object.object_id, NULL::BIGINT AS attribute_id, 'object_description' AS field_name
              FROM application.workflow_run_object_selection AS object
             WHERE object.workflow_run_id = p_workflow_run_id
            UNION ALL
            SELECT attribute.object_id, attribute.attribute_id, field.name
              FROM core.attribute AS attribute
              JOIN application.workflow_run_object_selection AS selection USING (object_id)
              CROSS JOIN (VALUES ('attribute_description'), ('attribute_inferred_data_type')) AS field(name)
             WHERE selection.workflow_run_id = p_workflow_run_id
        ) AS expected
    ) OR EXISTS (
        SELECT jsonb_build_array(object -> 'object_id', 'null'::JSONB, 'object_description'::TEXT)
          FROM jsonb_array_elements(v_context -> 'objects') AS object
        UNION ALL
        SELECT jsonb_build_array(object -> 'object_id', attribute -> 'attribute_id', field.name)
          FROM jsonb_array_elements(v_context -> 'objects') AS object,
               jsonb_array_elements(object -> 'attributes') AS attribute,
               (VALUES ('attribute_description'), ('attribute_inferred_data_type')) AS field(name)
        EXCEPT
        SELECT jsonb_build_array(result -> 'object_id', result -> 'attribute_id', result -> 'field_name')
          FROM jsonb_array_elements(p_results) AS result
    )) THEN
        RAISE EXCEPTION 'metadata_enrichment_result_coverage_incomplete';
    END IF;
    FOR v_result IN SELECT value FROM jsonb_array_elements(p_results)
    LOOP
        IF jsonb_typeof(v_result) <> 'object'
           OR NOT v_result ?& ARRAY['object_id', 'attribute_id', 'field_name', 'status', 'evidence_method', 'applied_value', 'sample_count']
           OR v_result - ARRAY['object_id', 'attribute_id', 'field_name', 'status', 'evidence_method', 'applied_value', 'sample_count'] <> '{}'::JSONB
           OR jsonb_typeof(v_result -> 'object_id') <> 'number'
           OR (v_result ->> 'object_id') !~ '^[1-9][0-9]{0,17}$'
           OR jsonb_typeof(v_result -> 'sample_count') <> 'number'
           OR (v_result ->> 'sample_count') !~ '^[0-9]{1,2}$'
           OR (v_result ->> 'sample_count')::INTEGER > 50
           OR jsonb_typeof(v_result -> 'field_name') <> 'string'
           OR jsonb_typeof(v_result -> 'status') <> 'string'
           OR jsonb_typeof(v_result -> 'evidence_method') <> 'string'
           OR v_result ->> 'field_name' NOT IN ('object_description', 'attribute_description', 'attribute_inferred_data_type')
           OR v_result ->> 'status' NOT IN ('applied', 'existing', 'locked', 'inactive', 'changed', 'unavailable', 'inconclusive')
           OR v_result ->> 'evidence_method' NOT IN ('agent_description', 'source_comment', 'registered_type', 'source_schema', 'bronze_schema', 'source_sample', 'bronze_sample', 'none')
           OR jsonb_typeof(v_result -> 'applied_value') NOT IN ('null', 'string') THEN
            RAISE EXCEPTION 'metadata_enrichment_invalid_result';
        END IF;
        v_object_id := (v_result ->> 'object_id')::BIGINT;
        v_field := v_result ->> 'field_name';
        v_sample_count := (v_result ->> 'sample_count')::INTEGER;
        v_value := v_result ->> 'applied_value';
        IF (v_field = 'object_description' AND v_result -> 'attribute_id' <> 'null'::JSONB)
           OR (v_field <> 'object_description' AND (
               jsonb_typeof(v_result -> 'attribute_id') <> 'number'
               OR (v_result ->> 'attribute_id') !~ '^[1-9][0-9]{0,17}$'))
           OR (v_result ->> 'status' <> 'applied' AND v_value IS NOT NULL)
           OR (v_result ->> 'status' = 'applied' AND (
               (v_value IS NULL AND v_field = 'attribute_inferred_data_type')
               OR (v_value IS NOT NULL AND NOT reference.is_nonblank(v_value))
               OR CASE WHEN v_field = 'attribute_inferred_data_type'
                    THEN v_value ~ '[[:cntrl:]]'
                    ELSE translate(v_value, chr(9) || chr(10) || chr(13), '') ~ '[[:cntrl:]]' END
               OR (v_field = 'attribute_inferred_data_type' AND length(v_value) > 100)
               OR (v_field <> 'attribute_inferred_data_type' AND octet_length(v_value) > 2000))) THEN
            RAISE EXCEPTION 'metadata_enrichment_invalid_value';
        END IF;
        v_attribute_id := (v_result ->> 'attribute_id')::BIGINT;
        SELECT object.* INTO v_object FROM core.object AS object
          JOIN application.workflow_run_object_selection AS selection USING (object_id)
         WHERE selection.workflow_run_id = p_workflow_run_id AND object.object_id = v_object_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'metadata_enrichment_result_outside_scope'; END IF;
        v_current := v_object.object_description;
        v_status := CASE WHEN NOT v_object.is_active THEN 'inactive' WHEN v_object.is_locked THEN 'locked' END;
        IF v_attribute_id IS NOT NULL THEN
            SELECT * INTO v_attribute FROM core.attribute AS attribute
             WHERE attribute.attribute_id = v_attribute_id AND attribute.object_id = v_object_id;
            IF NOT FOUND THEN RAISE EXCEPTION 'metadata_enrichment_result_outside_scope'; END IF;
            v_current := CASE v_field WHEN 'attribute_description' THEN v_attribute.attribute_description
                ELSE v_attribute.attribute_inferred_data_type END;
            v_status := CASE WHEN NOT v_attribute.is_active THEN 'inactive'
                WHEN v_status IS NOT NULL THEN v_status WHEN v_attribute.is_locked THEN 'locked' END;
            IF v_result ->> 'evidence_method' IN ('source_sample', 'bronze_sample') AND (
                v_attribute.is_masking_required OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(v_context -> 'objects') AS object,
                        jsonb_array_elements(object -> 'attributes') AS attribute
                     WHERE (attribute ->> 'attribute_id')::BIGINT = v_attribute_id
                       AND coalesce((attribute #>> '{source,is_masking_required}')::BOOLEAN, FALSE)
                )) THEN RAISE EXCEPTION 'metadata_enrichment_masked_sample_denied'; END IF;
        END IF;
        IF v_sample_count > 0 AND v_result ->> 'evidence_method' NOT IN ('source_sample', 'bronze_sample') THEN
            RAISE EXCEPTION 'metadata_enrichment_invalid_evidence';
        END IF;
        IF v_result ->> 'status' = 'applied' AND (
            (v_field <> 'attribute_inferred_data_type' AND v_result ->> 'evidence_method' NOT IN ('agent_description', 'source_comment'))
            OR (v_field = 'attribute_inferred_data_type' AND v_result ->> 'evidence_method' NOT IN ('registered_type', 'source_schema', 'bronze_schema', 'source_sample', 'bronze_sample'))
        ) THEN RAISE EXCEPTION 'metadata_enrichment_invalid_evidence'; END IF;
        -- The original baseline fences every attempted patch. Locked descriptions
        -- remain immutable; generated unlocked descriptions, including null, replace
        -- current text. Inferred types still fill only missing values.
        v_status := CASE WHEN v_drift THEN 'changed' WHEN v_status IS NOT NULL THEN v_status
            WHEN reference.is_nonblank(v_current) AND v_field = 'attribute_inferred_data_type' THEN 'existing'
            WHEN v_result ->> 'status' IN ('applied', 'unavailable', 'inconclusive') THEN v_result ->> 'status'
            ELSE 'inconclusive' END;
        IF v_status = 'applied' THEN
            IF v_field = 'object_description' THEN
                UPDATE core.object SET object_description = v_value,
                    updated_time = clock_timestamp(), updated_by = v_decision.principal_id::TEXT
                 WHERE object_id = v_object_id;
            ELSIF v_field = 'attribute_description' THEN
                UPDATE core.attribute SET attribute_description = v_value,
                    updated_time = clock_timestamp(), updated_by = v_decision.principal_id::TEXT
                 WHERE attribute_id = v_attribute_id;
            ELSE
                UPDATE core.attribute SET attribute_inferred_data_type = v_value,
                    updated_time = clock_timestamp(), updated_by = v_decision.principal_id::TEXT
                 WHERE attribute_id = v_attribute_id;
            END IF;
        END IF;
        INSERT INTO application.metadata_enrichment_result (
            workflow_run_id, object_id, attribute_id, field_name, status, evidence_method, applied_value, sample_count
        ) VALUES (p_workflow_run_id, v_object_id, v_attribute_id, v_field, v_status,
            v_result ->> 'evidence_method', CASE WHEN v_status = 'applied' THEN v_value END, v_sample_count);
    END LOOP;
    IF v_drift AND v_run.metadata_enrichment_description_targets IS NULL THEN
        -- A newly registered Attribute has no original candidate. Record its
        -- current fields as changed too, without inventing an inferred value.
        INSERT INTO application.metadata_enrichment_result (
            workflow_run_id, object_id, attribute_id, field_name,
            status, evidence_method, applied_value, sample_count
        )
        SELECT p_workflow_run_id, expected.object_id, expected.attribute_id,
               expected.field_name, 'changed', 'none', NULL, 0
          FROM (
              SELECT selection.object_id, NULL::BIGINT AS attribute_id,
                     'object_description' AS field_name
                FROM application.workflow_run_object_selection AS selection
               WHERE selection.workflow_run_id = p_workflow_run_id
              UNION ALL
              SELECT attribute.object_id, attribute.attribute_id, field.name
                FROM core.attribute AS attribute
                JOIN application.workflow_run_object_selection AS selection USING (object_id)
                CROSS JOIN (VALUES ('attribute_description'), ('attribute_inferred_data_type')) AS field(name)
               WHERE selection.workflow_run_id = p_workflow_run_id
          ) AS expected
         WHERE NOT EXISTS (
             SELECT 1 FROM application.metadata_enrichment_result AS result
              WHERE result.workflow_run_id = p_workflow_run_id
                AND result.object_id = expected.object_id
                AND result.attribute_id IS NOT DISTINCT FROM expected.attribute_id
                AND result.field_name = expected.field_name
         ) ORDER BY expected.object_id, expected.attribute_id NULLS FIRST, expected.field_name;
    END IF;
    -- Recheck expiry after work and before establishing the atomic receipt.
    PERFORM application.assert_workflow_run_claim(p_workflow_run_id, p_workflow_run_claim_token);
    UPDATE application.workflow_run SET metadata_enrichment_receipt_digest = v_receipt_digest
     WHERE workflow_run_id = p_workflow_run_id;
    SELECT count(*)::INTEGER INTO v_warning_count FROM application.metadata_enrichment_result
     WHERE workflow_run_id = p_workflow_run_id AND status IN ('changed', 'unavailable', 'inconclusive');
    PERFORM application.complete_workflow_run(p_entra_tenant_id, p_entra_object_id,
        p_expected_principal_type, p_workflow_run_id, p_expected_model_revision, v_warning_count);
    v_summary := application.get_metadata_enrichment_results(p_entra_tenant_id, p_entra_object_id,
        p_expected_principal_type, p_workflow_run_id, 1, 0);
    RETURN v_summary - 'results' - 'total_count' - 'tenant_id' - 'applied_field_counts';
END;
$complete_metadata_enrichment$;
REVOKE ALL ON FUNCTION application.complete_metadata_enrichment(UUID, UUID, VARCHAR, BIGINT, BIGINT, UUID, CHAR, JSONB) FROM PUBLIC;

-- Opaque full-row witnesses shared by catalog reads and explicit physical review.
-- Epoch timestamps keep the digest independent of the database session timezone.
CREATE FUNCTION application.metadata_object_review_revision(p_object core.object)
RETURNS TEXT LANGUAGE SQL IMMUTABLE STRICT SECURITY INVOKER SET search_path = pg_catalog
AS $metadata_object_review_revision$
    SELECT encode(sha256(convert_to((
        (to_jsonb(p_object) - 'created_time' - 'updated_time') || jsonb_build_object(
            'created_time', extract(epoch FROM p_object.created_time),
            'updated_time', extract(epoch FROM p_object.updated_time)
        )
    )::TEXT, 'UTF8')), 'hex')
$metadata_object_review_revision$;
REVOKE ALL ON FUNCTION application.metadata_object_review_revision(core.object) FROM PUBLIC;

CREATE FUNCTION application.metadata_attribute_review_revision(
    p_attribute core.attribute, p_object core.object
)
RETURNS TEXT LANGUAGE SQL IMMUTABLE STRICT SECURITY INVOKER SET search_path = pg_catalog
AS $metadata_attribute_review_revision$
    SELECT encode(sha256(convert_to(jsonb_build_object(
        'attribute', (to_jsonb(p_attribute) - 'created_time' - 'updated_time') || jsonb_build_object(
            'created_time', extract(epoch FROM p_attribute.created_time),
            'updated_time', extract(epoch FROM p_attribute.updated_time)
        ),
        'parent', jsonb_build_object('object_id', p_object.object_id,
            'source_tenant_id', p_object.source_tenant_id,
            'is_active', p_object.is_active, 'is_locked', p_object.is_locked)
    )::TEXT, 'UTF8')), 'hex')
$metadata_attribute_review_revision$;
REVOKE ALL ON FUNCTION application.metadata_attribute_review_revision(core.attribute, core.object) FROM PUBLIC;

CREATE TABLE application.metadata_review_event (
    metadata_review_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES core.tenant (tenant_id),
    actor_principal_id BIGINT NOT NULL REFERENCES security.principal (principal_id),
    correlation_id UUID NOT NULL,
    record_type VARCHAR(10) NOT NULL,
    action VARCHAR(10) NOT NULL,
    request_digest CHAR(64) NOT NULL,
    action_count INTEGER NOT NULL,
    before_records JSONB NOT NULL,
    records JSONB NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_metadata_review_request UNIQUE (tenant_id, actor_principal_id, correlation_id),
    CONSTRAINT ck_metadata_review_action CHECK (
        record_type IN ('object', 'attribute') AND action IN ('lock', 'unlock', 'deactivate', 'reactivate', 'describe')
        AND request_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_metadata_review_records CHECK (
        jsonb_typeof(before_records) = 'array' AND jsonb_typeof(records) = 'array'
        AND jsonb_array_length(records) BETWEEN 1 AND 200
        AND jsonb_array_length(before_records) = jsonb_array_length(records)
        AND action_count BETWEEN 0 AND jsonb_array_length(records)
        AND octet_length(before_records::TEXT) <= 65536 AND octet_length(records::TEXT) <= 65536
    )
);
CREATE FUNCTION application.guard_metadata_review_event()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = pg_catalog
AS $guard_metadata_review_event$
BEGIN
    RAISE EXCEPTION 'Metadata review events are immutable';
END;
$guard_metadata_review_event$;
CREATE TRIGGER guard_metadata_review_event BEFORE UPDATE OR DELETE
ON application.metadata_review_event FOR EACH ROW EXECUTE FUNCTION application.guard_metadata_review_event();
REVOKE ALL ON application.metadata_review_event FROM PUBLIC;

-- Model review and workflow start both lock Model before Tenant. Read authority
-- precedes the exclusive fence; write authority is checked again after waiting.
CREATE FUNCTION application.authorize_model_record_review(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_expected_principal_type VARCHAR,
    p_tenant_id BIGINT, p_model_id BIGINT
)
RETURNS TABLE (
    denial_code VARCHAR(50), principal_id BIGINT, model_id BIGINT,
    tenant_id BIGINT, model_name VARCHAR(255), model_revision BIGINT
)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $authorize_model_record_review$
DECLARE
    v_model model.model%ROWTYPE;
    v_decision RECORD;
BEGIN
    IF p_entra_tenant_id IS NULL OR p_entra_object_id IS NULL
       OR p_tenant_id IS NULL OR p_tenant_id < 1
       OR p_model_id IS NULL OR p_model_id < 1 THEN
        denial_code := 'invalid_request'; RETURN NEXT; RETURN;
    END IF;
    IF p_expected_principal_type IS DISTINCT FROM 'user' THEN
        denial_code := 'authorization_denied'; RETURN NEXT; RETURN;
    END IF;
    SELECT target.* INTO v_model FROM model.model AS target
     WHERE target.model_id = p_model_id AND target.tenant_id = p_tenant_id AND target.is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        denial_code := 'model_not_found'; RETURN NEXT; RETURN;
    END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type, p_tenant_id, 'tenant_read');
    IF NOT FOUND OR NOT v_decision.authorized THEN
        denial_code := coalesce(v_decision.denial_code, 'authorization_denied'); RETURN NEXT; RETURN;
    END IF;
    -- Never acquire authorization's SHARE lock before this exclusive lock.
    PERFORM 1 FROM security.tenant_lock AS tenant_lock
     WHERE tenant_lock.tenant_id = p_tenant_id FOR UPDATE;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type, p_tenant_id, 'tenant_model_write');
    IF NOT FOUND OR NOT v_decision.authorized THEN
        denial_code := coalesce(v_decision.denial_code, 'authorization_denied'); RETURN NEXT; RETURN;
    END IF;
    principal_id := v_decision.principal_id;
    model_id := v_model.model_id;
    tenant_id := v_model.tenant_id;
    model_name := v_model.model_name;
    model_revision := v_model.model_revision;
    RETURN NEXT;
END;
$authorize_model_record_review$;
REVOKE ALL ON FUNCTION application.authorize_model_record_review(UUID, UUID, VARCHAR, BIGINT, BIGINT) FROM PUBLIC;

-- Narrow web-only Scope primitive. The caller records the validated Change Set
-- and advances its revision in this same transaction; direct table writes stay denied.
CREATE FUNCTION application.add_model_input_scope_objects(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_tenant_id BIGINT,
    p_model_id BIGINT, p_expected_model_revision BIGINT, p_object_ids BIGINT[]
)
RETURNS INTEGER
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $add_model_input_scope_objects$
DECLARE
    v_decision RECORD;
    v_count INTEGER;
BEGIN
    IF p_object_ids IS NULL OR cardinality(p_object_ids) NOT BETWEEN 1 AND 200
       OR (SELECT count(DISTINCT id) FROM unnest(p_object_ids) AS ids(id))
            <> cardinality(p_object_ids)
       OR EXISTS (SELECT 1 FROM unnest(p_object_ids) AS ids(id) WHERE id IS NULL OR id < 1) THEN
        RAISE EXCEPTION 'invalid Input Scope selection' USING ERRCODE = '22023';
    END IF;
    SELECT * INTO v_decision FROM application.authorize_model_record_review(
        p_entra_tenant_id, p_entra_object_id, 'user', p_tenant_id, p_model_id);
    IF NOT FOUND OR v_decision.denial_code IS NOT NULL THEN
        RAISE EXCEPTION 'Input Scope authorization denied' USING ERRCODE = '42501';
    END IF;
    IF v_decision.model_revision IS DISTINCT FROM p_expected_model_revision THEN
        RAISE EXCEPTION 'Model revision changed' USING ERRCODE = '40001';
    END IF;
    IF EXISTS (SELECT 1 FROM application.workflow_run AS run
        JOIN model.model AS target ON target.model_id = run.model_id
        WHERE target.tenant_id = p_tenant_id AND run.workflow_run_state = 'running') THEN
        RAISE EXCEPTION 'Tenant workflow is running' USING ERRCODE = '55000';
    END IF;
    IF (SELECT count(*) FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
        WHERE eligible.object_id = ANY(p_object_ids) AND eligible.is_model_input_eligible)
        <> cardinality(p_object_ids) THEN
        RAISE EXCEPTION 'Objects are not eligible for Input Scope' USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM model.model_input_scope AS scope
     WHERE scope.model_id = p_model_id AND scope.object_id = ANY(p_object_ids)
     ORDER BY scope.model_input_scope_id FOR UPDATE;
    IF EXISTS (SELECT 1 FROM model.model_input_scope AS scope
        WHERE scope.model_id = p_model_id AND scope.object_id = ANY(p_object_ids)
          AND scope.model_input_scope_is_locked AND NOT scope.is_active) THEN
        RAISE EXCEPTION 'Input Scope record is locked' USING ERRCODE = '55000';
    END IF;
    INSERT INTO model.model_input_scope (model_id, object_id, created_by, updated_by)
    SELECT p_model_id, id, v_decision.principal_id::TEXT, v_decision.principal_id::TEXT
      FROM unnest(p_object_ids) AS ids(id) ORDER BY id
    ON CONFLICT (model_id, object_id) DO UPDATE
       SET is_active = TRUE, updated_time = clock_timestamp(),
           updated_by = EXCLUDED.updated_by
     WHERE NOT model.model_input_scope.is_active;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$add_model_input_scope_objects$;
REVOKE ALL ON FUNCTION application.add_model_input_scope_objects(
    UUID, UUID, BIGINT, BIGINT, BIGINT, BIGINT[]) FROM PUBLIC;

CREATE FUNCTION application.review_metadata_records(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_expected_principal_type VARCHAR,
    p_tenant_id BIGINT, p_record_type VARCHAR, p_action VARCHAR, p_records JSONB,
    p_correlation_id UUID
)
RETURNS TABLE (denial_code VARCHAR(50), review_event_id BIGINT, action_count INTEGER, records JSONB)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $review_metadata_records$
DECLARE
    v_decision RECORD;
    v_existing application.metadata_review_event%ROWTYPE;
    v_records JSONB;
    v_before JSONB;
    v_ids BIGINT[];
    v_parent_ids BIGINT[];
    v_request_digest CHAR(64);
    v_now TIMESTAMPTZ;
    v_actor VARCHAR(255);
    v_count INTEGER;
BEGIN
    IF p_entra_tenant_id IS NULL OR p_entra_object_id IS NULL OR p_tenant_id IS NULL
       OR p_tenant_id < 1 OR p_correlation_id IS NULL
       OR p_record_type IS NULL OR p_record_type NOT IN ('object', 'attribute')
       OR p_action IS NULL OR p_action NOT IN ('lock', 'unlock', 'deactivate', 'reactivate', 'describe')
       OR p_records IS NULL OR jsonb_typeof(p_records) <> 'array' THEN
        denial_code := 'invalid_request'; RETURN NEXT; RETURN;
    END IF;
    IF p_expected_principal_type IS DISTINCT FROM 'user' THEN
        denial_code := 'authorization_denied'; RETURN NEXT; RETURN;
    END IF;
    IF jsonb_array_length(p_records) NOT BETWEEN 1 AND 200
       OR octet_length(p_records::TEXT) > 32768 OR EXISTS (
           SELECT 1 FROM jsonb_array_elements(p_records) AS item(value)
            WHERE jsonb_typeof(item.value) <> 'object'
               OR NOT item.value ?& ARRAY['record_id', 'expected_revision']
               OR item.value - CASE WHEN p_action = 'describe'
                    THEN ARRAY['record_id', 'expected_revision', 'description']
                    ELSE ARRAY['record_id', 'expected_revision'] END <> '{}'::JSONB
               OR (p_action = 'describe' AND (
                    NOT item.value ? 'description'
                    OR jsonb_typeof(item.value->'description') NOT IN ('string', 'null')
                    OR octet_length(item.value->>'description') > 2000
                    OR (item.value->>'description') ~ '[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]'
               ))
               OR jsonb_typeof(item.value->'record_id') IS DISTINCT FROM 'number'
               OR (item.value->>'record_id') !~ '^[1-9][0-9]{0,18}$'
               OR jsonb_typeof(item.value->'expected_revision') IS DISTINCT FROM 'string'
               OR (item.value->>'expected_revision') !~ '^[0-9a-f]{64}$'
       ) THEN
        denial_code := 'invalid_request'; RETURN NEXT; RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_records) AS item(value)
               WHERE (item.value->>'record_id')::NUMERIC > 9223372036854775807)
       OR (SELECT count(DISTINCT item.value->>'record_id')
             FROM jsonb_array_elements(p_records) AS item(value)) <> jsonb_array_length(p_records) THEN
        denial_code := 'invalid_request'; RETURN NEXT; RETURN;
    END IF;
    SELECT array_agg((item.value->>'record_id')::BIGINT ORDER BY (item.value->>'record_id')::BIGINT),
           jsonb_agg(item.value ORDER BY (item.value->>'record_id')::BIGINT)
      INTO v_ids, v_records FROM jsonb_array_elements(p_records) AS item(value);
    v_request_digest := encode(sha256(convert_to(jsonb_build_object(
        'record_type', p_record_type, 'action', p_action, 'records', v_records
    )::TEXT, 'UTF8')), 'hex');

    -- Do not upgrade a SHARE lock: simultaneous reviews would deadlock.
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type, p_tenant_id, 'tenant_read');
    IF NOT FOUND OR NOT v_decision.authorized THEN
        denial_code := coalesce(v_decision.denial_code, 'authorization_denied'); RETURN NEXT; RETURN;
    END IF;
    PERFORM 1 FROM security.tenant_lock WHERE tenant_id = p_tenant_id FOR UPDATE;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type, p_tenant_id, 'tenant_metadata_write');
    IF NOT FOUND OR NOT v_decision.authorized THEN
        denial_code := coalesce(v_decision.denial_code, 'authorization_denied'); RETURN NEXT; RETURN;
    END IF;
    SELECT event.* INTO v_existing FROM application.metadata_review_event AS event
     WHERE event.tenant_id = p_tenant_id AND event.actor_principal_id = v_decision.principal_id
       AND event.correlation_id = p_correlation_id;
    IF FOUND THEN
        IF v_existing.request_digest <> v_request_digest THEN
            denial_code := 'metadata_review_conflict'; RETURN NEXT; RETURN;
        END IF;
        review_event_id := v_existing.metadata_review_event_id;
        action_count := v_existing.action_count;
        records := v_existing.records;
        RETURN NEXT; RETURN;
    END IF;
    -- Starts hold Model/Run before Tenant Lock SHARE. Never lock those rows here.
    IF EXISTS (SELECT 1 FROM application.workflow_run
               WHERE tenant_id = p_tenant_id AND workflow_run_state = 'running') THEN
        denial_code := 'tenant_workflow_conflict'; RETURN NEXT; RETURN;
    END IF;
    IF p_record_type = 'object' THEN
        PERFORM 1 FROM core.object WHERE object_id = ANY(v_ids) AND source_tenant_id = p_tenant_id
         ORDER BY object_id FOR UPDATE;
        SELECT count(*) INTO v_count FROM core.object
         WHERE object_id = ANY(v_ids) AND source_tenant_id = p_tenant_id;
        IF v_count <> cardinality(v_ids) THEN
            denial_code := 'metadata_selection_conflict'; RETURN NEXT; RETURN;
        END IF;
        IF EXISTS (SELECT 1 FROM jsonb_to_recordset(v_records) AS item(record_id BIGINT, expected_revision TEXT)
                   JOIN core.object AS object ON object.object_id = item.record_id
                   WHERE application.metadata_object_review_revision(object) <> item.expected_revision) THEN
            denial_code := 'metadata_revision_conflict'; RETURN NEXT; RETURN;
        END IF;
        IF p_action IN ('deactivate', 'reactivate', 'describe') AND EXISTS (
            SELECT 1 FROM core.object WHERE object_id = ANY(v_ids) AND is_locked
        ) THEN
            denial_code := 'object_locked'; RETURN NEXT; RETURN;
        END IF;
        SELECT jsonb_agg(jsonb_build_object('record_id', object_id,
            'is_active', is_active, 'is_locked', is_locked) || CASE WHEN p_action = 'describe'
            THEN jsonb_build_object('description_digest', encode(sha256(convert_to(
                jsonb_build_object('value', object_description)::TEXT, 'UTF8')), 'hex'))
            ELSE '{}'::JSONB END ORDER BY object_id)
          INTO v_before FROM core.object WHERE object_id = ANY(v_ids);
    ELSE
        SELECT array_agg(DISTINCT object.object_id ORDER BY object.object_id) INTO v_parent_ids
          FROM core.attribute AS attribute JOIN core.object AS object USING (object_id)
         WHERE attribute.attribute_id = ANY(v_ids) AND object.source_tenant_id = p_tenant_id;
        PERFORM 1 FROM core.object WHERE object_id = ANY(v_parent_ids) AND source_tenant_id = p_tenant_id
         ORDER BY object_id FOR UPDATE;
        PERFORM 1 FROM core.attribute WHERE attribute_id = ANY(v_ids) AND object_id = ANY(v_parent_ids)
         ORDER BY attribute_id FOR UPDATE;
        SELECT count(*) INTO v_count FROM core.attribute AS attribute JOIN core.object AS object USING (object_id)
         WHERE attribute.attribute_id = ANY(v_ids) AND object.object_id = ANY(v_parent_ids)
           AND object.source_tenant_id = p_tenant_id;
        IF v_count <> cardinality(v_ids) THEN
            denial_code := 'metadata_selection_conflict'; RETURN NEXT; RETURN;
        END IF;
        IF EXISTS (SELECT 1 FROM jsonb_to_recordset(v_records) AS item(record_id BIGINT, expected_revision TEXT)
                   JOIN core.attribute AS attribute ON attribute.attribute_id = item.record_id
                   JOIN core.object AS object USING (object_id)
                   WHERE application.metadata_attribute_review_revision(attribute, object) <> item.expected_revision) THEN
            denial_code := 'metadata_revision_conflict'; RETURN NEXT; RETURN;
        END IF;
        IF EXISTS (SELECT 1 FROM core.object WHERE object_id = ANY(v_parent_ids) AND is_locked) THEN
            denial_code := 'object_locked'; RETURN NEXT; RETURN;
        END IF;
        IF p_action IN ('deactivate', 'reactivate', 'describe') AND EXISTS (
            SELECT 1 FROM core.attribute WHERE attribute_id = ANY(v_ids) AND is_locked
        ) THEN
            denial_code := 'attribute_locked'; RETURN NEXT; RETURN;
        END IF;
        SELECT jsonb_agg(jsonb_build_object('record_id', attribute_id,
            'is_active', is_active, 'is_locked', is_locked) || CASE WHEN p_action = 'describe'
            THEN jsonb_build_object('description_digest', encode(sha256(convert_to(
                jsonb_build_object('value', attribute_description)::TEXT, 'UTF8')), 'hex'))
            ELSE '{}'::JSONB END ORDER BY attribute_id)
          INTO v_before FROM core.attribute WHERE attribute_id = ANY(v_ids);
    END IF;
    -- A lock can expire while waiting for selected rows; recheck before any write.
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, p_expected_principal_type, p_tenant_id, 'tenant_metadata_write');
    IF NOT FOUND OR NOT v_decision.authorized THEN
        denial_code := coalesce(v_decision.denial_code, 'authorization_denied'); RETURN NEXT; RETURN;
    END IF;
    v_now := clock_timestamp();
    v_actor := ('principal:' || v_decision.principal_id::TEXT)::VARCHAR(255);
    IF p_action = 'describe' AND p_record_type = 'object' THEN
        UPDATE core.object AS object SET object_description = item.description,
            updated_time = v_now, updated_by = v_actor
          FROM jsonb_to_recordset(v_records) AS item(record_id BIGINT, description TEXT)
         WHERE object.object_id = item.record_id
           AND object.object_description IS DISTINCT FROM item.description;
        GET DIAGNOSTICS action_count = ROW_COUNT;
    ELSIF p_action = 'describe' THEN
        UPDATE core.attribute AS attribute SET attribute_description = item.description,
            updated_time = v_now, updated_by = v_actor
          FROM jsonb_to_recordset(v_records) AS item(record_id BIGINT, description TEXT)
         WHERE attribute.attribute_id = item.record_id
           AND attribute.attribute_description IS DISTINCT FROM item.description;
        GET DIAGNOSTICS action_count = ROW_COUNT;
    END IF;
    IF p_record_type = 'object' THEN
        UPDATE core.object SET
            is_locked = CASE p_action WHEN 'lock' THEN TRUE WHEN 'unlock' THEN FALSE ELSE is_locked END,
            is_active = CASE p_action WHEN 'reactivate' THEN TRUE WHEN 'deactivate' THEN FALSE ELSE is_active END,
            updated_time = v_now, updated_by = v_actor
         WHERE object_id = ANY(v_ids) AND CASE p_action
            WHEN 'lock' THEN NOT is_locked WHEN 'unlock' THEN is_locked
            WHEN 'deactivate' THEN is_active WHEN 'reactivate' THEN NOT is_active END;
        IF p_action <> 'describe' THEN GET DIAGNOSTICS action_count = ROW_COUNT; END IF;
        SELECT jsonb_agg(jsonb_build_object('record_id', object_id,
            'is_active', is_active, 'is_locked', is_locked,
            'review_revision', application.metadata_object_review_revision(object)) ORDER BY object_id)
          INTO records FROM core.object AS object WHERE object_id = ANY(v_ids);
    ELSE
        UPDATE core.attribute SET
            is_locked = CASE p_action WHEN 'lock' THEN TRUE WHEN 'unlock' THEN FALSE ELSE is_locked END,
            is_active = CASE p_action WHEN 'reactivate' THEN TRUE WHEN 'deactivate' THEN FALSE ELSE is_active END,
            updated_time = v_now, updated_by = v_actor
         WHERE attribute_id = ANY(v_ids) AND CASE p_action
            WHEN 'lock' THEN NOT is_locked WHEN 'unlock' THEN is_locked
            WHEN 'deactivate' THEN is_active WHEN 'reactivate' THEN NOT is_active END;
        IF p_action <> 'describe' THEN GET DIAGNOSTICS action_count = ROW_COUNT; END IF;
        SELECT jsonb_agg(jsonb_build_object('record_id', attribute_id,
            'is_active', attribute.is_active, 'is_locked', attribute.is_locked,
            'review_revision', application.metadata_attribute_review_revision(attribute, object)) ORDER BY attribute_id)
          INTO records FROM core.attribute AS attribute JOIN core.object AS object USING (object_id)
         WHERE attribute_id = ANY(v_ids);
    END IF;
    INSERT INTO application.metadata_review_event AS event (
        tenant_id, actor_principal_id, correlation_id, record_type, action,
        request_digest, action_count, before_records, records
    ) VALUES (
        p_tenant_id, v_decision.principal_id, p_correlation_id, p_record_type, p_action,
        v_request_digest, action_count, v_before, records
    ) RETURNING event.metadata_review_event_id INTO review_event_id;
    RETURN NEXT;
END;
$review_metadata_records$;
REVOKE ALL ON FUNCTION application.review_metadata_records(UUID, UUID, VARCHAR, BIGINT, VARCHAR, VARCHAR, JSONB, UUID) FROM PUBLIC;
