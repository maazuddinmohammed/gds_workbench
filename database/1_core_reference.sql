-- GDS ETL Workbench Release 1: canonical core reference schema.
-- Fresh-install DDL only. Execute numbered files exactly once in numeric order.

CREATE SCHEMA core;

CREATE FUNCTION core.is_nonblank(value TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN value IS NOT NULL AND length(btrim(value)) > 0;

CREATE TABLE core.environment (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_code VARCHAR(100) NOT NULL,
    environment_name VARCHAR(200) NOT NULL,
    environment_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_environment_code CHECK (core.is_nonblank(environment_code)),
    CONSTRAINT ck_environment_name CHECK (core.is_nonblank(environment_name))
);

CREATE TABLE core.system_type (
    system_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_type_code VARCHAR(100) NOT NULL,
    system_type_name VARCHAR(200) NOT NULL,
    system_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_system_type_code CHECK (core.is_nonblank(system_type_code)),
    CONSTRAINT ck_system_type_name CHECK (core.is_nonblank(system_type_name))
);

CREATE TABLE core.zone (
    zone_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_code VARCHAR(30) NOT NULL,
    zone_name VARCHAR(200) NOT NULL,
    zone_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_zone_code CHECK (core.is_nonblank(zone_code)),
    CONSTRAINT ck_zone_name CHECK (core.is_nonblank(zone_name))
);

CREATE TABLE core.connection_type (
    connection_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_type_code VARCHAR(100) NOT NULL,
    connection_type_name VARCHAR(200) NOT NULL,
    connection_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_connection_type_code CHECK (
        core.is_nonblank(connection_type_code)
    ),
    CONSTRAINT ck_connection_type_name CHECK (core.is_nonblank(connection_type_name))
);

CREATE TABLE core.object_type (
    object_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_type_code VARCHAR(100) NOT NULL,
    object_type_name VARCHAR(200) NOT NULL,
    object_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_object_type_code CHECK (core.is_nonblank(object_type_code)),
    CONSTRAINT ck_object_type_name CHECK (core.is_nonblank(object_type_name))
);

CREATE TABLE core.connection_parameter (
    connection_parameter_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_parameter_code VARCHAR(100) NOT NULL,
    connection_parameter_name VARCHAR(200) NOT NULL,
    connection_parameter_description TEXT,
    is_key_vault BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_connection_parameter_code CHECK (
        core.is_nonblank(connection_parameter_code)
    ),
    CONSTRAINT ck_connection_parameter_name CHECK (
        core.is_nonblank(connection_parameter_name)
    )
);

CREATE TABLE core.purge_policy (
    purge_policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purge_policy_name VARCHAR(200) NOT NULL,
    purge_policy_description TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_purge_policy_name CHECK (
        core.is_nonblank(purge_policy_name)
    )
);

CREATE TABLE core.system_notebook (
    system_notebook_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_notebook_name VARCHAR(200) NOT NULL,
    system_notebook_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_system_notebook_name CHECK (
        core.is_nonblank(system_notebook_name)
    )
);

CREATE TABLE core.location_type (
    location_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_type_name VARCHAR(200) NOT NULL,
    location_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_location_type_name CHECK (
        core.is_nonblank(location_type_name)
    )
);

CREATE TABLE core.file_type (
    file_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_type_name VARCHAR(200) NOT NULL,
    file_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_file_type_name CHECK (
        core.is_nonblank(file_type_name)
    )
);

CREATE TABLE core.domain (
    domain_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain_name VARCHAR(200) NOT NULL,
    domain_description TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_domain_name CHECK (core.is_nonblank(domain_name))
);

CREATE TABLE core.data_operation (
    data_operation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_operation_name VARCHAR(200) NOT NULL,
    data_operation_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_data_operation_name CHECK (
        core.is_nonblank(data_operation_name)
    )
);

CREATE TABLE core.chunk_type (
    chunk_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chunk_type_name VARCHAR(200) NOT NULL,
    chunk_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_chunk_type_name CHECK (
        core.is_nonblank(chunk_type_name)
    )
);

CREATE TABLE core.pipeline (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name VARCHAR(200) NOT NULL,
    pipeline_description TEXT,
    parent_pipeline_name VARCHAR(200),
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT uq_pipeline_name UNIQUE (pipeline_name),
    CONSTRAINT fk_pipeline_parent FOREIGN KEY (parent_pipeline_name)
        REFERENCES core.pipeline (pipeline_name) ON DELETE NO ACTION,
    CONSTRAINT ck_pipeline_name CHECK (core.is_nonblank(pipeline_name)),
    CONSTRAINT ck_pipeline_parent_name CHECK (
        parent_pipeline_name IS NULL
        OR (
            core.is_nonblank(parent_pipeline_name)
            AND lower(btrim(parent_pipeline_name))
                <> lower(btrim(pipeline_name))
        )
    )
);

CREATE TABLE core.process_type (
    process_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    process_type_name VARCHAR(200) NOT NULL,
    process_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_process_type_name CHECK (
        core.is_nonblank(process_type_name)
    )
);

CREATE TABLE core.currency (
    currency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL,
    currency_name VARCHAR(200) NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_currency_code CHECK (core.is_nonblank(currency_code)),
    CONSTRAINT ck_currency_name CHECK (core.is_nonblank(currency_name))
);

CREATE TABLE core.job_type (
    job_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type_name VARCHAR(200) NOT NULL,
    job_type_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_job_type_name CHECK (core.is_nonblank(job_type_name))
);

CREATE TABLE core.lane (
    lane_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lane_code VARCHAR(100) NOT NULL,
    lane_name VARCHAR(200) NOT NULL,
    lane_description TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_lane_code CHECK (core.is_nonblank(lane_code)),
    CONSTRAINT ck_lane_name CHECK (core.is_nonblank(lane_name))
);

CREATE UNIQUE INDEX ux_environment_code_ci
    ON core.environment (lower(btrim(environment_code)));
CREATE UNIQUE INDEX ux_system_type_code_ci
    ON core.system_type (lower(btrim(system_type_code)));
CREATE UNIQUE INDEX ux_zone_code_ci
    ON core.zone (lower(btrim(zone_code)));
CREATE UNIQUE INDEX ux_zone_name_ci
    ON core.zone (lower(btrim(zone_name)));
CREATE UNIQUE INDEX ux_connection_type_code_ci
    ON core.connection_type (lower(btrim(connection_type_code)));
CREATE UNIQUE INDEX ux_object_type_code_ci
    ON core.object_type (lower(btrim(object_type_code)));
CREATE UNIQUE INDEX ux_connection_parameter_code_ci
    ON core.connection_parameter (lower(btrim(connection_parameter_code)));
CREATE UNIQUE INDEX ux_purge_policy_name_ci
    ON core.purge_policy (lower(btrim(purge_policy_name)));
CREATE UNIQUE INDEX ux_system_notebook_name_ci
    ON core.system_notebook (lower(btrim(system_notebook_name)));
CREATE UNIQUE INDEX ux_location_type_name_ci
    ON core.location_type (lower(btrim(location_type_name)));
CREATE UNIQUE INDEX ux_file_type_name_ci
    ON core.file_type (lower(btrim(file_type_name)));
CREATE UNIQUE INDEX ux_domain_name_ci
    ON core.domain (lower(btrim(domain_name)));
CREATE UNIQUE INDEX ux_data_operation_name_ci
    ON core.data_operation (lower(btrim(data_operation_name)));
CREATE UNIQUE INDEX ux_chunk_type_name_ci
    ON core.chunk_type (lower(btrim(chunk_type_name)));
CREATE UNIQUE INDEX ux_pipeline_name_ci
    ON core.pipeline (lower(btrim(pipeline_name)));
CREATE UNIQUE INDEX ux_process_type_name_ci
    ON core.process_type (lower(btrim(process_type_name)));
CREATE UNIQUE INDEX ux_currency_code_ci
    ON core.currency (lower(btrim(currency_code)));
CREATE UNIQUE INDEX ux_job_type_name_ci
    ON core.job_type (lower(btrim(job_type_name)));
CREATE UNIQUE INDEX ux_lane_code_ci
    ON core.lane (lower(btrim(lane_code)));

CREATE INDEX ix_environment_active ON core.environment (is_active, environment_code);
CREATE INDEX ix_system_type_active ON core.system_type (is_active, system_type_code);
CREATE INDEX ix_zone_active ON core.zone (is_active, zone_code);
CREATE INDEX ix_connection_type_active
    ON core.connection_type (is_active, connection_type_code);
CREATE INDEX ix_object_type_active ON core.object_type (is_active, object_type_code);
CREATE INDEX ix_connection_parameter_active
    ON core.connection_parameter (is_active, connection_parameter_code);
CREATE INDEX ix_system_notebook_active
    ON core.system_notebook (is_active, system_notebook_name);
CREATE INDEX ix_location_type_active
    ON core.location_type (is_active, location_type_name);
CREATE INDEX ix_file_type_active
    ON core.file_type (is_active, file_type_name);
CREATE INDEX ix_data_operation_active
    ON core.data_operation (is_active, data_operation_name);
CREATE INDEX ix_chunk_type_active
    ON core.chunk_type (is_active, chunk_type_name);
CREATE INDEX ix_pipeline_parent
    ON core.pipeline (parent_pipeline_name);
CREATE INDEX ix_process_type_active
    ON core.process_type (is_active, process_type_name);
CREATE INDEX ix_job_type_active
    ON core.job_type (is_active, job_type_name);
