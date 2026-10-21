-- Run this entire script in a fresh SQL session against the intended database.
-- Catalog reads only: no application functions, project data, DDL or data writes.
-- PASS covers workflow lock fixes and selected Profiling/usage contracts, not full app readiness.
-- Output contains one summary row and only failed checks; no function bodies.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';

WITH required_functions(signature, required_source, web_execute, expected_return) AS (
    VALUES
        ('application.claim_next_workflow_run(integer)',
         ARRAY['%application.claim_workflow_run(p_lease_duration_seconds, ''web'')%'],
         TRUE, NULL::TEXT),
        ('application.claim_workflow_run(integer,character varying)',
         ARRAY['%ready AS MATERIALIZED%clock_timestamp() AS claimed_time%',
               '%workflow_run_revision_stale%', '%workflow_run_authorization_unavailable%'],
         FALSE, NULL),
        ('application.renew_workflow_run_claim(bigint,uuid,integer)',
         ARRAY['%FOR NO KEY UPDATE OF run;%PERFORM project.assert_writable(v_project_id);%'
               'v_heartbeat_time := clock_timestamp();%'
               'workflow_run_claim_expires_time > v_heartbeat_time%'], TRUE, NULL),
        ('application.release_workflow_run_claim(bigint,uuid)',
         ARRAY['%FOR NO KEY UPDATE OF run;%PERFORM project.assert_writable(v_project_id);%'
               'v_released_time := clock_timestamp();%'
               'workflow_run_claim_expires_time > v_released_time%'], TRUE, NULL),
        ('application.assert_workflow_run_claim(bigint,uuid)',
         ARRAY['%FOR UPDATE OF run;%v_expires_time <= clock_timestamp()%'], TRUE, NULL),
        ('application.fail_workflow_run(uuid,uuid,character varying,bigint,bigint,'
         'character varying,character varying)',
         ARRAY['%Workflow Run has a durable authoring outcome%'], TRUE, NULL),
        ('application.get_profiling_execution_context('
         'uuid,uuid,character varying,bigint,bigint)',
         ARRAY['%FOR KEY SHARE OF run FOR SHARE OF target_project%'], TRUE, NULL),
        ('application.get_profiling_connection_values('
         'uuid,uuid,character varying,bigint,bigint,character varying)',
         ARRAY[]::TEXT[], TRUE, 'record'),
        ('application.append_workflow_run_event('
         'uuid,uuid,character varying,bigint,bigint,bigint,integer,'
         'character varying,character varying,character varying,integer,integer,integer)',
         ARRAY[]::TEXT[], TRUE, 'project.project_event_log'),
        ('application.persist_profiling_results('
         'uuid,uuid,character varying,bigint,bigint,jsonb)',
         ARRAY[]::TEXT[], TRUE, 'record'),
        ('application.complete_workflow_run('
         'uuid,uuid,character varying,bigint,bigint,integer)',
         ARRAY[]::TEXT[], TRUE, 'record'),
        ('application.get_analysis_validation_execution_context('
         'uuid,uuid,character varying,bigint,bigint,character varying)',
         ARRAY['%FOR KEY SHARE OF run FOR SHARE OF target_project%'], TRUE, NULL),
        ('application.get_metadata_enrichment_execution_context('
         'uuid,uuid,character varying,bigint,bigint)',
         ARRAY['%FOR KEY SHARE OF run FOR SHARE OF target_project%'], TRUE, NULL),
        ('application.begin_workflow_run_usage('
         'uuid,uuid,character varying,bigint,bigint,uuid)',
         ARRAY[]::TEXT[], TRUE, 'character varying'),
        ('application.begin_workflow_run_model_request('
         'uuid,uuid,character varying,bigint,bigint,uuid,uuid,uuid,'
         'character varying,integer,integer,jsonb)',
         ARRAY[]::TEXT[], TRUE, 'uuid'),
        ('application.complete_workflow_run_model_request('
         'uuid,uuid,character varying,bigint,bigint,uuid,uuid,'
         'bigint,bigint,bigint,bigint,bigint,bigint,boolean)',
         ARRAY[]::TEXT[], TRUE, 'void')
),
required_columns(table_name, column_name, expected_type) AS (
    VALUES
        ('workflow_run', 'usage_tracking_version', 'smallint'),
        ('workflow_run', 'usage_tracked_recovery_count', 'integer'),
        ('workflow_run', 'usage_history_incomplete', 'boolean'),
        ('workflow_run_model_request', 'pricing_basis', 'character varying(80)'),
        ('workflow_run_model_request', 'pricing_valid_from', 'timestamp with time zone'),
        ('workflow_run_model_request', 'pricing_valid_until', 'timestamp with time zone'),
        ('workflow_run_model_request', 'pricing_max_input_tokens', 'bigint'),
        ('workflow_run_model_request', 'pricing_input_usd_per_million', 'numeric(15,8)'),
        ('workflow_run_model_request', 'pricing_cached_input_usd_per_million', 'numeric(15,8)'),
        ('workflow_run_model_request', 'pricing_cache_write_input_usd_per_million', 'numeric(15,8)'),
        ('workflow_run_model_request', 'pricing_output_usd_per_million', 'numeric(15,8)')
),
installed AS (
    SELECT required.*,
           proc.oid AS function_oid,
           proc.prosecdef,
           proc.provolatile,
           proc.proconfig,
           proc.prosrc,
           proc.prorettype,
           runtime_role.oid AS role_oid
      FROM required_functions AS required
      LEFT JOIN pg_catalog.pg_proc AS proc
        ON proc.oid = pg_catalog.to_regprocedure(required.signature)
      LEFT JOIN pg_catalog.pg_roles AS runtime_role
        ON runtime_role.rolname = 'gds_web_write'
),
checks(check_name, passed) AS (
    SELECT 'postgresql_18',
           current_setting('server_version_num')::INTEGER / 10000 = 18
    UNION ALL
    SELECT 'read_only_transaction', current_setting('transaction_read_only') = 'on'
    UNION ALL
    SELECT 'gds_web_write_role_exists',
           EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'gds_web_write')
    UNION ALL
    SELECT signature || ': function_exists', function_oid IS NOT NULL
      FROM installed
    UNION ALL
    SELECT signature || ': security_definer_and_safe_search_path',
           coalesce(prosecdef AND provolatile = 'v'
                    AND proconfig = ARRAY['search_path=pg_catalog']::TEXT[], FALSE)
      FROM installed
    UNION ALL
    SELECT signature || ': required_workflow_fixes',
           function_oid IS NOT NULL
           AND coalesce(regexp_replace(prosrc, '[[:space:]]+', ' ', 'g')
                        LIKE ALL (required_source), FALSE)
      FROM installed
     WHERE cardinality(required_source) > 0
    UNION ALL
    SELECT signature || CASE WHEN web_execute THEN ': web_execute_required'
                             ELSE ': internal_function_must_not_be_callable' END,
           role_oid IS NOT NULL AND function_oid IS NOT NULL
           AND coalesce(pg_catalog.has_function_privilege(
                            role_oid, function_oid, 'EXECUTE'
                        ) = web_execute, FALSE)
      FROM installed
    UNION ALL
    SELECT signature || ': return_type',
           coalesce(prorettype = pg_catalog.to_regtype(expected_return), FALSE)
      FROM installed
     WHERE expected_return IS NOT NULL
    UNION ALL
    SELECT 'application.' || required.table_name || '.' || required.column_name
           || ': expected_column_type',
           coalesce(pg_catalog.format_type(attribute.atttypid, attribute.atttypmod)
                    = required.expected_type, FALSE)
      FROM required_columns AS required
      LEFT JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid = pg_catalog.to_regclass('application.' || required.table_name)
       AND attribute.attname = required.column_name
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped
)
SELECT 'workflow_sql_checks' AS check_name,
       CASE WHEN bool_and(passed) THEN 'PASS' ELSE 'FAIL' END AS status
  FROM checks
UNION ALL
SELECT check_name, 'FAIL' AS status
  FROM checks
 WHERE NOT passed
ORDER BY check_name;

ROLLBACK;
