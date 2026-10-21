-- Run the entire script in a fresh session against the intended database.
-- Catalog reads only; no application calls, definitions, identities or Run data.
-- Checks direct owner privileges for the two usage-startup functions only.
-- TRUE is not proof of full runtime compatibility or nested authorization success.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';

WITH required_functions(function_name, signature) AS (
    VALUES
        ('begin_usage', 'application.begin_workflow_run_usage('
         'uuid,uuid,character varying,bigint,bigint,uuid)'),
        ('usage_binding', 'application.assert_workflow_run_usage_binding('
         'uuid,uuid,character varying,bigint,bigint,uuid)')
),
installed AS (
    SELECT required.function_name, proc.oid, proc.proowner, proc.prosecdef
      FROM required_functions AS required
      LEFT JOIN pg_catalog.pg_proc AS proc
        ON proc.oid = pg_catalog.to_regprocedure(required.signature)
),
checks(function_name, check_name, passed) AS (
    SELECT function_name, 'function_exists', oid IS NOT NULL FROM installed
    UNION ALL
    SELECT function_name, 'security_definer', prosecdef FROM installed
    UNION ALL
    SELECT function_name, 'schema_usage', NOT EXISTS (
        SELECT 1 FROM unnest(CASE WHEN function_name = 'begin_usage'
            THEN ARRAY['application'] ELSE ARRAY['application','project','security'] END) AS schema_name
         WHERE NOT coalesce(pg_catalog.has_schema_privilege(
             installed.proowner, pg_catalog.to_regnamespace(schema_name), 'USAGE'
         ), FALSE)
    ) FROM installed
    UNION ALL
    SELECT function_name, 'nested_execute', NOT EXISTS (
        SELECT 1 FROM unnest(CASE WHEN function_name = 'begin_usage'
            THEN ARRAY['application.assert_workflow_run_usage_binding('
                       'uuid,uuid,character varying,bigint,bigint,uuid)']
            ELSE ARRAY['application.assert_workflow_run_claim(bigint,uuid)',
                       'security.authorize_tenant_operation('
                       'uuid,uuid,character varying,bigint,character varying)'] END) AS signature
         WHERE NOT coalesce(pg_catalog.has_function_privilege(
             installed.proowner, pg_catalog.to_regprocedure(signature), 'EXECUTE'
         ), FALSE)
    ) FROM installed
    UNION ALL
    SELECT function_name, 'run_select', (
        SELECT count(*) > 0 AND bool_and(pg_catalog.has_column_privilege(
            installed.proowner, attribute.attrelid, attribute.attnum, 'SELECT'
        )) FROM pg_catalog.pg_attribute AS attribute
         WHERE attribute.attrelid = pg_catalog.to_regclass('application.workflow_run')
           AND attribute.attnum > 0 AND NOT attribute.attisdropped
           AND (installed.function_name = 'usage_binding' OR attribute.attname = 'workflow_run_id')
    ) FROM installed
    UNION ALL
    SELECT function_name, 'usage_update', (
        SELECT count(*) = 3 AND bool_and(pg_catalog.has_column_privilege(
            installed.proowner, attribute.attrelid, attribute.attnum, 'UPDATE'
        )) FROM pg_catalog.pg_attribute AS attribute
         WHERE attribute.attrelid = pg_catalog.to_regclass('application.workflow_run')
           AND attribute.attnum > 0 AND NOT attribute.attisdropped
           AND attribute.attname IN ('usage_tracking_version',
               'usage_tracked_recovery_count', 'usage_history_incomplete')
    ) FROM installed WHERE function_name = 'begin_usage'
    UNION ALL
    SELECT function_name, 'project_select', (
        SELECT count(*) = 4 AND bool_and(pg_catalog.has_column_privilege(
            installed.proowner, attribute.attrelid, attribute.attnum, 'SELECT'
        )) FROM pg_catalog.pg_attribute AS attribute
         WHERE attribute.attrelid = pg_catalog.to_regclass('project.project')
           AND attribute.attnum > 0 AND NOT attribute.attisdropped
           AND attribute.attname IN ('project_id', 'tenant_id', 'is_active', 'project_revision')
    ) FROM installed WHERE function_name = 'usage_binding'
    UNION ALL
    -- FOR SHARE, like FOR UPDATE, requires UPDATE on at least one column.
    SELECT function_name, 'project_row_lock', pg_catalog.has_any_column_privilege(
        proowner, pg_catalog.to_regclass('project.project'), 'UPDATE'
    ) FROM installed WHERE function_name = 'usage_binding'
)
SELECT function_name, bool_and(coalesce(passed, FALSE)) AS access_ok,
       coalesce(array_agg(check_name ORDER BY check_name)
           FILTER (WHERE NOT coalesce(passed, FALSE)), ARRAY[]::TEXT[]) AS failed_checks
  FROM checks
 GROUP BY function_name
 ORDER BY function_name;

ROLLBACK;
