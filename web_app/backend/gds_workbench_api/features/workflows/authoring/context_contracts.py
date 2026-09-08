"""Approved workflow-local evidence contracts, shipped with every runtime artifact.

Schemas mirror the reviewed JSON artifacts; tests compare their wire contracts.
No project documentation is loaded by a deployed runtime.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

INPUT_SHAPES: dict[str, Any] = {
    "source_context": {
        "description": "Unique contributing source Connections and business context.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/source_context_entry"},
            "$defs": {
                "source_context_entry": {
                    "type": "object",
                    "properties": {
                        "tenant_code": {"type": "string", "minLength": 1},
                        "tenant_description": {"type": ["string", "null"]},
                        "system_code": {"type": "string", "minLength": 1},
                        "system_description": {"type": ["string", "null"]},
                        "system_type_code": {"type": ["string", "null"]},
                        "system_type_description": {"type": ["string", "null"]},
                        "connection_code": {"type": "string", "minLength": 1},
                        "connection_description": {"type": ["string", "null"]},
                        "connection_type_code": {"type": ["string", "null"]},
                        "connection_type_description": {"type": ["string", "null"]},
                        "zone_code": {"type": "string", "minLength": 1},
                        "zone_description": {"type": ["string", "null"]},
                    },
                    "required": [
                        "tenant_code",
                        "tenant_description",
                        "system_code",
                        "system_description",
                        "system_type_code",
                        "system_type_description",
                        "connection_code",
                        "connection_description",
                        "connection_type_code",
                        "connection_type_description",
                        "zone_code",
                        "zone_description",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "gds_context": {
        "description": "Unique GDS Connection/zone placements for the selected Objects; "
        "empty for Source-only scope.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/gds_context_entry"},
            "$defs": {
                "gds_context_entry": {
                    "type": "object",
                    "properties": {
                        "tenant_code": {"type": "string", "minLength": 1},
                        "system_code": {"type": "string", "minLength": 1},
                        "connection_code": {"type": "string", "minLength": 1},
                        "zone_code": {"type": "string", "minLength": 1},
                        "zone_description": {"type": ["string", "null"]},
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "zone_code",
                        "zone_description",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "object_context": {
        "description": "Selected physical Objects with current saved descriptions.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/object_context_entry"},
            "$defs": {
                "object_context_entry": {
                    "type": "object",
                    "properties": {
                        "tenant_code": {"type": "string", "minLength": 1},
                        "system_code": {"type": "string", "minLength": 1},
                        "connection_code": {"type": "string", "minLength": 1},
                        "object_schema": {"type": "string", "minLength": 1},
                        "object_name": {"type": "string", "minLength": 1},
                        "object_description": {"type": ["string", "null"]},
                        "zone_code": {"type": "string", "minLength": 1},
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                        "object_description",
                        "zone_code",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "object_attribute_context": {
        "description": "Eligible Attributes grouped by physical Object, "
        "with current saved descriptions, types, flags, and "
        "Profiles.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/object_attribute_context_entry"},
            "$defs": {
                "object_attribute_context_entry": {
                    "type": "object",
                    "properties": {
                        "tenant_code": {"type": "string", "minLength": 1},
                        "system_code": {"type": "string", "minLength": 1},
                        "connection_code": {"type": "string", "minLength": 1},
                        "object_schema": {"type": "string", "minLength": 1},
                        "object_name": {"type": "string", "minLength": 1},
                        "attributes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "attribute_name": {"type": "string", "minLength": 1},
                                    "attribute_description": {"type": ["string", "null"]},
                                    "attribute_data_type": {"type": ["string", "null"]},
                                    "attribute_inferred_data_type": {"type": ["string", "null"]},
                                    "attribute_nullability": {"type": ["boolean", "null"]},
                                    "is_natural_key": {"type": ["boolean", "null"]},
                                    "is_surrogate_key": {"type": ["boolean", "null"]},
                                    "is_masking_required": {"type": ["boolean", "null"]},
                                    "is_meta_data": {"type": ["boolean", "null"]},
                                    "profile": {
                                        "anyOf": [
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "profiled_at": {"type": ["string", "null"]},
                                                    "row_scope": {
                                                        "enum": ["all_rows", "batch", None]
                                                    },
                                                    "batch_attribute_name": {
                                                        "type": ["string", "null"]
                                                    },
                                                    "batch_id": {"type": ["string", "null"]},
                                                    "row_count": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "non_null_count": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "null_count": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "blank_count": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "distinct_count": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "min_data_length": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "max_data_length": {
                                                        "type": ["integer", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "avg_data_length": {
                                                        "type": ["number", "null"],
                                                        "minimum": 0,
                                                    },
                                                    "percent_populated": {
                                                        "type": ["number", "null"],
                                                        "minimum": 0,
                                                        "maximum": 100,
                                                    },
                                                    "percent_duplicates": {
                                                        "type": ["number", "null"],
                                                        "minimum": 0,
                                                        "maximum": 100,
                                                    },
                                                    "percent_null": {
                                                        "type": ["number", "null"],
                                                        "minimum": 0,
                                                        "maximum": 100,
                                                    },
                                                    "percent_blank": {
                                                        "type": ["number", "null"],
                                                        "minimum": 0,
                                                        "maximum": 100,
                                                    },
                                                    "percent_distinct": {
                                                        "type": ["number", "null"],
                                                        "minimum": 0,
                                                        "maximum": 100,
                                                    },
                                                },
                                                "required": [
                                                    "profiled_at",
                                                    "row_scope",
                                                    "batch_attribute_name",
                                                    "batch_id",
                                                    "row_count",
                                                    "non_null_count",
                                                    "null_count",
                                                    "blank_count",
                                                    "distinct_count",
                                                    "min_data_length",
                                                    "max_data_length",
                                                    "avg_data_length",
                                                    "percent_populated",
                                                    "percent_duplicates",
                                                    "percent_null",
                                                    "percent_blank",
                                                    "percent_distinct",
                                                ],
                                                "additionalProperties": False,
                                            },
                                            {"type": "null"},
                                        ]
                                    },
                                },
                                "required": [
                                    "attribute_name",
                                    "attribute_description",
                                    "attribute_data_type",
                                    "attribute_inferred_data_type",
                                    "attribute_nullability",
                                    "is_natural_key",
                                    "is_surrogate_key",
                                    "is_masking_required",
                                    "is_meta_data",
                                    "profile",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "selected_attribute_names": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                        "attributes",
                        "selected_attribute_names",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "ingestion_mapping": {
        "description": "Registered Object-only source-to-selected-target links.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/ingestion_mapping_entry"},
            "$defs": {
                "ingestion_mapping_entry": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "object",
                            "properties": {
                                "tenant_code": {"type": "string", "minLength": 1},
                                "system_code": {"type": "string", "minLength": 1},
                                "connection_code": {"type": "string", "minLength": 1},
                                "object_schema": {"type": "string", "minLength": 1},
                                "object_name": {"type": "string", "minLength": 1},
                                "object_description": {"type": ["string", "null"]},
                            },
                            "required": [
                                "tenant_code",
                                "system_code",
                                "connection_code",
                                "object_schema",
                                "object_name",
                                "object_description",
                            ],
                            "additionalProperties": False,
                        },
                        "target": {
                            "type": "object",
                            "properties": {
                                "tenant_code": {"type": "string", "minLength": 1},
                                "system_code": {"type": "string", "minLength": 1},
                                "connection_code": {"type": "string", "minLength": 1},
                                "object_schema": {"type": "string", "minLength": 1},
                                "object_name": {"type": "string", "minLength": 1},
                            },
                            "required": [
                                "tenant_code",
                                "system_code",
                                "connection_code",
                                "object_schema",
                                "object_name",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["source", "target"],
                    "additionalProperties": False,
                }
            },
        },
    },
    "object_relationship_context": {
        "description": "Existing applied relationships grouped by each "
        "scoped physical Object. Incoming matches the "
        "to-Object; outgoing matches the from-Object. "
        "Include groups with empty arrays. Each "
        "relationship retains all 17 approved "
        "endpoint/kind/confidence/basis/status/lock "
        "fields and excludes validation fields.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/object_relationship_context_entry"},
            "$defs": {
                "object_relationship_context_entry": {
                    "type": "object",
                    "properties": {
                        "tenant_code": {"type": "string", "minLength": 1},
                        "system_code": {"type": "string", "minLength": 1},
                        "connection_code": {"type": "string", "minLength": 1},
                        "object_schema": {"type": "string", "minLength": 1},
                        "object_name": {"type": "string", "minLength": 1},
                        "incoming_relationships": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/applied_relationships_entry"},
                        },
                        "outgoing_relationships": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/applied_relationships_entry"},
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                        "incoming_relationships",
                        "outgoing_relationships",
                    ],
                    "additionalProperties": False,
                },
                "applied_relationships_entry": {
                    "type": "object",
                    "properties": {
                        "from_tenant_code": {"type": "string", "minLength": 1},
                        "from_system_code": {"type": "string", "minLength": 1},
                        "from_connection_code": {"type": "string", "minLength": 1},
                        "from_object_schema": {"type": "string", "minLength": 1},
                        "from_object_name": {"type": "string", "minLength": 1},
                        "from_attribute_name": {"type": "string", "minLength": 1},
                        "to_tenant_code": {"type": "string", "minLength": 1},
                        "to_system_code": {"type": "string", "minLength": 1},
                        "to_connection_code": {"type": "string", "minLength": 1},
                        "to_object_schema": {"type": "string", "minLength": 1},
                        "to_object_name": {"type": "string", "minLength": 1},
                        "to_attribute_name": {"type": "string", "minLength": 1},
                        "relationship_kind": {"type": "string", "minLength": 1},
                        "relationship_confidence": {"enum": ["low", "medium", "high"]},
                        "relationship_basis": {"type": "string", "minLength": 1},
                        "analysis_result_status": {"enum": ["active", "inactive", "deprecated"]},
                        "analysis_result_is_locked": {"type": "boolean"},
                    },
                    "required": [
                        "from_tenant_code",
                        "from_system_code",
                        "from_connection_code",
                        "from_object_schema",
                        "from_object_name",
                        "from_attribute_name",
                        "to_tenant_code",
                        "to_system_code",
                        "to_connection_code",
                        "to_object_schema",
                        "to_object_name",
                        "to_attribute_name",
                        "relationship_kind",
                        "relationship_confidence",
                        "relationship_basis",
                        "analysis_result_status",
                        "analysis_result_is_locked",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    },
    "modeling_assertions": {
        "description": "Active governed Analysis-applicable assertion records "
        "from active documents within authorized Model/source "
        "scope; includes applicable Model-wide assertions.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/modeling_assertions_entry"},
            "$defs": {
                "modeling_assertions_entry": {
                    "type": "object",
                    "properties": {
                        "modeling_assertion_record_key": {"type": "string", "minLength": 1},
                        "modeling_assertion_document_name": {"type": "string", "minLength": 1},
                        "modeling_assertion_record_type": {"type": "string", "minLength": 1},
                        "modeling_assertion_text": {"type": "string", "minLength": 1},
                        "modeling_assertion_details": {"type": "object"},
                        "modeling_assertion_source_location": {"type": ["object", "null"]},
                        "modeling_assertion_confidence": {"enum": ["low", "medium", "high", None]},
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
                }
            },
        },
    },
    "conceptual_object_list": {
        "description": "Compact directory of all existing eligible "
        "Conceptual record identities in the frozen Model. "
        "Natural-key fields only; no descriptions, types, "
        "supports, status, or locks. Use the corresponding "
        "detail variable or reader to interpret a record. [] "
        "means known empty; null means the applied Conceptual "
        "section is unavailable.",
        "schema": {
            "$defs": {
                "ConceptualObjectKey": {
                    "type": "object",
                    "properties": {
                        "conceptual_object_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Object Name",
                            "type": "string",
                        }
                    },
                    "required": ["conceptual_object_name"],
                    "additionalProperties": False,
                }
            },
            "anyOf": [
                {"type": "array", "items": {"$ref": "#/$defs/ConceptualObjectKey"}},
                {"type": "null"},
            ],
        },
    },
    "conceptual_objects": {
        "description": "Existing Conceptual objects, retaining all existing "
        "record fields and nested Object/Assertion supports, "
        "confidence, lifecycle status, and locks. Known empty is "
        "[]; null means the applied section is unavailable.",
        "schema": {
            "$defs": {
                "AssertionRecordKey": {
                    "additionalProperties": False,
                    "properties": {
                        "modeling_assertion_record_key": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
                            "title": "Modeling Assertion Record Key",
                            "type": "string",
                        }
                    },
                    "required": ["modeling_assertion_record_key"],
                    "title": "AssertionRecordKey",
                    "type": "object",
                },
                "AssertionSupportRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "assertion",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "assertion_record": {"$ref": "#/$defs/AssertionRecordKey"},
                        "support_role": {
                            "anyOf": [
                                {
                                    "maxLength": 255,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Support Role",
                        },
                        "support_reason": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Support Reason",
                            "type": "string",
                        },
                        "support_reason_detail": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Support Reason Detail",
                        },
                        "support_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Support Confidence",
                            "type": "string",
                        },
                        "support_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Support Status",
                            "type": "string",
                        },
                        "support_is_locked": {"title": "Support Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "assertion_record",
                        "support_role",
                        "support_reason",
                        "support_reason_detail",
                        "support_confidence",
                        "support_status",
                        "support_is_locked",
                    ],
                    "title": "AssertionSupportRecord",
                    "type": "object",
                },
                "ConceptualObjectRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "conceptual_object_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Object Name",
                            "type": "string",
                        },
                        "conceptual_object_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Object Definition",
                            "type": "string",
                        },
                        "conceptual_object_type": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Object Type",
                            "type": "string",
                        },
                        "conceptual_object_grain": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Object Grain",
                            "type": "string",
                        },
                        "conceptual_object_aliases": {
                            "items": {"type": "string"},
                            "title": "Conceptual Object Aliases",
                            "type": "array",
                        },
                        "conceptual_object_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Conceptual Object Confidence",
                            "type": "string",
                        },
                        "conceptual_object_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Conceptual Object Status",
                            "type": "string",
                        },
                        "conceptual_object_is_locked": {
                            "title": "Conceptual Object Is Locked",
                            "type": "boolean",
                        },
                        "supports": {
                            "items": {"$ref": "#/$defs/SupportRecord"},
                            "title": "Supports",
                            "type": "array",
                        },
                    },
                    "required": [
                        "conceptual_object_name",
                        "conceptual_object_definition",
                        "conceptual_object_type",
                        "conceptual_object_grain",
                        "conceptual_object_aliases",
                        "conceptual_object_confidence",
                        "conceptual_object_status",
                        "conceptual_object_is_locked",
                        "supports",
                    ],
                    "title": "ConceptualObjectRecord",
                    "type": "object",
                },
                "ObjectSupportRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "object",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "source_object": {"$ref": "#/$defs/PhysicalObjectKey"},
                        "support_role": {
                            "anyOf": [
                                {
                                    "maxLength": 255,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Support Role",
                        },
                        "support_reason": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Support Reason",
                            "type": "string",
                        },
                        "support_reason_detail": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Support Reason Detail",
                        },
                        "support_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Support Confidence",
                            "type": "string",
                        },
                        "support_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Support Status",
                            "type": "string",
                        },
                        "support_is_locked": {"title": "Support Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "source_object",
                        "support_role",
                        "support_reason",
                        "support_reason_detail",
                        "support_confidence",
                        "support_status",
                        "support_is_locked",
                    ],
                    "title": "ObjectSupportRecord",
                    "type": "object",
                },
                "PhysicalObjectKey": {
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
                        "connection_code": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Connection Code",
                            "type": "string",
                        },
                        "object_schema": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Schema",
                            "type": "string",
                        },
                        "object_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    ],
                    "title": "PhysicalObjectKey",
                    "type": "object",
                },
                "SupportRecord": {
                    "discriminator": {
                        "mapping": {
                            "assertion": "#/$defs/AssertionSupportRecord",
                            "object": "#/$defs/ObjectSupportRecord",
                        },
                        "propertyName": "support_source_type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/ObjectSupportRecord"},
                        {"$ref": "#/$defs/AssertionSupportRecord"},
                    ],
                },
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/ConceptualObjectRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "conceptual_relationship_list": {
        "description": "Compact directory of all existing eligible "
        "Conceptual record identities in the frozen "
        "Model. Natural-key fields only; no "
        "descriptions, types, supports, status, or "
        "locks. Use the corresponding detail variable "
        "or reader to interpret a record. [] means "
        "known empty; null means the applied Conceptual "
        "section is unavailable.",
        "schema": {
            "$defs": {
                "ConceptualRelationshipKey": {
                    "type": "object",
                    "properties": {
                        "from_conceptual_object_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "From Conceptual Object Name",
                            "type": "string",
                        },
                        "to_conceptual_object_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "To Conceptual Object Name",
                            "type": "string",
                        },
                        "conceptual_relationship_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Relationship Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "from_conceptual_object_name",
                        "to_conceptual_object_name",
                        "conceptual_relationship_name",
                    ],
                    "additionalProperties": False,
                }
            },
            "anyOf": [
                {"type": "array", "items": {"$ref": "#/$defs/ConceptualRelationshipKey"}},
                {"type": "null"},
            ],
        },
    },
    "conceptual_relationships": {
        "description": "Existing Conceptual relationships, retaining all "
        "existing record fields and nested Object/Assertion "
        "supports, confidence, lifecycle status, and locks. "
        "Known empty is []; null means the applied section "
        "is unavailable.",
        "schema": {
            "$defs": {
                "AssertionRecordKey": {
                    "additionalProperties": False,
                    "properties": {
                        "modeling_assertion_record_key": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
                            "title": "Modeling Assertion Record Key",
                            "type": "string",
                        }
                    },
                    "required": ["modeling_assertion_record_key"],
                    "title": "AssertionRecordKey",
                    "type": "object",
                },
                "AssertionSupportRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "assertion",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "assertion_record": {"$ref": "#/$defs/AssertionRecordKey"},
                        "support_role": {
                            "anyOf": [
                                {
                                    "maxLength": 255,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Support Role",
                        },
                        "support_reason": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Support Reason",
                            "type": "string",
                        },
                        "support_reason_detail": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Support Reason Detail",
                        },
                        "support_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Support Confidence",
                            "type": "string",
                        },
                        "support_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Support Status",
                            "type": "string",
                        },
                        "support_is_locked": {"title": "Support Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "assertion_record",
                        "support_role",
                        "support_reason",
                        "support_reason_detail",
                        "support_confidence",
                        "support_status",
                        "support_is_locked",
                    ],
                    "title": "AssertionSupportRecord",
                    "type": "object",
                },
                "ConceptualRelationshipRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "from_conceptual_object_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "From Conceptual Object Name",
                            "type": "string",
                        },
                        "to_conceptual_object_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "To Conceptual Object Name",
                            "type": "string",
                        },
                        "conceptual_relationship_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Relationship Name",
                            "type": "string",
                        },
                        "conceptual_relationship_type": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Relationship Type",
                            "type": "string",
                        },
                        "conceptual_relationship_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Relationship Definition",
                            "type": "string",
                        },
                        "conceptual_relationship_cardinality": {
                            "anyOf": [
                                {
                                    "enum": [
                                        "one_to_one",
                                        "one_to_many",
                                        "many_to_one",
                                        "many_to_many",
                                    ],
                                    "type": "string",
                                },
                                {"const": "unknown", "type": "string"},
                            ],
                            "title": "Conceptual Relationship Cardinality",
                        },
                        "conceptual_relationship_basis": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Relationship Basis",
                            "type": "string",
                        },
                        "conceptual_relationship_cardinality_basis": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Conceptual Relationship Cardinality Basis",
                            "type": "string",
                        },
                        "conceptual_relationship_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Conceptual Relationship Confidence",
                            "type": "string",
                        },
                        "conceptual_relationship_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Conceptual Relationship Status",
                            "type": "string",
                        },
                        "conceptual_relationship_is_locked": {
                            "title": "Conceptual Relationship Is Locked",
                            "type": "boolean",
                        },
                        "supports": {
                            "items": {"$ref": "#/$defs/SupportRecord"},
                            "title": "Supports",
                            "type": "array",
                        },
                    },
                    "required": [
                        "from_conceptual_object_name",
                        "to_conceptual_object_name",
                        "conceptual_relationship_name",
                        "conceptual_relationship_type",
                        "conceptual_relationship_definition",
                        "conceptual_relationship_cardinality",
                        "conceptual_relationship_basis",
                        "conceptual_relationship_cardinality_basis",
                        "conceptual_relationship_confidence",
                        "conceptual_relationship_status",
                        "conceptual_relationship_is_locked",
                        "supports",
                    ],
                    "title": "ConceptualRelationshipRecord",
                    "type": "object",
                },
                "ObjectSupportRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "object",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "source_object": {"$ref": "#/$defs/PhysicalObjectKey"},
                        "support_role": {
                            "anyOf": [
                                {
                                    "maxLength": 255,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Support Role",
                        },
                        "support_reason": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Support Reason",
                            "type": "string",
                        },
                        "support_reason_detail": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Support Reason Detail",
                        },
                        "support_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Support Confidence",
                            "type": "string",
                        },
                        "support_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Support Status",
                            "type": "string",
                        },
                        "support_is_locked": {"title": "Support Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "source_object",
                        "support_role",
                        "support_reason",
                        "support_reason_detail",
                        "support_confidence",
                        "support_status",
                        "support_is_locked",
                    ],
                    "title": "ObjectSupportRecord",
                    "type": "object",
                },
                "PhysicalObjectKey": {
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
                        "connection_code": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Connection Code",
                            "type": "string",
                        },
                        "object_schema": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Schema",
                            "type": "string",
                        },
                        "object_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    ],
                    "title": "PhysicalObjectKey",
                    "type": "object",
                },
                "SupportRecord": {
                    "discriminator": {
                        "mapping": {
                            "assertion": "#/$defs/AssertionSupportRecord",
                            "object": "#/$defs/ObjectSupportRecord",
                        },
                        "propertyName": "support_source_type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/ObjectSupportRecord"},
                        {"$ref": "#/$defs/AssertionSupportRecord"},
                    ],
                },
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/ConceptualRelationshipRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "logical_submodel_list": {
        "description": "Compact existing Logical submodel identities only. "
        "All authorized applied records, including "
        "inactive/deprecated history; obtain details to "
        "interpret status, meaning, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "logical_submodel_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Logical Submodel Name",
                                "type": "string",
                            }
                        },
                        "required": ["logical_submodel_name"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "logical_submodels": {
        "description": "Complete existing LogicalSubmodelRecord entries without "
        "added or removed fields. Exact nominal keys; current "
        "saved statuses and locks.",
        "schema": {
            "$defs": {
                "LogicalSubmodelRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "logical_submodel_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Submodel Name",
                            "type": "string",
                        },
                        "logical_submodel_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Submodel Definition",
                            "type": "string",
                        },
                        "logical_submodel_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Logical Submodel Status",
                            "type": "string",
                        },
                        "logical_submodel_is_locked": {
                            "title": "Logical Submodel Is Locked",
                            "type": "boolean",
                        },
                    },
                    "required": [
                        "logical_submodel_name",
                        "logical_submodel_definition",
                        "logical_submodel_status",
                        "logical_submodel_is_locked",
                    ],
                    "title": "LogicalSubmodelRecord",
                    "type": "object",
                }
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/LogicalSubmodelRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "logical_entity_list": {
        "description": "Compact existing Logical entity identities only. All "
        "authorized applied records, including "
        "inactive/deprecated history; obtain details to "
        "interpret status, meaning, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "logical_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Logical Entity Name",
                                "type": "string",
                            }
                        },
                        "required": ["logical_entity_name"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "logical_entities": {
        "description": "Complete existing LogicalEntityRecord entries without "
        "added or removed fields. Exact nominal keys; current saved "
        "statuses and locks.",
        "schema": {
            "$defs": {
                "AssertionRecordKey": {
                    "additionalProperties": False,
                    "properties": {
                        "modeling_assertion_record_key": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
                            "title": "Modeling Assertion Record Key",
                            "type": "string",
                        }
                    },
                    "required": ["modeling_assertion_record_key"],
                    "title": "AssertionRecordKey",
                    "type": "object",
                },
                "LogicalAssertionSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "assertion",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "assertion_record": {"$ref": "#/$defs/AssertionRecordKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "assertion_record",
                        "rationale",
                        "status",
                        "is_locked",
                    ],
                    "title": "LogicalAssertionSourceRecord",
                    "type": "object",
                },
                "LogicalEntityRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "logical_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Entity Name",
                            "type": "string",
                        },
                        "logical_entity_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Entity Definition",
                            "type": "string",
                        },
                        "logical_entity_type": {
                            "enum": [
                                "core",
                                "reference",
                                "transaction",
                                "event",
                                "bridge",
                                "history",
                                "snapshot",
                                "association",
                                "aggregate",
                                "other",
                            ],
                            "title": "Logical Entity Type",
                            "type": "string",
                        },
                        "logical_entity_type_detail": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Logical Entity Type Detail",
                        },
                        "logical_entity_grain": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Entity Grain",
                            "type": "string",
                        },
                        "logical_entity_dependency_order": {
                            "minimum": 0,
                            "title": "Logical Entity Dependency Order",
                            "type": "integer",
                        },
                        "logical_entity_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Logical Entity Confidence",
                            "type": "string",
                        },
                        "logical_entity_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Logical Entity Status",
                            "type": "string",
                        },
                        "logical_entity_is_locked": {
                            "title": "Logical Entity Is Locked",
                            "type": "boolean",
                        },
                        "submodels": {
                            "items": {"$ref": "#/$defs/SubmodelMembershipRecord"},
                            "title": "Submodels",
                            "type": "array",
                        },
                        "sources": {
                            "items": {"$ref": "#/$defs/LogicalEntitySourceRecord"},
                            "title": "Sources",
                            "type": "array",
                        },
                    },
                    "required": [
                        "logical_entity_name",
                        "logical_entity_definition",
                        "logical_entity_type",
                        "logical_entity_type_detail",
                        "logical_entity_grain",
                        "logical_entity_dependency_order",
                        "logical_entity_confidence",
                        "logical_entity_status",
                        "logical_entity_is_locked",
                        "submodels",
                        "sources",
                    ],
                    "title": "LogicalEntityRecord",
                    "type": "object",
                },
                "LogicalEntitySourceRecord": {
                    "discriminator": {
                        "mapping": {
                            "assertion": "#/$defs/LogicalAssertionSourceRecord",
                            "object": "#/$defs/LogicalObjectSourceRecord",
                        },
                        "propertyName": "support_source_type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/LogicalObjectSourceRecord"},
                        {"$ref": "#/$defs/LogicalAssertionSourceRecord"},
                    ],
                },
                "LogicalObjectSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "object",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "source_object": {"$ref": "#/$defs/PhysicalObjectKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "source_object",
                        "rationale",
                        "status",
                        "is_locked",
                    ],
                    "title": "LogicalObjectSourceRecord",
                    "type": "object",
                },
                "PhysicalObjectKey": {
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
                        "connection_code": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Connection Code",
                            "type": "string",
                        },
                        "object_schema": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Schema",
                            "type": "string",
                        },
                        "object_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    ],
                    "title": "PhysicalObjectKey",
                    "type": "object",
                },
                "SubmodelMembershipRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "submodel_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Submodel Name",
                            "type": "string",
                        },
                        "membership_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Membership Status",
                            "type": "string",
                        },
                        "membership_is_locked": {
                            "title": "Membership Is Locked",
                            "type": "boolean",
                        },
                    },
                    "required": ["submodel_name", "membership_status", "membership_is_locked"],
                    "title": "SubmodelMembershipRecord",
                    "type": "object",
                },
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/LogicalEntityRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "logical_attribute_list": {
        "description": "Compact existing Logical attribute identities only. "
        "All authorized applied records, including "
        "inactive/deprecated history; obtain details to "
        "interpret status, meaning, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "logical_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Logical Entity Name",
                                "type": "string",
                            },
                            "logical_attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Logical Attribute Name",
                                "type": "string",
                            },
                        },
                        "required": ["logical_entity_name", "logical_attribute_name"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "logical_attributes": {
        "description": "Complete existing LogicalAttributeRecord entries without "
        "added or removed fields. Exact nominal keys; current "
        "saved statuses and locks.",
        "schema": {
            "$defs": {
                "AssertionRecordKey": {
                    "additionalProperties": False,
                    "properties": {
                        "modeling_assertion_record_key": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
                            "title": "Modeling Assertion Record Key",
                            "type": "string",
                        }
                    },
                    "required": ["modeling_assertion_record_key"],
                    "title": "AssertionRecordKey",
                    "type": "object",
                },
                "AttributeAssertionSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "assertion",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "assertion_record": {"$ref": "#/$defs/AssertionRecordKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "assertion_record",
                        "rationale",
                        "status",
                        "is_locked",
                    ],
                    "title": "AttributeAssertionSourceRecord",
                    "type": "object",
                },
                "AttributePhysicalSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "attribute",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "source_attribute": {"$ref": "#/$defs/PhysicalAttributeKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "source_attribute",
                        "rationale",
                        "status",
                        "is_locked",
                    ],
                    "title": "AttributePhysicalSourceRecord",
                    "type": "object",
                },
                "AttributeSourceRecord": {
                    "discriminator": {
                        "mapping": {
                            "assertion": "#/$defs/AttributeAssertionSourceRecord",
                            "attribute": "#/$defs/AttributePhysicalSourceRecord",
                        },
                        "propertyName": "support_source_type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/AttributePhysicalSourceRecord"},
                        {"$ref": "#/$defs/AttributeAssertionSourceRecord"},
                    ],
                },
                "LogicalAttributeRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "logical_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Entity Name",
                            "type": "string",
                        },
                        "logical_attribute_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Attribute Name",
                            "type": "string",
                        },
                        "logical_attribute_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Attribute Definition",
                            "type": "string",
                        },
                        "logical_attribute_data_type": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Attribute Data Type",
                            "type": "string",
                        },
                        "logical_attribute_is_nullable": {
                            "title": "Logical Attribute Is Nullable",
                            "type": "boolean",
                        },
                        "logical_attribute_is_primary_key": {
                            "title": "Logical Attribute Is Primary Key",
                            "type": "boolean",
                        },
                        "logical_attribute_is_natural_key": {
                            "title": "Logical Attribute Is Natural Key",
                            "type": "boolean",
                        },
                        "logical_attribute_is_surrogate_key": {
                            "title": "Logical Attribute Is Surrogate Key",
                            "type": "boolean",
                        },
                        "logical_attribute_ordinal_position": {
                            "exclusiveMinimum": 0,
                            "title": "Logical Attribute Ordinal Position",
                            "type": "integer",
                        },
                        "logical_attribute_is_audit_column": {
                            "title": "Logical Attribute Is Audit Column",
                            "type": "boolean",
                        },
                        "logical_attribute_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Logical Attribute Status",
                            "type": "string",
                        },
                        "logical_attribute_is_locked": {
                            "title": "Logical Attribute Is Locked",
                            "type": "boolean",
                        },
                        "sources": {
                            "items": {"$ref": "#/$defs/AttributeSourceRecord"},
                            "title": "Sources",
                            "type": "array",
                        },
                    },
                    "required": [
                        "logical_entity_name",
                        "logical_attribute_name",
                        "logical_attribute_definition",
                        "logical_attribute_data_type",
                        "logical_attribute_is_nullable",
                        "logical_attribute_is_primary_key",
                        "logical_attribute_is_natural_key",
                        "logical_attribute_is_surrogate_key",
                        "logical_attribute_ordinal_position",
                        "logical_attribute_is_audit_column",
                        "logical_attribute_status",
                        "logical_attribute_is_locked",
                        "sources",
                    ],
                    "title": "LogicalAttributeRecord",
                    "type": "object",
                },
                "PhysicalAttributeKey": {
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
                        "connection_code": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Connection Code",
                            "type": "string",
                        },
                        "object_schema": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Schema",
                            "type": "string",
                        },
                        "object_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Name",
                            "type": "string",
                        },
                        "attribute_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Attribute Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                        "attribute_name",
                    ],
                    "title": "PhysicalAttributeKey",
                    "type": "object",
                },
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/LogicalAttributeRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "logical_relationship_list": {
        "description": "Compact existing Logical relationship identities "
        "only. All authorized applied records, including "
        "inactive/deprecated history; obtain details to "
        "interpret status, meaning, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_logical_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "From Logical Entity Name",
                                "type": "string",
                            },
                            "from_logical_attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "From Logical Attribute Name",
                                "type": "string",
                            },
                            "to_logical_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "To Logical Entity Name",
                                "type": "string",
                            },
                            "to_logical_attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "To Logical Attribute Name",
                                "type": "string",
                            },
                            "logical_relationship_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Logical Relationship Name",
                                "type": "string",
                            },
                        },
                        "required": [
                            "from_logical_entity_name",
                            "from_logical_attribute_name",
                            "to_logical_entity_name",
                            "to_logical_attribute_name",
                            "logical_relationship_name",
                        ],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "logical_relationships": {
        "description": "Complete existing LogicalRelationshipRecord entries "
        "without added or removed fields. Exact nominal keys; "
        "current saved statuses and locks.",
        "schema": {
            "$defs": {
                "LogicalRelationshipRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "logical_relationship_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Relationship Name",
                            "type": "string",
                        },
                        "logical_relationship_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Relationship Definition",
                            "type": "string",
                        },
                        "from_logical_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "From Logical Entity Name",
                            "type": "string",
                        },
                        "from_logical_attribute_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "From Logical Attribute Name",
                            "type": "string",
                        },
                        "to_logical_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "To Logical Entity Name",
                            "type": "string",
                        },
                        "to_logical_attribute_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "To Logical Attribute Name",
                            "type": "string",
                        },
                        "logical_relationship_cardinality": {
                            "enum": ["one_to_one", "one_to_many", "many_to_one", "many_to_many"],
                            "title": "Logical Relationship Cardinality",
                            "type": "string",
                        },
                        "logical_relationship_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Logical Relationship Confidence",
                            "type": "string",
                        },
                        "logical_relationship_basis": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Relationship Basis",
                            "type": "string",
                        },
                        "logical_relationship_cardinality_basis": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Logical Relationship Cardinality Basis",
                            "type": "string",
                        },
                        "logical_relationship_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Logical Relationship Status",
                            "type": "string",
                        },
                        "logical_relationship_is_locked": {
                            "title": "Logical Relationship Is Locked",
                            "type": "boolean",
                        },
                    },
                    "required": [
                        "logical_relationship_name",
                        "logical_relationship_definition",
                        "from_logical_entity_name",
                        "from_logical_attribute_name",
                        "to_logical_entity_name",
                        "to_logical_attribute_name",
                        "logical_relationship_cardinality",
                        "logical_relationship_confidence",
                        "logical_relationship_basis",
                        "logical_relationship_cardinality_basis",
                        "logical_relationship_status",
                        "logical_relationship_is_locked",
                    ],
                    "title": "LogicalRelationshipRecord",
                    "type": "object",
                }
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/LogicalRelationshipRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "logical.naming_instructions": {
        "description": "Effective Logical naming guidance. Use the "
        "saved Silver Model override when present, "
        "otherwise the existing Logical default. "
        "Advisory guidance; preserve saved identities. "
        "This is resolved before rendering and remains a "
        "Logical-local variable.",
        "schema": {"maxLength": 32768, "minLength": 1, "pattern": "\\S", "type": "string"},
    },
    "logical.audit_columns": {
        "description": "Exact configured Silver audit-column template: "
        "schema_version and columns with semantic_name, "
        "data_type, nullable, definition. Null means no "
        "configured template. Preserve the existing "
        "deterministic backend projection and lock/conflict "
        "checks. The complete model includes required audit "
        "Attributes; do not invent physical sources for "
        "configured audit columns.",
        "schema": {
            "$defs": {
                "LogicalAuditPolicy": {
                    "additionalProperties": False,
                    "properties": {
                        "schema_version": {
                            "const": "1.0",
                            "default": "1.0",
                            "title": "Schema Version",
                            "type": "string",
                        },
                        "columns": {
                            "items": {"$ref": "#/$defs/LogicalAuditPolicyColumn"},
                            "maxItems": 32,
                            "minItems": 1,
                            "title": "Columns",
                            "type": "array",
                        },
                    },
                    "required": ["columns"],
                    "title": "LogicalAuditPolicy",
                    "type": "object",
                },
                "LogicalAuditPolicyColumn": {
                    "additionalProperties": False,
                    "properties": {
                        "semantic_name": {"$ref": "#/$defs/_Nonblank255"},
                        "data_type": {"$ref": "#/$defs/_Nonblank100"},
                        "nullable": {"title": "Nullable", "type": "boolean"},
                        "definition": {
                            "anyOf": [{"$ref": "#/$defs/_Nonblank2000"}, {"type": "null"}]
                        },
                    },
                    "required": ["semantic_name", "data_type", "nullable", "definition"],
                    "title": "LogicalAuditPolicyColumn",
                    "type": "object",
                },
                "_Nonblank100": {
                    "maxLength": 100,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Nonblank2000": {
                    "maxLength": 2000,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Nonblank255": {
                    "maxLength": 255,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
            },
            "anyOf": [{"$ref": "#/$defs/LogicalAuditPolicy"}, {"type": "null"}],
        },
    },
    "dimensional_submodel_list": {
        "description": "Compact existing Dimensional submodel identities "
        "only. Retain complete natural keys, including "
        "nullable role for relationship identity. Read "
        "details to interpret meaning, lifecycle, and "
        "locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimensional_submodel_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Dimensional Submodel Name",
                                "type": "string",
                            }
                        },
                        "required": ["dimensional_submodel_name"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "dimensional_submodels": {
        "description": "Complete existing DimensionalSubmodelRecord entries. "
        "Preserve all fields, nested sources/memberships, "
        "lifecycle, and locks.",
        "schema": {
            "$defs": {
                "DimensionalSubmodelRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "dimensional_submodel_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Submodel Name",
                            "type": "string",
                        },
                        "dimensional_submodel_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Submodel Definition",
                            "type": "string",
                        },
                        "dimensional_submodel_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Dimensional Submodel Status",
                            "type": "string",
                        },
                        "dimensional_submodel_is_locked": {
                            "title": "Dimensional Submodel Is Locked",
                            "type": "boolean",
                        },
                    },
                    "required": [
                        "dimensional_submodel_name",
                        "dimensional_submodel_definition",
                        "dimensional_submodel_status",
                        "dimensional_submodel_is_locked",
                    ],
                    "title": "DimensionalSubmodelRecord",
                    "type": "object",
                }
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/DimensionalSubmodelRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "dimensional_entity_list": {
        "description": "Compact existing Dimensional entity identities "
        "only. Retain complete natural keys, including "
        "nullable role for relationship identity. Read "
        "details to interpret meaning, lifecycle, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimensional_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Dimensional Entity Name",
                                "type": "string",
                            }
                        },
                        "required": ["dimensional_entity_name"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "dimensional_entities": {
        "description": "Complete existing DimensionalEntityRecord entries. "
        "Preserve all fields, nested sources/memberships, "
        "lifecycle, and locks.",
        "schema": {
            "$defs": {
                "AssertionRecordKey": {
                    "additionalProperties": False,
                    "properties": {
                        "modeling_assertion_record_key": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
                            "title": "Modeling Assertion Record Key",
                            "type": "string",
                        }
                    },
                    "required": ["modeling_assertion_record_key"],
                    "title": "AssertionRecordKey",
                    "type": "object",
                },
                "DimensionalAssertionSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "assertion",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "assertion_record": {"$ref": "#/$defs/AssertionRecordKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                        "source_role": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Source Role",
                            "type": "string",
                        },
                    },
                    "required": [
                        "support_source_type",
                        "assertion_record",
                        "rationale",
                        "status",
                        "is_locked",
                        "source_role",
                    ],
                    "title": "DimensionalAssertionSourceRecord",
                    "type": "object",
                },
                "DimensionalEntityRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "dimensional_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Entity Name",
                            "type": "string",
                        },
                        "dimensional_entity_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Entity Definition",
                            "type": "string",
                        },
                        "dimensional_entity_type": {
                            "enum": ["fact", "dimension", "bridge"],
                            "title": "Dimensional Entity Type",
                            "type": "string",
                        },
                        "dimensional_fact_type": {
                            "anyOf": [
                                {
                                    "enum": [
                                        "transaction",
                                        "periodic_snapshot",
                                        "accumulating_snapshot",
                                        "factless",
                                    ],
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Dimensional Fact Type",
                        },
                        "dimensional_entity_grain_definition": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Dimensional Entity Grain Definition",
                        },
                        "dimensional_entity_dependency_order": {
                            "minimum": 0,
                            "title": "Dimensional Entity Dependency Order",
                            "type": "integer",
                        },
                        "dimensional_entity_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Dimensional Entity Confidence",
                            "type": "string",
                        },
                        "dimensional_entity_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Dimensional Entity Status",
                            "type": "string",
                        },
                        "dimensional_entity_is_locked": {
                            "title": "Dimensional Entity Is Locked",
                            "type": "boolean",
                        },
                        "submodels": {
                            "items": {"$ref": "#/$defs/SubmodelMembershipRecord"},
                            "title": "Submodels",
                            "type": "array",
                        },
                        "sources": {
                            "items": {"$ref": "#/$defs/DimensionalEntitySourceRecord"},
                            "title": "Sources",
                            "type": "array",
                        },
                    },
                    "required": [
                        "dimensional_entity_name",
                        "dimensional_entity_definition",
                        "dimensional_entity_type",
                        "dimensional_fact_type",
                        "dimensional_entity_grain_definition",
                        "dimensional_entity_dependency_order",
                        "dimensional_entity_confidence",
                        "dimensional_entity_status",
                        "dimensional_entity_is_locked",
                        "submodels",
                        "sources",
                    ],
                    "title": "DimensionalEntityRecord",
                    "type": "object",
                },
                "DimensionalEntitySourceRecord": {
                    "discriminator": {
                        "mapping": {
                            "assertion": "#/$defs/DimensionalAssertionSourceRecord",
                            "object": "#/$defs/DimensionalObjectSourceRecord",
                        },
                        "propertyName": "support_source_type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/DimensionalObjectSourceRecord"},
                        {"$ref": "#/$defs/DimensionalAssertionSourceRecord"},
                    ],
                },
                "DimensionalObjectSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "object",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "source_object": {"$ref": "#/$defs/PhysicalObjectKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                        "source_role": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Source Role",
                            "type": "string",
                        },
                    },
                    "required": [
                        "support_source_type",
                        "source_object",
                        "rationale",
                        "status",
                        "is_locked",
                        "source_role",
                    ],
                    "title": "DimensionalObjectSourceRecord",
                    "type": "object",
                },
                "PhysicalObjectKey": {
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
                        "connection_code": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Connection Code",
                            "type": "string",
                        },
                        "object_schema": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Schema",
                            "type": "string",
                        },
                        "object_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    ],
                    "title": "PhysicalObjectKey",
                    "type": "object",
                },
                "SubmodelMembershipRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "submodel_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Submodel Name",
                            "type": "string",
                        },
                        "membership_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Membership Status",
                            "type": "string",
                        },
                        "membership_is_locked": {
                            "title": "Membership Is Locked",
                            "type": "boolean",
                        },
                    },
                    "required": ["submodel_name", "membership_status", "membership_is_locked"],
                    "title": "SubmodelMembershipRecord",
                    "type": "object",
                },
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/DimensionalEntityRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "dimensional_attribute_list": {
        "description": "Compact existing Dimensional attribute "
        "identities only. Retain complete natural keys, "
        "including nullable role for relationship "
        "identity. Read details to interpret meaning, "
        "lifecycle, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimensional_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Dimensional Entity Name",
                                "type": "string",
                            },
                            "dimensional_attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Dimensional Attribute Name",
                                "type": "string",
                            },
                        },
                        "required": ["dimensional_entity_name", "dimensional_attribute_name"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "dimensional_attributes": {
        "description": "Complete existing DimensionalAttributeRecord "
        "entries. Preserve all fields, nested "
        "sources/memberships, lifecycle, and locks.",
        "schema": {
            "$defs": {
                "AssertionRecordKey": {
                    "additionalProperties": False,
                    "properties": {
                        "modeling_assertion_record_key": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
                            "title": "Modeling Assertion Record Key",
                            "type": "string",
                        }
                    },
                    "required": ["modeling_assertion_record_key"],
                    "title": "AssertionRecordKey",
                    "type": "object",
                },
                "AttributeAssertionSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "assertion",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "assertion_record": {"$ref": "#/$defs/AssertionRecordKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "assertion_record",
                        "rationale",
                        "status",
                        "is_locked",
                    ],
                    "title": "AttributeAssertionSourceRecord",
                    "type": "object",
                },
                "AttributePhysicalSourceRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "support_source_type": {
                            "const": "attribute",
                            "title": "Support Source Type",
                            "type": "string",
                        },
                        "source_attribute": {"$ref": "#/$defs/PhysicalAttributeKey"},
                        "source_order": {
                            "anyOf": [{"exclusiveMinimum": 0, "type": "integer"}, {"type": "null"}],
                            "default": None,
                            "title": "Source Order",
                        },
                        "rationale": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Rationale",
                            "type": "string",
                        },
                        "status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Status",
                            "type": "string",
                        },
                        "is_locked": {"title": "Is Locked", "type": "boolean"},
                    },
                    "required": [
                        "support_source_type",
                        "source_attribute",
                        "rationale",
                        "status",
                        "is_locked",
                    ],
                    "title": "AttributePhysicalSourceRecord",
                    "type": "object",
                },
                "AttributeSourceRecord": {
                    "discriminator": {
                        "mapping": {
                            "assertion": "#/$defs/AttributeAssertionSourceRecord",
                            "attribute": "#/$defs/AttributePhysicalSourceRecord",
                        },
                        "propertyName": "support_source_type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/AttributePhysicalSourceRecord"},
                        {"$ref": "#/$defs/AttributeAssertionSourceRecord"},
                    ],
                },
                "DimensionalAttributeRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "dimensional_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Entity Name",
                            "type": "string",
                        },
                        "dimensional_attribute_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Attribute Name",
                            "type": "string",
                        },
                        "dimensional_attribute_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Attribute Definition",
                            "type": "string",
                        },
                        "dimensional_attribute_data_type": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Attribute Data Type",
                            "type": "string",
                        },
                        "dimensional_attribute_is_nullable": {
                            "title": "Dimensional Attribute Is Nullable",
                            "type": "boolean",
                        },
                        "dimensional_attribute_ordinal_position": {
                            "exclusiveMinimum": 0,
                            "title": "Dimensional Attribute Ordinal Position",
                            "type": "integer",
                        },
                        "dimensional_attribute_role": {
                            "enum": [
                                "key",
                                "descriptor",
                                "measure",
                                "degenerate_dimension",
                                "bridge_weight",
                                "technical",
                                "audit",
                            ],
                            "title": "Dimensional Attribute Role",
                            "type": "string",
                        },
                        "dimensional_attribute_key_role": {
                            "enum": ["none", "surrogate", "business", "foreign"],
                            "title": "Dimensional Attribute Key Role",
                            "type": "string",
                        },
                        "dimensional_attribute_is_grain_component": {
                            "title": "Dimensional Attribute Is Grain Component",
                            "type": "boolean",
                        },
                        "dimensional_attribute_additivity": {
                            "anyOf": [
                                {
                                    "enum": ["additive", "semi_additive", "non_additive"],
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Dimensional Attribute Additivity",
                        },
                        "dimensional_attribute_default_aggregation": {
                            "anyOf": [
                                {
                                    "maxLength": 100,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Dimensional Attribute Default Aggregation",
                        },
                        "dimensional_attribute_aggregation_basis": {
                            "anyOf": [
                                {"minLength": 1, "pattern": "\\S", "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Dimensional Attribute Aggregation Basis",
                        },
                        "dimensional_attribute_change_behavior": {
                            "anyOf": [
                                {"enum": ["fixed", "overwrite", "historize"], "type": "string"},
                                {"type": "null"},
                            ],
                            "title": "Dimensional Attribute Change Behavior",
                        },
                        "dimensional_attribute_is_audit_column": {
                            "title": "Dimensional Attribute Is Audit Column",
                            "type": "boolean",
                        },
                        "dimensional_attribute_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Dimensional Attribute Confidence",
                            "type": "string",
                        },
                        "dimensional_attribute_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Dimensional Attribute Status",
                            "type": "string",
                        },
                        "dimensional_attribute_is_locked": {
                            "title": "Dimensional Attribute Is Locked",
                            "type": "boolean",
                        },
                        "sources": {
                            "items": {"$ref": "#/$defs/AttributeSourceRecord"},
                            "title": "Sources",
                            "type": "array",
                        },
                    },
                    "required": [
                        "dimensional_entity_name",
                        "dimensional_attribute_name",
                        "dimensional_attribute_definition",
                        "dimensional_attribute_data_type",
                        "dimensional_attribute_is_nullable",
                        "dimensional_attribute_ordinal_position",
                        "dimensional_attribute_role",
                        "dimensional_attribute_key_role",
                        "dimensional_attribute_is_grain_component",
                        "dimensional_attribute_additivity",
                        "dimensional_attribute_default_aggregation",
                        "dimensional_attribute_aggregation_basis",
                        "dimensional_attribute_change_behavior",
                        "dimensional_attribute_is_audit_column",
                        "dimensional_attribute_confidence",
                        "dimensional_attribute_status",
                        "dimensional_attribute_is_locked",
                        "sources",
                    ],
                    "title": "DimensionalAttributeRecord",
                    "type": "object",
                },
                "PhysicalAttributeKey": {
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
                        "connection_code": {
                            "maxLength": 100,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Connection Code",
                            "type": "string",
                        },
                        "object_schema": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Schema",
                            "type": "string",
                        },
                        "object_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Object Name",
                            "type": "string",
                        },
                        "attribute_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Attribute Name",
                            "type": "string",
                        },
                    },
                    "required": [
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                        "attribute_name",
                    ],
                    "title": "PhysicalAttributeKey",
                    "type": "object",
                },
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/DimensionalAttributeRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "dimensional_relationship_list": {
        "description": "Compact existing Dimensional relationship "
        "identities only. Retain complete natural "
        "keys, including nullable role for "
        "relationship identity. Read details to "
        "interpret meaning, lifecycle, and locks.",
        "schema": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_dimensional_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "From Dimensional Entity Name",
                                "type": "string",
                            },
                            "from_dimensional_attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "From Dimensional Attribute Name",
                                "type": "string",
                            },
                            "to_dimensional_entity_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "To Dimensional Entity Name",
                                "type": "string",
                            },
                            "to_dimensional_attribute_name": {
                                "maxLength": 255,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "To Dimensional Attribute Name",
                                "type": "string",
                            },
                            "dimensional_relationship_kind": {
                                "maxLength": 50,
                                "minLength": 1,
                                "pattern": "\\S",
                                "title": "Dimensional Relationship Kind",
                                "type": "string",
                            },
                            "dimensional_relationship_role_name": {
                                "anyOf": [
                                    {
                                        "maxLength": 255,
                                        "minLength": 1,
                                        "pattern": "\\S",
                                        "type": "string",
                                    },
                                    {"type": "null"},
                                ],
                                "title": "Dimensional Relationship Role Name",
                            },
                        },
                        "required": [
                            "from_dimensional_entity_name",
                            "from_dimensional_attribute_name",
                            "to_dimensional_entity_name",
                            "to_dimensional_attribute_name",
                            "dimensional_relationship_kind",
                            "dimensional_relationship_role_name",
                        ],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ]
        },
    },
    "dimensional_relationships": {
        "description": "Complete existing DimensionalRelationshipRecord "
        "entries. Preserve all fields, nested "
        "sources/memberships, lifecycle, and locks.",
        "schema": {
            "$defs": {
                "DimensionalRelationshipRecord": {
                    "additionalProperties": False,
                    "properties": {
                        "dimensional_relationship_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Relationship Name",
                            "type": "string",
                        },
                        "dimensional_relationship_definition": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Relationship Definition",
                            "type": "string",
                        },
                        "from_dimensional_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "From Dimensional Entity Name",
                            "type": "string",
                        },
                        "from_dimensional_attribute_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "From Dimensional Attribute Name",
                            "type": "string",
                        },
                        "to_dimensional_entity_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "To Dimensional Entity Name",
                            "type": "string",
                        },
                        "to_dimensional_attribute_name": {
                            "maxLength": 255,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "To Dimensional Attribute Name",
                            "type": "string",
                        },
                        "dimensional_relationship_kind": {
                            "maxLength": 50,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Relationship Kind",
                            "type": "string",
                        },
                        "dimensional_relationship_cardinality": {
                            "enum": ["one_to_one", "one_to_many", "many_to_one", "many_to_many"],
                            "title": "Dimensional Relationship Cardinality",
                            "type": "string",
                        },
                        "dimensional_relationship_is_optional": {
                            "title": "Dimensional Relationship Is Optional",
                            "type": "boolean",
                        },
                        "dimensional_relationship_role_name": {
                            "anyOf": [
                                {
                                    "maxLength": 255,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Dimensional Relationship Role Name",
                        },
                        "dimensional_relationship_confidence": {
                            "enum": ["low", "medium", "high"],
                            "title": "Dimensional Relationship Confidence",
                            "type": "string",
                        },
                        "dimensional_relationship_basis": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Relationship Basis",
                            "type": "string",
                        },
                        "dimensional_relationship_cardinality_basis": {
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Dimensional Relationship Cardinality Basis",
                            "type": "string",
                        },
                        "dimensional_relationship_status": {
                            "enum": ["active", "inactive", "deprecated"],
                            "title": "Dimensional Relationship Status",
                            "type": "string",
                        },
                        "dimensional_relationship_is_locked": {
                            "title": "Dimensional Relationship Is Locked",
                            "type": "boolean",
                        },
                    },
                    "required": [
                        "dimensional_relationship_name",
                        "dimensional_relationship_definition",
                        "from_dimensional_entity_name",
                        "from_dimensional_attribute_name",
                        "to_dimensional_entity_name",
                        "to_dimensional_attribute_name",
                        "dimensional_relationship_kind",
                        "dimensional_relationship_cardinality",
                        "dimensional_relationship_is_optional",
                        "dimensional_relationship_role_name",
                        "dimensional_relationship_confidence",
                        "dimensional_relationship_basis",
                        "dimensional_relationship_cardinality_basis",
                        "dimensional_relationship_status",
                        "dimensional_relationship_is_locked",
                    ],
                    "title": "DimensionalRelationshipRecord",
                    "type": "object",
                }
            },
            "anyOf": [
                {"items": {"$ref": "#/$defs/DimensionalRelationshipRecord"}, "type": "array"},
                {"type": "null"},
            ],
        },
    },
    "logical_bindings": {
        "description": "Compact active upstream binding projection: one selected "
        "eligible Silver Object key, its Logical Entity name, and "
        "eligible selected physical-to-Logical Attribute name "
        "pairs. Identity link only; no repeated Logical "
        "definitions, Mapping bodies, downstream dependency "
        "records, or IDs.",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
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
                    "connection_code": {
                        "maxLength": 100,
                        "minLength": 1,
                        "pattern": "\\S",
                        "title": "Connection Code",
                        "type": "string",
                    },
                    "object_schema": {
                        "maxLength": 400,
                        "minLength": 1,
                        "pattern": "\\S",
                        "title": "Object Schema",
                        "type": "string",
                    },
                    "object_name": {
                        "maxLength": 400,
                        "minLength": 1,
                        "pattern": "\\S",
                        "title": "Object Name",
                        "type": "string",
                    },
                    "logical_entity_name": {
                        "maxLength": 255,
                        "minLength": 1,
                        "pattern": "\\S",
                        "title": "Logical Entity Name",
                        "type": "string",
                    },
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "attribute_name": {
                                    "maxLength": 400,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "title": "Attribute Name",
                                    "type": "string",
                                },
                                "logical_attribute_name": {
                                    "maxLength": 255,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "title": "Logical Attribute Name",
                                    "type": "string",
                                },
                            },
                            "required": ["attribute_name", "logical_attribute_name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "logical_entity_name",
                    "attributes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "dimensional.naming_instructions": {
        "description": "Effective Gold naming override, otherwise "
        "the existing Dimensional default: "
        "PascalCase names and key Attributes ending "
        "in Key. Preserve existing identities.",
        "schema": {"maxLength": 32768, "minLength": 1, "pattern": "\\S", "type": "string"},
    },
    "dimensional.audit_columns": {
        "description": "Exact required Gold audit template. Same "
        "schema_version/ordered columns layout as Logical "
        "audit settings. Each column has semantic_name, "
        "data_type, nullable, definition. Gold requires "
        "this template before model execution.",
        "schema": {
            "$defs": {
                "GoldPolicyColumn": {
                    "additionalProperties": False,
                    "properties": {
                        "semantic_name": {"$ref": "#/$defs/_Nonblank255"},
                        "data_type": {"$ref": "#/$defs/_Nonblank100"},
                        "nullable": {"title": "Nullable", "type": "boolean"},
                        "definition": {
                            "anyOf": [{"$ref": "#/$defs/_Nonblank2000"}, {"type": "null"}]
                        },
                    },
                    "required": ["semantic_name", "data_type", "nullable", "definition"],
                    "title": "GoldPolicyColumn",
                    "type": "object",
                },
                "_Nonblank100": {
                    "maxLength": 100,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Nonblank2000": {
                    "maxLength": 2000,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Nonblank255": {
                    "maxLength": 255,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
            },
            "additionalProperties": False,
            "properties": {
                "schema_version": {
                    "const": "1.0",
                    "default": "1.0",
                    "title": "Schema Version",
                    "type": "string",
                },
                "columns": {
                    "items": {"$ref": "#/$defs/GoldPolicyColumn"},
                    "maxItems": 32,
                    "minItems": 1,
                    "title": "Columns",
                    "type": "array",
                },
            },
            "required": ["columns"],
            "title": "GoldAuditPolicy",
            "type": "object",
        },
    },
    "dimensional.technical_columns": {
        "description": "Exact required GoldTechnicalPolicy: "
        "schema_version, dimension_surrogate_key, "
        "fact_bridge_foreign_key, type_2. Do not add "
        "guessed policy fields. The current backend "
        "projects "
        "technical/surrogate/foreign-key/audit "
        "Attributes.",
        "schema": {
            "$defs": {
                "GoldPolicyColumn": {
                    "additionalProperties": False,
                    "properties": {
                        "semantic_name": {"$ref": "#/$defs/_Nonblank255"},
                        "data_type": {"$ref": "#/$defs/_Nonblank100"},
                        "nullable": {"title": "Nullable", "type": "boolean"},
                        "definition": {
                            "anyOf": [{"$ref": "#/$defs/_Nonblank2000"}, {"type": "null"}]
                        },
                    },
                    "required": ["semantic_name", "data_type", "nullable", "definition"],
                    "title": "GoldPolicyColumn",
                    "type": "object",
                },
                "_DimensionSurrogateKey": {
                    "additionalProperties": False,
                    "properties": {
                        "semantic_name_template": {"$ref": "#/$defs/_Nonblank255"},
                        "data_type": {"$ref": "#/$defs/_Nonblank100"},
                        "nullable": {"const": False, "title": "Nullable", "type": "boolean"},
                        "definition_template": {"$ref": "#/$defs/_Nonblank2000"},
                    },
                    "required": [
                        "semantic_name_template",
                        "data_type",
                        "nullable",
                        "definition_template",
                    ],
                    "title": "_DimensionSurrogateKey",
                    "type": "object",
                },
                "_FactBridgeForeignKey": {
                    "additionalProperties": False,
                    "properties": {
                        "with_role_semantic_name_template": {"$ref": "#/$defs/_Nonblank255"},
                        "without_role_semantic_name_template": {"$ref": "#/$defs/_Nonblank255"},
                        "definition_template": {"$ref": "#/$defs/_Nonblank2000"},
                    },
                    "required": [
                        "with_role_semantic_name_template",
                        "without_role_semantic_name_template",
                        "definition_template",
                    ],
                    "title": "_FactBridgeForeignKey",
                    "type": "object",
                },
                "_Nonblank100": {
                    "maxLength": 100,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Nonblank2000": {
                    "maxLength": 2000,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Nonblank255": {
                    "maxLength": 255,
                    "minLength": 1,
                    "pattern": "\\S",
                    "type": "string",
                },
                "_Type2Policy": {
                    "additionalProperties": False,
                    "properties": {
                        "effective_from": {"$ref": "#/$defs/GoldPolicyColumn"},
                        "effective_to": {"$ref": "#/$defs/GoldPolicyColumn"},
                        "is_current": {"$ref": "#/$defs/GoldPolicyColumn"},
                    },
                    "required": ["effective_from", "effective_to", "is_current"],
                    "title": "_Type2Policy",
                    "type": "object",
                },
            },
            "additionalProperties": False,
            "properties": {
                "schema_version": {
                    "const": "1.0",
                    "default": "1.0",
                    "title": "Schema Version",
                    "type": "string",
                },
                "dimension_surrogate_key": {"$ref": "#/$defs/_DimensionSurrogateKey"},
                "fact_bridge_foreign_key": {"$ref": "#/$defs/_FactBridgeForeignKey"},
                "type_2": {"$ref": "#/$defs/_Type2Policy"},
            },
            "required": ["dimension_surrogate_key", "fact_bridge_foreign_key", "type_2"],
            "title": "GoldTechnicalPolicy",
            "type": "object",
        },
    },
}

WORKFLOW_INPUTS: dict[str, dict[str, str]] = {
    "analysis": {
        "source_context": "source_context",
        "gds_context": "gds_context",
        "object_context": "object_context",
        "object_attribute_context": "object_attribute_context",
        "ingestion_mapping": "ingestion_mapping",
        "object_relationship_context": "object_relationship_context",
        "modeling_assertions": "modeling_assertions",
    },
    "conceptual": {
        "source_context": "source_context",
        "gds_context": "gds_context",
        "object_context": "object_context",
        "object_attribute_context": "object_attribute_context",
        "ingestion_mapping": "ingestion_mapping",
        "object_relationship_context": "object_relationship_context",
        "modeling_assertions": "modeling_assertions",
        "conceptual_object_list": "conceptual_object_list",
        "conceptual_objects": "conceptual_objects",
        "conceptual_relationship_list": "conceptual_relationship_list",
        "conceptual_relationships": "conceptual_relationships",
    },
    "logical": {
        "source_context": "source_context",
        "gds_context": "gds_context",
        "object_context": "object_context",
        "object_attribute_context": "object_attribute_context",
        "ingestion_mapping": "ingestion_mapping",
        "object_relationship_context": "object_relationship_context",
        "modeling_assertions": "modeling_assertions",
        "conceptual_object_list": "conceptual_object_list",
        "conceptual_objects": "conceptual_objects",
        "conceptual_relationship_list": "conceptual_relationship_list",
        "conceptual_relationships": "conceptual_relationships",
        "logical_submodel_list": "logical_submodel_list",
        "logical_submodels": "logical_submodels",
        "logical_entity_list": "logical_entity_list",
        "logical_entities": "logical_entities",
        "logical_attribute_list": "logical_attribute_list",
        "logical_attributes": "logical_attributes",
        "logical_relationship_list": "logical_relationship_list",
        "logical_relationships": "logical_relationships",
        "naming_instructions": "logical.naming_instructions",
        "audit_columns": "logical.audit_columns",
    },
    "dimensional": {
        "logical_submodel_list": "logical_submodel_list",
        "logical_submodels": "logical_submodels",
        "logical_entity_list": "logical_entity_list",
        "logical_entities": "logical_entities",
        "logical_attribute_list": "logical_attribute_list",
        "logical_attributes": "logical_attributes",
        "logical_relationship_list": "logical_relationship_list",
        "logical_relationships": "logical_relationships",
        "dimensional_submodel_list": "dimensional_submodel_list",
        "dimensional_submodels": "dimensional_submodels",
        "dimensional_entity_list": "dimensional_entity_list",
        "dimensional_entities": "dimensional_entities",
        "dimensional_attribute_list": "dimensional_attribute_list",
        "dimensional_attributes": "dimensional_attributes",
        "dimensional_relationship_list": "dimensional_relationship_list",
        "dimensional_relationships": "dimensional_relationships",
        "gds_context": "gds_context",
        "object_context": "object_context",
        "object_attribute_context": "object_attribute_context",
        "modeling_assertions": "modeling_assertions",
        "logical_bindings": "logical_bindings",
        "naming_instructions": "dimensional.naming_instructions",
        "audit_columns": "dimensional.audit_columns",
        "technical_columns": "dimensional.technical_columns",
    },
}

INPUT_EXAMPLES: dict[str, dict[str, Any]] = {
    "analysis": {
        "source_context": [
            {
                "tenant_code": "ACME",
                "tenant_description": "Wholesale distribution business.",
                "system_code": "ERP",
                "system_description": "Manages sales orders and billing.",
                "system_type_code": "ERP",
                "system_type_description": "Systems for managing core business operations.",
                "connection_code": "ERP_SOURCE",
                "connection_description": None,
                "connection_type_code": "SQL_SERVER",
                "connection_type_description": "Connection to a Microsoft SQL Server database.",
                "zone_code": "source",
                "zone_description": "Originating source data.",
            }
        ],
        "gds_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "zone_code": "bronze",
                "zone_description": "Stores ingested source data.",
            }
        ],
        "object_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "object_description": "Sales orders; one row represents one order.",
                "zone_code": "bronze",
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "object_description": "ERP customer accounts; one row per customer account.",
                "zone_code": "bronze",
            },
        ],
        "object_attribute_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "attributes": [
                    {
                        "attribute_name": "CustomerCode",
                        "attribute_description": "ERP customer account that placed this order.",
                        "attribute_data_type": "VARCHAR",
                        "attribute_inferred_data_type": "VARCHAR",
                        "attribute_nullability": False,
                        "is_natural_key": False,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": {
                            "profiled_at": "2026-09-07T14:30:00Z",
                            "row_scope": "all_rows",
                            "batch_attribute_name": None,
                            "batch_id": None,
                            "row_count": 1000,
                            "non_null_count": 1000,
                            "null_count": 0,
                            "blank_count": 0,
                            "distinct_count": 100,
                            "min_data_length": 6,
                            "max_data_length": 6,
                            "avg_data_length": 6,
                            "percent_populated": 100,
                            "percent_duplicates": 90,
                            "percent_null": 0,
                            "percent_blank": 0,
                            "percent_distinct": 10,
                        },
                    }
                ],
                "selected_attribute_names": ["CustomerCode"],
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "attributes": [
                    {
                        "attribute_name": "CustomerCode",
                        "attribute_description": "Business "
                        "identifier "
                        "of this "
                        "ERP "
                        "customer "
                        "account.",
                        "attribute_data_type": "VARCHAR",
                        "attribute_inferred_data_type": "VARCHAR",
                        "attribute_nullability": False,
                        "is_natural_key": True,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": {
                            "profiled_at": "2026-09-07T14:30:00Z",
                            "row_scope": "all_rows",
                            "batch_attribute_name": None,
                            "batch_id": None,
                            "row_count": 100,
                            "non_null_count": 100,
                            "null_count": 0,
                            "blank_count": 0,
                            "distinct_count": 100,
                            "min_data_length": 6,
                            "max_data_length": 6,
                            "avg_data_length": 6,
                            "percent_populated": 100,
                            "percent_duplicates": 0,
                            "percent_null": 0,
                            "percent_blank": 0,
                            "percent_distinct": 100,
                        },
                    }
                ],
                "selected_attribute_names": ["CustomerCode"],
            },
        ],
        "ingestion_mapping": [
            {
                "source": {
                    "tenant_code": "ACME",
                    "system_code": "ERP",
                    "connection_code": "ERP_SOURCE",
                    "object_schema": "sales",
                    "object_name": "SalesOrder",
                    "object_description": "Sales orders created in ERP; one row per order.",
                },
                "target": {
                    "tenant_code": "GDS",
                    "system_code": "WAREHOUSE",
                    "connection_code": "MAIN",
                    "object_schema": "bronze",
                    "object_name": "Orders",
                },
            },
            {
                "source": {
                    "tenant_code": "ACME",
                    "system_code": "ERP",
                    "connection_code": "ERP_SOURCE",
                    "object_schema": "sales",
                    "object_name": "Customer",
                    "object_description": "ERP customer accounts; one row per customer account.",
                },
                "target": {
                    "tenant_code": "GDS",
                    "system_code": "WAREHOUSE",
                    "connection_code": "MAIN",
                    "object_schema": "bronze",
                    "object_name": "Customers",
                },
            },
        ],
        "object_relationship_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "incoming_relationships": [],
                "outgoing_relationships": [],
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "incoming_relationships": [],
                "outgoing_relationships": [],
            },
        ],
        "modeling_assertions": [
            {
                "modeling_assertion_record_key": "order_customer_reference",
                "modeling_assertion_document_name": "ERP relationship notes",
                "modeling_assertion_record_type": "relationship",
                "modeling_assertion_text": "Within this ERP source, "
                "Orders.CustomerCode "
                "references the customer "
                "account identified by "
                "Customers.CustomerCode.",
                "modeling_assertion_details": {
                    "from": {
                        "tenant_code": "GDS",
                        "system_code": "WAREHOUSE",
                        "connection_code": "MAIN",
                        "object_schema": "bronze",
                        "object_name": "Orders",
                        "attribute_name": "CustomerCode",
                    },
                    "to": {
                        "tenant_code": "GDS",
                        "system_code": "WAREHOUSE",
                        "connection_code": "MAIN",
                        "object_schema": "bronze",
                        "object_name": "Customers",
                        "attribute_name": "CustomerCode",
                    },
                },
                "modeling_assertion_source_location": {"section": "Orders and customers"},
                "modeling_assertion_confidence": "high",
            }
        ],
    },
    "conceptual": {
        "source_context": [
            {
                "tenant_code": "ACME",
                "tenant_description": "Wholesale distribution business.",
                "system_code": "ERP",
                "system_description": "Manages sales orders and billing.",
                "system_type_code": "ERP",
                "system_type_description": "Systems for managing core business operations.",
                "connection_code": "ERP_SOURCE",
                "connection_description": None,
                "connection_type_code": "SQL_SERVER",
                "connection_type_description": "Connection to a Microsoft SQL Server database.",
                "zone_code": "source",
                "zone_description": "Originating source data.",
            }
        ],
        "gds_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "zone_code": "bronze",
                "zone_description": "Stores ingested source data.",
            }
        ],
        "object_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "object_description": "Sales orders; one row represents one order.",
                "zone_code": "bronze",
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "object_description": "ERP customer accounts; one row per customer account.",
                "zone_code": "bronze",
            },
        ],
        "object_attribute_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "attributes": [
                    {
                        "attribute_name": "CustomerCode",
                        "attribute_description": "ERP customer account that placed this order.",
                        "attribute_data_type": "VARCHAR",
                        "attribute_inferred_data_type": "VARCHAR",
                        "attribute_nullability": False,
                        "is_natural_key": False,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": {
                            "profiled_at": "2026-09-07T14:30:00Z",
                            "row_scope": "all_rows",
                            "batch_attribute_name": None,
                            "batch_id": None,
                            "row_count": 1000,
                            "non_null_count": 1000,
                            "null_count": 0,
                            "blank_count": 0,
                            "distinct_count": 100,
                            "min_data_length": 6,
                            "max_data_length": 6,
                            "avg_data_length": 6,
                            "percent_populated": 100,
                            "percent_duplicates": 90,
                            "percent_null": 0,
                            "percent_blank": 0,
                            "percent_distinct": 10,
                        },
                    }
                ],
                "selected_attribute_names": ["CustomerCode"],
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "attributes": [
                    {
                        "attribute_name": "CustomerCode",
                        "attribute_description": "Business "
                        "identifier "
                        "of this "
                        "ERP "
                        "customer "
                        "account.",
                        "attribute_data_type": "VARCHAR",
                        "attribute_inferred_data_type": "VARCHAR",
                        "attribute_nullability": False,
                        "is_natural_key": True,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": {
                            "profiled_at": "2026-09-07T14:30:00Z",
                            "row_scope": "all_rows",
                            "batch_attribute_name": None,
                            "batch_id": None,
                            "row_count": 100,
                            "non_null_count": 100,
                            "null_count": 0,
                            "blank_count": 0,
                            "distinct_count": 100,
                            "min_data_length": 6,
                            "max_data_length": 6,
                            "avg_data_length": 6,
                            "percent_populated": 100,
                            "percent_duplicates": 0,
                            "percent_null": 0,
                            "percent_blank": 0,
                            "percent_distinct": 100,
                        },
                    }
                ],
                "selected_attribute_names": ["CustomerCode"],
            },
        ],
        "ingestion_mapping": [
            {
                "source": {
                    "tenant_code": "ACME",
                    "system_code": "ERP",
                    "connection_code": "ERP_SOURCE",
                    "object_schema": "sales",
                    "object_name": "SalesOrder",
                    "object_description": "Sales orders created in ERP; one row per order.",
                },
                "target": {
                    "tenant_code": "GDS",
                    "system_code": "WAREHOUSE",
                    "connection_code": "MAIN",
                    "object_schema": "bronze",
                    "object_name": "Orders",
                },
            },
            {
                "source": {
                    "tenant_code": "ACME",
                    "system_code": "ERP",
                    "connection_code": "ERP_SOURCE",
                    "object_schema": "sales",
                    "object_name": "Customer",
                    "object_description": "ERP customer accounts; one row per customer account.",
                },
                "target": {
                    "tenant_code": "GDS",
                    "system_code": "WAREHOUSE",
                    "connection_code": "MAIN",
                    "object_schema": "bronze",
                    "object_name": "Customers",
                },
            },
        ],
        "object_relationship_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "incoming_relationships": [],
                "outgoing_relationships": [],
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "incoming_relationships": [],
                "outgoing_relationships": [],
            },
        ],
        "modeling_assertions": [
            {
                "modeling_assertion_record_key": "order_customer_reference",
                "modeling_assertion_document_name": "ERP relationship notes",
                "modeling_assertion_record_type": "relationship",
                "modeling_assertion_text": "Within this ERP source, "
                "Orders.CustomerCode "
                "references the customer "
                "account identified by "
                "Customers.CustomerCode.",
                "modeling_assertion_details": {
                    "from": {
                        "tenant_code": "GDS",
                        "system_code": "WAREHOUSE",
                        "connection_code": "MAIN",
                        "object_schema": "bronze",
                        "object_name": "Orders",
                        "attribute_name": "CustomerCode",
                    },
                    "to": {
                        "tenant_code": "GDS",
                        "system_code": "WAREHOUSE",
                        "connection_code": "MAIN",
                        "object_schema": "bronze",
                        "object_name": "Customers",
                        "attribute_name": "CustomerCode",
                    },
                },
                "modeling_assertion_source_location": {"section": "Orders and customers"},
                "modeling_assertion_confidence": "high",
            }
        ],
        "conceptual_object_list": [],
        "conceptual_objects": [],
        "conceptual_relationship_list": [],
        "conceptual_relationships": [],
    },
    "logical": {
        "source_context": [
            {
                "tenant_code": "ACME",
                "tenant_description": "Wholesale distribution business.",
                "system_code": "ERP",
                "system_description": "Manages sales orders and billing.",
                "system_type_code": "ERP",
                "system_type_description": "Systems for managing core business operations.",
                "connection_code": "ERP_SOURCE",
                "connection_description": None,
                "connection_type_code": "SQL_SERVER",
                "connection_type_description": "Connection to a Microsoft SQL Server database.",
                "zone_code": "source",
                "zone_description": "Originating source data.",
            }
        ],
        "gds_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "zone_code": "bronze",
                "zone_description": "Stores ingested source data.",
            }
        ],
        "object_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "object_description": "Sales orders; one row represents one order.",
                "zone_code": "bronze",
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "object_description": "ERP customer accounts; one row per customer account.",
                "zone_code": "bronze",
            },
        ],
        "object_attribute_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "attributes": [
                    {
                        "attribute_name": "order_id",
                        "attribute_description": "Stable "
                        "identifier "
                        "of one "
                        "order "
                        "within this "
                        "ERP source.",
                        "attribute_data_type": "BIGINT",
                        "attribute_inferred_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "is_natural_key": True,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": None,
                    },
                    {
                        "attribute_name": "customer_id",
                        "attribute_description": "ERP customer account that placed this order.",
                        "attribute_data_type": "BIGINT",
                        "attribute_inferred_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "is_natural_key": False,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": None,
                    },
                ],
                "selected_attribute_names": ["order_id", "customer_id"],
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "attributes": [
                    {
                        "attribute_name": "customer_id",
                        "attribute_description": "Business "
                        "identifier "
                        "of this ERP "
                        "customer "
                        "account.",
                        "attribute_data_type": "BIGINT",
                        "attribute_inferred_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "is_natural_key": True,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": None,
                    }
                ],
                "selected_attribute_names": ["customer_id"],
            },
        ],
        "ingestion_mapping": [
            {
                "source": {
                    "tenant_code": "ACME",
                    "system_code": "ERP",
                    "connection_code": "ERP_SOURCE",
                    "object_schema": "sales",
                    "object_name": "SalesOrder",
                    "object_description": "Sales orders created in ERP; one row per order.",
                },
                "target": {
                    "tenant_code": "GDS",
                    "system_code": "WAREHOUSE",
                    "connection_code": "MAIN",
                    "object_schema": "bronze",
                    "object_name": "Orders",
                },
            },
            {
                "source": {
                    "tenant_code": "ACME",
                    "system_code": "ERP",
                    "connection_code": "ERP_SOURCE",
                    "object_schema": "sales",
                    "object_name": "Customer",
                    "object_description": "ERP customer accounts; one row per customer account.",
                },
                "target": {
                    "tenant_code": "GDS",
                    "system_code": "WAREHOUSE",
                    "connection_code": "MAIN",
                    "object_schema": "bronze",
                    "object_name": "Customers",
                },
            },
        ],
        "object_relationship_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Orders",
                "incoming_relationships": [],
                "outgoing_relationships": [],
            },
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "bronze",
                "object_name": "Customers",
                "incoming_relationships": [],
                "outgoing_relationships": [],
            },
        ],
        "modeling_assertions": [
            {
                "modeling_assertion_record_key": "order_customer_reference",
                "modeling_assertion_document_name": "ERP relationship notes",
                "modeling_assertion_record_type": "relationship",
                "modeling_assertion_text": "Within this ERP source, "
                "Orders.order_id identifies one "
                "order. Each order belongs to "
                "exactly one customer "
                "identified by "
                "Customers.customer_id through "
                "Orders.customer_id; one "
                "customer may have many orders. "
                "Customer IDs are stable within "
                "this source.",
                "modeling_assertion_details": {},
                "modeling_assertion_source_location": {"section": "Orders and customers"},
                "modeling_assertion_confidence": "high",
            }
        ],
        "conceptual_object_list": [],
        "conceptual_objects": [],
        "conceptual_relationship_list": [],
        "conceptual_relationships": [],
        "logical_submodel_list": [{"logical_submodel_name": "Sales"}],
        "logical_submodels": [
            {
                "logical_submodel_name": "Sales",
                "logical_submodel_definition": "Customer and order management.",
                "logical_submodel_status": "active",
                "logical_submodel_is_locked": False,
            }
        ],
        "logical_entity_list": [
            {"logical_entity_name": "Customer"},
            {"logical_entity_name": "Order"},
        ],
        "logical_entities": [
            {
                "logical_entity_name": "Customer",
                "logical_entity_definition": "A recorded business customer.",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One row per customer.",
                "logical_entity_dependency_order": 0,
                "logical_entity_confidence": "high",
                "logical_entity_status": "active",
                "logical_entity_is_locked": True,
                "submodels": [
                    {
                        "submodel_name": "Sales",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Customers",
                        },
                        "source_order": 1,
                        "rationale": "Registered physical source for this Entity.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "logical_entity_name": "Order",
                "logical_entity_definition": "A recorded business order.",
                "logical_entity_type": "transaction",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One row per order.",
                "logical_entity_dependency_order": 1,
                "logical_entity_confidence": "high",
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "submodels": [
                    {
                        "submodel_name": "Sales",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Orders",
                        },
                        "source_order": 1,
                        "rationale": "Registered physical source for this Entity.",
                        "status": "active",
                        "is_locked": False,
                    },
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {
                            "modeling_assertion_record_key": "order_customer_reference"
                        },
                        "source_order": 2,
                        "rationale": "Approved rule defines each Order "
                        "as belonging to one Customer.",
                        "status": "active",
                        "is_locked": False,
                    },
                ],
            },
        ],
        "logical_attribute_list": [
            {"logical_entity_name": "Customer", "logical_attribute_name": "CustomerId"},
            {"logical_entity_name": "Order", "logical_attribute_name": "OrderId"},
            {"logical_entity_name": "Order", "logical_attribute_name": "CustomerId"},
        ],
        "logical_attributes": [
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "CustomerId",
                "logical_attribute_definition": "CustomerId recorded for this Customer.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": True,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 1,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": True,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Customers",
                            "attribute_name": "customer_id",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "logical_entity_name": "Order",
                "logical_attribute_name": "OrderId",
                "logical_attribute_definition": "OrderId recorded for this Order.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": True,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 1,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Orders",
                            "attribute_name": "order_id",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "logical_entity_name": "Order",
                "logical_attribute_name": "CustomerId",
                "logical_attribute_definition": "CustomerId recorded for this Order.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": False,
                "logical_attribute_is_natural_key": False,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 2,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Orders",
                            "attribute_name": "customer_id",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    },
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {
                            "modeling_assertion_record_key": "order_customer_reference"
                        },
                        "source_order": 2,
                        "rationale": "Approved rule defines each Order "
                        "as belonging to one Customer.",
                        "status": "active",
                        "is_locked": False,
                    },
                ],
            },
        ],
        "logical_relationship_list": [
            {
                "from_logical_entity_name": "Order",
                "from_logical_attribute_name": "CustomerId",
                "to_logical_entity_name": "Customer",
                "to_logical_attribute_name": "CustomerId",
                "logical_relationship_name": "OrderCustomer",
            }
        ],
        "logical_relationships": [
            {
                "logical_relationship_name": "OrderCustomer",
                "logical_relationship_definition": "An Order belongs to "
                "one Customer; a "
                "Customer may have "
                "many Orders.",
                "from_logical_entity_name": "Order",
                "from_logical_attribute_name": "CustomerId",
                "to_logical_entity_name": "Customer",
                "to_logical_attribute_name": "CustomerId",
                "logical_relationship_cardinality": "many_to_one",
                "logical_relationship_confidence": "high",
                "logical_relationship_basis": "The saved business rule "
                "identifies the Order "
                "customer reference.",
                "logical_relationship_cardinality_basis": "The rule "
                "requires one "
                "Customer per "
                "Order and "
                "permits many "
                "Orders per "
                "Customer.",
                "logical_relationship_status": "active",
                "logical_relationship_is_locked": False,
            }
        ],
        "naming_instructions": "Use PascalCase for Logical entity, attribute, and "
        "relationship names. Identifier Attribute names end with ID, "
        "with both I and D uppercase.",
        "audit_columns": {
            "schema_version": "1.0",
            "columns": [
                {
                    "semantic_name": "CreatedAt",
                    "data_type": "timestamp",
                    "nullable": False,
                    "definition": "Time the target row was created.",
                },
                {
                    "semantic_name": "UpdatedAt",
                    "data_type": "timestamp",
                    "nullable": True,
                    "definition": "Time the target row was last updated.",
                },
            ],
        },
    },
    "dimensional": {
        "logical_submodel_list": [],
        "logical_submodels": [
            {
                "logical_submodel_name": "Sales",
                "logical_submodel_definition": "Customer and order management.",
                "logical_submodel_status": "active",
                "logical_submodel_is_locked": False,
            }
        ],
        "logical_entity_list": [],
        "logical_entities": [
            {
                "logical_entity_name": "Customer",
                "logical_entity_definition": "A recorded business customer.",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One row per customer.",
                "logical_entity_dependency_order": 0,
                "logical_entity_confidence": "high",
                "logical_entity_status": "active",
                "logical_entity_is_locked": True,
                "submodels": [
                    {
                        "submodel_name": "Sales",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Customers",
                        },
                        "source_order": 1,
                        "rationale": "Registered physical source for this Entity.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "logical_entity_name": "Order",
                "logical_entity_definition": "A recorded business order.",
                "logical_entity_type": "transaction",
                "logical_entity_type_detail": None,
                "logical_entity_grain": "One row per order.",
                "logical_entity_dependency_order": 1,
                "logical_entity_confidence": "high",
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "submodels": [
                    {
                        "submodel_name": "Sales",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "object",
                        "source_object": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Orders",
                        },
                        "source_order": 1,
                        "rationale": "Registered physical source for this Entity.",
                        "status": "active",
                        "is_locked": False,
                    },
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {
                            "modeling_assertion_record_key": "order_customer_reference"
                        },
                        "source_order": 2,
                        "rationale": "Approved rule defines each "
                        "Order as belonging to one "
                        "Customer.",
                        "status": "active",
                        "is_locked": False,
                    },
                ],
            },
        ],
        "logical_attribute_list": [],
        "logical_attributes": [
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "CustomerId",
                "logical_attribute_definition": "CustomerId recorded for this Customer.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": True,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 1,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": True,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Customers",
                            "attribute_name": "customer_id",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "logical_entity_name": "Order",
                "logical_attribute_name": "OrderId",
                "logical_attribute_definition": "OrderId recorded for this Order.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": True,
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 1,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Orders",
                            "attribute_name": "order_id",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "logical_entity_name": "Order",
                "logical_attribute_name": "CustomerId",
                "logical_attribute_definition": "CustomerId recorded for this Order.",
                "logical_attribute_data_type": "bigint",
                "logical_attribute_is_nullable": False,
                "logical_attribute_is_primary_key": False,
                "logical_attribute_is_natural_key": False,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 2,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Orders",
                            "attribute_name": "customer_id",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    },
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {
                            "modeling_assertion_record_key": "order_customer_reference"
                        },
                        "source_order": 2,
                        "rationale": "Approved rule defines each "
                        "Order as belonging to one "
                        "Customer.",
                        "status": "active",
                        "is_locked": False,
                    },
                ],
            },
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "CustomerName",
                "logical_attribute_definition": "Recorded customer display name.",
                "logical_attribute_data_type": "string",
                "logical_attribute_is_nullable": True,
                "logical_attribute_is_primary_key": False,
                "logical_attribute_is_natural_key": False,
                "logical_attribute_is_surrogate_key": False,
                "logical_attribute_ordinal_position": 2,
                "logical_attribute_is_audit_column": False,
                "logical_attribute_status": "active",
                "logical_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "attribute",
                        "source_attribute": {
                            "tenant_code": "GDS",
                            "system_code": "WAREHOUSE",
                            "connection_code": "MAIN",
                            "object_schema": "bronze",
                            "object_name": "Customers",
                            "attribute_name": "customer_name",
                        },
                        "source_order": 1,
                        "rationale": "Recorded source for this Attribute.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
        ],
        "logical_relationship_list": [],
        "logical_relationships": [
            {
                "logical_relationship_name": "OrderCustomer",
                "logical_relationship_definition": "An Order belongs "
                "to one Customer; "
                "a Customer may "
                "have many "
                "Orders.",
                "from_logical_entity_name": "Order",
                "from_logical_attribute_name": "CustomerId",
                "to_logical_entity_name": "Customer",
                "to_logical_attribute_name": "CustomerId",
                "logical_relationship_cardinality": "many_to_one",
                "logical_relationship_confidence": "high",
                "logical_relationship_basis": "The saved business "
                "rule identifies the "
                "Order customer "
                "reference.",
                "logical_relationship_cardinality_basis": "The rule "
                "requires "
                "one "
                "Customer "
                "per Order "
                "and "
                "permits "
                "many "
                "Orders "
                "per "
                "Customer.",
                "logical_relationship_status": "active",
                "logical_relationship_is_locked": False,
            }
        ],
        "dimensional_submodel_list": [{"dimensional_submodel_name": "SalesMart"}],
        "dimensional_submodels": [
            {
                "dimensional_submodel_name": "SalesMart",
                "dimensional_submodel_definition": "Sales analytics.",
                "dimensional_submodel_status": "active",
                "dimensional_submodel_is_locked": False,
            }
        ],
        "dimensional_entity_list": [
            {"dimensional_entity_name": "SalesFact"},
            {"dimensional_entity_name": "CustomerDimension"},
        ],
        "dimensional_entities": [
            {
                "dimensional_entity_name": "SalesFact",
                "dimensional_entity_definition": "A transaction fact "
                "recording one "
                "governed sales "
                "order.",
                "dimensional_entity_type": "fact",
                "dimensional_fact_type": "transaction",
                "dimensional_entity_grain_definition": "One sales "
                "order within "
                "the governed "
                "source "
                "identity "
                "scope.",
                "dimensional_entity_dependency_order": 0,
                "dimensional_entity_confidence": "high",
                "dimensional_entity_status": "active",
                "dimensional_entity_is_locked": False,
                "submodels": [
                    {
                        "submodel_name": "SalesMart",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_role": "business_rule",
                        "source_order": 1,
                        "rationale": "Approved dimensional requirement.",
                        "status": "active",
                        "is_locked": False,
                    },
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "sales_order_count"},
                        "source_order": 2,
                        "rationale": "The confirmed rule defines "
                        "one order per fact row and "
                        "a count of one for that "
                        "row.",
                        "status": "active",
                        "is_locked": False,
                        "source_role": "grain_rule",
                    },
                ],
            },
            {
                "dimensional_entity_name": "CustomerDimension",
                "dimensional_entity_definition": "CustomerDimension entity.",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "dimensional_entity_dependency_order": 0,
                "dimensional_entity_confidence": "high",
                "dimensional_entity_status": "active",
                "dimensional_entity_is_locked": True,
                "submodels": [
                    {
                        "submodel_name": "SalesMart",
                        "membership_status": "active",
                        "membership_is_locked": False,
                    }
                ],
                "sources": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_role": "business_rule",
                        "source_order": 1,
                        "rationale": "Approved dimensional requirement.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
        ],
        "dimensional_attribute_list": [
            {"dimensional_entity_name": "SalesFact", "dimensional_attribute_name": "SalesKey"},
            {"dimensional_entity_name": "SalesFact", "dimensional_attribute_name": "CustomerKey"},
            {"dimensional_entity_name": "SalesFact", "dimensional_attribute_name": "OrderCount"},
            {
                "dimensional_entity_name": "CustomerDimension",
                "dimensional_attribute_name": "CustomerKey",
            },
        ],
        "dimensional_attributes": [
            {
                "dimensional_entity_name": "SalesFact",
                "dimensional_attribute_name": "SalesKey",
                "dimensional_attribute_definition": "SalesKey attribute.",
                "dimensional_attribute_data_type": "bigint",
                "dimensional_attribute_is_nullable": False,
                "dimensional_attribute_ordinal_position": 1,
                "dimensional_attribute_role": "key",
                "dimensional_attribute_key_role": "surrogate",
                "dimensional_attribute_is_grain_component": True,
                "dimensional_attribute_additivity": None,
                "dimensional_attribute_default_aggregation": None,
                "dimensional_attribute_aggregation_basis": None,
                "dimensional_attribute_change_behavior": None,
                "dimensional_attribute_is_audit_column": False,
                "dimensional_attribute_confidence": "high",
                "dimensional_attribute_status": "active",
                "dimensional_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_order": 1,
                        "rationale": "Approved dimensional requirement.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "dimensional_entity_name": "SalesFact",
                "dimensional_attribute_name": "CustomerKey",
                "dimensional_attribute_definition": "CustomerKey attribute.",
                "dimensional_attribute_data_type": "bigint",
                "dimensional_attribute_is_nullable": False,
                "dimensional_attribute_ordinal_position": 1,
                "dimensional_attribute_role": "key",
                "dimensional_attribute_key_role": "foreign",
                "dimensional_attribute_is_grain_component": True,
                "dimensional_attribute_additivity": None,
                "dimensional_attribute_default_aggregation": None,
                "dimensional_attribute_aggregation_basis": None,
                "dimensional_attribute_change_behavior": None,
                "dimensional_attribute_is_audit_column": False,
                "dimensional_attribute_confidence": "high",
                "dimensional_attribute_status": "active",
                "dimensional_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_order": 1,
                        "rationale": "Approved dimensional requirement.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "dimensional_entity_name": "SalesFact",
                "dimensional_attribute_name": "OrderCount",
                "dimensional_attribute_definition": "One for each "
                "governed order "
                "fact row; sum "
                "counts orders "
                "at compatible "
                "aggregation "
                "levels.",
                "dimensional_attribute_data_type": "bigint",
                "dimensional_attribute_is_nullable": False,
                "dimensional_attribute_ordinal_position": 3,
                "dimensional_attribute_role": "measure",
                "dimensional_attribute_key_role": "none",
                "dimensional_attribute_is_grain_component": False,
                "dimensional_attribute_additivity": "additive",
                "dimensional_attribute_default_aggregation": "SUM",
                "dimensional_attribute_aggregation_basis": "Each "
                "fact "
                "row "
                "contributes "
                "exactly "
                "one "
                "distinct "
                "order "
                "under "
                "the "
                "confirmed "
                "grain "
                "rule.",
                "dimensional_attribute_change_behavior": None,
                "dimensional_attribute_is_audit_column": False,
                "dimensional_attribute_confidence": "high",
                "dimensional_attribute_status": "active",
                "dimensional_attribute_is_locked": False,
                "sources": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "sales_order_count"},
                        "source_order": 2,
                        "rationale": "The confirmed rule "
                        "defines one order per "
                        "fact row and a count of "
                        "one for that row.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
            {
                "dimensional_entity_name": "CustomerDimension",
                "dimensional_attribute_name": "CustomerKey",
                "dimensional_attribute_definition": "CustomerKey attribute.",
                "dimensional_attribute_data_type": "bigint",
                "dimensional_attribute_is_nullable": False,
                "dimensional_attribute_ordinal_position": 1,
                "dimensional_attribute_role": "key",
                "dimensional_attribute_key_role": "surrogate",
                "dimensional_attribute_is_grain_component": True,
                "dimensional_attribute_additivity": None,
                "dimensional_attribute_default_aggregation": None,
                "dimensional_attribute_aggregation_basis": None,
                "dimensional_attribute_change_behavior": None,
                "dimensional_attribute_is_audit_column": False,
                "dimensional_attribute_confidence": "high",
                "dimensional_attribute_status": "active",
                "dimensional_attribute_is_locked": True,
                "sources": [
                    {
                        "support_source_type": "assertion",
                        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                        "source_order": 1,
                        "rationale": "Approved dimensional requirement.",
                        "status": "active",
                        "is_locked": False,
                    }
                ],
            },
        ],
        "dimensional_relationship_list": [
            {
                "from_dimensional_entity_name": "SalesFact",
                "from_dimensional_attribute_name": "CustomerKey",
                "to_dimensional_entity_name": "CustomerDimension",
                "to_dimensional_attribute_name": "CustomerKey",
                "dimensional_relationship_kind": "fact_dimension",
                "dimensional_relationship_role_name": None,
            }
        ],
        "dimensional_relationships": [
            {
                "dimensional_relationship_name": "SalesCustomer",
                "dimensional_relationship_definition": "Fact joins Customer Dimension.",
                "from_dimensional_entity_name": "SalesFact",
                "from_dimensional_attribute_name": "CustomerKey",
                "to_dimensional_entity_name": "CustomerDimension",
                "to_dimensional_attribute_name": "CustomerKey",
                "dimensional_relationship_kind": "fact_dimension",
                "dimensional_relationship_cardinality": "many_to_one",
                "dimensional_relationship_is_optional": False,
                "dimensional_relationship_role_name": None,
                "dimensional_relationship_confidence": "high",
                "dimensional_relationship_basis": "The saved "
                "sales policy "
                "assigns each "
                "order to one "
                "customer "
                "dimension "
                "member.",
                "dimensional_relationship_cardinality_basis": "Each "
                "order "
                "references "
                "one "
                "customer "
                "member; "
                "a "
                "customer "
                "member "
                "may "
                "receive "
                "many "
                "orders.",
                "dimensional_relationship_status": "active",
                "dimensional_relationship_is_locked": False,
            }
        ],
        "gds_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "zone_code": "silver",
                "zone_description": "Modeled operational data populated through Logical Mapping.",
            }
        ],
        "object_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "silver",
                "object_name": "sales_order",
                "object_description": "One governed sales order, populated "
                "from the applied Logical Order "
                "Mapping.",
                "zone_code": "silver",
            }
        ],
        "object_attribute_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "silver",
                "object_name": "sales_order",
                "attributes": [
                    {
                        "attribute_name": "order_id",
                        "attribute_description": "Identifier of one governed sales order.",
                        "attribute_data_type": "BIGINT",
                        "attribute_inferred_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "is_natural_key": True,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": None,
                    },
                    {
                        "attribute_name": "customer_id",
                        "attribute_description": "Customer reference recorded on the order.",
                        "attribute_data_type": "BIGINT",
                        "attribute_inferred_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "is_natural_key": False,
                        "is_surrogate_key": False,
                        "is_masking_required": False,
                        "is_meta_data": False,
                        "profile": None,
                    },
                ],
                "selected_attribute_names": ["order_id", "customer_id"],
            }
        ],
        "modeling_assertions": [
            {
                "modeling_assertion_record_key": "sales_order_count",
                "modeling_assertion_document_name": "Sales analytics rules",
                "modeling_assertion_record_type": "business_rule",
                "modeling_assertion_text": "One fact row represents "
                "one governed order. "
                "OrderCount is one for that "
                "row. Sum counts orders "
                "only across compatible "
                "aggregation levels.",
                "modeling_assertion_details": {},
                "modeling_assertion_source_location": None,
                "modeling_assertion_confidence": "high",
            }
        ],
        "logical_bindings": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "object_schema": "silver",
                "object_name": "sales_order",
                "logical_entity_name": "Order",
                "attributes": [
                    {"attribute_name": "order_id", "logical_attribute_name": "OrderID"},
                    {"attribute_name": "customer_id", "logical_attribute_name": "CustomerID"},
                ],
            }
        ],
        "naming_instructions": "Use PascalCase for Dimensional submodel, entity, "
        "attribute, and relationship names. Dimensional key "
        "Attribute names end with Key.",
        "audit_columns": {
            "schema_version": "1.0",
            "columns": [
                {
                    "semantic_name": "LoadedAt",
                    "data_type": "TIMESTAMP",
                    "nullable": False,
                    "definition": "Warehouse load time.",
                }
            ],
        },
        "technical_columns": {
            "schema_version": "1.0",
            "dimension_surrogate_key": {
                "semantic_name_template": "{entity_name}Key",
                "data_type": "BIGINT",
                "nullable": False,
                "definition_template": "Surrogate key for {entity_name}.",
            },
            "fact_bridge_foreign_key": {
                "with_role_semantic_name_template": "{role_name}Key",
                "without_role_semantic_name_template": "{entity_name}Key",
                "definition_template": "Foreign key to {entity_name} for {role_name}.",
            },
            "type_2": {
                "effective_from": {
                    "semantic_name": "EffectiveFrom",
                    "data_type": "TIMESTAMP",
                    "nullable": False,
                    "definition": "Start of this version validity.",
                },
                "effective_to": {
                    "semantic_name": "EffectiveTo",
                    "data_type": "TIMESTAMP",
                    "nullable": True,
                    "definition": "End of validity; null for current version.",
                },
                "is_current": {
                    "semantic_name": "IsCurrent",
                    "data_type": "BOOLEAN",
                    "nullable": False,
                    "definition": "Whether this is the current version.",
                },
            },
        },
    },
}


def workflow_input_contracts(workflow: str) -> dict[str, dict[str, Any]]:
    return {
        name: {**deepcopy(INPUT_SHAPES[shape]), "example": deepcopy(INPUT_EXAMPLES[workflow][name])}
        for name, shape in WORKFLOW_INPUTS.get(workflow, {}).items()
    }


# The two enrichment workflows reuse the same five exact foundational shapes.
for _enrichment_workflow in ("metadata_enrichment_object", "metadata_enrichment_attribute"):
    WORKFLOW_INPUTS[_enrichment_workflow] = {
        name: name
        for name in (
            "source_context",
            "gds_context",
            "object_context",
            "object_attribute_context",
            "ingestion_mapping",
        )
    }
    INPUT_EXAMPLES[_enrichment_workflow] = {
        name: INPUT_EXAMPLES["analysis"][name] for name in WORKFLOW_INPUTS[_enrichment_workflow]
    }
