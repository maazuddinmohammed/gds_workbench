-- GDS ETL Workbench Release 1: Workflow Run state and lifecycle.

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
    mapping_route VARCHAR(30),
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
            'dimensional', 'mapping', 'code_generation', 'validation'
        )
    ),
    CONSTRAINT ck_workflow_run_model_revision CHECK (
        model_revision > 0
    ),
    CONSTRAINT ck_workflow_run_execution_mode CHECK (
        (
            workflow_execution_mode IS NULL
            AND model_workflow IN (
                'profiling', 'analysis', 'code_generation', 'validation'
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
            model_workflow NOT IN ('code_generation', 'validation')
            AND workflow_execution_mode IS NULL
            AND agent_sdk_code IS NULL
            AND agent_provider_code IS NULL
            AND agent_model_code IS NULL
            AND reasoning_effort_code IS NULL
            AND max_turns IS NULL
            AND validation_retry_count IS NULL
        ) OR (
            (
                model_workflow IN ('code_generation', 'validation')
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
                mapping_route
            ) = 3
            AND mapping_operation IN ('build', 'extend')
            AND mapping_coverage_mode = 'selected_targets'
            AND mapping_route = CASE modeled_entity_type
                WHEN 'logical_entity' THEN 'logical_to_silver'
                WHEN 'dimensional_entity' THEN 'dimensional_to_gold'
                ELSE NULL
            END
            AND selected_scope_count = 1
        ) OR (
            model_workflow <> 'mapping'
            AND mapping_operation IS NULL
            AND mapping_coverage_mode IS NULL
            AND mapping_route IS NULL
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
                    'analysis', 'conceptual', 'logical', 'dimensional', 'mapping',
                    'code_generation', 'validation'
                )
                AND (
                    (
                        model_workflow IN (
                            'analysis', 'conceptual', 'logical',
                            'dimensional', 'mapping'
                        )
                        AND workflow_execution_mode IS NOT NULL
                    ) OR (
                        model_workflow IN ('code_generation', 'validation')
                        AND workflow_execution_mode IS NULL
                    )
                )
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
    CONSTRAINT fk_workflow_run_object_selection_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
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

CREATE TABLE application.workflow_run_system_selection (
    workflow_run_system_selection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    system_code VARCHAR(100) NOT NULL,
    selection_order INTEGER NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_workflow_run_system_selection_run FOREIGN KEY (
        workflow_run_id,
        model_id
    ) REFERENCES application.workflow_run (workflow_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_run_system_selection_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_workflow_run_system_selection_system UNIQUE (
        workflow_run_id,
        system_id
    ),
    CONSTRAINT uq_workflow_run_system_selection_order UNIQUE (
        workflow_run_id,
        selection_order
    ),
    CONSTRAINT ck_workflow_run_system_selection_code CHECK (
        reference.is_nonblank(system_code)
    ),
    CONSTRAINT ck_workflow_run_system_selection_order CHECK (
        selection_order > 0
    )
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
    CONSTRAINT fk_workflow_run_mapping_target_selection_binding FOREIGN KEY (
        model_id,
        object_id
    ) REFERENCES workflow.model_object_binding (model_id, object_id)
        ON DELETE NO ACTION,
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

CREATE FUNCTION application.guard_workflow_run_system_selection()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_workflow_run_system_selection$
BEGIN
    RAISE EXCEPTION 'Workflow Run System selections are immutable';
END;
$guard_workflow_run_system_selection$;

CREATE TRIGGER guard_workflow_run_system_selection
BEFORE UPDATE OR DELETE ON application.workflow_run_system_selection
FOR EACH ROW EXECUTE FUNCTION application.guard_workflow_run_system_selection();

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
        NEW.mapping_route,
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
        OLD.mapping_route,
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

ALTER TABLE model.modeling_assertion_document
    ADD CONSTRAINT fk_modeling_assertion_document_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE model.modeling_assertion_record
    ADD CONSTRAINT fk_modeling_assertion_record_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.attribute_profile
    ADD CONSTRAINT fk_attribute_profile_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.analysis_result
    ADD CONSTRAINT fk_analysis_result_inference_workflow_run
    FOREIGN KEY (inference_workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION,
    ADD CONSTRAINT fk_analysis_result_validation_workflow_run
    FOREIGN KEY (validation_workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.conceptual_object
    ADD CONSTRAINT fk_conceptual_object_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.conceptual_relationship
    ADD CONSTRAINT fk_conceptual_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.conceptual_support
    ADD CONSTRAINT fk_conceptual_support_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_submodel
    ADD CONSTRAINT fk_logical_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_entity
    ADD CONSTRAINT fk_logical_entity_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_entity_submodel
    ADD CONSTRAINT fk_logical_entity_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_attribute
    ADD CONSTRAINT fk_logical_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_entity_source_mapping
    ADD CONSTRAINT fk_logical_entity_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_attribute_source_mapping
    ADD CONSTRAINT fk_logical_attribute_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.logical_relationship
    ADD CONSTRAINT fk_logical_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_submodel
    ADD CONSTRAINT fk_dimensional_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_entity
    ADD CONSTRAINT fk_dimensional_entity_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_entity_submodel
    ADD CONSTRAINT fk_dimensional_entity_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_attribute
    ADD CONSTRAINT fk_dimensional_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_entity_source_mapping
    ADD CONSTRAINT fk_dimensional_entity_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_attribute_source_mapping
    ADD CONSTRAINT fk_dimensional_attribute_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.dimensional_relationship
    ADD CONSTRAINT fk_dimensional_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.model_object_binding
    ADD CONSTRAINT fk_model_object_binding_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.model_attribute_binding
    ADD CONSTRAINT fk_model_attribute_binding_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.mapping_source_system_dependency
    ADD CONSTRAINT fk_mapping_source_system_dependency_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.mapping_object
    ADD CONSTRAINT fk_mapping_object_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.mapping_attribute
    ADD CONSTRAINT fk_mapping_attribute_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.generated_code
    ADD CONSTRAINT fk_generated_code_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.generated_code_source_system
    ADD CONSTRAINT fk_generated_code_source_system_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;

ALTER TABLE workflow.validation_group
    ADD CONSTRAINT fk_validation_group_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;

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
    p_selected_system_codes VARCHAR(100)[],
    p_modeled_entity_type VARCHAR(30),
    p_requested_batch_id VARCHAR(500),
    p_correlation_id UUID,
    p_prompt_overrides JSONB,
    p_mapping_operation VARCHAR(20) DEFAULT NULL,
    p_mapping_coverage_mode VARCHAR(30) DEFAULT NULL,
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
    v_caller_selected_system_codes VARCHAR(100)[];
    v_selected_system_ids BIGINT[];
    v_selected_system_codes VARCHAR(100)[];
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
    IF p_selected_object_ids IS NULL OR p_selected_system_codes IS NULL THEN
        RAISE EXCEPTION 'Selected Scope is required';
    END IF;
    IF p_model_workflow = 'validation' THEN
        IF cardinality(p_selected_object_ids) <> 0
           OR cardinality(p_selected_system_codes) NOT BETWEEN 1 AND 1000 THEN
            RAISE EXCEPTION
                'Validation requires between 1 and 1000 Systems and no Object selection';
        END IF;
        IF p_code_generation_coverage_mode IS NOT NULL
           OR p_sql_generation_guide_version_id IS NOT NULL THEN
            RAISE EXCEPTION
                'Code Generation inputs are unavailable for this Workflow Run';
        END IF;
    ELSIF p_model_workflow = 'code_generation' THEN
        IF cardinality(p_selected_system_codes) <> 0 THEN
            RAISE EXCEPTION
                'System selection is available only for Validation';
        END IF;
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
        IF cardinality(p_selected_system_codes) <> 0 THEN
            RAISE EXCEPTION
                'System selection is available only for Validation';
        END IF;
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

    IF EXISTS (
        SELECT 1
          FROM unnest(p_selected_system_codes) AS selected(system_code)
         WHERE selected.system_code IS NULL
            OR NOT reference.is_nonblank(selected.system_code)
            OR octet_length(btrim(selected.system_code)) > 100
    ) THEN
        RAISE EXCEPTION 'Selected System Codes must be nonblank';
    END IF;
    IF cardinality(p_selected_system_codes) <> (
        SELECT count(DISTINCT lower(btrim(selected.system_code)))
          FROM unnest(p_selected_system_codes) AS selected(system_code)
    ) THEN
        RAISE EXCEPTION 'Selected System Codes must be unique';
    END IF;
    SELECT coalesce(
               array_agg(
                   lower(btrim(selected.system_code))
                   ORDER BY selected.selection_order
               ),
               ARRAY[]::VARCHAR(100)[]
           )
      INTO v_caller_selected_system_codes
      FROM unnest(p_selected_system_codes) WITH ORDINALITY
           AS selected(system_code, selection_order);
    IF p_model_workflow = 'validation' THEN
        v_selected_scope_count := cardinality(v_caller_selected_system_codes);
        v_selected_scope_digest := encode(
            sha256(
                convert_to(
                    array_to_string(v_caller_selected_system_codes, ','),
                    'UTF8'
                )
            ),
            'hex'
        );
    END IF;

    v_modeled_entity_type := p_modeled_entity_type;
    IF p_model_workflow = 'mapping' THEN
        IF p_modeled_entity_type IS NOT NULL THEN
            RAISE EXCEPTION 'Mapping route is inferred by the server';
        END IF;
        IF num_nonnulls(
               p_mapping_operation,
               p_mapping_coverage_mode,
               p_mapping_source_system_id
           ) <> 3
           OR v_selected_scope_count <> 1
           OR p_mapping_operation NOT IN ('build', 'extend')
           OR p_mapping_coverage_mode <> 'selected_targets'
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
                    'mapping_source_system_id', p_mapping_source_system_id,
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
                    'selected_system_codes', v_caller_selected_system_codes,
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

    IF p_model_workflow = 'validation' THEN
        WITH target_context AS MATERIALIZED (
            SELECT context.*
              FROM workflow.list_code_generation_target_context(
                  p_model_id,
                  'logical_entity',
                  NULL
              ) AS context
            UNION ALL
            SELECT context.*
              FROM workflow.list_code_generation_target_context(
                  p_model_id,
                  'dimensional_entity',
                  NULL
              ) AS context
        ), eligible_system AS MATERIALIZED (
            SELECT DISTINCT
                   (source_system.document ->> 'source_system_id')::BIGINT
                       AS system_id
              FROM target_context AS context
              CROSS JOIN LATERAL jsonb_array_elements(
                  context.source_context -> 'source_systems'
              ) AS source_system(document)
        )
        SELECT coalesce(
                   array_agg(
                       source_system.system_id
                       ORDER BY requested.selection_order
                   ),
                   ARRAY[]::BIGINT[]
               ),
               coalesce(
                   array_agg(
                       source_system.system_code
                       ORDER BY requested.selection_order
                   ),
                   ARRAY[]::VARCHAR(100)[]
               )
          INTO v_selected_system_ids,
               v_selected_system_codes
          FROM unnest(v_caller_selected_system_codes) WITH ORDINALITY
               AS requested(system_code, selection_order)
          JOIN core.system AS source_system
            ON lower(btrim(source_system.system_code)) = requested.system_code
           AND source_system.is_active
          JOIN eligible_system
            ON eligible_system.system_id = source_system.system_id;
        IF cardinality(v_selected_system_ids) <> v_selected_scope_count THEN
            RAISE EXCEPTION
                'Selected Validation System lacks complete applied Mapping';
        END IF;
        SELECT encode(
                   sha256(
                       convert_to(
                           jsonb_agg(
                               jsonb_build_object(
                                   'system_id', selected.system_id,
                                   'system_code', selected.system_code
                               )
                               ORDER BY selected.selection_order
                           )::TEXT,
                           'UTF8'
                       )
                   ),
                   'hex'
               )
          INTO v_selected_scope_digest
          FROM unnest(v_selected_system_ids, v_selected_system_codes)
               WITH ORDINALITY
               AS selected(system_id, system_code, selection_order);
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
               count(DISTINCT binding.modeled_entity_type)::INTEGER,
               count(*) FILTER (
                   WHERE binding.model_object_binding_status <> 'active'
                      OR binding.model_object_binding_is_locked
                      OR NOT EXISTS (
                          SELECT 1
                            FROM workflow.mapping_source_system_dependency
                                 AS dependency
                           WHERE dependency.model_id = binding.model_id
                             AND dependency.modeled_entity_type =
                                 binding.modeled_entity_type
                             AND dependency.source_system_id =
                                 p_mapping_source_system_id
                             AND dependency.mapping_source_system_dependency_status =
                                 'active'
                      )
                      OR NOT EXISTS (
                          SELECT 1
                            FROM core.system AS source_system
                           WHERE source_system.system_id =
                                 p_mapping_source_system_id
                             AND source_system.is_active
                      )
                      OR (
                          binding.modeled_entity_type = 'logical_entity'
                          AND NOT EXISTS (
                              SELECT 1
                                FROM workflow.logical_entity AS entity
                               WHERE entity.logical_entity_id =
                                     binding.logical_entity_id
                                 AND entity.model_id = binding.model_id
                                 AND entity.logical_entity_status = 'active'
                          )
                      )
                      OR (
                          binding.modeled_entity_type = 'dimensional_entity'
                          AND NOT EXISTS (
                              SELECT 1
                                FROM workflow.dimensional_entity AS entity
                               WHERE entity.dimensional_entity_id =
                                     binding.dimensional_entity_id
                                 AND entity.model_id = binding.model_id
                                 AND entity.dimensional_entity_status = 'active'
                          )
                      )
                      OR EXISTS (
                          SELECT 1
                            FROM workflow.mapping_object AS mapping
                           WHERE mapping.model_object_binding_id =
                                 binding.model_object_binding_id
                             AND mapping.source_system_id =
                                 p_mapping_source_system_id
                             AND mapping.object_mapping_is_locked
                      )
               )::INTEGER,
               min(binding.modeled_entity_type)
          INTO v_mapping_header_count,
               v_mapping_header_layer_count,
               v_mapping_invalid_header_count,
               v_modeled_entity_type
          FROM workflow.model_object_binding AS binding
         WHERE binding.model_id = p_model_id
           AND binding.object_id = v_selected_object_ids[1];

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

        SELECT zone.zone_code
          INTO v_mapping_zone_code
          FROM workflow.model_object_binding AS binding
          JOIN core.object AS object
            ON object.object_id = binding.object_id
           AND object.is_active
          JOIN reference.zone AS zone
            ON zone.zone_id = object.zone_id
           AND zone.is_active
         WHERE binding.model_id = p_model_id
           AND binding.object_id = v_selected_object_ids[1]
           AND binding.model_object_binding_status = 'active';
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

    IF p_model_workflow <> 'validation' THEN
        SELECT count(*)::INTEGER
          INTO v_eligible_scope_count
          FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
         WHERE eligible.object_id = ANY(v_selected_object_ids)
           AND CASE
                   WHEN p_model_workflow IN (
                       'profiling', 'analysis', 'conceptual', 'logical'
                   ) THEN eligible.is_model_input_eligible
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
    END IF;

    IF v_requested_batch_id IS NOT NULL THEN
        SELECT count(DISTINCT eligible.system_id)::INTEGER
          INTO v_selected_system_count
          FROM workflow.list_model_object_eligibility(p_model_id) AS eligible
         WHERE eligible.object_id = ANY(v_selected_object_ids)
           AND eligible.is_model_input_eligible;
        IF v_selected_system_count <> 1 THEN
            RAISE EXCEPTION
                'Requested batch ID requires Selected Scope from one System';
        END IF;
    END IF;

    v_is_agentic := p_model_workflow IN ('code_generation', 'validation')
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
        mapping_route,
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
        v_mapping_route,
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

    IF p_model_workflow = 'validation' THEN
        INSERT INTO application.workflow_run_system_selection (
            workflow_run_id,
            model_id,
            system_id,
            system_code,
            selection_order
        )
        SELECT v_created.workflow_run_id,
               v_created.model_id,
               selected.system_id,
               selected.system_code,
               selected.selection_order::INTEGER
          FROM unnest(v_selected_system_ids, v_selected_system_codes)
               WITH ORDINALITY
               AS selected(system_id, system_code, selection_order);
    ELSE
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
    END IF;

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
    VARCHAR[],
    VARCHAR,
    VARCHAR,
    UUID,
    JSONB,
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
       AND (
           (
               run.model_workflow IN (
                   'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
               )
               AND run.workflow_execution_mode IS NOT NULL
           ) OR (
               run.model_workflow IN ('code_generation', 'validation')
               AND run.workflow_execution_mode IS NULL
           )
       )
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
           run.model_revision AS run_model_revision,
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

    IF p_expected_model_revision IS NULL
       OR v_run.run_model_revision <> p_expected_model_revision
       OR v_run.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;

    IF v_run.workflow_run_state <> 'queued' THEN
        RETURN QUERY SELECT
            FALSE,
            v_run.workflow_run_id,
            v_run.workflow_run_state,
            v_run.started_time;
        RETURN;
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
           'dimensional', 'mapping', 'code_generation', 'validation'
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
    p_selected_system_codes VARCHAR(100)[],
    p_modeled_entity_type VARCHAR(30),
    p_requested_batch_id VARCHAR(500),
    p_correlation_id UUID,
    p_prompt_overrides JSONB,
    p_mapping_operation VARCHAR(20) DEFAULT NULL,
    p_mapping_coverage_mode VARCHAR(30) DEFAULT NULL,
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
          p_selected_system_codes,
          p_modeled_entity_type,
          p_requested_batch_id,
          p_correlation_id,
          p_prompt_overrides,
          p_mapping_operation,
          p_mapping_coverage_mode,
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
    VARCHAR[],
    VARCHAR,
    VARCHAR,
    UUID,
    JSONB,
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
           'dimensional', 'mapping', 'code_generation', 'validation'
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
        WHEN v_run.model_workflow IN ('code_generation', 'validation')
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
        'analysis', 'conceptual', 'logical', 'dimensional', 'mapping',
        'code_generation', 'validation'
    ) THEN
        RAISE EXCEPTION 'Workflow Run no-op Workflow is invalid';
    END IF;
    IF (
        p_expected_workflow IN ('code_generation', 'validation')
        AND p_expected_execution_mode IS NOT NULL
    ) OR (
        p_expected_workflow NOT IN ('code_generation', 'validation')
        AND (
            p_expected_execution_mode IS NULL
            OR p_expected_execution_mode NOT IN (
                'one_shot', 'tool_assisted', 'detailed_coverage'
            )
        )
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
