-- Read-only preflight for a new PostgreSQL 18 database.
-- This intentionally fails if the target is not empty for this release.

-- OPTIONAL WHOLE-SERVER CLEANUP REFERENCE. KEEP DISABLED IN SOURCE.
-- Use only as a manual DBA operation after stopping clients, taking the
-- required backup, and confirming that no other database or application uses
-- these schemas or cluster-wide roles. Do not use for installation recovery,
-- migration, or selective schema redeployment. CASCADE can remove dependent
-- objects outside the named schema.
--
-- The schemas are listed in reverse dependency order. They contain every
-- release-created table, function, trigger, index, sequence, constraint, and
-- required seed row. This release creates no object in public and installs no
-- extension, database, tablespace, publication, subscription, or foreign
-- server, so none of those should be dropped here.

--DROP SCHEMA mcp CASCADE;
--DROP SCHEMA application CASCADE;
--DROP SCHEMA workflow CASCADE;
--DROP SCHEMA model CASCADE;
--DROP SCHEMA security CASCADE;
--DROP SCHEMA core CASCADE;
--DROP SCHEMA reference CASCADE;

-- DROP OWNED is database-scoped. Run the applicable commented statement while
-- connected to every database containing a dependency for these roles before
-- attempting the cluster-wide DROP ROLE statements. These five entries cover
-- every role created by this release, including group-role grants omitted from
-- the earlier cleanup reference.

--DROP OWNED BY gds_mcp_runtime CASCADE;
--DROP OWNED BY gds_web_runtime CASCADE;
--DROP OWNED BY gds_app_write CASCADE;
--DROP OWNED BY gds_web_write CASCADE;
--DROP OWNED BY gds_migration CASCADE;

-- Drop login roles before their granted group roles. DROP ROLE removes their
-- membership links and fails if an unresolved dependency remains elsewhere.

--DROP ROLE gds_mcp_runtime;
--DROP ROLE gds_web_runtime;
--DROP ROLE gds_app_write;
--DROP ROLE gds_web_write;
--DROP ROLE gds_migration;

DO $preflight$
DECLARE
    v_existing_schema TEXT;
    v_existing_role TEXT;
    v_can_create_roles BOOLEAN;
BEGIN
    IF current_setting('server_version_num')::INTEGER / 10000 <> 18 THEN
        RAISE EXCEPTION 'PostgreSQL 18 is required';
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
               'reference', 'core', 'security', 'model', 'workflow',
               'application', 'mcp'
           )
     ORDER BY namespace_record.nspname
     LIMIT 1;

    IF v_existing_schema IS NOT NULL THEN
        RAISE EXCEPTION 'release schema already exists: %', v_existing_schema;
    END IF;

    SELECT role_record.rolname
      INTO v_existing_role
     FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname IN (
               'gds_migration', 'gds_app_write', 'gds_web_write',
               'gds_mcp_runtime', 'gds_web_runtime'
           )
     ORDER BY role_record.rolname
     LIMIT 1;

    IF v_existing_role IS NOT NULL THEN
        RAISE EXCEPTION 'release role already exists: %', v_existing_role;
    END IF;
END;
$preflight$;

SELECT 18 AS required_postgres_major,
       current_setting('server_version_num')::INTEGER / 10000
           AS actual_postgres_major,
       'passed' AS preflight_status;
