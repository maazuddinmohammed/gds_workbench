-- GDS ETL Workbench Release 1: Conceptual Section and typed Support.

CREATE TABLE workflow.conceptual_object (
    conceptual_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    conceptual_object_name VARCHAR(255) NOT NULL,
    conceptual_object_definition TEXT NOT NULL,
    conceptual_object_type VARCHAR(100) NOT NULL,
    conceptual_object_grain TEXT NOT NULL,
    conceptual_object_aliases TEXT[] NOT NULL DEFAULT '{}',
    conceptual_object_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_object_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_object_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_object_id_project
        UNIQUE (conceptual_object_id, project_id),
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
    CONSTRAINT ck_conceptual_object_status CHECK (
        conceptual_object_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_object_project_name
    ON workflow.conceptual_object (
        project_id,
        lower(btrim(conceptual_object_name))
    );

CREATE TABLE workflow.conceptual_relationship (
    conceptual_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
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
    conceptual_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_relationship_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_relationship_from_object FOREIGN KEY (
        from_conceptual_object_id,
        project_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_relationship_to_object FOREIGN KEY (
        to_conceptual_object_id,
        project_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_relationship_id_project
        UNIQUE (conceptual_relationship_id, project_id),
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
    CONSTRAINT ck_conceptual_relationship_status CHECK (
        conceptual_relationship_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_relationship_identity
    ON workflow.conceptual_relationship (
        project_id,
        from_conceptual_object_id,
        to_conceptual_object_id,
        lower(btrim(conceptual_relationship_name))
    );

CREATE TABLE workflow.conceptual_support (
    conceptual_support_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    supported_artifact_type VARCHAR(30) NOT NULL,
    conceptual_object_id BIGINT,
    conceptual_relationship_id BIGINT,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    context_record_id UUID,
    conceptual_support_role VARCHAR(255),
    conceptual_support_reason TEXT NOT NULL,
    conceptual_support_reason_detail TEXT,
    conceptual_support_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_support_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_support_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_object_parent FOREIGN KEY (
        conceptual_object_id,
        project_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_relationship_parent FOREIGN KEY (
        conceptual_relationship_id,
        project_id
    ) REFERENCES workflow.conceptual_relationship (
        conceptual_relationship_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_physical_object FOREIGN KEY (
        project_id,
        source_object_id
    ) REFERENCES project.project_input_scope (project_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_context_record FOREIGN KEY (
        context_record_id,
        project_id
    ) REFERENCES project.context_record (
        context_record_id,
        project_id
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
            AND context_record_id IS NULL
        ) OR (
            support_source_type = 'context_record'
            AND context_record_id IS NOT NULL
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
    CONSTRAINT ck_conceptual_support_status CHECK (
        conceptual_support_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_conceptual_support_object_parent_object_source
    ON workflow.conceptual_support (
        project_id,
        conceptual_object_id,
        source_object_id
    ) WHERE supported_artifact_type = 'conceptual_object'
        AND support_source_type = 'object';
CREATE UNIQUE INDEX ux_conceptual_support_object_parent_context_source
    ON workflow.conceptual_support (
        project_id,
        conceptual_object_id,
        context_record_id
    ) WHERE supported_artifact_type = 'conceptual_object'
        AND support_source_type = 'context_record';
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent_object_source
    ON workflow.conceptual_support (
        project_id,
        conceptual_relationship_id,
        source_object_id
    ) WHERE supported_artifact_type = 'conceptual_relationship'
        AND support_source_type = 'object';
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent_context_source
    ON workflow.conceptual_support (
        project_id,
        conceptual_relationship_id,
        context_record_id
    ) WHERE supported_artifact_type = 'conceptual_relationship'
        AND support_source_type = 'context_record';

CREATE INDEX ix_conceptual_object_project_status
    ON workflow.conceptual_object (project_id, conceptual_object_status);
CREATE INDEX ix_conceptual_relationship_to_object
    ON workflow.conceptual_relationship (project_id, to_conceptual_object_id);
CREATE INDEX ix_conceptual_support_physical_object
    ON workflow.conceptual_support (project_id, source_object_id)
    WHERE support_source_type = 'object';
CREATE INDEX ix_conceptual_support_context_record
    ON workflow.conceptual_support (project_id, context_record_id)
    WHERE support_source_type = 'context_record';
