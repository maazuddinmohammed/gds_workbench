-- GDS ETL Workbench Release 1: web application state and orchestration.

CREATE SCHEMA application;

CREATE TABLE application.principal_preference (
    principal_preference_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal_id BIGINT NOT NULL,
    last_tenant_id BIGINT NOT NULL,
    last_accessed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_principal_preference_principal FOREIGN KEY (principal_id)
        REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_principal_preference_tenant FOREIGN KEY (
        last_tenant_id
    ) REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT uq_principal_preference_principal UNIQUE (principal_id)
);

CREATE FUNCTION application.set_principal_last_tenant(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT
)
RETURNS SETOF application.principal_preference
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $set_principal_last_tenant$
DECLARE
    v_decision RECORD;
    v_preference application.principal_preference%ROWTYPE;
BEGIN
    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_read'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'last Tenant preference denied: %',
            coalesce(v_decision.denial_code, 'tenant_not_found');
    END IF;

    INSERT INTO application.principal_preference AS preference (
        principal_id,
        last_tenant_id
    ) VALUES (
        v_decision.principal_id,
        p_tenant_id
    )
    ON CONFLICT (principal_id) DO UPDATE
       SET last_tenant_id = EXCLUDED.last_tenant_id,
           last_accessed_time = CURRENT_TIMESTAMP,
           updated_time = CURRENT_TIMESTAMP,
           updated_by = CURRENT_USER
    RETURNING preference.* INTO v_preference;

    RETURN NEXT v_preference;
END;
$set_principal_last_tenant$;

REVOKE ALL ON FUNCTION application.set_principal_last_tenant(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) FROM PUBLIC;

CREATE FUNCTION application.create_model(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_model_name VARCHAR(255),
    p_model_description VARCHAR(2000),
    p_silver_model_naming_instructions TEXT,
    p_silver_model_audit_columns_template JSONB,
    p_gold_model_naming_instructions TEXT,
    p_gold_model_technical_columns_template JSONB,
    p_gold_model_audit_columns_template JSONB,
    p_default_agent_sdk_code VARCHAR(100),
    p_default_agent_provider_code VARCHAR(100),
    p_default_agent_model_code VARCHAR(200),
    p_default_reasoning_effort_code VARCHAR(50),
    p_default_max_turns INTEGER,
    p_default_validation_retry_count INTEGER
)
RETURNS SETOF model.model
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $create_model$
DECLARE
    v_decision RECORD;
    v_created model.model%ROWTYPE;
BEGIN
    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Model creation denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    INSERT INTO model.model AS target_model (
        tenant_id,
        model_name,
        model_description,
        silver_model_naming_instructions,
        silver_model_audit_columns_template,
        gold_model_naming_instructions,
        gold_model_technical_columns_template,
        gold_model_audit_columns_template,
        default_agent_sdk_code,
        default_agent_provider_code,
        default_agent_model_code,
        default_reasoning_effort_code,
        default_max_turns,
        default_validation_retry_count
    ) VALUES (
        p_tenant_id,
        p_model_name,
        p_model_description,
        p_silver_model_naming_instructions,
        p_silver_model_audit_columns_template,
        p_gold_model_naming_instructions,
        p_gold_model_technical_columns_template,
        p_gold_model_audit_columns_template,
        p_default_agent_sdk_code,
        p_default_agent_provider_code,
        p_default_agent_model_code,
        p_default_reasoning_effort_code,
        p_default_max_turns,
        p_default_validation_retry_count
    )
    RETURNING target_model.* INTO v_created;

    INSERT INTO model.model_revision_transaction (
        model_id,
        change_kind
    ) VALUES (
        v_created.model_id,
        'web_model_create'
    );

    RETURN NEXT v_created;
END;
$create_model$;

REVOKE ALL ON FUNCTION application.create_model(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR,
    TEXT,
    JSONB,
    TEXT,
    JSONB,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.update_model(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_model_id BIGINT,
    p_expected_model_revision BIGINT,
    p_model_name VARCHAR(255),
    p_model_description VARCHAR(2000),
    p_silver_model_naming_instructions TEXT,
    p_silver_model_audit_columns_template JSONB,
    p_gold_model_naming_instructions TEXT,
    p_gold_model_technical_columns_template JSONB,
    p_gold_model_audit_columns_template JSONB,
    p_default_agent_sdk_code VARCHAR(100),
    p_default_agent_provider_code VARCHAR(100),
    p_default_agent_model_code VARCHAR(200),
    p_default_reasoning_effort_code VARCHAR(50),
    p_default_max_turns INTEGER,
    p_default_validation_retry_count INTEGER
)
RETURNS SETOF model.model
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $update_model$
DECLARE
    v_existing model.model%ROWTYPE;
    v_decision RECORD;
    v_updated model.model%ROWTYPE;
    v_updated_time TIMESTAMPTZ;
BEGIN
    SELECT target_model.*
      INTO v_existing
      FROM model.model AS target_model
     WHERE target_model.model_id = p_model_id
       AND target_model.is_active
     FOR UPDATE OF target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Model is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_existing.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Model update denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_existing.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;
    IF ROW(
        v_existing.model_name,
        v_existing.model_description,
        v_existing.silver_model_naming_instructions,
        v_existing.silver_model_audit_columns_template,
        v_existing.gold_model_naming_instructions,
        v_existing.gold_model_technical_columns_template,
        v_existing.gold_model_audit_columns_template,
        v_existing.default_agent_sdk_code,
        v_existing.default_agent_provider_code,
        v_existing.default_agent_model_code,
        v_existing.default_reasoning_effort_code,
        v_existing.default_max_turns,
        v_existing.default_validation_retry_count
    ) IS NOT DISTINCT FROM ROW(
        p_model_name,
        p_model_description,
        p_silver_model_naming_instructions,
        p_silver_model_audit_columns_template,
        p_gold_model_naming_instructions,
        p_gold_model_technical_columns_template,
        p_gold_model_audit_columns_template,
        p_default_agent_sdk_code,
        p_default_agent_provider_code,
        p_default_agent_model_code,
        p_default_reasoning_effort_code,
        p_default_max_turns,
        p_default_validation_retry_count
    ) THEN
        RETURN NEXT v_existing;
        RETURN;
    END IF;

    v_updated_time := clock_timestamp();
    UPDATE model.model AS target_model
       SET model_name = p_model_name,
           model_description = p_model_description,
           model_revision = target_model.model_revision + 1,
           silver_model_naming_instructions =
               p_silver_model_naming_instructions,
           silver_model_audit_columns_template =
               p_silver_model_audit_columns_template,
           gold_model_naming_instructions =
               p_gold_model_naming_instructions,
           gold_model_technical_columns_template =
               p_gold_model_technical_columns_template,
           gold_model_audit_columns_template =
               p_gold_model_audit_columns_template,
           default_agent_sdk_code = p_default_agent_sdk_code,
           default_agent_provider_code = p_default_agent_provider_code,
           default_agent_model_code = p_default_agent_model_code,
           default_reasoning_effort_code = p_default_reasoning_effort_code,
           default_max_turns = p_default_max_turns,
           default_validation_retry_count =
               p_default_validation_retry_count,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE target_model.model_id = p_model_id
    RETURNING target_model.* INTO v_updated;

    INSERT INTO model.model_revision_transaction (
        model_id,
        change_kind
    ) VALUES (
        v_updated.model_id,
        'web_model_update'
    );

    RETURN NEXT v_updated;
END;
$update_model$;

REVOKE ALL ON FUNCTION application.update_model(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
    TEXT,
    JSONB,
    TEXT,
    JSONB,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.archive_model(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_model_id BIGINT,
    p_expected_model_revision BIGINT
)
RETURNS SETOF model.model
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $archive_model$
DECLARE
    v_existing model.model%ROWTYPE;
    v_decision RECORD;
    v_archived model.model%ROWTYPE;
BEGIN
    SELECT target_model.*
      INTO v_existing
      FROM model.model AS target_model
     WHERE target_model.model_id = p_model_id
       AND target_model.is_active
     FOR UPDATE OF target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Model is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_existing.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Model archive denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_existing.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM application.workflow_run AS run
         WHERE run.tenant_id = v_existing.tenant_id
           AND run.workflow_run_state = 'running'
    ) THEN
        RAISE EXCEPTION 'tenant_workflow_conflict';
    END IF;

    UPDATE model.model AS target_model
       SET model_revision = target_model.model_revision + 1,
           is_active = FALSE,
           updated_time = clock_timestamp(),
           updated_by = CURRENT_USER
     WHERE target_model.model_id = p_model_id
    RETURNING target_model.* INTO v_archived;

    INSERT INTO model.model_revision_transaction (
        model_id,
        change_kind
    ) VALUES (
        v_archived.model_id,
        'web_model_archive'
    );

    RETURN NEXT v_archived;
END;
$archive_model$;

REVOKE ALL ON FUNCTION application.archive_model(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) FROM PUBLIC;

CREATE FUNCTION application.replace_model_scope(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_model_id BIGINT,
    p_expected_model_revision BIGINT,
    p_object_ids BIGINT[]
)
RETURNS TABLE (
    changed BOOLEAN,
    model_id BIGINT,
    model_revision BIGINT,
    active_scope_count INTEGER,
    updated_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $replace_model_scope$
DECLARE
    v_existing model.model%ROWTYPE;
    v_decision RECORD;
    v_object_ids BIGINT[];
    v_current_object_ids BIGINT[];
    v_object_count INTEGER;
    v_active_object_count INTEGER;
    v_updated model.model%ROWTYPE;
    v_updated_time TIMESTAMPTZ;
BEGIN
    IF p_object_ids IS NULL OR cardinality(p_object_ids) > 50000 THEN
        RAISE EXCEPTION
            'Model Scope must contain between 0 and 50000 Objects';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM unnest(p_object_ids) AS selected(object_id)
         WHERE selected.object_id IS NULL
            OR selected.object_id <= 0
    ) THEN
        RAISE EXCEPTION 'Model Scope Object IDs must be positive';
    END IF;
    IF cardinality(p_object_ids) <> (
        SELECT count(DISTINCT selected.object_id)
          FROM unnest(p_object_ids) AS selected(object_id)
    ) THEN
        RAISE EXCEPTION 'Model Scope Object IDs must be unique';
    END IF;

    SELECT coalesce(
               array_agg(selected.object_id ORDER BY selected.object_id),
               ARRAY[]::BIGINT[]
           ),
           count(*)::INTEGER
      INTO v_object_ids,
           v_object_count
      FROM unnest(p_object_ids) AS selected(object_id);

    SELECT target_model.*
      INTO v_existing
      FROM model.model AS target_model
     WHERE target_model.model_id = p_model_id
       AND target_model.is_active
     FOR UPDATE OF target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Model is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_existing.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Model Scope replacement denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_existing.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_active_object_count
      FROM workflow.list_tenant_visible_objects(
               v_existing.tenant_id
           ) AS visible_object
      JOIN core.object AS object_record
        ON object_record.object_id = visible_object.object_id
       AND object_record.is_active
     WHERE visible_object.object_id = ANY(v_object_ids);
    IF v_active_object_count <> v_object_count THEN
        RAISE EXCEPTION 'Model Scope contains an unavailable Object';
    END IF;

    SELECT coalesce(
               array_agg(scope.object_id ORDER BY scope.object_id),
               ARRAY[]::BIGINT[]
           )
      INTO v_current_object_ids
      FROM model.model_scope AS scope
     WHERE scope.model_id = p_model_id
       AND scope.is_active;
    IF v_current_object_ids = v_object_ids THEN
        RETURN QUERY SELECT
            FALSE,
            v_existing.model_id,
            v_existing.model_revision,
            v_object_count,
            v_existing.updated_time;
        RETURN;
    END IF;

    v_updated_time := clock_timestamp();
    UPDATE model.model_scope AS scope
       SET is_active = FALSE,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE scope.model_id = p_model_id
       AND scope.is_active
       AND NOT (scope.object_id = ANY(v_object_ids));

    INSERT INTO model.model_scope AS scope (
        model_id,
        object_id
    )
    SELECT p_model_id,
           selected.object_id
      FROM unnest(v_object_ids) AS selected(object_id)
    ON CONFLICT ON CONSTRAINT uq_model_scope DO UPDATE
       SET is_active = TRUE,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE NOT scope.is_active;

    UPDATE model.model AS target_model
       SET model_revision = target_model.model_revision + 1,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE target_model.model_id = p_model_id
    RETURNING target_model.* INTO v_updated;

    INSERT INTO model.model_revision_transaction (
        model_id,
        change_kind
    ) VALUES (
        v_updated.model_id,
        'web_model_scope_replace'
    );

    RETURN QUERY SELECT
        TRUE,
        v_updated.model_id,
        v_updated.model_revision,
        v_object_count,
        v_updated.updated_time;
END;
$replace_model_scope$;

REVOKE ALL ON FUNCTION application.replace_model_scope(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT[]
) FROM PUBLIC;

CREATE TABLE application.workflow_stage (
    workflow_stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_workflow VARCHAR(30) NOT NULL,
    workflow_execution_mode VARCHAR(50),
    workflow_stage_code VARCHAR(100) NOT NULL,
    workflow_stage_name VARCHAR(200) NOT NULL,
    workflow_stage_description TEXT,
    workflow_stage_order INTEGER NOT NULL,
    workflow_stage_is_agentic BOOLEAN NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT uq_workflow_stage_identity UNIQUE NULLS NOT DISTINCT (
        model_workflow,
        workflow_execution_mode,
        workflow_stage_code
    ),
    CONSTRAINT uq_workflow_stage_order UNIQUE NULLS NOT DISTINCT (
        model_workflow,
        workflow_execution_mode,
        workflow_stage_order
    ),
    CONSTRAINT ck_workflow_stage_workflow CHECK (
        model_workflow IN (
            'profiling', 'analysis', 'conceptual', 'logical',
            'dimensional', 'mapping', 'code_generation'
        )
    ),
    CONSTRAINT ck_workflow_stage_execution_mode CHECK (
        workflow_execution_mode IS NULL
        OR workflow_execution_mode IN (
            'one_shot', 'tool_assisted', 'detailed_coverage'
        )
    ),
    CONSTRAINT ck_workflow_stage_code CHECK (
        workflow_stage_code ~ '^[a-z][a-z0-9_]{0,99}$'
    ),
    CONSTRAINT ck_workflow_stage_name CHECK (
        reference.is_nonblank(workflow_stage_name)
    ),
    CONSTRAINT ck_workflow_stage_description CHECK (
        workflow_stage_description IS NULL
        OR reference.is_nonblank(workflow_stage_description)
    ),
    CONSTRAINT ck_workflow_stage_order CHECK (workflow_stage_order > 0)
);

CREATE INDEX ix_workflow_stage_lookup
    ON application.workflow_stage (
        model_workflow,
        workflow_execution_mode,
        is_active,
        workflow_stage_order
    );

CREATE TABLE application.workflow_stage_variable (
    workflow_stage_variable_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_stage_id BIGINT NOT NULL,
    workflow_stage_variable_name VARCHAR(100) NOT NULL,
    workflow_stage_variable_resolver_key VARCHAR(200) NOT NULL,
    workflow_stage_variable_data_type VARCHAR(30) NOT NULL,
    workflow_stage_variable_is_required BOOLEAN NOT NULL DEFAULT FALSE,
    workflow_stage_variable_description TEXT NOT NULL,
    workflow_stage_variable_example JSONB,
    workflow_stage_variable_order INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_workflow_stage_variable_stage FOREIGN KEY (
        workflow_stage_id
    ) REFERENCES application.workflow_stage (workflow_stage_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_workflow_stage_variable_name UNIQUE (
        workflow_stage_id,
        workflow_stage_variable_name
    ),
    CONSTRAINT uq_workflow_stage_variable_resolver UNIQUE (
        workflow_stage_id,
        workflow_stage_variable_resolver_key
    ),
    CONSTRAINT uq_workflow_stage_variable_order UNIQUE (
        workflow_stage_id,
        workflow_stage_variable_order
    ),
    CONSTRAINT ck_workflow_stage_variable_name CHECK (
        workflow_stage_variable_name ~ '^[a-z][a-z0-9_]{0,99}$'
    ),
    CONSTRAINT ck_workflow_stage_variable_resolver CHECK (
        workflow_stage_variable_resolver_key
            ~ '^[a-z][a-z0-9_.]{0,199}$'
    ),
    CONSTRAINT ck_workflow_stage_variable_data_type CHECK (
        workflow_stage_variable_data_type IN (
            'text', 'integer', 'number', 'boolean', 'json'
        )
    ),
    CONSTRAINT ck_workflow_stage_variable_description CHECK (
        reference.is_nonblank(workflow_stage_variable_description)
    ),
    CONSTRAINT ck_workflow_stage_variable_order CHECK (
        workflow_stage_variable_order > 0
    ),
    CONSTRAINT ck_workflow_stage_variable_example CHECK (
        workflow_stage_variable_example IS NULL
        OR (
            octet_length(workflow_stage_variable_example::TEXT) <= 4096
            AND (
                workflow_stage_variable_data_type = 'json'
                OR (
                    workflow_stage_variable_data_type = 'text'
                    AND jsonb_typeof(workflow_stage_variable_example) = 'string'
                )
                OR (
                    workflow_stage_variable_data_type = 'integer'
                    AND jsonb_typeof(workflow_stage_variable_example) = 'number'
                    AND workflow_stage_variable_example::TEXT ~ '^-?[0-9]+$'
                )
                OR (
                    workflow_stage_variable_data_type = 'number'
                    AND jsonb_typeof(workflow_stage_variable_example) = 'number'
                )
                OR (
                    workflow_stage_variable_data_type = 'boolean'
                    AND jsonb_typeof(workflow_stage_variable_example) = 'boolean'
                )
            )
        )
    )
);

CREATE INDEX ix_workflow_stage_variable_lookup
    ON application.workflow_stage_variable (
        workflow_stage_id,
        is_active,
        workflow_stage_variable_order
    );

CREATE TABLE application.prompt_template (
    prompt_template_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_stage_id BIGINT NOT NULL,
    prompt_template_ownership_scope VARCHAR(20) NOT NULL,
    owner_tenant_id BIGINT,
    prompt_template_code VARCHAR(100) NOT NULL,
    prompt_template_name VARCHAR(200) NOT NULL,
    prompt_template_description TEXT,
    created_by_principal_id BIGINT NOT NULL,
    updated_by_principal_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_prompt_template_stage FOREIGN KEY (workflow_stage_id)
        REFERENCES application.workflow_stage (workflow_stage_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_owner_tenant FOREIGN KEY (owner_tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_updater FOREIGN KEY (
        updated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_prompt_template_witness UNIQUE (
        prompt_template_id,
        workflow_stage_id
    ),
    CONSTRAINT ck_prompt_template_ownership CHECK (
        (
            prompt_template_ownership_scope = 'global'
            AND owner_tenant_id IS NULL
        ) OR (
            prompt_template_ownership_scope = 'tenant'
            AND owner_tenant_id IS NOT NULL
        )
    ),
    CONSTRAINT ck_prompt_template_code CHECK (
        prompt_template_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_prompt_template_name CHECK (
        reference.is_nonblank(prompt_template_name)
    ),
    CONSTRAINT ck_prompt_template_description CHECK (
        prompt_template_description IS NULL
        OR reference.is_nonblank(prompt_template_description)
    )
);

CREATE UNIQUE INDEX ux_prompt_template_global_code
    ON application.prompt_template (
        workflow_stage_id,
        lower(prompt_template_code)
    ) WHERE prompt_template_ownership_scope = 'global';
CREATE UNIQUE INDEX ux_prompt_template_tenant_code
    ON application.prompt_template (
        owner_tenant_id,
        workflow_stage_id,
        lower(prompt_template_code)
    ) WHERE prompt_template_ownership_scope = 'tenant';

CREATE FUNCTION application.guard_prompt_template()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_prompt_template$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'prompt templates cannot be deleted';
    END IF;

    IF ROW(
        NEW.prompt_template_id,
        NEW.workflow_stage_id,
        NEW.prompt_template_ownership_scope,
        NEW.owner_tenant_id,
        NEW.prompt_template_code,
        NEW.created_by_principal_id,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.prompt_template_id,
        OLD.workflow_stage_id,
        OLD.prompt_template_ownership_scope,
        OLD.owner_tenant_id,
        OLD.prompt_template_code,
        OLD.created_by_principal_id,
        OLD.created_time,
        OLD.created_by
    ) THEN
        RAISE EXCEPTION 'prompt template identity is immutable';
    END IF;

    RETURN NEW;
END;
$guard_prompt_template$;

CREATE TRIGGER guard_prompt_template
BEFORE UPDATE OR DELETE ON application.prompt_template
FOR EACH ROW EXECUTE FUNCTION application.guard_prompt_template();

CREATE TABLE application.prompt_template_version (
    prompt_template_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prompt_template_id BIGINT NOT NULL,
    workflow_stage_id BIGINT NOT NULL,
    prompt_template_version_number INTEGER NOT NULL,
    system_prompt_template TEXT NOT NULL,
    instruction_prompt_template TEXT NOT NULL,
    tool_instruction_prompt_template TEXT,
    prompt_template_digest CHAR(64) NOT NULL,
    prompt_template_version_status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_by_principal_id BIGINT NOT NULL,
    updated_by_principal_id BIGINT NOT NULL,
    published_time TIMESTAMPTZ,
    published_by_principal_id BIGINT,
    retired_time TIMESTAMPTZ,
    retired_by_principal_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_prompt_template_version_template FOREIGN KEY (
        prompt_template_id,
        workflow_stage_id
    ) REFERENCES application.prompt_template (
        prompt_template_id,
        workflow_stage_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_version_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_version_updater FOREIGN KEY (
        updated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_version_publisher FOREIGN KEY (
        published_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_template_version_retirer FOREIGN KEY (
        retired_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_prompt_template_version UNIQUE (
        prompt_template_id,
        prompt_template_version_number
    ),
    CONSTRAINT uq_prompt_template_version_stage_witness UNIQUE (
        prompt_template_version_id,
        workflow_stage_id
    ),
    CONSTRAINT uq_prompt_template_version_digest_witness UNIQUE (
        prompt_template_version_id,
        workflow_stage_id,
        prompt_template_digest
    ),
    CONSTRAINT ck_prompt_template_version_number CHECK (
        prompt_template_version_number > 0
    ),
    CONSTRAINT ck_prompt_template_version_content CHECK (
        reference.is_nonblank(system_prompt_template)
        AND reference.is_nonblank(instruction_prompt_template)
        AND (
            tool_instruction_prompt_template IS NULL
            OR reference.is_nonblank(tool_instruction_prompt_template)
        )
        AND octet_length(system_prompt_template) <= 262144
        AND octet_length(instruction_prompt_template) <= 262144
        AND (
            tool_instruction_prompt_template IS NULL
            OR octet_length(tool_instruction_prompt_template) <= 262144
        )
    ),
    CONSTRAINT ck_prompt_template_version_digest CHECK (
        prompt_template_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_prompt_template_version_lifecycle CHECK (
        (
            prompt_template_version_status = 'draft'
            AND published_time IS NULL
            AND published_by_principal_id IS NULL
            AND retired_time IS NULL
            AND retired_by_principal_id IS NULL
        ) OR (
            prompt_template_version_status = 'published'
            AND published_time IS NOT NULL
            AND published_by_principal_id IS NOT NULL
            AND updated_by_principal_id = published_by_principal_id
            AND retired_time IS NULL
            AND retired_by_principal_id IS NULL
        ) OR (
            prompt_template_version_status = 'retired'
            AND published_time IS NOT NULL
            AND published_by_principal_id IS NOT NULL
            AND retired_time IS NOT NULL
            AND retired_by_principal_id IS NOT NULL
            AND updated_by_principal_id = retired_by_principal_id
            AND retired_time >= published_time
        )
    )
);

CREATE INDEX ix_prompt_template_version_lookup
    ON application.prompt_template_version (
        prompt_template_id,
        prompt_template_version_status,
        prompt_template_version_number DESC
    );
CREATE UNIQUE INDEX ux_prompt_template_one_draft
    ON application.prompt_template_version (prompt_template_id)
    WHERE prompt_template_version_status = 'draft';

CREATE FUNCTION application.guard_prompt_template_version()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_prompt_template_version$
DECLARE
    v_expected_digest CHAR(64);
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'prompt versions cannot be deleted';
    END IF;

    v_expected_digest := encode(
        sha256(
            convert_to(
                jsonb_build_object(
                    'system_prompt_template', NEW.system_prompt_template,
                    'instruction_prompt_template',
                        NEW.instruction_prompt_template,
                    'tool_instruction_prompt_template',
                        NEW.tool_instruction_prompt_template
                )::TEXT,
                'UTF8'
            )
        ),
        'hex'
    );
    IF TG_OP = 'INSERT'
       AND NEW.prompt_template_digest IS DISTINCT FROM v_expected_digest THEN
        RAISE EXCEPTION
            'prompt template digest does not match prompt content';
    END IF;

    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF ROW(
        NEW.prompt_template_version_id,
        NEW.prompt_template_id,
        NEW.workflow_stage_id,
        NEW.prompt_template_version_number,
        NEW.created_by_principal_id,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.prompt_template_version_id,
        OLD.prompt_template_id,
        OLD.workflow_stage_id,
        OLD.prompt_template_version_number,
        OLD.created_by_principal_id,
        OLD.created_time,
        OLD.created_by
    ) THEN
        RAISE EXCEPTION 'prompt version identity is immutable';
    END IF;

    IF OLD.prompt_template_version_status = 'retired' THEN
        RAISE EXCEPTION 'retired prompt version is immutable';
    END IF;

    IF OLD.prompt_template_version_status = 'published' THEN
        IF NEW.prompt_template_version_status <> 'retired'
           OR ROW(
               NEW.system_prompt_template,
               NEW.instruction_prompt_template,
               NEW.tool_instruction_prompt_template,
               NEW.prompt_template_digest,
               NEW.published_time,
               NEW.published_by_principal_id
           ) IS DISTINCT FROM ROW(
               OLD.system_prompt_template,
               OLD.instruction_prompt_template,
               OLD.tool_instruction_prompt_template,
               OLD.prompt_template_digest,
               OLD.published_time,
               OLD.published_by_principal_id
           ) THEN
            RAISE EXCEPTION 'published prompt version is immutable';
        END IF;
    ELSIF NEW.prompt_template_version_status NOT IN ('draft', 'published') THEN
        RAISE EXCEPTION 'draft prompt version can only be published';
    END IF;

    IF NEW.prompt_template_digest IS DISTINCT FROM v_expected_digest THEN
        RAISE EXCEPTION
            'prompt template digest does not match prompt content';
    END IF;

    RETURN NEW;
END;
$guard_prompt_template_version$;

CREATE TRIGGER guard_prompt_template_version
BEFORE INSERT OR UPDATE OR DELETE ON application.prompt_template_version
FOR EACH ROW EXECUTE FUNCTION application.guard_prompt_template_version();

CREATE TABLE application.prompt_assignment (
    prompt_assignment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_stage_id BIGINT NOT NULL,
    prompt_template_version_id BIGINT NOT NULL,
    prompt_assignment_scope VARCHAR(20) NOT NULL,
    model_id BIGINT,
    assigned_by_principal_id BIGINT NOT NULL,
    deactivated_by_principal_id BIGINT,
    deactivated_time TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_prompt_assignment_version FOREIGN KEY (
        prompt_template_version_id,
        workflow_stage_id
    ) REFERENCES application.prompt_template_version (
        prompt_template_version_id,
        workflow_stage_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_assignment_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_assignment_actor FOREIGN KEY (
        assigned_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_prompt_assignment_deactivator FOREIGN KEY (
        deactivated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT ck_prompt_assignment_shape CHECK (
        (
            prompt_assignment_scope = 'global_default'
            AND model_id IS NULL
        ) OR (
            prompt_assignment_scope = 'model_default'
            AND model_id IS NOT NULL
        )
    ),
    CONSTRAINT ck_prompt_assignment_lifecycle CHECK (
        (
            is_active
            AND deactivated_by_principal_id IS NULL
            AND deactivated_time IS NULL
        ) OR (
            NOT is_active
            AND deactivated_by_principal_id IS NOT NULL
            AND deactivated_time IS NOT NULL
            AND deactivated_time >= created_time
        )
    )
);

CREATE UNIQUE INDEX ux_prompt_assignment_global_active
    ON application.prompt_assignment (workflow_stage_id)
    WHERE prompt_assignment_scope = 'global_default' AND is_active;
CREATE UNIQUE INDEX ux_prompt_assignment_model_active
    ON application.prompt_assignment (model_id, workflow_stage_id)
    WHERE prompt_assignment_scope = 'model_default' AND is_active;
CREATE INDEX ix_prompt_assignment_version
    ON application.prompt_assignment (
        prompt_template_version_id,
        is_active
    );

CREATE FUNCTION application.validate_prompt_assignment()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $validate_prompt_assignment$
DECLARE
    v_version_status VARCHAR(20);
    v_template_scope VARCHAR(20);
    v_template_tenant_id BIGINT;
    v_template_active BOOLEAN;
    v_stage_agentic BOOLEAN;
    v_stage_active BOOLEAN;
    v_model_tenant_id BIGINT;
    v_actor_super_admin BOOLEAN;
    v_actor_authorized BOOLEAN;
    v_actor_has_lock BOOLEAN;
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.is_active
       AND NOT NEW.is_active
       AND ROW(
           NEW.workflow_stage_id,
           NEW.prompt_template_version_id,
           NEW.prompt_assignment_scope,
           NEW.model_id,
           NEW.assigned_by_principal_id
       ) IS NOT DISTINCT FROM ROW(
           OLD.workflow_stage_id,
           OLD.prompt_template_version_id,
           OLD.prompt_assignment_scope,
           OLD.model_id,
           OLD.assigned_by_principal_id
       ) THEN
        RETURN NEW;
    END IF;

    SELECT version.prompt_template_version_status,
           template.prompt_template_ownership_scope,
           template.owner_tenant_id,
           template.is_active,
           stage.workflow_stage_is_agentic,
           stage.is_active
      INTO v_version_status,
           v_template_scope,
           v_template_tenant_id,
           v_template_active,
           v_stage_agentic,
           v_stage_active
      FROM application.prompt_template_version AS version
      JOIN application.prompt_template AS template
        ON template.prompt_template_id = version.prompt_template_id
       AND template.workflow_stage_id = version.workflow_stage_id
      JOIN application.workflow_stage AS stage
        ON stage.workflow_stage_id = version.workflow_stage_id
     WHERE version.prompt_template_version_id = NEW.prompt_template_version_id
       AND version.workflow_stage_id = NEW.workflow_stage_id;

    IF NOT FOUND OR v_version_status <> 'published' THEN
        RAISE EXCEPTION 'assignment requires a published prompt version';
    END IF;
    IF NOT v_template_active OR NOT v_stage_active OR NOT v_stage_agentic THEN
        RAISE EXCEPTION 'assignment requires an active agentic prompt stage';
    END IF;

    SELECT principal.is_super_admin
      INTO v_actor_super_admin
      FROM security.principal AS principal
     WHERE principal.principal_id = NEW.assigned_by_principal_id
       AND principal.is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'assignment actor is unavailable';
    END IF;

    IF NEW.prompt_assignment_scope = 'global_default' THEN
        IF v_template_scope <> 'global' THEN
            RAISE EXCEPTION 'global default requires a global prompt';
        END IF;
        IF NOT v_actor_super_admin THEN
            RAISE EXCEPTION 'global prompt assignment requires Super Admin';
        END IF;
        RETURN NEW;
    END IF;

    SELECT model.tenant_id
      INTO v_model_tenant_id
      FROM model.model AS model
     WHERE model.model_id = NEW.model_id
       AND model.is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'assignment Model is unavailable';
    END IF;

    IF v_template_scope = 'tenant'
       AND v_template_tenant_id <> v_model_tenant_id THEN
        RAISE EXCEPTION 'prompt does not belong to the Model owner Tenant';
    END IF;

    SELECT v_actor_super_admin OR EXISTS (
               SELECT 1
                 FROM security.tenant_principal_access AS access
                WHERE access.tenant_id = v_model_tenant_id
                  AND access.principal_id = NEW.assigned_by_principal_id
                  AND access.tenant_role IN ('architect', 'tenant_admin')
                  AND access.is_active
                  AND (
                      access.access_expires_time IS NULL
                      OR access.access_expires_time > clock_timestamp()
                  )
           )
      INTO v_actor_authorized;
    IF NOT v_actor_authorized THEN
        RAISE EXCEPTION 'Model prompt assignment is not authorized';
    END IF;

    SELECT EXISTS (
               SELECT 1
                 FROM security.tenant_lock AS tenant_lock
                WHERE tenant_lock.tenant_id = v_model_tenant_id
                  AND tenant_lock.locked_by_principal_id =
                      NEW.assigned_by_principal_id
                  AND tenant_lock.tenant_lock_expires_time > clock_timestamp()
           )
      INTO v_actor_has_lock;
    IF NOT v_actor_has_lock THEN
        RAISE EXCEPTION 'Model prompt assignment requires the owned Tenant Lock';
    END IF;

    RETURN NEW;
END;
$validate_prompt_assignment$;

CREATE TRIGGER validate_prompt_assignment
BEFORE INSERT OR UPDATE ON application.prompt_assignment
FOR EACH ROW EXECUTE FUNCTION application.validate_prompt_assignment();

CREATE FUNCTION application.save_prompt_template(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_prompt_template_id BIGINT,
    p_workflow_stage_id BIGINT,
    p_prompt_template_ownership_scope VARCHAR(20),
    p_owner_tenant_id BIGINT,
    p_prompt_template_code VARCHAR(100),
    p_prompt_template_name VARCHAR(200),
    p_prompt_template_description TEXT,
    p_is_active BOOLEAN,
    p_expected_updated_time TIMESTAMPTZ
)
RETURNS SETOF application.prompt_template
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $save_prompt_template$
DECLARE
    v_existing application.prompt_template%ROWTYPE;
    v_saved application.prompt_template%ROWTYPE;
    v_decision RECORD;
    v_actor RECORD;
    v_scope VARCHAR(20);
    v_owner_tenant_id BIGINT;
    v_stage_id BIGINT;
    v_updated_time TIMESTAMPTZ;
BEGIN
    IF p_prompt_template_id IS NULL THEN
        v_scope := p_prompt_template_ownership_scope;
        v_owner_tenant_id := p_owner_tenant_id;
        v_stage_id := p_workflow_stage_id;
    ELSE
        SELECT template.*
          INTO v_existing
          FROM application.prompt_template AS template
         WHERE template.prompt_template_id = p_prompt_template_id
         FOR UPDATE OF template;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Prompt Template is unavailable';
        END IF;
        v_scope := v_existing.prompt_template_ownership_scope;
        v_owner_tenant_id := v_existing.owner_tenant_id;
        v_stage_id := v_existing.workflow_stage_id;
    END IF;

    IF v_scope = 'global' AND v_owner_tenant_id IS NULL THEN
        SELECT principal.principal_id, principal.is_super_admin
          INTO v_actor
          FROM security.entra_principal_identity AS identity
          JOIN security.principal AS principal
            ON principal.principal_id = identity.principal_id
           AND principal.principal_type = identity.principal_type
         WHERE identity.entra_tenant_id = p_entra_tenant_id
           AND identity.entra_object_id = p_entra_object_id
           AND identity.principal_type = p_expected_principal_type
           AND identity.is_active
           AND principal.is_active
         FOR SHARE OF identity, principal;
        IF NOT FOUND OR NOT v_actor.is_super_admin THEN
            RAISE EXCEPTION 'Global Prompt Template requires Super Admin';
        END IF;
    ELSIF v_scope = 'tenant' AND v_owner_tenant_id IS NOT NULL THEN
        SELECT *
          INTO v_decision
          FROM security.authorize_tenant_operation(
              p_entra_tenant_id,
              p_entra_object_id,
              p_expected_principal_type,
              v_owner_tenant_id,
              'tenant_model_write'
          );
        IF NOT FOUND OR NOT v_decision.authorized THEN
            RAISE EXCEPTION 'Tenant Prompt Template denied: %',
                coalesce(v_decision.denial_code, 'authorization_denied');
        END IF;
        v_actor := v_decision;
    ELSE
        RAISE EXCEPTION 'Prompt Template ownership is invalid';
    END IF;

    PERFORM 1
      FROM application.workflow_stage AS stage
     WHERE stage.workflow_stage_id = v_stage_id
       AND stage.workflow_stage_is_agentic
       AND stage.is_active
     FOR SHARE OF stage;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Prompt Template requires an active agentic Workflow Stage';
    END IF;

    IF p_prompt_template_id IS NULL THEN
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended(
                concat_ws(
                    ':',
                    'application.prompt_template',
                    p_workflow_stage_id::TEXT,
                    p_prompt_template_ownership_scope,
                    coalesce(p_owner_tenant_id::TEXT, 'global'),
                    lower(p_prompt_template_code)
                ),
                0
            )
        );
        SELECT template.*
          INTO v_existing
          FROM application.prompt_template AS template
         WHERE template.workflow_stage_id = p_workflow_stage_id
           AND template.prompt_template_ownership_scope =
               p_prompt_template_ownership_scope
           AND template.owner_tenant_id IS NOT DISTINCT FROM p_owner_tenant_id
           AND lower(template.prompt_template_code) =
               lower(p_prompt_template_code)
         FOR UPDATE OF template;
        IF FOUND THEN
            IF ROW(
                v_existing.prompt_template_code,
                v_existing.prompt_template_name,
                v_existing.prompt_template_description,
                v_existing.is_active
            ) IS DISTINCT FROM ROW(
                p_prompt_template_code,
                p_prompt_template_name,
                p_prompt_template_description,
                p_is_active
            ) THEN
                RAISE EXCEPTION 'Prompt Template code conflict';
            END IF;
            RETURN NEXT v_existing;
            RETURN;
        END IF;

        INSERT INTO application.prompt_template AS template (
            workflow_stage_id,
            prompt_template_ownership_scope,
            owner_tenant_id,
            prompt_template_code,
            prompt_template_name,
            prompt_template_description,
            created_by_principal_id,
            updated_by_principal_id,
            is_active
        ) VALUES (
            p_workflow_stage_id,
            p_prompt_template_ownership_scope,
            p_owner_tenant_id,
            p_prompt_template_code,
            p_prompt_template_name,
            p_prompt_template_description,
            v_actor.principal_id,
            v_actor.principal_id,
            p_is_active
        )
        RETURNING template.* INTO v_saved;
        RETURN NEXT v_saved;
        RETURN;
    END IF;

    IF ROW(
        v_existing.workflow_stage_id,
        v_existing.prompt_template_ownership_scope,
        v_existing.owner_tenant_id,
        v_existing.prompt_template_code
    ) IS DISTINCT FROM ROW(
        p_workflow_stage_id,
        p_prompt_template_ownership_scope,
        p_owner_tenant_id,
        p_prompt_template_code
    ) THEN
        RAISE EXCEPTION 'Prompt Template identity is immutable';
    END IF;
    IF ROW(
        v_existing.prompt_template_name,
        v_existing.prompt_template_description,
        v_existing.is_active
    ) IS NOT DISTINCT FROM ROW(
        p_prompt_template_name,
        p_prompt_template_description,
        p_is_active
    ) THEN
        RETURN NEXT v_existing;
        RETURN;
    END IF;
    IF p_expected_updated_time IS NULL
       OR v_existing.updated_time <> p_expected_updated_time THEN
        RAISE EXCEPTION 'stale_prompt_template';
    END IF;
    IF v_existing.is_active
       AND NOT p_is_active
       AND EXISTS (
           SELECT 1
             FROM application.prompt_template_version AS version
             JOIN application.prompt_assignment AS assignment
               ON assignment.prompt_template_version_id =
                  version.prompt_template_version_id
              AND assignment.is_active
            WHERE version.prompt_template_id = p_prompt_template_id
       ) THEN
        RAISE EXCEPTION
            'Prompt Template has active assignments; clear them first';
    END IF;

    v_updated_time := clock_timestamp();
    UPDATE application.prompt_template AS template
       SET prompt_template_name = p_prompt_template_name,
           prompt_template_description = p_prompt_template_description,
           updated_by_principal_id = v_actor.principal_id,
           is_active = p_is_active,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE template.prompt_template_id = p_prompt_template_id
    RETURNING template.* INTO v_saved;

    RETURN NEXT v_saved;
END;
$save_prompt_template$;

REVOKE ALL ON FUNCTION application.save_prompt_template(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR,
    TEXT,
    BOOLEAN,
    TIMESTAMPTZ
) FROM PUBLIC;

CREATE FUNCTION application.save_prompt_template_draft(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_prompt_template_id BIGINT,
    p_expected_prompt_template_version_id BIGINT,
    p_system_prompt_template TEXT,
    p_instruction_prompt_template TEXT,
    p_tool_instruction_prompt_template TEXT,
    p_expected_updated_time TIMESTAMPTZ
)
RETURNS SETOF application.prompt_template_version
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $save_prompt_template_draft$
DECLARE
    v_template RECORD;
    v_decision RECORD;
    v_actor RECORD;
    v_draft application.prompt_template_version%ROWTYPE;
    v_saved application.prompt_template_version%ROWTYPE;
    v_digest CHAR(64);
    v_version_number INTEGER;
    v_updated_time TIMESTAMPTZ;
BEGIN
    IF p_system_prompt_template IS NULL
       OR btrim(p_system_prompt_template) = ''
       OR octet_length(p_system_prompt_template) > 262144
       OR p_instruction_prompt_template IS NULL
       OR btrim(p_instruction_prompt_template) = ''
       OR octet_length(p_instruction_prompt_template) > 262144
       OR (
           p_tool_instruction_prompt_template IS NOT NULL
           AND (
               btrim(p_tool_instruction_prompt_template) = ''
               OR octet_length(p_tool_instruction_prompt_template) > 262144
           )
       ) THEN
        RAISE EXCEPTION 'Prompt Template content is invalid';
    END IF;

    SELECT template.prompt_template_id,
           template.workflow_stage_id,
           template.prompt_template_ownership_scope,
           template.owner_tenant_id,
           stage.workflow_stage_is_agentic,
           stage.is_active AS workflow_stage_is_active
      INTO v_template
      FROM application.prompt_template AS template
      JOIN application.workflow_stage AS stage
        ON stage.workflow_stage_id = template.workflow_stage_id
     WHERE template.prompt_template_id = p_prompt_template_id
       AND template.is_active
     FOR UPDATE OF template, stage;
    IF NOT FOUND
       OR NOT v_template.workflow_stage_is_agentic
       OR NOT v_template.workflow_stage_is_active THEN
        RAISE EXCEPTION 'Prompt Template is unavailable for draft authoring';
    END IF;

    IF v_template.prompt_template_ownership_scope = 'global' THEN
        SELECT principal.principal_id, principal.is_super_admin
          INTO v_actor
          FROM security.entra_principal_identity AS identity
          JOIN security.principal AS principal
            ON principal.principal_id = identity.principal_id
           AND principal.principal_type = identity.principal_type
         WHERE identity.entra_tenant_id = p_entra_tenant_id
           AND identity.entra_object_id = p_entra_object_id
           AND identity.principal_type = p_expected_principal_type
           AND identity.is_active
           AND principal.is_active
         FOR SHARE OF identity, principal;
        IF NOT FOUND OR NOT v_actor.is_super_admin THEN
            RAISE EXCEPTION 'Global Prompt Template requires Super Admin';
        END IF;
    ELSE
        SELECT *
          INTO v_decision
          FROM security.authorize_tenant_operation(
              p_entra_tenant_id,
              p_entra_object_id,
              p_expected_principal_type,
              v_template.owner_tenant_id,
              'tenant_model_write'
          );
        IF NOT FOUND OR NOT v_decision.authorized THEN
            RAISE EXCEPTION 'Tenant Prompt Template draft denied: %',
                coalesce(v_decision.denial_code, 'authorization_denied');
        END IF;
        v_actor := v_decision;
    END IF;

    v_digest := encode(
        sha256(
            convert_to(
                jsonb_build_object(
                    'system_prompt_template', p_system_prompt_template,
                    'instruction_prompt_template', p_instruction_prompt_template,
                    'tool_instruction_prompt_template',
                        p_tool_instruction_prompt_template
                )::TEXT,
                'UTF8'
            )
        ),
        'hex'
    );

    SELECT version.*
      INTO v_draft
      FROM application.prompt_template_version AS version
     WHERE version.prompt_template_id = p_prompt_template_id
       AND version.prompt_template_version_status = 'draft'
     FOR UPDATE OF version;
    IF FOUND THEN
        IF v_draft.prompt_template_digest = v_digest THEN
            RETURN NEXT v_draft;
            RETURN;
        END IF;
        IF p_expected_prompt_template_version_id IS NULL
           OR v_draft.prompt_template_version_id <>
              p_expected_prompt_template_version_id
           OR p_expected_updated_time IS NULL
           OR v_draft.updated_time <> p_expected_updated_time THEN
            RAISE EXCEPTION 'stale_prompt_template_draft';
        END IF;

        v_updated_time := clock_timestamp();
        UPDATE application.prompt_template_version AS version
           SET system_prompt_template = p_system_prompt_template,
               instruction_prompt_template = p_instruction_prompt_template,
               tool_instruction_prompt_template =
                   p_tool_instruction_prompt_template,
               prompt_template_digest = v_digest,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_updated_time,
               updated_by = CURRENT_USER
         WHERE version.prompt_template_version_id =
               v_draft.prompt_template_version_id
        RETURNING version.* INTO v_saved;
        RETURN NEXT v_saved;
        RETURN;
    END IF;

    IF p_expected_prompt_template_version_id IS NOT NULL
       OR p_expected_updated_time IS NOT NULL THEN
        RAISE EXCEPTION 'Prompt Template draft does not exist';
    END IF;
    SELECT coalesce(max(version.prompt_template_version_number), 0) + 1
      INTO v_version_number
      FROM application.prompt_template_version AS version
     WHERE version.prompt_template_id = p_prompt_template_id;

    INSERT INTO application.prompt_template_version AS version (
        prompt_template_id,
        workflow_stage_id,
        prompt_template_version_number,
        system_prompt_template,
        instruction_prompt_template,
        tool_instruction_prompt_template,
        prompt_template_digest,
        created_by_principal_id,
        updated_by_principal_id
    ) VALUES (
        p_prompt_template_id,
        v_template.workflow_stage_id,
        v_version_number,
        p_system_prompt_template,
        p_instruction_prompt_template,
        p_tool_instruction_prompt_template,
        v_digest,
        v_actor.principal_id,
        v_actor.principal_id
    )
    RETURNING version.* INTO v_saved;

    RETURN NEXT v_saved;
END;
$save_prompt_template_draft$;

REVOKE ALL ON FUNCTION application.save_prompt_template_draft(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    TEXT,
    TEXT,
    TEXT,
    TIMESTAMPTZ
) FROM PUBLIC;

CREATE FUNCTION application.transition_prompt_template_version(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_prompt_template_version_id BIGINT,
    p_expected_status VARCHAR(20),
    p_target_status VARCHAR(20)
)
RETURNS SETOF application.prompt_template_version
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $transition_prompt_template_version$
DECLARE
    v_version application.prompt_template_version%ROWTYPE;
    v_template RECORD;
    v_template_id BIGINT;
    v_decision RECORD;
    v_actor RECORD;
    v_saved application.prompt_template_version%ROWTYPE;
    v_transition_time TIMESTAMPTZ;
BEGIN
    SELECT version.prompt_template_id
      INTO v_template_id
      FROM application.prompt_template_version AS version
     WHERE version.prompt_template_version_id = p_prompt_template_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Prompt Template version is unavailable';
    END IF;

    SELECT template.prompt_template_ownership_scope,
           template.owner_tenant_id,
           template.is_active
      INTO v_template
      FROM application.prompt_template AS template
     WHERE template.prompt_template_id = v_template_id
     FOR UPDATE OF template;
    IF NOT FOUND OR NOT v_template.is_active THEN
        RAISE EXCEPTION 'Prompt Template is unavailable';
    END IF;

    SELECT version.*
      INTO v_version
      FROM application.prompt_template_version AS version
     WHERE version.prompt_template_version_id = p_prompt_template_version_id
       AND version.prompt_template_id = v_template_id
     FOR UPDATE OF version;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Prompt Template version is unavailable';
    END IF;

    IF v_template.prompt_template_ownership_scope = 'global' THEN
        SELECT principal.principal_id, principal.is_super_admin
          INTO v_actor
          FROM security.entra_principal_identity AS identity
          JOIN security.principal AS principal
            ON principal.principal_id = identity.principal_id
           AND principal.principal_type = identity.principal_type
         WHERE identity.entra_tenant_id = p_entra_tenant_id
           AND identity.entra_object_id = p_entra_object_id
           AND identity.principal_type = p_expected_principal_type
           AND identity.is_active
           AND principal.is_active
         FOR SHARE OF identity, principal;
        IF NOT FOUND OR NOT v_actor.is_super_admin THEN
            RAISE EXCEPTION 'Global Prompt Template requires Super Admin';
        END IF;
    ELSE
        SELECT *
          INTO v_decision
          FROM security.authorize_tenant_operation(
              p_entra_tenant_id,
              p_entra_object_id,
              p_expected_principal_type,
              v_template.owner_tenant_id,
              'tenant_model_write'
          );
        IF NOT FOUND OR NOT v_decision.authorized THEN
            RAISE EXCEPTION 'Tenant Prompt Template transition denied: %',
                coalesce(v_decision.denial_code, 'authorization_denied');
        END IF;
        v_actor := v_decision;
    END IF;

    IF p_expected_status IS NULL
       OR p_target_status IS NULL
       OR NOT (
        (
            p_expected_status = 'draft'
            AND p_target_status = 'published'
        ) OR (
            p_expected_status = 'published'
            AND p_target_status = 'retired'
        )
    ) THEN
        RAISE EXCEPTION 'Prompt Template version transition conflict';
    END IF;
    IF v_version.prompt_template_version_status = p_target_status THEN
        RETURN NEXT v_version;
        RETURN;
    END IF;
    IF v_version.prompt_template_version_status <> p_expected_status THEN
        RAISE EXCEPTION 'Prompt Template version transition conflict';
    END IF;
    IF p_target_status = 'retired'
       AND EXISTS (
           SELECT 1
             FROM application.prompt_assignment AS assignment
            WHERE assignment.prompt_template_version_id =
                  p_prompt_template_version_id
              AND assignment.is_active
       ) THEN
        RAISE EXCEPTION
            'Prompt Template version has active assignments; clear them first';
    END IF;

    v_transition_time := clock_timestamp();
    IF p_target_status = 'published' THEN
        UPDATE application.prompt_template_version AS version
           SET prompt_template_version_status = 'published',
               published_time = v_transition_time,
               published_by_principal_id = v_actor.principal_id,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_transition_time,
               updated_by = CURRENT_USER
         WHERE version.prompt_template_version_id =
               p_prompt_template_version_id
        RETURNING version.* INTO v_saved;
    ELSE
        UPDATE application.prompt_template_version AS version
           SET prompt_template_version_status = 'retired',
               retired_time = v_transition_time,
               retired_by_principal_id = v_actor.principal_id,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_transition_time,
               updated_by = CURRENT_USER
         WHERE version.prompt_template_version_id =
               p_prompt_template_version_id
        RETURNING version.* INTO v_saved;
    END IF;

    RETURN NEXT v_saved;
END;
$transition_prompt_template_version$;

REVOKE ALL ON FUNCTION application.transition_prompt_template_version(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR
) FROM PUBLIC;

CREATE FUNCTION application.set_prompt_assignment(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_stage_id BIGINT,
    p_prompt_assignment_scope VARCHAR(20),
    p_model_id BIGINT,
    p_prompt_template_version_id BIGINT,
    p_expected_prompt_assignment_id BIGINT
)
RETURNS SETOF application.prompt_assignment
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $set_prompt_assignment$
DECLARE
    v_decision RECORD;
    v_actor RECORD;
    v_model_tenant_id BIGINT;
    v_current application.prompt_assignment%ROWTYPE;
    v_saved application.prompt_assignment%ROWTYPE;
    v_target_template_id BIGINT;
    v_target_template RECORD;
    v_target_version RECORD;
    v_updated_time TIMESTAMPTZ;
BEGIN
    PERFORM 1
      FROM application.workflow_stage AS stage
     WHERE stage.workflow_stage_id = p_workflow_stage_id
       AND stage.workflow_stage_is_agentic
       AND stage.is_active
     FOR SHARE OF stage;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Prompt assignment requires an active agentic Workflow Stage';
    END IF;

    IF p_prompt_assignment_scope = 'global_default' AND p_model_id IS NULL THEN
        SELECT principal.principal_id, principal.is_super_admin
          INTO v_actor
          FROM security.entra_principal_identity AS identity
          JOIN security.principal AS principal
            ON principal.principal_id = identity.principal_id
           AND principal.principal_type = identity.principal_type
         WHERE identity.entra_tenant_id = p_entra_tenant_id
           AND identity.entra_object_id = p_entra_object_id
           AND identity.principal_type = p_expected_principal_type
           AND identity.is_active
           AND principal.is_active
         FOR SHARE OF identity, principal;
        IF NOT FOUND OR NOT v_actor.is_super_admin THEN
            RAISE EXCEPTION 'Global Prompt assignment requires Super Admin';
        END IF;
    ELSIF p_prompt_assignment_scope = 'model_default'
          AND p_model_id IS NOT NULL THEN
        SELECT target_model.tenant_id
          INTO v_model_tenant_id
          FROM model.model AS target_model
         WHERE target_model.model_id = p_model_id
           AND target_model.is_active
         FOR UPDATE OF target_model;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Prompt assignment Model is unavailable';
        END IF;

        SELECT *
          INTO v_decision
          FROM security.authorize_tenant_operation(
              p_entra_tenant_id,
              p_entra_object_id,
              p_expected_principal_type,
              v_model_tenant_id,
              'tenant_model_write'
          );
        IF NOT FOUND OR NOT v_decision.authorized THEN
            RAISE EXCEPTION 'Model Prompt assignment denied: %',
                coalesce(v_decision.denial_code, 'authorization_denied');
        END IF;
        v_actor := v_decision;
    ELSE
        RAISE EXCEPTION 'Prompt assignment scope is invalid';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            concat_ws(
                ':',
                'application.prompt_assignment',
                p_workflow_stage_id::TEXT,
                p_prompt_assignment_scope,
                coalesce(p_model_id::TEXT, 'global')
            ),
            0
        )
    );

    IF p_prompt_template_version_id IS NOT NULL THEN
        SELECT version.prompt_template_id
          INTO v_target_template_id
          FROM application.prompt_template_version AS version
         WHERE version.prompt_template_version_id =
               p_prompt_template_version_id
           AND version.workflow_stage_id = p_workflow_stage_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Prompt assignment requires a published active Prompt';
        END IF;

        SELECT template.prompt_template_ownership_scope,
               template.owner_tenant_id,
               template.is_active
          INTO v_target_template
          FROM application.prompt_template AS template
         WHERE template.prompt_template_id = v_target_template_id
           AND template.workflow_stage_id = p_workflow_stage_id
         FOR UPDATE OF template;
        IF NOT FOUND OR NOT v_target_template.is_active THEN
            RAISE EXCEPTION
                'Prompt assignment requires a published active Prompt';
        END IF;

        SELECT version.prompt_template_version_status
          INTO v_target_version
          FROM application.prompt_template_version AS version
         WHERE version.prompt_template_version_id =
               p_prompt_template_version_id
           AND version.prompt_template_id = v_target_template_id
           AND version.workflow_stage_id = p_workflow_stage_id
         FOR UPDATE OF version;
        IF NOT FOUND
           OR v_target_version.prompt_template_version_status <>
              'published' THEN
            RAISE EXCEPTION
                'Prompt assignment requires a published active Prompt';
        END IF;
        IF p_prompt_assignment_scope = 'global_default'
           AND v_target_template.prompt_template_ownership_scope <>
               'global' THEN
            RAISE EXCEPTION 'Global default requires a global Prompt';
        END IF;
        IF p_prompt_assignment_scope = 'model_default'
           AND v_target_template.prompt_template_ownership_scope = 'tenant'
           AND v_target_template.owner_tenant_id <> v_model_tenant_id THEN
            RAISE EXCEPTION
                'Prompt does not belong to the Model owner Tenant';
        END IF;
    END IF;

    SELECT assignment.*
      INTO v_current
      FROM application.prompt_assignment AS assignment
     WHERE assignment.workflow_stage_id = p_workflow_stage_id
       AND assignment.prompt_assignment_scope = p_prompt_assignment_scope
       AND assignment.model_id IS NOT DISTINCT FROM p_model_id
       AND assignment.is_active
     FOR UPDATE OF assignment;

    IF FOUND
       AND p_prompt_template_version_id IS NOT NULL
       AND v_current.prompt_template_version_id =
           p_prompt_template_version_id THEN
        IF p_expected_prompt_assignment_id IS NOT NULL
           AND p_expected_prompt_assignment_id <>
               v_current.prompt_assignment_id THEN
            RAISE EXCEPTION 'stale_prompt_assignment';
        END IF;
        RETURN NEXT v_current;
        RETURN;
    END IF;
    IF FOUND THEN
        IF p_expected_prompt_assignment_id IS NULL
           OR p_expected_prompt_assignment_id <>
              v_current.prompt_assignment_id THEN
            RAISE EXCEPTION 'stale_prompt_assignment';
        END IF;
    ELSIF p_expected_prompt_assignment_id IS NOT NULL THEN
        RAISE EXCEPTION 'Prompt assignment does not exist';
    END IF;

    v_updated_time := clock_timestamp();
    IF v_current.prompt_assignment_id IS NOT NULL THEN
        UPDATE application.prompt_assignment AS assignment
           SET is_active = FALSE,
               deactivated_by_principal_id = v_actor.principal_id,
               deactivated_time = v_updated_time,
               updated_time = v_updated_time,
               updated_by = CURRENT_USER
         WHERE assignment.prompt_assignment_id =
               v_current.prompt_assignment_id
        RETURNING assignment.* INTO v_saved;
    END IF;

    IF p_prompt_template_version_id IS NULL THEN
        IF v_current.prompt_assignment_id IS NOT NULL THEN
            RETURN NEXT v_saved;
        END IF;
        RETURN;
    END IF;

    INSERT INTO application.prompt_assignment AS assignment (
        workflow_stage_id,
        prompt_template_version_id,
        prompt_assignment_scope,
        model_id,
        assigned_by_principal_id
    ) VALUES (
        p_workflow_stage_id,
        p_prompt_template_version_id,
        p_prompt_assignment_scope,
        p_model_id,
        v_actor.principal_id
    )
    RETURNING assignment.* INTO v_saved;

    RETURN NEXT v_saved;
END;
$set_prompt_assignment$;

REVOKE ALL ON FUNCTION application.set_prompt_assignment(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT
) FROM PUBLIC;

CREATE TABLE application.output_template (
    output_template_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    output_template_code VARCHAR(100) NOT NULL,
    output_template_name VARCHAR(200) NOT NULL,
    output_template_description VARCHAR(2000),
    output_template_target_type VARCHAR(30) NOT NULL,
    output_template_schema_digest CHAR(64) NOT NULL,
    created_by_principal_id BIGINT NOT NULL,
    updated_by_principal_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_output_template_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_output_template_updater FOREIGN KEY (
        updated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT ck_output_template_code CHECK (
        output_template_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_output_template_name CHECK (
        reference.is_nonblank(output_template_name)
    ),
    CONSTRAINT ck_output_template_description CHECK (
        output_template_description IS NULL
        OR reference.is_nonblank(output_template_description)
    ),
    CONSTRAINT ck_output_template_target_type CHECK (
        output_template_target_type IN ('mapping_object', 'mapping_attribute')
    ),
    CONSTRAINT ck_output_template_schema_digest CHECK (
        output_template_schema_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT uq_output_template_id_schema_digest UNIQUE (
        output_template_id,
        output_template_schema_digest
    )
);

CREATE UNIQUE INDEX ux_output_template_code
    ON application.output_template (lower(output_template_code));

CREATE FUNCTION application.guard_output_template_schema()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_output_template_schema$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'output templates cannot be deleted';
    END IF;

    IF ROW(
        NEW.output_template_id,
        NEW.output_template_code,
        NEW.output_template_target_type,
        NEW.output_template_schema_digest,
        NEW.created_by_principal_id,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.output_template_id,
        OLD.output_template_code,
        OLD.output_template_target_type,
        OLD.output_template_schema_digest,
        OLD.created_by_principal_id,
        OLD.created_time,
        OLD.created_by
    ) THEN
        RAISE EXCEPTION 'output template schema is immutable';
    END IF;

    RETURN NEW;
END;
$guard_output_template_schema$;

CREATE TRIGGER guard_output_template_schema
BEFORE UPDATE OR DELETE ON application.output_template
FOR EACH ROW EXECUTE FUNCTION application.guard_output_template_schema();

CREATE TABLE application.output_template_field (
    output_template_field_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    output_template_id BIGINT NOT NULL,
    output_template_field_name VARCHAR(100) NOT NULL,
    output_template_field_description VARCHAR(2000) NOT NULL,
    output_template_field_data_type VARCHAR(30) NOT NULL,
    output_template_field_array_item_type VARCHAR(30),
    output_template_field_example JSONB,
    output_template_field_is_required BOOLEAN NOT NULL DEFAULT TRUE,
    output_template_field_order INTEGER NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_output_template_field_template FOREIGN KEY (
        output_template_id
    ) REFERENCES application.output_template (output_template_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_output_template_field_name UNIQUE (
        output_template_id,
        output_template_field_name
    ),
    CONSTRAINT uq_output_template_field_order UNIQUE (
        output_template_id,
        output_template_field_order
    ),
    CONSTRAINT ck_output_template_field_name CHECK (
        output_template_field_name ~ '^[a-z][a-z0-9_]{0,99}$'
    ),
    CONSTRAINT ck_output_template_field_description CHECK (
        reference.is_nonblank(output_template_field_description)
    ),
    CONSTRAINT ck_output_template_field_data_type CHECK (
        output_template_field_data_type IN (
            'string', 'integer', 'number', 'boolean', 'object', 'array'
        )
    ),
    CONSTRAINT ck_output_template_field_array_item CHECK (
        (
            output_template_field_data_type = 'array'
            AND output_template_field_array_item_type IN (
                'string', 'integer', 'number', 'boolean', 'object'
            )
        ) OR (
            output_template_field_data_type <> 'array'
            AND output_template_field_array_item_type IS NULL
        )
    ),
    CONSTRAINT ck_output_template_field_example CHECK (
        output_template_field_example IS NULL
        OR octet_length(output_template_field_example::TEXT) <= 4096
    ),
    CONSTRAINT ck_output_template_field_order CHECK (
        output_template_field_order > 0
    )
);

CREATE FUNCTION application.guard_output_template_field()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_output_template_field$
DECLARE
    v_template_created_time TIMESTAMPTZ;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT template.created_time
          INTO v_template_created_time
          FROM application.output_template AS template
         WHERE template.output_template_id = NEW.output_template_id;

        IF NOT FOUND OR v_template_created_time IS DISTINCT FROM CURRENT_TIMESTAMP THEN
            RAISE EXCEPTION
                'output template fields must be created atomically with the template';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'output template fields cannot be deleted';
    END IF;

    RAISE EXCEPTION 'output template fields are immutable';
END;
$guard_output_template_field$;

CREATE TRIGGER guard_output_template_field
BEFORE INSERT OR UPDATE OR DELETE ON application.output_template_field
FOR EACH ROW EXECUTE FUNCTION application.guard_output_template_field();

ALTER TABLE workflow.mapping_object
    ADD CONSTRAINT fk_mapping_object_output_template
    FOREIGN KEY (output_template_id)
    REFERENCES application.output_template (output_template_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_mapping_object_output_template
    ON workflow.mapping_object (output_template_id)
    WHERE output_template_id IS NOT NULL;

ALTER TABLE workflow.mapping_attribute
    ADD CONSTRAINT fk_mapping_attribute_output_template
    FOREIGN KEY (output_template_id)
    REFERENCES application.output_template (output_template_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_mapping_attribute_output_template
    ON workflow.mapping_attribute (output_template_id)
    WHERE output_template_id IS NOT NULL;

CREATE FUNCTION application.validate_mapping_output_template()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $validate_mapping_output_template$
DECLARE
    v_expected_target_type VARCHAR(30);
    v_actual_target_type VARCHAR(30);
    v_template_active BOOLEAN;
    v_template_has_fields BOOLEAN;
    v_document JSONB;
    v_field RECORD;
    v_value JSONB;
    v_type_matches BOOLEAN;
    v_undeclared_field TEXT;
BEGIN
    IF NEW.output_template_id IS NULL THEN
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'mapping_object' THEN
        v_expected_target_type := 'mapping_object';
        v_document := to_jsonb(NEW) ->
            'object_mapping_transformation_document';
    ELSIF TG_TABLE_NAME = 'mapping_attribute' THEN
        v_expected_target_type := 'mapping_attribute';
        v_document := to_jsonb(NEW) ->
            'attribute_mapping_transformation_document';
    ELSE
        v_expected_target_type := NULL;
    END IF;
    IF v_expected_target_type IS NULL THEN
        RAISE EXCEPTION 'unsupported Mapping output-template target';
    END IF;

    SELECT template.output_template_target_type,
           template.is_active,
           EXISTS (
               SELECT 1
                 FROM application.output_template_field AS field
                WHERE field.output_template_id = template.output_template_id
           )
      INTO v_actual_target_type,
           v_template_active,
           v_template_has_fields
      FROM application.output_template AS template
     WHERE template.output_template_id = NEW.output_template_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Mapping output template is unavailable';
    END IF;
    IF v_actual_target_type <> v_expected_target_type THEN
        RAISE EXCEPTION
            'Mapping output template requires % target type',
            v_expected_target_type;
    END IF;
    IF NOT v_template_active OR NOT v_template_has_fields THEN
        RAISE EXCEPTION 'Mapping output template is not usable';
    END IF;
    IF v_document IS NULL OR jsonb_typeof(v_document) <> 'object' THEN
        RAISE EXCEPTION 'Mapping output-template document is required';
    END IF;
    IF jsonb_typeof(v_document -> 'schema_version') IS DISTINCT FROM 'string'
       OR v_document ->> 'schema_version' IS DISTINCT FROM '1.0' THEN
        RAISE EXCEPTION
            'Mapping output-template schema_version must be 1.0';
    END IF;
    IF jsonb_typeof(v_document -> 'transformation_kind') IS DISTINCT FROM
       'string' OR (
        v_expected_target_type = 'mapping_object'
        AND v_document ->> 'transformation_kind' NOT IN (
            'direct', 'derived'
        )
    ) OR (
        v_expected_target_type = 'mapping_attribute'
        AND v_document ->> 'transformation_kind' NOT IN (
            'direct', 'expression'
        )
    ) OR v_document ->> 'transformation_kind' IS NULL THEN
        RAISE EXCEPTION
            'Mapping output-template transformation_kind is invalid';
    END IF;

    FOR v_field IN
        SELECT field.output_template_field_name,
               field.output_template_field_data_type,
               field.output_template_field_array_item_type,
               field.output_template_field_is_required
          FROM application.output_template_field AS field
         WHERE field.output_template_id = NEW.output_template_id
         ORDER BY field.output_template_field_order
    LOOP
        IF v_field.output_template_field_is_required
           AND NOT v_document ? v_field.output_template_field_name THEN
            RAISE EXCEPTION 'Mapping output-template field % is required',
                v_field.output_template_field_name;
        END IF;

        IF v_document ? v_field.output_template_field_name THEN
            v_value := v_document -> v_field.output_template_field_name;
            v_type_matches := CASE v_field.output_template_field_data_type
                WHEN 'string' THEN jsonb_typeof(v_value) = 'string'
                WHEN 'integer' THEN
                    CASE
                        WHEN jsonb_typeof(v_value) = 'number' THEN
                            (v_value #>> '{}')::NUMERIC =
                                trunc((v_value #>> '{}')::NUMERIC)
                        ELSE FALSE
                    END
                WHEN 'number' THEN jsonb_typeof(v_value) = 'number'
                WHEN 'boolean' THEN jsonb_typeof(v_value) = 'boolean'
                WHEN 'object' THEN jsonb_typeof(v_value) = 'object'
                WHEN 'array' THEN jsonb_typeof(v_value) = 'array'
                ELSE FALSE
            END;

            IF v_type_matches
               AND v_field.output_template_field_data_type = 'array' THEN
                SELECT NOT EXISTS (
                           SELECT 1
                             FROM jsonb_array_elements(v_value) AS item(value)
                            WHERE NOT CASE
                                v_field.output_template_field_array_item_type
                                WHEN 'string' THEN
                                    jsonb_typeof(item.value) = 'string'
                                WHEN 'integer' THEN
                                    CASE
                                        WHEN jsonb_typeof(item.value) =
                                             'number' THEN
                                            (item.value #>> '{}')::NUMERIC =
                                                trunc(
                                                    (item.value #>> '{}')::NUMERIC
                                                )
                                        ELSE FALSE
                                    END
                                WHEN 'number' THEN
                                    jsonb_typeof(item.value) = 'number'
                                WHEN 'boolean' THEN
                                    jsonb_typeof(item.value) = 'boolean'
                                WHEN 'object' THEN
                                    jsonb_typeof(item.value) = 'object'
                                ELSE FALSE
                            END
                       )
                  INTO v_type_matches;
            END IF;

            IF NOT v_type_matches THEN
                RAISE EXCEPTION
                    'Mapping output-template field % must be %',
                    v_field.output_template_field_name,
                    CASE
                        WHEN v_field.output_template_field_data_type = 'array'
                        THEN 'array of ' ||
                            v_field.output_template_field_array_item_type
                        ELSE v_field.output_template_field_data_type
                    END;
            END IF;
        END IF;
    END LOOP;

    SELECT document_key.value
      INTO v_undeclared_field
      FROM jsonb_object_keys(v_document) AS document_key(value)
     WHERE document_key.value NOT IN (
               'schema_version', 'transformation_kind'
           )
       AND NOT EXISTS (
           SELECT 1
             FROM application.output_template_field AS field
            WHERE field.output_template_id = NEW.output_template_id
              AND field.output_template_field_name = document_key.value
       )
     ORDER BY document_key.value
     LIMIT 1;
    IF v_undeclared_field IS NOT NULL THEN
        RAISE EXCEPTION 'Mapping document contains undeclared field %',
            v_undeclared_field;
    END IF;

    RETURN NEW;
END;
$validate_mapping_output_template$;

REVOKE ALL ON FUNCTION application.validate_mapping_output_template()
FROM PUBLIC;

CREATE TRIGGER validate_mapping_object_output_template
BEFORE INSERT OR UPDATE OF
    output_template_id,
    object_mapping_transformation_document
ON workflow.mapping_object
FOR EACH ROW EXECUTE FUNCTION application.validate_mapping_output_template();

CREATE TRIGGER validate_mapping_attribute_output_template
BEFORE INSERT OR UPDATE OF
    output_template_id,
    attribute_mapping_transformation_document
ON workflow.mapping_attribute
FOR EACH ROW EXECUTE FUNCTION application.validate_mapping_output_template();

CREATE FUNCTION application.create_output_template(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_output_template_code VARCHAR(100),
    p_output_template_name VARCHAR(200),
    p_output_template_description VARCHAR(2000),
    p_output_template_target_type VARCHAR(30),
    p_fields JSONB
)
RETURNS SETOF application.output_template
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $create_output_template$
DECLARE
    v_actor RECORD;
    v_field JSONB;
    v_field_name TEXT;
    v_field_description TEXT;
    v_field_data_type TEXT;
    v_field_array_item_type TEXT;
    v_field_example JSONB;
    v_field_is_required BOOLEAN;
    v_field_order INTEGER;
    v_normalized_fields JSONB;
    v_schema_digest CHAR(64);
    v_existing application.output_template%ROWTYPE;
    v_created application.output_template%ROWTYPE;
BEGIN
    SELECT principal.principal_id, principal.is_super_admin
      INTO v_actor
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
     WHERE identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.is_active
       AND principal.is_active
     FOR SHARE OF identity, principal;
    IF NOT FOUND OR NOT v_actor.is_super_admin THEN
        RAISE EXCEPTION 'Output Template creation authorization denied';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            concat_ws(
                ':',
                'application.output_template',
                lower(p_output_template_code)
            ),
            0
        )
    );

    IF p_fields IS NULL
       OR jsonb_typeof(p_fields) <> 'array'
       OR jsonb_array_length(p_fields) = 0
       OR jsonb_array_length(p_fields) > 500
       OR octet_length(p_fields::TEXT) > 262144 THEN
        RAISE EXCEPTION 'Output Template fields must be a bounded nonempty array';
    END IF;

    FOR v_field IN SELECT item.value FROM jsonb_array_elements(p_fields) AS item(value)
    LOOP
        IF jsonb_typeof(v_field) <> 'object'
           OR EXISTS (
               SELECT 1
                 FROM jsonb_object_keys(v_field) AS field_key(value)
                WHERE field_key.value NOT IN (
                          'output_template_field_name',
                          'output_template_field_description',
                          'output_template_field_data_type',
                          'output_template_field_array_item_type',
                          'output_template_field_example',
                          'output_template_field_is_required',
                          'output_template_field_order'
                      )
           ) THEN
            RAISE EXCEPTION 'Output Template field structure is invalid';
        END IF;

        v_field_name := v_field ->> 'output_template_field_name';
        v_field_description :=
            v_field ->> 'output_template_field_description';
        v_field_data_type := v_field ->> 'output_template_field_data_type';
        v_field_array_item_type :=
            v_field ->> 'output_template_field_array_item_type';
        v_field_example := NULLIF(
            v_field -> 'output_template_field_example',
            'null'::JSONB
        );
        v_field_is_required := CASE
            WHEN NOT v_field ? 'output_template_field_is_required' THEN TRUE
            WHEN jsonb_typeof(
                v_field -> 'output_template_field_is_required'
            ) = 'boolean' THEN
                (v_field ->> 'output_template_field_is_required')::BOOLEAN
            ELSE NULL
        END;
        v_field_order := CASE
            WHEN jsonb_typeof(
                v_field -> 'output_template_field_order'
            ) = 'number'
             AND v_field ->> 'output_template_field_order' ~
                 '^[1-9][0-9]*$'
                THEN (v_field ->> 'output_template_field_order')::INTEGER
            ELSE NULL
        END;

        IF v_field_name IN ('schema_version', 'transformation_kind') THEN
            RAISE EXCEPTION 'Output Template field name is reserved';
        END IF;
        IF v_field_data_type IS NULL
           OR v_field_data_type NOT IN (
               'string', 'integer', 'number', 'boolean', 'object', 'array'
           ) THEN
            RAISE EXCEPTION 'Output Template field data type is invalid';
        END IF;
        IF (
            v_field_data_type = 'array'
            AND (
                v_field_array_item_type IS NULL
                OR v_field_array_item_type NOT IN (
                    'string', 'integer', 'number', 'boolean', 'object'
                )
            )
        ) OR (
            v_field_data_type <> 'array'
            AND v_field_array_item_type IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'Output Template field array definition is invalid';
        END IF;

        IF jsonb_typeof(
               v_field -> 'output_template_field_name'
           ) <> 'string'
           OR jsonb_typeof(
               v_field -> 'output_template_field_description'
           ) <> 'string'
           OR jsonb_typeof(
               v_field -> 'output_template_field_data_type'
           ) <> 'string'
           OR (
               v_field ? 'output_template_field_array_item_type'
               AND v_field -> 'output_template_field_array_item_type' <>
                   'null'::JSONB
               AND jsonb_typeof(
                   v_field -> 'output_template_field_array_item_type'
               ) <> 'string'
           )
           OR v_field_name IS NULL
           OR v_field_name !~ '^[a-z][a-z0-9_]{0,99}$'
           OR NOT reference.is_nonblank(v_field_description)
           OR v_field_is_required IS NULL
           OR v_field_order IS NULL
           OR (
               v_field_example IS NOT NULL
               AND octet_length(v_field_example::TEXT) > 4096
           ) THEN
            RAISE EXCEPTION 'Output Template field definition is invalid';
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_fields) WITH ORDINALITY
                   AS left_field(value, position)
          JOIN jsonb_array_elements(p_fields) WITH ORDINALITY
                   AS right_field(value, position)
            ON left_field.position < right_field.position
           AND (
               left_field.value ->> 'output_template_field_name' =
                   right_field.value ->> 'output_template_field_name'
               OR left_field.value ->> 'output_template_field_order' =
                   right_field.value ->> 'output_template_field_order'
           )
    ) THEN
        RAISE EXCEPTION 'Output Template contains a duplicate field name or order';
    END IF;

    SELECT jsonb_agg(
               jsonb_build_object(
                   'output_template_field_name',
                       field.value ->> 'output_template_field_name',
                   'output_template_field_description',
                       field.value ->> 'output_template_field_description',
                   'output_template_field_data_type',
                       field.value ->> 'output_template_field_data_type',
                   'output_template_field_array_item_type',
                       field.value ->> 'output_template_field_array_item_type',
                   'output_template_field_example',
                       coalesce(
                           field.value -> 'output_template_field_example',
                           'null'::JSONB
                       ),
                   'output_template_field_is_required',
                       CASE
                           WHEN field.value ?
                                'output_template_field_is_required'
                               THEN (
                                   field.value ->>
                                   'output_template_field_is_required'
                               )::BOOLEAN
                           ELSE TRUE
                       END,
                   'output_template_field_order',
                       (
                           field.value ->>
                           'output_template_field_order'
                       )::INTEGER
               )
               ORDER BY (
                   field.value ->> 'output_template_field_order'
               )::INTEGER
           )
      INTO v_normalized_fields
      FROM jsonb_array_elements(p_fields) AS field(value);
    v_schema_digest := encode(
        sha256(
            convert_to(
                jsonb_build_object(
                    'output_template_target_type',
                        p_output_template_target_type,
                    'fields', v_normalized_fields
                )::TEXT,
                'UTF8'
            )
        ),
        'hex'
    );

    SELECT template.*
      INTO v_existing
      FROM application.output_template AS template
     WHERE lower(template.output_template_code) =
           lower(p_output_template_code)
     FOR UPDATE OF template;
    IF FOUND THEN
        IF ROW(
            v_existing.output_template_code,
            v_existing.output_template_name,
            v_existing.output_template_description,
            v_existing.output_template_target_type,
            v_existing.output_template_schema_digest,
            v_existing.is_active
        ) IS DISTINCT FROM ROW(
            p_output_template_code,
            p_output_template_name,
            p_output_template_description,
            p_output_template_target_type,
            v_schema_digest,
            TRUE
        ) THEN
            RAISE EXCEPTION 'Output Template code conflict';
        END IF;
        RETURN NEXT v_existing;
        RETURN;
    END IF;

    INSERT INTO application.output_template AS template (
        output_template_code,
        output_template_name,
        output_template_description,
        output_template_target_type,
        output_template_schema_digest,
        created_by_principal_id,
        updated_by_principal_id
    ) VALUES (
        p_output_template_code,
        p_output_template_name,
        p_output_template_description,
        p_output_template_target_type,
        v_schema_digest,
        v_actor.principal_id,
        v_actor.principal_id
    )
    RETURNING template.* INTO v_created;

    FOR v_field IN SELECT item.value FROM jsonb_array_elements(v_normalized_fields) AS item(value)
    LOOP
        INSERT INTO application.output_template_field (
            output_template_id,
            output_template_field_name,
            output_template_field_description,
            output_template_field_data_type,
            output_template_field_array_item_type,
            output_template_field_example,
            output_template_field_is_required,
            output_template_field_order
        ) VALUES (
            v_created.output_template_id,
            v_field ->> 'output_template_field_name',
            v_field ->> 'output_template_field_description',
            v_field ->> 'output_template_field_data_type',
            v_field ->> 'output_template_field_array_item_type',
            NULLIF(
                v_field -> 'output_template_field_example',
                'null'::JSONB
            ),
            (v_field ->> 'output_template_field_is_required')::BOOLEAN,
            (v_field ->> 'output_template_field_order')::INTEGER
        );
    END LOOP;

    RETURN NEXT v_created;
END;
$create_output_template$;

REVOKE ALL ON FUNCTION application.create_output_template(
    UUID,
    UUID,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    JSONB
) FROM PUBLIC;

CREATE FUNCTION application.update_output_template(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_output_template_id BIGINT,
    p_output_template_name VARCHAR(200),
    p_output_template_description VARCHAR(2000),
    p_is_active BOOLEAN,
    p_expected_updated_time TIMESTAMPTZ
)
RETURNS SETOF application.output_template
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $update_output_template$
DECLARE
    v_actor RECORD;
    v_existing application.output_template%ROWTYPE;
    v_saved application.output_template%ROWTYPE;
    v_updated_time TIMESTAMPTZ;
BEGIN
    SELECT principal.principal_id, principal.is_super_admin
      INTO v_actor
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
     WHERE identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.is_active
       AND principal.is_active
     FOR SHARE OF identity, principal;
    IF NOT FOUND OR NOT v_actor.is_super_admin THEN
        RAISE EXCEPTION 'Output Template update authorization denied';
    END IF;

    SELECT template.*
      INTO v_existing
      FROM application.output_template AS template
     WHERE template.output_template_id = p_output_template_id
     FOR UPDATE OF template;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Output Template is unavailable';
    END IF;
    IF ROW(
        v_existing.output_template_name,
        v_existing.output_template_description,
        v_existing.is_active
    ) IS NOT DISTINCT FROM ROW(
        p_output_template_name,
        p_output_template_description,
        p_is_active
    ) THEN
        RETURN NEXT v_existing;
        RETURN;
    END IF;
    IF p_expected_updated_time IS NULL
       OR v_existing.updated_time <> p_expected_updated_time THEN
        RAISE EXCEPTION 'stale_output_template';
    END IF;

    v_updated_time := clock_timestamp();
    UPDATE application.output_template AS template
       SET output_template_name = p_output_template_name,
           output_template_description = p_output_template_description,
           updated_by_principal_id = v_actor.principal_id,
           is_active = p_is_active,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE template.output_template_id = p_output_template_id
    RETURNING template.* INTO v_saved;

    RETURN NEXT v_saved;
END;
$update_output_template$;

REVOKE ALL ON FUNCTION application.update_output_template(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR,
    BOOLEAN,
    TIMESTAMPTZ
) FROM PUBLIC;

CREATE TABLE application.sql_generation_guide (
    sql_generation_guide_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sql_generation_guide_code VARCHAR(100) NOT NULL,
    sql_generation_guide_name VARCHAR(200) NOT NULL,
    sql_generation_guide_description VARCHAR(2000),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_principal_id BIGINT NOT NULL,
    updated_by_principal_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_sql_generation_guide_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_sql_generation_guide_updater FOREIGN KEY (
        updated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT ck_sql_generation_guide_code CHECK (
        sql_generation_guide_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_sql_generation_guide_name CHECK (
        reference.is_nonblank(sql_generation_guide_name)
    ),
    CONSTRAINT ck_sql_generation_guide_description CHECK (
        sql_generation_guide_description IS NULL
        OR reference.is_nonblank(sql_generation_guide_description)
    ),
    CONSTRAINT ck_sql_generation_guide_default_active CHECK (
        NOT is_default OR is_active
    )
);

CREATE UNIQUE INDEX ux_sql_generation_guide_code
    ON application.sql_generation_guide (
        lower(sql_generation_guide_code)
    );
CREATE UNIQUE INDEX ux_sql_generation_guide_default
    ON application.sql_generation_guide ((1))
    WHERE is_default AND is_active;

CREATE FUNCTION application.guard_sql_generation_guide()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_sql_generation_guide$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'SQL generation guides cannot be deleted';
    END IF;

    IF ROW(
        NEW.sql_generation_guide_id,
        NEW.sql_generation_guide_code,
        NEW.created_by_principal_id,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.sql_generation_guide_id,
        OLD.sql_generation_guide_code,
        OLD.created_by_principal_id,
        OLD.created_time,
        OLD.created_by
    ) THEN
        RAISE EXCEPTION 'SQL generation guide identity is immutable';
    END IF;

    RETURN NEW;
END;
$guard_sql_generation_guide$;

CREATE TRIGGER guard_sql_generation_guide
BEFORE UPDATE OR DELETE ON application.sql_generation_guide
FOR EACH ROW EXECUTE FUNCTION application.guard_sql_generation_guide();

CREATE TABLE application.sql_generation_guide_version (
    sql_generation_guide_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sql_generation_guide_id BIGINT NOT NULL,
    sql_generation_guide_version_number INTEGER NOT NULL,
    sql_generation_guide_content TEXT NOT NULL,
    sql_generation_guide_digest CHAR(64) NOT NULL,
    sql_generation_guide_version_status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_by_principal_id BIGINT NOT NULL,
    updated_by_principal_id BIGINT NOT NULL,
    published_time TIMESTAMPTZ,
    published_by_principal_id BIGINT,
    retired_time TIMESTAMPTZ,
    retired_by_principal_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_sql_generation_guide_version_guide FOREIGN KEY (
        sql_generation_guide_id
    ) REFERENCES application.sql_generation_guide (sql_generation_guide_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_sql_generation_guide_version_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_sql_generation_guide_version_updater FOREIGN KEY (
        updated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_sql_generation_guide_version_publisher FOREIGN KEY (
        published_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_sql_generation_guide_version_retirer FOREIGN KEY (
        retired_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_sql_generation_guide_version UNIQUE (
        sql_generation_guide_id,
        sql_generation_guide_version_number
    ),
    CONSTRAINT uq_sql_generation_guide_version_witness UNIQUE (
        sql_generation_guide_version_id,
        sql_generation_guide_id
    ),
    CONSTRAINT uq_sql_generation_guide_version_digest_witness UNIQUE (
        sql_generation_guide_version_id,
        sql_generation_guide_id,
        sql_generation_guide_digest
    ),
    CONSTRAINT ck_sql_generation_guide_version_number CHECK (
        sql_generation_guide_version_number > 0
    ),
    CONSTRAINT ck_sql_generation_guide_content CHECK (
        reference.is_nonblank(sql_generation_guide_content)
        AND octet_length(sql_generation_guide_content) <= 262144
    ),
    CONSTRAINT ck_sql_generation_guide_digest CHECK (
        sql_generation_guide_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_sql_generation_guide_version_lifecycle CHECK (
        (
            sql_generation_guide_version_status = 'draft'
            AND published_time IS NULL
            AND published_by_principal_id IS NULL
            AND retired_time IS NULL
            AND retired_by_principal_id IS NULL
        ) OR (
            sql_generation_guide_version_status = 'published'
            AND published_time IS NOT NULL
            AND published_by_principal_id IS NOT NULL
            AND updated_by_principal_id = published_by_principal_id
            AND retired_time IS NULL
            AND retired_by_principal_id IS NULL
        ) OR (
            sql_generation_guide_version_status = 'retired'
            AND published_time IS NOT NULL
            AND published_by_principal_id IS NOT NULL
            AND retired_time IS NOT NULL
            AND retired_by_principal_id IS NOT NULL
            AND updated_by_principal_id = retired_by_principal_id
            AND retired_time >= published_time
        )
    )
);

CREATE INDEX ix_sql_generation_guide_version_lookup
    ON application.sql_generation_guide_version (
        sql_generation_guide_id,
        sql_generation_guide_version_status,
        sql_generation_guide_version_number DESC
    );
CREATE UNIQUE INDEX ux_sql_generation_guide_version_one_draft
    ON application.sql_generation_guide_version (
        sql_generation_guide_id
    )
    WHERE sql_generation_guide_version_status = 'draft';

CREATE FUNCTION application.guard_sql_generation_guide_version()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_sql_generation_guide_version$
DECLARE
    v_expected_digest CHAR(64);
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'SQL generation guide versions cannot be deleted';
    END IF;

    v_expected_digest := encode(
        sha256(
            convert_to(NEW.sql_generation_guide_content, 'UTF8')
        ),
        'hex'
    );
    IF TG_OP = 'INSERT'
       AND NEW.sql_generation_guide_digest IS DISTINCT FROM v_expected_digest THEN
        RAISE EXCEPTION
            'SQL generation guide digest does not match content';
    END IF;

    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF ROW(
        NEW.sql_generation_guide_version_id,
        NEW.sql_generation_guide_id,
        NEW.sql_generation_guide_version_number,
        NEW.created_by_principal_id,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.sql_generation_guide_version_id,
        OLD.sql_generation_guide_id,
        OLD.sql_generation_guide_version_number,
        OLD.created_by_principal_id,
        OLD.created_time,
        OLD.created_by
    ) THEN
        RAISE EXCEPTION 'SQL generation guide version identity is immutable';
    END IF;

    IF OLD.sql_generation_guide_version_status = 'retired' THEN
        RAISE EXCEPTION 'retired SQL generation guide version is immutable';
    END IF;

    IF OLD.sql_generation_guide_version_status = 'published' THEN
        IF NEW.sql_generation_guide_version_status <> 'retired'
           OR ROW(
               NEW.sql_generation_guide_content,
               NEW.sql_generation_guide_digest,
               NEW.published_time,
               NEW.published_by_principal_id
           ) IS DISTINCT FROM ROW(
               OLD.sql_generation_guide_content,
               OLD.sql_generation_guide_digest,
               OLD.published_time,
               OLD.published_by_principal_id
           ) THEN
            RAISE EXCEPTION
                'published SQL generation guide version is immutable';
        END IF;
    ELSIF NEW.sql_generation_guide_version_status NOT IN ('draft', 'published') THEN
        RAISE EXCEPTION
            'draft SQL generation guide version can only be published';
    END IF;

    IF NEW.sql_generation_guide_digest IS DISTINCT FROM v_expected_digest THEN
        RAISE EXCEPTION
            'SQL generation guide digest does not match content';
    END IF;

    RETURN NEW;
END;
$guard_sql_generation_guide_version$;

CREATE TRIGGER guard_sql_generation_guide_version
BEFORE INSERT OR UPDATE OR DELETE ON application.sql_generation_guide_version
FOR EACH ROW EXECUTE FUNCTION application.guard_sql_generation_guide_version();

CREATE FUNCTION application.save_sql_generation_guide(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_sql_generation_guide_id BIGINT,
    p_sql_generation_guide_code VARCHAR(100),
    p_sql_generation_guide_name VARCHAR(200),
    p_sql_generation_guide_description VARCHAR(2000),
    p_is_default BOOLEAN,
    p_is_active BOOLEAN,
    p_expected_updated_time TIMESTAMPTZ
)
RETURNS SETOF application.sql_generation_guide
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $save_sql_generation_guide$
DECLARE
    v_actor RECORD;
    v_existing application.sql_generation_guide%ROWTYPE;
    v_saved application.sql_generation_guide%ROWTYPE;
    v_updated_time TIMESTAMPTZ;
BEGIN
    SELECT principal.principal_id, principal.is_super_admin
      INTO v_actor
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
     WHERE identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.is_active
       AND principal.is_active
     FOR SHARE OF identity, principal;
    IF NOT FOUND OR NOT v_actor.is_super_admin THEN
        RAISE EXCEPTION 'SQL generation guide requires Super Admin';
    END IF;
    IF p_is_default AND NOT p_is_active THEN
        RAISE EXCEPTION 'default SQL generation guide must be active';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'application.sql_generation_guide.default',
            0
        )
    );

    IF p_sql_generation_guide_id IS NULL THEN
        SELECT guide.*
          INTO v_existing
          FROM application.sql_generation_guide AS guide
         WHERE lower(guide.sql_generation_guide_code) =
               lower(p_sql_generation_guide_code)
         FOR UPDATE OF guide;
        IF FOUND THEN
            IF ROW(
                v_existing.sql_generation_guide_name,
                v_existing.sql_generation_guide_description,
                v_existing.is_default,
                v_existing.is_active
            ) IS DISTINCT FROM ROW(
                p_sql_generation_guide_name,
                p_sql_generation_guide_description,
                p_is_default,
                p_is_active
            ) THEN
                RAISE EXCEPTION 'SQL generation guide code conflict';
            END IF;
            RETURN NEXT v_existing;
            RETURN;
        END IF;

        v_updated_time := clock_timestamp();
        IF p_is_default THEN
            UPDATE application.sql_generation_guide AS guide
               SET is_default = FALSE,
                   updated_by_principal_id = v_actor.principal_id,
                   updated_time = v_updated_time,
                   updated_by = CURRENT_USER
             WHERE guide.is_default
               AND guide.is_active;
        END IF;

        INSERT INTO application.sql_generation_guide AS guide (
            sql_generation_guide_code,
            sql_generation_guide_name,
            sql_generation_guide_description,
            is_default,
            created_by_principal_id,
            updated_by_principal_id,
            is_active,
            updated_time
        ) VALUES (
            p_sql_generation_guide_code,
            p_sql_generation_guide_name,
            p_sql_generation_guide_description,
            p_is_default,
            v_actor.principal_id,
            v_actor.principal_id,
            p_is_active,
            v_updated_time
        )
        RETURNING guide.* INTO v_saved;
        RETURN NEXT v_saved;
        RETURN;
    END IF;

    SELECT guide.*
      INTO v_existing
      FROM application.sql_generation_guide AS guide
     WHERE guide.sql_generation_guide_id = p_sql_generation_guide_id
     FOR UPDATE OF guide;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SQL generation guide is unavailable';
    END IF;
    IF v_existing.sql_generation_guide_code <>
       p_sql_generation_guide_code THEN
        RAISE EXCEPTION 'SQL generation guide identity is immutable';
    END IF;
    IF ROW(
        v_existing.sql_generation_guide_name,
        v_existing.sql_generation_guide_description,
        v_existing.is_default,
        v_existing.is_active
    ) IS NOT DISTINCT FROM ROW(
        p_sql_generation_guide_name,
        p_sql_generation_guide_description,
        p_is_default,
        p_is_active
    ) THEN
        RETURN NEXT v_existing;
        RETURN;
    END IF;
    IF p_expected_updated_time IS NULL
       OR v_existing.updated_time <> p_expected_updated_time THEN
        RAISE EXCEPTION 'stale_sql_generation_guide';
    END IF;

    v_updated_time := clock_timestamp();
    IF p_is_default THEN
        UPDATE application.sql_generation_guide AS guide
           SET is_default = FALSE,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_updated_time,
               updated_by = CURRENT_USER
         WHERE guide.sql_generation_guide_id <>
               p_sql_generation_guide_id
           AND guide.is_default
           AND guide.is_active;
    END IF;

    UPDATE application.sql_generation_guide AS guide
       SET sql_generation_guide_name = p_sql_generation_guide_name,
           sql_generation_guide_description =
               p_sql_generation_guide_description,
           is_default = p_is_default,
           updated_by_principal_id = v_actor.principal_id,
           is_active = p_is_active,
           updated_time = v_updated_time,
           updated_by = CURRENT_USER
     WHERE guide.sql_generation_guide_id = p_sql_generation_guide_id
    RETURNING guide.* INTO v_saved;

    RETURN NEXT v_saved;
END;
$save_sql_generation_guide$;

REVOKE ALL ON FUNCTION application.save_sql_generation_guide(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    BOOLEAN,
    BOOLEAN,
    TIMESTAMPTZ
) FROM PUBLIC;

CREATE FUNCTION application.save_sql_generation_guide_draft(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_sql_generation_guide_id BIGINT,
    p_expected_sql_generation_guide_version_id BIGINT,
    p_sql_generation_guide_content TEXT,
    p_expected_updated_time TIMESTAMPTZ
)
RETURNS SETOF application.sql_generation_guide_version
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $save_sql_generation_guide_draft$
DECLARE
    v_actor RECORD;
    v_guide application.sql_generation_guide%ROWTYPE;
    v_draft application.sql_generation_guide_version%ROWTYPE;
    v_saved application.sql_generation_guide_version%ROWTYPE;
    v_digest CHAR(64);
    v_version_number INTEGER;
    v_updated_time TIMESTAMPTZ;
BEGIN
    IF p_sql_generation_guide_content IS NULL
       OR btrim(p_sql_generation_guide_content) = ''
       OR octet_length(p_sql_generation_guide_content) > 262144 THEN
        RAISE EXCEPTION 'SQL generation guide content is invalid';
    END IF;

    SELECT principal.principal_id, principal.is_super_admin
      INTO v_actor
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
     WHERE identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.is_active
       AND principal.is_active
     FOR SHARE OF identity, principal;
    IF NOT FOUND OR NOT v_actor.is_super_admin THEN
        RAISE EXCEPTION 'SQL generation guide requires Super Admin';
    END IF;

    SELECT guide.*
      INTO v_guide
      FROM application.sql_generation_guide AS guide
     WHERE guide.sql_generation_guide_id = p_sql_generation_guide_id
       AND guide.is_active
     FOR UPDATE OF guide;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SQL generation guide is unavailable for draft authoring';
    END IF;

    v_digest := encode(
        sha256(convert_to(p_sql_generation_guide_content, 'UTF8')),
        'hex'
    );

    SELECT version.*
      INTO v_draft
      FROM application.sql_generation_guide_version AS version
     WHERE version.sql_generation_guide_id = p_sql_generation_guide_id
       AND version.sql_generation_guide_version_status = 'draft'
     FOR UPDATE OF version;
    IF FOUND THEN
        IF v_draft.sql_generation_guide_digest = v_digest THEN
            RETURN NEXT v_draft;
            RETURN;
        END IF;
        IF p_expected_sql_generation_guide_version_id IS NULL
           AND p_expected_updated_time IS NULL THEN
            RAISE EXCEPTION 'SQL generation guide draft already exists';
        END IF;
        IF p_expected_sql_generation_guide_version_id IS NULL
           OR v_draft.sql_generation_guide_version_id <>
              p_expected_sql_generation_guide_version_id
           OR p_expected_updated_time IS NULL
           OR v_draft.updated_time <> p_expected_updated_time THEN
            RAISE EXCEPTION 'stale_sql_generation_guide_draft';
        END IF;

        v_updated_time := clock_timestamp();
        UPDATE application.sql_generation_guide_version AS version
           SET sql_generation_guide_content =
                   p_sql_generation_guide_content,
               sql_generation_guide_digest = v_digest,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_updated_time,
               updated_by = CURRENT_USER
         WHERE version.sql_generation_guide_version_id =
               v_draft.sql_generation_guide_version_id
        RETURNING version.* INTO v_saved;
        RETURN NEXT v_saved;
        RETURN;
    END IF;

    IF p_expected_sql_generation_guide_version_id IS NOT NULL
       OR p_expected_updated_time IS NOT NULL THEN
        RAISE EXCEPTION 'SQL generation guide draft does not exist';
    END IF;

    SELECT coalesce(max(version.sql_generation_guide_version_number), 0) + 1
      INTO v_version_number
      FROM application.sql_generation_guide_version AS version
     WHERE version.sql_generation_guide_id = p_sql_generation_guide_id;

    INSERT INTO application.sql_generation_guide_version AS version (
        sql_generation_guide_id,
        sql_generation_guide_version_number,
        sql_generation_guide_content,
        sql_generation_guide_digest,
        created_by_principal_id,
        updated_by_principal_id
    ) VALUES (
        p_sql_generation_guide_id,
        v_version_number,
        p_sql_generation_guide_content,
        v_digest,
        v_actor.principal_id,
        v_actor.principal_id
    )
    RETURNING version.* INTO v_saved;

    RETURN NEXT v_saved;
END;
$save_sql_generation_guide_draft$;

REVOKE ALL ON FUNCTION application.save_sql_generation_guide_draft(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    TEXT,
    TIMESTAMPTZ
) FROM PUBLIC;

CREATE FUNCTION application.transition_sql_generation_guide_version(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_sql_generation_guide_version_id BIGINT,
    p_expected_status VARCHAR(20),
    p_target_status VARCHAR(20)
)
RETURNS SETOF application.sql_generation_guide_version
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $transition_sql_generation_guide_version$
DECLARE
    v_actor RECORD;
    v_guide_id BIGINT;
    v_guide application.sql_generation_guide%ROWTYPE;
    v_version application.sql_generation_guide_version%ROWTYPE;
    v_saved application.sql_generation_guide_version%ROWTYPE;
    v_transition_time TIMESTAMPTZ;
BEGIN
    SELECT principal.principal_id, principal.is_super_admin
      INTO v_actor
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
     WHERE identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.is_active
       AND principal.is_active
     FOR SHARE OF identity, principal;
    IF NOT FOUND OR NOT v_actor.is_super_admin THEN
        RAISE EXCEPTION 'SQL generation guide requires Super Admin';
    END IF;

    SELECT version.sql_generation_guide_id
      INTO v_guide_id
      FROM application.sql_generation_guide_version AS version
     WHERE version.sql_generation_guide_version_id =
           p_sql_generation_guide_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SQL generation guide version is unavailable';
    END IF;

    SELECT guide.*
      INTO v_guide
      FROM application.sql_generation_guide AS guide
     WHERE guide.sql_generation_guide_id = v_guide_id
       AND guide.is_active
     FOR UPDATE OF guide;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SQL generation guide is unavailable';
    END IF;

    SELECT version.*
      INTO v_version
      FROM application.sql_generation_guide_version AS version
     WHERE version.sql_generation_guide_version_id =
           p_sql_generation_guide_version_id
       AND version.sql_generation_guide_id = v_guide_id
     FOR UPDATE OF version;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SQL generation guide version is unavailable';
    END IF;

    IF p_expected_status IS NULL
       OR p_target_status IS NULL
       OR NOT (
        (
            p_expected_status = 'draft'
            AND p_target_status = 'published'
        ) OR (
            p_expected_status = 'published'
            AND p_target_status = 'retired'
        )
    ) THEN
        RAISE EXCEPTION 'SQL generation guide version transition is invalid';
    END IF;
    IF v_version.sql_generation_guide_version_status = p_target_status THEN
        RETURN NEXT v_version;
        RETURN;
    END IF;
    IF v_version.sql_generation_guide_version_status <>
       p_expected_status THEN
        RAISE EXCEPTION 'stale SQL generation guide version status';
    END IF;

    v_transition_time := clock_timestamp();
    IF p_target_status = 'published' THEN
        UPDATE application.sql_generation_guide_version AS version
           SET sql_generation_guide_version_status = 'published',
               published_time = v_transition_time,
               published_by_principal_id = v_actor.principal_id,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_transition_time,
               updated_by = CURRENT_USER
         WHERE version.sql_generation_guide_version_id =
               p_sql_generation_guide_version_id
        RETURNING version.* INTO v_saved;
    ELSE
        UPDATE application.sql_generation_guide_version AS version
           SET sql_generation_guide_version_status = 'retired',
               retired_time = v_transition_time,
               retired_by_principal_id = v_actor.principal_id,
               updated_by_principal_id = v_actor.principal_id,
               updated_time = v_transition_time,
               updated_by = CURRENT_USER
         WHERE version.sql_generation_guide_version_id =
               p_sql_generation_guide_version_id
        RETURNING version.* INTO v_saved;
    END IF;

    RETURN NEXT v_saved;
END;
$transition_sql_generation_guide_version$;

REVOKE ALL ON FUNCTION application.transition_sql_generation_guide_version(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR
) FROM PUBLIC;

CREATE TABLE application.workflow_run (
    workflow_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    model_revision BIGINT NOT NULL,
    model_workflow VARCHAR(30) NOT NULL,
    workflow_execution_mode VARCHAR(50),
    actor_principal_id BIGINT NOT NULL,
    actor_entra_principal_identity_id BIGINT,
    agent_sdk_code VARCHAR(100),
    agent_provider_code VARCHAR(100),
    agent_model_code VARCHAR(200),
    reasoning_effort_code VARCHAR(50),
    max_turns INTEGER,
    validation_retry_count INTEGER,
    modeled_entity_type VARCHAR(30),
    code_generation_coverage_mode VARCHAR(30),
    sql_generation_guide_id BIGINT,
    sql_generation_guide_version_id BIGINT,
    sql_generation_guide_digest CHAR(64),
    requested_batch_id VARCHAR(500),
    mapping_operation VARCHAR(20),
    mapping_coverage_mode VARCHAR(30),
    mapping_artifact_type VARCHAR(30),
    mapping_route VARCHAR(30),
    mapping_profile_key VARCHAR(100),
    mapping_profile_version VARCHAR(50),
    mapping_profile_schema_digest CHAR(64),
    mapping_object_output_template_id BIGINT,
    mapping_object_output_template_schema_digest CHAR(64),
    mapping_attribute_output_template_id BIGINT,
    mapping_attribute_output_template_schema_digest CHAR(64),
    selected_scope_digest CHAR(64) NOT NULL,
    selected_scope_count INTEGER NOT NULL,
    workflow_run_state VARCHAR(30) NOT NULL DEFAULT 'queued',
    workflow_run_claim_token_digest CHAR(64),
    workflow_run_claimed_time TIMESTAMPTZ,
    workflow_run_claim_heartbeat_time TIMESTAMPTZ,
    workflow_run_claim_expires_time TIMESTAMPTZ,
    workflow_run_recovery_count INTEGER NOT NULL DEFAULT 0,
    correlation_id UUID NOT NULL,
    workflow_run_request_digest CHAR(64),
    started_time TIMESTAMPTZ,
    completed_time TIMESTAMPTZ,
    failure_code VARCHAR(100),
    failure_message VARCHAR(2000),
    authoring_no_op_base_model_revision BIGINT,
    authoring_no_op_candidate_digest CHAR(64),
    authoring_no_op_model_event_log_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_workflow_run_model FOREIGN KEY (model_id, tenant_id)
        REFERENCES model.model (model_id, tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_actor FOREIGN KEY (actor_principal_id)
        REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_actor_identity FOREIGN KEY (
        actor_entra_principal_identity_id
    ) REFERENCES security.entra_principal_identity (
        entra_principal_identity_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_sql_generation_guide_version FOREIGN KEY (
        sql_generation_guide_version_id,
        sql_generation_guide_id,
        sql_generation_guide_digest
    ) REFERENCES application.sql_generation_guide_version (
        sql_generation_guide_version_id,
        sql_generation_guide_id,
        sql_generation_guide_digest
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_authoring_no_op_event FOREIGN KEY (
        authoring_no_op_model_event_log_id
    ) REFERENCES model.model_event_log (model_event_log_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_mapping_object_output_template FOREIGN KEY (
        mapping_object_output_template_id,
        mapping_object_output_template_schema_digest
    ) REFERENCES application.output_template (
        output_template_id,
        output_template_schema_digest
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_mapping_attribute_output_template FOREIGN KEY (
        mapping_attribute_output_template_id,
        mapping_attribute_output_template_schema_digest
    ) REFERENCES application.output_template (
        output_template_id,
        output_template_schema_digest
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_workflow_run_correlation UNIQUE (correlation_id),
    CONSTRAINT uq_workflow_run_authoring_no_op_event UNIQUE (
        authoring_no_op_model_event_log_id
    ),
    CONSTRAINT uq_workflow_run_model_witness UNIQUE (
        workflow_run_id,
        model_id
    ),
    CONSTRAINT ck_workflow_run_workflow CHECK (
        model_workflow IN (
            'profiling', 'analysis', 'conceptual', 'logical',
            'dimensional', 'mapping', 'code_generation'
        )
    ),
    CONSTRAINT ck_workflow_run_model_revision CHECK (
        model_revision > 0
    ),
    CONSTRAINT ck_workflow_run_execution_mode CHECK (
        (
            workflow_execution_mode IS NULL
            AND model_workflow IN (
                'profiling', 'analysis', 'code_generation'
            )
        ) OR (
            workflow_execution_mode IN (
                'one_shot', 'tool_assisted', 'detailed_coverage'
            )
            AND model_workflow IN (
                'analysis', 'conceptual', 'logical',
                'dimensional', 'mapping'
            )
        )
    ),
    CONSTRAINT ck_workflow_run_agent_configuration CHECK (
        (
            model_workflow <> 'code_generation'
            AND workflow_execution_mode IS NULL
            AND agent_sdk_code IS NULL
            AND agent_provider_code IS NULL
            AND agent_model_code IS NULL
            AND reasoning_effort_code IS NULL
            AND max_turns IS NULL
            AND validation_retry_count IS NULL
        ) OR (
            (
                model_workflow = 'code_generation'
                OR workflow_execution_mode IS NOT NULL
            )
            AND agent_sdk_code IS NOT NULL
            AND agent_provider_code IS NOT NULL
            AND agent_model_code IS NOT NULL
            AND reasoning_effort_code IS NOT NULL
            AND max_turns BETWEEN 1 AND 50
            AND validation_retry_count BETWEEN 0 AND 5
        )
    ),
    CONSTRAINT ck_workflow_run_agent_codes CHECK (
        (agent_sdk_code IS NULL OR agent_sdk_code ~ '^[a-z][a-z0-9_.-]{0,99}$')
        AND (
            agent_provider_code IS NULL
            OR agent_provider_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        )
        AND (
            agent_model_code IS NULL
            OR agent_model_code ~ '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$'
        )
        AND (
            reasoning_effort_code IS NULL
            OR reasoning_effort_code ~ '^[a-z][a-z0-9_-]{0,49}$'
        )
    ),
    CONSTRAINT ck_workflow_run_modeled_entity_type CHECK (
        (
            model_workflow IN ('mapping', 'code_generation')
            AND modeled_entity_type IS NOT NULL
            AND modeled_entity_type IN (
                'logical_entity', 'dimensional_entity'
            )
        ) OR (
            model_workflow NOT IN ('mapping', 'code_generation')
            AND modeled_entity_type IS NULL
        )
    ),
    CONSTRAINT ck_workflow_run_code_generation_request CHECK (
        (
            model_workflow = 'code_generation'
            AND code_generation_coverage_mode IS NOT NULL
            AND code_generation_coverage_mode IN (
                'selected_targets', 'all_eligible_targets'
            )
            AND num_nonnulls(
                sql_generation_guide_id,
                sql_generation_guide_version_id,
                sql_generation_guide_digest
            ) = 3
            AND sql_generation_guide_digest ~ '^[0-9a-f]{64}$'
        ) OR (
            model_workflow <> 'code_generation'
            AND code_generation_coverage_mode IS NULL
            AND sql_generation_guide_id IS NULL
            AND sql_generation_guide_version_id IS NULL
            AND sql_generation_guide_digest IS NULL
        )
    ),
    CONSTRAINT ck_workflow_run_mapping_request CHECK (
        (
            model_workflow = 'mapping'
            AND num_nonnulls(
                mapping_operation,
                mapping_coverage_mode,
                mapping_artifact_type,
                mapping_route,
                mapping_profile_key,
                mapping_profile_version,
                mapping_profile_schema_digest
            ) = 7
            AND mapping_operation IN ('build', 'extend')
            AND mapping_coverage_mode = 'selected_targets'
            AND mapping_artifact_type IN (
                'sql_file', 'python_file', 'python_notebook'
            )
            AND mapping_route = CASE modeled_entity_type
                WHEN 'logical_entity' THEN 'logical_to_silver'
                WHEN 'dimensional_entity' THEN 'dimensional_to_gold'
                ELSE NULL
            END
            AND mapping_profile_key = 'mapping.standard'
            AND mapping_profile_version = '1.0.0'
            AND mapping_profile_schema_digest =
                'b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa'
            AND selected_scope_count = 1
        ) OR (
            model_workflow <> 'mapping'
            AND mapping_operation IS NULL
            AND mapping_coverage_mode IS NULL
            AND mapping_artifact_type IS NULL
            AND mapping_route IS NULL
            AND mapping_profile_key IS NULL
            AND mapping_profile_version IS NULL
            AND mapping_profile_schema_digest IS NULL
        )
    ),
    CONSTRAINT ck_workflow_run_mapping_output_templates CHECK (
        num_nonnulls(
            mapping_object_output_template_id,
            mapping_object_output_template_schema_digest
        ) IN (0, 2)
        AND num_nonnulls(
            mapping_attribute_output_template_id,
            mapping_attribute_output_template_schema_digest
        ) IN (0, 2)
        AND (
            model_workflow = 'mapping'
            OR num_nonnulls(
                mapping_object_output_template_id,
                mapping_object_output_template_schema_digest,
                mapping_attribute_output_template_id,
                mapping_attribute_output_template_schema_digest
            ) = 0
        )
    ),
    CONSTRAINT ck_workflow_run_requested_batch_id CHECK (
        requested_batch_id IS NULL
        OR (
            model_workflow IN ('profiling', 'analysis')
            AND reference.is_nonblank(requested_batch_id)
            AND requested_batch_id = btrim(requested_batch_id)
            AND octet_length(requested_batch_id) <= 500
        )
    ),
    CONSTRAINT ck_workflow_run_selected_scope CHECK (
        selected_scope_digest ~ '^[0-9a-f]{64}$'
        AND selected_scope_count > 0
    ),
    CONSTRAINT ck_workflow_run_request_digest CHECK (
        workflow_run_request_digest IS NULL
        OR workflow_run_request_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_workflow_run_state CHECK (
        workflow_run_state IN (
            'queued', 'running', 'completed',
            'completed_with_repair', 'failed'
        )
    ),
    CONSTRAINT ck_workflow_run_claim CHECK (
        workflow_run_recovery_count BETWEEN 0 AND 5
        AND (
            (
                workflow_run_state = 'running'
                AND num_nonnulls(
                    workflow_run_claim_token_digest,
                    workflow_run_claimed_time,
                    workflow_run_claim_heartbeat_time,
                    workflow_run_claim_expires_time
                ) IN (0, 4)
                AND (
                    workflow_run_claim_token_digest IS NULL
                    OR (
                        workflow_run_claim_token_digest ~ '^[0-9a-f]{64}$'
                        AND workflow_run_claimed_time
                            <= workflow_run_claim_heartbeat_time
                        AND workflow_run_claim_heartbeat_time
                            < workflow_run_claim_expires_time
                    )
                )
            ) OR (
                workflow_run_state <> 'running'
                AND num_nonnulls(
                    workflow_run_claim_token_digest,
                    workflow_run_claimed_time,
                    workflow_run_claim_heartbeat_time,
                    workflow_run_claim_expires_time
                ) = 0
            )
        )
    ),
    CONSTRAINT ck_workflow_run_timestamps CHECK (
        (
            workflow_run_state = 'queued'
            AND started_time IS NULL
            AND completed_time IS NULL
        ) OR (
            workflow_run_state = 'running'
            AND started_time IS NOT NULL
            AND started_time >= created_time
            AND completed_time IS NULL
        ) OR (
            workflow_run_state IN (
                'completed', 'completed_with_repair', 'failed'
            )
            AND started_time IS NOT NULL
            AND started_time >= created_time
            AND completed_time IS NOT NULL
            AND completed_time >= started_time
        )
    ),
    CONSTRAINT ck_workflow_run_failure CHECK (
        (
            workflow_run_state = 'failed'
            AND reference.is_nonblank(failure_code)
            AND reference.is_nonblank(failure_message)
        ) OR (
            workflow_run_state <> 'failed'
            AND failure_code IS NULL
            AND failure_message IS NULL
        )
    ),
    CONSTRAINT ck_workflow_run_authoring_no_op_receipt CHECK (
        num_nonnulls(
            authoring_no_op_base_model_revision,
            authoring_no_op_candidate_digest,
            authoring_no_op_model_event_log_id
        ) IN (0, 3)
        AND (
            authoring_no_op_candidate_digest IS NULL
            OR (
                workflow_run_state IN ('completed', 'completed_with_repair')
                AND model_workflow IN (
                    'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
                )
                AND workflow_execution_mode IS NOT NULL
                AND authoring_no_op_base_model_revision > 0
                AND authoring_no_op_candidate_digest ~ '^[0-9a-f]{64}$'
            )
        )
    )
);

CREATE INDEX ix_workflow_run_model_created
    ON application.workflow_run (model_id, created_time DESC);
CREATE INDEX ix_workflow_run_state
    ON application.workflow_run (workflow_run_state, created_time);
CREATE INDEX ix_workflow_run_claim_eligibility
    ON application.workflow_run (created_time, workflow_run_id)
    INCLUDE (
        workflow_run_claim_token_digest,
        workflow_run_claim_expires_time,
        workflow_run_recovery_count
    )
    WHERE workflow_run_state = 'running';
CREATE UNIQUE INDEX uq_workflow_run_running_tenant
    ON application.workflow_run (tenant_id)
    WHERE workflow_run_state = 'running';

CREATE TABLE application.workflow_run_object_selection (
    workflow_run_object_selection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    selection_order INTEGER NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_workflow_run_object_selection_run FOREIGN KEY (
        workflow_run_id,
        model_id
    ) REFERENCES application.workflow_run (workflow_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_object_selection_scope FOREIGN KEY (
        model_id,
        object_id
    ) REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_workflow_run_object_selection_object UNIQUE (
        workflow_run_id,
        object_id
    ),
    CONSTRAINT uq_workflow_run_object_selection_order UNIQUE (
        workflow_run_id,
        selection_order
    ),
    CONSTRAINT ck_workflow_run_object_selection_order CHECK (
        selection_order > 0
    )
);

CREATE INDEX ix_workflow_run_object_selection_scope
    ON application.workflow_run_object_selection (
        model_id,
        object_id,
        workflow_run_id
    );

CREATE TABLE application.workflow_run_mapping_target_selection (
    workflow_run_mapping_target_selection_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    selection_order INTEGER NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_workflow_run_mapping_target_selection_run FOREIGN KEY (
        workflow_run_id,
        model_id
    ) REFERENCES application.workflow_run (workflow_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_mapping_target_selection_scope FOREIGN KEY (
        model_id,
        object_id
    ) REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_mapping_target_selection_system FOREIGN KEY (
        source_system_id
    ) REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_workflow_run_mapping_target_selection_pair UNIQUE (
        workflow_run_id,
        object_id,
        source_system_id
    ),
    CONSTRAINT uq_workflow_run_mapping_target_selection_order UNIQUE (
        workflow_run_id,
        selection_order
    ),
    CONSTRAINT ck_workflow_run_mapping_target_selection_order CHECK (
        selection_order > 0
    )
);

CREATE INDEX ix_workflow_run_mapping_target_selection_pair
    ON application.workflow_run_mapping_target_selection (
        model_id,
        object_id,
        source_system_id,
        workflow_run_id
    );

CREATE FUNCTION application.guard_workflow_run_mapping_target_selection()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_workflow_run_mapping_target_selection$
BEGIN
    RAISE EXCEPTION 'Workflow Run Mapping target selections are immutable';
END;
$guard_workflow_run_mapping_target_selection$;

CREATE TRIGGER guard_workflow_run_mapping_target_selection
BEFORE UPDATE OR DELETE ON application.workflow_run_mapping_target_selection
FOR EACH ROW
EXECUTE FUNCTION application.guard_workflow_run_mapping_target_selection();

CREATE FUNCTION application.guard_workflow_run_object_selection()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_workflow_run_object_selection$
BEGIN
    RAISE EXCEPTION 'Workflow Run Object selections are immutable';
END;
$guard_workflow_run_object_selection$;

CREATE TRIGGER guard_workflow_run_object_selection
BEFORE UPDATE OR DELETE ON application.workflow_run_object_selection
FOR EACH ROW EXECUTE FUNCTION application.guard_workflow_run_object_selection();

CREATE FUNCTION application.guard_workflow_run()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_workflow_run$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'workflow runs cannot be deleted' USING ERRCODE = '55000';
    END IF;

    IF ROW(
        NEW.tenant_id,
        NEW.model_id,
        NEW.model_revision,
        NEW.model_workflow,
        NEW.workflow_execution_mode,
        NEW.actor_principal_id,
        NEW.actor_entra_principal_identity_id,
        NEW.agent_sdk_code,
        NEW.agent_provider_code,
        NEW.agent_model_code,
        NEW.reasoning_effort_code,
        NEW.max_turns,
        NEW.validation_retry_count,
        NEW.modeled_entity_type,
        NEW.code_generation_coverage_mode,
        NEW.sql_generation_guide_id,
        NEW.sql_generation_guide_version_id,
        NEW.sql_generation_guide_digest,
        NEW.requested_batch_id,
        NEW.mapping_operation,
        NEW.mapping_coverage_mode,
        NEW.mapping_artifact_type,
        NEW.mapping_route,
        NEW.mapping_profile_key,
        NEW.mapping_profile_version,
        NEW.mapping_profile_schema_digest,
        NEW.mapping_object_output_template_id,
        NEW.mapping_object_output_template_schema_digest,
        NEW.mapping_attribute_output_template_id,
        NEW.mapping_attribute_output_template_schema_digest,
        NEW.selected_scope_digest,
        NEW.selected_scope_count,
        NEW.correlation_id,
        NEW.workflow_run_request_digest,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.tenant_id,
        OLD.model_id,
        OLD.model_revision,
        OLD.model_workflow,
        OLD.workflow_execution_mode,
        OLD.actor_principal_id,
        OLD.actor_entra_principal_identity_id,
        OLD.agent_sdk_code,
        OLD.agent_provider_code,
        OLD.agent_model_code,
        OLD.reasoning_effort_code,
        OLD.max_turns,
        OLD.validation_retry_count,
        OLD.modeled_entity_type,
        OLD.code_generation_coverage_mode,
        OLD.sql_generation_guide_id,
        OLD.sql_generation_guide_version_id,
        OLD.sql_generation_guide_digest,
        OLD.requested_batch_id,
        OLD.mapping_operation,
        OLD.mapping_coverage_mode,
        OLD.mapping_artifact_type,
        OLD.mapping_route,
        OLD.mapping_profile_key,
        OLD.mapping_profile_version,
        OLD.mapping_profile_schema_digest,
        OLD.mapping_object_output_template_id,
        OLD.mapping_object_output_template_schema_digest,
        OLD.mapping_attribute_output_template_id,
        OLD.mapping_attribute_output_template_schema_digest,
        OLD.selected_scope_digest,
        OLD.selected_scope_count,
        OLD.correlation_id,
        OLD.workflow_run_request_digest,
        OLD.created_time,
        OLD.created_by
    ) THEN
        RAISE EXCEPTION 'workflow run identity is immutable' USING ERRCODE = '55000';
    END IF;

    IF OLD.workflow_run_state IN (
        'completed', 'completed_with_repair', 'failed'
    ) THEN
        RAISE EXCEPTION 'terminal workflow run is immutable' USING ERRCODE = '55000';
    END IF;

    IF OLD.workflow_run_state = 'running'
       AND NEW.workflow_run_state = 'running' THEN
        IF ROW(
            NEW.started_time,
            NEW.completed_time,
            NEW.failure_code,
            NEW.failure_message,
            NEW.authoring_no_op_base_model_revision,
            NEW.authoring_no_op_candidate_digest,
            NEW.authoring_no_op_model_event_log_id
        ) IS DISTINCT FROM ROW(
            OLD.started_time,
            OLD.completed_time,
            OLD.failure_code,
            OLD.failure_message,
            OLD.authoring_no_op_base_model_revision,
            OLD.authoring_no_op_candidate_digest,
            OLD.authoring_no_op_model_event_log_id
        ) THEN
            RAISE EXCEPTION 'workflow run outcome is immutable while running'
                USING ERRCODE = '55000';
        END IF;
        IF NEW.workflow_run_recovery_count < OLD.workflow_run_recovery_count
           OR NEW.workflow_run_recovery_count
                > OLD.workflow_run_recovery_count + 1 THEN
            RAISE EXCEPTION 'invalid workflow run recovery count'
                USING ERRCODE = '55000';
        END IF;
        IF NEW.workflow_run_recovery_count =
               OLD.workflow_run_recovery_count + 1
           AND (
               OLD.workflow_run_claim_token_digest IS NULL
               OR NEW.workflow_run_claim_token_digest IS NULL
               OR NEW.workflow_run_claim_token_digest =
                   OLD.workflow_run_claim_token_digest
               OR OLD.workflow_run_claim_expires_time > clock_timestamp()
           ) THEN
            RAISE EXCEPTION 'invalid workflow run claim recovery'
                USING ERRCODE = '55000';
        END IF;
        IF NEW.workflow_run_recovery_count = OLD.workflow_run_recovery_count
           AND NEW.workflow_run_claim_token_digest IS NOT NULL
           AND OLD.workflow_run_claim_token_digest IS NOT NULL
           AND NEW.workflow_run_claim_token_digest <>
               OLD.workflow_run_claim_token_digest THEN
            RAISE EXCEPTION 'invalid workflow run claim rotation'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.workflow_run_state = 'queued' AND NEW.workflow_run_state = 'running')
        OR (
            OLD.workflow_run_state = 'running'
            AND NEW.workflow_run_state IN (
                'completed', 'completed_with_repair', 'failed'
            )
        )
    ) THEN
        RAISE EXCEPTION 'invalid workflow run state transition'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$guard_workflow_run$;

CREATE TRIGGER guard_workflow_run
BEFORE UPDATE OR DELETE ON application.workflow_run
FOR EACH ROW EXECUTE FUNCTION application.guard_workflow_run();

ALTER TABLE model.model_event_log
    ADD CONSTRAINT fk_model_event_log_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_model_event_log_workflow_run
    ON model.model_event_log (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE model.modeling_assertion_document
    ADD CONSTRAINT fk_modeling_assertion_document_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_modeling_assertion_document_workflow_run
    ON model.modeling_assertion_document (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE model.modeling_assertion_record
    ADD CONSTRAINT fk_modeling_assertion_record_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_modeling_assertion_record_workflow_run
    ON model.modeling_assertion_record (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.attribute_profile
    ADD CONSTRAINT fk_attribute_profile_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_attribute_profile_workflow_run
    ON workflow.attribute_profile (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.analysis_result
    ADD CONSTRAINT fk_analysis_result_inference_workflow_run
    FOREIGN KEY (inference_workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION,
    ADD CONSTRAINT fk_analysis_result_validation_workflow_run
    FOREIGN KEY (validation_workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_analysis_result_inference_workflow_run
    ON workflow.analysis_result (inference_workflow_run_id, model_id)
    WHERE inference_workflow_run_id IS NOT NULL;
CREATE INDEX ix_analysis_result_validation_workflow_run
    ON workflow.analysis_result (validation_workflow_run_id, model_id)
    WHERE validation_workflow_run_id IS NOT NULL;

ALTER TABLE workflow.conceptual_object
    ADD CONSTRAINT fk_conceptual_object_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_conceptual_object_workflow_run
    ON workflow.conceptual_object (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.conceptual_relationship
    ADD CONSTRAINT fk_conceptual_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_conceptual_relationship_workflow_run
    ON workflow.conceptual_relationship (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.conceptual_support
    ADD CONSTRAINT fk_conceptual_support_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_conceptual_support_workflow_run
    ON workflow.conceptual_support (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_submodel
    ADD CONSTRAINT fk_logical_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_submodel_workflow_run
    ON workflow.logical_submodel (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_entity
    ADD CONSTRAINT fk_logical_entity_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_entity_workflow_run
    ON workflow.logical_entity (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_entity_submodel
    ADD CONSTRAINT fk_logical_entity_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_entity_submodel_workflow_run
    ON workflow.logical_entity_submodel (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_attribute
    ADD CONSTRAINT fk_logical_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_attribute_workflow_run
    ON workflow.logical_attribute (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_entity_source_mapping
    ADD CONSTRAINT fk_logical_entity_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_entity_source_mapping_workflow_run
    ON workflow.logical_entity_source_mapping (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_attribute_source_mapping
    ADD CONSTRAINT fk_logical_attribute_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_attribute_source_mapping_workflow_run
    ON workflow.logical_attribute_source_mapping (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.logical_relationship
    ADD CONSTRAINT fk_logical_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_logical_relationship_workflow_run
    ON workflow.logical_relationship (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_submodel
    ADD CONSTRAINT fk_dimensional_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_submodel_workflow_run
    ON workflow.dimensional_submodel (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_entity
    ADD CONSTRAINT fk_dimensional_entity_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_entity_workflow_run
    ON workflow.dimensional_entity (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_entity_submodel
    ADD CONSTRAINT fk_dimensional_entity_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_entity_submodel_workflow_run
    ON workflow.dimensional_entity_submodel (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_attribute
    ADD CONSTRAINT fk_dimensional_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_attribute_workflow_run
    ON workflow.dimensional_attribute (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_entity_source_mapping
    ADD CONSTRAINT fk_dimensional_entity_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_entity_source_mapping_workflow_run
    ON workflow.dimensional_entity_source_mapping (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_attribute_source_mapping
    ADD CONSTRAINT fk_dimensional_attribute_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_attribute_source_mapping_workflow_run
    ON workflow.dimensional_attribute_source_mapping (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.dimensional_relationship
    ADD CONSTRAINT fk_dimensional_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_dimensional_relationship_workflow_run
    ON workflow.dimensional_relationship (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.mapping_source_system_dependency
    ADD CONSTRAINT fk_mapping_source_system_dependency_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_mapping_source_system_dependency_workflow_run
    ON workflow.mapping_source_system_dependency (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.mapping_object
    ADD CONSTRAINT fk_mapping_object_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_mapping_object_workflow_run
    ON workflow.mapping_object (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

ALTER TABLE workflow.mapping_attribute
    ADD CONSTRAINT fk_mapping_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
CREATE INDEX ix_mapping_attribute_workflow_run
    ON workflow.mapping_attribute (workflow_run_id, model_id)
    WHERE workflow_run_id IS NOT NULL;

CREATE TABLE application.workflow_run_prompt_snapshot (
    workflow_run_prompt_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    workflow_stage_id BIGINT NOT NULL,
    prompt_template_version_id BIGINT NOT NULL,
    prompt_resolution_source VARCHAR(20) NOT NULL,
    prompt_template_digest CHAR(64) NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_workflow_run_prompt_snapshot_run FOREIGN KEY (
        workflow_run_id,
        model_id
    ) REFERENCES application.workflow_run (workflow_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_prompt_snapshot_version FOREIGN KEY (
        prompt_template_version_id,
        workflow_stage_id,
        prompt_template_digest
    ) REFERENCES application.prompt_template_version (
        prompt_template_version_id,
        workflow_stage_id,
        prompt_template_digest
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_workflow_run_prompt_snapshot_stage UNIQUE (
        workflow_run_id,
        workflow_stage_id
    ),
    CONSTRAINT ck_workflow_run_prompt_snapshot_source CHECK (
        prompt_resolution_source IN (
            'run_override', 'model_default', 'global_default'
        )
    ),
    CONSTRAINT ck_workflow_run_prompt_snapshot_digest CHECK (
        prompt_template_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE INDEX ix_workflow_run_prompt_snapshot_version
    ON application.workflow_run_prompt_snapshot (
        prompt_template_version_id,
        workflow_run_id
    );

CREATE FUNCTION application.guard_workflow_run_prompt_snapshot()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_workflow_run_prompt_snapshot$
BEGIN
    RAISE EXCEPTION 'Workflow Run prompt snapshots are immutable';
END;
$guard_workflow_run_prompt_snapshot$;

CREATE TRIGGER guard_workflow_run_prompt_snapshot
BEFORE UPDATE OR DELETE ON application.workflow_run_prompt_snapshot
FOR EACH ROW EXECUTE FUNCTION application.guard_workflow_run_prompt_snapshot();

CREATE FUNCTION application.snapshot_workflow_run_prompts(
    p_workflow_run_id BIGINT,
    p_run_overrides JSONB
)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $snapshot_workflow_run_prompts$
DECLARE
    v_run RECORD;
    v_stage RECORD;
    v_prompt_template_version_id BIGINT;
    v_prompt_template_digest CHAR(64);
    v_prompt_resolution_source VARCHAR(20);
    v_override_value TEXT;
    v_snapshot_count INTEGER := 0;
    v_override_count INTEGER := 0;
BEGIN
    IF p_run_overrides IS NULL
       OR jsonb_typeof(p_run_overrides) <> 'object'
       OR octet_length(p_run_overrides::TEXT) > 32768 THEN
        RAISE EXCEPTION 'Run prompt overrides must be a bounded JSON object';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.model_workflow,
           run.workflow_execution_mode,
           model.tenant_id
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS model
        ON model.model_id = run.model_id
       AND model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.workflow_run_state = 'queued'
     FOR UPDATE OF run;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run is unavailable for prompt resolution';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM application.workflow_run_prompt_snapshot AS snapshot
         WHERE snapshot.workflow_run_id = p_workflow_run_id
    ) THEN
        RAISE EXCEPTION 'Workflow Run prompts have already been resolved';
    END IF;

    FOR v_stage IN
        SELECT stage.workflow_stage_id
          FROM application.workflow_stage AS stage
         WHERE stage.model_workflow = v_run.model_workflow
           AND stage.workflow_execution_mode IS NOT DISTINCT FROM
               v_run.workflow_execution_mode
           AND stage.workflow_stage_is_agentic
           AND stage.is_active
         ORDER BY stage.workflow_stage_order
    LOOP
        v_override_value := p_run_overrides ->>
            v_stage.workflow_stage_id::TEXT;
        v_prompt_template_version_id := NULL;
        v_prompt_resolution_source := NULL;

        IF v_override_value IS NOT NULL THEN
            IF v_override_value !~ '^[1-9][0-9]*$' THEN
                RAISE EXCEPTION 'Run prompt override version is invalid';
            END IF;
            v_prompt_template_version_id := v_override_value::BIGINT;
            v_prompt_resolution_source := 'run_override';
            v_override_count := v_override_count + 1;
        ELSE
            SELECT assignment.prompt_template_version_id
              INTO v_prompt_template_version_id
              FROM application.prompt_assignment AS assignment
             WHERE assignment.workflow_stage_id = v_stage.workflow_stage_id
               AND assignment.prompt_assignment_scope = 'model_default'
               AND assignment.model_id = v_run.model_id
               AND assignment.is_active;
            IF FOUND THEN
                v_prompt_resolution_source := 'model_default';
            ELSE
                SELECT assignment.prompt_template_version_id
                  INTO v_prompt_template_version_id
                  FROM application.prompt_assignment AS assignment
                 WHERE assignment.workflow_stage_id = v_stage.workflow_stage_id
                   AND assignment.prompt_assignment_scope = 'global_default'
                   AND assignment.is_active;
                IF FOUND THEN
                    v_prompt_resolution_source := 'global_default';
                END IF;
            END IF;
        END IF;

        IF v_prompt_template_version_id IS NULL THEN
            RAISE EXCEPTION 'No usable prompt is assigned to Workflow Stage %',
                v_stage.workflow_stage_id;
        END IF;

        SELECT version.prompt_template_digest
          INTO v_prompt_template_digest
          FROM application.prompt_template_version AS version
          JOIN application.prompt_template AS template
            ON template.prompt_template_id = version.prompt_template_id
           AND template.workflow_stage_id = version.workflow_stage_id
         WHERE version.prompt_template_version_id =
               v_prompt_template_version_id
           AND version.workflow_stage_id = v_stage.workflow_stage_id
           AND version.prompt_template_version_status = 'published'
           AND template.is_active
           AND (
               template.prompt_template_ownership_scope = 'global'
               OR template.owner_tenant_id = v_run.tenant_id
           );
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Resolved prompt version is unavailable to the Model';
        END IF;

        INSERT INTO application.workflow_run_prompt_snapshot (
            workflow_run_id,
            model_id,
            workflow_stage_id,
            prompt_template_version_id,
            prompt_resolution_source,
            prompt_template_digest
        ) VALUES (
            p_workflow_run_id,
            v_run.model_id,
            v_stage.workflow_stage_id,
            v_prompt_template_version_id,
            v_prompt_resolution_source,
            v_prompt_template_digest
        );
        v_snapshot_count := v_snapshot_count + 1;
    END LOOP;

    IF v_snapshot_count = 0 THEN
        RAISE EXCEPTION 'Workflow Run has no active agentic prompt stages';
    END IF;
    IF v_override_count <> (
        SELECT count(*)
          FROM jsonb_object_keys(p_run_overrides)
    ) THEN
        RAISE EXCEPTION 'Run prompt override does not belong to this Workflow Run';
    END IF;

    RETURN v_snapshot_count;
END;
$snapshot_workflow_run_prompts$;

REVOKE ALL ON FUNCTION application.snapshot_workflow_run_prompts(
    BIGINT,
    JSONB
) FROM PUBLIC;

CREATE FUNCTION application.create_workflow_run(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_model_id BIGINT,
    p_expected_model_revision BIGINT,
    p_model_workflow VARCHAR(30),
    p_workflow_execution_mode VARCHAR(50),
    p_agent_sdk_code VARCHAR(100),
    p_agent_provider_code VARCHAR(100),
    p_agent_model_code VARCHAR(200),
    p_reasoning_effort_code VARCHAR(50),
    p_max_turns INTEGER,
    p_validation_retry_count INTEGER,
    p_selected_object_ids BIGINT[],
    p_modeled_entity_type VARCHAR(30),
    p_requested_batch_id VARCHAR(500),
    p_correlation_id UUID,
    p_prompt_overrides JSONB,
    p_mapping_operation VARCHAR(20) DEFAULT NULL,
    p_mapping_coverage_mode VARCHAR(30) DEFAULT NULL,
    p_mapping_artifact_type VARCHAR(30) DEFAULT NULL,
    p_mapping_source_system_id BIGINT DEFAULT NULL,
    p_mapping_object_output_template_id BIGINT DEFAULT NULL,
    p_mapping_attribute_output_template_id BIGINT DEFAULT NULL,
    p_code_generation_coverage_mode VARCHAR(30) DEFAULT NULL,
    p_sql_generation_guide_version_id BIGINT DEFAULT NULL
)
RETURNS TABLE (
    created BOOLEAN,
    denial_code VARCHAR(50),
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    correlation_id UUID,
    prompt_snapshot_count INTEGER,
    created_time TIMESTAMPTZ,
    model_revision BIGINT,
    selected_scope_digest CHAR(64),
    selected_scope_count INTEGER,
    code_generation_coverage_mode VARCHAR(30),
    sql_generation_guide_id BIGINT,
    sql_generation_guide_version_id BIGINT,
    sql_generation_guide_digest CHAR(64)
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $create_workflow_run$
DECLARE
    v_model RECORD;
    v_decision RECORD;
    v_actor_entra_principal_identity_id BIGINT;
    v_existing application.workflow_run%ROWTYPE;
    v_created application.workflow_run%ROWTYPE;
    v_is_agentic BOOLEAN;
    v_agent_input_count INTEGER;
    v_agent_sdk_code VARCHAR(100);
    v_agent_provider_code VARCHAR(100);
    v_agent_model_code VARCHAR(200);
    v_reasoning_effort_code VARCHAR(50);
    v_max_turns INTEGER;
    v_validation_retry_count INTEGER;
    v_selected_object_ids BIGINT[];
    v_caller_selected_object_ids BIGINT[];
    v_caller_selected_scope_digest CHAR(64);
    v_caller_selected_scope_count INTEGER;
    v_selected_scope_digest CHAR(64);
    v_selected_scope_count INTEGER;
    v_eligible_scope_count INTEGER;
    v_selected_system_count INTEGER;
    v_requested_batch_id VARCHAR(500);
    v_modeled_entity_type VARCHAR(30);
    v_mapping_route VARCHAR(30);
    v_mapping_header_count INTEGER;
    v_mapping_header_layer_count INTEGER;
    v_mapping_invalid_header_count INTEGER;
    v_mapping_zone_code TEXT;
    v_mapping_profile_key CONSTANT VARCHAR(100) := 'mapping.standard';
    v_mapping_profile_version CONSTANT VARCHAR(50) := '1.0.0';
    v_mapping_profile_schema_digest CONSTANT CHAR(64) :=
        'b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa';
    v_mapping_object_output_template_schema_digest CHAR(64);
    v_mapping_attribute_output_template_schema_digest CHAR(64);
    v_sql_generation_guide_id BIGINT;
    v_sql_generation_guide_version_id BIGINT;
    v_sql_generation_guide_digest CHAR(64);
    v_request_digest CHAR(64);
    v_prompt_snapshot_count INTEGER := 0;
BEGIN
    IF p_correlation_id IS NULL THEN
        RAISE EXCEPTION 'Workflow Run correlation ID is required';
    END IF;
    IF p_selected_object_ids IS NULL THEN
        RAISE EXCEPTION 'Selected Scope Object IDs are required';
    END IF;
    IF p_model_workflow = 'code_generation' THEN
        IF p_code_generation_coverage_mode IS NULL
           OR p_code_generation_coverage_mode NOT IN (
               'selected_targets', 'all_eligible_targets'
           ) THEN
            RAISE EXCEPTION
                'Code Generation coverage mode is invalid';
        END IF;
        IF p_code_generation_coverage_mode = 'selected_targets'
           AND cardinality(p_selected_object_ids) NOT BETWEEN 1 AND 50000 THEN
            RAISE EXCEPTION
                'Selected target coverage must contain between 1 and 50000 Objects';
        END IF;
        IF p_code_generation_coverage_mode = 'all_eligible_targets'
           AND cardinality(p_selected_object_ids) <> 0 THEN
            RAISE EXCEPTION
                'All eligible target coverage requires an empty Object selection';
        END IF;
        IF p_sql_generation_guide_version_id IS NOT NULL
           AND p_sql_generation_guide_version_id <= 0 THEN
            RAISE EXCEPTION
                'SQL generation guide version is invalid';
        END IF;
    ELSE
        IF p_code_generation_coverage_mode IS NOT NULL
           OR p_sql_generation_guide_version_id IS NOT NULL THEN
            RAISE EXCEPTION
                'Code Generation inputs are unavailable for this Workflow Run';
        END IF;
        IF cardinality(p_selected_object_ids) NOT BETWEEN 1 AND 50000 THEN
            RAISE EXCEPTION
                'Selected Scope must contain between 1 and 50000 Objects';
        END IF;
    END IF;
    IF EXISTS (
        SELECT 1
          FROM unnest(p_selected_object_ids) AS selected(object_id)
         WHERE selected.object_id IS NULL
            OR selected.object_id <= 0
    ) THEN
        RAISE EXCEPTION 'Selected Scope Object IDs must be positive';
    END IF;
    IF cardinality(p_selected_object_ids) <> (
        SELECT count(DISTINCT selected.object_id)
          FROM unnest(p_selected_object_ids) AS selected(object_id)
    ) THEN
        RAISE EXCEPTION 'Selected Scope Object IDs must be unique';
    END IF;

    SELECT coalesce(
               array_agg(selected.object_id ORDER BY selected.object_id),
               ARRAY[]::BIGINT[]
           ),
           count(*)::INTEGER
      INTO v_caller_selected_object_ids,
           v_caller_selected_scope_count
      FROM unnest(p_selected_object_ids) AS selected(object_id);
    v_caller_selected_scope_digest := encode(
        sha256(
            convert_to(
                array_to_string(v_caller_selected_object_ids, ','),
                'UTF8'
            )
        ),
        'hex'
    );
    v_selected_object_ids := v_caller_selected_object_ids;
    v_selected_scope_count := v_caller_selected_scope_count;
    v_selected_scope_digest := v_caller_selected_scope_digest;

    v_modeled_entity_type := p_modeled_entity_type;
    IF p_model_workflow = 'mapping' THEN
        IF p_modeled_entity_type IS NOT NULL THEN
            RAISE EXCEPTION 'Mapping route is inferred by the server';
        END IF;
        IF num_nonnulls(
               p_mapping_operation,
               p_mapping_coverage_mode,
               p_mapping_artifact_type,
               p_mapping_source_system_id
           ) <> 4
           OR v_selected_scope_count <> 1
           OR p_mapping_operation NOT IN ('build', 'extend')
           OR p_mapping_coverage_mode <> 'selected_targets'
           OR p_mapping_artifact_type NOT IN (
               'sql_file', 'python_file', 'python_notebook'
           )
           OR p_mapping_source_system_id IS NULL
           OR p_mapping_source_system_id <= 0
           OR (
               p_mapping_object_output_template_id IS NOT NULL
               AND p_mapping_object_output_template_id <= 0
           )
           OR (
               p_mapping_attribute_output_template_id IS NOT NULL
               AND p_mapping_attribute_output_template_id <= 0
           ) THEN
            RAISE EXCEPTION
                'Mapping requires one complete selected target and source System pair';
        END IF;
    ELSIF p_model_workflow = 'code_generation' THEN
        IF p_modeled_entity_type IS NULL
           OR p_modeled_entity_type NOT IN (
               'logical_entity', 'dimensional_entity'
           ) THEN
            RAISE EXCEPTION
                'Code Generation requires a modeled Entity type';
        END IF;
        IF num_nonnulls(
            p_mapping_operation,
            p_mapping_coverage_mode,
            p_mapping_artifact_type,
            p_mapping_source_system_id,
            p_mapping_object_output_template_id,
            p_mapping_attribute_output_template_id
        ) <> 0 THEN
            RAISE EXCEPTION
                'Mapping inputs are unavailable for this Workflow Run';
        END IF;
    ELSIF p_modeled_entity_type IS NOT NULL THEN
        RAISE EXCEPTION
            'Modeled Entity type is unavailable for this Workflow Run';
    ELSIF num_nonnulls(
        p_mapping_operation,
        p_mapping_coverage_mode,
        p_mapping_artifact_type,
        p_mapping_source_system_id,
        p_mapping_object_output_template_id,
        p_mapping_attribute_output_template_id
    ) <> 0 THEN
        RAISE EXCEPTION
            'Mapping inputs are unavailable for this Workflow Run';
    END IF;

    IF p_requested_batch_id IS NOT NULL THEN
        v_requested_batch_id := btrim(p_requested_batch_id);
        IF p_model_workflow NOT IN ('profiling', 'analysis')
           OR NOT reference.is_nonblank(v_requested_batch_id)
           OR octet_length(v_requested_batch_id) > 500 THEN
            RAISE EXCEPTION
                'Requested batch ID is invalid for this Workflow Run';
        END IF;
    END IF;
    IF p_prompt_overrides IS NULL
       OR jsonb_typeof(p_prompt_overrides) <> 'object'
       OR octet_length(p_prompt_overrides::TEXT) > 32768 THEN
        RAISE EXCEPTION 'Run prompt overrides must be a bounded JSON object';
    END IF;

    SELECT target_model.tenant_id,
           target_model.model_revision,
           target_model.default_agent_sdk_code,
           target_model.default_agent_provider_code,
           target_model.default_agent_model_code,
           target_model.default_reasoning_effort_code,
           target_model.default_max_turns,
           target_model.default_validation_retry_count
      INTO v_model
      FROM model.model AS target_model
     WHERE target_model.model_id = p_model_id
       AND target_model.is_active
     FOR UPDATE OF target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run Model is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_model.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Workflow Run creation denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    SELECT identity.entra_principal_identity_id
      INTO v_actor_entra_principal_identity_id
      FROM security.entra_principal_identity AS identity
     WHERE identity.principal_id = v_decision.principal_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.is_active
     FOR SHARE OF identity;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run actor identity is unavailable';
    END IF;

    IF p_mapping_object_output_template_id IS NOT NULL THEN
        SELECT template.output_template_schema_digest
          INTO v_mapping_object_output_template_schema_digest
          FROM application.output_template AS template
         WHERE template.output_template_id =
               p_mapping_object_output_template_id
           AND template.output_template_target_type = 'mapping_object'
           AND template.is_active
           AND EXISTS (
               SELECT 1
                 FROM application.output_template_field AS field
                WHERE field.output_template_id = template.output_template_id
           )
         FOR SHARE OF template;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Selected Mapping Object output template is unavailable';
        END IF;
    END IF;

    IF p_mapping_attribute_output_template_id IS NOT NULL THEN
        SELECT template.output_template_schema_digest
          INTO v_mapping_attribute_output_template_schema_digest
          FROM application.output_template AS template
         WHERE template.output_template_id =
               p_mapping_attribute_output_template_id
           AND template.output_template_target_type = 'mapping_attribute'
           AND template.is_active
           AND EXISTS (
               SELECT 1
                 FROM application.output_template_field AS field
                WHERE field.output_template_id = template.output_template_id
           )
         FOR SHARE OF template;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Selected Mapping Attribute output template is unavailable';
        END IF;
    END IF;

    v_request_digest := encode(
        sha256(
            convert_to(
                jsonb_build_object(
                    'model_id', p_model_id,
                    'expected_model_revision', p_expected_model_revision,
                    'model_workflow', p_model_workflow,
                    'workflow_execution_mode', p_workflow_execution_mode,
                    'agent_sdk_code', p_agent_sdk_code,
                    'agent_provider_code', p_agent_provider_code,
                    'agent_model_code', p_agent_model_code,
                    'reasoning_effort_code', p_reasoning_effort_code,
                    'max_turns', p_max_turns,
                    'validation_retry_count', p_validation_retry_count,
                    'modeled_entity_type', p_modeled_entity_type,
                    'code_generation_coverage_mode',
                        p_code_generation_coverage_mode,
                    'sql_generation_guide_version_id',
                        p_sql_generation_guide_version_id,
                    'requested_batch_id', v_requested_batch_id,
                    'mapping_operation', p_mapping_operation,
                    'mapping_coverage_mode', p_mapping_coverage_mode,
                    'mapping_artifact_type', p_mapping_artifact_type,
                    'mapping_source_system_id', p_mapping_source_system_id,
                    'mapping_profile_key', v_mapping_profile_key,
                    'mapping_profile_version', v_mapping_profile_version,
                    'mapping_profile_schema_digest',
                        v_mapping_profile_schema_digest,
                    'mapping_object_output_template_id',
                        p_mapping_object_output_template_id,
                    'mapping_object_output_template_schema_digest',
                        v_mapping_object_output_template_schema_digest,
                    'mapping_attribute_output_template_id',
                        p_mapping_attribute_output_template_id,
                    'mapping_attribute_output_template_schema_digest',
                        v_mapping_attribute_output_template_schema_digest,
                    'selected_scope_digest',
                        btrim(v_caller_selected_scope_digest::TEXT),
                    'selected_scope_count', v_caller_selected_scope_count,
                    'prompt_overrides', p_prompt_overrides
                )::TEXT,
                'UTF8'
            )
        ),
        'hex'
    );

    SELECT run.*
      INTO v_existing
      FROM application.workflow_run AS run
     WHERE run.correlation_id = p_correlation_id
     FOR UPDATE OF run;
    IF FOUND THEN
        IF v_existing.model_id <> p_model_id
           OR v_existing.actor_principal_id <> v_decision.principal_id
           OR v_existing.actor_entra_principal_identity_id IS DISTINCT FROM
              v_actor_entra_principal_identity_id
           OR v_existing.workflow_run_request_digest IS DISTINCT FROM
              v_request_digest THEN
            RAISE EXCEPTION 'Workflow Run correlation conflict';
        END IF;

        SELECT count(*)::INTEGER
          INTO v_prompt_snapshot_count
          FROM application.workflow_run_prompt_snapshot AS snapshot
         WHERE snapshot.workflow_run_id = v_existing.workflow_run_id;

        RETURN QUERY SELECT
            FALSE,
            NULL::VARCHAR(50),
            v_existing.workflow_run_id,
            v_existing.workflow_run_state,
            v_existing.correlation_id,
            v_prompt_snapshot_count,
            v_existing.created_time,
            v_existing.model_revision,
            v_existing.selected_scope_digest,
            v_existing.selected_scope_count,
            v_existing.code_generation_coverage_mode,
            v_existing.sql_generation_guide_id,
            v_existing.sql_generation_guide_version_id,
            v_existing.sql_generation_guide_digest;
        RETURN;
    END IF;

    IF p_expected_model_revision IS NULL
       OR v_model.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    IF p_model_workflow = 'code_generation' THEN
        IF p_code_generation_coverage_mode = 'all_eligible_targets' THEN
            SELECT coalesce(
                       array_agg(context.object_id ORDER BY context.object_id),
                       ARRAY[]::BIGINT[]
                   ),
                   count(*)::INTEGER
              INTO v_selected_object_ids,
                   v_selected_scope_count
              FROM workflow.list_code_generation_target_context(
                       p_model_id,
                       p_modeled_entity_type
                   ) AS context;
            IF v_selected_scope_count NOT BETWEEN 1 AND 50000 THEN
                RAISE EXCEPTION
                    'Code Generation has no bounded eligible target set';
            END IF;
            v_selected_scope_digest := encode(
                sha256(
                    convert_to(
                        array_to_string(v_selected_object_ids, ','),
                        'UTF8'
                    )
                ),
                'hex'
            );
        ELSE
            SELECT count(*)::INTEGER
              INTO v_eligible_scope_count
              FROM workflow.list_code_generation_target_context(
                       p_model_id,
                       p_modeled_entity_type
                   ) AS context
             WHERE context.object_id = ANY(v_selected_object_ids);
            IF v_eligible_scope_count <> v_selected_scope_count THEN
                RAISE EXCEPTION
                    'Selected Code Generation target lacks complete applied SQL Mapping';
            END IF;
        END IF;

        IF p_sql_generation_guide_version_id IS NULL THEN
            SELECT guide.sql_generation_guide_id,
                   version.sql_generation_guide_version_id,
                   version.sql_generation_guide_digest
              INTO v_sql_generation_guide_id,
                   v_sql_generation_guide_version_id,
                   v_sql_generation_guide_digest
              FROM application.sql_generation_guide AS guide
              JOIN application.sql_generation_guide_version AS version
                ON version.sql_generation_guide_id =
                   guide.sql_generation_guide_id
               AND version.sql_generation_guide_version_status = 'published'
             WHERE guide.is_default
               AND guide.is_active
             ORDER BY version.sql_generation_guide_version_number DESC,
                      version.sql_generation_guide_version_id DESC
             LIMIT 1
             FOR SHARE OF guide, version;
        ELSE
            SELECT guide.sql_generation_guide_id,
                   version.sql_generation_guide_version_id,
                   version.sql_generation_guide_digest
              INTO v_sql_generation_guide_id,
                   v_sql_generation_guide_version_id,
                   v_sql_generation_guide_digest
              FROM application.sql_generation_guide_version AS version
              JOIN application.sql_generation_guide AS guide
                ON guide.sql_generation_guide_id =
                   version.sql_generation_guide_id
             WHERE version.sql_generation_guide_version_id =
                   p_sql_generation_guide_version_id
               AND version.sql_generation_guide_version_status = 'published'
               AND guide.is_active
             FOR SHARE OF version, guide;
        END IF;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Active published SQL generation guide is required';
        END IF;
    END IF;

    IF p_model_workflow = 'mapping' THEN
        SELECT count(*)::INTEGER,
               count(DISTINCT mapping.modeled_entity_type)::INTEGER,
               count(*) FILTER (
                   WHERE mapping.object_mapping_status <> 'active'
                      OR NOT EXISTS (
                          SELECT 1
                            FROM workflow.mapping_source_system_dependency
                                 AS dependency
                           WHERE dependency.model_id = mapping.model_id
                             AND dependency.modeled_entity_type =
                                 mapping.modeled_entity_type
                             AND dependency.source_system_id =
                                 mapping.source_system_id
                             AND dependency.mapping_source_system_dependency_status =
                                 'active'
                      )
                      OR NOT EXISTS (
                          SELECT 1
                            FROM core.system AS source_system
                           WHERE source_system.system_id = mapping.source_system_id
                             AND source_system.is_active
                      )
                      OR (
                          mapping.modeled_entity_type = 'logical_entity'
                          AND NOT EXISTS (
                              SELECT 1
                                FROM workflow.logical_entity AS entity
                               WHERE entity.logical_entity_id =
                                     mapping.logical_entity_id
                                 AND entity.model_id = mapping.model_id
                                 AND entity.logical_entity_status = 'active'
                          )
                      )
                      OR (
                          mapping.modeled_entity_type = 'dimensional_entity'
                          AND NOT EXISTS (
                              SELECT 1
                                FROM workflow.dimensional_entity AS entity
                               WHERE entity.dimensional_entity_id =
                                     mapping.dimensional_entity_id
                                 AND entity.model_id = mapping.model_id
                                 AND entity.dimensional_entity_status = 'active'
                          )
                      )
                      OR (
                          mapping.object_mapping_is_locked
                          AND mapping.mapping_profile_key IS NULL
                      )
                      OR EXISTS (
                          SELECT 1
                            FROM workflow.mapping_attribute AS child
                           WHERE child.model_id = mapping.model_id
                             AND child.mapping_object_id =
                                 mapping.mapping_object_id
                             AND child.attribute_mapping_status = 'active'
                             AND child.attribute_mapping_transformation_document
                                 IS NULL
                             AND (
                                 child.attribute_mapping_is_locked
                                 OR mapping.object_mapping_is_locked
                             )
                      )
               )::INTEGER,
               min(mapping.modeled_entity_type)
          INTO v_mapping_header_count,
               v_mapping_header_layer_count,
               v_mapping_invalid_header_count,
               v_modeled_entity_type
          FROM workflow.mapping_object AS mapping
         WHERE mapping.model_id = p_model_id
           AND mapping.object_id = v_selected_object_ids[1]
           AND mapping.source_system_id = p_mapping_source_system_id;

        IF v_mapping_header_count = 0 THEN
            RAISE EXCEPTION
                'Selected Mapping target has no preregistered header';
        END IF;
        IF v_mapping_header_layer_count <> 1 THEN
            RAISE EXCEPTION
                'Selected Mapping target contains mixed modeled layers';
        END IF;
        IF v_mapping_invalid_header_count <> 0 THEN
            RAISE EXCEPTION
                'Selected Mapping target contains an unavailable or locked header';
        END IF;

        SELECT eligible.zone_code
          INTO v_mapping_zone_code
          FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
         WHERE eligible.object_id = v_selected_object_ids[1];
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Selected Mapping target is unavailable';
        END IF;

        IF v_modeled_entity_type = 'logical_entity'
           AND v_mapping_zone_code = 'silver' THEN
            v_mapping_route := 'logical_to_silver';
        ELSIF v_modeled_entity_type = 'dimensional_entity'
              AND v_mapping_zone_code = 'gold' THEN
            v_mapping_route := 'dimensional_to_gold';
        ELSE
            RAISE EXCEPTION
                'Selected Mapping target has a mixed or wrong-zone route';
        END IF;
    END IF;

    SELECT count(*)::INTEGER
      INTO v_eligible_scope_count
      FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
     WHERE eligible.object_id = ANY(v_selected_object_ids)
       AND CASE
               WHEN p_model_workflow IN (
                   'profiling', 'analysis', 'conceptual', 'logical'
               ) THEN eligible.is_bronze_source_eligible
               WHEN p_model_workflow = 'dimensional' THEN
                   eligible.is_dimensional_source_eligible
               WHEN p_model_workflow = 'mapping'
                    AND v_modeled_entity_type = 'logical_entity' THEN
                   eligible.is_logical_mapping_target_eligible
               WHEN p_model_workflow = 'mapping'
                    AND v_modeled_entity_type = 'dimensional_entity' THEN
                   eligible.is_dimensional_mapping_target_eligible
               WHEN p_model_workflow = 'code_generation'
                    AND p_modeled_entity_type = 'logical_entity' THEN
                   eligible.is_logical_mapping_target_eligible
               WHEN p_model_workflow = 'code_generation'
                    AND p_modeled_entity_type = 'dimensional_entity' THEN
                   eligible.is_dimensional_mapping_target_eligible
               ELSE FALSE
           END;
    IF v_eligible_scope_count <> v_selected_scope_count THEN
        RAISE EXCEPTION
            'Selected Scope contains an unavailable or ineligible Object';
    END IF;

    IF v_requested_batch_id IS NOT NULL THEN
        SELECT count(DISTINCT eligible.system_id)::INTEGER
          INTO v_selected_system_count
          FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
         WHERE eligible.object_id = ANY(v_selected_object_ids)
           AND eligible.is_bronze_source_eligible;
        IF v_selected_system_count <> 1 THEN
            RAISE EXCEPTION
                'Requested batch ID requires Selected Scope from one System';
        END IF;
    END IF;

    v_is_agentic := p_model_workflow = 'code_generation'
        OR p_workflow_execution_mode IS NOT NULL;
    v_agent_input_count := num_nonnulls(
        p_agent_sdk_code,
        p_agent_provider_code,
        p_agent_model_code,
        p_reasoning_effort_code,
        p_max_turns,
        p_validation_retry_count
    );

    IF v_is_agentic THEN
        IF v_agent_input_count = 0 THEN
            IF num_nonnulls(
                v_model.default_agent_sdk_code,
                v_model.default_agent_provider_code,
                v_model.default_agent_model_code,
                v_model.default_reasoning_effort_code,
                v_model.default_max_turns,
                v_model.default_validation_retry_count
            ) <> 6 THEN
                RAISE EXCEPTION 'Agent configuration is required for this Workflow Run';
            END IF;
            v_agent_sdk_code := v_model.default_agent_sdk_code;
            v_agent_provider_code := v_model.default_agent_provider_code;
            v_agent_model_code := v_model.default_agent_model_code;
            v_reasoning_effort_code := v_model.default_reasoning_effort_code;
            v_max_turns := v_model.default_max_turns;
            v_validation_retry_count := v_model.default_validation_retry_count;
        ELSIF v_agent_input_count = 6 THEN
            v_agent_sdk_code := p_agent_sdk_code;
            v_agent_provider_code := p_agent_provider_code;
            v_agent_model_code := p_agent_model_code;
            v_reasoning_effort_code := p_reasoning_effort_code;
            v_max_turns := p_max_turns;
            v_validation_retry_count := p_validation_retry_count;
        ELSE
            RAISE EXCEPTION 'Agent configuration override must be complete';
        END IF;
    ELSE
        IF v_agent_input_count <> 0 THEN
            RAISE EXCEPTION 'Deterministic Workflow Run cannot use agent configuration';
        END IF;
        IF p_prompt_overrides <> '{}'::JSONB THEN
            RAISE EXCEPTION 'Deterministic Workflow Run cannot use prompt overrides';
        END IF;
    END IF;

    INSERT INTO application.workflow_run AS run (
        tenant_id,
        model_id,
        model_revision,
        model_workflow,
        workflow_execution_mode,
        actor_principal_id,
        actor_entra_principal_identity_id,
        agent_sdk_code,
        agent_provider_code,
        agent_model_code,
        reasoning_effort_code,
        max_turns,
        validation_retry_count,
        modeled_entity_type,
        code_generation_coverage_mode,
        sql_generation_guide_id,
        sql_generation_guide_version_id,
        sql_generation_guide_digest,
        requested_batch_id,
        mapping_operation,
        mapping_coverage_mode,
        mapping_artifact_type,
        mapping_route,
        mapping_profile_key,
        mapping_profile_version,
        mapping_profile_schema_digest,
        mapping_object_output_template_id,
        mapping_object_output_template_schema_digest,
        mapping_attribute_output_template_id,
        mapping_attribute_output_template_schema_digest,
        selected_scope_digest,
        selected_scope_count,
        correlation_id,
        workflow_run_request_digest
    ) VALUES (
        v_model.tenant_id,
        p_model_id,
        v_model.model_revision,
        p_model_workflow,
        p_workflow_execution_mode,
        v_decision.principal_id,
        v_actor_entra_principal_identity_id,
        v_agent_sdk_code,
        v_agent_provider_code,
        v_agent_model_code,
        v_reasoning_effort_code,
        v_max_turns,
        v_validation_retry_count,
        v_modeled_entity_type,
        p_code_generation_coverage_mode,
        v_sql_generation_guide_id,
        v_sql_generation_guide_version_id,
        v_sql_generation_guide_digest,
        v_requested_batch_id,
        p_mapping_operation,
        p_mapping_coverage_mode,
        p_mapping_artifact_type,
        v_mapping_route,
        CASE WHEN p_model_workflow = 'mapping'
             THEN v_mapping_profile_key END,
        CASE WHEN p_model_workflow = 'mapping'
             THEN v_mapping_profile_version END,
        CASE WHEN p_model_workflow = 'mapping'
             THEN v_mapping_profile_schema_digest END,
        p_mapping_object_output_template_id,
        v_mapping_object_output_template_schema_digest,
        p_mapping_attribute_output_template_id,
        v_mapping_attribute_output_template_schema_digest,
        v_selected_scope_digest,
        v_selected_scope_count,
        p_correlation_id,
        v_request_digest
    )
    RETURNING run.* INTO v_created;

    INSERT INTO application.workflow_run_object_selection (
        workflow_run_id,
        model_id,
        object_id,
        selection_order
    )
    SELECT v_created.workflow_run_id,
           v_created.model_id,
           selected.object_id,
           selected.selection_order::INTEGER
      FROM unnest(v_selected_object_ids) WITH ORDINALITY
           AS selected(object_id, selection_order);

    IF p_model_workflow = 'mapping' THEN
        INSERT INTO application.workflow_run_mapping_target_selection (
            workflow_run_id,
            model_id,
            object_id,
            source_system_id,
            selection_order
        ) VALUES (
            v_created.workflow_run_id,
            v_created.model_id,
            v_selected_object_ids[1],
            p_mapping_source_system_id,
            1
        );
    END IF;

    IF v_is_agentic THEN
        v_prompt_snapshot_count := application.snapshot_workflow_run_prompts(
            v_created.workflow_run_id,
            p_prompt_overrides
        );
    END IF;

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_created.workflow_run_id,
        v_created.workflow_run_state,
        v_created.correlation_id,
        v_prompt_snapshot_count,
        v_created.created_time,
        v_created.model_revision,
        v_created.selected_scope_digest,
        v_created.selected_scope_count,
        v_created.code_generation_coverage_mode,
        v_created.sql_generation_guide_id,
        v_created.sql_generation_guide_version_id,
        v_created.sql_generation_guide_digest;
END;
$create_workflow_run$;

REVOKE ALL ON FUNCTION application.create_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER,
    BIGINT[],
    VARCHAR,
    VARCHAR,
    UUID,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT
) FROM PUBLIC;

CREATE FUNCTION application.lock_authoring_workflow_run(
    p_workflow_run_id BIGINT,
    p_model_id BIGINT
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_workflow VARCHAR(30),
    workflow_execution_mode VARCHAR(50),
    actor_principal_id BIGINT,
    workflow_run_state VARCHAR(30),
    correlation_id UUID
)
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $lock_authoring_workflow_run$
    SELECT run.workflow_run_id,
           run.model_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.actor_principal_id,
           run.workflow_run_state,
           run.correlation_id
      FROM application.workflow_run AS run
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.model_id = p_model_id
       AND run.model_workflow IN (
               'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
           )
       AND run.workflow_execution_mode IS NOT NULL
     FOR UPDATE OF run
$lock_authoring_workflow_run$;

REVOKE ALL ON FUNCTION application.lock_authoring_workflow_run(
    BIGINT,
    BIGINT
) FROM PUBLIC;

CREATE FUNCTION application.start_workflow_run(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    started_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $start_workflow_run$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_started_time TIMESTAMPTZ;
    v_constraint_name TEXT;
BEGIN
    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.workflow_run_state,
           run.correlation_id,
           run.model_workflow,
           run.started_time,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Workflow Run start denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;

    IF v_run.workflow_run_state <> 'queued' THEN
        RETURN QUERY SELECT
            FALSE,
            v_run.workflow_run_id,
            v_run.workflow_run_state,
            v_run.started_time;
        RETURN;
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM application.workflow_run AS active_run
         WHERE active_run.tenant_id = v_run.tenant_id
           AND active_run.workflow_run_state = 'running'
           AND active_run.workflow_run_id <> v_run.workflow_run_id
    ) THEN
        RAISE EXCEPTION 'tenant_workflow_conflict';
    END IF;

    v_started_time := clock_timestamp();
    BEGIN
        UPDATE application.workflow_run AS run
           SET workflow_run_state = 'running',
               started_time = v_started_time,
               updated_time = v_started_time,
               updated_by = CURRENT_USER
         WHERE run.workflow_run_id = p_workflow_run_id;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_constraint_name = CONSTRAINT_NAME;
        IF v_constraint_name = 'uq_workflow_run_running_tenant' THEN
            RAISE EXCEPTION 'tenant_workflow_conflict';
        END IF;
        RAISE;
    END;

    INSERT INTO model.model_event_log (
        model_id,
        correlation_id,
        workflow_run_id,
        model_event_log_sequence,
        model_event_log_attempt,
        model_workflow,
        model_event_log_stage,
        model_event_log_status,
        model_event_log_message,
        finding_count
    ) VALUES (
        v_run.model_id,
        v_run.correlation_id,
        v_run.workflow_run_id,
        1,
        1,
        v_run.model_workflow,
        'workflow_run',
        'started',
        'Workflow run started.',
        0
    );

    RETURN QUERY SELECT
        TRUE,
        v_run.workflow_run_id,
        'running'::VARCHAR(30),
        v_started_time;
END;
$start_workflow_run$;

REVOKE ALL ON FUNCTION application.start_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) FROM PUBLIC;

CREATE FUNCTION application.claim_next_workflow_run(
    p_lease_duration_seconds INTEGER
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    tenant_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    model_workflow VARCHAR(30),
    workflow_execution_mode VARCHAR(50),
    correlation_id UUID,
    actor_principal_type VARCHAR(30),
    actor_entra_tenant_id UUID,
    actor_entra_object_id UUID,
    workflow_run_claim_token UUID,
    workflow_run_claimed_time TIMESTAMPTZ,
    workflow_run_claim_expires_time TIMESTAMPTZ,
    workflow_run_recovery_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $claim_next_workflow_run$
DECLARE
    v_claim_token UUID;
    v_claimed_time TIMESTAMPTZ;
BEGIN
    IF p_lease_duration_seconds IS NULL
       OR p_lease_duration_seconds NOT BETWEEN 1 AND 300 THEN
        RAISE EXCEPTION 'Workflow Run lease duration must be between 1 and 300 seconds';
    END IF;

    v_claim_token := gen_random_uuid();
    v_claimed_time := clock_timestamp();

    RETURN QUERY
    WITH invalid AS (
        SELECT run.workflow_run_id,
               run.model_id,
               run.correlation_id,
               run.model_workflow,
               coalesce(event.maximum_attempt, 1) AS event_attempt,
               coalesce(event.maximum_sequence, 0) + 1 AS event_sequence
          FROM application.workflow_run AS run
          LEFT JOIN model.model AS target_model
            ON target_model.model_id = run.model_id
           AND target_model.tenant_id = run.tenant_id
          LEFT JOIN security.principal AS actor
            ON actor.principal_id = run.actor_principal_id
          LEFT JOIN LATERAL (
              SELECT count(*) AS active_identity_count
                FROM security.entra_principal_identity AS identity
               WHERE identity.principal_id = run.actor_principal_id
                 AND identity.principal_type = actor.principal_type
                 AND identity.is_active
                 AND (
                     run.actor_entra_principal_identity_id IS NULL
                     OR identity.entra_principal_identity_id =
                        run.actor_entra_principal_identity_id
                 )
          ) AS identity_context ON TRUE
          LEFT JOIN LATERAL (
              SELECT max(log.model_event_log_attempt) AS maximum_attempt,
                     max(log.model_event_log_sequence) AS maximum_sequence
                FROM model.model_event_log AS log
               WHERE log.workflow_run_id = run.workflow_run_id
          ) AS event ON TRUE
         WHERE run.workflow_run_state = 'running'
           AND (
               target_model.model_id IS NULL
               OR NOT target_model.is_active
               OR actor.principal_id IS NULL
               OR NOT actor.is_active
               OR identity_context.active_identity_count <> 1
           )
         ORDER BY run.created_time, run.workflow_run_id
         FOR UPDATE OF run SKIP LOCKED
         LIMIT 100
    ),
    invalid_failed AS (
        UPDATE application.workflow_run AS run
           SET workflow_run_state = 'failed',
               completed_time = v_claimed_time,
               failure_code = 'workflow_run_context_unavailable',
               failure_message =
                   'Workflow Run execution context is unavailable.',
               workflow_run_claim_token_digest = NULL,
               workflow_run_claimed_time = NULL,
               workflow_run_claim_heartbeat_time = NULL,
               workflow_run_claim_expires_time = NULL,
               updated_time = v_claimed_time,
               updated_by = CURRENT_USER
          FROM invalid
         WHERE run.workflow_run_id = invalid.workflow_run_id
        RETURNING run.workflow_run_id,
                  run.model_id,
                  run.correlation_id,
                  run.model_workflow
    ),
    invalid_failure_events AS (
        INSERT INTO model.model_event_log (
            model_id,
            correlation_id,
            workflow_run_id,
            model_event_log_sequence,
            model_event_log_attempt,
            model_workflow,
            model_event_log_stage,
            model_event_log_status,
            model_event_log_message,
            finding_count,
            created_time
        )
        SELECT invalid_failed.model_id,
               invalid_failed.correlation_id,
               invalid_failed.workflow_run_id,
               invalid.event_sequence,
               invalid.event_attempt,
               invalid_failed.model_workflow,
               'workflow_run',
               'failed',
               'Workflow Run execution context is unavailable.',
               0,
               v_claimed_time
          FROM invalid_failed
          JOIN invalid
            ON invalid.workflow_run_id = invalid_failed.workflow_run_id
        RETURNING model_event_log_id
    ),
    exhausted AS (
        SELECT run.workflow_run_id,
               run.model_id,
               run.correlation_id,
               run.model_workflow,
               coalesce(event.maximum_attempt, 1) AS event_attempt,
               coalesce(event.maximum_sequence, 0) + 1 AS event_sequence
          FROM application.workflow_run AS run
          LEFT JOIN LATERAL (
              SELECT max(log.model_event_log_attempt) AS maximum_attempt,
                     max(log.model_event_log_sequence) AS maximum_sequence
                FROM model.model_event_log AS log
               WHERE log.workflow_run_id = run.workflow_run_id
          ) AS event ON TRUE
         WHERE run.workflow_run_state = 'running'
           AND NOT EXISTS (
               SELECT 1
                 FROM invalid_failed
                WHERE invalid_failed.workflow_run_id = run.workflow_run_id
           )
           AND run.workflow_run_claim_token_digest IS NOT NULL
           AND run.workflow_run_claim_expires_time <= v_claimed_time
           AND run.workflow_run_recovery_count >= 5
         ORDER BY run.created_time, run.workflow_run_id
         FOR UPDATE OF run SKIP LOCKED
         LIMIT 100
    ),
    failed AS (
        UPDATE application.workflow_run AS run
           SET workflow_run_state = 'failed',
               completed_time = v_claimed_time,
               failure_code = 'workflow_run_recovery_exhausted',
               failure_message = 'Workflow Run recovery limit exhausted.',
               workflow_run_claim_token_digest = NULL,
               workflow_run_claimed_time = NULL,
               workflow_run_claim_heartbeat_time = NULL,
               workflow_run_claim_expires_time = NULL,
               updated_time = v_claimed_time,
               updated_by = CURRENT_USER
          FROM exhausted
         WHERE run.workflow_run_id = exhausted.workflow_run_id
        RETURNING run.workflow_run_id,
                  run.model_id,
                  run.correlation_id,
                  run.model_workflow
    ),
    failure_events AS (
        INSERT INTO model.model_event_log (
            model_id,
            correlation_id,
            workflow_run_id,
            model_event_log_sequence,
            model_event_log_attempt,
            model_workflow,
            model_event_log_stage,
            model_event_log_status,
            model_event_log_message,
            finding_count,
            created_time
        )
        SELECT failed.model_id,
               failed.correlation_id,
               failed.workflow_run_id,
               exhausted.event_sequence,
               exhausted.event_attempt,
               failed.model_workflow,
               'workflow_run',
               'failed',
               'Workflow Run recovery limit exhausted.',
               0,
               v_claimed_time
          FROM failed
          JOIN exhausted
            ON exhausted.workflow_run_id = failed.workflow_run_id
        RETURNING model_event_log_id
    ),
    candidate AS (
        SELECT run.workflow_run_id,
               target_model.tenant_id,
               run.model_id,
               run.model_revision,
               run.model_workflow,
               run.workflow_execution_mode,
               run.correlation_id,
               actor.principal_type AS actor_principal_type,
               actor_identity.entra_tenant_id AS actor_entra_tenant_id,
               actor_identity.entra_object_id AS actor_entra_object_id,
               run.workflow_run_claim_token_digest IS NOT NULL AS is_recovery
          FROM application.workflow_run AS run
          JOIN model.model AS target_model
            ON target_model.model_id = run.model_id
           AND target_model.is_active
          JOIN security.principal AS actor
            ON actor.principal_id = run.actor_principal_id
           AND actor.is_active
          JOIN security.entra_principal_identity AS actor_identity
            ON actor_identity.principal_id = actor.principal_id
           AND actor_identity.principal_type = actor.principal_type
           AND actor_identity.is_active
           AND (
               run.actor_entra_principal_identity_id IS NULL
               OR actor_identity.entra_principal_identity_id =
                   run.actor_entra_principal_identity_id
           )
         WHERE run.workflow_run_state = 'running'
           AND NOT EXISTS (
               SELECT 1
                 FROM invalid_failed
                WHERE invalid_failed.workflow_run_id = run.workflow_run_id
           )
           AND (
               run.actor_entra_principal_identity_id IS NOT NULL
               OR NOT EXISTS (
                   SELECT 1
                     FROM security.entra_principal_identity AS other_identity
                    WHERE other_identity.principal_id = actor.principal_id
                      AND other_identity.principal_type = actor.principal_type
                      AND other_identity.is_active
                      AND other_identity.entra_principal_identity_id <>
                          actor_identity.entra_principal_identity_id
               )
           )
           AND (
               run.workflow_run_claim_token_digest IS NULL
               OR run.workflow_run_claim_expires_time <= v_claimed_time
           )
           AND (
               run.workflow_run_claim_token_digest IS NULL
               OR run.workflow_run_recovery_count < 5
           )
         ORDER BY run.created_time, run.workflow_run_id
         FOR UPDATE OF run SKIP LOCKED
         LIMIT 1
    ),
    claimed AS (
        UPDATE application.workflow_run AS run
           SET workflow_run_claim_token_digest = encode(
                   sha256(convert_to(v_claim_token::TEXT, 'UTF8')),
                   'hex'
               ),
               workflow_run_claimed_time = v_claimed_time,
               workflow_run_claim_heartbeat_time = v_claimed_time,
               workflow_run_claim_expires_time = v_claimed_time
                   + make_interval(secs => p_lease_duration_seconds),
               workflow_run_recovery_count =
                   run.workflow_run_recovery_count
                   + candidate.is_recovery::INTEGER,
               updated_time = v_claimed_time,
               updated_by = CURRENT_USER
          FROM candidate
         WHERE run.workflow_run_id = candidate.workflow_run_id
        RETURNING run.workflow_run_id,
                  candidate.tenant_id,
                  candidate.model_id,
                  candidate.model_revision,
                  candidate.model_workflow,
                  candidate.workflow_execution_mode,
                  candidate.correlation_id,
                  candidate.actor_principal_type,
                  candidate.actor_entra_tenant_id,
                  candidate.actor_entra_object_id,
                  run.workflow_run_claimed_time,
                  run.workflow_run_claim_expires_time,
                  run.workflow_run_recovery_count
    )
    SELECT claimed.workflow_run_id,
           claimed.tenant_id,
           claimed.model_id,
           claimed.model_revision,
           claimed.model_workflow,
           claimed.workflow_execution_mode,
           claimed.correlation_id,
           claimed.actor_principal_type,
           claimed.actor_entra_tenant_id,
           claimed.actor_entra_object_id,
           v_claim_token,
           claimed.workflow_run_claimed_time,
           claimed.workflow_run_claim_expires_time,
           claimed.workflow_run_recovery_count
      FROM claimed;
END;
$claim_next_workflow_run$;

REVOKE ALL ON FUNCTION application.claim_next_workflow_run(INTEGER)
FROM PUBLIC;

-- Claim only one notebook-owned Workflow Run. Unlike the web worker claim,
-- this function never scans, skips to, or terminalizes any other Run.
CREATE FUNCTION application.claim_workflow_run_exact(
    p_workflow_run_id BIGINT,
    p_expected_model_workflow VARCHAR(30),
    p_lease_duration_seconds INTEGER
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    tenant_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    model_workflow VARCHAR(30),
    workflow_execution_mode VARCHAR(50),
    correlation_id UUID,
    actor_principal_type VARCHAR(30),
    actor_entra_tenant_id UUID,
    actor_entra_object_id UUID,
    workflow_run_claim_token UUID,
    workflow_run_claimed_time TIMESTAMPTZ,
    workflow_run_claim_expires_time TIMESTAMPTZ,
    workflow_run_recovery_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $claim_workflow_run_exact$
DECLARE
    v_principal RECORD;
    v_run RECORD;
    v_claim_token UUID;
    v_claimed_time TIMESTAMPTZ;
    v_event_attempt INTEGER;
    v_event_sequence BIGINT;
    v_is_recovery BOOLEAN;
BEGIN
    IF p_workflow_run_id IS NULL OR p_workflow_run_id <= 0 THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
    IF p_expected_model_workflow IS NULL
       OR p_expected_model_workflow NOT IN (
           'profiling', 'analysis', 'conceptual', 'logical',
           'dimensional', 'mapping', 'code_generation'
       ) THEN
        RAISE EXCEPTION 'Workflow Run claim Workflow is invalid';
    END IF;
    IF p_lease_duration_seconds IS NULL
       OR p_lease_duration_seconds NOT BETWEEN 1 AND 300 THEN
        RAISE EXCEPTION
            'Workflow Run lease duration must be between 1 and 300 seconds';
    END IF;

    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT run.workflow_run_id,
           run.tenant_id,
           run.model_id,
           run.model_revision,
           run.model_workflow,
           run.workflow_execution_mode,
           run.correlation_id,
           run.workflow_run_state,
           run.workflow_run_claim_token_digest,
           run.workflow_run_claim_expires_time,
           run.workflow_run_recovery_count,
           (
               target_model.model_id IS NOT NULL
               AND target_model.is_active
               AND actor.principal_id IS NOT NULL
               AND actor.is_active
               AND actor.principal_type = v_principal.principal_type
               AND actor_identity.entra_principal_identity_id IS NOT NULL
               AND actor_identity.is_active
           ) AS context_available
      INTO v_run
      FROM application.workflow_run AS run
      LEFT JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.tenant_id = run.tenant_id
      LEFT JOIN security.principal AS actor
        ON actor.principal_id = run.actor_principal_id
      LEFT JOIN security.entra_principal_identity AS actor_identity
        ON actor_identity.entra_principal_identity_id =
               run.actor_entra_principal_identity_id
       AND actor_identity.principal_id = run.actor_principal_id
       AND actor_identity.principal_type = actor.principal_type
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.model_workflow = p_expected_model_workflow
       AND run.actor_principal_id = v_principal.principal_id
       AND run.actor_entra_principal_identity_id =
           v_principal.entra_principal_identity_id
     FOR UPDATE OF run;
    IF NOT FOUND OR v_run.workflow_run_state <> 'running' THEN
        RETURN;
    END IF;

    v_claimed_time := clock_timestamp();
    SELECT coalesce(max(event.model_event_log_attempt), 1),
           coalesce(max(event.model_event_log_sequence), 0) + 1
      INTO v_event_attempt, v_event_sequence
      FROM model.model_event_log AS event
     WHERE event.workflow_run_id = p_workflow_run_id;

    IF NOT v_run.context_available THEN
        UPDATE application.workflow_run AS run
           SET workflow_run_state = 'failed',
               completed_time = v_claimed_time,
               failure_code = 'workflow_run_context_unavailable',
               failure_message =
                   'Workflow Run execution context is unavailable.',
               workflow_run_claim_token_digest = NULL,
               workflow_run_claimed_time = NULL,
               workflow_run_claim_heartbeat_time = NULL,
               workflow_run_claim_expires_time = NULL,
               updated_time = v_claimed_time,
               updated_by = CURRENT_USER
         WHERE run.workflow_run_id = p_workflow_run_id;

        INSERT INTO model.model_event_log (
            model_id,
            correlation_id,
            workflow_run_id,
            model_event_log_sequence,
            model_event_log_attempt,
            model_workflow,
            model_event_log_stage,
            model_event_log_status,
            model_event_log_message,
            finding_count,
            created_time
        ) VALUES (
            v_run.model_id,
            v_run.correlation_id,
            v_run.workflow_run_id,
            v_event_sequence,
            v_event_attempt,
            v_run.model_workflow,
            'workflow_run',
            'failed',
            'Workflow Run execution context is unavailable.',
            0,
            v_claimed_time
        );
        RETURN;
    END IF;

    IF v_run.workflow_run_claim_token_digest IS NOT NULL
       AND v_run.workflow_run_claim_expires_time > v_claimed_time THEN
        RETURN;
    END IF;

    IF v_run.workflow_run_claim_token_digest IS NOT NULL
       AND v_run.workflow_run_recovery_count >= 5 THEN
        UPDATE application.workflow_run AS run
           SET workflow_run_state = 'failed',
               completed_time = v_claimed_time,
               failure_code = 'workflow_run_recovery_exhausted',
               failure_message = 'Workflow Run recovery limit exhausted.',
               workflow_run_claim_token_digest = NULL,
               workflow_run_claimed_time = NULL,
               workflow_run_claim_heartbeat_time = NULL,
               workflow_run_claim_expires_time = NULL,
               updated_time = v_claimed_time,
               updated_by = CURRENT_USER
         WHERE run.workflow_run_id = p_workflow_run_id;

        INSERT INTO model.model_event_log (
            model_id,
            correlation_id,
            workflow_run_id,
            model_event_log_sequence,
            model_event_log_attempt,
            model_workflow,
            model_event_log_stage,
            model_event_log_status,
            model_event_log_message,
            finding_count,
            created_time
        ) VALUES (
            v_run.model_id,
            v_run.correlation_id,
            v_run.workflow_run_id,
            v_event_sequence,
            v_event_attempt,
            v_run.model_workflow,
            'workflow_run',
            'failed',
            'Workflow Run recovery limit exhausted.',
            0,
            v_claimed_time
        );
        RETURN;
    END IF;

    v_claim_token := gen_random_uuid();
    v_is_recovery := v_run.workflow_run_claim_token_digest IS NOT NULL;
    UPDATE application.workflow_run AS run
       SET workflow_run_claim_token_digest = encode(
               sha256(convert_to(v_claim_token::TEXT, 'UTF8')),
               'hex'
           ),
           workflow_run_claimed_time = v_claimed_time,
           workflow_run_claim_heartbeat_time = v_claimed_time,
           workflow_run_claim_expires_time = v_claimed_time
               + make_interval(secs => p_lease_duration_seconds),
           workflow_run_recovery_count = run.workflow_run_recovery_count
               + v_is_recovery::INTEGER,
           updated_time = v_claimed_time,
           updated_by = CURRENT_USER
     WHERE run.workflow_run_id = p_workflow_run_id;

    RETURN QUERY SELECT
        v_run.workflow_run_id,
        v_run.tenant_id,
        v_run.model_id,
        v_run.model_revision,
        v_run.model_workflow,
        v_run.workflow_execution_mode,
        v_run.correlation_id,
        v_principal.principal_type::VARCHAR(30),
        v_principal.entra_tenant_id,
        v_principal.entra_object_id,
        v_claim_token,
        v_claimed_time,
        v_claimed_time + make_interval(secs => p_lease_duration_seconds),
        v_run.workflow_run_recovery_count + v_is_recovery::INTEGER;
END;
$claim_workflow_run_exact$;

REVOKE ALL ON FUNCTION application.claim_workflow_run_exact(
    BIGINT,
    VARCHAR,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.renew_workflow_run_claim(
    p_workflow_run_id BIGINT,
    p_workflow_run_claim_token UUID,
    p_lease_duration_seconds INTEGER
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    workflow_run_claim_heartbeat_time TIMESTAMPTZ,
    workflow_run_claim_expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $renew_workflow_run_claim$
DECLARE
    v_heartbeat_time TIMESTAMPTZ;
BEGIN
    IF p_lease_duration_seconds IS NULL
       OR p_lease_duration_seconds NOT BETWEEN 1 AND 300 THEN
        RAISE EXCEPTION 'Workflow Run lease duration must be between 1 and 300 seconds';
    END IF;
    IF p_workflow_run_id IS NULL OR p_workflow_run_id <= 0
       OR p_workflow_run_claim_token IS NULL THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;

    v_heartbeat_time := clock_timestamp();
    RETURN QUERY
    UPDATE application.workflow_run AS run
       SET workflow_run_claim_heartbeat_time = v_heartbeat_time,
           workflow_run_claim_expires_time = v_heartbeat_time
               + make_interval(secs => p_lease_duration_seconds),
           updated_time = v_heartbeat_time,
           updated_by = CURRENT_USER
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.workflow_run_state = 'running'
       AND run.workflow_run_claim_token_digest = encode(
               sha256(
                   convert_to(p_workflow_run_claim_token::TEXT, 'UTF8')
               ),
               'hex'
           )
       AND run.workflow_run_claim_expires_time > v_heartbeat_time
    RETURNING run.workflow_run_id,
              run.workflow_run_claim_heartbeat_time,
              run.workflow_run_claim_expires_time;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
END;
$renew_workflow_run_claim$;

REVOKE ALL ON FUNCTION application.renew_workflow_run_claim(
    BIGINT,
    UUID,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.release_workflow_run_claim(
    p_workflow_run_id BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $release_workflow_run_claim$
DECLARE
    v_released BOOLEAN;
    v_released_time TIMESTAMPTZ;
BEGIN
    IF p_workflow_run_id IS NULL OR p_workflow_run_id <= 0
       OR p_workflow_run_claim_token IS NULL THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;

    v_released_time := clock_timestamp();
    UPDATE application.workflow_run AS run
       SET workflow_run_claim_token_digest = NULL,
           workflow_run_claimed_time = NULL,
           workflow_run_claim_heartbeat_time = NULL,
           workflow_run_claim_expires_time = NULL,
           updated_time = v_released_time,
           updated_by = CURRENT_USER
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.workflow_run_state = 'running'
       AND run.workflow_run_claim_token_digest = encode(
               sha256(
                   convert_to(p_workflow_run_claim_token::TEXT, 'UTF8')
               ),
               'hex'
           )
       AND run.workflow_run_claim_expires_time > v_released_time
    RETURNING TRUE INTO v_released;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
    RETURN v_released;
END;
$release_workflow_run_claim$;

REVOKE ALL ON FUNCTION application.release_workflow_run_claim(
    BIGINT,
    UUID
) FROM PUBLIC;

CREATE FUNCTION application.assert_workflow_run_claim(
    p_workflow_run_id BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS VOID
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $assert_workflow_run_claim$
DECLARE
    v_checked_time TIMESTAMPTZ;
BEGIN
    IF p_workflow_run_id IS NULL OR p_workflow_run_id <= 0
       OR p_workflow_run_claim_token IS NULL THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;

    v_checked_time := clock_timestamp();
    PERFORM 1
      FROM application.workflow_run AS run
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.workflow_run_state = 'running'
       AND run.workflow_run_claim_token_digest = encode(
               sha256(
                   convert_to(p_workflow_run_claim_token::TEXT, 'UTF8')
               ),
               'hex'
           )
       AND run.workflow_run_claim_expires_time > v_checked_time
     FOR UPDATE OF run;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
END;
$assert_workflow_run_claim$;

REVOKE ALL ON FUNCTION application.assert_workflow_run_claim(
    BIGINT,
    UUID
) FROM PUBLIC;

-- Notebook Workflow entry points derive the actor from SESSION_USER. The
-- caller supplies workflow intent only; editable notebook values never select
-- a Principal or Entra identity.
CREATE FUNCTION application.create_notebook_workflow_run(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_expected_model_revision BIGINT,
    p_model_workflow VARCHAR(30),
    p_workflow_execution_mode VARCHAR(50),
    p_agent_sdk_code VARCHAR(100),
    p_agent_provider_code VARCHAR(100),
    p_agent_model_code VARCHAR(200),
    p_reasoning_effort_code VARCHAR(50),
    p_max_turns INTEGER,
    p_validation_retry_count INTEGER,
    p_selected_object_ids BIGINT[],
    p_modeled_entity_type VARCHAR(30),
    p_requested_batch_id VARCHAR(500),
    p_correlation_id UUID,
    p_prompt_overrides JSONB,
    p_mapping_operation VARCHAR(20) DEFAULT NULL,
    p_mapping_coverage_mode VARCHAR(30) DEFAULT NULL,
    p_mapping_artifact_type VARCHAR(30) DEFAULT NULL,
    p_mapping_source_system_id BIGINT DEFAULT NULL,
    p_mapping_object_output_template_id BIGINT DEFAULT NULL,
    p_mapping_attribute_output_template_id BIGINT DEFAULT NULL,
    p_code_generation_coverage_mode VARCHAR(30) DEFAULT NULL,
    p_sql_generation_guide_version_id BIGINT DEFAULT NULL
)
RETURNS TABLE (
    created BOOLEAN,
    denial_code VARCHAR(50),
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    correlation_id UUID,
    prompt_snapshot_count INTEGER,
    created_time TIMESTAMPTZ,
    model_revision BIGINT,
    selected_scope_digest CHAR(64),
    selected_scope_count INTEGER,
    code_generation_coverage_mode VARCHAR(30),
    sql_generation_guide_id BIGINT,
    sql_generation_guide_version_id BIGINT,
    sql_generation_guide_digest CHAR(64)
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $create_notebook_workflow_run$
DECLARE
    v_principal RECORD;
BEGIN
    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Notebook runtime Principal is unavailable';
    END IF;
    IF p_tenant_id IS NULL OR p_tenant_id <= 0
       OR NOT EXISTS (
           SELECT 1
             FROM model.model AS target_model
            WHERE target_model.tenant_id = p_tenant_id
              AND target_model.model_id = p_model_id
              AND target_model.is_active
       ) THEN
        RAISE EXCEPTION 'Workflow Run Tenant/Model binding is unavailable';
    END IF;

    RETURN QUERY
    SELECT *
      FROM application.create_workflow_run(
          v_principal.entra_tenant_id,
          v_principal.entra_object_id,
          v_principal.principal_type,
          p_model_id,
          p_expected_model_revision,
          p_model_workflow,
          p_workflow_execution_mode,
          p_agent_sdk_code,
          p_agent_provider_code,
          p_agent_model_code,
          p_reasoning_effort_code,
          p_max_turns,
          p_validation_retry_count,
          p_selected_object_ids,
          p_modeled_entity_type,
          p_requested_batch_id,
          p_correlation_id,
          p_prompt_overrides,
          p_mapping_operation,
          p_mapping_coverage_mode,
          p_mapping_artifact_type,
          p_mapping_source_system_id,
          p_mapping_object_output_template_id,
          p_mapping_attribute_output_template_id,
          p_code_generation_coverage_mode,
          p_sql_generation_guide_version_id
      );
END;
$create_notebook_workflow_run$;

REVOKE ALL ON FUNCTION application.create_notebook_workflow_run(
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER,
    BIGINT[],
    VARCHAR,
    VARCHAR,
    UUID,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT
) FROM PUBLIC;

-- Starting and claiming are deliberately one database function call. A web
-- worker cannot observe a newly running Run before its exact claim is stored.
CREATE FUNCTION application.start_and_claim_notebook_workflow_run(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_expected_model_workflow VARCHAR(30),
    p_lease_duration_seconds INTEGER
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    tenant_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    model_workflow VARCHAR(30),
    workflow_execution_mode VARCHAR(50),
    correlation_id UUID,
    actor_principal_type VARCHAR(30),
    actor_entra_tenant_id UUID,
    actor_entra_object_id UUID,
    workflow_run_claim_token UUID,
    workflow_run_claimed_time TIMESTAMPTZ,
    workflow_run_claim_expires_time TIMESTAMPTZ,
    workflow_run_recovery_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $start_and_claim_notebook_workflow_run$
DECLARE
    v_principal RECORD;
    v_run RECORD;
    v_started RECORD;
BEGIN
    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RETURN;
    END IF;
    IF p_expected_model_workflow IS NULL
       OR p_expected_model_workflow NOT IN (
           'profiling', 'analysis', 'conceptual', 'logical',
           'dimensional', 'mapping', 'code_generation'
       ) THEN
        RAISE EXCEPTION 'Workflow Run claim Workflow is invalid';
    END IF;

    SELECT run.workflow_run_state,
           run.model_revision
      INTO v_run
      FROM application.workflow_run AS run
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.tenant_id = p_tenant_id
       AND run.model_id = p_model_id
       AND run.model_workflow = p_expected_model_workflow
       AND run.actor_principal_id = v_principal.principal_id
       AND run.actor_entra_principal_identity_id =
           v_principal.entra_principal_identity_id
     FOR UPDATE OF run;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    IF v_run.workflow_run_state = 'queued' THEN
        SELECT *
          INTO v_started
          FROM application.start_workflow_run(
              v_principal.entra_tenant_id,
              v_principal.entra_object_id,
              v_principal.principal_type,
              p_workflow_run_id,
              p_expected_model_revision
          );
        IF NOT FOUND OR v_started.workflow_run_state <> 'running' THEN
            RETURN;
        END IF;
    ELSIF v_run.workflow_run_state <> 'running' THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT *
      FROM application.claim_workflow_run_exact(
          p_workflow_run_id,
          p_expected_model_workflow,
          p_lease_duration_seconds
      );
END;
$start_and_claim_notebook_workflow_run$;

REVOKE ALL ON FUNCTION application.start_and_claim_notebook_workflow_run(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.renew_notebook_workflow_run_claim(
    p_workflow_run_id BIGINT,
    p_workflow_run_claim_token UUID,
    p_lease_duration_seconds INTEGER
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    workflow_run_claim_heartbeat_time TIMESTAMPTZ,
    workflow_run_claim_expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $renew_notebook_workflow_run_claim$
DECLARE
    v_principal RECORD;
BEGIN
    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
    PERFORM 1
      FROM application.workflow_run AS run
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.actor_principal_id = v_principal.principal_id
       AND run.actor_entra_principal_identity_id =
           v_principal.entra_principal_identity_id
     FOR UPDATE OF run;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;

    RETURN QUERY
    SELECT *
      FROM application.renew_workflow_run_claim(
          p_workflow_run_id,
          p_workflow_run_claim_token,
          p_lease_duration_seconds
      );
END;
$renew_notebook_workflow_run_claim$;

REVOKE ALL ON FUNCTION application.renew_notebook_workflow_run_claim(
    BIGINT,
    UUID,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.release_notebook_workflow_run_claim(
    p_workflow_run_id BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $release_notebook_workflow_run_claim$
DECLARE
    v_principal RECORD;
    v_released BOOLEAN;
BEGIN
    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
    PERFORM 1
      FROM application.workflow_run AS run
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.actor_principal_id = v_principal.principal_id
       AND run.actor_entra_principal_identity_id =
           v_principal.entra_principal_identity_id
     FOR UPDATE OF run;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;

    SELECT application.release_workflow_run_claim(
               p_workflow_run_id,
               p_workflow_run_claim_token
           )
      INTO v_released;
    RETURN v_released;
END;
$release_notebook_workflow_run_claim$;

REVOKE ALL ON FUNCTION application.release_notebook_workflow_run_claim(
    BIGINT,
    UUID
) FROM PUBLIC;

CREATE FUNCTION application.assert_notebook_workflow_run_claim(
    p_workflow_run_id BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS VOID
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $assert_notebook_workflow_run_claim$
DECLARE
    v_principal RECORD;
BEGIN
    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;
    PERFORM 1
      FROM application.workflow_run AS run
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.actor_principal_id = v_principal.principal_id
       AND run.actor_entra_principal_identity_id =
           v_principal.entra_principal_identity_id
     FOR UPDATE OF run;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run claim is unavailable';
    END IF;

    PERFORM application.assert_workflow_run_claim(
        p_workflow_run_id,
        p_workflow_run_claim_token
    );
END;
$assert_notebook_workflow_run_claim$;

REVOKE ALL ON FUNCTION application.assert_notebook_workflow_run_claim(
    BIGINT,
    UUID
) FROM PUBLIC;

CREATE FUNCTION application.append_workflow_run_event(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_event_sequence BIGINT,
    p_attempt INTEGER,
    p_stage_code VARCHAR(100),
    p_status VARCHAR(30),
    p_safe_message VARCHAR(2000),
    p_current_count INTEGER,
    p_total_count INTEGER,
    p_finding_count INTEGER
)
RETURNS SETOF model.model_event_log
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $append_workflow_run_event$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_existing model.model_event_log%ROWTYPE;
    v_event model.model_event_log%ROWTYPE;
    v_expected_sequence BIGINT;
    v_percent NUMERIC(5, 2);
    v_max_attempt INTEGER;
BEGIN
    IF p_event_sequence IS NULL OR p_event_sequence <= 1 THEN
        RAISE EXCEPTION 'Workflow Run event sequence must follow the start event';
    END IF;
    IF p_stage_code IS NULL
       OR p_stage_code !~ '^[a-z][a-z0-9_.-]{0,99}$' THEN
        RAISE EXCEPTION 'Workflow Run event stage is invalid';
    END IF;
    IF p_status IS NULL
       OR p_status NOT IN ('running', 'warning', 'blocked') THEN
        RAISE EXCEPTION 'Workflow Run event status is invalid';
    END IF;
    IF p_attempt IS NULL THEN
        RAISE EXCEPTION 'Workflow Run event attempt is invalid';
    END IF;
    IF NOT reference.is_nonblank(p_safe_message)
       OR octet_length(p_safe_message) > 2000
       OR p_safe_message ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Workflow Run event message is invalid';
    END IF;
    IF p_finding_count IS NULL OR p_finding_count < 0 THEN
        RAISE EXCEPTION 'Workflow Run event finding count is invalid';
    END IF;
    IF (p_current_count IS NULL) <> (p_total_count IS NULL)
       OR (
           p_total_count IS NOT NULL
           AND (
               p_total_count <= 0
               OR p_current_count < 0
               OR p_current_count > p_total_count
           )
       ) THEN
        RAISE EXCEPTION 'Workflow Run event progress is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.workflow_run_state,
           run.correlation_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.validation_retry_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Workflow Run event denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT event.*
      INTO v_existing
      FROM model.model_event_log AS event
    WHERE event.workflow_run_id = p_workflow_run_id
       AND event.model_event_log_sequence = p_event_sequence;
    IF FOUND THEN
        IF v_existing.model_event_log_attempt IS DISTINCT FROM p_attempt
           OR v_existing.model_event_log_stage IS DISTINCT FROM p_stage_code
           OR v_existing.model_event_log_status IS DISTINCT FROM p_status
           OR v_existing.model_event_log_message IS DISTINCT FROM p_safe_message
           OR v_existing.model_event_log_current IS DISTINCT FROM p_current_count
           OR v_existing.model_event_log_total IS DISTINCT FROM p_total_count
           OR v_existing.finding_count IS DISTINCT FROM p_finding_count THEN
            RAISE EXCEPTION 'Workflow Run event sequence conflict';
        END IF;
        RETURN NEXT v_existing;
        RETURN;
    END IF;

    IF v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION 'Workflow Run must be running to append an event';
    END IF;

    v_max_attempt := CASE
        WHEN v_run.model_workflow = 'code_generation'
             OR v_run.workflow_execution_mode IS NOT NULL
            THEN v_run.validation_retry_count + 1
        ELSE 1
    END;
    IF p_attempt < 1 OR p_attempt > v_max_attempt THEN
        RAISE EXCEPTION 'Workflow Run event attempt is invalid';
    END IF;

    SELECT coalesce(max(event.model_event_log_sequence), 0) + 1
      INTO v_expected_sequence
      FROM model.model_event_log AS event
     WHERE event.workflow_run_id = p_workflow_run_id;
    IF p_event_sequence <> v_expected_sequence THEN
        RAISE EXCEPTION 'Workflow Run event sequence must be contiguous';
    END IF;

    v_percent := CASE
        WHEN p_total_count IS NULL THEN NULL
        ELSE round((p_current_count::NUMERIC * 100) / p_total_count, 2)
    END;
    INSERT INTO model.model_event_log AS event (
        model_id,
        correlation_id,
        workflow_run_id,
        model_event_log_sequence,
        model_event_log_attempt,
        model_workflow,
        model_event_log_stage,
        model_event_log_status,
        model_event_log_message,
        model_event_log_current,
        model_event_log_total,
        model_event_log_percent,
        finding_count
    ) VALUES (
        v_run.model_id,
        v_run.correlation_id,
        v_run.workflow_run_id,
        p_event_sequence,
        p_attempt,
        v_run.model_workflow,
        p_stage_code,
        p_status,
        p_safe_message,
        p_current_count,
        p_total_count,
        v_percent,
        p_finding_count
    )
    RETURNING event.* INTO v_event;

    RETURN NEXT v_event;
END;
$append_workflow_run_event$;

REVOKE ALL ON FUNCTION application.append_workflow_run_event(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT,
    INTEGER,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.complete_workflow_run(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_final_finding_count INTEGER
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    completed_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $complete_workflow_run$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_terminal_event RECORD;
    v_max_attempt INTEGER;
    v_next_sequence BIGINT;
    v_terminal_state VARCHAR(30);
    v_completed_time TIMESTAMPTZ;
BEGIN
    IF p_final_finding_count IS NULL OR p_final_finding_count < 0 THEN
        RAISE EXCEPTION 'Workflow Run final finding count is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.workflow_run_state,
           run.correlation_id,
           run.model_workflow,
           run.authoring_no_op_candidate_digest,
           run.completed_time,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Workflow Run completion denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    IF v_run.authoring_no_op_candidate_digest IS NOT NULL THEN
        RAISE EXCEPTION 'Workflow Run completion conflict';
    END IF;

    IF v_run.workflow_run_state IN ('completed', 'completed_with_repair') THEN
        SELECT event.finding_count
          INTO v_terminal_event
          FROM model.model_event_log AS event
         WHERE event.workflow_run_id = p_workflow_run_id
           AND event.model_event_log_stage = 'workflow_run'
           AND event.model_event_log_status = 'completed'
         ORDER BY event.model_event_log_sequence DESC
         LIMIT 1;
        IF NOT FOUND
           OR v_terminal_event.finding_count <> p_final_finding_count THEN
            RAISE EXCEPTION 'Workflow Run completion conflict';
        END IF;
        RETURN QUERY SELECT
            FALSE,
            v_run.workflow_run_id,
            v_run.workflow_run_state,
            v_run.completed_time;
        RETURN;
    END IF;
    IF v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION 'Workflow Run must be running to complete';
    END IF;

    SELECT coalesce(max(event.model_event_log_attempt), 1),
           coalesce(max(event.model_event_log_sequence), 0) + 1
      INTO v_max_attempt, v_next_sequence
      FROM model.model_event_log AS event
     WHERE event.workflow_run_id = p_workflow_run_id;
    v_terminal_state := CASE
        WHEN v_max_attempt > 1 THEN 'completed_with_repair'
        ELSE 'completed'
    END;
    v_completed_time := clock_timestamp();

    UPDATE application.workflow_run AS run
       SET workflow_run_state = v_terminal_state,
           completed_time = v_completed_time,
           workflow_run_claim_token_digest = NULL,
           workflow_run_claimed_time = NULL,
           workflow_run_claim_heartbeat_time = NULL,
           workflow_run_claim_expires_time = NULL,
           updated_time = v_completed_time,
           updated_by = CURRENT_USER
     WHERE run.workflow_run_id = p_workflow_run_id;

    INSERT INTO model.model_event_log (
        model_id,
        correlation_id,
        workflow_run_id,
        model_event_log_sequence,
        model_event_log_attempt,
        model_workflow,
        model_event_log_stage,
        model_event_log_status,
        model_event_log_message,
        finding_count
    ) VALUES (
        v_run.model_id,
        v_run.correlation_id,
        v_run.workflow_run_id,
        v_next_sequence,
        v_max_attempt,
        v_run.model_workflow,
        'workflow_run',
        'completed',
        'Workflow run completed.',
        p_final_finding_count
    );

    RETURN QUERY SELECT
        TRUE,
        v_run.workflow_run_id,
        v_terminal_state,
        v_completed_time;
END;
$complete_workflow_run$;

REVOKE ALL ON FUNCTION application.complete_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.complete_authoring_workflow_run_no_op(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_workflow VARCHAR(30),
    p_expected_execution_mode VARCHAR(50),
    p_expected_correlation_id UUID,
    p_expected_base_model_revision BIGINT,
    p_candidate_digest CHAR(64),
    p_final_event_sequence BIGINT,
    p_final_event_attempt INTEGER,
    p_final_event_stage VARCHAR(100),
    p_final_event_status VARCHAR(30),
    p_final_event_message VARCHAR(2000),
    p_final_event_current INTEGER,
    p_final_event_total INTEGER,
    p_final_finding_count INTEGER
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    model_id BIGINT,
    model_revision BIGINT,
    model_workflow VARCHAR(30),
    workflow_execution_mode VARCHAR(50),
    correlation_id UUID,
    candidate_digest CHAR(64),
    final_event_sequence BIGINT,
    final_event_attempt INTEGER,
    final_event_stage VARCHAR(100),
    final_event_status VARCHAR(30),
    final_event_message VARCHAR(2000),
    final_event_current INTEGER,
    final_event_total INTEGER,
    final_finding_count INTEGER,
    completed_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $complete_authoring_workflow_run_no_op$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_terminal_event model.model_event_log%ROWTYPE;
    v_prior_max_attempt INTEGER;
    v_allowed_max_attempt INTEGER;
    v_expected_sequence BIGINT;
    v_terminal_state VARCHAR(30);
    v_completed_time TIMESTAMPTZ;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0
       OR p_model_id IS NULL OR p_model_id <= 0
       OR p_workflow_run_id IS NULL OR p_workflow_run_id <= 0 THEN
        RAISE EXCEPTION 'Workflow Run no-op identity is invalid';
    END IF;
    IF p_expected_workflow IS NULL OR p_expected_workflow NOT IN (
        'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
    ) THEN
        RAISE EXCEPTION 'Workflow Run no-op Workflow is invalid';
    END IF;
    IF p_expected_execution_mode IS NULL OR p_expected_execution_mode NOT IN (
        'one_shot', 'tool_assisted', 'detailed_coverage'
    ) THEN
        RAISE EXCEPTION 'Workflow Run no-op execution mode is invalid';
    END IF;
    IF p_expected_correlation_id IS NULL THEN
        RAISE EXCEPTION 'Workflow Run no-op correlation is invalid';
    END IF;
    IF p_expected_base_model_revision IS NULL
       OR p_expected_base_model_revision <= 0 THEN
        RAISE EXCEPTION 'Workflow Run no-op base revision is invalid';
    END IF;
    IF p_candidate_digest IS NULL
       OR p_candidate_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Workflow Run no-op Candidate digest is invalid';
    END IF;
    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.workflow_run_state,
           run.correlation_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.validation_retry_count,
           run.completed_time,
           run.authoring_no_op_base_model_revision,
           run.authoring_no_op_candidate_digest,
           run.authoring_no_op_model_event_log_id,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Workflow Run no-op completion denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;
    IF v_run.tenant_id <> p_tenant_id
       OR v_run.model_id <> p_model_id
       OR v_run.model_workflow <> p_expected_workflow
       OR v_run.workflow_execution_mode IS DISTINCT FROM p_expected_execution_mode
       OR v_run.correlation_id <> p_expected_correlation_id THEN
        RAISE EXCEPTION 'Workflow Run no-op completion conflict';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM mcp.model_change_set AS change_set
         WHERE change_set.workflow_run_id = p_workflow_run_id
    ) THEN
        RAISE EXCEPTION 'Workflow Run no-op requires no Model Change Set';
    END IF;

    IF v_run.authoring_no_op_candidate_digest IS NOT NULL THEN
        IF v_run.authoring_no_op_base_model_revision
               <> p_expected_base_model_revision
           OR v_run.authoring_no_op_candidate_digest <> p_candidate_digest
           OR v_run.authoring_no_op_model_event_log_id IS NULL THEN
            RAISE EXCEPTION 'Workflow Run no-op completion conflict';
        END IF;

        SELECT event.*
          INTO v_terminal_event
          FROM model.model_event_log AS event
         WHERE event.model_event_log_id =
                   v_run.authoring_no_op_model_event_log_id;
        IF NOT FOUND
           OR v_terminal_event.model_id <> v_run.model_id
           OR v_terminal_event.workflow_run_id IS DISTINCT FROM v_run.workflow_run_id
           OR v_terminal_event.correlation_id <> v_run.correlation_id
           OR v_terminal_event.agent_run_id IS NOT NULL
           OR v_terminal_event.model_workflow <> v_run.model_workflow
           OR v_terminal_event.model_event_log_sequence IS DISTINCT FROM
              p_final_event_sequence
           OR v_terminal_event.model_event_log_attempt IS DISTINCT FROM
              p_final_event_attempt
           OR v_terminal_event.model_event_log_stage IS DISTINCT FROM
              p_final_event_stage
           OR v_terminal_event.model_event_log_status IS DISTINCT FROM
              p_final_event_status
           OR v_terminal_event.model_event_log_message IS DISTINCT FROM
              p_final_event_message
           OR v_terminal_event.model_event_log_current IS DISTINCT FROM
              p_final_event_current
           OR v_terminal_event.model_event_log_total IS DISTINCT FROM
              p_final_event_total
           OR v_terminal_event.model_event_log_percent <> 100.00
           OR v_terminal_event.finding_count IS DISTINCT FROM
              p_final_finding_count
           OR v_terminal_event.created_time <> v_run.completed_time
           OR v_run.workflow_run_state <> (CASE
               WHEN v_terminal_event.model_event_log_attempt > 1
                   THEN 'completed_with_repair'
               ELSE 'completed'
           END)
           OR EXISTS (
               SELECT 1
                 FROM model.model_event_log AS later_event
                WHERE later_event.workflow_run_id = v_run.workflow_run_id
                  AND later_event.model_event_log_sequence >
                      v_terminal_event.model_event_log_sequence
           ) THEN
            RAISE EXCEPTION 'Workflow Run no-op completion conflict';
        END IF;

        RETURN QUERY SELECT
            FALSE,
            v_run.workflow_run_id,
            v_run.workflow_run_state,
            v_run.model_id,
            v_run.authoring_no_op_base_model_revision,
            v_run.model_workflow,
            v_run.workflow_execution_mode,
            v_run.correlation_id,
            v_run.authoring_no_op_candidate_digest,
            v_terminal_event.model_event_log_sequence,
            v_terminal_event.model_event_log_attempt,
            v_terminal_event.model_event_log_stage,
            v_terminal_event.model_event_log_status,
            v_terminal_event.model_event_log_message,
            v_terminal_event.model_event_log_current,
            v_terminal_event.model_event_log_total,
            v_terminal_event.finding_count,
            v_run.completed_time;
        RETURN;
    END IF;

    IF v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION 'Workflow Run must be running to complete as no-op';
    END IF;
    IF p_final_event_sequence IS NULL OR p_final_event_sequence <= 1 THEN
        RAISE EXCEPTION 'Workflow Run no-op event sequence is invalid';
    END IF;
    IF p_final_event_attempt IS NULL OR p_final_event_attempt <= 0 THEN
        RAISE EXCEPTION 'Workflow Run no-op event attempt is invalid';
    END IF;
    IF p_final_event_stage IS DISTINCT FROM
       p_expected_workflow || '.backend_validation' THEN
        RAISE EXCEPTION 'Workflow Run no-op event stage is invalid';
    END IF;
    IF p_final_event_status IS NULL
       OR p_final_event_status NOT IN ('running', 'warning') THEN
        RAISE EXCEPTION 'Workflow Run no-op event status is invalid';
    END IF;
    IF NOT reference.is_nonblank(p_final_event_message)
       OR octet_length(p_final_event_message) > 2000
       OR p_final_event_message ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Workflow Run no-op event message is invalid';
    END IF;
    IF p_final_event_current IS DISTINCT FROM 1
       OR p_final_event_total IS DISTINCT FROM 1
       OR p_final_finding_count IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'Workflow Run no-op event counts are invalid';
    END IF;
    IF v_run.model_revision <> p_expected_base_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT coalesce(max(event.model_event_log_attempt), 1),
           coalesce(max(event.model_event_log_sequence), 0) + 1
      INTO v_prior_max_attempt, v_expected_sequence
      FROM model.model_event_log AS event
     WHERE event.workflow_run_id = p_workflow_run_id;
    v_allowed_max_attempt := v_run.validation_retry_count + 1;
    IF p_final_event_sequence <> v_expected_sequence THEN
        RAISE EXCEPTION 'Workflow Run no-op event sequence must be contiguous';
    END IF;
    IF p_final_event_attempt < v_prior_max_attempt
       OR p_final_event_attempt > v_allowed_max_attempt THEN
        RAISE EXCEPTION 'Workflow Run no-op event attempt is invalid';
    END IF;
    v_terminal_state := CASE
        WHEN p_final_event_attempt > 1 THEN 'completed_with_repair'
        ELSE 'completed'
    END;
    v_completed_time := clock_timestamp();

    INSERT INTO model.model_event_log AS event (
        model_id,
        correlation_id,
        workflow_run_id,
        model_event_log_sequence,
        model_event_log_attempt,
        model_workflow,
        model_event_log_stage,
        model_event_log_status,
        model_event_log_message,
        model_event_log_current,
        model_event_log_total,
        model_event_log_percent,
        finding_count,
        created_time
    ) VALUES (
        v_run.model_id,
        v_run.correlation_id,
        v_run.workflow_run_id,
        p_final_event_sequence,
        p_final_event_attempt,
        v_run.model_workflow,
        p_final_event_stage,
        p_final_event_status,
        p_final_event_message,
        p_final_event_current,
        p_final_event_total,
        100.00,
        p_final_finding_count,
        v_completed_time
    )
    RETURNING event.* INTO v_terminal_event;

    UPDATE application.workflow_run AS run
       SET workflow_run_state = v_terminal_state,
           completed_time = v_completed_time,
           workflow_run_claim_token_digest = NULL,
           workflow_run_claimed_time = NULL,
           workflow_run_claim_heartbeat_time = NULL,
           workflow_run_claim_expires_time = NULL,
           authoring_no_op_base_model_revision = p_expected_base_model_revision,
           authoring_no_op_candidate_digest = p_candidate_digest,
           authoring_no_op_model_event_log_id =
               v_terminal_event.model_event_log_id,
           updated_time = v_completed_time,
           updated_by = CURRENT_USER
     WHERE run.workflow_run_id = p_workflow_run_id;

    RETURN QUERY SELECT
        TRUE,
        v_run.workflow_run_id,
        v_terminal_state,
        v_run.model_id,
        p_expected_base_model_revision,
        v_run.model_workflow,
        v_run.workflow_execution_mode,
        v_run.correlation_id,
        p_candidate_digest,
        v_terminal_event.model_event_log_sequence,
        v_terminal_event.model_event_log_attempt,
        v_terminal_event.model_event_log_stage,
        v_terminal_event.model_event_log_status,
        v_terminal_event.model_event_log_message,
        v_terminal_event.model_event_log_current,
        v_terminal_event.model_event_log_total,
        v_terminal_event.finding_count,
        v_completed_time;
END;
$complete_authoring_workflow_run_no_op$;

REVOKE ALL ON FUNCTION application.complete_authoring_workflow_run_no_op(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
    UUID,
    BIGINT,
    CHAR,
    BIGINT,
    INTEGER,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER,
    INTEGER
) FROM PUBLIC;

CREATE FUNCTION application.fail_workflow_run(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_failure_code VARCHAR(100),
    p_safe_failure_message VARCHAR(2000)
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    completed_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $fail_workflow_run$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_max_attempt INTEGER;
    v_next_sequence BIGINT;
    v_completed_time TIMESTAMPTZ;
BEGIN
    IF p_failure_code IS NULL
       OR p_failure_code !~ '^[a-z][a-z0-9_.-]{0,99}$' THEN
        RAISE EXCEPTION 'Workflow Run failure code is invalid';
    END IF;
    IF NOT reference.is_nonblank(p_safe_failure_message)
       OR octet_length(p_safe_failure_message) > 2000
       OR p_safe_failure_message ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Workflow Run failure message is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.workflow_run_state,
           run.correlation_id,
           run.model_workflow,
           run.failure_code,
           run.failure_message,
           run.authoring_no_op_candidate_digest,
           run.completed_time,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Workflow Run failure denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    IF v_run.authoring_no_op_candidate_digest IS NOT NULL
       OR EXISTS (
           SELECT 1
             FROM mcp.model_change_set AS change_set
            WHERE change_set.workflow_run_id = p_workflow_run_id
              AND change_set.model_change_set_status IN ('validated', 'applied')
       ) THEN
        RAISE EXCEPTION 'Workflow Run has a durable authoring outcome';
    END IF;

    IF v_run.workflow_run_state = 'failed' THEN
        IF v_run.failure_code <> p_failure_code
           OR v_run.failure_message <> p_safe_failure_message THEN
            RAISE EXCEPTION 'Workflow Run failure conflict';
        END IF;
        RETURN QUERY SELECT
            FALSE,
            v_run.workflow_run_id,
            v_run.workflow_run_state,
            v_run.completed_time;
        RETURN;
    END IF;
    IF v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION 'Workflow Run must be running to fail';
    END IF;

    SELECT coalesce(max(event.model_event_log_attempt), 1),
           coalesce(max(event.model_event_log_sequence), 0) + 1
      INTO v_max_attempt, v_next_sequence
      FROM model.model_event_log AS event
     WHERE event.workflow_run_id = p_workflow_run_id;
    v_completed_time := clock_timestamp();

    UPDATE application.workflow_run AS run
       SET workflow_run_state = 'failed',
           completed_time = v_completed_time,
           workflow_run_claim_token_digest = NULL,
           workflow_run_claimed_time = NULL,
           workflow_run_claim_heartbeat_time = NULL,
           workflow_run_claim_expires_time = NULL,
           failure_code = p_failure_code,
           failure_message = p_safe_failure_message,
           updated_time = v_completed_time,
           updated_by = CURRENT_USER
     WHERE run.workflow_run_id = p_workflow_run_id;

    INSERT INTO model.model_event_log (
        model_id,
        correlation_id,
        workflow_run_id,
        model_event_log_sequence,
        model_event_log_attempt,
        model_workflow,
        model_event_log_stage,
        model_event_log_status,
        model_event_log_message,
        finding_count
    ) VALUES (
        v_run.model_id,
        v_run.correlation_id,
        v_run.workflow_run_id,
        v_next_sequence,
        v_max_attempt,
        v_run.model_workflow,
        'workflow_run',
        'failed',
        p_safe_failure_message,
        0
    );

    RETURN QUERY SELECT
        TRUE,
        v_run.workflow_run_id,
        'failed'::VARCHAR(30),
        v_completed_time;
END;
$fail_workflow_run$;

REVOKE ALL ON FUNCTION application.fail_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR
) FROM PUBLIC;

-- Resolve the complete immutable physical input for one running Profiling Run.
-- Relation catalog ownership comes only from the exact active Metadata
-- Discovery Scope assignment; Connection ownership is never a fallback.
CREATE FUNCTION application.get_profiling_execution_context(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    requested_batch_id VARCHAR(500),
    selection_order INTEGER,
    source_tenant_id BIGINT,
    source_tenant_code VARCHAR(100),
    gds_connection_id BIGINT,
    relation_catalog VARCHAR(255),
    relation_schema VARCHAR(400),
    relation_object VARCHAR(400),
    system_id BIGINT,
    system_code VARCHAR(100),
    object_id BIGINT,
    batch_attribute_name VARCHAR(400),
    attribute_id BIGINT,
    attribute_name VARCHAR(400),
    attribute_data_type VARCHAR(100),
    attribute_ordinal_position INTEGER,
    is_batch_attribute BOOLEAN
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_profiling_execution_context$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_selected_scope_count INTEGER;
    v_eligible_object_count INTEGER;
    v_discovery_object_count INTEGER;
    v_attribute_object_count INTEGER;
    v_attribute_count INTEGER;
BEGIN
    IF p_workflow_run_id IS NULL
       OR p_workflow_run_id < 1
       OR p_expected_model_revision IS NULL
       OR p_expected_model_revision < 1 THEN
        RAISE EXCEPTION
            'invalid_request: Profiling execution context input is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.model_workflow,
           run.workflow_run_state,
           run.requested_batch_id,
           run.selected_scope_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR SHARE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'profiling_run_not_found: Profiling Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'profiling_execution_denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION
            'workflow_run_owner_mismatch: Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'profiling'
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'profiling_run_not_running: A running Profiling Workflow Run is required';
    END IF;
    IF v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_selected_scope_count
      FROM application.workflow_run_object_selection AS selection
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_selected_scope_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_scope_incomplete: Workflow Run Selected Scope is incomplete';
    END IF;

    SELECT count(DISTINCT selection.object_id)::INTEGER
      INTO v_discovery_object_count
      FROM application.workflow_run_object_selection AS selection
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.is_active
      JOIN core.connection AS gds_connection
        ON gds_connection.connection_id = object_record.connection_id
       AND gds_connection.is_active
       AND gds_connection.is_global_data_store
      JOIN core.system AS system_record
        ON system_record.system_id = gds_connection.system_id
       AND system_record.is_active
      JOIN reference.zone AS zone_record
        ON zone_record.zone_id = object_record.zone_id
       AND zone_record.is_active
       AND lower(btrim(zone_record.zone_code)) = 'bronze'
      JOIN core.tenant_metadata_discovery_scope AS discovery_scope
        ON discovery_scope.gds_connection_id = gds_connection.connection_id
       AND discovery_scope.zone_id = object_record.zone_id
       AND lower(btrim(discovery_scope.object_schema)) =
           lower(btrim(object_record.object_schema))
       AND discovery_scope.is_active
      JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = discovery_scope.tenant_id
       AND source_tenant.is_active
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_discovery_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_discovery_scope_missing: Every selected Object requires one active Discovery Scope assignment';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_eligible_object_count
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_object_eligibility(v_run.model_id) AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_bronze_source_eligible
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_eligible_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_scope_changed: Selected Bronze Object membership has changed';
    END IF;

    SELECT count(DISTINCT eligible.object_id)::INTEGER,
           count(*)::INTEGER
      INTO v_attribute_object_count,
           v_attribute_count
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id) AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_bronze_source_eligible
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_attribute_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'profiling_attributes_missing: Every selected Object requires one active eligible Attribute';
    END IF;
    IF v_attribute_count > 50000 THEN
        RAISE EXCEPTION
            'profiling_context_too_large: Profiling execution exceeds 50000 Attributes';
    END IF;

    RETURN QUERY
    SELECT v_run.workflow_run_id,
           v_run.model_id,
           v_run.model_revision,
           v_run.requested_batch_id,
           selection.selection_order,
           source_tenant.tenant_id,
           source_tenant.tenant_code,
           gds_connection.connection_id,
           source_tenant.tenant_catalog,
           object_record.object_schema,
           object_record.object_name,
           system_record.system_id,
           system_record.system_code,
           object_record.object_id,
           object_record.batch_attribute_name,
           eligible.attribute_id,
           eligible.attribute_name,
           attribute_record.attribute_data_type,
           eligible.attribute_ordinal_position,
           object_record.batch_attribute_name IS NOT NULL
           AND lower(btrim(object_record.batch_attribute_name)) =
               lower(btrim(eligible.attribute_name))
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id) AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_bronze_source_eligible
      JOIN core.attribute AS attribute_record
        ON attribute_record.attribute_id = eligible.attribute_id
       AND attribute_record.object_id = eligible.object_id
       AND attribute_record.is_active
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.is_active
      JOIN core.connection AS gds_connection
        ON gds_connection.connection_id = object_record.connection_id
       AND gds_connection.is_active
       AND gds_connection.is_global_data_store
      JOIN core.system AS system_record
        ON system_record.system_id = gds_connection.system_id
       AND system_record.is_active
      JOIN reference.zone AS zone_record
        ON zone_record.zone_id = object_record.zone_id
       AND zone_record.is_active
       AND lower(btrim(zone_record.zone_code)) = 'bronze'
      JOIN core.tenant_metadata_discovery_scope AS discovery_scope
        ON discovery_scope.gds_connection_id = gds_connection.connection_id
       AND discovery_scope.zone_id = object_record.zone_id
       AND lower(btrim(discovery_scope.object_schema)) =
           lower(btrim(object_record.object_schema))
       AND discovery_scope.is_active
      JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = discovery_scope.tenant_id
       AND source_tenant.is_active
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
     ORDER BY selection.selection_order,
              eligible.attribute_ordinal_position,
              eligible.attribute_id;
END;
$get_profiling_execution_context$;

REVOKE ALL ON FUNCTION application.get_profiling_execution_context(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) FROM PUBLIC;

-- Return one credential tuple per exact GDS Connection selected through the
-- validated execution context. Any configuration gap returns one fixed safe
-- failure row and no partial credential values.
CREATE FUNCTION application.get_profiling_connection_values(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    gds_connection_id BIGINT,
    environment_code VARCHAR(100),
    failure_code VARCHAR(50),
    failure_message VARCHAR(200),
    databricks_host_name TEXT,
    databricks_http_path TEXT,
    databricks_token TEXT
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_profiling_connection_values$
DECLARE
    v_workflow_run_id BIGINT;
    v_model_id BIGINT;
    v_model_revision BIGINT;
    v_gds_connection_ids BIGINT[];
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_connection_count INTEGER;
    v_complete_connection_count INTEGER;
    v_connection_snapshot JSONB;
BEGIN
    SELECT min(context.workflow_run_id),
           min(context.model_id),
           min(context.model_revision),
           array_agg(
               DISTINCT context.gds_connection_id
               ORDER BY context.gds_connection_id
           )
      INTO v_workflow_run_id,
           v_model_id,
           v_model_revision,
           v_gds_connection_ids
      FROM application.get_profiling_execution_context(
               p_entra_tenant_id,
               p_entra_object_id,
               p_expected_principal_type,
               p_workflow_run_id,
               p_expected_model_revision
           ) AS context;
    v_connection_count := cardinality(v_gds_connection_ids);

    IF p_environment_code IS NULL
       OR NOT reference.is_nonblank(p_environment_code)
       OR length(btrim(p_environment_code)) > 100 THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'invalid_request'::VARCHAR(50),
            'Profiling Environment input is invalid.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id,
           v_environment_code
     FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code))
     FOR SHARE OF environment_record;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'environment_not_found'::VARCHAR(50),
            'Profiling Environment is unavailable.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    -- Read every required value once. Completeness checks and returned secret
    -- tuples use this exact local snapshot, never a second table read.
    WITH requested_connection AS (
        SELECT connection_id
          FROM unnest(v_gds_connection_ids) AS requested(connection_id)
    ), connection_values AS MATERIALIZED (
        SELECT requested.connection_id,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_host_name'
               ) AS databricks_host_name,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_http_path'
               ) AS databricks_http_path,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_token'
               ) AS databricks_token
          FROM requested_connection AS requested
          JOIN core.connection AS gds_connection
            ON gds_connection.connection_id = requested.connection_id
           AND gds_connection.is_active
           AND gds_connection.is_global_data_store
          LEFT JOIN core.connection_value AS connection_value
            ON connection_value.connection_id = requested.connection_id
           AND connection_value.environment_id = v_environment_id
          LEFT JOIN reference.connection_parameter AS parameter
            ON parameter.connection_parameter_id =
               connection_value.connection_parameter_id
           AND parameter.is_active
           AND lower(btrim(parameter.connection_parameter_code)) IN (
                   'databricks_host_name',
                   'databricks_http_path',
                   'databricks_token'
               )
         GROUP BY requested.connection_id
    )
    SELECT jsonb_build_object(
               'complete_connection_count',
               count(*) FILTER (
                   WHERE values.databricks_host_name IS NOT NULL
                     AND values.databricks_http_path IS NOT NULL
                     AND values.databricks_token IS NOT NULL
               )::INTEGER,
               'rows', coalesce(
                   jsonb_agg(
                       jsonb_build_object(
                           'gds_connection_id', values.connection_id,
                           'databricks_host_name',
                           values.databricks_host_name,
                           'databricks_http_path',
                           values.databricks_http_path,
                           'databricks_token', values.databricks_token
                       )
                       ORDER BY values.connection_id
                   ),
                   '[]'::JSONB
               )
           )
      INTO v_connection_snapshot
      FROM connection_values AS values;
    v_complete_connection_count :=
        (v_connection_snapshot ->> 'complete_connection_count')::INTEGER;
    IF v_connection_count IS NULL
       OR v_connection_count < 1
       OR v_complete_connection_count <> v_connection_count THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            v_environment_code,
            'connection_values_missing'::VARCHAR(50),
            'Profiling GDS connection values are incomplete.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT v_workflow_run_id,
           v_model_id,
           v_model_revision,
           snapshot.gds_connection_id,
           v_environment_code,
           NULL::VARCHAR(50),
           NULL::VARCHAR(200),
           snapshot.databricks_host_name,
           snapshot.databricks_http_path,
           snapshot.databricks_token
      FROM jsonb_to_recordset(v_connection_snapshot -> 'rows') AS snapshot(
               gds_connection_id BIGINT,
               databricks_host_name TEXT,
               databricks_http_path TEXT,
               databricks_token TEXT
           )
     ORDER BY snapshot.gds_connection_id;
END;
$get_profiling_connection_values$;

REVOKE ALL ON FUNCTION application.get_profiling_connection_values(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

-- Resolve the complete immutable physical input for one running deterministic
-- Analysis validation Run. A relationship is eligible only when both endpoint
-- Objects are selected. Validation may refresh locked rows because it never
-- changes inference-owned or user-owned fields.
CREATE FUNCTION application.get_analysis_validation_execution_context(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    requested_batch_id VARCHAR(500),
    analysis_result_id BIGINT,
    relationship_kind VARCHAR(100),
    relationship_confidence VARCHAR(10),
    relationship_basis TEXT,
    analysis_result_status VARCHAR(20),
    analysis_result_is_locked BOOLEAN,
    gds_connection_id BIGINT,
    source_context_digest CHAR(64),
    from_relation_catalog VARCHAR(255),
    from_relation_schema VARCHAR(400),
    from_relation_object VARCHAR(400),
    from_object_id BIGINT,
    from_attribute_id BIGINT,
    from_attribute_name VARCHAR(400),
    from_attribute_data_type VARCHAR(100),
    from_batch_attribute_name VARCHAR(400),
    from_batch_attribute_data_type VARCHAR(100),
    to_relation_catalog VARCHAR(255),
    to_relation_schema VARCHAR(400),
    to_relation_object VARCHAR(400),
    to_object_id BIGINT,
    to_attribute_id BIGINT,
    to_attribute_name VARCHAR(400),
    to_attribute_data_type VARCHAR(100),
    to_batch_attribute_name VARCHAR(400),
    to_batch_attribute_data_type VARCHAR(100)
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_analysis_validation_execution_context$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_actor_entra_principal_identity_id BIGINT;
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_selected_scope_count INTEGER;
    v_partial_relationship_count INTEGER;
    v_relationship_count INTEGER;
    v_resolved_relationship_count INTEGER;
    v_cross_connection_count INTEGER;
    v_context_snapshot JSONB;
BEGIN
    IF p_workflow_run_id IS NULL
       OR p_workflow_run_id < 1
       OR p_expected_model_revision IS NULL
       OR p_expected_model_revision < 1
       OR p_environment_code IS NULL
       OR NOT reference.is_nonblank(p_environment_code)
       OR length(btrim(p_environment_code)) > 100 THEN
        RAISE EXCEPTION
            'invalid_request: Analysis validation execution context input is invalid';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.actor_entra_principal_identity_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.workflow_run_state,
           run.requested_batch_id,
           run.selected_scope_digest,
           run.selected_scope_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR SHARE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_found: Analysis Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'analysis_validation_execution_denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    SELECT identity.entra_principal_identity_id
      INTO v_actor_entra_principal_identity_id
      FROM security.entra_principal_identity AS identity
     WHERE identity.principal_id = v_decision.principal_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.is_active
     FOR SHARE OF identity;
    IF NOT FOUND
       OR v_run.actor_principal_id <> v_decision.principal_id
       OR v_run.actor_entra_principal_identity_id IS DISTINCT FROM
          v_actor_entra_principal_identity_id THEN
        RAISE EXCEPTION
            'workflow_run_owner_mismatch: Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'analysis'
       OR v_run.workflow_execution_mode IS NOT NULL
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_running: A running deterministic Analysis Workflow Run is required';
    END IF;
    IF v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id,
           v_environment_code
      FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code))
     FOR SHARE OF environment_record;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'analysis_validation_environment_not_found: Analysis validation Environment is unavailable';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_selected_scope_count
      FROM application.workflow_run_object_selection AS selection
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;
    IF v_selected_scope_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'analysis_validation_scope_incomplete: Workflow Run Selected Scope is incomplete';
    END IF;

    -- Resolve and serialize the complete relationship context in one SQL
    -- statement. All subsequent checks and returned rows use this exact local
    -- snapshot, so concurrent metadata changes cannot split validation from
    -- execution input.
    WITH relationship_membership AS MATERIALIZED (
        SELECT result.*,
               from_selection.object_id IS NOT NULL AS from_is_selected,
               to_selection.object_id IS NOT NULL AS to_is_selected
          FROM workflow.analysis_result AS result
          LEFT JOIN application.workflow_run_object_selection
               AS from_selection
            ON from_selection.workflow_run_id = p_workflow_run_id
           AND from_selection.model_id = result.model_id
           AND from_selection.object_id = result.from_object_id
          LEFT JOIN application.workflow_run_object_selection AS to_selection
            ON to_selection.workflow_run_id = p_workflow_run_id
           AND to_selection.model_id = result.model_id
           AND to_selection.object_id = result.to_object_id
         WHERE result.model_id = v_run.model_id
           AND result.analysis_result_status IN ('active', 'needs_review')
    ), selected_relationship AS MATERIALIZED (
        SELECT membership.*
          FROM relationship_membership AS membership
         WHERE membership.from_is_selected
           AND membership.to_is_selected
    ), resolved_relationship_input AS MATERIALIZED (
        SELECT result.analysis_result_id,
               result.relationship_kind,
               result.relationship_confidence,
               result.relationship_basis,
               result.analysis_result_status,
               result.analysis_result_is_locked,
               from_connection.connection_id AS from_connection_id,
               to_connection.connection_id AS to_connection_id,
               from_source_tenant.tenant_catalog AS from_relation_catalog,
               from_object.object_schema AS from_relation_schema,
               from_object.object_name AS from_relation_object,
               from_object.object_id AS from_object_id,
               from_attribute.attribute_id AS from_attribute_id,
               from_attribute.attribute_name AS from_attribute_name,
               from_attribute.attribute_data_type
                   AS from_attribute_data_type,
               from_batch_attribute.attribute_name
                   AS from_batch_attribute_name,
               from_batch_attribute.attribute_data_type
                   AS from_batch_attribute_data_type,
               to_source_tenant.tenant_catalog AS to_relation_catalog,
               to_object.object_schema AS to_relation_schema,
               to_object.object_name AS to_relation_object,
               to_object.object_id AS to_object_id,
               to_attribute.attribute_id AS to_attribute_id,
               to_attribute.attribute_name AS to_attribute_name,
               to_attribute.attribute_data_type AS to_attribute_data_type,
               to_batch_attribute.attribute_name
                   AS to_batch_attribute_name,
               to_batch_attribute.attribute_data_type
                   AS to_batch_attribute_data_type,
               v_environment_id AS environment_id,
               v_environment_code AS environment_code,
               host_value.connection_value_id AS host_connection_value_id,
               host_value.row_version AS host_connection_value_row_version,
               path_value.connection_value_id AS path_connection_value_id,
               path_value.row_version AS path_connection_value_row_version,
               token_value.connection_value_id AS token_connection_value_id,
               token_value.row_version AS token_connection_value_row_version
          FROM selected_relationship AS result
          JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
               AS from_eligible
            ON from_eligible.model_id = result.model_id
           AND from_eligible.object_id = result.from_object_id
           AND from_eligible.attribute_id = result.from_attribute_id
           AND from_eligible.is_bronze_source_eligible
          JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
               AS to_eligible
            ON to_eligible.model_id = result.model_id
           AND to_eligible.object_id = result.to_object_id
           AND to_eligible.attribute_id = result.to_attribute_id
           AND to_eligible.is_bronze_source_eligible
          JOIN core.object AS from_object
            ON from_object.object_id = result.from_object_id
           AND from_object.connection_id = from_eligible.connection_id
           AND from_object.is_active
          JOIN core.object AS to_object
            ON to_object.object_id = result.to_object_id
           AND to_object.connection_id = to_eligible.connection_id
           AND to_object.is_active
          JOIN core.connection AS from_connection
            ON from_connection.connection_id = from_object.connection_id
           AND from_connection.is_active
           AND from_connection.is_global_data_store
          JOIN core.connection AS to_connection
            ON to_connection.connection_id = to_object.connection_id
           AND to_connection.is_active
           AND to_connection.is_global_data_store
          JOIN core.attribute AS from_attribute
            ON from_attribute.attribute_id = result.from_attribute_id
           AND from_attribute.object_id = result.from_object_id
           AND from_attribute.is_active
          JOIN core.attribute AS to_attribute
            ON to_attribute.attribute_id = result.to_attribute_id
           AND to_attribute.object_id = result.to_object_id
           AND to_attribute.is_active
          JOIN core.tenant_metadata_discovery_scope AS from_discovery_scope
            ON from_discovery_scope.gds_connection_id =
               from_connection.connection_id
           AND from_discovery_scope.zone_id = from_object.zone_id
           AND lower(btrim(from_discovery_scope.object_schema)) =
               lower(btrim(from_object.object_schema))
           AND from_discovery_scope.is_active
          JOIN core.tenant AS from_source_tenant
            ON from_source_tenant.tenant_id = from_discovery_scope.tenant_id
           AND from_source_tenant.is_active
           AND reference.is_nonblank(from_source_tenant.tenant_catalog)
          JOIN core.tenant_metadata_discovery_scope AS to_discovery_scope
            ON to_discovery_scope.gds_connection_id =
               to_connection.connection_id
           AND to_discovery_scope.zone_id = to_object.zone_id
           AND lower(btrim(to_discovery_scope.object_schema)) =
               lower(btrim(to_object.object_schema))
           AND to_discovery_scope.is_active
          JOIN core.tenant AS to_source_tenant
            ON to_source_tenant.tenant_id = to_discovery_scope.tenant_id
           AND to_source_tenant.is_active
           AND reference.is_nonblank(to_source_tenant.tenant_catalog)
          LEFT JOIN core.attribute AS from_batch_attribute
            ON from_batch_attribute.object_id = from_object.object_id
           AND lower(btrim(from_batch_attribute.attribute_name)) =
               lower(btrim(from_object.batch_attribute_name))
           AND from_batch_attribute.is_active
          LEFT JOIN core.attribute AS to_batch_attribute
            ON to_batch_attribute.object_id = to_object.object_id
           AND lower(btrim(to_batch_attribute.attribute_name)) =
               lower(btrim(to_object.batch_attribute_name))
           AND to_batch_attribute.is_active
          LEFT JOIN LATERAL (
              SELECT connection_value.connection_value_id,
                     connection_value.xmin::TEXT AS row_version
                FROM core.connection_value AS connection_value
                JOIN reference.connection_parameter AS parameter
                  ON parameter.connection_parameter_id =
                     connection_value.connection_parameter_id
                 AND parameter.is_active
                 AND lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_host_name'
               WHERE connection_value.connection_id =
                     from_connection.connection_id
                 AND connection_value.environment_id = v_environment_id
          ) AS host_value ON TRUE
          LEFT JOIN LATERAL (
              SELECT connection_value.connection_value_id,
                     connection_value.xmin::TEXT AS row_version
                FROM core.connection_value AS connection_value
                JOIN reference.connection_parameter AS parameter
                  ON parameter.connection_parameter_id =
                     connection_value.connection_parameter_id
                 AND parameter.is_active
                 AND lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_http_path'
               WHERE connection_value.connection_id =
                     from_connection.connection_id
                 AND connection_value.environment_id = v_environment_id
          ) AS path_value ON TRUE
          LEFT JOIN LATERAL (
              SELECT connection_value.connection_value_id,
                     connection_value.xmin::TEXT AS row_version
                FROM core.connection_value AS connection_value
                JOIN reference.connection_parameter AS parameter
                  ON parameter.connection_parameter_id =
                     connection_value.connection_parameter_id
                 AND parameter.is_active
                 AND lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_token'
               WHERE connection_value.connection_id =
                     from_connection.connection_id
                 AND connection_value.environment_id = v_environment_id
          ) AS token_value ON TRUE
         WHERE reference.is_nonblank(from_attribute.attribute_data_type)
           AND reference.is_nonblank(to_attribute.attribute_data_type)
           AND (
                   from_object.batch_attribute_name IS NULL
                   OR (
                       from_batch_attribute.attribute_id IS NOT NULL
                       AND reference.is_nonblank(
                           from_batch_attribute.attribute_data_type
                       )
                   )
               )
           AND (
                   to_object.batch_attribute_name IS NULL
                   OR (
                       to_batch_attribute.attribute_id IS NOT NULL
                       AND reference.is_nonblank(
                           to_batch_attribute.attribute_data_type
                       )
                   )
               )
    ), resolved_relationship AS MATERIALIZED (
        SELECT input.*,
               encode(
                   sha256(
                       convert_to(
                           jsonb_build_object(
                               'schema_version', '1.0',
                               'workflow_run_id', v_run.workflow_run_id,
                               'model_id', v_run.model_id,
                               'selected_scope_digest',
                               v_run.selected_scope_digest,
                               'requested_batch_id', v_run.requested_batch_id,
                               'environment_id', input.environment_id,
                               'environment_code', input.environment_code,
                               'host_connection_value_id',
                               input.host_connection_value_id,
                               'host_connection_value_row_version',
                               input.host_connection_value_row_version,
                               'path_connection_value_id',
                               input.path_connection_value_id,
                               'path_connection_value_row_version',
                               input.path_connection_value_row_version,
                               'token_connection_value_id',
                               input.token_connection_value_id,
                               'token_connection_value_row_version',
                               input.token_connection_value_row_version,
                               'analysis_result_id',
                               input.analysis_result_id,
                               'relationship_kind', input.relationship_kind,
                               'from_gds_connection_id',
                               input.from_connection_id,
                               'to_gds_connection_id', input.to_connection_id,
                               'from_relation_catalog',
                               input.from_relation_catalog,
                               'from_relation_schema',
                               input.from_relation_schema,
                               'from_relation_object',
                               input.from_relation_object,
                               'from_object_id', input.from_object_id,
                               'from_attribute_id', input.from_attribute_id,
                               'from_attribute_name', input.from_attribute_name,
                               'from_attribute_data_type',
                               input.from_attribute_data_type,
                               'from_batch_attribute_name',
                               input.from_batch_attribute_name,
                               'from_batch_attribute_data_type',
                               input.from_batch_attribute_data_type,
                               'to_relation_catalog',
                               input.to_relation_catalog,
                               'to_relation_schema', input.to_relation_schema,
                               'to_relation_object', input.to_relation_object,
                               'to_object_id', input.to_object_id,
                               'to_attribute_id', input.to_attribute_id,
                               'to_attribute_name', input.to_attribute_name,
                               'to_attribute_data_type',
                               input.to_attribute_data_type,
                               'to_batch_attribute_name',
                               input.to_batch_attribute_name,
                               'to_batch_attribute_data_type',
                               input.to_batch_attribute_data_type
                           )::TEXT,
                           'UTF8'
                       )
                   ),
                   'hex'
               )::CHAR(64) AS source_context_digest
          FROM resolved_relationship_input AS input
    ), relationship_statistics AS (
        SELECT (
                   SELECT count(*)
                     FROM relationship_membership AS membership
                    WHERE membership.from_is_selected <>
                          membership.to_is_selected
               )::INTEGER AS partial_relationship_count,
               (
                   SELECT count(*)
                     FROM selected_relationship
               )::INTEGER AS relationship_count,
               (
                   SELECT count(DISTINCT resolved.analysis_result_id)
                     FROM resolved_relationship AS resolved
               )::INTEGER AS resolved_relationship_count,
               (
                   SELECT count(*)
                     FROM resolved_relationship AS resolved
                    WHERE resolved.from_connection_id <>
                          resolved.to_connection_id
               )::INTEGER AS cross_connection_count
    )
    SELECT jsonb_build_object(
               'partial_relationship_count',
               statistics.partial_relationship_count,
               'relationship_count', statistics.relationship_count,
               'resolved_relationship_count',
               statistics.resolved_relationship_count,
               'cross_connection_count', statistics.cross_connection_count,
               'rows', coalesce(
                   (
                       SELECT jsonb_agg(
                                  jsonb_build_object(
                                      'workflow_run_id', v_run.workflow_run_id,
                                      'model_id', v_run.model_id,
                                      'model_revision', v_run.model_revision,
                                      'requested_batch_id',
                                      v_run.requested_batch_id,
                                      'analysis_result_id',
                                      resolved.analysis_result_id,
                                      'relationship_kind',
                                      resolved.relationship_kind,
                                      'relationship_confidence',
                                      resolved.relationship_confidence,
                                      'relationship_basis',
                                      resolved.relationship_basis,
                                      'analysis_result_status',
                                      resolved.analysis_result_status,
                                      'analysis_result_is_locked',
                                      resolved.analysis_result_is_locked,
                                      'gds_connection_id',
                                      resolved.from_connection_id,
                                      'source_context_digest',
                                      resolved.source_context_digest,
                                      'from_relation_catalog',
                                      resolved.from_relation_catalog,
                                      'from_relation_schema',
                                      resolved.from_relation_schema,
                                      'from_relation_object',
                                      resolved.from_relation_object,
                                      'from_object_id', resolved.from_object_id,
                                      'from_attribute_id',
                                      resolved.from_attribute_id,
                                      'from_attribute_name',
                                      resolved.from_attribute_name,
                                      'from_attribute_data_type',
                                      resolved.from_attribute_data_type,
                                      'from_batch_attribute_name',
                                      resolved.from_batch_attribute_name,
                                      'from_batch_attribute_data_type',
                                      resolved.from_batch_attribute_data_type,
                                      'to_relation_catalog',
                                      resolved.to_relation_catalog,
                                      'to_relation_schema',
                                      resolved.to_relation_schema,
                                      'to_relation_object',
                                      resolved.to_relation_object,
                                      'to_object_id', resolved.to_object_id,
                                      'to_attribute_id',
                                      resolved.to_attribute_id,
                                      'to_attribute_name',
                                      resolved.to_attribute_name,
                                      'to_attribute_data_type',
                                      resolved.to_attribute_data_type,
                                      'to_batch_attribute_name',
                                      resolved.to_batch_attribute_name,
                                      'to_batch_attribute_data_type',
                                      resolved.to_batch_attribute_data_type
                                  )
                                  ORDER BY resolved.analysis_result_id
                              )
                         FROM resolved_relationship AS resolved
                   ),
                   '[]'::JSONB
               )
           )
      INTO v_context_snapshot
      FROM relationship_statistics AS statistics;

    v_partial_relationship_count :=
        (v_context_snapshot ->> 'partial_relationship_count')::INTEGER;
    v_relationship_count :=
        (v_context_snapshot ->> 'relationship_count')::INTEGER;
    v_resolved_relationship_count :=
        (v_context_snapshot ->> 'resolved_relationship_count')::INTEGER;
    v_cross_connection_count :=
        (v_context_snapshot ->> 'cross_connection_count')::INTEGER;

    IF v_partial_relationship_count > 0 THEN
        RAISE EXCEPTION
            'analysis_validation_endpoint_not_selected: Every eligible relationship requires both endpoint Objects';
    END IF;
    IF v_cross_connection_count > 0 THEN
        RAISE EXCEPTION
            'analysis_validation_cross_connection: Relationship endpoints must use one GDS Connection';
    END IF;
    IF v_resolved_relationship_count <> v_relationship_count THEN
        RAISE EXCEPTION
            'analysis_validation_context_changed: Relationship physical metadata is incomplete';
    END IF;
    IF v_relationship_count > 50000 THEN
        RAISE EXCEPTION
            'analysis_validation_context_too_large: Analysis validation exceeds 50000 relationships';
    END IF;
    IF octet_length(v_context_snapshot::TEXT) > 33554432 THEN
        RAISE EXCEPTION
            'analysis_validation_context_too_large: Analysis validation context exceeds 32 MiB';
    END IF;

    RETURN QUERY
    SELECT snapshot.*
      FROM jsonb_to_recordset(v_context_snapshot -> 'rows') AS snapshot(
               workflow_run_id BIGINT,
               model_id BIGINT,
               model_revision BIGINT,
               requested_batch_id VARCHAR(500),
               analysis_result_id BIGINT,
               relationship_kind VARCHAR(100),
               relationship_confidence VARCHAR(10),
               relationship_basis TEXT,
               analysis_result_status VARCHAR(20),
               analysis_result_is_locked BOOLEAN,
               gds_connection_id BIGINT,
               source_context_digest CHAR(64),
               from_relation_catalog VARCHAR(255),
               from_relation_schema VARCHAR(400),
               from_relation_object VARCHAR(400),
               from_object_id BIGINT,
               from_attribute_id BIGINT,
               from_attribute_name VARCHAR(400),
               from_attribute_data_type VARCHAR(100),
               from_batch_attribute_name VARCHAR(400),
               from_batch_attribute_data_type VARCHAR(100),
               to_relation_catalog VARCHAR(255),
               to_relation_schema VARCHAR(400),
               to_relation_object VARCHAR(400),
               to_object_id BIGINT,
               to_attribute_id BIGINT,
               to_attribute_name VARCHAR(400),
               to_attribute_data_type VARCHAR(100),
               to_batch_attribute_name VARCHAR(400),
               to_batch_attribute_data_type VARCHAR(100)
           )
     ORDER BY snapshot.analysis_result_id;
END;
$get_analysis_validation_execution_context$;

REVOKE ALL ON FUNCTION application.get_analysis_validation_execution_context(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

-- Return one complete credential tuple per exact GDS Connection resolved by
-- the validated relationship context. Configuration failures disclose no
-- partial credential values.
CREATE FUNCTION application.get_analysis_validation_connection_values(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100)
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    gds_connection_id BIGINT,
    environment_code VARCHAR(100),
    failure_code VARCHAR(50),
    failure_message VARCHAR(200),
    databricks_host_name TEXT,
    databricks_http_path TEXT,
    databricks_token TEXT
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_analysis_validation_connection_values$
DECLARE
    v_workflow_run_id BIGINT;
    v_model_id BIGINT;
    v_model_revision BIGINT;
    v_gds_connection_ids BIGINT[];
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_connection_count INTEGER;
    v_complete_connection_count INTEGER;
    v_connection_snapshot JSONB;
BEGIN
    SELECT min(context.workflow_run_id),
           min(context.model_id),
           min(context.model_revision),
           array_agg(
               DISTINCT context.gds_connection_id
               ORDER BY context.gds_connection_id
           )
      INTO v_workflow_run_id,
           v_model_id,
           v_model_revision,
           v_gds_connection_ids
      FROM application.get_analysis_validation_execution_context(
               p_entra_tenant_id,
               p_entra_object_id,
               p_expected_principal_type,
               p_workflow_run_id,
               p_expected_model_revision,
               p_environment_code
           ) AS context;
    v_connection_count := cardinality(v_gds_connection_ids);

    IF p_environment_code IS NULL
       OR NOT reference.is_nonblank(p_environment_code)
       OR length(btrim(p_environment_code)) > 100 THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'invalid_request'::VARCHAR(50),
            'Analysis validation Environment input is invalid.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id,
           v_environment_code
      FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code))
     FOR SHARE OF environment_record;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            NULL::VARCHAR(100),
            'environment_not_found'::VARCHAR(50),
            'Analysis validation Environment is unavailable.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    -- Read every required value once. Completeness checks and returned secret
    -- tuples use this exact local snapshot, never a second table read.
    WITH requested_connection AS (
        SELECT connection_id
          FROM unnest(v_gds_connection_ids) AS requested(connection_id)
    ), connection_values AS MATERIALIZED (
        SELECT requested.connection_id,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_host_name'
               ) AS databricks_host_name,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_http_path'
               ) AS databricks_http_path,
               max(connection_value.connection_value) FILTER (
                   WHERE lower(btrim(parameter.connection_parameter_code)) =
                         'databricks_token'
               ) AS databricks_token
          FROM requested_connection AS requested
          JOIN core.connection AS gds_connection
            ON gds_connection.connection_id = requested.connection_id
           AND gds_connection.is_active
           AND gds_connection.is_global_data_store
          LEFT JOIN core.connection_value AS connection_value
            ON connection_value.connection_id = requested.connection_id
           AND connection_value.environment_id = v_environment_id
          LEFT JOIN reference.connection_parameter AS parameter
            ON parameter.connection_parameter_id =
               connection_value.connection_parameter_id
           AND parameter.is_active
           AND lower(btrim(parameter.connection_parameter_code)) IN (
                   'databricks_host_name',
                   'databricks_http_path',
                   'databricks_token'
               )
         GROUP BY requested.connection_id
    )
    SELECT jsonb_build_object(
               'complete_connection_count',
               count(*) FILTER (
                   WHERE values.databricks_host_name IS NOT NULL
                     AND values.databricks_http_path IS NOT NULL
                     AND values.databricks_token IS NOT NULL
               )::INTEGER,
               'rows', coalesce(
                   jsonb_agg(
                       jsonb_build_object(
                           'gds_connection_id', values.connection_id,
                           'databricks_host_name',
                           values.databricks_host_name,
                           'databricks_http_path',
                           values.databricks_http_path,
                           'databricks_token', values.databricks_token
                       )
                       ORDER BY values.connection_id
                   ),
                   '[]'::JSONB
               )
           )
      INTO v_connection_snapshot
      FROM connection_values AS values;
    v_complete_connection_count :=
        (v_connection_snapshot ->> 'complete_connection_count')::INTEGER;
    IF v_connection_count IS NULL
       OR v_connection_count < 1
       OR v_complete_connection_count <> v_connection_count THEN
        RETURN QUERY SELECT
            v_workflow_run_id,
            v_model_id,
            v_model_revision,
            NULL::BIGINT,
            v_environment_code,
            'connection_values_missing'::VARCHAR(50),
            'Analysis validation GDS connection values are incomplete.'::VARCHAR(200),
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT v_workflow_run_id,
           v_model_id,
           v_model_revision,
           snapshot.gds_connection_id,
           v_environment_code,
           NULL::VARCHAR(50),
           NULL::VARCHAR(200),
           snapshot.databricks_host_name,
           snapshot.databricks_http_path,
           snapshot.databricks_token
      FROM jsonb_to_recordset(v_connection_snapshot -> 'rows') AS snapshot(
               gds_connection_id BIGINT,
               databricks_host_name TEXT,
               databricks_http_path TEXT,
               databricks_token TEXT
           )
     ORDER BY snapshot.gds_connection_id;
END;
$get_analysis_validation_connection_values$;

REVOKE ALL ON FUNCTION application.get_analysis_validation_connection_values(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

-- Atomically replace only the validation-owned columns for the exact eligible
-- relationship set of one running deterministic Analysis Run. Inference,
-- status, and lock fields are never changed.
CREATE FUNCTION application.persist_analysis_validation_results(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_environment_code VARCHAR(100),
    p_validation_results JSONB
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    submitted_result_count INTEGER,
    changed_result_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $persist_analysis_validation_results$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_actor_entra_principal_identity_id BIGINT;
    v_result_count INTEGER;
    v_expected_result_ids BIGINT[];
    v_payload_result_ids BIGINT[];
    v_expected_context_digests JSONB;
    v_payload_context_digests JSONB;
    v_changed_result_count INTEGER;
    v_model_revision BIGINT;
BEGIN
    IF p_validation_results IS NULL
       OR jsonb_typeof(p_validation_results) <> 'array'
       OR octet_length(p_validation_results::TEXT) > 33554432 THEN
        RAISE EXCEPTION
            'Analysis validation results must be a JSON array no larger than 32 MiB';
    END IF;

    v_result_count := jsonb_array_length(p_validation_results);
    IF v_result_count NOT BETWEEN 0 AND 50000 THEN
        RAISE EXCEPTION
            'Analysis validation results must contain between 0 and 50000 Results';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_validation_results) AS result(value)
         WHERE jsonb_typeof(result.value) <> 'object'
            OR NOT result.value ?& ARRAY[
                   'analysis_result_id',
                   'source_context_digest',
                   'validation_policy_version',
                   'validation_policy_digest',
                   'validation_result',
                   'validation_source_non_null_count',
                   'validation_source_distinct_count',
                   'validation_target_non_null_count',
                   'validation_target_distinct_count',
                   'validation_source_missing_target_count',
                   'validation_unused_target_count',
                   'validation_duplicate_target_key_count'
               ]::TEXT[]
            OR (
                   SELECT count(*)
                     FROM jsonb_object_keys(result.value)
               ) <> 12
            OR jsonb_typeof(result.value -> 'analysis_result_id') <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'analysis_result_id')
                        ~ '^[1-9][0-9]*$'
                    AND length(
                            result.value ->> 'analysis_result_id'
                        ) <= 19
                   THEN (result.value ->> 'analysis_result_id')::NUMERIC <=
                        9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'source_context_digest'
               ) <> 'string'
            OR (result.value ->> 'source_context_digest')
               !~ '^[0-9a-f]{64}$'
            OR jsonb_typeof(
                   result.value -> 'validation_policy_version'
               ) <> 'string'
            OR (result.value ->> 'validation_policy_version')
               !~ '^[0-9]+\.[0-9]+\.[0-9]+$'
            OR octet_length(
                   result.value ->> 'validation_policy_version'
               ) > 50
            OR jsonb_typeof(
                   result.value -> 'validation_policy_digest'
               ) <> 'string'
            OR (result.value ->> 'validation_policy_digest')
               !~ '^[0-9a-f]{64}$'
            OR jsonb_typeof(result.value -> 'validation_result') <> 'string'
            OR (result.value ->> 'validation_result') NOT IN (
                   'supported', 'inconclusive', 'unsupported'
               )
            OR jsonb_typeof(
                   result.value -> 'validation_source_non_null_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_source_non_null_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_source_non_null_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_source_non_null_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_source_distinct_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_source_distinct_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_source_distinct_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_source_distinct_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_target_non_null_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_target_non_null_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_target_non_null_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_target_non_null_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_target_distinct_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_target_distinct_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_target_distinct_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_target_distinct_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value ->
                   'validation_source_missing_target_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (
                            result.value ->>
                            'validation_source_missing_target_count'
                        ) ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_source_missing_target_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_source_missing_target_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value -> 'validation_unused_target_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (result.value ->> 'validation_unused_target_count')
                        ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_unused_target_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_unused_target_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
            OR jsonb_typeof(
                   result.value ->
                   'validation_duplicate_target_key_count'
               ) <> 'number'
            OR NOT CASE
                   WHEN (
                            result.value ->>
                            'validation_duplicate_target_key_count'
                        ) ~ '^(0|[1-9][0-9]*)$'
                    AND length(
                            result.value ->>
                            'validation_duplicate_target_key_count'
                        ) <= 19
                   THEN (
                            result.value ->>
                            'validation_duplicate_target_key_count'
                        )::NUMERIC <= 9223372036854775807
                   ELSE FALSE
               END
    ) THEN
        RAISE EXCEPTION 'Analysis validation result payload shape is invalid';
    END IF;

    IF v_result_count <> (
        SELECT count(DISTINCT result.analysis_result_id)
          FROM jsonb_to_recordset(p_validation_results) AS result(
                   analysis_result_id BIGINT
               )
    ) THEN
        RAISE EXCEPTION 'Analysis validation result IDs must be unique';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM jsonb_to_recordset(p_validation_results) AS result(
                   validation_result VARCHAR(30),
                   validation_source_non_null_count BIGINT,
                   validation_source_distinct_count BIGINT,
                   validation_target_non_null_count BIGINT,
                   validation_target_distinct_count BIGINT,
                   validation_source_missing_target_count BIGINT,
                   validation_unused_target_count BIGINT,
                   validation_duplicate_target_key_count BIGINT
               )
         WHERE result.validation_source_distinct_count >
               result.validation_source_non_null_count
            OR (result.validation_source_non_null_count = 0) <>
               (result.validation_source_distinct_count = 0)
            OR result.validation_target_distinct_count >
               result.validation_target_non_null_count
            OR (result.validation_target_non_null_count = 0) <>
               (result.validation_target_distinct_count = 0)
            OR result.validation_source_missing_target_count >
               result.validation_source_distinct_count
            OR result.validation_unused_target_count >
               result.validation_target_distinct_count
            OR result.validation_duplicate_target_key_count <>
               result.validation_target_non_null_count -
               result.validation_target_distinct_count
            OR result.validation_result <> CASE
                   WHEN result.validation_source_non_null_count = 0
                     OR result.validation_target_non_null_count = 0
                   THEN 'inconclusive'
                   WHEN result.validation_source_missing_target_count = 0
                    AND result.validation_duplicate_target_key_count = 0
                   THEN 'supported'
                   ELSE 'unsupported'
               END
    ) THEN
        RAISE EXCEPTION
            'Analysis validation result evidence is inconsistent';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.actor_entra_principal_identity_id,
           run.model_workflow,
           run.workflow_execution_mode,
           run.workflow_run_state,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_found: Analysis Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'analysis_validation_persistence_denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    SELECT identity.entra_principal_identity_id
      INTO v_actor_entra_principal_identity_id
      FROM security.entra_principal_identity AS identity
     WHERE identity.principal_id = v_decision.principal_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.is_active
     FOR SHARE OF identity;
    IF NOT FOUND
       OR v_run.actor_principal_id <> v_decision.principal_id
       OR v_run.actor_entra_principal_identity_id IS DISTINCT FROM
          v_actor_entra_principal_identity_id THEN
        RAISE EXCEPTION
            'workflow_run_owner_mismatch: Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'analysis'
       OR v_run.workflow_execution_mode IS NOT NULL
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'analysis_validation_run_not_running: A running deterministic Analysis Workflow Run is required';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    -- Freeze all existing Analysis rows for this Model. The Model row lock also
    -- fences inserts through the Analysis Result foreign key until commit.
    PERFORM result.analysis_result_id
      FROM workflow.analysis_result AS result
     WHERE result.model_id = v_run.model_id
     ORDER BY result.analysis_result_id
     FOR UPDATE OF result;

    SELECT coalesce(
               array_agg(
                   context.analysis_result_id
                   ORDER BY context.analysis_result_id
               ),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               jsonb_object_agg(
                   context.analysis_result_id::TEXT,
                   context.source_context_digest
                   ORDER BY context.analysis_result_id
               ),
               '{}'::JSONB
           )
      INTO v_expected_result_ids,
           v_expected_context_digests
      FROM application.get_analysis_validation_execution_context(
               p_entra_tenant_id,
               p_entra_object_id,
               p_expected_principal_type,
               p_workflow_run_id,
               p_expected_model_revision,
               p_environment_code
           ) AS context;

    SELECT coalesce(
               array_agg(
                   result.analysis_result_id
                   ORDER BY result.analysis_result_id
               ),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               jsonb_object_agg(
                   result.analysis_result_id::TEXT,
                   result.source_context_digest
                   ORDER BY result.analysis_result_id
               ),
               '{}'::JSONB
           )
      INTO v_payload_result_ids,
           v_payload_context_digests
      FROM jsonb_to_recordset(p_validation_results) AS result(
               analysis_result_id BIGINT,
               source_context_digest CHAR(64)
           );
    IF v_payload_result_ids IS DISTINCT FROM v_expected_result_ids THEN
        RAISE EXCEPTION
            'Analysis validation results must exactly cover eligible Results';
    END IF;
    IF v_payload_context_digests IS DISTINCT FROM
       v_expected_context_digests THEN
        RAISE EXCEPTION
            'Analysis validation source context digest does not match current metadata';
    END IF;

    WITH result_payload AS MATERIALIZED (
        SELECT result.*
          FROM jsonb_to_recordset(p_validation_results) AS result(
                   analysis_result_id BIGINT,
                   source_context_digest CHAR(64),
                   validation_policy_version VARCHAR(50),
                   validation_policy_digest CHAR(64),
                   validation_result VARCHAR(30),
                   validation_source_non_null_count BIGINT,
                   validation_source_distinct_count BIGINT,
                   validation_target_non_null_count BIGINT,
                   validation_target_distinct_count BIGINT,
                   validation_source_missing_target_count BIGINT,
                   validation_unused_target_count BIGINT,
                   validation_duplicate_target_key_count BIGINT
               )
    ), changed_results AS (
        UPDATE workflow.analysis_result AS stored
           SET validation_workflow_run_id = p_workflow_run_id,
               validation_source_context_digest =
                   payload.source_context_digest,
               validation_policy_version =
                   payload.validation_policy_version,
               validation_policy_digest = payload.validation_policy_digest,
               validation_result = payload.validation_result,
               validation_source_non_null_count =
                   payload.validation_source_non_null_count,
               validation_source_distinct_count =
                   payload.validation_source_distinct_count,
               validation_target_non_null_count =
                   payload.validation_target_non_null_count,
               validation_target_distinct_count =
                   payload.validation_target_distinct_count,
               validation_source_missing_target_count =
                   payload.validation_source_missing_target_count,
               validation_unused_target_count =
                   payload.validation_unused_target_count,
               validation_duplicate_target_key_count =
                   payload.validation_duplicate_target_key_count,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
          FROM result_payload AS payload
         WHERE stored.model_id = v_run.model_id
           AND stored.analysis_result_id = payload.analysis_result_id
           AND ROW(
                   stored.validation_workflow_run_id,
                   stored.validation_source_context_digest,
                   stored.validation_policy_version,
                   stored.validation_policy_digest,
                   stored.validation_result,
                   stored.validation_source_non_null_count,
                   stored.validation_source_distinct_count,
                   stored.validation_target_non_null_count,
                   stored.validation_target_distinct_count,
                   stored.validation_source_missing_target_count,
                   stored.validation_unused_target_count,
                   stored.validation_duplicate_target_key_count
               ) IS DISTINCT FROM ROW(
                   p_workflow_run_id,
                   payload.source_context_digest,
                   payload.validation_policy_version,
                   payload.validation_policy_digest,
                   payload.validation_result,
                   payload.validation_source_non_null_count,
                   payload.validation_source_distinct_count,
                   payload.validation_target_non_null_count,
                   payload.validation_target_distinct_count,
                   payload.validation_source_missing_target_count,
                   payload.validation_unused_target_count,
                   payload.validation_duplicate_target_key_count
               )
        RETURNING 1
    )
    SELECT count(*)::INTEGER
      INTO v_changed_result_count
      FROM changed_results;

    IF v_changed_result_count > 0 THEN
        UPDATE model.model AS target_model
           SET model_revision = target_model.model_revision + 1,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
         WHERE target_model.model_id = v_run.model_id
        RETURNING target_model.model_revision INTO v_model_revision;

        INSERT INTO model.model_revision_transaction (
            model_id,
            change_kind
        ) VALUES (
            v_run.model_id,
            'web_analysis_validation_results_persist'
        );
    ELSE
        v_model_revision := v_run.model_revision;
    END IF;

    RETURN QUERY SELECT
        v_changed_result_count > 0,
        v_run.workflow_run_id::BIGINT,
        v_run.model_id::BIGINT,
        v_model_revision,
        v_result_count,
        v_changed_result_count;
END;
$persist_analysis_validation_results$;

REVOKE ALL ON FUNCTION application.persist_analysis_validation_results(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    JSONB
) FROM PUBLIC;

CREATE FUNCTION application.persist_profiling_results(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_profiles JSONB
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    submitted_profile_count INTEGER,
    changed_profile_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $persist_profiling_results$
DECLARE
    v_run RECORD;
    v_decision RECORD;
    v_profile_count INTEGER;
    v_selected_scope_count INTEGER;
    v_eligible_selected_object_count INTEGER;
    v_expected_attribute_ids BIGINT[];
    v_expected_object_ids BIGINT[];
    v_expected_context_digests JSONB;
    v_payload_attribute_ids BIGINT[];
    v_payload_object_ids BIGINT[];
    v_payload_context_digests JSONB;
    v_removed_profile_count INTEGER;
    v_changed_profile_count INTEGER;
    v_model_revision BIGINT;
BEGIN
    IF p_profiles IS NULL
       OR jsonb_typeof(p_profiles) <> 'array'
       OR octet_length(p_profiles::TEXT) > 33554432 THEN
        RAISE EXCEPTION
            'Profiling results must be a JSON array no larger than 32 MiB';
    END IF;

    v_profile_count := jsonb_array_length(p_profiles);
    IF v_profile_count NOT BETWEEN 0 AND 50000 THEN
        RAISE EXCEPTION
            'Profiling results must contain between 0 and 50000 Profiles';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_profiles) AS profile(value)
         WHERE jsonb_typeof(profile.value) <> 'object'
            OR NOT profile.value ?& ARRAY[
                   'object_id',
                   'attribute_id',
                   'source_context_digest',
                   'row_count',
                   'non_null_count',
                   'null_count',
                   'blank_count',
                   'distinct_count',
                   'min_data_length',
                   'max_data_length',
                   'avg_data_length',
                   'percent_populated',
                   'percent_duplicates',
                   'percent_null',
                   'percent_blank',
                   'percent_distinct'
               ]::TEXT[]
            OR (
                   SELECT count(*)
                     FROM jsonb_object_keys(profile.value)
               ) <> 16
            OR jsonb_typeof(profile.value -> 'object_id') <> 'number'
            OR (profile.value ->> 'object_id') !~ '^[1-9][0-9]*$'
            OR jsonb_typeof(profile.value -> 'attribute_id') <> 'number'
            OR (profile.value ->> 'attribute_id') !~ '^[1-9][0-9]*$'
            OR jsonb_typeof(
                   profile.value -> 'source_context_digest'
               ) <> 'string'
            OR (profile.value ->> 'source_context_digest')
               !~ '^[0-9a-f]{64}$'
            OR jsonb_typeof(profile.value -> 'row_count') <> 'number'
            OR (profile.value ->> 'row_count') !~ '^(0|[1-9][0-9]*)$'
            OR jsonb_typeof(profile.value -> 'non_null_count') <> 'number'
            OR (profile.value ->> 'non_null_count')
               !~ '^(0|[1-9][0-9]*)$'
            OR jsonb_typeof(profile.value -> 'null_count') <> 'number'
            OR (profile.value ->> 'null_count') !~ '^(0|[1-9][0-9]*)$'
            OR jsonb_typeof(profile.value -> 'blank_count')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'blank_count') = 'number'
                   AND (profile.value ->> 'blank_count')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'distinct_count')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'distinct_count') = 'number'
                   AND (profile.value ->> 'distinct_count')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'min_data_length')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'min_data_length') = 'number'
                   AND (profile.value ->> 'min_data_length')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'max_data_length')
               NOT IN ('number', 'null')
            OR (
                   jsonb_typeof(profile.value -> 'max_data_length') = 'number'
                   AND (profile.value ->> 'max_data_length')
                       !~ '^(0|[1-9][0-9]*)$'
               )
            OR jsonb_typeof(profile.value -> 'avg_data_length')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_populated')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_duplicates')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_null')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_blank')
               NOT IN ('number', 'null')
            OR jsonb_typeof(profile.value -> 'percent_distinct')
               NOT IN ('number', 'null')
    ) THEN
        RAISE EXCEPTION 'Profiling result payload shape is invalid';
    END IF;

    IF v_profile_count <> (
        SELECT count(DISTINCT profile.attribute_id)
          FROM jsonb_to_recordset(p_profiles) AS profile(
                   attribute_id BIGINT
               )
    ) THEN
        RAISE EXCEPTION 'Profiling result Attribute IDs must be unique';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_to_recordset(p_profiles) AS profile(
                   row_count BIGINT,
                   non_null_count BIGINT,
                   null_count BIGINT,
                   blank_count BIGINT,
                   distinct_count BIGINT,
                   min_data_length INTEGER,
                   max_data_length INTEGER,
                   percent_populated NUMERIC(7, 4),
                   percent_duplicates NUMERIC(7, 4),
                   percent_null NUMERIC(7, 4),
                   percent_blank NUMERIC(7, 4),
                   percent_distinct NUMERIC(7, 4)
               )
         WHERE profile.non_null_count::NUMERIC + profile.null_count <>
               profile.row_count
            OR profile.blank_count > profile.non_null_count
            OR profile.distinct_count > profile.non_null_count
            OR profile.min_data_length > profile.max_data_length
            OR profile.percent_populated IS DISTINCT FROM CASE
                   WHEN profile.row_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.non_null_count /
                       profile.row_count,
                       4
                   )
               END
            OR profile.percent_null IS DISTINCT FROM CASE
                   WHEN profile.row_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.null_count /
                       profile.row_count,
                       4
                   )
               END
            OR profile.percent_duplicates IS DISTINCT FROM CASE
                   WHEN profile.distinct_count IS NULL THEN NULL::NUMERIC
                   WHEN profile.non_null_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * (
                           profile.non_null_count - profile.distinct_count
                       ) / profile.non_null_count,
                       4
                   )
               END
            OR profile.percent_blank IS DISTINCT FROM CASE
                   WHEN profile.blank_count IS NULL THEN NULL::NUMERIC
                   WHEN profile.non_null_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.blank_count /
                       profile.non_null_count,
                       4
                   )
               END
            OR profile.percent_distinct IS DISTINCT FROM CASE
                   WHEN profile.distinct_count IS NULL THEN NULL::NUMERIC
                   WHEN profile.non_null_count = 0 THEN 0::NUMERIC
                   ELSE round(
                       100::NUMERIC * profile.distinct_count /
                       profile.non_null_count,
                       4
                   )
               END
    ) THEN
        RAISE EXCEPTION 'Profiling result metrics do not reconcile';
    END IF;

    SELECT run.workflow_run_id,
           run.model_id,
           run.actor_principal_id,
           run.model_workflow,
           run.workflow_run_state,
           run.requested_batch_id,
           run.selected_scope_count,
           target_model.tenant_id,
           target_model.model_revision
      INTO v_run
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.is_active
     WHERE run.workflow_run_id = p_workflow_run_id
     FOR UPDATE OF run, target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Profiling Workflow Run is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_run.tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Profiling result persistence denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_run.actor_principal_id <> v_decision.principal_id THEN
        RAISE EXCEPTION 'Workflow Run belongs to another Principal';
    END IF;
    IF v_run.model_workflow <> 'profiling'
       OR v_run.workflow_run_state <> 'running' THEN
        RAISE EXCEPTION
            'A running Profiling Workflow Run is required';
    END IF;
    IF p_expected_model_revision IS NULL
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    SELECT count(*)::INTEGER
      INTO v_selected_scope_count
      FROM application.workflow_run_object_selection AS selection
     WHERE selection.workflow_run_id = p_workflow_run_id;
    IF v_selected_scope_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION 'Workflow Run Selected Scope is incomplete';
    END IF;

    -- Freeze selected physical membership for this transaction. Object locks
    -- fence new Attributes through their foreign key; Attribute locks fence
    -- activation and membership changes.
    PERFORM object_record.object_id
      FROM application.workflow_run_object_selection AS selection
      JOIN model.model_scope AS scope
        ON scope.model_id = selection.model_id
       AND scope.object_id = selection.object_id
       AND scope.is_active
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = object_record.connection_id
       AND connection.is_active
      LEFT JOIN core.tenant_metadata_discovery_scope AS discovery_scope
        ON connection.is_global_data_store
       AND discovery_scope.gds_connection_id = connection.connection_id
       AND discovery_scope.zone_id = object_record.zone_id
       AND lower(btrim(discovery_scope.object_schema)) =
           lower(btrim(object_record.object_schema))
       AND discovery_scope.is_active
      JOIN core.tenant AS object_tenant
        ON object_tenant.is_active
       AND (
               (
                   NOT connection.is_global_data_store
                   AND object_tenant.tenant_id = connection.tenant_id
               )
               OR (
                   connection.is_global_data_store
                   AND object_tenant.tenant_id = discovery_scope.tenant_id
               )
           )
      JOIN core.system AS system
        ON system.system_id = connection.system_id
       AND system.is_active
      JOIN reference.zone AS zone
        ON zone.zone_id = object_record.zone_id
       AND zone.is_active
       AND lower(btrim(zone.zone_code)) = 'bronze'
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
     ORDER BY object_record.object_id
     FOR UPDATE OF object_record
     FOR SHARE OF selection, scope, connection, object_tenant, system, zone;
    GET DIAGNOSTICS v_eligible_selected_object_count = ROW_COUNT;
    IF v_eligible_selected_object_count <> v_run.selected_scope_count THEN
        RAISE EXCEPTION
            'Workflow Run Selected Scope membership has changed';
    END IF;

    PERFORM attribute.attribute_id
      FROM application.workflow_run_object_selection AS selection
      JOIN core.attribute AS attribute
        ON attribute.object_id = selection.object_id
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id
     ORDER BY attribute.attribute_id
     FOR UPDATE OF attribute;

    SELECT coalesce(
               array_agg(
                   eligible.attribute_id
                   ORDER BY eligible.attribute_id
               ),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               array_agg(
                   eligible.object_id
                   ORDER BY eligible.attribute_id
               ),
               ARRAY[]::BIGINT[]
           )
      INTO v_expected_attribute_ids,
           v_expected_object_ids
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
           AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_bronze_source_eligible
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;

    SELECT coalesce(
               array_agg(profile.attribute_id ORDER BY profile.attribute_id),
               ARRAY[]::BIGINT[]
           ),
           coalesce(
               array_agg(profile.object_id ORDER BY profile.attribute_id),
               ARRAY[]::BIGINT[]
           )
      INTO v_payload_attribute_ids,
           v_payload_object_ids
      FROM jsonb_to_recordset(p_profiles) AS profile(
               object_id BIGINT,
               attribute_id BIGINT
           );
    IF v_payload_attribute_ids IS DISTINCT FROM v_expected_attribute_ids
       OR v_payload_object_ids IS DISTINCT FROM v_expected_object_ids THEN
        RAISE EXCEPTION
            'Profiling results must exactly cover the eligible Selected Scope Attributes';
    END IF;

    SELECT coalesce(
               jsonb_object_agg(
                   attribute.attribute_id::TEXT,
                   encode(
                       sha256(
                           convert_to(
                               '{"attribute_data_type":' ||
                               to_jsonb(attribute.attribute_data_type)::TEXT ||
                               ',"attribute_id":' ||
                               attribute.attribute_id::TEXT ||
                               ',"attribute_name":' ||
                               to_jsonb(attribute.attribute_name)::TEXT ||
                               ',"batch_attribute_name":' ||
                               coalesce(
                                   to_jsonb(
                                       object_record.batch_attribute_name
                                   )::TEXT,
                                   'null'
                               ) ||
                               ',"catalog":' ||
                               to_jsonb(source_tenant.tenant_catalog)::TEXT ||
                               ',"object_id":' ||
                               object_record.object_id::TEXT ||
                               ',"requested_batch_id":' ||
                               coalesce(
                                   to_jsonb(v_run.requested_batch_id)::TEXT,
                                   'null'
                               ) ||
                               ',"schema":' ||
                               to_jsonb(object_record.object_schema)::TEXT ||
                               ',"table":' ||
                               to_jsonb(object_record.object_name)::TEXT ||
                               '}',
                               'UTF8'
                           )
                       ),
                       'hex'
                   )
                   ORDER BY attribute.attribute_id
               ),
               '{}'::JSONB
           )
      INTO v_expected_context_digests
      FROM application.workflow_run_object_selection AS selection
      JOIN workflow.list_model_attribute_eligibility(v_run.model_id)
           AS eligible
        ON eligible.model_id = selection.model_id
       AND eligible.object_id = selection.object_id
       AND eligible.is_bronze_source_eligible
      JOIN core.attribute AS attribute
        ON attribute.attribute_id = eligible.attribute_id
       AND attribute.object_id = eligible.object_id
       AND attribute.is_active
      JOIN core.object AS object_record
        ON object_record.object_id = selection.object_id
       AND object_record.is_active
      JOIN core.connection AS connection
        ON connection.connection_id = object_record.connection_id
       AND connection.is_active
      LEFT JOIN core.tenant_metadata_discovery_scope AS discovery_scope
        ON connection.is_global_data_store
       AND discovery_scope.gds_connection_id = connection.connection_id
       AND discovery_scope.zone_id = object_record.zone_id
       AND lower(btrim(discovery_scope.object_schema)) =
           lower(btrim(object_record.object_schema))
       AND discovery_scope.is_active
      JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = CASE
               WHEN connection.is_global_data_store
                   THEN discovery_scope.tenant_id
               ELSE connection.tenant_id
           END
       AND source_tenant.is_active
     WHERE selection.workflow_run_id = p_workflow_run_id
       AND selection.model_id = v_run.model_id;

    SELECT coalesce(
               jsonb_object_agg(
                   profile.attribute_id::TEXT,
                   profile.source_context_digest
                   ORDER BY profile.attribute_id
               ),
               '{}'::JSONB
           )
      INTO v_payload_context_digests
      FROM jsonb_to_recordset(p_profiles) AS profile(
               attribute_id BIGINT,
               source_context_digest TEXT
           );
    IF v_payload_context_digests IS DISTINCT FROM
       v_expected_context_digests THEN
        RAISE EXCEPTION 'Profiling result source context has changed';
    END IF;

    WITH profile_payload AS MATERIALIZED (
        SELECT profile.*
          FROM jsonb_to_recordset(p_profiles) AS profile(
                   object_id BIGINT,
                   attribute_id BIGINT,
                   source_context_digest TEXT,
                   row_count BIGINT,
                   non_null_count BIGINT,
                   null_count BIGINT,
                   blank_count BIGINT,
                   distinct_count BIGINT,
                   min_data_length INTEGER,
                   max_data_length INTEGER,
                   avg_data_length NUMERIC(20, 6),
                   percent_populated NUMERIC(7, 4),
                   percent_duplicates NUMERIC(7, 4),
                   percent_null NUMERIC(7, 4),
                   percent_blank NUMERIC(7, 4),
                   percent_distinct NUMERIC(7, 4)
               )
    ),
    removed_profiles AS (
        DELETE FROM workflow.attribute_profile AS stored
         USING application.workflow_run_object_selection AS selection
         WHERE selection.workflow_run_id = p_workflow_run_id
           AND selection.model_id = v_run.model_id
           AND stored.model_id = selection.model_id
           AND stored.object_id = selection.object_id
           AND NOT EXISTS (
                   SELECT 1
                     FROM profile_payload AS profile
                    WHERE profile.attribute_id = stored.attribute_id
                      AND profile.object_id = stored.object_id
               )
        RETURNING 1
    ),
    changed_profiles AS (
        INSERT INTO workflow.attribute_profile AS stored (
            model_id,
            attribute_id,
            object_id,
            agent_run_id,
            workflow_run_id,
            source_context_digest,
            row_count,
            non_null_count,
            null_count,
            blank_count,
            distinct_count,
            min_data_length,
            max_data_length,
            avg_data_length,
            percent_populated,
            percent_duplicates,
            percent_null,
            percent_blank,
            percent_distinct
        )
        SELECT v_run.model_id,
               profile.attribute_id,
               profile.object_id,
               NULL,
               p_workflow_run_id,
               profile.source_context_digest,
               profile.row_count,
               profile.non_null_count,
               profile.null_count,
               profile.blank_count,
               profile.distinct_count,
               profile.min_data_length,
               profile.max_data_length,
               profile.avg_data_length,
               profile.percent_populated,
               profile.percent_duplicates,
               profile.percent_null,
               profile.percent_blank,
               profile.percent_distinct
          FROM profile_payload AS profile
         ORDER BY profile.attribute_id
        ON CONFLICT ON CONSTRAINT attribute_profile_pkey DO UPDATE
           SET object_id = EXCLUDED.object_id,
               agent_run_id = EXCLUDED.agent_run_id,
               workflow_run_id = EXCLUDED.workflow_run_id,
               source_context_digest = EXCLUDED.source_context_digest,
               row_count = EXCLUDED.row_count,
               non_null_count = EXCLUDED.non_null_count,
               null_count = EXCLUDED.null_count,
               blank_count = EXCLUDED.blank_count,
               distinct_count = EXCLUDED.distinct_count,
               min_data_length = EXCLUDED.min_data_length,
               max_data_length = EXCLUDED.max_data_length,
               avg_data_length = EXCLUDED.avg_data_length,
               percent_populated = EXCLUDED.percent_populated,
               percent_duplicates = EXCLUDED.percent_duplicates,
               percent_null = EXCLUDED.percent_null,
               percent_blank = EXCLUDED.percent_blank,
               percent_distinct = EXCLUDED.percent_distinct,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
         WHERE ROW(
                   stored.object_id,
                   stored.agent_run_id,
                   stored.workflow_run_id,
                   stored.source_context_digest,
                   stored.row_count,
                   stored.non_null_count,
                   stored.null_count,
                   stored.blank_count,
                   stored.distinct_count,
                   stored.min_data_length,
                   stored.max_data_length,
                   stored.avg_data_length,
                   stored.percent_populated,
                   stored.percent_duplicates,
                   stored.percent_null,
                   stored.percent_blank,
                   stored.percent_distinct
               ) IS DISTINCT FROM ROW(
                   EXCLUDED.object_id,
                   EXCLUDED.agent_run_id,
                   EXCLUDED.workflow_run_id,
                   EXCLUDED.source_context_digest,
                   EXCLUDED.row_count,
                   EXCLUDED.non_null_count,
                   EXCLUDED.null_count,
                   EXCLUDED.blank_count,
                   EXCLUDED.distinct_count,
                   EXCLUDED.min_data_length,
                   EXCLUDED.max_data_length,
                   EXCLUDED.avg_data_length,
                   EXCLUDED.percent_populated,
                   EXCLUDED.percent_duplicates,
                   EXCLUDED.percent_null,
                   EXCLUDED.percent_blank,
                   EXCLUDED.percent_distinct
               )
        RETURNING 1
    )
    SELECT (SELECT count(*) FROM removed_profiles)::INTEGER,
           (SELECT count(*) FROM changed_profiles)::INTEGER
      INTO v_removed_profile_count,
           v_changed_profile_count;
    v_changed_profile_count :=
        v_removed_profile_count + v_changed_profile_count;

    IF v_changed_profile_count > 0 THEN
        UPDATE model.model AS target_model
           SET model_revision = target_model.model_revision + 1,
               updated_time = CURRENT_TIMESTAMP,
               updated_by = CURRENT_USER
         WHERE target_model.model_id = v_run.model_id
        RETURNING target_model.model_revision INTO v_model_revision;

        INSERT INTO model.model_revision_transaction (
            model_id,
            change_kind
        ) VALUES (
            v_run.model_id,
            'web_profiling_results_persist'
        );
    ELSE
        v_model_revision := v_run.model_revision;
    END IF;

    RETURN QUERY SELECT
        v_changed_profile_count > 0,
        v_run.workflow_run_id::BIGINT,
        v_run.model_id::BIGINT,
        v_model_revision,
        v_profile_count,
        v_changed_profile_count;
END;
$persist_profiling_results$;

REVOKE ALL ON FUNCTION application.persist_profiling_results(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    JSONB
) FROM PUBLIC;

-- Resolve and fence one exact notebook-owned Profiling Run. This private
-- helper keeps every notebook execution wrapper bound to the same immutable
-- Tenant, Model, base revision, actor identity, and live claim digest.
CREATE FUNCTION application.resolve_notebook_profiling_claim(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS TABLE (
    principal_id BIGINT,
    entra_principal_identity_id BIGINT,
    principal_type VARCHAR(30),
    entra_tenant_id UUID,
    entra_object_id UUID,
    databricks_environment_code VARCHAR(100)
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $resolve_notebook_profiling_claim$
DECLARE
    v_principal RECORD;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0
       OR p_model_id IS NULL OR p_model_id <= 0
       OR p_workflow_run_id IS NULL OR p_workflow_run_id <= 0
       OR p_expected_model_revision IS NULL
       OR p_expected_model_revision <= 0
       OR p_workflow_run_claim_token IS NULL THEN
        RAISE EXCEPTION 'Notebook Profiling Run is unavailable';
    END IF;

    SELECT *
      INTO v_principal
      FROM security.current_notebook_principal();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Notebook Profiling Run is unavailable';
    END IF;

    PERFORM 1
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.tenant_id = run.tenant_id
       AND target_model.is_active
       AND target_model.model_revision = p_expected_model_revision
     WHERE run.workflow_run_id = p_workflow_run_id
       AND run.tenant_id = p_tenant_id
       AND run.model_id = p_model_id
       AND run.model_revision = p_expected_model_revision
       AND run.model_workflow = 'profiling'
       AND run.workflow_execution_mode IS NULL
       AND run.workflow_run_state = 'running'
       AND run.actor_principal_id = v_principal.principal_id
       AND run.actor_entra_principal_identity_id =
           v_principal.entra_principal_identity_id
     FOR UPDATE OF run
     FOR SHARE OF target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Notebook Profiling Run is unavailable';
    END IF;

    PERFORM application.assert_workflow_run_claim(
        p_workflow_run_id,
        p_workflow_run_claim_token
    );

    RETURN QUERY SELECT
        v_principal.principal_id::BIGINT,
        v_principal.entra_principal_identity_id::BIGINT,
        v_principal.principal_type::VARCHAR(30),
        v_principal.entra_tenant_id::UUID,
        v_principal.entra_object_id::UUID,
        v_principal.databricks_environment_code::VARCHAR(100);
END;
$resolve_notebook_profiling_claim$;

REVOKE ALL ON FUNCTION application.resolve_notebook_profiling_claim(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    UUID
) FROM PUBLIC;

CREATE FUNCTION application.get_notebook_profiling_execution_context(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    requested_batch_id VARCHAR(500),
    selection_order INTEGER,
    source_tenant_id BIGINT,
    source_tenant_code VARCHAR(100),
    gds_connection_id BIGINT,
    relation_catalog VARCHAR(255),
    relation_schema VARCHAR(400),
    relation_object VARCHAR(400),
    system_id BIGINT,
    system_code VARCHAR(100),
    object_id BIGINT,
    batch_attribute_name VARCHAR(400),
    attribute_id BIGINT,
    attribute_name VARCHAR(400),
    attribute_data_type VARCHAR(100),
    attribute_ordinal_position INTEGER,
    is_batch_attribute BOOLEAN
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_notebook_profiling_execution_context$
DECLARE
    v_claim RECORD;
BEGIN
    SELECT *
      INTO v_claim
      FROM application.resolve_notebook_profiling_claim(
          p_tenant_id,
          p_model_id,
          p_workflow_run_id,
          p_expected_model_revision,
          p_workflow_run_claim_token
      );

    RETURN QUERY
    SELECT context.workflow_run_id,
           context.model_id,
           context.model_revision,
           context.requested_batch_id,
           context.selection_order,
           context.source_tenant_id,
           context.source_tenant_code,
           context.gds_connection_id,
           context.relation_catalog,
           context.relation_schema,
           context.relation_object,
           context.system_id,
           context.system_code,
           context.object_id,
           context.batch_attribute_name,
           context.attribute_id,
           context.attribute_name,
           context.attribute_data_type,
           context.attribute_ordinal_position,
           context.is_batch_attribute
      FROM application.get_profiling_execution_context(
          v_claim.entra_tenant_id,
          v_claim.entra_object_id,
          v_claim.principal_type,
          p_workflow_run_id,
          p_expected_model_revision
      ) AS context;
END;
$get_notebook_profiling_execution_context$;

REVOKE ALL ON FUNCTION application.get_notebook_profiling_execution_context(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    UUID
) FROM PUBLIC;

CREATE FUNCTION application.get_notebook_profiling_connection_values(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID
)
RETURNS TABLE (
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    gds_connection_id BIGINT,
    environment_code VARCHAR(100),
    failure_code VARCHAR(50),
    failure_message VARCHAR(200),
    databricks_host_name TEXT,
    databricks_http_path TEXT,
    databricks_token TEXT
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_notebook_profiling_connection_values$
DECLARE
    v_claim RECORD;
BEGIN
    SELECT *
      INTO v_claim
      FROM application.resolve_notebook_profiling_claim(
          p_tenant_id,
          p_model_id,
          p_workflow_run_id,
          p_expected_model_revision,
          p_workflow_run_claim_token
      );

    RETURN QUERY
    SELECT connection_values.workflow_run_id,
           connection_values.model_id,
           connection_values.model_revision,
           connection_values.gds_connection_id,
           connection_values.environment_code,
           connection_values.failure_code,
           connection_values.failure_message,
           connection_values.databricks_host_name,
           connection_values.databricks_http_path,
           connection_values.databricks_token
      FROM application.get_profiling_connection_values(
          v_claim.entra_tenant_id,
          v_claim.entra_object_id,
          v_claim.principal_type,
          p_workflow_run_id,
          p_expected_model_revision,
          v_claim.databricks_environment_code
      ) AS connection_values;
END;
$get_notebook_profiling_connection_values$;

REVOKE ALL ON FUNCTION application.get_notebook_profiling_connection_values(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    UUID
) FROM PUBLIC;

CREATE FUNCTION application.append_notebook_profiling_event(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID,
    p_event_sequence BIGINT,
    p_stage_code VARCHAR(100),
    p_status VARCHAR(30),
    p_safe_message VARCHAR(2000),
    p_current_count INTEGER,
    p_total_count INTEGER,
    p_finding_count INTEGER
)
RETURNS TABLE (
    model_event_log_id BIGINT,
    workflow_run_id BIGINT,
    event_sequence BIGINT,
    event_attempt INTEGER,
    stage_code VARCHAR(100),
    status VARCHAR(30),
    safe_message VARCHAR(2000),
    current_count INTEGER,
    total_count INTEGER,
    percent_complete NUMERIC(5, 2),
    finding_count INTEGER,
    created_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $append_notebook_profiling_event$
DECLARE
    v_claim RECORD;
BEGIN
    SELECT *
      INTO v_claim
      FROM application.resolve_notebook_profiling_claim(
          p_tenant_id,
          p_model_id,
          p_workflow_run_id,
          p_expected_model_revision,
          p_workflow_run_claim_token
      );

    RETURN QUERY
    SELECT event.model_event_log_id,
           event.workflow_run_id,
           event.model_event_log_sequence,
           event.model_event_log_attempt,
           event.model_event_log_stage,
           event.model_event_log_status,
           event.model_event_log_message,
           event.model_event_log_current,
           event.model_event_log_total,
           event.model_event_log_percent,
           event.finding_count,
           event.created_time
      FROM application.append_workflow_run_event(
          v_claim.entra_tenant_id,
          v_claim.entra_object_id,
          v_claim.principal_type,
          p_workflow_run_id,
          p_expected_model_revision,
          p_event_sequence,
          1,
          p_stage_code,
          p_status,
          p_safe_message,
          p_current_count,
          p_total_count,
          p_finding_count
      ) AS event;
END;
$append_notebook_profiling_event$;

REVOKE ALL ON FUNCTION application.append_notebook_profiling_event(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    UUID,
    BIGINT,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER,
    INTEGER,
    INTEGER
) FROM PUBLIC;

-- Profile replacement and terminal completion are one database statement and
-- therefore one transaction. Any persistence or completion error rolls back
-- both the Profile writes and Model revision change.
CREATE FUNCTION application.persist_and_complete_notebook_profiling_run(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID,
    p_profiles JSONB
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    model_id BIGINT,
    model_revision BIGINT,
    submitted_profile_count INTEGER,
    changed_profile_count INTEGER,
    workflow_run_state VARCHAR(30),
    completed_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $persist_and_complete_notebook_profiling_run$
DECLARE
    v_claim RECORD;
    v_persisted RECORD;
    v_completed RECORD;
BEGIN
    SELECT *
      INTO v_claim
      FROM application.resolve_notebook_profiling_claim(
          p_tenant_id,
          p_model_id,
          p_workflow_run_id,
          p_expected_model_revision,
          p_workflow_run_claim_token
      );

    SELECT *
      INTO v_persisted
      FROM application.persist_profiling_results(
          v_claim.entra_tenant_id,
          v_claim.entra_object_id,
          v_claim.principal_type,
          p_workflow_run_id,
          p_expected_model_revision,
          p_profiles
      );
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Notebook Profiling result persistence failed';
    END IF;

    SELECT *
      INTO v_completed
      FROM application.complete_workflow_run(
          v_claim.entra_tenant_id,
          v_claim.entra_object_id,
          v_claim.principal_type,
          p_workflow_run_id,
          v_persisted.model_revision,
          v_persisted.submitted_profile_count
      );
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Notebook Profiling completion failed';
    END IF;

    RETURN QUERY SELECT
        v_persisted.changed::BOOLEAN,
        v_persisted.workflow_run_id::BIGINT,
        v_persisted.model_id::BIGINT,
        v_persisted.model_revision::BIGINT,
        v_persisted.submitted_profile_count::INTEGER,
        v_persisted.changed_profile_count::INTEGER,
        v_completed.workflow_run_state::VARCHAR(30),
        v_completed.completed_time::TIMESTAMPTZ;
END;
$persist_and_complete_notebook_profiling_run$;

REVOKE ALL ON FUNCTION
application.persist_and_complete_notebook_profiling_run(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    UUID,
    JSONB
) FROM PUBLIC;

CREATE FUNCTION application.fail_notebook_profiling_run(
    p_tenant_id BIGINT,
    p_model_id BIGINT,
    p_workflow_run_id BIGINT,
    p_expected_model_revision BIGINT,
    p_workflow_run_claim_token UUID,
    p_failure_code VARCHAR(100),
    p_safe_failure_message VARCHAR(2000)
)
RETURNS TABLE (
    changed BOOLEAN,
    workflow_run_id BIGINT,
    workflow_run_state VARCHAR(30),
    completed_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $fail_notebook_profiling_run$
DECLARE
    v_claim RECORD;
BEGIN
    SELECT *
      INTO v_claim
      FROM application.resolve_notebook_profiling_claim(
          p_tenant_id,
          p_model_id,
          p_workflow_run_id,
          p_expected_model_revision,
          p_workflow_run_claim_token
      );

    RETURN QUERY
    SELECT failed.changed,
           failed.workflow_run_id,
           failed.workflow_run_state,
           failed.completed_time
      FROM application.fail_workflow_run(
          v_claim.entra_tenant_id,
          v_claim.entra_object_id,
          v_claim.principal_type,
          p_workflow_run_id,
          p_expected_model_revision,
          p_failure_code,
          p_safe_failure_message
      ) AS failed;
END;
$fail_notebook_profiling_run$;

REVOKE ALL ON FUNCTION application.fail_notebook_profiling_run(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    UUID,
    VARCHAR,
    VARCHAR
) FROM PUBLIC;

CREATE TABLE application.generated_sql_artifact (
    generated_sql_artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    model_revision BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    object_id BIGINT NOT NULL,
    mapping_context_digest CHAR(64) NOT NULL,
    source_context_digest CHAR(64) NOT NULL,
    sql_generation_guide_id BIGINT NOT NULL,
    sql_generation_guide_version_id BIGINT NOT NULL,
    sql_generation_guide_digest CHAR(64) NOT NULL,
    workflow_run_id BIGINT,
    generator_code VARCHAR(100) NOT NULL,
    generator_version VARCHAR(50) NOT NULL,
    generated_by_principal_id BIGINT NOT NULL,
    generated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    generated_sql TEXT NOT NULL,
    generated_sql_digest CHAR(64) NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_generated_sql_artifact_scope FOREIGN KEY (
        model_id,
        object_id
    ) REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_generated_sql_artifact_guide_version FOREIGN KEY (
        sql_generation_guide_version_id,
        sql_generation_guide_id,
        sql_generation_guide_digest
    ) REFERENCES application.sql_generation_guide_version (
        sql_generation_guide_version_id,
        sql_generation_guide_id,
        sql_generation_guide_digest
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_generated_sql_artifact_generator FOREIGN KEY (
        generated_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_generated_sql_artifact_run FOREIGN KEY (
        workflow_run_id,
        model_id
    ) REFERENCES application.workflow_run (workflow_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_generated_sql_artifact_identity UNIQUE (
        model_id,
        modeled_entity_type,
        object_id
    ),
    CONSTRAINT ck_generated_sql_artifact_model_revision CHECK (
        model_revision > 0
    ),
    CONSTRAINT ck_generated_sql_artifact_entity_type CHECK (
        modeled_entity_type IN ('logical_entity', 'dimensional_entity')
    ),
    CONSTRAINT ck_generated_sql_artifact_digests CHECK (
        mapping_context_digest ~ '^[0-9a-f]{64}$'
        AND source_context_digest ~ '^[0-9a-f]{64}$'
        AND sql_generation_guide_digest ~ '^[0-9a-f]{64}$'
        AND generated_sql_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_generated_sql_artifact_generator CHECK (
        generator_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        AND generator_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),
    CONSTRAINT ck_generated_sql_artifact_sql CHECK (
        reference.is_nonblank(generated_sql)
        AND octet_length(generated_sql) <= 4194304
    )
);

CREATE INDEX ix_generated_sql_artifact_run
    ON application.generated_sql_artifact (workflow_run_id)
    WHERE workflow_run_id IS NOT NULL;

CREATE FUNCTION application.store_generated_sql_artifact(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_model_id BIGINT,
    p_expected_model_revision BIGINT,
    p_modeled_entity_type VARCHAR(30),
    p_object_id BIGINT,
    p_mapping_context_digest CHAR(64),
    p_source_context_digest CHAR(64),
    p_sql_generation_guide_version_id BIGINT,
    p_workflow_run_id BIGINT,
    p_generator_code VARCHAR(100),
    p_generator_version VARCHAR(50),
    p_generated_sql TEXT,
    p_generated_sql_digest CHAR(64)
)
RETURNS SETOF application.generated_sql_artifact
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $store_generated_sql_artifact$
DECLARE
    v_model_tenant_id BIGINT;
    v_decision RECORD;
    v_actor_entra_principal_identity_id BIGINT;
    v_target RECORD;
    v_sql_generation_guide_id BIGINT;
    v_sql_generation_guide_digest CHAR(64);
    v_run RECORD;
    v_actual_sql_digest CHAR(64);
    v_stored application.generated_sql_artifact%ROWTYPE;
BEGIN
    SELECT target_model.tenant_id
      INTO v_model_tenant_id
      FROM model.model AS target_model
     WHERE target_model.model_id = p_model_id
       AND target_model.is_active
       AND target_model.model_revision = p_expected_model_revision
     FOR SHARE OF target_model;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'generated SQL Model is unavailable';
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          v_model_tenant_id,
          'tenant_model_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'generated SQL storage denied: %',
            coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;

    SELECT identity.entra_principal_identity_id
      INTO v_actor_entra_principal_identity_id
      FROM security.entra_principal_identity AS identity
     WHERE identity.principal_id = v_decision.principal_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.is_active
     FOR SHARE OF identity;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'generated SQL actor identity is unavailable';
    END IF;

    SELECT context.*
      INTO v_target
      FROM workflow.list_code_generation_target_context(
               p_model_id,
               p_modeled_entity_type
           ) AS context
     WHERE context.object_id = p_object_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'generated SQL target is not eligible';
    END IF;
    IF v_target.mapping_context_digest IS DISTINCT FROM
       p_mapping_context_digest THEN
        RAISE EXCEPTION 'generated SQL Mapping context digest is stale';
    END IF;
    IF v_target.source_context_digest IS DISTINCT FROM
       p_source_context_digest THEN
        RAISE EXCEPTION 'generated SQL source context digest is stale';
    END IF;

    IF p_workflow_run_id IS NOT NULL THEN
        SELECT run.actor_principal_id,
               run.actor_entra_principal_identity_id,
               run.sql_generation_guide_id,
               run.sql_generation_guide_version_id,
               run.sql_generation_guide_digest
          INTO v_run
          FROM application.workflow_run AS run
         WHERE run.workflow_run_id = p_workflow_run_id
           AND run.model_id = p_model_id
           AND run.model_revision = p_expected_model_revision
           AND run.model_workflow = 'code_generation'
           AND run.workflow_run_state = 'running'
           AND run.modeled_entity_type = p_modeled_entity_type
           AND run.actor_principal_id = v_decision.principal_id
           AND run.actor_entra_principal_identity_id =
               v_actor_entra_principal_identity_id
           AND run.sql_generation_guide_version_id =
               p_sql_generation_guide_version_id
           AND EXISTS (
               SELECT 1
                 FROM application.workflow_run_object_selection AS selection
                WHERE selection.workflow_run_id = run.workflow_run_id
                  AND selection.model_id = run.model_id
                  AND selection.object_id = p_object_id
           )
         FOR SHARE OF run;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'running Code Generation Workflow Run is required';
        END IF;
        v_sql_generation_guide_id := v_run.sql_generation_guide_id;
        v_sql_generation_guide_digest :=
            v_run.sql_generation_guide_digest;
    ELSE
        SELECT guide_version.sql_generation_guide_id,
               guide_version.sql_generation_guide_digest
          INTO v_sql_generation_guide_id,
               v_sql_generation_guide_digest
          FROM application.sql_generation_guide_version AS guide_version
          JOIN application.sql_generation_guide AS guide
            ON guide.sql_generation_guide_id =
               guide_version.sql_generation_guide_id
           AND guide.is_active
         WHERE guide_version.sql_generation_guide_version_id =
               p_sql_generation_guide_version_id
           AND guide_version.sql_generation_guide_version_status = 'published'
         FOR SHARE OF guide_version, guide;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'published SQL generation guide is required';
        END IF;
    END IF;

    v_actual_sql_digest := encode(
        sha256(convert_to(p_generated_sql, 'UTF8')),
        'hex'
    );
    IF v_actual_sql_digest <> p_generated_sql_digest THEN
        RAISE EXCEPTION 'generated SQL digest does not match the SQL content';
    END IF;

    INSERT INTO application.generated_sql_artifact AS artifact (
        model_id,
        model_revision,
        modeled_entity_type,
        object_id,
        mapping_context_digest,
        source_context_digest,
        sql_generation_guide_id,
        sql_generation_guide_version_id,
        sql_generation_guide_digest,
        workflow_run_id,
        generator_code,
        generator_version,
        generated_by_principal_id,
        generated_sql,
        generated_sql_digest
    ) VALUES (
        p_model_id,
        p_expected_model_revision,
        p_modeled_entity_type,
        p_object_id,
        p_mapping_context_digest,
        p_source_context_digest,
        v_sql_generation_guide_id,
        p_sql_generation_guide_version_id,
        v_sql_generation_guide_digest,
        p_workflow_run_id,
        p_generator_code,
        p_generator_version,
        v_decision.principal_id,
        p_generated_sql,
        p_generated_sql_digest
    )
    ON CONFLICT (
        model_id,
        modeled_entity_type,
        object_id
    ) DO UPDATE
       SET model_revision = EXCLUDED.model_revision,
           mapping_context_digest = EXCLUDED.mapping_context_digest,
           source_context_digest = EXCLUDED.source_context_digest,
           sql_generation_guide_id = EXCLUDED.sql_generation_guide_id,
           sql_generation_guide_version_id =
               EXCLUDED.sql_generation_guide_version_id,
           sql_generation_guide_digest =
               EXCLUDED.sql_generation_guide_digest,
           workflow_run_id = EXCLUDED.workflow_run_id,
           generator_code = EXCLUDED.generator_code,
           generator_version = EXCLUDED.generator_version,
           generated_by_principal_id = EXCLUDED.generated_by_principal_id,
           generated_time = CURRENT_TIMESTAMP,
           generated_sql = EXCLUDED.generated_sql,
           generated_sql_digest = EXCLUDED.generated_sql_digest,
           updated_time = CURRENT_TIMESTAMP,
           updated_by = CURRENT_USER
    RETURNING artifact.* INTO v_stored;

    RETURN NEXT v_stored;
END;
$store_generated_sql_artifact$;

REVOKE ALL ON FUNCTION application.store_generated_sql_artifact(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT,
    CHAR,
    CHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
    TEXT,
    CHAR
) FROM PUBLIC;
