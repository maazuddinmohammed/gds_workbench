-- GDS ETL Workbench Release 1: Project, Input Scope, policy, Context, and revision state.

CREATE SCHEMA project;

-- Schema lists are Project-owned authoring configuration, not physical registrations.
CREATE FUNCTION project.valid_schema_list(value JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $valid_schema_list$
DECLARE
    item JSONB;
    names TEXT[] := ARRAY[]::TEXT[];
    normalized_name TEXT;
BEGIN
    IF value IS NULL OR jsonb_typeof(value) <> 'array'
       OR octet_length(value::TEXT) > 262144 THEN
        RETURN FALSE;
    END IF;
    IF jsonb_array_length(value) > 100 THEN
        RETURN FALSE;
    END IF;
    FOR item IN SELECT element FROM jsonb_array_elements(value) AS entry(element) LOOP
        IF jsonb_typeof(item) <> 'object'
           OR NOT (item ? 'schema_name' AND item ? 'description')
           OR item - ARRAY['schema_name', 'description'] <> '{}'::JSONB
           OR jsonb_typeof(item -> 'schema_name') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item -> 'description') NOT IN ('string', 'null')
           OR length(btrim(item ->> 'schema_name')) = 0
           OR length(item ->> 'schema_name') > 400
           OR (jsonb_typeof(item -> 'description') = 'string'
               AND (length(btrim(item ->> 'description')) = 0
                    OR length(item ->> 'description') > 2000)) THEN
            RETURN FALSE;
        END IF;
        normalized_name := lower(btrim(item ->> 'schema_name'));
        IF normalized_name = ANY(names) THEN
            RETURN FALSE;
        END IF;
        names := array_append(names, normalized_name);
    END LOOP;
    RETURN TRUE;
END;
$valid_schema_list$;

CREATE TABLE project.project (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    project_name VARCHAR(255) NOT NULL,
    project_description VARCHAR(2000),
    project_revision BIGINT NOT NULL DEFAULT 1,
    logical_schemas JSONB NOT NULL DEFAULT '[]'::JSONB,
    dimensional_schemas JSONB NOT NULL DEFAULT '[]'::JSONB,
    default_mapping_source_system_id BIGINT,
    logical_entity_scd_type VARCHAR(10),
    dimensional_entity_scd_type VARCHAR(10),
    logical_coverage_threshold_percent INTEGER NOT NULL DEFAULT 70,
    dimensional_coverage_threshold_percent INTEGER NOT NULL DEFAULT 60,
    logical_enforce_coverage_threshold BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_enforce_coverage_threshold BOOLEAN NOT NULL DEFAULT FALSE,
    silver_model_naming_instructions TEXT,
    silver_model_audit_columns_template JSONB,
    gold_model_naming_instructions TEXT,
    gold_model_technical_columns_template JSONB,
    gold_model_audit_columns_template JSONB,
    default_agent_sdk_code VARCHAR(100),
    default_agent_provider_code VARCHAR(100),
    default_agent_model_code VARCHAR(200),
    default_reasoning_effort_code VARCHAR(50),
    default_max_turns INTEGER,
    default_validation_retry_count INTEGER,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_project_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_project_default_mapping_system FOREIGN KEY (default_mapping_source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_project_id_tenant UNIQUE (project_id, tenant_id),
    CONSTRAINT ck_project_name CHECK (reference.is_nonblank(project_name)),
    CONSTRAINT ck_project_description CHECK (
        project_description IS NULL
        OR reference.is_nonblank(project_description)
    ),
    CONSTRAINT ck_project_revision CHECK (project_revision > 0),
    CONSTRAINT ck_project_logical_coverage CHECK (logical_coverage_threshold_percent BETWEEN 1 AND 100),
    CONSTRAINT ck_project_dimensional_coverage CHECK (dimensional_coverage_threshold_percent BETWEEN 1 AND 100),
    CONSTRAINT ck_project_logical_schemas CHECK (project.valid_schema_list(logical_schemas)),
    CONSTRAINT ck_project_logical_entity_scd_type CHECK (
        logical_entity_scd_type IS NULL OR logical_entity_scd_type IN ('type_1', 'type_2')
    ),
    CONSTRAINT ck_project_dimensional_entity_scd_type CHECK (
        dimensional_entity_scd_type IS NULL OR dimensional_entity_scd_type IN ('type_1', 'type_2')
    ),
    CONSTRAINT ck_project_dimensional_schemas CHECK (project.valid_schema_list(dimensional_schemas)),
    CONSTRAINT ck_project_silver_naming_instructions CHECK (
        silver_model_naming_instructions IS NULL
        OR (
            reference.is_nonblank(silver_model_naming_instructions)
            AND octet_length(silver_model_naming_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_project_gold_naming_instructions CHECK (
        gold_model_naming_instructions IS NULL
        OR (
            reference.is_nonblank(gold_model_naming_instructions)
            AND octet_length(gold_model_naming_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_project_default_agent_configuration CHECK (
        (
            default_agent_sdk_code IS NULL
            AND default_agent_provider_code IS NULL
            AND default_agent_model_code IS NULL
            AND default_reasoning_effort_code IS NULL
            AND default_max_turns IS NULL
            AND default_validation_retry_count IS NULL
        ) OR (
            default_agent_sdk_code IS NOT NULL
            AND default_agent_provider_code IS NOT NULL
            AND default_agent_model_code IS NOT NULL
            AND default_reasoning_effort_code IS NOT NULL
            AND default_max_turns BETWEEN 1 AND 100
            AND default_validation_retry_count BETWEEN 0 AND 25
        )
    ),
    CONSTRAINT ck_project_default_agent_codes CHECK (
        (
            default_agent_sdk_code IS NULL
            OR default_agent_sdk_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        )
        AND (
            default_agent_provider_code IS NULL
            OR default_agent_provider_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        )
        AND (
            default_agent_model_code IS NULL
            OR default_agent_model_code
                ~ '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$'
        )
        AND (
            default_reasoning_effort_code IS NULL
            OR default_reasoning_effort_code ~ '^[a-z][a-z0-9_-]{0,49}$'
        )
    )
);

CREATE TABLE project.project_lock_event (
    project_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES project.project (project_id),
    is_locked BOOLEAN NOT NULL,
    project_revision BIGINT NOT NULL,
    changed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NOT NULL
);

CREATE TABLE project.project_input_scope (
    project_input_scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    project_input_scope_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_project_input_scope_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_project_input_scope_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_project_input_scope UNIQUE (project_id, object_id)
);

CREATE TABLE project.project_event_log (
    project_event_log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    project_event_log_sequence BIGINT NOT NULL,
    project_event_log_attempt INTEGER NOT NULL,
    project_workflow VARCHAR(30) NOT NULL,
    project_event_log_stage VARCHAR(100) NOT NULL,
    project_event_log_status VARCHAR(30) NOT NULL,
    project_event_log_message VARCHAR(2000) NOT NULL,
    project_event_log_current INTEGER,
    project_event_log_total INTEGER,
    project_event_log_percent NUMERIC(5, 2),
    finding_count INTEGER NOT NULL DEFAULT 0,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_project_event_log_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT ck_project_event_log_workflow CHECK (
        project_workflow IN (
            'profiling', 'analysis', 'subject_area',
            'logical', 'dimensional', 'mapping',
            'code_generation', 'validation', 'metadata_enrichment', 'dbml'
        )
    ),
    CONSTRAINT ck_project_event_log_order CHECK (
        project_event_log_sequence > 0
        AND project_event_log_attempt > 0
    ),
    CONSTRAINT ck_project_event_log_stage CHECK (
        reference.is_nonblank(project_event_log_stage)
    ),
    CONSTRAINT ck_project_event_log_status CHECK (
        project_event_log_status IN (
            'started', 'running', 'completed', 'warning', 'failed', 'blocked'
        )
    ),
    CONSTRAINT ck_project_event_log_message CHECK (
        reference.is_nonblank(project_event_log_message)
    ),
    CONSTRAINT ck_project_event_log_progress CHECK (
        (project_event_log_current IS NULL OR project_event_log_current >= 0)
        AND (project_event_log_total IS NULL OR project_event_log_total >= 0)
        AND (
            project_event_log_current IS NULL
            OR project_event_log_total IS NULL
            OR project_event_log_current <= project_event_log_total
        )
        AND (
            project_event_log_percent IS NULL
            OR project_event_log_percent BETWEEN 0 AND 100
        )
        AND finding_count >= 0
    ),
    CONSTRAINT uq_project_event_log_sequence UNIQUE (
        project_id,
        correlation_id,
        project_event_log_sequence
    )
);

CREATE FUNCTION project.reject_project_event_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $reject_project_event_log_mutation$
BEGIN
    RAISE EXCEPTION 'Project event log is append-only' USING ERRCODE = '55000';
END;
$reject_project_event_log_mutation$;

CREATE TRIGGER reject_project_event_log_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE
ON project.project_event_log
FOR EACH STATEMENT
EXECUTE FUNCTION project.reject_project_event_log_mutation();

CREATE INDEX ix_project_event_log_run_sequence
    ON project.project_event_log (workflow_run_id, project_event_log_sequence)
    WHERE workflow_run_id IS NOT NULL;

CREATE TABLE project.context_group (
    context_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    context_type_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(2000),
    source_system_id BIGINT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_context_group_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_context_group_type FOREIGN KEY (context_type_id)
        REFERENCES reference.context_type (context_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_context_group_source_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_context_group_id_project UNIQUE (context_group_id, project_id),
    CONSTRAINT ck_context_group_name CHECK (reference.is_nonblank(name)),
    CONSTRAINT ck_context_group_description CHECK (
        description IS NULL OR reference.is_nonblank(description)
    )
);

CREATE TABLE project.context_record (
    context_record_id UUID PRIMARY KEY,
    project_id BIGINT NOT NULL,
    context_group_id BIGINT NOT NULL,
    context_text TEXT NOT NULL,
    source_reference TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_context_record_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_context_record_group FOREIGN KEY (context_group_id, project_id)
        REFERENCES project.context_group (context_group_id, project_id) ON DELETE NO ACTION,
    CONSTRAINT uq_context_record_id_project UNIQUE (context_record_id, project_id),
    CONSTRAINT ck_context_record_text CHECK (
        reference.is_nonblank(context_text) AND length(context_text) <= 262144
    ),
    CONSTRAINT ck_context_record_source_reference CHECK (
        source_reference IS NULL OR octet_length(source_reference) <= 65536
    ),
    CONSTRAINT ck_context_record_status CHECK (status IN ('active', 'inactive', 'deprecated'))
);

CREATE TABLE project.project_revision_transaction (
    project_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL DEFAULT txid_current(),
    change_kind VARCHAR(100) NOT NULL,
    changed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NOT NULL DEFAULT SESSION_USER,
    PRIMARY KEY (project_id, transaction_id),
    CONSTRAINT fk_project_revision_transaction_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT ck_project_revision_change_kind CHECK (
        reference.is_nonblank(change_kind)
    )
);

CREATE UNIQUE INDEX ux_project_tenant_name_ci
    ON project.project (tenant_id, lower(btrim(project_name)));
CREATE UNIQUE INDEX ux_context_group_project_name_ci
    ON project.context_group (project_id, lower(btrim(name)));

CREATE INDEX ix_project_tenant_active ON project.project (tenant_id, is_active);
CREATE INDEX ix_project_event_log_project_created
    ON project.project_event_log (project_id, created_time);
CREATE INDEX ix_context_group_project_active
    ON project.context_group (project_id, is_active);
CREATE INDEX ix_context_group_source_system
    ON project.context_group (source_system_id);
CREATE INDEX ix_context_record_project_status
    ON project.context_record (project_id, status, context_group_id);
