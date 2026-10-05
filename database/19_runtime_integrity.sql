-- GDS ETL Workbench Release 1: final privileges after runtime-role creation.

-- Least-privilege runtime roles. Deployment owns DDL; these roles cannot create it.
REVOKE ALL ON SCHEMA reference, core, security, model, workflow, application, mcp FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA reference, core, security, model, workflow, application, mcp FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow, application, mcp FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA mcp
FROM gds_app_write, gds_web_write;

GRANT USAGE ON SCHEMA reference, core, security, model, workflow, application, mcp
    TO gds_app_write;
GRANT USAGE ON SCHEMA reference, core, security, model, workflow, application, mcp
    TO gds_web_write;

-- Reassert the exact transaction-scoped memberships used by MCP and web.
GRANT gds_app_write TO gds_mcp_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
GRANT gds_web_write TO gds_web_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

-- Runtime writes need the pure validator referenced by CHECK constraints.
GRANT EXECUTE ON FUNCTION reference.is_nonblank(TEXT) TO gds_app_write;
GRANT EXECUTE ON FUNCTION reference.is_nonblank(TEXT) TO gds_web_write;
GRANT EXECUTE ON FUNCTION model.valid_schema_list(JSONB) TO gds_app_write, gds_web_write;

GRANT EXECUTE ON FUNCTION security.authorize_tenant_operation(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.check_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.acquire_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER,
    VARCHAR
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.override_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.renew_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.release_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION security.authorize_tenant_operation(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION security.check_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION security.acquire_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER,
    VARCHAR
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION security.override_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION security.renew_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    INTEGER
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION security.release_tenant_lock(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION security.expire_tenant_locks(INTEGER)
TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.create_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.stage_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    JSONB,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.begin_metadata_stage_batch(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    UUID,
    VARCHAR,
    INTEGER,
    INTEGER,
    CHAR,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.put_metadata_stage_chunk(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    UUID,
    VARCHAR,
    INTEGER,
    CHAR,
    JSONB
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.commit_metadata_stage_batch(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    UUID,
    BIGINT,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.get_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.record_metadata_change_set_validation(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    BOOLEAN,
    CHAR,
    JSONB,
    UUID,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.apply_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    CHAR,
    UUID
) TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.archive_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    UUID
) TO gds_app_write;

-- The web application reuses the same governed, lock-checked Metadata Change
-- Set boundary. It stages one bounded complete dataset at a time, so the MCP
-- chunk-upload functions remain unavailable to the web role.
GRANT EXECUTE ON FUNCTION mcp.create_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    UUID
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION mcp.stage_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    JSONB,
    UUID
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION mcp.get_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION mcp.record_metadata_change_set_validation(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    BOOLEAN,
    CHAR,
    JSONB,
    UUID,
    UUID
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION mcp.apply_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    CHAR,
    UUID
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION mcp.archive_metadata_change_set(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    UUID,
    BIGINT,
    UUID
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION mcp.get_databricks_sql_connection_values(BIGINT, TEXT)
TO gds_app_write;
REVOKE EXECUTE ON FUNCTION mcp.get_databricks_sql_connection_values(BIGINT, TEXT)
FROM gds_web_write;

GRANT EXECUTE ON FUNCTION workflow.list_tenant_visible_objects(BIGINT)
TO gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION workflow.list_model_object_eligibility(BIGINT)
TO gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION workflow.list_model_attribute_eligibility(BIGINT)
TO gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION workflow.is_assertion_only_mapping_target(BIGINT, BIGINT, VARCHAR)
TO gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION workflow.list_model_input_sources(BIGINT)
TO gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION workflow.list_mapping_source_objects(
    BIGINT, BIGINT, VARCHAR, BIGINT
) TO gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION workflow.list_code_generation_target_context(
    BIGINT,
    VARCHAR,
    VARCHAR
) TO gds_app_write, gds_web_write;

-- One runtime-owned readiness contract for the exact database surface used by
-- the registered MCP tools. The function performs no writes and returns only posture
-- booleans; it never returns physical rows, identities, or configuration.
CREATE OR REPLACE FUNCTION mcp.runtime_readiness()
RETURNS TABLE (
    schema_version VARCHAR(20),
    postgres_major INTEGER,
    schema_shape_ok BOOLEAN,
    runtime_role_ok BOOLEAN,
    runtime_privileges_ok BOOLEAN,
    runtime_query_contract_ok BOOLEAN
)
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog
AS $runtime_readiness$
DECLARE
    runtime_schema_usage_ok BOOLEAN;
BEGIN
    schema_version := '1.0.0';
    postgres_major := current_setting('server_version_num')::INTEGER / 10000;

    runtime_schema_usage_ok := NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference', 'core', 'security', 'model', 'workflow', 'mcp'
               ]) AS required_schema(name)
          LEFT JOIN pg_namespace AS namespace_record
            ON namespace_record.nspname = required_schema.name
         WHERE namespace_record.oid IS NULL
            OR has_schema_privilege(
                   'gds_app_write', namespace_record.oid, 'USAGE'
               ) IS NOT TRUE
    );

    schema_shape_ok := EXISTS (
        SELECT 1 FROM information_schema.columns WHERE table_schema='model' AND table_name='model'
          AND column_name='is_locked' AND data_type='boolean' AND is_nullable='NO'
    ) AND NOT EXISTS (
        SELECT 1 FROM unnest(ARRAY['object','attribute','copy','process','copy_group','process_group',
            'member_group','member','tenant','system','connection','connection_location']) AS required(name)
        WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='core'
            AND table_name=required.name AND column_name='value' AND data_type='jsonb' AND is_nullable='YES')
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_class AS relation JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace
        JOIN pg_attribute AS column_record ON column_record.attrelid=relation.oid
        WHERE namespace.nspname IN ('model','workflow','application','mcp') AND relation.relkind='r'
          AND NOT column_record.attisdropped AND column_record.attname IN ('model_id','workflow_run_id')
          AND (namespace.nspname, relation.relname) <> ('model','model_lock_event')
          AND NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=relation.oid
              AND tgname='aa_model_write_fence' AND tgenabled='O')
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'core' AND table_name = 'process_group'
           AND column_name = 'process_group_dependency_order'
           AND data_type = 'integer' AND is_nullable = 'NO'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'core.copy'::regclass AND conname = 'uq_copy_group_order'
    ) AND NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference.system_type',
                   'reference.connection_type',
                   'reference.object_type',
                   'reference.zone',
                   'reference.chunk_type',
                   'reference.file_type',
                   'reference.data_operation',
                   'reference.process_type',
                   'core.project',
                   'core.tenant',
                   'core.system',
                   'core.connection',
                   'core.connection_value',
                   'core.object',
                   'core.attribute',
                   'core.ingestion_object_mapping',
                   'core.ingestion_attribute_mapping',
                   'core.copy_group',
                   'core.member_group',
                   'core.member',
                   'core.copy_group_control',
                   'core.copy',
                   'core.process_group',
                   'core.process',
                   'security.principal',
                   'security.entra_principal_identity',
                   'security.tenant_principal_access',
                   'security.tenant_lock',
                   'security.tenant_lock_event',
                   'model.model',
                   'model.model_input_scope',
                   'model.modeling_assertion_document',
                   'model.modeling_assertion_record',
                   'workflow.attribute_profile',
                   'workflow.object_enrichment',
                   'workflow.attribute_enrichment',
                   'workflow.analysis_result',
                   'workflow.conceptual_object',
                   'workflow.conceptual_relationship',
                   'workflow.conceptual_support',
                   'workflow.logical_submodel',
                   'workflow.logical_entity',
                   'workflow.logical_entity_submodel',
                   'workflow.logical_entity_source_mapping',
                   'workflow.logical_attribute',
                   'workflow.logical_attribute_source_mapping',
                   'workflow.logical_relationship',
                   'workflow.dimensional_submodel',
                   'workflow.dimensional_entity',
                   'workflow.dimensional_entity_submodel',
                   'workflow.dimensional_entity_source_mapping',
                   'workflow.dimensional_attribute',
                   'workflow.dimensional_attribute_source_mapping',
                   'workflow.dimensional_relationship',
                   'workflow.mapping_object',
                   'workflow.mapping_attribute',
                   'workflow.generated_code',
                   'workflow.generated_code_source_system',
                   'workflow.validation_group',
                   'workflow.validation_check',
                   'application.output_template',
                   'application.output_template_field',
                   'mcp.model_change_set',
                   'mcp.model_change_set_event',
                   'mcp.model_stage_batch',
                   'mcp.model_stage_chunk',
                   'mcp.model_stage_payload_chunk',
                   'mcp.metadata_change_set',
                   'mcp.metadata_change_set_event',
                   'mcp.metadata_stage_batch',
                   'mcp.metadata_stage_chunk',
                   'mcp.tool_call_log'
               ]) AS required_relation(name)
         WHERE NOT EXISTS (
                   SELECT 1
                     FROM pg_class AS relation_record
                     JOIN pg_namespace AS namespace_record
                       ON namespace_record.oid = relation_record.relnamespace
                    WHERE namespace_record.nspname =
                              split_part(required_relation.name, '.', 1)
                      AND relation_record.relname =
                              split_part(required_relation.name, '.', 2)
                      AND relation_record.relkind IN ('r', 'p')
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM (
                   VALUES
                       ('core.tenant', 'gds_connection_id'),
                       ('core.object', 'connection_id'),
                       ('core.object', 'source_tenant_id'),
                       ('core.object', 'zone_id'),
                       ('core.object', 'object_schema'),
                       ('core.object', 'object_name'),
                       ('core.object', 'is_locked'),
                       ('model.model', 'logical_schemas'),
                       ('model.model', 'dimensional_schemas'),
                       ('model.model', 'default_mapping_source_system_id'),
                       ('model.model', 'logical_entity_scd_type'),
                       ('model.model', 'dimensional_entity_scd_type'),
                       ('workflow.logical_entity', 'logical_entity_schema_name'),
                       ('workflow.dimensional_entity', 'dimensional_entity_schema_name'),
                       ('model.model', 'silver_model_naming_instructions'),
                       ('model.model', 'silver_model_audit_columns_template'),
                       ('model.model', 'gold_model_naming_instructions'),
                       ('model.model', 'gold_model_technical_columns_template'),
                       ('model.model', 'gold_model_audit_columns_template'),
                       ('model.model_input_scope', 'is_active'),
                       ('workflow.object_enrichment', 'object_description'),
                       ('workflow.object_enrichment', 'is_locked'),
                       ('workflow.attribute_enrichment', 'attribute_description'),
                       ('workflow.attribute_enrichment', 'attribute_inferred_data_type'),
                       ('workflow.attribute_enrichment', 'is_natural_key'),
                       ('workflow.attribute_enrichment', 'is_primary_key'),
                       ('workflow.attribute_enrichment', 'is_nullable'),
                       ('workflow.attribute_enrichment', 'is_pii'),
                       ('workflow.attribute_enrichment', 'is_locked'),
                       ('workflow.mapping_object', 'mapping_transformation_document'),
                       ('workflow.dimensional_relationship', 'dimensional_relationship_is_optional'),
                       ('workflow.generated_code', 'generated_code_content'),
                       ('workflow.generated_code', 'artifact_name'),
                       ('workflow.generated_code', 'code_input_digest'),
                       ('workflow.generated_code', 'generated_code_is_locked'),
                       ('workflow.generated_code_source_system', 'generated_code_source_system_is_locked'),
                       ('workflow.validation_group', 'is_locked'),
                       ('workflow.validation_check', 'is_locked'),
                       ('workflow.validation_group', 'mapping_context_digest'),
                       ('workflow.validation_check', 'validation_query_sql'),
                       ('mcp.model_change_set', 'enrichment_document'),
                       ('mcp.model_change_set', 'code_generation_document'),
                       ('mcp.model_change_set', 'validation_document'),
                       ('core.attribute', 'object_id'),
                       ('core.attribute', 'attribute_name'),
                       ('core.attribute', 'attribute_inferred_data_type'),
                       ('core.attribute', 'is_locked'),
                       ('mcp.metadata_change_set', 'created_by_principal_id'),
                       ('mcp.metadata_change_set', 'source_object_document'),
                       ('mcp.metadata_change_set', 'source_attribute_document'),
                       ('mcp.metadata_change_set', 'bronze_object_document'),
                       ('mcp.metadata_change_set', 'bronze_attribute_document'),
                       ('mcp.metadata_change_set', 'silver_object_document'),
                       ('mcp.metadata_change_set', 'silver_attribute_document'),
                       ('mcp.metadata_change_set', 'gold_object_document'),
                       ('mcp.metadata_change_set', 'gold_attribute_document'),
                       ('mcp.metadata_change_set', 'ingestion_object_mapping_document'),
                       ('mcp.metadata_change_set', 'ingestion_attribute_mapping_document'),
                       ('mcp.metadata_change_set', 'copy_group_document'),
                       ('mcp.metadata_change_set', 'member_group_document'),
                       ('mcp.metadata_change_set', 'member_document'),
                       ('mcp.metadata_change_set', 'copy_group_control_document'),
                       ('mcp.metadata_change_set', 'copy_document'),
                       ('mcp.metadata_change_set', 'process_group_document'),
                       ('mcp.metadata_change_set', 'process_document')
               ) AS required_column(relation_name, column_name)
         WHERE NOT EXISTS (
                   SELECT 1
                     FROM pg_attribute AS attribute_record
                     JOIN pg_class AS relation_record
                       ON relation_record.oid = attribute_record.attrelid
                     JOIN pg_namespace AS namespace_record
                       ON namespace_record.oid = relation_record.relnamespace
                    WHERE namespace_record.nspname =
                              split_part(required_column.relation_name, '.', 1)
                      AND relation_record.relname =
                              split_part(required_column.relation_name, '.', 2)
                      AND attribute_record.attname = required_column.column_name
                      AND attribute_record.attnum > 0
                      AND NOT attribute_record.attisdropped
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM (VALUES
                   (
                       'security',
                       'authorize_tenant_operation',
                       'uuid, uuid, character varying, bigint, character varying'
                   ),
                   (
                       'security',
                       'check_tenant_lock',
                       'uuid, uuid, character varying, bigint'
                   ),
                   (
                       'security',
                       'acquire_tenant_lock',
                       'uuid, uuid, character varying, bigint, integer, character varying'
                   ),
                   (
                       'security',
                       'renew_tenant_lock',
                       'uuid, uuid, character varying, bigint, integer'
                   ),
                   (
                       'security',
                       'release_tenant_lock',
                       'uuid, uuid, character varying, bigint'
                   ),
                   (
                       'security',
                       'override_tenant_lock',
                       'uuid, uuid, character varying, bigint, character varying'
                   ),
                   ('security', 'expire_tenant_locks', 'integer'),
                   (
                       'mcp',
                       'create_metadata_change_set',
                       'uuid, uuid, character varying, bigint, uuid, uuid'
                   ),
                   (
                       'mcp',
                       'stage_metadata_change_set',
                       'uuid, uuid, character varying, bigint, uuid, bigint, jsonb, uuid'
                   ),
                   (
                       'mcp',
                       'begin_metadata_stage_batch',
                       'uuid, uuid, character varying, bigint, uuid, bigint, uuid, character varying, integer, integer, character, uuid'
                   ),
                   (
                       'mcp',
                       'put_metadata_stage_chunk',
                       'uuid, uuid, character varying, bigint, uuid, uuid, character varying, integer, character, jsonb'
                   ),
                   (
                       'mcp',
                       'commit_metadata_stage_batch',
                       'uuid, uuid, character varying, bigint, uuid, uuid, bigint, uuid'
                   ),
                   (
                       'mcp',
                       'get_metadata_change_set',
                       'uuid, uuid, character varying, bigint, uuid'
                   ),
                   (
                       'mcp',
                       'record_metadata_change_set_validation',
                       'uuid, uuid, character varying, bigint, uuid, bigint, boolean, character, jsonb, uuid, uuid'
                   ),
                   (
                       'mcp',
                       'apply_metadata_change_set',
                       'uuid, uuid, character varying, bigint, uuid, bigint, character, uuid'
                   ),
                   (
                       'mcp',
                       'archive_metadata_change_set',
                       'uuid, uuid, character varying, bigint, uuid, bigint, uuid'
                   ),
                   (
                       'workflow',
                       'list_tenant_visible_objects',
                       'bigint'
                   ),
                   (
                       'workflow',
                       'list_model_object_eligibility',
                       'bigint'
                   ),
                   (
                       'workflow',
                       'list_model_attribute_eligibility',
                       'bigint'
                   ),
                   (
                       'workflow',
                       'list_code_generation_target_context',
                       'bigint, character varying, character varying'
                   ),
                   (
                       'workflow',
                       'list_mapping_source_objects',
                       'bigint, bigint, character varying, bigint'
                   ),
                   ('workflow', 'list_model_input_sources', 'bigint'),
                   ('workflow', 'is_assertion_only_mapping_target', 'bigint, bigint, character varying'),
                   ('mcp', 'get_databricks_sql_connection_values', 'bigint, text')
               ) AS required_function(
                   schema_name,
                   function_name,
                   argument_types
               )
         WHERE NOT EXISTS (
                   SELECT 1
                     FROM pg_proc AS function_record
                     JOIN pg_namespace AS namespace_record
                       ON namespace_record.oid = function_record.pronamespace
                    WHERE namespace_record.nspname =
                              required_function.schema_name
                      AND function_record.proname =
                              required_function.function_name
                      AND oidvectortypes(function_record.proargtypes) =
                              required_function.argument_types
               )
    ) AND EXISTS (
        SELECT 1
          FROM pg_attribute AS duplicate_lock
          JOIN pg_class AS relation_record
            ON relation_record.oid = duplicate_lock.attrelid
          JOIN pg_namespace AS namespace_record
            ON namespace_record.oid = relation_record.relnamespace
         WHERE namespace_record.nspname = 'core'
           AND relation_record.relname = 'attribute'
           AND duplicate_lock.attname = 'is_locked'
           AND duplicate_lock.atttypid = 'boolean'::REGTYPE
           AND duplicate_lock.attnotnull
           AND duplicate_lock.attnum > 0
           AND NOT duplicate_lock.attisdropped
    ) AND EXISTS (
        SELECT 1
          FROM pg_index AS ownership_index
          JOIN pg_class AS index_record
            ON index_record.oid = ownership_index.indexrelid
          JOIN pg_namespace AS namespace_record
            ON namespace_record.oid = index_record.relnamespace
         WHERE namespace_record.nspname = 'core'
           AND index_record.relname = 'ix_object_source_tenant_zone_active'
           AND NOT ownership_index.indisunique
           AND pg_get_expr(
                   ownership_index.indpred,
                   ownership_index.indrelid
               ) = 'is_active'
           AND pg_get_indexdef(ownership_index.indexrelid) LIKE
               '%(source_tenant_id, zone_id)%'
    );

    runtime_role_ok := CURRENT_USER = 'gds_app_write'
        AND EXISTS (
            SELECT 1
              FROM pg_roles AS runtime_login
             WHERE runtime_login.rolname = SESSION_USER
               AND runtime_login.rolcanlogin
               AND NOT runtime_login.rolsuper
               AND NOT runtime_login.rolinherit
               AND NOT runtime_login.rolcreatedb
               AND NOT runtime_login.rolcreaterole
               AND NOT runtime_login.rolreplication
               AND NOT runtime_login.rolbypassrls
        )
        AND EXISTS (
            SELECT 1
              FROM pg_auth_members AS membership
              JOIN pg_roles AS runtime_login
                ON runtime_login.oid = membership.member
              JOIN pg_roles AS runtime_group
                ON runtime_group.oid = membership.roleid
             WHERE runtime_login.rolname = SESSION_USER
               AND runtime_group.rolname = 'gds_app_write'
               AND NOT membership.admin_option
               AND NOT membership.inherit_option
               AND membership.set_option
        )
        AND (
            SELECT count(*) = 1
              FROM pg_auth_members AS membership
              JOIN pg_roles AS runtime_login
                ON runtime_login.oid = membership.member
             WHERE runtime_login.rolname = SESSION_USER
        );

    runtime_privileges_ok := FALSE;
    IF schema_shape_ok AND runtime_schema_usage_ok THEN
        runtime_privileges_ok := NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference.system_type',
                   'reference.connection_type',
                   'reference.object_type',
                   'reference.zone',
                   'reference.chunk_type',
                   'reference.file_type',
                   'reference.data_operation',
                   'reference.process_type',
                   'core.project',
                   'core.tenant',
                   'core.system',
                   'core.connection',
                   'core.object',
                   'core.attribute',
                   'core.ingestion_object_mapping',
                   'core.ingestion_attribute_mapping',
                   'core.copy_group',
                   'core.member_group',
                   'core.member',
                   'core.copy_group_control',
                   'core.copy',
                   'core.process_group',
                   'core.process',
                   'security.principal',
                   'security.entra_principal_identity',
                   'security.tenant_principal_access',
                   'model.model',
                   'model.model_input_scope',
                   'model.modeling_assertion_document',
                   'model.modeling_assertion_record',
                   'workflow.attribute_profile',
                   'workflow.object_enrichment',
                   'workflow.attribute_enrichment',
                   'workflow.analysis_result',
                   'workflow.conceptual_object',
                   'workflow.conceptual_relationship',
                   'workflow.conceptual_support',
                   'workflow.logical_submodel',
                   'workflow.logical_entity',
                   'workflow.logical_entity_submodel',
                   'workflow.logical_entity_source_mapping',
                   'workflow.logical_attribute',
                   'workflow.logical_attribute_source_mapping',
                   'workflow.logical_relationship',
                   'workflow.dimensional_submodel',
                   'workflow.dimensional_entity',
                   'workflow.dimensional_entity_submodel',
                   'workflow.dimensional_entity_source_mapping',
                   'workflow.dimensional_attribute',
                   'workflow.dimensional_attribute_source_mapping',
                   'workflow.dimensional_relationship',
                   'workflow.mapping_object',
                   'workflow.mapping_attribute',
                   'workflow.generated_code',
                   'workflow.generated_code_source_system',
                   'workflow.validation_group',
                   'workflow.validation_check',
                   'application.output_template',
                   'application.output_template_field',
                   'mcp.model_change_set',
                   'mcp.model_change_set_event',
                   'mcp.model_stage_batch',
                   'mcp.model_stage_chunk',
                   'mcp.model_stage_payload_chunk'
               ]) AS readable_relation(name)
         WHERE NOT has_table_privilege(
                   'gds_app_write', readable_relation.name, 'SELECT'
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'workflow.object_enrichment', 'workflow.attribute_enrichment'
               ]) AS enrichment_relation(name)
         WHERE has_table_privilege(
                   'gds_app_write', enrichment_relation.name,
                   'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN'
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'workflow.generated_code',
                   'workflow.generated_code_source_system',
                   'workflow.validation_group',
                   'workflow.validation_check'
               ]) AS model_section_relation(name)
         WHERE NOT has_table_privilege(
                   'gds_app_write',
                   model_section_relation.name,
                   'SELECT,INSERT,UPDATE'
               )
            OR EXISTS (
                   SELECT 1
                     FROM unnest(ARRAY[
                              'DELETE', 'TRUNCATE', 'REFERENCES',
                              'TRIGGER', 'MAINTAIN'
                          ]) AS forbidden_privilege(name)
                    WHERE has_table_privilege(
                              'gds_app_write',
                              model_section_relation.name,
                              forbidden_privilege.name
                          )
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM (VALUES
                   ('workflow.generated_code', 'generated_code_id'),
                   ('workflow.generated_code_source_system',
                       'generated_code_source_system_id'),
                   ('workflow.validation_group', 'validation_group_id'),
                   ('workflow.validation_check', 'validation_check_id')
               ) AS identity_column(relation_name, column_name)
         WHERE NOT coalesce(
                   has_sequence_privilege(
                       'gds_app_write',
                       pg_get_serial_sequence(
                           identity_column.relation_name,
                           identity_column.column_name
                       ),
                       'USAGE,SELECT'
                   ),
                   FALSE
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'security.authorize_tenant_operation(uuid,uuid,character varying,bigint,character varying)',
                   'security.check_tenant_lock(uuid,uuid,character varying,bigint)',
                   'security.acquire_tenant_lock(uuid,uuid,character varying,bigint,integer,character varying)',
                   'security.renew_tenant_lock(uuid,uuid,character varying,bigint,integer)',
                   'security.release_tenant_lock(uuid,uuid,character varying,bigint)',
                   'security.override_tenant_lock(uuid,uuid,character varying,bigint,character varying)',
                   'security.expire_tenant_locks(integer)',
                   'mcp.create_metadata_change_set(uuid,uuid,character varying,bigint,uuid,uuid)',
                   'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
                   'mcp.begin_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,bigint,uuid,character varying,integer,integer,character,uuid)',
                   'mcp.put_metadata_stage_chunk(uuid,uuid,character varying,bigint,uuid,uuid,character varying,integer,character,jsonb)',
                   'mcp.commit_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,uuid,bigint,uuid)',
                   'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                   'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                   'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
                   'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)',
                   'workflow.list_tenant_visible_objects(bigint)',
                   'workflow.list_model_object_eligibility(bigint)',
                   'workflow.list_model_attribute_eligibility(bigint)',
                   'workflow.list_model_input_sources(bigint)',
                   'workflow.is_assertion_only_mapping_target(bigint,bigint,character varying)',
                   'workflow.list_mapping_source_objects(bigint,bigint,character varying,bigint)',
                   'workflow.list_code_generation_target_context(bigint,character varying,character varying)',
                   'mcp.start_mcp_profiling_run(uuid,uuid,character varying,bigint,bigint,bigint[],text[],character varying,uuid)',
                   'mcp.get_mcp_profiling_status(uuid,uuid,character varying,bigint)',
                   'mcp.cancel_mcp_profiling_run(uuid,uuid,character varying,bigint)',
                   'mcp.mcp_profiling_worker(text,bigint,uuid,jsonb)',
                   'mcp.apply_model_enrichment_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character varying)',
                   'mcp.get_databricks_sql_connection_values(bigint,text)'
               ]) AS executable_function(signature)
         WHERE NOT has_function_privilege(
                   'gds_app_write', executable_function.signature, 'EXECUTE'
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_proc AS mcp_function
          JOIN pg_namespace AS namespace_record
            ON namespace_record.oid = mcp_function.pronamespace
         WHERE namespace_record.nspname = 'mcp'
           AND has_function_privilege(
                   'gds_app_write',
                   mcp_function.oid,
                   'EXECUTE'
               )
           AND NOT EXISTS (
                   SELECT 1
                     FROM unnest(ARRAY[
                              'mcp.create_metadata_change_set(uuid,uuid,character varying,bigint,uuid,uuid)',
                              'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
                              'mcp.begin_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,bigint,uuid,character varying,integer,integer,character,uuid)',
                              'mcp.put_metadata_stage_chunk(uuid,uuid,character varying,bigint,uuid,uuid,character varying,integer,character,jsonb)',
                              'mcp.commit_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,uuid,bigint,uuid)',
                              'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                              'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                              'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
                              'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)',
                              'mcp.start_mcp_profiling_run(uuid,uuid,character varying,bigint,bigint,bigint[],text[],character varying,uuid)',
                              'mcp.get_mcp_profiling_status(uuid,uuid,character varying,bigint)',
                              'mcp.cancel_mcp_profiling_run(uuid,uuid,character varying,bigint)',
                              'mcp.mcp_profiling_worker(text,bigint,uuid,jsonb)',
                              'mcp.apply_model_enrichment_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character varying)',
                              'mcp.get_databricks_sql_connection_values(bigint,text)',
                              'mcp.runtime_readiness()'
                          ]) AS allowed_mcp_function(signature)
                    WHERE to_regprocedure(
                              allowed_mcp_function.signature
                          ) = mcp_function.oid
               )
    ) AND has_table_privilege(
        'gds_app_write', 'mcp.tool_call_log', 'INSERT'
    ) AND has_table_privilege(
        'gds_app_write', 'mcp.model_stage_batch', 'SELECT,INSERT,UPDATE'
    ) AND has_table_privilege(
        'gds_app_write', 'mcp.model_stage_chunk', 'SELECT,INSERT'
    ) AND has_table_privilege(
        'gds_app_write', 'mcp.model_stage_payload_chunk', 'SELECT,INSERT'
    ) AND NOT has_table_privilege(
        'gds_app_write', 'mcp.model_stage_batch', 'DELETE,TRUNCATE'
    ) AND NOT has_table_privilege(
        'gds_app_write', 'mcp.model_stage_chunk', 'UPDATE,DELETE,TRUNCATE'
    ) AND NOT has_table_privilege(
        'gds_app_write', 'mcp.model_stage_payload_chunk', 'UPDATE,DELETE,TRUNCATE'
    ) AND NOT has_table_privilege(
        'gds_app_write', 'core.connection_value', 'SELECT'
    ) AND NOT (
        has_table_privilege('gds_app_write', 'mcp.metadata_change_set', 'SELECT')
        OR has_table_privilege('gds_app_write', 'mcp.metadata_change_set', 'INSERT')
        OR has_table_privilege('gds_app_write', 'mcp.metadata_change_set', 'UPDATE')
        OR has_table_privilege('gds_app_write', 'mcp.metadata_change_set', 'DELETE')
    ) AND NOT (
        has_table_privilege(
            'gds_app_write', 'mcp.metadata_change_set_event', 'SELECT'
        )
        OR has_table_privilege(
            'gds_app_write', 'mcp.metadata_change_set_event', 'INSERT'
        )
        OR has_table_privilege(
            'gds_app_write', 'mcp.metadata_change_set_event', 'UPDATE'
        )
        OR has_table_privilege(
            'gds_app_write', 'mcp.metadata_change_set_event', 'DELETE'
        )
    ) AND NOT (
        has_table_privilege(
            'gds_app_write', 'mcp.metadata_stage_batch', 'SELECT,INSERT,UPDATE,DELETE'
        )
        OR has_table_privilege(
            'gds_app_write', 'mcp.metadata_stage_chunk', 'SELECT,INSERT,UPDATE,DELETE'
        )
    ) AND NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference.system_type',
                   'reference.connection_type',
                   'reference.object_type',
                   'reference.zone',
                   'reference.chunk_type',
                   'reference.file_type',
                   'reference.data_operation',
                   'reference.process_type',
                   'core.project',
                   'core.tenant',
                   'core.system',
                   'core.connection',
                   'core.connection_value',
                   'core.object',
                   'core.attribute',
                   'core.ingestion_object_mapping',
                   'core.ingestion_attribute_mapping',
                   'core.copy_group',
                   'core.member_group',
                   'core.member',
                   'core.copy_group_control',
                   'core.copy',
                   'core.process_group',
                   'core.process',
                   'security.principal',
                   'security.entra_principal_identity',
                   'security.tenant_principal_access',
                   'security.tenant_lock',
                   'security.tenant_lock_event',
                   'model.model',
                   'mcp.metadata_change_set',
                   'mcp.metadata_change_set_event',
                   'mcp.metadata_stage_batch',
                   'mcp.metadata_stage_chunk'
               ]) AS protected_relation(name)
         CROSS JOIN unnest(ARRAY[
                   'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'
               ]) AS forbidden_privilege(name)
         WHERE has_table_privilege(
                   'gds_app_write',
                   protected_relation.name,
                   forbidden_privilege.name
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'is_locked',
                   'default_agent_sdk_code',
                   'default_agent_provider_code',
                   'default_agent_model_code',
                   'default_reasoning_effort_code',
                   'default_max_turns',
                   'default_validation_retry_count',
                   'model_name'
               ]) AS web_only_model_column(name)
         WHERE has_column_privilege(
                   'gds_app_write',
                   'model.model',
                   web_only_model_column.name,
                   'UPDATE'
               )
    ) AND NOT (
        has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'SELECT')
        OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'UPDATE')
        OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'DELETE')
        OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'TRUNCATE')
    );
    END IF;

    runtime_query_contract_ok := FALSE;
    IF schema_shape_ok AND runtime_role_ok AND runtime_privileges_ok THEN
        BEGIN
            PERFORM object_record.source_tenant_id
              FROM core.object AS object_record
              JOIN core.tenant AS source_tenant
                ON source_tenant.tenant_id = object_record.source_tenant_id
             WHERE FALSE;

            PERFORM 1
              FROM security.check_tenant_lock(
                  '00000000-0000-0000-0000-000000000000'::UUID,
                  '00000000-0000-0000-0000-000000000000'::UUID,
                  'user',
                  9223372036854775807
              );

            PERFORM 1
              FROM mcp.get_metadata_change_set(
                  '00000000-0000-0000-0000-000000000000'::UUID,
                  '00000000-0000-0000-0000-000000000000'::UUID,
                  'user',
                  9223372036854775807,
                  '00000000-0000-0000-0000-000000000000'::UUID
              );

            PERFORM 1
              FROM mcp.get_databricks_sql_connection_values(
                  9223372036854775807,
                  'readiness_missing_environment'
              );

            PERFORM 1
              FROM workflow.list_tenant_visible_objects(
                  9223372036854775807
              );

            PERFORM 1
              FROM workflow.list_model_object_eligibility(
                  9223372036854775807
              );

            PERFORM 1
              FROM workflow.list_model_attribute_eligibility(
                  9223372036854775807
              );

            PERFORM 1
              FROM workflow.list_mapping_source_objects(
                  9223372036854775807,
                  9223372036854775807,
                  'logical_entity',
                  9223372036854775807
              );

            PERFORM 1
              FROM workflow.list_code_generation_target_context(
                  9223372036854775807,
                  'logical_entity'
              );

            runtime_query_contract_ok := TRUE;
        EXCEPTION WHEN OTHERS THEN
            runtime_query_contract_ok := FALSE;
        END;
    END IF;

    RETURN NEXT;
END;
$runtime_readiness$;

REVOKE ALL ON FUNCTION mcp.runtime_readiness() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mcp.runtime_readiness() TO gds_app_write;

GRANT SELECT ON ALL TABLES IN SCHEMA reference, core, model, workflow
    TO gds_app_write;
REVOKE SELECT ON core.connection_value FROM gds_app_write;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, core, model, workflow
    TO gds_web_write;
REVOKE SELECT ON core.connection_value FROM gds_web_write;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
ON model.model_revision_transaction
FROM gds_app_write, gds_web_write;
GRANT SELECT ON
    mcp.model_change_set,
    mcp.model_change_set_event,
    mcp.model_stage_batch,
    mcp.model_stage_chunk,
    mcp.model_stage_payload_chunk
TO gds_app_write;
GRANT SELECT ON
    security.principal,
    security.entra_principal_identity,
    security.tenant_principal_access
TO gds_app_write;
GRANT SELECT ON
    security.principal,
    security.entra_principal_identity,
    security.tenant_principal_access,
    security.tenant_lock,
    security.tenant_lock_event
TO gds_web_write;
GRANT INSERT ON mcp.tool_call_log TO gds_app_write;

-- MCP mutates only normalized artifacts and workflow state through governed
-- Model Change Sets. Foundational target rows, Model revision audit, web-only Model
-- defaults, audit rows, and every DELETE remain outside its write surface.
GRANT INSERT, UPDATE ON
    model.model_input_scope,
    model.modeling_assertion_document,
    model.modeling_assertion_record,
    workflow.analysis_result,
    workflow.generated_code,
    workflow.generated_code_source_system,
    workflow.mapping_attribute,
    workflow.attribute_profile,
    workflow.conceptual_object,
    workflow.conceptual_relationship,
    workflow.conceptual_support,
    workflow.dimensional_attribute,
    workflow.dimensional_attribute_source_mapping,
    workflow.dimensional_entity,
    workflow.dimensional_entity_source_mapping,
    workflow.dimensional_entity_submodel,
    workflow.dimensional_relationship,
    workflow.dimensional_submodel,
    workflow.logical_attribute,
    workflow.logical_attribute_source_mapping,
    workflow.logical_entity,
    workflow.logical_entity_source_mapping,
    workflow.logical_entity_submodel,
    workflow.logical_relationship,
    workflow.logical_submodel,
    workflow.validation_check,
    workflow.validation_group,
    mcp.model_change_set,
    mcp.model_stage_batch,
    workflow.mapping_object
TO gds_app_write;
GRANT INSERT ON mcp.model_stage_chunk, mcp.model_stage_payload_chunk TO gds_app_write;
GRANT UPDATE (
    default_mapping_source_system_id,
    logical_entity_scd_type,
    dimensional_entity_scd_type,
    model_description,
    logical_schemas,
    dimensional_schemas,
    model_revision,
    silver_model_naming_instructions,
    silver_model_audit_columns_template,
    gold_model_naming_instructions,
    gold_model_technical_columns_template,
    gold_model_audit_columns_template,
    updated_time,
    updated_by
)
    ON model.model TO gds_app_write;
REVOKE UPDATE (
    default_agent_sdk_code,
    default_agent_provider_code,
    default_agent_model_code,
    default_reasoning_effort_code,
    default_max_turns,
    default_validation_retry_count,
    model_name
) ON model.model FROM gds_app_write;
GRANT INSERT ON
    mcp.model_change_set_event
TO gds_app_write;

-- The web runtime shares only the governed Model Change Set transport and its
-- canonical materializer target surface. Attribute Profile persistence and
-- other web writes remain function-only.
GRANT SELECT ON
    mcp.model_change_set,
    mcp.model_change_set_event,
    mcp.model_stage_batch,
    mcp.model_stage_chunk,
    mcp.model_stage_payload_chunk
TO gds_web_write;
GRANT INSERT, UPDATE ON
    model.modeling_assertion_document,
    model.modeling_assertion_record,
    workflow.analysis_result,
    workflow.generated_code,
    workflow.generated_code_source_system,
    workflow.mapping_attribute,
    workflow.conceptual_object,
    workflow.conceptual_relationship,
    workflow.conceptual_support,
    workflow.dimensional_attribute,
    workflow.dimensional_attribute_source_mapping,
    workflow.dimensional_entity,
    workflow.dimensional_entity_source_mapping,
    workflow.dimensional_entity_submodel,
    workflow.dimensional_relationship,
    workflow.dimensional_submodel,
    workflow.logical_attribute,
    workflow.logical_attribute_source_mapping,
    workflow.logical_entity,
    workflow.logical_entity_source_mapping,
    workflow.logical_entity_submodel,
    workflow.logical_relationship,
    workflow.logical_submodel,
    workflow.validation_check,
    workflow.validation_group,
    mcp.model_change_set,
    mcp.model_stage_batch,
    workflow.mapping_object
TO gds_web_write;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
ON workflow.attribute_profile FROM gds_web_write;
-- Enrichment persistence remains function-only for both runtime roles.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
ON workflow.object_enrichment, workflow.attribute_enrichment
FROM gds_app_write, gds_web_write;
GRANT INSERT ON
    mcp.model_stage_chunk,
    mcp.model_stage_payload_chunk,
    mcp.model_change_set_event
TO gds_web_write;
GRANT UPDATE (
    default_mapping_source_system_id,
    logical_entity_scd_type,
    dimensional_entity_scd_type,
    model_description,
    logical_schemas,
    dimensional_schemas,
    model_revision,
    silver_model_naming_instructions,
    silver_model_audit_columns_template,
    gold_model_naming_instructions,
    gold_model_technical_columns_template,
    gold_model_audit_columns_template,
    updated_time,
    updated_by
)
    ON model.model TO gds_web_write;
REVOKE UPDATE (
    default_agent_sdk_code,
    default_agent_provider_code,
    default_agent_model_code,
    default_reasoning_effort_code,
    default_max_turns,
    default_validation_retry_count,
    model_name
) ON model.model FROM gds_web_write;
REVOKE ALL ON ALL TABLES IN SCHEMA application
FROM gds_app_write, gds_web_write;
GRANT SELECT ON application.output_template, application.output_template_field TO gds_app_write;
GRANT SELECT ON ALL TABLES IN SCHEMA application TO gds_web_write;
REVOKE SELECT ON application.metadata_enrichment_result FROM gds_web_write;
REVOKE SELECT ON application.metadata_review_event FROM gds_web_write;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA application
FROM PUBLIC, gds_app_write, gds_web_write;
GRANT EXECUTE ON FUNCTION application.add_model_input_scope_objects(
    UUID, UUID, BIGINT, BIGINT, BIGINT, BIGINT[]) TO gds_web_write;

GRANT EXECUTE ON FUNCTION application.delete_model_records(
    UUID, UUID, BIGINT, BIGINT, BIGINT, UUID, JSONB) TO gds_web_write;

GRANT EXECUTE ON FUNCTION application.authorize_model_record_review(
    UUID, UUID, VARCHAR, BIGINT, BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.set_principal_last_tenant(
    UUID,
    UUID,
    VARCHAR,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.create_model(
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
    VARCHAR,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.update_model(
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
    VARCHAR,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.archive_model(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.save_prompt_template(
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
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.save_prompt_template_draft(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    TEXT,
    TEXT,
    TEXT,
    TIMESTAMPTZ, TEXT[]
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.transition_prompt_template_version(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.set_prompt_assignment(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.create_output_template(
    UUID,
    UUID,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    JSONB,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.update_output_template(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR,
    BOOLEAN,
    TIMESTAMPTZ
) TO gds_web_write;
REVOKE EXECUTE ON FUNCTION application.snapshot_workflow_run_prompts(
    BIGINT,
    JSONB
) FROM gds_web_write;
GRANT EXECUTE ON FUNCTION application.create_workflow_run(
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
    JSONB,
    JSONB,
    VARCHAR,
    BIGINT[]
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.lock_authoring_workflow_run(
    BIGINT,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.start_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.cancel_workflow_run(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.claim_next_workflow_run(INTEGER)
TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.renew_workflow_run_claim(
    BIGINT,
    UUID,
    INTEGER
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.release_workflow_run_claim(
    BIGINT,
    UUID
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.assert_workflow_run_claim(
    BIGINT,
    UUID
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.begin_workflow_run_usage(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, UUID
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.begin_workflow_run_model_request(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, UUID, UUID, UUID, VARCHAR, INTEGER, INTEGER, JSONB
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.complete_workflow_run_model_request(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, UUID, UUID, BIGINT, BIGINT, BIGINT,
    BIGINT, BIGINT, BIGINT, BOOLEAN
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.append_workflow_run_event(
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
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.complete_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    INTEGER
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.complete_authoring_workflow_run_no_op(
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
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.fail_workflow_run(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.get_profiling_execution_context(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.get_profiling_connection_values(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.get_analysis_validation_execution_context(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.get_analysis_validation_connection_values(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.persist_analysis_validation_results(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    JSONB
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.persist_profiling_results(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    JSONB
) TO gds_web_write;

GRANT EXECUTE ON FUNCTION application.get_metadata_enrichment_execution_context(
    UUID, UUID, VARCHAR, BIGINT, BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.get_metadata_enrichment_connection_values(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, BIGINT, VARCHAR
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.complete_metadata_enrichment(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, UUID, CHAR, JSONB
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.get_metadata_enrichment_results(
    UUID, UUID, VARCHAR, BIGINT, INTEGER, INTEGER
) TO gds_web_write;

-- Identity sequences are granted only when owned by an INSERT-allowlisted
-- table.  This excludes foundational and authoritative audit sequences while
-- avoiding reliance on PostgreSQL's truncated generated sequence names.
DO $grant_runtime_sequences$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT DISTINCT sequence_namespace.nspname AS schema_name,
                        sequence_relation.relname AS sequence_name
          FROM pg_depend AS dependency
          JOIN pg_class AS sequence_relation
            ON sequence_relation.oid = dependency.objid
           AND sequence_relation.relkind = 'S'
          JOIN pg_namespace AS sequence_namespace
            ON sequence_namespace.oid = sequence_relation.relnamespace
          JOIN pg_class AS table_relation
            ON table_relation.oid = dependency.refobjid
           AND table_relation.relkind IN ('r', 'p')
          JOIN pg_namespace AS table_namespace
            ON table_namespace.oid = table_relation.relnamespace
         WHERE dependency.classid = 'pg_class'::REGCLASS
           AND dependency.refclassid = 'pg_class'::REGCLASS
           AND dependency.deptype IN ('a', 'i')
           AND table_namespace.nspname IN ('model', 'workflow', 'mcp')
           AND (
               has_table_privilege(
                   'gds_app_write',
                   table_relation.oid,
                   'INSERT'
               )
               OR has_any_column_privilege(
                   'gds_app_write',
                   table_relation.oid,
                   'INSERT'
               )
           )
    LOOP
        EXECUTE format(
            'GRANT USAGE, SELECT ON SEQUENCE %I.%I TO gds_app_write',
            target.schema_name,
            target.sequence_name
        );
    END LOOP;
END;
$grant_runtime_sequences$;

DO $grant_web_change_set_sequences$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT DISTINCT sequence_namespace.nspname AS schema_name,
                        sequence_relation.relname AS sequence_name
          FROM pg_depend AS dependency
          JOIN pg_class AS sequence_relation
            ON sequence_relation.oid = dependency.objid
           AND sequence_relation.relkind = 'S'
          JOIN pg_namespace AS sequence_namespace
            ON sequence_namespace.oid = sequence_relation.relnamespace
          JOIN pg_class AS table_relation
            ON table_relation.oid = dependency.refobjid
           AND table_relation.relkind IN ('r', 'p')
          JOIN pg_namespace AS table_namespace
            ON table_namespace.oid = table_relation.relnamespace
         WHERE dependency.classid = 'pg_class'::REGCLASS
           AND dependency.refclassid = 'pg_class'::REGCLASS
           AND dependency.deptype IN ('a', 'i')
           AND table_namespace.nspname IN ('model', 'workflow', 'mcp')
           AND (
               has_table_privilege(
                   'gds_web_write',
                   table_relation.oid,
                   'INSERT'
               )
               OR has_any_column_privilege(
                   'gds_web_write',
                   table_relation.oid,
                   'INSERT'
               )
           )
    LOOP
        EXECUTE format(
            'GRANT USAGE, SELECT ON SEQUENCE %I.%I TO gds_web_write',
            target.schema_name,
            target.sequence_name
        );
    END LOOP;
END;
$grant_web_change_set_sequences$;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA application
FROM gds_app_write, gds_web_write;

GRANT USAGE, CREATE ON SCHEMA reference, core, security, model, workflow, application, mcp TO gds_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reference, core, security, model, workflow, application, mcp
    TO gds_migration;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA reference, core, security, model, workflow, application, mcp
    TO gds_migration;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow, application, mcp
    TO gds_migration;

GRANT EXECUTE ON FUNCTION workflow.enrichment_review_revision(BIGINT, BIGINT, BIGINT)
TO gds_app_write, gds_web_write;

GRANT EXECUTE ON FUNCTION application.review_model_enrichment(UUID, UUID, BIGINT, BIGINT, BIGINT, VARCHAR, VARCHAR, JSONB, UUID) TO gds_web_write;
-- Model-wide write fence. Metadata has independent Tenant governance.
CREATE OR REPLACE FUNCTION model.assert_writable(p_model_id BIGINT)
RETURNS VOID LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog
AS $assert_model_writable$
DECLARE v_locked BOOLEAN;
BEGIN
    IF current_setting('transaction_read_only') = 'on' THEN
        SELECT is_locked INTO v_locked FROM model.model WHERE model_id = p_model_id;
    ELSE
        SELECT is_locked INTO v_locked FROM model.model WHERE model_id = p_model_id FOR SHARE;
    END IF;
    IF v_locked THEN
        RAISE EXCEPTION 'model_locked' USING ERRCODE = '55000';
    END IF;
END;
$assert_model_writable$;
REVOKE ALL ON FUNCTION model.assert_writable(BIGINT) FROM PUBLIC;

CREATE OR REPLACE FUNCTION model.guard_model_write()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $guard_model_write$
DECLARE
    v_row JSONB;
    v_model_id BIGINT;
BEGIN
    IF TG_TABLE_SCHEMA = 'model' AND TG_TABLE_NAME = 'model' THEN
        IF TG_OP = 'UPDATE' AND NEW.is_locked IS DISTINCT FROM OLD.is_locked THEN
            IF (to_jsonb(NEW) - ARRAY['is_locked','model_revision','updated_time','updated_by'])
                IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['is_locked','model_revision','updated_time','updated_by']) THEN
                RAISE EXCEPTION 'model_locked' USING ERRCODE = '55000';
            END IF;
            IF NEW.is_locked AND EXISTS (
                SELECT 1 FROM application.workflow_run
                 WHERE model_id = OLD.model_id AND workflow_run_state IN ('queued','running')
            ) THEN
                RAISE EXCEPTION 'model_workflow_conflict' USING ERRCODE = '55000';
            END IF;
            NEW.model_revision := OLD.model_revision + 1;
            NEW.updated_time := clock_timestamp();
            INSERT INTO model.model_lock_event(model_id, is_locked, model_revision, changed_by)
            VALUES (NEW.model_id, NEW.is_locked, NEW.model_revision, NEW.updated_by);
            RETURN NEW;
        END IF;
        IF TG_OP <> 'INSERT' AND OLD.is_locked THEN
            RAISE EXCEPTION 'model_locked' USING ERRCODE = '55000';
        END IF;
    ELSE
        -- Check both owners on updates, so re-parenting cannot escape a lock.
        FOR v_row IN SELECT value FROM jsonb_array_elements(
            CASE TG_OP WHEN 'INSERT' THEN jsonb_build_array(to_jsonb(NEW))
                       WHEN 'DELETE' THEN jsonb_build_array(to_jsonb(OLD))
                       ELSE jsonb_build_array(to_jsonb(OLD), to_jsonb(NEW)) END
        ) LOOP
            v_model_id := (v_row ->> 'model_id')::BIGINT;
            IF v_model_id IS NULL THEN
                IF TG_TABLE_SCHEMA = 'workflow' AND TG_TABLE_NAME = 'generated_code_source_system' THEN
                    SELECT model_id INTO v_model_id FROM workflow.generated_code
                     WHERE generated_code_id = (v_row ->> 'generated_code_id')::BIGINT;
                ELSIF TG_TABLE_SCHEMA = 'workflow' AND TG_TABLE_NAME = 'validation_check' THEN
                    SELECT model_id INTO v_model_id FROM workflow.validation_group
                     WHERE validation_group_id = (v_row ->> 'validation_group_id')::BIGINT;
                ELSIF TG_TABLE_SCHEMA = 'mcp' AND TG_TABLE_NAME IN ('model_stage_chunk','model_stage_payload_chunk') THEN
                    SELECT model_id INTO v_model_id FROM mcp.model_stage_batch
                     WHERE stage_batch_id = (v_row ->> 'stage_batch_id')::UUID;
                ELSIF v_row ? 'workflow_run_id' THEN
                    SELECT model_id INTO v_model_id FROM application.workflow_run
                     WHERE workflow_run_id = (v_row ->> 'workflow_run_id')::BIGINT;
                END IF;
            END IF;
            IF v_model_id IS NOT NULL THEN PERFORM model.assert_writable(v_model_id); END IF;
        END LOOP;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$guard_model_write$;
REVOKE ALL ON FUNCTION model.guard_model_write() FROM PUBLIC;

DO $install_model_write_fences$
DECLARE v_table RECORD;
BEGIN
    FOR v_table IN
        SELECT DISTINCT namespace.nspname, relation.relname
          FROM pg_class AS relation
          JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
          JOIN pg_attribute AS column_record ON column_record.attrelid = relation.oid
         WHERE namespace.nspname IN ('model','workflow','application','mcp')
           AND relation.relkind = 'r' AND NOT column_record.attisdropped
           AND (column_record.attname IN ('model_id','workflow_run_id')
                OR (namespace.nspname, relation.relname) IN (
                    ('workflow','validation_check'), ('mcp','model_stage_chunk'),
                    ('mcp','model_stage_payload_chunk')))
           AND (namespace.nspname, relation.relname) <> ('model','model_lock_event')
    LOOP
        EXECUTE format('CREATE OR REPLACE TRIGGER aa_model_write_fence BEFORE INSERT OR UPDATE OR DELETE ON %I.%I '
                       'FOR EACH ROW EXECUTE FUNCTION model.guard_model_write()',
                       v_table.nspname, v_table.relname);
    END LOOP;
END;
$install_model_write_fences$;

CREATE OR REPLACE FUNCTION application.set_model_lock(
    p_entra_tenant_id UUID, p_entra_object_id UUID, p_tenant_id BIGINT,
    p_model_id BIGINT, p_expected_model_revision BIGINT, p_is_locked BOOLEAN
)
RETURNS SETOF model.model LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog
AS $set_model_lock$
DECLARE v_model model.model%ROWTYPE; v_decision RECORD;
BEGIN
    IF p_expected_model_revision IS NULL OR p_is_locked IS NULL THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;
    SELECT * INTO v_model FROM model.model
     WHERE model_id = p_model_id AND tenant_id = p_tenant_id AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Model is unavailable'; END IF;
    SELECT * INTO v_decision FROM security.authorize_tenant_operation(
        p_entra_tenant_id, p_entra_object_id, 'user', p_tenant_id, 'tenant_model_write');
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RAISE EXCEPTION 'Model lock denied: %', coalesce(v_decision.denial_code, 'authorization_denied');
    END IF;
    IF v_model.model_revision <> p_expected_model_revision THEN
        RAISE EXCEPTION 'stale_model_revision';
    END IF;
    IF v_model.is_locked = p_is_locked THEN RETURN NEXT v_model; RETURN; END IF;
    RETURN QUERY UPDATE model.model SET is_locked = p_is_locked,
        updated_by = 'principal:' || v_decision.principal_id::TEXT
     WHERE model_id = p_model_id RETURNING *;
END;
$set_model_lock$;
REVOKE ALL ON FUNCTION application.set_model_lock(UUID, UUID, BIGINT, BIGINT, BIGINT, BOOLEAN) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION application.set_model_lock(UUID, UUID, BIGINT, BIGINT, BIGINT, BOOLEAN) TO gds_web_write;
GRANT EXECUTE ON FUNCTION model.assert_writable(BIGINT) TO gds_app_write, gds_web_write;

GRANT EXECUTE ON FUNCTION model.assert_writable(BIGINT), model.guard_model_write(),
    application.set_model_lock(UUID, UUID, BIGINT, BIGINT, BIGINT, BOOLEAN) TO gds_migration;

-- Narrow MCP profiling commands; generic web workflow functions stay web-only.
GRANT EXECUTE ON FUNCTION mcp.start_mcp_profiling_run(
    UUID, UUID, VARCHAR, BIGINT, BIGINT, BIGINT[], TEXT[], VARCHAR, UUID
), mcp.get_mcp_profiling_status(UUID, UUID, VARCHAR, BIGINT),
   mcp.cancel_mcp_profiling_run(UUID, UUID, VARCHAR, BIGINT),
   mcp.mcp_profiling_worker(TEXT, BIGINT, UUID, JSONB)
TO gds_app_write;

GRANT EXECUTE ON FUNCTION mcp.apply_model_enrichment_change_set(UUID, UUID, VARCHAR, BIGINT, UUID, BIGINT, VARCHAR)
TO gds_app_write, gds_web_write;
