-- GDS ETL Workbench Release 1: MCP-owned persistence.

CREATE SCHEMA mcp;

CREATE TABLE mcp.model_change_set (
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
BEGIN
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
    IF FOUND THEN
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

    INSERT INTO mcp.metadata_change_set AS created_change_set (
        metadata_change_set_id,
        tenant_id,
        created_by_principal_id,
        correlation_id
    ) VALUES (
        p_new_metadata_change_set_id,
        p_tenant_id,
        v_decision.principal_id,
        p_correlation_id
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
    p_section_name VARCHAR(30),
    p_document JSONB,
    p_correlation_id UUID
)
RETURNS TABLE (
    staged BOOLEAN,
    denial_code VARCHAR(50),
    draft_revision BIGINT,
    record_count INTEGER,
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
    v_record_count INTEGER;
    v_event_sequence BIGINT;
BEGIN
    IF p_expected_draft_revision < 1
       OR p_section_name NOT IN (
           'source_object', 'source_attribute',
           'bronze_object', 'bronze_attribute',
           'silver_object', 'silver_attribute',
           'gold_object', 'gold_attribute',
           'ingestion_object_mapping', 'ingestion_attribute_mapping',
           'copy_group', 'member_group', 'copy_group_control', 'copy',
           'process_group', 'process'
       )
       OR jsonb_typeof(p_document) <> 'array'
       OR octet_length(p_document::TEXT) > 16777216 THEN
        RETURN QUERY SELECT
            FALSE,
            'invalid_request'::VARCHAR(50),
            NULL::BIGINT,
            NULL::INTEGER,
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
            NULL::BIGINT,
            NULL::INTEGER,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT change_set.metadata_change_set_status,
           change_set.draft_revision,
           change_set.expires_time,
           CASE p_section_name
               WHEN 'source_object' THEN change_set.source_object_document
               WHEN 'source_attribute' THEN change_set.source_attribute_document
               WHEN 'bronze_object' THEN change_set.bronze_object_document
               WHEN 'bronze_attribute' THEN change_set.bronze_attribute_document
               WHEN 'silver_object' THEN change_set.silver_object_document
               WHEN 'silver_attribute' THEN change_set.silver_attribute_document
               WHEN 'gold_object' THEN change_set.gold_object_document
               WHEN 'gold_attribute' THEN change_set.gold_attribute_document
               WHEN 'ingestion_object_mapping'
                   THEN change_set.ingestion_object_mapping_document
               WHEN 'ingestion_attribute_mapping'
                   THEN change_set.ingestion_attribute_mapping_document
               WHEN 'copy_group' THEN change_set.copy_group_document
               WHEN 'member_group' THEN change_set.member_group_document
               WHEN 'copy_group_control' THEN change_set.copy_group_control_document
               WHEN 'copy' THEN change_set.copy_document
               WHEN 'process_group' THEN change_set.process_group_document
               WHEN 'process' THEN change_set.process_document
           END AS current_document
      INTO v_change_set
      FROM mcp.metadata_change_set AS change_set
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
       AND change_set.tenant_id = p_tenant_id
       AND change_set.created_by_principal_id = v_decision.principal_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            'metadata_change_set_not_found'::VARCHAR(50),
            NULL::BIGINT,
            NULL::INTEGER,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE,
            'metadata_change_set_not_active'::VARCHAR(50),
            v_change_set.draft_revision::BIGINT,
            jsonb_array_length(v_change_set.current_document)::INTEGER,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision <> p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE,
            'draft_revision_conflict'::VARCHAR(50),
            v_change_set.draft_revision::BIGINT,
            jsonb_array_length(v_change_set.current_document)::INTEGER,
            v_change_set.expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_change_set AS change_set
       SET source_object_document = CASE
               WHEN p_section_name = 'source_object' THEN p_document
               ELSE change_set.source_object_document
           END,
           source_attribute_document = CASE
               WHEN p_section_name = 'source_attribute' THEN p_document
               ELSE change_set.source_attribute_document
           END,
           bronze_object_document = CASE
               WHEN p_section_name = 'bronze_object' THEN p_document
               ELSE change_set.bronze_object_document
           END,
           bronze_attribute_document = CASE
               WHEN p_section_name = 'bronze_attribute' THEN p_document
               ELSE change_set.bronze_attribute_document
           END,
           silver_object_document = CASE
               WHEN p_section_name = 'silver_object' THEN p_document
               ELSE change_set.silver_object_document
           END,
           silver_attribute_document = CASE
               WHEN p_section_name = 'silver_attribute' THEN p_document
               ELSE change_set.silver_attribute_document
           END,
           gold_object_document = CASE
               WHEN p_section_name = 'gold_object' THEN p_document
               ELSE change_set.gold_object_document
           END,
           gold_attribute_document = CASE
               WHEN p_section_name = 'gold_attribute' THEN p_document
               ELSE change_set.gold_attribute_document
           END,
           ingestion_object_mapping_document = CASE
               WHEN p_section_name = 'ingestion_object_mapping' THEN p_document
               ELSE change_set.ingestion_object_mapping_document
           END,
           ingestion_attribute_mapping_document = CASE
               WHEN p_section_name = 'ingestion_attribute_mapping' THEN p_document
               ELSE change_set.ingestion_attribute_mapping_document
           END,
           copy_group_document = CASE
               WHEN p_section_name = 'copy_group' THEN p_document
               ELSE change_set.copy_group_document
           END,
           member_group_document = CASE
               WHEN p_section_name = 'member_group' THEN p_document
               ELSE change_set.member_group_document
           END,
           copy_group_control_document = CASE
               WHEN p_section_name = 'copy_group_control' THEN p_document
               ELSE change_set.copy_group_control_document
           END,
           copy_document = CASE
               WHEN p_section_name = 'copy' THEN p_document
               ELSE change_set.copy_document
           END,
           process_group_document = CASE
               WHEN p_section_name = 'process_group' THEN p_document
               ELSE change_set.process_group_document
           END,
           process_document = CASE
               WHEN p_section_name = 'process' THEN p_document
               ELSE change_set.process_document
           END,
           metadata_change_set_status = 'active',
           draft_revision = change_set.draft_revision + 1,
           candidate_digest = NULL,
           validation_outcome = NULL,
           validated_time = NULL,
           last_activity_time = CURRENT_TIMESTAMP,
           expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
     WHERE change_set.metadata_change_set_id = p_metadata_change_set_id
    RETURNING change_set.draft_revision, change_set.expires_time
         INTO v_new_revision, v_expires_time;

    v_record_count := jsonb_array_length(p_document);
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
        section_name,
        action_count,
        outcome,
        correlation_id
    ) VALUES (
        p_metadata_change_set_id,
        p_tenant_id,
        v_event_sequence,
        'section_put',
        v_new_revision,
        p_section_name,
        v_record_count,
        'accepted',
        p_correlation_id
    );

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_new_revision,
        v_record_count,
        v_expires_time;
END;
$stage_metadata_change_set$;

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
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, mcp, security, core
AS $get_metadata_change_set$
DECLARE
    v_decision RECORD;
BEGIN
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
BEGIN
    IF p_expected_draft_revision < 1
       OR jsonb_typeof(p_validation_outcome) <> 'object'
       OR octet_length(p_validation_outcome::TEXT) > 1048576
       OR (p_validation_succeeded AND (
           p_candidate_digest IS NULL
           OR p_candidate_digest !~ '^[0-9a-f]{64}$'
       ))
       OR (NOT p_validation_succeeded AND p_candidate_digest IS NOT NULL) THEN
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
    IF v_change_set.draft_revision <> p_expected_draft_revision THEN
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
               WHEN p_validation_succeeded THEN CURRENT_TIMESTAMP
               ELSE NULL
           END,
           last_activity_time = CURRENT_TIMESTAMP,
           expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
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
BEGIN
    IF p_expected_draft_revision < 1 THEN
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
           change_set.terminal_time
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
    IF v_change_set.metadata_change_set_status NOT IN ('active', 'validated') THEN
        RETURN QUERY SELECT
            FALSE, 'metadata_change_set_not_active'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.terminal_time::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_change_set.draft_revision <> p_expected_draft_revision THEN
        RETURN QUERY SELECT
            FALSE, 'draft_revision_conflict'::VARCHAR(50),
            v_change_set.metadata_change_set_status::VARCHAR(20),
            v_change_set.draft_revision::BIGINT,
            v_change_set.terminal_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE mcp.metadata_change_set AS change_set
       SET metadata_change_set_status = 'archived',
           terminal_time = CURRENT_TIMESTAMP,
           last_activity_time = CURRENT_TIMESTAMP,
           expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
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

-- One immutable row per completed MCP tool call. input_metadata is a bounded,
-- server-created summary; it must never contain raw prompts, rows, output, or secrets.
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
        AND octet_length(input_metadata::TEXT) <= 16384
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

CREATE INDEX ix_metadata_change_set_tenant_status_activity
    ON mcp.metadata_change_set (
        tenant_id,
        metadata_change_set_status,
        last_activity_time
    );

CREATE UNIQUE INDEX uq_metadata_change_set_ongoing_owner
    ON mcp.metadata_change_set (tenant_id, created_by_principal_id)
    WHERE metadata_change_set_status IN ('active', 'validated');

CREATE INDEX ix_metadata_change_set_expiry
    ON mcp.metadata_change_set (expires_time)
    WHERE metadata_change_set_status IN ('active', 'validated');
