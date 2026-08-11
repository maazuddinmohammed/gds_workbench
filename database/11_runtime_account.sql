-- GDS ETL Workbench Release 1: group roles and least-privilege MCP runtime login.
-- Set its password afterward with psql: \password gds_mcp_runtime

--CREATE ROLE gds_migration NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

--CREATE ROLE gds_app_write NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE ROLE gds_mcp_runtime
    LOGIN
    NOINHERIT
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT gds_app_write TO gds_mcp_runtime;

DO $grant_runtime_database_connect$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO gds_mcp_runtime',
        current_database()
    );
END;
$grant_runtime_database_connect$;
