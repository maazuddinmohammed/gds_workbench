-- Fail-fast verification after database/01_reference.sql through
-- database/12_runtime_integrity.sql have completed.

DO $verify_install$
DECLARE
    v_schema_count INTEGER;
    v_application_table_count INTEGER;
    v_group_role_count INTEGER;
    v_membership_count INTEGER;
    v_web_membership_count INTEGER;
    v_security_definer_count INTEGER;
    v_metadata_change_set_function_count INTEGER;
    v_databricks_function_count INTEGER;
    v_application_web_function_count INTEGER;
    v_application_web_function_signatures TEXT[] := ARRAY[
        'application.archive_model(uuid,uuid,character varying,bigint,bigint)',
        'application.set_principal_last_tenant(uuid,uuid,character varying,bigint)',
        'application.create_model(uuid,uuid,character varying,bigint,character varying,character varying,text,jsonb,text,jsonb,jsonb,character varying,character varying,character varying,character varying,integer,integer)',
        'application.update_model(uuid,uuid,character varying,bigint,bigint,character varying,character varying,text,jsonb,text,jsonb,jsonb,character varying,character varying,character varying,character varying,integer,integer)',
        'application.replace_model_scope(uuid,uuid,character varying,bigint,bigint,bigint[])',
        'application.save_prompt_template(uuid,uuid,character varying,bigint,bigint,character varying,bigint,character varying,character varying,text,boolean,timestamp with time zone)',
        'application.save_prompt_template_draft(uuid,uuid,character varying,bigint,bigint,text,text,text,timestamp with time zone)',
        'application.transition_prompt_template_version(uuid,uuid,character varying,bigint,character varying,character varying)',
        'application.set_prompt_assignment(uuid,uuid,character varying,bigint,character varying,bigint,bigint,bigint)',
        'application.create_output_template(uuid,uuid,character varying,character varying,character varying,character varying,character varying,jsonb)',
        'application.update_output_template(uuid,uuid,character varying,bigint,character varying,character varying,boolean,timestamp with time zone)',
        'application.save_sql_generation_guide(uuid,uuid,character varying,bigint,character varying,character varying,character varying,boolean,boolean,timestamp with time zone)',
        'application.save_sql_generation_guide_draft(uuid,uuid,character varying,bigint,bigint,text,timestamp with time zone)',
        'application.transition_sql_generation_guide_version(uuid,uuid,character varying,bigint,character varying,character varying)',
        'application.create_workflow_run(uuid,uuid,character varying,bigint,bigint,character varying,character varying,character varying,character varying,character varying,character varying,integer,integer,bigint[],character varying,character varying,uuid,jsonb,character varying,character varying,character varying,bigint,bigint,bigint,character varying,bigint)',
        'application.start_workflow_run(uuid,uuid,character varying,bigint,bigint)',
        'application.claim_next_workflow_run(integer)',
        'application.renew_workflow_run_claim(bigint,uuid,integer)',
        'application.release_workflow_run_claim(bigint,uuid)',
        'application.assert_workflow_run_claim(bigint,uuid)',
        'application.append_workflow_run_event(uuid,uuid,character varying,bigint,bigint,bigint,integer,character varying,character varying,character varying,integer,integer,integer)',
        'application.complete_authoring_workflow_run_no_op(uuid,uuid,character varying,bigint,bigint,bigint,character varying,character varying,uuid,bigint,character,bigint,integer,character varying,character varying,character varying,integer,integer,integer)',
        'application.complete_workflow_run(uuid,uuid,character varying,bigint,bigint,integer)',
        'application.fail_workflow_run(uuid,uuid,character varying,bigint,bigint,character varying,character varying)',
        'application.get_profiling_execution_context(uuid,uuid,character varying,bigint,bigint)',
        'application.get_profiling_connection_values(uuid,uuid,character varying,bigint,bigint,character varying)',
        'application.get_analysis_validation_execution_context(uuid,uuid,character varying,bigint,bigint,character varying)',
        'application.get_analysis_validation_connection_values(uuid,uuid,character varying,bigint,bigint,character varying)',
        'application.persist_analysis_validation_results(uuid,uuid,character varying,bigint,bigint,character varying,jsonb)',
        'application.lock_authoring_workflow_run(bigint,bigint)',
        'application.persist_profiling_results(uuid,uuid,character varying,bigint,bigint,jsonb)',
        'application.store_generated_sql_artifact(uuid,uuid,character varying,bigint,bigint,character varying,bigint,character,character,bigint,bigint,character varying,character varying,text,character)'
    ];
BEGIN
    IF current_setting('server_version_num')::INTEGER / 10000 <> 18 THEN
        RAISE EXCEPTION 'PostgreSQL 18 is required';
    END IF;

    SELECT count(*)
      INTO v_schema_count
     FROM pg_catalog.pg_namespace AS namespace_record
     WHERE namespace_record.nspname IN (
               'reference', 'core', 'security', 'model', 'workflow',
               'application', 'mcp'
           );

    IF v_schema_count <> 7 THEN
        RAISE EXCEPTION 'one or more release schemas are missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'workflow'
           AND column_record.table_name = 'dimensional_relationship'
           AND column_record.column_name =
               'dimensional_relationship_is_optional'
           AND column_record.data_type = 'boolean'
           AND column_record.is_nullable = 'NO'
           AND column_record.column_default IS NULL
    ) THEN
        RAISE EXCEPTION
            'Dimensional Relationship optionality contract is invalid';
    END IF;

    IF (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name IN (
                   'workflow_run_claim_token_digest',
                   'workflow_run_claimed_time',
                   'workflow_run_claim_heartbeat_time',
                   'workflow_run_claim_expires_time'
               )
           AND column_record.is_nullable = 'YES'
    ) <> 4 OR NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name = 'tenant_id'
           AND column_record.data_type = 'bigint'
           AND column_record.is_nullable = 'NO'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.conrelid =
               'application.workflow_run'::REGCLASS
           AND constraint_record.conname = 'fk_workflow_run_model'
           AND constraint_record.contype = 'f'
           AND pg_catalog.pg_get_constraintdef(constraint_record.oid) =
               'FOREIGN KEY (model_id, tenant_id) REFERENCES model.model(model_id, tenant_id)'
    ) OR NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name = 'workflow_run_recovery_count'
           AND column_record.data_type = 'integer'
           AND column_record.is_nullable = 'NO'
           AND column_record.column_default = '0'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name = 'workflow_run_claim_token'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.conrelid =
               'application.workflow_run'::REGCLASS
           AND constraint_record.conname = 'ck_workflow_run_claim'
           AND constraint_record.contype = 'c'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_index AS index_record
          JOIN pg_catalog.pg_class AS relation_record
            ON relation_record.oid = index_record.indrelid
          JOIN pg_catalog.pg_class AS index_relation
            ON index_relation.oid = index_record.indexrelid
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = relation_record.relnamespace
         WHERE namespace_record.nspname = 'application'
           AND relation_record.relname = 'workflow_run'
           AND index_relation.relname =
               'ix_workflow_run_claim_eligibility'
           AND index_record.indisvalid
           AND pg_catalog.pg_get_expr(
                   index_record.indpred,
                   index_record.indrelid
               ) = '((workflow_run_state)::text = ''running''::text)'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_index AS index_record
          JOIN pg_catalog.pg_class AS relation_record
            ON relation_record.oid = index_record.indrelid
          JOIN pg_catalog.pg_class AS index_relation
            ON index_relation.oid = index_record.indexrelid
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = relation_record.relnamespace
         WHERE namespace_record.nspname = 'application'
           AND relation_record.relname = 'workflow_run'
           AND index_relation.relname = 'uq_workflow_run_running_tenant'
           AND index_record.indisunique
           AND index_record.indisvalid
           AND index_record.indnkeyatts = 1
           AND pg_catalog.pg_get_indexdef(
                   index_relation.oid,
                   1,
                   TRUE
               ) = 'tenant_id'
           AND pg_catalog.pg_get_expr(
                   index_record.indpred,
                   index_record.indrelid
               ) = '((workflow_run_state)::text = ''running''::text)'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS function_record
         WHERE function_record.oid =
               'application.claim_next_workflow_run(integer)'::REGPROCEDURE
           AND pg_catalog.pg_get_function_result(function_record.oid)
               LIKE '%tenant_id bigint%'
           AND pg_catalog.pg_get_function_result(function_record.oid)
               LIKE '%workflow_execution_mode character varying%'
           AND pg_catalog.pg_get_function_result(function_record.oid)
               LIKE '%actor_principal_type character varying%'
           AND pg_catalog.pg_get_function_result(function_record.oid)
               LIKE '%actor_entra_tenant_id uuid%'
           AND pg_catalog.pg_get_function_result(function_record.oid)
               LIKE '%actor_entra_object_id uuid%'
    ) THEN
        RAISE EXCEPTION 'Workflow Run claim column contract is invalid';
    END IF;

    SELECT count(*)
      INTO v_application_table_count
      FROM information_schema.tables AS table_record
     WHERE table_record.table_schema = 'application'
       AND table_record.table_type = 'BASE TABLE'
       AND table_record.table_name IN (
               'principal_preference',
               'workflow_stage',
               'workflow_stage_variable',
               'prompt_template',
               'prompt_template_version',
               'prompt_assignment',
               'output_template',
               'output_template_field',
               'sql_generation_guide',
               'sql_generation_guide_version',
               'workflow_run',
               'workflow_run_object_selection',
               'workflow_run_mapping_target_selection',
               'workflow_run_prompt_snapshot',
               'generated_sql_artifact'
           );

    IF v_application_table_count <> 15 OR EXISTS (
        SELECT 1
          FROM information_schema.tables AS table_record
         WHERE table_record.table_schema = 'application'
           AND table_record.table_type = 'BASE TABLE'
           AND table_record.table_name NOT IN (
                   'principal_preference',
                   'workflow_stage',
                   'workflow_stage_variable',
                   'prompt_template',
                   'prompt_template_version',
                   'prompt_assignment',
                   'output_template',
                   'output_template_field',
                   'sql_generation_guide',
                   'sql_generation_guide_version',
                   'workflow_run',
                   'workflow_run_object_selection',
                   'workflow_run_mapping_target_selection',
                   'workflow_run_prompt_snapshot',
                   'generated_sql_artifact'
               )
    ) THEN
        RAISE EXCEPTION 'application table contract is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name = 'model_revision'
           AND column_record.data_type = 'bigint'
           AND column_record.is_nullable = 'NO'
    ) OR (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name IN (
                   'code_generation_coverage_mode',
                   'sql_generation_guide_id',
                   'sql_generation_guide_version_id',
                   'sql_generation_guide_digest'
               )
           AND column_record.is_nullable = 'YES'
    ) <> 4 OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'c'
           AND constraint_record.conname =
               'ck_workflow_run_code_generation_request'
           AND constraint_record.conrelid =
               'application.workflow_run'::regclass
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'f'
           AND constraint_record.conname =
               'fk_workflow_run_sql_generation_guide_version'
           AND constraint_record.conrelid =
               'application.workflow_run'::regclass
           AND constraint_record.confrelid =
               'application.sql_generation_guide_version'::regclass
           AND (
               SELECT array_agg(attribute.attname ORDER BY key.position)
                 FROM unnest(constraint_record.conkey) WITH ORDINALITY
                      AS key(attnum, position)
                 JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = constraint_record.conrelid
                  AND attribute.attnum = key.attnum
           ) = ARRAY[
                   'sql_generation_guide_version_id',
                   'sql_generation_guide_id',
                   'sql_generation_guide_digest'
               ]::name[]
           AND constraint_record.confdeltype = 'a'
    ) OR (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'generated_sql_artifact'
    ) <> 21 OR (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'generated_sql_artifact'
           AND column_record.column_name IN (
                   'generated_sql_artifact_id',
                   'model_id',
                   'model_revision',
                   'modeled_entity_type',
                   'object_id',
                   'mapping_context_digest',
                   'source_context_digest',
                   'sql_generation_guide_id',
                   'sql_generation_guide_version_id',
                   'sql_generation_guide_digest',
                   'workflow_run_id',
                   'generator_code',
                   'generator_version',
                   'generated_by_principal_id',
                   'generated_time',
                   'generated_sql',
                   'generated_sql_digest',
                   'created_time',
                   'created_by',
                   'updated_time',
                   'updated_by'
               )
    ) <> 21 OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'generated_sql_artifact'
           AND column_record.column_name = 'source_system_id'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'u'
           AND constraint_record.conname =
               'uq_generated_sql_artifact_identity'
           AND constraint_record.conrelid =
               'application.generated_sql_artifact'::regclass
           AND (
               SELECT array_agg(attribute.attname ORDER BY key.position)
                 FROM unnest(constraint_record.conkey) WITH ORDINALITY
                      AS key(attnum, position)
                 JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = constraint_record.conrelid
                  AND attribute.attnum = key.attnum
           ) = ARRAY[
                   'model_id',
                   'modeled_entity_type',
                   'object_id'
               ]::name[]
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS function_record
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = function_record.pronamespace
         WHERE namespace_record.nspname = 'workflow'
           AND function_record.proname =
               'list_code_generation_target_context'
           AND oidvectortypes(function_record.proargtypes) =
               'bigint, character varying'
           AND function_record.provolatile = 's'
           AND NOT function_record.prosecdef
           AND function_record.proconfig =
               ARRAY['search_path=pg_catalog']::TEXT[]
    ) THEN
        RAISE EXCEPTION 'Code Generation database contract is invalid';
    END IF;

    IF (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run'
           AND column_record.column_name IN (
                   'actor_entra_principal_identity_id',
                   'modeled_entity_type',
                   'requested_batch_id',
                   'mapping_operation',
                   'mapping_coverage_mode',
                   'mapping_artifact_type',
                   'mapping_route',
                   'mapping_profile_key',
                   'mapping_profile_version',
                   'mapping_profile_schema_digest',
                   'authoring_no_op_base_model_revision',
                   'authoring_no_op_candidate_digest',
                   'authoring_no_op_model_event_log_id'
               )
           AND column_record.is_nullable = 'YES'
    ) <> 13 OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'f'
           AND constraint_record.conname =
               'fk_workflow_run_authoring_no_op_event'
           AND constraint_record.conrelid =
               'application.workflow_run'::regclass
           AND constraint_record.confrelid = 'model.model_event_log'::regclass
           AND constraint_record.confdeltype = 'a'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'c'
           AND constraint_record.conname =
               'ck_workflow_run_authoring_no_op_receipt'
           AND constraint_record.conrelid =
               'application.workflow_run'::regclass
    ) OR (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name = 'workflow_run_object_selection'
           AND column_record.column_name IN (
                   'workflow_run_id',
                   'model_id',
                   'object_id',
                   'selection_order'
               )
           AND column_record.is_nullable = 'NO'
    ) <> 4 OR (
        SELECT count(*)
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'application'
           AND column_record.table_name =
               'workflow_run_mapping_target_selection'
           AND column_record.column_name IN (
                   'workflow_run_id',
                   'model_id',
                   'object_id',
                   'source_system_id',
                   'selection_order'
               )
           AND column_record.is_nullable = 'NO'
    ) <> 5 OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'c'
           AND constraint_record.conname = 'ck_workflow_run_mapping_request'
           AND constraint_record.conrelid =
               'application.workflow_run'::regclass
    ) THEN
        RAISE EXCEPTION 'durable Workflow Run input contract is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'mcp'
           AND column_record.table_name = 'model_change_set'
           AND column_record.column_name = 'workflow_run_id'
           AND column_record.data_type = 'bigint'
           AND column_record.is_nullable = 'YES'
    ) OR NOT EXISTS (
        SELECT 1
         FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'f'
           AND constraint_record.conname = 'fk_change_set_workflow_run'
           AND constraint_record.conrelid = 'mcp.model_change_set'::regclass
           AND constraint_record.confrelid = 'application.workflow_run'::regclass
           AND (
               SELECT array_agg(attribute.attname ORDER BY key.position)
                 FROM unnest(constraint_record.conkey) WITH ORDINALITY
                      AS key(attnum, position)
                 JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = constraint_record.conrelid
                  AND attribute.attnum = key.attnum
           ) = ARRAY['workflow_run_id', 'model_id']::name[]
           AND (
               SELECT array_agg(attribute.attname ORDER BY key.position)
                 FROM unnest(constraint_record.confkey) WITH ORDINALITY
                      AS key(attnum, position)
                 JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = constraint_record.confrelid
                  AND attribute.attnum = key.attnum
           ) = ARRAY['workflow_run_id', 'model_id']::name[]
           AND constraint_record.confdeltype = 'a'
    ) OR NOT EXISTS (
        SELECT 1
         FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.contype = 'u'
           AND constraint_record.conname = 'uq_change_set_workflow_run'
           AND constraint_record.conrelid = 'mcp.model_change_set'::regclass
           AND (
               SELECT array_agg(attribute.attname ORDER BY key.position)
                 FROM unnest(constraint_record.conkey) WITH ORDINALITY
                      AS key(attnum, position)
                 JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = constraint_record.conrelid
                  AND attribute.attnum = key.attnum
           ) = ARRAY['workflow_run_id']::name[]
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_trigger AS trigger_record
          JOIN pg_catalog.pg_proc AS function_record
            ON function_record.oid = trigger_record.tgfoid
          JOIN pg_catalog.pg_namespace AS function_namespace
            ON function_namespace.oid = function_record.pronamespace
         WHERE trigger_record.tgrelid = 'mcp.model_change_set'::regclass
           AND trigger_record.tgname = 'guard_model_change_set_workflow_binding'
           AND trigger_record.tgenabled = 'O'
           AND NOT trigger_record.tgisinternal
           AND function_namespace.nspname = 'mcp'
           AND function_record.proname =
               'guard_model_change_set_workflow_binding'
           AND NOT function_record.prosecdef
           AND function_record.proconfig =
               ARRAY['search_path=pg_catalog']::TEXT[]
    ) THEN
        RAISE EXCEPTION
            'Model Change Set Workflow Run binding contract is invalid';
    END IF;

    SELECT count(*)
      INTO v_group_role_count
      FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname IN (
               'gds_migration', 'gds_app_write', 'gds_web_write'
           )
       AND NOT role_record.rolcanlogin
       AND NOT role_record.rolsuper
       AND NOT role_record.rolinherit
       AND NOT role_record.rolcreatedb
       AND NOT role_record.rolcreaterole
       AND NOT role_record.rolreplication
       AND NOT role_record.rolbypassrls;

    IF v_group_role_count <> 3 THEN
        RAISE EXCEPTION 'release group-role posture is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles AS role_record
         WHERE role_record.rolname = 'gds_mcp_runtime'
           AND role_record.rolcanlogin
           AND NOT role_record.rolsuper
           AND NOT role_record.rolinherit
           AND NOT role_record.rolcreatedb
           AND NOT role_record.rolcreaterole
           AND NOT role_record.rolreplication
           AND NOT role_record.rolbypassrls
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime posture is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles AS role_record
         WHERE role_record.rolname = 'gds_web_runtime'
           AND role_record.rolcanlogin
           AND NOT role_record.rolsuper
           AND NOT role_record.rolinherit
           AND NOT role_record.rolcreatedb
           AND NOT role_record.rolcreaterole
           AND NOT role_record.rolreplication
           AND NOT role_record.rolbypassrls
    ) THEN
        RAISE EXCEPTION 'gds_web_runtime posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_membership_count
      FROM pg_catalog.pg_auth_members AS membership
      JOIN pg_catalog.pg_roles AS member_role
        ON member_role.oid = membership.member
     WHERE member_role.rolname = 'gds_mcp_runtime';

    IF v_membership_count <> 1 OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_auth_members AS membership
          JOIN pg_catalog.pg_roles AS member_role
            ON member_role.oid = membership.member
          JOIN pg_catalog.pg_roles AS group_role
            ON group_role.oid = membership.roleid
         WHERE member_role.rolname = 'gds_mcp_runtime'
           AND group_role.rolname = 'gds_app_write'
           AND NOT membership.admin_option
           AND NOT membership.inherit_option
           AND membership.set_option
    ) THEN
        RAISE EXCEPTION
            'gds_mcp_runtime gds_app_write membership options are invalid';
    END IF;

    SELECT count(*)
      INTO v_web_membership_count
      FROM pg_catalog.pg_auth_members AS membership
      JOIN pg_catalog.pg_roles AS member_role
        ON member_role.oid = membership.member
     WHERE member_role.rolname = 'gds_web_runtime';

    IF v_web_membership_count <> 1 OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_auth_members AS membership
          JOIN pg_catalog.pg_roles AS member_role
            ON member_role.oid = membership.member
          JOIN pg_catalog.pg_roles AS group_role
            ON group_role.oid = membership.roleid
         WHERE member_role.rolname = 'gds_web_runtime'
           AND group_role.rolname = 'gds_web_write'
           AND NOT membership.admin_option
           AND NOT membership.inherit_option
           AND membership.set_option
    ) THEN
        RAISE EXCEPTION
            'gds_web_runtime gds_web_write membership options are invalid';
    END IF;

    IF NOT has_database_privilege(
        'gds_mcp_runtime',
        current_database(),
        'CONNECT'
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime cannot connect to this database';
    END IF;

    IF NOT has_database_privilege(
        'gds_web_runtime',
        current_database(),
        'CONNECT'
    ) THEN
        RAISE EXCEPTION 'gds_web_runtime cannot connect to this database';
    END IF;

    IF to_regclass('core.tenant_metadata_discovery_scope') IS NULL
       OR to_regclass('workflow.mapping_object') IS NULL
       OR to_regclass('workflow.mapping_attribute') IS NULL
       OR to_regclass('mcp.tool_call_log') IS NULL THEN
        RAISE EXCEPTION 'required release tables are missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'workflow'
           AND column_record.table_name = 'mapping_attribute'
           AND column_record.column_name = 'mapping_object_id'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'workflow'
           AND column_record.table_name = 'mapping_attribute'
           AND column_record.column_name = 'object_mapping_id'
    ) THEN
        RAISE EXCEPTION 'workflow.mapping_attribute identifier is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'object'
           AND column_record.column_name = 'is_locked'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'attribute'
           AND column_record.column_name = 'is_locked'
    ) THEN
        RAISE EXCEPTION 'Object lock source is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'workflow'
           AND column_record.table_name = 'analysis_result'
           AND column_record.column_name =
               'validation_source_context_digest'
           AND column_record.data_type = 'character'
           AND column_record.character_maximum_length = 64
           AND column_record.is_nullable = 'YES'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.conrelid =
               'workflow.analysis_result'::REGCLASS
           AND constraint_record.conname =
               'ck_analysis_source_context_digest'
           AND constraint_record.contype = 'c'
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint AS constraint_record
         WHERE constraint_record.conrelid =
               'workflow.analysis_result'::REGCLASS
           AND constraint_record.conname =
               'ck_analysis_web_validation_context'
           AND constraint_record.contype = 'c'
    ) THEN
        RAISE EXCEPTION
            'Analysis validation source context contract is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'tenant_metadata_discovery_scope'
           AND column_record.column_name = 'gds_connection_id'
    ) OR EXISTS (
        SELECT 1
          FROM information_schema.columns AS column_record
         WHERE column_record.table_schema = 'core'
           AND column_record.table_name = 'tenant_metadata_discovery_scope'
           AND column_record.column_name = 'connection_id'
    ) THEN
        RAISE EXCEPTION 'Metadata Discovery Scope Connection identifier is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_index AS assignment_index
          JOIN pg_catalog.pg_class AS index_record
            ON index_record.oid = assignment_index.indexrelid
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = index_record.relnamespace
         WHERE namespace_record.nspname = 'core'
           AND index_record.relname =
               'ux_active_metadata_discovery_scope_assignment'
           AND assignment_index.indisunique
           AND pg_catalog.pg_get_expr(
                   assignment_index.indpred,
                   assignment_index.indrelid
               ) = 'is_active'
           AND pg_catalog.pg_get_indexdef(assignment_index.indexrelid) LIKE
               '%(gds_connection_id, zone_id, lower(btrim((object_schema)::text)))%'
    ) THEN
        RAISE EXCEPTION 'Metadata Discovery Scope assignment index is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS function_record
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = function_record.pronamespace
         WHERE namespace_record.nspname = 'mcp'
           AND function_record.proname = 'runtime_readiness'
           AND function_record.pronargs = 0
           AND NOT function_record.prosecdef
           AND EXISTS (
                   SELECT 1
                     FROM unnest(function_record.proconfig) AS setting(value)
                    WHERE setting.value = 'search_path=pg_catalog'
               )
    ) THEN
        RAISE EXCEPTION 'runtime readiness function posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_security_definer_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'security'
       AND function_record.proname IN (
               'authorize_tenant_operation',
               'check_tenant_lock',
               'acquire_tenant_lock',
               'override_tenant_lock',
               'renew_tenant_lock',
               'release_tenant_lock',
               'expire_tenant_locks'
           )
       AND function_record.prosecdef
       AND EXISTS (
               SELECT 1
                 FROM unnest(function_record.proconfig) AS setting(value)
                WHERE setting.value LIKE 'search_path=pg_catalog%'
           );

    IF v_security_definer_count <> 7 THEN
        RAISE EXCEPTION 'security function posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_metadata_change_set_function_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'mcp'
       AND function_record.proname IN (
               'create_metadata_change_set',
               'stage_metadata_change_set',
               'get_metadata_change_set',
               'record_metadata_change_set_validation',
               'apply_metadata_change_set',
               'archive_metadata_change_set'
           )
       AND function_record.prosecdef
       AND EXISTS (
               SELECT 1
                 FROM unnest(function_record.proconfig) AS setting(value)
                WHERE setting.value LIKE 'search_path=pg_catalog%'
           );

    IF v_metadata_change_set_function_count <> 6 THEN
        RAISE EXCEPTION 'Metadata Change Set function posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_databricks_function_count
      FROM pg_catalog.pg_proc AS function_record
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.oid = function_record.pronamespace
     WHERE namespace_record.nspname = 'mcp'
       AND function_record.proname = 'get_databricks_sql_connection_values'
       AND oidvectortypes(function_record.proargtypes) = 'bigint, text'
       AND function_record.prosecdef
       AND EXISTS (
               SELECT 1
                 FROM unnest(function_record.proconfig) AS setting(value)
                WHERE setting.value LIKE 'search_path=pg_catalog%'
           );

    IF v_databricks_function_count <> 1 THEN
        RAISE EXCEPTION 'Databricks connection function posture is invalid';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference', 'core', 'security', 'model', 'workflow',
                   'application', 'mcp'
               ]) AS schema_name(value)
         WHERE has_schema_privilege('public', schema_name.value, 'USAGE')
    ) THEN
        RAISE EXCEPTION 'PUBLIC retains release-schema usage';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference', 'core', 'security', 'model', 'workflow', 'mcp'
               ]) AS schema_name(value)
         WHERE NOT has_schema_privilege(
                   'gds_app_write', schema_name.value, 'USAGE'
               )
    ) THEN
        RAISE EXCEPTION 'gds_app_write release schema usage is invalid';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'reference', 'core', 'security', 'model', 'workflow',
                   'application', 'mcp'
               ]) AS schema_name(value)
         WHERE NOT has_schema_privilege(
                   'gds_web_write', schema_name.value, 'USAGE'
               )
    ) THEN
        RAISE EXCEPTION 'gds_web_write release schema usage is invalid';
    END IF;

    IF NOT has_table_privilege('gds_app_write', 'core.project', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'core.tenant', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'core.object', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'core.attribute', 'SELECT')
       OR NOT has_table_privilege(
           'gds_app_write',
           'core.tenant_metadata_discovery_scope',
           'SELECT'
       )
       OR has_table_privilege('gds_app_write', 'core.connection_value', 'SELECT')
       OR NOT has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'INSERT')
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'SELECT')
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'UPDATE')
       OR has_table_privilege('gds_app_write', 'mcp.tool_call_log', 'DELETE')
       OR has_table_privilege('gds_app_write', 'mcp.metadata_change_set', 'SELECT')
       OR has_table_privilege(
           'gds_app_write', 'mcp.metadata_change_set', 'INSERT,UPDATE,DELETE'
       )
       OR has_table_privilege(
           'gds_app_write', 'mcp.metadata_change_set_event', 'INSERT'
       )
       OR EXISTS (
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
       )
       OR EXISTS (
           SELECT 1
             FROM pg_catalog.pg_attribute AS attribute
            CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE'])
                       AS privilege_name(value)
            WHERE attribute.attrelid = 'model.model_scope'::REGCLASS
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
              AND has_column_privilege(
                      'gds_app_write',
                      'model.model_scope',
                      attribute.attname,
                      privilege_name.value
                  )
       )
       OR EXISTS (
           SELECT 1
             FROM unnest(ARRAY[
                      'model.modeling_assertion_document',
                      'model.modeling_assertion_record',
                      'workflow.analysis_result',
                      'workflow.mapping_attribute',
                      'workflow.conceptual_object',
                      'workflow.conceptual_relationship',
                      'workflow.conceptual_support',
                      'workflow.dimensional_attribute',
                      'workflow.dimensional_attribute_source_mapping',
                      'workflow.dimensional_entity',
                      'workflow.dimensional_entity_source_mapping',
                      'workflow.dimensional_entity_submodel',
                      'workflow.dimensional_relationship',
                      'workflow.dimensional_submodel',
                      'workflow.logical_attribute',
                      'workflow.logical_attribute_source_mapping',
                      'workflow.logical_entity',
                      'workflow.logical_entity_source_mapping',
                      'workflow.logical_entity_submodel',
                      'workflow.logical_relationship',
                      'workflow.logical_submodel',
                      'workflow.mapping_source_system_dependency',
                      'workflow.mapping_object'
                  ]) AS web_materializer_table(name)
            WHERE NOT has_table_privilege(
                      'gds_web_write', web_materializer_table.name,
                      'SELECT,INSERT,UPDATE'
                  )
               OR EXISTS (
                   SELECT 1
                     FROM unnest(ARRAY[
                              'DELETE', 'TRUNCATE', 'REFERENCES',
                              'TRIGGER', 'MAINTAIN'
                          ]) AS forbidden_privilege(name)
                    WHERE has_table_privilege(
                              'gds_web_write', web_materializer_table.name,
                              forbidden_privilege.name
                          )
                  )
       )
       OR NOT has_table_privilege(
              'gds_web_write', 'mcp.model_change_set',
              'SELECT,INSERT,UPDATE'
          )
       OR NOT has_table_privilege(
              'gds_web_write', 'mcp.model_stage_batch',
              'SELECT,INSERT,UPDATE'
          )
       OR NOT has_table_privilege(
              'gds_web_write', 'mcp.model_stage_chunk', 'SELECT,INSERT'
          )
       OR NOT has_table_privilege(
              'gds_web_write', 'mcp.model_change_set_event', 'SELECT,INSERT'
          )
       OR EXISTS (
           SELECT 1
             FROM unnest(ARRAY[
                      'mcp.metadata_change_set',
                      'mcp.metadata_change_set_event',
                      'mcp.metadata_stage_batch',
                      'mcp.metadata_stage_chunk'
                  ]) AS metadata_private_table(name)
            CROSS JOIN unnest(ARRAY[
                      'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                      'REFERENCES', 'TRIGGER', 'MAINTAIN'
                  ]) AS forbidden_privilege(name)
            WHERE has_table_privilege(
                      'gds_web_write',
                      metadata_private_table.name,
                      forbidden_privilege.name
                  )
       )
       OR EXISTS (
           SELECT 1
             FROM unnest(ARRAY[
                      'mcp.model_stage_chunk',
                      'mcp.model_change_set_event'
                  ]) AS insert_only_table(name)
            CROSS JOIN unnest(ARRAY[
                      'UPDATE', 'DELETE', 'TRUNCATE'
                  ]) AS forbidden_privilege(name)
            WHERE has_table_privilege(
                      'gds_web_write', insert_only_table.name,
                      forbidden_privilege.name
                  )
       )
       OR EXISTS (
           SELECT 1
             FROM unnest(ARRAY[
                      'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                      'REFERENCES', 'TRIGGER', 'MAINTAIN'
                  ]) AS forbidden_privilege(name)
            WHERE has_table_privilege(
                      'gds_web_write', 'workflow.attribute_profile',
                      forbidden_privilege.name
                  )
          )
       OR EXISTS (
           SELECT 1
             FROM pg_catalog.pg_class AS relation
             JOIN pg_catalog.pg_namespace AS namespace_record
               ON namespace_record.oid = relation.relnamespace
            WHERE namespace_record.nspname = 'model'
              AND relation.relname IN (
                      'model_scope',
                      'model_revision_transaction'
                  )
              AND has_table_privilege(
                      'gds_web_write',
                      relation.oid,
                      'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
                  )
       )
       OR EXISTS (
           SELECT 1
             FROM pg_catalog.pg_attribute AS attribute
             JOIN pg_catalog.pg_class AS relation
               ON relation.oid = attribute.attrelid
             JOIN pg_catalog.pg_namespace AS namespace_record
               ON namespace_record.oid = relation.relnamespace
            CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE'])
                       AS privilege_name(value)
            WHERE namespace_record.nspname = 'model'
              AND relation.relname IN (
                      'model_scope',
                      'model_revision_transaction'
                  )
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
              AND has_column_privilege(
                      'gds_web_write',
                      relation.oid,
                      attribute.attname,
                      privilege_name.value
                  )
       OR EXISTS (
           SELECT 1
             FROM unnest(ARRAY[
                      'model_name',
                      'model_description',
                      'model_revision',
                      'silver_model_naming_instructions',
                      'silver_model_audit_columns_template',
                      'gold_model_naming_instructions',
                      'gold_model_technical_columns_template',
                      'gold_model_audit_columns_template',
                      'updated_time',
                      'updated_by'
                  ]) AS materializer_model_column(name)
            WHERE NOT has_column_privilege(
                      'gds_web_write', 'model.model',
                      materializer_model_column.name, 'UPDATE'
                  )
       )
       OR EXISTS (
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
                      'gds_web_write', 'model.model',
                      web_only_model_column.name, 'UPDATE'
                  )
       )
       ) THEN
        RAISE EXCEPTION 'runtime table privileges are invalid';
    END IF;

    IF has_schema_privilege('gds_app_write', 'application', 'USAGE')
       OR has_schema_privilege('gds_app_write', 'application', 'CREATE')
       OR has_schema_privilege('gds_mcp_runtime', 'application', 'USAGE')
       OR has_schema_privilege('gds_mcp_runtime', 'application', 'CREATE')
       OR NOT has_schema_privilege('gds_web_write', 'application', 'USAGE')
       OR has_schema_privilege('gds_web_write', 'application', 'CREATE')
       OR EXISTS (
           SELECT 1
             FROM pg_catalog.pg_class AS application_table
             JOIN pg_catalog.pg_namespace AS namespace_record
               ON namespace_record.oid = application_table.relnamespace
            WHERE namespace_record.nspname = 'application'
              AND application_table.relkind IN ('r', 'p')
              AND (
                  NOT has_table_privilege(
                      'gds_web_write', application_table.oid, 'SELECT'
                  )
                  OR EXISTS (
                      SELECT 1
                        FROM unnest(ARRAY[
                                 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                                 'REFERENCES', 'TRIGGER', 'MAINTAIN'
                             ]) AS privilege_name(value)
                       WHERE has_table_privilege(
                                 'gds_web_write',
                                 application_table.oid,
                                 privilege_name.value
                             )
                  )
                  OR EXISTS (
                      SELECT 1
                        FROM unnest(ARRAY[
                                 'gds_app_write', 'gds_mcp_runtime'
                             ]) AS runtime_role(value)
                        CROSS JOIN unnest(ARRAY[
                                 'SELECT', 'INSERT', 'UPDATE', 'DELETE',
                                 'TRUNCATE', 'REFERENCES', 'TRIGGER',
                                 'MAINTAIN'
                             ]) AS privilege_name(value)
                       WHERE has_table_privilege(
                                 runtime_role.value,
                                 application_table.oid,
                                 privilege_name.value
                             )
                  )
              )
       ) THEN
        RAISE EXCEPTION 'application runtime table privileges are invalid';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_class AS application_sequence
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = application_sequence.relnamespace
         WHERE namespace_record.nspname = 'application'
           AND application_sequence.relkind = 'S'
           AND EXISTS (
               SELECT 1
                 FROM unnest(ARRAY[
                          'public', 'gds_app_write', 'gds_mcp_runtime',
                          'gds_web_write'
                      ]) AS runtime_role(value)
                 CROSS JOIN unnest(ARRAY[
                          'USAGE', 'SELECT', 'UPDATE'
                      ]) AS privilege_name(value)
                WHERE has_sequence_privilege(
                          runtime_role.value,
                          application_sequence.oid,
                          privilege_name.value
                      )
           )
    ) THEN
        RAISE EXCEPTION 'application runtime sequence privileges are invalid';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS application_function
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = application_function.pronamespace
         WHERE namespace_record.nspname = 'application'
           AND EXISTS (
               SELECT 1
                 FROM unnest(ARRAY[
                          'public', 'gds_app_write', 'gds_mcp_runtime'
                      ]) AS runtime_role(value)
                WHERE has_function_privilege(
                          runtime_role.value,
                          application_function.oid,
                          'EXECUTE'
                      )
           )
    ) THEN
        RAISE EXCEPTION 'application private function privileges are invalid';
    END IF;

    SELECT count(*)
      INTO v_application_web_function_count
      FROM unnest(v_application_web_function_signatures)
           AS expected_function(signature)
     JOIN pg_catalog.pg_proc AS application_function
        ON application_function.oid = to_regprocedure(expected_function.signature)
     WHERE application_function.prosecdef
       AND application_function.proconfig =
           ARRAY['search_path=pg_catalog']::TEXT[]
       AND has_function_privilege(
               'gds_web_write', application_function.oid, 'EXECUTE'
           )
       AND NOT has_function_privilege(
               'gds_app_write', application_function.oid, 'EXECUTE'
           )
       AND NOT has_function_privilege(
               'public', application_function.oid, 'EXECUTE'
           );

    IF v_application_web_function_count <> 32 OR EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS application_function
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = application_function.pronamespace
         WHERE namespace_record.nspname = 'application'
           AND has_function_privilege(
                   'gds_web_write', application_function.oid, 'EXECUTE'
               )
           AND NOT EXISTS (
                   SELECT 1
                     FROM unnest(v_application_web_function_signatures)
                          AS expected_function(signature)
                    WHERE to_regprocedure(expected_function.signature) =
                          application_function.oid
               )
    ) THEN
        RAISE EXCEPTION 'application web function contract is invalid';
    END IF;

    IF NOT has_function_privilege(
        'gds_app_write',
        'security.authorize_tenant_operation(uuid,uuid,character varying,bigint,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.check_tenant_lock(uuid,uuid,character varying,bigint)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.acquire_tenant_lock(uuid,uuid,character varying,bigint,integer,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.renew_tenant_lock(uuid,uuid,character varying,bigint,integer)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.release_tenant_lock(uuid,uuid,character varying,bigint)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.override_tenant_lock(uuid,uuid,character varying,bigint,character varying)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'security.expire_tenant_locks(integer)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.create_metadata_change_set(uuid,uuid,character varying,bigint,uuid,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.begin_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,bigint,uuid,character varying,integer,integer,character,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.put_metadata_stage_chunk(uuid,uuid,character varying,bigint,uuid,uuid,character varying,integer,character,jsonb)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.commit_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,uuid,bigint,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.get_databricks_sql_connection_values(bigint,text)',
        'EXECUTE'
    ) OR NOT has_function_privilege(
        'gds_app_write',
        'mcp.runtime_readiness()',
        'EXECUTE'
    ) OR has_function_privilege(
        'gds_web_write',
        'mcp.get_databricks_sql_connection_values(bigint,text)',
        'EXECUTE'
    ) OR EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'workflow.list_tenant_visible_objects(bigint)',
                   'workflow.list_model_object_eligibility(bigint)',
                   'workflow.list_model_attribute_eligibility(bigint)',
                   'workflow.list_code_generation_target_context(bigint,character varying)'
               ]) AS web_workflow_function(signature)
         WHERE NOT has_function_privilege(
                   'gds_web_write',
                   web_workflow_function.signature,
                   'EXECUTE'
               )
    ) OR EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS mcp_function
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = mcp_function.pronamespace
         WHERE namespace_record.nspname = 'mcp'
           AND has_function_privilege(
                   'gds_web_write',
                   mcp_function.oid,
                   'EXECUTE'
               )
           AND NOT EXISTS (
                   SELECT 1
                     FROM unnest(ARRAY[
                              'mcp.create_metadata_change_set(uuid,uuid,character varying,bigint,uuid,uuid)',
                              'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
                              'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                              'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                              'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
                              'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)'
                          ]) AS allowed_web_mcp_function(signature)
                    WHERE to_regprocedure(
                              allowed_web_mcp_function.signature
                          ) = mcp_function.oid
               )
    ) OR EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS mcp_function
          JOIN pg_catalog.pg_namespace AS namespace_record
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
    ) OR EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'mcp.create_metadata_change_set(uuid,uuid,character varying,bigint,uuid,uuid)',
                   'mcp.stage_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
                   'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                   'mcp.record_metadata_change_set_validation(uuid,uuid,character varying,bigint,uuid,bigint,boolean,character,jsonb,uuid,uuid)',
                   'mcp.apply_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,character,uuid)',
                   'mcp.archive_metadata_change_set(uuid,uuid,character varying,bigint,uuid,bigint,uuid)'
               ]) AS web_metadata_function(signature)
         WHERE NOT has_function_privilege(
                   'gds_web_write',
                   web_metadata_function.signature,
                   'EXECUTE'
               )
    ) OR EXISTS (
        SELECT 1
          FROM unnest(ARRAY[
                   'mcp.begin_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,bigint,uuid,character varying,integer,integer,character,uuid)',
                   'mcp.put_metadata_stage_chunk(uuid,uuid,character varying,bigint,uuid,uuid,character varying,integer,character,jsonb)',
                   'mcp.commit_metadata_stage_batch(uuid,uuid,character varying,bigint,uuid,uuid,bigint,uuid)'
               ]) AS web_forbidden_metadata_function(signature)
         WHERE has_function_privilege(
                   'gds_web_write',
                   web_forbidden_metadata_function.signature,
                   'EXECUTE'
               )
    ) THEN
        RAISE EXCEPTION 'runtime function privileges are invalid';
    END IF;
END;
$verify_install$;

SELECT '1.0.0' AS schema_version,
       'gds_mcp_runtime' AS runtime_login,
       'gds_app_write' AS activated_role,
       'passed' AS verification_status;
