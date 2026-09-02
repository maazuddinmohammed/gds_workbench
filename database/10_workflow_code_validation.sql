-- GDS ETL Workbench Release 1: generated Code and Validation Model Sections.

CREATE TABLE workflow.generated_code (
    generated_code_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_object_binding_id BIGINT NOT NULL,
    artifact_name VARCHAR(400) NOT NULL,
    artifact_type VARCHAR(30) NOT NULL,
    generated_code_content TEXT NOT NULL,
    code_input_digest CHAR(64) NOT NULL,
    generated_code_digest CHAR(64) GENERATED ALWAYS AS (
        encode(
            sha256(generated_code_content::BYTEA),
            'hex'
        )
    ) STORED,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    generated_code_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_generated_code_binding FOREIGN KEY (model_object_binding_id)
        REFERENCES workflow.model_object_binding (model_object_binding_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_generated_code_artifact_name CHECK (
        reference.is_nonblank(artifact_name)
        AND artifact_name = btrim(artifact_name)
        AND artifact_name !~ '[/\\]'
        AND artifact_name NOT IN ('.', '..')
    ),
    CONSTRAINT ck_generated_code_artifact_type CHECK (
        artifact_type IN ('sql_file', 'python_file', 'python_notebook')
    ),
    CONSTRAINT ck_generated_code_content CHECK (
        reference.is_nonblank(generated_code_content)
    ),
    CONSTRAINT ck_generated_code_input_digest CHECK (
        code_input_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_generated_code_status CHECK (
        generated_code_status IN ('active', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_generated_code_artifact_name_ci
    ON workflow.generated_code (
        model_object_binding_id,
        lower(btrim(artifact_name))
    );

CREATE TABLE workflow.generated_code_source_system (
    generated_code_source_system_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    generated_code_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    generated_code_source_system_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_generated_code_source_system_code
        FOREIGN KEY (generated_code_id)
        REFERENCES workflow.generated_code (generated_code_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_generated_code_source_system_system
        FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_generated_code_source_system UNIQUE (
        generated_code_id,
        source_system_id
    ),
    CONSTRAINT ck_generated_code_source_system_status CHECK (
        generated_code_source_system_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE TABLE workflow.validation_group (
    validation_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    validation_group_name VARCHAR(200) NOT NULL,
    validation_group_description TEXT,
    mapping_context_digest CHAR(64) NOT NULL,
    code_context_digest CHAR(64),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_validation_group_model_tenant FOREIGN KEY (
        model_id,
        tenant_id
    ) REFERENCES model.model (model_id, tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_validation_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_validation_group_scope_witness UNIQUE (
        validation_group_id,
        model_id,
        tenant_id,
        system_id
    ),
    CONSTRAINT ck_validation_group_name CHECK (
        reference.is_nonblank(validation_group_name)
    ),
    CONSTRAINT ck_validation_group_description CHECK (
        validation_group_description IS NULL
        OR (
            reference.is_nonblank(validation_group_description)
            AND octet_length(validation_group_description) <= 16384
        )
    ),
    CONSTRAINT ck_validation_group_digests CHECK (
        mapping_context_digest ~ '^[0-9a-f]{64}$'
        AND (
            code_context_digest IS NULL
            OR code_context_digest ~ '^[0-9a-f]{64}$'
        )
    )
);

CREATE UNIQUE INDEX ux_validation_group_scope_name_ci
    ON workflow.validation_group (
        model_id,
        tenant_id,
        system_id,
        lower(btrim(validation_group_name))
    );
CREATE INDEX ix_validation_group_pipeline_lookup
    ON workflow.validation_group (
        tenant_id,
        system_id,
        model_id,
        validation_group_id
    )
    WHERE is_active;

CREATE TABLE workflow.validation_check (
    validation_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    validation_group_id BIGINT NOT NULL,
    validation_check_name VARCHAR(200) NOT NULL,
    validation_check_description TEXT,
    validation_category_code VARCHAR(100) NOT NULL,
    validation_severity VARCHAR(20) NOT NULL,
    validation_query_sql TEXT NOT NULL,
    validation_comparison_query_sql TEXT,
    validation_result_data_type VARCHAR(20),
    validation_comparison_operator VARCHAR(30) NOT NULL,
    validation_comparison_value_type VARCHAR(20) NOT NULL,
    validation_comparison_value JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_validation_check_group FOREIGN KEY (validation_group_id)
        REFERENCES workflow.validation_group (validation_group_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_validation_check_name CHECK (
        reference.is_nonblank(validation_check_name)
    ),
    CONSTRAINT ck_validation_check_description CHECK (
        validation_check_description IS NULL
        OR (
            reference.is_nonblank(validation_check_description)
            AND octet_length(validation_check_description) <= 16384
        )
    ),
    CONSTRAINT ck_validation_check_category CHECK (
        validation_category_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_validation_check_severity CHECK (
        validation_severity IN ('blocking', 'warning', 'informational')
    ),
    CONSTRAINT ck_validation_check_query_a CHECK (
        reference.is_nonblank(validation_query_sql)
        AND octet_length(validation_query_sql) <= 100000
    ),
    CONSTRAINT ck_validation_check_query_b CHECK (
        validation_comparison_query_sql IS NULL
        OR (
            reference.is_nonblank(validation_comparison_query_sql)
            AND octet_length(validation_comparison_query_sql) <= 100000
        )
    ),
    CONSTRAINT ck_validation_check_result_type CHECK (
        validation_result_data_type IS NULL
        OR validation_result_data_type IN (
            'boolean', 'integer', 'decimal', 'text', 'date', 'timestamp'
        )
    ),
    CONSTRAINT ck_validation_check_operator CHECK (
        validation_comparison_operator IN (
            'executes_successfully',
            'is_null', 'is_not_null',
            'is_true', 'is_false',
            'equal', 'not_equal',
            'greater_than', 'greater_than_or_equal',
            'less_than', 'less_than_or_equal',
            'in', 'not_in'
        )
    ),
    CONSTRAINT ck_validation_check_value_type CHECK (
        validation_comparison_value_type IN (
            'none', 'literal', 'literal_list', 'query'
        )
    ),
    CONSTRAINT ck_validation_check_value_size CHECK (
        validation_comparison_value IS NULL
        OR octet_length(validation_comparison_value::TEXT) <= 65536
    ),
    CONSTRAINT ck_validation_check_assertion_shape CHECK (
        CASE
            WHEN validation_comparison_operator = 'executes_successfully'
            THEN
                validation_result_data_type IS NULL
                AND validation_comparison_value_type = 'none'
                AND validation_comparison_value IS NULL
                AND validation_comparison_query_sql IS NULL
            WHEN validation_comparison_operator IN ('is_null', 'is_not_null')
            THEN
                validation_result_data_type IS NOT NULL
                AND validation_comparison_value_type = 'none'
                AND validation_comparison_value IS NULL
                AND validation_comparison_query_sql IS NULL
            WHEN validation_comparison_operator IN ('is_true', 'is_false')
            THEN
                validation_result_data_type = 'boolean'
                AND validation_comparison_value_type = 'none'
                AND validation_comparison_value IS NULL
                AND validation_comparison_query_sql IS NULL
            WHEN validation_comparison_operator IN ('equal', 'not_equal')
            THEN
                validation_result_data_type IS NOT NULL
                AND (
                    (
                        validation_comparison_value_type = 'literal'
                        AND validation_comparison_value IS NOT NULL
                        AND validation_comparison_query_sql IS NULL
                    ) OR (
                        validation_comparison_value_type = 'query'
                        AND validation_comparison_value IS NULL
                        AND validation_comparison_query_sql IS NOT NULL
                    )
                )
            WHEN validation_comparison_operator IN (
                'greater_than', 'greater_than_or_equal',
                'less_than', 'less_than_or_equal'
            )
            THEN
                validation_result_data_type IN (
                    'integer', 'decimal', 'date', 'timestamp'
                )
                AND (
                    (
                        validation_comparison_value_type = 'literal'
                        AND validation_comparison_value IS NOT NULL
                        AND validation_comparison_query_sql IS NULL
                    ) OR (
                        validation_comparison_value_type = 'query'
                        AND validation_comparison_value IS NULL
                        AND validation_comparison_query_sql IS NOT NULL
                    )
                )
            WHEN validation_comparison_operator IN ('in', 'not_in')
            THEN
                validation_result_data_type IS NOT NULL
                AND validation_comparison_value_type = 'literal_list'
                AND validation_comparison_query_sql IS NULL
                AND CASE jsonb_typeof(validation_comparison_value)
                    WHEN 'array' THEN
                        jsonb_array_length(validation_comparison_value)
                            BETWEEN 1 AND 10000
                    ELSE FALSE
                END
            ELSE FALSE
        END
    ),
    CONSTRAINT ck_validation_check_literal_type CHECK (
        validation_comparison_value_type NOT IN ('literal', 'literal_list')
        OR CASE validation_comparison_value_type
            WHEN 'literal' THEN
                CASE validation_result_data_type
                    WHEN 'boolean' THEN
                        jsonb_typeof(validation_comparison_value) = 'boolean'
                    WHEN 'integer' THEN
                        CASE jsonb_typeof(validation_comparison_value)
                            WHEN 'number' THEN
                                coalesce(
                                    validation_comparison_value #>> '{}'
                                        ~ '^-?(0|[1-9][0-9]*)$',
                                    FALSE
                                )
                            ELSE FALSE
                        END
                    WHEN 'decimal' THEN
                        jsonb_typeof(validation_comparison_value) = 'number'
                    WHEN 'text' THEN
                        jsonb_typeof(validation_comparison_value) = 'string'
                    WHEN 'date' THEN
                        jsonb_typeof(validation_comparison_value) = 'string'
                    WHEN 'timestamp' THEN
                        jsonb_typeof(validation_comparison_value) = 'string'
                    ELSE FALSE
                END
            WHEN 'literal_list' THEN
                CASE validation_result_data_type
                    WHEN 'boolean' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "boolean")'
                        )
                    WHEN 'integer' THEN
                        validation_comparison_value::TEXT ~
                            '^\[[[:space:]]*-?(0|[1-9][0-9]*)'
                            '([[:space:]]*,[[:space:]]*'
                            '-?(0|[1-9][0-9]*))*[[:space:]]*\]$'
                    WHEN 'decimal' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "number")'
                        )
                    WHEN 'text' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "string")'
                        )
                    WHEN 'date' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "string")'
                        )
                    WHEN 'timestamp' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "string")'
                        )
                    ELSE FALSE
                END
            ELSE FALSE
        END
    )
);

CREATE UNIQUE INDEX ux_validation_check_group_name_ci
    ON workflow.validation_check (
        validation_group_id,
        lower(btrim(validation_check_name))
    );
CREATE INDEX ix_validation_check_group_active
    ON workflow.validation_check (
        validation_group_id,
        validation_check_id
    )
    WHERE is_active;
