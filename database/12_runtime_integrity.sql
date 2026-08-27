-- GDS ETL Workbench Release 1: final privileges after runtime-role creation.

-- Least-privilege runtime roles. Deployment owns DDL; these roles cannot create it.
REVOKE ALL ON SCHEMA reference, core, security, model, workflow, application, mcp FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA reference, core, security, model, workflow, application, mcp FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow, application, mcp FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA mcp
FROM gds_app_write, gds_web_write;

-- The notebook login does not inherit its sole gds_web_write membership and has
-- no direct table, sequence, or general function surface. Control connections
-- use only these SECURITY DEFINER wrappers. In-process execution explicitly
-- activates gds_web_write with SET LOCAL ROLE for one transaction.
REVOKE ALL ON SCHEMA reference, core, security, model, workflow, application, mcp
FROM gds_notebook_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA reference, core, security, model, workflow, application, mcp
FROM gds_notebook_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA reference, core, security, model, workflow, application, mcp
FROM gds_notebook_runtime;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow, application, mcp
FROM gds_notebook_runtime;

GRANT USAGE ON SCHEMA security, application TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION security.current_notebook_principal()
TO gds_notebook_runtime;
-- Execution transactions retain SESSION_USER = gds_notebook_runtime after
-- activating gds_web_write, so they may resolve the same fixed workload actor.
GRANT EXECUTE ON FUNCTION security.current_notebook_principal()
TO gds_web_write;
GRANT EXECUTE ON FUNCTION security.check_notebook_tenant_lock(BIGINT)
TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION security.acquire_notebook_tenant_lock(
    BIGINT,
    INTEGER,
    VARCHAR
) TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION security.renew_notebook_tenant_lock(BIGINT, INTEGER)
TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION security.release_notebook_tenant_lock(BIGINT)
TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION application.create_notebook_workflow_run(
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
    VARCHAR,
    VARCHAR,
    UUID,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT
) TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION application.start_and_claim_notebook_workflow_run(
    BIGINT,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    INTEGER
) TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION application.renew_notebook_workflow_run_claim(
    BIGINT,
    UUID,
    INTEGER
) TO gds_notebook_runtime;
GRANT EXECUTE ON FUNCTION application.release_notebook_workflow_run_claim(
    BIGINT,
    UUID
) TO gds_notebook_runtime;

GRANT USAGE ON SCHEMA reference, core, security, model, workflow, mcp
    TO gds_app_write;
GRANT USAGE ON SCHEMA reference, core, security, model, workflow, application, mcp
    TO gds_web_write;

-- Reassert the exact transaction-scoped memberships used by web and notebook
-- workflow execution.
GRANT gds_app_write TO gds_mcp_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
GRANT gds_web_write TO gds_web_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
GRANT gds_web_write TO gds_notebook_runtime
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

-- Runtime writes need the pure validator referenced by CHECK constraints.
GRANT EXECUTE ON FUNCTION reference.is_nonblank(TEXT) TO gds_app_write;
GRANT EXECUTE ON FUNCTION reference.is_nonblank(TEXT) TO gds_web_write;

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
GRANT EXECUTE ON FUNCTION workflow.list_code_generation_target_context(
    BIGINT,
    VARCHAR
) TO gds_web_write;

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

    schema_shape_ok := NOT EXISTS (
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
                   'core.tenant_metadata_discovery_scope',
                   'core.object',
                   'core.attribute',
                   'core.ingestion_object_mapping',
                   'core.ingestion_attribute_mapping',
                   'core.copy_group',
                   'core.member_group',
                   'core.copy_group_control',
                   'core.copy',
                   'core.process_group',
                   'core.process',
                   'security.principal',
                   'security.entra_principal_identity',
                   'security.notebook_runtime_principal',
                   'security.tenant_principal_access',
                   'security.tenant_lock',
                   'security.tenant_lock_event',
                   'model.model',
                   'model.model_scope',
                   'model.modeling_assertion_document',
                   'model.modeling_assertion_record',
                   'workflow.attribute_profile',
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
                   'workflow.mapping_source_system_dependency',
                   'workflow.mapping_object',
                   'workflow.mapping_attribute',
                   'mcp.model_change_set',
                   'mcp.model_change_set_event',
                   'mcp.model_stage_batch',
                   'mcp.model_stage_chunk',
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
                       ('core.tenant_metadata_discovery_scope', 'tenant_id'),
                       ('core.tenant_metadata_discovery_scope', 'gds_connection_id'),
                       ('core.tenant_metadata_discovery_scope', 'zone_id'),
                       ('core.tenant_metadata_discovery_scope', 'object_schema'),
                       ('core.tenant_metadata_discovery_scope', 'is_active'),
                       ('core.object', 'connection_id'),
                       ('core.object', 'zone_id'),
                       ('core.object', 'object_schema'),
                       ('core.object', 'object_name'),
                       ('core.object', 'is_locked'),
                       ('model.model', 'silver_model_naming_instructions'),
                       ('model.model', 'silver_model_audit_columns_template'),
                       ('model.model', 'gold_model_naming_instructions'),
                       ('model.model', 'gold_model_technical_columns_template'),
                       ('model.model', 'gold_model_audit_columns_template'),
                       ('model.model_scope', 'is_active'),
                       ('workflow.dimensional_relationship', 'dimensional_relationship_is_optional'),
                       ('core.attribute', 'object_id'),
                       ('core.attribute', 'attribute_name'),
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
                   ('security', 'current_notebook_principal', ''),
                   ('security', 'check_notebook_tenant_lock', 'bigint'),
                   (
                       'security',
                       'acquire_notebook_tenant_lock',
                       'bigint, integer, character varying'
                   ),
                   (
                       'security',
                       'renew_notebook_tenant_lock',
                       'bigint, integer'
                   ),
                   ('security', 'release_notebook_tenant_lock', 'bigint'),
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
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_attribute AS old_column
          JOIN pg_class AS relation_record
            ON relation_record.oid = old_column.attrelid
          JOIN pg_namespace AS namespace_record
            ON namespace_record.oid = relation_record.relnamespace
         WHERE namespace_record.nspname = 'core'
           AND relation_record.relname = 'tenant_metadata_discovery_scope'
           AND old_column.attname = 'connection_id'
           AND old_column.attnum > 0
           AND NOT old_column.attisdropped
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_attribute AS duplicate_lock
          JOIN pg_class AS relation_record
            ON relation_record.oid = duplicate_lock.attrelid
          JOIN pg_namespace AS namespace_record
            ON namespace_record.oid = relation_record.relnamespace
         WHERE namespace_record.nspname = 'core'
           AND relation_record.relname = 'attribute'
           AND duplicate_lock.attname = 'is_locked'
           AND duplicate_lock.attnum > 0
           AND NOT duplicate_lock.attisdropped
    ) AND EXISTS (
        SELECT 1
          FROM pg_index AS assignment_index
          JOIN pg_class AS index_record
            ON index_record.oid = assignment_index.indexrelid
          JOIN pg_namespace AS namespace_record
            ON namespace_record.oid = index_record.relnamespace
         WHERE namespace_record.nspname = 'core'
           AND index_record.relname =
               'ux_active_metadata_discovery_scope_assignment'
           AND assignment_index.indisunique
           AND pg_get_expr(
                   assignment_index.indpred,
                   assignment_index.indrelid
               ) = 'is_active'
           AND pg_get_indexdef(assignment_index.indexrelid) LIKE
               '%(gds_connection_id, zone_id, lower(btrim((object_schema)::text)))%'
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
                   'core.tenant_metadata_discovery_scope',
                   'core.object',
                   'core.attribute',
                   'core.ingestion_object_mapping',
                   'core.ingestion_attribute_mapping',
                   'core.copy_group',
                   'core.member_group',
                   'core.copy_group_control',
                   'core.copy',
                   'core.process_group',
                   'core.process',
                   'security.principal',
                   'security.entra_principal_identity',
                   'security.tenant_principal_access',
                   'model.model',
                   'model.model_scope',
                   'model.modeling_assertion_document',
                   'model.modeling_assertion_record',
                   'workflow.attribute_profile',
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
                   'workflow.mapping_source_system_dependency',
                   'workflow.mapping_object',
                   'workflow.mapping_attribute',
                   'mcp.model_change_set',
                   'mcp.model_change_set_event',
                   'mcp.model_stage_batch',
                   'mcp.model_stage_chunk'
               ]) AS readable_relation(name)
         WHERE NOT has_table_privilege(
                   'gds_app_write', readable_relation.name, 'SELECT'
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
    ) AND NOT has_table_privilege(
        'gds_app_write', 'mcp.model_stage_batch', 'DELETE,TRUNCATE'
    ) AND NOT has_table_privilege(
        'gds_app_write', 'mcp.model_stage_chunk', 'UPDATE,DELETE,TRUNCATE'
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
                   'core.tenant_metadata_discovery_scope',
                   'core.object',
                   'core.attribute',
                   'core.ingestion_object_mapping',
                   'core.ingestion_attribute_mapping',
                   'core.copy_group',
                   'core.member_group',
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
                   'model.model_scope',
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
                   'default_agent_sdk_code',
                   'default_agent_provider_code',
                   'default_agent_model_code',
                   'default_reasoning_effort_code',
                   'default_max_turns',
                   'default_validation_retry_count'
               ]) AS web_only_model_column(name)
         WHERE has_column_privilege(
                   'gds_app_write',
                   'model.model',
                   web_only_model_column.name,
                   'UPDATE'
               )
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_attribute AS attribute
         CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE']) AS privilege_name(value)
         WHERE attribute.attrelid = 'model.model_scope'::REGCLASS
           AND attribute.attnum > 0
           AND NOT attribute.attisdropped
           AND has_column_privilege(
                   'gds_app_write',
                   'model.model_scope',
                   attribute.attname,
                   privilege_name.value
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
            PERFORM scope.gds_connection_id
              FROM core.tenant_metadata_discovery_scope AS scope
              JOIN core.connection AS connection_record
                ON connection_record.connection_id = scope.gds_connection_id
              JOIN reference.zone AS zone_record
                ON zone_record.zone_id = scope.zone_id
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
GRANT SELECT ON
    mcp.model_change_set,
    mcp.model_change_set_event,
    mcp.model_stage_batch,
    mcp.model_stage_chunk
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
-- Model Change Sets. Foundational target rows, Model Scope, web-only Model
-- defaults, audit rows, and every DELETE remain outside its write surface.
GRANT INSERT, UPDATE ON
    model.modeling_assertion_document,
    model.modeling_assertion_record,
    workflow.analysis_result,
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
    workflow.mapping_source_system_dependency,
    mcp.model_change_set,
    mcp.model_stage_batch,
    workflow.mapping_object
TO gds_app_write;
GRANT INSERT ON mcp.model_stage_chunk TO gds_app_write;
GRANT UPDATE (
    model_name,
    model_description,
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
    default_validation_retry_count
) ON model.model FROM gds_app_write;
REVOKE INSERT (model_id, object_id, model_scope_is_locked, is_active),
       UPDATE (model_scope_is_locked, is_active, updated_time, updated_by)
    ON model.model_scope FROM gds_app_write;
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
    mcp.model_stage_chunk
TO gds_web_write;
GRANT INSERT, UPDATE ON
    model.modeling_assertion_document,
    model.modeling_assertion_record,
    workflow.analysis_result,
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
    workflow.mapping_source_system_dependency,
    mcp.model_change_set,
    mcp.model_stage_batch,
    workflow.mapping_object
TO gds_web_write;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
ON workflow.attribute_profile FROM gds_web_write;
GRANT INSERT ON
    mcp.model_stage_chunk,
    mcp.model_change_set_event
TO gds_web_write;
GRANT UPDATE (
    model_name,
    model_description,
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
    default_validation_retry_count
) ON model.model FROM gds_web_write;
REVOKE INSERT (model_id, object_id, model_scope_is_locked, is_active),
       UPDATE (model_scope_is_locked, is_active, updated_time, updated_by)
    ON model.model_scope FROM gds_web_write;
REVOKE ALL ON ALL TABLES IN SCHEMA application
FROM gds_app_write, gds_web_write;
GRANT SELECT ON ALL TABLES IN SCHEMA application TO gds_web_write;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA application
FROM PUBLIC, gds_app_write, gds_web_write;
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
    INTEGER
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.update_model(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
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
    INTEGER
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.archive_model(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.replace_model_scope(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT[]
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
    TIMESTAMPTZ
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
    JSONB
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
GRANT EXECUTE ON FUNCTION application.save_sql_generation_guide(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    BOOLEAN,
    BOOLEAN,
    TIMESTAMPTZ
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.save_sql_generation_guide_draft(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    TEXT,
    TIMESTAMPTZ
) TO gds_web_write;
GRANT EXECUTE ON FUNCTION application.transition_sql_generation_guide_version(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    VARCHAR,
    VARCHAR
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
    VARCHAR,
    VARCHAR,
    UUID,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    BIGINT,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT
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
GRANT EXECUTE ON FUNCTION application.store_generated_sql_artifact(
    UUID,
    UUID,
    VARCHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    BIGINT,
    CHAR,
    CHAR,
    BIGINT,
    BIGINT,
    VARCHAR,
    VARCHAR,
    TEXT,
    CHAR
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
