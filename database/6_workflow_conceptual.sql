-- GDS ETL Workbench Release 1: Conceptual artifacts and physical Support.

CREATE TABLE workflow.conceptual_object (
    conceptual_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
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
        core.is_nonblank(conceptual_object_name)
    ),
    CONSTRAINT ck_conceptual_object_definition CHECK (
        core.is_nonblank(conceptual_object_definition)
    ),
    CONSTRAINT ck_conceptual_object_type CHECK (
        core.is_nonblank(conceptual_object_type)
    ),
    CONSTRAINT ck_conceptual_object_grain CHECK (
        core.is_nonblank(conceptual_object_grain)
    ),
    CONSTRAINT ck_conceptual_object_confidence CHECK (
        conceptual_object_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_object_status CHECK (
        conceptual_object_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
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
        core.is_nonblank(conceptual_relationship_name)
    ),
    CONSTRAINT ck_conceptual_relationship_type CHECK (
        core.is_nonblank(conceptual_relationship_type)
    ),
    CONSTRAINT ck_conceptual_relationship_definition CHECK (
        core.is_nonblank(conceptual_relationship_definition)
    ),
    CONSTRAINT ck_conceptual_relationship_cardinality CHECK (
        conceptual_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one',
            'many_to_many', 'unknown'
        )
    ),
    CONSTRAINT ck_conceptual_relationship_basis CHECK (
        core.is_nonblank(conceptual_relationship_basis)
        AND core.is_nonblank(conceptual_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_conceptual_relationship_confidence CHECK (
        conceptual_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_relationship_status CHECK (
        conceptual_relationship_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
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
    supported_artifact_type VARCHAR(30) NOT NULL,
    conceptual_object_id BIGINT,
    conceptual_relationship_id BIGINT,
    object_id BIGINT NOT NULL,
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
        object_id
    ) REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_support_id_model
        UNIQUE (conceptual_support_id, model_id),
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
    CONSTRAINT ck_conceptual_support_role CHECK (
        conceptual_support_role IS NULL
        OR core.is_nonblank(conceptual_support_role)
    ),
    CONSTRAINT ck_conceptual_support_reason CHECK (
        core.is_nonblank(conceptual_support_reason)
    ),
    CONSTRAINT ck_conceptual_support_reason_detail CHECK (
        conceptual_support_reason_detail IS NULL
        OR core.is_nonblank(conceptual_support_reason_detail)
    ),
    CONSTRAINT ck_conceptual_support_confidence CHECK (
        conceptual_support_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_support_status CHECK (
        conceptual_support_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_support_object_parent
    ON workflow.conceptual_support (model_id, conceptual_object_id, object_id)
    WHERE supported_artifact_type = 'conceptual_object';
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent
    ON workflow.conceptual_support (
        model_id,
        conceptual_relationship_id,
        object_id
    ) WHERE supported_artifact_type = 'conceptual_relationship';

CREATE TRIGGER capture_conceptual_object_change
BEFORE INSERT OR UPDATE OR DELETE ON workflow.conceptual_object
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();
CREATE TRIGGER capture_conceptual_relationship_change
BEFORE INSERT OR UPDATE OR DELETE ON workflow.conceptual_relationship
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();
CREATE TRIGGER capture_conceptual_support_change
BEFORE INSERT OR UPDATE OR DELETE ON workflow.conceptual_support
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();

CREATE INDEX ix_conceptual_object_model_status
    ON workflow.conceptual_object (model_id, conceptual_object_status);
CREATE INDEX ix_conceptual_relationship_from_object
    ON workflow.conceptual_relationship (model_id, from_conceptual_object_id);
CREATE INDEX ix_conceptual_relationship_to_object
    ON workflow.conceptual_relationship (model_id, to_conceptual_object_id);
CREATE INDEX ix_conceptual_support_physical_object
    ON workflow.conceptual_support (model_id, object_id);
CREATE INDEX ix_conceptual_object_locked
    ON workflow.conceptual_object (model_id, conceptual_object_id)
    WHERE conceptual_object_is_locked;
CREATE INDEX ix_conceptual_relationship_locked
    ON workflow.conceptual_relationship (model_id, conceptual_relationship_id)
    WHERE conceptual_relationship_is_locked;
CREATE INDEX ix_conceptual_support_locked
    ON workflow.conceptual_support (model_id, conceptual_support_id)
    WHERE conceptual_support_is_locked;
