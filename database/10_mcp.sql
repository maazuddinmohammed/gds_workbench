-- GDS ETL Workbench Release 1: MCP-owned persistence.

CREATE SCHEMA mcp;

CREATE TABLE mcp.model_change_set (
    model_change_set_id UUID PRIMARY KEY,
    model_id BIGINT NOT NULL,
    workflow_run_id BIGINT,
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
    CONSTRAINT fk_change_set_workflow_run FOREIGN KEY (
        workflow_run_id,
        model_id
    ) REFERENCES application.workflow_run (workflow_run_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_change_set_creator FOREIGN KEY (created_by_principal_id)
        REFERENCES security.principal (principal_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_change_set_id_model UNIQUE (model_change_set_id, model_id),
    CONSTRAINT uq_change_set_workflow_run UNIQUE (workflow_run_id),
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

CREATE FUNCTION mcp.guard_model_change_set_workflow_binding()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $guard_model_change_set_workflow_binding$
BEGIN
    IF NEW.workflow_run_id IS DISTINCT FROM OLD.workflow_run_id THEN
        RAISE EXCEPTION 'Model Change Set Workflow Run binding is immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$guard_model_change_set_workflow_binding$;

CREATE TRIGGER guard_model_change_set_workflow_binding
BEFORE UPDATE ON mcp.model_change_set
FOR EACH ROW EXECUTE FUNCTION mcp.guard_model_change_set_workflow_binding();

CREATE TABLE mcp.model_stage_batch (
    stage_batch_id UUID PRIMARY KEY,
    model_change_set_id UUID NOT NULL,
    model_id BIGINT NOT NULL,
    dataset_name VARCHAR(50) NOT NULL,
    expected_draft_revision BIGINT NOT NULL,
    total_record_count INTEGER NOT NULL,
    total_chunk_count INTEGER NOT NULL,
    batch_sha256 CHAR(64) NOT NULL,
    stage_batch_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_by_principal_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (
        CURRENT_TIMESTAMP + INTERVAL '4 hours'
    ),
    committed_revision BIGINT,
    committed_expires_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_model_stage_batch_change_set FOREIGN KEY (
        model_change_set_id,
        model_id
    ) REFERENCES mcp.model_change_set (
        model_change_set_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_model_stage_batch_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_stage_batch_id_model
        UNIQUE (stage_batch_id, model_id),
    CONSTRAINT ck_model_stage_batch_dataset CHECK (
        dataset_name IN (
            'model_details', 'model_scope', 'profiling_profile',
            'analysis_result', 'modeling_assertion_document',
            'modeling_assertion_record', 'conceptual_object',
            'conceptual_relationship', 'logical_submodel', 'logical_entity',
            'logical_attribute', 'logical_relationship',
            'dimensional_submodel', 'dimensional_entity',
            'dimensional_attribute', 'dimensional_relationship',
            'mapping_dependency', 'mapping_object', 'mapping_attribute'
        )
    ),
    CONSTRAINT ck_model_stage_batch_manifest CHECK (
        expected_draft_revision >= 1
        AND total_record_count BETWEEN 1 AND 20000
        AND total_chunk_count BETWEEN 1 AND 64
        AND batch_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_model_stage_batch_status CHECK (
        stage_batch_status IN ('active', 'committed', 'expired')
    ),
    CONSTRAINT ck_model_stage_batch_expiry CHECK (
        last_activity_time >= created_time
        AND expires_time > last_activity_time
    ),
    CONSTRAINT ck_model_stage_batch_terminal_state CHECK (
        (
            stage_batch_status = 'active'
            AND committed_revision IS NULL
            AND committed_expires_time IS NULL
            AND terminal_time IS NULL
        ) OR (
            stage_batch_status = 'committed'
            AND committed_revision > expected_draft_revision
            AND committed_expires_time IS NOT NULL
            AND terminal_time IS NOT NULL
        ) OR (
            stage_batch_status = 'expired'
            AND committed_revision IS NULL
            AND committed_expires_time IS NULL
            AND terminal_time IS NOT NULL
        )
    )
);

CREATE TABLE mcp.model_stage_chunk (
    stage_batch_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    record_count INTEGER NOT NULL,
    chunk_sha256 CHAR(64) NOT NULL,
    records_document JSONB NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_model_stage_chunk PRIMARY KEY (
        stage_batch_id,
        chunk_index
    ),
    CONSTRAINT fk_model_stage_chunk_batch FOREIGN KEY (stage_batch_id)
        REFERENCES mcp.model_stage_batch (stage_batch_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_model_stage_chunk_index CHECK (
        chunk_index BETWEEN 1 AND 64
    ),
    CONSTRAINT ck_model_stage_chunk_content CHECK (
        record_count >= 1
        AND chunk_sha256 ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(records_document) = 'array'
        AND jsonb_array_length(records_document) = record_count
        AND octet_length(records_document::TEXT) <= 524288
    )
);

CREATE TABLE mcp.model_change_set_event (
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
    ) REFERENCES mcp.model_change_set (model_change_set_id, model_id)
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

CREATE TABLE mcp.metadata_change_set (
    metadata_change_set_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    metadata_change_set_status VARCHAR(20) NOT NULL DEFAULT 'active',
    draft_revision BIGINT NOT NULL DEFAULT 1,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    source_object_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    source_attribute_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    bronze_object_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    bronze_attribute_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    silver_object_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    silver_attribute_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    gold_object_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    gold_attribute_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    ingestion_object_mapping_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    ingestion_attribute_mapping_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    copy_group_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    member_group_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    copy_group_control_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    copy_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    process_group_document JSONB NOT NULL DEFAULT '[]'::JSONB,
    process_document JSONB NOT NULL DEFAULT '[]'::JSONB,
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
            'expired', 'archived', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_revision CHECK (draft_revision >= 1),
    CONSTRAINT ck_metadata_change_set_candidate_digest CHECK (
        candidate_digest IS NULL OR candidate_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_metadata_change_set_validation_outcome CHECK (
        validation_outcome IS NULL
        OR jsonb_typeof(validation_outcome) = 'object'
    ),
    CONSTRAINT ck_metadata_change_set_documents CHECK (
        jsonb_typeof(source_object_document) = 'array'
        AND jsonb_typeof(source_attribute_document) = 'array'
        AND jsonb_typeof(bronze_object_document) = 'array'
        AND jsonb_typeof(bronze_attribute_document) = 'array'
        AND jsonb_typeof(silver_object_document) = 'array'
        AND jsonb_typeof(silver_attribute_document) = 'array'
        AND jsonb_typeof(gold_object_document) = 'array'
        AND jsonb_typeof(gold_attribute_document) = 'array'
        AND jsonb_typeof(ingestion_object_mapping_document) = 'array'
        AND jsonb_typeof(ingestion_attribute_mapping_document) = 'array'
        AND jsonb_typeof(copy_group_document) = 'array'
        AND jsonb_typeof(member_group_document) = 'array'
        AND jsonb_typeof(copy_group_control_document) = 'array'
        AND jsonb_typeof(copy_document) = 'array'
        AND jsonb_typeof(process_group_document) = 'array'
        AND jsonb_typeof(process_document) = 'array'
        AND octet_length(source_object_document::TEXT) <= 16777216
        AND octet_length(source_attribute_document::TEXT) <= 16777216
        AND octet_length(bronze_object_document::TEXT) <= 16777216
        AND octet_length(bronze_attribute_document::TEXT) <= 16777216
        AND octet_length(silver_object_document::TEXT) <= 16777216
        AND octet_length(silver_attribute_document::TEXT) <= 16777216
        AND octet_length(gold_object_document::TEXT) <= 16777216
        AND octet_length(gold_attribute_document::TEXT) <= 16777216
        AND octet_length(ingestion_object_mapping_document::TEXT) <= 16777216
        AND octet_length(ingestion_attribute_mapping_document::TEXT) <= 16777216
        AND octet_length(copy_group_document::TEXT) <= 16777216
        AND octet_length(member_group_document::TEXT) <= 16777216
        AND octet_length(copy_group_control_document::TEXT) <= 16777216
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
            'expired', 'archived', 'superseded'
        )
    ),
    CONSTRAINT ck_metadata_change_set_terminal_time CHECK (
        (
            metadata_change_set_status IN (
                'applied', 'expired', 'archived', 'superseded'
            )
        ) = (terminal_time IS NOT NULL)
    )
);

CREATE TABLE mcp.metadata_stage_batch (
    stage_batch_id UUID PRIMARY KEY,
    metadata_change_set_id UUID NOT NULL,
    tenant_id BIGINT NOT NULL,
    dataset_name VARCHAR(40) NOT NULL,
    expected_draft_revision BIGINT NOT NULL,
    total_record_count INTEGER NOT NULL,
    total_chunk_count INTEGER NOT NULL,
    batch_sha256 CHAR(64) NOT NULL,
    stage_batch_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_by_principal_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_time TIMESTAMPTZ NOT NULL DEFAULT (
        CURRENT_TIMESTAMP + INTERVAL '4 hours'
    ),
    committed_revision BIGINT,
    committed_expires_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ,
    CONSTRAINT fk_metadata_stage_batch_change_set FOREIGN KEY (
        metadata_change_set_id,
        tenant_id
    ) REFERENCES mcp.metadata_change_set (
        metadata_change_set_id,
        tenant_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_stage_batch_creator FOREIGN KEY (
        created_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_stage_batch_id_tenant
        UNIQUE (stage_batch_id, tenant_id),
    CONSTRAINT ck_metadata_stage_batch_dataset CHECK (
        dataset_name IN (
            'source_object', 'source_attribute',
            'bronze_object', 'bronze_attribute',
            'silver_object', 'silver_attribute',
            'gold_object', 'gold_attribute',
            'ingestion_object_mapping', 'ingestion_attribute_mapping',
            'copy_group', 'member_group', 'copy_group_control', 'copy',
            'process_group', 'process'
        )
    ),
    CONSTRAINT ck_metadata_stage_batch_manifest CHECK (
        expected_draft_revision >= 1
        AND total_record_count BETWEEN 1 AND 50000
        AND total_chunk_count BETWEEN 1 AND 64
        AND batch_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_metadata_stage_batch_status CHECK (
        stage_batch_status IN ('active', 'committed', 'expired')
    ),
    CONSTRAINT ck_metadata_stage_batch_expiry CHECK (
        last_activity_time >= created_time
        AND expires_time > last_activity_time
    ),
    CONSTRAINT ck_metadata_stage_batch_terminal_state CHECK (
        (
            stage_batch_status = 'active'
            AND committed_revision IS NULL
            AND committed_expires_time IS NULL
            AND terminal_time IS NULL
        ) OR (
            stage_batch_status = 'committed'
            AND committed_revision > expected_draft_revision
            AND committed_expires_time IS NOT NULL
            AND terminal_time IS NOT NULL
        ) OR (
            stage_batch_status = 'expired'
            AND committed_revision IS NULL
            AND committed_expires_time IS NULL
            AND terminal_time IS NOT NULL
        )
    )
);

CREATE TABLE mcp.metadata_stage_chunk (
    stage_batch_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    record_count INTEGER NOT NULL,
    chunk_sha256 CHAR(64) NOT NULL,
    records_document JSONB NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_metadata_stage_chunk PRIMARY KEY (
        stage_batch_id,
        chunk_index
    ),
    CONSTRAINT fk_metadata_stage_chunk_batch FOREIGN KEY (stage_batch_id)
        REFERENCES mcp.metadata_stage_batch (stage_batch_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_metadata_stage_chunk_index CHECK (
        chunk_index BETWEEN 1 AND 64
    ),
    CONSTRAINT ck_metadata_stage_chunk_content CHECK (
        record_count >= 1
        AND chunk_sha256 ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(records_document) = 'array'
        AND jsonb_array_length(records_document) = record_count
        AND octet_length(records_document::TEXT) <= 524288
    )
);

CREATE TABLE mcp.metadata_change_set_event (
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
    ) REFERENCES mcp.metadata_change_set (
        metadata_change_set_id,
        tenant_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_metadata_change_set_event_sequence
        UNIQUE (metadata_change_set_id, event_sequence),
    CONSTRAINT ck_metadata_change_set_event_sequence CHECK (event_sequence > 0),
    CONSTRAINT ck_metadata_change_set_event_type CHECK (
        event_type IN (
            'created', 'section_put', 'validated', 'validation_failed',
            'applied', 'expired', 'archived', 'superseded'
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
            'ingestion_object_mapping', 'ingestion_attribute_mapping',
            'copy_group', 'member_group', 'copy_group_control', 'copy',
            'process_group', 'process'
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

CREATE FUNCTION mcp.create_metadata_change_set(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_new_metadata_change_set_id UUID,
    p_correlation_id UUID
)
RETURNS TABLE (
    created BOOLEAN,
    denial_code VARCHAR(50),
    metadata_change_set_id UUID,
    metadata_change_set_status VARCHAR(20),
    draft_revision BIGINT,
    created_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $create_metadata_change_set$
DECLARE
    v_decision RECORD;
    v_existing RECORD;
    v_created RECORD;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_new_metadata_change_set_id IS NULL
       OR p_correlation_id IS NULL THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::UUID,
            NULL::VARCHAR(20), NULL::BIGINT, NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    PERFORM 1
      FROM core.tenant AS tenant
     WHERE tenant.tenant_id = p_tenant_id
       AND tenant.is_active
     FOR UPDATE;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::UUID,
            NULL::VARCHAR(20),
            NULL::BIGINT,
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_id,
           change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.created_time,
           change_set.expires_time
      INTO v_existing
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
       AND change_set.metadata_change_set_status IN ('active', 'validated')
     FOR UPDATE;
    v_now := clock_timestamp();
    IF FOUND THEN
        IF v_existing.expires_time <= v_now THEN
            UPDATE mcp.metadata_change_set AS change_set
               SET metadata_change_set_status = 'expired',
                   terminal_time = v_now
             WHERE change_set.metadata_change_set_id =
                   v_existing.metadata_change_set_id;
            UPDATE mcp.metadata_stage_batch AS batch
               SET stage_batch_status = 'expired',
                   terminal_time = v_now
             WHERE batch.metadata_change_set_id =
                   v_existing.metadata_change_set_id
               AND batch.stage_batch_status = 'active';

            SELECT coalesce(max(event.event_sequence), 0) + 1
              INTO v_event_sequence
              FROM mcp.metadata_change_set_event AS event
             WHERE event.metadata_change_set_id =
                   v_existing.metadata_change_set_id;
            INSERT INTO mcp.metadata_change_set_event (
                metadata_change_set_id,
                tenant_id,
                event_sequence,
                event_type,
                draft_revision,
                action_count,
                outcome,
                correlation_id
            ) VALUES (
                v_existing.metadata_change_set_id,
                p_tenant_id,
                v_event_sequence,
                'expired',
                v_existing.draft_revision,
                0,
                'expired',
                p_correlation_id
            );
        ELSE
            RETURN QUERY SELECT
                FALSE,
                'metadata_change_set_exists'::VARCHAR(50),
                v_existing.metadata_change_set_id::UUID,
                v_existing.metadata_change_set_status::VARCHAR(20),
                v_existing.draft_revision::BIGINT,
                v_existing.created_time::TIMESTAMPTZ,
                v_existing.expires_time::TIMESTAMPTZ;
            RETURN;
        END IF;
    END IF;

    INSERT INTO mcp.metadata_change_set AS created_change_set (
        metadata_change_set_id,
        tenant_id,
        created_by_principal_id,
        correlation_id,
        created_time,
        last_activity_time,
        expires_time
    ) VALUES (
        p_new_metadata_change_set_id,
        p_tenant_id,
        v_decision.principal_id,
        p_correlation_id,
        v_now,
        v_now,
        v_now + INTERVAL '4 hours'
    )
    RETURNING created_change_set.metadata_change_set_id,
              created_change_set.metadata_change_set_status,
              created_change_set.draft_revision,
              created_change_set.created_time,
              created_change_set.expires_time
         INTO v_created;

    INSERT INTO mcp.metadata_change_set_event (
        metadata_change_set_id,
        tenant_id,
        event_sequence,
        event_type,
        draft_revision,
        action_count,
        outcome,
        correlation_id
    ) VALUES (
        v_created.metadata_change_set_id,
        p_tenant_id,
        1,
        'created',
        v_created.draft_revision,
        0,
        'created',
        p_correlation_id
    );

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_created.metadata_change_set_id::UUID,
        v_created.metadata_change_set_status::VARCHAR(20),
        v_created.draft_revision::BIGINT,
        v_created.created_time::TIMESTAMPTZ,
        v_created.expires_time::TIMESTAMPTZ;
END;
$create_metadata_change_set$;

CREATE FUNCTION mcp.stage_metadata_change_set(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_expected_draft_revision BIGINT,
    p_documents JSONB,
    p_correlation_id UUID
)
RETURNS TABLE (
    staged BOOLEAN,
    denial_code VARCHAR(50),
    draft_revision BIGINT,
    dataset_counts JSONB,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $stage_metadata_change_set$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_new_revision BIGINT;
    v_expires_time TIMESTAMPTZ;
    v_dataset_counts JSONB;
    v_record_count INTEGER;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL
       OR p_expected_draft_revision IS NULL
       OR p_expected_draft_revision < 1
       OR p_documents IS NULL
       OR jsonb_typeof(p_documents) <> 'object'
       OR p_documents = '{}'::JSONB
       OR octet_length(p_documents::TEXT) > 16777216
       OR p_correlation_id IS NULL
       OR EXISTS (
           SELECT 1
             FROM jsonb_each(p_documents) AS document(name, records)
            WHERE document.name NOT IN (
                'source_object', 'source_attribute',
                'bronze_object', 'bronze_attribute',
                'silver_object', 'silver_attribute',
                'gold_object', 'gold_attribute',
                'ingestion_object_mapping', 'ingestion_attribute_mapping',
                'copy_group', 'member_group', 'copy_group_control', 'copy',
                'process_group', 'process'
            )
               OR jsonb_typeof(document.records) <> 'array'
               OR jsonb_array_length(document.records) > 50000
       ) THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::BIGINT,
            NULL::JSONB, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::BIGINT, NULL::JSONB, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.expires_time
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50), NULL::BIGINT,
            NULL::JSONB, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_now := clock_timestamp();
    IF v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired', p_correlation_id
        );
        v_change_set.metadata_change_set_status := 'expired';
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50),
            v_change_set.draft_revision::BIGINT, NULL::JSONB,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision IS DISTINCT FROM p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50),
            v_change_set.draft_revision::BIGINT, NULL::JSONB,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_change_set AS change_set
       SET source_object_document = CASE WHEN p_documents ? 'source_object'
               THEN p_documents -> 'source_object' ELSE change_set.source_object_document END,
           source_attribute_document = CASE WHEN p_documents ? 'source_attribute'
               THEN p_documents -> 'source_attribute' ELSE change_set.source_attribute_document END,
           bronze_object_document = CASE WHEN p_documents ? 'bronze_object'
               THEN p_documents -> 'bronze_object' ELSE change_set.bronze_object_document END,
           bronze_attribute_document = CASE WHEN p_documents ? 'bronze_attribute'
               THEN p_documents -> 'bronze_attribute' ELSE change_set.bronze_attribute_document END,
           silver_object_document = CASE WHEN p_documents ? 'silver_object'
               THEN p_documents -> 'silver_object' ELSE change_set.silver_object_document END,
           silver_attribute_document = CASE WHEN p_documents ? 'silver_attribute'
               THEN p_documents -> 'silver_attribute' ELSE change_set.silver_attribute_document END,
           gold_object_document = CASE WHEN p_documents ? 'gold_object'
               THEN p_documents -> 'gold_object' ELSE change_set.gold_object_document END,
           gold_attribute_document = CASE WHEN p_documents ? 'gold_attribute'
               THEN p_documents -> 'gold_attribute' ELSE change_set.gold_attribute_document END,
           ingestion_object_mapping_document = CASE
               WHEN p_documents ? 'ingestion_object_mapping'
               THEN p_documents -> 'ingestion_object_mapping'
               ELSE change_set.ingestion_object_mapping_document END,
           ingestion_attribute_mapping_document = CASE
               WHEN p_documents ? 'ingestion_attribute_mapping'
               THEN p_documents -> 'ingestion_attribute_mapping'
               ELSE change_set.ingestion_attribute_mapping_document END,
           copy_group_document = CASE WHEN p_documents ? 'copy_group'
               THEN p_documents -> 'copy_group' ELSE change_set.copy_group_document END,
           member_group_document = CASE WHEN p_documents ? 'member_group'
               THEN p_documents -> 'member_group' ELSE change_set.member_group_document END,
           copy_group_control_document = CASE WHEN p_documents ? 'copy_group_control'
               THEN p_documents -> 'copy_group_control'
               ELSE change_set.copy_group_control_document END,
           copy_document = CASE WHEN p_documents ? 'copy'
               THEN p_documents -> 'copy' ELSE change_set.copy_document END,
           process_group_document = CASE WHEN p_documents ? 'process_group'
               THEN p_documents -> 'process_group' ELSE change_set.process_group_document END,
           process_document = CASE WHEN p_documents ? 'process'
               THEN p_documents -> 'process' ELSE change_set.process_document END,
           metadata_change_set_status = 'active',
           draft_revision = change_set.draft_revision + 1,
           candidate_digest = NULL,
           validation_outcome = NULL,
           validated_time = NULL,
           last_activity_time = v_now,
           expires_time = v_now + INTERVAL '4 hours'
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
    RETURNING change_set.draft_revision, change_set.expires_time
         INTO v_new_revision, v_expires_time;

    SELECT jsonb_object_agg(document.name, jsonb_array_length(document.records)),
           sum(jsonb_array_length(document.records))::INTEGER
      INTO v_dataset_counts, v_record_count
      FROM jsonb_each(p_documents) AS document(name, records);
    SELECT coalesce(max(event.event_sequence), 0) + 1
      INTO v_event_sequence
      FROM mcp.metadata_change_set_event AS event
     WHERE event.metadata_change_set_id = p_metadata_change_set_id;
    INSERT INTO mcp.metadata_change_set_event (
        metadata_change_set_id, tenant_id, event_sequence, event_type,
        draft_revision, action_count, outcome, event_metadata, correlation_id
    ) VALUES (
        p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'section_put',
        v_new_revision, v_record_count, 'accepted',
        jsonb_build_object('dataset_counts', v_dataset_counts), p_correlation_id
    );

    RETURN QUERY SELECT
        TRUE, NULL::VARCHAR(50), v_new_revision, v_dataset_counts, v_expires_time;
END;
$stage_metadata_change_set$;

CREATE FUNCTION mcp.begin_metadata_stage_batch(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_expected_draft_revision BIGINT,
    p_new_stage_batch_id UUID,
    p_dataset_name VARCHAR(40),
    p_total_record_count INTEGER,
    p_total_chunk_count INTEGER,
    p_batch_sha256 CHAR(64),
    p_correlation_id UUID
)
RETURNS TABLE (
    started BOOLEAN,
    denial_code VARCHAR(50),
    stage_batch_id UUID,
    created BOOLEAN,
    dataset_name VARCHAR(40),
    total_record_count INTEGER,
    total_chunk_count INTEGER,
    received_chunk_count INTEGER,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $begin_metadata_stage_batch$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_existing RECORD;
    v_expires_time TIMESTAMPTZ;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL
       OR p_expected_draft_revision IS NULL
       OR p_expected_draft_revision < 1
       OR p_new_stage_batch_id IS NULL
       OR p_dataset_name IS NULL
       OR p_dataset_name NOT IN (
           'source_object', 'source_attribute',
           'bronze_object', 'bronze_attribute',
           'silver_object', 'silver_attribute',
           'gold_object', 'gold_attribute',
           'ingestion_object_mapping', 'ingestion_attribute_mapping',
           'copy_group', 'member_group', 'copy_group_control', 'copy',
           'process_group', 'process'
       )
       OR p_total_record_count IS NULL
       OR p_total_record_count NOT BETWEEN 1 AND 50000
       OR p_total_chunk_count IS NULL
       OR p_total_chunk_count NOT BETWEEN 1 AND 64
       OR p_batch_sha256 IS NULL
       OR p_batch_sha256 !~ '^[0-9a-f]{64}$'
       OR p_correlation_id IS NULL THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::UUID, FALSE,
            NULL::VARCHAR(40), NULL::INTEGER, NULL::INTEGER, NULL::INTEGER,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::UUID, FALSE, NULL::VARCHAR(40), NULL::INTEGER,
            NULL::INTEGER, NULL::INTEGER, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.expires_time
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50), NULL::UUID,
            FALSE, NULL::VARCHAR(40), NULL::INTEGER, NULL::INTEGER,
            NULL::INTEGER, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_now := clock_timestamp();
    IF v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired', p_correlation_id
        );
        v_change_set.metadata_change_set_status := 'expired';
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50), NULL::UUID,
            FALSE, NULL::VARCHAR(40), NULL::INTEGER, NULL::INTEGER,
            NULL::INTEGER, v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision IS DISTINCT FROM p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50), NULL::UUID,
            FALSE, NULL::VARCHAR(40), NULL::INTEGER, NULL::INTEGER,
            NULL::INTEGER, v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_stage_batch AS batch
       SET stage_batch_status = 'expired',
           terminal_time = v_now
     WHERE batch.metadata_change_set_id = p_metadata_change_set_id
       AND batch.dataset_name = p_dataset_name
       AND batch.stage_batch_status = 'active'
       AND batch.expires_time <= v_now;

    SELECT batch.stage_batch_id,
           batch.expected_draft_revision,
           batch.total_record_count,
           batch.total_chunk_count,
           batch.batch_sha256,
           batch.expires_time,
           (
               SELECT count(*)::INTEGER
                 FROM mcp.metadata_stage_chunk AS chunk
                WHERE chunk.stage_batch_id = batch.stage_batch_id
           ) AS received_chunk_count
      INTO v_existing
      FROM mcp.metadata_stage_batch AS batch
     WHERE batch.metadata_change_set_id = p_metadata_change_set_id
       AND batch.dataset_name = p_dataset_name
       AND batch.stage_batch_status = 'active'
     FOR UPDATE;
    IF FOUND THEN
        IF v_existing.expected_draft_revision IS NOT DISTINCT FROM
               p_expected_draft_revision
           AND v_existing.total_record_count = p_total_record_count
           AND v_existing.total_chunk_count = p_total_chunk_count
           AND v_existing.batch_sha256 = p_batch_sha256 THEN
            RETURN QUERY SELECT
                TRUE, NULL::VARCHAR(50), v_existing.stage_batch_id::UUID,
                FALSE, p_dataset_name::VARCHAR(40), p_total_record_count,
                p_total_chunk_count, v_existing.received_chunk_count::INTEGER,
                v_existing.expires_time::TIMESTAMPTZ;
        ELSE
            RETURN QUERY SELECT
                FALSE, 'stage_batch_conflict'::VARCHAR(50),
                v_existing.stage_batch_id::UUID, FALSE,
                p_dataset_name::VARCHAR(40),
                v_existing.total_record_count::INTEGER,
                v_existing.total_chunk_count::INTEGER,
                v_existing.received_chunk_count::INTEGER,
                v_existing.expires_time::TIMESTAMPTZ;
        END IF;
        RETURN;
    END IF;

    v_expires_time := least(
        v_change_set.expires_time,
        v_now + INTERVAL '4 hours'
    );
    INSERT INTO mcp.metadata_stage_batch (
        stage_batch_id,
        metadata_change_set_id,
        tenant_id,
        dataset_name,
        expected_draft_revision,
        total_record_count,
        total_chunk_count,
        batch_sha256,
        created_by_principal_id,
        correlation_id,
        created_time,
        last_activity_time,
        expires_time
    ) VALUES (
        p_new_stage_batch_id,
        p_metadata_change_set_id,
        p_tenant_id,
        p_dataset_name,
        p_expected_draft_revision,
        p_total_record_count,
        p_total_chunk_count,
        p_batch_sha256,
        v_decision.principal_id,
        p_correlation_id,
        v_now,
        v_now,
        v_expires_time
    );

    RETURN QUERY SELECT
        TRUE, NULL::VARCHAR(50), p_new_stage_batch_id,
        TRUE, p_dataset_name::VARCHAR(40), p_total_record_count,
        p_total_chunk_count, 0, v_expires_time;
END;
$begin_metadata_stage_batch$;

CREATE FUNCTION mcp.put_metadata_stage_chunk(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_stage_batch_id UUID,
    p_dataset_name VARCHAR(40),
    p_chunk_index INTEGER,
    p_chunk_sha256 CHAR(64),
    p_records JSONB
)
RETURNS TABLE (
    accepted BOOLEAN,
    denial_code VARCHAR(50),
    duplicate BOOLEAN,
    received_chunk_count INTEGER,
    total_chunk_count INTEGER,
    record_count INTEGER,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $put_metadata_stage_chunk$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_batch RECORD;
    v_existing RECORD;
    v_received_chunk_count INTEGER;
    v_received_record_count INTEGER;
    v_record_count INTEGER;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL
       OR p_stage_batch_id IS NULL
       OR p_dataset_name IS NULL
       OR p_chunk_index IS NULL
       OR p_chunk_index NOT BETWEEN 1 AND 64
       OR p_chunk_sha256 IS NULL
       OR p_chunk_sha256 !~ '^[0-9a-f]{64}$'
       OR p_records IS NULL
       OR jsonb_typeof(p_records) <> 'array'
       OR jsonb_array_length(p_records) < 1
       OR octet_length(p_records::TEXT) > 524288 THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), FALSE,
            NULL::INTEGER, NULL::INTEGER, NULL::INTEGER, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_record_count := jsonb_array_length(p_records);

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            FALSE, NULL::INTEGER, NULL::INTEGER, NULL::INTEGER,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.expires_time,
           change_set.correlation_id
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50), FALSE,
            NULL::INTEGER, NULL::INTEGER, NULL::INTEGER, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_now := clock_timestamp();
    IF v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired',
            v_change_set.correlation_id
        );
        v_change_set.metadata_change_set_status := 'expired';
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50), FALSE,
            NULL::INTEGER, NULL::INTEGER, NULL::INTEGER,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_batch
      FROM mcp.metadata_stage_batch AS batch
     WHERE batch.stage_batch_id = p_stage_batch_id
       AND batch.metadata_change_set_id = p_metadata_change_set_id
       AND batch.tenant_id = p_tenant_id
       AND batch.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'stage_batch_not_found'::VARCHAR(50), FALSE,
            NULL::INTEGER, NULL::INTEGER, NULL::INTEGER, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_batch.stage_batch_status <> 'active'
       OR v_batch.expires_time <= v_now THEN
        IF v_batch.stage_batch_status = 'active' THEN
            UPDATE mcp.metadata_stage_batch
               SET stage_batch_status = 'expired',
                   terminal_time = v_now
             WHERE stage_batch_id = p_stage_batch_id;
        END IF;
        RETURN QUERY SELECT
            FALSE, 'stage_batch_not_active'::VARCHAR(50), FALSE,
            NULL::INTEGER, v_batch.total_chunk_count::INTEGER,
            NULL::INTEGER, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision IS DISTINCT FROM
           v_batch.expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50), FALSE,
            NULL::INTEGER, v_batch.total_chunk_count::INTEGER,
            NULL::INTEGER, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_batch.dataset_name IS DISTINCT FROM p_dataset_name
       OR p_chunk_index > v_batch.total_chunk_count THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), FALSE,
            NULL::INTEGER, v_batch.total_chunk_count::INTEGER,
            NULL::INTEGER, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT chunk.chunk_sha256,
           chunk.records_document,
           chunk.record_count
      INTO v_existing
      FROM mcp.metadata_stage_chunk AS chunk
     WHERE chunk.stage_batch_id = p_stage_batch_id
       AND chunk.chunk_index = p_chunk_index;
    IF FOUND THEN
        IF v_existing.chunk_sha256 = p_chunk_sha256
           AND v_existing.records_document = p_records THEN
            SELECT count(*)::INTEGER
              INTO v_received_chunk_count
              FROM mcp.metadata_stage_chunk
             WHERE stage_batch_id = p_stage_batch_id;
            RETURN QUERY SELECT
                TRUE, NULL::VARCHAR(50), TRUE,
                v_received_chunk_count, v_batch.total_chunk_count::INTEGER,
                v_existing.record_count::INTEGER,
                v_batch.expires_time::TIMESTAMPTZ;
        ELSE
            RETURN QUERY SELECT
                FALSE, 'stage_chunk_conflict'::VARCHAR(50), FALSE,
                NULL::INTEGER, v_batch.total_chunk_count::INTEGER,
                NULL::INTEGER, v_batch.expires_time::TIMESTAMPTZ;
        END IF;
        RETURN;
    END IF;

    SELECT coalesce(sum(chunk.record_count), 0)::INTEGER
      INTO v_received_record_count
      FROM mcp.metadata_stage_chunk AS chunk
     WHERE chunk.stage_batch_id = p_stage_batch_id;
    IF v_received_record_count + v_record_count > v_batch.total_record_count THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), FALSE,
            NULL::INTEGER, v_batch.total_chunk_count::INTEGER,
            NULL::INTEGER, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    INSERT INTO mcp.metadata_stage_chunk (
        stage_batch_id,
        chunk_index,
        record_count,
        chunk_sha256,
        records_document
    ) VALUES (
        p_stage_batch_id,
        p_chunk_index,
        v_record_count,
        p_chunk_sha256,
        p_records
    );
    UPDATE mcp.metadata_stage_batch
       SET last_activity_time = v_now
     WHERE stage_batch_id = p_stage_batch_id;
    SELECT count(*)::INTEGER
      INTO v_received_chunk_count
      FROM mcp.metadata_stage_chunk
     WHERE stage_batch_id = p_stage_batch_id;

    RETURN QUERY SELECT
        TRUE, NULL::VARCHAR(50), FALSE, v_received_chunk_count,
        v_batch.total_chunk_count::INTEGER, v_record_count,
        v_batch.expires_time::TIMESTAMPTZ;
END;
$put_metadata_stage_chunk$;

CREATE FUNCTION mcp.commit_metadata_stage_batch(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_stage_batch_id UUID,
    p_expected_draft_revision BIGINT,
    p_correlation_id UUID
)
RETURNS TABLE (
    committed BOOLEAN,
    denial_code VARCHAR(50),
    replayed BOOLEAN,
    dataset_name VARCHAR(40),
    record_count INTEGER,
    draft_revision BIGINT,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $commit_metadata_stage_batch$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_batch RECORD;
    v_chunk_count INTEGER;
    v_record_count INTEGER;
    v_batch_sha256 TEXT;
    v_document JSONB;
    v_staged RECORD;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL
       OR p_stage_batch_id IS NULL
       OR p_expected_draft_revision IS NULL
       OR p_expected_draft_revision < 1
       OR p_correlation_id IS NULL THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), FALSE,
            NULL::VARCHAR(40), NULL::INTEGER, NULL::BIGINT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            FALSE, NULL::VARCHAR(40), NULL::INTEGER, NULL::BIGINT,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.expires_time
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50), FALSE,
            NULL::VARCHAR(40), NULL::INTEGER, NULL::BIGINT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_now := clock_timestamp();
    IF v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired', p_correlation_id
        );
        v_change_set.metadata_change_set_status := 'expired';
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50), FALSE,
            NULL::VARCHAR(40), NULL::INTEGER,
            v_change_set.draft_revision::BIGINT,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_batch
      FROM mcp.metadata_stage_batch AS batch
     WHERE batch.stage_batch_id = p_stage_batch_id
       AND batch.metadata_change_set_id = p_metadata_change_set_id
       AND batch.tenant_id = p_tenant_id
       AND batch.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'stage_batch_not_found'::VARCHAR(50), FALSE,
            NULL::VARCHAR(40), NULL::INTEGER, NULL::BIGINT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_batch.expected_draft_revision IS DISTINCT FROM
           p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), FALSE,
            v_batch.dataset_name::VARCHAR(40), NULL::INTEGER,
            NULL::BIGINT, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_batch.stage_batch_status = 'committed' THEN
        RETURN QUERY SELECT
            TRUE, NULL::VARCHAR(50), TRUE,
            v_batch.dataset_name::VARCHAR(40),
            v_batch.total_record_count::INTEGER,
            v_batch.committed_revision::BIGINT,
            v_batch.committed_expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_batch.stage_batch_status <> 'active'
       OR v_batch.expires_time <= v_now THEN
        IF v_batch.stage_batch_status = 'active' THEN
            UPDATE mcp.metadata_stage_batch
               SET stage_batch_status = 'expired',
                   terminal_time = v_now
             WHERE stage_batch_id = p_stage_batch_id;
        END IF;
        RETURN QUERY SELECT
            FALSE, 'stage_batch_not_active'::VARCHAR(50), FALSE,
            v_batch.dataset_name::VARCHAR(40), NULL::INTEGER,
            NULL::BIGINT, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision IS DISTINCT FROM p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50), FALSE,
            v_batch.dataset_name::VARCHAR(40), NULL::INTEGER,
            v_change_set.draft_revision::BIGINT,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT count(*)::INTEGER,
           coalesce(sum(chunk.record_count), 0)::INTEGER,
           encode(
               sha256(
                   convert_to(
                       coalesce(
                           string_agg(
                               trim(chunk.chunk_sha256)::TEXT,
                               '' ORDER BY chunk.chunk_index
                           ),
                           ''
                       ),
                       'UTF8'
                   )
               ),
               'hex'
           )
      INTO v_chunk_count, v_record_count, v_batch_sha256
      FROM mcp.metadata_stage_chunk AS chunk
     WHERE chunk.stage_batch_id = p_stage_batch_id;
    IF v_chunk_count <> v_batch.total_chunk_count
       OR v_record_count <> v_batch.total_record_count
       OR v_batch_sha256 <> v_batch.batch_sha256 THEN
        RETURN QUERY SELECT
            FALSE, 'stage_batch_incomplete'::VARCHAR(50), FALSE,
            v_batch.dataset_name::VARCHAR(40), v_record_count,
            NULL::BIGINT, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT coalesce(
               jsonb_agg(
                   record.value ORDER BY chunk.chunk_index, record.ordinality
               ),
               '[]'::JSONB
           )
      INTO v_document
      FROM mcp.metadata_stage_chunk AS chunk
      CROSS JOIN LATERAL jsonb_array_elements(chunk.records_document)
          WITH ORDINALITY AS record(value, ordinality)
     WHERE chunk.stage_batch_id = p_stage_batch_id;
    IF jsonb_array_length(v_document) <> v_batch.total_record_count
       OR octet_length(v_document::TEXT) > 16777216 THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), FALSE,
            v_batch.dataset_name::VARCHAR(40), v_record_count,
            NULL::BIGINT, v_batch.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_staged
      FROM mcp.stage_metadata_change_set(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          p_metadata_change_set_id,
          p_expected_draft_revision,
          jsonb_build_object(v_batch.dataset_name, v_document),
          p_correlation_id
      );
    IF NOT v_staged.staged THEN
        RETURN QUERY SELECT
            FALSE, v_staged.denial_code::VARCHAR(50), FALSE,
            v_batch.dataset_name::VARCHAR(40), v_record_count,
            v_staged.draft_revision::BIGINT,
            v_staged.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_stage_batch
       SET stage_batch_status = 'committed',
           last_activity_time = v_now,
           committed_revision = v_staged.draft_revision,
           committed_expires_time = v_staged.expires_time,
           terminal_time = v_now
     WHERE stage_batch_id = p_stage_batch_id;

    RETURN QUERY SELECT
        TRUE, NULL::VARCHAR(50), FALSE,
        v_batch.dataset_name::VARCHAR(40), v_record_count,
        v_staged.draft_revision::BIGINT, v_staged.expires_time::TIMESTAMPTZ;
END;
$commit_metadata_stage_batch$;

CREATE FUNCTION mcp.get_metadata_change_set(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID
)
RETURNS TABLE (
    found BOOLEAN,
    denial_code VARCHAR(50),
    metadata_change_set_status VARCHAR(20),
    draft_revision BIGINT,
    candidate_digest CHAR(64),
    validation_outcome JSONB,
    source_object_document JSONB,
    source_attribute_document JSONB,
    bronze_object_document JSONB,
    bronze_attribute_document JSONB,
    silver_object_document JSONB,
    silver_attribute_document JSONB,
    gold_object_document JSONB,
    gold_attribute_document JSONB,
    ingestion_object_mapping_document JSONB,
    ingestion_attribute_mapping_document JSONB,
    copy_group_document JSONB,
    member_group_document JSONB,
    copy_group_control_document JSONB,
    copy_document JSONB,
    process_group_document JSONB,
    process_document JSONB,
    created_time TIMESTAMPTZ,
    last_activity_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ,
    validated_time TIMESTAMPTZ,
    applied_time TIMESTAMPTZ,
    terminal_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $get_metadata_change_set$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::VARCHAR(20),
            NULL::BIGINT, NULL::CHAR(64), NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_lock_manage'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::VARCHAR(20),
            NULL::BIGINT,
            NULL::CHAR(64),
            NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.expires_time,
           change_set.correlation_id
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    v_now := clock_timestamp();
    IF FOUND
       AND v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired',
            v_change_set.correlation_id
        );
    END IF;

    RETURN QUERY
    SELECT TRUE,
           NULL::VARCHAR(50),
           change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.candidate_digest,
           change_set.validation_outcome,
           change_set.source_object_document,
           change_set.source_attribute_document,
           change_set.bronze_object_document,
           change_set.bronze_attribute_document,
           change_set.silver_object_document,
           change_set.silver_attribute_document,
           change_set.gold_object_document,
           change_set.gold_attribute_document,
           change_set.ingestion_object_mapping_document,
           change_set.ingestion_attribute_mapping_document,
           change_set.copy_group_document,
           change_set.member_group_document,
           change_set.copy_group_control_document,
           change_set.copy_document,
           change_set.process_group_document,
           change_set.process_document,
           change_set.created_time,
           change_set.last_activity_time,
           change_set.expires_time,
           change_set.validated_time,
           change_set.applied_time,
           change_set.terminal_time
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            'metadata_change_set_not_found'::VARCHAR(50),
            NULL::VARCHAR(20),
            NULL::BIGINT,
            NULL::CHAR(64),
            NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::JSONB, NULL::JSONB, NULL::JSONB, NULL::JSONB,
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ;
    END IF;
END;
$get_metadata_change_set$;

CREATE FUNCTION mcp.record_metadata_change_set_validation(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_expected_draft_revision BIGINT,
    p_validation_succeeded BOOLEAN,
    p_candidate_digest CHAR(64),
    p_validation_outcome JSONB,
    p_validation_report_id UUID,
    p_correlation_id UUID
)
RETURNS TABLE (
    recorded BOOLEAN,
    denial_code VARCHAR(50),
    metadata_change_set_status VARCHAR(20),
    draft_revision BIGINT,
    candidate_digest CHAR(64),
    validated_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $record_metadata_change_set_validation$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_updated RECORD;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL
       OR p_expected_draft_revision IS NULL
       OR p_expected_draft_revision < 1
       OR p_validation_succeeded IS NULL
       OR p_validation_outcome IS NULL
       OR jsonb_typeof(p_validation_outcome) <> 'object'
       OR octet_length(p_validation_outcome::TEXT) > 1048576
       OR (p_validation_succeeded AND (
           p_candidate_digest IS NULL
           OR p_candidate_digest !~ '^[0-9a-f]{64}$'
       ))
       OR (NOT p_validation_succeeded AND p_candidate_digest IS NOT NULL)
       OR p_correlation_id IS NULL THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::VARCHAR(20),
            NULL::BIGINT, NULL::CHAR(64), NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_metadata_write'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::VARCHAR(20), NULL::BIGINT, NULL::CHAR(64),
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.candidate_digest,
           change_set.validated_time,
           change_set.expires_time
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50),
            NULL::VARCHAR(20), NULL::BIGINT, NULL::CHAR(64),
            NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_now := clock_timestamp();
    IF v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired', p_correlation_id
        );
        v_change_set.metadata_change_set_status := 'expired';
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.candidate_digest::CHAR(64),
            v_change_set.validated_time::TIMESTAMPTZ,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision IS DISTINCT FROM p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.candidate_digest::CHAR(64),
            v_change_set.validated_time::TIMESTAMPTZ,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_change_set AS change_set
       SET metadata_change_set_status = CASE
               WHEN p_validation_succeeded THEN 'validated'
               ELSE 'active'
           END,
           candidate_digest = CASE
               WHEN p_validation_succeeded THEN p_candidate_digest
               ELSE NULL
           END,
           validation_outcome = p_validation_outcome,
           validated_time = CASE
               WHEN p_validation_succeeded THEN v_now
               ELSE NULL
           END,
           last_activity_time = v_now,
           expires_time = v_now + INTERVAL '4 hours'
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
    RETURNING change_set.metadata_change_set_status,
              change_set.draft_revision,
              change_set.candidate_digest,
              change_set.validated_time,
              change_set.expires_time
         INTO v_updated;

    SELECT coalesce(max(event.event_sequence), 0) + 1
      INTO v_event_sequence
      FROM mcp.metadata_change_set_event AS event
     WHERE event.metadata_change_set_id = p_metadata_change_set_id;
    INSERT INTO mcp.metadata_change_set_event (
        metadata_change_set_id,
        tenant_id,
        event_sequence,
        event_type,
        draft_revision,
        action_count,
        outcome,
        validation_report_id,
        correlation_id
    ) VALUES (
        p_metadata_change_set_id,
        p_tenant_id,
        v_event_sequence,
        CASE WHEN p_validation_succeeded THEN 'validated' ELSE 'validation_failed' END,
        v_updated.draft_revision,
        0,
        CASE WHEN p_validation_succeeded THEN 'valid' ELSE 'invalid' END,
        p_validation_report_id,
        p_correlation_id
    );

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_updated.metadata_change_set_status::VARCHAR(20),
        v_updated.draft_revision::BIGINT,
        v_updated.candidate_digest::CHAR(64),
        v_updated.validated_time::TIMESTAMPTZ,
        v_updated.expires_time::TIMESTAMPTZ;
END;
$record_metadata_change_set_validation$;

CREATE FUNCTION mcp.archive_metadata_change_set(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_metadata_change_set_id UUID,
    p_expected_draft_revision BIGINT,
    p_correlation_id UUID
)
RETURNS TABLE (
    archived BOOLEAN,
    denial_code VARCHAR(50),
    metadata_change_set_status VARCHAR(20),
    draft_revision BIGINT,
    terminal_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $archive_metadata_change_set$
DECLARE
    v_decision RECORD;
    v_change_set RECORD;
    v_terminal_time TIMESTAMPTZ;
    v_event_sequence BIGINT;
    v_now TIMESTAMPTZ;
BEGIN
    IF p_entra_tenant_id IS NULL
       OR p_entra_object_id IS NULL
       OR p_expected_principal_type IS NULL
       OR p_tenant_id IS NULL
       OR p_metadata_change_set_id IS NULL
       OR p_expected_draft_revision IS NULL
       OR p_expected_draft_revision < 1
       OR p_correlation_id IS NULL THEN
        RETURN QUERY SELECT
            FALSE, 'invalid_request'::VARCHAR(50), NULL::VARCHAR(20),
            NULL::BIGINT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_lock_manage'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(v_decision.denial_code, 'authorization_denied')::VARCHAR(50),
            NULL::VARCHAR(20), NULL::BIGINT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.terminal_time,
           change_set.expires_time
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_found'::VARCHAR(50),
            NULL::VARCHAR(20), NULL::BIGINT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    v_now := clock_timestamp();
    IF v_change_set.metadata_change_set_status IN ('active', 'validated')
       AND v_change_set.expires_time <= v_now THEN
        UPDATE mcp.metadata_change_set AS change_set
           SET metadata_change_set_status = 'expired',
               terminal_time = v_now
         WHERE change_set.metadata_change_set_id = p_metadata_change_set_id;
        UPDATE mcp.metadata_stage_batch AS batch
           SET stage_batch_status = 'expired',
               terminal_time = v_now
         WHERE batch.metadata_change_set_id = p_metadata_change_set_id
           AND batch.stage_batch_status = 'active';

        SELECT coalesce(max(event.event_sequence), 0) + 1
          INTO v_event_sequence
          FROM mcp.metadata_change_set_event AS event
         WHERE event.metadata_change_set_id = p_metadata_change_set_id;
        INSERT INTO mcp.metadata_change_set_event (
            metadata_change_set_id, tenant_id, event_sequence, event_type,
            draft_revision, action_count, outcome, correlation_id
        ) VALUES (
            p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'expired',
            v_change_set.draft_revision, 0, 'expired', p_correlation_id
        );
        v_change_set.metadata_change_set_status := 'expired';
        v_change_set.terminal_time := v_now;
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.terminal_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision IS DISTINCT FROM p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.terminal_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_change_set AS change_set
       SET metadata_change_set_status = 'archived',
           terminal_time = v_now,
           last_activity_time = v_now,
           expires_time = v_now + INTERVAL '4 hours'
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
    RETURNING change_set.terminal_time INTO v_terminal_time;

    SELECT coalesce(max(event.event_sequence), 0) + 1
      INTO v_event_sequence
      FROM mcp.metadata_change_set_event AS event
     WHERE event.metadata_change_set_id = p_metadata_change_set_id;
    INSERT INTO mcp.metadata_change_set_event (
        metadata_change_set_id, tenant_id, event_sequence, event_type,
        draft_revision, action_count, outcome, correlation_id
    ) VALUES (
        p_metadata_change_set_id, p_tenant_id, v_event_sequence, 'archived',
        v_change_set.draft_revision, 0, 'archived', p_correlation_id
    );

    RETURN QUERY SELECT
        TRUE, NULL::VARCHAR(50), 'archived'::VARCHAR(20),
        v_change_set.draft_revision::BIGINT, v_terminal_time;
END;
$archive_metadata_change_set$;

-- Exact secret-bearing lookup for the governed Databricks SQL tool. The
-- runtime role never receives table-wide access to core.connection_value.
CREATE FUNCTION mcp.get_databricks_sql_connection_values(
    p_connection_id BIGINT,
    p_environment_code TEXT
)
RETURNS TABLE (
    connection_tenant_id BIGINT,
    gds_connection_id BIGINT,
    environment_code VARCHAR(100),
    failure_code VARCHAR(50),
    databricks_host_name TEXT,
    databricks_http_path TEXT,
    databricks_token TEXT
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $get_databricks_sql_connection_values$
DECLARE
    v_tenant_id BIGINT;
    v_gds_connection_id BIGINT;
    v_environment_id BIGINT;
    v_environment_code VARCHAR(100);
    v_host_name TEXT;
    v_http_path TEXT;
    v_token TEXT;
BEGIN
    IF p_connection_id < 1 OR NULLIF(btrim(p_environment_code), '') IS NULL THEN
        RETURN QUERY SELECT
            NULL::BIGINT, NULL::BIGINT, NULL::VARCHAR(100),
            'invalid_request'::VARCHAR(50),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    SELECT source_connection.tenant_id,
           tenant_record.gds_connection_id
      INTO v_tenant_id, v_gds_connection_id
      FROM core.connection AS source_connection
      JOIN core.tenant AS tenant_record
        ON tenant_record.tenant_id = source_connection.tenant_id
       AND tenant_record.is_active
     WHERE source_connection.connection_id = p_connection_id
       AND source_connection.is_active
       AND NOT source_connection.is_global_data_store;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            NULL::BIGINT, NULL::BIGINT, NULL::VARCHAR(100),
            'connection_not_found'::VARCHAR(50),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    PERFORM 1
      FROM core.connection AS gds_connection
     WHERE gds_connection.connection_id = v_gds_connection_id
       AND gds_connection.is_active
       AND gds_connection.is_global_data_store;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_tenant_id, v_gds_connection_id, NULL::VARCHAR(100),
            'gds_connection_not_found'::VARCHAR(50),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    SELECT environment_record.environment_id,
           environment_record.environment_code
      INTO v_environment_id, v_environment_code
      FROM reference.environment AS environment_record
     WHERE environment_record.is_active
       AND lower(btrim(environment_record.environment_code)) =
           lower(btrim(p_environment_code));
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_tenant_id, v_gds_connection_id, NULL::VARCHAR(100),
            'environment_not_found'::VARCHAR(50),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    SELECT max(connection_value.connection_value) FILTER (
               WHERE lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_host_name'
           ),
           max(connection_value.connection_value) FILTER (
               WHERE lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_http_path'
           ),
           max(connection_value.connection_value) FILTER (
               WHERE lower(btrim(parameter.connection_parameter_code)) =
                     'databricks_token'
           )
      INTO v_host_name, v_http_path, v_token
      FROM core.connection_value AS connection_value
      JOIN reference.connection_parameter AS parameter
        ON parameter.connection_parameter_id =
           connection_value.connection_parameter_id
       AND parameter.is_active
     WHERE connection_value.connection_id = v_gds_connection_id
       AND connection_value.environment_id = v_environment_id
       AND lower(btrim(parameter.connection_parameter_code)) IN (
           'databricks_host_name',
           'databricks_http_path',
           'databricks_token'
       );

    IF v_host_name IS NULL OR v_http_path IS NULL OR v_token IS NULL THEN
        RETURN QUERY SELECT
            v_tenant_id, v_gds_connection_id, v_environment_code,
            'connection_values_missing'::VARCHAR(50),
            NULL::TEXT, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    RETURN QUERY SELECT
        v_tenant_id, v_gds_connection_id, v_environment_code,
        NULL::VARCHAR(50), v_host_name, v_http_path, v_token;
END;
$get_databricks_sql_connection_values$;

-- One immutable row per completed MCP tool call. input_metadata is server-created.
-- PostgreSQL imposes no application-specific byte ceiling on the JSON object.
CREATE TABLE mcp.tool_call_log (
    tool_call_id UUID PRIMARY KEY,
    principal_id BIGINT,
    principal_display_name VARCHAR(200) NOT NULL,
    actor_kind VARCHAR(20) NOT NULL,
    tool_name VARCHAR(200) NOT NULL,
    tool_policy VARCHAR(50) NOT NULL,
    tenant_id BIGINT,
    input_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    tool_call_status VARCHAR(20) NOT NULL,
    failure_code VARCHAR(100),
    tool_call_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mcp_tool_call_principal FOREIGN KEY (principal_id)
        REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mcp_tool_call_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT ck_mcp_tool_call_principal CHECK (
        (
            actor_kind = 'development'
            AND principal_id IS NULL
        )
        OR
        (
            actor_kind IN ('human', 'workload')
            AND principal_id IS NOT NULL
        )
    ),
    CONSTRAINT ck_mcp_tool_call_display_name CHECK (
        reference.is_nonblank(principal_display_name)
    ),
    CONSTRAINT ck_mcp_tool_call_name CHECK (
        reference.is_nonblank(tool_name)
    ),
    CONSTRAINT ck_mcp_tool_call_policy CHECK (
        tool_policy IN (
            'tenant_read',
            'tenant_metadata_write',
            'tenant_model_write',
            'tenant_lock_manage',
            'super_admin_only'
        )
    ),
    CONSTRAINT ck_mcp_tool_call_input_metadata CHECK (
        jsonb_typeof(input_metadata) = 'object'
    ),
    CONSTRAINT ck_mcp_tool_call_status CHECK (
        tool_call_status IN ('succeeded', 'failed')
    ),
    CONSTRAINT ck_mcp_tool_call_failure CHECK (
        (
            tool_call_status = 'succeeded'
            AND failure_code IS NULL
        )
        OR
        (
            tool_call_status = 'failed'
            AND reference.is_nonblank(failure_code)
        )
    )
);

CREATE FUNCTION mcp.reject_tool_call_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $reject_tool_call_log_mutation$
BEGIN
    RAISE EXCEPTION 'MCP tool call log is append-only' USING ERRCODE = '55000';
END;
$reject_tool_call_log_mutation$;

CREATE TRIGGER reject_tool_call_log_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE
ON mcp.tool_call_log
FOR EACH STATEMENT
EXECUTE FUNCTION mcp.reject_tool_call_log_mutation();

CREATE INDEX ix_tool_call_log_time
    ON mcp.tool_call_log (tool_call_time DESC);
CREATE INDEX ix_tool_call_log_principal_time
    ON mcp.tool_call_log (principal_id, tool_call_time DESC);
CREATE INDEX ix_tool_call_log_tool_time
    ON mcp.tool_call_log (tool_name, tool_call_time DESC);

CREATE INDEX ix_change_set_model_status_activity
    ON mcp.model_change_set (model_id, model_change_set_status, last_activity_time);

CREATE INDEX ix_change_set_expiry
    ON mcp.model_change_set (expires_time)
    WHERE model_change_set_status IN ('active', 'validated');

CREATE UNIQUE INDEX uq_model_stage_batch_active_dataset
    ON mcp.model_stage_batch (
        model_change_set_id,
        dataset_name
    )
    WHERE stage_batch_status = 'active';

CREATE INDEX ix_model_stage_batch_expiry
    ON mcp.model_stage_batch (expires_time)
    WHERE stage_batch_status = 'active';

CREATE INDEX ix_metadata_change_set_tenant_status_activity
    ON mcp.metadata_change_set (
        tenant_id,
        metadata_change_set_status,
        last_activity_time
    );

CREATE UNIQUE INDEX uq_metadata_change_set_ongoing_owner
    ON mcp.metadata_change_set (tenant_id, created_by_principal_id)
    WHERE metadata_change_set_status IN ('active', 'validated');

CREATE UNIQUE INDEX uq_metadata_stage_batch_active_dataset
    ON mcp.metadata_stage_batch (
        metadata_change_set_id,
        dataset_name
    )
    WHERE stage_batch_status = 'active';

CREATE INDEX ix_metadata_stage_batch_expiry
    ON mcp.metadata_stage_batch (expires_time)
    WHERE stage_batch_status = 'active';

CREATE INDEX ix_metadata_change_set_expiry
    ON mcp.metadata_change_set (expires_time)
    WHERE metadata_change_set_status IN ('active', 'validated');
