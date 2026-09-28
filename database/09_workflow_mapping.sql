-- Entity-owned Mapping; physical registration is independent of authoring.

CREATE TABLE workflow.mapping_object (
    mapping_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_entity_id BIGINT,
    dimensional_entity_id BIGINT,
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
    CONSTRAINT fk_mapping_object_logical_entity FOREIGN KEY (logical_entity_id, model_id)
        REFERENCES workflow.logical_entity (logical_entity_id, model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_object_dimensional_entity FOREIGN KEY (dimensional_entity_id, model_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_mapping_object_typed_entity CHECK (
        (modeled_entity_type = 'logical_entity' AND logical_entity_id IS NOT NULL
            AND dimensional_entity_id IS NULL)
        OR (modeled_entity_type = 'dimensional_entity' AND dimensional_entity_id IS NOT NULL
            AND logical_entity_id IS NULL)
    ),
    CONSTRAINT uq_mapping_object_logical_witness UNIQUE (
        mapping_object_id, model_id, modeled_entity_type, logical_entity_id
    ),
    CONSTRAINT uq_mapping_object_dimensional_witness UNIQUE (
        mapping_object_id, model_id, modeled_entity_type, dimensional_entity_id
    ),
    CONSTRAINT fk_mapping_object_source_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,

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
    model_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_entity_id BIGINT,
    dimensional_entity_id BIGINT,
    logical_attribute_id BIGINT,
    dimensional_attribute_id BIGINT,
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
    CONSTRAINT fk_mapping_attribute_logical_parent FOREIGN KEY (
        mapping_object_id, model_id, modeled_entity_type, logical_entity_id
    ) REFERENCES workflow.mapping_object (
        mapping_object_id, model_id, modeled_entity_type, logical_entity_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_attribute_dimensional_parent FOREIGN KEY (
        mapping_object_id, model_id, modeled_entity_type, dimensional_entity_id
    ) REFERENCES workflow.mapping_object (
        mapping_object_id, model_id, modeled_entity_type, dimensional_entity_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_attribute_logical FOREIGN KEY (
        logical_attribute_id, logical_entity_id, model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id, logical_entity_id, model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_attribute_dimensional FOREIGN KEY (
        dimensional_attribute_id, dimensional_entity_id, model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id, dimensional_entity_id, model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_mapping_attribute_typed_entity CHECK (
        (modeled_entity_type = 'logical_entity' AND logical_entity_id IS NOT NULL
            AND logical_attribute_id IS NOT NULL AND dimensional_entity_id IS NULL
            AND dimensional_attribute_id IS NULL)
        OR (modeled_entity_type = 'dimensional_entity' AND dimensional_entity_id IS NOT NULL
            AND dimensional_attribute_id IS NOT NULL AND logical_entity_id IS NULL
            AND logical_attribute_id IS NULL)
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

-- Supports dependency-ordered target reads for Mapping and Code Generation.
CREATE INDEX ix_mapping_object_model_wave
    ON workflow.mapping_object (
        model_id,
        object_dependency_order,
        modeled_entity_type,
        logical_entity_id,
        dimensional_entity_id,
        source_system_id
    )
    WHERE object_mapping_status = 'active';

CREATE UNIQUE INDEX ux_mapping_object_logical_system
    ON workflow.mapping_object (model_id, logical_entity_id, source_system_id)
    WHERE modeled_entity_type = 'logical_entity';
CREATE UNIQUE INDEX ux_mapping_object_dimensional_system
    ON workflow.mapping_object (model_id, dimensional_entity_id, source_system_id)
    WHERE modeled_entity_type = 'dimensional_entity';
CREATE UNIQUE INDEX ux_mapping_attribute_logical
    ON workflow.mapping_attribute (mapping_object_id, logical_attribute_id)
    WHERE logical_attribute_id IS NOT NULL;
CREATE UNIQUE INDEX ux_mapping_attribute_dimensional
    ON workflow.mapping_attribute (mapping_object_id, dimensional_attribute_id)
    WHERE dimensional_attribute_id IS NOT NULL;
