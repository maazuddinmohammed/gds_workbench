-- GDS ETL Workbench Release 1: direct Profiling Run and receipt state.

CREATE TABLE workflow.profiling_run (
    profiling_run_id UUID PRIMARY KEY,
    model_id BIGINT NOT NULL,
    profiling_run_status VARCHAR(30) NOT NULL DEFAULT 'running',
    request_document JSONB NOT NULL,
    batch_environment VARCHAR(20) NOT NULL,
    batch_mode VARCHAR(20) NOT NULL,
    selection_digest CHAR(64) NOT NULL,
    source_context_digest CHAR(64) NOT NULL,
    base_model_revision BIGINT NOT NULL,
    selected_object_count INTEGER NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '4 hours'),
    CONSTRAINT fk_profiling_run_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_profiling_run_id_model UNIQUE (profiling_run_id, model_id),
    CONSTRAINT ck_profiling_run_status CHECK (
        profiling_run_status IN (
            'running', 'completed', 'completed_with_warnings',
            'failed', 'expired'
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
    ),
    CONSTRAINT ck_profiling_run_completion CHECK (
        (profiling_run_status = 'running') = (completed_time IS NULL)
    ),
    CONSTRAINT ck_profiling_run_expiry CHECK (expires_time > created_time)
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

CREATE INDEX ix_profiling_run_model_status
    ON workflow.profiling_run (model_id, profiling_run_status, created_time);
