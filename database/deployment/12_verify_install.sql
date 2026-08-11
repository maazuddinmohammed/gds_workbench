-- Fail-fast verification after database/01_reference.sql through
-- database/11_runtime_integrity.sql have completed.

DO $verify_install$
DECLARE
    v_schema_count INTEGER;
    v_role_count INTEGER;
    v_security_definer_count INTEGER;
BEGIN
    IF current_setting('server_version_num')::INTEGER / 10000 <> 16 THEN
        RAISE EXCEPTION 'PostgreSQL 16 is required';
    END IF;

    SELECT count(*)
      INTO v_schema_count
      FROM pg_catalog.pg_namespace AS namespace_record
     WHERE namespace_record.nspname IN (
               'reference', 'core', 'security', 'model', 'workflow', 'mcp'
           );

    IF v_schema_count <> 6 THEN
        RAISE EXCEPTION 'one or more release schemas are missing';
    END IF;

    SELECT count(*)
      INTO v_role_count
      FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname IN ('gds_migration', 'gds_app_write')
       AND NOT role_record.rolcanlogin
       AND NOT role_record.rolsuper
       AND NOT role_record.rolinherit
       AND NOT role_record.rolcreatedb
       AND NOT role_record.rolcreaterole
       AND NOT role_record.rolreplication
       AND NOT role_record.rolbypassrls;

    IF v_role_count <> 2 THEN
        RAISE EXCEPTION 'release group-role posture is invalid';
    END IF;

    IF to_regclass('core.tenant_metadata_discovery_scope') IS NULL
       OR to_regclass('workflow.mapping_object') IS NULL
       OR to_regclass('workflow.mapping_attribute') IS NULL
       OR to_regclass('mcp.tool_call_log') IS NULL THEN
        RAISE EXCEPTION 'required release tables are missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'workflow'
           AND column_record.table_name = 'mapping_attribute'
           AND column_record.column_name = 'mapping_object_id'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'workflow'
           AND column_record.table_name = 'mapping_attribute'
           AND column_record.column_name = 'object_mapping_id'
    ) THEN
        RAISE EXCEPTION 'workflow.mapping_attribute identifier is invalid';
    END IF;

    SELECT count(*)
      INTO v_security_definer_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'security'
       AND function_record.proname IN (
               'authorize_tenant_operation',
               'acquire_tenant_lock',
               'override_tenant_lock',
               'renew_tenant_lock',
               'release_tenant_lock',
               'expire_tenant_locks'
           )
       AND function_record.prosecdef
       AND EXISTS (
               SELECT 1
                 FROM unnest(function_record.proconfig) AS setting(value)
                WHERE setting.value LIKE 'search_path=pg_catalog%'
           );

    IF v_security_definer_count <> 6 THEN
        RAISE EXCEPTION 'security function posture is invalid';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference', 'core', 'security', 'model', 'workflow', 'mcp'
               ]) AS schema_name(value)
         WHERE has_schema_privilege('public', schema_name.value, 'USAGE')
    ) THEN
        RAISE EXCEPTION 'PUBLIC retains release-schema usage';
    END IF;

    IF NOT has_table_privilege('gds_app_write', 'core.project', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'core.tenant', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'core.object', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'core.attribute', 'SELECT')
       OR NOT has_table_privilege(
           'gds_app_write',
           'core.tenant_metadata_discovery_scope',
           'SELECT'
       )
       OR has_table_privilege('gds_app_write', 'core.connection_value', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'INSERT')
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'SELECT')
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'UPDATE')
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'DELETE') THEN
        RAISE EXCEPTION 'runtime table privileges are invalid';
    END IF;

    IF NOT has_function_privilege(
        'gds_app_write',
        'security.authorize_tenant_operation(uuid,uuid,character varying,bigint,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.expire_tenant_locks(integer)',
        'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'runtime function privileges are invalid';
    END IF;
END;
$verify_install$;

SELECT '1.0.0' AS schema_version,
       'passed' AS verification_status;
