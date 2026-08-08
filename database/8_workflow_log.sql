-- GDS ETL Workbench Release 1: durable change control and workflow run state.

CREATE FUNCTION core.is_canonical_text_array(value TEXT[])
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURN value IS NOT NULL
   AND cardinality(value) > 0
   AND array_ndims(value) = 1
   AND array_lower(value, 1) = 1
   AND array_position(value, NULL) IS NULL
   AND NOT EXISTS (
        SELECT 1
        FROM unnest(value) WITH ORDINALITY AS current_value(item, ordinal)
        JOIN unnest(value) WITH ORDINALITY AS prior_value(item, ordinal)
          ON prior_value.ordinal < current_value.ordinal
         AND prior_value.item >= current_value.item
   )
   AND NOT EXISTS (
        SELECT 1 FROM unnest(value) AS item WHERE NOT core.is_nonblank(item)
   );

CREATE TABLE workflow.model_change_set (
    model_change_set_id UUID PRIMARY KEY,
    model_id BIGINT NOT NULL,
    model_change_set_status VARCHAR(20) NOT NULL DEFAULT 'active',
    base_model_revision BIGINT NOT NULL,
    base_source_context_digest CHAR(64) NOT NULL,
    base_evidence_digest CHAR(64) NOT NULL,
    base_policy_digest CHAR(64) NOT NULL,
    draft_revision BIGINT NOT NULL DEFAULT 1,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    evidence_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    analysis_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    conceptual_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    logical_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    dimensional_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    mapping_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by_user_account_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '4 hours'),
    validated_time TIMESTAMPTZ,
    applied_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_change_set_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_change_set_creator FOREIGN KEY (created_by_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_change_set_id_model UNIQUE (model_change_set_id, model_id),
    CONSTRAINT ck_change_set_status CHECK (
        model_change_set_status IN (
            'active', 'validated', 'applied', 'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_change_set_revisions CHECK (
        base_model_revision > 0 AND draft_revision >= 1
    ),
    CONSTRAINT ck_change_set_digests CHECK (
        base_source_context_digest ~ '^[0-9a-f]{64}$'
        AND base_evidence_digest ~ '^[0-9a-f]{64}$'
        AND base_policy_digest ~ '^[0-9a-f]{64}$'
        AND (candidate_digest IS NULL OR candidate_digest ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT ck_change_set_validation_outcome CHECK (
        validation_outcome IS NULL OR jsonb_typeof(validation_outcome) = 'object'
    ),
    CONSTRAINT ck_change_set_documents CHECK (
        jsonb_typeof(evidence_document) = 'object'
        AND jsonb_typeof(analysis_document) = 'object'
        AND jsonb_typeof(conceptual_document) = 'object'
        AND jsonb_typeof(logical_document) = 'object'
        AND jsonb_typeof(dimensional_document) = 'object'
        AND jsonb_typeof(mapping_document) = 'object'
        AND octet_length(evidence_document::TEXT) <= 16777216
        AND octet_length(analysis_document::TEXT) <= 16777216
        AND octet_length(conceptual_document::TEXT) <= 16777216
        AND octet_length(logical_document::TEXT) <= 16777216
        AND octet_length(dimensional_document::TEXT) <= 16777216
        AND octet_length(mapping_document::TEXT) <= 16777216
    ),
    CONSTRAINT ck_change_set_expiry CHECK (
        last_activity_time >= created_time
        AND expires_time > last_activity_time
    ),
    CONSTRAINT ck_change_set_candidate_state CHECK (
        (model_change_set_status = 'active' AND candidate_digest IS NULL)
        OR (
            model_change_set_status IN ('validated', 'applied')
            AND candidate_digest IS NOT NULL
        ) OR model_change_set_status IN ('expired', 'discarded', 'superseded')
    ),
    CONSTRAINT ck_change_set_terminal_time CHECK (
        (model_change_set_status IN ('applied', 'expired', 'discarded', 'superseded'))
        = (terminal_time IS NOT NULL)
    )
);

CREATE TABLE workflow.model_change_set_event (
    model_change_set_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_change_set_id UUID NOT NULL,
    model_id BIGINT NOT NULL,
    event_sequence BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    draft_revision BIGINT NOT NULL,
    section_name VARCHAR(20),
    action_count INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(30) NOT NULL,
    validation_report_id UUID,
    event_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_change_set_event_parent FOREIGN KEY (
        model_change_set_id,
        model_id
    ) REFERENCES workflow.model_change_set (model_change_set_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_change_set_event_sequence
        UNIQUE (model_change_set_id, event_sequence),
    CONSTRAINT ck_change_set_event_sequence CHECK (event_sequence > 0),
    CONSTRAINT ck_change_set_event_type CHECK (
        event_type IN (
            'created', 'section_put', 'validated', 'validation_failed',
            'applied', 'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_change_set_event_revision CHECK (draft_revision >= 1),
    CONSTRAINT ck_change_set_event_section CHECK (
        section_name IS NULL
        OR section_name IN (
            'evidence', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping'
        )
    ),
    CONSTRAINT ck_change_set_event_action_count CHECK (action_count >= 0),
    CONSTRAINT ck_change_set_event_outcome CHECK (core.is_nonblank(outcome)),
    CONSTRAINT ck_change_set_event_metadata CHECK (
        jsonb_typeof(event_metadata) = 'object'
        AND octet_length(event_metadata::TEXT) <= 65536
    )
);

CREATE TABLE workflow.idempotency_outcome (
    idempotency_outcome_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_scope VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    request_digest CHAR(64) NOT NULL,
    outcome_status VARCHAR(20) NOT NULL,
    outcome_document JSONB NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT uq_idempotency_scope_key UNIQUE (operation_scope, idempotency_key),
    CONSTRAINT ck_idempotency_scope CHECK (core.is_nonblank(operation_scope)),
    CONSTRAINT ck_idempotency_key CHECK (core.is_nonblank(idempotency_key)),
    CONSTRAINT ck_idempotency_request_digest CHECK (
        request_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_idempotency_status CHECK (
        outcome_status IN ('succeeded', 'rejected', 'failed')
    ),
    CONSTRAINT ck_idempotency_outcome CHECK (
        jsonb_typeof(outcome_document) = 'object'
        AND octet_length(outcome_document::TEXT) <= 1048576
    )
);

CREATE TABLE workflow.profiling_run (
    profiling_run_id UUID PRIMARY KEY,
    model_id BIGINT NOT NULL,
    profiling_run_status VARCHAR(30) NOT NULL DEFAULT 'staging',
    request_document JSONB NOT NULL,
    batch_environment VARCHAR(20) NOT NULL,
    batch_mode VARCHAR(20) NOT NULL,
    selection_digest CHAR(64) NOT NULL,
    source_context_digest CHAR(64) NOT NULL,
    base_model_revision BIGINT NOT NULL,
    selected_object_count INTEGER NOT NULL,
    staged_result_count INTEGER NOT NULL DEFAULT 0,
    staged_failure_count INTEGER NOT NULL DEFAULT 0,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    validated_time TIMESTAMPTZ,
    finalized_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '4 hours'),
    CONSTRAINT fk_profiling_run_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_profiling_run_id_model UNIQUE (profiling_run_id, model_id),
    CONSTRAINT ck_profiling_run_status CHECK (
        profiling_run_status IN (
            'staging', 'validated', 'completed',
            'completed_with_warnings', 'failed', 'expired'
        )
    ),
    CONSTRAINT ck_profiling_run_request CHECK (
        jsonb_typeof(request_document) = 'object'
        AND octet_length(request_document::TEXT) <= 1048576
    ),
    CONSTRAINT ck_profiling_run_batch CHECK (
        batch_environment IN ('development', 'test')
        AND batch_mode IN ('initial', 'incremental')
    ),
    CONSTRAINT ck_profiling_run_digests CHECK (
        selection_digest ~ '^[0-9a-f]{64}$'
        AND source_context_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_profiling_run_counts CHECK (
        base_model_revision > 0
        AND selected_object_count > 0
        AND staged_result_count >= 0
        AND staged_failure_count >= 0
    ),
    CONSTRAINT ck_profiling_run_expiry CHECK (expires_time > created_time)
);

CREATE TABLE workflow.workflow_grant (
    workflow_grant_id UUID PRIMARY KEY,
    workflow_run_id UUID NOT NULL UNIQUE,
    initiating_user_account_id BIGINT NOT NULL,
    initiating_user_entra_identity_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    workflow_name VARCHAR(30) NOT NULL,
    request_document JSONB NOT NULL,
    selection_digest CHAR(64) NOT NULL,
    allowed_operations TEXT[] NOT NULL,
    job_key VARCHAR(100) NOT NULL,
    source_release VARCHAR(100) NOT NULL,
    notebook_definition_version VARCHAR(100) NOT NULL,
    workload_entra_tenant_id UUID NOT NULL,
    workload_entra_object_id UUID NOT NULL,
    workflow_grant_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    issued_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activation_expires_time TIMESTAMPTZ NOT NULL,
    expires_time TIMESTAMPTZ NOT NULL,
    activated_time TIMESTAMPTZ,
    revoked_time TIMESTAMPTZ,
    revoked_by_user_account_id BIGINT,
    revoked_reason VARCHAR(2000),
    completed_time TIMESTAMPTZ,
    bound_change_set_id UUID,
    bound_profiling_run_id UUID,
    databricks_workspace_id VARCHAR(255),
    databricks_job_id VARCHAR(255),
    databricks_run_id VARCHAR(255),
    CONSTRAINT fk_workflow_grant_human_identity FOREIGN KEY (
        initiating_user_entra_identity_id,
        initiating_user_account_id
    ) REFERENCES core_security.user_entra_identity (
        user_entra_identity_id,
        user_account_id
    )
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_model FOREIGN KEY (model_id, tenant_id)
        REFERENCES model.model (model_id, tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_revoker FOREIGN KEY (revoked_by_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_change_set FOREIGN KEY (
        bound_change_set_id,
        model_id
    ) REFERENCES workflow.model_change_set (model_change_set_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_profiling_run FOREIGN KEY (
        bound_profiling_run_id,
        model_id
    ) REFERENCES workflow.profiling_run (profiling_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_workflow_grant_workflow CHECK (
        workflow_name IN (
            'profiling', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping', 'dbml'
        )
    ),
    CONSTRAINT ck_workflow_grant_request CHECK (
        jsonb_typeof(request_document) = 'object'
        AND octet_length(request_document::TEXT) <= 1048576
    ),
    CONSTRAINT ck_workflow_grant_selection_digest CHECK (
        selection_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_workflow_grant_operations CHECK (
        core.is_canonical_text_array(allowed_operations)
    ),
    CONSTRAINT ck_workflow_grant_job_key CHECK (
        job_key ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_workflow_grant_release_identity CHECK (
        source_release ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$'
        AND notebook_definition_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$'
    ),
    CONSTRAINT ck_workflow_grant_status CHECK (
        workflow_grant_status IN (
            'pending', 'active', 'revoked', 'expired', 'completed'
        )
    ),
    CONSTRAINT ck_workflow_grant_times CHECK (
        activation_expires_time > issued_time
        AND activation_expires_time <= issued_time + INTERVAL '15 minutes'
        AND expires_time > activation_expires_time
        AND expires_time <= issued_time + INTERVAL '4 hours'
        AND (activated_time IS NULL OR activated_time <= activation_expires_time)
        AND (completed_time IS NULL OR completed_time <= expires_time)
    ),
    CONSTRAINT ck_workflow_grant_revocation CHECK (
        (
            workflow_grant_status = 'revoked'
            AND revoked_time IS NOT NULL
            AND revoked_by_user_account_id IS NOT NULL
            AND core.is_nonblank(revoked_reason)
        ) OR (
            workflow_grant_status <> 'revoked'
            AND revoked_time IS NULL
            AND revoked_by_user_account_id IS NULL
            AND revoked_reason IS NULL
        )
    ),
    CONSTRAINT ck_workflow_grant_binding CHECK (
        (bound_change_set_id IS NOT NULL)::INTEGER
        + (bound_profiling_run_id IS NOT NULL)::INTEGER <= 1
    ),
    CONSTRAINT ck_workflow_grant_status_times CHECK (
        (
            workflow_grant_status = 'pending'
            AND activated_time IS NULL
            AND completed_time IS NULL
        ) OR (
            workflow_grant_status = 'active'
            AND activated_time IS NOT NULL
            AND completed_time IS NULL
        ) OR (
            workflow_grant_status IN ('revoked', 'expired')
            AND completed_time IS NULL
        ) OR (
            workflow_grant_status = 'completed'
            AND activated_time IS NOT NULL
            AND completed_time IS NOT NULL
        )
    )
);

ALTER TABLE workflow.workflow_grant
    ADD CONSTRAINT uq_workflow_grant_summary_witness UNIQUE (
        workflow_grant_id,
        workflow_run_id,
        model_id,
        workflow_name
    );

CREATE UNIQUE INDEX ux_workflow_grant_active_change_set
    ON workflow.workflow_grant (bound_change_set_id)
    WHERE bound_change_set_id IS NOT NULL
      AND workflow_grant_status IN ('pending', 'active');
CREATE UNIQUE INDEX ux_workflow_grant_active_profiling_run
    ON workflow.workflow_grant (bound_profiling_run_id)
    WHERE bound_profiling_run_id IS NOT NULL
      AND workflow_grant_status IN ('pending', 'active');

CREATE TABLE workflow.workflow_run_summary (
    workflow_run_id UUID PRIMARY KEY,
    workflow_grant_id UUID NOT NULL UNIQUE,
    model_id BIGINT NOT NULL,
    workflow_name VARCHAR(30) NOT NULL,
    run_status VARCHAR(30) NOT NULL,
    coverage_summary JSONB NOT NULL DEFAULT '{}'::JSONB,
    diagnostic_summary JSONB NOT NULL DEFAULT '{}'::JSONB,
    expected_item_count INTEGER NOT NULL DEFAULT 0,
    completed_item_count INTEGER NOT NULL DEFAULT 0,
    failed_item_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    started_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_time TIMESTAMPTZ,
    CONSTRAINT fk_workflow_run_summary_grant FOREIGN KEY (
        workflow_grant_id,
        workflow_run_id,
        model_id,
        workflow_name
    ) REFERENCES workflow.workflow_grant (
        workflow_grant_id,
        workflow_run_id,
        model_id,
        workflow_name
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_workflow_run_summary_workflow CHECK (
        workflow_name IN (
            'profiling', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping', 'dbml'
        )
    ),
    CONSTRAINT ck_workflow_run_summary_status CHECK (
        run_status IN (
            'pending', 'running', 'awaiting_validation', 'completed',
            'completed_with_warnings', 'blocked', 'failed', 'expired', 'revoked'
        )
    ),
    CONSTRAINT ck_workflow_run_summary_documents CHECK (
        jsonb_typeof(coverage_summary) = 'object'
        AND jsonb_typeof(diagnostic_summary) = 'object'
        AND octet_length(coverage_summary::TEXT) <= 1048576
        AND octet_length(diagnostic_summary::TEXT) <= 1048576
    ),
    CONSTRAINT ck_workflow_run_summary_counts CHECK (
        expected_item_count >= 0
        AND completed_item_count >= 0
        AND failed_item_count >= 0
        AND warning_count >= 0
        AND completed_item_count + failed_item_count <= expected_item_count
    ),
    CONSTRAINT ck_workflow_run_summary_completion CHECK (
        (run_status IN ('completed', 'completed_with_warnings', 'failed', 'expired', 'revoked'))
        = (completed_time IS NOT NULL)
    )
);

CREATE TABLE workflow.profiling_result_stage (
    profiling_result_stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profiling_run_id UUID NOT NULL,
    model_id BIGINT NOT NULL,
    stage_batch_id UUID NOT NULL,
    stage_batch_index INTEGER NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    object_id BIGINT NOT NULL,
    attribute_id BIGINT NOT NULL,
    profile_document JSONB NOT NULL,
    profile_digest CHAR(64) NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_profiling_result_run FOREIGN KEY (profiling_run_id, model_id)
        REFERENCES workflow.profiling_run (profiling_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_profiling_result_attribute FOREIGN KEY (attribute_id, object_id)
        REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_profiling_result_target
        UNIQUE (profiling_run_id, attribute_id),
    CONSTRAINT uq_profiling_result_idempotency
        UNIQUE (profiling_run_id, idempotency_key, attribute_id),
    CONSTRAINT ck_profiling_result_batch_index CHECK (stage_batch_index > 0),
    CONSTRAINT ck_profiling_result_document CHECK (
        jsonb_typeof(profile_document) = 'object'
        AND octet_length(profile_document::TEXT) <= 65536
    ),
    CONSTRAINT ck_profiling_result_digest CHECK (
        profile_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE workflow.profiling_failure_stage (
    profiling_failure_stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profiling_run_id UUID NOT NULL,
    model_id BIGINT NOT NULL,
    stage_batch_id UUID NOT NULL,
    stage_batch_index INTEGER NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    object_id BIGINT NOT NULL,
    attribute_id BIGINT NOT NULL,
    failure_code VARCHAR(100) NOT NULL,
    failure_message VARCHAR(2000) NOT NULL,
    failure_retryable BOOLEAN NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_profiling_failure_run FOREIGN KEY (profiling_run_id, model_id)
        REFERENCES workflow.profiling_run (profiling_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_profiling_failure_attribute FOREIGN KEY (attribute_id, object_id)
        REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_profiling_failure_target
        UNIQUE (profiling_run_id, attribute_id),
    CONSTRAINT uq_profiling_failure_idempotency
        UNIQUE (profiling_run_id, idempotency_key, attribute_id),
    CONSTRAINT ck_profiling_failure_batch_index CHECK (stage_batch_index > 0),
    CONSTRAINT ck_profiling_failure_code CHECK (core.is_nonblank(failure_code)),
    CONSTRAINT ck_profiling_failure_message CHECK (core.is_nonblank(failure_message))
);

CREATE TABLE workflow.profiling_final_receipt (
    profiling_final_receipt_id UUID PRIMARY KEY,
    profiling_run_id UUID NOT NULL UNIQUE,
    model_id BIGINT NOT NULL,
    model_revision_before BIGINT NOT NULL,
    model_revision_after BIGINT NOT NULL,
    changed_profile_count INTEGER NOT NULL,
    retained_failure_count INTEGER NOT NULL,
    receipt_status VARCHAR(30) NOT NULL,
    was_noop BOOLEAN NOT NULL,
    receipt_digest CHAR(64) NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_profiling_receipt_run FOREIGN KEY (profiling_run_id, model_id)
        REFERENCES workflow.profiling_run (profiling_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_profiling_receipt_revisions CHECK (
        model_revision_before > 0
        AND model_revision_after >= model_revision_before
        AND model_revision_after <= model_revision_before + 1
        AND was_noop = (model_revision_after = model_revision_before)
    ),
    CONSTRAINT ck_profiling_receipt_counts CHECK (
        changed_profile_count >= 0
        AND retained_failure_count >= 0
        AND was_noop = (changed_profile_count = 0)
    ),
    CONSTRAINT ck_profiling_receipt_status CHECK (
        receipt_status IN ('completed', 'completed_with_warnings', 'failed')
        AND (receipt_status <> 'completed' OR retained_failure_count = 0)
        AND (receipt_status <> 'completed_with_warnings' OR retained_failure_count > 0)
        AND (
            receipt_status <> 'failed'
            OR (retained_failure_count > 0 AND changed_profile_count = 0 AND was_noop)
        )
    ),
    CONSTRAINT ck_profiling_receipt_digest CHECK (
        receipt_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE workflow.model_apply_receipt (
    model_apply_receipt_id UUID PRIMARY KEY,
    model_change_set_id UUID NOT NULL UNIQUE,
    model_id BIGINT NOT NULL,
    candidate_digest CHAR(64) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    model_revision_before BIGINT NOT NULL,
    model_revision_after BIGINT NOT NULL,
    was_effective_change BOOLEAN NOT NULL,
    operation_counts JSONB NOT NULL,
    correlation_id UUID NOT NULL,
    applied_by_user_account_id BIGINT NOT NULL,
    workflow_run_id UUID,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_apply_receipt_change_set FOREIGN KEY (
        model_change_set_id,
        model_id
    ) REFERENCES workflow.model_change_set (model_change_set_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_apply_receipt_actor FOREIGN KEY (applied_by_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_apply_receipt_id_model UNIQUE (model_apply_receipt_id, model_id),
    CONSTRAINT uq_apply_receipt_idempotency UNIQUE (model_id, idempotency_key),
    CONSTRAINT ck_apply_receipt_digest CHECK (
        candidate_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_apply_receipt_revisions CHECK (
        model_revision_before > 0
        AND model_revision_after >= model_revision_before
        AND model_revision_after <= model_revision_before + 1
        AND was_effective_change = (
            model_revision_after = model_revision_before + 1
        )
    ),
    CONSTRAINT ck_apply_receipt_counts CHECK (
        jsonb_typeof(operation_counts) = 'object'
        AND octet_length(operation_counts::TEXT) <= 65536
    )
);

CREATE TABLE workflow.model_apply_receipt_ref (
    model_apply_receipt_ref_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_apply_receipt_id UUID NOT NULL,
    model_id BIGINT NOT NULL,
    section_name VARCHAR(20) NOT NULL,
    artifact_type VARCHAR(100) NOT NULL,
    local_ref VARCHAR(255) NOT NULL,
    database_id BIGINT NOT NULL,
    CONSTRAINT fk_apply_receipt_ref_parent FOREIGN KEY (
        model_apply_receipt_id,
        model_id
    ) REFERENCES workflow.model_apply_receipt (
        model_apply_receipt_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_apply_receipt_local_ref UNIQUE (
        model_apply_receipt_id,
        section_name,
        local_ref
    ),
    CONSTRAINT ck_apply_receipt_ref_section CHECK (
        section_name IN (
            'evidence', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping'
        )
    ),
    CONSTRAINT ck_apply_receipt_ref_values CHECK (
        core.is_nonblank(artifact_type)
        AND core.is_nonblank(local_ref)
        AND database_id > 0
    )
);

CREATE FUNCTION workflow.guard_model_change_set_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.model_change_set_id <> OLD.model_change_set_id
       OR NEW.model_id <> OLD.model_id
       OR NEW.base_model_revision <> OLD.base_model_revision
       OR NEW.base_source_context_digest <> OLD.base_source_context_digest
       OR NEW.base_evidence_digest <> OLD.base_evidence_digest
       OR NEW.base_policy_digest <> OLD.base_policy_digest
       OR NEW.created_by_user_account_id <> OLD.created_by_user_account_id
       OR NEW.created_time <> OLD.created_time
    THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'change-set identity is immutable';
    END IF;

    IF OLD.model_change_set_status IN ('applied', 'expired', 'discarded', 'superseded') THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'terminal change set is immutable';
    END IF;

    IF ((
        NEW.evidence_document IS DISTINCT FROM OLD.evidence_document
        OR NEW.analysis_document IS DISTINCT FROM OLD.analysis_document
        OR NEW.conceptual_document IS DISTINCT FROM OLD.conceptual_document
        OR NEW.logical_document IS DISTINCT FROM OLD.logical_document
        OR NEW.dimensional_document IS DISTINCT FROM OLD.dimensional_document
        OR NEW.mapping_document IS DISTINCT FROM OLD.mapping_document
    ) OR NEW.draft_revision <> OLD.draft_revision) AND NOT (
        NEW.draft_revision = OLD.draft_revision + 1
        AND NEW.model_change_set_status = 'active'
        AND NEW.candidate_digest IS NULL
        AND NEW.validation_outcome IS NULL
        AND NEW.validated_time IS NULL
        AND NEW.last_activity_time > OLD.last_activity_time
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'section put must advance draft revision and invalidate validation';
    END IF;

    IF NEW.model_change_set_status = 'validated' AND NOT (
        NEW.candidate_digest IS NOT NULL
        AND NEW.validation_outcome IS NOT NULL
        AND NEW.validated_time IS NOT NULL
        AND NEW.last_activity_time > OLD.last_activity_time
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'validated change set requires a sealed validation outcome';
    END IF;

    IF NOT (
        (OLD.model_change_set_status = 'active' AND NEW.model_change_set_status IN (
            'active', 'validated', 'expired', 'discarded', 'superseded'
        )) OR
        (OLD.model_change_set_status = 'validated' AND NEW.model_change_set_status IN (
            'active', 'validated', 'applied', 'expired', 'discarded', 'superseded'
        ))
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid change-set transition';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.guard_workflow_grant_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.workflow_grant_id <> OLD.workflow_grant_id
       OR NEW.workflow_run_id <> OLD.workflow_run_id
       OR NEW.initiating_user_account_id <> OLD.initiating_user_account_id
       OR NEW.initiating_user_entra_identity_id <> OLD.initiating_user_entra_identity_id
       OR NEW.tenant_id <> OLD.tenant_id
       OR NEW.model_id <> OLD.model_id
       OR NEW.workflow_name <> OLD.workflow_name
       OR NEW.request_document <> OLD.request_document
       OR NEW.selection_digest <> OLD.selection_digest
       OR NEW.allowed_operations <> OLD.allowed_operations
       OR NEW.job_key <> OLD.job_key
       OR NEW.source_release <> OLD.source_release
       OR NEW.notebook_definition_version <> OLD.notebook_definition_version
       OR NEW.workload_entra_tenant_id <> OLD.workload_entra_tenant_id
       OR NEW.workload_entra_object_id <> OLD.workload_entra_object_id
       OR NEW.issued_time <> OLD.issued_time
       OR NEW.activation_expires_time <> OLD.activation_expires_time
       OR NEW.expires_time <> OLD.expires_time
    THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'workflow grant scope is immutable';
    END IF;

    IF OLD.workflow_grant_status IN ('revoked', 'expired', 'completed') THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'terminal workflow grant is immutable';
    END IF;

    IF OLD.bound_change_set_id IS NOT NULL
       AND NEW.bound_change_set_id IS DISTINCT FROM OLD.bound_change_set_id
    OR OLD.bound_profiling_run_id IS NOT NULL
       AND NEW.bound_profiling_run_id IS DISTINCT FROM OLD.bound_profiling_run_id
    THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'workflow grant binding is immutable once set';
    END IF;

    IF OLD.databricks_workspace_id IS NOT NULL
       AND NEW.databricks_workspace_id IS DISTINCT FROM OLD.databricks_workspace_id
    OR OLD.databricks_job_id IS NOT NULL
       AND NEW.databricks_job_id IS DISTINCT FROM OLD.databricks_job_id
    OR OLD.databricks_run_id IS NOT NULL
       AND NEW.databricks_run_id IS DISTINCT FROM OLD.databricks_run_id
    THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'Databricks run identity is immutable once set';
    END IF;

    IF NEW.workflow_grant_status = 'active'
       AND CURRENT_TIMESTAMP > NEW.activation_expires_time
    THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'workflow grant activation deadline passed';
    END IF;
    IF NOT (
        (OLD.workflow_grant_status = 'pending' AND NEW.workflow_grant_status IN (
            'pending', 'active', 'revoked', 'expired'
        )) OR
        (OLD.workflow_grant_status = 'active' AND NEW.workflow_grant_status IN (
            'active', 'revoked', 'expired', 'completed'
        ))
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid workflow-grant transition';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.guard_profiling_run_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.profiling_run_id <> OLD.profiling_run_id
       OR NEW.model_id <> OLD.model_id
       OR NEW.request_document <> OLD.request_document
       OR NEW.batch_environment <> OLD.batch_environment
       OR NEW.batch_mode <> OLD.batch_mode
       OR NEW.selection_digest <> OLD.selection_digest
       OR NEW.source_context_digest <> OLD.source_context_digest
       OR NEW.base_model_revision <> OLD.base_model_revision
       OR NEW.selected_object_count <> OLD.selected_object_count
       OR NEW.correlation_id <> OLD.correlation_id
       OR NEW.created_time <> OLD.created_time
       OR NEW.expires_time <> OLD.expires_time
    THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'profiling run scope is immutable';
    END IF;
    IF OLD.profiling_run_status IN (
        'completed', 'completed_with_warnings', 'failed', 'expired'
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'terminal profiling run is immutable';
    END IF;
    IF NOT (
        (OLD.profiling_run_status = 'staging' AND NEW.profiling_run_status IN (
            'staging', 'validated', 'failed', 'expired'
        )) OR
        (OLD.profiling_run_status = 'validated' AND NEW.profiling_run_status IN (
            'validated', 'completed', 'completed_with_warnings', 'failed', 'expired'
        ))
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid profiling-run transition';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.guard_workflow_run_summary_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.workflow_run_id <> OLD.workflow_run_id
       OR NEW.workflow_grant_id <> OLD.workflow_grant_id
       OR NEW.model_id <> OLD.model_id
       OR NEW.workflow_name <> OLD.workflow_name
       OR NEW.started_time <> OLD.started_time
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'workflow run summary identity is immutable';
    END IF;
    IF OLD.run_status IN (
        'completed', 'completed_with_warnings', 'failed', 'expired', 'revoked'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'terminal workflow run summary is immutable';
    END IF;
    IF NOT (
        (OLD.run_status = 'pending' AND NEW.run_status IN (
            'pending', 'running', 'expired', 'revoked'
        )) OR
        (OLD.run_status = 'running' AND NEW.run_status IN (
            'running', 'awaiting_validation', 'completed',
            'completed_with_warnings', 'blocked', 'failed', 'expired', 'revoked'
        )) OR
        (OLD.run_status = 'awaiting_validation' AND NEW.run_status IN (
            'awaiting_validation', 'running', 'completed',
            'completed_with_warnings', 'blocked', 'failed', 'expired', 'revoked'
        )) OR
        (OLD.run_status = 'blocked' AND NEW.run_status IN (
            'blocked', 'running', 'failed', 'expired', 'revoked'
        ))
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'invalid workflow-run-summary transition';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION workflow.assert_profiling_stage_disposition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM workflow.profiling_result_stage AS result
          JOIN workflow.profiling_failure_stage AS failure
            ON failure.profiling_run_id = result.profiling_run_id
           AND failure.attribute_id = result.attribute_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'profiling target cannot have both result and failure dispositions';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER guard_change_set_transition BEFORE UPDATE
ON workflow.model_change_set FOR EACH ROW
EXECUTE FUNCTION workflow.guard_model_change_set_transition();
CREATE TRIGGER guard_workflow_grant_transition BEFORE UPDATE
ON workflow.workflow_grant FOR EACH ROW
EXECUTE FUNCTION workflow.guard_workflow_grant_transition();
CREATE TRIGGER guard_profiling_run_transition BEFORE UPDATE
ON workflow.profiling_run FOR EACH ROW
EXECUTE FUNCTION workflow.guard_profiling_run_transition();
CREATE TRIGGER guard_workflow_run_summary_transition BEFORE UPDATE
ON workflow.workflow_run_summary FOR EACH ROW
EXECUTE FUNCTION workflow.guard_workflow_run_summary_transition();

CREATE CONSTRAINT TRIGGER validate_profiling_result_disposition
AFTER INSERT OR UPDATE ON workflow.profiling_result_stage
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION workflow.assert_profiling_stage_disposition();
CREATE CONSTRAINT TRIGGER validate_profiling_failure_disposition
AFTER INSERT OR UPDATE ON workflow.profiling_failure_stage
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION workflow.assert_profiling_stage_disposition();

CREATE TRIGGER guard_change_set_event_append_only BEFORE UPDATE OR DELETE
ON workflow.model_change_set_event FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_idempotency_outcome_append_only BEFORE UPDATE OR DELETE
ON workflow.idempotency_outcome FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_profiling_result_stage_append_only BEFORE UPDATE OR DELETE
ON workflow.profiling_result_stage FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_profiling_failure_stage_append_only BEFORE UPDATE OR DELETE
ON workflow.profiling_failure_stage FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_profiling_receipt_append_only BEFORE UPDATE OR DELETE
ON workflow.profiling_final_receipt FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_apply_receipt_append_only BEFORE UPDATE OR DELETE
ON workflow.model_apply_receipt FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();
CREATE TRIGGER guard_apply_receipt_ref_append_only BEFORE UPDATE OR DELETE
ON workflow.model_apply_receipt_ref FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();

CREATE INDEX ix_change_set_model_status_activity
    ON workflow.model_change_set (model_id, model_change_set_status, last_activity_time);
CREATE INDEX ix_change_set_expiry
    ON workflow.model_change_set (expires_time)
    WHERE model_change_set_status IN ('active', 'validated');
CREATE INDEX ix_change_set_event_parent_sequence
    ON workflow.model_change_set_event (model_change_set_id, event_sequence);
CREATE INDEX ix_profiling_run_model_status
    ON workflow.profiling_run (model_id, profiling_run_status, created_time);
CREATE INDEX ix_workflow_grant_model_status
    ON workflow.workflow_grant (model_id, workflow_grant_status, expires_time);
CREATE INDEX ix_workflow_grant_human_status
    ON workflow.workflow_grant (
        initiating_user_account_id,
        workflow_grant_status,
        expires_time
    );
CREATE INDEX ix_workflow_grant_workload_status
    ON workflow.workflow_grant (
        workload_entra_tenant_id,
        workload_entra_object_id,
        workflow_grant_status,
        expires_time
    );
CREATE INDEX ix_workflow_run_summary_model
    ON workflow.workflow_run_summary (model_id, workflow_name, started_time);
CREATE INDEX ix_profiling_result_stage_run_batch
    ON workflow.profiling_result_stage (profiling_run_id, stage_batch_index);
CREATE INDEX ix_profiling_failure_stage_run_batch
    ON workflow.profiling_failure_stage (profiling_run_id, stage_batch_index);
