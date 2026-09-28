-- Governed global defaults for new Logical and Dimensional Mapping documents.
-- Copy outside the repository and replace the three identity placeholders with
-- one existing active Super Admin Entra identity. Run after install verification.
-- Exact replay is a no-op; conflicting content is rejected, never overwritten.
-- Existing Mapping documents and frozen Workflow Runs are not changed.

DO $global_mapping_output_template_seed$
DECLARE
    v_entra_tenant_text TEXT := '__REPLACE_WITH_ENTRA_TENANT_ID__';
    v_entra_object_text TEXT := '__REPLACE_WITH_ENTRA_OBJECT_ID__';
    v_principal_type TEXT := '__REPLACE_WITH_PRINCIPAL_TYPE__';
    v_template JSONB;
BEGIN
    IF v_entra_tenant_text LIKE '%__REPLACE_%'
       OR v_entra_object_text LIKE '%__REPLACE_%'
       OR v_principal_type LIKE '%__REPLACE_%' THEN
        RAISE EXCEPTION 'replace every global Mapping template seed identity placeholder';
    END IF;
    IF v_principal_type NOT IN ('user', 'service_principal') THEN
        RAISE EXCEPTION 'Mapping template seed Principal type must be user or service_principal';
    END IF;
    IF v_entra_tenant_text::UUID = '00000000-0000-0000-0000-000000000000'::UUID
       OR v_entra_object_text::UUID = '00000000-0000-0000-0000-000000000000'::UUID THEN
        RAISE EXCEPTION 'Mapping template seed Entra identity UUIDs must be nonzero';
    END IF;

    FOR v_template IN
        SELECT value FROM jsonb_array_elements($mapping_templates$
[
  {
    "output_template_code": "mapping_object_default",
    "output_template_name": "Default Object Mapping",
    "output_template_description": "Describe physical inputs or modeled input/lookup sources and ordered Entity transformation steps.",
    "output_template_target_type": "mapping_object",
    "fields": [
      {
        "output_template_field_name": "source_objects",
        "output_template_field_description": "Nullable list of source Objects. Each entry has tenant_code, system_code, connection_code, object_schema, object_name, alias, in that order. The field is present and may be JSON null. Use only for Logical Mapping; set null for Dimensional Mapping.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": true,
        "output_template_field_order": 1,
        "output_template_field_example": [
          {
            "tenant_code": "NWA",
            "system_code": "GDS",
            "connection_code": "lakehouse",
            "object_schema": "bronze_crm",
            "object_name": "customer",
            "alias": "c"
          }
        ]
      },
      {
        "output_template_field_name": "source_logical_entities",
        "output_template_field_description": "Optional nullable Logical Entity sources for Dimensional input or Logical foreign-key lookups. Each entry has logical_entity_schema_name, logical_entity_name, alias. Use only frozen eligible source evidence.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": false,
        "output_template_field_order": 2,
        "output_template_field_example": [
          {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": "Customer",
            "alias": "c"
          }
        ]
      },
      {
        "output_template_field_name": "source_dimensional_entities",
        "output_template_field_description": "Optional nullable Dimensional Entity lookup sources on the Dimensional route only. Each entry has dimensional_entity_schema_name, dimensional_entity_name, alias. Use only frozen eligible same-Model peer lookup evidence.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": false,
        "output_template_field_order": 3,
        "output_template_field_example": [
          {
            "dimensional_entity_schema_name": "gold",
            "dimensional_entity_name": "CustomerDimension",
            "alias": "customer_dim"
          }
        ]
      },
      {
        "output_template_field_name": "steps",
        "output_template_field_description": "Nullable ordered list of Object transformation instructions: Objects/tables to join, join types and column predicates, filters and any additional processing. The field is present and may be JSON null.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "string",
        "output_template_field_is_required": true,
        "output_template_field_order": 4,
        "output_template_field_example": [
          "Read customer rows from c.",
          "Keep rows where c.is_active = true."
        ]
      }
    ]
  },
  {
    "output_template_code": "mapping_attribute_default",
    "output_template_name": "Default Attribute Mapping",
    "output_template_description": "Describe physical inputs or modeled input/lookup sources and the target Attribute transformation.",
    "output_template_target_type": "mapping_attribute",
    "fields": [
      {
        "output_template_field_name": "source_attributes",
        "output_template_field_description": "Optional nullable list of source Attributes. Each entry has tenant_code, system_code, connection_code, object_schema, object_name, attribute_name, in that order. Omission or JSON null is permitted. Use only for Logical Mapping; leave null or absent for Dimensional Mapping.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": false,
        "output_template_field_order": 1,
        "output_template_field_example": [
          {
            "tenant_code": "NWA",
            "system_code": "GDS",
            "connection_code": "lakehouse",
            "object_schema": "bronze_crm",
            "object_name": "customer",
            "attribute_name": "customer_name"
          }
        ]
      },
      {
        "output_template_field_name": "source_logical_attributes",
        "output_template_field_description": "Optional nullable Logical Attribute sources for Dimensional input or Logical foreign-key lookups. Each entry has logical_entity_schema_name, logical_entity_name, logical_attribute_name. Use only frozen eligible source evidence.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": false,
        "output_template_field_order": 2,
        "output_template_field_example": [
          {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": "Customer",
            "logical_attribute_name": "CustomerName"
          }
        ]
      },
      {
        "output_template_field_name": "source_dimensional_attributes",
        "output_template_field_description": "Optional nullable Dimensional Attribute lookup sources on the Dimensional route only. Each entry has dimensional_entity_schema_name, dimensional_entity_name, dimensional_attribute_name. Use only frozen eligible same-Model peer lookup evidence.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": false,
        "output_template_field_order": 3,
        "output_template_field_example": [
          {
            "dimensional_entity_schema_name": "gold",
            "dimensional_entity_name": "CustomerDimension",
            "dimensional_attribute_name": "CustomerKey"
          }
        ]
      },
      {
        "output_template_field_name": "transformation",
        "output_template_field_description": "Required SQL expression using available Object aliases, or precise implementable generation rule. Include any necessary cast, null/default, aggregation or self-join source-role behavior.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 4,
        "output_template_field_example": "TRIM(c.customer_name)"
      }
    ]
  }
]
$mapping_templates$::JSONB)
    LOOP
        PERFORM application.create_output_template(
            v_entra_tenant_text::UUID,
            v_entra_object_text::UUID,
            v_principal_type::VARCHAR,
            (v_template ->> 'output_template_code')::VARCHAR,
            (v_template ->> 'output_template_name')::VARCHAR,
            (v_template ->> 'output_template_description')::VARCHAR,
            (v_template ->> 'output_template_target_type')::VARCHAR,
            v_template -> 'fields'
        );
    END LOOP;
END;
$global_mapping_output_template_seed$;
