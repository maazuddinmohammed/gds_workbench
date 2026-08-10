-- GDS ETL Workbench Release 1: exact seven-table Dimensional Section.

CREATE TABLE workflow.dimensional_submodel (
    dimensional_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_submodel_name VARCHAR(255) NOT NULL,
    dimensional_submodel_definition TEXT NOT NULL,
    dimensional_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_submodel_id_model
        UNIQUE (dimensional_submodel_id, model_id),
    CONSTRAINT ck_dimensional_submodel_name CHECK (
        reference.is_nonblank(dimensional_submodel_name)
    ),
    CONSTRAINT ck_dimensional_submodel_definition CHECK (
        reference.is_nonblank(dimensional_submodel_definition)
    ),
    CONSTRAINT ck_dimensional_submodel_status CHECK (
        dimensional_submodel_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_submodel_effective_name
    ON workflow.dimensional_submodel (
        model_id,
        lower(btrim(dimensional_submodel_name))
    ) WHERE dimensional_submodel_status IN ('active', 'needs_review');

CREATE TABLE workflow.dimensional_entity (
    dimensional_entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_entity_name VARCHAR(255) NOT NULL,
    dimensional_entity_definition TEXT NOT NULL,
    dimensional_entity_type VARCHAR(20) NOT NULL,
    dimensional_fact_type VARCHAR(30),
    dimensional_entity_grain_definition TEXT,
    dimensional_entity_dependency_order INTEGER NOT NULL DEFAULT 0,
    dimensional_entity_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    dimensional_entity_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_entity_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_entity_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_id_model
        UNIQUE (dimensional_entity_id, model_id),
    CONSTRAINT ck_dimensional_entity_name CHECK (
        reference.is_nonblank(dimensional_entity_name)
    ),
    CONSTRAINT ck_dimensional_entity_definition CHECK (
        reference.is_nonblank(dimensional_entity_definition)
    ),
    CONSTRAINT ck_dimensional_entity_type CHECK (
        dimensional_entity_type IN ('fact', 'dimension', 'bridge')
    ),
    CONSTRAINT ck_dimensional_fact_type CHECK (
        (
            dimensional_entity_type = 'fact'
            AND dimensional_fact_type IN (
                'transaction', 'periodic_snapshot',
                'accumulating_snapshot', 'factless'
            )
        ) OR (
            dimensional_entity_type <> 'fact'
            AND dimensional_fact_type IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_entity_grain CHECK (
        (
            dimensional_entity_type IN ('fact', 'bridge')
            AND reference.is_nonblank(dimensional_entity_grain_definition)
        ) OR (
            dimensional_entity_type = 'dimension'
            AND (
                dimensional_entity_grain_definition IS NULL
                OR reference.is_nonblank(dimensional_entity_grain_definition)
            )
        )
    ),
    CONSTRAINT ck_dimensional_entity_dependency_order CHECK (
        dimensional_entity_dependency_order >= 0
    ),
    CONSTRAINT ck_dimensional_entity_confidence CHECK (
        dimensional_entity_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_dimensional_entity_status CHECK (
        dimensional_entity_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_entity_effective_name
    ON workflow.dimensional_entity (
        model_id,
        lower(btrim(dimensional_entity_name))
    ) WHERE dimensional_entity_status IN ('active', 'needs_review');

CREATE TABLE workflow.dimensional_entity_submodel (
    dimensional_entity_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_submodel_id BIGINT NOT NULL,
    dimensional_entity_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_entity_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_entity_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_submodel_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_submodel_submodel FOREIGN KEY (
        dimensional_submodel_id,
        model_id
    ) REFERENCES workflow.dimensional_submodel (dimensional_submodel_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_submodel_id_model
        UNIQUE (dimensional_entity_submodel_id, model_id),
    CONSTRAINT ck_dimensional_entity_submodel_status CHECK (
        dimensional_entity_submodel_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_entity_submodel_effective
    ON workflow.dimensional_entity_submodel (
        model_id,
        dimensional_entity_id,
        dimensional_submodel_id
    ) WHERE dimensional_entity_submodel_status IN ('active', 'needs_review');

CREATE TABLE workflow.dimensional_attribute (
    dimensional_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_attribute_name VARCHAR(255) NOT NULL,
    dimensional_attribute_definition TEXT NOT NULL,
    dimensional_attribute_data_type VARCHAR(100) NOT NULL,
    dimensional_attribute_is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_attribute_ordinal_position INTEGER NOT NULL,
    dimensional_attribute_role VARCHAR(30) NOT NULL,
    dimensional_attribute_key_role VARCHAR(20) NOT NULL DEFAULT 'none',
    dimensional_attribute_is_grain_component BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_additivity VARCHAR(30),
    dimensional_attribute_default_aggregation VARCHAR(100),
    dimensional_attribute_aggregation_basis TEXT,
    dimensional_attribute_change_behavior VARCHAR(20),
    dimensional_attribute_is_audit_column BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    dimensional_attribute_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_attribute_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_attribute_id_model
        UNIQUE (dimensional_attribute_id, model_id),
    CONSTRAINT uq_dimensional_attribute_witness
        UNIQUE (dimensional_attribute_id, dimensional_entity_id, model_id),
    CONSTRAINT ck_dimensional_attribute_name CHECK (
        reference.is_nonblank(dimensional_attribute_name)
    ),
    CONSTRAINT ck_dimensional_attribute_definition CHECK (
        reference.is_nonblank(dimensional_attribute_definition)
    ),
    CONSTRAINT ck_dimensional_attribute_data_type CHECK (
        reference.is_nonblank(dimensional_attribute_data_type)
    ),
    CONSTRAINT ck_dimensional_attribute_ordinal CHECK (
        dimensional_attribute_ordinal_position > 0
    ),
    CONSTRAINT ck_dimensional_attribute_role CHECK (
        dimensional_attribute_role IN (
            'key', 'descriptor', 'measure', 'degenerate_dimension',
            'bridge_weight', 'technical', 'audit'
        )
    ),
    CONSTRAINT ck_dimensional_attribute_key_role CHECK (
        dimensional_attribute_key_role IN ('none', 'surrogate', 'business', 'foreign')
        AND (
            dimensional_attribute_key_role = 'none'
            OR dimensional_attribute_role IN ('key', 'technical')
        )
    ),
    CONSTRAINT ck_dimensional_measure_policy CHECK (
        (
            dimensional_attribute_role = 'measure'
            AND dimensional_attribute_additivity IN (
                'additive', 'semi_additive', 'non_additive'
            )
            AND reference.is_nonblank(dimensional_attribute_default_aggregation)
            AND (
                dimensional_attribute_additivity = 'additive'
                OR reference.is_nonblank(dimensional_attribute_aggregation_basis)
            )
        ) OR (
            dimensional_attribute_role <> 'measure'
            AND dimensional_attribute_additivity IS NULL
            AND dimensional_attribute_default_aggregation IS NULL
            AND dimensional_attribute_aggregation_basis IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_change_behavior CHECK (
        dimensional_attribute_change_behavior IS NULL
        OR dimensional_attribute_change_behavior IN (
            'fixed', 'overwrite', 'historize'
        )
    ),
    CONSTRAINT ck_dimensional_audit_role CHECK (
        dimensional_attribute_is_audit_column
        = (dimensional_attribute_role = 'audit')
    ),
    CONSTRAINT ck_dimensional_attribute_confidence CHECK (
        dimensional_attribute_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_dimensional_attribute_status CHECK (
        dimensional_attribute_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_attribute_effective_name
    ON workflow.dimensional_attribute (
        model_id,
        dimensional_entity_id,
        lower(btrim(dimensional_attribute_name))
    ) WHERE dimensional_attribute_status IN ('active', 'needs_review');

CREATE TABLE workflow.dimensional_entity_source_mapping (
    dimensional_entity_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_entity_id BIGINT NOT NULL,
    source_object_id BIGINT NOT NULL,
    dimensional_entity_source_role VARCHAR(255) NOT NULL,
    dimensional_entity_source_mapping_order INTEGER,
    dimensional_entity_source_mapping_rationale TEXT NOT NULL,
    dimensional_entity_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_entity_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_entity_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_object FOREIGN KEY (source_object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_source_id_model
        UNIQUE (dimensional_entity_source_mapping_id, model_id),
    CONSTRAINT uq_dimensional_entity_source_witness UNIQUE (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_object_id,
        model_id
    ),
    CONSTRAINT ck_dimensional_entity_source_role CHECK (
        reference.is_nonblank(dimensional_entity_source_role)
    ),
    CONSTRAINT ck_dimensional_entity_source_order CHECK (
        dimensional_entity_source_mapping_order IS NULL
        OR dimensional_entity_source_mapping_order > 0
    ),
    CONSTRAINT ck_dimensional_entity_source_rationale CHECK (
        reference.is_nonblank(dimensional_entity_source_mapping_rationale)
    ),
    CONSTRAINT ck_dimensional_entity_source_status CHECK (
        dimensional_entity_source_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_entity_source_effective
    ON workflow.dimensional_entity_source_mapping (
        model_id,
        dimensional_entity_id,
        source_object_id
    ) WHERE dimensional_entity_source_mapping_status IN ('active', 'needs_review');

CREATE TABLE workflow.dimensional_attribute_source_mapping (
    dimensional_attribute_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_entity_source_mapping_id BIGINT NOT NULL,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_attribute_id BIGINT NOT NULL,
    source_object_id BIGINT NOT NULL,
    source_attribute_id BIGINT NOT NULL,
    dimensional_attribute_source_mapping_order INTEGER,
    dimensional_attribute_source_mapping_rationale TEXT NOT NULL,
    dimensional_attribute_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_attribute_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_attribute_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_parent FOREIGN KEY (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_object_id,
        model_id
    ) REFERENCES workflow.dimensional_entity_source_mapping (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_attribute FOREIGN KEY (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_physical FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_attribute_source_id_model
        UNIQUE (dimensional_attribute_source_mapping_id, model_id),
    CONSTRAINT ck_dimensional_attribute_source_order CHECK (
        dimensional_attribute_source_mapping_order IS NULL
        OR dimensional_attribute_source_mapping_order > 0
    ),
    CONSTRAINT ck_dimensional_attribute_source_rationale CHECK (
        reference.is_nonblank(dimensional_attribute_source_mapping_rationale)
    ),
    CONSTRAINT ck_dimensional_attribute_source_status CHECK (
        dimensional_attribute_source_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_attribute_source_effective
    ON workflow.dimensional_attribute_source_mapping (
        model_id,
        dimensional_entity_source_mapping_id,
        dimensional_attribute_id,
        source_attribute_id
    ) WHERE dimensional_attribute_source_mapping_status IN ('active', 'needs_review');

CREATE TABLE workflow.dimensional_relationship (
    dimensional_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    dimensional_relationship_name VARCHAR(255) NOT NULL,
    dimensional_relationship_definition TEXT NOT NULL,
    dimensional_relationship_from_entity_id BIGINT NOT NULL,
    dimensional_relationship_from_attribute_id BIGINT NOT NULL,
    dimensional_relationship_to_entity_id BIGINT NOT NULL,
    dimensional_relationship_to_attribute_id BIGINT NOT NULL,
    dimensional_relationship_kind VARCHAR(50) NOT NULL,
    dimensional_relationship_cardinality VARCHAR(50) NOT NULL,
    dimensional_relationship_role_name VARCHAR(255),
    dimensional_relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    dimensional_relationship_basis TEXT NOT NULL,
    dimensional_relationship_cardinality_basis TEXT NOT NULL,
    dimensional_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_relationship_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_from_entity FOREIGN KEY (
        dimensional_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_to_entity FOREIGN KEY (
        dimensional_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_from_attribute FOREIGN KEY (
        dimensional_relationship_from_attribute_id,
        dimensional_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_to_attribute FOREIGN KEY (
        dimensional_relationship_to_attribute_id,
        dimensional_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_relationship_id_model
        UNIQUE (dimensional_relationship_id, model_id),
    CONSTRAINT ck_dimensional_relationship_distinct_endpoints CHECK (
        (
            dimensional_relationship_from_entity_id,
            dimensional_relationship_from_attribute_id
        ) <> (
            dimensional_relationship_to_entity_id,
            dimensional_relationship_to_attribute_id
        )
    ),
    CONSTRAINT ck_dimensional_relationship_name CHECK (
        reference.is_nonblank(dimensional_relationship_name)
    ),
    CONSTRAINT ck_dimensional_relationship_definition CHECK (
        reference.is_nonblank(dimensional_relationship_definition)
    ),
    CONSTRAINT ck_dimensional_relationship_kind CHECK (
        reference.is_nonblank(dimensional_relationship_kind)
    ),
    CONSTRAINT ck_dimensional_relationship_cardinality CHECK (
        dimensional_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'
        )
    ),
    CONSTRAINT ck_dimensional_relationship_role CHECK (
        dimensional_relationship_role_name IS NULL
        OR reference.is_nonblank(dimensional_relationship_role_name)
    ),
    CONSTRAINT ck_dimensional_relationship_confidence CHECK (
        dimensional_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_dimensional_relationship_bases CHECK (
        reference.is_nonblank(dimensional_relationship_basis)
        AND reference.is_nonblank(dimensional_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_dimensional_relationship_status CHECK (
        dimensional_relationship_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_dimensional_relationship_effective_identity
    ON workflow.dimensional_relationship (
        model_id,
        dimensional_relationship_from_entity_id,
        dimensional_relationship_from_attribute_id,
        dimensional_relationship_to_entity_id,
        dimensional_relationship_to_attribute_id,
        dimensional_relationship_kind,
        coalesce(lower(btrim(dimensional_relationship_role_name)), '')
    ) WHERE dimensional_relationship_status IN ('active', 'needs_review');

-- Every Dimensional mutation participates in the one-revision transaction guard.

-- Supporting read, impact, and parent indexes.
CREATE INDEX ix_dimensional_submodel_status ON workflow.dimensional_submodel (model_id, dimensional_submodel_status);
CREATE INDEX ix_dimensional_entity_status_order ON workflow.dimensional_entity (model_id, dimensional_entity_status, dimensional_entity_dependency_order);
CREATE INDEX ix_dimensional_entity_submodel_entity ON workflow.dimensional_entity_submodel (model_id, dimensional_entity_id);
CREATE INDEX ix_dimensional_entity_submodel_submodel ON workflow.dimensional_entity_submodel (model_id, dimensional_submodel_id);
CREATE INDEX ix_dimensional_attribute_entity_status ON workflow.dimensional_attribute (model_id, dimensional_entity_id, dimensional_attribute_status);
CREATE INDEX ix_dimensional_entity_source_object ON workflow.dimensional_entity_source_mapping (model_id, source_object_id);
CREATE INDEX ix_dimensional_attribute_source_physical ON workflow.dimensional_attribute_source_mapping (model_id, source_object_id, source_attribute_id);
CREATE INDEX ix_dimensional_attribute_source_target ON workflow.dimensional_attribute_source_mapping (model_id, dimensional_attribute_id);
CREATE INDEX ix_dimensional_relationship_from ON workflow.dimensional_relationship (model_id, dimensional_relationship_from_entity_id, dimensional_relationship_from_attribute_id);
CREATE INDEX ix_dimensional_relationship_to ON workflow.dimensional_relationship (model_id, dimensional_relationship_to_entity_id, dimensional_relationship_to_attribute_id);
