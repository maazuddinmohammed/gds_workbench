-- GDS ETL Workbench Release 1: append-only MCP Tool Call Log.

-- One immutable row per completed MCP tool call. input_metadata is server-created.
-- PostgreSQL imposes no application-specific byte ceiling on the JSON object.
CREATE TABLE mcp.tool_call_log (
    tool_call_id UUID PRIMARY KEY,
    principal_id BIGINT,
    principal_display_name VARCHAR(200) NOT NULL,
    actor_kind VARCHAR(20) NOT NULL,
    tool_name VARCHAR(200) NOT NULL,
    tool_policy VARCHAR(50) NOT NULL,
    tenant_id BIGINT,
    input_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    tool_call_status VARCHAR(20) NOT NULL,
    failure_code VARCHAR(100),
    tool_call_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mcp_tool_call_principal FOREIGN KEY (principal_id)
        REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mcp_tool_call_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT ck_mcp_tool_call_principal CHECK (
        (
            actor_kind = 'development'
            AND principal_id IS NULL
        )
        OR
        (
            actor_kind IN ('human', 'workload')
            AND principal_id IS NOT NULL
        )
    ),
    CONSTRAINT ck_mcp_tool_call_display_name CHECK (
        reference.is_nonblank(principal_display_name)
    ),
    CONSTRAINT ck_mcp_tool_call_name CHECK (
        reference.is_nonblank(tool_name)
    ),
    CONSTRAINT ck_mcp_tool_call_policy CHECK (
        tool_policy IN (
            'tenant_read',
            'tenant_metadata_write',
            'tenant_model_write',
            'tenant_lock_manage',
            'super_admin_only'
        )
    ),
    CONSTRAINT ck_mcp_tool_call_input_metadata CHECK (
        jsonb_typeof(input_metadata) = 'object'
    ),
    CONSTRAINT ck_mcp_tool_call_status CHECK (
        tool_call_status IN ('succeeded', 'failed')
    ),
    CONSTRAINT ck_mcp_tool_call_failure CHECK (
        (
            tool_call_status = 'succeeded'
            AND failure_code IS NULL
        )
        OR
        (
            tool_call_status = 'failed'
            AND reference.is_nonblank(failure_code)
        )
    )
);

CREATE FUNCTION mcp.reject_tool_call_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $reject_tool_call_log_mutation$
BEGIN
    RAISE EXCEPTION 'MCP tool call log is append-only' USING ERRCODE = '55000';
END;
$reject_tool_call_log_mutation$;

CREATE TRIGGER reject_tool_call_log_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE
ON mcp.tool_call_log
FOR EACH STATEMENT
EXECUTE FUNCTION mcp.reject_tool_call_log_mutation();

CREATE INDEX ix_tool_call_log_time
    ON mcp.tool_call_log (tool_call_time DESC);
CREATE INDEX ix_tool_call_log_principal_time
    ON mcp.tool_call_log (principal_id, tool_call_time DESC);
CREATE INDEX ix_tool_call_log_tool_time
    ON mcp.tool_call_log (tool_name, tool_call_time DESC);
