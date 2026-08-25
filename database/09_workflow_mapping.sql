-- GDS ETL Workbench Release 1: exact combined Mapping Section.

CREATE TABLE workflow.mapping_source_system_dependency (
    mapping_source_system_dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    modeled_entity_type VARCHAR(30) NOT NULL,
    source_system_id BIGINT NOT NULL,
    source_system_dependency_order INTEGER NOT NULL DEFAULT 0,
    mapping_source_system_dependency_status VARCHAR(20) NOT NULL DEFAULT 'active',
    mapping_source_system_dependency_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_mapping_source_dependency_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_source_dependency_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_source_dependency_binding
        UNIQUE (model_id, modeled_entity_type, source_system_id),
    CONSTRAINT ck_mapping_source_dependency_entity_type CHECK (
        modeled_entity_type IN ('logical_entity', 'dimensional_entity')
    ),
    CONSTRAINT ck_mapping_source_dependency_order CHECK (
        source_system_dependency_order >= 0
    ),
    CONSTRAINT ck_mapping_source_dependency_status CHECK (
        mapping_source_system_dependency_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE TABLE workflow.mapping_object (
    mapping_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    output_template_id BIGINT,
    object_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_entity_id BIGINT,
    dimensional_entity_id BIGINT,
    object_dependency_order INTEGER NOT NULL DEFAULT 0,
    artifact_type VARCHAR(30),
    artifact_generation_instructions TEXT,
    mapping_profile_key VARCHAR(100),
    mapping_profile_version VARCHAR(50),
    mapping_profile_schema_digest CHAR(64),
    mapping_package_document JSONB,
    mapping_package_digest CHAR(64),
    object_mapping_transformation_document JSONB,
    object_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    object_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_object_mapping_source_dependency FOREIGN KEY (
        model_id,
        modeled_entity_type,
        source_system_id
    ) REFERENCES workflow.mapping_source_system_dependency (
        model_id,
        modeled_entity_type,
        source_system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_logical_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_dimensional_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_scope FOREIGN KEY (model_id, object_id)
        REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_object_witness UNIQUE (
        mapping_object_id,
        model_id,
        modeled_entity_type,
        object_id
    ),
    CONSTRAINT ck_object_mapping_typed_entity CHECK (
        (
            modeled_entity_type = 'logical_entity'
            AND logical_entity_id IS NOT NULL
            AND dimensional_entity_id IS NULL
        ) OR (
            modeled_entity_type = 'dimensional_entity'
            AND dimensional_entity_id IS NOT NULL
            AND logical_entity_id IS NULL
        )
    ),
    CONSTRAINT ck_object_mapping_dependency_order CHECK (
        object_dependency_order >= 0
    ),
    CONSTRAINT ck_object_mapping_authored_group CHECK (
        (
            artifact_type IS NULL
            AND artifact_generation_instructions IS NULL
            AND mapping_profile_key IS NULL
            AND mapping_profile_version IS NULL
            AND mapping_profile_schema_digest IS NULL
            AND mapping_package_document IS NULL
            AND mapping_package_digest IS NULL
            AND object_mapping_transformation_document IS NULL
        ) OR (
            artifact_type IS NOT NULL
            AND artifact_generation_instructions IS NOT NULL
            AND mapping_profile_key IS NOT NULL
            AND mapping_profile_version IS NOT NULL
            AND mapping_profile_schema_digest IS NOT NULL
            AND mapping_package_document IS NOT NULL
            AND mapping_package_digest IS NOT NULL
            AND object_mapping_transformation_document IS NOT NULL
        )
    ),
    CONSTRAINT ck_object_mapping_artifact_type CHECK (
        artifact_type IS NULL
        OR artifact_type IN ('sql_file', 'python_file', 'python_notebook')
    ),
    CONSTRAINT ck_object_mapping_instructions CHECK (
        artifact_generation_instructions IS NULL
        OR (
            reference.is_nonblank(artifact_generation_instructions)
            AND length(artifact_generation_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_object_mapping_profile_key CHECK (
        mapping_profile_key IS NULL
        OR mapping_profile_key ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_object_mapping_profile_version CHECK (
        mapping_profile_version IS NULL
        OR mapping_profile_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),
    CONSTRAINT ck_object_mapping_profile_digest CHECK (
        mapping_profile_schema_digest IS NULL
        OR mapping_profile_schema_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_object_mapping_package CHECK (
        mapping_package_document IS NULL
        OR (
            jsonb_typeof(mapping_package_document) = 'object'
            AND octet_length(mapping_package_document::TEXT) <= 524288
        )
    ),
    CONSTRAINT ck_object_mapping_package_digest CHECK (
        mapping_package_digest IS NULL
        OR mapping_package_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_object_mapping_transformation CHECK (
        object_mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(object_mapping_transformation_document) = 'object'
            AND octet_length(object_mapping_transformation_document::TEXT) <= 262144
            AND object_mapping_transformation_document ->> 'schema_version' = '1.0'
            AND object_mapping_transformation_document ->> 'transformation_kind'
                IN ('direct', 'derived')
        )
    ),
    CONSTRAINT ck_object_mapping_status CHECK (
        object_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_mapping_object_logical_binding
    ON workflow.mapping_object (
        model_id,
        logical_entity_id,
        object_id,
        source_system_id
    ) WHERE modeled_entity_type = 'logical_entity';
CREATE UNIQUE INDEX ux_mapping_object_dimensional_binding
    ON workflow.mapping_object (
        model_id,
        dimensional_entity_id,
        object_id,
        source_system_id
    ) WHERE modeled_entity_type = 'dimensional_entity';

CREATE TABLE workflow.mapping_attribute (
    mapping_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    output_template_id BIGINT,
    object_id BIGINT NOT NULL,
    attribute_id BIGINT NOT NULL,
    mapping_object_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_attribute_id BIGINT,
    dimensional_attribute_id BIGINT,
    attribute_mapping_transformation_document JSONB,
    attribute_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    attribute_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_attribute_mapping_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_parent FOREIGN KEY (
        mapping_object_id,
        model_id,
        modeled_entity_type,
        object_id
    ) REFERENCES workflow.mapping_object (
        mapping_object_id,
        model_id,
        modeled_entity_type,
        object_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_logical_attribute FOREIGN KEY (
        logical_attribute_id,
        model_id
    ) REFERENCES workflow.logical_attribute (logical_attribute_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_dimensional_attribute FOREIGN KEY (
        dimensional_attribute_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_attribute FOREIGN KEY (
        attribute_id,
        object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT ck_attribute_mapping_typed_attribute CHECK (
        (
            modeled_entity_type = 'logical_entity'
            AND logical_attribute_id IS NOT NULL
            AND dimensional_attribute_id IS NULL
        ) OR (
            modeled_entity_type = 'dimensional_entity'
            AND dimensional_attribute_id IS NOT NULL
            AND logical_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_attribute_mapping_transformation CHECK (
        attribute_mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(attribute_mapping_transformation_document) = 'object'
            AND octet_length(attribute_mapping_transformation_document::TEXT) <= 65536
            AND attribute_mapping_transformation_document ->> 'schema_version' = '1.0'
            AND attribute_mapping_transformation_document ->> 'transformation_kind'
                IN ('direct', 'expression')
        )
    ),
    CONSTRAINT ck_attribute_mapping_status CHECK (
        attribute_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_mapping_attribute_logical_binding
    ON workflow.mapping_attribute (
        model_id,
        mapping_object_id,
        logical_attribute_id,
        attribute_id
    ) WHERE modeled_entity_type = 'logical_entity';
CREATE UNIQUE INDEX ux_mapping_attribute_dimensional_binding
    ON workflow.mapping_attribute (
        model_id,
        mapping_object_id,
        dimensional_attribute_id,
        attribute_id
    ) WHERE modeled_entity_type = 'dimensional_entity';

CREATE INDEX ix_mapping_object_model_package_status
    ON workflow.mapping_object (
        model_id,
        modeled_entity_type,
        object_id,
        source_system_id,
        object_mapping_status
    );
CREATE INDEX ix_mapping_source_dependency_wave
    ON workflow.mapping_source_system_dependency (
        model_id,
        modeled_entity_type,
        source_system_dependency_order,
        source_system_id
    );
CREATE INDEX ix_mapping_source_dependency_system
    ON workflow.mapping_source_system_dependency (
        source_system_id,
        mapping_source_system_dependency_status,
        model_id
    );
CREATE INDEX ix_mapping_object_object_wave
    ON workflow.mapping_object (
        model_id,
        modeled_entity_type,
        object_dependency_order,
        object_id
    );
CREATE INDEX ix_mapping_object_source_system
    ON workflow.mapping_object (model_id, source_system_id);
CREATE INDEX ix_mapping_attribute_parent
    ON workflow.mapping_attribute (model_id, mapping_object_id, attribute_mapping_status);
CREATE INDEX ix_mapping_attribute_target
    ON workflow.mapping_attribute (model_id, object_id, attribute_id);
CREATE INDEX ix_mapping_attribute_logical_attribute
    ON workflow.mapping_attribute (model_id, logical_attribute_id)
    WHERE modeled_entity_type = 'logical_entity';
CREATE INDEX ix_mapping_attribute_dimensional_attribute
    ON workflow.mapping_attribute (model_id, dimensional_attribute_id)
    WHERE modeled_entity_type = 'dimensional_entity';
