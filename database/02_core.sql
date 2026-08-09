-- GDS ETL Workbench Release 1: foundational Core business and physical metadata.

CREATE SCHEMA core;

CREATE TABLE core.project (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_code VARCHAR(100) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    project_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_project_code CHECK (reference.is_nonblank(project_code)),
    CONSTRAINT ck_project_name CHECK (reference.is_nonblank(project_name))
);

CREATE TABLE core.tenant (
    tenant_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    tenant_code VARCHAR(100) NOT NULL,
    tenant_name VARCHAR(200) NOT NULL,
    tenant_description TEXT,
    tenant_catalog VARCHAR(255) NOT NULL,
    gds_admin_catalog VARCHAR(255) NOT NULL,
    gds_connection_id BIGINT,
    tenant_visibility VARCHAR(20) NOT NULL DEFAULT 'private',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_project FOREIGN KEY (project_id)
        REFERENCES core.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT ck_tenant_code CHECK (reference.is_nonblank(tenant_code)),
    CONSTRAINT ck_tenant_name CHECK (reference.is_nonblank(tenant_name)),
    CONSTRAINT ck_tenant_visibility CHECK (
        tenant_visibility IN ('global', 'private')
    )
);

CREATE TABLE core.system (
    system_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_code VARCHAR(100) NOT NULL,
    system_name VARCHAR(200) NOT NULL,
    system_description TEXT,
    system_type_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_system_system_type FOREIGN KEY (system_type_id)
        REFERENCES reference.system_type (system_type_id) ON DELETE NO ACTION,
    CONSTRAINT ck_system_code CHECK (reference.is_nonblank(system_code)),
    CONSTRAINT ck_system_name CHECK (reference.is_nonblank(system_name))
);

CREATE TABLE core.system_notebook_path (
    system_notebook_path_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_id BIGINT NOT NULL,
    system_notebook_id BIGINT NOT NULL,
    system_notebook_path TEXT NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_system_notebook_path_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT fk_system_notebook_path_notebook FOREIGN KEY (system_notebook_id)
        REFERENCES reference.system_notebook (system_notebook_id) ON DELETE NO ACTION,
    CONSTRAINT uq_system_notebook_path
        UNIQUE (system_id, system_notebook_id),
    CONSTRAINT ck_system_notebook_path CHECK (
        reference.is_nonblank(system_notebook_path)
    )
);

CREATE TABLE core.connection (
    connection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    connection_code VARCHAR(100) NOT NULL,
    connection_name VARCHAR(200) NOT NULL,
    connection_type_id BIGINT NOT NULL,
    has_foreign_catalog BOOLEAN NOT NULL DEFAULT FALSE,
    foreign_catalog VARCHAR(255),
    is_global_data_store BOOLEAN NOT NULL DEFAULT FALSE,
    test_initial_batch_id BIGINT,
    test_incremental_batch_ids BIGINT[],
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_connection_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_type FOREIGN KEY (connection_type_id)
        REFERENCES reference.connection_type (connection_type_id) ON DELETE NO ACTION,
    CONSTRAINT uq_connection_id_tenant UNIQUE (connection_id, tenant_id),
    CONSTRAINT ck_connection_code CHECK (reference.is_nonblank(connection_code)),
    CONSTRAINT ck_connection_name CHECK (reference.is_nonblank(connection_name))
);

CREATE TABLE core.connection_location (
    connection_location_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_id BIGINT NOT NULL,
    location_type_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,
    connection_location_storage_account VARCHAR(255) NOT NULL,
    connection_location_secret_reference TEXT NOT NULL,
    connection_location_container VARCHAR(255) NOT NULL,
    connection_location_path TEXT NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_connection_location_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_location_type FOREIGN KEY (location_type_id)
        REFERENCES reference.location_type (location_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_location_environment FOREIGN KEY (environment_id)
        REFERENCES reference.environment (environment_id) ON DELETE NO ACTION,
    CONSTRAINT uq_connection_location
        UNIQUE (connection_id, location_type_id, environment_id),
    CONSTRAINT ck_connection_location_storage_account CHECK (
        reference.is_nonblank(connection_location_storage_account)
    ),
    CONSTRAINT ck_connection_location_secret_reference CHECK (
        reference.is_nonblank(connection_location_secret_reference)
    ),
    CONSTRAINT ck_connection_location_container CHECK (
        reference.is_nonblank(connection_location_container)
    ),
    CONSTRAINT ck_connection_location_path CHECK (
        reference.is_nonblank(connection_location_path)
    )
);

CREATE TABLE core.connection_value (
    connection_value_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL,
    connection_id BIGINT NOT NULL,
    connection_parameter_id BIGINT NOT NULL,
    connection_value TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_connection_value_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_value_parameter FOREIGN KEY (connection_parameter_id)
        REFERENCES reference.connection_parameter (connection_parameter_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_connection_value_parameter
        UNIQUE (connection_id, connection_parameter_id, environment_id),
    CONSTRAINT ck_connection_literal_value CHECK (
        connection_value IS NULL OR reference.is_nonblank(connection_value)
    )
);

CREATE TABLE core.object (
    object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_id BIGINT NOT NULL,
    object_schema VARCHAR(400) NOT NULL,
    object_name VARCHAR(400) NOT NULL,
    fc_object_schema VARCHAR(400),
    fc_object_name VARCHAR(400),
    object_transformation TEXT,
    object_description TEXT,
    batch_attribute_name VARCHAR(400),
    object_type_id BIGINT NOT NULL,
    zone_id BIGINT NOT NULL,
    object_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_object_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_type FOREIGN KEY (object_type_id)
        REFERENCES reference.object_type (object_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id) ON DELETE NO ACTION,
    CONSTRAINT uq_object_id_connection UNIQUE (object_id, connection_id),
    CONSTRAINT uq_object_id_zone UNIQUE (object_id, zone_id),
    CONSTRAINT ck_object_schema CHECK (reference.is_nonblank(object_schema)),
    CONSTRAINT ck_object_name CHECK (reference.is_nonblank(object_name))
);

CREATE TABLE core.attribute (
    attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL,
    attribute_name VARCHAR(400) NOT NULL,
    fc_attribute_name VARCHAR(400),
    attribute_ordinal_position INTEGER NOT NULL,
    attribute_description TEXT,
    attribute_data_type VARCHAR(100) NOT NULL,
    attribute_nullability BOOLEAN NOT NULL DEFAULT TRUE,
    attribute_custom_code TEXT,
    business_glossary_id BIGINT,
    is_surrogate_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_natural_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_meta_data BOOLEAN NOT NULL DEFAULT FALSE,
    is_masking_required BOOLEAN NOT NULL DEFAULT FALSE,
    is_mapped BOOLEAN NOT NULL DEFAULT FALSE,
    is_purge BOOLEAN NOT NULL DEFAULT FALSE,
    attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_attribute_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_attribute_object_ordinal
        UNIQUE (object_id, attribute_ordinal_position),
    CONSTRAINT uq_attribute_id_object UNIQUE (attribute_id, object_id),
    CONSTRAINT ck_attribute_name CHECK (reference.is_nonblank(attribute_name)),
    CONSTRAINT ck_attribute_ordinal CHECK (attribute_ordinal_position > 0)
);

CREATE TABLE core.ingestion_object_mapping (
    ingestion_object_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_object_id BIGINT NOT NULL,
    target_object_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_ingestion_source_object FOREIGN KEY (source_object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_ingestion_target_object FOREIGN KEY (target_object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_ingestion_object_source_target
        UNIQUE (source_object_id, target_object_id),
    CONSTRAINT uq_ingestion_object_witness
        UNIQUE (
            ingestion_object_mapping_id,
            source_object_id,
            target_object_id
        ),
    CONSTRAINT ck_ingestion_objects_different CHECK (
        source_object_id <> target_object_id
    )
);

CREATE TABLE core.ingestion_attribute_mapping (
    ingestion_attribute_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingestion_object_mapping_id BIGINT NOT NULL,
    source_object_id BIGINT NOT NULL,
    target_object_id BIGINT NOT NULL,
    source_attribute_id BIGINT NOT NULL,
    target_attribute_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_ingestion_attribute_parent FOREIGN KEY (
        ingestion_object_mapping_id,
        source_object_id,
        target_object_id
    ) REFERENCES core.ingestion_object_mapping (
        ingestion_object_mapping_id,
        source_object_id,
        target_object_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_ingestion_source_attribute FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_ingestion_target_attribute FOREIGN KEY (
        target_attribute_id,
        target_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_ingestion_attribute_source_target
        UNIQUE (
            ingestion_object_mapping_id,
            source_attribute_id,
            target_attribute_id
        ),
    CONSTRAINT ck_ingestion_attributes_different CHECK (
        source_attribute_id <> target_attribute_id
    )
);

CREATE TABLE core.copy_group (
    copy_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    copy_group_name VARCHAR(200) NOT NULL,
    copy_group_description TEXT,
    is_member_group_required BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_copy_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_copy_group_scope
        UNIQUE (copy_group_id, tenant_id, system_id),
    CONSTRAINT ck_copy_group_name CHECK (
        reference.is_nonblank(copy_group_name)
    )
);

CREATE TABLE core.member_group (
    member_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    member_group_name VARCHAR(200) NOT NULL,
    member_group_description TEXT,
    member_group_initial_load_date DATE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_member_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_member_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_member_group_scope
        UNIQUE (member_group_id, tenant_id, system_id),
    CONSTRAINT ck_member_group_name CHECK (
        reference.is_nonblank(member_group_name)
    )
);

CREATE TABLE core.copy_group_control (
    copy_group_control_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    copy_group_id BIGINT NOT NULL,
    member_group_id BIGINT,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    copy_group_control_initial_load_date DATE,
    copy_group_control_last_run_time TIMESTAMPTZ,
    copy_group_control_last_run_value TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_copy_group_control_copy_group FOREIGN KEY (
        copy_group_id,
        tenant_id,
        system_id
    ) REFERENCES core.copy_group (
        copy_group_id,
        tenant_id,
        system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_group_control_member_group FOREIGN KEY (
        member_group_id,
        tenant_id,
        system_id
    ) REFERENCES core.member_group (
        member_group_id,
        tenant_id,
        system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_copy_group_control
        UNIQUE NULLS NOT DISTINCT (copy_group_id, member_group_id),
    CONSTRAINT ck_copy_group_control_last_run_value CHECK (
        copy_group_control_last_run_value IS NULL
        OR reference.is_nonblank(copy_group_control_last_run_value)
    )
);

CREATE TABLE core.copy (
    copy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    copy_group_id BIGINT NOT NULL,
    ingestion_object_mapping_id BIGINT NOT NULL,
    copy_source_record_limit BIGINT,
    copy_source_record_limit_attribute VARCHAR(400),
    chunk_type_id BIGINT,
    copy_source_initial_sql_script TEXT,
    copy_source_incremental_sql_script TEXT,
    copy_source_file_name TEXT,
    copy_source_file_pattern TEXT,
    copy_source_file_delimiter VARCHAR(20),
    source_file_type_id BIGINT,
    copy_source_order INTEGER NOT NULL,
    source_data_operation_id BIGINT NOT NULL,
    target_data_operation_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_copy_group FOREIGN KEY (copy_group_id)
        REFERENCES core.copy_group (copy_group_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_ingestion_object_mapping FOREIGN KEY (
        ingestion_object_mapping_id
    ) REFERENCES core.ingestion_object_mapping (ingestion_object_mapping_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_copy_chunk_type FOREIGN KEY (chunk_type_id)
        REFERENCES reference.chunk_type (chunk_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_source_file_type FOREIGN KEY (source_file_type_id)
        REFERENCES reference.file_type (file_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_source_data_operation FOREIGN KEY (
        source_data_operation_id
    ) REFERENCES reference.data_operation (data_operation_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_target_data_operation FOREIGN KEY (
        target_data_operation_id
    ) REFERENCES reference.data_operation (data_operation_id) ON DELETE NO ACTION,
    CONSTRAINT uq_copy_group_mapping
        UNIQUE (copy_group_id, ingestion_object_mapping_id),
    CONSTRAINT uq_copy_group_order
        UNIQUE (copy_group_id, copy_source_order)
);

CREATE TABLE core.process_group (
    process_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    zone_id BIGINT NOT NULL,
    process_group_name VARCHAR(200) NOT NULL,
    process_group_description TEXT,
    copy_group_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_process_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group_copy_group FOREIGN KEY (
        copy_group_id,
        tenant_id,
        system_id
    ) REFERENCES core.copy_group (
        copy_group_id,
        tenant_id,
        system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_process_group_name CHECK (
        reference.is_nonblank(process_group_name)
    )
);

CREATE TABLE core.process (
    process_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    process_execution_order INTEGER NOT NULL,
    process_location TEXT NOT NULL,
    process_executable TEXT NOT NULL,
    process_type_id BIGINT NOT NULL,
    process_group_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_process_object_connection FOREIGN KEY (
        object_id,
        connection_id
    ) REFERENCES core.object (object_id, connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_type FOREIGN KEY (process_type_id)
        REFERENCES reference.process_type (process_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group FOREIGN KEY (process_group_id)
        REFERENCES core.process_group (process_group_id) ON DELETE NO ACTION,
    CONSTRAINT uq_process_group_order
        UNIQUE (process_group_id, process_execution_order, process_location, process_executable),
    CONSTRAINT ck_process_execution_order CHECK (process_execution_order > 0),
    CONSTRAINT ck_process_location CHECK (
        reference.is_nonblank(process_location)
    ),
    CONSTRAINT ck_process_executable CHECK (
        reference.is_nonblank(process_executable)
    )
);

CREATE UNIQUE INDEX ux_project_code_ci
    ON core.project (lower(btrim(project_code)));
CREATE UNIQUE INDEX ux_tenant_code_ci
    ON core.tenant (lower(btrim(tenant_code)));
CREATE UNIQUE INDEX ux_system_code_ci
    ON core.system (lower(btrim(system_code)));
CREATE UNIQUE INDEX ux_connection_system_tenant_code_ci
    ON core.connection (
        system_id,
        tenant_id,
        lower(btrim(connection_code))
    );
CREATE UNIQUE INDEX ux_object_connection_schema_name_ci
    ON core.object (
        connection_id,
        lower(btrim(object_schema)),
        lower(btrim(object_name))
    );
CREATE UNIQUE INDEX ux_attribute_object_name_ci
    ON core.attribute (object_id, lower(btrim(attribute_name)));
CREATE UNIQUE INDEX ux_copy_group_name_ci
    ON core.copy_group (
        tenant_id,
        system_id,
        lower(btrim(copy_group_name))
    );
CREATE UNIQUE INDEX ux_member_group_name_ci
    ON core.member_group (
        tenant_id,
        system_id,
        lower(btrim(member_group_name))
    );
CREATE UNIQUE INDEX ux_process_group_name_ci
    ON core.process_group (
        tenant_id,
        system_id,
        zone_id,
        lower(btrim(process_group_name))
    );

CREATE INDEX ix_tenant_project_active ON core.tenant (project_id, is_active);
CREATE INDEX ix_system_system_type_active ON core.system (system_type_id, is_active);
CREATE INDEX ix_connection_tenant_active ON core.connection (tenant_id, is_active);
CREATE INDEX ix_connection_system_active ON core.connection (system_id, is_active);
CREATE INDEX ix_object_connection_active ON core.object (connection_id, is_active);
CREATE INDEX ix_object_zone_active ON core.object (zone_id, is_active);
CREATE INDEX ix_attribute_object_active ON core.attribute (object_id, is_active);
CREATE INDEX ix_ingestion_object_target_active
    ON core.ingestion_object_mapping (target_object_id, is_active);
CREATE INDEX ix_ingestion_attribute_target_active
    ON core.ingestion_attribute_mapping (target_attribute_id, is_active);
CREATE INDEX ix_system_notebook_path_notebook
    ON core.system_notebook_path (system_notebook_id, system_id);
CREATE INDEX ix_connection_location_type_environment
    ON core.connection_location (location_type_id, environment_id, connection_id);
CREATE INDEX ix_copy_group_system_active
    ON core.copy_group (system_id, is_active, tenant_id);
CREATE INDEX ix_member_group_system
    ON core.member_group (system_id, tenant_id);
CREATE INDEX ix_copy_group_control_member
    ON core.copy_group_control (member_group_id, copy_group_id);
CREATE INDEX ix_copy_mapping_active
    ON core.copy (ingestion_object_mapping_id, is_active);
CREATE INDEX ix_process_group_copy_active
    ON core.process_group (copy_group_id, is_active);
CREATE INDEX ix_process_group_zone_active
    ON core.process_group (zone_id, is_active, tenant_id, system_id);
CREATE INDEX ix_process_connection_active
    ON core.process (connection_id, is_active);
CREATE INDEX ix_process_object_active
    ON core.process (object_id, is_active);
CREATE INDEX ix_process_process_type_active
    ON core.process (process_type_id, is_active);
