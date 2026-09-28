"""Approved natural-key downstream inputs matching Entity-owned context projections."""

from typing import Any

from .mapping_input_schemas import mapping_input_schemas

CONTRACTS: dict[str, dict[str, dict[str, Any]]] = {
    "mapping": {
        "mapping_route": {
            "description": "logical_to_silver or dimensional_to_gold. "
            "Source and target layers are fixed by this "
            "route; do not invent intermediate targets.",
            "value_schema": mapping_input_schemas()["mapping_route"],
            "example": "logical_to_silver",
        },
        "operation": {
            "description": "build authors a new pair; extend regenerates selected, unlocked "
            "transformations in an existing pair. Omitted or null selected output clears "
            "saved documents; locked and unselected content is preserved. generate selects "
            "the effective operation per pair. Read readiness for the exact per-record action.",
            "value_schema": mapping_input_schemas()["operation"],
            "example": "build",
        },
        "target_metadata": {
            "description": "Selected modeled Entity, schema and "
            "Attributes. Preserve the schema-qualified "
            "Entity identity, Attribute names, types and "
            "nullability.",
            "value_schema": mapping_input_schemas()["target_metadata"],
            "example": {
                "attributes": [
                    {
                        "attribute_data_type": "BIGINT",
                        "attribute_definition": "Stable customer key.",
                        "attribute_name": "CustomerID",
                        "is_audit_column": False,
                        "is_locked": False,
                        "is_nullable": False,
                        "ordinal_position": 1,
                        "status": "active",
                    }
                ],
                "dependency_order": 0,
                "entity_definition": "A customer.",
                "entity_kind": "core",
                "entity_name": "Customer",
                "grain": "One row per customer.",
                "is_locked": False,
                "status": "active",
                "entity_type": "logical_entity",
                "entity_schema_name": "silver_crm",
            },
        },
        "source_evidence": {
            "description": "Eligible physical sources for Logical Mapping "
            "or Logical Entity/Attribute sources for "
            "Dimensional Mapping, including descriptions, "
            "roles and rationale. Use their complete "
            "natural keys; IDs are not business joins.",
            "value_schema": mapping_input_schemas()["source_evidence"],
            "example": [
                {
                    "is_locked": False,
                    "mapping_order": 1,
                    "object": {
                        "attributes": [
                            {
                                "attribute_data_type": "BIGINT",
                                "attribute_description": None,
                                "attribute_inferred_data_type": None,
                                "attribute_name": "customer_id",
                                "attribute_nullability": False,
                                "attribute_ordinal_position": 1,
                                "is_active": True,
                            }
                        ],
                        "batch_attribute_name": None,
                        "connection_code": "crm_bronze",
                        "connection_is_active": True,
                        "is_active": True,
                        "is_global_data_store": False,
                        "is_locked": False,
                        "object_description": None,
                        "object_name": "customer",
                        "object_schema": "bronze_crm",
                        "scope_is_active": True,
                        "scope_is_locked": False,
                        "system_code": "CRM",
                        "system_is_active": True,
                        "tenant_catalog": "northwind",
                        "tenant_code": "NWA",
                        "tenant_is_active": True,
                        "zone_code": "bronze",
                    },
                    "rationale": "Authoritative CRM feed.",
                    "role": "support",
                }
            ],
        },
        "existing_mapping": {
            "description": "Existing header, owning modeled "
            "Entity/Attributes and their transformation "
            "documents. Preserve locked/preserved "
            "records. A null document is unauthored, not "
            "an empty executable transformation.",
            "value_schema": mapping_input_schemas()["existing_mapping"],
            "example": [
                {
                    "attribute_mappings": [
                        {
                            "is_locked": False,
                            "status": "active",
                            "transformation_document": None,
                            "modeled_attribute_name": "CustomerID",
                        }
                    ],
                    "is_locked": False,
                    "modeled_entity": {
                        "attributes": [
                            {
                                "attribute_data_type": "BIGINT",
                                "attribute_definition": "Stable customer key.",
                                "attribute_name": "CustomerID",
                                "is_audit_column": False,
                                "is_locked": False,
                                "is_nullable": False,
                                "ordinal_position": 1,
                                "status": "active",
                            }
                        ],
                        "dependency_order": 0,
                        "entity_definition": "A customer.",
                        "entity_kind": "core",
                        "entity_name": "Customer",
                        "grain": "One row per customer.",
                        "is_locked": False,
                        "status": "active",
                        "entity_type": "logical_entity",
                        "entity_schema_name": "silver_crm",
                    },
                    "object_dependency_order": 0,
                    "status": "active",
                    "transformation_document": None,
                }
            ],
        },
        "authoring_policy": {
            "description": "Model name, naming instructions and "
            "audit/technical templates, plus logical_entity_scd_type history guidance. "
            "For Logical targets type_1 overwrites current values; type_2 preserves versions. "
            "Null is unspecified. Do not infer keys or invent history Attributes. Apply only "
            "recorded policy to transformation content; "
            "use existing modeled Attributes.",
            "value_schema": mapping_input_schemas()["authoring_policy"],
            "example": {
                "audit_columns_template": None,
                "model_name": "Customer Model",
                "logical_entity_scd_type": "type_2",
                "naming_instructions": "Use PascalCase names.",
                "technical_columns_template": None,
            },
        },
        "readiness": {
            "description": "Backend-computed action for the Object and each "
            "modeled Attribute. author/extend are actionable; "
            "preserve means omit from authored output. blocked "
            "is not permission to force a mapping.",
            "value_schema": mapping_input_schemas()["readiness"],
            "example": {
                "headers": [
                    {
                        "action": "author",
                        "attribute_actions": [
                            {"action": "author", "modeled_attribute_name": "CustomerID"}
                        ],
                    }
                ],
                "issues": [],
                "operation": "build",
                "ready": True,
            },
        },
        "source_system": {
            "description": "Exact source System for this pair. Its "
            "name/description supplies context, never a SQL "
            "credential or connection string.",
            "value_schema": mapping_input_schemas()["source_system"],
            "example": {
                "is_active": True,
                "system_code": "CRM",
                "system_description": None,
                "system_name": "CRM",
            },
        },
        "object_output_template": {
            "description": "Selected Object transformation "
            "template by nominal code with "
            "description, typed ordered fields, "
            "required flags and examples; null "
            "means no selected template. Guidance "
            "does not change the fixed outer output "
            "schema.",
            "value_schema": mapping_input_schemas()["object_output_template"],
            "example": {
                "code": "mapping_object_default",
                "name": "Default Object Mapping",
                "description": "Describe physical inputs "
                "or modeled input/lookup "
                "sources and ordered Entity "
                "transformation steps.",
                "target_type": "mapping_object",
                "is_active": True,
                "fields": [
                    {
                        "name": "source_objects",
                        "description": "Nullable list "
                        "of source "
                        "Objects. Each "
                        "entry has "
                        "tenant_code, "
                        "system_code, "
                        "connection_code, "
                        "object_schema, "
                        "object_name, "
                        "alias, in that "
                        "order. The "
                        "field is "
                        "present and "
                        "may be JSON "
                        "null. Use only "
                        "for Logical "
                        "Mapping; set "
                        "null for "
                        "Dimensional "
                        "Mapping.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": True,
                        "order": 1,
                        "example": [
                            {
                                "tenant_code": "NWA",
                                "system_code": "GDS",
                                "connection_code": "lakehouse",
                                "object_schema": "bronze_crm",
                                "object_name": "customer",
                                "alias": "c",
                            }
                        ],
                    },
                    {
                        "name": "source_logical_entities",
                        "description": "Optional "
                        "nullable "
                        "Logical Entity "
                        "sources for "
                        "Dimensional "
                        "input or "
                        "Logical "
                        "foreign-key "
                        "lookups. Each "
                        "entry has "
                        "logical_entity_schema_name, "
                        "logical_entity_name, "
                        "alias. Use "
                        "only frozen "
                        "eligible "
                        "source "
                        "evidence.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": False,
                        "order": 2,
                        "example": [
                            {
                                "logical_entity_schema_name": "silver",
                                "logical_entity_name": "Customer",
                                "alias": "c",
                            }
                        ],
                    },
                    {
                        "name": "source_dimensional_entities",
                        "description": "Optional "
                        "nullable "
                        "Dimensional "
                        "Entity lookup "
                        "sources on the "
                        "Dimensional "
                        "route only. "
                        "Each entry has "
                        "dimensional_entity_schema_name, "
                        "dimensional_entity_name, "
                        "alias. Use "
                        "only frozen "
                        "eligible "
                        "same-Model "
                        "peer lookup "
                        "evidence.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": False,
                        "order": 3,
                        "example": [
                            {
                                "dimensional_entity_schema_name": "gold",
                                "dimensional_entity_name": "CustomerDimension",
                                "alias": "customer_dim",
                            }
                        ],
                    },
                    {
                        "name": "steps",
                        "description": "Nullable "
                        "ordered list "
                        "of Object "
                        "transformation "
                        "instructions: "
                        "Objects/tables "
                        "to join, join "
                        "types and "
                        "column "
                        "predicates, "
                        "filters and "
                        "any additional "
                        "processing. "
                        "The field is "
                        "present and "
                        "may be JSON "
                        "null.",
                        "data_type": "array",
                        "array_item_type": "string",
                        "is_required": True,
                        "order": 4,
                        "example": [
                            "Read customer rows from c.",
                            "Keep rows where c.is_active = true.",
                        ],
                    },
                ],
            },
        },
        "attribute_output_template": {
            "description": "Selected Attribute transformation "
            "template by nominal code with "
            "description, typed ordered fields, "
            "required flags and examples; null "
            "means no selected template.",
            "value_schema": mapping_input_schemas()["attribute_output_template"],
            "example": {
                "code": "mapping_attribute_default",
                "name": "Default Attribute Mapping",
                "description": "Describe physical "
                "inputs or modeled "
                "input/lookup sources "
                "and the target "
                "Attribute "
                "transformation.",
                "target_type": "mapping_attribute",
                "is_active": True,
                "fields": [
                    {
                        "name": "source_attributes",
                        "description": "Optional "
                        "nullable "
                        "list of "
                        "source "
                        "Attributes. "
                        "Each entry "
                        "has "
                        "tenant_code, "
                        "system_code, "
                        "connection_code, "
                        "object_schema, "
                        "object_name, "
                        "attribute_name, "
                        "in that "
                        "order. "
                        "Omission or "
                        "JSON null "
                        "is "
                        "permitted. "
                        "Use only "
                        "for Logical "
                        "Mapping; "
                        "leave null "
                        "or absent "
                        "for "
                        "Dimensional "
                        "Mapping.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": False,
                        "order": 1,
                        "example": [
                            {
                                "tenant_code": "NWA",
                                "system_code": "GDS",
                                "connection_code": "lakehouse",
                                "object_schema": "bronze_crm",
                                "object_name": "customer",
                                "attribute_name": "customer_name",
                            }
                        ],
                    },
                    {
                        "name": "source_logical_attributes",
                        "description": "Optional "
                        "nullable "
                        "Logical "
                        "Attribute "
                        "sources for "
                        "Dimensional "
                        "input or "
                        "Logical "
                        "foreign-key "
                        "lookups. "
                        "Each entry "
                        "has "
                        "logical_entity_schema_name, "
                        "logical_entity_name, "
                        "logical_attribute_name. "
                        "Use only "
                        "frozen "
                        "eligible "
                        "source "
                        "evidence.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": False,
                        "order": 2,
                        "example": [
                            {
                                "logical_entity_schema_name": "silver",
                                "logical_entity_name": "Customer",
                                "logical_attribute_name": "CustomerName",
                            }
                        ],
                    },
                    {
                        "name": "source_dimensional_attributes",
                        "description": "Optional "
                        "nullable "
                        "Dimensional "
                        "Attribute "
                        "lookup "
                        "sources on "
                        "the "
                        "Dimensional "
                        "route only. "
                        "Each entry "
                        "has "
                        "dimensional_entity_schema_name, "
                        "dimensional_entity_name, "
                        "dimensional_attribute_name. "
                        "Use only "
                        "frozen "
                        "eligible "
                        "same-Model "
                        "peer lookup "
                        "evidence.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": False,
                        "order": 3,
                        "example": [
                            {
                                "dimensional_entity_schema_name": "gold",
                                "dimensional_entity_name": "CustomerDimension",
                                "dimensional_attribute_name": "CustomerKey",
                            }
                        ],
                    },
                    {
                        "name": "transformation",
                        "description": "Required "
                        "SQL "
                        "expression "
                        "using "
                        "available "
                        "Object "
                        "aliases, or "
                        "precise "
                        "implementable "
                        "generation "
                        "rule. "
                        "Include any "
                        "necessary "
                        "cast, "
                        "null/default, "
                        "aggregation "
                        "or "
                        "self-join "
                        "source-role "
                        "behavior.",
                        "data_type": "string",
                        "array_item_type": None,
                        "is_required": True,
                        "order": 4,
                        "example": "TRIM(c.customer_name)",
                    },
                ],
            },
        },
        "mapping_support": {
            "description": "Saved evidence scoped to this target and "
            "eligible sources: attribute_lineage links "
            "modeled names to physical source Attributes "
            "or assertion keys, with rationale and key "
            "roles; modeled_relationships describe "
            "conceptual join intent, not physical join "
            "proof; source_relationships carry Analysis "
            "confidence and measured validation when "
            "available; profiles are saved aggregate "
            "counts, percentages and lengths, not live "
            "rows or guaranteed current observations; "
            "assertions contain active Model/System "
            "context automatically without requiring "
            "Entity links or matching legacy layer flags. "
            "Evaluate relevance to this Entity; assertions "
            "are not proof of available sources. Keys "
            "identify provenance; free-text type and "
            "statement distinguish intent from facts. "
            "details may include notes, formula, grain, "
            "dimensions, date_basis, exclusions, history "
            "and acceptance_criteria when supplied. "
            "Missing details are unspecified. Empty lists "
            "mean no saved evidence, never permission to "
            "invent rules.",
            "value_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "attribute_lineage": {"type": "array", "items": {"type": "object"}},
                    "modeled_relationships": {"type": "array", "items": {"type": "object"}},
                    "source_relationships": {"type": "array", "items": {"type": "object"}},
                    "profiles": {"type": "array", "items": {"type": "object"}},
                    "assertions": {"type": "array", "items": {"type": "object"}},
                },
            },
            "example": {
                "attribute_lineage": [],
                "modeled_relationships": [],
                "source_relationships": [],
                "profiles": [],
                "assertions": [],
            },
        },
    },
    "code_generation": {
        "target_metadata": {
            "description": "Owning Entity schema, name and "
            "modeled columns with Tenant catalog "
            "for generated SQL.",
            "value_schema": {
                "$defs": {
                    "SqlPhysicalAttribute": {
                        "additionalProperties": False,
                        "properties": {
                            "attribute_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Attribute Name",
                                "type": "string",
                            },
                            "attribute_data_type": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Attribute Data Type",
                                "type": "string",
                            },
                            "attribute_inferred_data_type": {
                                "anyOf": [
                                    {"maxLength": 100, "minLength": 1, "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Attribute Inferred Data Type",
                            },
                            "attribute_nullability": {
                                "title": "Attribute Nullability",
                                "type": "boolean",
                            },
                            "attribute_ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Attribute Ordinal Position",
                                "type": "integer",
                            },
                            "attribute_description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Attribute Description",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "fc_attribute_name": {"type": ["string", "null"]},
                            "attribute_custom_code": {"type": ["string", "null"]},
                            "population": {"enum": ["database", "framework", "mapping"]},
                            "is_surrogate_key": {"type": "boolean"},
                            "is_natural_key": {"type": "boolean"},
                            "is_meta_data": {"type": "boolean"},
                            "is_masking_required": {"type": "boolean"},
                            "logical_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "attribute_name",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                            "attribute_nullability",
                            "attribute_ordinal_position",
                            "is_active",
                            "is_locked",
                        ],
                        "title": "SqlPhysicalAttribute",
                        "type": "object",
                    }
                },
                "additionalProperties": False,
                "properties": {
                    "tenant_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "title": "Tenant Code",
                        "type": "string",
                    },
                    "tenant_catalog": {
                        "maxLength": 255,
                        "minLength": 1,
                        "title": "Tenant Catalog",
                        "type": "string",
                    },
                    "system_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "title": "System Code",
                        "type": "string",
                    },
                    "connection_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "title": "Connection Code",
                        "type": "string",
                    },
                    "object_schema": {
                        "maxLength": 400,
                        "minLength": 1,
                        "title": "Object Schema",
                        "type": "string",
                    },
                    "object_name": {
                        "maxLength": 400,
                        "minLength": 1,
                        "title": "Object Name",
                        "type": "string",
                    },
                    "object_description": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "default": None,
                        "title": "Object Description",
                    },
                    "zone_code": {
                        "enum": ["source", "bronze", "silver", "gold"],
                        "title": "Zone Code",
                        "type": "string",
                    },
                    "attributes": {
                        "items": {"$ref": "#/$defs/SqlPhysicalAttribute"},
                        "title": "Attributes",
                        "type": "array",
                    },
                    "source_tenant_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "title": "Source Tenant Code",
                        "type": "string",
                    },
                    "source_tenant_name": {
                        "maxLength": 200,
                        "minLength": 1,
                        "title": "Source Tenant Name",
                        "type": "string",
                    },
                    "tenant_name": {
                        "maxLength": 200,
                        "minLength": 1,
                        "title": "Tenant Name",
                        "type": "string",
                    },
                    "system_name": {
                        "maxLength": 200,
                        "minLength": 1,
                        "title": "System Name",
                        "type": "string",
                    },
                    "batch_attribute_name": {"type": ["string", "null"]},
                    "audit_columns_template": {"type": ["object", "null"]},
                    "technical_columns_template": {"type": ["object", "null"]},
                    "modeled_entity_type": {"enum": ["logical_entity", "dimensional_entity"]},
                    "modeled_entity_schema_name": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 400,
                    },
                    "modeled_entity_name": {"type": "string", "minLength": 1, "maxLength": 400},
                    "is_locked": {"type": "boolean"},
                },
                "required": [
                    "tenant_code",
                    "tenant_catalog",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "zone_code",
                    "attributes",
                    "source_tenant_code",
                    "source_tenant_name",
                    "tenant_name",
                    "system_name",
                    "modeled_entity_type",
                    "modeled_entity_schema_name",
                    "modeled_entity_name",
                ],
                "title": "SqlTargetMetadata",
                "type": "object",
            },
            "example": {
                "tenant_code": "NWA",
                "tenant_catalog": "northwind",
                "system_code": "GDS",
                "connection_code": "lakehouse",
                "object_schema": "silver_crm",
                "object_name": "Customer",
                "object_description": None,
                "zone_code": "silver",
                "source_tenant_code": "NWA",
                "source_tenant_name": "Northwind",
                "tenant_name": "Shared warehouse",
                "system_name": "Warehouse",
                "attributes": [
                    {
                        "attribute_data_type": "BIGINT",
                        "attribute_description": None,
                        "attribute_inferred_data_type": None,
                        "attribute_name": "CustomerID",
                        "attribute_nullability": False,
                        "attribute_ordinal_position": 1,
                        "is_active": True,
                        "is_locked": False,
                    }
                ],
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver_crm",
                "modeled_entity_name": "Customer",
            },
        },
        "source_metadata": {
            "description": "Physical input coordinates and "
            "schema-qualified modeled input or "
            "peer lookup coordinates from the "
            "Model Tenant GDS placement, with "
            "contributing System.",
            "value_schema": {
                "$defs": {
                    "SqlPhysicalAttribute": {
                        "additionalProperties": False,
                        "properties": {
                            "attribute_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Attribute Name",
                                "type": "string",
                            },
                            "attribute_data_type": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Attribute Data Type",
                                "type": "string",
                            },
                            "attribute_inferred_data_type": {
                                "anyOf": [
                                    {"maxLength": 100, "minLength": 1, "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Attribute Inferred Data Type",
                            },
                            "attribute_nullability": {
                                "title": "Attribute Nullability",
                                "type": "boolean",
                            },
                            "attribute_ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Attribute Ordinal Position",
                                "type": "integer",
                            },
                            "attribute_description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Attribute Description",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "fc_attribute_name": {"type": ["string", "null"]},
                            "attribute_custom_code": {"type": ["string", "null"]},
                            "population": {"enum": ["database", "framework", "mapping"]},
                            "is_surrogate_key": {"type": "boolean"},
                            "is_natural_key": {"type": "boolean"},
                            "is_meta_data": {"type": "boolean"},
                            "is_masking_required": {"type": "boolean"},
                            "logical_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "attribute_name",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                            "attribute_nullability",
                            "attribute_ordinal_position",
                            "is_active",
                            "is_locked",
                        ],
                        "title": "SqlPhysicalAttribute",
                        "type": "object",
                    },
                    "SqlPhysicalSource": {
                        "additionalProperties": False,
                        "properties": {
                            "role": {"title": "Role", "type": "string"},
                            "rationale": {"title": "Rationale", "type": "string"},
                            "mapping_order": {
                                "anyOf": [
                                    {"exclusiveMinimum": 0, "type": "integer"},
                                    {"type": "null"},
                                ],
                                "title": "Mapping Order",
                            },
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "object": {"$ref": "#/$defs/SqlSourceObject"},
                            "source_system_code": {"type": "string", "minLength": 1},
                        },
                        "required": [
                            "role",
                            "rationale",
                            "mapping_order",
                            "is_locked",
                            "object",
                            "source_system_code",
                        ],
                        "title": "SqlPhysicalSource",
                        "type": "object",
                    },
                    "SqlSourceObject": {
                        "additionalProperties": False,
                        "properties": {
                            "tenant_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Tenant Code",
                                "type": "string",
                            },
                            "tenant_catalog": {
                                "maxLength": 255,
                                "minLength": 1,
                                "title": "Tenant Catalog",
                                "type": "string",
                            },
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "System Code",
                                "type": "string",
                            },
                            "connection_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Connection Code",
                                "type": "string",
                            },
                            "object_schema": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Object Schema",
                                "type": "string",
                            },
                            "object_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Object Name",
                                "type": "string",
                            },
                            "object_description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Object Description",
                            },
                            "zone_code": {
                                "enum": ["source", "bronze", "silver", "gold"],
                                "title": "Zone Code",
                                "type": "string",
                            },
                            "attributes": {
                                "items": {"$ref": "#/$defs/SqlPhysicalAttribute"},
                                "title": "Attributes",
                                "type": "array",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "scope_is_active": {"title": "Scope Is Active", "type": "boolean"},
                            "scope_is_locked": {"title": "Scope Is Locked", "type": "boolean"},
                            "fc_object_schema": {"type": ["string", "null"]},
                            "fc_object_name": {"type": ["string", "null"]},
                            "foreign_catalog": {"type": ["string", "null"]},
                            "batch_attribute_name": {"type": ["string", "null"]},
                            "modeled_entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"]
                            },
                            "modeled_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "modeled_entity_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "logical_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "logical_entity_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_entity_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "tenant_code",
                            "tenant_catalog",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                            "zone_code",
                            "attributes",
                            "is_active",
                            "is_locked",
                            "scope_is_active",
                            "scope_is_locked",
                        ],
                        "title": "SqlSourceObject",
                        "type": "object",
                    },
                },
                "items": {"$ref": "#/$defs/SqlPhysicalSource"},
                "type": "array",
            },
            "example": [
                {
                    "role": "primary",
                    "rationale": "Recorded customer source.",
                    "mapping_order": 1,
                    "is_locked": False,
                    "object": {
                        "tenant_code": "NWA",
                        "tenant_catalog": "northwind",
                        "system_code": "CRM",
                        "connection_code": "crm_bronze",
                        "object_schema": "bronze_crm",
                        "object_name": "customer",
                        "object_description": None,
                        "zone_code": "bronze",
                        "is_active": True,
                        "is_locked": False,
                        "scope_is_active": True,
                        "scope_is_locked": False,
                        "attributes": [
                            {
                                "attribute_data_type": "BIGINT",
                                "attribute_description": None,
                                "attribute_inferred_data_type": None,
                                "attribute_name": "customer_id",
                                "attribute_nullability": False,
                                "attribute_ordinal_position": 1,
                                "is_active": True,
                                "is_locked": False,
                            }
                        ],
                    },
                    "source_system_code": "CRM",
                }
            ],
        },
        "source_systems": {
            "description": "Frozen contributing Source System "
            "codes/names sorted by System code. Codes "
            "belong to the one Source Tenant of "
            "this target; assign each exactly once "
            "across transformation artifacts.",
            "value_schema": {
                "$defs": {
                    "SqlSourceSystem": {
                        "additionalProperties": False,
                        "properties": {
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "System Code",
                                "type": "string",
                            },
                            "system_name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "title": "System Name",
                                "type": "string",
                            },
                            "source_system_value": {"type": "integer", "minimum": 1},
                        },
                        "required": ["system_code", "system_name"],
                        "title": "SqlSourceSystem",
                        "type": "object",
                    }
                },
                "items": {"$ref": "#/$defs/SqlSourceSystem"},
                "type": "array",
            },
            "example": [{"system_code": "CRM", "system_name": "CRM"}],
        },
        "object_transformations": {
            "description": "Applied Object transformation "
            "documents with "
            "source_system_code, dependency "
            "order and exact modeled Entity "
            "identity, definition, "
            "classification and grain. "
            "entity.assertions contains "
            "active Model/System assertions "
            "without requiring Entity "
            "links: assess relevance; keys "
            "identify provenance, text "
            "states context, details may "
            "include notes, formula, grain, "
            "dimensions, date_basis, "
            "exclusions, history and "
            "acceptance_criteria. Use these "
            "to interpret approved "
            "transformations and report "
            "conflicts; never silently "
            "replace approved Mapping "
            "rules.",
            "value_schema": {
                "$defs": {
                    "JsonValue": {},
                    "SqlMappedEntity": {
                        "additionalProperties": False,
                        "properties": {
                            "entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"],
                                "title": "Entity Type",
                                "type": "string",
                            },
                            "entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "title": "Entity Name",
                                "type": "string",
                            },
                            "assertions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "modeling_assertion_record_key": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_document_name": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_record_type": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_text": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_details": {"type": "object"},
                                        "modeling_assertion_source_location": {
                                            "type": ["object", "null"]
                                        },
                                        "modeling_assertion_confidence": {
                                            "enum": ["low", "medium", "high", None]
                                        },
                                    },
                                    "required": [
                                        "modeling_assertion_record_key",
                                        "modeling_assertion_document_name",
                                        "modeling_assertion_record_type",
                                        "modeling_assertion_text",
                                        "modeling_assertion_details",
                                        "modeling_assertion_source_location",
                                        "modeling_assertion_confidence",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                            "definition": {"title": "Definition", "type": "string"},
                            "classification": {"title": "Classification", "type": "string"},
                            "grain": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "title": "Grain",
                            },
                            "entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "entity_type",
                            "entity_name",
                            "definition",
                            "classification",
                            "grain",
                            "entity_schema_name",
                        ],
                        "title": "SqlMappedEntity",
                        "type": "object",
                    },
                    "SqlObjectTransformation": {
                        "additionalProperties": False,
                        "properties": {
                            "object_dependency_order": {
                                "minimum": 0,
                                "title": "Object Dependency Order",
                                "type": "integer",
                            },
                            "entity": {"$ref": "#/$defs/SqlMappedEntity"},
                            "transformation": {
                                "additionalProperties": {"$ref": "#/$defs/JsonValue"},
                                "title": "Transformation",
                                "type": "object",
                            },
                            "source_system_code": {"type": "string", "minLength": 1},
                        },
                        "required": [
                            "object_dependency_order",
                            "entity",
                            "transformation",
                            "source_system_code",
                        ],
                        "title": "SqlObjectTransformation",
                        "type": "object",
                    },
                },
                "items": {"$ref": "#/$defs/SqlObjectTransformation"},
                "type": "array",
            },
            "example": [
                {
                    "object_dependency_order": 10,
                    "entity": {
                        "entity_type": "logical_entity",
                        "entity_name": "Customer",
                        "definition": "Customer identity.",
                        "classification": "entity",
                        "grain": None,
                        "entity_schema_name": "silver",
                    },
                    "transformation": {
                        "steps": [{"name": "customers", "source": "customer_source"}]
                    },
                    "source_system_code": "CRM",
                }
            ],
        },
        "attribute_transformations": {
            "description": "Applied Attribute "
            "transformation documents "
            "with source_system_code, "
            "modeled Entity type/name, "
            "physical "
            "target_attribute_name and "
            "target ordinal. Identity "
            "links are resolved from "
            "modeled Entity identities; "
            "no guessed name matching.",
            "value_schema": {
                "$defs": {
                    "JsonValue": {},
                    "SqlAttributeTransformation": {
                        "additionalProperties": False,
                        "properties": {
                            "target_attribute_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Target Attribute Name",
                                "type": "string",
                            },
                            "target_attribute_ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Target Attribute Ordinal Position",
                                "type": "integer",
                            },
                            "transformation": {
                                "additionalProperties": {"$ref": "#/$defs/JsonValue"},
                                "title": "Transformation",
                                "type": "object",
                            },
                            "source_system_code": {"type": "string", "minLength": 1},
                            "modeled_entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"]
                            },
                            "modeled_entity_name": {"type": "string", "minLength": 1},
                            "modeled_attribute_name": {"type": ["string", "null"]},
                            "modeled_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "target_attribute_name",
                            "target_attribute_ordinal_position",
                            "transformation",
                            "source_system_code",
                            "modeled_entity_type",
                            "modeled_entity_name",
                            "modeled_entity_schema_name",
                        ],
                        "title": "SqlAttributeTransformation",
                        "type": "object",
                    },
                },
                "items": {"$ref": "#/$defs/SqlAttributeTransformation"},
                "type": "array",
            },
            "example": [
                {
                    "target_attribute_name": "CustomerID",
                    "target_attribute_ordinal_position": 1,
                    "transformation": {"expression": "CAST(customer_id AS BIGINT)"},
                    "source_system_code": "CRM",
                    "modeled_entity_type": "logical_entity",
                    "modeled_entity_name": "Customer",
                    "modeled_entity_schema_name": "silver",
                }
            ],
        },
        "target_ref": {
            "description": "Frozen opaque output-control handle; copy "
            "unchanged into artifacts. It is not a "
            "database ID and never identifies a SQL "
            "relation.",
            "value_schema": {"pattern": "^target_[1-9][0-9]*$", "type": "string"},
            "example": "target_1",
        },
        "sql_generation_guide": {
            "description": "Exact content of the selected "
            "frozen published SQL Generation "
            "Guide. Apply its target dialect "
            "and generation conventions.",
            "value_schema": {"type": "string", "minLength": 1},
            "example": "Generate Databricks SQL using exact "
            "applied transformations and "
            "qualified physical names.",
        },
    },
    "validation": {
        "system_ref": {
            "description": "Frozen opaque output-control handle for this "
            "selected System. Copy unchanged; it is not a "
            "database ID.",
            "value_schema": {"pattern": "^system_[1-9][0-9]*$", "type": "string"},
            "example": "system_1",
        },
        "system_scope": {
            "description": "Owning Source Tenant code and selected System "
            "code. Author only this System's complete "
            "desired Validation ledger.",
            "value_schema": {
                "additionalProperties": False,
                "properties": {
                    "tenant_code": {"title": "Tenant Code", "type": "string"},
                    "system_code": {"title": "System Code", "type": "string"},
                },
                "required": ["tenant_code", "system_code"],
                "title": "ValidationSystemScope",
                "type": "object",
            },
            "example": {"tenant_code": "NWA", "system_code": "CRM"},
        },
        "mapping_evidence": {
            "description": "Relevant applied modeled target "
            "identities with natural-key Code-style "
            "target/source metadata and exact applied "
            "Object/Attribute transformations. Context "
            "is design evidence, not measured "
            "outcomes.",
            "value_schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "modeled_entity_type": {"enum": ["logical_entity", "dimensional_entity"]},
                        "modeled_entity_name": {"type": "string", "minLength": 1},
                        "context": {
                            "type": "object",
                            "properties": {
                                "target_metadata": {
                                    "additionalProperties": False,
                                    "properties": {
                                        "tenant_code": {
                                            "maxLength": 100,
                                            "minLength": 1,
                                            "title": "Tenant Code",
                                            "type": "string",
                                        },
                                        "tenant_catalog": {
                                            "maxLength": 255,
                                            "minLength": 1,
                                            "title": "Tenant Catalog",
                                            "type": "string",
                                        },
                                        "system_code": {
                                            "maxLength": 100,
                                            "minLength": 1,
                                            "title": "System Code",
                                            "type": "string",
                                        },
                                        "connection_code": {
                                            "maxLength": 100,
                                            "minLength": 1,
                                            "title": "Connection Code",
                                            "type": "string",
                                        },
                                        "object_schema": {
                                            "maxLength": 400,
                                            "minLength": 1,
                                            "title": "Object Schema",
                                            "type": "string",
                                        },
                                        "object_name": {
                                            "maxLength": 400,
                                            "minLength": 1,
                                            "title": "Object Name",
                                            "type": "string",
                                        },
                                        "object_description": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}],
                                            "default": None,
                                            "title": "Object Description",
                                        },
                                        "zone_code": {
                                            "enum": ["source", "bronze", "silver", "gold"],
                                            "title": "Zone Code",
                                            "type": "string",
                                        },
                                        "attributes": {
                                            "items": {
                                                "$ref": (
                                                    "#/$defs/target_metadata_SqlPhysicalAttribute"
                                                )
                                            },
                                            "title": "Attributes",
                                            "type": "array",
                                        },
                                        "source_tenant_code": {
                                            "maxLength": 100,
                                            "minLength": 1,
                                            "title": "Source Tenant Code",
                                            "type": "string",
                                        },
                                        "source_tenant_name": {
                                            "maxLength": 200,
                                            "minLength": 1,
                                            "title": "Source Tenant Name",
                                            "type": "string",
                                        },
                                        "tenant_name": {
                                            "maxLength": 200,
                                            "minLength": 1,
                                            "title": "Tenant Name",
                                            "type": "string",
                                        },
                                        "system_name": {
                                            "maxLength": 200,
                                            "minLength": 1,
                                            "title": "System Name",
                                            "type": "string",
                                        },
                                        "batch_attribute_name": {"type": ["string", "null"]},
                                        "audit_columns_template": {"type": ["object", "null"]},
                                        "technical_columns_template": {"type": ["object", "null"]},
                                        "modeled_entity_type": {
                                            "enum": ["logical_entity", "dimensional_entity"]
                                        },
                                        "modeled_entity_schema_name": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 400,
                                        },
                                        "modeled_entity_name": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 400,
                                        },
                                        "is_locked": {"type": "boolean"},
                                    },
                                    "required": [
                                        "tenant_code",
                                        "tenant_catalog",
                                        "system_code",
                                        "connection_code",
                                        "object_schema",
                                        "object_name",
                                        "zone_code",
                                        "attributes",
                                        "source_tenant_code",
                                        "source_tenant_name",
                                        "tenant_name",
                                        "system_name",
                                        "modeled_entity_type",
                                        "modeled_entity_schema_name",
                                        "modeled_entity_name",
                                    ],
                                    "title": "SqlTargetMetadata",
                                    "type": "object",
                                },
                                "source_metadata": {
                                    "items": {"$ref": "#/$defs/source_metadata_SqlPhysicalSource"},
                                    "type": "array",
                                },
                                "source_systems": {
                                    "items": {"$ref": "#/$defs/source_systems_SqlSourceSystem"},
                                    "type": "array",
                                },
                                "object_transformations": {
                                    "items": {
                                        "$ref": (
                                            "#/$defs/object_transformations_SqlObjectTransformation"
                                        )
                                    },
                                    "type": "array",
                                },
                                "attribute_transformations": {
                                    "items": {
                                        "$ref": (
                                            "#/$defs/"
                                            "attribute_transformations_SqlAttributeTransformation"
                                        )
                                    },
                                    "type": "array",
                                },
                            },
                            "required": [
                                "target_metadata",
                                "source_metadata",
                                "source_systems",
                                "object_transformations",
                                "attribute_transformations",
                            ],
                            "additionalProperties": False,
                        },
                        "modeled_entity_schema_name": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 400,
                        },
                    },
                    "required": [
                        "modeled_entity_type",
                        "modeled_entity_name",
                        "context",
                        "modeled_entity_schema_name",
                    ],
                    "additionalProperties": False,
                },
                "$defs": {
                    "target_metadata_SqlPhysicalAttribute": {
                        "additionalProperties": False,
                        "properties": {
                            "attribute_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Attribute Name",
                                "type": "string",
                            },
                            "attribute_data_type": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Attribute Data Type",
                                "type": "string",
                            },
                            "attribute_inferred_data_type": {
                                "anyOf": [
                                    {"maxLength": 100, "minLength": 1, "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Attribute Inferred Data Type",
                            },
                            "attribute_nullability": {
                                "title": "Attribute Nullability",
                                "type": "boolean",
                            },
                            "attribute_ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Attribute Ordinal Position",
                                "type": "integer",
                            },
                            "attribute_description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Attribute Description",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "fc_attribute_name": {"type": ["string", "null"]},
                            "attribute_custom_code": {"type": ["string", "null"]},
                            "population": {"enum": ["database", "framework", "mapping"]},
                            "is_surrogate_key": {"type": "boolean"},
                            "is_natural_key": {"type": "boolean"},
                            "is_meta_data": {"type": "boolean"},
                            "is_masking_required": {"type": "boolean"},
                            "logical_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "attribute_name",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                            "attribute_nullability",
                            "attribute_ordinal_position",
                            "is_active",
                            "is_locked",
                        ],
                        "title": "SqlPhysicalAttribute",
                        "type": "object",
                    },
                    "source_metadata_SqlPhysicalAttribute": {
                        "additionalProperties": False,
                        "properties": {
                            "attribute_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Attribute Name",
                                "type": "string",
                            },
                            "attribute_data_type": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Attribute Data Type",
                                "type": "string",
                            },
                            "attribute_inferred_data_type": {
                                "anyOf": [
                                    {"maxLength": 100, "minLength": 1, "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Attribute Inferred Data Type",
                            },
                            "attribute_nullability": {
                                "title": "Attribute Nullability",
                                "type": "boolean",
                            },
                            "attribute_ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Attribute Ordinal Position",
                                "type": "integer",
                            },
                            "attribute_description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Attribute Description",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "fc_attribute_name": {"type": ["string", "null"]},
                            "attribute_custom_code": {"type": ["string", "null"]},
                            "population": {"enum": ["database", "framework", "mapping"]},
                            "is_surrogate_key": {"type": "boolean"},
                            "is_natural_key": {"type": "boolean"},
                            "is_meta_data": {"type": "boolean"},
                            "is_masking_required": {"type": "boolean"},
                            "logical_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_attribute_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "attribute_name",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                            "attribute_nullability",
                            "attribute_ordinal_position",
                            "is_active",
                            "is_locked",
                        ],
                        "title": "SqlPhysicalAttribute",
                        "type": "object",
                    },
                    "source_metadata_SqlPhysicalSource": {
                        "additionalProperties": False,
                        "properties": {
                            "role": {"title": "Role", "type": "string"},
                            "rationale": {"title": "Rationale", "type": "string"},
                            "mapping_order": {
                                "anyOf": [
                                    {"exclusiveMinimum": 0, "type": "integer"},
                                    {"type": "null"},
                                ],
                                "title": "Mapping Order",
                            },
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "object": {"$ref": "#/$defs/source_metadata_SqlSourceObject"},
                            "source_system_code": {"type": "string", "minLength": 1},
                        },
                        "required": [
                            "role",
                            "rationale",
                            "mapping_order",
                            "is_locked",
                            "object",
                            "source_system_code",
                        ],
                        "title": "SqlPhysicalSource",
                        "type": "object",
                    },
                    "source_metadata_SqlSourceObject": {
                        "additionalProperties": False,
                        "properties": {
                            "tenant_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Tenant Code",
                                "type": "string",
                            },
                            "tenant_catalog": {
                                "maxLength": 255,
                                "minLength": 1,
                                "title": "Tenant Catalog",
                                "type": "string",
                            },
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "System Code",
                                "type": "string",
                            },
                            "connection_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Connection Code",
                                "type": "string",
                            },
                            "object_schema": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Object Schema",
                                "type": "string",
                            },
                            "object_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "title": "Object Name",
                                "type": "string",
                            },
                            "object_description": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Object Description",
                            },
                            "zone_code": {
                                "enum": ["source", "bronze", "silver", "gold"],
                                "title": "Zone Code",
                                "type": "string",
                            },
                            "attributes": {
                                "items": {"$ref": "#/$defs/source_metadata_SqlPhysicalAttribute"},
                                "title": "Attributes",
                                "type": "array",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "scope_is_active": {"title": "Scope Is Active", "type": "boolean"},
                            "scope_is_locked": {"title": "Scope Is Locked", "type": "boolean"},
                            "fc_object_schema": {"type": ["string", "null"]},
                            "fc_object_name": {"type": ["string", "null"]},
                            "foreign_catalog": {"type": ["string", "null"]},
                            "batch_attribute_name": {"type": ["string", "null"]},
                            "modeled_entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"]
                            },
                            "modeled_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "modeled_entity_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "logical_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "logical_entity_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                            "dimensional_entity_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "tenant_code",
                            "tenant_catalog",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                            "zone_code",
                            "attributes",
                            "is_active",
                            "is_locked",
                            "scope_is_active",
                            "scope_is_locked",
                        ],
                        "title": "SqlSourceObject",
                        "type": "object",
                    },
                    "source_systems_SqlSourceSystem": {
                        "additionalProperties": False,
                        "properties": {
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "System Code",
                                "type": "string",
                            },
                            "system_name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "title": "System Name",
                                "type": "string",
                            },
                            "source_system_value": {"type": "integer", "minimum": 1},
                        },
                        "required": ["system_code", "system_name"],
                        "title": "SqlSourceSystem",
                        "type": "object",
                    },
                    "object_transformations_JsonValue": {},
                    "object_transformations_SqlMappedEntity": {
                        "additionalProperties": False,
                        "properties": {
                            "entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"],
                                "title": "Entity Type",
                                "type": "string",
                            },
                            "entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "title": "Entity Name",
                                "type": "string",
                            },
                            "assertions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "modeling_assertion_record_key": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_document_name": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_record_type": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_text": {
                                            "type": "string",
                                            "minLength": 1,
                                        },
                                        "modeling_assertion_details": {"type": "object"},
                                        "modeling_assertion_source_location": {
                                            "type": ["object", "null"]
                                        },
                                        "modeling_assertion_confidence": {
                                            "enum": ["low", "medium", "high", None]
                                        },
                                    },
                                    "required": [
                                        "modeling_assertion_record_key",
                                        "modeling_assertion_document_name",
                                        "modeling_assertion_record_type",
                                        "modeling_assertion_text",
                                        "modeling_assertion_details",
                                        "modeling_assertion_source_location",
                                        "modeling_assertion_confidence",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                            "definition": {"title": "Definition", "type": "string"},
                            "classification": {"title": "Classification", "type": "string"},
                            "grain": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "title": "Grain",
                            },
                            "entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "entity_type",
                            "entity_name",
                            "definition",
                            "classification",
                            "grain",
                            "entity_schema_name",
                        ],
                        "title": "SqlMappedEntity",
                        "type": "object",
                    },
                    "object_transformations_SqlObjectTransformation": {
                        "additionalProperties": False,
                        "properties": {
                            "object_dependency_order": {
                                "minimum": 0,
                                "title": "Object Dependency Order",
                                "type": "integer",
                            },
                            "entity": {"$ref": "#/$defs/object_transformations_SqlMappedEntity"},
                            "transformation": {
                                "additionalProperties": {
                                    "$ref": "#/$defs/object_transformations_JsonValue"
                                },
                                "title": "Transformation",
                                "type": "object",
                            },
                            "source_system_code": {"type": "string", "minLength": 1},
                        },
                        "required": [
                            "object_dependency_order",
                            "entity",
                            "transformation",
                            "source_system_code",
                        ],
                        "title": "SqlObjectTransformation",
                        "type": "object",
                    },
                    "attribute_transformations_JsonValue": {},
                    "attribute_transformations_SqlAttributeTransformation": {
                        "additionalProperties": False,
                        "properties": {
                            "target_attribute_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Target Attribute Name",
                                "type": "string",
                            },
                            "target_attribute_ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Target Attribute Ordinal Position",
                                "type": "integer",
                            },
                            "transformation": {
                                "additionalProperties": {
                                    "$ref": "#/$defs/attribute_transformations_JsonValue"
                                },
                                "title": "Transformation",
                                "type": "object",
                            },
                            "source_system_code": {"type": "string", "minLength": 1},
                            "modeled_entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"]
                            },
                            "modeled_entity_name": {"type": "string", "minLength": 1},
                            "modeled_attribute_name": {"type": ["string", "null"]},
                            "modeled_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "target_attribute_name",
                            "target_attribute_ordinal_position",
                            "transformation",
                            "source_system_code",
                            "modeled_entity_type",
                            "modeled_entity_name",
                            "modeled_entity_schema_name",
                        ],
                        "title": "SqlAttributeTransformation",
                        "type": "object",
                    },
                },
            },
            "example": [
                {
                    "modeled_entity_type": "logical_entity",
                    "modeled_entity_name": "Customer",
                    "context": {
                        "target_metadata": {
                            "tenant_code": "NWA",
                            "tenant_catalog": "northwind",
                            "system_code": "GDS",
                            "connection_code": "lakehouse",
                            "object_schema": "silver_crm",
                            "object_name": "Customer",
                            "object_description": None,
                            "zone_code": "silver",
                            "source_tenant_code": "NWA",
                            "source_tenant_name": "Northwind",
                            "tenant_name": "Shared warehouse",
                            "system_name": "Warehouse",
                            "attributes": [
                                {
                                    "attribute_data_type": "BIGINT",
                                    "attribute_description": None,
                                    "attribute_inferred_data_type": None,
                                    "attribute_name": "CustomerID",
                                    "attribute_nullability": False,
                                    "attribute_ordinal_position": 1,
                                    "is_active": True,
                                    "is_locked": False,
                                }
                            ],
                            "modeled_entity_type": "logical_entity",
                            "modeled_entity_schema_name": "silver_crm",
                            "modeled_entity_name": "Customer",
                        },
                        "source_metadata": [
                            {
                                "role": "primary",
                                "rationale": "Recorded customer source.",
                                "mapping_order": 1,
                                "is_locked": False,
                                "object": {
                                    "tenant_code": "NWA",
                                    "tenant_catalog": "northwind",
                                    "system_code": "CRM",
                                    "connection_code": "crm_bronze",
                                    "object_schema": "bronze_crm",
                                    "object_name": "customer",
                                    "object_description": None,
                                    "zone_code": "bronze",
                                    "is_active": True,
                                    "is_locked": False,
                                    "scope_is_active": True,
                                    "scope_is_locked": False,
                                    "attributes": [
                                        {
                                            "attribute_data_type": "BIGINT",
                                            "attribute_description": None,
                                            "attribute_inferred_data_type": None,
                                            "attribute_name": "customer_id",
                                            "attribute_nullability": False,
                                            "attribute_ordinal_position": 1,
                                            "is_active": True,
                                            "is_locked": False,
                                        }
                                    ],
                                },
                                "source_system_code": "CRM",
                            }
                        ],
                        "source_systems": [{"system_code": "CRM", "system_name": "CRM"}],
                        "object_transformations": [
                            {
                                "object_dependency_order": 10,
                                "entity": {
                                    "entity_type": "logical_entity",
                                    "entity_name": "Customer",
                                    "definition": "Customer identity.",
                                    "classification": "entity",
                                    "grain": None,
                                    "entity_schema_name": "silver",
                                },
                                "transformation": {
                                    "steps": [{"name": "customers", "source": "customer_source"}]
                                },
                                "source_system_code": "CRM",
                            }
                        ],
                        "attribute_transformations": [
                            {
                                "target_attribute_name": "CustomerID",
                                "target_attribute_ordinal_position": 1,
                                "transformation": {"expression": "CAST(customer_id AS BIGINT)"},
                                "source_system_code": "CRM",
                                "modeled_entity_type": "logical_entity",
                                "modeled_entity_name": "Customer",
                                "modeled_entity_schema_name": "silver",
                            }
                        ],
                    },
                    "modeled_entity_schema_name": "silver",
                }
            ],
        },
        "current_code": {
            "description": "Current saved Code artifacts and contributing "
            "Source System codes, with lifecycle/locks and "
            "generated content. Empty means unavailable; "
            "no execution success is implied.",
            "value_schema": {
                "$defs": {
                    "ValidationGeneratedCodeArtifact": {
                        "additionalProperties": False,
                        "properties": {
                            "modeled_entity_type": {
                                "enum": ["logical_entity", "dimensional_entity"],
                                "title": "Modeled Entity Type",
                                "type": "string",
                            },
                            "modeled_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Modeled Entity Name",
                                "type": "string",
                            },
                            "artifact_name": {
                                "maxLength": 400,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Artifact Name",
                                "type": "string",
                            },
                            "artifact_type": {
                                "enum": ["sql_file", "python_file", "python_notebook"],
                                "title": "Artifact Type",
                                "type": "string",
                            },
                            "generated_code_content": {
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Generated Code Content",
                                "type": "string",
                            },
                            "generated_code_status": {
                                "enum": ["active", "inactive", "deprecated"],
                                "title": "Generated Code Status",
                                "type": "string",
                            },
                            "generated_code_is_locked": {
                                "title": "Generated Code Is Locked",
                                "type": "boolean",
                            },
                            "source_system_codes": {
                                "items": {"type": "string"},
                                "maxItems": 1000,
                                "title": "Source System Codes",
                                "type": "array",
                            },
                            "modeled_entity_schema_name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 400,
                            },
                        },
                        "required": [
                            "modeled_entity_type",
                            "modeled_entity_name",
                            "artifact_name",
                            "artifact_type",
                            "generated_code_content",
                            "generated_code_status",
                            "generated_code_is_locked",
                            "source_system_codes",
                            "modeled_entity_schema_name",
                        ],
                        "title": "ValidationGeneratedCodeArtifact",
                        "type": "object",
                    }
                },
                "items": {"$ref": "#/$defs/ValidationGeneratedCodeArtifact"},
                "type": "array",
            },
            "example": [
                {
                    "modeled_entity_type": "logical_entity",
                    "modeled_entity_name": "Customer",
                    "artifact_name": "customer.sql",
                    "artifact_type": "sql_file",
                    "generated_code_content": "SELECT customer_id FROM warehouse.bronze.customer;",
                    "generated_code_status": "active",
                    "generated_code_is_locked": False,
                    "source_system_codes": ["CRM"],
                    "modeled_entity_schema_name": "silver",
                }
            ],
        },
        "applied_groups": {
            "description": "Existing Validation Group records, "
            "including lifecycle, locks and exact "
            "Tenant/System/Group natural identities.",
            "value_schema": {
                "$defs": {
                    "ValidationGroupRecord": {
                        "additionalProperties": False,
                        "properties": {
                            "tenant_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Tenant Code",
                                "type": "string",
                            },
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "System Code",
                                "type": "string",
                            },
                            "validation_group_name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Validation Group Name",
                                "type": "string",
                            },
                            "validation_group_description": {
                                "anyOf": [
                                    {"minLength": 1, "pattern": "\\S", "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Validation Group Description",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                        },
                        "required": [
                            "tenant_code",
                            "system_code",
                            "validation_group_name",
                            "validation_group_description",
                            "is_active",
                            "is_locked",
                        ],
                        "title": "ValidationGroupRecord",
                        "type": "object",
                    }
                },
                "items": {"$ref": "#/$defs/ValidationGroupRecord"},
                "type": "array",
            },
            "example": [
                {
                    "is_locked": False,
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "validation_group_name": "customer_keys",
                    "validation_group_description": "Recorded customer key constraints.",
                    "is_active": True,
                }
            ],
        },
        "applied_checks": {
            "description": "Existing Validation Check records, exact "
            "typed operator/operand definitions and SQL, "
            "lifecycle/locks and "
            "Tenant/System/Group/Check natural "
            "identities. These are definitions, not "
            "execution results.",
            "value_schema": {
                "$defs": {
                    "ValidationCheckRecord": {
                        "additionalProperties": False,
                        "description": "Validation "
                        "definition "
                        "with "
                        "a "
                        "scalar "
                        "result "
                        "except "
                        "for "
                        "execution-only "
                        "checks.",
                        "properties": {
                            "tenant_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Tenant Code",
                                "type": "string",
                            },
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "System Code",
                                "type": "string",
                            },
                            "validation_group_name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Validation Group Name",
                                "type": "string",
                            },
                            "validation_check_name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Validation Check Name",
                                "type": "string",
                            },
                            "validation_check_description": {
                                "anyOf": [
                                    {"minLength": 1, "pattern": "\\S", "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Validation Check Description",
                            },
                            "validation_category_code": {
                                "pattern": "^[a-z][a-z0-9_.-]{0,99}$",
                                "title": "Validation Category Code",
                                "type": "string",
                            },
                            "validation_severity": {
                                "enum": ["blocking", "warning", "informational"],
                                "title": "Validation Severity",
                                "type": "string",
                            },
                            "validation_query_sql": {
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Validation Query Sql",
                                "type": "string",
                            },
                            "validation_comparison_query_sql": {
                                "anyOf": [
                                    {"minLength": 1, "pattern": "\\S", "type": "string"},
                                    {"type": "null"},
                                ],
                                "title": "Validation Comparison Query Sql",
                            },
                            "validation_result_data_type": {
                                "anyOf": [
                                    {
                                        "enum": [
                                            "boolean",
                                            "integer",
                                            "decimal",
                                            "text",
                                            "date",
                                            "timestamp",
                                        ],
                                        "type": "string",
                                    },
                                    {"type": "null"},
                                ],
                                "title": "Validation Result Data Type",
                            },
                            "validation_comparison_operator": {
                                "enum": [
                                    "executes_successfully",
                                    "is_null",
                                    "is_not_null",
                                    "is_true",
                                    "is_false",
                                    "equal",
                                    "not_equal",
                                    "greater_than",
                                    "greater_than_or_equal",
                                    "less_than",
                                    "less_than_or_equal",
                                    "in",
                                    "not_in",
                                ],
                                "title": "Validation Comparison Operator",
                                "type": "string",
                            },
                            "validation_comparison_value_type": {
                                "enum": ["none", "literal", "literal_list", "query"],
                                "title": "Validation Comparison Value Type",
                                "type": "string",
                            },
                            "validation_comparison_value": {
                                "anyOf": [
                                    {"$ref": "#/$defs/ValidationLiteral"},
                                    {
                                        "items": {"$ref": "#/$defs/ValidationLiteral"},
                                        "type": "array",
                                    },
                                    {"type": "null"},
                                ],
                                "title": "Validation Comparison Value",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                        },
                        "required": [
                            "tenant_code",
                            "system_code",
                            "validation_group_name",
                            "validation_check_name",
                            "validation_check_description",
                            "validation_category_code",
                            "validation_severity",
                            "validation_query_sql",
                            "validation_comparison_query_sql",
                            "validation_result_data_type",
                            "validation_comparison_operator",
                            "validation_comparison_value_type",
                            "validation_comparison_value",
                            "is_active",
                            "is_locked",
                        ],
                        "title": "ValidationCheckRecord",
                        "type": "object",
                    },
                    "ValidationLiteral": {
                        "anyOf": [
                            {"type": "boolean"},
                            {"type": "integer"},
                            {"type": "number"},
                            {"type": "string"},
                        ]
                    },
                },
                "items": {"$ref": "#/$defs/ValidationCheckRecord"},
                "type": "array",
            },
            "example": [
                {
                    "is_locked": False,
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "validation_group_name": "customer_keys",
                    "validation_check_name": "customer_id_not_null",
                    "validation_check_description": None,
                    "validation_category_code": "technical.nullability",
                    "validation_severity": "blocking",
                    "validation_query_sql": "SELECT count(*) FROM "
                    "warehouse.silver.customer "
                    "WHERE customer_id IS "
                    "NULL",
                    "validation_comparison_query_sql": None,
                    "validation_result_data_type": "integer",
                    "validation_comparison_operator": "equal",
                    "validation_comparison_value_type": "literal",
                    "validation_comparison_value": 0,
                    "is_active": True,
                }
            ],
        },
    },
}
