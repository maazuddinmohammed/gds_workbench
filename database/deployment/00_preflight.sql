-- Read-only preflight for a new PostgreSQL 16 database.
-- This intentionally fails if the target is not empty for this release.

DO $preflight$
DECLARE
    v_existing_schema TEXT;
    v_existing_role TEXT;
    v_can_create_roles BOOLEAN;
BEGIN
    IF current_setting('server_version_num')::INTEGER / 10000 <> 16 THEN
        RAISE EXCEPTION 'PostgreSQL 16 is required';
    END IF;

    SELECT role_record.rolsuper OR role_record.rolcreaterole
      INTO v_can_create_roles
      FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname = CURRENT_USER;

    IF v_can_create_roles IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'installer must be able to create roles';
    END IF;

    SELECT namespace_record.nspname
      INTO v_existing_schema
      FROM pg_catalog.pg_namespace AS namespace_record
     WHERE namespace_record.nspname IN (
               'reference', 'core', 'security', 'model', 'workflow', 'mcp'
           )
     ORDER BY namespace_record.nspname
     LIMIT 1;

    IF v_existing_schema IS NOT NULL THEN
        RAISE EXCEPTION 'release schema already exists: %', v_existing_schema;
    END IF;

    SELECT role_record.rolname
      INTO v_existing_role
      FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname IN ('gds_migration', 'gds_app_write')
     ORDER BY role_record.rolname
     LIMIT 1;

    IF v_existing_role IS NOT NULL THEN
        RAISE EXCEPTION 'release role already exists: %', v_existing_role;
    END IF;
END;
$preflight$;

SELECT 16 AS required_postgres_major,
       current_setting('server_version_num')::INTEGER / 10000
           AS actual_postgres_major,
       'passed' AS preflight_status;
