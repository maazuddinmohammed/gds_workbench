-- GDS ETL Workbench Release 1: registered Principal Workflow Grant and Workflow Run state.

CREATE TABLE workflow.workflow_grant (
    workflow_grant_id UUID PRIMARY KEY,
    workflow_run_id UUID NOT NULL UNIQUE,
    initiating_principal_id BIGINT NOT NULL,
    initiating_entra_principal_identity_id BIGINT NOT NULL,
    initiating_principal_type VARCHAR(30) NOT NULL DEFAULT 'user',
    tenant_id BIGINT NOT NULL,
    model_id BIGINT NOT NULL,
    workflow_name VARCHAR(30) NOT NULL,
    request_document JSONB NOT NULL,
    selection_digest CHAR(64) NOT NULL,
    allowed_operations TEXT[] NOT NULL,
    job_key VARCHAR(100) NOT NULL,
    source_release VARCHAR(100) NOT NULL,
    notebook_definition_version VARCHAR(100) NOT NULL,
    workload_principal_id BIGINT NOT NULL,
    workload_entra_principal_identity_id BIGINT NOT NULL,
    workload_principal_type VARCHAR(30) NOT NULL DEFAULT 'service_principal',
    workflow_grant_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    issued_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activation_expires_time TIMESTAMPTZ NOT NULL,
    expires_time TIMESTAMPTZ NOT NULL,
    activated_time TIMESTAMPTZ,
    revoked_time TIMESTAMPTZ,
    revoked_by_principal_id BIGINT,
    revoked_reason VARCHAR(2000),
    completed_time TIMESTAMPTZ,
    bound_change_set_id UUID,
    bound_profiling_run_id UUID,
    databricks_workspace_id VARCHAR(255),
    databricks_job_id VARCHAR(255),
    databricks_run_id VARCHAR(255),
    CONSTRAINT fk_workflow_grant_initiating_identity FOREIGN KEY (
        initiating_entra_principal_identity_id,
        initiating_principal_id,
        initiating_principal_type
    ) REFERENCES security.entra_principal_identity (
        entra_principal_identity_id,
        principal_id,
        principal_type
    )
        ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_workload_identity FOREIGN KEY (
        workload_entra_principal_identity_id,
        workload_principal_id,
        workload_principal_type
    ) REFERENCES security.entra_principal_identity (
        entra_principal_identity_id,
        principal_id,
        principal_type
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_model FOREIGN KEY (model_id, tenant_id)
        REFERENCES model.model (model_id, tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_workflow_grant_revoker FOREIGN KEY (revoked_by_principal_id)
        REFERENCES security.principal (principal_id)
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
    CONSTRAINT ck_workflow_grant_principal_types CHECK (
        initiating_principal_type = 'user'
        AND workload_principal_type = 'service_principal'
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
            AND revoked_by_principal_id IS NOT NULL
            AND reference.is_nonblank(revoked_reason)
        ) OR (
            workflow_grant_status <> 'revoked'
            AND revoked_time IS NULL
            AND revoked_by_principal_id IS NULL
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

CREATE FUNCTION workflow.guard_workflow_grant_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.workflow_grant_id <> OLD.workflow_grant_id
       OR NEW.workflow_run_id <> OLD.workflow_run_id
       OR NEW.initiating_principal_id <> OLD.initiating_principal_id
       OR NEW.initiating_entra_principal_identity_id
          <> OLD.initiating_entra_principal_identity_id
       OR NEW.initiating_principal_type <> OLD.initiating_principal_type
       OR NEW.tenant_id <> OLD.tenant_id
       OR NEW.model_id <> OLD.model_id
       OR NEW.workflow_name <> OLD.workflow_name
       OR NEW.request_document <> OLD.request_document
       OR NEW.selection_digest <> OLD.selection_digest
       OR NEW.allowed_operations <> OLD.allowed_operations
       OR NEW.job_key <> OLD.job_key
       OR NEW.source_release <> OLD.source_release
       OR NEW.notebook_definition_version <> OLD.notebook_definition_version
       OR NEW.workload_principal_id <> OLD.workload_principal_id
       OR NEW.workload_entra_principal_identity_id
          <> OLD.workload_entra_principal_identity_id
       OR NEW.workload_principal_type <> OLD.workload_principal_type
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

CREATE TRIGGER guard_workflow_grant_transition BEFORE UPDATE
ON workflow.workflow_grant FOR EACH ROW
EXECUTE FUNCTION workflow.guard_workflow_grant_transition();

CREATE TRIGGER guard_workflow_run_summary_transition BEFORE UPDATE
ON workflow.workflow_run_summary FOR EACH ROW
EXECUTE FUNCTION workflow.guard_workflow_run_summary_transition();

CREATE INDEX ix_workflow_grant_model_status
    ON workflow.workflow_grant (model_id, workflow_grant_status, expires_time);

CREATE INDEX ix_workflow_grant_human_status
    ON workflow.workflow_grant (
        initiating_principal_id,
        workflow_grant_status,
        expires_time
    );

CREATE INDEX ix_workflow_grant_workload_status
    ON workflow.workflow_grant (
        workload_entra_principal_identity_id,
        workflow_grant_status,
        expires_time
    );

CREATE INDEX ix_workflow_run_summary_model
    ON workflow.workflow_run_summary (model_id, workflow_name, started_time);
