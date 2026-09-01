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

-- Notebook control code authenticates directly as this login and receives only
-- governed notebook wrappers. In-process workflow execution must explicitly
-- activate gds_web_write for each transaction.
CREATE ROLE gds_notebook_runtime
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

GRANT gds_web_write TO gds_notebook_runtime
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
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO gds_notebook_runtime',
        current_database()
    );
END;
$grant_runtime_database_connect$;
