-- DESTRUCTIVE MODEL RESET TEMPLATE.
--
-- Copy this file outside the repository and replace
-- __REPLACE_WITH_MODEL_ID__ with one positive Model ID. The unchanged template
-- always fails before deleting data. Run only in a maintenance window as the
-- database owner with psql -X -v ON_ERROR_STOP=1.
--
-- This removes the Model, model-owned workflow and Model Change Set history,
-- model-specific MCP audit rows, generated Code, Validations, Bindings, and
-- bound Silver/Gold Objects. It removes ingestion/process records referencing
-- those Objects and related groups only when they become unused. Model Input
-- Objects are preserved unless also bound. Shared bound Objects cause failure.

DO $model_cleanup$
DECLARE
    v_model_id_text TEXT := '__REPLACE_WITH_MODEL_ID__';
    v_model_id BIGINT;
    v_model_name VARCHAR(255);
    v_remaining RECORD;
    v_has_remaining BOOLEAN;
    v_bound_object_count INTEGER;
BEGIN
    IF v_model_id_text LIKE '%__REPLACE_%' THEN
        RAISE EXCEPTION 'replace the Model cleanup Model ID placeholder';
    END IF;
    IF v_model_id_text !~ '^[1-9][0-9]*$' THEN
        RAISE EXCEPTION 'Model cleanup requires one positive numeric Model ID';
    END IF;
    BEGIN
        v_model_id := v_model_id_text::BIGINT;
    EXCEPTION
        WHEN numeric_value_out_of_range THEN
            RAISE EXCEPTION 'Model cleanup Model ID is outside the BIGINT range';
    END;

    PERFORM set_config('lock_timeout', '10s', TRUE);

    SELECT target_model.model_name
      INTO v_model_name
      FROM model.model AS target_model
     WHERE target_model.model_id = v_model_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Model % does not exist', v_model_id;
    END IF;

    CREATE TEMPORARY TABLE gds_cleanup_bound_object (
        object_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_bound_object (object_id)
    SELECT DISTINCT binding.object_id
      FROM workflow.model_object_binding AS binding
     WHERE binding.model_id = v_model_id;

    SELECT count(*)::INTEGER
      INTO v_bound_object_count
      FROM pg_temp.gds_cleanup_bound_object;

    IF EXISTS (
        SELECT 1
          FROM workflow.model_object_binding AS other_binding
          JOIN pg_temp.gds_cleanup_bound_object AS target
            ON target.object_id = other_binding.object_id
         WHERE other_binding.model_id <> v_model_id
    ) OR EXISTS (
        SELECT 1
          FROM model.model_input_scope AS other_scope
          JOIN pg_temp.gds_cleanup_bound_object AS target
            ON target.object_id = other_scope.object_id
         WHERE other_scope.model_id <> v_model_id
    ) THEN
        RAISE EXCEPTION
            'Model % has a bound Object used by another Model; cleanup refused',
            v_model_id;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_temp.gds_cleanup_bound_object AS target
          JOIN core.object AS object_record
            ON object_record.object_id = target.object_id
          JOIN reference.zone AS zone_record
            ON zone_record.zone_id = object_record.zone_id
         WHERE lower(btrim(zone_record.zone_code)) NOT IN ('silver', 'gold')
    ) THEN
        RAISE EXCEPTION
            'Model % binds a non-Silver/Gold Object; cleanup refused',
            v_model_id;
    END IF;

    CREATE TEMPORARY TABLE gds_cleanup_bound_attribute (
        attribute_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_bound_attribute (attribute_id)
    SELECT attribute.attribute_id
      FROM core.attribute AS attribute
      JOIN pg_temp.gds_cleanup_bound_object AS target
        ON target.object_id = attribute.object_id;

    CREATE TEMPORARY TABLE gds_cleanup_workflow_run (
        workflow_run_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_workflow_run (workflow_run_id)
    SELECT run.workflow_run_id
      FROM application.workflow_run AS run
     WHERE run.model_id = v_model_id;

    CREATE TEMPORARY TABLE gds_cleanup_model_change_set (
        model_change_set_id UUID PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_model_change_set (model_change_set_id)
    SELECT change_set.model_change_set_id
      FROM mcp.model_change_set AS change_set
     WHERE change_set.model_id = v_model_id;

    CREATE TEMPORARY TABLE gds_cleanup_model_stage_batch (
        stage_batch_id UUID PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_model_stage_batch (stage_batch_id)
    SELECT batch.stage_batch_id
      FROM mcp.model_stage_batch AS batch
     WHERE batch.model_id = v_model_id;

    CREATE TEMPORARY TABLE gds_cleanup_ingestion_mapping (
        ingestion_object_mapping_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_ingestion_mapping (
        ingestion_object_mapping_id
    )
    SELECT mapping.ingestion_object_mapping_id
      FROM core.ingestion_object_mapping AS mapping
     WHERE mapping.source_object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           )
        OR mapping.target_object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           );

    CREATE TEMPORARY TABLE gds_cleanup_process_group (
        process_group_id BIGINT PRIMARY KEY,
        copy_group_id BIGINT NOT NULL
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_process_group (
        process_group_id,
        copy_group_id
    )
    SELECT DISTINCT process_group.process_group_id,
           process_group.copy_group_id
      FROM core.process AS process
      JOIN core.process_group AS process_group
        ON process_group.process_group_id = process.process_group_id
     WHERE process.object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           );

    CREATE TEMPORARY TABLE gds_cleanup_copy_group_candidate (
        copy_group_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_copy_group_candidate (copy_group_id)
    SELECT DISTINCT copy_record.copy_group_id
      FROM core.copy AS copy_record
     WHERE copy_record.ingestion_object_mapping_id IN (
               SELECT target.ingestion_object_mapping_id
                 FROM pg_temp.gds_cleanup_ingestion_mapping AS target
           )
    UNION
    SELECT process_group.copy_group_id
      FROM pg_temp.gds_cleanup_process_group AS process_group;

    -- Bypass only named immutable-history guards. Foreign-key triggers stay on.
    EXECUTE 'ALTER TABLE mcp.tool_call_log DISABLE TRIGGER reject_tool_call_log_mutation';
    EXECUTE 'ALTER TABLE model.model_event_log DISABLE TRIGGER reject_model_event_log_mutation';
    EXECUTE 'ALTER TABLE application.workflow_run DISABLE TRIGGER guard_workflow_run';
    EXECUTE 'ALTER TABLE application.workflow_run_object_selection DISABLE TRIGGER guard_workflow_run_object_selection';
    EXECUTE 'ALTER TABLE application.workflow_run_system_selection DISABLE TRIGGER guard_workflow_run_system_selection';
    EXECUTE 'ALTER TABLE application.workflow_run_mapping_target_selection DISABLE TRIGGER guard_workflow_run_mapping_target_selection';
    EXECUTE 'ALTER TABLE application.workflow_run_prompt_snapshot DISABLE TRIGGER guard_workflow_run_prompt_snapshot';

    DELETE FROM mcp.tool_call_log AS log
     WHERE log.input_metadata ->> 'model_id' = v_model_id::TEXT
        OR EXISTS (
               SELECT 1
                 FROM pg_temp.gds_cleanup_workflow_run AS target
                WHERE log.input_metadata ->> 'workflow_run_id' =
                      target.workflow_run_id::TEXT
           )
        OR EXISTS (
               SELECT 1
                 FROM pg_temp.gds_cleanup_model_change_set AS target
                WHERE log.input_metadata ->> 'model_change_set_id' =
                      target.model_change_set_id::TEXT
           )
        OR EXISTS (
               SELECT 1
                 FROM pg_temp.gds_cleanup_model_stage_batch AS target
                WHERE log.input_metadata ->> 'stage_batch_id' =
                      target.stage_batch_id::TEXT
           );

    DELETE FROM mcp.model_stage_chunk
     WHERE stage_batch_id IN (
               SELECT target.stage_batch_id
                 FROM pg_temp.gds_cleanup_model_stage_batch AS target
           );
    DELETE FROM mcp.model_stage_payload_chunk
     WHERE stage_batch_id IN (
               SELECT target.stage_batch_id
                 FROM pg_temp.gds_cleanup_model_stage_batch AS target
           );
    DELETE FROM mcp.model_change_set_event WHERE model_id = v_model_id;
    DELETE FROM mcp.model_stage_batch WHERE model_id = v_model_id;
    DELETE FROM mcp.model_change_set WHERE model_id = v_model_id;

    -- Break the nullable Workflow Run/Event Log cycle.
    UPDATE application.workflow_run
       SET authoring_no_op_model_event_log_id = NULL
     WHERE model_id = v_model_id;
    UPDATE model.model_event_log
       SET workflow_run_id = NULL
     WHERE model_id = v_model_id;

    DELETE FROM application.workflow_run_prompt_snapshot
     WHERE model_id = v_model_id;
    DELETE FROM application.workflow_run_mapping_target_selection
     WHERE model_id = v_model_id;
    DELETE FROM application.workflow_run_object_selection
     WHERE model_id = v_model_id;
    DELETE FROM application.workflow_run_system_selection
     WHERE model_id = v_model_id;

    DELETE FROM workflow.generated_code_source_system AS source_system
     WHERE source_system.generated_code_id IN (
               SELECT code.generated_code_id
                 FROM workflow.generated_code AS code
                 JOIN workflow.model_object_binding AS binding
                   ON binding.model_object_binding_id =
                      code.model_object_binding_id
                WHERE binding.model_id = v_model_id
           );
    DELETE FROM workflow.generated_code AS code
     WHERE code.model_object_binding_id IN (
               SELECT binding.model_object_binding_id
                 FROM workflow.model_object_binding AS binding
                WHERE binding.model_id = v_model_id
           );

    DELETE FROM workflow.validation_check AS validation_check
     WHERE validation_check.validation_group_id IN (
               SELECT validation_group.validation_group_id
                 FROM workflow.validation_group AS validation_group
                WHERE validation_group.model_id = v_model_id
           );
    DELETE FROM workflow.validation_group WHERE model_id = v_model_id;

    DELETE FROM workflow.mapping_attribute AS mapping_attribute
     WHERE mapping_attribute.mapping_object_id IN (
               SELECT mapping_object.mapping_object_id
                 FROM workflow.mapping_object AS mapping_object
                WHERE mapping_object.model_id = v_model_id
           )
        OR mapping_attribute.model_attribute_binding_id IN (
               SELECT attribute_binding.model_attribute_binding_id
                 FROM workflow.model_attribute_binding AS attribute_binding
                 JOIN workflow.model_object_binding AS object_binding
                   ON object_binding.model_object_binding_id =
                      attribute_binding.model_object_binding_id
                WHERE object_binding.model_id = v_model_id
           );
    DELETE FROM workflow.mapping_object WHERE model_id = v_model_id;
    DELETE FROM workflow.mapping_source_system_dependency
     WHERE model_id = v_model_id;

    DELETE FROM workflow.dimensional_attribute_source_mapping
     WHERE model_id = v_model_id;
    DELETE FROM workflow.dimensional_entity_source_mapping
     WHERE model_id = v_model_id;
    DELETE FROM workflow.logical_attribute_source_mapping
     WHERE model_id = v_model_id;
    DELETE FROM workflow.logical_entity_source_mapping
     WHERE model_id = v_model_id;

    DELETE FROM workflow.model_attribute_binding AS attribute_binding
     WHERE attribute_binding.model_object_binding_id IN (
               SELECT object_binding.model_object_binding_id
                 FROM workflow.model_object_binding AS object_binding
                WHERE object_binding.model_id = v_model_id
           );
    DELETE FROM workflow.model_object_binding WHERE model_id = v_model_id;

    DELETE FROM workflow.dimensional_relationship WHERE model_id = v_model_id;
    DELETE FROM workflow.dimensional_entity_submodel WHERE model_id = v_model_id;
    DELETE FROM workflow.dimensional_attribute WHERE model_id = v_model_id;
    DELETE FROM workflow.dimensional_entity WHERE model_id = v_model_id;
    DELETE FROM workflow.dimensional_submodel WHERE model_id = v_model_id;

    DELETE FROM workflow.logical_relationship WHERE model_id = v_model_id;
    DELETE FROM workflow.logical_entity_submodel WHERE model_id = v_model_id;
    DELETE FROM workflow.logical_attribute WHERE model_id = v_model_id;
    DELETE FROM workflow.logical_entity WHERE model_id = v_model_id;
    DELETE FROM workflow.logical_submodel WHERE model_id = v_model_id;

    DELETE FROM workflow.conceptual_support WHERE model_id = v_model_id;
    DELETE FROM workflow.conceptual_relationship WHERE model_id = v_model_id;
    DELETE FROM workflow.conceptual_object WHERE model_id = v_model_id;
    DELETE FROM workflow.analysis_result WHERE model_id = v_model_id;
    DELETE FROM workflow.attribute_profile WHERE model_id = v_model_id;

    DELETE FROM model.modeling_assertion_record WHERE model_id = v_model_id;
    DELETE FROM model.modeling_assertion_document WHERE model_id = v_model_id;
    DELETE FROM application.prompt_assignment WHERE model_id = v_model_id;
    DELETE FROM model.model_revision_transaction WHERE model_id = v_model_id;
    DELETE FROM model.model_input_scope WHERE model_id = v_model_id;
    DELETE FROM model.model_event_log WHERE model_id = v_model_id;
    DELETE FROM application.workflow_run WHERE model_id = v_model_id;

    -- Remove bound physical metadata and its ingestion/process dependants.
    DELETE FROM core.process AS process
     WHERE process.object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           );
    DELETE FROM core.copy AS copy_record
     WHERE copy_record.ingestion_object_mapping_id IN (
               SELECT target.ingestion_object_mapping_id
                 FROM pg_temp.gds_cleanup_ingestion_mapping AS target
           );
    DELETE FROM core.ingestion_attribute_mapping AS attribute_mapping
     WHERE attribute_mapping.ingestion_object_mapping_id IN (
               SELECT target.ingestion_object_mapping_id
                 FROM pg_temp.gds_cleanup_ingestion_mapping AS target
           )
        OR attribute_mapping.source_object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           )
        OR attribute_mapping.target_object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           );
    DELETE FROM core.ingestion_object_mapping AS object_mapping
     WHERE object_mapping.ingestion_object_mapping_id IN (
               SELECT target.ingestion_object_mapping_id
                 FROM pg_temp.gds_cleanup_ingestion_mapping AS target
           );

    DELETE FROM core.process_group AS process_group
     WHERE process_group.process_group_id IN (
               SELECT target.process_group_id
                 FROM pg_temp.gds_cleanup_process_group AS target
           )
       AND NOT EXISTS (
               SELECT 1
                 FROM core.process AS process
                WHERE process.process_group_id = process_group.process_group_id
           );

    CREATE TEMPORARY TABLE gds_cleanup_copy_group (
        copy_group_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_copy_group (copy_group_id)
    SELECT candidate.copy_group_id
      FROM pg_temp.gds_cleanup_copy_group_candidate AS candidate
     WHERE NOT EXISTS (
               SELECT 1
                 FROM core.copy AS copy_record
                WHERE copy_record.copy_group_id = candidate.copy_group_id
           )
       AND NOT EXISTS (
               SELECT 1
                 FROM core.process_group AS process_group
                WHERE process_group.copy_group_id = candidate.copy_group_id
           );

    CREATE TEMPORARY TABLE gds_cleanup_member_group (
        member_group_id BIGINT PRIMARY KEY
    ) ON COMMIT DROP;
    INSERT INTO pg_temp.gds_cleanup_member_group (member_group_id)
    SELECT DISTINCT control.member_group_id
      FROM core.copy_group_control AS control
     WHERE control.copy_group_id IN (
               SELECT target.copy_group_id
                 FROM pg_temp.gds_cleanup_copy_group AS target
           )
       AND control.member_group_id IS NOT NULL;

    DELETE FROM core.copy_group_control AS control
     WHERE control.copy_group_id IN (
               SELECT target.copy_group_id
                 FROM pg_temp.gds_cleanup_copy_group AS target
           );
    DELETE FROM core.copy_group AS copy_group
     WHERE copy_group.copy_group_id IN (
               SELECT target.copy_group_id
                 FROM pg_temp.gds_cleanup_copy_group AS target
           );
    DELETE FROM core.member_group AS member_group
     WHERE member_group.member_group_id IN (
               SELECT target.member_group_id
                 FROM pg_temp.gds_cleanup_member_group AS target
           )
       AND NOT EXISTS (
               SELECT 1
                 FROM core.copy_group_control AS control
                WHERE control.member_group_id = member_group.member_group_id
           );

    DELETE FROM core.attribute AS attribute
     WHERE attribute.attribute_id IN (
               SELECT target.attribute_id
                 FROM pg_temp.gds_cleanup_bound_attribute AS target
           );
    DELETE FROM core.object AS object_record
     WHERE object_record.object_id IN (
               SELECT target.object_id
                 FROM pg_temp.gds_cleanup_bound_object AS target
           );

    DELETE FROM model.model WHERE model_id = v_model_id;

    EXECUTE 'ALTER TABLE application.workflow_run_prompt_snapshot ENABLE TRIGGER guard_workflow_run_prompt_snapshot';
    EXECUTE 'ALTER TABLE application.workflow_run_mapping_target_selection ENABLE TRIGGER guard_workflow_run_mapping_target_selection';
    EXECUTE 'ALTER TABLE application.workflow_run_system_selection ENABLE TRIGGER guard_workflow_run_system_selection';
    EXECUTE 'ALTER TABLE application.workflow_run_object_selection ENABLE TRIGGER guard_workflow_run_object_selection';
    EXECUTE 'ALTER TABLE application.workflow_run ENABLE TRIGGER guard_workflow_run';
    EXECUTE 'ALTER TABLE model.model_event_log ENABLE TRIGGER reject_model_event_log_mutation';
    EXECUTE 'ALTER TABLE mcp.tool_call_log ENABLE TRIGGER reject_tool_call_log_mutation';

    -- Catch newly added tables that this template does not yet cover.
    FOR v_remaining IN
        SELECT namespace_record.nspname AS schema_name,
               relation.relname AS table_name
          FROM pg_catalog.pg_attribute AS attribute
          JOIN pg_catalog.pg_class AS relation
            ON relation.oid = attribute.attrelid
          JOIN pg_catalog.pg_namespace AS namespace_record
            ON namespace_record.oid = relation.relnamespace
         WHERE namespace_record.nspname IN (
                   'application', 'mcp', 'model', 'workflow'
               )
           AND relation.relkind IN ('r', 'p')
           AND attribute.attname = 'model_id'
           AND attribute.attnum > 0
           AND NOT attribute.attisdropped
         ORDER BY namespace_record.nspname, relation.relname
    LOOP
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %I.%I WHERE model_id = $1)',
            v_remaining.schema_name,
            v_remaining.table_name
        )
        INTO v_has_remaining
        USING v_model_id;
        IF v_has_remaining THEN
            RAISE EXCEPTION
                'Model cleanup left rows in %.%',
                v_remaining.schema_name,
                v_remaining.table_name;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM core.object AS object_record
          JOIN pg_temp.gds_cleanup_bound_object AS target
            ON target.object_id = object_record.object_id
    ) OR EXISTS (
        SELECT 1
          FROM core.attribute AS attribute
          JOIN pg_temp.gds_cleanup_bound_attribute AS target
            ON target.attribute_id = attribute.attribute_id
    ) THEN
        RAISE EXCEPTION 'Model cleanup left bound physical metadata';
    END IF;

    RAISE NOTICE
        'Removed Model % (%) and % bound Silver/Gold Objects',
        v_model_id,
        v_model_name,
        v_bound_object_count;
END;
$model_cleanup$;
