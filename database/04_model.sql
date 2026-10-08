-- GDS ETL Workbench Release 1: Model, Input Scope, policy, Assertions, and revision state.

CREATE SCHEMA model;

-- Schema lists are Model-owned authoring configuration, not physical registrations.
CREATE FUNCTION model.valid_schema_list(value JSONB)
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

CREATE TABLE model.model (
    model_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    model_description VARCHAR(2000),
    model_revision BIGINT NOT NULL DEFAULT 1,
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
    CONSTRAINT fk_model_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_default_mapping_system FOREIGN KEY (default_mapping_source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_id_tenant UNIQUE (model_id, tenant_id),
    CONSTRAINT ck_model_name CHECK (reference.is_nonblank(model_name)),
    CONSTRAINT ck_model_description CHECK (
        model_description IS NULL
        OR reference.is_nonblank(model_description)
    ),
    CONSTRAINT ck_model_revision CHECK (model_revision > 0),
    CONSTRAINT ck_model_logical_coverage CHECK (logical_coverage_threshold_percent BETWEEN 1 AND 100),
    CONSTRAINT ck_model_dimensional_coverage CHECK (dimensional_coverage_threshold_percent BETWEEN 1 AND 100),
    CONSTRAINT ck_model_logical_schemas CHECK (model.valid_schema_list(logical_schemas)),
    CONSTRAINT ck_model_logical_entity_scd_type CHECK (
        logical_entity_scd_type IS NULL OR logical_entity_scd_type IN ('type_1', 'type_2')
    ),
    CONSTRAINT ck_model_dimensional_entity_scd_type CHECK (
        dimensional_entity_scd_type IS NULL OR dimensional_entity_scd_type IN ('type_1', 'type_2')
    ),
    CONSTRAINT ck_model_dimensional_schemas CHECK (model.valid_schema_list(dimensional_schemas)),
    CONSTRAINT ck_model_silver_naming_instructions CHECK (
        silver_model_naming_instructions IS NULL
        OR (
            reference.is_nonblank(silver_model_naming_instructions)
            AND octet_length(silver_model_naming_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_model_gold_naming_instructions CHECK (
        gold_model_naming_instructions IS NULL
        OR (
            reference.is_nonblank(gold_model_naming_instructions)
            AND octet_length(gold_model_naming_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_model_default_agent_configuration CHECK (
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
    CONSTRAINT ck_model_default_agent_codes CHECK (
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

CREATE TABLE model.model_lock_event (
    model_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL REFERENCES model.model (model_id),
    is_locked BOOLEAN NOT NULL,
    model_revision BIGINT NOT NULL,
    changed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NOT NULL
);

CREATE TABLE model.model_input_scope (
    model_input_scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    model_input_scope_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_input_scope_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_input_scope_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_input_scope UNIQUE (model_id, object_id)
);

CREATE TABLE model.model_event_log (
    model_event_log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    model_event_log_sequence BIGINT NOT NULL,
    model_event_log_attempt INTEGER NOT NULL,
    model_workflow VARCHAR(30) NOT NULL,
    model_event_log_stage VARCHAR(100) NOT NULL,
    model_event_log_status VARCHAR(30) NOT NULL,
    model_event_log_message VARCHAR(2000) NOT NULL,
    model_event_log_current INTEGER,
    model_event_log_total INTEGER,
    model_event_log_percent NUMERIC(5, 2),
    finding_count INTEGER NOT NULL DEFAULT 0,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_event_log_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_model_event_log_workflow CHECK (
        model_workflow IN (
            'profiling', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping',
            'code_generation', 'validation', 'metadata_enrichment', 'dbml'
        )
    ),
    CONSTRAINT ck_model_event_log_order CHECK (
        model_event_log_sequence > 0
        AND model_event_log_attempt > 0
    ),
    CONSTRAINT ck_model_event_log_stage CHECK (
        reference.is_nonblank(model_event_log_stage)
    ),
    CONSTRAINT ck_model_event_log_status CHECK (
        model_event_log_status IN (
            'started', 'running', 'completed', 'warning', 'failed', 'blocked'
        )
    ),
    CONSTRAINT ck_model_event_log_message CHECK (
        reference.is_nonblank(model_event_log_message)
    ),
    CONSTRAINT ck_model_event_log_progress CHECK (
        (model_event_log_current IS NULL OR model_event_log_current >= 0)
        AND (model_event_log_total IS NULL OR model_event_log_total >= 0)
        AND (
            model_event_log_current IS NULL
            OR model_event_log_total IS NULL
            OR model_event_log_current <= model_event_log_total
        )
        AND (
            model_event_log_percent IS NULL
            OR model_event_log_percent BETWEEN 0 AND 100
        )
        AND finding_count >= 0
    ),
    CONSTRAINT uq_model_event_log_sequence UNIQUE (
        model_id,
        correlation_id,
        model_event_log_sequence
    )
);

CREATE FUNCTION model.reject_model_event_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $reject_model_event_log_mutation$
BEGIN
    RAISE EXCEPTION 'Model event log is append-only' USING ERRCODE = '55000';
END;
$reject_model_event_log_mutation$;

CREATE TRIGGER reject_model_event_log_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE
ON model.model_event_log
FOR EACH STATEMENT
EXECUTE FUNCTION model.reject_model_event_log_mutation();

CREATE INDEX ix_model_event_log_run_sequence
    ON model.model_event_log (workflow_run_id, model_event_log_sequence)
    WHERE workflow_run_id IS NOT NULL;

CREATE TABLE model.modeling_assertion_document (
    modeling_assertion_document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    tenant_id BIGINT,
    system_id BIGINT,
    modeling_assertion_document_name VARCHAR(255) NOT NULL,
    modeling_assertion_file_pattern VARCHAR(500),
    modeling_assertion_document_type VARCHAR(100),
    modeling_assertion_document_description VARCHAR(2000),
    modeling_assertion_document_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_assertion_document_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_assertion_document_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_assertion_document_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_assertion_document_id_model
        UNIQUE (modeling_assertion_document_id, model_id),
    CONSTRAINT ck_assertion_document_name CHECK (
        reference.is_nonblank(modeling_assertion_document_name)
    ),
    CONSTRAINT ck_assertion_file_pattern CHECK (
        modeling_assertion_file_pattern IS NULL
        OR reference.is_nonblank(modeling_assertion_file_pattern)
    ),
    CONSTRAINT ck_assertion_document_type CHECK (
        modeling_assertion_document_type IS NULL
        OR reference.is_nonblank(modeling_assertion_document_type)
    ),
    CONSTRAINT ck_assertion_document_description CHECK (
        modeling_assertion_document_description IS NULL
        OR reference.is_nonblank(modeling_assertion_document_description)
    ),
    CONSTRAINT ck_assertion_document_metadata CHECK (
        jsonb_typeof(modeling_assertion_document_metadata) = 'object'
    )
);

CREATE TABLE model.modeling_assertion_record (
    modeling_assertion_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    modeling_assertion_document_id BIGINT NOT NULL,
    modeling_assertion_record_key VARCHAR(100) NOT NULL,
    modeling_assertion_record_type VARCHAR(100) NOT NULL,
    modeling_assertion_text TEXT NOT NULL,
    modeling_assertion_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    modeling_assertion_source_location JSONB,
    modeling_assertion_applicable_layers TEXT[] NOT NULL DEFAULT '{}',
    modeling_assertion_confidence VARCHAR(10),
    modeling_assertion_record_status VARCHAR(20) NOT NULL DEFAULT 'active',
    modeling_assertion_record_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_assertion_record_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_assertion_record_document FOREIGN KEY (
        modeling_assertion_document_id,
        model_id
    ) REFERENCES model.modeling_assertion_document (
        modeling_assertion_document_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_assertion_record_id_model
        UNIQUE (modeling_assertion_record_id, model_id),
    CONSTRAINT ck_assertion_record_key CHECK (
        modeling_assertion_record_key ~ '^[A-Za-z][A-Za-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_assertion_record_type CHECK (
        reference.is_nonblank(modeling_assertion_record_type)
    ),
    CONSTRAINT ck_assertion_record_text CHECK (
        reference.is_nonblank(modeling_assertion_text)
    ),
    CONSTRAINT ck_assertion_record_details CHECK (
        jsonb_typeof(modeling_assertion_details) = 'object'
    ),
    CONSTRAINT ck_assertion_source_location CHECK (
        modeling_assertion_source_location IS NULL
        OR jsonb_typeof(modeling_assertion_source_location) = 'object'
    ),
    CONSTRAINT ck_assertion_applicable_layers CHECK (
        modeling_assertion_applicable_layers <@ ARRAY[
            'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
        ]::TEXT[]
    ),
    CONSTRAINT ck_assertion_confidence CHECK (
        modeling_assertion_confidence IS NULL
        OR modeling_assertion_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_assertion_record_status CHECK (
        modeling_assertion_record_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE TABLE model.model_revision_transaction (
    model_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL DEFAULT txid_current(),
    change_kind VARCHAR(100) NOT NULL,
    changed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NOT NULL DEFAULT SESSION_USER,
    PRIMARY KEY (model_id, transaction_id),
    CONSTRAINT fk_model_revision_transaction_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_model_revision_change_kind CHECK (
        reference.is_nonblank(change_kind)
    )
);

CREATE UNIQUE INDEX ux_model_tenant_name_ci
    ON model.model (tenant_id, lower(btrim(model_name)));
CREATE UNIQUE INDEX ux_assertion_document_model_name_ci
    ON model.modeling_assertion_document (
        model_id,
        lower(btrim(modeling_assertion_document_name))
    );
CREATE UNIQUE INDEX ux_assertion_record_model_key_ci
    ON model.modeling_assertion_record (
        model_id,
        lower(btrim(modeling_assertion_record_key))
    );

CREATE INDEX ix_model_tenant_active ON model.model (tenant_id, is_active);
CREATE INDEX ix_model_event_log_model_created
    ON model.model_event_log (model_id, created_time);
CREATE INDEX ix_assertion_document_model_active
    ON model.modeling_assertion_document (model_id, is_active);
CREATE INDEX ix_assertion_document_tenant_system
    ON model.modeling_assertion_document (tenant_id, system_id);
CREATE INDEX ix_assertion_record_model_status
    ON model.modeling_assertion_record (
        model_id,
        modeling_assertion_record_status,
        modeling_assertion_document_id
    );
