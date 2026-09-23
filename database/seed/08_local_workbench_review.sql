-- Local-only review data for the complete GDS Workbench journey.
-- The database-name guard prevents this seed from running outside the disposable
-- stack created by web_app/local/run.py.

DO $local_workbench_review$
DECLARE
    v_tenant_id BIGINT;
    v_system_id BIGINT;
    v_source_connection_id BIGINT;
    v_gds_connection_id BIGINT;
    v_gds_catalog TEXT;
    v_object_type_id BIGINT;
    v_source_zone_id BIGINT;
    v_bronze_zone_id BIGINT;
    v_silver_zone_id BIGINT;
    v_gold_zone_id BIGINT;
    v_source_order_id BIGINT;
    v_bronze_customer_id BIGINT;
    v_bronze_order_id BIGINT;
    v_silver_customer_id BIGINT;
    v_silver_order_id BIGINT;
    v_gold_customer_id BIGINT;
    v_gold_order_id BIGINT;
    v_bronze_customer_key_id BIGINT;
    v_bronze_customer_name_id BIGINT;
    v_bronze_order_key_id BIGINT;
    v_bronze_order_customer_id BIGINT;
    v_bronze_order_date_id BIGINT;
    v_bronze_order_amount_id BIGINT;
    v_silver_customer_key_id BIGINT;
    v_silver_customer_name_id BIGINT;
    v_silver_order_key_id BIGINT;
    v_silver_order_customer_id BIGINT;
    v_silver_order_date_id BIGINT;
    v_silver_order_amount_id BIGINT;
    v_gold_customer_key_id BIGINT;
    v_gold_customer_name_id BIGINT;
    v_gold_order_key_id BIGINT;
    v_gold_order_customer_id BIGINT;
    v_gold_order_date_id BIGINT;
    v_gold_order_amount_id BIGINT;
    v_model_id BIGINT;
    v_document_id BIGINT;
    v_customer_assertion_id BIGINT;
    v_order_assertion_id BIGINT;
    v_conceptual_customer_id BIGINT;
    v_conceptual_order_id BIGINT;
    v_conceptual_relationship_id BIGINT;
    v_logical_submodel_id BIGINT;
    v_logical_customer_id BIGINT;
    v_logical_order_id BIGINT;
    v_logical_customer_key_id BIGINT;
    v_logical_customer_name_id BIGINT;
    v_logical_order_key_id BIGINT;
    v_logical_order_customer_id BIGINT;
    v_logical_order_date_id BIGINT;
    v_logical_order_amount_id BIGINT;
    v_logical_customer_source_id BIGINT;
    v_logical_order_source_id BIGINT;
    v_dimensional_submodel_id BIGINT;
    v_dimensional_customer_id BIGINT;
    v_dimensional_order_id BIGINT;
    v_dimensional_customer_key_id BIGINT;
    v_dimensional_customer_name_id BIGINT;
    v_dimensional_order_key_id BIGINT;
    v_dimensional_order_customer_id BIGINT;
    v_dimensional_order_date_id BIGINT;
    v_dimensional_order_amount_id BIGINT;
    v_dimensional_customer_source_id BIGINT;
    v_dimensional_order_source_id BIGINT;
    v_logical_customer_binding_id BIGINT;
    v_logical_order_binding_id BIGINT;
    v_dimensional_customer_binding_id BIGINT;
    v_dimensional_order_binding_id BIGINT;
    v_mapping_object_id BIGINT;
    v_validation_group_id BIGINT;
    v_principal_id BIGINT;
    v_workflow_run_id BIGINT;
    v_guide_id BIGINT;
    v_guide_content TEXT := 'Generate Databricks transformation SQL from the applied Mapping. Use registered schema.table identifiers and isolate each contributing System. Declare unqualified temporary views before use; end with an explicit target-column SELECT. The runtime writes the target and supplies framework-managed fields. Do not emit persistent DDL, DML, comments, Markdown, invented columns, joins, or reconciliation.';
BEGIN
    IF current_database() !~ '^gds_local_[0-9a-f]{12}$' THEN
        RAISE EXCEPTION 'local Workbench review seed requires a disposable gds_local database';
    END IF;

    SELECT tenant_id
      INTO STRICT v_tenant_id
      FROM core.tenant
     WHERE tenant_code = 'DEMO_TENANT';
    SELECT system_id
      INTO STRICT v_system_id
      FROM core.system
     WHERE system_code = 'DEMO_CUSTOMER_SYSTEM';
    SELECT connection_id
      INTO STRICT v_source_connection_id
      FROM core.connection
     WHERE connection_code = 'DEMO_SOURCE';
    SELECT connection.connection_id, tenant.tenant_catalog
      INTO STRICT v_gds_connection_id, v_gds_catalog
      FROM core.connection AS connection
      JOIN core.tenant AS tenant USING (tenant_id)
     WHERE connection.connection_code = 'DEMO_GDS';
    SELECT object_type_id
      INTO STRICT v_object_type_id
      FROM reference.object_type
     WHERE object_type_code = 'TABLE';
    SELECT zone_id INTO STRICT v_source_zone_id FROM reference.zone WHERE zone_code = 'source';
    SELECT zone_id INTO STRICT v_bronze_zone_id FROM reference.zone WHERE zone_code = 'bronze';
    SELECT zone_id INTO STRICT v_silver_zone_id FROM reference.zone WHERE zone_code = 'silver';
    SELECT zone_id INTO STRICT v_gold_zone_id FROM reference.zone WHERE zone_code = 'gold';

    UPDATE core.object
       SET object_description = CASE object_schema
               WHEN 'bronze_demo' THEN 'Raw customer records received from the customer platform.'
               WHEN 'silver_demo' THEN 'Conformed customer identities used across analytical products.'
               WHEN 'gold_demo' THEN 'Customer dimension with durable keys and descriptive attributes.'
               ELSE object_description
           END,
           batch_attribute_name = CASE
               WHEN object_schema = 'bronze_demo' THEN 'customer_id'
               ELSE batch_attribute_name
           END
     WHERE source_tenant_id = v_tenant_id
       AND object_name IN ('customer', 'dim_customer');

    UPDATE core.attribute AS attribute
       SET attribute_inferred_data_type = CASE attribute.attribute_name
               WHEN 'customer_id' THEN 'BIGINT'
               WHEN 'customer_name' THEN 'VARCHAR(200)'
           END
      FROM core.object AS object
     WHERE object.object_id = attribute.object_id
       AND object.source_tenant_id = v_tenant_id
       AND attribute.attribute_name IN ('customer_id', 'customer_name');

    INSERT INTO core.object (
        connection_id, source_tenant_id, object_schema, object_name,
        fc_object_schema, fc_object_name, object_description,
        batch_attribute_name, object_type_id, zone_id
    ) VALUES (
        v_source_connection_id, v_tenant_id, 'source_demo', 'orders',
        'public', 'orders', 'Source order headers captured by the commerce platform.',
        'order_date', v_object_type_id, v_source_zone_id
    ) RETURNING object_id INTO v_source_order_id;

    INSERT INTO core.object (
        connection_id, source_tenant_id, object_schema, object_name,
        object_description, batch_attribute_name, object_type_id, zone_id
    ) VALUES (
        v_gds_connection_id, v_tenant_id, 'bronze_demo', 'orders',
        'Raw order records received from the commerce platform.',
        'order_date', v_object_type_id, v_bronze_zone_id
    ) RETURNING object_id INTO v_bronze_order_id;

    INSERT INTO core.object (
        connection_id, source_tenant_id, object_schema, object_name,
        object_description, batch_attribute_name, object_type_id, zone_id
    ) VALUES (
        v_gds_connection_id, v_tenant_id, 'silver_demo', 'orders',
        'Conformed order transactions with governed customer references.',
        'order_date', v_object_type_id, v_silver_zone_id
    ) RETURNING object_id INTO v_silver_order_id;

    INSERT INTO core.object (
        connection_id, source_tenant_id, object_schema, object_name,
        object_description, batch_attribute_name, object_type_id, zone_id
    ) VALUES (
        v_gds_connection_id, v_tenant_id, 'gold_demo', 'fact_order',
        'Order fact table at one row per submitted order.',
        'order_date', v_object_type_id, v_gold_zone_id
    ) RETURNING object_id INTO v_gold_order_id;

    INSERT INTO core.attribute (
        object_id, attribute_name, fc_attribute_name, attribute_ordinal_position,
        attribute_description, attribute_data_type, attribute_inferred_data_type,
        attribute_nullability, is_natural_key, is_mapped
    )
    SELECT object_id,
           attribute_name,
           CASE WHEN object_id = v_source_order_id THEN attribute_name END,
           ordinal_position,
           description,
           data_type,
           data_type,
           is_nullable,
           is_natural_key,
           TRUE
      FROM (VALUES
          (v_source_order_id, 1, 'order_id', 'Stable order business identifier.', 'BIGINT', FALSE, TRUE),
          (v_source_order_id, 2, 'customer_id', 'Customer placing the order.', 'BIGINT', FALSE, FALSE),
          (v_source_order_id, 3, 'order_date', 'Date the order was submitted.', 'DATE', FALSE, FALSE),
          (v_source_order_id, 4, 'order_amount', 'Gross order amount in USD.', 'DECIMAL(18,2)', FALSE, FALSE),
          (v_bronze_order_id, 1, 'order_id', 'Stable order business identifier.', 'BIGINT', FALSE, TRUE),
          (v_bronze_order_id, 2, 'customer_id', 'Customer placing the order.', 'BIGINT', FALSE, FALSE),
          (v_bronze_order_id, 3, 'order_date', 'Date the order was submitted.', 'DATE', FALSE, FALSE),
          (v_bronze_order_id, 4, 'order_amount', 'Gross order amount in USD.', 'DECIMAL(18,2)', FALSE, FALSE),
          (v_silver_order_id, 1, 'order_id', 'Stable order business identifier.', 'BIGINT', FALSE, TRUE),
          (v_silver_order_id, 2, 'customer_id', 'Governed customer business identifier.', 'BIGINT', FALSE, FALSE),
          (v_silver_order_id, 3, 'order_date', 'Date the order was submitted.', 'DATE', FALSE, FALSE),
          (v_silver_order_id, 4, 'order_amount', 'Gross order amount in USD.', 'DECIMAL(18,2)', FALSE, FALSE),
          (v_gold_order_id, 1, 'order_id', 'Degenerate order identifier.', 'BIGINT', FALSE, TRUE),
          (v_gold_order_id, 2, 'customer_id', 'Customer dimension lookup key.', 'BIGINT', FALSE, FALSE),
          (v_gold_order_id, 3, 'order_date', 'Order activity date.', 'DATE', FALSE, FALSE),
          (v_gold_order_id, 4, 'order_amount', 'Additive gross order amount.', 'DECIMAL(18,2)', FALSE, FALSE)
      ) AS seed(
          object_id, ordinal_position, attribute_name, description,
          data_type, is_nullable, is_natural_key
      );

    SELECT object_id INTO STRICT v_bronze_customer_id
      FROM core.object WHERE source_tenant_id = v_tenant_id
       AND object_schema = 'bronze_demo' AND object_name = 'customer';
    SELECT object_id INTO STRICT v_silver_customer_id
      FROM core.object WHERE source_tenant_id = v_tenant_id
       AND object_schema = 'silver_demo' AND object_name = 'customer';
    SELECT object_id INTO STRICT v_gold_customer_id
      FROM core.object WHERE source_tenant_id = v_tenant_id
       AND object_schema = 'gold_demo' AND object_name = 'dim_customer';

    INSERT INTO core.ingestion_object_mapping (source_object_id, target_object_id)
    VALUES
        (v_source_order_id, v_bronze_order_id),
        (v_bronze_order_id, v_silver_order_id),
        (v_silver_order_id, v_gold_order_id);

    INSERT INTO core.ingestion_attribute_mapping (
        ingestion_object_mapping_id, source_object_id, target_object_id,
        source_attribute_id, target_attribute_id
    )
    SELECT object_mapping.ingestion_object_mapping_id,
           object_mapping.source_object_id,
           object_mapping.target_object_id,
           source_attribute.attribute_id,
           target_attribute.attribute_id
      FROM core.ingestion_object_mapping AS object_mapping
      JOIN core.attribute AS source_attribute
        ON source_attribute.object_id = object_mapping.source_object_id
      JOIN core.attribute AS target_attribute
        ON target_attribute.object_id = object_mapping.target_object_id
       AND target_attribute.attribute_name = source_attribute.attribute_name
     WHERE object_mapping.source_object_id IN (
           v_source_order_id, v_bronze_order_id, v_silver_order_id
       );

    SELECT attribute_id INTO STRICT v_bronze_customer_key_id FROM core.attribute
     WHERE object_id = v_bronze_customer_id AND attribute_name = 'customer_id';
    SELECT attribute_id INTO STRICT v_bronze_customer_name_id FROM core.attribute
     WHERE object_id = v_bronze_customer_id AND attribute_name = 'customer_name';
    SELECT attribute_id INTO STRICT v_bronze_order_key_id FROM core.attribute
     WHERE object_id = v_bronze_order_id AND attribute_name = 'order_id';
    SELECT attribute_id INTO STRICT v_bronze_order_customer_id FROM core.attribute
     WHERE object_id = v_bronze_order_id AND attribute_name = 'customer_id';
    SELECT attribute_id INTO STRICT v_bronze_order_date_id FROM core.attribute
     WHERE object_id = v_bronze_order_id AND attribute_name = 'order_date';
    SELECT attribute_id INTO STRICT v_bronze_order_amount_id FROM core.attribute
     WHERE object_id = v_bronze_order_id AND attribute_name = 'order_amount';
    SELECT attribute_id INTO STRICT v_silver_customer_key_id FROM core.attribute
     WHERE object_id = v_silver_customer_id AND attribute_name = 'customer_id';
    SELECT attribute_id INTO STRICT v_silver_customer_name_id FROM core.attribute
     WHERE object_id = v_silver_customer_id AND attribute_name = 'customer_name';
    SELECT attribute_id INTO STRICT v_silver_order_key_id FROM core.attribute
     WHERE object_id = v_silver_order_id AND attribute_name = 'order_id';
    SELECT attribute_id INTO STRICT v_silver_order_customer_id FROM core.attribute
     WHERE object_id = v_silver_order_id AND attribute_name = 'customer_id';
    SELECT attribute_id INTO STRICT v_silver_order_date_id FROM core.attribute
     WHERE object_id = v_silver_order_id AND attribute_name = 'order_date';
    SELECT attribute_id INTO STRICT v_silver_order_amount_id FROM core.attribute
     WHERE object_id = v_silver_order_id AND attribute_name = 'order_amount';
    SELECT attribute_id INTO STRICT v_gold_customer_key_id FROM core.attribute
     WHERE object_id = v_gold_customer_id AND attribute_name = 'customer_id';
    SELECT attribute_id INTO STRICT v_gold_customer_name_id FROM core.attribute
     WHERE object_id = v_gold_customer_id AND attribute_name = 'customer_name';
    SELECT attribute_id INTO STRICT v_gold_order_key_id FROM core.attribute
     WHERE object_id = v_gold_order_id AND attribute_name = 'order_id';
    SELECT attribute_id INTO STRICT v_gold_order_customer_id FROM core.attribute
     WHERE object_id = v_gold_order_id AND attribute_name = 'customer_id';
    SELECT attribute_id INTO STRICT v_gold_order_date_id FROM core.attribute
     WHERE object_id = v_gold_order_id AND attribute_name = 'order_date';
    SELECT attribute_id INTO STRICT v_gold_order_amount_id FROM core.attribute
     WHERE object_id = v_gold_order_id AND attribute_name = 'order_amount';

    INSERT INTO model.model (
        tenant_id, model_name, model_description,
        silver_model_naming_instructions, gold_model_naming_instructions
    ) VALUES (
        v_tenant_id,
        'Customer Orders 360',
        'Review model connecting customer identities, orders, conformed Silver outputs, and a Gold sales mart.',
        'Use snake_case names and preserve stable business identifiers.',
        'Use dim_ and fact_ prefixes with explicit grain.'
    ) RETURNING model_id INTO v_model_id;

    INSERT INTO model.model_input_scope (model_id, object_id)
    VALUES
        (v_model_id, v_bronze_customer_id),
        (v_model_id, v_bronze_order_id);

    INSERT INTO workflow.attribute_profile (
        model_id, attribute_id, object_id, source_context_digest,
        row_count, non_null_count, null_count, blank_count, distinct_count,
        min_data_length, max_data_length, avg_data_length,
        percent_populated, percent_duplicates, percent_null,
        percent_blank, percent_distinct
    ) VALUES
        (v_model_id, v_bronze_customer_key_id, v_bronze_customer_id, repeat('a', 64),
         125000, 125000, 0, 0, 125000, 1, 12, 8.4, 100, 0, 0, 0, 100),
        (v_model_id, v_bronze_customer_name_id, v_bronze_customer_id, repeat('a', 64),
         125000, 124820, 180, 24, 93210, 1, 98, 24.7, 99.856, 25.326, 0.144, 0.0192, 74.677),
        (v_model_id, v_bronze_order_key_id, v_bronze_order_id, repeat('a', 64),
         842310, 842310, 0, 0, 842310, 1, 14, 10.2, 100, 0, 0, 0, 100),
        (v_model_id, v_bronze_order_customer_id, v_bronze_order_id, repeat('a', 64),
         842310, 842310, 0, 0, 124996, 1, 12, 8.3, 100, 85.160, 0, 0, 14.840),
        (v_model_id, v_bronze_order_date_id, v_bronze_order_id, repeat('a', 64),
         842310, 842310, 0, 0, 730, 10, 10, 10, 100, 99.913, 0, 0, 0.087),
        (v_model_id, v_bronze_order_amount_id, v_bronze_order_id, repeat('a', 64),
         842310, 842104, 206, 0, 415892, 1, 12, 6.8, 99.976, 50.614, 0.024, 0, 49.386);

    INSERT INTO workflow.analysis_result (
        model_id, validation_source_context_digest,
        from_object_id, from_attribute_id, to_object_id, to_attribute_id,
        relationship_kind, relationship_confidence, relationship_basis,
        validation_policy_version, validation_policy_digest, validation_result,
        validation_source_non_null_count, validation_source_distinct_count,
        validation_target_non_null_count, validation_target_distinct_count,
        validation_source_missing_target_count, validation_unused_target_count,
        validation_duplicate_target_key_count
    ) VALUES (
        v_model_id, repeat('b', 64),
        v_bronze_order_id, v_bronze_order_customer_id,
        v_bronze_customer_id, v_bronze_customer_key_id,
        'foreign_key', 'high',
        'Order customer identifiers are contained in the unique Customer identifier set.',
        '1.0.0', repeat('c', 64), 'supported',
        842310, 124996, 125000, 125000, 0, 4, 0
    );

    INSERT INTO model.modeling_assertion_document (
        model_id, tenant_id, system_id, modeling_assertion_document_name,
        modeling_assertion_document_type, modeling_assertion_document_description
    ) VALUES (
        v_model_id, v_tenant_id, v_system_id, 'Customer Orders business rules',
        'business_rules', 'Review-ready customer and order modeling decisions.'
    ) RETURNING modeling_assertion_document_id INTO v_document_id;

    INSERT INTO model.modeling_assertion_record (
        model_id, modeling_assertion_document_id,
        modeling_assertion_record_key, modeling_assertion_record_type,
        modeling_assertion_text, modeling_assertion_details,
        modeling_assertion_applicable_layers, modeling_assertion_confidence
    ) VALUES (
        v_model_id, v_document_id, 'customer.grain', 'grain_rule',
        'One Customer record represents one durable customer identity.',
        '{"owner":"Customer Data Product","review_status":"approved"}',
        ARRAY['conceptual', 'logical', 'dimensional', 'mapping'], 'high'
    ) RETURNING modeling_assertion_record_id INTO v_customer_assertion_id;

    INSERT INTO model.modeling_assertion_record (
        model_id, modeling_assertion_document_id,
        modeling_assertion_record_key, modeling_assertion_record_type,
        modeling_assertion_text, modeling_assertion_details,
        modeling_assertion_applicable_layers, modeling_assertion_confidence
    ) VALUES (
        v_model_id, v_document_id, 'order.customer', 'relationship_rule',
        'Every submitted Order belongs to exactly one Customer.',
        '{"owner":"Commerce Data Product","review_status":"approved"}',
        ARRAY['analysis', 'conceptual', 'logical', 'dimensional', 'mapping'], 'high'
    ) RETURNING modeling_assertion_record_id INTO v_order_assertion_id;

    INSERT INTO workflow.conceptual_object (
        model_id, conceptual_object_name, conceptual_object_definition,
        conceptual_object_type, conceptual_object_grain,
        conceptual_object_aliases, conceptual_object_confidence
    ) VALUES (
        v_model_id, 'Customer', 'A person or organization that places Orders.',
        'business_entity', 'One durable customer identity', ARRAY['Client'], 'high'
    ) RETURNING conceptual_object_id INTO v_conceptual_customer_id;

    INSERT INTO workflow.conceptual_object (
        model_id, conceptual_object_name, conceptual_object_definition,
        conceptual_object_type, conceptual_object_grain,
        conceptual_object_aliases, conceptual_object_confidence
    ) VALUES (
        v_model_id, 'Order', 'A commercial request submitted by a Customer.',
        'business_event', 'One submitted order', ARRAY['Purchase'], 'high'
    ) RETURNING conceptual_object_id INTO v_conceptual_order_id;

    INSERT INTO workflow.conceptual_relationship (
        model_id, from_conceptual_object_id, to_conceptual_object_id,
        conceptual_relationship_name, conceptual_relationship_type,
        conceptual_relationship_definition, conceptual_relationship_cardinality,
        conceptual_relationship_basis, conceptual_relationship_cardinality_basis,
        conceptual_relationship_confidence
    ) VALUES (
        v_model_id, v_conceptual_order_id, v_conceptual_customer_id,
        'Order belongs to Customer', 'ownership',
        'Each Order is placed by one Customer.', 'many_to_one',
        'Supported by the Customer identifier relationship and business rule.',
        'Many Orders may share one Customer identifier.', 'high'
    ) RETURNING conceptual_relationship_id INTO v_conceptual_relationship_id;

    INSERT INTO workflow.conceptual_support (
        model_id, supported_artifact_type, conceptual_object_id,
        support_source_type, source_object_id, conceptual_support_role,
        conceptual_support_reason, conceptual_support_confidence
    ) VALUES
        (v_model_id, 'conceptual_object', v_conceptual_customer_id,
         'object', v_bronze_customer_id, 'primary evidence',
         'Customer records demonstrate the governed identity.', 'high'),
        (v_model_id, 'conceptual_object', v_conceptual_order_id,
         'object', v_bronze_order_id, 'primary evidence',
         'Order records demonstrate the transaction grain.', 'high');

    INSERT INTO workflow.conceptual_support (
        model_id, supported_artifact_type, conceptual_relationship_id,
        support_source_type, modeling_assertion_record_id,
        conceptual_support_role, conceptual_support_reason,
        conceptual_support_confidence
    ) VALUES (
        v_model_id, 'conceptual_relationship', v_conceptual_relationship_id,
        'assertion', v_order_assertion_id, 'business rule',
        'The approved rule defines the Customer ownership relationship.', 'high'
    );

    INSERT INTO workflow.logical_submodel (
        model_id, logical_submodel_name, logical_submodel_definition
    ) VALUES (
        v_model_id, 'Customer Commerce', 'Customer and Order entities for commerce analytics.'
    ) RETURNING logical_submodel_id INTO v_logical_submodel_id;

    INSERT INTO workflow.logical_entity (
        model_id, logical_entity_name, logical_entity_definition,
        logical_entity_type, logical_entity_grain,
        logical_entity_dependency_order, logical_entity_confidence
    ) VALUES (
        v_model_id, 'Customer', 'A conformed durable customer identity.',
        'core', 'One Customer', 0, 'high'
    ) RETURNING logical_entity_id INTO v_logical_customer_id;

    INSERT INTO workflow.logical_entity (
        model_id, logical_entity_name, logical_entity_definition,
        logical_entity_type, logical_entity_grain,
        logical_entity_dependency_order, logical_entity_confidence
    ) VALUES (
        v_model_id, 'Order', 'A conformed commercial order.',
        'transaction', 'One submitted Order', 1, 'high'
    ) RETURNING logical_entity_id INTO v_logical_order_id;

    INSERT INTO workflow.logical_entity_submodel (
        model_id, logical_entity_id, logical_submodel_id
    ) VALUES
        (v_model_id, v_logical_customer_id, v_logical_submodel_id),
        (v_model_id, v_logical_order_id, v_logical_submodel_id);

    INSERT INTO workflow.logical_attribute (
        model_id, logical_entity_id, logical_attribute_name,
        logical_attribute_definition, logical_attribute_data_type,
        logical_attribute_is_nullable, logical_attribute_is_primary_key,
        logical_attribute_is_natural_key, logical_attribute_ordinal_position
    ) VALUES (
        v_model_id, v_logical_customer_id, 'Customer ID',
        'Stable Customer business identifier.', 'BIGINT', FALSE, TRUE, TRUE, 1
    ) RETURNING logical_attribute_id INTO v_logical_customer_key_id;
    INSERT INTO workflow.logical_attribute (
        model_id, logical_entity_id, logical_attribute_name,
        logical_attribute_definition, logical_attribute_data_type,
        logical_attribute_is_nullable, logical_attribute_ordinal_position
    ) VALUES (
        v_model_id, v_logical_customer_id, 'Customer Name',
        'Current Customer display name.', 'VARCHAR(200)', TRUE, 2
    ) RETURNING logical_attribute_id INTO v_logical_customer_name_id;
    INSERT INTO workflow.logical_attribute (
        model_id, logical_entity_id, logical_attribute_name,
        logical_attribute_definition, logical_attribute_data_type,
        logical_attribute_is_nullable, logical_attribute_is_primary_key,
        logical_attribute_is_natural_key, logical_attribute_ordinal_position
    ) VALUES (
        v_model_id, v_logical_order_id, 'Order ID',
        'Stable Order business identifier.', 'BIGINT', FALSE, TRUE, TRUE, 1
    ) RETURNING logical_attribute_id INTO v_logical_order_key_id;
    INSERT INTO workflow.logical_attribute (
        model_id, logical_entity_id, logical_attribute_name,
        logical_attribute_definition, logical_attribute_data_type,
        logical_attribute_is_nullable, logical_attribute_ordinal_position
    ) VALUES (
        v_model_id, v_logical_order_id, 'Customer ID',
        'Customer that placed the Order.', 'BIGINT', FALSE, 2
    ) RETURNING logical_attribute_id INTO v_logical_order_customer_id;
    INSERT INTO workflow.logical_attribute (
        model_id, logical_entity_id, logical_attribute_name,
        logical_attribute_definition, logical_attribute_data_type,
        logical_attribute_is_nullable, logical_attribute_ordinal_position
    ) VALUES (
        v_model_id, v_logical_order_id, 'Order Date',
        'Date the Order was submitted.', 'DATE', FALSE, 3
    ) RETURNING logical_attribute_id INTO v_logical_order_date_id;
    INSERT INTO workflow.logical_attribute (
        model_id, logical_entity_id, logical_attribute_name,
        logical_attribute_definition, logical_attribute_data_type,
        logical_attribute_is_nullable, logical_attribute_ordinal_position
    ) VALUES (
        v_model_id, v_logical_order_id, 'Order Amount',
        'Gross Order amount in USD.', 'DECIMAL(18,2)', FALSE, 4
    ) RETURNING logical_attribute_id INTO v_logical_order_amount_id;

    INSERT INTO workflow.logical_entity_source_mapping (
        model_id, logical_entity_id, support_source_type, source_object_id,
        logical_entity_source_mapping_order, logical_entity_source_mapping_rationale
    ) VALUES (
        v_model_id, v_logical_customer_id, 'object', v_bronze_customer_id, 1,
        'The Bronze Customer object supplies the conformed identity.'
    ) RETURNING logical_entity_source_mapping_id INTO v_logical_customer_source_id;
    INSERT INTO workflow.logical_entity_source_mapping (
        model_id, logical_entity_id, support_source_type, source_object_id,
        logical_entity_source_mapping_order, logical_entity_source_mapping_rationale
    ) VALUES (
        v_model_id, v_logical_order_id, 'object', v_bronze_order_id, 1,
        'The Bronze Order object supplies the transaction grain.'
    ) RETURNING logical_entity_source_mapping_id INTO v_logical_order_source_id;

    INSERT INTO workflow.logical_attribute_source_mapping (
        model_id, logical_entity_source_mapping_id, logical_entity_id,
        logical_attribute_id, support_source_type, source_object_id,
        source_attribute_id, logical_attribute_source_mapping_order,
        logical_attribute_source_mapping_rationale
    ) VALUES
        (v_model_id, v_logical_customer_source_id, v_logical_customer_id,
         v_logical_customer_key_id, 'attribute', v_bronze_customer_id,
         v_bronze_customer_key_id, 1, 'Direct governed identifier mapping.'),
        (v_model_id, v_logical_customer_source_id, v_logical_customer_id,
         v_logical_customer_name_id, 'attribute', v_bronze_customer_id,
         v_bronze_customer_name_id, 2, 'Direct descriptive mapping.'),
        (v_model_id, v_logical_order_source_id, v_logical_order_id,
         v_logical_order_key_id, 'attribute', v_bronze_order_id,
         v_bronze_order_key_id, 1, 'Direct governed identifier mapping.'),
        (v_model_id, v_logical_order_source_id, v_logical_order_id,
         v_logical_order_customer_id, 'attribute', v_bronze_order_id,
         v_bronze_order_customer_id, 2, 'Direct Customer reference mapping.'),
        (v_model_id, v_logical_order_source_id, v_logical_order_id,
         v_logical_order_date_id, 'attribute', v_bronze_order_id,
         v_bronze_order_date_id, 3, 'Direct activity date mapping.'),
        (v_model_id, v_logical_order_source_id, v_logical_order_id,
         v_logical_order_amount_id, 'attribute', v_bronze_order_id,
         v_bronze_order_amount_id, 4, 'Direct monetary amount mapping.');

    INSERT INTO workflow.logical_relationship (
        model_id, logical_relationship_name, logical_relationship_definition,
        logical_relationship_from_entity_id, logical_relationship_from_attribute_id,
        logical_relationship_to_entity_id, logical_relationship_to_attribute_id,
        logical_relationship_cardinality, logical_relationship_confidence,
        logical_relationship_basis, logical_relationship_cardinality_basis
    ) VALUES (
        v_model_id, 'Order references Customer',
        'Every Order references the Customer that placed it.',
        v_logical_order_id, v_logical_order_customer_id,
        v_logical_customer_id, v_logical_customer_key_id,
        'many_to_one', 'high', 'Validated physical relationship.',
        'Many Orders may reference one Customer.'
    );

    INSERT INTO workflow.model_object_binding (
        model_id, object_id, modeled_entity_type, logical_entity_id
    ) VALUES (
        v_model_id, v_silver_customer_id, 'logical_entity', v_logical_customer_id
    ) RETURNING model_object_binding_id INTO v_logical_customer_binding_id;
    INSERT INTO workflow.model_object_binding (
        model_id, object_id, modeled_entity_type, logical_entity_id
    ) VALUES (
        v_model_id, v_silver_order_id, 'logical_entity', v_logical_order_id
    ) RETURNING model_object_binding_id INTO v_logical_order_binding_id;

    INSERT INTO workflow.model_attribute_binding (
        model_object_binding_id, logical_attribute_id, attribute_id
    ) VALUES
        (v_logical_customer_binding_id, v_logical_customer_key_id, v_silver_customer_key_id),
        (v_logical_customer_binding_id, v_logical_customer_name_id, v_silver_customer_name_id),
        (v_logical_order_binding_id, v_logical_order_key_id, v_silver_order_key_id),
        (v_logical_order_binding_id, v_logical_order_customer_id, v_silver_order_customer_id),
        (v_logical_order_binding_id, v_logical_order_date_id, v_silver_order_date_id),
        (v_logical_order_binding_id, v_logical_order_amount_id, v_silver_order_amount_id);

    INSERT INTO workflow.dimensional_submodel (
        model_id, dimensional_submodel_name, dimensional_submodel_definition
    ) VALUES (
        v_model_id, 'Sales Mart', 'Customer and Order structures for governed sales reporting.'
    ) RETURNING dimensional_submodel_id INTO v_dimensional_submodel_id;

    INSERT INTO workflow.dimensional_entity (
        model_id, dimensional_entity_name, dimensional_entity_definition,
        dimensional_entity_type, dimensional_entity_dependency_order,
        dimensional_entity_confidence
    ) VALUES (
        v_model_id, 'Dim Customer', 'Conformed Customer descriptors.',
        'dimension', 0, 'high'
    ) RETURNING dimensional_entity_id INTO v_dimensional_customer_id;
    INSERT INTO workflow.dimensional_entity (
        model_id, dimensional_entity_name, dimensional_entity_definition,
        dimensional_entity_type, dimensional_fact_type,
        dimensional_entity_grain_definition, dimensional_entity_dependency_order,
        dimensional_entity_confidence
    ) VALUES (
        v_model_id, 'Fact Order', 'Submitted Order activity and amount.',
        'fact', 'transaction', 'One row per submitted Order', 1, 'high'
    ) RETURNING dimensional_entity_id INTO v_dimensional_order_id;

    INSERT INTO workflow.dimensional_entity_submodel (
        model_id, dimensional_entity_id, dimensional_submodel_id
    ) VALUES
        (v_model_id, v_dimensional_customer_id, v_dimensional_submodel_id),
        (v_model_id, v_dimensional_order_id, v_dimensional_submodel_id);

    INSERT INTO workflow.dimensional_attribute (
        model_id, dimensional_entity_id, dimensional_attribute_name,
        dimensional_attribute_definition, dimensional_attribute_data_type,
        dimensional_attribute_is_nullable, dimensional_attribute_ordinal_position,
        dimensional_attribute_role, dimensional_attribute_key_role,
        dimensional_attribute_change_behavior, dimensional_attribute_confidence
    ) VALUES (
        v_model_id, v_dimensional_customer_id, 'Customer Key',
        'Durable Customer dimension key.', 'BIGINT', FALSE, 1,
        'key', 'surrogate', 'fixed', 'high'
    ) RETURNING dimensional_attribute_id INTO v_dimensional_customer_key_id;
    INSERT INTO workflow.dimensional_attribute (
        model_id, dimensional_entity_id, dimensional_attribute_name,
        dimensional_attribute_definition, dimensional_attribute_data_type,
        dimensional_attribute_is_nullable, dimensional_attribute_ordinal_position,
        dimensional_attribute_role, dimensional_attribute_change_behavior,
        dimensional_attribute_confidence
    ) VALUES (
        v_model_id, v_dimensional_customer_id, 'Customer Name',
        'Current Customer display name.', 'VARCHAR(200)', TRUE, 2,
        'descriptor', 'overwrite', 'high'
    ) RETURNING dimensional_attribute_id INTO v_dimensional_customer_name_id;
    INSERT INTO workflow.dimensional_attribute (
        model_id, dimensional_entity_id, dimensional_attribute_name,
        dimensional_attribute_definition, dimensional_attribute_data_type,
        dimensional_attribute_is_nullable, dimensional_attribute_ordinal_position,
        dimensional_attribute_role, dimensional_attribute_key_role,
        dimensional_attribute_is_grain_component, dimensional_attribute_confidence
    ) VALUES (
        v_model_id, v_dimensional_order_id, 'Order ID',
        'Degenerate Order business identifier.', 'BIGINT', FALSE, 1,
        'degenerate_dimension', 'none', TRUE, 'high'
    ) RETURNING dimensional_attribute_id INTO v_dimensional_order_key_id;
    INSERT INTO workflow.dimensional_attribute (
        model_id, dimensional_entity_id, dimensional_attribute_name,
        dimensional_attribute_definition, dimensional_attribute_data_type,
        dimensional_attribute_is_nullable, dimensional_attribute_ordinal_position,
        dimensional_attribute_role, dimensional_attribute_key_role,
        dimensional_attribute_is_grain_component, dimensional_attribute_confidence
    ) VALUES (
        v_model_id, v_dimensional_order_id, 'Customer Key',
        'Foreign key to Dim Customer.', 'BIGINT', FALSE, 2,
        'key', 'foreign', FALSE, 'high'
    ) RETURNING dimensional_attribute_id INTO v_dimensional_order_customer_id;
    INSERT INTO workflow.dimensional_attribute (
        model_id, dimensional_entity_id, dimensional_attribute_name,
        dimensional_attribute_definition, dimensional_attribute_data_type,
        dimensional_attribute_is_nullable, dimensional_attribute_ordinal_position,
        dimensional_attribute_role, dimensional_attribute_is_grain_component,
        dimensional_attribute_confidence
    ) VALUES (
        v_model_id, v_dimensional_order_id, 'Order Date',
        'Order activity date.', 'DATE', FALSE, 3,
        'descriptor', TRUE, 'high'
    ) RETURNING dimensional_attribute_id INTO v_dimensional_order_date_id;
    INSERT INTO workflow.dimensional_attribute (
        model_id, dimensional_entity_id, dimensional_attribute_name,
        dimensional_attribute_definition, dimensional_attribute_data_type,
        dimensional_attribute_is_nullable, dimensional_attribute_ordinal_position,
        dimensional_attribute_role, dimensional_attribute_additivity,
        dimensional_attribute_default_aggregation, dimensional_attribute_confidence
    ) VALUES (
        v_model_id, v_dimensional_order_id, 'Order Amount',
        'Additive gross Order amount.', 'DECIMAL(18,2)', FALSE, 4,
        'measure', 'additive', 'sum', 'high'
    ) RETURNING dimensional_attribute_id INTO v_dimensional_order_amount_id;

    INSERT INTO workflow.dimensional_entity_source_mapping (
        model_id, dimensional_entity_id, support_source_type, source_object_id,
        dimensional_entity_source_role, dimensional_entity_source_mapping_order,
        dimensional_entity_source_mapping_rationale
    ) VALUES (
        v_model_id, v_dimensional_customer_id, 'object', v_silver_customer_id,
        'dimension source', 1, 'Silver Customer supplies conformed descriptors.'
    ) RETURNING dimensional_entity_source_mapping_id INTO v_dimensional_customer_source_id;
    INSERT INTO workflow.dimensional_entity_source_mapping (
        model_id, dimensional_entity_id, support_source_type, source_object_id,
        dimensional_entity_source_role, dimensional_entity_source_mapping_order,
        dimensional_entity_source_mapping_rationale
    ) VALUES (
        v_model_id, v_dimensional_order_id, 'object', v_silver_order_id,
        'fact source', 1, 'Silver Order supplies the transaction grain and measure.'
    ) RETURNING dimensional_entity_source_mapping_id INTO v_dimensional_order_source_id;

    INSERT INTO workflow.dimensional_attribute_source_mapping (
        model_id, dimensional_entity_source_mapping_id, dimensional_entity_id,
        dimensional_attribute_id, support_source_type, source_object_id,
        source_attribute_id, dimensional_attribute_source_mapping_order,
        dimensional_attribute_source_mapping_rationale
    ) VALUES
        (v_model_id, v_dimensional_customer_source_id, v_dimensional_customer_id,
         v_dimensional_customer_key_id, 'attribute', v_silver_customer_id,
         v_silver_customer_key_id, 1, 'Promote the governed Customer identifier.'),
        (v_model_id, v_dimensional_customer_source_id, v_dimensional_customer_id,
         v_dimensional_customer_name_id, 'attribute', v_silver_customer_id,
         v_silver_customer_name_id, 2, 'Carry the current Customer name.'),
        (v_model_id, v_dimensional_order_source_id, v_dimensional_order_id,
         v_dimensional_order_key_id, 'attribute', v_silver_order_id,
         v_silver_order_key_id, 1, 'Carry the degenerate Order identifier.'),
        (v_model_id, v_dimensional_order_source_id, v_dimensional_order_id,
         v_dimensional_order_customer_id, 'attribute', v_silver_order_id,
         v_silver_order_customer_id, 2, 'Resolve the Customer dimension key.'),
        (v_model_id, v_dimensional_order_source_id, v_dimensional_order_id,
         v_dimensional_order_date_id, 'attribute', v_silver_order_id,
         v_silver_order_date_id, 3, 'Carry the activity date.'),
        (v_model_id, v_dimensional_order_source_id, v_dimensional_order_id,
         v_dimensional_order_amount_id, 'attribute', v_silver_order_id,
         v_silver_order_amount_id, 4, 'Carry the additive Order amount.');

    INSERT INTO workflow.dimensional_relationship (
        model_id, dimensional_relationship_name, dimensional_relationship_definition,
        dimensional_relationship_from_entity_id,
        dimensional_relationship_from_attribute_id,
        dimensional_relationship_to_entity_id,
        dimensional_relationship_to_attribute_id,
        dimensional_relationship_kind, dimensional_relationship_cardinality,
        dimensional_relationship_is_optional, dimensional_relationship_role_name,
        dimensional_relationship_confidence, dimensional_relationship_basis,
        dimensional_relationship_cardinality_basis
    ) VALUES (
        v_model_id, 'Fact Order to Dim Customer',
        'Each Fact Order row resolves to its Customer dimension member.',
        v_dimensional_order_id, v_dimensional_order_customer_id,
        v_dimensional_customer_id, v_dimensional_customer_key_id,
        'fact_dimension', 'many_to_one', FALSE, 'ordering_customer', 'high',
        'Conformed Customer key mapping.', 'Many Order facts per Customer member.'
    );

    INSERT INTO workflow.model_object_binding (
        model_id, object_id, modeled_entity_type, dimensional_entity_id
    ) VALUES (
        v_model_id, v_gold_customer_id, 'dimensional_entity', v_dimensional_customer_id
    ) RETURNING model_object_binding_id INTO v_dimensional_customer_binding_id;
    INSERT INTO workflow.model_object_binding (
        model_id, object_id, modeled_entity_type, dimensional_entity_id
    ) VALUES (
        v_model_id, v_gold_order_id, 'dimensional_entity', v_dimensional_order_id
    ) RETURNING model_object_binding_id INTO v_dimensional_order_binding_id;

    INSERT INTO workflow.model_attribute_binding (
        model_object_binding_id, dimensional_attribute_id, attribute_id
    ) VALUES
        (v_dimensional_customer_binding_id, v_dimensional_customer_key_id, v_gold_customer_key_id),
        (v_dimensional_customer_binding_id, v_dimensional_customer_name_id, v_gold_customer_name_id),
        (v_dimensional_order_binding_id, v_dimensional_order_key_id, v_gold_order_key_id),
        (v_dimensional_order_binding_id, v_dimensional_order_customer_id, v_gold_order_customer_id),
        (v_dimensional_order_binding_id, v_dimensional_order_date_id, v_gold_order_date_id),
        (v_dimensional_order_binding_id, v_dimensional_order_amount_id, v_gold_order_amount_id);

    INSERT INTO workflow.mapping_source_system_dependency (
        model_id, modeled_entity_type, source_system_id, source_system_dependency_order
    ) VALUES
        (v_model_id, 'logical_entity', v_system_id, 0),
        (v_model_id, 'dimensional_entity', v_system_id, 0);

    FOR v_mapping_object_id IN
        INSERT INTO workflow.mapping_object (
            model_id, model_object_binding_id, source_system_id,
            object_dependency_order, mapping_transformation_document
        ) VALUES
            (v_model_id, v_logical_customer_binding_id, v_system_id, 0,
             '{"source_objects":["bronze_demo.customer"],"steps":["Standardize identifiers","Select current descriptive values"]}'),
            (v_model_id, v_logical_order_binding_id, v_system_id, 1,
             '{"source_objects":["bronze_demo.orders"],"steps":["Validate order grain","Normalize monetary values"]}'),
            (v_model_id, v_dimensional_customer_binding_id, v_system_id, 0,
             '{"source_objects":["silver_demo.customer"],"steps":["Generate durable Customer key","Apply overwrite policy"]}'),
            (v_model_id, v_dimensional_order_binding_id, v_system_id, 1,
             '{"source_objects":["silver_demo.orders","gold_demo.dim_customer"],"steps":["Resolve Customer key","Publish Order measure"]}')
        RETURNING mapping_object_id
    LOOP
        INSERT INTO workflow.mapping_attribute (
            mapping_object_id, model_attribute_binding_id,
            attribute_mapping_transformation_document
        )
        SELECT v_mapping_object_id,
               binding.model_attribute_binding_id,
               jsonb_build_object(
                   'transformation', 'Direct governed projection',
                   'target_attribute_id', binding.attribute_id
               )
          FROM workflow.mapping_object AS mapping
          JOIN workflow.model_attribute_binding AS binding
            ON binding.model_object_binding_id = mapping.model_object_binding_id
         WHERE mapping.mapping_object_id = v_mapping_object_id;
    END LOOP;

    INSERT INTO workflow.generated_code (
        model_object_binding_id, artifact_name, artifact_type,
        generated_code_content, code_input_digest
    ) VALUES
        (v_logical_customer_binding_id, 'silver_customer.sql', 'sql_file',
         E'CREATE OR REPLACE TABLE silver_demo.customer AS\nSELECT customer_id, customer_name\nFROM bronze_demo.customer;', repeat('d', 64)),
        (v_logical_order_binding_id, 'silver_orders.sql', 'sql_file',
         E'CREATE OR REPLACE TABLE silver_demo.orders AS\nSELECT order_id, customer_id, order_date, order_amount\nFROM bronze_demo.orders;', repeat('e', 64)),
        (v_dimensional_customer_binding_id, 'dim_customer.sql', 'sql_file',
         E'CREATE OR REPLACE TABLE gold_demo.dim_customer AS\nSELECT customer_id, customer_name\nFROM silver_demo.customer;', repeat('f', 64)),
        (v_dimensional_order_binding_id, 'fact_order.sql', 'sql_file',
         E'CREATE OR REPLACE TABLE gold_demo.fact_order AS\nSELECT order_id, customer_id, order_date, order_amount\nFROM silver_demo.orders;', repeat('1', 64));

    INSERT INTO workflow.generated_code_source_system (
        generated_code_id, source_system_id
    )
    SELECT generated.generated_code_id, v_system_id
      FROM workflow.generated_code AS generated
      JOIN workflow.model_object_binding AS binding
        ON binding.model_object_binding_id = generated.model_object_binding_id
     WHERE binding.model_id = v_model_id;

    INSERT INTO workflow.validation_group (
        model_id, tenant_id, system_id, validation_group_name,
        validation_group_description, mapping_context_digest, code_context_digest
    ) VALUES (
        v_model_id, v_tenant_id, v_system_id, 'Customer Orders release checks',
        'Blocking and warning checks for the conformed Customer Orders pipeline.',
        repeat('2', 64), repeat('3', 64)
    ) RETURNING validation_group_id INTO v_validation_group_id;

    INSERT INTO workflow.validation_check (
        validation_group_id, validation_check_name, validation_check_description,
        validation_category_code, validation_severity, validation_query_sql,
        validation_result_data_type, validation_comparison_operator,
        validation_comparison_value_type, validation_comparison_value
    ) VALUES
        (v_validation_group_id, 'Order identifiers are unique',
         'No duplicate Order identifiers may reach the Gold fact.',
         'uniqueness', 'blocking',
         format('SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM %I.gold_demo.fact_order', v_gds_catalog),
         'integer', 'equal', 'literal', '0'::JSONB),
        (v_validation_group_id, 'Every Order resolves a Customer',
         'All Order Customer keys must resolve to Dim Customer.',
         'referential_integrity', 'blocking',
         format('SELECT COUNT(*) FROM %I.gold_demo.fact_order f LEFT ANTI JOIN %I.gold_demo.dim_customer d ON f.customer_id = d.customer_id', v_gds_catalog, v_gds_catalog),
         'integer', 'equal', 'literal', '0'::JSONB),
        (v_validation_group_id, 'Order amount is populated',
         'Monitor missing gross amounts before release.',
         'completeness', 'warning',
         format('SELECT COUNT(*) FROM %I.gold_demo.fact_order WHERE order_amount IS NULL', v_gds_catalog),
         'integer', 'equal', 'literal', '0'::JSONB);

    SELECT principal_id
      INTO STRICT v_principal_id
      FROM security.principal
     WHERE is_super_admin
       AND is_active
     ORDER BY principal_id
     LIMIT 1;

    IF NOT EXISTS (SELECT 1 FROM application.sql_generation_guide WHERE is_default) THEN
        INSERT INTO application.sql_generation_guide (
            sql_generation_guide_code, sql_generation_guide_name, is_default,
            created_by_principal_id, updated_by_principal_id
        ) VALUES ('local.transformation', 'Local transformation SQL', true,
            v_principal_id, v_principal_id)
        RETURNING sql_generation_guide_id INTO v_guide_id;
        INSERT INTO application.sql_generation_guide_version (
            sql_generation_guide_id, sql_generation_guide_version_number,
            sql_generation_guide_content, sql_generation_guide_digest,
            sql_generation_guide_version_status, created_by_principal_id,
            updated_by_principal_id, published_time, published_by_principal_id
        ) VALUES (v_guide_id, 1, v_guide_content,
            encode(sha256(convert_to(v_guide_content, 'UTF8')), 'hex'),
            'published', v_principal_id, v_principal_id, CURRENT_TIMESTAMP, v_principal_id);
    END IF;

    INSERT INTO application.workflow_run (
        tenant_id, model_id, model_revision, model_workflow,
        actor_principal_id, selected_scope_digest, selected_scope_count,
        workflow_run_state, correlation_id, started_time, completed_time,
        created_time
    )
    SELECT v_tenant_id, v_model_id, model_revision, 'profiling',
           v_principal_id, repeat('4', 64), 2, 'completed', gen_random_uuid(),
           CURRENT_TIMESTAMP - INTERVAL '4 minutes',
           CURRENT_TIMESTAMP - INTERVAL '3 minutes',
           CURRENT_TIMESTAMP - INTERVAL '5 minutes'
      FROM model.model
     WHERE model_id = v_model_id
    RETURNING workflow_run_id INTO v_workflow_run_id;

    INSERT INTO application.workflow_run_object_selection (
        workflow_run_id, model_id, object_id, selection_order
    ) VALUES
        (v_workflow_run_id, v_model_id, v_bronze_customer_id, 1),
        (v_workflow_run_id, v_model_id, v_bronze_order_id, 2);

    INSERT INTO model.model_event_log (
        model_id, correlation_id, workflow_run_id,
        model_event_log_sequence, model_event_log_attempt,
        model_workflow, model_event_log_stage, model_event_log_status,
        model_event_log_message, model_event_log_current,
        model_event_log_total, model_event_log_percent
    ) VALUES (
        v_model_id, gen_random_uuid(), v_workflow_run_id,
        1, 1, 'profiling', 'completed', 'completed',
        'Profiled six Customer and Order attributes.', 6, 6, 100
    );
END;
$local_workbench_review$;
