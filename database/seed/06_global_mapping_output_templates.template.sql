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
    "output_template_code": "mapping_logical_object_default",
    "output_template_name": "Default Logical Object Mapping",
    "output_template_description": "Logical Object Mapping using the agreed source, transformation and null-handling fields.",
    "output_template_target_type": "mapping_object",
    "output_template_modeled_entity_type": "logical_entity",
    "fields": [
      {
        "output_template_field_name": "source_tables",
        "output_template_field_description": "Required non-null array; [] is allowed. Each physical source has tenant_code, system_code, connection_code, object_schema, object_name. Logical lookup sources have entity_type=logical_entity, entity_schema_name, entity_name. Use only eligible frozen sources. No alias field is required; explain join roles in the sample query when needed.",
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
            "object_name": "customer"
          }
        ]
      },
      {
        "output_template_field_name": "filter_criteria",
        "output_template_field_description": "Required field, nullable text. Object-level filters; null when no filter applies.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 2,
        "output_template_field_example": "Keep active customer records."
      },
      {
        "output_template_field_name": "sample_query",
        "output_template_field_description": "Required field, nullable text. Pseudo-SQL illustrating supported source joins, predicates, filters and transformations. Null when unavailable; do not invent missing rules.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 3,
        "output_template_field_example": "SELECT * FROM bronze_crm.customer WHERE is_active = true"
      }
    ]
  },
  {
    "output_template_code": "mapping_logical_attribute_default",
    "output_template_name": "Default Logical Attribute Mapping",
    "output_template_description": "Logical Attribute Mapping using the agreed source, transformation and null-handling fields.",
    "output_template_target_type": "mapping_attribute",
    "output_template_modeled_entity_type": "logical_entity",
    "fields": [
      {
        "output_template_field_name": "transformation_logic",
        "output_template_field_description": "Required field, nullable text. Attribute-level natural-language or pseudocode transformation suitable for SQL generation; null when unsupported or not applicable.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 1,
        "output_template_field_example": "Trim whitespace from the source customer name."
      },
      {
        "output_template_field_name": "default_record",
        "output_template_field_description": "Required field, nullable text. Default value or fallback logic to use when the input is null. Null means do nothing; do not invent a replacement.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 2,
        "output_template_field_example": null
      },
      {
        "output_template_field_name": "source_columns",
        "output_template_field_description": "Required field, nullable array; [] is allowed. Each physical source has tenant_code, system_code, connection_code, object_schema, object_name. Logical lookup sources have entity_type=logical_entity, entity_schema_name, entity_name. Each source also has attribute_name. Use only eligible frozen Attributes. Null when not specified.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": true,
        "output_template_field_order": 3,
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
      }
    ]
  },
  {
    "output_template_code": "mapping_dimensional_object_default",
    "output_template_name": "Default Dimensional Object Mapping",
    "output_template_description": "Dimensional Object Mapping using the agreed source, transformation and null-handling fields.",
    "output_template_target_type": "mapping_object",
    "output_template_modeled_entity_type": "dimensional_entity",
    "fields": [
      {
        "output_template_field_name": "source_tables",
        "output_template_field_description": "Required non-null array; [] is allowed. Logical input sources have entity_type=logical_entity, entity_schema_name, entity_name. Dimensional peer lookup sources use entity_type=dimensional_entity with the same schema/name fields. Do not invent physical Connection or table identities. Use only eligible frozen sources. No alias field is required; explain join roles in the sample query when needed.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": true,
        "output_template_field_order": 1,
        "output_template_field_example": [
          {
            "entity_type": "logical_entity",
            "entity_schema_name": "silver",
            "entity_name": "Customer"
          }
        ]
      },
      {
        "output_template_field_name": "filter_criteria",
        "output_template_field_description": "Required field, nullable text. Object-level filters; null when no filter applies.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 2,
        "output_template_field_example": "Keep active customer records."
      },
      {
        "output_template_field_name": "sample_query",
        "output_template_field_description": "Required field, nullable text. Pseudo-SQL illustrating supported source joins, predicates, filters and transformations. Null when unavailable; do not invent missing rules.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 3,
        "output_template_field_example": "SELECT * FROM silver.Customer WHERE is_active = true"
      }
    ]
  },
  {
    "output_template_code": "mapping_dimensional_attribute_default",
    "output_template_name": "Default Dimensional Attribute Mapping",
    "output_template_description": "Dimensional Attribute Mapping using the agreed source, transformation and null-handling fields.",
    "output_template_target_type": "mapping_attribute",
    "output_template_modeled_entity_type": "dimensional_entity",
    "fields": [
      {
        "output_template_field_name": "transformation_logic",
        "output_template_field_description": "Required field, nullable text. Attribute-level natural-language or pseudocode transformation suitable for SQL generation; null when unsupported or not applicable.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 1,
        "output_template_field_example": "Trim whitespace from the source customer name."
      },
      {
        "output_template_field_name": "default_record",
        "output_template_field_description": "Required field, nullable text. Default value or fallback logic to use when the input is null. Null means do nothing; do not invent a replacement.",
        "output_template_field_data_type": "string",
        "output_template_field_array_item_type": null,
        "output_template_field_is_required": true,
        "output_template_field_order": 2,
        "output_template_field_example": null
      },
      {
        "output_template_field_name": "source_columns",
        "output_template_field_description": "Required field, nullable array; [] is allowed. Logical input sources have entity_type=logical_entity, entity_schema_name, entity_name. Dimensional peer lookup sources use entity_type=dimensional_entity with the same schema/name fields. Do not invent physical Connection or table identities. Each source also has attribute_name. Use only eligible frozen Attributes. Null when not specified.",
        "output_template_field_data_type": "array",
        "output_template_field_array_item_type": "object",
        "output_template_field_is_required": true,
        "output_template_field_order": 3,
        "output_template_field_example": [
          {
            "entity_type": "logical_entity",
            "entity_schema_name": "silver",
            "entity_name": "Customer",
            "attribute_name": "CustomerName"
          }
        ]
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
            v_template -> 'fields',
            (v_template ->> 'output_template_modeled_entity_type')::VARCHAR
        );
    END LOOP;
END;
$global_mapping_output_template_seed$;
