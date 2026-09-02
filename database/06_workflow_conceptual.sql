-- GDS ETL Workbench Release 1: Conceptual Section and typed Support.

CREATE TABLE workflow.conceptual_object (
    conceptual_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    conceptual_object_name VARCHAR(255) NOT NULL,
    conceptual_object_definition TEXT NOT NULL,
    conceptual_object_type VARCHAR(100) NOT NULL,
    conceptual_object_grain TEXT NOT NULL,
    conceptual_object_aliases TEXT[] NOT NULL DEFAULT '{}',
    conceptual_object_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    conceptual_object_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_object_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_object_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_object_id_model
        UNIQUE (conceptual_object_id, model_id),
    CONSTRAINT ck_conceptual_object_name CHECK (
        reference.is_nonblank(conceptual_object_name)
    ),
    CONSTRAINT ck_conceptual_object_definition CHECK (
        reference.is_nonblank(conceptual_object_definition)
    ),
    CONSTRAINT ck_conceptual_object_type CHECK (
        reference.is_nonblank(conceptual_object_type)
    ),
    CONSTRAINT ck_conceptual_object_grain CHECK (
        reference.is_nonblank(conceptual_object_grain)
    ),
    CONSTRAINT ck_conceptual_object_confidence CHECK (
        conceptual_object_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_object_status CHECK (
        conceptual_object_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_object_model_name
    ON workflow.conceptual_object (
        model_id,
        lower(btrim(conceptual_object_name))
    );

CREATE TABLE workflow.conceptual_relationship (
    conceptual_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    from_conceptual_object_id BIGINT NOT NULL,
    to_conceptual_object_id BIGINT NOT NULL,
    conceptual_relationship_name VARCHAR(255) NOT NULL,
    conceptual_relationship_type VARCHAR(100) NOT NULL,
    conceptual_relationship_definition TEXT NOT NULL,
    conceptual_relationship_cardinality VARCHAR(30) NOT NULL,
    conceptual_relationship_basis TEXT NOT NULL,
    conceptual_relationship_cardinality_basis TEXT NOT NULL,
    conceptual_relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    conceptual_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_relationship_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_relationship_from_object FOREIGN KEY (
        from_conceptual_object_id,
        model_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_relationship_to_object FOREIGN KEY (
        to_conceptual_object_id,
        model_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_relationship_id_model
        UNIQUE (conceptual_relationship_id, model_id),
    CONSTRAINT ck_conceptual_relationship_objects_different CHECK (
        from_conceptual_object_id <> to_conceptual_object_id
    ),
    CONSTRAINT ck_conceptual_relationship_name CHECK (
        reference.is_nonblank(conceptual_relationship_name)
    ),
    CONSTRAINT ck_conceptual_relationship_type CHECK (
        reference.is_nonblank(conceptual_relationship_type)
    ),
    CONSTRAINT ck_conceptual_relationship_definition CHECK (
        reference.is_nonblank(conceptual_relationship_definition)
    ),
    CONSTRAINT ck_conceptual_relationship_cardinality CHECK (
        conceptual_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one',
            'many_to_many', 'unknown'
        )
    ),
    CONSTRAINT ck_conceptual_relationship_basis CHECK (
        reference.is_nonblank(conceptual_relationship_basis)
        AND reference.is_nonblank(conceptual_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_conceptual_relationship_confidence CHECK (
        conceptual_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_relationship_status CHECK (
        conceptual_relationship_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_relationship_identity
    ON workflow.conceptual_relationship (
        model_id,
        from_conceptual_object_id,
        to_conceptual_object_id,
        lower(btrim(conceptual_relationship_name))
    );

CREATE TABLE workflow.conceptual_support (
    conceptual_support_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    supported_artifact_type VARCHAR(30) NOT NULL,
    conceptual_object_id BIGINT,
    conceptual_relationship_id BIGINT,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    modeling_assertion_record_id BIGINT,
    conceptual_support_role VARCHAR(255),
    conceptual_support_reason TEXT NOT NULL,
    conceptual_support_reason_detail TEXT,
    conceptual_support_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    conceptual_support_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_support_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_support_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_object_parent FOREIGN KEY (
        conceptual_object_id,
        model_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_relationship_parent FOREIGN KEY (
        conceptual_relationship_id,
        model_id
    ) REFERENCES workflow.conceptual_relationship (
        conceptual_relationship_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_physical_object FOREIGN KEY (
        model_id,
        source_object_id
    ) REFERENCES model.model_input_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_conceptual_support_typed_parent CHECK (
        (
            supported_artifact_type = 'conceptual_object'
            AND conceptual_object_id IS NOT NULL
            AND conceptual_relationship_id IS NULL
        ) OR (
            supported_artifact_type = 'conceptual_relationship'
            AND conceptual_relationship_id IS NOT NULL
            AND conceptual_object_id IS NULL
        )
    ),
    CONSTRAINT ck_conceptual_support_typed_source CHECK (
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
    CONSTRAINT ck_conceptual_support_role CHECK (
        conceptual_support_role IS NULL
        OR reference.is_nonblank(conceptual_support_role)
    ),
    CONSTRAINT ck_conceptual_support_reason CHECK (
        reference.is_nonblank(conceptual_support_reason)
    ),
    CONSTRAINT ck_conceptual_support_reason_detail CHECK (
        conceptual_support_reason_detail IS NULL
        OR reference.is_nonblank(conceptual_support_reason_detail)
    ),
    CONSTRAINT ck_conceptual_support_confidence CHECK (
        conceptual_support_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_support_status CHECK (
        conceptual_support_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_support_object_parent_object_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_object_id,
        source_object_id
    ) WHERE supported_artifact_type = 'conceptual_object'
        AND support_source_type = 'object';
CREATE UNIQUE INDEX ux_conceptual_support_object_parent_assertion_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_object_id,
        modeling_assertion_record_id
    ) WHERE supported_artifact_type = 'conceptual_object'
        AND support_source_type = 'assertion';
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent_object_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_relationship_id,
        source_object_id
    ) WHERE supported_artifact_type = 'conceptual_relationship'
        AND support_source_type = 'object';
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent_assertion_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_relationship_id,
        modeling_assertion_record_id
    ) WHERE supported_artifact_type = 'conceptual_relationship'
        AND support_source_type = 'assertion';

CREATE INDEX ix_conceptual_object_model_status
    ON workflow.conceptual_object (model_id, conceptual_object_status);
CREATE INDEX ix_conceptual_relationship_to_object
    ON workflow.conceptual_relationship (model_id, to_conceptual_object_id);
CREATE INDEX ix_conceptual_support_physical_object
    ON workflow.conceptual_support (model_id, source_object_id)
    WHERE support_source_type = 'object';
CREATE INDEX ix_conceptual_support_assertion_record
    ON workflow.conceptual_support (model_id, modeling_assertion_record_id)
    WHERE support_source_type = 'assertion';
