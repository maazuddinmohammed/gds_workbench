-- Fail-fast verification after database/01_reference.sql through
-- database/12_runtime_integrity.sql have completed.

DO $verify_install$
DECLARE
    v_schema_count INTEGER;
    v_group_role_count INTEGER;
    v_membership_count INTEGER;
    v_security_definer_count INTEGER;
    v_metadata_change_set_function_count INTEGER;
    v_databricks_function_count INTEGER;
BEGIN
    IF current_setting('server_version_num')::INTEGER / 10000 <> 18 THEN
        RAISE EXCEPTION 'PostgreSQL 18 is required';
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
      INTO v_group_role_count
      FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname IN ('gds_migration', 'gds_app_write')
       AND NOT role_record.rolcanlogin
       AND NOT role_record.rolsuper
       AND NOT role_record.rolinherit
       AND NOT role_record.rolcreatedb
       AND NOT role_record.rolcreaterole
       AND NOT role_record.rolreplication
       AND NOT role_record.rolbypassrls;

    IF v_group_role_count <> 2 THEN
        RAISE EXCEPTION 'release group-role posture is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles AS role_record
         WHERE role_record.rolname = 'gds_mcp_runtime'
           AND role_record.rolcanlogin
           AND NOT role_record.rolsuper
           AND NOT role_record.rolinherit
           AND NOT role_record.rolcreatedb
           AND NOT role_record.rolcreaterole
           AND NOT role_record.rolreplication
           AND NOT role_record.rolbypassrls
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_membership_count
      FROM pg_catalog.pg_auth_members AS membership
      JOIN pg_catalog.pg_roles AS member_role
        ON member_role.oid = membership.member
     WHERE member_role.rolname = 'gds_mcp_runtime';

    IF v_membership_count <> 1 OR NOT pg_has_role(
        'gds_mcp_runtime',
        'gds_app_write',
        'MEMBER'
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime must have exactly one direct membership';
    END IF;

    IF NOT has_database_privilege(
        'gds_mcp_runtime',
        current_database(),
        'CONNECT'
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime cannot connect to this database';
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

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'object'
           AND column_record.column_name = 'is_locked'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'attribute'
           AND column_record.column_name = 'is_locked'
    ) THEN
        RAISE EXCEPTION 'Object lock source is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'tenant_metadata_discovery_scope'
           AND column_record.column_name = 'gds_connection_id'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'tenant_metadata_discovery_scope'
           AND column_record.column_name = 'connection_id'
    ) THEN
        RAISE EXCEPTION 'Metadata Discovery Scope Connection identifier is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS function_record
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = function_record.pronamespace
         WHERE namespace_record.nspname = 'mcp'
           AND function_record.proname = 'runtime_readiness'
           AND function_record.pronargs = 0
           AND NOT function_record.prosecdef
           AND EXISTS (
                   SELECT 1
                     FROM unnest(function_record.proconfig) AS setting(value)
                    WHERE setting.value = 'search_path=pg_catalog'
               )
    ) THEN
        RAISE EXCEPTION 'runtime readiness function posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_security_definer_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'security'
       AND function_record.proname IN (
               'authorize_tenant_operation',
               'check_tenant_lock',
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

    IF v_security_definer_count <> 7 THEN
        RAISE EXCEPTION 'security function posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_metadata_change_set_function_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'mcp'
       AND function_record.proname IN (
               'create_metadata_change_set',
               'stage_metadata_change_set',
               'get_metadata_change_set',
               'record_metadata_change_set_validation',
               'apply_metadata_change_set',
               'archive_metadata_change_set'
           )
       AND function_record.prosecdef
       AND EXISTS (
               SELECT 1
                 FROM unnest(function_record.proconfig) AS setting(value)
                WHERE setting.value LIKE 'search_path=pg_catalog%'
           );

    IF v_metadata_change_set_function_count <> 6 THEN
        RAISE EXCEPTION 'Metadata Change Set function posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_databricks_function_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'mcp'
       AND function_record.proname = 'get_databricks_sql_connection_values'
       AND function_record.prosecdef
       AND EXISTS (
               SELECT 1
                 FROM unnest(function_record.proconfig) AS setting(value)
                WHERE setting.value LIKE 'search_path=pg_catalog%'
           );

    IF v_databricks_function_count <> 1 THEN
        RAISE EXCEPTION 'Databricks connection function posture is invalid';
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
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'DELETE')
       OR has_table_privilege('gds_app_write', 'mcp.metadata_change_set', 'SELECT')
       OR has_table_privilege(
           'gds_app_write', 'mcp.metadata_change_set', 'INSERT,UPDATE,DELETE'
       )
       OR has_table_privilege(
           'gds_app_write', 'mcp.metadata_change_set_event', 'INSERT'
       ) THEN
        RAISE EXCEPTION 'runtime table privileges are invalid';
    END IF;

    IF NOT has_function_privilege(
        'gds_app_write',
        'security.authorize_tenant_operation(uuid,uuid,character varying,bigint,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.check_tenant_lock(uuid,uuid,character varying,bigint)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.acquire_tenant_lock(uuid,uuid,character varying,bigint,integer,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.renew_tenant_lock(uuid,uuid,character varying,bigint,integer)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.release_tenant_lock(uuid,uuid,character varying,bigint)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.override_tenant_lock(uuid,uuid,character varying,bigint,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.expire_tenant_locks(integer)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.create_metadata_change_set(uuid,uuid,character varying,bigint,uuid,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.get_databricks_sql_connection_values(bigint)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.runtime_readiness()',
        'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'runtime function privileges are invalid';
    END IF;
END;
$verify_install$;

SELECT '1.0.0' AS schema_version,
       'gds_mcp_runtime' AS runtime_login,
       'gds_app_write' AS activated_role,
       'passed' AS verification_status;
