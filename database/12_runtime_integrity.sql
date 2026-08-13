-- GDS ETL Workbench Release 1: final privileges after runtime-role creation.

-- Least-privilege runtime roles. Deployment owns DDL; these roles cannot create it.
REVOKE ALL ON SCHEMA reference, core, security, model, workflow, mcp FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA reference, core, security, model, workflow, mcp FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow, mcp FROM PUBLIC;

GRANT USAGE ON SCHEMA reference, core, security, model, workflow, mcp
    TO gds_app_write;

-- Runtime writes need the pure validator referenced by CHECK constraints.
GRANT EXECUTE ON FUNCTION reference.is_nonblank(TEXT) TO gds_app_write;

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
    VARCHAR,
    JSONB,
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

-- One runtime-owned readiness contract for the exact database surface used by
-- the 21 MCP tools. The function performs no writes and returns only posture
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
BEGIN
    schema_version := '1.0.0';
    postgres_major := current_setting('server_version_num')::INTEGER / 10000;

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
                   'security.tenant_principal_access',
                   'security.tenant_lock',
                   'security.tenant_lock_event',
                   'model.model',
                   'model.model_scope',
                   'mcp.metadata_change_set',
                   'mcp.metadata_change_set_event',
                   'mcp.tool_call_log'
               ]) AS required_relation(name)
         WHERE to_regclass(required_relation.name) IS NULL
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
                    WHERE attribute_record.attrelid =
                              to_regclass(required_column.relation_name)
                      AND attribute_record.attname = required_column.column_name
                      AND attribute_record.attnum > 0
                      AND NOT attribute_record.attisdropped
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
                   'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character varying,jsonb,uuid)',
                   'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                   'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                   'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
                   'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)'
               ]) AS required_function(signature)
         WHERE to_regprocedure(required_function.signature) IS NULL
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_attribute AS old_column
         WHERE old_column.attrelid =
                   to_regclass('core.tenant_metadata_discovery_scope')
           AND old_column.attname = 'connection_id'
           AND old_column.attnum > 0
           AND NOT old_column.attisdropped
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_attribute AS duplicate_lock
         WHERE duplicate_lock.attrelid = to_regclass('core.attribute')
           AND duplicate_lock.attname = 'is_locked'
           AND duplicate_lock.attnum > 0
           AND NOT duplicate_lock.attisdropped
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
        AND pg_has_role(SESSION_USER, 'gds_app_write', 'MEMBER')
        AND (
            SELECT count(*) = 1
              FROM pg_auth_members AS membership
              JOIN pg_roles AS runtime_login
                ON runtime_login.oid = membership.member
             WHERE runtime_login.rolname = SESSION_USER
        );

    runtime_privileges_ok := FALSE;
    IF schema_shape_ok THEN
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
                   'model.model_scope'
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
                   'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character varying,jsonb,uuid)',
                   'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                   'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                   'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
                   'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)'
               ]) AS executable_function(signature)
         WHERE NOT has_function_privilege(
                   'gds_app_write', executable_function.signature, 'EXECUTE'
               )
    ) AND has_table_privilege(
        'gds_app_write', 'mcp.tool_call_log', 'INSERT'
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
                   'mcp.metadata_change_set_event'
               ]) AS protected_relation(name)
         CROSS JOIN unnest(ARRAY[
                   'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'
               ]) AS forbidden_privilege(name)
         WHERE has_table_privilege(
                   'gds_app_write',
                   protected_relation.name,
                   forbidden_privilege.name
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
GRANT SELECT ON
    mcp.model_change_set,
    mcp.model_change_set_event
TO gds_app_write;
GRANT SELECT ON
    security.principal,
    security.entra_principal_identity,
    security.tenant_principal_access
TO gds_app_write;
GRANT INSERT ON mcp.tool_call_log TO gds_app_write;

-- The application mutates only the normalized artifact and workflow state used
-- by PostgresRepository.  Foundational Model/Scope/target rows, audit rows, and
-- every DELETE operation remain deployment-owner capabilities.
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
    workflow.mapping_object
TO gds_app_write;
GRANT INSERT ON
    mcp.model_change_set_event
TO gds_app_write;

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
           AND has_table_privilege(
                'gds_app_write',
                table_relation.oid,
                'INSERT'
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

GRANT USAGE, CREATE ON SCHEMA reference, core, security, model, workflow, mcp TO gds_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reference, core, security, model, workflow, mcp
    TO gds_migration;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA reference, core, security, model, workflow, mcp
    TO gds_migration;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA reference, core, security, model, workflow, mcp
    TO gds_migration;
