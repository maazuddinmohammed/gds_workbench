-- GDS ETL Workbench Release 1: MCP-owned persistence.

CREATE SCHEMA mcp;

CREATE TABLE mcp.model_change_set (
    model_change_set_id UUID PRIMARY KEY,
    model_id BIGINT NOT NULL,
    model_change_set_status VARCHAR(20) NOT NULL DEFAULT 'active',
    base_model_revision BIGINT NOT NULL,
    base_source_context_digest CHAR(64) NOT NULL,
    base_assertion_digest CHAR(64) NOT NULL,
    base_policy_digest CHAR(64) NOT NULL,
    draft_revision BIGINT NOT NULL DEFAULT 1,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    model_scope_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    profiling_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    assertion_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    analysis_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    conceptual_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    logical_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    dimensional_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    mapping_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by_principal_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '4 hours'),
    validated_time TIMESTAMPTZ,
    applied_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_change_set_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_change_set_creator FOREIGN KEY (created_by_principal_id)
        REFERENCES security.principal (principal_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_change_set_id_model UNIQUE (model_change_set_id, model_id),
    CONSTRAINT ck_change_set_status CHECK (
        model_change_set_status IN (
            'active', 'validated', 'applied', 'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_change_set_revisions CHECK (
        base_model_revision > 0 AND draft_revision >= 1
    ),
    CONSTRAINT ck_change_set_digests CHECK (
        base_source_context_digest ~ '^[0-9a-f]{64}$'
        AND base_assertion_digest ~ '^[0-9a-f]{64}$'
        AND base_policy_digest ~ '^[0-9a-f]{64}$'
        AND (candidate_digest IS NULL OR candidate_digest ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT ck_change_set_validation_outcome CHECK (
        validation_outcome IS NULL OR jsonb_typeof(validation_outcome) = 'object'
    ),
    CONSTRAINT ck_change_set_documents CHECK (
        jsonb_typeof(model_scope_document) = 'object'
        AND jsonb_typeof(profiling_document) = 'object'
        AND jsonb_typeof(assertion_document) = 'object'
        AND jsonb_typeof(analysis_document) = 'object'
        AND jsonb_typeof(conceptual_document) = 'object'
        AND jsonb_typeof(logical_document) = 'object'
        AND jsonb_typeof(dimensional_document) = 'object'
        AND jsonb_typeof(mapping_document) = 'object'
        AND octet_length(model_scope_document::TEXT) <= 16777216
        AND octet_length(profiling_document::TEXT) <= 16777216
        AND octet_length(assertion_document::TEXT) <= 16777216
        AND octet_length(analysis_document::TEXT) <= 16777216
        AND octet_length(conceptual_document::TEXT) <= 16777216
        AND octet_length(logical_document::TEXT) <= 16777216
        AND octet_length(dimensional_document::TEXT) <= 16777216
        AND octet_length(mapping_document::TEXT) <= 16777216
    ),
    CONSTRAINT ck_change_set_expiry CHECK (
        last_activity_time >= created_time
        AND expires_time > last_activity_time
    ),
    CONSTRAINT ck_change_set_candidate_state CHECK (
        (model_change_set_status = 'active' AND candidate_digest IS NULL)
        OR (
            model_change_set_status IN ('validated', 'applied')
            AND candidate_digest IS NOT NULL
        ) OR model_change_set_status IN ('expired', 'discarded', 'superseded')
    ),
    CONSTRAINT ck_change_set_terminal_time CHECK (
        (model_change_set_status IN ('applied', 'expired', 'discarded', 'superseded'))
        = (terminal_time IS NOT NULL)
    )
);

CREATE TABLE mcp.model_change_set_event (
    model_change_set_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_change_set_id UUID NOT NULL,
    model_id BIGINT NOT NULL,
    event_sequence BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    draft_revision BIGINT NOT NULL,
    section_name VARCHAR(20),
    action_count INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(30) NOT NULL,
    validation_report_id UUID,
    event_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_change_set_event_parent FOREIGN KEY (
        model_change_set_id,
        model_id
    ) REFERENCES mcp.model_change_set (model_change_set_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_change_set_event_sequence
        UNIQUE (model_change_set_id, event_sequence),
    CONSTRAINT ck_change_set_event_sequence CHECK (event_sequence > 0),
    CONSTRAINT ck_change_set_event_type CHECK (
        event_type IN (
            'created', 'section_put', 'validated', 'validation_failed',
            'applied', 'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_change_set_event_revision CHECK (draft_revision >= 1),
    CONSTRAINT ck_change_set_event_section CHECK (
        section_name IS NULL
        OR section_name IN (
            'model_scope', 'profiling', 'assertion', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping'
        )
    ),
    CONSTRAINT ck_change_set_event_action_count CHECK (action_count >= 0),
    CONSTRAINT ck_change_set_event_outcome CHECK (reference.is_nonblank(outcome)),
    CONSTRAINT ck_change_set_event_metadata CHECK (
        jsonb_typeof(event_metadata) = 'object'
        AND octet_length(event_metadata::TEXT) <= 65536
    )
);

CREATE TABLE mcp.metadata_change_set (
    metadata_change_set_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    metadata_change_set_status VARCHAR(20) NOT NULL DEFAULT 'active',
    base_metadata_digest CHAR(64) NOT NULL,
    draft_revision BIGINT NOT NULL DEFAULT 1,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    source_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    source_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    bronze_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    bronze_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    silver_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    silver_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    gold_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    gold_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    copy_group_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    copy_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    process_group_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    process_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by_principal_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (
        CURRENT_TIMESTAMP + INTERVAL '4 hours'
    ),
    validated_time TIMESTAMPTZ,
    applied_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_metadata_change_set_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_change_set_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_change_set_id_tenant
        UNIQUE (metadata_change_set_id, tenant_id),
    CONSTRAINT ck_metadata_change_set_status CHECK (
        metadata_change_set_status IN (
            'active', 'validated', 'applied',
            'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_revision CHECK (draft_revision >= 1),
    CONSTRAINT ck_metadata_change_set_digests CHECK (
        base_metadata_digest ~ '^[0-9a-f]{64}$'
        AND (candidate_digest IS NULL OR candidate_digest ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT ck_metadata_change_set_validation_outcome CHECK (
        validation_outcome IS NULL
        OR jsonb_typeof(validation_outcome) = 'object'
    ),
    CONSTRAINT ck_metadata_change_set_documents CHECK (
        jsonb_typeof(source_object_document) = 'object'
        AND jsonb_typeof(source_attribute_document) = 'object'
        AND jsonb_typeof(bronze_object_document) = 'object'
        AND jsonb_typeof(bronze_attribute_document) = 'object'
        AND jsonb_typeof(silver_object_document) = 'object'
        AND jsonb_typeof(silver_attribute_document) = 'object'
        AND jsonb_typeof(gold_object_document) = 'object'
        AND jsonb_typeof(gold_attribute_document) = 'object'
        AND jsonb_typeof(copy_group_document) = 'object'
        AND jsonb_typeof(copy_document) = 'object'
        AND jsonb_typeof(process_group_document) = 'object'
        AND jsonb_typeof(process_document) = 'object'
        AND octet_length(source_object_document::TEXT) <= 16777216
        AND octet_length(source_attribute_document::TEXT) <= 16777216
        AND octet_length(bronze_object_document::TEXT) <= 16777216
        AND octet_length(bronze_attribute_document::TEXT) <= 16777216
        AND octet_length(silver_object_document::TEXT) <= 16777216
        AND octet_length(silver_attribute_document::TEXT) <= 16777216
        AND octet_length(gold_object_document::TEXT) <= 16777216
        AND octet_length(gold_attribute_document::TEXT) <= 16777216
        AND octet_length(copy_group_document::TEXT) <= 16777216
        AND octet_length(copy_document::TEXT) <= 16777216
        AND octet_length(process_group_document::TEXT) <= 16777216
        AND octet_length(process_document::TEXT) <= 16777216
    ),
    CONSTRAINT ck_metadata_change_set_expiry CHECK (
        last_activity_time >= created_time
        AND expires_time > last_activity_time
    ),
    CONSTRAINT ck_metadata_change_set_candidate_state CHECK (
        (metadata_change_set_status = 'active' AND candidate_digest IS NULL)
        OR (
            metadata_change_set_status IN ('validated', 'applied')
            AND candidate_digest IS NOT NULL
        )
        OR metadata_change_set_status IN (
            'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_terminal_time CHECK (
        (
            metadata_change_set_status IN (
                'applied', 'expired', 'discarded', 'superseded'
            )
        ) = (terminal_time IS NOT NULL)
    )
);

CREATE TABLE mcp.metadata_change_set_event (
    metadata_change_set_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metadata_change_set_id UUID NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_sequence BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    draft_revision BIGINT NOT NULL,
    section_name VARCHAR(30),
    action_count INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(30) NOT NULL,
    validation_report_id UUID,
    event_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_metadata_change_set_event_parent FOREIGN KEY (
        metadata_change_set_id,
        tenant_id
    ) REFERENCES mcp.metadata_change_set (
        metadata_change_set_id,
        tenant_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_change_set_event_sequence
        UNIQUE (metadata_change_set_id, event_sequence),
    CONSTRAINT ck_metadata_change_set_event_sequence CHECK (event_sequence > 0),
    CONSTRAINT ck_metadata_change_set_event_type CHECK (
        event_type IN (
            'created', 'section_put', 'validated', 'validation_failed',
            'applied', 'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_event_revision CHECK (
        draft_revision >= 1
    ),
    CONSTRAINT ck_metadata_change_set_event_section CHECK (
        section_name IS NULL
        OR section_name IN (
            'source_object', 'source_attribute',
            'bronze_object', 'bronze_attribute',
            'silver_object', 'silver_attribute',
            'gold_object', 'gold_attribute',
            'copy_group', 'copy', 'process_group', 'process'
        )
    ),
    CONSTRAINT ck_metadata_change_set_event_action_count CHECK (
        action_count >= 0
    ),
    CONSTRAINT ck_metadata_change_set_event_outcome CHECK (
        reference.is_nonblank(outcome)
    ),
    CONSTRAINT ck_metadata_change_set_event_metadata CHECK (
        jsonb_typeof(event_metadata) = 'object'
        AND octet_length(event_metadata::TEXT) <= 65536
    )
);

-- One immutable row per completed MCP tool call. input_metadata is a bounded,
-- server-created summary; it must never contain raw prompts, rows, output, or secrets.
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

CREATE INDEX ix_change_set_model_status_activity
    ON mcp.model_change_set (model_id, model_change_set_status, last_activity_time);

CREATE INDEX ix_change_set_expiry
    ON mcp.model_change_set (expires_time)
    WHERE model_change_set_status IN ('active', 'validated');

CREATE INDEX ix_metadata_change_set_tenant_status_activity
    ON mcp.metadata_change_set (
        tenant_id,
        metadata_change_set_status,
        last_activity_time
    );

CREATE INDEX ix_metadata_change_set_expiry
    ON mcp.metadata_change_set (expires_time)
    WHERE metadata_change_set_status IN ('active', 'validated');
