-- GDS ETL Workbench Release 1: Model, Scope, policy, Evidence, and revision.

CREATE SCHEMA model;

CREATE FUNCTION model.is_versioned_object(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN value IS NOT NULL
   AND jsonb_typeof(value) = 'object'
   AND value ->> 'schema_version' = '1.0';

CREATE FUNCTION model.is_naming_template_v1(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN model.is_versioned_object(value)
   AND value ->> 'default_style' = 'PascalCase'
   AND value ->> 'submodel_style' = 'PascalCase'
   AND value ->> 'entity_style' = 'PascalCase'
   AND value ->> 'attribute_style' = 'PascalCase'
   AND value ->> 'relationship_style' = 'PascalCase'
   AND jsonb_typeof(value -> 'acronyms') = 'object'
   AND jsonb_typeof(value -> 'reserved_words') = 'array'
   AND (value ->> 'max_length') ~ '^[0-9]+$'
   AND (value ->> 'max_length')::INTEGER BETWEEN 1 AND 255;

CREATE FUNCTION model.is_audit_columns_template_v1(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN model.is_versioned_object(value)
   AND jsonb_typeof(value -> 'columns') = 'array'
   AND jsonb_array_length(value -> 'columns') BETWEEN 1 AND 32;

CREATE FUNCTION model.is_gold_technical_columns_template_v1(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN model.is_versioned_object(value)
   AND jsonb_typeof(value -> 'dimension_surrogate_key') = 'object'
   AND jsonb_typeof(value -> 'fact_bridge_foreign_key') = 'object'
   AND jsonb_typeof(value -> 'type_2') = 'object'
   AND jsonb_typeof(value #> '{type_2,effective_from}') = 'object'
   AND jsonb_typeof(value #> '{type_2,effective_to}') = 'object'
   AND jsonb_typeof(value #> '{type_2,is_current}') = 'object';

CREATE TABLE model.model (
    model_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    model_description VARCHAR(2000),
    model_revision BIGINT NOT NULL DEFAULT 1,
    silver_model_naming_template JSONB,
    silver_model_audit_columns_template JSONB,
    gold_model_naming_template JSONB,
    gold_model_technical_columns_template JSONB,
    gold_model_audit_columns_template JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_id_tenant UNIQUE (model_id, tenant_id),
    CONSTRAINT ck_model_name CHECK (core.is_nonblank(model_name)),
    CONSTRAINT ck_model_description CHECK (
        model_description IS NULL OR core.is_nonblank(model_description)
    ),
    CONSTRAINT ck_model_revision CHECK (model_revision > 0),
    CONSTRAINT ck_model_silver_policy_group CHECK (
        (silver_model_naming_template IS NULL)
        = (silver_model_audit_columns_template IS NULL)
    ),
    CONSTRAINT ck_model_gold_policy_group CHECK (
        (gold_model_naming_template IS NULL)
        = (gold_model_technical_columns_template IS NULL)
        AND (gold_model_naming_template IS NULL)
        = (gold_model_audit_columns_template IS NULL)
    ),
    CONSTRAINT ck_model_silver_naming_template CHECK (
        silver_model_naming_template IS NULL
        OR model.is_naming_template_v1(silver_model_naming_template)
    ),
    CONSTRAINT ck_model_silver_audit_template CHECK (
        silver_model_audit_columns_template IS NULL
        OR model.is_audit_columns_template_v1(
            silver_model_audit_columns_template
        )
    ),
    CONSTRAINT ck_model_gold_naming_template CHECK (
        gold_model_naming_template IS NULL
        OR model.is_naming_template_v1(gold_model_naming_template)
    ),
    CONSTRAINT ck_model_gold_technical_template CHECK (
        gold_model_technical_columns_template IS NULL
        OR model.is_gold_technical_columns_template_v1(
            gold_model_technical_columns_template
        )
    ),
    CONSTRAINT ck_model_gold_audit_template CHECK (
        gold_model_audit_columns_template IS NULL
        OR model.is_audit_columns_template_v1(gold_model_audit_columns_template)
    )
);

CREATE TABLE model.model_scope (
    model_scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_scope_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_scope_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_scope UNIQUE (model_id, object_id),
    CONSTRAINT uq_model_scope_witness UNIQUE (model_scope_id, model_id, object_id)
);

CREATE TABLE model.model_event_log (
    model_event_log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    agent_run_id VARCHAR(500),
    model_workflow VARCHAR(30) NOT NULL,
    model_event_log_stage VARCHAR(100) NOT NULL,
    model_event_log_status VARCHAR(30) NOT NULL,
    model_event_log_message VARCHAR(2000) NOT NULL,
    model_event_log_current INTEGER,
    model_event_log_total INTEGER,
    model_event_log_percent NUMERIC(5, 2),
    finding_count INTEGER NOT NULL DEFAULT 0,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_event_log_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_model_event_log_workflow CHECK (
        model_workflow IN (
            'profiling', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping', 'dbml'
        )
    ),
    CONSTRAINT ck_model_event_log_stage CHECK (
        core.is_nonblank(model_event_log_stage)
    ),
    CONSTRAINT ck_model_event_log_status CHECK (
        model_event_log_status IN (
            'started', 'running', 'completed', 'warning', 'failed', 'blocked'
        )
    ),
    CONSTRAINT ck_model_event_log_message CHECK (
        core.is_nonblank(model_event_log_message)
    ),
    CONSTRAINT ck_model_event_log_progress CHECK (
        (model_event_log_current IS NULL OR model_event_log_current >= 0)
        AND (model_event_log_total IS NULL OR model_event_log_total >= 0)
        AND (
            model_event_log_current IS NULL
            OR model_event_log_total IS NULL
            OR model_event_log_current <= model_event_log_total
        )
        AND (
            model_event_log_percent IS NULL
            OR model_event_log_percent BETWEEN 0 AND 100
        )
        AND finding_count >= 0
    )
);

CREATE TABLE model.modeling_evidence_document (
    modeling_evidence_document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    tenant_id BIGINT,
    system_id BIGINT,
    modeling_evidence_document_name VARCHAR(255) NOT NULL,
    modeling_evidence_file_pattern VARCHAR(500),
    modeling_evidence_document_type VARCHAR(100),
    modeling_evidence_document_description VARCHAR(2000),
    modeling_evidence_document_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    agent_run_id VARCHAR(500),
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_evidence_document_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_evidence_document_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_evidence_document_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_evidence_document_id_model
        UNIQUE (modeling_evidence_document_id, model_id),
    CONSTRAINT ck_evidence_document_name CHECK (
        core.is_nonblank(modeling_evidence_document_name)
    ),
    CONSTRAINT ck_evidence_file_pattern CHECK (
        modeling_evidence_file_pattern IS NULL
        OR core.is_nonblank(modeling_evidence_file_pattern)
    ),
    CONSTRAINT ck_evidence_document_type CHECK (
        modeling_evidence_document_type IS NULL
        OR core.is_nonblank(modeling_evidence_document_type)
    ),
    CONSTRAINT ck_evidence_document_description CHECK (
        modeling_evidence_document_description IS NULL
        OR core.is_nonblank(modeling_evidence_document_description)
    ),
    CONSTRAINT ck_evidence_document_metadata CHECK (
        jsonb_typeof(modeling_evidence_document_metadata) = 'object'
    )
);

CREATE TABLE model.modeling_evidence_record (
    modeling_evidence_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    modeling_evidence_document_id BIGINT NOT NULL,
    modeling_evidence_record_type VARCHAR(100) NOT NULL,
    modeling_evidence_text TEXT NOT NULL,
    modeling_evidence_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    modeling_evidence_source_location JSONB,
    modeling_evidence_applicable_layers TEXT[] NOT NULL DEFAULT '{}',
    modeling_evidence_confidence VARCHAR(10),
    modeling_evidence_record_status VARCHAR(20) NOT NULL DEFAULT 'active',
    modeling_evidence_record_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    agent_run_id VARCHAR(500),
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_evidence_record_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_evidence_record_document FOREIGN KEY (
        modeling_evidence_document_id,
        model_id
    ) REFERENCES model.modeling_evidence_document (
        modeling_evidence_document_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_evidence_record_id_model
        UNIQUE (modeling_evidence_record_id, model_id),
    CONSTRAINT ck_evidence_record_type CHECK (
        core.is_nonblank(modeling_evidence_record_type)
    ),
    CONSTRAINT ck_evidence_record_text CHECK (
        core.is_nonblank(modeling_evidence_text)
    ),
    CONSTRAINT ck_evidence_record_details CHECK (
        jsonb_typeof(modeling_evidence_details) = 'object'
    ),
    CONSTRAINT ck_evidence_source_location CHECK (
        modeling_evidence_source_location IS NULL
        OR jsonb_typeof(modeling_evidence_source_location) = 'object'
    ),
    CONSTRAINT ck_evidence_applicable_layers CHECK (
        modeling_evidence_applicable_layers <@ ARRAY[
            'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
        ]::TEXT[]
    ),
    CONSTRAINT ck_evidence_confidence CHECK (
        modeling_evidence_confidence IS NULL
        OR modeling_evidence_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_evidence_record_status CHECK (
        modeling_evidence_record_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE TABLE model.model_revision_transaction (
    model_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL DEFAULT txid_current(),
    change_kind VARCHAR(100) NOT NULL,
    changed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NOT NULL DEFAULT SESSION_USER,
    PRIMARY KEY (model_id, transaction_id),
    CONSTRAINT fk_model_revision_transaction_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_model_revision_change_kind CHECK (
        core.is_nonblank(change_kind)
    )
);

CREATE FUNCTION model.guard_model_revision()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.model_revision IS DISTINCT FROM OLD.model_revision
       AND NOT (
            current_setting('gds.revision_write', true) = 'on'
            AND current_user = pg_get_userbyid((
                SELECT proowner
                  FROM pg_proc
                 WHERE oid = 'model.record_effective_change(bigint,text)'::regprocedure
            ))
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'model_revision is maintained by database guards';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION model.record_effective_change(
    target_model_id BIGINT,
    target_change_kind TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF target_model_id IS NULL OR NOT core.is_nonblank(target_change_kind) THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'model change requires a Model and nonblank change kind';
    END IF;

    PERFORM 1
      FROM model.model
     WHERE model_id = target_model_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23503',
            MESSAGE = 'Model does not exist';
    END IF;

    INSERT INTO model.model_revision_transaction (
        model_id,
        transaction_id,
        change_kind
    ) VALUES (
        target_model_id,
        txid_current(),
        target_change_kind
    )
    ON CONFLICT (model_id, transaction_id) DO NOTHING;

    IF FOUND THEN
        PERFORM set_config('gds.revision_write', 'on', true);
        UPDATE model.model
           SET model_revision = model_revision + 1,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = SESSION_USER
         WHERE model_id = target_model_id;
        PERFORM set_config('gds.revision_write', 'off', true);
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION model.record_effective_change(BIGINT, TEXT) FROM PUBLIC;

CREATE FUNCTION model.capture_effective_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    target_model_id BIGINT;
BEGIN
    IF TG_OP = 'UPDATE' AND to_jsonb(NEW) IS NOT DISTINCT FROM to_jsonb(OLD) THEN
        RETURN NEW;
    END IF;

    target_model_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.model_id ELSE NEW.model_id END;
    PERFORM model.record_effective_change(
        target_model_id,
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    );
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION model.capture_model_row_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    PERFORM model.record_effective_change(NEW.model_id, 'model.model');
    RETURN NULL;
END;
$$;

CREATE TRIGGER guard_model_revision
BEFORE UPDATE ON model.model
FOR EACH ROW EXECUTE FUNCTION model.guard_model_revision();

CREATE TRIGGER capture_model_policy_change
AFTER UPDATE ON model.model
FOR EACH ROW
WHEN (
    OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
    OR OLD.model_name IS DISTINCT FROM NEW.model_name
    OR OLD.model_description IS DISTINCT FROM NEW.model_description
    OR OLD.silver_model_naming_template IS DISTINCT FROM NEW.silver_model_naming_template
    OR OLD.silver_model_audit_columns_template IS DISTINCT FROM NEW.silver_model_audit_columns_template
    OR OLD.gold_model_naming_template IS DISTINCT FROM NEW.gold_model_naming_template
    OR OLD.gold_model_technical_columns_template IS DISTINCT FROM NEW.gold_model_technical_columns_template
    OR OLD.gold_model_audit_columns_template IS DISTINCT FROM NEW.gold_model_audit_columns_template
    OR OLD.is_active IS DISTINCT FROM NEW.is_active
)
EXECUTE FUNCTION model.capture_model_row_change();

CREATE TRIGGER capture_model_scope_change
BEFORE INSERT OR UPDATE OR DELETE ON model.model_scope
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();
CREATE TRIGGER capture_evidence_document_change
BEFORE INSERT OR UPDATE OR DELETE ON model.modeling_evidence_document
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();
CREATE TRIGGER capture_evidence_record_change
BEFORE INSERT OR UPDATE OR DELETE ON model.modeling_evidence_record
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();

CREATE TRIGGER guard_model_event_log_append_only
BEFORE UPDATE OR DELETE ON model.model_event_log
FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_model_revision_transaction_append_only
BEFORE UPDATE OR DELETE ON model.model_revision_transaction
FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();

CREATE UNIQUE INDEX ux_model_tenant_name_ci
    ON model.model (tenant_id, lower(btrim(model_name)));
CREATE UNIQUE INDEX ux_evidence_document_model_name_ci
    ON model.modeling_evidence_document (
        model_id,
        lower(btrim(modeling_evidence_document_name))
    );

CREATE INDEX ix_model_tenant_active ON model.model (tenant_id, is_active);
CREATE INDEX ix_model_scope_object ON model.model_scope (object_id, model_id);
CREATE INDEX ix_model_event_log_model_created
    ON model.model_event_log (model_id, created_time);
CREATE INDEX ix_evidence_document_model_active
    ON model.modeling_evidence_document (model_id, is_active);
CREATE INDEX ix_evidence_document_tenant_system
    ON model.modeling_evidence_document (tenant_id, system_id);
CREATE INDEX ix_evidence_record_model_status
    ON model.modeling_evidence_record (
        model_id,
        modeling_evidence_record_status,
        modeling_evidence_document_id
    );
CREATE INDEX ix_evidence_record_locked
    ON model.modeling_evidence_record (model_id, modeling_evidence_record_id)
    WHERE modeling_evidence_record_is_locked;
