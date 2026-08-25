// THROWAWAY PROTOTYPE: Tenant entry, Metadata, and connected Model workflows.
(function () {
  "use strict";

  const tenants = [
    { id: "northwind", code: "NWA", name: "Northwind Analytics", role: "Tenant Admin", environment: "Production", systems: 3, objects: 187, last: "12 minutes ago", isLast: true },
    { id: "grdm", code: "GRDM", name: "Global Reference Data", role: "Architect", environment: "Production", systems: 5, objects: 264, last: "Yesterday" },
    { id: "retail", code: "RDS", name: "Retail Data Services", role: "Developer", environment: "Test", systems: 4, objects: 143, last: "Aug 20" },
    { id: "finance", code: "FDH", name: "Finance Data Hub", role: "Viewer", environment: "Production", systems: 2, objects: 98, last: "Aug 14" },
  ];

  const objectRows = [
    object("customer_raw", "CRM", "GRDM", 12, "batch_id", "Complete", "2.4M", "2h", "3.1%", "18.4%"),
    object("customer_address_raw", "CRM", "GRDM", 14, "batch_id", "Complete", "3.8M", "2h", "6.2%", "22.7%"),
    object("contact_raw", "CRM", "GRDM", 11, "batch_id", "Warning", "1.9M", "2h", "14.8%", "34.1%"),
    object("account_raw", "CRM", "GRDM", 13, "batch_id", "Complete", "620K", "2h", "2.4%", "42.6%"),
    object("account_contact_raw", "CRM", "GRDM", 8, "batch_id", "Complete", "2.1M", "2h", "0.9%", "35.5%"),
    object("customer_consent_raw", "CRM", "GRDM", 9, "batch_id", "Not profiled", "—", "—", "—", "—"),
    object("support_case_raw", "CRM", "GRDM", 16, "batch_id", "Not profiled", "—", "—", "—", "—"),
    object("employee_raw", "ERP", "DDS", 10, "ingest_batch_id", "Complete", "84K", "6h", "1.2%", "48.2%"),
    object("supplier_raw", "ERP", "DDS", 12, "ingest_batch_id", "Warning", "38K", "6h", "18.7%", "54.7%"),
    object("product_raw", "ERP", "DDS", 15, "ingest_batch_id", "Complete", "410K", "6h", "4.8%", "31.9%"),
    object("product_category_raw", "ERP", "DDS", 7, "ingest_batch_id", "Complete", "2.8K", "6h", "0.4%", "61.3%"),
    object("currency_raw", "ERP", "DDS", 5, null, "Complete", "172", "1d", "0.0%", "72.4%"),
    object("country_raw", "ERP", "DDS", 8, null, "Complete", "249", "1d", "0.0%", "63.1%"),
    object("warehouse_raw", "ERP", "DDS", 10, "ingest_batch_id", "Complete", "318", "6h", "1.1%", "51.8%"),
    object("inventory_raw", "ERP", "DDS", 13, "ingest_batch_id", "Complete", "4.6M", "6h", "0.7%", "20.6%"),
    object("invoice_raw", "ERP", "DDS", 17, "ingest_batch_id", "Complete", "8.7M", "6h", "5.3%", "16.8%"),
    object("invoice_line_raw", "ERP", "DDS", 16, "ingest_batch_id", "Complete", "31.2M", "6h", "2.2%", "12.4%"),
    object("payment_raw", "ERP", "DDS", 14, "ingest_batch_id", "Complete", "7.9M", "6h", "3.8%", "17.5%"),
    object("order_raw", "Commerce", "GDS", 18, "batch_id", "Complete", "9.1M", "1h", "4.1%", "15.8%"),
    object("order_line_raw", "Commerce", "GDS", 15, "batch_id", "Complete", "42.6M", "1h", "1.8%", "11.3%"),
    object("shipment_raw", "Commerce", "GDS", 14, "batch_id", "Not profiled", "—", "—", "—", "—"),
    object("promotion_raw", "Commerce", "GDS", 11, "batch_id", "Not profiled", "—", "—", "—", "—"),
    object("return_raw", "Commerce", "GDS", 13, "batch_id", "Not profiled", "—", "—", "—", "—"),
    object("return_line_raw", "Commerce", "GDS", 11, "batch_id", "Not profiled", "—", "—", "—", "—"),
    object("sales_region_raw", "CRM", "GRDM", 7, null, "Not profiled", "—", "—", "—", "—"),
  ];

  const candidateRows = [
    object("loyalty_account_raw", "CRM", "GRDM", 11, "batch_id", "Not profiled", "—", "—", "—", "—"),
    zonedObject("marketing_event_source", "Marketing", "NWA", "Source", 17),
    object("email_preference_raw", "CRM", "GRDM", 8, "batch_id", "Not profiled", "—", "—", "—", "—"),
    zonedObject("customer_segment", "GDS", "NWA", "Silver", 9),
    zonedObject("dim_web_identity", "GDS", "NWA", "Gold", 12),
  ];

  const metadataObjectRows = [
    ...objectRows,
    zonedObject("customer_source", "CRM", "GRDM", "Source", 12),
    zonedObject("customer", "GDS", "NWA", "Silver", 16),
    zonedObject("invoice", "GDS", "NWA", "Silver", 18),
    zonedObject("dim_customer", "GDS", "NWA", "Gold", 14),
    zonedObject("fact_sales", "GDS", "NWA", "Gold", 22),
  ];

  const findings = [
    finding("customer_raw", "customer_id", "invoice_raw", "customer_id", "Reference", "High", "Supported", true),
    finding("customer_raw", "customer_id", "contact_raw", "customer_id", "Reference", "High", "Pending", true),
    finding("account_raw", "account_id", "contact_raw", "account_id", "Reference", "High", "Supported", false),
    finding("invoice_raw", "invoice_id", "invoice_line_raw", "invoice_id", "Parent / child", "High", "Supported", false),
    finding("product_raw", "product_id", "order_line_raw", "product_id", "Reference", "Medium", "Inconclusive", false),
    finding("order_raw", "order_id", "shipment_raw", "order_id", "Reference", "Medium", "Pending", false),
    finding("currency_raw", "currency_code", "invoice_raw", "currency_code", "Lookup", "High", "Supported", false),
    finding("supplier_raw", "supplier_id", "product_raw", "supplier_id", "Reference", "Low", "Unsupported", false),
    finding("customer_raw", "customer_id", "customer_address_raw", "customer_id", "Parent / child", "High", "Pending", false),
    finding("order_raw", "order_id", "payment_raw", "order_id", "Reference", "Medium", "Pending", false),
    finding("product_category_raw", "category_id", "product_raw", "category_id", "Lookup", "High", "Supported", false),
    finding("return_raw", "return_id", "return_line_raw", "return_id", "Parent / child", "High", "Pending", false),
  ];

  const profileRuns = [
    run("PR-1048", "Completed with warnings", "Today, 10:42 AM", "CRM", "8", "10428", "Maaz", "1m 42s"),
    run("PR-1047", "Completed", "Yesterday, 4:18 PM", "ERP", "11", "8841", "Maaz", "2m 11s"),
    run("PR-1046", "Failed", "Aug 21, 9:04 AM", "Commerce", "6", "—", "Elena Morris", "18s"),
    run("PR-1045", "Completed", "Aug 20, 2:31 PM", "CRM", "7", "10387", "Elena Morris", "1m 36s"),
  ];

  const analysisRuns = [
    run("AN-0318", "Completed", "Today, 11:06 AM", "All systems", "25", "—", "Maaz", "3m 24s"),
    run("AN-0317", "Completed with repair", "Yesterday, 5:02 PM", "CRM", "8", "—", "Maaz", "2m 18s"),
    run("AN-0316", "Failed", "Aug 21, 1:44 PM", "ERP", "11", "—", "Elena Morris", "42s"),
  ];

  const authoringRuns = [
    run("AU-0214", "Completed", "Today, 12:14 PM", "Conceptual", "25", "Detailed Coverage", "Maaz", "4m 18s"),
    run("AU-0213", "Completed with repair", "Yesterday, 6:20 PM", "Logical", "18", "Tool-assisted", "Maaz", "6m 02s"),
    run("AU-0212", "Failed", "Aug 21, 2:35 PM", "Dimensional", "7", "One-shot", "Elena Morris", "38s"),
  ];

  const mappingRuns = [
    run("MP-0094", "Completed", "Today, 1:18 PM", "Logical", "6", "Detailed Coverage", "Maaz", "3m 41s"),
    run("MP-0093", "Completed with repair", "Yesterday, 4:11 PM", "Dimensional", "4", "Tool-assisted", "Maaz", "4m 09s"),
  ];

  const codeRuns = [
    run("CG-0042", "Completed", "Today, 2:04 PM", "Logical", "6", "SQL", "Maaz", "1m 12s"),
    run("CG-0041", "Failed", "Yesterday, 3:26 PM", "Dimensional", "3", "SQL", "Elena Morris", "29s"),
  ];

  const codeTargets = [
    { id: "customer", model_name: "Customer 360", modeled_entity_type: "logical_entity", modeled_entity_name: "Customer", source_system_code: "CRM", target_tenant_code: "NWA", target_system_code: "GDS", target_connection_code: "gds_primary", target_object_schema: "silver_nwa", target_object_name: "customer", mapping_status: "active", generation_guide: "Default Databricks SQL", output_type: "sql", generated_sql: storedSql("silver_nwa", "customer", "bronze_crm", "customer_raw"), generated_at: "Today, 2:04 PM", generated_run_id: "CG-0042" },
    { id: "invoice", model_name: "Customer 360", modeled_entity_type: "logical_entity", modeled_entity_name: "Invoice", source_system_code: "ERP", target_tenant_code: "NWA", target_system_code: "GDS", target_connection_code: "gds_primary", target_object_schema: "silver_nwa", target_object_name: "invoice", mapping_status: "active", generation_guide: "Default Databricks SQL", output_type: "sql", generated_sql: storedSql("silver_nwa", "invoice", "bronze_erp", "invoice_raw"), generated_at: "Today, 2:04 PM", generated_run_id: "CG-0042" },
    { id: "order", model_name: "Customer 360", modeled_entity_type: "logical_entity", modeled_entity_name: "Order", source_system_code: "COMMERCE", target_tenant_code: "NWA", target_system_code: "GDS", target_connection_code: "gds_primary", target_object_schema: "silver_nwa", target_object_name: "order", mapping_status: "active", generation_guide: "Default Databricks SQL", output_type: "sql", generated_sql: storedSql("silver_nwa", "order", "bronze_commerce", "order_raw"), generated_at: "Today, 2:04 PM", generated_run_id: "CG-0042" },
    { id: "dim_customer", model_name: "Customer 360", modeled_entity_type: "dimensional_entity", modeled_entity_name: "Dim Customer", source_system_code: "GDS", target_tenant_code: "NWA", target_system_code: "GDS", target_connection_code: "gds_primary", target_object_schema: "gold_nwa", target_object_name: "dim_customer", mapping_status: "active", generation_guide: "Default Databricks SQL", output_type: "sql", generated_sql: storedSql("gold_nwa", "dim_customer", "silver_nwa", "customer"), generated_at: "Yesterday, 3:18 PM", generated_run_id: "CG-0040" },
    { id: "fact_sales", model_name: "Customer 360", modeled_entity_type: "dimensional_entity", modeled_entity_name: "Fact Sales", source_system_code: "GDS", target_tenant_code: "NWA", target_system_code: "GDS", target_connection_code: "gds_primary", target_object_schema: "gold_nwa", target_object_name: "fact_sales", mapping_status: "active", generation_guide: "Default Databricks SQL", output_type: "sql", generated_sql: null, generated_at: null, generated_run_id: null },
  ];

  const modelContracts = {
    model_scope: {
      label: "Model Scope",
      columns: ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "model_scope_is_locked", "is_active"],
      filters: ["system_code", "tenant_code", "model_scope_is_locked", "is_active"],
    },
    profiling_profile: {
      label: "Profiling Profiles",
      columns: ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "attribute_name", "row_count", "non_null_count", "null_count", "blank_count", "distinct_count", "min_data_length", "max_data_length", "avg_data_length", "percent_populated", "percent_duplicates", "percent_null", "percent_blank", "percent_distinct"],
      filters: ["system_code", "object_name", "percent_populated"],
    },
    analysis_result: {
      label: "Analysis Results",
      columns: ["from_tenant_code", "from_system_code", "from_connection_code", "from_object_schema", "from_object_name", "from_attribute_name", "to_tenant_code", "to_system_code", "to_connection_code", "to_object_schema", "to_object_name", "to_attribute_name", "relationship_kind", "relationship_confidence", "relationship_basis", "validation_policy_version", "validation_result", "validation_source_non_null_count", "validation_source_distinct_count", "validation_target_non_null_count", "validation_target_distinct_count", "validation_source_missing_target_count", "validation_unused_target_count", "validation_duplicate_target_key_count", "analysis_result_status", "analysis_result_is_locked"],
      filters: ["__object_name", "relationship_confidence", "validation_result", "analysis_result_status", "analysis_result_is_locked"],
    },
    modeling_assertion_document: {
      label: "Assertion Documents",
      columns: ["modeling_assertion_document_name", "tenant_code", "system_code", "modeling_assertion_file_pattern", "modeling_assertion_document_type", "modeling_assertion_document_description", "modeling_assertion_document_metadata", "is_active"],
      filters: ["system_code", "modeling_assertion_document_type", "is_active"],
      rows: [
        { modeling_assertion_document_name: "customer_domain_rules", tenant_code: "NWA", system_code: "CRM", modeling_assertion_file_pattern: "customer-domain-*.md", modeling_assertion_document_type: "business_rules", modeling_assertion_document_description: "Approved Customer domain rules", modeling_assertion_document_metadata: "{owner: Data Architecture, approved: true}", is_active: true },
        { modeling_assertion_document_name: "finance_model_notes", tenant_code: "NWA", system_code: "ERP", modeling_assertion_file_pattern: "finance-notes.docx", modeling_assertion_document_type: "meeting_notes", modeling_assertion_document_description: "Finance modeling workshop notes", modeling_assertion_document_metadata: "{meeting_date: 2026-08-18}", is_active: true },
      ],
    },
    modeling_assertion_record: {
      label: "Assertion Records",
      columns: ["modeling_assertion_record_key", "modeling_assertion_document_name", "modeling_assertion_record_type", "modeling_assertion_text", "modeling_assertion_details", "modeling_assertion_source_location", "modeling_assertion_applicable_layers", "modeling_assertion_confidence", "modeling_assertion_record_status", "modeling_assertion_record_is_locked"],
      filters: ["modeling_assertion_record_type", "modeling_assertion_confidence", "modeling_assertion_record_status", "modeling_assertion_record_is_locked"],
      rows: [
        { modeling_assertion_record_key: "customer.one_per_party", modeling_assertion_document_name: "customer_domain_rules", modeling_assertion_record_type: "grain_rule", modeling_assertion_text: "A Customer represents one governed party.", modeling_assertion_details: "{subject: customer, grain: party}", modeling_assertion_source_location: "{section: Customer identity}", modeling_assertion_applicable_layers: "conceptual, logical, mapping", modeling_assertion_confidence: "high", modeling_assertion_record_status: "active", modeling_assertion_record_is_locked: true },
        { modeling_assertion_record_key: "invoice.immutable_number", modeling_assertion_document_name: "finance_model_notes", modeling_assertion_record_type: "key_rule", modeling_assertion_text: "Invoice number is immutable within ERP.", modeling_assertion_details: "{subject: invoice_number}", modeling_assertion_source_location: "{page: 3}", modeling_assertion_applicable_layers: "analysis, logical, dimensional", modeling_assertion_confidence: "medium", modeling_assertion_record_status: "needs_review", modeling_assertion_record_is_locked: false },
      ],
    },
    conceptual_object: {
      label: "Conceptual Objects",
      columns: ["conceptual_object_name", "conceptual_object_definition", "conceptual_object_type", "conceptual_object_grain", "conceptual_object_aliases", "conceptual_object_confidence", "conceptual_object_status", "conceptual_object_is_locked", "supports"],
      filters: ["conceptual_object_type", "conceptual_object_confidence", "conceptual_object_status", "conceptual_object_is_locked"],
      rows: [
        { conceptual_object_name: "Customer", conceptual_object_definition: "A governed party receiving products or services.", conceptual_object_type: "business_entity", conceptual_object_grain: "One governed party", conceptual_object_aliases: "Client, Account holder", conceptual_object_confidence: "high", conceptual_object_status: "active", conceptual_object_is_locked: true, supports: [objectSupport("customer_raw", "CRM", "GRDM", "Primary Customer identity evidence"), objectSupport("customer_address_raw", "CRM", "GRDM", "Customer address context", "context"), objectSupport("contact_raw", "CRM", "GRDM", "Customer contact context", "context"), assertionSupport("customer.one_per_party", "Confirms governed Customer grain")] },
        { conceptual_object_name: "Invoice", conceptual_object_definition: "A financial request for payment.", conceptual_object_type: "business_event", conceptual_object_grain: "One issued invoice", conceptual_object_aliases: "Bill", conceptual_object_confidence: "high", conceptual_object_status: "active", conceptual_object_is_locked: false, supports: [objectSupport("invoice_raw", "ERP", "DDS", "Invoice header evidence"), objectSupport("invoice_line_raw", "ERP", "DDS", "Invoice composition evidence", "detail")] },
        { conceptual_object_name: "Order", conceptual_object_definition: "A customer commitment to purchase.", conceptual_object_type: "business_event", conceptual_object_grain: "One submitted order", conceptual_object_aliases: "Purchase", conceptual_object_confidence: "medium", conceptual_object_status: "needs_review", conceptual_object_is_locked: false, supports: [objectSupport("order_raw", "COMMERCE", "GDS", "Order header evidence"), objectSupport("order_line_raw", "COMMERCE", "GDS", "Order-line composition evidence", "detail")] },
      ],
    },
    conceptual_relationship: {
      label: "Conceptual Relationships",
      columns: ["from_conceptual_object_name", "to_conceptual_object_name", "conceptual_relationship_name", "conceptual_relationship_type", "conceptual_relationship_definition", "conceptual_relationship_cardinality", "conceptual_relationship_basis", "conceptual_relationship_cardinality_basis", "conceptual_relationship_confidence", "conceptual_relationship_status", "conceptual_relationship_is_locked", "supports"],
      filters: ["conceptual_relationship_type", "conceptual_relationship_cardinality", "conceptual_relationship_status", "conceptual_relationship_is_locked"],
      rows: [
        { from_conceptual_object_name: "Customer", to_conceptual_object_name: "Order", conceptual_relationship_name: "Customer places Order", conceptual_relationship_type: "association", conceptual_relationship_definition: "A Customer may place Orders.", conceptual_relationship_cardinality: "one_to_many", conceptual_relationship_basis: "Customer and Order metadata", conceptual_relationship_cardinality_basis: "Validated customer_id reuse", conceptual_relationship_confidence: "high", conceptual_relationship_status: "active", conceptual_relationship_is_locked: true, supports: [objectSupport("customer_raw", "CRM", "GRDM", "Supplies the Customer endpoint"), objectSupport("order_raw", "COMMERCE", "GDS", "Supplies the Order endpoint")] },
        { from_conceptual_object_name: "Customer", to_conceptual_object_name: "Invoice", conceptual_relationship_name: "Customer receives Invoice", conceptual_relationship_type: "association", conceptual_relationship_definition: "An Invoice is issued to a Customer.", conceptual_relationship_cardinality: "one_to_many", conceptual_relationship_basis: "Invoice relationship analysis", conceptual_relationship_cardinality_basis: "Supported validation", conceptual_relationship_confidence: "high", conceptual_relationship_status: "needs_review", conceptual_relationship_is_locked: false, supports: [objectSupport("invoice_raw", "ERP", "DDS", "Validated customer_id reference"), assertionSupport("invoice.immutable_number", "Supports the Invoice business identity")] },
      ],
    },
    logical_submodel: {
      label: "Logical Submodels",
      columns: ["logical_submodel_name", "logical_submodel_definition", "logical_submodel_status", "logical_submodel_is_locked"],
      filters: ["logical_submodel_status", "logical_submodel_is_locked"],
      rows: [
        { logical_submodel_name: "Customer Management", logical_submodel_definition: "Customer identity and contact structures.", logical_submodel_status: "active", logical_submodel_is_locked: true },
        { logical_submodel_name: "Order Management", logical_submodel_definition: "Order lifecycle structures.", logical_submodel_status: "active", logical_submodel_is_locked: false },
      ],
    },
    logical_entity: {
      label: "Logical Entities",
      columns: ["logical_entity_name", "logical_entity_definition", "logical_entity_type", "logical_entity_type_detail", "logical_entity_grain", "logical_entity_dependency_order", "logical_entity_confidence", "logical_entity_status", "logical_entity_is_locked", "submodels", "sources"],
      filters: ["submodels", "logical_entity_type", "logical_entity_confidence", "logical_entity_status", "logical_entity_is_locked"],
      rows: [
        { logical_entity_name: "Customer", logical_entity_definition: "Normalized Customer master.", logical_entity_type: "core", logical_entity_type_detail: null, logical_entity_grain: "One governed Customer", logical_entity_dependency_order: 10, logical_entity_confidence: "high", logical_entity_status: "active", logical_entity_is_locked: true, submodels: [submodelMembership("Customer Management")], sources: [entityObjectSource("customer_raw", "CRM", "GRDM", "Primary Customer identity", 1), entityObjectSource("customer_address_raw", "CRM", "GRDM", "Customer address contribution", 2)] },
        { logical_entity_name: "Invoice", logical_entity_definition: "Normalized Invoice header.", logical_entity_type: "transaction", logical_entity_type_detail: null, logical_entity_grain: "One Invoice", logical_entity_dependency_order: 20, logical_entity_confidence: "high", logical_entity_status: "active", logical_entity_is_locked: false, submodels: [submodelMembership("Order Management")], sources: [entityObjectSource("invoice_raw", "ERP", "DDS", "Invoice header contribution", 1)] },
        { logical_entity_name: "Order", logical_entity_definition: "Normalized Order header.", logical_entity_type: "transaction", logical_entity_type_detail: null, logical_entity_grain: "One Order", logical_entity_dependency_order: 20, logical_entity_confidence: "medium", logical_entity_status: "needs_review", logical_entity_is_locked: false, submodels: [submodelMembership("Order Management")], sources: [entityObjectSource("order_raw", "COMMERCE", "GDS", "Order header contribution", 1)] },
      ],
    },
    logical_attribute: {
      label: "Logical Attributes",
      columns: ["logical_entity_name", "logical_attribute_name", "logical_attribute_definition", "logical_attribute_data_type", "logical_attribute_is_nullable", "logical_attribute_is_primary_key", "logical_attribute_is_natural_key", "logical_attribute_is_surrogate_key", "logical_attribute_ordinal_position", "logical_attribute_is_audit_column", "logical_attribute_status", "logical_attribute_is_locked", "sources"],
      filters: ["logical_entity_name", "logical_attribute_data_type", "logical_attribute_status", "logical_attribute_is_locked"],
      rows: [
        { logical_entity_name: "Customer", logical_attribute_name: "customer_key", logical_attribute_definition: "Surrogate Customer key.", logical_attribute_data_type: "bigint", logical_attribute_is_nullable: false, logical_attribute_is_primary_key: true, logical_attribute_is_natural_key: false, logical_attribute_is_surrogate_key: true, logical_attribute_ordinal_position: 1, logical_attribute_is_audit_column: false, logical_attribute_status: "active", logical_attribute_is_locked: true, sources: [attributeObjectSource("customer_raw", "customer_id", "CRM", "GRDM", "Generates the Customer surrogate key", 1)] },
        { logical_entity_name: "Customer", logical_attribute_name: "customer_name", logical_attribute_definition: "Governed Customer name.", logical_attribute_data_type: "string", logical_attribute_is_nullable: false, logical_attribute_is_primary_key: false, logical_attribute_is_natural_key: false, logical_attribute_is_surrogate_key: false, logical_attribute_ordinal_position: 2, logical_attribute_is_audit_column: false, logical_attribute_status: "active", logical_attribute_is_locked: false, sources: [attributeObjectSource("customer_raw", "customer_name", "CRM", "GRDM", "Direct name source", 1)] },
        { logical_entity_name: "Invoice", logical_attribute_name: "invoice_number", logical_attribute_definition: "Business Invoice identifier.", logical_attribute_data_type: "string", logical_attribute_is_nullable: false, logical_attribute_is_primary_key: false, logical_attribute_is_natural_key: true, logical_attribute_is_surrogate_key: false, logical_attribute_ordinal_position: 2, logical_attribute_is_audit_column: false, logical_attribute_status: "needs_review", logical_attribute_is_locked: false, sources: [attributeObjectSource("invoice_raw", "invoice_id", "ERP", "DDS", "Invoice identifier source", 1), attributeAssertionSource("invoice.immutable_number", "Confirms identifier immutability", 2)] },
      ],
    },
    logical_relationship: {
      label: "Logical Relationships",
      columns: ["logical_relationship_name", "logical_relationship_definition", "from_logical_entity_name", "from_logical_attribute_name", "to_logical_entity_name", "to_logical_attribute_name", "logical_relationship_cardinality", "logical_relationship_confidence", "logical_relationship_basis", "logical_relationship_cardinality_basis", "logical_relationship_status", "logical_relationship_is_locked"],
      filters: ["logical_relationship_cardinality", "logical_relationship_confidence", "logical_relationship_status", "logical_relationship_is_locked"],
      rows: [
        { logical_relationship_name: "Customer to Invoice", logical_relationship_definition: "Customer receives Invoice.", from_logical_entity_name: "Customer", from_logical_attribute_name: "customer_key", to_logical_entity_name: "Invoice", to_logical_attribute_name: "customer_key", logical_relationship_cardinality: "one_to_many", logical_relationship_confidence: "high", logical_relationship_basis: "Shared Customer key", logical_relationship_cardinality_basis: "Validated physical relationship", logical_relationship_status: "active", logical_relationship_is_locked: true },
        { logical_relationship_name: "Customer to Order", logical_relationship_definition: "Customer places Order.", from_logical_entity_name: "Customer", from_logical_attribute_name: "customer_key", to_logical_entity_name: "Order", to_logical_attribute_name: "customer_key", logical_relationship_cardinality: "one_to_many", logical_relationship_confidence: "medium", logical_relationship_basis: "Shared Customer key", logical_relationship_cardinality_basis: "Inferred metadata", logical_relationship_status: "needs_review", logical_relationship_is_locked: false },
      ],
    },
    dimensional_submodel: {
      label: "Dimensional Submodels",
      columns: ["dimensional_submodel_name", "dimensional_submodel_definition", "dimensional_submodel_status", "dimensional_submodel_is_locked"],
      filters: ["dimensional_submodel_status", "dimensional_submodel_is_locked"],
      rows: [
        { dimensional_submodel_name: "Sales Analytics", dimensional_submodel_definition: "Customer sales analysis.", dimensional_submodel_status: "active", dimensional_submodel_is_locked: true },
        { dimensional_submodel_name: "Finance Analytics", dimensional_submodel_definition: "Invoice and payment analysis.", dimensional_submodel_status: "needs_review", dimensional_submodel_is_locked: false },
      ],
    },
    dimensional_entity: {
      label: "Dimensional Entities",
      columns: ["dimensional_entity_name", "dimensional_entity_definition", "dimensional_entity_type", "dimensional_fact_type", "dimensional_entity_grain_definition", "dimensional_entity_dependency_order", "dimensional_entity_confidence", "dimensional_entity_status", "dimensional_entity_is_locked", "submodels", "sources"],
      filters: ["submodels", "dimensional_entity_type", "dimensional_fact_type", "dimensional_entity_status", "dimensional_entity_is_locked"],
      rows: [
        { dimensional_entity_name: "Dim Customer", dimensional_entity_definition: "Conformed Customer dimension.", dimensional_entity_type: "dimension", dimensional_fact_type: null, dimensional_entity_grain_definition: null, dimensional_entity_dependency_order: 10, dimensional_entity_confidence: "high", dimensional_entity_status: "active", dimensional_entity_is_locked: true, submodels: [submodelMembership("Sales Analytics"), submodelMembership("Finance Analytics")], sources: [entityObjectSource("customer", "GDS", "NWA", "Conformed Customer source", 1, "dimension_source", "silver_nwa")] },
        { dimensional_entity_name: "Fact Sales", dimensional_entity_definition: "Order-line sales facts.", dimensional_entity_type: "fact", dimensional_fact_type: "transaction", dimensional_entity_grain_definition: "One Order line", dimensional_entity_dependency_order: 30, dimensional_entity_confidence: "high", dimensional_entity_status: "active", dimensional_entity_is_locked: false, submodels: [submodelMembership("Sales Analytics")], sources: [entityObjectSource("order", "GDS", "NWA", "Order header contribution", 1, "fact_header", "silver_nwa"), entityObjectSource("order_line", "GDS", "NWA", "Order-line grain contribution", 2, "fact_detail", "silver_nwa")] },
        { dimensional_entity_name: "Fact Invoice", dimensional_entity_definition: "Invoice financial facts.", dimensional_entity_type: "fact", dimensional_fact_type: "transaction", dimensional_entity_grain_definition: "One Invoice line", dimensional_entity_dependency_order: 30, dimensional_entity_confidence: "medium", dimensional_entity_status: "needs_review", dimensional_entity_is_locked: false, submodels: [submodelMembership("Finance Analytics")], sources: [entityObjectSource("invoice", "GDS", "NWA", "Invoice contribution", 1, "fact_source", "silver_nwa")] },
      ],
    },
    dimensional_attribute: {
      label: "Dimensional Attributes",
      columns: ["dimensional_entity_name", "dimensional_attribute_name", "dimensional_attribute_definition", "dimensional_attribute_data_type", "dimensional_attribute_is_nullable", "dimensional_attribute_ordinal_position", "dimensional_attribute_role", "dimensional_attribute_key_role", "dimensional_attribute_is_grain_component", "dimensional_attribute_additivity", "dimensional_attribute_default_aggregation", "dimensional_attribute_aggregation_basis", "dimensional_attribute_change_behavior", "dimensional_attribute_is_audit_column", "dimensional_attribute_confidence", "dimensional_attribute_status", "dimensional_attribute_is_locked", "sources"],
      filters: ["dimensional_entity_name", "dimensional_attribute_role", "dimensional_attribute_status", "dimensional_attribute_is_locked"],
      rows: [
        { dimensional_entity_name: "Dim Customer", dimensional_attribute_name: "customer_key", dimensional_attribute_definition: "Surrogate Customer key.", dimensional_attribute_data_type: "bigint", dimensional_attribute_is_nullable: false, dimensional_attribute_ordinal_position: 1, dimensional_attribute_role: "key", dimensional_attribute_key_role: "surrogate", dimensional_attribute_is_grain_component: false, dimensional_attribute_additivity: null, dimensional_attribute_default_aggregation: null, dimensional_attribute_aggregation_basis: null, dimensional_attribute_change_behavior: "fixed", dimensional_attribute_is_audit_column: false, dimensional_attribute_confidence: "high", dimensional_attribute_status: "active", dimensional_attribute_is_locked: true, sources: [attributeObjectSource("customer", "customer_key", "GDS", "NWA", "Conformed Customer key", 1, "silver_nwa")] },
        { dimensional_entity_name: "Fact Sales", dimensional_attribute_name: "sales_amount", dimensional_attribute_definition: "Extended sales amount.", dimensional_attribute_data_type: "decimal(18,2)", dimensional_attribute_is_nullable: false, dimensional_attribute_ordinal_position: 5, dimensional_attribute_role: "measure", dimensional_attribute_key_role: "none", dimensional_attribute_is_grain_component: false, dimensional_attribute_additivity: "additive", dimensional_attribute_default_aggregation: "sum", dimensional_attribute_aggregation_basis: "Fully additive", dimensional_attribute_change_behavior: null, dimensional_attribute_is_audit_column: false, dimensional_attribute_confidence: "high", dimensional_attribute_status: "active", dimensional_attribute_is_locked: false, sources: [attributeObjectSource("order_line", "sales_amount", "GDS", "NWA", "Extended sales amount source", 1, "silver_nwa")] },
      ],
    },
    dimensional_relationship: {
      label: "Dimensional Relationships",
      columns: ["dimensional_relationship_name", "dimensional_relationship_definition", "from_dimensional_entity_name", "from_dimensional_attribute_name", "to_dimensional_entity_name", "to_dimensional_attribute_name", "dimensional_relationship_kind", "dimensional_relationship_cardinality", "dimensional_relationship_role_name", "dimensional_relationship_confidence", "dimensional_relationship_basis", "dimensional_relationship_cardinality_basis", "dimensional_relationship_status", "dimensional_relationship_is_locked"],
      filters: ["dimensional_relationship_kind", "dimensional_relationship_cardinality", "dimensional_relationship_status", "dimensional_relationship_is_locked"],
      rows: [
        { dimensional_relationship_name: "Sales Customer", dimensional_relationship_definition: "Sales Facts reference Customer.", from_dimensional_entity_name: "Fact Sales", from_dimensional_attribute_name: "customer_key", to_dimensional_entity_name: "Dim Customer", to_dimensional_attribute_name: "customer_key", dimensional_relationship_kind: "foreign_key", dimensional_relationship_cardinality: "many_to_one", dimensional_relationship_role_name: "Customer", dimensional_relationship_confidence: "high", dimensional_relationship_basis: "Logical Mapping eligibility", dimensional_relationship_cardinality_basis: "Fact grain", dimensional_relationship_status: "active", dimensional_relationship_is_locked: true },
        { dimensional_relationship_name: "Invoice Customer", dimensional_relationship_definition: "Invoice Facts reference Customer.", from_dimensional_entity_name: "Fact Invoice", from_dimensional_attribute_name: "customer_key", to_dimensional_entity_name: "Dim Customer", to_dimensional_attribute_name: "customer_key", dimensional_relationship_kind: "foreign_key", dimensional_relationship_cardinality: "many_to_one", dimensional_relationship_role_name: "Bill-to Customer", dimensional_relationship_confidence: "medium", dimensional_relationship_basis: "Silver Invoice contribution", dimensional_relationship_cardinality_basis: "Invoice grain", dimensional_relationship_status: "needs_review", dimensional_relationship_is_locked: false },
      ],
    },
    mapping_dependency: {
      label: "Source Dependencies",
      columns: ["modeled_entity_type", "source_system_code", "source_system_dependency_order", "mapping_source_system_dependency_status", "mapping_source_system_dependency_is_locked"],
      filters: ["__model_name", "modeled_entity_type", "source_system_code"],
      rows: [
        { __model_name: "Customer 360", modeled_entity_type: "logical_entity", source_system_code: "CRM", source_system_dependency_order: 10, mapping_source_system_dependency_status: "active", mapping_source_system_dependency_is_locked: true },
        { __model_name: "Customer 360", modeled_entity_type: "logical_entity", source_system_code: "ERP", source_system_dependency_order: 20, mapping_source_system_dependency_status: "active", mapping_source_system_dependency_is_locked: false },
        { __model_name: "Customer 360", modeled_entity_type: "dimensional_entity", source_system_code: "GDS", source_system_dependency_order: 10, mapping_source_system_dependency_status: "needs_review", mapping_source_system_dependency_is_locked: false },
      ],
    },
    mapping_object: {
      label: "Object Mappings",
      columns: ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "source_system_code", "modeled_entity_type", "modeled_entity_name", "object_dependency_order", "artifact_type", "artifact_generation_instructions", "mapping_profile_key", "mapping_profile_version", "mapping_package_document", "object_mapping_transformation_document", "object_mapping_status", "object_mapping_is_locked"],
      filters: ["__model_name", "modeled_entity_type", "source_system_code"],
      rows: [
        { __model_name: "Customer 360", tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "silver_nwa", object_name: "customer", source_system_code: "CRM", modeled_entity_type: "logical_entity", modeled_entity_name: "Customer", object_dependency_order: 10, artifact_type: "sql_file", artifact_generation_instructions: "Generate idempotent Databricks SQL.", mapping_profile_key: "standard.logical", mapping_profile_version: "1.0.0", mapping_package_document: { source_objects: [physicalObject("customer_raw", "CRM", "GRDM"), physicalObject("customer_address_raw", "CRM", "GRDM")], target_grain: "One governed Customer", load_pattern: "incremental_merge", business_keys: ["customer_id"] }, object_mapping_transformation_document: { schema_version: "1.0", transformation_kind: "derived", join_strategy: { base_object: "customer_raw", joins: [{ object_name: "customer_address_raw", join_type: "left", condition: "customer_raw.customer_id = customer_address_raw.customer_id" }] }, filter_criteria: ["customer_raw.is_deleted = false"], transformation_steps: ["Resolve one current address per Customer", "Apply governed audit columns"] }, object_mapping_status: "active", object_mapping_is_locked: true },
        { __model_name: "Customer 360", tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "silver_nwa", object_name: "invoice", source_system_code: "ERP", modeled_entity_type: "logical_entity", modeled_entity_name: "Invoice", object_dependency_order: 20, artifact_type: "sql_file", artifact_generation_instructions: "Generate incremental Databricks SQL.", mapping_profile_key: "standard.logical", mapping_profile_version: "1.0.0", mapping_package_document: { source_objects: [physicalObject("invoice_raw", "ERP", "DDS")], target_grain: "One issued Invoice", load_pattern: "incremental_merge", business_keys: ["invoice_id"] }, object_mapping_transformation_document: { schema_version: "1.0", transformation_kind: "direct", filter_criteria: ["invoice_raw.is_deleted = false"], transformation_steps: ["Rename source attributes", "Apply governed audit columns"] }, object_mapping_status: "needs_review", object_mapping_is_locked: false },
        { __model_name: "Customer 360", tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "gold_nwa", object_name: "fact_sales", source_system_code: "GDS", modeled_entity_type: "dimensional_entity", modeled_entity_name: "Fact Sales", object_dependency_order: 30, artifact_type: "sql_file", artifact_generation_instructions: "Generate fact load SQL.", mapping_profile_key: "standard.dimensional", mapping_profile_version: "1.0.0", mapping_package_document: { source_objects: [physicalObject("order", "GDS", "NWA", "silver_nwa"), physicalObject("order_line", "GDS", "NWA", "silver_nwa")], target_grain: "One Order line", load_pattern: "incremental_append", business_keys: ["order_id", "order_line_id"] }, object_mapping_transformation_document: { schema_version: "1.0", transformation_kind: "derived", join_strategy: { base_object: "order_line", joins: [{ object_name: "order", join_type: "inner", condition: "order_line.order_id = order.order_id" }] }, measures: [{ target_attribute: "sales_amount", expression: "quantity * unit_price" }], transformation_steps: ["Join Order header", "Derive additive measures", "Resolve dimension keys"] }, object_mapping_status: "active", object_mapping_is_locked: false },
      ],
    },
    mapping_attribute: {
      label: "Attribute Mappings",
      columns: ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "attribute_name", "source_system_code", "modeled_entity_type", "modeled_entity_name", "modeled_attribute_name", "attribute_mapping_transformation_document", "attribute_mapping_status", "attribute_mapping_is_locked"],
      filters: ["__model_name", "modeled_entity_type", "source_system_code"],
      rows: [
        { __model_name: "Customer 360", tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "silver_nwa", object_name: "customer", attribute_name: "customer_key", source_system_code: "CRM", modeled_entity_type: "logical_entity", modeled_entity_name: "Customer", modeled_attribute_name: "customer_key", attribute_mapping_transformation_document: { schema_version: "1.0", transformation_kind: "direct", source_attributes: [{ ...physicalObject("customer_raw", "CRM", "GRDM"), attribute_name: "customer_id" }], expression: "customer_raw.customer_id", null_handling: "Reject null business keys", data_type_handling: "CAST AS BIGINT" }, attribute_mapping_status: "active", attribute_mapping_is_locked: true },
        { __model_name: "Customer 360", tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "silver_nwa", object_name: "customer", attribute_name: "customer_name", source_system_code: "CRM", modeled_entity_type: "logical_entity", modeled_entity_name: "Customer", modeled_attribute_name: "customer_name", attribute_mapping_transformation_document: { schema_version: "1.0", transformation_kind: "expression", source_attributes: [{ ...physicalObject("customer_raw", "CRM", "GRDM"), attribute_name: "customer_name" }], expression: "TRIM(customer_raw.customer_name)", null_handling: "Preserve null", data_type_handling: "STRING" }, attribute_mapping_status: "active", attribute_mapping_is_locked: false },
        { __model_name: "Customer 360", tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "gold_nwa", object_name: "fact_sales", attribute_name: "sales_amount", source_system_code: "GDS", modeled_entity_type: "dimensional_entity", modeled_entity_name: "Fact Sales", modeled_attribute_name: "sales_amount", attribute_mapping_transformation_document: { schema_version: "1.0", transformation_kind: "expression", source_attributes: [{ ...physicalObject("order_line", "GDS", "NWA", "silver_nwa"), attribute_name: "quantity" }, { ...physicalObject("order_line", "GDS", "NWA", "silver_nwa"), attribute_name: "unit_price" }], expression: "quantity * unit_price", null_handling: "Treat missing quantity as zero", data_type_handling: "DECIMAL(18,2)" }, attribute_mapping_status: "needs_review", attribute_mapping_is_locked: false },
      ],
    },
  };

  const metadataGroups = {
    reference: [
      { id: "system_type", label: "System types", count: 5 },
      { id: "connection_type", label: "Connection types", count: 4 },
      { id: "object_type", label: "Object types", count: 4 },
      { id: "zone", label: "Zones", count: 4 },
      { id: "chunk_type", label: "Chunk types", count: 3 },
      { id: "file_type", label: "File types", count: 3 },
      { id: "data_operation", label: "Data operations", count: 4 },
      { id: "process_type", label: "Process types", count: 3 },
    ],
    foundational: [
      { id: "project", label: "Projects", count: 1 },
      { id: "tenant", label: "Tenants", count: 4 },
      { id: "system", label: "Systems", count: 3 },
      { id: "connection", label: "Connections", count: 4 },
      { id: "tenant_metadata_discovery_scope", label: "Metadata discovery scopes", count: 6 },
    ],
    operational: [
      { id: "source_object", label: "Source objects", count: 62 },
      { id: "source_attribute", label: "Source attributes", count: 724 },
      { id: "bronze_object", label: "Bronze objects", count: 95 },
      { id: "bronze_attribute", label: "Bronze attributes", count: 1120 },
      { id: "silver_object", label: "Silver objects", count: 18 },
      { id: "silver_attribute", label: "Silver attributes", count: 210 },
      { id: "gold_object", label: "Gold objects", count: 12 },
      { id: "gold_attribute", label: "Gold attributes", count: 92 },
      { id: "ingestion_object_mapping", label: "Ingestion object mappings", count: 84 },
      { id: "ingestion_attribute_mapping", label: "Ingestion attribute mappings", count: 1218 },
      { id: "copy_group", label: "Copy groups", count: 12 },
      { id: "member_group", label: "Member groups", count: 18 },
      { id: "copy_group_control", label: "Copy group controls", count: 18 },
      { id: "copy", label: "Copies", count: 84 },
      { id: "process_group", label: "Process groups", count: 9 },
      { id: "process", label: "Processes", count: 47 },
    ],
  };

  const objectMetadataColumns = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "fc_object_schema", "fc_object_name", "object_transformation", "object_description", "batch_attribute_name", "object_type_code", "zone_code", "is_locked", "is_active"];
  const attributeMetadataColumns = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "attribute_name", "fc_attribute_name", "attribute_ordinal_position", "attribute_description", "attribute_data_type", "attribute_nullability", "attribute_custom_code", "is_surrogate_key", "is_natural_key", "is_meta_data", "is_masking_required", "is_mapped", "is_purge", "is_active"];
  const metadataColumns = {
    project: ["project_code", "project_name", "project_description", "is_active"],
    tenant: ["tenant_code", "project_code", "tenant_name", "tenant_description", "tenant_catalog", "gds_admin_catalog", "gds_connection_tenant_code", "gds_connection_system_code", "gds_connection_code", "tenant_visibility", "is_active"],
    system: ["system_code", "system_name", "system_description", "system_type_code", "is_active"],
    connection: ["tenant_code", "system_code", "connection_code", "connection_name", "connection_type_code", "has_foreign_catalog", "foreign_catalog", "is_global_data_store", "is_active"],
    tenant_metadata_discovery_scope: ["scope_tenant_code", "connection_tenant_code", "connection_system_code", "connection_code", "zone_code", "object_schema", "is_active"],
    system_type: ["system_type_code", "system_type_name", "system_type_description", "is_active"],
    connection_type: ["connection_type_code", "connection_type_name", "connection_type_description", "is_active"],
    object_type: ["object_type_code", "object_type_name", "object_type_description", "is_active"],
    zone: ["zone_code", "zone_name", "zone_description", "is_active"],
    chunk_type: ["chunk_type_name", "chunk_type_description", "is_active"],
    file_type: ["file_type_name", "file_type_description", "is_active"],
    data_operation: ["data_operation_name", "data_operation_description", "is_active"],
    process_type: ["process_type_name", "process_type_description", "is_active"],
    source_object: objectMetadataColumns,
    bronze_object: objectMetadataColumns,
    silver_object: objectMetadataColumns,
    gold_object: objectMetadataColumns,
    source_attribute: attributeMetadataColumns,
    bronze_attribute: attributeMetadataColumns,
    silver_attribute: attributeMetadataColumns,
    gold_attribute: attributeMetadataColumns,
    ingestion_object_mapping: ["source_tenant_code", "source_system_code", "source_connection_code", "source_object_schema", "source_object_name", "target_tenant_code", "target_system_code", "target_connection_code", "target_object_schema", "target_object_name", "is_active"],
    ingestion_attribute_mapping: ["source_tenant_code", "source_system_code", "source_connection_code", "source_object_schema", "source_object_name", "source_attribute_name", "target_tenant_code", "target_system_code", "target_connection_code", "target_object_schema", "target_object_name", "target_attribute_name", "is_active"],
    copy_group: ["tenant_code", "system_code", "copy_group_name", "copy_group_description", "is_member_group_required", "is_active"],
    member_group: ["tenant_code", "system_code", "member_group_name", "member_group_description", "member_group_initial_load_date", "is_active"],
    copy_group_control: ["tenant_code", "system_code", "copy_group_name", "member_group_name", "copy_group_control_initial_load_date", "copy_group_control_last_run_time", "copy_group_control_last_run_value"],
    copy: ["tenant_code", "system_code", "copy_group_name", "source_tenant_code", "source_system_code", "source_connection_code", "source_object_schema", "source_object_name", "target_tenant_code", "target_system_code", "target_connection_code", "target_object_schema", "target_object_name", "copy_source_record_limit", "copy_source_record_limit_attribute", "chunk_type_name", "copy_source_initial_sql_script", "copy_source_incremental_sql_script", "copy_source_file_name", "copy_source_file_pattern", "copy_source_file_delimiter", "source_file_type_name", "copy_source_order", "source_data_operation_name", "target_data_operation_name", "is_active"],
    process_group: ["tenant_code", "system_code", "zone_code", "process_group_name", "process_group_description", "copy_group_name", "is_active"],
    process: ["tenant_code", "system_code", "zone_code", "process_group_name", "process_execution_order", "process_location", "process_executable", "object_tenant_code", "object_system_code", "object_connection_code", "object_schema", "object_name", "process_type_name", "is_active"],
  };

  const metadataFilters = {
    project: ["is_active"], tenant: ["project_code", "tenant_visibility", "is_active"], system: ["system_type_code", "is_active"], connection: ["system_code", "connection_type_code", "is_active"],
    tenant_metadata_discovery_scope: ["connection_system_code", "zone_code", "is_active"],
    system_type: ["is_active"], connection_type: ["is_active"], object_type: ["is_active"], zone: ["is_active"], chunk_type: ["is_active"], file_type: ["is_active"], data_operation: ["is_active"], process_type: ["is_active"],
    ingestion_object_mapping: ["source_system_code", "target_system_code", "is_active"], ingestion_attribute_mapping: ["source_system_code", "target_system_code", "is_active"],
    copy_group: ["system_code", "is_member_group_required", "is_active"], member_group: ["system_code", "is_active"], copy_group_control: ["system_code", "member_group_name"],
    copy: ["system_code", "source_data_operation_name", "target_data_operation_name", "is_active"], process_group: ["system_code", "zone_code", "is_active"], process: ["system_code", "process_type_name", "is_active"],
  };
  ["source", "bronze", "silver", "gold"].forEach((zone) => {
    metadataFilters[`${zone}_object`] = ["system_code", "object_type_code", "is_locked", "is_active"];
    metadataFilters[`${zone}_attribute`] = ["system_code", "object_name", "attribute_data_type", "is_active"];
  });

  const operationalExportSheets = [
    ["Source Objects", 62], ["Source Attributes", 724],
    ["Bronze Objects", 95], ["Bronze Attributes", 1120],
    ["Silver Objects", 18], ["Silver Attributes", 210],
    ["Gold Objects", 12], ["Gold Attributes", 92],
    ["Ingestion Object Mappings", 84], ["Ingestion Attribute Mappings", 1218],
    ["Copy Groups", 12], ["Member Groups", 18], ["Copy Group Controls", 18],
    ["Copies", 84], ["Process Groups", 9], ["Processes", 47],
  ];

  const allowedScreens = new Set(["tenant-select", "tenant-home", "metadata", "models", "model-home", "scope", "profiling", "analysis", "assertions", "conceptual", "logical", "dimensional", "mapping", "mapping-logical", "mapping-dimensional", "record-detail", "code", "code-model"]);
  const refreshableStages = new Set(["profiling", "analysis", "conceptual", "logical", "dimensional"]);
  const initialRecordDetail = queryRecordDetail();
  const state = {
    screen: queryScreen(), selectedTenant: "northwind", activeObject: "customer_raw", activeMetadataObject: "customer_raw", activeProfileRun: "PR-1048", activeAnalysisRun: "AN-0318",
    selectedScope: new Set(), selectedProfile: new Set(), selectedFindings: new Set(), selectedCandidates: new Set(), selectedContractRows: new Set(), selectedCodeTargets: new Set(),
    metaSection: "operational", metaDataset: "bronze_object", metadataDetailOpen: false, scopeDetailOpen: false, runDetailOpen: false, activeRunId: null, profilingView: "results", analysisView: "all", panel: null, lockState: "other", running: false, showInactive: false,
    assertionDataset: "modeling_assertion_record", conceptualDataset: "conceptual_object", logicalDataset: "logical_entity", dimensionalDataset: "dimensional_entity", mappingDataset: "mapping_object", contractDetailOpen: false, activeContractRow: initialRecordDetail?.active || null, detailReturnScreen: initialRecordDetail?.origin || "conceptual", codeView: "generate", activeCodeTarget: "customer",
    candidateFilters: { tenant: "all", system: "all", zone: "all", search: "" },
  };

  function object(name, system, tenant, attributeCount, batchAttribute, profileStatus, rowCount, freshness, nullRate, uniqueRate) {
    return { id: name, name, system, tenant, zone: "Bronze", attributeCount, batchAttribute, profileStatus, rowCount, freshness, nullRate, uniqueRate };
  }
  function zonedObject(name, system, tenant, zone, attributeCount) {
    const row = object(name, system, tenant, attributeCount, null, "Not profiled", "—", "—", "—", "—");
    row.zone = zone;
    return row;
  }
  function finding(fromObject, fromAttribute, toObject, toAttribute, type, confidence, validation, locked) {
    return { id: `${fromObject}.${fromAttribute}-${toObject}.${toAttribute}`, fromObject, fromAttribute, toObject, toAttribute, type, confidence, validation, locked, active: true };
  }
  function run(id, status, started, system, objectCount, batch, actor, duration) { return { id, status, started, system, objectCount, batch, actor, duration }; }
  function physicalObject(name, system, tenant, schema = `bronze_${system.toLowerCase()}`) {
    return { tenant_code: tenant, system_code: system, connection_code: `${system.toLowerCase()}_prod`, object_schema: schema, object_name: name };
  }
  function objectSupport(name, system, tenant, reason, role = "primary") {
    return { support_source_type: "object", source_object: physicalObject(name, system, tenant), support_role: role, support_reason: reason, support_reason_detail: null, support_confidence: "high", support_status: "active", support_is_locked: false };
  }
  function assertionSupport(key, reason, role = "business_rule") {
    return { support_source_type: "assertion", assertion_record: { modeling_assertion_record_key: key }, support_role: role, support_reason: reason, support_reason_detail: null, support_confidence: "high", support_status: "active", support_is_locked: true };
  }
  function submodelMembership(name) { return { submodel_name: name, membership_status: "active", membership_is_locked: false }; }
  function entityObjectSource(name, system, tenant, rationale, order, role = null, schema) {
    const source = { support_source_type: "object", source_object: physicalObject(name, system, tenant, schema), source_order: order, rationale, status: "active", is_locked: false };
    if (role) source.source_role = role;
    return source;
  }
  function attributeObjectSource(name, attribute, system, tenant, rationale, order, schema) {
    return { support_source_type: "attribute", source_attribute: { ...physicalObject(name, system, tenant, schema), attribute_name: attribute }, source_order: order, rationale, status: "active", is_locked: false };
  }
  function attributeAssertionSource(key, rationale, order) {
    return { support_source_type: "assertion", assertion_record: { modeling_assertion_record_key: key }, source_order: order, rationale, status: "active", is_locked: true };
  }
  function storedSql(targetSchema, targetName, sourceSchema, sourceName) {
    return `CREATE OR REPLACE TABLE ${targetSchema}.${targetName} AS\nSELECT\n    *\nFROM ${sourceSchema}.${sourceName};`;
  }
  function queryScreen() { const screen = new URLSearchParams(window.location.search).get("screen"); return allowedScreens.has(screen) ? screen : "tenant-select"; }
  function queryRecordDetail() {
    const query = new URLSearchParams(window.location.search);
    const dataset = query.get("dataset");
    const index = Number(query.get("row"));
    const origin = query.get("origin");
    if (!dataset || !modelContracts[dataset] || !Number.isInteger(index)) return null;
    return { active: { dataset, index }, origin: allowedScreens.has(origin) && origin !== "record-detail" ? origin : dataset.startsWith("mapping_") ? "mapping-logical" : dataset.split("_")[0] };
  }
  function currentTenant() { return tenants.find((tenant) => tenant.id === state.selectedTenant) || tenants[0]; }

  function navIcon(name) {
    const paths = {
      home: '<path d="M3.5 8.4 8 4.5l4.5 3.9v4.1a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1Z"/><path d="M6.4 13.4V9.8h3.2v3.6"/>',
      metadata: '<ellipse cx="8" cy="4" rx="4.7" ry="2"/><path d="M3.3 4v4c0 1.1 2.1 2 4.7 2s4.7-.9 4.7-2V4M3.3 8v4c0 1.1 2.1 2 4.7 2s4.7-.9 4.7-2V8"/>',
      models: '<rect x="2.8" y="3" width="4" height="4" rx=".7"/><rect x="9.2" y="3" width="4" height="4" rx=".7"/><rect x="6" y="10" width="4" height="4" rx=".7"/><path d="M4.8 7v1.2H8m3.2-1.2v1.2H8m0 0V10"/>',
      mapping: '<path d="M3 5h7.5M8.7 2.8 11 5 8.7 7.2M13 11H5.5M7.3 8.8 5 11l2.3 2.2"/>',
      code: '<path d="m6.2 3.5-4 4.5 4 4.5M9.8 3.5l4 4.5-4 4.5"/>',
      admin: '<path d="M8 2.3 13 4v3.7c0 3.1-2 5.3-5 6.2-3-.9-5-3.1-5-6.2V4Z"/><path d="m5.8 8 1.4 1.4 3-3"/>',
    };
    return `<svg aria-hidden="true" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
  }

  function tenantSelectPage() {
    return `<div class="entry-shell"><header class="entry-topbar"><div class="entry-brand"><span class="brand-mark">G</span><strong>GDS</strong><span>Workbench</span></div><div class="entry-user"><span>Signed in as</span><strong>Maaz</strong><i>M</i></div></header><main class="tenant-entry"><section class="tenant-entry-heading"><small>AVAILABLE WORKSPACES</small><h1>Choose a Tenant</h1></section><div class="tenant-search-row"><label class="search tenant-search"><span>${navIcon("metadata")}</span><input data-tenant-filter placeholder="Search Tenants by name or code" autofocus></label><span>${tenants.length} available</span></div><section class="tenant-cards">${tenants.map(tenantCard).join("")}</section><footer class="tenant-entry-footer"><div><strong>${currentTenant().name}</strong><span>${currentTenant().role} · ${currentTenant().environment}</span></div><button class="button button-primary enter-button" data-action="enter-tenant">Enter Workbench <span>→</span></button></footer></main><p class="entry-prototype-note">Interactive prototype · no external systems or databases are contacted.</p></div>`;
  }
  function tenantCard(tenant) {
    const selected = tenant.id === state.selectedTenant;
    return `<button class="tenant-card ${selected ? "is-selected" : ""}" data-tenant-id="${tenant.id}" data-tenant-search="${tenant.name.toLowerCase()} ${tenant.code.toLowerCase()}"><span class="tenant-monogram">${tenant.code.slice(0, 2)}</span><span class="tenant-card-copy"><span class="tenant-title"><strong>${tenant.name}</strong>${tenant.isLast ? '<em>Last accessed</em>' : ""}</span><small>${tenant.code} · ${tenant.environment}</small><span class="tenant-card-meta"><span>${tenant.role}</span><span>${tenant.systems} systems</span><span>${tenant.objects} Objects</span></span></span><i>${selected ? "✓" : "→"}</i></button>`;
  }

  function shell(content, activeNav, modelOpen) {
    const tenant = currentTenant();
    const navItems = [["Home", "tenant-home", "home"], ["Metadata", "metadata", "metadata"], ["Models", "models", "models"], ["Mapping", "mapping", "mapping"], ["Code generation", "code", "code"], ["Administration", "administration", "admin"]];
    return `<div class="app-shell"><header class="topbar"><button class="brand" data-nav="tenant-select"><span class="brand-mark">G</span><strong>GDS</strong><span>Workbench</span></button><div class="tenant-context"><strong>${tenant.name}</strong><span>${tenant.code}</span>${modelOpen ? `<i></i><small>MODEL</small><strong>Customer 360</strong><span>r18</span>` : ""}</div><div class="topbar-actions"><button class="switch-tenant" data-nav="tenant-select">Switch Tenant</button><span class="role-badge">${tenant.role}</span><span class="user-avatar">M</span></div></header><aside class="sidebar"><small class="nav-label">WORKSPACE</small><nav>${navItems.map(([label, key, icon]) => `<button class="nav-item ${activeNav === key ? "is-active" : ""}" ${allowedScreens.has(key) ? `data-nav="${key}"` : `data-action="${key}"`}>${navIcon(icon)}<span>${label}</span></button>`).join("")}</nav>${modelOpen ? `<div class="open-model"><small>OPEN MODEL</small><strong>Customer 360</strong><span>Owner · Northwind Analytics</span><button data-nav="model-home">Model overview →</button></div>` : ""}<p class="prototype-note">Prototype only.<br>Actions are in-memory.</p></aside><main class="workspace ${modelOpen ? "is-model" : ""}">${content}</main></div>`;
  }
  function workflowBar(tabs, actions = "", leading = "") {
    const refresh = refreshableStages.has(state.screen) ? '<button class="button" data-action="refresh-results">Refresh</button>' : "";
    return `<header class="section-bar model-workflow-bar"><div class="workflow-leading">${leading}</div><nav class="section-tabs">${tabs}</nav><div class="section-actions">${refresh}${actions}</div></header>`;
  }

  function tenantHomePage() {
    return shell(`<div class="tenant-home-page">${tenantLockPanel()}<section class="systems-section"><header><div><small>REGISTERED METADATA</small><h2>Systems</h2></div><button class="text-action" data-nav="metadata">Open Metadata →</button></header><div class="table-scroll"><table class="data-table systems-table"><thead><tr><th>System</th><th>Type</th><th>Connections</th><th>Registered Objects</th><th>Used by Models</th><th>Last metadata sync</th></tr></thead><tbody><tr><td><strong>Customer Relationship Management</strong><span>CRM</span></td><td>Salesforce</td><td>1</td><td>63</td><td>2 Models</td><td><em class="sync-state">38m ago</em></td></tr><tr><td><strong>Enterprise Resource Planning</strong><span>ERP</span></td><td>SAP</td><td>2</td><td>82</td><td>3 Models</td><td><em class="sync-state">1h ago</em></td></tr><tr><td><strong>Digital Commerce</strong><span>COMMERCE</span></td><td>Databricks</td><td>1</td><td>42</td><td>1 Model</td><td><em class="sync-state">2h ago</em></td></tr></tbody></table></div></section></div>`, "tenant-home", false);
  }

  function tenantLockPanel() {
    let stateMarkup;
    if (state.lockState === "mine") {
      stateMarkup = `<div class="lock-state-summary"><div class="lock-principal mine"><span class="lock-avatar">M</span><div><small>HELD BY YOU</small><strong>Maaz</strong><span>Tenant Admin</span></div></div><dl class="lock-facts"><div><dt>Expires</dt><dd>Today, 3:46 PM</dd></div><div><dt>Remaining</dt><dd>54 minutes</dd></div></dl></div><aside class="lock-action-panel"><div><small>AVAILABLE ACTIONS</small><strong>Manage your lock</strong><span>Extend the lease or release it when protected work is complete.</span></div><div class="lock-focus-actions"><button class="button button-primary" data-action="renew-lock">Extend 1 hour</button><button class="button" data-action="release-lock">Release lock</button><button class="button" data-action="lock-history">View history</button></div></aside>`;
    } else if (state.lockState === "unlocked") {
      stateMarkup = `<div class="lock-state-summary"><div class="lock-principal unlocked"><span class="lock-avatar">✓</span><div><small>AVAILABLE</small><strong>No active owner</strong><span>The Tenant is currently unlocked.</span></div></div><dl class="lock-facts"><div><dt>Write access</dt><dd>Lock required</dd></div><div><dt>Maximum duration</dt><dd>4 hours</dd></div></dl></div><aside class="lock-action-panel"><div><small>AVAILABLE ACTIONS</small><strong>Acquire governed access</strong><span>Protected Tenant changes require explicit lock ownership.</span></div><div class="lock-focus-actions"><button class="button button-primary" data-action="acquire-lock">Acquire lock</button><button class="button" data-action="lock-history">View history</button></div></aside>`;
    } else {
      stateMarkup = `<div class="lock-state-summary"><div class="lock-principal"><span class="lock-avatar">EM</span><div><small>CURRENT OWNER</small><strong>Elena Morris</strong><span>Architect</span></div></div><dl class="lock-facts"><div><dt>Expires</dt><dd>Today, 3:12 PM</dd></div><div><dt>Purpose</dt><dd>Metadata review</dd></div></dl></div><aside class="lock-action-panel"><div><small>AVAILABLE ACTIONS</small><strong>Lock owned by another user</strong><span>An override requires a reason and creates a governed audit event.</span></div><div class="lock-focus-actions"><button class="button button-primary" data-action="open-override">Override & acquire</button><button class="button" data-action="lock-history">View history</button></div></aside>${state.panel === "override-lock" ? `<div class="override-form"><label><span>Required reason</span><input id="override-reason" value="Continue approved metadata review"></label><div><button class="button button-small" data-action="cancel-override">Cancel</button><button class="button button-small button-primary" data-action="confirm-override">Confirm explicit override</button></div></div>` : ""}`;
    }
    return `<section class="tenant-lock-focus"><header><div><small>GOVERNED WRITE ACCESS</small><h1>Tenant Lock</h1><p>Controls protected changes for ${currentTenant().name}.</p></div><span class="lock-status ${state.lockState}">${state.lockState === "mine" ? "Owned by you" : state.lockState === "unlocked" ? "Unlocked" : "Locked by another user"}</span></header><div class="lock-focus-body">${stateMarkup}</div></section>`;
  }

  function metadataPage() {
    const sectionTabs = ["reference", "foundational", "operational"].map((section) => `<button class="${state.metaSection === section ? "is-active" : ""}" data-meta-section="${section}">${titleCase(section)}</button>`).join("");
    const canEdit = state.metaSection === "operational" && state.lockState === "mine";
    const permission = state.metaSection === "operational"
      ? canEdit ? '<span class="permission editable">Tenant Lock held · editing available</span>' : '<span class="permission">Read only · Tenant Lock required</span>'
      : '<span class="permission">Read only · Super Admin managed</span>';
    const excelAction = state.metaSection === "operational" ? `<button class="button" data-action="import-metadata" ${canEdit ? "" : "disabled"} title="${canEdit ? "Import Operational metadata" : "Acquire the Tenant Lock to import"}">Import Excel</button><button class="button button-primary" data-action="open-metadata-export">Export Excel</button>` : "";
    return shell(`<header class="metadata-commandbar"><div class="metadata-command-state">${permission}</div><nav class="metadata-mode-tabs">${sectionTabs}</nav><div class="metadata-command-actions">${excelAction}</div>${state.panel === "metadata-export" ? metadataExportPopover() : ""}</header><div class="metadata-layout"><aside class="metadata-index"><nav>${metadataGroups[state.metaSection].map((item) => `<button class="${state.metaDataset === item.id ? "is-active" : ""}" data-meta-dataset="${item.id}"><span>${item.label}</span><em>${item.count.toLocaleString()}</em></button>`).join("")}</nav><div class="metadata-boundary"><strong>${state.metaSection === "operational" ? "Tenant-scoped" : "Shared definitions"}</strong><span>${state.metaSection === "operational" ? "Protected writes require authorization and the Tenant Lock." : "Changes are managed centrally by a Super Admin."}</span></div></aside><section class="metadata-surface">${metadataSurface()}</section></div>`, "metadata", false);
  }

  function metadataExportPopover() {
    return `<aside class="metadata-export-popover"><header><div><small>OPERATIONAL ONLY · PLUGIN-COMPATIBLE</small><strong>Export Excel sheets</strong></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="export-sheet-list">${operationalExportSheets.map((sheet, index) => `<label><input type="checkbox" ${index === 0 ? "checked" : ""}><span>${sheet[0]}</span><em>${sheet[1].toLocaleString()}</em></label>`).join("")}</div><footer><button class="text-action" data-action="select-export-sheets">Select all</button><button class="button button-small" data-action="export-selected-sheets">Download selected</button><button class="button button-small button-primary" data-action="export-all-sheets">Download all 16 sheets</button></footer></aside>`;
  }

  function metadataSurface() {
    const dataset = metadataGroups[state.metaSection].find((item) => item.id === state.metaDataset) || metadataGroups[state.metaSection][0];
    const columns = metadataColumns[dataset.id];
    const rows = metadataRowsFor(dataset.id);
    const filters = metadataFilters[dataset.id] || [];
    const canEdit = state.metaSection === "operational" && state.lockState === "mine";
    const isObjectSheet = dataset.id.endsWith("_object");
    const filterControls = filters.map((field) => metadataFilterControl(field, rows)).join("");
    const addAction = state.metaSection === "operational" ? `<button class="button button-primary" data-action="metadata-add-row" ${canEdit ? "" : "disabled"} title="${canEdit ? `Add a ${dataset.label} row` : "Acquire the Tenant Lock to add rows"}">+ Add Row</button>` : "";
    const width = Math.max(920, (columns.length * 142) + (state.metaSection === "operational" ? 150 : 0));
    const active = findMetadataObject(state.activeMetadataObject);
    return `<div class="surface-toolbar metadata-controls"><div class="metadata-filter-set">${filterControls}</div><div class="metadata-sheet-actions">${addAction}</div></div><div class="catalog-layout ${state.metadataDetailOpen && isObjectSheet ? "has-inspector" : ""}"><section class="data-region"><div class="table-scroll metadata-ledger-scroll"><table id="metadata-contract-table" class="data-table metadata-contract-table" style="min-width:${width}px"><thead><tr>${columns.map((field) => `<th title="${field}">${field}</th>`).join("")}${state.metaSection === "operational" ? "<th class=\"metadata-row-action-heading\">Actions</th>" : ""}</tr></thead><tbody>${rows.map((row, index) => metadataRowMarkup(row, index, columns, filters, isObjectSheet, canEdit)).join("")}</tbody></table></div></section>${state.metadataDetailOpen && isObjectSheet ? metadataInspector(active) : ""}</div>`;
  }

  function metadataFilterControl(field, rows) {
    const values = [...new Set(rows.map((row) => row[field]).filter((value) => value !== null && value !== undefined && value !== "—").map(String))];
    return `<label class="metadata-filter"><span>${field.replaceAll("_", " ")}</span><select data-metadata-filter="${field}"><option value="all">All</option>${values.map((value) => `<option value="${value}">${metadataDisplayValue(value)}</option>`).join("")}</select></label>`;
  }

  function metadataRowMarkup(row, index, columns, filters, isObjectSheet, canEdit) {
    const filterAttributes = filters.map((field) => `data-filter-${field}="${String(row[field])}"`).join(" ");
    const active = isObjectSheet && state.metadataDetailOpen && row.__id === state.activeMetadataObject ? "is-active" : "";
    const cells = columns.map((field, cellIndex) => `<td class="${metadataCellClass(field)}">${metadataCellMarkup(row[field], field, cellIndex === 0)}</td>`).join("");
    const details = isObjectSheet && row.__id ? `<button class="text-action detail-action" data-show-metadata-detail="${row.__id}">Show details</button>` : "";
    const edit = state.metaSection === "operational" ? `<button class="button button-small metadata-edit-row" data-edit-metadata-row="${index}" ${canEdit ? "" : "disabled"} title="${canEdit ? "Edit this row" : "Acquire the Tenant Lock to edit"}">Edit</button>` : "";
    return `<tr class="${active}" ${filterAttributes}>${cells}${state.metaSection === "operational" ? `<td class="metadata-row-actions"><div>${details}${edit}</div></td>` : ""}</tr>`;
  }

  function metadataCellMarkup(value, field, isPrimary) {
    if (typeof value === "boolean") return `<em class="status ${value ? "complete" : "neutral"}">${value ? "Yes" : "No"}</em>`;
    if (field === "zone_code") return `<em class="zone">${titleCase(String(value))}</em>`;
    if (value === null || value === undefined || value === "—") return '<span class="metadata-empty">—</span>';
    return isPrimary ? `<strong>${value}</strong>` : String(value);
  }

  function metadataCellClass(field) {
    return field.includes("description") || field.includes("script") || field.includes("transformation") ? "metadata-long-cell" : "";
  }

  function metadataDisplayValue(value) {
    if (value === "true") return "Yes";
    if (value === "false") return "No";
    return titleCase(String(value).replaceAll("_", " "));
  }

  function metadataRowsFor(dataset) {
    const zone = dataset.split("_")[0];
    if (dataset.endsWith("_object")) {
      return metadataObjectRows.filter((item) => item.zone.toLowerCase() === zone).map((item, index, rows) => ({
        __id: item.id,
        tenant_code: item.tenant,
        system_code: item.system,
        connection_code: `${item.system.toLowerCase()}_prod`,
        object_schema: `${zone}_${item.system.toLowerCase()}`,
        object_name: item.name,
        fc_object_schema: zone === "source" ? `src_${item.system.toLowerCase()}` : "—",
        fc_object_name: zone === "source" ? item.name : "—",
        object_transformation: zone === "source" ? "Registered source metadata" : zone === "bronze" ? "Direct source-to-Bronze ingestion" : zone === "silver" ? "Applied Logical target" : "Applied Dimensional target",
        object_description: `${titleCase(zone)} metadata for ${item.name}`,
        batch_attribute_name: item.batchAttribute || "—",
        object_type_code: "table",
        zone_code: zone,
        is_locked: index === 1,
        is_active: rows.length < 4 || index !== rows.length - 1,
      }));
    }
    if (dataset.endsWith("_attribute")) {
      const objects = metadataObjectRows.filter((item) => item.zone.toLowerCase() === zone);
      const names = ["record_id", "record_name", "status_code", "effective_date", "source_system_code", "created_at"];
      return names.map((name, index) => {
        const item = objects[index % objects.length];
        return {
          tenant_code: item.tenant, system_code: item.system, connection_code: `${item.system.toLowerCase()}_prod`, object_schema: `${zone}_${item.system.toLowerCase()}`, object_name: item.name,
          attribute_name: name, fc_attribute_name: zone === "source" ? name : "—", attribute_ordinal_position: index + 1, attribute_description: `${titleCase(name.replaceAll("_", " "))} attribute`,
          attribute_data_type: name.endsWith("_id") ? "bigint" : name.includes("date") || name.includes("_at") ? "timestamp" : "string", attribute_nullability: index > 1, attribute_custom_code: "—",
          is_surrogate_key: index === 0 && zone !== "source", is_natural_key: index === 0, is_meta_data: index > 3, is_masking_required: false, is_mapped: zone !== "source", is_purge: false, is_active: index !== names.length - 1,
        };
      });
    }
    const rowCount = dataset === "project" ? 1 : dataset === "zone" ? 4 : 3;
    return Array.from({ length: rowCount }, (_, index) => Object.fromEntries(metadataColumns[dataset].map((field) => [field, metadataFieldValue(field, dataset, index)])));
  }

  function metadataFieldValue(field, dataset, index) {
    const systems = ["CRM", "ERP", "COMMERCE", "GDS"];
    const systemNames = ["Customer Relationship Management", "Enterprise Resource Planning", "Digital Commerce", "Global Data Store"];
    const connections = ["crm_prod", "erp_prod", "commerce_prod", "gds_primary"];
    const tenantCodes = ["NWA", "GRDM", "RDS", "FDH"];
    const tenantNames = ["Northwind Analytics", "Global Reference Data", "Retail Data Services", "Finance Data Hub"];
    const zones = ["source", "bronze", "silver", "gold"];
    const objectNames = ["customer_raw", "invoice_raw", "order_raw", "product_raw"];
    const sourceObjects = ["customer_source", "invoice_source", "order_source", "product_source"];
    const attributes = ["customer_id", "invoice_id", "order_id", "product_id"];
    const referenceValues = {
      system_type_code: ["salesforce", "sap", "databricks", "gds"], system_type_name: ["Salesforce", "SAP", "Databricks", "GDS"],
      connection_type_code: ["jdbc", "cloud_storage", "api", "databricks_sql"], connection_type_name: ["JDBC", "Cloud storage", "API", "Databricks SQL"],
      object_type_code: ["table", "view", "file", "stream"], object_type_name: ["Table", "View", "File", "Stream"],
      zone_code: zones, zone_name: ["Source", "Bronze", "Silver", "Gold"],
      chunk_type_name: ["batch", "date_range", "full", "full"], file_type_name: ["parquet", "csv", "json", "parquet"],
      data_operation_name: ["append", "merge", "overwrite", "delete"], process_type_name: ["sql", "notebook", "procedure", "sql"],
    };
    if (referenceValues[field]) return referenceValues[field][index % referenceValues[field].length];
    const fixed = {
      project_code: "GDS", project_name: "GDS Workbench", project_description: "Governed data engineering workbench",
      tenant_catalog: `${tenantCodes[index]}_catalog`.toLowerCase(), gds_admin_catalog: "gds_admin", tenant_visibility: index === 1 ? "global" : "private",
      scope_tenant_code: "NWA", connection_tenant_code: "NWA", connection_system_code: systems[index],
      foreign_catalog: index === 2 ? "commerce_external" : "—", has_foreign_catalog: index === 2, is_global_data_store: index === 3,
      object_schema: `bronze_${systems[index].toLowerCase()}`, copy_group_name: `${systems[index].toLowerCase()}_incremental`, member_group_name: index === 2 ? "—" : `${systems[index].toLowerCase()}_members`,
      member_group_initial_load_date: `2026-08-${String(10 + index).padStart(2, "0")}`, copy_group_control_initial_load_date: `2026-08-${String(10 + index).padStart(2, "0")}`,
      copy_group_control_last_run_time: `2026-08-23 10:${String(40 + index).padStart(2, "0")}:00`, copy_group_control_last_run_value: ["10428", "8841", "12932"][index],
      is_member_group_required: index !== 2, copy_source_record_limit: index === 1 ? "—" : "1000000", copy_source_record_limit_attribute: index === 1 ? "—" : "batch_id",
      chunk_type_name: index === 1 ? "date_range" : "batch", copy_source_initial_sql_script: `SELECT * FROM ${sourceObjects[index]}`, copy_source_incremental_sql_script: `SELECT * FROM ${sourceObjects[index]} WHERE batch_id = :batch_id`,
      copy_source_file_name: "—", copy_source_file_pattern: "—", copy_source_file_delimiter: "—", source_file_type_name: "parquet", copy_source_order: (index + 1) * 10,
      source_data_operation_name: "append", target_data_operation_name: index === 1 ? "merge" : "append", process_group_name: `${systems[index].toLowerCase()}_bronze_load`, process_group_description: `${systemNames[index]} Bronze processing`,
      process_execution_order: (index + 1) * 10, process_location: `/Workspace/gds/${systems[index].toLowerCase()}`, process_executable: `${systems[index].toLowerCase()}_bronze.sql`,
      object_tenant_code: "NWA", object_system_code: systems[index], object_connection_code: connections[index], object_name: objectNames[index],
    };
    if (Object.hasOwn(fixed, field)) return fixed[field];
    if (field === "tenant_code") return dataset === "tenant" ? tenantCodes[index] : "NWA";
    if (field === "tenant_name") return tenantNames[index];
    if (field === "tenant_description") return `${tenantNames[index]} Tenant`;
    if (field === "system_code") return systems[index];
    if (field === "system_name") return systemNames[index];
    if (field === "system_description") return `${systemNames[index]} metadata system`;
    if (field === "connection_code") return connections[index];
    if (field === "connection_name") return `${systemNames[index]} production`;
    if (field === "gds_connection_tenant_code") return "NWA";
    if (field === "gds_connection_system_code") return "GDS";
    if (field === "gds_connection_code") return "gds_primary";
    if (field.startsWith("source_")) {
      const suffix = field.slice(7);
      return { tenant_code: ["GRDM", "DDS", "GDS"][index], system_code: systems[index], connection_code: connections[index], object_schema: `source_${systems[index].toLowerCase()}`, object_name: sourceObjects[index], attribute_name: attributes[index] }[suffix] || "—";
    }
    if (field.startsWith("target_")) {
      const suffix = field.slice(7);
      return { tenant_code: "NWA", system_code: "GDS", connection_code: "gds_primary", object_schema: "bronze_nwa", object_name: objectNames[index], attribute_name: attributes[index] }[suffix] || "—";
    }
    if (field.endsWith("_description")) return `${titleCase(dataset.replaceAll("_", " "))} example ${index + 1}`;
    if (field === "is_active") return index !== 2;
    return "—";
  }

  function modelContractRows(dataset) {
    if (dataset === "model_scope") {
      return objectRows.map((item, index) => ({ __id: item.id, tenant_code: item.tenant, system_code: item.system, connection_code: `${item.system.toLowerCase()}_prod`, object_schema: `bronze_${item.system.toLowerCase()}`, object_name: item.name, model_scope_is_locked: index < 2, is_active: true }));
    }
    if (dataset === "profiling_profile") {
      return objectRows.map((item, index) => {
        const rowCount = Number(String(item.rowCount).replace(/[MK]/, "")) || (index + 1) * 1000;
        const scale = String(item.rowCount).includes("M") ? 1000000 : String(item.rowCount).includes("K") ? 1000 : 1;
        const total = Math.round(rowCount * scale);
        const nullCount = item.nullRate === "—" ? 0 : Math.round(total * Number(item.nullRate.replace("%", "")) / 100);
        const nonNull = Math.max(0, total - nullCount);
        const distinct = Math.max(1, Math.round(nonNull * (item.uniqueRate === "—" ? .5 : Number(item.uniqueRate.replace("%", "")) / 100)));
        return { tenant_code: item.tenant, system_code: item.system, connection_code: `${item.system.toLowerCase()}_prod`, object_schema: `bronze_${item.system.toLowerCase()}`, object_name: item.name, attribute_name: item.name.replace(/_raw$/, "_id"), row_count: total, non_null_count: nonNull, null_count: nullCount, blank_count: 0, distinct_count: distinct, min_data_length: 1, max_data_length: 36, avg_data_length: "12.400000", percent_populated: item.nullRate === "—" ? "—" : `${(100 - Number(item.nullRate.replace("%", ""))).toFixed(1)}%`, percent_duplicates: item.uniqueRate === "—" ? "—" : `${(100 - Number(item.uniqueRate.replace("%", ""))).toFixed(1)}%`, percent_null: item.nullRate, percent_blank: "0.0%", percent_distinct: item.uniqueRate };
      });
    }
    if (dataset === "analysis_result") {
      const rows = findings.map((item, index) => ({ from_tenant_code: index < 7 ? "GRDM" : "DDS", from_system_code: index < 7 ? "CRM" : "ERP", from_connection_code: index < 7 ? "crm_prod" : "erp_prod", from_object_schema: index < 7 ? "bronze_crm" : "bronze_erp", from_object_name: item.fromObject, from_attribute_name: item.fromAttribute, to_tenant_code: index % 3 === 0 ? "GDS" : "DDS", to_system_code: index % 3 === 0 ? "COMMERCE" : "ERP", to_connection_code: index % 3 === 0 ? "commerce_prod" : "erp_prod", to_object_schema: index % 3 === 0 ? "bronze_commerce" : "bronze_erp", to_object_name: item.toObject, to_attribute_name: item.toAttribute, relationship_kind: item.type.toLowerCase().replaceAll(" / ", "_"), relationship_confidence: item.confidence.toLowerCase(), relationship_basis: "Attribute-name and profiling evidence", validation_policy_version: "1.0.0", validation_result: item.validation === "Pending" ? "inconclusive" : item.validation.toLowerCase(), validation_source_non_null_count: 124000, validation_source_distinct_count: 82000, validation_target_non_null_count: 91000, validation_target_distinct_count: 81000, validation_source_missing_target_count: item.validation === "Supported" ? 0 : 42, validation_unused_target_count: 103, validation_duplicate_target_key_count: item.validation === "Unsupported" ? 27 : 0, analysis_result_status: item.active ? item.validation === "Pending" ? "needs_review" : "active" : "inactive", analysis_result_is_locked: item.locked, __object_name: [item.fromObject, item.toObject], __findingId: item.id }));
      if (state.analysisView === "locked") return rows.filter((row) => row.analysis_result_is_locked);
      if (state.analysisView === "review") return rows.filter((row) => row.analysis_result_status === "needs_review" || row.validation_result === "inconclusive");
      return rows.filter((row) => state.showInactive || row.analysis_result_status !== "inactive");
    }
    return modelContracts[dataset]?.rows || [];
  }

  function contractFilterControl(field, rows) {
    const values = [...new Set(rows.flatMap((row) => contractFilterTokens(row[field], field)))];
    const label = field === "__object_name" ? "Object name (from or to)" : field === "__model_name" ? "Model" : field === "submodels" ? "Submodel" : field.replaceAll("_", " ");
    return `<label class="metadata-filter"><span>${label}</span><select data-contract-filter="${field}"><option value="all">All</option>${values.map((value) => `<option value="${value}">${metadataDisplayValue(value)}</option>`).join("")}</select></label>`;
  }

  function contractFilterTokens(value, field) {
    if (value === null || value === undefined || value === "—") return [];
    if (field === "submodels" && Array.isArray(value)) return value.map((item) => item.submodel_name);
    if (Array.isArray(value)) return value.map(String);
    return [String(value)];
  }

  function contractLedger(dataset, options = {}) {
    const contract = modelContracts[dataset];
    const rows = modelContractRows(dataset);
    const displayColumns = contract.columns.filter((field) => !(options.hiddenColumns || []).includes(field));
    const canEdit = state.lockState === "mine";
    const selected = [...state.selectedContractRows].filter((key) => key.startsWith(`${dataset}:`)).length;
    const filters = contract.filters.map((field) => contractFilterControl(field, rows)).join("");
    const addButton = options.showAdd === false ? "" : `<button class="button button-primary" data-action="contract-add-row" ${canEdit ? "" : "disabled"} title="${canEdit ? `Add ${contract.label} row` : "Acquire the Tenant Lock to add rows"}">+ Add Row</button>`;
    const customActions = options.toolbarActions ? options.toolbarActions(canEdit, selected) : "";
    const selectable = options.selectable !== false;
    const bulkBar = selectable ? `<div class="bulk-bar contract-bulk-bar"><div>${selected ? `<strong>${selected} selected</strong>` : "Select rows for a governed action"}</div>${options.bulkMode === "scope" ? `<button class="button button-small" data-action="remove-scope" ${canEdit && selected ? "" : "disabled"}>Remove selected</button>` : options.bulkMode === "profile" ? `<button class="button button-small" data-panel="profiling-run" ${selected ? "" : "disabled"}>Profile selected</button>` : `<button class="button button-small" data-contract-lock="true" ${canEdit && selected ? "" : "disabled"}>Lock selected</button><button class="button button-small" data-contract-lock="false" ${canEdit && selected ? "" : "disabled"}>Unlock selected</button><button class="button button-small" data-action="contract-inactive" ${canEdit && selected ? "" : "disabled"}>Make inactive</button>`}</div>` : "";
    const width = Math.max(900, displayColumns.length * 148 + (selectable ? 38 : 0) + (options.showActions === false ? 0 : 150));
    const activeDetail = state.activeContractRow && state.activeContractRow.dataset === dataset ? rows[state.activeContractRow.index] : null;
    const inspector = !isDedicatedDetailDataset(dataset) && state.contractDetailOpen && activeDetail ? contractInspector(dataset, contract.label, activeDetail, contract.columns) : "";
    return `<div class="contract-toolbar"><div class="metadata-filter-set">${filters}</div><div class="contract-toolbar-actions">${customActions}${addButton}</div></div>${bulkBar}<div class="contract-layout ${inspector ? "has-inspector" : ""} ${dataset.startsWith("mapping_") ? "mapping-contract-layout" : ""}"><section class="data-region"><div class="table-scroll contract-ledger-scroll"><table id="contract-table" class="data-table metadata-contract-table contract-table" style="min-width:${width}px"><thead><tr>${selectable ? '<th class="check"><input type="checkbox" data-select-all-contract="' + dataset + '" aria-label="Select all rows"></th>' : ""}${displayColumns.map((field) => `<th title="${field}">${field}</th>`).join("")}${options.showActions === false ? "" : '<th class="metadata-row-action-heading">Actions</th>'}</tr></thead><tbody>${rows.map((row, index) => contractRowMarkup(dataset, row, index, displayColumns, contract.filters, { selectable, canEdit, showEdit: options.showEdit !== false, showActions: options.showActions !== false })).join("")}</tbody></table></div></section>${inspector}</div>`;
  }

  function contractRowMarkup(dataset, row, index, columns, filters, options) {
    const rowKey = `${dataset}:${index}`;
    const filterAttributes = filters.map((field) => `data-contract-${field}="${contractFilterTokens(row[field], field).join("|")}"`).join(" ");
    const selected = state.selectedContractRows.has(rowKey);
    const cells = columns.map((field, cellIndex) => `<td class="${metadataCellClass(field)}">${contractCellMarkup(row[field], field, cellIndex === 0)}</td>`).join("");
    const actions = options.showActions ? `<td class="metadata-row-actions"><div><button class="text-action" data-show-contract-detail="${dataset}:${index}">Show details</button>${options.showEdit ? `<button class="button button-small" data-edit-contract-row="${dataset}:${index}" ${options.canEdit ? "" : "disabled"} title="${options.canEdit ? "Edit this row" : "Acquire the Tenant Lock to edit"}">Edit</button>` : ""}</div></td>` : "";
    return `<tr class="${selected ? "is-active" : ""}" data-contract-row-key="${rowKey}" ${filterAttributes}>${options.selectable ? `<td class="check"><input type="checkbox" data-select-contract="${rowKey}" ${selected ? "checked" : ""} aria-label="Select ${dataset} row ${index + 1}"></td>` : ""}${cells}${actions}</tr>`;
  }

  function contractCellMarkup(value, field, isPrimary) {
    if (Array.isArray(value)) return `<span class="structured-summary">${value.length} ${field === "submodels" ? "submodel" : field === "supports" ? "support" : "source"}${value.length === 1 ? "" : "s"}</span>`;
    if (value && typeof value === "object") return '<span class="structured-summary">Structured document</span>';
    if (typeof value === "boolean") return `<em class="status ${value ? "complete" : "neutral"}">${value ? "Yes" : "No"}</em>`;
    if (field.endsWith("_status") || field === "validation_result") return `<em class="status ${contractStatusClass(String(value))}">${metadataDisplayValue(value)}</em>`;
    if (field.endsWith("_confidence")) return `<em class="confidence ${String(value)}">${metadataDisplayValue(value)}</em>`;
    if (value === null || value === undefined || value === "—") return '<span class="metadata-empty">—</span>';
    return isPrimary ? `<strong>${value}</strong>` : String(value);
  }

  function contractStatusClass(value) {
    if (["active", "supported", "completed"].includes(value)) return "complete";
    if (["needs_review", "inconclusive", "pending", "completed with repair"].includes(value)) return "warning";
    if (["inactive", "unsupported", "failed"].includes(value)) return "danger";
    return "neutral";
  }

  function contractInspector(dataset, label, row, columns) {
    if (dataset === "model_scope" && row.__id) return scopeInspector(findObject(row.__id)).replace("data-close-scope-detail", "data-close-contract-detail");
    const structured = columns.filter((field) => Array.isArray(row[field]) || (row[field] && typeof row[field] === "object"));
    const scalar = columns.filter((field) => !structured.includes(field));
    const mappingClass = dataset.startsWith("mapping_") ? " mapping-review-inspector" : "";
    return `<aside class="contract-inspector${mappingClass}"><header><div><small>${dataset.startsWith("mapping_") ? "MAPPING REVIEW" : "ROW DETAILS"}</small><h2>${escapeHtml(displayRecordTitle(row, label, dataset))}</h2></div><button class="panel-close" data-close-contract-detail aria-label="Close">×</button></header><dl>${scalar.map((field) => `<div><dt>${field}</dt><dd>${contractCellMarkup(row[field], field, false)}</dd></div>`).join("")}</dl>${structured.map((field) => structuredValueMarkup(row[field], field)).join("")}</aside>`;
  }

  function isDedicatedDetailDataset(dataset) {
    return ["conceptual_", "logical_", "dimensional_", "mapping_"].some((prefix) => dataset.startsWith(prefix));
  }

  function contractDetailPage() {
    const active = state.activeContractRow;
    const contract = active ? modelContracts[active.dataset] : null;
    const rows = contract ? modelContractRows(active.dataset) : [];
    const row = active ? rows[active.index] : null;
    if (!contract || !row || !isDedicatedDetailDataset(active.dataset)) {
      return shell(`<section class="record-detail-empty"><h1>Record not available</h1><p>The requested detail record is not available in this prototype.</p><button class="button button-primary" data-record-back>Back to records</button></section>`, "models", true);
    }
    const columns = contract.columns;
    const structured = columns.filter((field) => Array.isArray(row[field]) || (row[field] && typeof row[field] === "object"));
    const scalar = columns.filter((field) => !structured.includes(field));
    const governance = scalar.filter((field) => field.endsWith("_status") || field.endsWith("_confidence") || field.endsWith("_is_locked") || field === "is_active");
    const narrative = scalar.filter((field) => !governance.includes(field) && ["definition", "description", "basis", "grain", "instructions", "reason"].some((token) => field.includes(token)));
    const identity = scalar.filter((field) => !governance.includes(field) && !narrative.includes(field));
    const layer = active.dataset.startsWith("mapping_") ? "Mapping" : titleCase(active.dataset.split("_")[0]);
    const title = displayRecordTitle(row, contract.label, active.dataset);
    const recordNumber = active.index + 1;
    const previousDisabled = active.index === 0 ? "disabled" : "";
    const nextDisabled = active.index === rows.length - 1 ? "disabled" : "";
    return shell(`<div class="record-detail-page"><header class="record-detail-commandbar"><button class="text-action record-back" data-record-back>← Back to ${contract.label}</button><div class="record-breadcrumb"><span>Customer 360</span><i>›</i><span>${layer}</span><i>›</i><strong>${contract.label}</strong></div><div class="record-step-actions"><button class="button button-small" data-detail-step="-1" ${previousDisabled}>Previous</button><span>${recordNumber} of ${rows.length}</span><button class="button button-small" data-detail-step="1" ${nextDisabled}>Next</button></div></header><section class="record-detail-hero"><div><small>${escapeHtml(layer.toUpperCase())} · ${escapeHtml(contract.label.toUpperCase())}</small><h1>${escapeHtml(title)}</h1><p>Normalized record details for review.</p></div><div class="record-hero-status">${governance.slice(0, 3).map((field) => `<div><span>${escapeHtml(field.replaceAll("_", " "))}</span>${contractCellMarkup(row[field], field, false)}</div>`).join("")}</div></section><div class="record-detail-body"><main>${narrative.length ? recordFieldSection("Definition and rationale", narrative, row, "narrative") : ""}${identity.length ? recordFieldSection("Normalized fields", identity, row, "grid") : ""}</main><aside>${recordFieldSection("Governance", governance, row, "governance")}</aside></div>${structured.length ? `<section class="record-structured-area"><header><small>STRUCTURED RECORDS</small><h2>Supporting evidence and authored documents</h2><p>Every normalized nested field is shown without truncation.</p></header>${structured.map((field) => structuredValueMarkup(row[field], field)).join("")}</section>` : ""}</div>`, active.dataset.startsWith("mapping_") ? "mapping" : "models", true);
  }

  function recordFieldSection(title, fields, row, variant) {
    if (!fields.length) return "";
    return `<section class="record-field-section ${variant}"><header><h2>${title}</h2><span>${fields.length} fields</span></header><div>${fields.map((field) => `<article><span>${escapeHtml(field.replaceAll("_", " "))}</span><div>${contractCellMarkup(row[field], field, false)}</div></article>`).join("")}</div></section>`;
  }

  function displayRecordTitle(row, fallback, dataset = "") {
    if (dataset === "mapping_dependency") return `${row.source_system_code} · ${metadataDisplayValue(row.modeled_entity_type)}`;
    if (dataset === "mapping_object") return `${row.object_schema}.${row.object_name}`;
    if (dataset === "mapping_attribute") return `${row.object_schema}.${row.object_name}.${row.attribute_name}`;
    const field = Object.keys(row).find((key) => key.endsWith("_name") && !key.startsWith("from_") && !key.startsWith("to_"));
    return field ? row[field] : fallback;
  }

  function structuredValueMarkup(value, label) {
    const records = Array.isArray(value) ? value : [value];
    return `<section class="structured-block"><header><strong>${escapeHtml(label.replaceAll("_", " "))}</strong><span>${records.length} ${records.length === 1 ? "record" : "records"}</span></header><div class="structured-record-list">${records.map((record, index) => `<article class="structured-record"><small>RECORD ${index + 1}</small>${structuredObjectMarkup(record)}</article>`).join("")}</div></section>`;
  }

  function structuredObjectMarkup(record) {
    if (!record || typeof record !== "object") return `<p>${escapeHtml(metadataDisplayValue(record))}</p>`;
    if (Array.isArray(record)) return `<div class="structured-nested-list">${record.map((item, index) => `<section><small>ITEM ${index + 1}</small>${structuredObjectMarkup(item)}</section>`).join("")}</div>`;
    return `<div class="structured-object">${Object.entries(record).map(([key, value]) => `<div class="structured-field"><span>${escapeHtml(key.replaceAll("_", " "))}</span><div>${value && typeof value === "object" ? structuredObjectMarkup(value) : escapeHtml(metadataDisplayValue(value))}</div></div>`).join("")}</div>`;
  }

  function escapeHtml(value) {
    return String(value ?? "—").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
  }

  function modelsPage() {
    const canEdit = state.lockState === "mine";
    const actions = (openAction) => `<div class="model-list-actions"><button class="button button-small" ${openAction}><span>Open</span></button><button class="button button-small" data-action="edit-model" ${canEdit ? "" : "disabled"}>Edit</button></div>`;
    return shell(`<header class="models-commandbar"><span class="permission ${canEdit ? "editable" : ""}">${canEdit ? "Tenant Lock held · model editing available" : "Read only · Tenant Lock required"}</span><nav class="models-mode-tabs"><button class="is-active">Active <em>3</em></button><button>Archived <em>1</em></button></nav><div class="models-command-actions"><button class="button button-primary" data-action="new-model" ${canEdit ? "" : "disabled"}>New Model</button></div></header><section class="models-list" id="models-table"><header><span>Model</span><span>Owner Tenant</span><span>Revision</span><span>Active scope</span><span>Current attention</span><span>Updated</span><span>Actions</span></header><article><div><strong>Customer 360</strong><small>Cross-system customer domain</small></div><span>Northwind Analytics</span><span>r18</span><span>25 Bronze Objects</span><em class="status warning">15 Analysis findings</em><span>12m ago</span>${actions('data-nav="model-home"')}</article><article><div><strong>Finance Core</strong><small>Billing and settlement</small></div><span>Northwind Analytics</span><span>r11</span><span>42 Bronze Objects</span><em class="status complete">Logical reviewed</em><span>Yesterday</span>${actions('data-action="open-example-model"')}</article><article><div><strong>Commerce Fulfillment</strong><small>Order to shipment</small></div><span>Northwind Analytics</span><span>r7</span><span>31 Bronze Objects</span><em class="status neutral">Scope ready</em><span>Aug 19</span>${actions('data-action="open-example-model"')}</article></section>`, "models", false);
  }

  function modelShell(body, activeStage) {
    const stages = [["model-home", "Overview", "Current work"], ["scope", "Scope", `${objectRows.length} Objects`], ["profiling", "Profiling", "18 profiled"], ["analysis", "Analysis", "15 to review"], ["assertions", "Assertions", "2 records"], ["conceptual", "Conceptual", "3 Objects"], ["logical", "Logical", "3 Entities"], ["dimensional", "Dimensional", "Silver eligible"]];
    return shell(`<div class="model-layout"><aside class="model-rail"><div class="model-rail-title"><small>MODEL JOURNEY</small><strong>Customer 360</strong><span>Revision 18</span></div><nav>${stages.map(([key, label, summary], index) => { const navigable = allowedScreens.has(key); const done = ["scope", "profiling"].includes(key); return `<button class="model-step ${activeStage === key ? "is-active" : ""} ${done ? "is-complete" : ""}" ${navigable ? `data-nav="${key}"` : `data-action="${key}"`}><i>${done ? "✓" : index}</i><span><strong>${label}</strong><small>${summary}</small></span></button>`; }).join("")}</nav><div class="model-rail-note"><strong>Quality, never blocking</strong><span>Earlier evidence improves later work. Every workflow remains user-driven.</span></div></aside><section class="model-workspace">${body}</section></div>`, "models", true);
  }

  function modelHome() {
    const tabs = '<button class="is-active">Workflow ledger</button><button data-action="model-activity">Activity</button>';
    const rows = [["Scope", `${objectRows.length} Objects`, "Ready", "Review scope", "scope"], ["Profiling", "18 profiled", "Usable", "Profile remaining", "profiling"], ["Analysis", "22 / 37 reviewed", "Needs review", "Review 15 findings", "analysis"], ["Assertions", "2 records", "Available", "Review assertions", "assertions"], ["Conceptual", "3 Objects", "Needs review", "Review Conceptual", "conceptual"], ["Logical", "3 Entities", "Available", "Review Logical", "logical"], ["Dimensional", "3 Entities", "Waiting", "Review eligibility", "dimensional"]];
    return modelShell(`${workflowBar(tabs, `<button class="button" data-action="model-settings" ${state.lockState === "mine" ? "" : "disabled"}>Model settings</button>`)}<section class="next-action-strip"><div><small>RECOMMENDED NEXT</small><strong>Review 15 Analysis findings</strong><span>The latest inference completed. Lock accepted findings before another inference run.</span></div><div class="next-action-evidence"><span><strong>25</strong> in scope</span><span><strong>18</strong> profiled</span><span><strong>22</strong> reviewed</span></div><button class="button button-primary" data-nav="analysis">Continue review →</button></section><section class="ledger-home"><header><span>Workflow</span><span>Coverage</span><span>State</span><span>Next action</span></header>${rows.map((row) => `<article><strong>${row[0]}</strong><span>${row[1]}</span><em class="status ${row[2] === "Ready" || row[2] === "Usable" ? "complete" : row[2] === "Needs review" ? "warning" : "neutral"}">${row[2]}</em><button class="text-action" data-nav="${row[4]}">${row[3]} →</button></article>`).join("")}</section>`, "model-home");
  }

  function scopePage() {
    const tabs = `<button class="is-active">Active scope <em>${objectRows.length}</em></button><button data-action="scope-history">Change history</button>`;
    const ledger = contractLedger("model_scope", { showAdd: false, showEdit: false, bulkMode: "scope", toolbarActions: (canEdit) => `<button class="button button-primary" data-action="open-add-scope" ${canEdit ? "" : "disabled"}>Add Objects</button>` });
    return modelShell(`${workflowBar(tabs)}${state.panel === "add-scope" ? addScopePanel() : ""}${ledger}`, "scope");
  }

  function addScopePanel() {
    const filter = (field, label) => {
      const values = [...new Set(candidateRows.map((row) => row[field]))].sort();
      return `<label class="metadata-filter"><span>${label}</span><select data-candidate-filter="${field}"><option value="all">All ${label}s</option>${values.map((value) => `<option value="${value}" ${state.candidateFilters[field] === value ? "selected" : ""}>${value}</option>`).join("")}</select></label>`;
    };
    const visibleCandidates = candidateRows.filter((item) => (!state.candidateFilters.search || item.name.toLowerCase().includes(state.candidateFilters.search.toLowerCase())) && ["tenant", "system", "zone"].every((field) => state.candidateFilters[field] === "all" || item[field] === state.candidateFilters[field]));
    const allVisibleSelected = visibleCandidates.length > 0 && visibleCandidates.every((item) => state.selectedCandidates.has(item.id));
    return `<section class="inline-drawer add-scope-drawer"><header><div><small>ADD TO MODEL SCOPE</small><h2>Choose registered metadata Objects</h2><p>Filter by source Tenant, System, and Zone. No Zone is selected automatically.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="candidate-filter-bar">${filter("tenant", "Tenant")}${filter("system", "System")}${filter("zone", "Zone")}<label class="search"><span>⌕</span><input data-candidate-search value="${state.candidateFilters.search}" placeholder="Search Objects"></label></div><div class="candidate-grid"><table id="candidate-table" class="data-table"><thead><tr><th class="check"><input type="checkbox" data-select-all-candidates aria-label="Select all visible Objects" ${allVisibleSelected ? "checked" : ""}></th><th>Object</th><th>System</th><th>Source Tenant</th><th>Zone</th><th>Attributes</th><th>Batch attribute</th></tr></thead><tbody>${candidateRows.map((item) => `<tr data-candidate-id="${item.id}" data-search="${item.name.toLowerCase()}" data-candidate-tenant="${item.tenant}" data-candidate-system="${item.system}" data-candidate-zone="${item.zone}" class="${state.selectedCandidates.has(item.id) ? "is-active" : ""}"><td class="check"><input type="checkbox" data-select-candidate="${item.id}" ${state.selectedCandidates.has(item.id) ? "checked" : ""}></td><td><strong>${item.name}</strong><span>Table</span></td><td>${item.system}</td><td>${item.tenant}</td><td><em class="zone">${item.zone}</em></td><td>${item.attributeCount}</td><td>${item.batchAttribute || "—"}</td></tr>`).join("")}</tbody></table></div><footer><span>${state.selectedCandidates.size ? `<strong>${state.selectedCandidates.size}</strong> selected` : "Select Objects to add"}</span><button class="button button-primary" data-action="confirm-add-scope" ${state.selectedCandidates.size ? "" : "disabled"}>Add to active scope</button></footer></section>`;
  }

  function profilingPage() {
    const resultTabs = `<button class="${state.profilingView === "results" ? "is-active" : ""}" data-profile-view="results">Results <em>${objectRows.length}</em></button><button class="${state.profilingView === "runs" ? "is-active" : ""}" data-profile-view="runs">Runs <em>${profileRuns.length}</em></button>`;
    const content = state.profilingView === "runs" ? profilingRunsView() : profilingResultsView();
    const canEdit = state.lockState === "mine";
    return modelShell(`${workflowBar(resultTabs, `<span class="permission ${canEdit ? "editable" : ""}">${canEdit ? "Tenant Lock held" : "Tenant Lock required"}</span><button class="button button-primary" data-panel="profiling-run" ${canEdit ? "" : "disabled"}>Run profiling</button>`)}${state.panel === "profiling-run" ? profilingRunPanel() : ""}${content}`, "profiling");
  }

  function profilingResultsView() {
    return contractLedger("profiling_profile", { showAdd: false, showEdit: false, bulkMode: "profile" });
  }

  function profilingRunsView() {
    const active = profileRuns.find((item) => item.id === state.activeRunId) || profileRuns[0];
    return `<div class="run-layout ${state.runDetailOpen ? "has-inspector" : ""}"><section><div class="run-table-toolbar"><label class="metadata-filter"><span>Status</span><select data-run-filter="status"><option value="all">All</option><option>Completed</option><option>Completed with warnings</option><option>Failed</option></select></label><label class="metadata-filter"><span>System</span><select data-run-filter="system"><option value="all">All</option><option>CRM</option><option>ERP</option><option>Commerce</option></select></label></div><div class="table-scroll"><table id="profile-runs-table" class="data-table run-table"><thead><tr><th>Run</th><th>Status</th><th>Started</th><th>System</th><th>Objects</th><th>Batch ID</th><th>Actor</th><th>Duration</th><th></th></tr></thead><tbody>${profileRuns.map((item) => runRowMarkup(item, "profile", active.id)).join("")}</tbody></table></div></section>${state.runDetailOpen ? runInspector(active, "profiling") : ""}</div>`;
  }

  function analysisPage() {
    const tabs = `<button class="${state.analysisView === "all" ? "is-active" : ""}" data-analysis-view="all">All findings <em>37</em></button><button class="${state.analysisView === "review" ? "is-active" : ""}" data-analysis-view="review">Needs review <em>15</em></button><button class="${state.analysisView === "locked" ? "is-active" : ""}" data-analysis-view="locked">Locked <em>2</em></button><button class="${state.analysisView === "runs" ? "is-active" : ""}" data-analysis-view="runs">Runs <em>${analysisRuns.length}</em></button>`;
    const canEdit = state.lockState === "mine";
    const permission = `<span class="permission ${canEdit ? "editable" : ""}">${canEdit ? "Tenant Lock held" : "Tenant Lock required"}</span>`;
    const actions = `<button class="button" data-panel="analysis-inference" ${canEdit ? "" : "disabled"}>Run inference</button><button class="button button-primary" data-panel="analysis-validation" ${canEdit ? "" : "disabled"}>Validate pending</button>`;
    const content = state.analysisView === "runs" ? analysisRunsView() : analysisResultsView();
    return modelShell(`${workflowBar(tabs, actions, permission)}${["analysis-inference", "analysis-validation"].includes(state.panel) ? analysisRunPanel() : ""}${content}`, "analysis");
  }

  function analysisResultsView() {
    return `${contractLedger("analysis_result", { bulkMode: "lock" })}<label class="inactive-toggle-footer"><input type="checkbox" data-toggle-inactive ${state.showInactive ? "checked" : ""}> Show inactive Analysis records</label>`;
  }

  function analysisRunsView() {
    const active = analysisRuns.find((item) => item.id === state.activeRunId) || analysisRuns[0];
    return `<div class="run-layout ${state.runDetailOpen ? "has-inspector" : ""}"><section><div class="run-table-toolbar"><label class="metadata-filter"><span>Status</span><select data-run-filter="status"><option value="all">All</option><option>Completed</option><option>Completed with repair</option><option>Failed</option></select></label><label class="metadata-filter"><span>Scope</span><select data-run-filter="system"><option value="all">All</option><option>All systems</option><option>CRM</option><option>ERP</option></select></label></div><div class="table-scroll"><table id="analysis-runs-table" class="data-table run-table"><thead><tr><th>Run</th><th>Status</th><th>Started</th><th>Scope</th><th>Objects</th><th>Mode</th><th>Actor</th><th>Duration</th><th></th></tr></thead><tbody>${analysisRuns.map((item) => runRowMarkup(item, "analysis", active.id)).join("")}</tbody></table></div></section>${state.runDetailOpen ? runInspector(active, "analysis") : ""}</div>`;
  }

  function assertionsPage() {
    const datasets = [["modeling_assertion_document", "Documents"], ["modeling_assertion_record", "Records"]];
    const tabs = datasets.map(([dataset, label]) => `<button class="${state.assertionDataset === dataset ? "is-active" : ""}" data-model-dataset="${dataset}" data-model-stage="assertion">${label} <em>${modelContractRows(dataset).length}</em></button>`).join("");
    return modelShell(`${workflowBar(tabs)}${contractLedger(state.assertionDataset, { bulkMode: "lock" })}`, "assertions");
  }

  function authoringPage(stage) {
    const config = {
      conceptual: { property: "conceptualDataset", datasets: [["conceptual_object", "Objects"], ["conceptual_relationship", "Relationships"]] },
      logical: { property: "logicalDataset", datasets: [["logical_submodel", "Submodels"], ["logical_entity", "Entities"], ["logical_attribute", "Attributes"], ["logical_relationship", "Relationships"]] },
      dimensional: { property: "dimensionalDataset", datasets: [["dimensional_submodel", "Submodels"], ["dimensional_entity", "Entities"], ["dimensional_attribute", "Attributes"], ["dimensional_relationship", "Relationships"]] },
    }[stage];
    const activeDataset = state[config.property];
    const tabs = config.datasets.map(([dataset, label]) => `<button class="${activeDataset === dataset ? "is-active" : ""}" data-model-dataset="${dataset}" data-model-stage="${stage}">${label} <em>${modelContractRows(dataset).length}</em></button>`).join("") + `<button class="${activeDataset === "runs" ? "is-active" : ""}" data-model-dataset="runs" data-model-stage="${stage}">Runs <em>${authoringRuns.filter((item) => item.system.toLowerCase() === stage).length}</em></button>`;
    const canEdit = state.lockState === "mine";
    const permission = `<span class="permission ${canEdit ? "editable" : ""}">${canEdit ? "Tenant Lock held" : "Tenant Lock required"}</span>`;
    const actions = `<button class="button button-primary" data-panel="authoring-run" ${canEdit ? "" : "disabled"}>Run ${titleCase(stage)}</button>`;
    const content = activeDataset === "runs" ? authoringRunsView(stage) : contractLedger(activeDataset, { bulkMode: "lock" });
    return modelShell(`${workflowBar(tabs, actions, permission)}${state.panel === "authoring-run" ? authoringRunPanel(stage) : ""}${content}`, stage);
  }

  function authoringRunPanel(stage) {
    return `<section class="inline-drawer run-config"><header><div><small>NEW ${stage.toUpperCase()} RUN</small><h2>Generate a complete ${titleCase(stage)} candidate</h2><p>Mode and context handling are explicit. Nothing writes partially.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="common-fields authoring-run-fields"><label><span>Mode</span><select><option>One-shot</option><option>Tool-assisted</option><option>Detailed Coverage</option></select></label><label><span>Object scope</span><select><option>All active eligible Objects</option><option>Selected Objects</option></select></label><label><span>Registered model</span><select><option>Foundry · gpt-5</option><option>Foundry · gpt-5-mini</option></select></label><label><span>Reasoning effort</span><select><option>Medium</option><option>High</option><option>Low</option></select></label><label><span>Max turns</span><input type="number" value="12" min="1" max="50"></label><label><span>Validation retries</span><input type="number" value="2" min="0" max="5"></label></div><footer><span>Oversized one-shot context fails explicitly. There is no automatic fallback.</span><button class="button button-primary" data-start-run="${stage}">${state.running ? "Running…" : `Run ${titleCase(stage)}`}</button></footer></section>`;
  }

  function authoringRunsView(stage) {
    const rows = authoringRuns.filter((item) => item.system.toLowerCase() === stage);
    const active = rows.find((item) => item.id === state.activeRunId) || rows[0];
    return `<div class="run-layout ${state.runDetailOpen ? "has-inspector" : ""}"><section><div class="run-table-toolbar"><label class="metadata-filter"><span>Status</span><select data-run-filter="status"><option value="all">All</option><option>Completed</option><option>Completed with repair</option><option>Failed</option></select></label><label class="metadata-filter"><span>Mode</span><select data-run-filter="batch"><option value="all">All</option><option>One-shot</option><option>Tool-assisted</option><option>Detailed Coverage</option></select></label></div><div class="table-scroll"><table class="data-table run-table"><thead><tr><th>Run</th><th>Status</th><th>Started</th><th>Workflow</th><th>Objects</th><th>Mode</th><th>Actor</th><th>Duration</th><th></th></tr></thead><tbody>${rows.map((item) => runRowMarkup(item, "authoring", active?.id)).join("")}</tbody></table></div></section>${state.runDetailOpen && active ? runInspector(active, stage) : ""}</div>`;
  }

  function mappingPage() {
    return shell(`<header class="models-commandbar"><span></span><nav class="models-mode-tabs"><button class="is-active">Models with Mapping <em>3</em></button></nav><div></div></header><section class="models-list mapping-model-list"><header><span>Model</span><span>Revision</span><span>Logical targets</span><span>Gold targets</span><span>Current attention</span><span>Updated</span><span>Actions</span></header><article><div><strong>Customer 360</strong><small>Logical and Dimensional Mapping available</small></div><span>r18</span><span>6 Silver</span><span>4 Gold</span><em class="status warning">2 need review</em><span>18m ago</span><div class="model-list-actions"><button class="button button-small" data-nav="mapping-logical">Open</button></div></article><article><div><strong>Finance Core</strong><small>Logical Mapping available</small></div><span>r11</span><span>8 Silver</span><span>—</span><em class="status complete">Reviewed</em><span>Yesterday</span><div class="model-list-actions"><button class="button button-small" data-action="open-example-model">Open</button></div></article><article><div><strong>Commerce Fulfillment</strong><small>Awaiting registered Silver targets</small></div><span>r7</span><span>—</span><span>—</span><em class="status neutral">Not ready</em><span>Aug 19</span><div class="model-list-actions"><button class="button button-small" data-action="open-example-model">Open</button></div></article></section>`, "mapping", false);
  }

  function mappingWorkflowPage() {
    const activeDataset = state.mappingDataset;
    const counts = ["mapping_dependency", "mapping_object", "mapping_attribute"].map((dataset) => modelContractRows(dataset).length);
    const tabs = [["mapping_dependency", "Dependencies", counts[0]], ["mapping_object", "Object mappings", counts[1]], ["mapping_attribute", "Attribute mappings", counts[2]], ["runs", "Runs", mappingRuns.length]].map(([dataset, label, count]) => `<button class="${activeDataset === dataset ? "is-active" : ""}" data-mapping-dataset="${dataset}">${label} <em>${count}</em></button>`).join("");
    const canEdit = state.lockState === "mine";
    const leading = `<div class="mapping-workspace-leading"><button class="text-action" data-nav="mapping">← Back to Mapping</button><span class="permission ${canEdit ? "editable" : ""}">${canEdit ? "Tenant Lock held" : "Tenant Lock required"}</span></div>`;
    const actions = `<button class="button button-primary" data-panel="mapping-run" ${canEdit ? "" : "disabled"}>Run Mapping</button>`;
    const eligibility = `<div class="workflow-context-line"><strong>Applied Model → registered target</strong><span>Logical mappings use Silver targets. Dimensional mappings use Gold targets. Code generation reads the applied Mapping.</span></div>`;
    const hiddenColumns = activeDataset === "mapping_object" ? ["mapping_package_document", "object_mapping_transformation_document"] : activeDataset === "mapping_attribute" ? ["attribute_mapping_transformation_document"] : [];
    const content = activeDataset === "runs" ? mappingRunsView() : contractLedger(activeDataset, { bulkMode: "lock", hiddenColumns });
    return shell(`${workflowBar(tabs, actions, leading)}${eligibility}${state.panel === "mapping-run" ? mappingRunPanel() : ""}${content}`, "mapping", true);
  }

  function mappingRunPanel() {
    return `<section class="inline-drawer run-config"><header><div><small>NEW MAPPING RUN</small><h2>Build Mapping from the applied Model</h2><p>Entity type explicitly determines Silver or Gold target eligibility. Code generation remains separate.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="common-fields authoring-run-fields"><label><span>Model</span><select><option>Customer 360 · r18</option></select></label><label><span>Entity type</span><select><option>Logical Entity · Silver targets</option><option>Dimensional Entity · Gold targets</option></select></label><label><span>Mode</span><select><option>One-shot</option><option>Tool-assisted</option><option>Detailed Coverage</option></select></label><label><span>Target scope</span><select><option>All eligible target Objects</option><option>Selected target Objects</option></select></label><label><span>Registered model</span><select><option>Foundry · gpt-5</option><option>Foundry · gpt-5-mini</option></select></label><label><span>Reasoning effort</span><select><option>High</option><option>Medium</option><option>Low</option></select></label><label><span>Max turns</span><input type="number" value="12" min="1" max="50"></label><label><span>Validation retries</span><input type="number" value="2" min="0" max="5"></label><label><span>Object template</span><select><option>Free form (default)</option><option>Standard object mapping</option></select></label><label><span>Attribute template</span><select><option>Free form (default)</option><option>Standard attribute mapping</option></select></label></div><footer><span>Locked Mapping records remain unchanged. Agent output never deletes records.</span><button class="button button-primary" data-start-run="mapping">${state.running ? "Running…" : "Run Mapping"}</button></footer></section>`;
  }

  function mappingRunsView() {
    const rows = mappingRuns;
    const active = rows.find((item) => item.id === state.activeRunId) || rows[0];
    return `<div class="run-layout ${state.runDetailOpen ? "has-inspector" : ""}"><section><div class="run-table-toolbar"><label class="metadata-filter"><span>Status</span><select data-run-filter="status"><option value="all">All</option><option>Completed</option><option>Completed with repair</option><option>Failed</option></select></label><label class="metadata-filter"><span>Mode</span><select data-run-filter="batch"><option value="all">All</option><option>Tool-assisted</option><option>Detailed Coverage</option></select></label></div><div class="table-scroll"><table class="data-table run-table"><thead><tr><th>Run</th><th>Status</th><th>Started</th><th>Layer</th><th>Targets</th><th>Mode</th><th>Actor</th><th>Duration</th><th></th></tr></thead><tbody>${rows.map((item) => runRowMarkup(item, "mapping", active?.id)).join("")}</tbody></table></div></section>${state.runDetailOpen && active ? runInspector(active, "mapping") : ""}</div>`;
  }

  function codePage() {
    return shell(`<header class="models-commandbar"><span></span><nav class="models-mode-tabs"><button class="is-active">Models with applied Mapping <em>3</em></button></nav><div></div></header><section class="models-list code-model-list"><header><span>Model</span><span>Revision</span><span>Target Objects</span><span>Stored SQL</span><span>Current attention</span><span>Updated</span><span>Actions</span></header><article><div><strong>Customer 360</strong><small>Silver and Gold targets available</small></div><span>r18</span><span>5 targets</span><span>4 files</span><em class="status warning">1 not generated</em><span>12m ago</span><div class="model-list-actions"><button class="button button-small" data-nav="code-model">Open</button></div></article><article><div><strong>Finance Core</strong><small>Silver targets available</small></div><span>r11</span><span>8 targets</span><span>8 files</span><em class="status complete">Current</em><span>Yesterday</span><div class="model-list-actions"><button class="button button-small" data-action="open-example-model">Open</button></div></article><article><div><strong>Commerce Fulfillment</strong><small>Awaiting applied Mapping</small></div><span>r7</span><span>—</span><span>—</span><em class="status neutral">Not ready</em><span>Aug 19</span><div class="model-list-actions"><button class="button button-small" data-action="open-example-model">Open</button></div></article></section>`, "code", false);
  }

  function codeModelPage() {
    const generatedCount = codeTargets.filter((row) => row.generated_sql).length;
    const tabs = `<button class="${state.codeView === "generate" ? "is-active" : ""}" data-code-view="generate">Target Objects <em>${codeTargets.length}</em></button><button class="${state.codeView === "saved" ? "is-active" : ""}" data-code-view="saved">Stored SQL <em>${generatedCount}</em></button><button class="${state.codeView === "runs" ? "is-active" : ""}" data-code-view="runs">Runs <em>${codeRuns.length}</em></button>`;
    const content = state.codeView === "runs" ? codeRunsView() : state.codeView === "saved" ? codeSavedView() : codeGenerateView();
    return shell(`<header class="section-bar code-commandbar"><div class="mapping-workspace-leading"><button class="text-action" data-nav="code">← Back to Code generation</button><span class="code-boundary">Applied Mapping · SQL only</span></div><nav class="section-tabs">${tabs}</nav><div class="section-actions"><button class="button" data-action="refresh-results">Refresh</button></div></header>${state.panel === "code-run" ? codeRunPanel() : ""}${content}`, "code", true);
  }

  function codeGenerateView() {
    const selected = state.selectedCodeTargets.size;
    const selectedTarget = selected === 1 ? codeTargets.find((row) => state.selectedCodeTargets.has(row.id)) : null;
    const fields = ["target_object_schema", "target_system_code", "modeled_entity_type"];
    const filters = fields.map((field) => contractFilterControl(field, codeTargets)).join("").replaceAll("data-contract-filter", "data-code-filter");
    const columns = ["target_object_name", "target_object_schema", "target_system_code", "modeled_entity_name", "modeled_entity_type", "source_system_code", "mapping_status", "generated_state", "generated_at"];
    return `<div class="contract-toolbar code-target-toolbar"><div class="metadata-filter-set">${filters}</div><div class="contract-toolbar-actions"><button class="button" data-show-generated ${selectedTarget?.generated_sql ? "" : "disabled"}>Show generated code</button><button class="button" data-panel="code-run">Generate all</button><button class="button button-primary" data-panel="code-run" ${selected ? "" : "disabled"}>Generate selected${selected ? ` (${selected})` : ""}</button></div></div><div class="bulk-bar"><div>${selected ? `<strong>${selected} target Objects selected</strong>` : "Select target Objects from applied Mapping"}</div><span class="code-persisted-note">The target Object drives generation; its modeled Entity is supporting context.</span></div><div class="table-scroll code-target-scroll"><table id="code-target-table" class="data-table metadata-contract-table contract-table" style="min-width:1180px"><thead><tr><th class="check"><input type="checkbox" data-select-all-code aria-label="Select all code targets"></th>${columns.map((field) => `<th>${field}</th>`).join("")}</tr></thead><tbody>${codeTargets.map((row) => { const displayRow = { ...row, generated_state: row.generated_sql ? "stored" : "not_generated", generated_at: row.generated_at || "—" }; return `<tr ${fields.map((field) => `data-code-${field}="${row[field]}"`).join(" ")} class="${state.selectedCodeTargets.has(row.id) ? "is-active" : ""}"><td class="check"><input type="checkbox" data-select-code="${row.id}" ${state.selectedCodeTargets.has(row.id) ? "checked" : ""} aria-label="Select ${row.target_object_schema}.${row.target_object_name}"></td>${columns.map((field, index) => `<td>${field === "generated_state" ? `<em class="status ${row.generated_sql ? "complete" : "neutral"}">${row.generated_sql ? "Stored" : "Not generated"}</em>` : contractCellMarkup(displayRow[field], field, index === 0)}</td>`).join("")}</tr>`; }).join("")}</tbody></table></div>`;
  }

  function codeRunPanel() {
    const selected = state.selectedCodeTargets.size;
    return `<section class="inline-drawer run-config"><header><div><small>SQL GENERATION RUN</small><h2>${state.codeView === "saved" ? "Regenerate stored SQL from applied Mapping" : `Generate ${selected ? `${selected} selected SQL ${selected === 1 ? "file" : "files"}` : "all eligible SQL files"}`}</h2><p>Source is applied Mapping—not the Model. Successful output replaces the stored SQL for each target atomically.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="common-fields authoring-run-fields"><label><span>Model</span><select><option>Customer 360 · r18</option></select></label><label><span>Generation guide</span><select><option>Default Databricks SQL</option><option>Northwind SQL standard</option></select></label><label><span>Registered model</span><select><option>Foundry · gpt-5</option><option>Foundry · gpt-5-mini</option></select></label><label><span>Reasoning effort</span><select><option>High</option><option>Medium</option></select></label><label><span>Max turns</span><input type="number" value="12" min="1" max="50"></label><label><span>Validation retries</span><input type="number" value="2" min="0" max="5"></label></div><footer><span>Stored SQL remains unchanged if validation fails.</span><button class="button button-primary" data-start-run="code">${state.running ? "Generating…" : state.codeView === "saved" ? "Regenerate SQL" : "Generate SQL"}</button></footer></section>`;
  }

  function codeSavedView() {
    const generated = codeTargets.filter((row) => row.generated_sql);
    const active = generated.find((row) => row.id === state.activeCodeTarget) || generated[0];
    if (!active) return `<section class="empty-code-state"><h2>No generated SQL</h2><p>Select eligible Mapping targets and generate SQL first.</p><button class="button button-primary" data-code-view="generate">Generate SQL</button></section>`;
    return `<section class="saved-code-workspace"><header><div><small>STORED SQL</small><h2>${active.target_object_schema}.${active.target_object_name}</h2><span>${active.model_name} · ${metadataDisplayValue(active.modeled_entity_type)} · ${active.generated_run_id} · ${active.generated_at}</span></div><div><button class="button" data-action="download-sql">Download .sql</button><button class="button button-primary" data-panel="code-run">Regenerate from Mapping</button></div></header><div class="saved-code-body"><nav>${generated.map((row) => `<button class="${row.id === active.id ? "is-active" : ""}" data-code-target="${row.id}"><strong>${row.target_object_name}.sql</strong><span>${row.target_object_schema} · ${row.generated_at}</span></button>`).join("")}</nav><article><div class="code-source-strip"><span>Source</span><strong>Applied Mapping</strong><span>Guide</span><strong>${active.generation_guide}</strong></div><pre><code>${escapeHtml(active.generated_sql)}</code></pre></article></div></section>`;
  }

  function codeRunsView() {
    const active = codeRuns.find((item) => item.id === state.activeRunId) || codeRuns[0];
    return `<div class="run-layout ${state.runDetailOpen ? "has-inspector" : ""}"><section><div class="run-table-toolbar"><label class="metadata-filter"><span>Status</span><select data-run-filter="status"><option value="all">All</option><option>Completed</option><option>Failed</option></select></label><label class="metadata-filter"><span>Layer</span><select data-run-filter="system"><option value="all">All</option><option>Logical</option><option>Dimensional</option></select></label></div><div class="table-scroll"><table class="data-table run-table"><thead><tr><th>Run</th><th>Status</th><th>Started</th><th>Layer</th><th>Targets</th><th>Output</th><th>Actor</th><th>Duration</th><th></th></tr></thead><tbody>${codeRuns.map((item) => runRowMarkup(item, "code", active.id)).join("")}</tbody></table></div></section>${state.runDetailOpen ? runInspector(active, "code generation") : ""}</div>`;
  }

  function profilingRunPanel() {
    const selectedCount = [...state.selectedContractRows].filter((key) => key.startsWith("profiling_profile:")).length;
    return `<section class="inline-drawer run-config"><header><div><small>NEW PROFILING RUN</small><h2>Profile Objects on Databricks</h2><p>Runs are explicit. No Databricks job is created.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="common-fields"><label><span>Object scope</span><select><option>${selectedCount ? `${selectedCount} selected profiles` : `All ${objectRows.length} Objects`}</option></select></label><label><span>System</span><select><option>CRM · 8 Objects</option><option>ERP · 11 Objects</option><option>Commerce · 6 Objects</option></select></label><label><span>Batch ID (optional)</span><input value="10428"></label></div><footer><span>Objects without a batch attribute run without a batch predicate.</span><button class="button button-primary" data-start-run="profiling">${state.running ? "Running…" : "Run profiling"}</button></footer></section>`;
  }

  function analysisRunPanel() {
    if (state.panel === "analysis-validation") return `<section class="inline-drawer run-config"><header><div><small>NEW VALIDATION RUN</small><h2>Validate pending relationship evidence</h2><p>Validation updates evidence columns only. It never changes inference or lock state.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="common-fields"><label><span>Finding scope</span><select><option>15 pending findings</option><option>Selected findings</option></select></label><label><span>System</span><select><option>CRM</option><option>ERP</option><option>Commerce</option></select></label><label><span>Batch ID (optional)</span><input value="10428"></label></div><footer><span>Errors are captured as run events. Nothing is partially written.</span><button class="button button-primary" data-start-run="validation">${state.running ? "Running…" : "Run validation"}</button></footer></section>`;
    return `<section class="inline-drawer run-config"><header><div><small>NEW INFERENCE RUN</small><h2>Infer relationship candidates</h2><p>Locked findings remain unchanged. Mode selection is always explicit.</p></div><button class="panel-close" data-panel-close aria-label="Close">×</button></header><div class="common-fields authoring-run-fields"><label><span>Mode</span><select><option>One-shot</option><option>Tool-assisted</option><option>Detailed Coverage</option></select></label><label><span>Object scope</span><select><option>All ${objectRows.length} Objects</option><option>Selected Objects</option></select></label><label><span>Registered model</span><select><option>Foundry · gpt-5</option><option>Foundry · gpt-5-mini</option></select></label><label><span>Reasoning effort</span><select><option>Medium</option><option>High</option><option>Low</option></select></label><label><span>Max turns</span><input type="number" value="12" min="1" max="50"></label><label><span>Validation retries</span><input type="number" value="2" min="0" max="5"></label></div><footer><span>No automatic fallback or partial write.</span><button class="button button-primary" data-start-run="inference">${state.running ? "Running…" : "Run inference"}</button></footer></section>`;
  }

  function objectRowMarkup(item, context) {
    const active = item.id === state.activeObject ? "is-active" : "";
    const searchable = `${item.name} ${item.system} ${item.tenant} ${item.batchAttribute || ""}`.toLowerCase();
    if (context === "metadata") return `<tr class="${state.metadataDetailOpen && item.id === state.activeMetadataObject ? "is-active" : ""}" data-zone="${item.zone.toLowerCase()}" data-search="${searchable} ${item.zone.toLowerCase()}"><td><strong>${item.name}</strong><span>Table</span></td><td>${item.system}</td><td>${item.tenant}</td><td><em class="zone">${item.zone}</em></td><td>${item.attributeCount}</td><td>${item.batchAttribute || "—"}</td><td><button class="text-action detail-action" data-show-metadata-detail="${item.id}">Show details</button></td></tr>`;
    if (context === "scope") return `<tr class="${state.scopeDetailOpen ? active : ""}" data-search="${searchable}"><td class="check"><input type="checkbox" data-select-scope="${item.id}" aria-label="Select ${item.name}" ${state.selectedScope.has(item.id) ? "checked" : ""}></td><td><strong>${item.name}</strong><span>Table</span></td><td>${item.system}</td><td>${item.tenant}</td><td>${item.attributeCount}</td><td>${item.batchAttribute || "—"}</td><td><em class="zone">Bronze</em></td><td><button class="text-action detail-action" data-show-scope-detail="${item.id}">Show details</button></td></tr>`;
    return `<tr class="${active}" data-object-id="${item.id}" data-search="${searchable} ${item.profileStatus.toLowerCase()}"><td class="check"><input type="checkbox" data-select-profile="${item.id}" aria-label="Select ${item.name}" ${state.selectedProfile.has(item.id) ? "checked" : ""}></td><td><strong>${item.name}</strong><span>${item.system} · ${item.tenant}</span></td><td><em class="status ${statusClass(item.profileStatus)}">${item.profileStatus}</em></td><td>${item.rowCount}</td><td>${item.freshness}</td><td>${item.nullRate}</td><td>${item.uniqueRate}</td></tr>`;
  }

  function findingRowMarkup(item) {
    const searchable = `${item.fromObject} ${item.fromAttribute} ${item.toObject} ${item.toAttribute} ${item.type}`.toLowerCase();
    return `<tr data-search="${searchable}" class="${item.active ? "" : "is-inactive"}"><td class="check"><input type="checkbox" data-select-finding="${item.id}" aria-label="Select finding from ${item.fromObject}" ${state.selectedFindings.has(item.id) ? "checked" : ""}></td><td><strong>${item.fromObject}</strong><span>${item.fromAttribute}</span></td><td>${item.type}</td><td><strong>${item.toObject}</strong><span>${item.toAttribute}</span></td><td><em class="confidence ${item.confidence.toLowerCase()}">${item.confidence}</em></td><td><em class="status ${statusClass(item.validation)}">${item.validation}</em></td><td><button class="lock-control-row ${item.locked ? "is-locked" : ""}" data-direct-lock="${item.id}">${item.locked ? "Locked" : "Open"}</button></td></tr>`;
  }

  function runRowMarkup(item, workflow, activeId) {
    const mode = workflow === "analysis" ? item.id === "AN-0317" ? "Detailed Coverage" : "One-shot" : item.batch;
    return `<tr class="${state.runDetailOpen && item.id === activeId ? "is-active" : ""}" data-search="${Object.values(item).join(" ").toLowerCase()}" data-run-status="${item.status}" data-run-system="${item.system}" data-run-batch="${mode}"><td><strong>${item.id}</strong></td><td><em class="status ${statusClass(item.status)}">${item.status}</em></td><td>${item.started}</td><td>${item.system}</td><td>${item.objectCount}</td><td>${mode}</td><td>${item.actor}</td><td>${item.duration}</td><td><button class="text-action detail-action" data-show-run-detail="${workflow}" data-run-id="${item.id}">Show details</button></td></tr>`;
  }

  function runInspector(item, workflow) {
    const events = workflow === "profiling"
      ? [["Prepare", "8 Objects grouped for CRM"], ["Connect", "SQL Warehouse session opened"], ["Execute", "7 profiles completed"], ["Capture warning", "1 Object has no batch attribute"], ["Complete", "Results committed atomically"]]
      : [["Prepare", "Run configuration validated"], ["Assemble context", "25 Objects assembled"], ["Inference", "37 candidates returned"], ["Repair", "1 duplicate identity repaired"], ["Commit", "37 findings committed atomically"]];
    return `<aside class="run-inspector"><header><div><small>RUN EVENTS</small><h2>${item.id}</h2></div><div class="inspector-header-actions"><em class="status ${statusClass(item.status)}">${item.status}</em><button class="panel-close" data-close-run-detail aria-label="Close run details">×</button></div></header><dl><div><dt>Started</dt><dd>${item.started}</dd></div><div><dt>Actor</dt><dd>${item.actor}</dd></div><div><dt>Duration</dt><dd>${item.duration}</dd></div></dl><div class="event-list">${events.map((event, index) => `<article><i class="${item.status === "Failed" && index === 2 ? "danger" : index === events.length - 1 ? "complete" : ""}"></i><div><strong>${event[0]}</strong><span>${item.status === "Failed" && index === 2 ? "Run stopped: governed query validation failed" : event[1]}</span></div><time>${index === 0 ? "0s" : `${index * 18}s`}</time></article>`).join("")}</div><p>Events explain progress without storing raw prompts, physical rows, credentials, or unredacted tool output.</p></aside>`;
  }

  function metadataInspector(item) {
    return `<aside class="object-inspector metadata-object-inspector"><header><div><small>OBJECT DETAILS</small><h2>${item.name}</h2></div><div class="inspector-header-actions"><em class="zone">${item.zone}</em><button class="panel-close" data-close-metadata-detail aria-label="Close object details">×</button></div></header><dl class="object-facts"><div><dt>System</dt><dd>${item.system}</dd></div><div><dt>Source Tenant</dt><dd>${item.tenant}</dd></div><div><dt>Type</dt><dd>Table</dd></div><div><dt>Attributes</dt><dd>${item.attributeCount}</dd></div><div><dt>Batch attribute</dt><dd>${item.batchAttribute || "None"}</dd></div><div><dt>Profiling</dt><dd>${item.profileStatus}</dd></div></dl>${attributeTable(item, false)}</aside>`;
  }

  function scopeInspector(item) {
    return `<aside class="object-inspector compact scope-object-inspector"><header><div><small>OBJECT DETAILS</small><h2>${item.name}</h2></div><div class="inspector-header-actions"><em class="zone">Bronze</em><button class="panel-close" data-close-scope-detail aria-label="Close object details">×</button></div></header><p>${item.system} · ${item.tenant} · ${item.attributeCount} attributes</p><div class="eligibility"><strong>Eligible now</strong><span>Profiling, Analysis, Conceptual, and Logical</span></div>${attributeTable(item, false)}</aside>`;
  }

  function profileInspector(item) {
    if (item.profileStatus === "Not profiled") return `<aside class="object-inspector compact empty-inspector"><header><div><small>SELECTED OBJECT</small><h2>${item.name}</h2></div><em class="status neutral">Not profiled</em></header><p>No column statistics are stored for this Object.</p><button class="button button-primary" data-select-and-profile="${item.id}">Profile this Object</button></aside>`;
    return `<aside class="object-inspector compact"><header><div><small>PROFILE RESULT</small><h2>${item.name}</h2></div><em class="status ${statusClass(item.profileStatus)}">${item.profileStatus}</em></header><dl class="profile-facts"><div><dt>Rows</dt><dd>${item.rowCount}</dd></div><div><dt>Freshness</dt><dd>${item.freshness}</dd></div><div><dt>Batch</dt><dd>${item.batchAttribute || "Not used"}</dd></div></dl>${attributeTable(item, true)}</aside>`;
  }

  function attributesFor(objectRow) {
    const stem = objectRow.name.replace(/_raw$/, "");
    const special = {
      customer_raw: [["customer_id", "bigint", "No", "Primary key"], ["customer_name", "string", "No", "Business"], ["customer_type_code", "string", "Yes", "Business"], ["email_address", "string", "Yes", "Sensitive"], ["country_code", "string", "Yes", "Reference"], ["created_at", "timestamp", "No", "Audit"], ["updated_at", "timestamp", "Yes", "Audit"]],
      invoice_raw: [["invoice_id", "bigint", "No", "Primary key"], ["customer_id", "bigint", "No", "Reference"], ["currency_code", "string", "No", "Reference"], ["invoice_date", "date", "No", "Business"], ["due_date", "date", "Yes", "Business"], ["total_amount", "decimal(18,2)", "No", "Measure"], ["status_code", "string", "No", "Business"]],
      order_raw: [["order_id", "bigint", "No", "Primary key"], ["customer_id", "bigint", "No", "Reference"], ["order_date", "timestamp", "No", "Business"], ["currency_code", "string", "No", "Reference"], ["order_amount", "decimal(18,2)", "No", "Measure"], ["status_code", "string", "No", "Business"]],
    };
    const base = special[objectRow.name] || [[`${stem}_id`, "bigint", "No", "Primary key"], [`${stem}_name`, "string", "Yes", "Business"], ["status_code", "string", "Yes", "Business"], ["effective_date", "date", "Yes", "Business"], ["source_system_code", "string", "No", "Audit"], ["created_at", "timestamp", "No", "Audit"], ["updated_at", "timestamp", "Yes", "Audit"]];
    const rows = objectRow.batchAttribute ? [...base, [objectRow.batchAttribute, "bigint", "No", "Batch"]] : base;
    return rows.map((item, index) => ({ name: item[0], type: item[1], nullable: item[2], role: item[3], nullRate: objectRow.profileStatus === "Not profiled" ? "—" : index === 0 ? "0.0%" : `${((index * 2.3 + objectRow.attributeCount) % 17).toFixed(1)}%`, distinct: objectRow.profileStatus === "Not profiled" ? "—" : index === 0 ? objectRow.rowCount : `${Math.max(4, objectRow.attributeCount * (index + 3) * 19).toLocaleString()}` }));
  }

  function attributeTable(item, profile) {
    const attributes = attributesFor(item);
    return `<section class="attribute-section"><header><strong>${profile ? "Column profile" : "Attributes"}</strong><span>${attributes.length} of ${item.attributeCount} shown</span></header><div class="attribute-scroll"><table><thead><tr><th>Name</th><th>Type</th>${profile ? "<th>Null</th><th>Distinct</th>" : "<th>Null?</th><th>Role</th>"}</tr></thead><tbody>${attributes.map((attribute) => `<tr><td><strong>${attribute.name}</strong></td><td>${attribute.type}</td>${profile ? `<td>${attribute.nullRate}</td><td>${attribute.distinct}</td>` : `<td>${attribute.nullable}</td><td>${attribute.role}</td>`}</tr>`).join("")}</tbody></table></div></section>`;
  }

  function activityRows() {
    return `<article><i class="complete"></i><div><strong>Analysis inference completed</strong><span>Customer 360 · 37 findings · one repair</span></div><time>12m ago</time></article><article><i class="warning"></i><div><strong>Profiling completed with warnings</strong><span>Customer 360 · 18 of 25 Objects</span></div><time>1h ago</time></article><article><i class="complete"></i><div><strong>Metadata synchronized</strong><span>CRM · 63 Objects refreshed</span></div><time>38m ago</time></article>`;
  }

  function findObject(id) { return objectRows.find((item) => item.id === id) || objectRows[0]; }
  function findMetadataObject(id) { return metadataObjectRows.find((item) => item.id === id) || metadataObjectRows[0]; }
  function titleCase(value) { return value.charAt(0).toUpperCase() + value.slice(1); }
  function statusClass(value) {
    if (["Complete", "Completed", "Supported", "Completed with repair"].includes(value)) return "complete";
    if (["Warning", "Pending", "Inconclusive", "Completed with warnings"].includes(value)) return "warning";
    if (["Unsupported", "Failed"].includes(value)) return "danger";
    return "neutral";
  }

  function render(resetScroll = false) {
    const screens = {
      "tenant-select": tenantSelectPage, "tenant-home": tenantHomePage, metadata: metadataPage, models: modelsPage,
      "model-home": modelHome, scope: scopePage, profiling: profilingPage, analysis: analysisPage, assertions: assertionsPage,
      conceptual: () => authoringPage("conceptual"), logical: () => authoringPage("logical"), dimensional: () => authoringPage("dimensional"),
      mapping: mappingPage, "mapping-logical": () => mappingWorkflowPage("logical"), "mapping-dimensional": () => mappingWorkflowPage("dimensional"), "record-detail": contractDetailPage, code: codePage, "code-model": codeModelPage,
    };
    document.getElementById("app").innerHTML = screens[state.screen]();
    bindInteractions();
    if (resetScroll) window.requestAnimationFrame(() => { window.scrollTo(0, 0); const workspace = document.querySelector(".workspace"); if (workspace) workspace.scrollTop = 0; });
  }

  function bindInteractions() {
    document.querySelectorAll("[data-nav]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.nav)));
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => handleAction(button.dataset.action)));
    document.querySelectorAll("[data-tenant-id]").forEach((button) => button.addEventListener("click", () => { state.selectedTenant = button.dataset.tenantId; render(); }));
    document.querySelectorAll("[data-meta-section]").forEach((button) => button.addEventListener("click", () => { state.metaSection = button.dataset.metaSection; state.metaDataset = metadataGroups[state.metaSection][0].id; state.metadataDetailOpen = false; state.panel = null; if (state.metaSection === "operational") state.metaDataset = "bronze_object"; render(); }));
    document.querySelectorAll("[data-meta-dataset]").forEach((button) => button.addEventListener("click", () => { state.metaDataset = button.dataset.metaDataset; state.metadataDetailOpen = false; render(); }));
    document.querySelectorAll("[data-profile-view]").forEach((button) => button.addEventListener("click", () => { state.profilingView = button.dataset.profileView; state.runDetailOpen = false; state.panel = null; render(); }));
    document.querySelectorAll("[data-analysis-view]").forEach((button) => button.addEventListener("click", () => { state.analysisView = button.dataset.analysisView; state.runDetailOpen = false; state.panel = null; state.selectedFindings.clear(); render(); }));
    document.querySelectorAll("[data-model-dataset]").forEach((button) => button.addEventListener("click", () => {
      const property = button.dataset.modelStage === "assertion" ? "assertionDataset" : `${button.dataset.modelStage}Dataset`;
      state[property] = button.dataset.modelDataset; state.selectedContractRows.clear(); state.contractDetailOpen = false; state.runDetailOpen = false; state.panel = null; render();
    }));
    document.querySelectorAll("[data-mapping-dataset]").forEach((button) => button.addEventListener("click", () => { state.mappingDataset = button.dataset.mappingDataset; state.selectedContractRows.clear(); state.contractDetailOpen = false; state.runDetailOpen = false; state.panel = null; render(); }));
    document.querySelectorAll("[data-code-view]").forEach((button) => button.addEventListener("click", () => { state.codeView = button.dataset.codeView; state.runDetailOpen = false; state.panel = null; render(); }));
    document.querySelectorAll("[data-code-target]").forEach((button) => button.addEventListener("click", () => { state.activeCodeTarget = button.dataset.codeTarget; render(); }));
    const showGenerated = document.querySelector("[data-show-generated]");
    if (showGenerated) showGenerated.addEventListener("click", () => {
      const target = codeTargets.find((row) => state.selectedCodeTargets.has(row.id));
      if (!target?.generated_sql) return;
      state.activeCodeTarget = target.id; state.codeView = "saved"; state.selectedCodeTargets.clear(); render();
    });
    document.querySelectorAll("[data-panel]").forEach((button) => button.addEventListener("click", () => { state.panel = button.dataset.panel; render(true); }));
    document.querySelectorAll("[data-panel-close]").forEach((button) => button.addEventListener("click", () => { state.panel = null; render(); }));
    document.querySelectorAll("[data-object-id]").forEach((row) => row.addEventListener("click", (event) => { if (event.target.closest("input, button")) return; state.activeObject = row.dataset.objectId; render(); }));
    document.querySelectorAll("[data-show-metadata-detail]").forEach((button) => button.addEventListener("click", () => { state.activeMetadataObject = button.dataset.showMetadataDetail; state.metadataDetailOpen = true; render(); }));
    document.querySelectorAll("[data-close-metadata-detail]").forEach((button) => button.addEventListener("click", () => { state.metadataDetailOpen = false; render(); }));
    document.querySelectorAll("[data-show-scope-detail]").forEach((button) => button.addEventListener("click", () => { state.activeObject = button.dataset.showScopeDetail; state.scopeDetailOpen = true; render(); }));
    document.querySelectorAll("[data-close-scope-detail]").forEach((button) => button.addEventListener("click", () => { state.scopeDetailOpen = false; render(); }));
    document.querySelectorAll("[data-show-contract-detail]").forEach((button) => button.addEventListener("click", () => {
      const [dataset, index] = button.dataset.showContractDetail.split(":");
      if (isDedicatedDetailDataset(dataset)) { openContractDetail(dataset, Number(index)); return; }
      state.activeContractRow = { dataset, index: Number(index) }; state.contractDetailOpen = true; render();
    }));
    document.querySelectorAll("[data-record-back]").forEach((button) => button.addEventListener("click", backFromContractDetail));
    document.querySelectorAll("[data-detail-step]").forEach((button) => button.addEventListener("click", () => stepContractDetail(Number(button.dataset.detailStep))));
    document.querySelectorAll("[data-close-contract-detail]").forEach((button) => button.addEventListener("click", () => { state.contractDetailOpen = false; render(); }));
    document.querySelectorAll("[data-edit-contract-row]").forEach((button) => button.addEventListener("click", () => { const dataset = button.dataset.editContractRow.split(":")[0]; showToast(`Mock governed row editor opened for ${modelContracts[dataset]?.label || "record"}.`); }));
    document.querySelectorAll("[data-show-run-detail]").forEach((button) => button.addEventListener("click", () => { state.activeRunId = button.dataset.runId; state.runDetailOpen = true; render(); }));
    document.querySelectorAll("[data-close-run-detail]").forEach((button) => button.addEventListener("click", () => { state.runDetailOpen = false; render(); }));
    document.querySelectorAll("[data-select-scope]").forEach((input) => input.addEventListener("change", () => toggleSet(state.selectedScope, input.dataset.selectScope, input.checked)));
    document.querySelectorAll("[data-select-profile]").forEach((input) => input.addEventListener("change", () => toggleSet(state.selectedProfile, input.dataset.selectProfile, input.checked)));
    document.querySelectorAll("[data-select-finding]").forEach((input) => input.addEventListener("change", () => toggleSet(state.selectedFindings, input.dataset.selectFinding, input.checked)));
    document.querySelectorAll("[data-select-candidate]").forEach((input) => input.addEventListener("change", () => toggleSet(state.selectedCandidates, input.dataset.selectCandidate, input.checked)));
    document.querySelectorAll("[data-select-contract]").forEach((input) => input.addEventListener("change", () => toggleSet(state.selectedContractRows, input.dataset.selectContract, input.checked)));
    document.querySelectorAll("[data-select-code]").forEach((input) => input.addEventListener("change", () => toggleSet(state.selectedCodeTargets, input.dataset.selectCode, input.checked)));
    document.querySelectorAll("[data-select-all]").forEach((input) => input.addEventListener("change", () => selectAll(input.dataset.selectAll, input.checked)));
    document.querySelectorAll("[data-select-all-contract]").forEach((input) => input.addEventListener("change", () => selectAllContract(input.dataset.selectAllContract, input.checked)));
    document.querySelectorAll("[data-select-all-code]").forEach((input) => input.addEventListener("change", () => { state.selectedCodeTargets.clear(); if (input.checked) codeTargets.forEach((row) => state.selectedCodeTargets.add(row.id)); render(); }));
    document.querySelectorAll("[data-direct-lock]").forEach((button) => button.addEventListener("click", () => directLock(button.dataset.directLock)));
    document.querySelectorAll("[data-bulk-lock]").forEach((button) => button.addEventListener("click", () => bulkLock(button.dataset.bulkLock === "true")));
    document.querySelectorAll("[data-contract-lock]").forEach((button) => button.addEventListener("click", () => bulkContractLock(button.dataset.contractLock === "true")));
    document.querySelectorAll("[data-filter-table]").forEach((input) => input.addEventListener("input", () => filterTable(input.dataset.filterTable, input.value)));
    document.querySelectorAll("[data-metadata-filter]").forEach((select) => select.addEventListener("change", filterMetadataRows));
    document.querySelectorAll("[data-contract-filter]").forEach((select) => select.addEventListener("change", filterContractRows));
    document.querySelectorAll("[data-run-filter]").forEach((select) => select.addEventListener("change", filterRunRows));
    document.querySelectorAll("[data-code-filter]").forEach((select) => select.addEventListener("change", filterCodeRows));
    document.querySelectorAll("[data-candidate-filter]").forEach((select) => select.addEventListener("change", filterCandidateRows));
    const candidateSearch = document.querySelector("[data-candidate-search]");
    if (candidateSearch) candidateSearch.addEventListener("input", filterCandidateRows);
    const selectAllCandidates = document.querySelector("[data-select-all-candidates]");
    if (selectAllCandidates) selectAllCandidates.addEventListener("change", () => {
      document.querySelectorAll("#candidate-table tbody tr:not([hidden])").forEach((row) => {
        const id = row.dataset.candidateId;
        selectAllCandidates.checked ? state.selectedCandidates.add(id) : state.selectedCandidates.delete(id);
      });
      render();
    });
    document.querySelectorAll("[data-edit-metadata-row]").forEach((button) => button.addEventListener("click", () => showToast(`Mock governed row editor opened for ${metadataDatasetLabel()}.`)));
    document.querySelectorAll("[data-start-run]").forEach((button) => button.addEventListener("click", () => startRun(button.dataset.startRun)));
    document.querySelectorAll("[data-select-and-profile]").forEach((button) => button.addEventListener("click", () => { state.selectedProfile.add(button.dataset.selectAndProfile); state.panel = "profiling-run"; render(true); }));
    const tenantFilter = document.querySelector("[data-tenant-filter]");
    if (tenantFilter) tenantFilter.addEventListener("input", () => filterTenants(tenantFilter.value));
    const inactive = document.querySelector("[data-toggle-inactive]");
    if (inactive) inactive.addEventListener("change", () => { state.showInactive = inactive.checked; render(); });
    if (document.querySelector("#candidate-table")) filterCandidateRows();
  }

  function navigate(screen) {
    if (!allowedScreens.has(screen)) { handleAction(screen); return; }
    if (screen !== "scope") state.scopeDetailOpen = false;
    state.runDetailOpen = false; state.contractDetailOpen = false; state.selectedContractRows.clear();
    state.screen = screen; state.panel = null; updateUrl(); render(true);
  }
  function openContractDetail(dataset, index) {
    state.activeContractRow = { dataset, index };
    state.detailReturnScreen = state.screen;
    state.contractDetailOpen = false;
    state.screen = "record-detail";
    updateUrl(); render(true);
  }
  function backFromContractDetail() {
    const screen = state.detailReturnScreen || (state.activeContractRow?.dataset.startsWith("mapping_") ? "mapping-logical" : state.activeContractRow?.dataset.split("_")[0]) || "models";
    state.screen = allowedScreens.has(screen) && screen !== "record-detail" ? screen : "models";
    state.activeContractRow = null;
    updateUrl(); render(true);
  }
  function stepContractDetail(direction) {
    const active = state.activeContractRow;
    if (!active) return;
    const rows = modelContractRows(active.dataset);
    const next = Math.max(0, Math.min(rows.length - 1, active.index + direction));
    state.activeContractRow = { ...active, index: next };
    updateUrl(); render(true);
  }
  function toggleSet(set, id, checked) { checked ? set.add(id) : set.delete(id); render(); }
  function selectAll(kind, checked) {
    const visibleFindings = findings.filter((item) => state.showInactive || item.active);
    const mapping = { scope: [state.selectedScope, objectRows.map((item) => item.id)], profile: [state.selectedProfile, objectRows.map((item) => item.id)], findings: [state.selectedFindings, visibleFindings.map((item) => item.id)] };
    const [set, ids] = mapping[kind]; set.clear(); if (checked) ids.forEach((id) => set.add(id)); render();
  }
  function selectAllContract(dataset, checked) {
    [...state.selectedContractRows].filter((key) => key.startsWith(`${dataset}:`)).forEach((key) => state.selectedContractRows.delete(key));
    if (checked) document.querySelectorAll('#contract-table tbody tr:not([hidden])').forEach((row) => state.selectedContractRows.add(row.dataset.contractRowKey));
    render();
  }
  function directLock(id) { const item = findings.find((candidate) => candidate.id === id); item.locked = !item.locked; showToast(item.locked ? "Finding locked by user." : "Finding unlocked by user."); render(); }
  function bulkLock(locked) { findings.forEach((item) => { if (state.selectedFindings.has(item.id)) item.locked = locked; }); const count = state.selectedFindings.size; state.selectedFindings.clear(); render(); showToast(`${count} findings ${locked ? "locked" : "unlocked"}.`); }
  function bulkContractLock(locked) {
    const keys = [...state.selectedContractRows];
    keys.forEach((key) => {
      const [dataset, index] = key.split(":");
      const row = modelContractRows(dataset)[Number(index)];
      if (!row) return;
      if (row.__findingId) { const finding = findings.find((item) => item.id === row.__findingId); if (finding) finding.locked = locked; return; }
      const lockField = Object.keys(row).find((field) => field === "is_locked" || field.endsWith("_is_locked"));
      if (lockField) row[lockField] = locked;
    });
    const count = keys.length; state.selectedContractRows.clear(); render(); showToast(`${count} records ${locked ? "locked" : "unlocked"}.`);
  }
  function filterTable(tableId, value) { const query = value.trim().toLowerCase(); document.querySelectorAll(`#${tableId} [data-search]`).forEach((row) => { row.hidden = Boolean(query && !row.dataset.search.includes(query)); }); }
  function filterTenants(value) { const query = value.trim().toLowerCase(); document.querySelectorAll("[data-tenant-search]").forEach((card) => { card.hidden = Boolean(query && !card.dataset.tenantSearch.includes(query)); }); }
  function filterMetadataRows() {
    const filters = [...document.querySelectorAll("[data-metadata-filter]")];
    document.querySelectorAll("#metadata-contract-table tbody tr").forEach((row) => {
      row.hidden = filters.some((filter) => filter.value !== "all" && row.getAttribute(`data-filter-${filter.dataset.metadataFilter}`) !== filter.value);
    });
  }
  function filterContractRows() {
    const filters = [...document.querySelectorAll("[data-contract-filter]")];
    document.querySelectorAll("#contract-table tbody tr").forEach((row) => {
      row.hidden = filters.some((filter) => filter.value !== "all" && !(row.getAttribute(`data-contract-${filter.dataset.contractFilter}`) || "").split("|").includes(filter.value));
    });
  }
  function filterRunRows() {
    const filters = [...document.querySelectorAll("[data-run-filter]")];
    document.querySelectorAll(".run-table tbody tr").forEach((row) => {
      row.hidden = filters.some((filter) => filter.value !== "all" && row.getAttribute(`data-run-${filter.dataset.runFilter}`) !== filter.value);
    });
  }
  function filterCodeRows() {
    const filters = [...document.querySelectorAll("[data-code-filter]")];
    document.querySelectorAll("#code-target-table tbody tr").forEach((row) => {
      row.hidden = filters.some((filter) => filter.value !== "all" && row.getAttribute(`data-code-${filter.dataset.codeFilter}`) !== filter.value);
    });
  }
  function filterCandidateRows() {
    const search = document.querySelector("[data-candidate-search]");
    state.candidateFilters.search = search ? search.value : state.candidateFilters.search;
    document.querySelectorAll("[data-candidate-filter]").forEach((select) => { state.candidateFilters[select.dataset.candidateFilter] = select.value; });
    const query = state.candidateFilters.search.trim().toLowerCase();
    document.querySelectorAll("#candidate-table tbody tr").forEach((row) => {
      row.hidden = Boolean((query && !row.dataset.search.includes(query)) || ["tenant", "system", "zone"].some((field) => state.candidateFilters[field] !== "all" && row.dataset[`candidate${titleCase(field)}`] !== state.candidateFilters[field]));
    });
  }
  function metadataDatasetLabel() { return metadataGroups[state.metaSection].find((item) => item.id === state.metaDataset)?.label || "metadata"; }
  function activeContractDataset() {
    if (state.screen === "assertions") return state.assertionDataset;
    if (["conceptual", "logical", "dimensional"].includes(state.screen)) return state[`${state.screen}Dataset`];
    if (state.screen.startsWith("mapping-")) return state.mappingDataset;
    if (state.screen === "scope") return "model_scope";
    if (state.screen === "profiling") return "profiling_profile";
    if (state.screen === "analysis") return "analysis_result";
    return null;
  }

  function startRun(operation) {
    state.running = true; render(); showToast(`Mock ${operation} run started.`);
    window.setTimeout(() => {
      state.running = false; state.panel = null;
      if (operation === "profiling") state.profilingView = "runs";
      if (["inference", "validation"].includes(operation)) state.analysisView = "runs";
      if (["conceptual", "logical", "dimensional"].includes(operation)) state[`${operation}Dataset`] = "runs";
      if (operation === "mapping") state.mappingDataset = "runs";
      if (operation === "code") {
        const targets = state.selectedCodeTargets.size ? codeTargets.filter((row) => state.selectedCodeTargets.has(row.id)) : state.codeView === "saved" ? codeTargets.filter((row) => row.id === state.activeCodeTarget) : codeTargets;
        targets.forEach((target) => {
          const mapping = modelContracts.mapping_object.rows.find((row) => row.object_name === target.target_object_name);
          const source = mapping?.mapping_package_document?.source_objects?.[0] || physicalObject(target.modeled_entity_type === "logical_entity" ? `${target.target_object_name}_raw` : target.modeled_entity_name.toLowerCase().replaceAll(" ", "_"), target.source_system_code, target.target_tenant_code, target.modeled_entity_type === "logical_entity" ? `bronze_${target.source_system_code.toLowerCase()}` : "silver_nwa");
          target.generated_sql = storedSql(target.target_object_schema, target.target_object_name, source.object_schema, source.object_name); target.generated_at = "Just now"; target.generated_run_id = "CG-0043";
        });
        state.activeCodeTarget = targets[0]?.id || state.activeCodeTarget; state.selectedCodeTargets.clear(); state.codeView = "saved";
      }
      render(); showToast(`Mock ${operation} run completed.`);
    }, 1100);
  }

  function handleAction(action) {
    if (action === "enter-tenant") { navigate("tenant-home"); return; }
    if (action === "open-override") { state.panel = "override-lock"; render(); return; }
    if (action === "cancel-override") { state.panel = null; render(); return; }
    if (action === "confirm-override") { state.lockState = "mine"; state.panel = null; render(); showToast("Explicit override recorded. Tenant Lock acquired."); return; }
    if (action === "acquire-lock") { state.lockState = "mine"; render(); showToast("Tenant Lock acquired for 1 hour."); return; }
    if (action === "renew-lock") { showToast("Tenant Lock extended by 1 hour."); return; }
    if (action === "release-lock") { state.lockState = "unlocked"; render(); showToast("Tenant Lock released."); return; }
    if (action === "refresh-results") { showToast("Latest saved results refreshed."); return; }
    if (action === "import-metadata") { showToast("Mock Operational Excel import opened."); return; }
    if (action === "metadata-add-row") { showToast(`Mock governed Add Row editor opened for ${metadataDatasetLabel()}.`); return; }
    if (action === "contract-add-row") { const dataset = activeContractDataset(); showToast(`Mock governed Add Row editor opened for ${modelContracts[dataset]?.label || "record"}.`); return; }
    if (action === "contract-inactive") {
      const keys = [...state.selectedContractRows];
      keys.forEach((key) => {
        const [dataset, index] = key.split(":"); const row = modelContractRows(dataset)[Number(index)]; if (!row) return;
        if (row.__findingId) { const finding = findings.find((item) => item.id === row.__findingId); if (finding) finding.active = false; return; }
        const activeField = Object.keys(row).find((field) => field === "is_active" || field.endsWith("_status"));
        if (activeField) row[activeField] = activeField === "is_active" ? false : "inactive";
      });
      state.selectedContractRows.clear(); render(); showToast(`${keys.length} records made inactive.`); return;
    }
    if (action === "download-sql-zip") { showToast("Mock SQL ZIP download prepared."); return; }
    if (action === "download-sql") { showToast("Mock stored SQL download prepared."); return; }
    if (action === "open-metadata-export") { state.panel = state.panel === "metadata-export" ? null : "metadata-export"; render(); return; }
    if (action === "select-export-sheets") { document.querySelectorAll(".export-sheet-list input").forEach((input) => { input.checked = true; }); return; }
    if (action === "export-selected-sheets") { state.panel = null; render(); showToast("Mock Excel export prepared for selected Operational sheets."); return; }
    if (action === "export-all-sheets") { state.panel = null; render(); showToast("Mock Excel export prepared with all 16 Operational sheets."); return; }
    if (action === "open-add-scope") { state.panel = "add-scope"; render(true); return; }
    if (action === "confirm-add-scope") {
      const additions = candidateRows.filter((item) => state.selectedCandidates.has(item.id));
      additions.forEach((item) => objectRows.push(item));
      additions.forEach((item) => candidateRows.splice(candidateRows.findIndex((candidate) => candidate.id === item.id), 1));
      state.selectedCandidates.clear(); state.panel = null; render(); showToast(`${additions.length} Objects added to active scope.`); return;
    }
    if (action === "make-inactive") { findings.forEach((item) => { if (state.selectedFindings.has(item.id)) item.active = false; }); const count = state.selectedFindings.size; state.selectedFindings.clear(); render(); showToast(`${count} findings made inactive.`); return; }
    const labels = { administration: "Administration is outside this prototype.", "remove-scope": "Prototype only; no Scope mutation was sent.", "edit-metadata": "Would open the governed operational metadata editor.", "new-model": "Mock governed Model creation opened.", "edit-model": "Mock governed Model editor opened.", "workspace-history": "Would open the shared Tenant activity history.", "lock-history": "Would open governed Tenant Lock events.", "advanced-settings": "Advanced settings stay one level deeper.", "open-example-model": "Only Customer 360 is connected in this prototype.", "model-settings": "Model settings stay one level deeper.", "scope-history": "Would show Model Scope change history.", "model-activity": "Would show Model activity." };
    showToast(labels[action] || "Prototype action only.");
  }

  function updateUrl() {
    const url = new URL(window.location.href);
    url.searchParams.delete("variant");
    url.searchParams.set("screen", state.screen);
    if (state.screen === "record-detail" && state.activeContractRow) {
      url.searchParams.set("dataset", state.activeContractRow.dataset);
      url.searchParams.set("row", String(state.activeContractRow.index));
      url.searchParams.set("origin", state.detailReturnScreen);
    } else {
      url.searchParams.delete("dataset"); url.searchParams.delete("row"); url.searchParams.delete("origin");
    }
    window.history.replaceState({}, "", url);
  }
  let toastTimer;
  function showToast(message) { const toast = document.getElementById("toast"); toast.textContent = message; toast.classList.add("is-visible"); window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2100); }

  render();
})();
