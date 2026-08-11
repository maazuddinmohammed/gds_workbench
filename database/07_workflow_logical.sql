-- GDS ETL Workbench Release 1: exact seven-table Logical Section.

CREATE TABLE workflow.logical_submodel (
    logical_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_submodel_name VARCHAR(255) NOT NULL,
    logical_submodel_definition TEXT NOT NULL,
    logical_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_submodel_id_model UNIQUE (logical_submodel_id, model_id),
    CONSTRAINT ck_logical_submodel_name CHECK (reference.is_nonblank(logical_submodel_name)),
    CONSTRAINT ck_logical_submodel_definition CHECK (
        reference.is_nonblank(logical_submodel_definition)
    ),
    CONSTRAINT ck_logical_submodel_status CHECK (
        logical_submodel_status IN ('active', 'needs_review', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_logical_submodel_model_name
    ON workflow.logical_submodel (model_id, lower(btrim(logical_submodel_name)));

CREATE TABLE workflow.logical_entity (
    logical_entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_entity_name VARCHAR(255) NOT NULL,
    logical_entity_definition TEXT NOT NULL,
    logical_entity_type VARCHAR(50) NOT NULL,
    logical_entity_type_detail TEXT,
    logical_entity_grain TEXT NOT NULL,
    logical_entity_dependency_order INTEGER NOT NULL DEFAULT 0,
    logical_entity_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    logical_entity_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_entity_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_entity_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_id_model UNIQUE (logical_entity_id, model_id),
    CONSTRAINT ck_logical_entity_name CHECK (reference.is_nonblank(logical_entity_name)),
    CONSTRAINT ck_logical_entity_definition CHECK (
        reference.is_nonblank(logical_entity_definition)
    ),
    CONSTRAINT ck_logical_entity_type CHECK (
        logical_entity_type IN (
            'core', 'reference', 'transaction', 'event', 'bridge',
            'history', 'snapshot', 'association', 'aggregate', 'other'
        )
    ),
    CONSTRAINT ck_logical_entity_type_detail CHECK (
        (logical_entity_type = 'other' AND reference.is_nonblank(logical_entity_type_detail))
        OR (logical_entity_type <> 'other' AND logical_entity_type_detail IS NULL)
    ),
    CONSTRAINT ck_logical_entity_grain CHECK (reference.is_nonblank(logical_entity_grain)),
    CONSTRAINT ck_logical_entity_dependency_order CHECK (
        logical_entity_dependency_order >= 0
    ),
    CONSTRAINT ck_logical_entity_confidence CHECK (
        logical_entity_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_logical_entity_status CHECK (
        logical_entity_status IN ('active', 'needs_review', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_logical_entity_model_name
    ON workflow.logical_entity (model_id, lower(btrim(logical_entity_name)));

CREATE TABLE workflow.logical_entity_submodel (
    logical_entity_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_entity_id BIGINT NOT NULL,
    logical_submodel_id BIGINT NOT NULL,
    logical_entity_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_entity_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_entity_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_submodel_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_submodel_submodel FOREIGN KEY (
        logical_submodel_id,
        model_id
    ) REFERENCES workflow.logical_submodel (logical_submodel_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_submodel_id_model
        UNIQUE (logical_entity_submodel_id, model_id),
    CONSTRAINT uq_logical_entity_submodel_identity
        UNIQUE (model_id, logical_entity_id, logical_submodel_id),
    CONSTRAINT ck_logical_entity_submodel_status CHECK (
        logical_entity_submodel_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE TABLE workflow.logical_attribute (
    logical_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_entity_id BIGINT NOT NULL,
    logical_attribute_name VARCHAR(255) NOT NULL,
    logical_attribute_definition TEXT NOT NULL,
    logical_attribute_data_type VARCHAR(100) NOT NULL,
    logical_attribute_is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    logical_attribute_is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_is_natural_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_is_surrogate_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_ordinal_position INTEGER NOT NULL,
    logical_attribute_is_audit_column BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_attribute_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_logical_attribute_id_model UNIQUE (logical_attribute_id, model_id),
    CONSTRAINT uq_logical_attribute_witness
        UNIQUE (logical_attribute_id, logical_entity_id, model_id),
    CONSTRAINT ck_logical_attribute_name CHECK (
        reference.is_nonblank(logical_attribute_name)
    ),
    CONSTRAINT ck_logical_attribute_definition CHECK (
        reference.is_nonblank(logical_attribute_definition)
    ),
    CONSTRAINT ck_logical_attribute_data_type CHECK (
        reference.is_nonblank(logical_attribute_data_type)
    ),
    CONSTRAINT ck_logical_attribute_key_origin CHECK (
        NOT (
            logical_attribute_is_natural_key
            AND logical_attribute_is_surrogate_key
        )
    ),
    CONSTRAINT ck_logical_attribute_key_nullable CHECK (
        NOT (
            logical_attribute_is_primary_key
            OR logical_attribute_is_natural_key
            OR logical_attribute_is_surrogate_key
        ) OR NOT logical_attribute_is_nullable
    ),
    CONSTRAINT ck_logical_attribute_ordinal CHECK (
        logical_attribute_ordinal_position > 0
    ),
    CONSTRAINT ck_logical_attribute_status CHECK (
        logical_attribute_status IN ('active', 'needs_review', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_logical_attribute_entity_name
    ON workflow.logical_attribute (
        model_id,
        logical_entity_id,
        lower(btrim(logical_attribute_name))
    );

CREATE TABLE workflow.logical_entity_source_mapping (
    logical_entity_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_entity_id BIGINT NOT NULL,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    modeling_assertion_record_id BIGINT,
    logical_entity_source_mapping_order INTEGER,
    logical_entity_source_mapping_rationale TEXT NOT NULL,
    logical_entity_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_entity_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_entity_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_scope FOREIGN KEY (
        model_id,
        source_object_id
    ) REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_source_id_model
        UNIQUE (logical_entity_source_mapping_id, model_id),
    CONSTRAINT uq_logical_entity_source_witness UNIQUE (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        model_id
    ),
    CONSTRAINT ck_logical_entity_source_typed_source CHECK (
        (
            support_source_type = 'object'
            AND source_object_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND source_object_id IS NULL
        )
    ),
    CONSTRAINT ck_logical_entity_source_order CHECK (
        logical_entity_source_mapping_order IS NULL
        OR logical_entity_source_mapping_order > 0
    ),
    CONSTRAINT ck_logical_entity_source_rationale CHECK (
        reference.is_nonblank(logical_entity_source_mapping_rationale)
    ),
    CONSTRAINT ck_logical_entity_source_status CHECK (
        logical_entity_source_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_logical_entity_source_object
    ON workflow.logical_entity_source_mapping (
        model_id,
        logical_entity_id,
        source_object_id
    ) WHERE support_source_type = 'object';
CREATE UNIQUE INDEX ux_logical_entity_source_assertion
    ON workflow.logical_entity_source_mapping (
        model_id,
        logical_entity_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion';

CREATE TABLE workflow.logical_attribute_source_mapping (
    logical_attribute_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_entity_source_mapping_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    logical_attribute_id BIGINT NOT NULL,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    source_attribute_id BIGINT,
    modeling_assertion_record_id BIGINT,
    logical_attribute_source_mapping_order INTEGER,
    logical_attribute_source_mapping_rationale TEXT NOT NULL,
    logical_attribute_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_attribute_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_attribute_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_parent FOREIGN KEY (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        model_id
    ) REFERENCES workflow.logical_entity_source_mapping (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_attribute FOREIGN KEY (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_physical FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_attribute_source_id_model
        UNIQUE (logical_attribute_source_mapping_id, model_id),
    CONSTRAINT ck_logical_attribute_source_typed_source CHECK (
        (
            support_source_type = 'attribute'
            AND logical_entity_source_mapping_id IS NOT NULL
            AND source_object_id IS NOT NULL
            AND source_attribute_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND logical_entity_source_mapping_id IS NULL
            AND source_object_id IS NULL
            AND source_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_logical_attribute_source_order CHECK (
        logical_attribute_source_mapping_order IS NULL
        OR logical_attribute_source_mapping_order > 0
    ),
    CONSTRAINT ck_logical_attribute_source_rationale CHECK (
        reference.is_nonblank(logical_attribute_source_mapping_rationale)
    ),
    CONSTRAINT ck_logical_attribute_source_status CHECK (
        logical_attribute_source_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_logical_attribute_source_physical
    ON workflow.logical_attribute_source_mapping (
        model_id,
        logical_entity_source_mapping_id,
        logical_attribute_id,
        source_attribute_id
    ) WHERE support_source_type = 'attribute';
CREATE UNIQUE INDEX ux_logical_attribute_source_assertion
    ON workflow.logical_attribute_source_mapping (
        model_id,
        logical_attribute_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion';

CREATE TABLE workflow.logical_relationship (
    logical_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    logical_relationship_name VARCHAR(255) NOT NULL,
    logical_relationship_definition TEXT NOT NULL,
    logical_relationship_from_entity_id BIGINT NOT NULL,
    logical_relationship_from_attribute_id BIGINT NOT NULL,
    logical_relationship_to_entity_id BIGINT NOT NULL,
    logical_relationship_to_attribute_id BIGINT NOT NULL,
    logical_relationship_cardinality VARCHAR(50) NOT NULL,
    logical_relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    logical_relationship_basis TEXT NOT NULL,
    logical_relationship_cardinality_basis TEXT NOT NULL,
    logical_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_relationship_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_from_entity FOREIGN KEY (
        logical_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_to_entity FOREIGN KEY (
        logical_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_from_attribute FOREIGN KEY (
        logical_relationship_from_attribute_id,
        logical_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_to_attribute FOREIGN KEY (
        logical_relationship_to_attribute_id,
        logical_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_relationship_id_model
        UNIQUE (logical_relationship_id, model_id),
    CONSTRAINT ck_logical_relationship_distinct_endpoints CHECK (
        (logical_relationship_from_entity_id, logical_relationship_from_attribute_id)
        <> (logical_relationship_to_entity_id, logical_relationship_to_attribute_id)
    ),
    CONSTRAINT ck_logical_relationship_name CHECK (
        reference.is_nonblank(logical_relationship_name)
    ),
    CONSTRAINT ck_logical_relationship_definition CHECK (
        reference.is_nonblank(logical_relationship_definition)
    ),
    CONSTRAINT ck_logical_relationship_cardinality CHECK (
        logical_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'
        )
    ),
    CONSTRAINT ck_logical_relationship_confidence CHECK (
        logical_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_logical_relationship_bases CHECK (
        reference.is_nonblank(logical_relationship_basis)
        AND reference.is_nonblank(logical_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_logical_relationship_status CHECK (
        logical_relationship_status IN ('active', 'needs_review', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_logical_relationship_identity
    ON workflow.logical_relationship (
        model_id,
        logical_relationship_from_entity_id,
        logical_relationship_from_attribute_id,
        logical_relationship_to_entity_id,
        logical_relationship_to_attribute_id,
        lower(btrim(logical_relationship_name))
    );

-- Every Logical mutation participates in the one-revision transaction guard.

-- Supporting read, impact, and parent indexes.
CREATE INDEX ix_logical_submodel_status ON workflow.logical_submodel (model_id, logical_submodel_status);
CREATE INDEX ix_logical_entity_status_order ON workflow.logical_entity (model_id, logical_entity_status, logical_entity_dependency_order);
CREATE INDEX ix_logical_entity_submodel_submodel ON workflow.logical_entity_submodel (model_id, logical_submodel_id);
CREATE INDEX ix_logical_attribute_entity_status ON workflow.logical_attribute (model_id, logical_entity_id, logical_attribute_status);
CREATE INDEX ix_logical_entity_source_object
    ON workflow.logical_entity_source_mapping (model_id, source_object_id)
    WHERE support_source_type = 'object';
CREATE INDEX ix_logical_entity_source_assertion
    ON workflow.logical_entity_source_mapping (
        model_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion';
CREATE INDEX ix_logical_attribute_source_physical
    ON workflow.logical_attribute_source_mapping (
        model_id,
        source_object_id,
        source_attribute_id
    ) WHERE support_source_type = 'attribute';
CREATE INDEX ix_logical_attribute_source_assertion
    ON workflow.logical_attribute_source_mapping (
        model_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion';
CREATE INDEX ix_logical_attribute_source_target ON workflow.logical_attribute_source_mapping (model_id, logical_attribute_id);
CREATE INDEX ix_logical_relationship_to ON workflow.logical_relationship (model_id, logical_relationship_to_entity_id, logical_relationship_to_attribute_id);
