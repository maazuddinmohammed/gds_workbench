-- GDS ETL Workbench Release 1: audit tables and final privileges.

CREATE TABLE security.artifact_lock_event (
    artifact_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    artifact_type VARCHAR(100) NOT NULL,
    artifact_id BIGINT NOT NULL,
    artifact_is_locked BOOLEAN NOT NULL,
    acted_by_principal_id BIGINT NOT NULL,
    lock_reason VARCHAR(2000) NOT NULL,
    model_revision BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_artifact_lock_event_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_artifact_lock_event_actor FOREIGN KEY (acted_by_principal_id)
        REFERENCES security.principal (principal_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_artifact_lock_event_type CHECK (reference.is_nonblank(artifact_type)),
    CONSTRAINT ck_artifact_lock_event_id CHECK (artifact_id > 0),
    CONSTRAINT ck_artifact_lock_event_reason CHECK (reference.is_nonblank(lock_reason)),
    CONSTRAINT ck_artifact_lock_event_revision CHECK (model_revision > 0)
);

CREATE TABLE security.metadata_artifact_lock_event (
    metadata_artifact_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    artifact_type VARCHAR(30) NOT NULL,
    artifact_id BIGINT NOT NULL,
    artifact_is_locked BOOLEAN NOT NULL,
    acted_by_principal_id BIGINT NOT NULL,
    lock_reason VARCHAR(2000) NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_metadata_lock_event_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_lock_event_actor FOREIGN KEY (
        acted_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT ck_metadata_lock_event_type CHECK (
        artifact_type IN ('object', 'attribute')
    ),
    CONSTRAINT ck_metadata_lock_event_id CHECK (artifact_id > 0),
    CONSTRAINT ck_metadata_lock_event_reason CHECK (
        reference.is_nonblank(lock_reason)
    )
);

-- One immutable row per completed MCP tool call. input_metadata is a bounded,
-- server-created summary; it must never contain raw prompts, rows, output, or secrets.
CREATE TABLE security.mcp_tool_call_log (
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
        AND octet_length(input_metadata::TEXT) <= 16384
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

CREATE FUNCTION security.reject_mcp_tool_call_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $reject_mcp_tool_call_log_mutation$
BEGIN
    RAISE EXCEPTION 'MCP tool call log is append-only' USING ERRCODE = '55000';
END;
$reject_mcp_tool_call_log_mutation$;

CREATE TRIGGER reject_mcp_tool_call_log_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE
ON security.mcp_tool_call_log
FOR EACH STATEMENT
EXECUTE FUNCTION security.reject_mcp_tool_call_log_mutation();

CREATE INDEX ix_artifact_lock_event_model_created
    ON security.artifact_lock_event (model_id, created_time);
CREATE INDEX ix_artifact_lock_event_actor_created
    ON security.artifact_lock_event (
        acted_by_principal_id,
        created_time
    );
CREATE INDEX ix_metadata_lock_event_tenant_created
    ON security.metadata_artifact_lock_event (tenant_id, created_time);
CREATE INDEX ix_metadata_lock_event_actor_created
    ON security.metadata_artifact_lock_event (
        acted_by_principal_id,
        created_time
    );
CREATE INDEX ix_mcp_tool_call_log_time
    ON security.mcp_tool_call_log (tool_call_time DESC);
CREATE INDEX ix_mcp_tool_call_log_principal_time
    ON security.mcp_tool_call_log (principal_id, tool_call_time DESC);
CREATE INDEX ix_mcp_tool_call_log_tool_time
    ON security.mcp_tool_call_log (tool_name, tool_call_time DESC);

-- Least-privilege runtime roles. Deployment owns DDL; these roles cannot create it.
REVOKE ALL ON SCHEMA reference, core, security, model, workflow FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA reference, core, security, model, workflow FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow FROM PUBLIC;

GRANT USAGE ON SCHEMA reference, core, security, model, workflow
    TO gds_app_write;

-- Runtime writes need only the pure validators referenced by CHECK constraints.
GRANT EXECUTE ON FUNCTION
    reference.is_nonblank(TEXT),
    core.is_canonical_text_array(TEXT[])
TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.authorize_tenant_operation(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.acquire_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER,
    VARCHAR
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.override_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER,
    VARCHAR,
    VARCHAR
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.renew_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.release_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.expire_tenant_locks(INTEGER)
TO gds_app_write;

GRANT SELECT ON ALL TABLES IN SCHEMA reference, core, model, workflow
    TO gds_app_write;
REVOKE SELECT ON core.connection_value FROM gds_app_write;
GRANT SELECT ON
    security.principal,
    security.entra_principal_identity,
    security.tenant_principal_access,
    security.artifact_lock_event,
    security.metadata_artifact_lock_event
TO gds_app_write;
GRANT INSERT ON security.mcp_tool_call_log TO gds_app_write;

-- The application mutates only the normalized artifact and workflow state used
-- by PostgresRepository.  Foundational Model/Scope/target rows, audit rows, and
-- every DELETE operation remain deployment-owner capabilities.
GRANT INSERT, UPDATE ON
    model.modeling_evidence_document,
    model.modeling_evidence_record,
    workflow.analysis_result,
    workflow.attribute_mapping,
    workflow.attribute_profile,
    workflow.conceptual_object,
    workflow.conceptual_relationship,
    workflow.conceptual_support,
    workflow.dimensional_attribute,
    workflow.dimensional_attribute_source_mapping,
    workflow.dimensional_entity,
    workflow.dimensional_entity_source_mapping,
    workflow.dimensional_entity_submodel,
    workflow.dimensional_relationship,
    workflow.dimensional_submodel,
    workflow.logical_attribute,
    workflow.logical_attribute_source_mapping,
    workflow.logical_entity,
    workflow.logical_entity_source_mapping,
    workflow.logical_entity_submodel,
    workflow.logical_relationship,
    workflow.logical_submodel,
    workflow.mapping_source_system_dependency,
    workflow.metadata_change_set,
    workflow.model_change_set,
    workflow.object_mapping,
    workflow.profiling_run
TO gds_app_write;
GRANT INSERT ON
    workflow.metadata_change_set_event,
    workflow.metadata_apply_receipt,
    workflow.metadata_apply_receipt_ref,
    workflow.model_change_set_event,
    workflow.idempotency_outcome,
    workflow.profiling_final_receipt,
    workflow.model_apply_receipt,
    workflow.model_apply_receipt_ref
TO gds_app_write;

-- Identity sequences are granted only when owned by an INSERT-allowlisted
-- table.  This excludes foundational and authoritative audit sequences while
-- avoiding reliance on PostgreSQL's truncated generated sequence names.
DO $grant_runtime_sequences$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT DISTINCT sequence_namespace.nspname AS schema_name,
                        sequence_relation.relname AS sequence_name
          FROM pg_depend AS dependency
          JOIN pg_class AS sequence_relation
            ON sequence_relation.oid = dependency.objid
           AND sequence_relation.relkind = 'S'
          JOIN pg_namespace AS sequence_namespace
            ON sequence_namespace.oid = sequence_relation.relnamespace
          JOIN pg_class AS table_relation
            ON table_relation.oid = dependency.refobjid
           AND table_relation.relkind IN ('r', 'p')
          JOIN pg_namespace AS table_namespace
            ON table_namespace.oid = table_relation.relnamespace
         WHERE dependency.classid = 'pg_class'::REGCLASS
           AND dependency.refclassid = 'pg_class'::REGCLASS
           AND dependency.deptype IN ('a', 'i')
           AND table_namespace.nspname IN ('model', 'workflow')
           AND has_table_privilege(
                'gds_app_write',
                table_relation.oid,
                'INSERT'
           )
    LOOP
        EXECUTE format(
            'GRANT USAGE, SELECT ON SEQUENCE %I.%I TO gds_app_write',
            target.schema_name,
            target.sequence_name
        );
    END LOOP;
END;
$grant_runtime_sequences$;

GRANT USAGE, CREATE ON SCHEMA reference, core, security, model, workflow TO gds_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reference, core, security, model, workflow
    TO gds_migration;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA reference, core, security, model, workflow
    TO gds_migration;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow
    TO gds_migration;
