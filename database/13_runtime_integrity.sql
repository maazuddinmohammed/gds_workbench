-- GDS ETL Workbench Release 1: cross-Section integrity, Principal authorization, and final privileges.

CREATE TABLE security.artifact_lock_event (
    artifact_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    artifact_type VARCHAR(100) NOT NULL,
    artifact_id BIGINT NOT NULL,
    artifact_is_locked BOOLEAN NOT NULL,
    acted_by_principal_id BIGINT NOT NULL,
    lock_reason VARCHAR(2000) NOT NULL,
    model_revision BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_artifact_lock_event_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_artifact_lock_event_actor FOREIGN KEY (acted_by_principal_id)
        REFERENCES security.principal (principal_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_artifact_lock_event_type CHECK (reference.is_nonblank(artifact_type)),
    CONSTRAINT ck_artifact_lock_event_id CHECK (artifact_id > 0),
    CONSTRAINT ck_artifact_lock_event_reason CHECK (reference.is_nonblank(lock_reason)),
    CONSTRAINT ck_artifact_lock_event_revision CHECK (model_revision > 0)
);

CREATE TABLE security.metadata_artifact_lock_event (
    metadata_artifact_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    artifact_type VARCHAR(30) NOT NULL,
    artifact_id BIGINT NOT NULL,
    artifact_is_locked BOOLEAN NOT NULL,
    acted_by_principal_id BIGINT NOT NULL,
    lock_reason VARCHAR(2000) NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_metadata_lock_event_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_lock_event_actor FOREIGN KEY (
        acted_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT ck_metadata_lock_event_type CHECK (
        artifact_type IN ('object', 'attribute')
    ),
    CONSTRAINT ck_metadata_lock_event_id CHECK (artifact_id > 0),
    CONSTRAINT ck_metadata_lock_event_reason CHECK (
        reference.is_nonblank(lock_reason)
    )
);

-- One transient row per writing transaction deduplicates deferred whole-graph
-- validation. The deferred trigger removes the row before the transaction ends.
CREATE TABLE workflow.effective_graph_validation_queue (
    transaction_id BIGINT PRIMARY KEY,
    queued_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_effective_graph_queue_transaction CHECK (transaction_id > 0)
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
        AND current_user IN (
            SELECT pg_get_userbyid(proowner)
             FROM pg_proc
             WHERE oid IN (
                 'security.set_artifact_lock(bigint,text,bigint,boolean,uuid,uuid,text,uuid)'::regprocedure,
                 'security.set_metadata_artifact_lock(bigint,text,bigint,boolean,uuid,uuid,text,uuid)'::regprocedure
             )
        ),
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
    IF TG_TABLE_NAME = 'attribute' THEN
        SELECT EXISTS (
            SELECT 1 FROM core.object
             WHERE object_id = (row_value ->> 'object_id')::BIGINT
               AND object_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'model_scope' THEN
        SELECT EXISTS (
            SELECT 1 FROM core.object
             WHERE object_id = (row_value ->> 'object_id')::BIGINT
               AND object_is_locked
        ) INTO blocked;
    ELSIF TG_TABLE_NAME = 'conceptual_support' THEN
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

CREATE FUNCTION workflow.enqueue_effective_graph_validation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    INSERT INTO workflow.effective_graph_validation_queue (transaction_id)
    VALUES (txid_current())
    ON CONFLICT (transaction_id) DO NOTHING;
    RETURN NULL;
END;
$$;

CREATE FUNCTION workflow.assert_effective_graph()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    DELETE FROM workflow.effective_graph_validation_queue
     WHERE transaction_id = NEW.transaction_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    -- Profiles, Analysis, and Conceptual physical support are sourced only
    -- from active Bronze Objects in authoritative Model Scope.
    IF EXISTS (
        SELECT 1
          FROM workflow.attribute_profile AS profile
          JOIN core.object AS source_object
            ON source_object.object_id = profile.object_id
          JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
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
          JOIN reference.zone AS from_zone ON from_zone.zone_id = from_object.zone_id
          JOIN core.object AS to_object
            ON to_object.object_id = analysis.to_object_id
          JOIN reference.zone AS to_zone ON to_zone.zone_id = to_object.zone_id
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
        JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
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
        JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
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
        JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
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
        FROM workflow.mapping_source_system_dependency AS dependency
        JOIN core.system AS source_system
          ON source_system.system_id = dependency.source_system_id
        WHERE workflow.is_effective_status(
                  dependency.mapping_source_system_dependency_status
              )
          AND NOT source_system.is_active
    ) OR EXISTS (
        SELECT 1
        FROM workflow.object_mapping AS mapping
        JOIN core.object AS target_object ON target_object.object_id = mapping.target_object_id
        JOIN reference.zone AS target_zone ON target_zone.zone_id = target_object.zone_id
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
              OR NOT EXISTS (
                  SELECT 1
                  FROM workflow.mapping_source_system_dependency AS dependency
                  WHERE dependency.model_id = mapping.model_id
                    AND dependency.modeled_entity_type = mapping.modeled_entity_type
                    AND dependency.source_system_id = mapping.source_system_id
                    AND workflow.is_effective_status(
                        dependency.mapping_source_system_dependency_status
                    )
              )
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
              OR left_header.object_dependency_order IS DISTINCT FROM
                 right_header.object_dependency_order
          )
    ) OR EXISTS (
        SELECT 1
        FROM workflow.object_mapping
        WHERE workflow.is_effective_status(object_mapping_status)
        GROUP BY model_id, modeled_entity_type, target_object_id
        HAVING min(object_dependency_order) <>
               max(object_dependency_order)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid effective Mapping graph';
    END IF;

    RETURN NULL;
END;
$$;

-- Business locks are enforced on every curated lock-bearing family.
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON core.object FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('object_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON core.attribute FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('attribute_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON model.model_scope FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock('model_scope_is_locked');
CREATE TRIGGER guard_business_lock BEFORE INSERT OR UPDATE OR DELETE
ON workflow.mapping_source_system_dependency FOR EACH ROW
EXECUTE FUNCTION workflow.guard_business_lock(
    'mapping_source_system_dependency_is_locked'
);
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
ON core.object FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('object_id', 'connection_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON core.attribute FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('attribute_id', 'object_id');
CREATE TRIGGER guard_identity_witness BEFORE UPDATE
ON model.model_scope FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness('model_scope_id', 'model_id', 'object_id');
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
ON workflow.mapping_source_system_dependency FOR EACH ROW EXECUTE FUNCTION
workflow.guard_identity_witness(
    'mapping_source_system_dependency_id', 'model_id',
    'modeled_entity_type', 'source_system_id'
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
ON core.attribute FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
CREATE TRIGGER guard_locked_ancestor BEFORE INSERT OR UPDATE OR DELETE
ON model.model_scope FOR EACH ROW EXECUTE FUNCTION workflow.guard_locked_ancestor();
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

-- Relevant statements enqueue one request. The queue constraint validates the
-- final transaction state once, regardless of how many source rows changed.
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON model.modeling_evidence_document FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE
ON model.model FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON model.modeling_evidence_record FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON model.model_scope FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.attribute_profile FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.analysis_result FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.conceptual_object FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.conceptual_relationship FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.conceptual_support FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_submodel FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_entity FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_submodel FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_entity_source_mapping FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_attribute_source_mapping FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.logical_relationship FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_submodel FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_submodel FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_entity_source_mapping FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_attribute_source_mapping FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.dimensional_relationship FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.mapping_source_system_dependency FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.object_mapping FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON workflow.attribute_mapping FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON core.object FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON core.attribute FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON reference.zone FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();
CREATE TRIGGER queue_effective_graph_validation AFTER INSERT OR UPDATE OR DELETE
ON core.system FOR EACH STATEMENT
EXECUTE FUNCTION workflow.enqueue_effective_graph_validation();

CREATE CONSTRAINT TRIGGER validate_effective_graph
AFTER INSERT ON workflow.effective_graph_validation_queue
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION workflow.assert_effective_graph();

CREATE TRIGGER guard_artifact_lock_event_append_only
BEFORE UPDATE OR DELETE ON security.artifact_lock_event
FOR EACH ROW EXECUTE FUNCTION security.reject_append_only_change();
CREATE TRIGGER guard_metadata_artifact_lock_event_append_only
BEFORE UPDATE OR DELETE ON security.metadata_artifact_lock_event
FOR EACH ROW EXECUTE FUNCTION security.reject_append_only_change();

CREATE INDEX ix_artifact_lock_event_model_created
    ON security.artifact_lock_event (model_id, created_time);
CREATE INDEX ix_artifact_lock_event_actor_created
    ON security.artifact_lock_event (
        acted_by_principal_id,
        created_time
    );
CREATE INDEX ix_metadata_lock_event_tenant_created
    ON security.metadata_artifact_lock_event (tenant_id, created_time);
CREATE INDEX ix_metadata_lock_event_actor_created
    ON security.metadata_artifact_lock_event (
        acted_by_principal_id,
        created_time
    );

CREATE FUNCTION security.set_artifact_lock(
    target_model_id BIGINT,
    target_artifact_type TEXT,
    target_artifact_id BIGINT,
    target_is_locked BOOLEAN,
    actor_entra_tenant_id UUID,
    actor_entra_object_id UUID,
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
    resolved_actor_principal_id BIGINT;
    actor_is_super_admin BOOLEAN;
BEGIN
    IF target_model_id IS NULL
       OR target_artifact_id IS NULL
       OR target_artifact_id <= 0
       OR NOT reference.is_nonblank(target_artifact_type)
       OR actor_entra_tenant_id IS NULL
       OR actor_entra_object_id IS NULL
       OR NOT reference.is_nonblank(reason)
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
        WHEN 'model_scope' THEN
            target_schema := 'model'; target_table := 'model_scope';
            target_id_column := 'model_scope_id'; target_lock_column := 'model_scope_is_locked';
        WHEN 'object_mapping' THEN
            target_schema := 'workflow'; target_table := 'object_mapping';
            target_id_column := 'object_mapping_id'; target_lock_column := 'object_mapping_is_locked';
        WHEN 'mapping_source_system_dependency' THEN
            target_schema := 'workflow'; target_table := 'mapping_source_system_dependency';
            target_id_column := 'mapping_source_system_dependency_id';
            target_lock_column := 'mapping_source_system_dependency_is_locked';
        WHEN 'attribute_mapping' THEN
            target_schema := 'workflow'; target_table := 'attribute_mapping';
            target_id_column := 'attribute_mapping_id'; target_lock_column := 'attribute_mapping_is_locked';
        ELSE
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'unsupported lock artifact type';
    END CASE;

    SELECT owning_model.model_revision,
           actor.principal_id,
           actor.is_super_admin
      INTO resulting_revision,
           resolved_actor_principal_id,
           actor_is_super_admin
      FROM model.model AS owning_model
      JOIN core.tenant AS owning_tenant
        ON owning_tenant.tenant_id = owning_model.tenant_id
       AND owning_tenant.is_active
      JOIN security.entra_principal_identity AS actor_identity
        ON actor_identity.entra_tenant_id = actor_entra_tenant_id
       AND actor_identity.entra_object_id = actor_entra_object_id
       AND actor_identity.is_active
      JOIN security.principal AS actor
        ON actor.principal_id = actor_identity.principal_id
       AND actor.principal_type = actor_identity.principal_type
       AND actor.is_active
     WHERE owning_model.model_id = target_model_id
           AND owning_model.is_active
       FOR UPDATE OF owning_model
       FOR SHARE OF owning_tenant, actor_identity, actor;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'actor is not authorized to change this lock';
    END IF;

    IF NOT actor_is_super_admin THEN
        PERFORM 1
          FROM security.tenant_principal_access AS membership
         JOIN model.model AS owning_model
            ON owning_model.tenant_id = membership.tenant_id
         WHERE owning_model.model_id = target_model_id
           AND membership.principal_id = resolved_actor_principal_id
           AND membership.is_active
           AND (
               membership.access_expires_time IS NULL
               OR membership.access_expires_time > CURRENT_TIMESTAMP
           )
           AND membership.tenant_role IN ('architect', 'tenant_admin')
           FOR SHARE OF membership;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'actor is not authorized to change this lock';
        END IF;
    END IF;

    EXECUTE format(
        'SELECT count(*), bool_or(%I) FROM %I.%I '
        || 'WHERE model_id = $1 AND %I = $2',
        target_lock_column,
        target_schema,
        target_table,
        target_id_column
    ) INTO target_count, current_lock
    USING target_model_id, target_artifact_id;

    IF target_count <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'artifact does not exist in the Model';
    END IF;
    IF current_lock = target_is_locked THEN
        RETURN resulting_revision;
    END IF;

    PERFORM set_config('gds.lock_command', 'on', true);
    EXECUTE format(
        'UPDATE %I.%I SET %I = $1, updated_time = CURRENT_TIMESTAMP, '
        || 'updated_by = $4 WHERE model_id = $2 AND %I = $3',
        target_schema,
        target_table,
        target_lock_column,
        target_id_column
    ) USING target_is_locked, target_model_id, target_artifact_id,
            resolved_actor_principal_id::TEXT;
    PERFORM set_config('gds.lock_command', 'off', true);

    PERFORM model.record_effective_change(
        target_model_id,
        target_schema || '.' || target_table || '.lock'
    );

    SELECT model_revision INTO resulting_revision
      FROM model.model
     WHERE model_id = target_model_id;

    INSERT INTO security.artifact_lock_event (
        model_id,
        artifact_type,
        artifact_id,
        artifact_is_locked,
        acted_by_principal_id,
        lock_reason,
        model_revision,
        correlation_id
    ) VALUES (
        target_model_id,
        target_artifact_type,
        target_artifact_id,
        target_is_locked,
        resolved_actor_principal_id,
        reason,
        resulting_revision,
        target_correlation_id
    );

    RETURN resulting_revision;
END;
$$;

REVOKE ALL ON FUNCTION security.set_artifact_lock(
    BIGINT, TEXT, BIGINT, BOOLEAN, UUID, UUID, TEXT, UUID
) FROM PUBLIC;

CREATE FUNCTION security.set_metadata_artifact_lock(
    target_tenant_id BIGINT,
    target_artifact_type TEXT,
    target_artifact_id BIGINT,
    target_is_locked BOOLEAN,
    actor_entra_tenant_id UUID,
    actor_entra_object_id UUID,
    reason TEXT,
    target_correlation_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    target_table TEXT;
    target_id_column TEXT;
    target_lock_column TEXT;
    target_count BIGINT;
    current_lock BOOLEAN;
    resolved_actor_principal_id BIGINT;
    actor_is_super_admin BOOLEAN;
BEGIN
    IF target_tenant_id IS NULL
       OR target_artifact_id IS NULL
       OR target_artifact_id <= 0
       OR NOT reference.is_nonblank(target_artifact_type)
       OR actor_entra_tenant_id IS NULL
       OR actor_entra_object_id IS NULL
       OR NOT reference.is_nonblank(reason)
       OR target_correlation_id IS NULL
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'invalid metadata artifact lock request';
    END IF;

    CASE target_artifact_type
        WHEN 'object' THEN
            target_table := 'object';
            target_id_column := 'object_id';
            target_lock_column := 'object_is_locked';
        WHEN 'attribute' THEN
            target_table := 'attribute';
            target_id_column := 'attribute_id';
            target_lock_column := 'attribute_is_locked';
        ELSE
            RAISE EXCEPTION USING
                ERRCODE = '22023',
                MESSAGE = 'unsupported metadata lock artifact type';
    END CASE;

    SELECT actor.principal_id,
           actor.is_super_admin
      INTO resolved_actor_principal_id,
           actor_is_super_admin
      FROM core.tenant AS owning_tenant
      JOIN security.entra_principal_identity AS actor_identity
        ON actor_identity.entra_tenant_id = actor_entra_tenant_id
       AND actor_identity.entra_object_id = actor_entra_object_id
       AND actor_identity.is_active
      JOIN security.principal AS actor
        ON actor.principal_id = actor_identity.principal_id
       AND actor.principal_type = actor_identity.principal_type
       AND actor.is_active
     WHERE owning_tenant.tenant_id = target_tenant_id
       AND owning_tenant.is_active
       FOR SHARE OF owning_tenant, actor_identity, actor;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'actor is not authorized to change this metadata lock';
    END IF;

    IF NOT actor_is_super_admin THEN
        PERFORM 1
          FROM security.tenant_principal_access AS membership
         WHERE membership.tenant_id = target_tenant_id
           AND membership.principal_id = resolved_actor_principal_id
           AND membership.is_active
           AND (
               membership.access_expires_time IS NULL
               OR membership.access_expires_time > CURRENT_TIMESTAMP
           )
           AND membership.tenant_role IN ('architect', 'tenant_admin')
           FOR SHARE OF membership;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'actor is not authorized to change this metadata lock';
        END IF;
    END IF;

    IF target_artifact_type = 'object' THEN
        SELECT count(*), bool_or(artifact.object_is_locked)
          INTO target_count, current_lock
          FROM core.object AS artifact
          JOIN core.connection AS connection
            ON connection.connection_id = artifact.connection_id
         WHERE artifact.object_id = target_artifact_id
           AND connection.tenant_id = target_tenant_id;
    ELSE
        SELECT count(*), bool_or(artifact.attribute_is_locked)
          INTO target_count, current_lock
          FROM core.attribute AS artifact
          JOIN core.object AS parent_object
            ON parent_object.object_id = artifact.object_id
          JOIN core.connection AS connection
            ON connection.connection_id = parent_object.connection_id
         WHERE artifact.attribute_id = target_artifact_id
           AND connection.tenant_id = target_tenant_id;
    END IF;

    IF target_count <> 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0002',
            MESSAGE = 'metadata artifact does not exist in the Tenant';
    END IF;
    IF current_lock = target_is_locked THEN
        RETURN current_lock;
    END IF;

    PERFORM set_config('gds.lock_command', 'on', true);
    EXECUTE format(
        'UPDATE core.%I SET %I = $1, updated_time = CURRENT_TIMESTAMP, '
        || 'updated_by = $3 WHERE %I = $2',
        target_table,
        target_lock_column,
        target_id_column
    ) USING target_is_locked, target_artifact_id,
            resolved_actor_principal_id::TEXT;
    PERFORM set_config('gds.lock_command', 'off', true);

    INSERT INTO security.metadata_artifact_lock_event (
        tenant_id,
        artifact_type,
        artifact_id,
        artifact_is_locked,
        acted_by_principal_id,
        lock_reason,
        correlation_id
    ) VALUES (
        target_tenant_id,
        target_artifact_type,
        target_artifact_id,
        target_is_locked,
        resolved_actor_principal_id,
        reason,
        target_correlation_id
    );

    RETURN target_is_locked;
END;
$$;

REVOKE ALL ON FUNCTION security.set_metadata_artifact_lock(
    BIGINT, TEXT, BIGINT, BOOLEAN, UUID, UUID, TEXT, UUID
) FROM PUBLIC;

-- The application role cannot update foundational Model rows. This narrow
-- transaction-scoped primitive takes the authoritative row lock without
-- exposing Model mutation or data beyond an existence Boolean.
CREATE FUNCTION security.lock_model_row(target_model_id BIGINT)
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

REVOKE ALL ON FUNCTION security.lock_model_row(BIGINT) FROM PUBLIC;

-- Resolves one authenticated Entra identity and projects its effective Tenant
-- capabilities. Global visibility grants read only. Tenant roles grant their
-- fixed capability set, and super admin grants every application capability.
CREATE FUNCTION security.resolve_principal_access(
    target_entra_tenant_id UUID,
    target_entra_object_id UUID,
    target_tenant_id BIGINT
)
RETURNS TABLE (
    resolved_entra_principal_identity_id BIGINT,
    resolved_principal_id BIGINT,
    resolved_principal_type VARCHAR(30),
    resolved_is_super_admin BOOLEAN,
    resolved_tenant_id BIGINT,
    resolved_tenant_visibility VARCHAR(20),
    resolved_tenant_role VARCHAR(30),
    resolved_can_read BOOLEAN,
    resolved_can_develop BOOLEAN,
    resolved_can_architect BOOLEAN,
    resolved_can_administer BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    identity_id BIGINT;
    principal_id_value BIGINT;
    principal_type_value VARCHAR(30);
    principal_is_super_admin BOOLEAN;
    tenant_id_value BIGINT;
    tenant_visibility_value VARCHAR(20);
    membership_role VARCHAR(30);
    effective_role VARCHAR(30);
BEGIN
    SELECT identity.entra_principal_identity_id,
           principal.principal_id,
           principal.principal_type,
           principal.is_super_admin,
           owning_tenant.tenant_id,
           owning_tenant.tenant_visibility
      INTO identity_id,
           principal_id_value,
           principal_type_value,
           principal_is_super_admin,
           tenant_id_value,
           tenant_visibility_value
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
       AND principal.is_active
      JOIN core.tenant AS owning_tenant
        ON owning_tenant.tenant_id = target_tenant_id
       AND owning_tenant.is_active
     WHERE identity.entra_tenant_id = target_entra_tenant_id
       AND identity.entra_object_id = target_entra_object_id
       AND identity.is_active
       FOR SHARE OF identity, principal, owning_tenant;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT membership.tenant_role
      INTO membership_role
      FROM security.tenant_principal_access AS membership
     WHERE membership.principal_id = principal_id_value
       AND membership.tenant_id = target_tenant_id
       AND membership.is_active
       AND (
           membership.access_expires_time IS NULL
           OR membership.access_expires_time > CURRENT_TIMESTAMP
       )
       FOR SHARE OF membership;

    IF principal_is_super_admin THEN
        effective_role := 'super_admin';
    ELSIF membership_role IS NOT NULL THEN
        effective_role := membership_role;
    ELSIF tenant_visibility_value = 'global' THEN
        effective_role := 'viewer';
    END IF;

    RETURN QUERY
    SELECT identity_id,
           principal_id_value,
           principal_type_value,
           principal_is_super_admin,
           tenant_id_value,
           tenant_visibility_value,
           effective_role,
           effective_role IS NOT NULL,
           COALESCE(
               effective_role IN (
                   'developer', 'architect', 'tenant_admin', 'super_admin'
               ),
               FALSE
           ),
           COALESCE(
               effective_role IN ('architect', 'tenant_admin', 'super_admin'),
               FALSE
           ),
           COALESCE(
               effective_role IN ('tenant_admin', 'super_admin'),
               FALSE
           );
END;
$$;

REVOKE ALL ON FUNCTION security.resolve_principal_access(
    UUID, UUID, BIGINT
) FROM PUBLIC;

-- Least-privilege runtime roles. Deployment owns DDL; these roles cannot create it.
REVOKE ALL ON SCHEMA reference, core, security, model, workflow FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA reference, core, security, model, workflow FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow FROM PUBLIC;

GRANT USAGE ON SCHEMA reference, core, security, model, workflow
    TO gds_app_read, gds_app_write;

-- Runtime writes need only the pure validators referenced by CHECK
-- constraints. Trigger functions remain non-executable directly.
GRANT EXECUTE ON FUNCTION
    reference.is_nonblank(TEXT),
    core.is_canonical_text_array(TEXT[]),
    workflow.is_effective_status(TEXT)
TO gds_app_write;

GRANT SELECT ON ALL TABLES IN SCHEMA reference, core, model, workflow
    TO gds_app_read, gds_app_write;
REVOKE SELECT ON core.connection_value FROM gds_app_read, gds_app_write;
REVOKE SELECT ON workflow.effective_graph_validation_queue
    FROM gds_app_read, gds_app_write;
GRANT SELECT ON
    security.principal,
    security.entra_principal_identity,
    security.tenant_principal_access,
    security.artifact_lock_event,
    security.metadata_artifact_lock_event
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
    workflow.mapping_source_system_dependency,
    workflow.metadata_change_set,
    workflow.model_change_set,
    workflow.object_mapping,
    workflow.profiling_run,
    workflow.workflow_grant,
    workflow.workflow_run_summary
TO gds_app_write;
GRANT INSERT ON
    workflow.metadata_change_set_event,
    workflow.metadata_apply_receipt,
    workflow.metadata_apply_receipt_ref,
    workflow.model_change_set_event,
    workflow.idempotency_outcome,
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
GRANT EXECUTE ON FUNCTION security.set_artifact_lock(
    BIGINT, TEXT, BIGINT, BOOLEAN, UUID, UUID, TEXT, UUID
) TO gds_app_write;
GRANT EXECUTE ON FUNCTION security.set_metadata_artifact_lock(
    BIGINT, TEXT, BIGINT, BOOLEAN, UUID, UUID, TEXT, UUID
) TO gds_app_write;
GRANT EXECUTE ON FUNCTION security.lock_model_row(BIGINT)
TO gds_app_write;
GRANT EXECUTE ON FUNCTION security.resolve_principal_access(
    UUID, UUID, BIGINT
) TO gds_app_read, gds_app_write;

GRANT USAGE, CREATE ON SCHEMA reference, core, security, model, workflow TO gds_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reference, core, security, model, workflow
    TO gds_migration;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA reference, core, security, model, workflow
    TO gds_migration;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow
    TO gds_migration;
