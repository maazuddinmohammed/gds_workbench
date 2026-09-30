-- GDS ETL Workbench Release 1: application configuration and authoring policy.

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
    p_logical_schemas JSONB,
    p_dimensional_schemas JSONB,
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
    p_default_validation_retry_count INTEGER,
    p_default_mapping_source_system_id BIGINT DEFAULT NULL,
    p_logical_entity_scd_type VARCHAR(10) DEFAULT NULL
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

    IF p_default_mapping_source_system_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core.connection AS connection
        JOIN core.system AS system ON system.system_id = connection.system_id AND system.is_active
        WHERE connection.tenant_id = p_tenant_id AND connection.is_active
          AND system.system_id = p_default_mapping_source_system_id
    ) THEN
        RAISE EXCEPTION 'Default Mapping System is unavailable for this Tenant';
    END IF;

    INSERT INTO model.model AS target_model (
        tenant_id,
        model_name,
        model_description,
        logical_schemas,
        dimensional_schemas,
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
        default_validation_retry_count,
        default_mapping_source_system_id,
        logical_entity_scd_type
    ) VALUES (
        p_tenant_id,
        p_model_name,
        p_model_description,
        p_logical_schemas,
        p_dimensional_schemas,
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
        p_default_validation_retry_count,
        p_default_mapping_source_system_id,
        p_logical_entity_scd_type
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
    JSONB,
    JSONB,
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
    INTEGER,
    BIGINT,
    VARCHAR
) FROM PUBLIC;

CREATE FUNCTION application.update_model(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_model_id BIGINT,
    p_expected_model_revision BIGINT,
    p_model_name VARCHAR(255),
    p_model_description VARCHAR(2000),
    p_logical_schemas JSONB,
    p_dimensional_schemas JSONB,
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
    p_default_validation_retry_count INTEGER,
    p_default_mapping_source_system_id BIGINT DEFAULT NULL,
    p_logical_entity_scd_type VARCHAR(10) DEFAULT NULL
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
    IF p_default_mapping_source_system_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core.connection AS connection
        JOIN core.system AS system ON system.system_id = connection.system_id AND system.is_active
        WHERE connection.tenant_id = v_existing.tenant_id AND connection.is_active
          AND system.system_id = p_default_mapping_source_system_id
    ) THEN
        RAISE EXCEPTION 'Default Mapping System is unavailable for this Tenant';
    END IF;
    IF ROW(
        v_existing.model_name,
        v_existing.model_description,
        v_existing.logical_schemas,
        v_existing.dimensional_schemas,
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
        v_existing.default_validation_retry_count,
        v_existing.default_mapping_source_system_id,
        v_existing.logical_entity_scd_type
    ) IS NOT DISTINCT FROM ROW(
        p_model_name,
        p_model_description,
        p_logical_schemas,
        p_dimensional_schemas,
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
        p_default_validation_retry_count,
        p_default_mapping_source_system_id,
        p_logical_entity_scd_type
    ) THEN
        RETURN NEXT v_existing;
        RETURN;
    END IF;

    v_updated_time := clock_timestamp();
    UPDATE model.model AS target_model
       SET model_name = p_model_name,
           model_description = p_model_description,
           logical_schemas = p_logical_schemas,
           dimensional_schemas = p_dimensional_schemas,
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
           default_mapping_source_system_id = p_default_mapping_source_system_id,
           logical_entity_scd_type = p_logical_entity_scd_type,
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
    JSONB,
    JSONB,
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
    INTEGER,
    BIGINT,
    VARCHAR
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
            'dimensional', 'mapping', 'code_generation', 'validation',
            'metadata_enrichment', 'metadata_enrichment_object', 'metadata_enrichment_attribute'
        )
    ),
    CONSTRAINT ck_workflow_stage_execution_mode CHECK (
        workflow_execution_mode IS NULL
        OR workflow_execution_mode IN (
            'one_shot', 'tool_assisted'
        )
    ),
    CONSTRAINT ck_workflow_stage_metadata_enrichment_mode CHECK (
        model_workflow NOT IN ('metadata_enrichment', 'metadata_enrichment_object', 'metadata_enrichment_attribute')
        OR workflow_execution_mode IS NOT DISTINCT FROM 'one_shot'
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
    agent_tool_names TEXT[],
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
    v_mode VARCHAR(30);
    v_workflow VARCHAR(30);
    v_allowed_tools TEXT[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'prompt versions cannot be deleted';
    END IF;

    IF NEW.agent_tool_names IS NOT NULL THEN
        SELECT workflow_execution_mode, model_workflow INTO v_mode, v_workflow
          FROM application.workflow_stage WHERE workflow_stage_id = NEW.workflow_stage_id;
        v_allowed_tools := CASE v_workflow
            WHEN 'analysis' THEN ARRAY['get_source_context', 'get_gds_context', 'get_objects', 'get_object_details', 'get_object_relationships', 'get_modeling_assertions']
            WHEN 'conceptual' THEN ARRAY['get_source_context', 'get_gds_context', 'get_objects', 'get_object_details', 'get_object_relationships', 'get_modeling_assertions', 'list_conceptual_objects', 'get_conceptual_objects', 'list_conceptual_relationships', 'get_conceptual_relationships']
            WHEN 'logical' THEN ARRAY['get_source_context', 'get_gds_context', 'get_objects', 'get_object_details', 'get_object_relationships', 'get_modeling_assertions', 'list_conceptual_objects', 'get_conceptual_objects', 'list_conceptual_relationships', 'get_conceptual_relationships', 'list_logical_submodels', 'get_logical_submodels', 'list_logical_entities', 'get_logical_entities', 'list_logical_attributes', 'get_logical_attributes', 'list_logical_relationships', 'get_logical_relationships']
            WHEN 'dimensional' THEN ARRAY['get_source_context', 'get_objects', 'get_object_details', 'get_object_relationships', 'get_gds_context', 'get_selected_logical_entities', 'get_modeling_assertions', 'list_logical_submodels', 'get_logical_submodels', 'list_logical_entities', 'get_logical_entities', 'list_logical_attributes', 'get_logical_attributes', 'list_logical_relationships', 'get_logical_relationships', 'list_dimensional_submodels', 'get_dimensional_submodels', 'list_dimensional_entities', 'get_dimensional_entities', 'list_dimensional_attributes', 'get_dimensional_attributes', 'list_dimensional_relationships', 'get_dimensional_relationships']
            WHEN 'mapping' THEN ARRAY['get_mapping_target', 'get_mapping_sources', 'get_existing_mapping', 'get_mapping_support', 'get_mapping_support_records']
            WHEN 'code_generation' THEN ARRAY['get_code_target', 'get_code_sources', 'get_code_source_systems', 'get_object_transformations', 'get_attribute_transformations']
            WHEN 'validation' THEN ARRAY['get_mapping_evidence', 'get_current_code', 'get_applied_groups', 'get_applied_checks']
            ELSE ARRAY[]::TEXT[]
        END;
        IF (v_mode IS DISTINCT FROM 'tool_assisted' AND v_workflow NOT IN ('code_generation', 'validation'))
           OR cardinality(NEW.agent_tool_names) > 100
           OR (cardinality(NEW.agent_tool_names) > 0 AND (
               array_ndims(NEW.agent_tool_names) IS DISTINCT FROM 1
               OR array_lower(NEW.agent_tool_names, 1) IS DISTINCT FROM 1))
           OR array_position(NEW.agent_tool_names, NULL) IS NOT NULL
           OR NOT (NEW.agent_tool_names <@ v_allowed_tools)
           OR cardinality(NEW.agent_tool_names) <> (
               SELECT count(DISTINCT name) FROM unnest(NEW.agent_tool_names) AS name
           ) THEN
            RAISE EXCEPTION 'Prompt tool selection is invalid for this stage';
        END IF;
    END IF;

    v_expected_digest := encode(
        sha256(
            convert_to(
                (jsonb_build_object(
                    'system_prompt_template', NEW.system_prompt_template,
                    'instruction_prompt_template',
                        NEW.instruction_prompt_template,
                    'tool_instruction_prompt_template',
                        NEW.tool_instruction_prompt_template
                ) || CASE WHEN NEW.agent_tool_names IS NULL THEN '{}'::JSONB
                    ELSE jsonb_build_object('agent_tool_names', NEW.agent_tool_names) END)::TEXT,
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
               NEW.agent_tool_names,
               NEW.prompt_template_digest,
               NEW.published_time,
               NEW.published_by_principal_id
           ) IS DISTINCT FROM ROW(
               OLD.system_prompt_template,
               OLD.instruction_prompt_template,
               OLD.tool_instruction_prompt_template,
               OLD.agent_tool_names,
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
    p_expected_updated_time TIMESTAMPTZ,
    p_agent_tool_names TEXT[] DEFAULT NULL
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
       OR p_instruction_prompt_template IS NULL
       OR btrim(p_instruction_prompt_template) = ''
       OR (
           p_tool_instruction_prompt_template IS NOT NULL
           AND btrim(p_tool_instruction_prompt_template) = ''
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
                (jsonb_build_object(
                    'system_prompt_template', p_system_prompt_template,
                    'instruction_prompt_template', p_instruction_prompt_template,
                    'tool_instruction_prompt_template',
                        p_tool_instruction_prompt_template
                ) || CASE WHEN p_agent_tool_names IS NULL THEN '{}'::JSONB
                    ELSE jsonb_build_object('agent_tool_names', p_agent_tool_names) END)::TEXT,
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
               agent_tool_names = p_agent_tool_names,
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
        agent_tool_names,
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
        p_agent_tool_names,
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
    TIMESTAMPTZ, TEXT[]
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
    -- NULL permits a shared custom template; defaults always declare their layer.
    output_template_modeled_entity_type VARCHAR(30),
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
    CONSTRAINT ck_output_template_entity_type CHECK (
        output_template_modeled_entity_type IS NULL
        OR output_template_modeled_entity_type IN ('logical_entity', 'dimensional_entity')
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
        NEW.output_template_modeled_entity_type,
        NEW.output_template_schema_digest,
        NEW.created_by_principal_id,
        NEW.created_time,
        NEW.created_by
    ) IS DISTINCT FROM ROW(
        OLD.output_template_id,
        OLD.output_template_code,
        OLD.output_template_target_type,
        OLD.output_template_modeled_entity_type,
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

-- Applied Mapping consumers depend on the Output Template tables above.
CREATE FUNCTION workflow.list_code_generation_target_context(
    p_model_id BIGINT, p_modeled_entity_type VARCHAR(30),
    p_required_artifact_type VARCHAR(30) DEFAULT 'sql_file'
)
RETURNS TABLE (
    model_id BIGINT, modeled_entity_type VARCHAR(30), modeled_entity_id BIGINT,
    modeled_entity_schema_name VARCHAR(400), modeled_entity_name VARCHAR(255),
    source_system_count INTEGER, code_input_digest CHAR(64), source_context JSONB
)
LANGUAGE SQL STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $list_code_generation_target_context$
    WITH target AS MATERIALIZED (
        SELECT entity.*, model.tenant_id, model.silver_model_audit_columns_template,
               model.gold_model_audit_columns_template, model.gold_model_technical_columns_template,
               owner.tenant_code AS source_tenant_code, owner.tenant_name AS source_tenant_name,
               connection.connection_id, connection.connection_code,
               placement.tenant_id AS placement_tenant_id, placement.tenant_code,
               placement.tenant_name, placement.tenant_catalog,
               system.system_id, system.system_code, system.system_name
          FROM workflow.modeled_entity AS entity
          JOIN model.model AS model ON model.model_id = entity.model_id AND model.is_active
          JOIN core.tenant AS owner ON owner.tenant_id = model.tenant_id AND owner.is_active
          JOIN core.connection AS connection ON connection.connection_id = owner.gds_connection_id
           AND connection.is_active AND connection.is_global_data_store
          JOIN core.tenant AS placement ON placement.tenant_id = connection.tenant_id AND placement.is_active
          JOIN core.system AS system ON system.system_id = connection.system_id AND system.is_active
         WHERE entity.model_id = p_model_id AND entity.modeled_entity_type = p_modeled_entity_type
           AND entity.status = 'active'
           AND (p_required_artifact_type IS NULL OR p_required_artifact_type IN ('sql_file','python_file','python_notebook'))
    ), active_mapping AS MATERIALIZED (
        SELECT mapping.*, source.system_code AS source_system_code, source.system_name AS source_system_name
          FROM workflow.mapping_object AS mapping
          JOIN target ON target.model_id = mapping.model_id AND target.modeled_entity_type = mapping.modeled_entity_type
           AND target.modeled_entity_id = coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id)
          JOIN core.system AS source ON source.system_id = mapping.source_system_id AND source.is_active
         WHERE mapping.object_mapping_status = 'active'
           -- Code can be authored from a partial saved pair. Empty ledger rows
           -- are retained only by strict consumers so they still block readiness.
           AND (p_required_artifact_type IS NULL
                OR mapping.mapping_transformation_document IS NOT NULL
                OR EXISTS (
                    SELECT 1 FROM workflow.mapping_attribute AS mapped
                    JOIN workflow.modeled_attribute AS attribute
                      ON attribute.model_id = mapping.model_id
                     AND attribute.modeled_entity_type = mapping.modeled_entity_type
                     AND attribute.modeled_entity_id = coalesce(mapping.logical_entity_id,mapping.dimensional_entity_id)
                     AND attribute.modeled_attribute_id = coalesce(mapped.logical_attribute_id,mapped.dimensional_attribute_id)
                     AND attribute.status = 'active'
                   WHERE mapped.mapping_object_id = mapping.mapping_object_id
                     AND mapped.attribute_mapping_status = 'active'
                     AND mapped.attribute_mapping_transformation_document IS NOT NULL
                ))
    ), eligible AS MATERIALIZED (
        SELECT target.* FROM target
         WHERE EXISTS (SELECT 1 FROM active_mapping AS mapping WHERE mapping.model_id = target.model_id
           AND mapping.modeled_entity_type = target.modeled_entity_type
           AND coalesce(mapping.logical_entity_id,mapping.dimensional_entity_id) = target.modeled_entity_id)
           -- A NULL artifact type is the existing complete-Mapping contract
           -- used by Validation and execution-readiness consumers.
           AND (p_required_artifact_type IS NOT NULL OR NOT EXISTS (
             SELECT 1 FROM active_mapping AS mapping
              WHERE mapping.model_id = target.model_id AND mapping.modeled_entity_type = target.modeled_entity_type
                AND coalesce(mapping.logical_entity_id,mapping.dimensional_entity_id) = target.modeled_entity_id
                AND (mapping.mapping_transformation_document IS NULL OR EXISTS (
                  SELECT 1 FROM workflow.modeled_attribute AS attribute
                   WHERE attribute.model_id = target.model_id AND attribute.modeled_entity_type = target.modeled_entity_type
                     AND attribute.modeled_entity_id = target.modeled_entity_id AND attribute.status = 'active'
                     AND NOT EXISTS (
                       SELECT 1 FROM workflow.mapping_attribute AS mapped
                        WHERE mapped.mapping_object_id = mapping.mapping_object_id
                          AND coalesce(mapped.logical_attribute_id,mapped.dimensional_attribute_id) = attribute.modeled_attribute_id
                          AND mapped.attribute_mapping_status = 'active'
                          AND mapped.attribute_mapping_transformation_document IS NOT NULL
                     )
                ))
           ))
    ), assembled AS (
      SELECT target.model_id, target.modeled_entity_type, target.modeled_entity_id,
             target.modeled_entity_schema_name, target.modeled_entity_name,
             systems.source_system_count,
             jsonb_build_object(
               'consumer_context_version','entity-3',
               'target', jsonb_build_object(
                 'model_id',target.model_id,'modeled_entity_type',target.modeled_entity_type,
                 'modeled_entity_id',target.modeled_entity_id,
                 'modeled_entity_schema_name',target.modeled_entity_schema_name,
                 'modeled_entity_name',target.modeled_entity_name,
                 'source_tenant_id',target.tenant_id,'source_tenant_code',target.source_tenant_code,
                 'source_tenant_name',target.source_tenant_name,'tenant_id',target.placement_tenant_id,
                 'tenant_code',target.tenant_code,'tenant_name',target.tenant_name,'tenant_catalog',target.tenant_catalog,
                 'system_id',target.system_id,'system_code',target.system_code,'system_name',target.system_name,
                 'connection_id',target.connection_id,'connection_code',target.connection_code,
                 'object_schema',target.modeled_entity_schema_name,'object_name',target.modeled_entity_name,
                 'object_description',target.definition,'zone_code',CASE target.modeled_entity_type WHEN 'logical_entity' THEN 'silver' ELSE 'gold' END,
                 'batch_attribute_name',NULL,'is_locked',target.is_locked,
                 'audit_columns_template',CASE target.modeled_entity_type WHEN 'logical_entity' THEN target.silver_model_audit_columns_template ELSE target.gold_model_audit_columns_template END,
                 'technical_columns_template',CASE target.modeled_entity_type WHEN 'dimensional_entity' THEN target.gold_model_technical_columns_template ELSE NULL END,
                 'attributes',attributes.documents),
               'physical_sources',sources.documents,'source_systems',systems.documents,
               'object_mappings',mappings.documents,'attribute_mappings',attribute_mappings.documents,
               'mapping_templates',mapping_templates.documents
             ) AS source_context
        FROM eligible AS target
        CROSS JOIN LATERAL (
          SELECT coalesce(jsonb_agg(jsonb_build_object(
            'modeled_attribute_id',a.modeled_attribute_id,'attribute_name',a.attribute_name,
            'attribute_ordinal_position',a.ordinal_position,'attribute_data_type',a.data_type,
            'attribute_inferred_data_type',a.data_type,'attribute_nullability',a.is_nullable,
            'attribute_description',a.definition,'fc_attribute_name',NULL,'attribute_custom_code',NULL,
            'is_surrogate_key',a.is_surrogate_key,'is_natural_key',a.is_natural_key,'is_meta_data',a.is_audit_column,
            'is_masking_required',FALSE,'is_active',a.status = 'active','is_locked',a.is_locked
          ) ORDER BY a.ordinal_position,a.modeled_attribute_id),'[]'::JSONB) AS documents
          FROM workflow.modeled_attribute AS a WHERE a.model_id = target.model_id
           AND a.modeled_entity_type = target.modeled_entity_type AND a.modeled_entity_id = target.modeled_entity_id
        ) AS attributes
        CROSS JOIN LATERAL (
          SELECT count(*)::INTEGER AS source_system_count,
                 jsonb_agg(jsonb_build_object('source_system_id',m.source_system_id,
                   'system_code',m.source_system_code,'system_name',m.source_system_name)
                   ORDER BY lower(m.source_system_code),m.source_system_id) AS documents
            FROM active_mapping AS m WHERE m.model_id = target.model_id AND m.modeled_entity_type = target.modeled_entity_type
             AND coalesce(m.logical_entity_id,m.dimensional_entity_id) = target.modeled_entity_id
        ) AS systems
        CROSS JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_object('mapping_object_id',m.mapping_object_id,'source_system_id',m.source_system_id,
                   'object_dependency_order',m.object_dependency_order,
                   'output_template_code',template.output_template_code,
                   'entity',jsonb_build_object('entity_type',target.modeled_entity_type,'entity_id',target.modeled_entity_id,
                     'entity_schema_name',target.modeled_entity_schema_name,'entity_name',target.modeled_entity_name,
                     'definition',target.definition,'classification',target.classification,'grain',target.grain,'assertions',assertions.documents),
                   'transformation',m.mapping_transformation_document)
                   ORDER BY lower(m.source_system_code),m.source_system_id,m.object_dependency_order,m.mapping_object_id) AS documents
            FROM active_mapping AS m
            LEFT JOIN application.output_template AS template ON template.output_template_id = m.output_template_id
            CROSS JOIN LATERAL (
              SELECT coalesce(jsonb_agg(jsonb_build_object(
                'modeling_assertion_record_key',a.modeling_assertion_record_key,
                'modeling_assertion_record_type',a.modeling_assertion_record_type,'modeling_assertion_text',a.modeling_assertion_text,
                'modeling_assertion_details',a.modeling_assertion_details,'modeling_assertion_source_location',a.modeling_assertion_source_location,
                'modeling_assertion_confidence',a.modeling_assertion_confidence,'modeling_assertion_document_name',d.modeling_assertion_document_name
              ) ORDER BY lower(a.modeling_assertion_record_key)),'[]'::JSONB) AS documents
              FROM model.modeling_assertion_record AS a JOIN model.modeling_assertion_document AS d
                ON d.modeling_assertion_document_id = a.modeling_assertion_document_id AND d.model_id = a.model_id AND d.is_active
              WHERE a.model_id = target.model_id AND a.modeling_assertion_record_status = 'active'
                AND (d.system_id IS NULL OR d.system_id = m.source_system_id)
                AND (d.tenant_id IS NULL OR d.tenant_id = target.tenant_id OR EXISTS (
                  SELECT 1 FROM model.model_input_scope AS scope JOIN core.object AS source ON source.object_id = scope.object_id
                   WHERE scope.model_id = target.model_id AND scope.is_active AND source.source_tenant_id = d.tenant_id))
            ) AS assertions
           WHERE m.model_id = target.model_id AND m.modeled_entity_type = target.modeled_entity_type
             AND coalesce(m.logical_entity_id,m.dimensional_entity_id) = target.modeled_entity_id
        ) AS mappings
        CROSS JOIN LATERAL (
          SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'mapping_attribute_id',a.mapping_attribute_id,'mapping_object_id',m.mapping_object_id,
                   'source_system_id',m.source_system_id,'modeled_attribute_id',attribute.modeled_attribute_id,
                   'target_attribute_name',attribute.attribute_name,'modeled_attribute_name',attribute.attribute_name,
                   'target_attribute_ordinal_position',attribute.ordinal_position,
                   'output_template_code',template.output_template_code,
                   'transformation',a.attribute_mapping_transformation_document
                 ) ORDER BY lower(m.source_system_code),m.source_system_id,attribute.ordinal_position,
                     coalesce(a.mapping_attribute_id,attribute.modeled_attribute_id)),'[]'::JSONB) AS documents
            FROM active_mapping AS m
            JOIN workflow.modeled_attribute AS attribute ON attribute.model_id = m.model_id
              AND attribute.modeled_entity_type = m.modeled_entity_type
              AND attribute.modeled_entity_id = coalesce(m.logical_entity_id,m.dimensional_entity_id)
              AND attribute.status = 'active'
            LEFT JOIN workflow.mapping_attribute AS a ON a.mapping_object_id = m.mapping_object_id
              AND a.attribute_mapping_status = 'active'
              AND attribute.modeled_attribute_id = coalesce(a.logical_attribute_id,a.dimensional_attribute_id)
            LEFT JOIN application.output_template AS template ON template.output_template_id = a.output_template_id
           WHERE m.model_id = target.model_id AND m.modeled_entity_type = target.modeled_entity_type
             AND coalesce(m.logical_entity_id,m.dimensional_entity_id) = target.modeled_entity_id
        ) AS attribute_mappings
        CROSS JOIN LATERAL (
          SELECT coalesce(jsonb_agg(jsonb_build_object(
            'code',template.output_template_code,'name',template.output_template_name,
            'description',template.output_template_description,
            'target_type',template.output_template_target_type,
            'modeled_entity_type',template.output_template_modeled_entity_type,
            'is_active',template.is_active,'fields',fields.documents
          ) ORDER BY template.output_template_code),'[]'::JSONB) AS documents
          FROM application.output_template AS template
          JOIN (
            SELECT m.output_template_id FROM active_mapping AS m
             WHERE m.model_id = target.model_id AND m.modeled_entity_type = target.modeled_entity_type
               AND coalesce(m.logical_entity_id,m.dimensional_entity_id) = target.modeled_entity_id
            UNION
            SELECT a.output_template_id FROM active_mapping AS m
            JOIN workflow.mapping_attribute AS a ON a.mapping_object_id = m.mapping_object_id
              AND a.attribute_mapping_status = 'active'
            JOIN workflow.modeled_attribute AS attribute ON attribute.model_id = m.model_id
              AND attribute.modeled_entity_type = m.modeled_entity_type
              AND attribute.modeled_entity_id = coalesce(m.logical_entity_id,m.dimensional_entity_id)
              AND attribute.modeled_attribute_id = coalesce(a.logical_attribute_id,a.dimensional_attribute_id)
              AND attribute.status = 'active'
             WHERE m.model_id = target.model_id AND m.modeled_entity_type = target.modeled_entity_type
               AND coalesce(m.logical_entity_id,m.dimensional_entity_id) = target.modeled_entity_id
          ) AS used ON used.output_template_id = template.output_template_id
          CROSS JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object(
              'name',field.output_template_field_name,'description',field.output_template_field_description,
              'data_type',field.output_template_field_data_type,
              'array_item_type',field.output_template_field_array_item_type,
              'example',field.output_template_field_example,
              'is_required',field.output_template_field_is_required,'order',field.output_template_field_order
            ) ORDER BY field.output_template_field_order) AS documents
            FROM application.output_template_field AS field
             WHERE field.output_template_id = template.output_template_id
          ) AS fields
          -- Saved documents retain their defining schema when a template is inactive.
        ) AS mapping_templates
        CROSS JOIN LATERAL (
          SELECT coalesce(jsonb_agg(jsonb_build_object(
            'selected_source_system_id',m.source_system_id,'source_mapping_id',source.source_mapping_id,
            'role',source.role,'rationale',source.rationale,'mapping_order',source.mapping_order,'is_locked',source.is_locked,
            'object',CASE WHEN source.source_object_id IS NOT NULL THEN physical.document ELSE modeled.document END
          ) ORDER BY lower(m.source_system_code),m.source_system_id,source.mapping_order NULLS LAST,source.source_object_id,source.source_logical_entity_id,source.source_dimensional_entity_id),'[]'::JSONB) AS documents
          FROM active_mapping AS m
          CROSS JOIN LATERAL workflow.list_mapping_source_objects(m.model_id,target.modeled_entity_id,target.modeled_entity_type,m.source_system_id) AS source
          LEFT JOIN LATERAL (
            SELECT jsonb_build_object(
              'object_id',o.object_id,'source_tenant_id',o.source_tenant_id,'tenant_id',t.tenant_id,
              'tenant_code',t.tenant_code,'tenant_catalog',t.tenant_catalog,'system_id',system.system_id,'system_code',system.system_code,
              'connection_id',c.connection_id,'connection_code',c.connection_code,'object_schema',o.object_schema,'object_name',o.object_name,
              'object_description',o.object_description,'fc_object_schema',o.fc_object_schema,'fc_object_name',o.fc_object_name,
              'foreign_catalog',c.foreign_catalog,'batch_attribute_name',o.batch_attribute_name,'zone_code',lower(z.zone_code),
              'is_active',o.is_active,'is_locked',o.is_locked,'scope_is_active',source.scope_is_active,'scope_is_locked',source.scope_is_locked,
              'attributes',(SELECT coalesce(jsonb_agg(jsonb_build_object(
                'attribute_id',a.attribute_id,'attribute_name',a.attribute_name,'attribute_ordinal_position',a.attribute_ordinal_position,
                'attribute_data_type',a.attribute_data_type,'attribute_inferred_data_type',a.attribute_inferred_data_type,
                'attribute_nullability',a.attribute_nullability,'attribute_description',a.attribute_description,
                'fc_attribute_name',a.fc_attribute_name,'attribute_custom_code',a.attribute_custom_code,
                'is_surrogate_key',a.is_surrogate_key,'is_natural_key',a.is_natural_key,'is_meta_data',a.is_meta_data,
                'is_masking_required',a.is_masking_required,'is_active',a.is_active,'is_locked',a.is_locked
              ) ORDER BY a.attribute_ordinal_position,a.attribute_id),'[]'::JSONB) FROM core.attribute AS a WHERE a.object_id = o.object_id)
            ) AS document
            FROM core.object AS o JOIN core.connection AS c ON c.connection_id = o.connection_id
             JOIN core.tenant AS t ON t.tenant_id = c.tenant_id JOIN core.system AS system ON system.system_id = c.system_id
             JOIN reference.zone AS z ON z.zone_id = o.zone_id WHERE o.object_id = source.source_object_id
          ) AS physical ON TRUE
          LEFT JOIN LATERAL (
            SELECT jsonb_build_object(
              'modeled_entity_id',e.modeled_entity_id,'modeled_entity_type',e.modeled_entity_type,
              'modeled_entity_schema_name',e.modeled_entity_schema_name,'modeled_entity_name',e.modeled_entity_name,
              'source_tenant_id',target.tenant_id,'tenant_id',target.placement_tenant_id,'tenant_code',target.tenant_code,
              'tenant_catalog',target.tenant_catalog,'system_id',target.system_id,'system_code',target.system_code,
              'connection_id',target.connection_id,'connection_code',target.connection_code,
              'object_schema',e.modeled_entity_schema_name,'object_name',e.modeled_entity_name,'object_description',e.definition,
              'fc_object_schema',NULL,'fc_object_name',NULL,'foreign_catalog',NULL,'batch_attribute_name',NULL,
              'zone_code',CASE e.modeled_entity_type WHEN 'logical_entity' THEN 'silver' ELSE 'gold' END,
              'is_active',e.status = 'active','is_locked',e.is_locked,
              'scope_is_active',source.scope_is_active,'scope_is_locked',source.scope_is_locked,
              'attributes',(SELECT coalesce(jsonb_agg(jsonb_build_object(
                'modeled_attribute_id',a.modeled_attribute_id,
                'attribute_name',a.attribute_name,'attribute_ordinal_position',a.ordinal_position,
                'attribute_data_type',a.data_type,'attribute_inferred_data_type',a.data_type,'attribute_nullability',a.is_nullable,
                'attribute_description',a.definition,'fc_attribute_name',NULL,'attribute_custom_code',NULL,
                'is_surrogate_key',a.is_surrogate_key,'is_natural_key',a.is_natural_key,'is_meta_data',a.is_audit_column,
                'is_masking_required',FALSE,'is_active',a.status = 'active','is_locked',a.is_locked
              ) || jsonb_build_object(
                CASE e.modeled_entity_type WHEN 'logical_entity' THEN 'logical_attribute_name' ELSE 'dimensional_attribute_name' END,
                a.attribute_name
              ) ORDER BY a.ordinal_position,a.modeled_attribute_id),'[]'::JSONB) FROM workflow.modeled_attribute AS a
              WHERE a.model_id = e.model_id AND a.modeled_entity_type = e.modeled_entity_type AND a.modeled_entity_id = e.modeled_entity_id)
            ) || CASE e.modeled_entity_type WHEN 'logical_entity' THEN jsonb_build_object(
              'logical_entity_schema_name',e.modeled_entity_schema_name,'logical_entity_name',e.modeled_entity_name
            ) ELSE jsonb_build_object(
              'dimensional_entity_schema_name',e.modeled_entity_schema_name,'dimensional_entity_name',e.modeled_entity_name
            ) END AS document FROM workflow.modeled_entity AS e
             WHERE e.model_id = target.model_id
               AND e.modeled_entity_type = CASE WHEN source.source_dimensional_entity_id IS NOT NULL THEN 'dimensional_entity' ELSE 'logical_entity' END
               AND e.modeled_entity_id = coalesce(source.source_logical_entity_id,source.source_dimensional_entity_id)
          ) AS modeled ON TRUE
          WHERE m.model_id = target.model_id AND m.modeled_entity_type = target.modeled_entity_type
            AND coalesce(m.logical_entity_id,m.dimensional_entity_id) = target.modeled_entity_id
        ) AS sources
    )
    SELECT assembled.model_id,assembled.modeled_entity_type,assembled.modeled_entity_id,
           assembled.modeled_entity_schema_name,assembled.modeled_entity_name,assembled.source_system_count,
           encode(sha256(convert_to(assembled.source_context::TEXT,'UTF8')),'hex')::CHAR(64),assembled.source_context
      FROM assembled ORDER BY assembled.modeled_entity_id;
$list_code_generation_target_context$;
REVOKE ALL ON FUNCTION workflow.list_code_generation_target_context(BIGINT,VARCHAR,VARCHAR) FROM PUBLIC;

CREATE FUNCTION application.create_output_template(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_output_template_code VARCHAR(100),
    p_output_template_name VARCHAR(200),
    p_output_template_description VARCHAR(2000),
    p_output_template_target_type VARCHAR(30),
    p_fields JSONB,
    p_output_template_modeled_entity_type VARCHAR(30) DEFAULT NULL
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
                    'output_template_modeled_entity_type',
                        p_output_template_modeled_entity_type,
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
            v_existing.output_template_modeled_entity_type,
            v_existing.output_template_schema_digest,
            v_existing.is_active
        ) IS DISTINCT FROM ROW(
            p_output_template_code,
            p_output_template_name,
            p_output_template_description,
            p_output_template_target_type,
            p_output_template_modeled_entity_type,
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
        output_template_modeled_entity_type,
        output_template_schema_digest,
        created_by_principal_id,
        updated_by_principal_id
    ) VALUES (
        p_output_template_code,
        p_output_template_name,
        p_output_template_description,
        p_output_template_target_type,
        p_output_template_modeled_entity_type,
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
    JSONB,
    VARCHAR
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
