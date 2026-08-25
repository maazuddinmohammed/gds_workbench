-- GDS ETL Workbench Release 1: group roles and least-privilege runtime logins.
-- Set passwords afterward with psql for each runtime login.

CREATE ROLE gds_migration NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE ROLE gds_app_write NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE ROLE gds_web_write NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE ROLE gds_mcp_runtime
    LOGIN
    NOINHERIT
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE gds_web_runtime
    LOGIN
    NOINHERIT
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT gds_app_write TO gds_mcp_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

GRANT gds_web_write TO gds_web_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

DO $grant_runtime_database_connect$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO gds_mcp_runtime',
        current_database()
    );
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO gds_web_runtime',
        current_database()
    );
END;
$grant_runtime_database_connect$;
