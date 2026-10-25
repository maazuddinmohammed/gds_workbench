-- PROPOSAL (draft, not installed). Replaces database/08_workflow_dimensional.sql.
--
-- Comment format:  filled by · read by
--   filled by: AI = the model writes it | backend = computed | you = set in review
--   read by:   BUILD, MAP, CODE, VAL, DDL, REG (see README)
-- Nonblank text checks, the schema guard trigger and the one-revision write guard
-- stay as they are today. History (Type 1 / Type 2) stays a Project setting, and the
-- backend adds Type 2 columns, as today.
--
-- Removed tables: dimensional_submodel, dimensional_entity_submodel.
-- A Dimensional entity's subject areas are worked out through its Logical sources.

-- ---------------------------------------------------------------------------
-- Entity: a fact, dimension or bridge.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.dimensional_entity (
    dimensional_entity_id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                           BIGINT NOT NULL REFERENCES project.project,      -- backend
    dimensional_entity_schema_name       VARCHAR(400) NOT NULL, -- AI · DDL, REG, MAP, CODE
    dimensional_entity_name              VARCHAR(255) NOT NULL, -- AI · every step
    dimensional_entity_definition        TEXT NOT NULL,         -- AI: first says what one row is, then
                                                                -- what it means · MAP, DDL table comment, REG
    dimensional_entity_type              VARCHAR(20) NOT NULL,  -- AI · MAP, CODE, VAL; fixed list because
                                                                -- the backend treats each value differently
    dimensional_fact_type                VARCHAR(50)            -- AI, facts only, a value from
        REFERENCES reference.dimensional_fact_type (dimensional_fact_type_code), -- reference.dimensional_fact_type
                                                                -- · MAP, CODE load pattern
    dimensional_entity_dependency_order  INTEGER NOT NULL DEFAULT 0, -- backend, from relationships
                                                                -- (dimensions first) · DDL, CODE order
    dimensional_entity_is_active         BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    dimensional_entity_is_locked         BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                      BIGINT,                -- backend · audit
    created_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dimensional_entity_id, project_id),
    CHECK (dimensional_entity_type IN ('fact', 'dimension', 'bridge')),
    CHECK ((dimensional_entity_type = 'fact') = (dimensional_fact_type IS NOT NULL))
);
-- Backend rule, checked with the whole model: a fact or bridge needs natural-key columns.
-- They are its grain, and Validate checks them for duplicates.

CREATE UNIQUE INDEX ux_dimensional_entity_name
    ON workflow.dimensional_entity (
        project_id, lower(btrim(dimensional_entity_schema_name)), lower(btrim(dimensional_entity_name))
    );

-- Dropped: dimensional_entity_grain_definition (now the definition's first sentence, with
--          the natural-key columns as the checkable grain), status (now is_active),
--          agent_run_id, created_by, updated_by.
-- Changed: the fact type list moved to reference.dimensional_fact_type.

-- ---------------------------------------------------------------------------
-- Attribute: a column of a fact, dimension or bridge.
-- The definition carries measure meaning, units and how it may be summed, as today.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.dimensional_attribute (
    dimensional_attribute_id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                              BIGINT NOT NULL,       -- backend
    dimensional_entity_id                   BIGINT NOT NULL,       -- backend
    dimensional_attribute_name              VARCHAR(255) NOT NULL, -- AI · every step
    dimensional_attribute_definition        TEXT NOT NULL,         -- AI, or backend copies the Logical
                                                                   -- definition for a straight copy
                                                                   -- · MAP, DDL comment, REG
    dimensional_attribute_data_type         VARCHAR(100) NOT NULL, -- AI · DDL, CODE, MAP
    dimensional_attribute_is_nullable       BOOLEAN NOT NULL DEFAULT TRUE,   -- AI · DDL, CODE, MAP
    dimensional_attribute_is_natural_key    BOOLEAN NOT NULL DEFAULT FALSE,  -- AI · MAP, CODE (Type 2 match), VAL
    dimensional_attribute_is_surrogate_key  BOOLEAN NOT NULL DEFAULT FALSE,  -- backend · DDL, CODE
    dimensional_attribute_is_audit_column   BOOLEAN NOT NULL DEFAULT FALSE,  -- backend, from the Gold audit template
    dimensional_attribute_ordinal_position  INTEGER NOT NULL,      -- backend · DDL, CODE column order
    dimensional_attribute_is_active         BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    dimensional_attribute_is_locked         BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                         BIGINT,                -- backend · audit
    created_time                            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dimensional_attribute_id, dimensional_entity_id, project_id),
    FOREIGN KEY (dimensional_entity_id, project_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id, project_id),
    CHECK (NOT (dimensional_attribute_is_natural_key AND dimensional_attribute_is_surrogate_key)),
    CHECK (NOT (dimensional_attribute_is_natural_key OR dimensional_attribute_is_surrogate_key)
           OR NOT dimensional_attribute_is_nullable),
    CHECK (dimensional_attribute_ordinal_position > 0)
);

CREATE UNIQUE INDEX ux_dimensional_attribute_name
    ON workflow.dimensional_attribute (project_id, dimensional_entity_id, lower(btrim(dimensional_attribute_name)));

-- Dropped: status (now is_active), agent_run_id, created_by, updated_by.

-- ---------------------------------------------------------------------------
-- Entity source: which Logical entities (or requirement) feed it.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.dimensional_entity_source_mapping (
    dimensional_entity_source_mapping_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                            BIGINT NOT NULL,  -- backend
    dimensional_entity_id                 BIGINT NOT NULL,  -- backend
    source_logical_entity_id              BIGINT,           -- AI · coverage, subject areas, MAP
    context_record_id                     UUID,             -- AI · requirement-only entities
    source_rationale                      TEXT,             -- AI, only when several entities combine
                                                            -- or rows are filtered · MAP
    source_is_active                      BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    source_is_locked                      BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                       BIGINT,           -- backend · audit
    created_time                          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dimensional_entity_id, project_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id, project_id),
    FOREIGN KEY (source_logical_entity_id, project_id)
        REFERENCES workflow.logical_entity (logical_entity_id, project_id),
    FOREIGN KEY (context_record_id, project_id)
        REFERENCES project.context_record (context_record_id, project_id),
    CHECK (num_nonnulls(source_logical_entity_id, context_record_id) = 1),
    UNIQUE (project_id, dimensional_entity_id, source_logical_entity_id)
);

-- Dropped: support_source_type, source order, status, agent_run_id, created_by, updated_by.
-- Changed: rationale is now optional.

-- ---------------------------------------------------------------------------
-- Attribute source: which Logical attribute (or requirement) feeds it.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.dimensional_attribute_source_mapping (
    dimensional_attribute_source_mapping_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                               BIGINT NOT NULL,  -- backend
    dimensional_entity_id                    BIGINT NOT NULL,  -- backend
    dimensional_attribute_id                 BIGINT NOT NULL,  -- backend
    source_logical_entity_id                 BIGINT,           -- AI · MAP
    source_logical_attribute_id              BIGINT,           -- AI · MAP column lineage
    context_record_id                        UUID,             -- AI · requirement-only attributes
    source_rationale                         TEXT,             -- AI, only when it isn't a straight copy
                                                               -- (derived measure, aggregation) · MAP, CODE
    source_is_active                         BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    source_is_locked                         BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                          BIGINT,           -- backend · audit
    created_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dimensional_attribute_id, dimensional_entity_id, project_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id, dimensional_entity_id, project_id),
    -- The Logical attribute must belong to one of the entity's own Logical sources.
    FOREIGN KEY (project_id, dimensional_entity_id, source_logical_entity_id)
        REFERENCES workflow.dimensional_entity_source_mapping (project_id, dimensional_entity_id, source_logical_entity_id),
    FOREIGN KEY (source_logical_attribute_id, source_logical_entity_id, project_id)
        REFERENCES workflow.logical_attribute (logical_attribute_id, logical_entity_id, project_id),
    FOREIGN KEY (context_record_id, project_id)
        REFERENCES project.context_record (context_record_id, project_id),
    CHECK (
        (source_logical_attribute_id IS NOT NULL AND source_logical_entity_id IS NOT NULL AND context_record_id IS NULL)
        OR (context_record_id IS NOT NULL AND source_logical_attribute_id IS NULL AND source_logical_entity_id IS NULL)
    )
);

-- Dropped: dimensional_entity_source_mapping_id (the composite FK keeps the rule),
--          support_source_type, source order, status, agent_run_id, created_by, updated_by.

-- ---------------------------------------------------------------------------
-- Relationship: always child → parent, e.g. a fact's foreign-key column → a dimension.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.dimensional_relationship (
    dimensional_relationship_id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                                  BIGINT NOT NULL,  -- backend
    dimensional_relationship_from_entity_id     BIGINT NOT NULL,  -- AI (fact, bridge or outrigger) · DDL FK, MAP, CODE
    dimensional_relationship_from_attribute_id  BIGINT NOT NULL,  -- AI (its foreign-key column) · DDL FK, MAP, CODE
    dimensional_relationship_to_entity_id       BIGINT NOT NULL,  -- AI (the dimension) · DDL FK, MAP, CODE
    dimensional_relationship_to_attribute_id    BIGINT NOT NULL,  -- backend: the dimension's surrogate key
    dimensional_relationship_role_name          VARCHAR(255),     -- AI, only for role-playing dimensions
                                                                  -- (OrderDate vs ShipDate) · MAP, REG
    dimensional_relationship_basis              TEXT,             -- AI, only when it doesn't follow a Logical
                                                                  -- relationship · MAP
    dimensional_relationship_is_active          BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    dimensional_relationship_is_locked          BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                             BIGINT,           -- backend · audit
    created_time                                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dimensional_relationship_from_attribute_id, dimensional_relationship_from_entity_id, project_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id, dimensional_entity_id, project_id),
    FOREIGN KEY (dimensional_relationship_to_attribute_id, dimensional_relationship_to_entity_id, project_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id, dimensional_entity_id, project_id),
    UNIQUE (project_id, dimensional_relationship_from_attribute_id)  -- one foreign-key column, one dimension
);

-- Dropped:
--   name, definition          the role name and the foreign-key column say it
--   kind                      worked out from the two entity types (fact → dimension, ...)
--   cardinality               always many-to-one: the child holds the foreign key
--   is_optional               worked out from the foreign-key column's nullability
--   cardinality_basis         nothing reads it separately
--   status, agent_run_id, created_by, updated_by
-- Changed: basis is now optional.
