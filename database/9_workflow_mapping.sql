-- GDS ETL Workbench Release 1: exact combined Mapping plus final DB guards.

CREATE TABLE workflow.object_mapping (
    object_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_entity_id BIGINT,
    dimensional_entity_id BIGINT,
    target_object_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    source_system_dependency_order INTEGER NOT NULL DEFAULT 0,
    target_dependency_order INTEGER NOT NULL DEFAULT 0,
    artifact_type VARCHAR(30),
    artifact_generation_instructions TEXT,
    mapping_profile_key VARCHAR(100),
    mapping_profile_version VARCHAR(50),
    mapping_profile_schema_digest CHAR(64),
    mapping_package_document JSONB,
    mapping_package_digest CHAR(64),
    object_mapping_transformation_document JSONB,
    object_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    object_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_object_mapping_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_logical_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_dimensional_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_target_object FOREIGN KEY (target_object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_mapping_source_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_object_mapping_id_model
        UNIQUE (object_mapping_id, model_id),
    CONSTRAINT uq_object_mapping_witness UNIQUE (
        object_mapping_id,
        model_id,
        modeled_entity_type,
        target_object_id
    ),
    CONSTRAINT ck_object_mapping_typed_entity CHECK (
        (
            modeled_entity_type = 'logical_entity'
            AND logical_entity_id IS NOT NULL
            AND dimensional_entity_id IS NULL
        ) OR (
            modeled_entity_type = 'dimensional_entity'
            AND dimensional_entity_id IS NOT NULL
            AND logical_entity_id IS NULL
        )
    ),
    CONSTRAINT ck_object_mapping_orders CHECK (
        source_system_dependency_order >= 0
        AND target_dependency_order >= 0
    ),
    CONSTRAINT ck_object_mapping_authored_group CHECK (
        (
            artifact_type IS NULL
            AND artifact_generation_instructions IS NULL
            AND mapping_profile_key IS NULL
            AND mapping_profile_version IS NULL
            AND mapping_profile_schema_digest IS NULL
            AND mapping_package_document IS NULL
            AND mapping_package_digest IS NULL
            AND object_mapping_transformation_document IS NULL
        ) OR (
            artifact_type IS NOT NULL
            AND artifact_generation_instructions IS NOT NULL
            AND mapping_profile_key IS NOT NULL
            AND mapping_profile_version IS NOT NULL
            AND mapping_profile_schema_digest IS NOT NULL
            AND mapping_package_document IS NOT NULL
            AND mapping_package_digest IS NOT NULL
            AND object_mapping_transformation_document IS NOT NULL
        )
    ),
    CONSTRAINT ck_object_mapping_artifact_type CHECK (
        artifact_type IS NULL
        OR artifact_type IN ('sql_file', 'python_file', 'python_notebook')
    ),
    CONSTRAINT ck_object_mapping_instructions CHECK (
        artifact_generation_instructions IS NULL
        OR (
            core.is_nonblank(artifact_generation_instructions)
            AND length(artifact_generation_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_object_mapping_profile_key CHECK (
        mapping_profile_key IS NULL
        OR mapping_profile_key ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_object_mapping_profile_version CHECK (
        mapping_profile_version IS NULL
        OR mapping_profile_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),
    CONSTRAINT ck_object_mapping_profile_digest CHECK (
        mapping_profile_schema_digest IS NULL
        OR mapping_profile_schema_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_object_mapping_package CHECK (
        mapping_package_document IS NULL
        OR (
            jsonb_typeof(mapping_package_document) = 'object'
            AND octet_length(mapping_package_document::TEXT) <= 524288
        )
    ),
    CONSTRAINT ck_object_mapping_package_digest CHECK (
        mapping_package_digest IS NULL
        OR mapping_package_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_object_mapping_transformation CHECK (
        object_mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(object_mapping_transformation_document) = 'object'
            AND octet_length(object_mapping_transformation_document::TEXT) <= 262144
            AND object_mapping_transformation_document ->> 'schema_version' = '1.0'
            AND object_mapping_transformation_document ->> 'transformation_kind'
                IN ('direct', 'derived')
        )
    ),
    CONSTRAINT ck_object_mapping_status CHECK (
        object_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_object_mapping_logical_binding
    ON workflow.object_mapping (
        model_id,
        logical_entity_id,
        target_object_id,
        source_system_id
    ) WHERE modeled_entity_type = 'logical_entity';
CREATE UNIQUE INDEX ux_object_mapping_dimensional_binding
    ON workflow.object_mapping (
        model_id,
        dimensional_entity_id,
        target_object_id,
        source_system_id
    ) WHERE modeled_entity_type = 'dimensional_entity';

CREATE TABLE workflow.attribute_mapping (
    attribute_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    object_mapping_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    target_object_id BIGINT NOT NULL,
    logical_attribute_id BIGINT,
    dimensional_attribute_id BIGINT,
    target_attribute_id BIGINT NOT NULL,
    attribute_mapping_transformation_document JSONB,
    attribute_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    attribute_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_attribute_mapping_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_parent FOREIGN KEY (
        object_mapping_id,
        model_id,
        modeled_entity_type,
        target_object_id
    ) REFERENCES workflow.object_mapping (
        object_mapping_id,
        model_id,
        modeled_entity_type,
        target_object_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_logical_attribute FOREIGN KEY (
        logical_attribute_id,
        model_id
    ) REFERENCES workflow.logical_attribute (logical_attribute_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_dimensional_attribute FOREIGN KEY (
        dimensional_attribute_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_mapping_target_attribute FOREIGN KEY (
        target_attribute_id,
        target_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_attribute_mapping_id_model
        UNIQUE (attribute_mapping_id, model_id),
    CONSTRAINT ck_attribute_mapping_typed_attribute CHECK (
        (
            modeled_entity_type = 'logical_entity'
            AND logical_attribute_id IS NOT NULL
            AND dimensional_attribute_id IS NULL
        ) OR (
            modeled_entity_type = 'dimensional_entity'
            AND dimensional_attribute_id IS NOT NULL
            AND logical_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_attribute_mapping_transformation CHECK (
        attribute_mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(attribute_mapping_transformation_document) = 'object'
            AND octet_length(attribute_mapping_transformation_document::TEXT) <= 65536
            AND attribute_mapping_transformation_document ->> 'schema_version' = '1.0'
            AND attribute_mapping_transformation_document ->> 'transformation_kind'
                IN ('direct', 'expression')
        )
    ),
    CONSTRAINT ck_attribute_mapping_status CHECK (
        attribute_mapping_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE UNIQUE INDEX ux_attribute_mapping_logical_binding
    ON workflow.attribute_mapping (
        model_id,
        object_mapping_id,
        logical_attribute_id,
        target_attribute_id
    ) WHERE modeled_entity_type = 'logical_entity';
CREATE UNIQUE INDEX ux_attribute_mapping_dimensional_binding
    ON workflow.attribute_mapping (
        model_id,
        object_mapping_id,
        dimensional_attribute_id,
        target_attribute_id
    ) WHERE modeled_entity_type = 'dimensional_entity';

CREATE TRIGGER capture_object_mapping_change BEFORE INSERT OR UPDATE OR DELETE
ON workflow.object_mapping FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();
CREATE TRIGGER capture_attribute_mapping_change BEFORE INSERT OR UPDATE OR DELETE
ON workflow.attribute_mapping FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();

CREATE INDEX ix_object_mapping_model_package_status
    ON workflow.object_mapping (
        model_id,
        modeled_entity_type,
        target_object_id,
        source_system_id,
        object_mapping_status
    );
CREATE INDEX ix_object_mapping_system_wave
    ON workflow.object_mapping (
        model_id,
        modeled_entity_type,
        source_system_id,
        source_system_dependency_order
    );
CREATE INDEX ix_object_mapping_target_wave
    ON workflow.object_mapping (
        model_id,
        modeled_entity_type,
        target_dependency_order,
        target_object_id
    );
CREATE INDEX ix_object_mapping_logical_entity
    ON workflow.object_mapping (model_id, logical_entity_id)
    WHERE modeled_entity_type = 'logical_entity';
CREATE INDEX ix_object_mapping_dimensional_entity
    ON workflow.object_mapping (model_id, dimensional_entity_id)
    WHERE modeled_entity_type = 'dimensional_entity';
CREATE INDEX ix_object_mapping_source_system
    ON workflow.object_mapping (model_id, source_system_id);
CREATE INDEX ix_object_mapping_locked
    ON workflow.object_mapping (model_id, object_mapping_id)
    WHERE object_mapping_is_locked;
CREATE INDEX ix_attribute_mapping_parent
    ON workflow.attribute_mapping (model_id, object_mapping_id, attribute_mapping_status);
CREATE INDEX ix_attribute_mapping_target
    ON workflow.attribute_mapping (model_id, target_object_id, target_attribute_id);
CREATE INDEX ix_attribute_mapping_logical_attribute
    ON workflow.attribute_mapping (model_id, logical_attribute_id)
    WHERE modeled_entity_type = 'logical_entity';
CREATE INDEX ix_attribute_mapping_dimensional_attribute
    ON workflow.attribute_mapping (model_id, dimensional_attribute_id)
    WHERE modeled_entity_type = 'dimensional_entity';
CREATE INDEX ix_attribute_mapping_locked
    ON workflow.attribute_mapping (model_id, attribute_mapping_id)
    WHERE attribute_mapping_is_locked;

CREATE TABLE core_security.artifact_lock_event (
    artifact_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    artifact_type VARCHAR(100) NOT NULL,
    artifact_id BIGINT NOT NULL,
    artifact_is_locked BOOLEAN NOT NULL,
    acted_by_user_account_id BIGINT NOT NULL,
    lock_reason VARCHAR(2000) NOT NULL,
    model_revision BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_artifact_lock_event_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_artifact_lock_event_actor FOREIGN KEY (acted_by_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_artifact_lock_event_type CHECK (core.is_nonblank(artifact_type)),
    CONSTRAINT ck_artifact_lock_event_id CHECK (artifact_id > 0),
    CONSTRAINT ck_artifact_lock_event_reason CHECK (core.is_nonblank(lock_reason)),
    CONSTRAINT ck_artifact_lock_event_revision CHECK (model_revision > 0)
);

CREATE FUNCTION workflow.is_effective_status(value TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN value IN ('active', 'needs_review');

CREATE FUNCTION workflow.guard_business_lock()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    lock_column TEXT := TG_ARGV[0];
    old_locked BOOLEAN := FALSE;
    new_locked BOOLEAN := FALSE;
    lock_command BOOLEAN := COALESCE(
        current_setting('gds.lock_command', true) = 'on'
        AND current_user = pg_get_userbyid((
            SELECT proowner
              FROM pg_proc
             WHERE oid = 'core_security.set_artifact_lock(bigint,text,bigint,boolean,bigint,text,uuid)'::regprocedure
        )),
        FALSE
    );
BEGIN
    IF TG_OP <> 'INSERT' THEN
        old_locked := COALESCE((to_jsonb(OLD) ->> lock_column)::BOOLEAN, FALSE);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        new_locked := COALESCE((to_jsonb(NEW) ->> lock_column)::BOOLEAN, FALSE);
    END IF;

    IF TG_OP = 'DELETE' AND old_locked THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'locked artifact is immutable';
    ELSIF TG_OP = 'INSERT' AND new_locked AND NOT lock_command THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'ordinary DML cannot set a lock';
    ELSIF TG_OP = 'UPDATE' THEN
        IF old_locked AND NOT lock_command THEN
            RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'locked artifact is immutable';
        END IF;
        IF old_locked IS DISTINCT FROM new_locked AND NOT lock_command THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'ordinary DML cannot toggle a lock';
        END IF;
        IF lock_command AND (
            to_jsonb(NEW) - lock_column - 'updated_time' - 'updated_by'
            IS DISTINCT FROM
            to_jsonb(OLD) - lock_column - 'updated_time' - 'updated_by'
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'lock command may change only lock and audit fields';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.guard_identity_witness()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    old_row JSONB := to_jsonb(OLD);
    new_row JSONB := to_jsonb(NEW);
    identity_column TEXT;
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_NARGS = 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'identity guard requires an immutable-column manifest';
    END IF;

    FOREACH identity_column IN ARRAY TG_ARGV LOOP
        IF NOT (old_row ? identity_column) OR NOT (new_row ? identity_column) THEN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = format(
                    'identity guard column %s does not exist on %s.%s',
                    identity_column,
                    TG_TABLE_SCHEMA,
                    TG_TABLE_NAME
                );
        END IF;
        IF old_row -> identity_column IS DISTINCT FROM new_row -> identity_column THEN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = format(
                    '%s.%s identity witness %s is immutable',
                    TG_TABLE_SCHEMA,
                    TG_TABLE_NAME,
                    identity_column
                );
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.guard_locked_ancestor()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    row_value JSONB := COALESCE(to_jsonb(NEW), to_jsonb(OLD));
    blocked BOOLEAN := FALSE;
BEGIN
    IF TG_TABLE_NAME = 'conceptual_support' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.conceptual_object
             WHERE conceptual_object_id = (row_value ->> 'conceptual_object_id')::BIGINT
               AND conceptual_object_is_locked
            UNION ALL
            SELECT 1 FROM workflow.conceptual_relationship
             WHERE conceptual_relationship_id = (row_value ->> 'conceptual_relationship_id')::BIGINT
               AND conceptual_relationship_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'logical_entity_submodel' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.logical_entity
             WHERE logical_entity_id = (row_value ->> 'logical_entity_id')::BIGINT
               AND logical_entity_is_locked
            UNION ALL
            SELECT 1 FROM workflow.logical_submodel
             WHERE logical_submodel_id = (row_value ->> 'logical_submodel_id')::BIGINT
               AND logical_submodel_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'logical_attribute' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.logical_entity
             WHERE logical_entity_id = (row_value ->> 'logical_entity_id')::BIGINT
               AND logical_entity_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'logical_entity_source_mapping' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.logical_entity
             WHERE logical_entity_id = (row_value ->> 'logical_entity_id')::BIGINT
               AND logical_entity_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'logical_attribute_source_mapping' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.logical_entity
             WHERE logical_entity_id = (row_value ->> 'logical_entity_id')::BIGINT
               AND logical_entity_is_locked
            UNION ALL
            SELECT 1 FROM workflow.logical_attribute
             WHERE logical_attribute_id = (row_value ->> 'logical_attribute_id')::BIGINT
               AND logical_attribute_is_locked
            UNION ALL
            SELECT 1 FROM workflow.logical_entity_source_mapping
             WHERE logical_entity_source_mapping_id =
                   (row_value ->> 'logical_entity_source_mapping_id')::BIGINT
               AND logical_entity_source_mapping_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'dimensional_entity_submodel' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.dimensional_entity
             WHERE dimensional_entity_id = (row_value ->> 'dimensional_entity_id')::BIGINT
               AND dimensional_entity_is_locked
            UNION ALL
            SELECT 1 FROM workflow.dimensional_submodel
             WHERE dimensional_submodel_id = (row_value ->> 'dimensional_submodel_id')::BIGINT
               AND dimensional_submodel_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'dimensional_attribute' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.dimensional_entity
             WHERE dimensional_entity_id = (row_value ->> 'dimensional_entity_id')::BIGINT
               AND dimensional_entity_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'dimensional_entity_source_mapping' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.dimensional_entity
             WHERE dimensional_entity_id = (row_value ->> 'dimensional_entity_id')::BIGINT
               AND dimensional_entity_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'dimensional_attribute_source_mapping' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.dimensional_entity
             WHERE dimensional_entity_id = (row_value ->> 'dimensional_entity_id')::BIGINT
               AND dimensional_entity_is_locked
            UNION ALL
            SELECT 1 FROM workflow.dimensional_attribute
             WHERE dimensional_attribute_id = (row_value ->> 'dimensional_attribute_id')::BIGINT
               AND dimensional_attribute_is_locked
            UNION ALL
            SELECT 1 FROM workflow.dimensional_entity_source_mapping
             WHERE dimensional_entity_source_mapping_id =
                   (row_value ->> 'dimensional_entity_source_mapping_id')::BIGINT
               AND dimensional_entity_source_mapping_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'attribute_mapping' THEN
        SELECT EXISTS (
            SELECT 1 FROM workflow.object_mapping
             WHERE object_mapping_id = (row_value ->> 'object_mapping_id')::BIGINT
               AND object_mapping_is_locked
        ) INTO blocked;
    END IF;

    IF blocked THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'locked aggregate ancestor protects this row';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.assert_effective_graph()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    -- Profiles, Analysis, and Conceptual physical support are sourced only
    -- from active Bronze Objects in authoritative Model Scope.
    IF EXISTS (
        SELECT 1
          FROM workflow.attribute_profile AS profile
          JOIN core.object AS source_object
            ON source_object.object_id = profile.object_id
          JOIN core.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
     LEFT JOIN model.model_scope AS source_scope
            ON source_scope.model_id = profile.model_id
           AND source_scope.object_id = profile.object_id
         WHERE source_scope.object_id IS NULL
            OR NOT source_object.is_active
            OR NOT source_zone.is_active
            OR source_zone.zone_code <> 'bronze'
    ) OR EXISTS (
        SELECT 1
          FROM workflow.analysis_result AS analysis
          JOIN core.object AS from_object
            ON from_object.object_id = analysis.from_object_id
          JOIN core.zone AS from_zone ON from_zone.zone_id = from_object.zone_id
          JOIN core.object AS to_object
            ON to_object.object_id = analysis.to_object_id
          JOIN core.zone AS to_zone ON to_zone.zone_id = to_object.zone_id
     LEFT JOIN model.model_scope AS from_scope
            ON from_scope.model_id = analysis.model_id
           AND from_scope.object_id = analysis.from_object_id
     LEFT JOIN model.model_scope AS to_scope
            ON to_scope.model_id = analysis.model_id
           AND to_scope.object_id = analysis.to_object_id
         WHERE workflow.is_effective_status(analysis.analysis_result_status)
           AND (
               from_scope.object_id IS NULL
               OR to_scope.object_id IS NULL
               OR NOT from_object.is_active
               OR NOT from_zone.is_active
               OR from_zone.zone_code <> 'bronze'
               OR NOT to_object.is_active
               OR NOT to_zone.is_active
               OR to_zone.zone_code <> 'bronze'
           )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'Profile and Analysis sources require active scoped Bronze Objects';
    END IF;

    -- Evidence Records cannot remain effective beneath an inactive document.
    IF EXISTS (
        SELECT 1
        FROM model.modeling_evidence_record AS record
        JOIN model.modeling_evidence_document AS document
          ON document.modeling_evidence_document_id = record.modeling_evidence_document_id
         AND document.model_id = record.model_id
        WHERE workflow.is_effective_status(record.modeling_evidence_record_status)
          AND NOT document.is_active
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'effective Evidence Record requires an active document';
    END IF;

    -- Conceptual Support and Relationships require effective parents and active physical support.
    IF EXISTS (
        SELECT 1
        FROM workflow.conceptual_relationship AS relationship
        JOIN workflow.conceptual_object AS from_object
          ON from_object.conceptual_object_id = relationship.from_conceptual_object_id
         AND from_object.model_id = relationship.model_id
        JOIN workflow.conceptual_object AS to_object
          ON to_object.conceptual_object_id = relationship.to_conceptual_object_id
         AND to_object.model_id = relationship.model_id
        WHERE workflow.is_effective_status(relationship.conceptual_relationship_status)
          AND (
              NOT workflow.is_effective_status(from_object.conceptual_object_status)
              OR NOT workflow.is_effective_status(to_object.conceptual_object_status)
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.conceptual_support AS support
        LEFT JOIN workflow.conceptual_object AS object_parent
          ON object_parent.conceptual_object_id = support.conceptual_object_id
         AND object_parent.model_id = support.model_id
        LEFT JOIN workflow.conceptual_relationship AS relationship_parent
          ON relationship_parent.conceptual_relationship_id = support.conceptual_relationship_id
         AND relationship_parent.model_id = support.model_id
        JOIN core.object AS source_object ON source_object.object_id = support.object_id
        JOIN core.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
   LEFT JOIN model.model_scope AS source_scope
          ON source_scope.model_id = support.model_id
         AND source_scope.object_id = support.object_id
        WHERE workflow.is_effective_status(support.conceptual_support_status)
          AND (
              source_scope.object_id IS NULL
              OR NOT source_object.is_active
              OR NOT source_zone.is_active
              OR source_zone.zone_code <> 'bronze'
              OR (
                  support.supported_artifact_type = 'conceptual_object'
                  AND NOT workflow.is_effective_status(object_parent.conceptual_object_status)
              )
              OR (
                  support.supported_artifact_type = 'conceptual_relationship'
                  AND NOT workflow.is_effective_status(
                      relationship_parent.conceptual_relationship_status
                  )
              )
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid effective Conceptual dependency';
    END IF;

    -- Logical parent closure, Bronze eligibility, ordinals, and audit policy.
    IF EXISTS (
        SELECT 1
        FROM workflow.logical_entity_submodel AS membership
        JOIN workflow.logical_entity AS entity
          ON entity.logical_entity_id = membership.logical_entity_id
         AND entity.model_id = membership.model_id
        JOIN workflow.logical_submodel AS submodel
          ON submodel.logical_submodel_id = membership.logical_submodel_id
         AND submodel.model_id = membership.model_id
        WHERE workflow.is_effective_status(membership.logical_entity_submodel_status)
          AND (
              NOT workflow.is_effective_status(entity.logical_entity_status)
              OR NOT workflow.is_effective_status(submodel.logical_submodel_status)
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.logical_attribute AS attribute
        JOIN workflow.logical_entity AS entity
          ON entity.logical_entity_id = attribute.logical_entity_id
         AND entity.model_id = attribute.model_id
        WHERE workflow.is_effective_status(attribute.logical_attribute_status)
          AND NOT workflow.is_effective_status(entity.logical_entity_status)
    ) OR EXISTS (
        SELECT 1
        FROM workflow.logical_entity_source_mapping AS source_mapping
        JOIN workflow.logical_entity AS entity
          ON entity.logical_entity_id = source_mapping.logical_entity_id
         AND entity.model_id = source_mapping.model_id
        JOIN core.object AS source_object
          ON source_object.object_id = source_mapping.source_object_id
        JOIN core.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
   LEFT JOIN model.model_scope AS source_scope
          ON source_scope.model_id = source_mapping.model_id
         AND source_scope.object_id = source_mapping.source_object_id
        WHERE workflow.is_effective_status(source_mapping.logical_entity_source_mapping_status)
          AND (
              NOT workflow.is_effective_status(entity.logical_entity_status)
              OR source_scope.object_id IS NULL
              OR NOT source_object.is_active
              OR NOT source_zone.is_active
              OR source_zone.zone_code <> 'bronze'
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.logical_attribute_source_mapping AS source_mapping
        JOIN workflow.logical_entity_source_mapping AS parent_mapping
          ON parent_mapping.logical_entity_source_mapping_id =
             source_mapping.logical_entity_source_mapping_id
         AND parent_mapping.model_id = source_mapping.model_id
        JOIN workflow.logical_attribute AS attribute
          ON attribute.logical_attribute_id = source_mapping.logical_attribute_id
         AND attribute.model_id = source_mapping.model_id
        JOIN core.attribute AS source_attribute
          ON source_attribute.attribute_id = source_mapping.source_attribute_id
         AND source_attribute.object_id = source_mapping.source_object_id
   LEFT JOIN model.model_scope AS source_scope
          ON source_scope.model_id = source_mapping.model_id
         AND source_scope.object_id = source_mapping.source_object_id
        WHERE workflow.is_effective_status(source_mapping.logical_attribute_source_mapping_status)
          AND (
              NOT workflow.is_effective_status(parent_mapping.logical_entity_source_mapping_status)
              OR NOT workflow.is_effective_status(attribute.logical_attribute_status)
              OR source_scope.object_id IS NULL
              OR NOT source_attribute.is_active
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.logical_relationship AS relationship
        JOIN workflow.logical_entity AS from_entity
          ON from_entity.logical_entity_id = relationship.logical_relationship_from_entity_id
         AND from_entity.model_id = relationship.model_id
        JOIN workflow.logical_entity AS to_entity
          ON to_entity.logical_entity_id = relationship.logical_relationship_to_entity_id
         AND to_entity.model_id = relationship.model_id
        JOIN workflow.logical_attribute AS from_attribute
          ON from_attribute.logical_attribute_id = relationship.logical_relationship_from_attribute_id
         AND from_attribute.model_id = relationship.model_id
        JOIN workflow.logical_attribute AS to_attribute
          ON to_attribute.logical_attribute_id = relationship.logical_relationship_to_attribute_id
         AND to_attribute.model_id = relationship.model_id
        WHERE workflow.is_effective_status(relationship.logical_relationship_status)
          AND (
              NOT workflow.is_effective_status(from_entity.logical_entity_status)
              OR NOT workflow.is_effective_status(to_entity.logical_entity_status)
              OR NOT workflow.is_effective_status(from_attribute.logical_attribute_status)
              OR NOT workflow.is_effective_status(to_attribute.logical_attribute_status)
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.logical_attribute
        WHERE workflow.is_effective_status(logical_attribute_status)
        GROUP BY model_id, logical_entity_id, logical_attribute_ordinal_position
        HAVING count(*) > 1
    ) OR EXISTS (
        SELECT 1
        FROM workflow.logical_attribute AS attribute
        JOIN workflow.logical_attribute_source_mapping AS source_mapping
          ON source_mapping.logical_attribute_id = attribute.logical_attribute_id
         AND source_mapping.model_id = attribute.model_id
        WHERE workflow.is_effective_status(attribute.logical_attribute_status)
          AND attribute.logical_attribute_is_audit_column
          AND workflow.is_effective_status(source_mapping.logical_attribute_source_mapping_status)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid effective Logical graph';
    END IF;

    -- Dimensional parent closure, grain, policy, Silver eligibility, and ordinals.
    IF EXISTS (
        SELECT 1
        FROM workflow.dimensional_entity_submodel AS membership
        JOIN workflow.dimensional_entity AS entity
          ON entity.dimensional_entity_id = membership.dimensional_entity_id
         AND entity.model_id = membership.model_id
        JOIN workflow.dimensional_submodel AS submodel
          ON submodel.dimensional_submodel_id = membership.dimensional_submodel_id
         AND submodel.model_id = membership.model_id
        WHERE workflow.is_effective_status(membership.dimensional_entity_submodel_status)
          AND (
              NOT workflow.is_effective_status(entity.dimensional_entity_status)
              OR NOT workflow.is_effective_status(submodel.dimensional_submodel_status)
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_attribute AS attribute
        JOIN workflow.dimensional_entity AS entity
          ON entity.dimensional_entity_id = attribute.dimensional_entity_id
         AND entity.model_id = attribute.model_id
        WHERE workflow.is_effective_status(attribute.dimensional_attribute_status)
          AND (
              NOT workflow.is_effective_status(entity.dimensional_entity_status)
              OR (
                  attribute.dimensional_attribute_change_behavior IS NOT NULL
                  AND entity.dimensional_entity_type <> 'dimension'
              )
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_entity AS entity
        WHERE workflow.is_effective_status(entity.dimensional_entity_status)
          AND entity.dimensional_entity_type IN ('fact', 'bridge')
          AND NOT EXISTS (
              SELECT 1
              FROM workflow.dimensional_attribute AS attribute
              WHERE attribute.model_id = entity.model_id
                AND attribute.dimensional_entity_id = entity.dimensional_entity_id
                AND workflow.is_effective_status(attribute.dimensional_attribute_status)
                AND attribute.dimensional_attribute_is_grain_component
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_attribute AS attribute
        JOIN model.model AS owning_model ON owning_model.model_id = attribute.model_id
        WHERE workflow.is_effective_status(attribute.dimensional_attribute_status)
          AND attribute.dimensional_attribute_change_behavior = 'historize'
          AND owning_model.gold_model_technical_columns_template IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_entity_source_mapping AS source_mapping
        JOIN workflow.dimensional_entity AS entity
          ON entity.dimensional_entity_id = source_mapping.dimensional_entity_id
         AND entity.model_id = source_mapping.model_id
        JOIN core.object AS source_object
          ON source_object.object_id = source_mapping.source_object_id
        JOIN core.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
        WHERE workflow.is_effective_status(source_mapping.dimensional_entity_source_mapping_status)
          AND (
              NOT workflow.is_effective_status(entity.dimensional_entity_status)
              OR NOT source_object.is_active
              OR NOT source_zone.is_active
              OR source_zone.zone_code <> 'silver'
              OR NOT EXISTS (
                  SELECT 1
                  FROM workflow.object_mapping AS mapping
                  WHERE mapping.model_id = source_mapping.model_id
                    AND mapping.modeled_entity_type = 'logical_entity'
                    AND mapping.target_object_id = source_mapping.source_object_id
                    AND workflow.is_effective_status(mapping.object_mapping_status)
              )
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_attribute_source_mapping AS source_mapping
        JOIN workflow.dimensional_entity_source_mapping AS parent_mapping
          ON parent_mapping.dimensional_entity_source_mapping_id =
             source_mapping.dimensional_entity_source_mapping_id
         AND parent_mapping.model_id = source_mapping.model_id
        JOIN workflow.dimensional_attribute AS attribute
          ON attribute.dimensional_attribute_id = source_mapping.dimensional_attribute_id
         AND attribute.model_id = source_mapping.model_id
        JOIN core.attribute AS source_attribute
          ON source_attribute.attribute_id = source_mapping.source_attribute_id
         AND source_attribute.object_id = source_mapping.source_object_id
        WHERE workflow.is_effective_status(source_mapping.dimensional_attribute_source_mapping_status)
          AND (
              NOT workflow.is_effective_status(parent_mapping.dimensional_entity_source_mapping_status)
              OR NOT workflow.is_effective_status(attribute.dimensional_attribute_status)
              OR NOT source_attribute.is_active
              OR NOT EXISTS (
                  SELECT 1
                  FROM workflow.attribute_mapping AS mapping
                  JOIN workflow.object_mapping AS header
                    ON header.object_mapping_id = mapping.object_mapping_id
                   AND header.model_id = mapping.model_id
                  WHERE mapping.model_id = source_mapping.model_id
                    AND mapping.modeled_entity_type = 'logical_entity'
                    AND mapping.target_attribute_id = source_mapping.source_attribute_id
                    AND header.target_object_id = source_mapping.source_object_id
                    AND workflow.is_effective_status(mapping.attribute_mapping_status)
                    AND workflow.is_effective_status(header.object_mapping_status)
              )
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_relationship AS relationship
        JOIN workflow.dimensional_entity AS from_entity
          ON from_entity.dimensional_entity_id = relationship.dimensional_relationship_from_entity_id
         AND from_entity.model_id = relationship.model_id
        JOIN workflow.dimensional_entity AS to_entity
          ON to_entity.dimensional_entity_id = relationship.dimensional_relationship_to_entity_id
         AND to_entity.model_id = relationship.model_id
        JOIN workflow.dimensional_attribute AS from_attribute
          ON from_attribute.dimensional_attribute_id = relationship.dimensional_relationship_from_attribute_id
         AND from_attribute.model_id = relationship.model_id
        JOIN workflow.dimensional_attribute AS to_attribute
          ON to_attribute.dimensional_attribute_id = relationship.dimensional_relationship_to_attribute_id
         AND to_attribute.model_id = relationship.model_id
        WHERE workflow.is_effective_status(relationship.dimensional_relationship_status)
          AND (
              NOT workflow.is_effective_status(from_entity.dimensional_entity_status)
              OR NOT workflow.is_effective_status(to_entity.dimensional_entity_status)
              OR NOT workflow.is_effective_status(from_attribute.dimensional_attribute_status)
              OR NOT workflow.is_effective_status(to_attribute.dimensional_attribute_status)
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_attribute
        WHERE workflow.is_effective_status(dimensional_attribute_status)
        GROUP BY model_id, dimensional_entity_id, dimensional_attribute_ordinal_position
        HAVING count(*) > 1
    ) OR EXISTS (
        SELECT 1
        FROM workflow.dimensional_attribute AS attribute
        JOIN workflow.dimensional_attribute_source_mapping AS source_mapping
          ON source_mapping.dimensional_attribute_id = attribute.dimensional_attribute_id
         AND source_mapping.model_id = attribute.model_id
        WHERE workflow.is_effective_status(attribute.dimensional_attribute_status)
          AND attribute.dimensional_attribute_is_audit_column
          AND workflow.is_effective_status(source_mapping.dimensional_attribute_source_mapping_status)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid effective Dimensional graph';
    END IF;

    -- Combined Mapping route, typed parentage, source System, and package invariants.
    IF EXISTS (
        SELECT 1
        FROM workflow.object_mapping AS mapping
        JOIN core.object AS target_object ON target_object.object_id = mapping.target_object_id
        JOIN core.zone AS target_zone ON target_zone.zone_id = target_object.zone_id
        JOIN core.system AS source_system ON source_system.system_id = mapping.source_system_id
        LEFT JOIN workflow.logical_entity AS logical_entity
          ON logical_entity.logical_entity_id = mapping.logical_entity_id
         AND logical_entity.model_id = mapping.model_id
        LEFT JOIN workflow.dimensional_entity AS dimensional_entity
          ON dimensional_entity.dimensional_entity_id = mapping.dimensional_entity_id
         AND dimensional_entity.model_id = mapping.model_id
        WHERE workflow.is_effective_status(mapping.object_mapping_status)
          AND (
              NOT target_object.is_active
              OR NOT target_zone.is_active
              OR NOT source_system.is_active
              OR (
                  mapping.modeled_entity_type = 'logical_entity'
                  AND (
                      target_zone.zone_code <> 'silver'
                      OR NOT workflow.is_effective_status(logical_entity.logical_entity_status)
                      OR NOT EXISTS (
                          SELECT 1
                            FROM workflow.logical_entity_source_mapping AS source_mapping
                            JOIN core.object AS source_object
                              ON source_object.object_id = source_mapping.source_object_id
                            JOIN core.connection AS source_connection
                              ON source_connection.connection_id = source_object.connection_id
                           WHERE source_mapping.model_id = mapping.model_id
                             AND source_mapping.logical_entity_id = mapping.logical_entity_id
                             AND source_connection.system_id = mapping.source_system_id
                             AND workflow.is_effective_status(
                                 source_mapping.logical_entity_source_mapping_status
                             )
                      )
                  )
              )
              OR (
                  mapping.modeled_entity_type = 'dimensional_entity'
                  AND (
                      target_zone.zone_code <> 'gold'
                      OR NOT workflow.is_effective_status(
                          dimensional_entity.dimensional_entity_status
                      )
                      OR NOT EXISTS (
                          SELECT 1
                            FROM workflow.dimensional_entity_source_mapping
                                 AS dimensional_source
                            JOIN workflow.object_mapping AS logical_header
                              ON logical_header.model_id = dimensional_source.model_id
                             AND logical_header.modeled_entity_type = 'logical_entity'
                             AND logical_header.target_object_id =
                                 dimensional_source.source_object_id
                             AND logical_header.source_system_id = mapping.source_system_id
                           WHERE dimensional_source.model_id = mapping.model_id
                             AND dimensional_source.dimensional_entity_id =
                                 mapping.dimensional_entity_id
                             AND workflow.is_effective_status(
                                 dimensional_source.dimensional_entity_source_mapping_status
                             )
                             AND workflow.is_effective_status(
                                 logical_header.object_mapping_status
                             )
                      )
                  )
              )
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.attribute_mapping AS mapping
        JOIN workflow.object_mapping AS header
          ON header.object_mapping_id = mapping.object_mapping_id
         AND header.model_id = mapping.model_id
        JOIN core.attribute AS target_attribute
          ON target_attribute.attribute_id = mapping.target_attribute_id
         AND target_attribute.object_id = mapping.target_object_id
        LEFT JOIN workflow.logical_attribute AS logical_attribute
          ON logical_attribute.logical_attribute_id = mapping.logical_attribute_id
         AND logical_attribute.model_id = mapping.model_id
        LEFT JOIN workflow.dimensional_attribute AS dimensional_attribute
          ON dimensional_attribute.dimensional_attribute_id = mapping.dimensional_attribute_id
         AND dimensional_attribute.model_id = mapping.model_id
        WHERE workflow.is_effective_status(mapping.attribute_mapping_status)
          AND (
              NOT workflow.is_effective_status(header.object_mapping_status)
              OR NOT target_attribute.is_active
              OR (
                  mapping.modeled_entity_type = 'logical_entity'
                  AND (
                      NOT workflow.is_effective_status(logical_attribute.logical_attribute_status)
                      OR logical_attribute.logical_entity_id <> header.logical_entity_id
                  )
              )
              OR (
                  mapping.modeled_entity_type = 'dimensional_entity'
                  AND (
                      NOT workflow.is_effective_status(
                          dimensional_attribute.dimensional_attribute_status
                      )
                      OR dimensional_attribute.dimensional_entity_id <>
                         header.dimensional_entity_id
                  )
              )
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.object_mapping AS left_header
        JOIN workflow.object_mapping AS right_header
          ON right_header.model_id = left_header.model_id
         AND right_header.modeled_entity_type = left_header.modeled_entity_type
         AND right_header.target_object_id = left_header.target_object_id
         AND right_header.source_system_id = left_header.source_system_id
         AND right_header.object_mapping_id > left_header.object_mapping_id
        WHERE workflow.is_effective_status(left_header.object_mapping_status)
          AND workflow.is_effective_status(right_header.object_mapping_status)
          AND (
              left_header.artifact_type IS DISTINCT FROM right_header.artifact_type
              OR left_header.artifact_generation_instructions IS DISTINCT FROM
                 right_header.artifact_generation_instructions
              OR left_header.mapping_profile_key IS DISTINCT FROM right_header.mapping_profile_key
              OR left_header.mapping_profile_version IS DISTINCT FROM right_header.mapping_profile_version
              OR left_header.mapping_profile_schema_digest IS DISTINCT FROM
                 right_header.mapping_profile_schema_digest
              OR left_header.mapping_package_document IS DISTINCT FROM
                 right_header.mapping_package_document
              OR left_header.mapping_package_digest IS DISTINCT FROM
                 right_header.mapping_package_digest
              OR left_header.source_system_dependency_order IS DISTINCT FROM
                 right_header.source_system_dependency_order
              OR left_header.target_dependency_order IS DISTINCT FROM
                 right_header.target_dependency_order
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.object_mapping
        WHERE workflow.is_effective_status(object_mapping_status)
        GROUP BY model_id, modeled_entity_type, source_system_id
        HAVING min(source_system_dependency_order) <>
               max(source_system_dependency_order)
    ) OR EXISTS (
        SELECT 1
        FROM workflow.object_mapping
        WHERE workflow.is_effective_status(object_mapping_status)
        GROUP BY model_id, modeled_entity_type, target_object_id
        HAVING min(target_dependency_order) <>
               max(target_dependency_order)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid effective Mapping graph';
    END IF;

    RETURN NULL;
END;
$$;

-- Business locks are enforced on every curated lock-bearing family.
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON model.modeling_evidence_record FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('modeling_evidence_record_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.analysis_result FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('analysis_result_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.conceptual_object FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('conceptual_object_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.conceptual_relationship FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('conceptual_relationship_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.conceptual_support FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('conceptual_support_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_submodel FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_submodel_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_entity FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_entity_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_submodel FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_entity_submodel_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_attribute_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_source_mapping FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_entity_source_mapping_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute_source_mapping FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_attribute_source_mapping_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_relationship FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('logical_relationship_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_submodel FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_submodel_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_entity_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_submodel FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_entity_submodel_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_attribute_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_source_mapping FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_entity_source_mapping_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute_source_mapping FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_attribute_source_mapping_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_relationship FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('dimensional_relationship_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.object_mapping FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('object_mapping_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.attribute_mapping FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('attribute_mapping_is_locked');

-- Stable generated IDs, Model ownership, parentage, and repeated relational
-- witnesses are immutable. Authored content, lifecycle, lock, and audit fields
-- remain updateable through their dedicated guards.
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON model.modeling_evidence_document FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'modeling_evidence_document_id', 'model_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON model.modeling_evidence_record FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'modeling_evidence_record_id', 'model_id',
    'modeling_evidence_document_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.attribute_profile FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('model_id', 'attribute_id', 'object_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.analysis_result FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'analysis_result_id', 'model_id',
    'from_object_id', 'from_attribute_id',
    'to_object_id', 'to_attribute_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.conceptual_object FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('conceptual_object_id', 'model_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.conceptual_relationship FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'conceptual_relationship_id', 'model_id',
    'from_conceptual_object_id', 'to_conceptual_object_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.conceptual_support FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'conceptual_support_id', 'model_id', 'supported_artifact_type',
    'conceptual_object_id', 'conceptual_relationship_id', 'object_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_submodel FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('logical_submodel_id', 'model_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_entity FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('logical_entity_id', 'model_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_entity_submodel FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'logical_entity_submodel_id', 'model_id',
    'logical_entity_id', 'logical_submodel_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_attribute FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'logical_attribute_id', 'model_id', 'logical_entity_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_entity_source_mapping FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'logical_entity_source_mapping_id', 'model_id',
    'logical_entity_id', 'source_object_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_attribute_source_mapping FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'logical_attribute_source_mapping_id', 'model_id',
    'logical_entity_source_mapping_id', 'logical_entity_id',
    'logical_attribute_id', 'source_object_id', 'source_attribute_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.logical_relationship FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'logical_relationship_id', 'model_id',
    'logical_relationship_from_entity_id',
    'logical_relationship_from_attribute_id',
    'logical_relationship_to_entity_id',
    'logical_relationship_to_attribute_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_submodel FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('dimensional_submodel_id', 'model_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_entity FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('dimensional_entity_id', 'model_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_entity_submodel FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'dimensional_entity_submodel_id', 'model_id',
    'dimensional_entity_id', 'dimensional_submodel_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_attribute FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'dimensional_attribute_id', 'model_id', 'dimensional_entity_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_entity_source_mapping FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'dimensional_entity_source_mapping_id', 'model_id',
    'dimensional_entity_id', 'source_object_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_attribute_source_mapping FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'dimensional_attribute_source_mapping_id', 'model_id',
    'dimensional_entity_source_mapping_id', 'dimensional_entity_id',
    'dimensional_attribute_id', 'source_object_id', 'source_attribute_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.dimensional_relationship FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'dimensional_relationship_id', 'model_id',
    'dimensional_relationship_from_entity_id',
    'dimensional_relationship_from_attribute_id',
    'dimensional_relationship_to_entity_id',
    'dimensional_relationship_to_attribute_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.object_mapping FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'object_mapping_id', 'model_id', 'modeled_entity_type',
    'logical_entity_id', 'dimensional_entity_id',
    'target_object_id', 'source_system_id'
);
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON workflow.attribute_mapping FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'attribute_mapping_id', 'model_id', 'object_mapping_id',
    'modeled_entity_type', 'target_object_id',
    'logical_attribute_id', 'dimensional_attribute_id',
    'target_attribute_id'
);

CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.conceptual_support FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_submodel FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_source_mapping FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute_source_mapping FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_submodel FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_source_mapping FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute_source_mapping FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON workflow.attribute_mapping FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();

-- Deferred whole-graph checks run against final transaction state.
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON model.modeling_evidence_document DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE
ON model.model DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON model.modeling_evidence_record DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON model.model_scope DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.attribute_profile DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.analysis_result DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.conceptual_object DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.conceptual_relationship DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.conceptual_support DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_submodel DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_entity DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_submodel DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_source_mapping DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute_source_mapping DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_relationship DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_submodel DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_submodel DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_source_mapping DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute_source_mapping DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_relationship DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.object_mapping DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON workflow.attribute_mapping DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON core.object DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON core.attribute DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON core.zone DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();
CREATE CONSTRAINT TRIGGER validate_effective_graph AFTER INSERT OR UPDATE OR DELETE
ON core.system DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workflow.assert_effective_graph();

CREATE TRIGGER guard_artifact_lock_event_append_only
BEFORE UPDATE OR DELETE ON core_security.artifact_lock_event
FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();

CREATE INDEX ix_artifact_lock_event_model_created
    ON core_security.artifact_lock_event (model_id, created_time);
CREATE INDEX ix_artifact_lock_event_actor_created
    ON core_security.artifact_lock_event (
        acted_by_user_account_id,
        created_time
    );

CREATE FUNCTION core_security.set_artifact_lock(
    target_model_id BIGINT,
    target_artifact_type TEXT,
    target_artifact_id BIGINT,
    target_is_locked BOOLEAN,
    actor_user_account_id BIGINT,
    reason TEXT,
    target_correlation_id UUID
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    target_schema TEXT;
    target_table TEXT;
    target_id_column TEXT;
    target_lock_column TEXT;
    target_count BIGINT;
    current_lock BOOLEAN;
    resulting_revision BIGINT;
BEGIN
    IF target_model_id IS NULL
       OR target_artifact_id IS NULL
       OR target_artifact_id <= 0
       OR NOT core.is_nonblank(target_artifact_type)
       OR NOT core.is_nonblank(reason)
       OR target_correlation_id IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid artifact lock request';
    END IF;

    CASE target_artifact_type
        WHEN 'modeling_evidence_record' THEN
            target_schema := 'model'; target_table := 'modeling_evidence_record';
            target_id_column := 'modeling_evidence_record_id';
            target_lock_column := 'modeling_evidence_record_is_locked';
        WHEN 'analysis_result' THEN
            target_schema := 'workflow'; target_table := 'analysis_result';
            target_id_column := 'analysis_result_id'; target_lock_column := 'analysis_result_is_locked';
        WHEN 'conceptual_object' THEN
            target_schema := 'workflow'; target_table := 'conceptual_object';
            target_id_column := 'conceptual_object_id'; target_lock_column := 'conceptual_object_is_locked';
        WHEN 'conceptual_relationship' THEN
            target_schema := 'workflow'; target_table := 'conceptual_relationship';
            target_id_column := 'conceptual_relationship_id'; target_lock_column := 'conceptual_relationship_is_locked';
        WHEN 'conceptual_support' THEN
            target_schema := 'workflow'; target_table := 'conceptual_support';
            target_id_column := 'conceptual_support_id'; target_lock_column := 'conceptual_support_is_locked';
        WHEN 'logical_submodel' THEN
            target_schema := 'workflow'; target_table := 'logical_submodel';
            target_id_column := 'logical_submodel_id'; target_lock_column := 'logical_submodel_is_locked';
        WHEN 'logical_entity' THEN
            target_schema := 'workflow'; target_table := 'logical_entity';
            target_id_column := 'logical_entity_id'; target_lock_column := 'logical_entity_is_locked';
        WHEN 'logical_entity_submodel' THEN
            target_schema := 'workflow'; target_table := 'logical_entity_submodel';
            target_id_column := 'logical_entity_submodel_id'; target_lock_column := 'logical_entity_submodel_is_locked';
        WHEN 'logical_attribute' THEN
            target_schema := 'workflow'; target_table := 'logical_attribute';
            target_id_column := 'logical_attribute_id'; target_lock_column := 'logical_attribute_is_locked';
        WHEN 'logical_entity_source_mapping' THEN
            target_schema := 'workflow'; target_table := 'logical_entity_source_mapping';
            target_id_column := 'logical_entity_source_mapping_id'; target_lock_column := 'logical_entity_source_mapping_is_locked';
        WHEN 'logical_attribute_source_mapping' THEN
            target_schema := 'workflow'; target_table := 'logical_attribute_source_mapping';
            target_id_column := 'logical_attribute_source_mapping_id'; target_lock_column := 'logical_attribute_source_mapping_is_locked';
        WHEN 'logical_relationship' THEN
            target_schema := 'workflow'; target_table := 'logical_relationship';
            target_id_column := 'logical_relationship_id'; target_lock_column := 'logical_relationship_is_locked';
        WHEN 'dimensional_submodel' THEN
            target_schema := 'workflow'; target_table := 'dimensional_submodel';
            target_id_column := 'dimensional_submodel_id'; target_lock_column := 'dimensional_submodel_is_locked';
        WHEN 'dimensional_entity' THEN
            target_schema := 'workflow'; target_table := 'dimensional_entity';
            target_id_column := 'dimensional_entity_id'; target_lock_column := 'dimensional_entity_is_locked';
        WHEN 'dimensional_entity_submodel' THEN
            target_schema := 'workflow'; target_table := 'dimensional_entity_submodel';
            target_id_column := 'dimensional_entity_submodel_id'; target_lock_column := 'dimensional_entity_submodel_is_locked';
        WHEN 'dimensional_attribute' THEN
            target_schema := 'workflow'; target_table := 'dimensional_attribute';
            target_id_column := 'dimensional_attribute_id'; target_lock_column := 'dimensional_attribute_is_locked';
        WHEN 'dimensional_entity_source_mapping' THEN
            target_schema := 'workflow'; target_table := 'dimensional_entity_source_mapping';
            target_id_column := 'dimensional_entity_source_mapping_id'; target_lock_column := 'dimensional_entity_source_mapping_is_locked';
        WHEN 'dimensional_attribute_source_mapping' THEN
            target_schema := 'workflow'; target_table := 'dimensional_attribute_source_mapping';
            target_id_column := 'dimensional_attribute_source_mapping_id'; target_lock_column := 'dimensional_attribute_source_mapping_is_locked';
        WHEN 'dimensional_relationship' THEN
            target_schema := 'workflow'; target_table := 'dimensional_relationship';
            target_id_column := 'dimensional_relationship_id'; target_lock_column := 'dimensional_relationship_is_locked';
        WHEN 'object_mapping' THEN
            target_schema := 'workflow'; target_table := 'object_mapping';
            target_id_column := 'object_mapping_id'; target_lock_column := 'object_mapping_is_locked';
        WHEN 'attribute_mapping' THEN
            target_schema := 'workflow'; target_table := 'attribute_mapping';
            target_id_column := 'attribute_mapping_id'; target_lock_column := 'attribute_mapping_is_locked';
        ELSE
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'unsupported lock artifact type';
    END CASE;

    SELECT owning_model.model_revision
      INTO resulting_revision
      FROM model.model AS owning_model
      JOIN core.tenant AS owning_tenant
        ON owning_tenant.tenant_id = owning_model.tenant_id
       AND owning_tenant.is_active
      JOIN core_security.user_account AS actor
        ON actor.user_account_id = actor_user_account_id
       AND actor.is_active
      JOIN core_security.tenant_user_access AS membership
        ON membership.tenant_id = owning_model.tenant_id
       AND membership.user_account_id = actor.user_account_id
       AND membership.is_active
       AND membership.tenant_access_level IN ('architect', 'admin')
     WHERE owning_model.model_id = target_model_id
       AND owning_model.is_active
       FOR UPDATE OF owning_model
       FOR SHARE OF owning_tenant, actor, membership;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'actor is not authorized to change this lock';
    END IF;

    EXECUTE format(
        'SELECT count(*), bool_or(%I) FROM %I.%I WHERE model_id = $1 AND %I = $2',
        target_lock_column,
        target_schema,
        target_table,
        target_id_column
    ) INTO target_count, current_lock USING target_model_id, target_artifact_id;

    IF target_count <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'artifact does not exist in the Model';
    END IF;
    IF current_lock = target_is_locked THEN
        RETURN resulting_revision;
    END IF;

    PERFORM set_config('gds.lock_command', 'on', true);
    EXECUTE format(
        'UPDATE %I.%I SET %I = $1, updated_time = CURRENT_TIMESTAMP, updated_by = $4 '
        || 'WHERE model_id = $2 AND %I = $3',
        target_schema,
        target_table,
        target_lock_column,
        target_id_column
    ) USING target_is_locked, target_model_id, target_artifact_id, actor_user_account_id::TEXT;
    PERFORM set_config('gds.lock_command', 'off', true);

    SELECT model_revision INTO resulting_revision
      FROM model.model
     WHERE model_id = target_model_id;

    INSERT INTO core_security.artifact_lock_event (
        model_id,
        artifact_type,
        artifact_id,
        artifact_is_locked,
        acted_by_user_account_id,
        lock_reason,
        model_revision,
        correlation_id
    ) VALUES (
        target_model_id,
        target_artifact_type,
        target_artifact_id,
        target_is_locked,
        actor_user_account_id,
        reason,
        resulting_revision,
        target_correlation_id
    );

    RETURN resulting_revision;
END;
$$;

REVOKE ALL ON FUNCTION core_security.set_artifact_lock(
    BIGINT, TEXT, BIGINT, BOOLEAN, BIGINT, TEXT, UUID
) FROM PUBLIC;

-- The application role cannot update foundational Model rows. This narrow
-- transaction-scoped primitive takes the authoritative row lock without
-- exposing Model mutation or data beyond an existence Boolean.
CREATE FUNCTION core_security.lock_model_row(target_model_id BIGINT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    row_locked BOOLEAN;
BEGIN
    SELECT TRUE
      INTO row_locked
      FROM model.model AS target_model
     WHERE target_model.model_id = target_model_id
       FOR UPDATE;

    RETURN COALESCE(row_locked, FALSE);
END;
$$;

REVOKE ALL ON FUNCTION core_security.lock_model_row(BIGINT) FROM PUBLIC;

-- Mutation authorization must fence deactivation and membership changes for
-- the transaction without granting the runtime role UPDATE on foundational
-- identity tables. This function exposes only the already-safe identity ids,
-- owning Tenant id, and Tenant access level used by server-side authorization.
CREATE FUNCTION core_security.resolve_mutation_principal(
    target_entra_tenant_id UUID,
    target_entra_object_id UUID,
    target_tenant_id BIGINT
)
RETURNS TABLE (
    resolved_user_entra_identity_id BIGINT,
    resolved_user_account_id BIGINT,
    resolved_tenant_id BIGINT,
    resolved_tenant_access_level VARCHAR(50)
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    identity_id BIGINT;
    account_id BIGINT;
    membership_tenant_id BIGINT;
    membership_access_level VARCHAR(50);
BEGIN
    SELECT identity.user_entra_identity_id,
           account.user_account_id
      INTO identity_id,
           account_id
      FROM core_security.user_entra_identity AS identity
      JOIN core_security.user_account AS account
        ON account.user_account_id = identity.user_account_id
       AND account.is_active
     WHERE identity.entra_tenant_id = target_entra_tenant_id
       AND identity.entra_object_id = target_entra_object_id
       AND identity.is_active
       FOR SHARE OF identity, account;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT membership.tenant_id,
           membership.tenant_access_level
      INTO membership_tenant_id,
           membership_access_level
      FROM core_security.tenant_user_access AS membership
      JOIN core.tenant AS owning_tenant
        ON owning_tenant.tenant_id = membership.tenant_id
       AND owning_tenant.is_active
     WHERE membership.user_account_id = account_id
       AND membership.tenant_id = target_tenant_id
       AND membership.is_active
       FOR SHARE OF membership, owning_tenant;

    RETURN QUERY
    SELECT identity_id,
           account_id,
           membership_tenant_id,
           membership_access_level;
END;
$$;

REVOKE ALL ON FUNCTION core_security.resolve_mutation_principal(
    UUID, UUID, BIGINT
) FROM PUBLIC;

-- Least-privilege runtime roles. Deployment owns DDL; these roles cannot create it.
REVOKE ALL ON SCHEMA core, core_security, model, workflow FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA core, core_security, model, workflow FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA core, core_security, model, workflow FROM PUBLIC;

GRANT USAGE ON SCHEMA core, core_security, model, workflow
    TO gds_app_read, gds_app_write;

-- Runtime writes need only the pure validators referenced by CHECK
-- constraints. Trigger functions remain non-executable directly.
GRANT EXECUTE ON FUNCTION
    core.is_nonblank(TEXT),
    core.is_canonical_text_array(TEXT[]),
    model.is_versioned_object(JSONB),
    model.is_naming_template_v1(JSONB),
    model.is_audit_columns_template_v1(JSONB),
    model.is_gold_technical_columns_template_v1(JSONB),
    workflow.is_effective_status(TEXT)
TO gds_app_write;

GRANT SELECT ON ALL TABLES IN SCHEMA core, model, workflow
    TO gds_app_read, gds_app_write;
REVOKE SELECT ON core.connection_value FROM gds_app_read, gds_app_write;
GRANT SELECT ON
    core_security.user_account,
    core_security.user_entra_identity,
    core_security.tenant_user_access,
    core_security.artifact_lock_event
TO gds_app_read, gds_app_write;

-- The application mutates only the normalized artifact and workflow state used
-- by PostgresRepository.  Foundational Model/Scope/target rows, audit rows, and
-- every DELETE operation remain deployment-owner capabilities.
GRANT INSERT, UPDATE ON
    model.modeling_evidence_document,
    model.modeling_evidence_record,
    workflow.analysis_result,
    workflow.attribute_mapping,
    workflow.attribute_profile,
    workflow.conceptual_object,
    workflow.conceptual_relationship,
    workflow.conceptual_support,
    workflow.dimensional_attribute,
    workflow.dimensional_attribute_source_mapping,
    workflow.dimensional_entity,
    workflow.dimensional_entity_source_mapping,
    workflow.dimensional_entity_submodel,
    workflow.dimensional_relationship,
    workflow.dimensional_submodel,
    workflow.logical_attribute,
    workflow.logical_attribute_source_mapping,
    workflow.logical_entity,
    workflow.logical_entity_source_mapping,
    workflow.logical_entity_submodel,
    workflow.logical_relationship,
    workflow.logical_submodel,
    workflow.model_change_set,
    workflow.object_mapping,
    workflow.profiling_run,
    workflow.workflow_grant,
    workflow.workflow_run_summary
TO gds_app_write;
GRANT INSERT ON
    workflow.model_change_set_event,
    workflow.idempotency_outcome,
    workflow.profiling_result_stage,
    workflow.profiling_failure_stage,
    workflow.profiling_final_receipt,
    workflow.model_apply_receipt,
    workflow.model_apply_receipt_ref
TO gds_app_write;

-- Identity sequences are granted only when owned by an INSERT-allowlisted
-- table.  This excludes foundational and authoritative audit sequences while
-- avoiding reliance on PostgreSQL's truncated generated sequence names.
DO $grant_runtime_sequences$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT DISTINCT sequence_namespace.nspname AS schema_name,
                        sequence_relation.relname AS sequence_name
          FROM pg_depend AS dependency
          JOIN pg_class AS sequence_relation
            ON sequence_relation.oid = dependency.objid
           AND sequence_relation.relkind = 'S'
          JOIN pg_namespace AS sequence_namespace
            ON sequence_namespace.oid = sequence_relation.relnamespace
          JOIN pg_class AS table_relation
            ON table_relation.oid = dependency.refobjid
           AND table_relation.relkind IN ('r', 'p')
          JOIN pg_namespace AS table_namespace
            ON table_namespace.oid = table_relation.relnamespace
         WHERE dependency.classid = 'pg_class'::REGCLASS
           AND dependency.refclassid = 'pg_class'::REGCLASS
           AND dependency.deptype IN ('a', 'i')
           AND table_namespace.nspname IN ('model', 'workflow')
           AND has_table_privilege(
                'gds_app_write',
                table_relation.oid,
                'INSERT'
           )
    LOOP
        EXECUTE format(
            'GRANT USAGE, SELECT ON SEQUENCE %I.%I TO gds_app_write',
            target.schema_name,
            target.sequence_name
        );
    END LOOP;
END;
$grant_runtime_sequences$;
GRANT EXECUTE ON FUNCTION core_security.set_artifact_lock(
    BIGINT, TEXT, BIGINT, BOOLEAN, BIGINT, TEXT, UUID
) TO gds_app_write;
GRANT EXECUTE ON FUNCTION core_security.lock_model_row(BIGINT)
TO gds_app_write;
GRANT EXECUTE ON FUNCTION core_security.resolve_mutation_principal(
    UUID, UUID, BIGINT
) TO gds_app_write;

GRANT USAGE, CREATE ON SCHEMA core, core_security, model, workflow TO gds_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA core, core_security, model, workflow
    TO gds_migration;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA core, core_security, model, workflow
    TO gds_migration;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA core, core_security, model, workflow
    TO gds_migration;
