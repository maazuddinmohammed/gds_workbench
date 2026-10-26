-- GDS ETL Workbench Release 1: five-table Logical Section.
--
-- One Logical model per Project. Subject Areas only choose which tables a Build works on;
-- an Entity's areas are worked out from its source tables, never stored here.
-- Relationships point child -> parent: from the foreign-key Attribute to the parent's key.

CREATE TABLE workflow.logical_entity (
    logical_entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    logical_entity_schema_name VARCHAR(400) NOT NULL,
    logical_entity_name VARCHAR(255) NOT NULL,
    logical_entity_definition TEXT NOT NULL,
    logical_entity_type VARCHAR(50) NOT NULL,
    logical_entity_grain TEXT NOT NULL,
    logical_entity_dependency_order INTEGER NOT NULL DEFAULT 0,
    logical_entity_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    logical_entity_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logical_entity_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_type FOREIGN KEY (logical_entity_type)
        REFERENCES reference.logical_entity_type (logical_entity_type_code)
        ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_id_project UNIQUE (logical_entity_id, project_id),
    CONSTRAINT ck_logical_entity_schema_name CHECK (
        reference.is_nonblank(logical_entity_schema_name)
    ),
    CONSTRAINT ck_logical_entity_name CHECK (reference.is_nonblank(logical_entity_name)),
    CONSTRAINT ck_logical_entity_definition CHECK (
        reference.is_nonblank(logical_entity_definition)
    ),
    CONSTRAINT ck_logical_entity_grain CHECK (reference.is_nonblank(logical_entity_grain)),
    CONSTRAINT ck_logical_entity_dependency_order CHECK (
        logical_entity_dependency_order >= 0
    )
);

CREATE UNIQUE INDEX ux_logical_entity_project_name
    ON workflow.logical_entity (
        project_id, lower(btrim(logical_entity_schema_name)), lower(btrim(logical_entity_name))
    );

CREATE TABLE workflow.logical_attribute (
    logical_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    logical_attribute_name VARCHAR(255) NOT NULL,
    logical_attribute_definition TEXT NOT NULL,
    logical_attribute_data_type VARCHAR(100) NOT NULL,
    logical_attribute_is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    logical_attribute_is_natural_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_is_surrogate_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_ordinal_position INTEGER NOT NULL,
    logical_attribute_is_audit_column BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    logical_attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logical_attribute_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_entity FOREIGN KEY (
        logical_entity_id,
        project_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_logical_attribute_id_project UNIQUE (logical_attribute_id, project_id),
    CONSTRAINT uq_logical_attribute_witness
        UNIQUE (logical_attribute_id, logical_entity_id, project_id),
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
            logical_attribute_is_natural_key
            OR logical_attribute_is_surrogate_key
        ) OR NOT logical_attribute_is_nullable
    ),
    CONSTRAINT ck_logical_attribute_ordinal CHECK (
        logical_attribute_ordinal_position > 0
    )
);

CREATE UNIQUE INDEX ux_logical_attribute_entity_name
    ON workflow.logical_attribute (
        project_id,
        logical_entity_id,
        lower(btrim(logical_attribute_name))
    );

-- Which tables (or Context requirement) an Entity is built from. The filled id says
-- which kind of source it is. Also drives coverage and the Entity's Subject Areas.
CREATE TABLE workflow.logical_entity_source_mapping (
    logical_entity_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    source_object_id BIGINT,
    context_record_id UUID,
    logical_entity_source_mapping_rationale TEXT,
    logical_entity_source_mapping_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    logical_entity_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logical_entity_source_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_entity FOREIGN KEY (
        logical_entity_id,
        project_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_scope FOREIGN KEY (
        project_id,
        source_object_id
    ) REFERENCES project.project_input_scope (project_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_context_record FOREIGN KEY (
        context_record_id,
        project_id
    ) REFERENCES project.context_record (
        context_record_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_source_witness UNIQUE (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        project_id
    ),
    CONSTRAINT uq_logical_entity_source_object UNIQUE (
        project_id,
        logical_entity_id,
        source_object_id
    ),
    CONSTRAINT ck_logical_entity_source_typed_source CHECK (
        num_nonnulls(source_object_id, context_record_id) = 1
    ),
    CONSTRAINT ck_logical_entity_source_rationale CHECK (
        logical_entity_source_mapping_rationale IS NULL
        OR reference.is_nonblank(logical_entity_source_mapping_rationale)
    )
);

CREATE UNIQUE INDEX ux_logical_entity_source_context
    ON workflow.logical_entity_source_mapping (
        project_id,
        logical_entity_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL;

CREATE TABLE workflow.logical_attribute_source_mapping (
    logical_attribute_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    logical_entity_source_mapping_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    logical_attribute_id BIGINT NOT NULL,
    source_object_id BIGINT,
    source_attribute_id BIGINT,
    context_record_id UUID,
    logical_attribute_source_mapping_rationale TEXT,
    logical_attribute_source_mapping_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    logical_attribute_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logical_attribute_source_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    -- A physical column must come from one of the Entity's own source tables.
    CONSTRAINT fk_logical_attribute_source_parent FOREIGN KEY (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        project_id
    ) REFERENCES workflow.logical_entity_source_mapping (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_attribute FOREIGN KEY (
        logical_attribute_id,
        logical_entity_id,
        project_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_physical FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_context_record FOREIGN KEY (
        context_record_id,
        project_id
    ) REFERENCES project.context_record (
        context_record_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_logical_attribute_source_typed_source CHECK (
        (
            logical_entity_source_mapping_id IS NOT NULL
            AND source_object_id IS NOT NULL
            AND source_attribute_id IS NOT NULL
            AND context_record_id IS NULL
        ) OR (
            context_record_id IS NOT NULL
            AND logical_entity_source_mapping_id IS NULL
            AND source_object_id IS NULL
            AND source_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_logical_attribute_source_rationale CHECK (
        logical_attribute_source_mapping_rationale IS NULL
        OR reference.is_nonblank(logical_attribute_source_mapping_rationale)
    )
);

CREATE UNIQUE INDEX ux_logical_attribute_source_physical
    ON workflow.logical_attribute_source_mapping (
        project_id,
        logical_entity_source_mapping_id,
        logical_attribute_id,
        source_attribute_id
    ) WHERE source_attribute_id IS NOT NULL;
CREATE UNIQUE INDEX ux_logical_attribute_source_context
    ON workflow.logical_attribute_source_mapping (
        project_id,
        logical_attribute_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL;

-- Child -> parent: one foreign-key Attribute points at one parent Entity's key.
-- Many-to-many becomes an association Entity.
CREATE TABLE workflow.logical_relationship (
    logical_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    logical_relationship_from_entity_id BIGINT NOT NULL,
    logical_relationship_from_attribute_id BIGINT NOT NULL,
    logical_relationship_to_entity_id BIGINT NOT NULL,
    logical_relationship_to_attribute_id BIGINT NOT NULL,
    logical_relationship_cardinality VARCHAR(20) NOT NULL DEFAULT 'many_to_one',
    logical_relationship_basis TEXT NOT NULL,
    logical_relationship_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    logical_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logical_relationship_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_from_entity FOREIGN KEY (
        logical_relationship_from_entity_id,
        project_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_to_entity FOREIGN KEY (
        logical_relationship_to_entity_id,
        project_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_from_attribute FOREIGN KEY (
        logical_relationship_from_attribute_id,
        logical_relationship_from_entity_id,
        project_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_to_attribute FOREIGN KEY (
        logical_relationship_to_attribute_id,
        logical_relationship_to_entity_id,
        project_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_relationship_from_attribute UNIQUE (
        project_id,
        logical_relationship_from_attribute_id
    ),
    CONSTRAINT ck_logical_relationship_distinct_endpoints CHECK (
        (logical_relationship_from_entity_id, logical_relationship_from_attribute_id)
        <> (logical_relationship_to_entity_id, logical_relationship_to_attribute_id)
    ),
    CONSTRAINT ck_logical_relationship_cardinality CHECK (
        logical_relationship_cardinality IN ('many_to_one', 'one_to_one')
    ),
    CONSTRAINT ck_logical_relationship_basis CHECK (
        reference.is_nonblank(logical_relationship_basis)
    )
);

-- Every Logical mutation participates in the one-revision transaction guard.

-- Supporting read, impact, and parent indexes.
CREATE INDEX ix_logical_entity_active_order ON workflow.logical_entity (project_id, logical_entity_is_active, logical_entity_dependency_order);
CREATE INDEX ix_logical_attribute_entity_active ON workflow.logical_attribute (project_id, logical_entity_id, logical_attribute_is_active);
CREATE INDEX ix_logical_entity_source_object
    ON workflow.logical_entity_source_mapping (project_id, source_object_id)
    WHERE source_object_id IS NOT NULL;
CREATE INDEX ix_logical_entity_source_context
    ON workflow.logical_entity_source_mapping (
        project_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL;
CREATE INDEX ix_logical_attribute_source_physical
    ON workflow.logical_attribute_source_mapping (
        project_id,
        source_object_id,
        source_attribute_id
    ) WHERE source_attribute_id IS NOT NULL;
CREATE INDEX ix_logical_attribute_source_context
    ON workflow.logical_attribute_source_mapping (
        project_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL;
CREATE INDEX ix_logical_attribute_source_target ON workflow.logical_attribute_source_mapping (project_id, logical_attribute_id);
CREATE INDEX ix_logical_relationship_to ON workflow.logical_relationship (project_id, logical_relationship_to_entity_id, logical_relationship_to_attribute_id);
