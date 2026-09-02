-- GDS ETL Workbench Release 1: Model Bindings and Mapping Section.

CREATE TABLE workflow.model_object_binding (
    model_object_binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_entity_id BIGINT,
    dimensional_entity_id BIGINT,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    model_object_binding_status VARCHAR(20) NOT NULL DEFAULT 'active',
    model_object_binding_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_object_binding_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_object_binding_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_object_binding_logical_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_model_object_binding_dimensional_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_model_object_binding_model_object
        UNIQUE (model_id, object_id),
    CONSTRAINT ck_model_object_binding_typed_entity CHECK (
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
    CONSTRAINT ck_model_object_binding_status CHECK (
        model_object_binding_status IN ('active', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_model_object_binding_logical_entity
    ON workflow.model_object_binding (model_id, logical_entity_id)
    WHERE modeled_entity_type = 'logical_entity';

CREATE UNIQUE INDEX ux_model_object_binding_dimensional_entity
    ON workflow.model_object_binding (model_id, dimensional_entity_id)
    WHERE modeled_entity_type = 'dimensional_entity';

CREATE TABLE workflow.model_attribute_binding (
    model_attribute_binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_object_binding_id BIGINT NOT NULL,
    logical_attribute_id BIGINT,
    dimensional_attribute_id BIGINT,
    attribute_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    model_attribute_binding_status VARCHAR(20) NOT NULL DEFAULT 'active',
    model_attribute_binding_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_attribute_binding_parent
        FOREIGN KEY (model_object_binding_id)
        REFERENCES workflow.model_object_binding (model_object_binding_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_model_attribute_binding_target
        FOREIGN KEY (attribute_id)
        REFERENCES core.attribute (attribute_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_model_attribute_binding_logical
        FOREIGN KEY (logical_attribute_id)
        REFERENCES workflow.logical_attribute (logical_attribute_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_model_attribute_binding_dimensional
        FOREIGN KEY (dimensional_attribute_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_model_attribute_binding_target
        UNIQUE (model_object_binding_id, attribute_id),
    CONSTRAINT ck_model_attribute_binding_typed CHECK (
        num_nonnulls(logical_attribute_id, dimensional_attribute_id) = 1
    ),
    CONSTRAINT ck_model_attribute_binding_status CHECK (
        model_attribute_binding_status IN ('active', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_model_attribute_binding_logical
    ON workflow.model_attribute_binding (logical_attribute_id)
    WHERE logical_attribute_id IS NOT NULL;

CREATE UNIQUE INDEX ux_model_attribute_binding_dimensional
    ON workflow.model_attribute_binding (dimensional_attribute_id)
    WHERE dimensional_attribute_id IS NOT NULL;

-- Dimensional physical sources are realized Silver Objects, not Model Inputs.
-- Status, modeled layer, and active Mapping coverage remain authoritative
-- Model Change Set validations because a foreign key cannot express them.
ALTER TABLE workflow.dimensional_entity_source_mapping
    ADD CONSTRAINT fk_dimensional_entity_source_binding FOREIGN KEY (
        model_id,
        source_object_id
    ) REFERENCES workflow.model_object_binding (model_id, object_id)
        ON DELETE NO ACTION;

CREATE TABLE workflow.mapping_source_system_dependency (
    mapping_source_system_dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    source_system_id BIGINT NOT NULL,
    source_system_dependency_order INTEGER NOT NULL DEFAULT 0,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
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
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE TABLE workflow.mapping_object (
    mapping_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    model_object_binding_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    output_template_id BIGINT,
    object_dependency_order INTEGER NOT NULL DEFAULT 0,
    mapping_transformation_document JSONB,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    object_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    object_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_mapping_object_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_object_binding FOREIGN KEY (model_object_binding_id)
        REFERENCES workflow.model_object_binding (model_object_binding_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_object_source_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_object_binding_system UNIQUE (
        model_object_binding_id,
        source_system_id
    ),
    CONSTRAINT ck_mapping_object_dependency_order CHECK (
        object_dependency_order >= 0
    ),
    CONSTRAINT ck_mapping_object_transformation CHECK (
        mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(mapping_transformation_document) = 'object'
            AND octet_length(mapping_transformation_document::TEXT) <= 524288
        )
    ),
    CONSTRAINT ck_mapping_object_status CHECK (
        object_mapping_status IN ('active', 'inactive', 'deprecated')
    )
);

CREATE TABLE workflow.mapping_attribute (
    mapping_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mapping_object_id BIGINT NOT NULL,
    model_attribute_binding_id BIGINT NOT NULL,
    output_template_id BIGINT,
    attribute_mapping_transformation_document JSONB,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    attribute_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    attribute_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_mapping_attribute_parent FOREIGN KEY (mapping_object_id)
        REFERENCES workflow.mapping_object (mapping_object_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_attribute_binding FOREIGN KEY (
        model_attribute_binding_id
    ) REFERENCES workflow.model_attribute_binding (
        model_attribute_binding_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_attribute_target UNIQUE (
        mapping_object_id,
        model_attribute_binding_id
    ),
    CONSTRAINT ck_mapping_attribute_transformation CHECK (
        attribute_mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(attribute_mapping_transformation_document) = 'object'
            AND octet_length(attribute_mapping_transformation_document::TEXT) <= 65536
        )
    ),
    CONSTRAINT ck_mapping_attribute_status CHECK (
        attribute_mapping_status IN ('active', 'inactive', 'deprecated')
    )
);

-- Supports dependency-ordered Mapping reads for one Model and modeled layer.
CREATE INDEX ix_mapping_source_dependency_wave
    ON workflow.mapping_source_system_dependency (
        model_id,
        modeled_entity_type,
        source_system_dependency_order,
        source_system_id
    )
    WHERE mapping_source_system_dependency_status = 'active';

-- Supports dependency-ordered target reads for Mapping and Code Generation.
CREATE INDEX ix_mapping_object_model_wave
    ON workflow.mapping_object (
        model_id,
        object_dependency_order,
        model_object_binding_id,
        source_system_id
    )
    WHERE object_mapping_status = 'active';
