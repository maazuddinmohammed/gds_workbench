-- PROPOSAL (draft, not installed). Replaces database/07_workflow_logical.sql.
--
-- Comment format:  filled by · read by
--   filled by: AI = the model writes it | backend = computed | you = set in review
--   read by:   BUILD, DIM, MAP, CODE, VAL, DDL, REG (see README)
-- Nonblank text checks, the schema guard trigger and the one-revision write guard
-- stay as they are today.
--
-- Removed tables: logical_submodel, logical_entity_submodel.
-- Subject areas replace them; an entity's areas are worked out from its source tables.

-- ---------------------------------------------------------------------------
-- Entity: one business thing at one grain, e.g. SalesOrder.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.logical_entity (
    logical_entity_id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                       BIGINT NOT NULL REFERENCES project.project,      -- backend
    logical_entity_schema_name       VARCHAR(400) NOT NULL,  -- AI · DDL, REG, MAP, CODE (placement)
    logical_entity_name              VARCHAR(255) NOT NULL,  -- AI · every step
    logical_entity_definition        TEXT NOT NULL,          -- AI: first says what one row is ("One row per
                                                             -- order line ..."), then what it means
                                                             -- · DIM, MAP, DDL table comment, REG
    logical_entity_type              VARCHAR(50) NOT NULL    -- AI, a value from reference.logical_entity_type
        REFERENCES reference.logical_entity_type (logical_entity_type_code), -- · DIM: fact or dimension hint
    logical_entity_dependency_order  INTEGER NOT NULL DEFAULT 0, -- backend, from relationships (parents first) · DDL, CODE order
    logical_entity_is_active         BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire) · every step
    logical_entity_is_locked         BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                  BIGINT,                 -- backend · audit
    created_time                     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (logical_entity_id, project_id),
    CHECK (logical_entity_dependency_order >= 0)
);

CREATE UNIQUE INDEX ux_logical_entity_name
    ON workflow.logical_entity (
        project_id, lower(btrim(logical_entity_schema_name)), lower(btrim(logical_entity_name))
    );

-- Dropped: logical_entity_grain (now the definition's first sentence; the natural-key
--          columns are the grain in a form Validate can check),
--          logical_entity_type_detail ('other' is gone), status (now is_active),
--          agent_run_id, created_by, updated_by.
-- Changed: the type list moved to reference.logical_entity_type (00_reference_lists.sql),
--          so adding a type is an INSERT, not a DDL change.
-- Types dropped: 'bridge' (same as 'association'), 'aggregate' (no aggregates in Logical),
--          'other'.

-- ---------------------------------------------------------------------------
-- Attribute: one column of an entity.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.logical_attribute (
    logical_attribute_id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                          BIGINT NOT NULL,       -- backend
    logical_entity_id                   BIGINT NOT NULL,       -- backend, from the entity name
    logical_attribute_name              VARCHAR(255) NOT NULL, -- AI · every step
    logical_attribute_definition        TEXT NOT NULL,         -- AI, or backend copies the source column's
                                                               -- description when the AI leaves it out
                                                               -- · DIM, MAP, DDL column comment, REG
    logical_attribute_data_type         VARCHAR(100) NOT NULL, -- AI · DDL, CODE, MAP, DIM
    logical_attribute_is_nullable       BOOLEAN NOT NULL DEFAULT TRUE,   -- AI · DDL, CODE, MAP null rules
    logical_attribute_is_natural_key    BOOLEAN NOT NULL DEFAULT FALSE,  -- AI · MAP lookups and dedupe, VAL key check, DIM
    logical_attribute_is_surrogate_key  BOOLEAN NOT NULL DEFAULT FALSE,  -- backend adds <Entity>ID · DDL primary key, CODE (database fills it)
    logical_attribute_is_audit_column   BOOLEAN NOT NULL DEFAULT FALSE,  -- backend, from the Project audit template · CODE (framework fills it)
    logical_attribute_ordinal_position  INTEGER NOT NULL,      -- backend: surrogate first, then the AI's order,
                                                               -- audit last · DDL, CODE column order
    logical_attribute_is_active         BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    logical_attribute_is_locked         BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                     BIGINT,                -- backend · audit
    created_time                        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (logical_attribute_id, logical_entity_id, project_id),
    FOREIGN KEY (logical_entity_id, project_id)
        REFERENCES workflow.logical_entity (logical_entity_id, project_id),
    CHECK (NOT (logical_attribute_is_natural_key AND logical_attribute_is_surrogate_key)),
    CHECK (NOT (logical_attribute_is_natural_key OR logical_attribute_is_surrogate_key)
           OR NOT logical_attribute_is_nullable),
    CHECK (logical_attribute_ordinal_position > 0)
);

CREATE UNIQUE INDEX ux_logical_attribute_name
    ON workflow.logical_attribute (project_id, logical_entity_id, lower(btrim(logical_attribute_name)));

-- Dropped: status (now is_active), agent_run_id, created_by, updated_by.
-- Kept but no longer sent by the AI: surrogate flag, audit flag, ordinal position.

-- ---------------------------------------------------------------------------
-- Entity source: which tables (or requirement) an entity is built from.
-- Also drives coverage and an entity's subject areas.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.logical_entity_source_mapping (
    logical_entity_source_mapping_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                        BIGINT NOT NULL,  -- backend
    logical_entity_id                 BIGINT NOT NULL,  -- backend
    source_object_id                  BIGINT,           -- AI (by table id) · coverage, subject areas, MAP, DIM evidence
    context_record_id                 UUID,             -- AI · for requirement-only entities
    source_rationale                  TEXT,             -- AI, only when several tables combine or rows are
                                                        -- filtered · MAP
    source_is_active                  BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    source_is_locked                  BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                   BIGINT,           -- backend · audit
    created_time                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (logical_entity_id, project_id)
        REFERENCES workflow.logical_entity (logical_entity_id, project_id),
    FOREIGN KEY (project_id, source_object_id)
        REFERENCES project.project_input_scope (project_id, object_id),
    FOREIGN KEY (context_record_id, project_id)
        REFERENCES project.context_record (context_record_id, project_id),
    CHECK (num_nonnulls(source_object_id, context_record_id) = 1),
    UNIQUE (project_id, logical_entity_id, source_object_id)  -- target of the attribute-source FK below
);

CREATE UNIQUE INDEX ux_logical_entity_source_context
    ON workflow.logical_entity_source_mapping (project_id, logical_entity_id, context_record_id)
    WHERE context_record_id IS NOT NULL;

-- Dropped: support_source_type (which id is filled already says it), source order
--          (precedence between sources is a Mapping decision), status, agent_run_id,
--          created_by, updated_by.
-- Changed: rationale is now optional.

-- ---------------------------------------------------------------------------
-- Attribute source: which column (or requirement) feeds an attribute.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.logical_attribute_source_mapping (
    logical_attribute_source_mapping_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                           BIGINT NOT NULL,  -- backend
    logical_entity_id                    BIGINT NOT NULL,  -- backend
    logical_attribute_id                 BIGINT NOT NULL,  -- backend
    source_object_id                     BIGINT,           -- AI (table id) · MAP, DIM evidence
    source_attribute_id                  BIGINT,           -- AI (column name) · MAP column lineage, DIM evidence, DDL
    context_record_id                    UUID,             -- AI · requirement-only attributes
    source_rationale                     TEXT,             -- AI, only when it isn't a straight copy · MAP, CODE
    source_is_active                     BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    source_is_locked                     BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                      BIGINT,           -- backend · audit
    created_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (logical_attribute_id, logical_entity_id, project_id)
        REFERENCES workflow.logical_attribute (logical_attribute_id, logical_entity_id, project_id),
    -- The column must come from one of the entity's own source tables.
    FOREIGN KEY (project_id, logical_entity_id, source_object_id)
        REFERENCES workflow.logical_entity_source_mapping (project_id, logical_entity_id, source_object_id),
    FOREIGN KEY (source_attribute_id, source_object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    FOREIGN KEY (context_record_id, project_id)
        REFERENCES project.context_record (context_record_id, project_id),
    CHECK (
        (source_attribute_id IS NOT NULL AND source_object_id IS NOT NULL AND context_record_id IS NULL)
        OR (context_record_id IS NOT NULL AND source_attribute_id IS NULL AND source_object_id IS NULL)
    )
);

-- Dropped: logical_entity_source_mapping_id (the composite FK above keeps the same rule),
--          support_source_type, source order, status, agent_run_id, created_by, updated_by.
-- Changed: rationale is now optional.

-- ---------------------------------------------------------------------------
-- Relationship: always child → parent, from the foreign-key column to the parent entity.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.logical_relationship (
    logical_relationship_id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                           BIGINT NOT NULL,  -- backend
    logical_relationship_from_entity_id     BIGINT NOT NULL, -- AI (child entity) · DDL FK, MAP joins, DIM
    logical_relationship_from_attribute_id  BIGINT NOT NULL, -- AI (its foreign-key column) · DDL FK, MAP, DIM
    logical_relationship_to_entity_id       BIGINT NOT NULL, -- AI (parent entity) · DDL FK, MAP, DIM
    logical_relationship_to_attribute_id    BIGINT NOT NULL, -- backend: the parent's surrogate key · DDL FK, CODE
    logical_relationship_cardinality     VARCHAR(20) NOT NULL DEFAULT 'many_to_one', -- AI · DIM, MAP row counts
    logical_relationship_basis           TEXT NOT NULL,    -- AI: why the link and its cardinality hold
                                                           -- · DIM, MAP join confidence
    logical_relationship_is_active       BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (only to retire)
    logical_relationship_is_locked       BOOLEAN NOT NULL DEFAULT FALSE,  -- you
    workflow_run_id                      BIGINT,           -- backend · audit
    created_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (logical_relationship_from_attribute_id, logical_relationship_from_entity_id, project_id)
        REFERENCES workflow.logical_attribute (logical_attribute_id, logical_entity_id, project_id),
    FOREIGN KEY (logical_relationship_to_attribute_id, logical_relationship_to_entity_id, project_id)
        REFERENCES workflow.logical_attribute (logical_attribute_id, logical_entity_id, project_id),
    CHECK (logical_relationship_cardinality IN ('many_to_one', 'one_to_one')),
    UNIQUE (project_id, logical_relationship_from_attribute_id)  -- one foreign-key column, one parent
);

-- Dropped: relationship name (the foreign-key column name carries the role, e.g.
--          BillingCustomerID), definition (the basis covers it), cardinality_basis
--          (merged into basis), 'one_to_many' and 'many_to_many' (child → parent
--          direction only; many-to-many becomes an association entity), status,
--          agent_run_id, created_by, updated_by.
