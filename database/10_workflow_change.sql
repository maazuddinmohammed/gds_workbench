-- GDS ETL Workbench Release 1: durable Model Change Set state.

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
        SELECT 1 FROM unnest(value) AS item WHERE NOT reference.is_nonblank(item)
   );

CREATE TABLE workflow.model_change_set (
    model_change_set_id UUID PRIMARY KEY,
    model_id BIGINT NOT NULL,
    model_change_set_status VARCHAR(20) NOT NULL DEFAULT 'active',
    base_model_revision BIGINT NOT NULL,
    base_source_context_digest CHAR(64) NOT NULL,
    base_assertion_digest CHAR(64) NOT NULL,
    base_policy_digest CHAR(64) NOT NULL,
    draft_revision BIGINT NOT NULL DEFAULT 1,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    model_scope_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    profiling_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    assertion_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    analysis_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    conceptual_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    logical_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    dimensional_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    mapping_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by_principal_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '4 hours'),
    validated_time TIMESTAMPTZ,
    applied_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_change_set_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_change_set_creator FOREIGN KEY (created_by_principal_id)
        REFERENCES security.principal (principal_id)
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
        AND base_assertion_digest ~ '^[0-9a-f]{64}$'
        AND base_policy_digest ~ '^[0-9a-f]{64}$'
        AND (candidate_digest IS NULL OR candidate_digest ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT ck_change_set_validation_outcome CHECK (
        validation_outcome IS NULL OR jsonb_typeof(validation_outcome) = 'object'
    ),
    CONSTRAINT ck_change_set_documents CHECK (
        jsonb_typeof(model_scope_document) = 'object'
        AND jsonb_typeof(profiling_document) = 'object'
        AND jsonb_typeof(assertion_document) = 'object'
        AND jsonb_typeof(analysis_document) = 'object'
        AND jsonb_typeof(conceptual_document) = 'object'
        AND jsonb_typeof(logical_document) = 'object'
        AND jsonb_typeof(dimensional_document) = 'object'
        AND jsonb_typeof(mapping_document) = 'object'
        AND octet_length(model_scope_document::TEXT) <= 16777216
        AND octet_length(profiling_document::TEXT) <= 16777216
        AND octet_length(assertion_document::TEXT) <= 16777216
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
            'model_scope', 'profiling', 'assertion', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping'
        )
    ),
    CONSTRAINT ck_change_set_event_action_count CHECK (action_count >= 0),
    CONSTRAINT ck_change_set_event_outcome CHECK (reference.is_nonblank(outcome)),
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
    CONSTRAINT ck_idempotency_scope CHECK (reference.is_nonblank(operation_scope)),
    CONSTRAINT ck_idempotency_key CHECK (reference.is_nonblank(idempotency_key)),
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
    applied_by_principal_id BIGINT NOT NULL,
    workflow_run_id UUID,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_apply_receipt_change_set FOREIGN KEY (
        model_change_set_id,
        model_id
    ) REFERENCES workflow.model_change_set (model_change_set_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_apply_receipt_actor FOREIGN KEY (applied_by_principal_id)
        REFERENCES security.principal (principal_id)
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
            'model_scope', 'profiling', 'assertion', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping'
        )
    ),
    CONSTRAINT ck_apply_receipt_ref_values CHECK (
        reference.is_nonblank(artifact_type)
        AND reference.is_nonblank(local_ref)
        AND database_id > 0
    )
);

CREATE TABLE workflow.metadata_change_set (
    metadata_change_set_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    metadata_change_set_status VARCHAR(20) NOT NULL DEFAULT 'active',
    base_metadata_digest CHAR(64) NOT NULL,
    draft_revision BIGINT NOT NULL DEFAULT 1,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    source_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    source_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    bronze_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    bronze_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    silver_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    silver_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    gold_object_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    gold_attribute_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    copy_group_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    copy_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    process_group_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    process_document JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by_principal_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (
        CURRENT_TIMESTAMP + INTERVAL '4 hours'
    ),
    validated_time TIMESTAMPTZ,
    applied_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_metadata_change_set_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_change_set_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_change_set_id_tenant
        UNIQUE (metadata_change_set_id, tenant_id),
    CONSTRAINT ck_metadata_change_set_status CHECK (
        metadata_change_set_status IN (
            'active', 'validated', 'applied',
            'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_revision CHECK (draft_revision >= 1),
    CONSTRAINT ck_metadata_change_set_digests CHECK (
        base_metadata_digest ~ '^[0-9a-f]{64}$'
        AND (candidate_digest IS NULL OR candidate_digest ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT ck_metadata_change_set_validation_outcome CHECK (
        validation_outcome IS NULL
        OR jsonb_typeof(validation_outcome) = 'object'
    ),
    CONSTRAINT ck_metadata_change_set_documents CHECK (
        jsonb_typeof(source_object_document) = 'object'
        AND jsonb_typeof(source_attribute_document) = 'object'
        AND jsonb_typeof(bronze_object_document) = 'object'
        AND jsonb_typeof(bronze_attribute_document) = 'object'
        AND jsonb_typeof(silver_object_document) = 'object'
        AND jsonb_typeof(silver_attribute_document) = 'object'
        AND jsonb_typeof(gold_object_document) = 'object'
        AND jsonb_typeof(gold_attribute_document) = 'object'
        AND jsonb_typeof(copy_group_document) = 'object'
        AND jsonb_typeof(copy_document) = 'object'
        AND jsonb_typeof(process_group_document) = 'object'
        AND jsonb_typeof(process_document) = 'object'
        AND octet_length(source_object_document::TEXT) <= 16777216
        AND octet_length(source_attribute_document::TEXT) <= 16777216
        AND octet_length(bronze_object_document::TEXT) <= 16777216
        AND octet_length(bronze_attribute_document::TEXT) <= 16777216
        AND octet_length(silver_object_document::TEXT) <= 16777216
        AND octet_length(silver_attribute_document::TEXT) <= 16777216
        AND octet_length(gold_object_document::TEXT) <= 16777216
        AND octet_length(gold_attribute_document::TEXT) <= 16777216
        AND octet_length(copy_group_document::TEXT) <= 16777216
        AND octet_length(copy_document::TEXT) <= 16777216
        AND octet_length(process_group_document::TEXT) <= 16777216
        AND octet_length(process_document::TEXT) <= 16777216
    ),
    CONSTRAINT ck_metadata_change_set_expiry CHECK (
        last_activity_time >= created_time
        AND expires_time > last_activity_time
    ),
    CONSTRAINT ck_metadata_change_set_candidate_state CHECK (
        (metadata_change_set_status = 'active' AND candidate_digest IS NULL)
        OR (
            metadata_change_set_status IN ('validated', 'applied')
            AND candidate_digest IS NOT NULL
        )
        OR metadata_change_set_status IN (
            'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_terminal_time CHECK (
        (
            metadata_change_set_status IN (
                'applied', 'expired', 'discarded', 'superseded'
            )
        ) = (terminal_time IS NOT NULL)
    )
);

CREATE TABLE workflow.metadata_change_set_event (
    metadata_change_set_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metadata_change_set_id UUID NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_sequence BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    draft_revision BIGINT NOT NULL,
    section_name VARCHAR(30),
    action_count INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(30) NOT NULL,
    validation_report_id UUID,
    event_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_metadata_change_set_event_parent FOREIGN KEY (
        metadata_change_set_id,
        tenant_id
    ) REFERENCES workflow.metadata_change_set (
        metadata_change_set_id,
        tenant_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_change_set_event_sequence
        UNIQUE (metadata_change_set_id, event_sequence),
    CONSTRAINT ck_metadata_change_set_event_sequence CHECK (event_sequence > 0),
    CONSTRAINT ck_metadata_change_set_event_type CHECK (
        event_type IN (
            'created', 'section_put', 'validated', 'validation_failed',
            'applied', 'expired', 'discarded', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_event_revision CHECK (
        draft_revision >= 1
    ),
    CONSTRAINT ck_metadata_change_set_event_section CHECK (
        section_name IS NULL
        OR section_name IN (
            'source_object', 'source_attribute',
            'bronze_object', 'bronze_attribute',
            'silver_object', 'silver_attribute',
            'gold_object', 'gold_attribute',
            'copy_group', 'copy', 'process_group', 'process'
        )
    ),
    CONSTRAINT ck_metadata_change_set_event_action_count CHECK (
        action_count >= 0
    ),
    CONSTRAINT ck_metadata_change_set_event_outcome CHECK (
        reference.is_nonblank(outcome)
    ),
    CONSTRAINT ck_metadata_change_set_event_metadata CHECK (
        jsonb_typeof(event_metadata) = 'object'
        AND octet_length(event_metadata::TEXT) <= 65536
    )
);

CREATE TABLE workflow.metadata_apply_receipt (
    metadata_apply_receipt_id UUID PRIMARY KEY,
    metadata_change_set_id UUID NOT NULL UNIQUE,
    tenant_id BIGINT NOT NULL,
    candidate_digest CHAR(64) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    metadata_digest_before CHAR(64) NOT NULL,
    metadata_digest_after CHAR(64) NOT NULL,
    was_effective_change BOOLEAN NOT NULL,
    operation_counts JSONB NOT NULL,
    correlation_id UUID NOT NULL,
    applied_by_principal_id BIGINT NOT NULL,
    workflow_run_id UUID,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_metadata_apply_receipt_change_set FOREIGN KEY (
        metadata_change_set_id,
        tenant_id
    ) REFERENCES workflow.metadata_change_set (
        metadata_change_set_id,
        tenant_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_apply_receipt_actor FOREIGN KEY (
        applied_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_apply_receipt_id_tenant
        UNIQUE (metadata_apply_receipt_id, tenant_id),
    CONSTRAINT uq_metadata_apply_receipt_idempotency
        UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT ck_metadata_apply_receipt_digests CHECK (
        candidate_digest ~ '^[0-9a-f]{64}$'
        AND metadata_digest_before ~ '^[0-9a-f]{64}$'
        AND metadata_digest_after ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_metadata_apply_receipt_effect CHECK (
        was_effective_change = (
            metadata_digest_before <> metadata_digest_after
        )
    ),
    CONSTRAINT ck_metadata_apply_receipt_counts CHECK (
        jsonb_typeof(operation_counts) = 'object'
        AND octet_length(operation_counts::TEXT) <= 65536
    )
);

CREATE TABLE workflow.metadata_apply_receipt_ref (
    metadata_apply_receipt_ref_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metadata_apply_receipt_id UUID NOT NULL,
    tenant_id BIGINT NOT NULL,
    section_name VARCHAR(30) NOT NULL,
    artifact_type VARCHAR(100) NOT NULL,
    local_ref VARCHAR(255) NOT NULL,
    database_id BIGINT NOT NULL,
    CONSTRAINT fk_metadata_apply_receipt_ref_parent FOREIGN KEY (
        metadata_apply_receipt_id,
        tenant_id
    ) REFERENCES workflow.metadata_apply_receipt (
        metadata_apply_receipt_id,
        tenant_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_apply_receipt_local_ref UNIQUE (
        metadata_apply_receipt_id,
        section_name,
        local_ref
    ),
    CONSTRAINT ck_metadata_apply_receipt_ref_section CHECK (
        section_name IN (
            'source_object', 'source_attribute',
            'bronze_object', 'bronze_attribute',
            'silver_object', 'silver_attribute',
            'gold_object', 'gold_attribute',
            'copy_group', 'copy', 'process_group', 'process'
        )
    ),
    CONSTRAINT ck_metadata_apply_receipt_ref_values CHECK (
        reference.is_nonblank(artifact_type)
        AND reference.is_nonblank(local_ref)
        AND database_id > 0
    )
);

CREATE INDEX ix_change_set_model_status_activity
    ON workflow.model_change_set (model_id, model_change_set_status, last_activity_time);

CREATE INDEX ix_change_set_expiry
    ON workflow.model_change_set (expires_time)
    WHERE model_change_set_status IN ('active', 'validated');

CREATE INDEX ix_metadata_change_set_tenant_status_activity
    ON workflow.metadata_change_set (
        tenant_id,
        metadata_change_set_status,
        last_activity_time
    );

CREATE INDEX ix_metadata_change_set_expiry
    ON workflow.metadata_change_set (expires_time)
    WHERE metadata_change_set_status IN ('active', 'validated');
