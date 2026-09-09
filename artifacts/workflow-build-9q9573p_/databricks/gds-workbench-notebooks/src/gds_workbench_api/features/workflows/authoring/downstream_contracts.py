"""Natural-key downstream input schemas, projected from the existing DTOs."""

from typing import Any

CONTRACTS: dict[str, dict[str, dict[str, Any]]] = {
    "mapping": {
        "mapping_route": {
            "description": "Frozen logical_to_silver or dimensional_to_gold "
            "route; it fixes eligible source and target "
            "layers.",
            "value_schema": {
                "enum": ["logical_to_silver", "dimensional_to_gold"],
                "type": "string",
            },
            "example": "logical_to_silver",
        },
        "operation": {
            "description": "Frozen build or extend operation. Per-record "
            "readiness determines exactly which transformations "
            "are actionable.",
            "value_schema": {"enum": ["build", "extend"], "type": "string"},
            "example": "build",
        },
        "target_metadata": {
            "description": "Actual target Object natural key, physical "
            "catalog, description, layer, lifecycle/locks "
            "and ordered registered Attributes with type, "
            "inferred type, nullability and descriptions. No "
            "internal IDs.",
            "value_schema": {
                "$defs": {
                    "MappingPhysicalAttribute": {
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
                        },
                        "required": [
                            "attribute_name",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                            "attribute_nullability",
                            "attribute_ordinal_position",
                            "is_active",
                        ],
                        "title": "MappingPhysicalAttribute",
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
                    "tenant_is_active": {"title": "Tenant Is Active", "type": "boolean"},
                    "system_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "title": "System Code",
                        "type": "string",
                    },
                    "system_is_active": {"title": "System Is Active", "type": "boolean"},
                    "connection_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "title": "Connection Code",
                        "type": "string",
                    },
                    "connection_is_active": {"title": "Connection Is Active", "type": "boolean"},
                    "is_global_data_store": {"title": "Is Global Data Store", "type": "boolean"},
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
                    "batch_attribute_name": {
                        "anyOf": [{"maxLength": 400, "type": "string"}, {"type": "null"}],
                        "default": None,
                        "title": "Batch Attribute Name",
                    },
                    "zone_code": {
                        "enum": ["source", "bronze", "silver", "gold"],
                        "title": "Zone Code",
                        "type": "string",
                    },
                    "scope_is_locked": {"title": "Scope Is Locked", "type": "boolean"},
                    "scope_is_active": {"title": "Scope Is Active", "type": "boolean"},
                    "is_locked": {"title": "Is Locked", "type": "boolean"},
                    "is_active": {"title": "Is Active", "type": "boolean"},
                    "attributes": {
                        "items": {"$ref": "#/$defs/MappingPhysicalAttribute"},
                        "maxItems": 5000,
                        "title": "Attributes",
                        "type": "array",
                    },
                },
                "required": [
                    "tenant_code",
                    "tenant_catalog",
                    "tenant_is_active",
                    "system_code",
                    "system_is_active",
                    "connection_code",
                    "connection_is_active",
                    "is_global_data_store",
                    "object_schema",
                    "object_name",
                    "zone_code",
                    "scope_is_locked",
                    "scope_is_active",
                    "is_locked",
                    "is_active",
                    "attributes",
                ],
                "title": "MappingPhysicalObject",
                "type": "object",
            },
            "example": {
                "attributes": [
                    {
                        "attribute_data_type": "BIGINT",
                        "attribute_description": None,
                        "attribute_inferred_data_type": None,
                        "attribute_name": "CustomerID",
                        "attribute_nullability": False,
                        "attribute_ordinal_position": 1,
                        "is_active": True,
                    }
                ],
                "batch_attribute_name": None,
                "connection_code": "lakehouse",
                "connection_is_active": True,
                "is_active": True,
                "is_global_data_store": True,
                "is_locked": False,
                "object_description": None,
                "object_name": "Customer",
                "object_schema": "silver_crm",
                "scope_is_active": True,
                "scope_is_locked": False,
                "system_code": "GDS",
                "system_is_active": True,
                "tenant_catalog": "northwind",
                "tenant_code": "NWA",
                "tenant_is_active": True,
                "zone_code": "silver",
            },
        },
        "source_evidence": {
            "description": "Eligible source contributions, each with role, "
            "rationale, mapping_order, lock and nested "
            "actual physical Object/Attributes. Scoped to "
            "this frozen target/Source System pair.",
            "value_schema": {
                "$defs": {
                    "MappingPhysicalAttribute": {
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
                        },
                        "required": [
                            "attribute_name",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                            "attribute_nullability",
                            "attribute_ordinal_position",
                            "is_active",
                        ],
                        "title": "MappingPhysicalAttribute",
                        "type": "object",
                    },
                    "MappingPhysicalObject": {
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
                            "tenant_is_active": {"title": "Tenant Is Active", "type": "boolean"},
                            "system_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "System Code",
                                "type": "string",
                            },
                            "system_is_active": {"title": "System Is Active", "type": "boolean"},
                            "connection_code": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Connection Code",
                                "type": "string",
                            },
                            "connection_is_active": {
                                "title": "Connection Is Active",
                                "type": "boolean",
                            },
                            "is_global_data_store": {
                                "title": "Is Global Data Store",
                                "type": "boolean",
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
                            "batch_attribute_name": {
                                "anyOf": [{"maxLength": 400, "type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Batch Attribute Name",
                            },
                            "zone_code": {
                                "enum": ["source", "bronze", "silver", "gold"],
                                "title": "Zone Code",
                                "type": "string",
                            },
                            "scope_is_locked": {"title": "Scope Is Locked", "type": "boolean"},
                            "scope_is_active": {"title": "Scope Is Active", "type": "boolean"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "attributes": {
                                "items": {"$ref": "#/$defs/MappingPhysicalAttribute"},
                                "maxItems": 5000,
                                "title": "Attributes",
                                "type": "array",
                            },
                        },
                        "required": [
                            "tenant_code",
                            "tenant_catalog",
                            "tenant_is_active",
                            "system_code",
                            "system_is_active",
                            "connection_code",
                            "connection_is_active",
                            "is_global_data_store",
                            "object_schema",
                            "object_name",
                            "zone_code",
                            "scope_is_locked",
                            "scope_is_active",
                            "is_locked",
                            "is_active",
                            "attributes",
                        ],
                        "title": "MappingPhysicalObject",
                        "type": "object",
                    },
                    "MappingSource": {
                        "additionalProperties": False,
                        "properties": {
                            "role": {
                                "maxLength": 2000,
                                "minLength": 1,
                                "title": "Role",
                                "type": "string",
                            },
                            "rationale": {
                                "maxLength": 2000,
                                "minLength": 1,
                                "title": "Rationale",
                                "type": "string",
                            },
                            "mapping_order": {
                                "anyOf": [
                                    {"exclusiveMinimum": 0, "type": "integer"},
                                    {"type": "null"},
                                ],
                                "default": None,
                                "title": "Mapping Order",
                            },
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "object": {"$ref": "#/$defs/MappingPhysicalObject"},
                        },
                        "required": ["role", "rationale", "is_locked", "object"],
                        "title": "MappingSource",
                        "type": "object",
                    },
                },
                "items": {"$ref": "#/$defs/MappingSource"},
                "maxItems": 128,
                "type": "array",
            },
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
            "description": "Single existing target binding/header with "
            "modeled Entity/Attributes, natural "
            "Attribute-name bindings, Object/Attribute "
            "transformation documents, dependency order, "
            "statuses and locks. Null document means "
            "unauthored.",
            "value_schema": {
                "$defs": {
                    "ExistingMappingAttribute": {
                        "additionalProperties": False,
                        "properties": {
                            "transformation_document": {
                                "anyOf": [{"$ref": "#/$defs/JsonObject"}, {"type": "null"}],
                                "default": None,
                            },
                            "status": {"$ref": "#/$defs/LifecycleStatus", "default": "active"},
                            "is_locked": {
                                "default": False,
                                "title": "Is Locked",
                                "type": "boolean",
                            },
                            "modeled_attribute_name": {"type": "string", "minLength": 1},
                            "target_attribute_name": {"type": "string", "minLength": 1},
                        },
                        "required": ["modeled_attribute_name", "target_attribute_name"],
                        "title": "ExistingMappingAttribute",
                        "type": "object",
                    },
                    "ExistingMappingHeader": {
                        "additionalProperties": False,
                        "properties": {
                            "modeled_entity": {"$ref": "#/$defs/MappingModeledEntity"},
                            "object_dependency_order": {
                                "minimum": 0,
                                "title": "Object Dependency Order",
                                "type": "integer",
                            },
                            "transformation_document": {
                                "anyOf": [{"$ref": "#/$defs/JsonObject"}, {"type": "null"}],
                                "default": None,
                            },
                            "status": {"$ref": "#/$defs/LifecycleStatus", "default": "active"},
                            "is_locked": {
                                "default": False,
                                "title": "Is Locked",
                                "type": "boolean",
                            },
                            "attribute_mappings": {
                                "items": {"$ref": "#/$defs/ExistingMappingAttribute"},
                                "maxItems": 20000,
                                "title": "Attribute Mappings",
                                "type": "array",
                            },
                        },
                        "required": [
                            "modeled_entity",
                            "object_dependency_order",
                            "attribute_mappings",
                        ],
                        "title": "ExistingMappingHeader",
                        "type": "object",
                    },
                    "JsonObject": {
                        "additionalProperties": {"$ref": "#/$defs/JsonValue"},
                        "type": "object",
                    },
                    "JsonValue": {},
                    "LifecycleStatus": {
                        "enum": ["active", "inactive", "deprecated"],
                        "type": "string",
                    },
                    "MappingModeledAttribute": {
                        "additionalProperties": False,
                        "properties": {
                            "attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "title": "Attribute Name",
                                "type": "string",
                            },
                            "attribute_definition": {
                                "minLength": 1,
                                "title": "Attribute Definition",
                                "type": "string",
                            },
                            "attribute_data_type": {
                                "maxLength": 100,
                                "minLength": 1,
                                "title": "Attribute Data Type",
                                "type": "string",
                            },
                            "is_nullable": {"title": "Is Nullable", "type": "boolean"},
                            "ordinal_position": {
                                "exclusiveMinimum": 0,
                                "title": "Ordinal Position",
                                "type": "integer",
                            },
                            "is_audit_column": {"title": "Is Audit Column", "type": "boolean"},
                            "status": {"$ref": "#/$defs/LifecycleStatus"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                        },
                        "required": [
                            "attribute_name",
                            "attribute_definition",
                            "attribute_data_type",
                            "is_nullable",
                            "ordinal_position",
                            "is_audit_column",
                            "status",
                            "is_locked",
                        ],
                        "title": "MappingModeledAttribute",
                        "type": "object",
                    },
                    "MappingModeledEntity": {
                        "additionalProperties": False,
                        "properties": {
                            "entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "title": "Entity Name",
                                "type": "string",
                            },
                            "entity_definition": {
                                "minLength": 1,
                                "title": "Entity Definition",
                                "type": "string",
                            },
                            "entity_kind": {
                                "maxLength": 50,
                                "minLength": 1,
                                "title": "Entity Kind",
                                "type": "string",
                            },
                            "grain": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Grain",
                            },
                            "dependency_order": {
                                "minimum": 0,
                                "title": "Dependency Order",
                                "type": "integer",
                            },
                            "status": {"$ref": "#/$defs/LifecycleStatus"},
                            "is_locked": {"title": "Is Locked", "type": "boolean"},
                            "attributes": {
                                "items": {"$ref": "#/$defs/MappingModeledAttribute"},
                                "maxItems": 5000,
                                "title": "Attributes",
                                "type": "array",
                            },
                        },
                        "required": [
                            "entity_name",
                            "entity_definition",
                            "entity_kind",
                            "dependency_order",
                            "status",
                            "is_locked",
                            "attributes",
                        ],
                        "title": "MappingModeledEntity",
                        "type": "object",
                    },
                },
                "items": {"$ref": "#/$defs/ExistingMappingHeader"},
                "maxItems": 1,
                "minItems": 1,
                "type": "array",
            },
            "example": [
                {
                    "attribute_mappings": [
                        {
                            "is_locked": False,
                            "status": "active",
                            "transformation_document": None,
                            "modeled_attribute_name": "CustomerID",
                            "target_attribute_name": "CustomerID",
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
                    },
                    "object_dependency_order": 0,
                    "status": "active",
                    "transformation_document": None,
                }
            ],
        },
        "authoring_policy": {
            "description": "Model name, effective naming instructions and "
            "configured audit/technical column templates; "
            "do not invent physical columns.",
            "value_schema": {
                "$defs": {
                    "JsonObject": {
                        "additionalProperties": {"$ref": "#/$defs/JsonValue"},
                        "type": "object",
                    },
                    "JsonValue": {},
                },
                "additionalProperties": False,
                "properties": {
                    "model_name": {
                        "maxLength": 255,
                        "minLength": 1,
                        "title": "Model Name",
                        "type": "string",
                    },
                    "naming_instructions": {
                        "anyOf": [{"maxLength": 32768, "type": "string"}, {"type": "null"}],
                        "default": None,
                        "title": "Naming Instructions",
                    },
                    "audit_columns_template": {
                        "anyOf": [{"$ref": "#/$defs/JsonObject"}, {"type": "null"}],
                        "default": None,
                    },
                    "technical_columns_template": {
                        "anyOf": [{"$ref": "#/$defs/JsonObject"}, {"type": "null"}],
                        "default": None,
                    },
                },
                "required": ["model_name"],
                "title": "MappingAuthoringPolicy",
                "type": "object",
            },
            "example": {
                "audit_columns_template": None,
                "model_name": "Customer Model",
                "naming_instructions": "Use PascalCase names.",
                "technical_columns_template": None,
            },
        },
        "readiness": {
            "description": "Backend-computed ready flag, operation, Object action "
            "and Attribute actions keyed by "
            "modeled_attribute_name; author/extend require output, "
            "preserve requires omission, blocked prohibits "
            "generation.",
            "value_schema": {
                "$defs": {
                    "MappingAttributeReadiness": {
                        "additionalProperties": False,
                        "properties": {
                            "action": {"$ref": "#/$defs/ReadinessAction"},
                            "modeled_attribute_name": {"type": "string", "minLength": 1},
                        },
                        "required": ["action", "modeled_attribute_name"],
                        "title": "MappingAttributeReadiness",
                        "type": "object",
                    },
                    "MappingHeaderReadiness": {
                        "additionalProperties": False,
                        "properties": {
                            "action": {"$ref": "#/$defs/ReadinessAction"},
                            "attribute_actions": {
                                "items": {"$ref": "#/$defs/MappingAttributeReadiness"},
                                "title": "Attribute Actions",
                                "type": "array",
                            },
                        },
                        "required": ["action", "attribute_actions"],
                        "title": "MappingHeaderReadiness",
                        "type": "object",
                    },
                    "MappingOperation": {"enum": ["build", "extend"], "type": "string"},
                    "MappingReadinessIssue": {
                        "additionalProperties": False,
                        "properties": {
                            "code": {
                                "pattern": "^[a-z][a-z0-9_.-]{0,99}$",
                                "title": "Code",
                                "type": "string",
                            },
                            "message": {
                                "maxLength": 500,
                                "minLength": 1,
                                "title": "Message",
                                "type": "string",
                            },
                        },
                        "required": ["code", "message"],
                        "title": "MappingReadinessIssue",
                        "type": "object",
                    },
                    "ReadinessAction": {
                        "enum": ["author", "extend", "preserve", "blocked"],
                        "type": "string",
                    },
                },
                "additionalProperties": False,
                "properties": {
                    "ready": {"title": "Ready", "type": "boolean"},
                    "operation": {"$ref": "#/$defs/MappingOperation"},
                    "headers": {
                        "items": {"$ref": "#/$defs/MappingHeaderReadiness"},
                        "title": "Headers",
                        "type": "array",
                    },
                    "issues": {
                        "items": {"$ref": "#/$defs/MappingReadinessIssue"},
                        "title": "Issues",
                        "type": "array",
                    },
                },
                "required": ["ready", "operation", "headers", "issues"],
                "title": "MappingReadiness",
                "type": "object",
            },
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
            "description": "Exact selected Source System code, name, "
            "description and activity. The run supplies its "
            "single Source Tenant; System code is scoped to "
            "that Tenant.",
            "value_schema": {
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
                    "system_description": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "default": None,
                        "title": "System Description",
                    },
                    "is_active": {"title": "Is Active", "type": "boolean"},
                },
                "required": ["system_code", "system_name", "is_active"],
                "title": "MappingSourceSystem",
                "type": "object",
            },
            "example": {
                "is_active": True,
                "system_code": "CRM",
                "system_description": None,
                "system_name": "CRM",
            },
        },
        "object_output_template": {
            "description": "Selected Object transformation template "
            "by nominal code with description, typed "
            "ordered fields, required flags and "
            "examples; null means no selected "
            "template. Guidance does not change the "
            "fixed outer output schema.",
            "value_schema": {
                "anyOf": [
                    {
                        "$defs": {
                            "JsonValue": {},
                            "MappingOutputTemplateField": {
                                "additionalProperties": False,
                                "properties": {
                                    "name": {
                                        "pattern": "^[a-z][a-z0-9_]{0,99}$",
                                        "title": "Name",
                                        "type": "string",
                                    },
                                    "description": {
                                        "maxLength": 2000,
                                        "minLength": 1,
                                        "title": "Description",
                                        "type": "string",
                                    },
                                    "data_type": {
                                        "enum": [
                                            "string",
                                            "integer",
                                            "number",
                                            "boolean",
                                            "object",
                                            "array",
                                        ],
                                        "title": "Data Type",
                                        "type": "string",
                                    },
                                    "array_item_type": {
                                        "anyOf": [
                                            {
                                                "enum": [
                                                    "string",
                                                    "integer",
                                                    "number",
                                                    "boolean",
                                                    "object",
                                                ],
                                                "type": "string",
                                            },
                                            {"type": "null"},
                                        ],
                                        "title": "Array Item Type",
                                    },
                                    "example": {
                                        "anyOf": [{"$ref": "#/$defs/JsonValue"}, {"type": "null"}],
                                        "default": None,
                                    },
                                    "is_required": {"title": "Is Required", "type": "boolean"},
                                    "order": {
                                        "exclusiveMinimum": 0,
                                        "title": "Order",
                                        "type": "integer",
                                    },
                                },
                                "required": [
                                    "name",
                                    "description",
                                    "data_type",
                                    "array_item_type",
                                    "is_required",
                                    "order",
                                ],
                                "title": "MappingOutputTemplateField",
                                "type": "object",
                            },
                        },
                        "additionalProperties": False,
                        "properties": {
                            "code": {
                                "pattern": "^[a-z][a-z0-9_.-]{0,99}$",
                                "title": "Code",
                                "type": "string",
                            },
                            "name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "title": "Name",
                                "type": "string",
                            },
                            "description": {
                                "anyOf": [{"maxLength": 2000, "type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Description",
                            },
                            "target_type": {
                                "enum": ["mapping_object", "mapping_attribute"],
                                "title": "Target Type",
                                "type": "string",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "fields": {
                                "items": {"$ref": "#/$defs/MappingOutputTemplateField"},
                                "maxItems": 500,
                                "minItems": 1,
                                "title": "Fields",
                                "type": "array",
                            },
                        },
                        "required": ["code", "name", "target_type", "is_active", "fields"],
                        "title": "MappingOutputTemplate",
                        "type": "object",
                    },
                    {"type": "null"},
                ]
            },
            "example": None,
        },
        "attribute_output_template": {
            "description": "Selected Attribute transformation "
            "template by nominal code with "
            "description, typed ordered fields, "
            "required flags and examples; null "
            "means no selected template.",
            "value_schema": {
                "anyOf": [
                    {
                        "$defs": {
                            "JsonValue": {},
                            "MappingOutputTemplateField": {
                                "additionalProperties": False,
                                "properties": {
                                    "name": {
                                        "pattern": "^[a-z][a-z0-9_]{0,99}$",
                                        "title": "Name",
                                        "type": "string",
                                    },
                                    "description": {
                                        "maxLength": 2000,
                                        "minLength": 1,
                                        "title": "Description",
                                        "type": "string",
                                    },
                                    "data_type": {
                                        "enum": [
                                            "string",
                                            "integer",
                                            "number",
                                            "boolean",
                                            "object",
                                            "array",
                                        ],
                                        "title": "Data Type",
                                        "type": "string",
                                    },
                                    "array_item_type": {
                                        "anyOf": [
                                            {
                                                "enum": [
                                                    "string",
                                                    "integer",
                                                    "number",
                                                    "boolean",
                                                    "object",
                                                ],
                                                "type": "string",
                                            },
                                            {"type": "null"},
                                        ],
                                        "title": "Array Item Type",
                                    },
                                    "example": {
                                        "anyOf": [{"$ref": "#/$defs/JsonValue"}, {"type": "null"}],
                                        "default": None,
                                    },
                                    "is_required": {"title": "Is Required", "type": "boolean"},
                                    "order": {
                                        "exclusiveMinimum": 0,
                                        "title": "Order",
                                        "type": "integer",
                                    },
                                },
                                "required": [
                                    "name",
                                    "description",
                                    "data_type",
                                    "array_item_type",
                                    "is_required",
                                    "order",
                                ],
                                "title": "MappingOutputTemplateField",
                                "type": "object",
                            },
                        },
                        "additionalProperties": False,
                        "properties": {
                            "code": {
                                "pattern": "^[a-z][a-z0-9_.-]{0,99}$",
                                "title": "Code",
                                "type": "string",
                            },
                            "name": {
                                "maxLength": 200,
                                "minLength": 1,
                                "title": "Name",
                                "type": "string",
                            },
                            "description": {
                                "anyOf": [{"maxLength": 2000, "type": "string"}, {"type": "null"}],
                                "default": None,
                                "title": "Description",
                            },
                            "target_type": {
                                "enum": ["mapping_object", "mapping_attribute"],
                                "title": "Target Type",
                                "type": "string",
                            },
                            "is_active": {"title": "Is Active", "type": "boolean"},
                            "fields": {
                                "items": {"$ref": "#/$defs/MappingOutputTemplateField"},
                                "maxItems": 500,
                                "minItems": 1,
                                "title": "Fields",
                                "type": "array",
                            },
                        },
                        "required": ["code", "name", "target_type", "is_active", "fields"],
                        "title": "MappingOutputTemplate",
                        "type": "object",
                    },
                    {"type": "null"},
                ]
            },
            "example": None,
        },
    },
    "code_generation": {
        "target_metadata": {
            "description": "Actual physical target natural key and "
            "catalog plus ordered registered "
            "Attributes, exact data "
            "types/nullability, current descriptions "
            "and locks.",
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
            },
        },
        "source_metadata": {
            "description": "Eligible physical source contributions "
            "with source_system_code, role, "
            "rationale, order, lock and nested "
            "actual physical Object/Attributes. No "
            "database IDs.",
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
            "codes/names in dependency_order. Codes "
            "belong to the one Source Tenant of this "
            "target; assign each exactly once across "
            "transformation artifacts.",
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
                            "dependency_order": {
                                "minimum": 0,
                                "title": "Dependency Order",
                                "type": "integer",
                            },
                        },
                        "required": ["system_code", "system_name", "dependency_order"],
                        "title": "SqlSourceSystem",
                        "type": "object",
                    }
                },
                "items": {"$ref": "#/$defs/SqlSourceSystem"},
                "type": "array",
            },
            "example": [{"system_code": "CRM", "system_name": "CRM", "dependency_order": 10}],
        },
        "object_transformations": {
            "description": "Applied Object transformation "
            "documents with "
            "source_system_code, dependency "
            "order and exact modeled Entity "
            "identity, definition, "
            "classification and grain.",
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
                            "definition": {"title": "Definition", "type": "string"},
                            "classification": {"title": "Classification", "type": "string"},
                            "grain": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "title": "Grain",
                            },
                        },
                        "required": [
                            "entity_type",
                            "entity_name",
                            "definition",
                            "classification",
                            "grain",
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
            "transformation documents with "
            "source_system_code, modeled "
            "Entity type/name, physical "
            "target_attribute_name and "
            "target ordinal. Identity "
            "links are resolved from real "
            "bindings; no guessed name "
            "matching.",
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
                        },
                        "required": [
                            "target_attribute_name",
                            "target_attribute_ordinal_position",
                            "transformation",
                            "source_system_code",
                            "modeled_entity_type",
                            "modeled_entity_name",
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
            "applied transformations and qualified "
            "physical names.",
        },
    },
    "validation": {
        "system_ref": {
            "description": "Frozen opaque output-control handle for this "
            "selected System. Copy unchanged; it is not a "
            "database ID.",
            "value_schema": {"pattern": "^system_[1-9][0-9]{0,3}$", "type": "string"},
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
            "description": "Relevant applied modeled target identities "
            "with natural-key Code-style target/source "
            "metadata and exact applied Object/Attribute "
            "transformations. Context is design "
            "evidence, not measured outcomes.",
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
                                                "$ref": "#/$defs/target_metadata_SqlPhysicalAttribute"  # noqa: E501
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
                                        "$ref": "#/$defs/object_transformations_SqlObjectTransformation"  # noqa: E501
                                    },
                                    "type": "array",
                                },
                                "attribute_transformations": {
                                    "items": {
                                        "$ref": "#/$defs/attribute_transformations_SqlAttributeTransformation"  # noqa: E501
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
                    },
                    "required": ["modeled_entity_type", "modeled_entity_name", "context"],
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
                            "dependency_order": {
                                "minimum": 0,
                                "title": "Dependency Order",
                                "type": "integer",
                            },
                        },
                        "required": ["system_code", "system_name", "dependency_order"],
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
                            "definition": {"title": "Definition", "type": "string"},
                            "classification": {"title": "Classification", "type": "string"},
                            "grain": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "title": "Grain",
                            },
                        },
                        "required": [
                            "entity_type",
                            "entity_name",
                            "definition",
                            "classification",
                            "grain",
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
                        },
                        "required": [
                            "target_attribute_name",
                            "target_attribute_ordinal_position",
                            "transformation",
                            "source_system_code",
                            "modeled_entity_type",
                            "modeled_entity_name",
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
                        "source_systems": [
                            {"system_code": "CRM", "system_name": "CRM", "dependency_order": 10}
                        ],
                        "object_transformations": [
                            {
                                "object_dependency_order": 10,
                                "entity": {
                                    "entity_type": "logical_entity",
                                    "entity_name": "Customer",
                                    "definition": "Customer identity.",
                                    "classification": "entity",
                                    "grain": None,
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
                            }
                        ],
                    },
                }
            ],
        },
        "current_code": {
            "description": "Current saved Code artifacts and contributing "
            "Source System codes, with lifecycle/locks and "
            "generated content. Empty means unavailable; no "
            "execution success is implied.",
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
                }
            ],
        },
        "applied_groups": {
            "description": "Existing Validation Group records, including "
            "lifecycle, locks and exact "
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
            "lifecycle/locks and Tenant/System/Group/Check "
            "natural identities. These are definitions, "
            "not execution results.",
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
