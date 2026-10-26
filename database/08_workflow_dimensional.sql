-- GDS ETL Workbench Release 1: five-table Dimensional Section.
--
-- Dimensional reuses the Project's Subject Areas through its Logical sources; it has no
-- grouping of its own. Relationships point child -> parent: a fact, bridge or outrigger's
-- foreign-key Attribute -> the dimension's key. Kind and optionality are worked out from
-- the two Entity types and the foreign key's nullability; cardinality is always
-- many-to-one.

CREATE TABLE workflow.dimensional_entity (
    dimensional_entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    dimensional_entity_schema_name VARCHAR(400) NOT NULL,
    dimensional_entity_name VARCHAR(255) NOT NULL,
    dimensional_entity_definition TEXT NOT NULL,
    dimensional_entity_type VARCHAR(20) NOT NULL,
    dimensional_fact_type VARCHAR(50),
    dimensional_entity_grain_definition TEXT,
    dimensional_entity_dependency_order INTEGER NOT NULL DEFAULT 0,
    dimensional_entity_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_entity_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dimensional_entity_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_fact_type FOREIGN KEY (dimensional_fact_type)
        REFERENCES reference.dimensional_fact_type (dimensional_fact_type_code)
        ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_id_project
        UNIQUE (dimensional_entity_id, project_id),
    CONSTRAINT ck_dimensional_entity_schema_name CHECK (
        reference.is_nonblank(dimensional_entity_schema_name)
    ),
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
        (dimensional_entity_type = 'fact') = (dimensional_fact_type IS NOT NULL)
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
    )
);

CREATE UNIQUE INDEX ux_dimensional_entity_effective_name
    ON workflow.dimensional_entity (
        project_id,
        lower(btrim(dimensional_entity_schema_name)),
        lower(btrim(dimensional_entity_name))
    ) WHERE dimensional_entity_is_active;

CREATE TABLE workflow.dimensional_attribute (
    dimensional_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_attribute_name VARCHAR(255) NOT NULL,
    dimensional_attribute_definition TEXT NOT NULL,
    dimensional_attribute_data_type VARCHAR(100) NOT NULL,
    dimensional_attribute_is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_attribute_ordinal_position INTEGER NOT NULL,
    dimensional_attribute_is_natural_key BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_is_surrogate_key BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_is_audit_column BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dimensional_attribute_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_entity FOREIGN KEY (
        dimensional_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_attribute_id_project
        UNIQUE (dimensional_attribute_id, project_id),
    CONSTRAINT uq_dimensional_attribute_witness
        UNIQUE (dimensional_attribute_id, dimensional_entity_id, project_id),
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
    CONSTRAINT ck_dimensional_attribute_key_origin CHECK (
        NOT (
            dimensional_attribute_is_natural_key
            AND dimensional_attribute_is_surrogate_key
        )
    ),
    CONSTRAINT ck_dimensional_attribute_key_nullable CHECK (
        NOT (
            dimensional_attribute_is_natural_key
            OR dimensional_attribute_is_surrogate_key
        ) OR NOT dimensional_attribute_is_nullable
    )
);

CREATE UNIQUE INDEX ux_dimensional_attribute_effective_name
    ON workflow.dimensional_attribute (
        project_id,
        dimensional_entity_id,
        lower(btrim(dimensional_attribute_name))
    ) WHERE dimensional_attribute_is_active;

-- Which Logical Entities (or Context requirement) feed a Dimensional Entity. The filled
-- id says which kind of source it is.
CREATE TABLE workflow.dimensional_entity_source_mapping (
    dimensional_entity_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    source_logical_entity_id BIGINT,
    context_record_id UUID,
    dimensional_entity_source_mapping_rationale TEXT,
    dimensional_entity_source_mapping_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_entity_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dimensional_entity_source_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_entity FOREIGN KEY (
        dimensional_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_logical FOREIGN KEY (
        source_logical_entity_id, project_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_context_record FOREIGN KEY (
        context_record_id,
        project_id
    ) REFERENCES project.context_record (
        context_record_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_source_witness UNIQUE (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_logical_entity_id,
        project_id
    ),
    CONSTRAINT ck_dimensional_entity_source_typed_source CHECK (
        num_nonnulls(source_logical_entity_id, context_record_id) = 1
    ),
    CONSTRAINT ck_dimensional_entity_source_rationale CHECK (
        dimensional_entity_source_mapping_rationale IS NULL
        OR reference.is_nonblank(dimensional_entity_source_mapping_rationale)
    )
);

CREATE UNIQUE INDEX ux_dimensional_entity_source_logical_entity_effective
    ON workflow.dimensional_entity_source_mapping (
        project_id,
        dimensional_entity_id,
        source_logical_entity_id
    ) WHERE source_logical_entity_id IS NOT NULL
        AND dimensional_entity_source_mapping_is_active;
CREATE UNIQUE INDEX ux_dimensional_entity_source_context_effective
    ON workflow.dimensional_entity_source_mapping (
        project_id,
        dimensional_entity_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL
        AND dimensional_entity_source_mapping_is_active;

CREATE TABLE workflow.dimensional_attribute_source_mapping (
    dimensional_attribute_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    dimensional_entity_source_mapping_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_attribute_id BIGINT NOT NULL,
    source_logical_entity_id BIGINT,
    source_logical_attribute_id BIGINT,
    context_record_id UUID,
    dimensional_attribute_source_mapping_rationale TEXT,
    dimensional_attribute_source_mapping_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_attribute_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dimensional_attribute_source_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    -- A Logical Attribute must belong to one of the Entity's own Logical sources.
    CONSTRAINT fk_dimensional_attribute_source_parent FOREIGN KEY (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_logical_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_entity_source_mapping (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_logical_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_attribute FOREIGN KEY (
        dimensional_attribute_id,
        dimensional_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_logical FOREIGN KEY (
        source_logical_attribute_id, source_logical_entity_id, project_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id, logical_entity_id, project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_context_record FOREIGN KEY (
        context_record_id,
        project_id
    ) REFERENCES project.context_record (
        context_record_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_dimensional_attribute_source_typed_source CHECK (
        (
            dimensional_entity_source_mapping_id IS NOT NULL
            AND source_logical_entity_id IS NOT NULL
            AND source_logical_attribute_id IS NOT NULL
            AND context_record_id IS NULL
        ) OR (
            context_record_id IS NOT NULL
            AND dimensional_entity_source_mapping_id IS NULL
            AND source_logical_entity_id IS NULL
            AND source_logical_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_attribute_source_rationale CHECK (
        dimensional_attribute_source_mapping_rationale IS NULL
        OR reference.is_nonblank(dimensional_attribute_source_mapping_rationale)
    )
);

CREATE UNIQUE INDEX ux_dimensional_attribute_source_logical_attribute_effective
    ON workflow.dimensional_attribute_source_mapping (
        project_id,
        dimensional_entity_source_mapping_id,
        dimensional_attribute_id,
        source_logical_attribute_id
    ) WHERE source_logical_attribute_id IS NOT NULL
        AND dimensional_attribute_source_mapping_is_active;
CREATE UNIQUE INDEX ux_dimensional_attribute_source_context_effective
    ON workflow.dimensional_attribute_source_mapping (
        project_id,
        dimensional_attribute_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL
        AND dimensional_attribute_source_mapping_is_active;

-- Child -> parent: one foreign-key Attribute points at one dimension's key. role_name
-- names a role-playing use (OrderDate vs ShipDate); basis is needed only when the link
-- does not follow a Logical Relationship.
CREATE TABLE workflow.dimensional_relationship (
    dimensional_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
    dimensional_relationship_from_entity_id BIGINT NOT NULL,
    dimensional_relationship_from_attribute_id BIGINT NOT NULL,
    dimensional_relationship_to_entity_id BIGINT NOT NULL,
    dimensional_relationship_to_attribute_id BIGINT NOT NULL,
    dimensional_relationship_role_name VARCHAR(255),
    dimensional_relationship_basis TEXT,
    dimensional_relationship_is_active BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dimensional_relationship_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_from_entity FOREIGN KEY (
        dimensional_relationship_from_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_to_entity FOREIGN KEY (
        dimensional_relationship_to_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, project_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_from_attribute FOREIGN KEY (
        dimensional_relationship_from_attribute_id,
        dimensional_relationship_from_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_to_attribute FOREIGN KEY (
        dimensional_relationship_to_attribute_id,
        dimensional_relationship_to_entity_id,
        project_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_relationship_from_attribute UNIQUE (
        project_id,
        dimensional_relationship_from_attribute_id
    ),
    CONSTRAINT ck_dimensional_relationship_distinct_endpoints CHECK (
        (
            dimensional_relationship_from_entity_id,
            dimensional_relationship_from_attribute_id
        ) <> (
            dimensional_relationship_to_entity_id,
            dimensional_relationship_to_attribute_id
        )
    ),
    CONSTRAINT ck_dimensional_relationship_role CHECK (
        dimensional_relationship_role_name IS NULL
        OR reference.is_nonblank(dimensional_relationship_role_name)
    ),
    CONSTRAINT ck_dimensional_relationship_basis CHECK (
        dimensional_relationship_basis IS NULL
        OR reference.is_nonblank(dimensional_relationship_basis)
    )
);

-- Every Dimensional mutation participates in the one-revision transaction guard.

-- Supporting read, impact, and parent indexes.
CREATE INDEX ix_dimensional_entity_active_order ON workflow.dimensional_entity (project_id, dimensional_entity_is_active, dimensional_entity_dependency_order);
CREATE INDEX ix_dimensional_attribute_entity_active ON workflow.dimensional_attribute (project_id, dimensional_entity_id, dimensional_attribute_is_active);
CREATE INDEX ix_dimensional_entity_source_logical_entity
    ON workflow.dimensional_entity_source_mapping (project_id, source_logical_entity_id)
    WHERE source_logical_entity_id IS NOT NULL;
CREATE INDEX ix_dimensional_entity_source_context
    ON workflow.dimensional_entity_source_mapping (
        project_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL;
CREATE INDEX ix_dimensional_attribute_source_logical_attribute
    ON workflow.dimensional_attribute_source_mapping (
        project_id,
        source_logical_entity_id,
        source_logical_attribute_id
    ) WHERE source_logical_attribute_id IS NOT NULL;
CREATE INDEX ix_dimensional_attribute_source_context
    ON workflow.dimensional_attribute_source_mapping (
        project_id,
        context_record_id
    ) WHERE context_record_id IS NOT NULL;
CREATE INDEX ix_dimensional_attribute_source_target ON workflow.dimensional_attribute_source_mapping (project_id, dimensional_attribute_id);
CREATE INDEX ix_dimensional_relationship_to ON workflow.dimensional_relationship (project_id, dimensional_relationship_to_entity_id, dimensional_relationship_to_attribute_id);

-- Serialize schema membership and configuration changes through the Project row.
-- Revision increments remain owned by governed Project commands and Apply.
CREATE FUNCTION workflow.guard_entity_schema_membership()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_entity_schema_membership$
DECLARE
    schemas JSONB;
    schema_name TEXT;
BEGIN
    IF TG_TABLE_NAME = 'logical_entity' THEN
        SELECT target.logical_schemas INTO schemas
          FROM project.project AS target WHERE target.project_id = NEW.project_id
          FOR UPDATE;
        schema_name := NEW.logical_entity_schema_name;
    ELSE
        SELECT target.dimensional_schemas INTO schemas
          FROM project.project AS target WHERE target.project_id = NEW.project_id
          FOR UPDATE;
        schema_name := NEW.dimensional_entity_schema_name;
    END IF;
    IF schemas IS NULL OR NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(schemas) AS configured(value)
         WHERE lower(btrim(configured.value ->> 'schema_name')) = lower(btrim(schema_name))
    ) THEN
        RAISE EXCEPTION 'Entity schema is not configured on its Project';
    END IF;
    RETURN NEW;
END;
$guard_entity_schema_membership$;

CREATE TRIGGER guard_entity_schema_membership
BEFORE INSERT OR UPDATE OF project_id, logical_entity_schema_name ON workflow.logical_entity
FOR EACH ROW EXECUTE FUNCTION workflow.guard_entity_schema_membership();
CREATE TRIGGER guard_entity_schema_membership
BEFORE INSERT OR UPDATE OF project_id, dimensional_entity_schema_name ON workflow.dimensional_entity
FOR EACH ROW EXECUTE FUNCTION workflow.guard_entity_schema_membership();

CREATE FUNCTION project.guard_schema_list_references()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_schema_list_references$
BEGIN
    IF NOT project.valid_schema_list(NEW.logical_schemas)
       OR NOT project.valid_schema_list(NEW.dimensional_schemas) THEN
        RAISE EXCEPTION 'Project schema lists are invalid';
    END IF;
    IF EXISTS (
        SELECT 1 FROM workflow.logical_entity AS entity
         WHERE entity.project_id = NEW.project_id
           AND NOT EXISTS (
               SELECT 1 FROM jsonb_array_elements(NEW.logical_schemas) AS configured(value)
                WHERE lower(btrim(configured.value ->> 'schema_name')) =
                      lower(btrim(entity.logical_entity_schema_name))
           )
    ) OR EXISTS (
        SELECT 1 FROM workflow.dimensional_entity AS entity
         WHERE entity.project_id = NEW.project_id
           AND NOT EXISTS (
               SELECT 1 FROM jsonb_array_elements(NEW.dimensional_schemas) AS configured(value)
                WHERE lower(btrim(configured.value ->> 'schema_name')) =
                      lower(btrim(entity.dimensional_entity_schema_name))
           )
    ) THEN
        RAISE EXCEPTION 'A referenced Project schema cannot be removed or renamed';
    END IF;
    RETURN NEW;
END;
$guard_schema_list_references$;

CREATE TRIGGER guard_schema_list_references
BEFORE UPDATE OF logical_schemas, dimensional_schemas ON project.project
FOR EACH ROW EXECUTE FUNCTION project.guard_schema_list_references();

-- Read boundary for modeled layers; all writes retain typed table foreign keys.
CREATE VIEW workflow.modeled_entity AS
SELECT project_id, 'logical_entity'::VARCHAR(30) AS modeled_entity_type,
       logical_entity_id AS modeled_entity_id,
       logical_entity_schema_name AS modeled_entity_schema_name,
       logical_entity_name AS modeled_entity_name,
       logical_entity_definition AS definition, logical_entity_type::TEXT AS classification,
       logical_entity_grain AS grain, logical_entity_dependency_order AS dependency_order,
       logical_entity_is_active AS is_active, logical_entity_is_locked AS is_locked
  FROM workflow.logical_entity
UNION ALL
SELECT project_id, 'dimensional_entity'::VARCHAR(30), dimensional_entity_id,
       dimensional_entity_schema_name, dimensional_entity_name,
       dimensional_entity_definition, dimensional_entity_type::TEXT,
       dimensional_entity_grain_definition, dimensional_entity_dependency_order,
       dimensional_entity_is_active, dimensional_entity_is_locked
  FROM workflow.dimensional_entity;

CREATE VIEW workflow.modeled_attribute AS
SELECT project_id, 'logical_entity'::VARCHAR(30) AS modeled_entity_type,
       logical_entity_id AS modeled_entity_id, logical_attribute_id AS modeled_attribute_id,
       logical_attribute_name AS modeled_attribute_name,
       logical_attribute_name AS attribute_name, logical_attribute_definition AS definition,
       logical_attribute_data_type AS data_type, logical_attribute_is_nullable AS is_nullable,
       logical_attribute_ordinal_position AS ordinal_position,
       logical_attribute_is_natural_key AS is_natural_key,
       logical_attribute_is_surrogate_key AS is_surrogate_key,
       logical_attribute_is_audit_column AS is_audit_column,
       logical_attribute_is_active AS is_active, logical_attribute_is_locked AS is_locked
  FROM workflow.logical_attribute
UNION ALL
SELECT project_id, 'dimensional_entity'::VARCHAR(30), dimensional_entity_id,
       dimensional_attribute_id, dimensional_attribute_name, dimensional_attribute_name, dimensional_attribute_definition,
       dimensional_attribute_data_type, dimensional_attribute_is_nullable,
       dimensional_attribute_ordinal_position, dimensional_attribute_is_natural_key,
       dimensional_attribute_is_surrogate_key, dimensional_attribute_is_audit_column,
       dimensional_attribute_is_active, dimensional_attribute_is_locked
  FROM workflow.dimensional_attribute;
