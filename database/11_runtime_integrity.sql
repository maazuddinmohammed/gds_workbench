-- GDS ETL Workbench Release 1: final privileges.

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
    INTEGER,
    VARCHAR,
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

GRANT SELECT ON ALL TABLES IN SCHEMA reference, core, model, workflow
    TO gds_app_write;
REVOKE SELECT ON core.connection_value FROM gds_app_write;
GRANT SELECT ON
    mcp.metadata_change_set,
    mcp.metadata_change_set_event,
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
    workflow.attribute_mapping,
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
    mcp.metadata_change_set,
    mcp.model_change_set,
    workflow.object_mapping
TO gds_app_write;
GRANT INSERT ON
    mcp.metadata_change_set_event,
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
