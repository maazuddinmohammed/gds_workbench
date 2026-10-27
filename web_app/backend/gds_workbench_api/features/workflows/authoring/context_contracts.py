"""Approved workflow-local evidence contracts, shipped with every runtime artifact.

Schemas mirror the reviewed JSON artifacts; tests compare their wire contracts.
No project documentation is loaded by a deployed runtime.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
)
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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
        "description": "GDS Connection/zone placements for selected physical inputs "
        "or the Project-assigned placement of modeled Entity outputs.",
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
        "with current saved descriptions, types, flags, "
        "and Profiles.",
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
                                    "registered_is_natural_key": {
                                        "type": "boolean",
                                        "description": "Registered physical key flag; independent "
                                        "of the nullable Project-enriched is_natural_key finding.",
                                    },
                                    "is_natural_key": {"type": ["boolean", "null"]},
                                    "is_primary_key": {"type": ["boolean", "null"]},
                                    "is_nullable": {"type": ["boolean", "null"]},
                                    "is_pii": {"type": ["boolean", "null"]},
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
        "description": "Existing applied relationships touching each scoped physical Object. "
        "Incoming matches the to-Object; outgoing matches the from-Object. Include empty "
        "groups. Preserve endpoint, hypothesis, lifecycle, lock and recorded validation "
        "fields. Validation outcome and aggregate counts are saved evidence, not a fresh "
        "measurement; all-null validation fields mean unvalidated. An endpoint outside "
        "object_context is contextual only and does not become an eligible authoring source.",
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
                        "inferred_cardinality": {
                            "enum": [
                                "one_to_one",
                                "one_to_many",
                                "many_to_one",
                                "many_to_many",
                                "unknown",
                            ]
                        },
                        "validation_policy_version": {
                            "type": ["string", "null"],
                            "minLength": 1,
                            "maxLength": 50,
                            "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$",
                        },
                        "validation_result": {
                            "enum": ["supported", "inconclusive", "unsupported", None]
                        },
                        "validation_source_non_null_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "validation_source_distinct_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "validation_target_non_null_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "validation_target_distinct_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "validation_source_missing_target_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "validation_unused_target_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "validation_duplicate_target_key_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
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
                        "inferred_cardinality",
                        "validation_policy_version",
                        "validation_result",
                        "validation_source_non_null_count",
                        "validation_source_distinct_count",
                        "validation_target_non_null_count",
                        "validation_target_distinct_count",
                        "validation_source_missing_target_count",
                        "validation_unused_target_count",
                        "validation_duplicate_target_key_count",
                        "analysis_result_status",
                        "analysis_result_is_locked",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    },
    "context_records": {
        "description": "Active Context records from active groups in authorized "
        "Project/Source System scope are reusable guidance for every workflow. "
        "Each record has context_record_id (canonical UUID), context_group_name, "
        "context_type_name, context_text and nullable source_reference. The type "
        "classifies its purpose; context_text contains the requirement, decision, rule, "
        "convention or other guidance, including relevant exceptions and acceptance "
        "criteria. source_reference records provenance. Use UUIDs for Context support "
        "references. Context applicability does not prove physical source data or "
        "replace measured validation; preserve registered lineage and distinguish "
        "guidance from observed evidence.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/context_records_entry"},
            "$defs": {
                "context_records_entry": {
                    "type": "object",
                    "properties": {
                        "context_record_id": {
                            "type": "string",
                            "pattern": (
                                "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
                            ),
                        },
                        "context_group_name": {"type": "string", "minLength": 1, "maxLength": 255},
                        "context_type_name": {"type": "string", "minLength": 1, "maxLength": 200},
                        "context_text": {"type": "string", "minLength": 1, "maxLength": 262144},
                        "source_reference": {"type": ["string", "null"]},
                    },
                    "required": [
                        "context_record_id",
                        "context_group_name",
                        "context_type_name",
                        "context_text",
                        "source_reference",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "scope_tables": {
        "description": "One entry per table in this run, by table_index id: its Project "
        "description, zone, the largest profiled row count (null when unprofiled), column "
        "count and column names.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/scope_table_entry"},
            "$defs": {
                "scope_table_entry": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                        "description": {"type": ["string", "null"]},
                        "zone_code": {"type": "string", "minLength": 1},
                        "row_count": {"type": ["integer", "null"], "minimum": 0},
                        "column_count": {"type": "integer", "minimum": 0},
                        "column_names": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                    "required": [
                        "table",
                        "description",
                        "zone_code",
                        "row_count",
                        "column_count",
                        "column_names",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "table_links": {
        "description": "Table-level Analysis edges between this run's tables, one per "
        "ordered pair: from references to. validation_result is the strongest measured "
        "result among its column edges (supported, inconclusive, unsupported, or null when "
        "unvalidated, which is not disproof); edge_count counts those column edges.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/table_link_entry"},
            "$defs": {
                "table_link_entry": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                        "to": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                        "validation_result": {
                            "enum": ["supported", "inconclusive", "unsupported", None]
                        },
                        "edge_count": {"type": "integer", "minimum": 1},
                    },
                    "required": ["from", "to", "validation_result", "edge_count"],
                    "additionalProperties": False,
                }
            },
        },
    },
    "existing_subject_areas": {
        "description": "Saved Subject Areas with is_active, lock and active member tables "
        "by table_index id. other_table_count counts active members outside this run, which "
        "keep their membership. A locked area, and each table in locked_tables, cannot "
        "change. List a saved area in the answer only to change it.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/existing_subject_area_entry"},
            "$defs": {
                "existing_subject_area_entry": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 255},
                        "definition": {"type": "string", "minLength": 1},
                        "is_active": {"type": "boolean"},
                        "is_locked": {"type": "boolean"},
                        "tables": {
                            "type": "array",
                            "items": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                        },
                        "locked_tables": {
                            "type": "array",
                            "items": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                        },
                        "other_table_count": {"type": "integer", "minimum": 0},
                    },
                    "required": [
                        "name",
                        "definition",
                        "is_active",
                        "is_locked",
                        "tables",
                        "locked_tables",
                        "other_table_count",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "logical.naming_instructions": {
        "description": "Effective Logical naming guidance. Use the "
        "saved Silver Project override when present, "
        "otherwise the existing Logical default. "
        "Advisory guidance; preserve saved identities. "
        "This is resolved before rendering and remains "
        "a Logical-local variable.",
        "schema": {"maxLength": 32768, "minLength": 1, "pattern": "\\S", "type": "string"},
    },
    "logical.audit_columns": {
        "description": "Exact configured Silver audit-column template: "
        "schema_version and columns with semantic_name, "
        "data_type, nullable, definition. Null settings use shared defaults; "
        "an explicit empty columns array disables audits. Reserve effective names "
        "for framework Attributes; source/business fields need distinct names. Preserve "
        "the existing"
        "deterministic backend projection and lock/conflict "
        "checks. The complete project includes required audit "
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
    "dimensional.naming_instructions": {
        "description": "Effective Gold naming override, otherwise "
        "the existing Dimensional default: "
        "PascalCase names and key Attributes "
        "ending in Key. Preserve existing "
        "identities.",
        "schema": {"maxLength": 32768, "minLength": 1, "pattern": "\\S", "type": "string"},
    },
    "dimensional.audit_columns": {
        "description": "Effective Gold audit template; blank settings resolve to shared "
        "audit defaults;"
        "an explicit empty columns array disables audits. Reserve effective names "
        "for framework Attributes; source/business fields need distinct names. Same "
        "schema_version/ordered columns layout as "
        "Logical audit settings. Each column has "
        "semantic_name, data_type, nullable, definition. "
        "Configured audit columns remain authoritative.",
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
                    "minItems": 0,
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
        "description": "Effective GoldTechnicalPolicy (standard keys/history fields when unset): "
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
    "dimensional.dimensional_entity_scd_type": {
        "description": "Frozen Project policy for Dimension history, independent of Logical SCD. "
        "type_1 overwrites mutable descriptors ; type_2 preserves "
        "Dimension versions . Stable identity Attributes remain fixed. "
        "Null is unspecified: use evidenced per-Attribute behavior. Applies to Dimensions, not "
        "Fact or Bridge history. Backend projects surrogate/foreign keys and configured Type 2 "
        "effective/current columns. Do not invent business keys or source history; changing this "
        "setting does not migrate previously applied data.",
        "schema": {"enum": ["type_1", "type_2", None]},
    },
    "coverage_threshold_percent": {
        "description": "Frozen Project coverage target, a whole percentage from 1 to 100. "
        "Count distinct inputs selected for this run with active support on active Entities, "
        "including retained applied support; round the required input count up. "
        "Below target, repair the missing sources listed by backend validation. "
        "Only after the final retry may the backend return otherwise valid partial coverage.",
        "schema": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "table_index": {
        "description": "Short id of every selected Object, in selection order. Cite a table "
        "by its id (t1) and a column as id.column (t1.order_no); the backend expands each id "
        "to its full key.",
        "schema": {
            "type": "array",
            "items": {"$ref": "#/$defs/table_index_entry"},
            "$defs": {
                "table_index_entry": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                        "tenant_code": {"type": "string", "minLength": 1},
                        "system_code": {"type": "string", "minLength": 1},
                        "connection_code": {"type": "string", "minLength": 1},
                        "object_schema": {"type": "string", "minLength": 1},
                        "object_name": {"type": "string", "minLength": 1},
                    },
                    "required": [
                        "table",
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    ],
                    "additionalProperties": False,
                }
            },
        },
    },
    "logical.logical_entity_scd_type": {
        "description": "Frozen Project guidance for Logical Entity change history. type_1 means "
        "overwrite current values; type_2 means preserve versions. Null means unspecified. "
        "This setting does not create history columns, prove a natural key, or change saved "
        "Entities. Use supported source evidence and configured policy; report missing "
        "requirements rather than inventing keys or history Attributes.",
        "schema": {"enum": ["type_1", "type_2", None]},
    },
    "logical.schemas": {
        "description": "Configured logical schema names and placement "
        "descriptions. Assign every Entity to one listed schema.",
        "schema": {
            "$defs": {
                "ProjectSchemaDefinition": {
                    "additionalProperties": False,
                    "properties": {
                        "schema_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Schema Name",
                            "type": "string",
                        },
                        "description": {
                            "anyOf": [
                                {
                                    "maxLength": 2000,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Description",
                        },
                    },
                    "required": ["schema_name", "description"],
                    "title": "ProjectSchemaDefinition",
                    "type": "object",
                }
            },
            "items": {"$ref": "#/$defs/ProjectSchemaDefinition"},
            "type": "array",
        },
    },
    "dimensional.schemas": {
        "description": "Configured dimensional schema names and placement "
        "descriptions. Assign every Entity to one listed "
        "schema.",
        "schema": {
            "$defs": {
                "ProjectSchemaDefinition": {
                    "additionalProperties": False,
                    "properties": {
                        "schema_name": {
                            "maxLength": 400,
                            "minLength": 1,
                            "pattern": "\\S",
                            "title": "Schema Name",
                            "type": "string",
                        },
                        "description": {
                            "anyOf": [
                                {
                                    "maxLength": 2000,
                                    "minLength": 1,
                                    "pattern": "\\S",
                                    "type": "string",
                                },
                                {"type": "null"},
                            ],
                            "title": "Description",
                        },
                    },
                    "required": ["schema_name", "description"],
                    "title": "ProjectSchemaDefinition",
                    "type": "object",
                }
            },
            "items": {"$ref": "#/$defs/ProjectSchemaDefinition"},
            "type": "array",
        },
    },
}


class _SelectedLogicalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    selection_order: int = Field(gt=0)
    entity: LogicalEntityRecord
    attributes: tuple[LogicalAttributeRecord, ...]


# Saved model records exactly as Snapshots carry them; readers page them and Optimize
# reads them in full. Generated from the shared record classes so they never drift.
def _saved_records_shape(record: type[BaseModel], description: str) -> dict[str, Any]:
    return {
        "description": description,
        "schema": TypeAdapter(tuple[record, ...] | None).json_schema(),
    }


INPUT_SHAPES.update(
    {
        "logical_entities": _saved_records_shape(
            LogicalEntityRecord,
            "Saved Logical Entities (LogicalEntityRecord) with nested sources, is_active and "
            "locks. Null when no Logical section is available.",
        ),
        "logical_attributes": _saved_records_shape(
            LogicalAttributeRecord,
            "Saved Logical Attributes (LogicalAttributeRecord) with nested sources.",
        ),
        "logical_relationships": _saved_records_shape(
            LogicalRelationshipRecord,
            "Saved Logical Relationships, each from a child foreign-key Attribute to its "
            "parent's key.",
        ),
        "dimensional_entities": _saved_records_shape(
            DimensionalEntityRecord,
            "Saved Dimensional Entities (DimensionalEntityRecord) with nested Logical sources.",
        ),
        "dimensional_attributes": _saved_records_shape(
            DimensionalAttributeRecord,
            "Saved Dimensional Attributes (DimensionalAttributeRecord) with nested sources.",
        ),
        "dimensional_relationships": _saved_records_shape(
            DimensionalRelationshipRecord,
            "Saved Dimensional Relationships, each from a fact, bridge or outrigger "
            "foreign-key Attribute to a dimension's key.",
        ),
        "selected_logical_entities": {
            "description": "The Logical Entities this Dimensional call builds from: each with "
            "its active Attributes, grain and source lineage. Cite these exact "
            "schema-qualified identities as Dimensional sources.",
            "schema": TypeAdapter(tuple[_SelectedLogicalEntity, ...]).json_schema(),
        },
    }
)

_TEXT = {"type": "string", "minLength": 1}
_NAME_LIST = {"type": "array", "items": _TEXT}
_ENTITY_REF = {
    "type": "object",
    "properties": {"schema": _TEXT, "entity": _TEXT},
    "required": ["schema", "entity"],
    "additionalProperties": False,
}
_ATTRIBUTE_REF = {
    "type": "object",
    "properties": {"schema": _TEXT, "entity": _TEXT, "attribute": _TEXT},
    "required": ["schema", "entity", "attribute"],
    "additionalProperties": False,
}
_CONTEXT_REF = {
    "type": "object",
    "properties": {"context": _TEXT},
    "required": ["context"],
    "additionalProperties": False,
}
# Saved Logical records in the answer's own compact language: tables as t-ids, columns
# as t1.column, Context records as {"context": id}. Generated keys and audit columns are
# left out because the backend owns them.
_COMPACT_LOGICAL_MODEL = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "schema": _TEXT,
                    "name": _TEXT,
                    "type": _TEXT,
                    "definition": _TEXT,
                    "grain": _TEXT,
                    "is_locked": {"type": "boolean"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "anyOf": [{"type": "string", "pattern": "^t[1-9][0-9]*$"}, _CONTEXT_REF]
                        },
                    },
                    "other_source_count": {"type": "integer", "minimum": 0},
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": _TEXT,
                                "type": _TEXT,
                                "nullable": {"type": "boolean"},
                                "natural_key": {"type": "boolean"},
                                "from": {
                                    "type": "array",
                                    "items": {
                                        "anyOf": [
                                            {"type": "string", "pattern": "^t[1-9][0-9]*\\.\\S"},
                                            _CONTEXT_REF,
                                        ]
                                    },
                                },
                                "definition": _TEXT,
                                "is_locked": {"type": "boolean"},
                            },
                            "required": [
                                "name",
                                "type",
                                "nullable",
                                "natural_key",
                                "from",
                                "definition",
                                "is_locked",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "schema",
                    "name",
                    "type",
                    "definition",
                    "grain",
                    "is_locked",
                    "sources",
                    "other_source_count",
                    "attributes",
                ],
                "additionalProperties": False,
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": _ATTRIBUTE_REF,
                    "to": _ENTITY_REF,
                    "cardinality": {"enum": ["many_to_one", "one_to_one"]},
                    "basis": _TEXT,
                    "is_locked": {"type": "boolean"},
                },
                "required": ["from", "to", "cardinality", "basis", "is_locked"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entities", "relationships"],
    "additionalProperties": False,
}
_KEY_LIST = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"name": _TEXT, "type": _TEXT},
        "required": ["name", "type"],
        "additionalProperties": False,
    },
}
_NEIGHBORS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "schema": _TEXT,
            "name": _TEXT,
            "type": _TEXT,
            "grain": {"type": ["string", "null"]},
            "natural_keys": _KEY_LIST,
            "linked_via": {"type": "array", "items": {"enum": ["relationship", "analysis"]}},
        },
        "required": ["schema", "name", "type", "grain", "natural_keys", "linked_via"],
        "additionalProperties": False,
    },
}
_DIRECTORY = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"schema": _TEXT, "name": _TEXT, "type": _TEXT, "summary": _TEXT},
        "required": ["schema", "name", "type", "summary"],
        "additionalProperties": False,
    },
}
_TYPE_LIST = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
            "description": _TEXT,
        },
        "required": ["code", "description"],
        "additionalProperties": False,
    },
}
_TYPE_CONFLICTS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "kind": {"enum": ["relationship_key", "shared_name"]},
            "attribute": _TEXT,
            "values": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"entity": _TEXT, "attribute": _TEXT, "type": _TEXT},
                    "required": ["entity", "attribute", "type"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["kind", "attribute", "values"],
        "additionalProperties": False,
    },
}
_NAME_VARIANTS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"kind": {"enum": ["entity", "attribute"]}, "names": _NAME_LIST},
        "required": ["kind", "names"],
        "additionalProperties": False,
    },
}

INPUT_SHAPES.update(
    {
        "subject_area_context": {
            "description": "The one Subject Area this Build call works on: name, definition "
            "and how many of its inputs this call sees. A Build processes its areas one "
            "after another into one draft of one model; other areas are separate calls.",
            "schema": {
                "type": "object",
                "properties": {
                    "name": _TEXT,
                    "definition": _TEXT,
                    "input_count": {"type": "integer", "minimum": 1},
                },
                "required": ["name", "definition", "input_count"],
                "additionalProperties": False,
            },
        },
        "logical.existing_entities": {
            "description": "Active Entities already built from this area's tables, saved or "
            "built by an earlier area of this run, in the answer's own compact language. "
            "Reuse and extend them; never create a second Entity for the same thing. List one "
            "in your answer only to change it. sources lists this area's tables; "
            "other_source_count counts sources outside this area, which are kept. Generated "
            "keys and audit columns are not shown. relationships are links touching these "
            "Entities.",
            "schema": _COMPACT_LOGICAL_MODEL,
        },
        "logical.neighbor_entities": {
            "description": "Active Entities just outside this area: parents or children of "
            "existing_entities, or built from tables that Analysis links to this area's "
            "tables. Use them as Relationship parents by schema and name; change one only "
            "when this area's evidence requires it.",
            "schema": _NEIGHBORS,
        },
        "logical.entity_directory": {
            "description": "One line for every other active Entity in the model: schema, name, "
            "type and the first sentence of its definition. Reuse these names; never create "
            "a duplicate.",
            "schema": _DIRECTORY,
        },
        "logical_entity_types": {
            "description": "Active Logical Entity type codes and their meaning. Give every "
            "new Entity one code.",
            "schema": _TYPE_LIST,
        },
        "logical.model_summary": {
            "description": "The whole active Logical model in short form. Entities: schema, "
            "name, type, grain, the Subject Areas of their tables, natural-key Attributes, "
            "attribute count and source tables by table_index id. Relationships: "
            "child.foreign_key -> parent.",
            "schema": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "schema": _TEXT,
                                "name": _TEXT,
                                "type": _TEXT,
                                "grain": _TEXT,
                                "subject_areas": _NAME_LIST,
                                "keys": _KEY_LIST,
                                "attribute_count": {"type": "integer", "minimum": 0},
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string", "pattern": "^t[1-9][0-9]*$"},
                                },
                                "is_locked": {"type": "boolean"},
                            },
                            "required": [
                                "schema",
                                "name",
                                "type",
                                "grain",
                                "subject_areas",
                                "keys",
                                "attribute_count",
                                "sources",
                                "is_locked",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": _TEXT,
                                "to": _TEXT,
                                "cardinality": {"enum": ["many_to_one", "one_to_one"]},
                            },
                            "required": ["from", "to", "cardinality"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["entities", "relationships"],
                "additionalProperties": False,
            },
        },
        "logical.unlinked_analysis_edges": {
            "description": "Analysis links, measured supported or not yet validated, between "
            "two modeled tables whose Entities have no Relationship in either direction. "
            "Each is a candidate cross-area Relationship; add it only when the Entities' "
            "grain and keys support it.",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": _TEXT,
                        "to": _TEXT,
                        "validation_result": {"enum": ["supported", "inconclusive", None]},
                        "from_entities": _NAME_LIST,
                        "to_entities": _NAME_LIST,
                    },
                    "required": [
                        "from",
                        "to",
                        "validation_result",
                        "from_entities",
                        "to_entities",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "logical.type_conflicts": {
            "description": "Data type disagreements found by the backend: a foreign key whose "
            "type differs from its parent's key (relationship_key), or one Attribute name "
            "with different types across Entities (shared_name). Fix real conflicts; leave "
            "intentional differences.",
            "schema": _TYPE_CONFLICTS,
        },
        "logical.name_variants": {
            "description": "Entity or Attribute names that differ only by case, separators or "
            "a plural s. Each group may be one thing named twice: merge or rename when the "
            "evidence agrees.",
            "schema": _NAME_VARIANTS,
        },
        "logical.entity_details": {
            "description": "Full compact records for the Entities named by the findings above, "
            "so they can be changed or merged without reading the whole model.",
            "schema": _COMPACT_LOGICAL_MODEL,
        },
        "dimensional.existing_entities": {
            "description": "Active Dimensional Entities already built from this area's Logical "
            "Entities, saved or built by an earlier area of this run, with their Attributes "
            "and the Relationships touching them. Reuse and extend them; list a record in "
            "your answer only to change it.",
            "schema": {
                "type": "object",
                "properties": {
                    "entities": INPUT_SHAPES["dimensional_entities"]["schema"]["anyOf"][0],
                    "attributes": INPUT_SHAPES["dimensional_attributes"]["schema"]["anyOf"][0],
                    "relationships": INPUT_SHAPES["dimensional_relationships"]["schema"]["anyOf"][
                        0
                    ],
                },
                "required": ["entities", "attributes", "relationships"],
                "additionalProperties": False,
                "$defs": {
                    **INPUT_SHAPES["dimensional_entities"]["schema"].get("$defs", {}),
                    **INPUT_SHAPES["dimensional_attributes"]["schema"].get("$defs", {}),
                    **INPUT_SHAPES["dimensional_relationships"]["schema"].get("$defs", {}),
                },
            },
        },
        "dimensional.logical_links": {
            "description": "Active Logical Relationships touching this area's Logical "
            "Entities, child foreign key to parent: from (schema.Entity.Attribute), to "
            "(schema.Entity) and cardinality. They show the joins a Fact, Bridge or "
            "outrigger can follow.",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": _TEXT,
                        "to": _TEXT,
                        "cardinality": {"enum": ["many_to_one", "one_to_one"]},
                    },
                    "required": ["from", "to", "cardinality"],
                    "additionalProperties": False,
                },
            },
        },
        "dimensional.neighbor_entities": {
            "description": "Active Dimensional Entities just outside this area that its "
            "Entities link to, such as shared Date or Customer dimensions. Reuse them as "
            "dimensions by schema and name; never build a second copy.",
            "schema": _NEIGHBORS,
        },
        "dimensional.entity_directory": {
            "description": "One line for every other active Dimensional Entity: schema, "
            "name, type and the first sentence of its definition. Reuse conformed "
            "dimensions; never create a duplicate.",
            "schema": _DIRECTORY,
        },
        "dimensional_fact_types": {
            "description": "Active fact type codes and their meaning. Give every new fact "
            "one code; dimensions and bridges have none.",
            "schema": _TYPE_LIST,
        },
        "dimensional.model_summary": {
            "description": "The whole active Dimensional model in short form. Entities: "
            "schema, name, type, fact type, grain, Subject Areas, natural keys, attribute "
            "count and Logical sources. Relationships: child.foreign_key -> dimension "
            "(role).",
            "schema": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "schema": _TEXT,
                                "name": _TEXT,
                                "type": {"enum": ["fact", "dimension", "bridge"]},
                                "fact_type": {"type": ["string", "null"]},
                                "grain": {"type": ["string", "null"]},
                                "subject_areas": _NAME_LIST,
                                "keys": _KEY_LIST,
                                "attribute_count": {"type": "integer", "minimum": 0},
                                "logical_sources": _NAME_LIST,
                                "is_locked": {"type": "boolean"},
                            },
                            "required": [
                                "schema",
                                "name",
                                "type",
                                "fact_type",
                                "grain",
                                "subject_areas",
                                "keys",
                                "attribute_count",
                                "logical_sources",
                                "is_locked",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": _TEXT,
                                "to": _TEXT,
                                "role": {"type": ["string", "null"]},
                            },
                            "required": ["from", "to", "role"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["entities", "relationships"],
                "additionalProperties": False,
            },
        },
        "dimensional.conformance_candidates": {
            "description": "Dimensions built from the same Logical Entity, or with name "
            "variants: each group may need to become one conformed dimension.",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "reason": {"enum": ["same_logical_source", "name_variant"]},
                        "dimensions": _NAME_LIST,
                    },
                    "required": ["reason", "dimensions"],
                    "additionalProperties": False,
                },
            },
        },
        "dimensional.type_conflicts": {
            "description": "Data type disagreements: a foreign key whose type differs from "
            "its dimension's key, or one Attribute name with different types across "
            "Dimensional Entities.",
            "schema": _TYPE_CONFLICTS,
        },
        "dimensional.name_variants": {
            "description": "Dimensional Entity or Attribute names that differ only by case, "
            "separators or a plural s.",
            "schema": _NAME_VARIANTS,
        },
        "dimensional.entity_details": {
            "description": "Saved records for the Dimensional Entities named by the findings "
            "above, with their Attributes and Relationships.",
            "schema": {"$ref": "#/$defs/existing"},
        },
    }
)
INPUT_SHAPES["dimensional.entity_details"]["schema"] = deepcopy(
    INPUT_SHAPES["dimensional.existing_entities"]["schema"]
)


_PHYSICAL_INPUTS = {
    "source_context": "source_context",
    "gds_context": "gds_context",
    "object_context": "object_context",
    "object_attribute_context": "object_attribute_context",
    "ingestion_mapping": "ingestion_mapping",
    "object_relationship_context": "object_relationship_context",
    "context_records": "context_records",
}
_LOGICAL_SETTINGS = {
    "naming_instructions": "logical.naming_instructions",
    "audit_columns": "logical.audit_columns",
    "schemas": "logical.schemas",
    "logical_entity_scd_type": "logical.logical_entity_scd_type",
}
_DIMENSIONAL_SETTINGS = {
    "naming_instructions": "dimensional.naming_instructions",
    "audit_columns": "dimensional.audit_columns",
    "technical_columns": "dimensional.technical_columns",
    "schemas": "dimensional.schemas",
    "dimensional_entity_scd_type": "dimensional.dimensional_entity_scd_type",
}
# Whole-model records that back the get_logical_* and get_dimensional_* readers.
_LOGICAL_RECORDS = {
    name: name for name in ("logical_entities", "logical_attributes", "logical_relationships")
}
_DIMENSIONAL_RECORDS = {
    name: name
    for name in ("dimensional_entities", "dimensional_attributes", "dimensional_relationships")
}

# Inputs per authoring stage. Logical and Dimensional have two stages: Build works on one
# Subject Area per call; Optimize reviews the whole model (stage inputs "<workflow>_optimize").
WORKFLOW_INPUTS: dict[str, dict[str, str]] = {
    "analysis": {
        "source_context": "source_context",
        "gds_context": "gds_context",
        "object_context": "object_context",
        "object_attribute_context": "object_attribute_context",
        "ingestion_mapping": "ingestion_mapping",
        "object_relationship_context": "object_relationship_context",
        "context_records": "context_records",
    },
    "subject_area": {
        "source_context": "source_context",
        "gds_context": "gds_context",
        "table_index": "table_index",
        "scope_tables": "scope_tables",
        "table_links": "table_links",
        "existing_subject_areas": "existing_subject_areas",
        "context_records": "context_records",
    },
    "logical": {
        "subject_area_context": "subject_area_context",
        "table_index": "table_index",
        **_PHYSICAL_INPUTS,
        "existing_entities": "logical.existing_entities",
        "neighbor_entities": "logical.neighbor_entities",
        "entity_directory": "logical.entity_directory",
        "logical_entity_types": "logical_entity_types",
        **_LOGICAL_SETTINGS,
        "coverage_threshold_percent": "coverage_threshold_percent",
        **_LOGICAL_RECORDS,
    },
    "logical_optimize": {
        "table_index": "table_index",
        "model_summary": "logical.model_summary",
        "unlinked_analysis_edges": "logical.unlinked_analysis_edges",
        "type_conflicts": "logical.type_conflicts",
        "name_variants": "logical.name_variants",
        "entity_details": "logical.entity_details",
        **_PHYSICAL_INPUTS,
        "logical_entity_types": "logical_entity_types",
        **_LOGICAL_SETTINGS,
        **_LOGICAL_RECORDS,
    },
    "dimensional": {
        "subject_area_context": "subject_area_context",
        "selected_logical_entities": "selected_logical_entities",
        "logical_links": "dimensional.logical_links",
        **_PHYSICAL_INPUTS,
        "existing_entities": "dimensional.existing_entities",
        "neighbor_entities": "dimensional.neighbor_entities",
        "entity_directory": "dimensional.entity_directory",
        "dimensional_fact_types": "dimensional_fact_types",
        **_DIMENSIONAL_SETTINGS,
        "coverage_threshold_percent": "coverage_threshold_percent",
        **_LOGICAL_RECORDS,
        **_DIMENSIONAL_RECORDS,
    },
    "dimensional_optimize": {
        "model_summary": "dimensional.model_summary",
        "conformance_candidates": "dimensional.conformance_candidates",
        "type_conflicts": "dimensional.type_conflicts",
        "name_variants": "dimensional.name_variants",
        "entity_details": "dimensional.entity_details",
        "selected_logical_entities": "selected_logical_entities",
        **_PHYSICAL_INPUTS,
        "dimensional_fact_types": "dimensional_fact_types",
        **_DIMENSIONAL_SETTINGS,
        **_LOGICAL_RECORDS,
        **_DIMENSIONAL_RECORDS,
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
        "context_records": [
            {
                "context_record_id": "90b6320b-c2e0-5e9d-bd00-0e14e6d259fe",
                "context_group_name": "ERP relationship notes",
                "context_type_name": "Business Requirement",
                "context_text": (
                    "Within this ERP source, Orders.CustomerCode references "
                    "the customer account identified by "
                    "Customers.CustomerCode."
                ),
                "source_reference": '{"section": "Orders and customers"}',
            }
        ],
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
                        "within "
                        "this ERP "
                        "source.",
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
                        "of this "
                        "ERP "
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
        "context_records": [
            {
                "context_record_id": "90b6320b-c2e0-5e9d-bd00-0e14e6d259fe",
                "context_group_name": "ERP relationship notes",
                "context_type_name": "Business Requirement",
                "context_text": (
                    "Within this ERP source, Orders.order_id identifies one "
                    "order. Each order belongs to exactly one customer "
                    "identified by Customers.customer_id through "
                    "Orders.customer_id; one customer may have many orders. "
                    "Customer IDs are stable within this source."
                ),
                "source_reference": '{"section": "Orders and customers"}',
            }
        ],
        "naming_instructions": "Use PascalCase for Logical entity, attribute, and "
        "relationship names. Identifier Attribute names end with "
        "ID, with both I and D uppercase.",
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
        "schemas": [{"schema_name": "silver", "description": "Logical model schema."}],
        "logical_entity_scd_type": "type_2",
        "coverage_threshold_percent": 70,
    },
    "dimensional": {
        "dimensional_entity_scd_type": "type_2",
        "coverage_threshold_percent": 60,
        "gds_context": [
            {
                "tenant_code": "GDS",
                "system_code": "WAREHOUSE",
                "connection_code": "MAIN",
                "zone_code": "silver",
                "zone_description": "Logical entity placement.",
            }
        ],
        "context_records": [
            {
                "context_record_id": "9bbdef91-d027-58a3-b22f-92ef90293cd0",
                "context_group_name": "Sales analytics rules",
                "context_type_name": "Business Requirement",
                "context_text": (
                    "One fact row represents one governed order. OrderCount "
                    "is one for that row. Sum counts orders only across "
                    "compatible aggregation levels."
                ),
                "source_reference": None,
            }
        ],
        "naming_instructions": "Use PascalCase for Dimensional entity and attribute "
        "names. Dimensional key Attribute names end with Key.",
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
        "schemas": [{"schema_name": "gold", "description": "Dimensional model schema."}],
    },
}


# Logical answers cite tables by these ids, numbered in selection order.
INPUT_EXAMPLES["logical"]["table_index"] = [
    {
        "table": f"t{position}",
        **{
            name: entry[name]
            for name in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        },
    }
    for position, entry in enumerate(INPUT_EXAMPLES["logical"]["object_context"], start=1)
]

# One small applied model: Order (t1) references Customer (t2). Records are validated
# through the shared record classes so examples stay valid as the contract changes.
_ORDERS, _CUSTOMERS = (
    {
        name: entry[name]
        for name in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    for entry in INPUT_EXAMPLES["logical"]["object_context"][:2]
)


def _validated(record: type[BaseModel], value: dict[str, Any]) -> dict[str, Any]:
    return record.model_validate_json(json.dumps(value)).model_dump(mode="json")


def _source(key: dict[str, Any], column: str | None = None) -> dict[str, Any]:
    if column is None:
        return {
            "support_source_type": "object",
            "source_object": key,
            "is_active": True,
            "is_locked": False,
        }
    return {
        "support_source_type": "attribute",
        "source_attribute": {**key, "attribute_name": column},
        "is_active": True,
        "is_locked": False,
    }


def _logical_attribute(entity: str, name: str, ordinal: int, **values: Any) -> dict[str, Any]:
    return _validated(
        LogicalAttributeRecord,
        {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": entity,
            "logical_attribute_name": name,
            "logical_attribute_definition": values.pop("definition"),
            "logical_attribute_data_type": values.pop("data_type", "BIGINT"),
            "logical_attribute_is_nullable": values.pop("nullable", False),
            "logical_attribute_is_natural_key": values.pop("natural_key", False),
            "logical_attribute_is_surrogate_key": values.pop("surrogate_key", False),
            "logical_attribute_ordinal_position": ordinal,
            "logical_attribute_is_audit_column": False,
            "logical_attribute_is_active": True,
            "logical_attribute_is_locked": False,
            "sources": values.pop("sources", []),
        },
    )


_LOGICAL_ENTITIES = [
    _validated(
        LogicalEntityRecord,
        {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": name,
            "logical_entity_definition": definition,
            "logical_entity_type": entity_type,
            "logical_entity_grain": grain,
            "logical_entity_dependency_order": order,
            "logical_entity_is_active": True,
            "logical_entity_is_locked": False,
            "sources": [_source(key)],
        },
    )
    for name, definition, entity_type, grain, order, key in (
        (
            "Customer",
            "One row per ERP customer account.",
            "core",
            "One row per customer_id.",
            0,
            _CUSTOMERS,
        ),
        (
            "SalesOrder",
            "One row per order a customer places.",
            "transaction",
            "One row per order_id.",
            1,
            _ORDERS,
        ),
    )
]
_LOGICAL_ATTRIBUTES = [
    _logical_attribute(
        "Customer", "CustomerID", 1, definition="Surrogate key for Customer.", surrogate_key=True
    ),
    _logical_attribute(
        "Customer",
        "SourceCustomerNumber",
        2,
        definition="Business identifier of this ERP customer account.",
        natural_key=True,
        sources=[_source(_CUSTOMERS, "customer_id")],
    ),
    _logical_attribute(
        "SalesOrder",
        "SalesOrderID",
        1,
        definition="Surrogate key for SalesOrder.",
        surrogate_key=True,
    ),
    _logical_attribute(
        "SalesOrder",
        "CustomerID",
        2,
        definition="The Customer that placed this order.",
        sources=[_source(_ORDERS, "customer_id")],
    ),
]
_LOGICAL_RELATIONSHIPS = [
    _validated(
        LogicalRelationshipRecord,
        {
            "from_logical_entity_schema_name": "silver",
            "from_logical_entity_name": "SalesOrder",
            "from_logical_attribute_name": "CustomerID",
            "to_logical_entity_schema_name": "silver",
            "to_logical_entity_name": "Customer",
            "to_logical_attribute_name": "CustomerID",
            "logical_relationship_cardinality": "many_to_one",
            "logical_relationship_basis": (
                "Analysis: Orders.customer_id -> Customers.customer_id, supported."
            ),
            "logical_relationship_is_active": True,
            "logical_relationship_is_locked": False,
        },
    )
]
_COMPACT_ORDER_MODEL = {
    "entities": [
        {
            "schema": "silver",
            "name": "SalesOrder",
            "type": "transaction",
            "definition": "One row per order a customer places.",
            "grain": "One row per order_id.",
            "is_locked": False,
            "sources": ["t1"],
            "other_source_count": 0,
            "attributes": [
                {
                    "name": "CustomerID",
                    "type": "BIGINT",
                    "nullable": False,
                    "natural_key": False,
                    "from": ["t1.customer_id"],
                    "definition": "The Customer that placed this order.",
                    "is_locked": False,
                }
            ],
        }
    ],
    "relationships": [
        {
            "from": {"schema": "silver", "entity": "SalesOrder", "attribute": "CustomerID"},
            "to": {"schema": "silver", "entity": "Customer"},
            "cardinality": "many_to_one",
            "basis": "Analysis: Orders.customer_id -> Customers.customer_id, supported.",
            "is_locked": False,
        }
    ],
}
_LOGICAL_TYPES = [
    {
        "code": "core",
        "description": "A main business thing with its own identity, such as Customer or Product.",
    },
    {
        "code": "transaction",
        "description": (
            "A business document or exchange, such as SalesOrder or Invoice, often with lines."
        ),
    },
]
INPUT_EXAMPLES["logical"].update(
    {
        "subject_area_context": {
            "name": "Order Capture",
            "definition": (
                "Customer orders from submission to confirmation, with the customers placing them."
            ),
            "input_count": 2,
        },
        "existing_entities": deepcopy(_COMPACT_ORDER_MODEL),
        "neighbor_entities": [
            {
                "schema": "silver",
                "name": "Customer",
                "type": "core",
                "grain": "One row per customer_id.",
                "natural_keys": [{"name": "SourceCustomerNumber", "type": "BIGINT"}],
                "linked_via": ["relationship"],
            }
        ],
        "entity_directory": [
            {
                "schema": "silver",
                "name": "Invoice",
                "type": "transaction",
                "summary": "One row per invoice issued to a customer.",
            }
        ],
        "logical_entity_types": deepcopy(_LOGICAL_TYPES),
        "logical_entities": deepcopy(_LOGICAL_ENTITIES),
        "logical_attributes": deepcopy(_LOGICAL_ATTRIBUTES),
        "logical_relationships": deepcopy(_LOGICAL_RELATIONSHIPS),
    }
)
INPUT_EXAMPLES["logical_optimize"] = {
    **{
        name: deepcopy(INPUT_EXAMPLES["logical"][name])
        for name in WORKFLOW_INPUTS["logical_optimize"]
        if name in INPUT_EXAMPLES["logical"]
    },
    "model_summary": {
        "entities": [
            {
                "schema": "silver",
                "name": "Customer",
                "type": "core",
                "grain": "One row per customer_id.",
                "subject_areas": ["Order Capture", "Billing"],
                "keys": [{"name": "SourceCustomerNumber", "type": "BIGINT"}],
                "attribute_count": 2,
                "sources": ["t2"],
                "is_locked": False,
            },
            {
                "schema": "silver",
                "name": "SalesOrder",
                "type": "transaction",
                "grain": "One row per order_id.",
                "subject_areas": ["Order Capture"],
                "keys": [],
                "attribute_count": 2,
                "sources": ["t1"],
                "is_locked": False,
            },
        ],
        "relationships": [
            {
                "from": "silver.SalesOrder.CustomerID",
                "to": "silver.Customer",
                "cardinality": "many_to_one",
            }
        ],
    },
    "unlinked_analysis_edges": [
        {
            "from": "t1.customer_id",
            "to": "t2.customer_id",
            "validation_result": "supported",
            "from_entities": ["silver.SalesOrder"],
            "to_entities": ["silver.Customer"],
        }
    ],
    "type_conflicts": [
        {
            "kind": "shared_name",
            "attribute": "CustomerID",
            "values": [
                {"entity": "silver.SalesOrder", "attribute": "CustomerID", "type": "BIGINT"},
                {"entity": "silver.Invoice", "attribute": "CustomerID", "type": "STRING"},
            ],
        }
    ],
    "name_variants": [{"kind": "entity", "names": ["silver.Customer", "silver.Customers"]}],
    "entity_details": deepcopy(_COMPACT_ORDER_MODEL),
}

_DIMENSIONAL_ENTITIES = [
    _validated(
        DimensionalEntityRecord,
        {
            "dimensional_entity_schema_name": "gold",
            "dimensional_entity_name": name,
            "dimensional_entity_definition": definition,
            "dimensional_entity_type": entity_type,
            "dimensional_fact_type": fact_type,
            "dimensional_entity_grain_definition": grain,
            "dimensional_entity_dependency_order": order,
            "dimensional_entity_is_active": True,
            "dimensional_entity_is_locked": False,
            "sources": [
                {
                    "support_source_type": "logical_entity",
                    "source_logical_entity": {
                        "logical_entity_schema_name": "silver",
                        "logical_entity_name": logical,
                    },
                    "is_active": True,
                    "is_locked": False,
                }
            ],
        },
    )
    for name, definition, entity_type, fact_type, grain, order, logical in (
        ("DimCustomer", "One row per customer account.", "dimension", None, None, 0, "Customer"),
        (
            "FactSalesOrder",
            "One row per order.",
            "fact",
            "transaction",
            "One row per order_id.",
            1,
            "SalesOrder",
        ),
    )
]
_DIMENSIONAL_ATTRIBUTES = [
    _validated(
        DimensionalAttributeRecord,
        {
            "dimensional_entity_schema_name": "gold",
            "dimensional_entity_name": entity,
            "dimensional_attribute_name": name,
            "dimensional_attribute_definition": definition,
            "dimensional_attribute_data_type": "BIGINT",
            "dimensional_attribute_is_nullable": False,
            "dimensional_attribute_ordinal_position": ordinal,
            "dimensional_attribute_is_natural_key": False,
            "dimensional_attribute_is_surrogate_key": surrogate,
            "dimensional_attribute_is_audit_column": False,
            "dimensional_attribute_is_active": True,
            "dimensional_attribute_is_locked": False,
            "sources": [],
        },
    )
    for entity, name, definition, ordinal, surrogate in (
        ("DimCustomer", "CustomerKey", "Surrogate key for DimCustomer.", 1, True),
        ("FactSalesOrder", "CustomerKey", "Foreign key to DimCustomer.", 1, False),
    )
]
_DIMENSIONAL_RELATIONSHIPS = [
    _validated(
        DimensionalRelationshipRecord,
        {
            "from_dimensional_entity_schema_name": "gold",
            "from_dimensional_entity_name": "FactSalesOrder",
            "from_dimensional_attribute_name": "CustomerKey",
            "to_dimensional_entity_schema_name": "gold",
            "to_dimensional_entity_name": "DimCustomer",
            "to_dimensional_attribute_name": "CustomerKey",
            "dimensional_relationship_is_active": True,
            "dimensional_relationship_is_locked": False,
        },
    )
]
_DIMENSIONAL_MODEL = {
    "entities": deepcopy(_DIMENSIONAL_ENTITIES),
    "attributes": deepcopy(_DIMENSIONAL_ATTRIBUTES),
    "relationships": deepcopy(_DIMENSIONAL_RELATIONSHIPS),
}
_FACT_TYPES = [
    {"code": "transaction", "description": "One row per business event at its lowest detail."},
    {
        "code": "periodic_snapshot",
        "description": "One row per thing per period, such as daily stock levels.",
    },
]
INPUT_EXAMPLES["dimensional"].update(
    {
        "subject_area_context": deepcopy(INPUT_EXAMPLES["logical"]["subject_area_context"]),
        "selected_logical_entities": [
            {
                "selection_order": 1,
                "entity": deepcopy(_LOGICAL_ENTITIES[1]),
                "attributes": deepcopy(_LOGICAL_ATTRIBUTES[2:]),
            }
        ],
        "existing_entities": deepcopy(_DIMENSIONAL_MODEL),
        "neighbor_entities": [
            {
                "schema": "gold",
                "name": "DimDate",
                "type": "dimension",
                "grain": None,
                "natural_keys": [{"name": "CalendarDate", "type": "DATE"}],
                "linked_via": ["relationship"],
            }
        ],
        "entity_directory": [
            {
                "schema": "gold",
                "name": "DimProduct",
                "type": "dimension",
                "summary": "One row per product.",
            }
        ],
        "logical_links": [
            {
                "from": "silver.SalesOrder.CustomerID",
                "to": "silver.Customer",
                "cardinality": "many_to_one",
            }
        ],
        "dimensional_fact_types": deepcopy(_FACT_TYPES),
        "logical_entities": deepcopy(_LOGICAL_ENTITIES),
        "logical_attributes": deepcopy(_LOGICAL_ATTRIBUTES),
        "logical_relationships": deepcopy(_LOGICAL_RELATIONSHIPS),
        "dimensional_entities": deepcopy(_DIMENSIONAL_ENTITIES),
        "dimensional_attributes": deepcopy(_DIMENSIONAL_ATTRIBUTES),
        "dimensional_relationships": deepcopy(_DIMENSIONAL_RELATIONSHIPS),
    }
)


# Subject Area runs see their Objects (all or some of the Bronze Input Scope) in compact
# form, by table_index id.
INPUT_EXAMPLES["subject_area"] = {
    "source_context": deepcopy(INPUT_EXAMPLES["analysis"]["source_context"]),
    "gds_context": deepcopy(INPUT_EXAMPLES["analysis"]["gds_context"]),
    "table_index": [
        {
            "table": f"t{position}",
            **{
                name: entry[name]
                for name in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                )
            },
        }
        for position, entry in enumerate(INPUT_EXAMPLES["analysis"]["object_context"], start=1)
    ],
    "scope_tables": [
        {
            "table": f"t{position}",
            "description": entry["object_description"],
            "zone_code": entry["zone_code"],
            "row_count": None,
            "column_count": len(group["attributes"]),
            "column_names": [attribute["attribute_name"] for attribute in group["attributes"]],
        }
        for position, (entry, group) in enumerate(
            zip(
                INPUT_EXAMPLES["analysis"]["object_context"],
                INPUT_EXAMPLES["analysis"]["object_attribute_context"],
                strict=True,
            ),
            start=1,
        )
    ],
    "table_links": [{"from": "t1", "to": "t2", "validation_result": "supported", "edge_count": 1}],
    "existing_subject_areas": [
        {
            "name": "Sales",
            "definition": "Customer orders and the customers who place them.",
            "is_active": True,
            "is_locked": False,
            "tables": ["t1", "t2"],
            "locked_tables": [],
            "other_table_count": 0,
        }
    ],
    "context_records": deepcopy(INPUT_EXAMPLES["analysis"]["context_records"]),
}

# Use one complete saved validation example in each physical modeling workflow.
# These are aggregate measurements, never sample source rows.
for _relationship_workflow in ("analysis", "logical"):
    _relationship_groups = INPUT_EXAMPLES[_relationship_workflow]["object_relationship_context"]
    _relationship_attribute = (
        "customer_id" if _relationship_workflow == "logical" else "CustomerCode"
    )
    _relationship_example = {
        **{
            f"{side}_{name}": value
            for side, group in zip(("from", "to"), _relationship_groups, strict=True)
            for name, value in group.items()
            if name not in {"incoming_relationships", "outgoing_relationships"}
        },
        "from_attribute_name": _relationship_attribute,
        "to_attribute_name": _relationship_attribute,
        "relationship_kind": "reference",
        "inferred_cardinality": "many_to_one",
        "analysis_result_status": "active",
        "analysis_result_is_locked": False,
        "validation_policy_version": "1.0.0",
        "validation_result": "supported",
        "validation_source_non_null_count": 20,
        "validation_source_distinct_count": 10,
        "validation_target_non_null_count": 10,
        "validation_target_distinct_count": 10,
        "validation_source_missing_target_count": 0,
        "validation_unused_target_count": 0,
        "validation_duplicate_target_key_count": 0,
    }
    _relationship_groups[0]["outgoing_relationships"] = [deepcopy(_relationship_example)]
    _relationship_groups[1]["incoming_relationships"] = [deepcopy(_relationship_example)]

# The selected Logical Order traces to Orders only. Its saved relationship to
# Customers remains contextual without making that second Object a selected source.
for _physical_input in (
    "source_context",
    "object_context",
    "object_attribute_context",
    "ingestion_mapping",
    "object_relationship_context",
):
    INPUT_EXAMPLES["dimensional"][_physical_input] = deepcopy(
        INPUT_EXAMPLES["logical"][_physical_input][:1]
    )

INPUT_EXAMPLES["dimensional_optimize"] = {
    **{
        name: deepcopy(INPUT_EXAMPLES["dimensional"][name])
        for name in WORKFLOW_INPUTS["dimensional_optimize"]
        if name in INPUT_EXAMPLES["dimensional"]
    },
    "model_summary": {
        "entities": [
            {
                "schema": "gold",
                "name": "DimCustomer",
                "type": "dimension",
                "fact_type": None,
                "grain": None,
                "subject_areas": ["Order Capture", "Billing"],
                "keys": [],
                "attribute_count": 1,
                "logical_sources": ["silver.Customer"],
                "is_locked": False,
            }
        ],
        "relationships": [
            {"from": "gold.FactSalesOrder.CustomerKey", "to": "gold.DimCustomer", "role": None}
        ],
    },
    "conformance_candidates": [
        {"reason": "same_logical_source", "dimensions": ["gold.DimCustomer", "gold.Customer"]}
    ],
    "type_conflicts": [],
    "name_variants": [{"kind": "entity", "names": ["gold.DimCustomer", "gold.DimCustomers"]}],
    "entity_details": deepcopy(INPUT_EXAMPLES["dimensional"]["existing_entities"]),
}


def workflow_input_contracts(workflow: str) -> dict[str, dict[str, Any]]:
    contracts = {
        name: {**deepcopy(INPUT_SHAPES[shape]), "example": deepcopy(INPUT_EXAMPLES[workflow][name])}
        for name, shape in WORKFLOW_INPUTS.get(workflow, {}).items()
    }
    if workflow in {"dimensional", "dimensional_optimize"}:
        for name in (
            "source_context",
            "object_context",
            "object_attribute_context",
            "ingestion_mapping",
            "object_relationship_context",
        ):
            contracts[name]["description"] = (
                "Read-only physical support traced from active lineage of the selected Logical "
                "Entities/Attributes; it does not expand Dimensional authoring sources. "
                + contracts[name]["description"]
            )
        contracts["object_attribute_context"]["description"] += (
            " selected_attribute_names lists included physical evidence, "
            "not eligible Dimensional lineage."
        )
    return contracts


# The two enrichment workflows reuse the five foundational inputs. Their Object and
# Attribute shapes, defined below, add the registered physical descriptions.
for _enrichment_workflow in ("metadata_enrichment_object", "metadata_enrichment_attribute"):
    WORKFLOW_INPUTS[_enrichment_workflow] = {
        "source_context": "source_context",
        "gds_context": "gds_context",
        "object_context": "metadata_enrichment.object_context",
        "object_attribute_context": "metadata_enrichment.object_attribute_context",
        "ingestion_mapping": "ingestion_mapping",
    }
    INPUT_EXAMPLES[_enrichment_workflow] = {
        name: deepcopy(INPUT_EXAMPLES["analysis"][name][:1])
        for name in WORKFLOW_INPUTS[_enrichment_workflow]
    }
    INPUT_EXAMPLES[_enrichment_workflow]["object_context"][0]["registered_object_description"] = (
        "ERP sales order headers."
    )
    _attribute_group = INPUT_EXAMPLES[_enrichment_workflow]["object_attribute_context"][0]
    _attribute_group["attributes"].append(
        {
            **deepcopy(_attribute_group["attributes"][0]),
            "attribute_name": "OrderID",
            "attribute_description": "Business identifier of this ERP sales order.",
            "is_natural_key": True,
            "profile": None,
        }
    )
    _attribute_group["attributes"][0]["registered_attribute_description"] = "Customer code."
    _attribute_group["attributes"][1]["registered_attribute_description"] = None
    _attribute_group["selected_attribute_names"] = (
        [] if _enrichment_workflow == "metadata_enrichment_object" else ["CustomerCode"]
    )

# Saved Project findings remain distinct from registered physical key/nullability/masking.
for _examples in INPUT_EXAMPLES.values():
    for _group in _examples.get("object_attribute_context", []):
        for _attribute in _group.get("attributes", []):
            _attribute["registered_is_natural_key"] = _attribute["is_natural_key"]
            for _flag in ("is_primary_key", "is_nullable", "is_pii"):
                _attribute.setdefault(_flag, None)
INPUT_SHAPES["object_attribute_context"]["description"] += (
    " Descriptions, inferred types and is_natural_key/is_primary_key/is_nullable/is_pii "
    "are current Project enrichment. NULL means unknown, not false. Multiple true key flags "
    "identify members of the chosen composite key, not independently unique columns. "
    "registered_is_natural_key, attribute_nullability and is_masking_required remain "
    "registered physical metadata. Keep registered and enriched key findings separate, "
    "including disagreements; neither flag alone proves observed uniqueness. "
    "profile contains saved counts, percentages, lengths and measurement scope; batch "
    "profiles cannot establish whole-table uniqueness or non-nullability. PII is an "
    "inferred classification and must not weaken registered masking requirements."
)

# Enrichment replaces the saved Project descriptions, so it also needs the
# registered physical descriptions, as separate read-only fields.
INPUT_SHAPES["metadata_enrichment.object_context"] = deepcopy(INPUT_SHAPES["object_context"])
INPUT_SHAPES["metadata_enrichment.object_context"]["description"] = (
    "The selected physical Object. object_description is the current saved Project "
    "description; registered_object_description is registered physical metadata."
)
INPUT_SHAPES["metadata_enrichment.object_attribute_context"] = deepcopy(
    INPUT_SHAPES["object_attribute_context"]
)
INPUT_SHAPES["metadata_enrichment.object_attribute_context"]["description"] += (
    " registered_attribute_description is registered physical metadata, separate from "
    "the Project attribute_description."
)
_object_entry = INPUT_SHAPES["metadata_enrichment.object_context"]["schema"]["$defs"][
    "object_context_entry"
]
_attribute_entry = INPUT_SHAPES["metadata_enrichment.object_attribute_context"]["schema"]["$defs"][
    "object_attribute_context_entry"
]["properties"]["attributes"]["items"]
for _entry, _field, _project_field in (
    (_object_entry, "registered_object_description", "object_description"),
    (_attribute_entry, "registered_attribute_description", "attribute_description"),
):
    _entry["properties"][_field] = {
        "type": ["string", "null"],
        "description": "Registered physical description; read-only evidence, independent "
        f"of the Project-owned {_project_field}.",
    }
    _entry["required"].append(_field)

# Per-table Analysis makes one call per selected table. Every call sees the same key
# directory of all selected tables by short id (t1, t2, ... in selection order) and its
# own focus table in full; answers and saved findings cite columns as `t2.column`.
_TABLE_ID = {"type": "string", "pattern": r"^t[1-9][0-9]*$"}
_COLUMN_ID = {"type": "string", "pattern": r"^t[1-9][0-9]*\..+$"}
_TABLE_KEY_FIELDS = (
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
)
_TABLE_PROPERTIES: dict[str, Any] = {
    "table": _TABLE_ID,
    **{name: {"type": "string", "minLength": 1} for name in _TABLE_KEY_FIELDS},
    "object_description": {"type": ["string", "null"]},
    "zone_code": {"type": "string", "minLength": 1},
}
_COUNT = {"type": ["integer", "null"], "minimum": 0}
_KEY_PROFILE_FIELDS = (
    "row_scope",
    "row_count",
    "non_null_count",
    "null_count",
    "distinct_count",
    "min_data_length",
    "max_data_length",
)
_KEY_COLUMN: dict[str, Any] = {
    "type": "object",
    "properties": {
        "attribute_name": {"type": "string", "minLength": 1},
        "attribute_description": {"type": ["string", "null"]},
        "attribute_data_type": {"type": ["string", "null"]},
        "attribute_inferred_data_type": {"type": ["string", "null"]},
        "registered_is_natural_key": {"type": "boolean"},
        "is_surrogate_key": {"type": ["boolean", "null"]},
        "is_natural_key": {"type": ["boolean", "null"]},
        "is_primary_key": {"type": ["boolean", "null"]},
        "profile": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "row_scope": {"enum": ["all_rows", "batch", None]},
                        **{name: _COUNT for name in _KEY_PROFILE_FIELDS[1:]},
                    },
                    "required": list(_KEY_PROFILE_FIELDS),
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
        "registered_is_natural_key",
        "is_surrogate_key",
        "is_natural_key",
        "is_primary_key",
        "profile",
    ],
    "additionalProperties": False,
}
_OTHER_COLUMN: dict[str, Any] = {
    "type": "object",
    "properties": {
        "attribute_name": {"type": "string", "minLength": 1},
        "attribute_data_type": {"type": ["string", "null"]},
        "attribute_inferred_data_type": {"type": ["string", "null"]},
    },
    "required": ["attribute_name", "attribute_data_type", "attribute_inferred_data_type"],
    "additionalProperties": False,
}
INPUT_SHAPES["analysis.focus_table"] = {
    "description": "The one selected table this call analyzes, by its key_directory id, with "
    "every eligible column in full: descriptions, registered attribute_data_type and Project "
    "attribute_inferred_data_type, registered and Project key flags, and saved Profiles.",
    "schema": {
        "type": "object",
        "properties": {
            **deepcopy(_TABLE_PROPERTIES),
            "attributes": {
                "type": "array",
                "minItems": 1,
                "items": deepcopy(
                    INPUT_SHAPES["object_attribute_context"]["schema"]["$defs"][
                        "object_attribute_context_entry"
                    ]["properties"]["attributes"]["items"]
                ),
            },
        },
        "required": [*_TABLE_PROPERTIES, "attributes"],
        "additionalProperties": False,
    },
}
INPUT_SHAPES["analysis.key_directory"] = {
    "description": "Every selected table of this run, the focus table included, by short id. "
    "key_columns are the columns other tables can point to: a registered or Project key "
    "flag, or a saved Profile in which every non-null value is distinct (operational "
    "columns only when flagged). A table without such a column lists every eligible column "
    "with both data types in other_columns instead.",
    "schema": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                **deepcopy(_TABLE_PROPERTIES),
                "key_columns": {"type": "array", "items": deepcopy(_KEY_COLUMN)},
                "other_columns": {"type": "array", "items": deepcopy(_OTHER_COLUMN)},
            },
            "required": [*_TABLE_PROPERTIES, "key_columns", "other_columns"],
            "additionalProperties": False,
        },
    },
}
INPUT_SHAPES["analysis.focus_ingestion_mapping"] = deepcopy(INPUT_SHAPES["ingestion_mapping"])
INPUT_SHAPES["analysis.focus_ingestion_mapping"]["description"] = (
    "Registered Object-level lineage into or out of the focus table only. It is "
    "provenance: a table is never related to its own copy."
)
INPUT_SHAPES["analysis.saved_relationships"] = {
    "description": "Saved Analysis findings between two tables of this run that touch the "
    "focus table, cited as tN.column. Status, lock and the last measured validation are "
    "read-only evidence.",
    "schema": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "from": _COLUMN_ID,
                "to": _COLUMN_ID,
                "relationship_kind": {"type": "string", "minLength": 1},
                "inferred_cardinality": {
                    "enum": ["one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"]
                },
                "analysis_result_status": {"enum": ["active", "inactive", "deprecated"]},
                "analysis_result_is_locked": {"type": "boolean"},
                "validation_result": {"enum": ["supported", "inconclusive", "unsupported", None]},
                **{
                    name: _COUNT
                    for name in (
                        "validation_source_non_null_count",
                        "validation_source_distinct_count",
                        "validation_target_non_null_count",
                        "validation_target_distinct_count",
                        "validation_source_missing_target_count",
                        "validation_unused_target_count",
                        "validation_duplicate_target_key_count",
                    )
                },
            },
            "required": [
                "from",
                "to",
                "relationship_kind",
                "inferred_cardinality",
                "analysis_result_status",
                "analysis_result_is_locked",
                "validation_result",
                "validation_source_non_null_count",
                "validation_source_distinct_count",
                "validation_target_non_null_count",
                "validation_target_distinct_count",
                "validation_source_missing_target_count",
                "validation_unused_target_count",
                "validation_duplicate_target_key_count",
            ],
            "additionalProperties": False,
        },
    },
}
# The shared inputs come first and are identical in every call of a run.
WORKFLOW_INPUTS["analysis_per_table"] = {
    "source_context": "source_context",
    "gds_context": "gds_context",
    "context_records": "context_records",
    "key_directory": "analysis.key_directory",
    "focus_table": "analysis.focus_table",
    "ingestion_mapping": "analysis.focus_ingestion_mapping",
    "saved_relationships": "analysis.saved_relationships",
}
_orders, _customers = (
    {
        "table": table,
        **{
            name: value
            for name, value in entry.items()
            if name in (*_TABLE_KEY_FIELDS, "object_description", "zone_code")
        },
    }
    for table, entry in zip(("t1", "t2"), INPUT_EXAMPLES["analysis"]["object_context"], strict=True)
)
_customer_code = INPUT_EXAMPLES["analysis"]["object_attribute_context"][1]["attributes"][0]
INPUT_EXAMPLES["analysis_per_table"] = {
    "source_context": deepcopy(INPUT_EXAMPLES["analysis"]["source_context"]),
    "gds_context": deepcopy(INPUT_EXAMPLES["analysis"]["gds_context"]),
    "context_records": deepcopy(INPUT_EXAMPLES["analysis"]["context_records"]),
    "key_directory": [
        {
            **_orders,
            "key_columns": [],
            "other_columns": [
                {
                    "attribute_name": "CustomerCode",
                    "attribute_data_type": "VARCHAR",
                    "attribute_inferred_data_type": "VARCHAR",
                }
            ],
        },
        {
            **_customers,
            "key_columns": [
                {
                    **{name: _customer_code[name] for name in _KEY_COLUMN["required"]},
                    "profile": {
                        name: _customer_code["profile"][name] for name in _KEY_PROFILE_FIELDS
                    },
                }
            ],
            "other_columns": [],
        },
    ],
    "focus_table": {
        **_orders,
        "attributes": deepcopy(
            INPUT_EXAMPLES["analysis"]["object_attribute_context"][0]["attributes"]
        ),
    },
    "ingestion_mapping": deepcopy(INPUT_EXAMPLES["analysis"]["ingestion_mapping"][:1]),
    "saved_relationships": [
        {
            "from": "t1.CustomerCode",
            "to": "t2.CustomerCode",
            "relationship_kind": "reference",
            "inferred_cardinality": "many_to_one",
            "analysis_result_status": "active",
            "analysis_result_is_locked": False,
            "validation_result": "supported",
            "validation_source_non_null_count": 1000,
            "validation_source_distinct_count": 100,
            "validation_target_non_null_count": 100,
            "validation_target_distinct_count": 100,
            "validation_source_missing_target_count": 0,
            "validation_unused_target_count": 0,
            "validation_duplicate_target_key_count": 0,
        }
    ],
}
