-- GDS ETL Workbench Release 1: computed Attribute Profiles and Analysis.

CREATE SCHEMA workflow;

CREATE TABLE workflow.attribute_profile (
    model_id BIGINT NOT NULL,
    attribute_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    source_context_digest CHAR(64) NOT NULL,
    row_count BIGINT NOT NULL,
    non_null_count BIGINT NOT NULL,
    null_count BIGINT NOT NULL,
    blank_count BIGINT,
    distinct_count BIGINT,
    min_data_length INTEGER,
    max_data_length INTEGER,
    avg_data_length NUMERIC(20, 6),
    percent_populated NUMERIC(7, 4),
    percent_duplicates NUMERIC(7, 4),
    percent_null NUMERIC(7, 4),
    percent_blank NUMERIC(7, 4),
    percent_distinct NUMERIC(7, 4),
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    PRIMARY KEY (model_id, attribute_id),
    CONSTRAINT fk_attribute_profile_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_profile_scope FOREIGN KEY (model_id, object_id)
        REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_profile_attribute FOREIGN KEY (
        attribute_id,
        object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT ck_attribute_profile_digest CHECK (
        source_context_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_attribute_profile_counts CHECK (
        row_count >= 0
        AND non_null_count >= 0
        AND null_count >= 0
        AND non_null_count + null_count = row_count
        AND (blank_count IS NULL OR blank_count BETWEEN 0 AND non_null_count)
        AND (distinct_count IS NULL OR distinct_count BETWEEN 0 AND non_null_count)
    ),
    CONSTRAINT ck_attribute_profile_lengths CHECK (
        (min_data_length IS NULL OR min_data_length >= 0)
        AND (max_data_length IS NULL OR max_data_length >= 0)
        AND (
            min_data_length IS NULL
            OR max_data_length IS NULL
            OR min_data_length <= max_data_length
        )
        AND (avg_data_length IS NULL OR avg_data_length >= 0)
    ),
    CONSTRAINT ck_attribute_profile_percentages CHECK (
        (percent_populated IS NULL OR percent_populated BETWEEN 0 AND 100)
        AND (percent_duplicates IS NULL OR percent_duplicates BETWEEN 0 AND 100)
        AND (percent_null IS NULL OR percent_null BETWEEN 0 AND 100)
        AND (percent_blank IS NULL OR percent_blank BETWEEN 0 AND 100)
        AND (percent_distinct IS NULL OR percent_distinct BETWEEN 0 AND 100)
    )
);

CREATE TABLE workflow.analysis_result (
    analysis_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    from_object_id BIGINT NOT NULL,
    from_attribute_id BIGINT NOT NULL,
    to_object_id BIGINT NOT NULL,
    to_attribute_id BIGINT NOT NULL,
    relationship_kind VARCHAR(100) NOT NULL,
    relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    relationship_basis TEXT NOT NULL,
    validation_policy_version VARCHAR(50) NOT NULL,
    validation_policy_digest CHAR(64) NOT NULL,
    validation_result VARCHAR(30) NOT NULL,
    validation_source_non_null_count BIGINT NOT NULL,
    validation_source_distinct_count BIGINT NOT NULL,
    validation_target_non_null_count BIGINT NOT NULL,
    validation_target_distinct_count BIGINT NOT NULL,
    validation_source_missing_target_count BIGINT NOT NULL,
    validation_unused_target_count BIGINT NOT NULL,
    validation_duplicate_target_key_count BIGINT NOT NULL,
    analysis_result_status VARCHAR(20) NOT NULL DEFAULT 'active',
    analysis_result_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_analysis_result_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_from_scope FOREIGN KEY (model_id, from_object_id)
        REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_to_scope FOREIGN KEY (model_id, to_object_id)
        REFERENCES model.model_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_from_attribute FOREIGN KEY (
        from_attribute_id,
        from_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_to_attribute FOREIGN KEY (
        to_attribute_id,
        to_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_analysis_result_id_model UNIQUE (analysis_result_id, model_id),
    CONSTRAINT uq_analysis_result_identity UNIQUE (
        model_id,
        from_attribute_id,
        to_attribute_id,
        relationship_kind
    ),
    CONSTRAINT ck_analysis_distinct_endpoints CHECK (
        from_attribute_id <> to_attribute_id
    ),
    CONSTRAINT ck_analysis_relationship_kind CHECK (
        core.is_nonblank(relationship_kind)
    ),
    CONSTRAINT ck_analysis_confidence CHECK (
        relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_analysis_basis CHECK (core.is_nonblank(relationship_basis)),
    CONSTRAINT ck_analysis_policy_version CHECK (
        validation_policy_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),
    CONSTRAINT ck_analysis_policy_digest CHECK (
        validation_policy_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_analysis_validation_result CHECK (
        validation_result IN ('supported', 'inconclusive', 'unsupported')
    ),
    CONSTRAINT ck_analysis_counts CHECK (
        validation_source_non_null_count >= 0
        AND validation_source_distinct_count >= 0
        AND validation_target_non_null_count >= 0
        AND validation_target_distinct_count >= 0
        AND validation_source_missing_target_count >= 0
        AND validation_unused_target_count >= 0
        AND validation_duplicate_target_key_count >= 0
    ),
    CONSTRAINT ck_analysis_result_status CHECK (
        analysis_result_status IN (
            'active', 'needs_review', 'inactive', 'deprecated'
        )
    )
);

CREATE TRIGGER capture_attribute_profile_change
BEFORE INSERT OR UPDATE OR DELETE ON workflow.attribute_profile
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();
CREATE TRIGGER capture_analysis_result_change
BEFORE INSERT OR UPDATE OR DELETE ON workflow.analysis_result
FOR EACH ROW EXECUTE FUNCTION model.capture_effective_change();

CREATE INDEX ix_attribute_profile_object
    ON workflow.attribute_profile (model_id, object_id, attribute_id);
CREATE INDEX ix_attribute_profile_digest
    ON workflow.attribute_profile (model_id, source_context_digest);
CREATE INDEX ix_analysis_result_model_status
    ON workflow.analysis_result (model_id, analysis_result_status);
CREATE INDEX ix_analysis_result_from_endpoint
    ON workflow.analysis_result (model_id, from_object_id, from_attribute_id);
CREATE INDEX ix_analysis_result_to_endpoint
    ON workflow.analysis_result (model_id, to_object_id, to_attribute_id);
CREATE INDEX ix_analysis_result_locked
    ON workflow.analysis_result (model_id, analysis_result_id)
    WHERE analysis_result_is_locked;
