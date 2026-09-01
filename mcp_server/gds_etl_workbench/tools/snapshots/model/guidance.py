"""Machine-readable authoring guidance for every Model Snapshot dataset."""

from __future__ import annotations

from collections.abc import MutableMapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel

from gds_etl_workbench.domain.mapping_contracts import (
    AttributeMappingTransformationDocumentV1,
    MappingPackageDocumentV1,
    ObjectMappingTransformationDocumentV1,
)
from gds_etl_workbench.tools.snapshots.dataset_description import (
    DatasetColumnAcceptedValues,
    DatasetColumnDescription,
    DatasetDescription,
    JsonScalar,
)

_CONSTRAINT_KEYS = (
    "$ref",
    "format",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
    "items",
    "x-gds-authoritative-validator",
    "x-gds-authoring-tool",
    "x-gds-governed-authoring-schema",
    "x-gds-stage-record-validation",
)


@dataclass(frozen=True, slots=True)
class ColumnGuidance:
    description: str
    population_guidance: str
    examples: tuple[JsonScalar, ...] = ()


_TARGET_FIELDS = [
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
]

_COMMON_DIGEST_ALGORITHM = {
    "hash": "sha256",
    "encoding": "utf-8",
    "target_natural_key_normalization": {
        "applies_to": _TARGET_FIELDS,
        "operations_in_order": [
            "strip_leading_and_trailing_u+0020",
            "unicode_default_casefold",
        ],
    },
    "canonical_json": {
        "ensure_ascii": False,
        "sort_keys": True,
        "separators": [",", ":"],
        "allow_nan": False,
    },
}

_QA_MAPPING_ENTRY_FIELDS = [
    "modeled_entity_type",
    "target",
    "mapping_context_digest",
]
_QA_CODE_ENTRY_FIELDS = [
    "modeled_entity_type",
    "target",
    "artifact_type",
    "generated_code_digest",
]
_QA_CURRENT_CODE_REFERENCE_FIELDS = [
    *_TARGET_FIELDS,
    "modeled_entity_type",
    "artifact_type",
    "generated_code_digest",
]

_DATASET_RULES: dict[str, tuple[str, ...]] = {
    "model_details": (
        "The future Model graph must contain exactly one Model Details record.",
        "model_name must be unique among active Models for the Tenant; authoritative server "
        "validation checks the current database.",
        "Naming instructions and column templates are independent optional policies. Preserve "
        "null when a policy is not configured; never invent one.",
    ),
    "model_scope": (
        "This is server-derived read-only Snapshot context. Never stage or edit Model Scope "
        "records through a Model Change Set.",
        "Eligibility booleans are authoritative derived workflow gates; never infer eligibility "
        "from zone_code alone.",
    ),
    "profiling_profile": (
        "Profile only an active eligible Bronze Attribute and populate measured aggregates, "
        "never sampled physical rows.",
        "row_count equals non_null_count plus null_count; blank_count and distinct_count cannot "
        "exceed non_null_count; min_data_length cannot exceed max_data_length.",
        "Optional metrics use null when not measured. Percentages, when present, are between 0 "
        "and 100 inclusive.",
    ),
    "analysis_result": (
        "Both different endpoints must be active eligible Bronze Attributes in Model Scope.",
        "An inference-only relationship sets every validation_* field to null. Deterministic "
        "validation populates all nine validation fields together; partial validation is invalid.",
        "Relationship basis and confidence describe the inference independently from optional "
        "measured validation.",
    ),
    "modeling_assertion_document": (
        "Store normalized source-document metadata only; never store original file bytes, raw "
        "prompts, raw rows, credentials, secrets, or raw tool output.",
        "When tenant_code or system_code is present, it must identify the Model Tenant or an "
        "active System respectively.",
    ),
    "modeling_assertion_record": (
        "Reference an existing Modeling Assertion Document by exact name and record one "
        "normalized factual assertion, not raw source content.",
        "applicable_layers contains unique declared layers. A downstream support may reference "
        "this Assertion only for a listed layer.",
        "Structured details and source location must remain bounded safe JSON without secrets, "
        "raw prompts, raw rows, file contents, or raw tool output.",
    ),
    "conceptual_object": (
        "Use stable business concepts supported by active eligible Bronze Objects or applicable "
        "Assertions; never fabricate support.",
        "Aliases and supports must each be unique after Model key normalization.",
    ),
    "conceptual_relationship": (
        "Both endpoints must reference Conceptual Objects in the future Model graph and must "
        "differ.",
        "Record relationship and cardinality basis explicitly; unknown cardinality is allowed "
        "only when the evidence is unresolved.",
    ),
    "logical_submodel": (
        "Use a stable optional grouping for Logical Entities; Entity memberships reference the "
        "Submodel by exact name.",
    ),
    "logical_entity": (
        "Use an evidence-backed third-normal-form Entity with explicit grain, dependency order, "
        "confidence, and active eligible Bronze Object or applicable Assertion sources.",
        "logical_entity_type_detail is present only when logical_entity_type is other.",
    ),
    "logical_attribute": (
        "Reference a Logical Entity in the future graph and retain active eligible Bronze "
        "Attribute or applicable Assertion sources.",
        "Natural and surrogate key flags are mutually exclusive; every primary, natural, or "
        "surrogate key is non-nullable.",
    ),
    "logical_relationship": (
        "Both endpoint Entity/Attribute pairs must exist in the future Logical graph and must "
        "differ.",
        "Record relationship and cardinality basis from evidence; never infer a key relationship "
        "from names alone.",
    ),
    "dimensional_submodel": (
        "Use a stable optional business-process grouping for Dimensional Entities; Entity "
        "memberships reference the Submodel by exact name.",
    ),
    "dimensional_entity": (
        "Use only active eligible Silver contributions backed by applied Logical Mapping or an "
        "applicable Assertion source.",
        "Facts require dimensional_fact_type; facts and bridges require an explicit grain; "
        "dimensions must not populate dimensional_fact_type.",
    ),
    "dimensional_attribute": (
        "Reference a Dimensional Entity in the future graph and retain active eligible Silver "
        "Attribute contributions backed by applied Logical Mapping or applicable Assertions.",
        "Measure fields are all required for measures, with aggregation basis required when not "
        "additive; non-measures leave measure fields null.",
        "A non-none key role requires role key or technical, and audit role must exactly match "
        "the audit-column flag.",
    ),
    "dimensional_relationship": (
        "Both endpoint Entity/Attribute pairs must exist in the future Dimensional graph and "
        "must differ.",
        "For Fact/Bridge-to-Dimension relationships, set optionality explicitly from projected "
        "foreign-key nullability; never infer it from cardinality.",
    ),
    "mapping_dependency": (
        "Create one dependency per modeled layer and active source System represented by Mapping.",
        "Use a non-negative dependency order derived from proven source prerequisites; lower "
        "orders execute first.",
    ),
    "mapping_object": (
        "The physical Object key is the eligible registered target: Silver for logical_entity "
        "Mapping or Gold for dimensional_entity Mapping. source_system_code is the contributing "
        "active source System.",
        "Reference an existing modeled Entity and matching Mapping Dependency. An active record "
        "requires both parents active.",
        "The six authored fields—artifact type, generation instructions, profile key/version, "
        "package, and Object transformation—must be all present or all null. Use governed "
        "mapping-authoring tool output; never hand-build the package.",
    ),
    "mapping_attribute": (
        "The physical Attribute key is an eligible target Attribute and must belong to the exact "
        "parent Mapping Object identified by target, source System, layer, and Entity.",
        "Reference an existing modeled Attribute on that Entity. An active record requires its "
        "Mapping Object and modeled Attribute active.",
        "Use the governed mapping-authoring tool's complete direct/expression transformation; "
        "null means the registered binding remains unauthored.",
    ),
    "generated_code": (
        "Apply complete Mapping first. Do not co-stage Mapping and generated_code.",
        "Copy target_mapping_context_digest and target_source_context_digest from the latest "
        "get_model_code_generation_document result for this exact target Object.",
        "Set generated_code_digest to the lowercase SHA-256 of generated_code_content UTF-8 "
        "bytes. Keep the complete artifact in one logical record.",
        "Apply stores Model state only. It never executes or deploys the artifact.",
    ),
    "qa_authoring_context": (
        "This is a bounded, server-derived, read-only Snapshot dataset. Never stage it in a "
        "Model Change Set.",
        "Select the exact tenant_code and pipeline/source system_code row. Copy its trusted "
        "mapping_context_digest and code_context_digest unchanged into every Validation Group "
        "for that System.",
        "current_code_references is the authoritative allowlist of current relevant Code. Join "
        "only those references to generated_code and ignore every unreferenced artifact.",
        "A null code_context_digest with an empty current_code_references list means no current "
        "relevant Code exists; QA may then author from applied Mapping alone.",
    ),
    "validation_group": (
        "Apply complete Mapping first. Apply relevant generated_code first when Code exists; "
        "do not co-stage either upstream dataset with QA.",
        "Copy both context digests unchanged from the exact qa_authoring_context Snapshot row "
        "for the Validation Group System.",
        "code_context_digest is required when that trusted row lists current relevant Code and "
        "null only when its current_code_references list is empty.",
        "A Validation Group is keyed by Model-owned tenant_code, pipeline/source system_code, "
        "and validation_group_name.",
    ),
    "validation_check": (
        "Stage the owning validation_group in the same QA Change Set or reference an applied "
        "Group with the same Tenant, System, and Group name.",
        "Query A is validation_query_sql. Query B is "
        "validation_comparison_query_sql and is present only for query comparisons.",
        "executes_successfully passes when Query A completes; it does not require a returned "
        "value, ignores result cardinality, and requires null result type, null Query B, "
        "value_type none, and null value.",
        "Every other operator requires Query A, and Query B when present, to return exactly "
        "one row and one column at runtime. Each cell uses validation_result_data_type. Any "
        "other cardinality is a query-contract execution error, not an assertion failure.",
        "Every physical SQL relation must be catalog.schema.table. Only a temporary relation "
        "declared earlier in the same SQL batch may be unqualified. Apply never executes SQL.",
    ),
}

_MODELED_LAYER_DATASETS = frozenset(
    {
        "conceptual_object",
        "conceptual_relationship",
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
        "logical_relationship",
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
    }
)

_MODELED_FIELD_GUIDANCE: dict[str, ColumnGuidance] = {
    "conceptual_object_type": ColumnGuidance(
        "Stable business classification of the Conceptual Object.",
        "Use a concise domain classification supported by the evidence; do not use a database ID.",
    ),
    "conceptual_object_grain": ColumnGuidance(
        "Business grain represented by one occurrence of the Conceptual Object.",
        "State what one instance represents and preserve unresolved grain as needs_review rather "
        "than guessing.",
    ),
    "conceptual_object_aliases": ColumnGuidance(
        "Alternative business names for the Conceptual Object.",
        "Use a JSON array of unique non-duplicated aliases; use an empty array when none are "
        "known.",
    ),
    "conceptual_relationship_type": ColumnGuidance(
        "Stable business classification of the Conceptual Relationship.",
        "Use the relationship kind supported by the business evidence; do not use a database ID.",
    ),
    "conceptual_relationship_cardinality": ColumnGuidance(
        "Business cardinality between the two Conceptual Objects.",
        "Use one_to_one, one_to_many, many_to_one, or many_to_many when supported; otherwise use "
        "unknown and explain the gap in the basis.",
    ),
    "conceptual_relationship_basis": ColumnGuidance(
        "Evidence and reasoning supporting the Conceptual Relationship.",
        "Explain why the relationship exists using the attached supports; never fabricate "
        "evidence.",
    ),
    "conceptual_relationship_cardinality_basis": ColumnGuidance(
        "Evidence and reasoning supporting the stated Conceptual cardinality.",
        "Explain the cardinality independently from the general relationship basis.",
    ),
    "logical_entity_type": ColumnGuidance(
        "Governed Logical Entity classification.",
        "Choose the exact schema literal that matches the Entity's business behavior; use other "
        "only with a populated type detail.",
    ),
    "logical_entity_type_detail": ColumnGuidance(
        "Custom Logical Entity classification when type is other.",
        "Populate only when logical_entity_type is other; otherwise use null.",
    ),
    "logical_entity_grain": ColumnGuidance(
        "Business grain represented by one Logical Entity row.",
        "State one-row meaning from physical or Assertion evidence before defining keys.",
    ),
    "logical_entity_dependency_order": ColumnGuidance(
        "Non-negative dependency order used to sequence Logical processing.",
        "Use zero or a higher integer derived from proven dependencies; lower orders run first.",
    ),
    "logical_attribute_data_type": ColumnGuidance(
        "Canonical modeled data type of the Logical Attribute.",
        "Choose the type supported by source values and target policy; never narrow silently.",
    ),
    "logical_attribute_is_nullable": ColumnGuidance(
        "Whether the Logical Attribute may be null.",
        "Set from grain, key, and source evidence; every primary, natural, or surrogate key is "
        "false.",
    ),
    "logical_attribute_is_primary_key": ColumnGuidance(
        "Whether the Logical Attribute participates in the primary key.",
        "Set true only from supported grain/key evidence; a true value requires non-nullability.",
    ),
    "logical_attribute_is_natural_key": ColumnGuidance(
        "Whether the Logical Attribute is a business natural-key component.",
        "Set true only from supported business identity evidence; it cannot also be surrogate.",
    ),
    "logical_attribute_is_surrogate_key": ColumnGuidance(
        "Whether the Logical Attribute is a generated surrogate-key component.",
        "Set true only under an explicit modeling policy; it cannot also be natural.",
    ),
    "logical_attribute_ordinal_position": ColumnGuidance(
        "One-based deterministic position of the Logical Attribute within its Entity.",
        "Use a positive position unique within the Entity and preserve intended column order.",
    ),
    "logical_attribute_is_audit_column": ColumnGuidance(
        "Whether the Logical Attribute is a policy-driven audit column.",
        "Set true only for an explicit audit policy column and retain that policy as "
        "rationale/source.",
    ),
    "logical_relationship_cardinality": ColumnGuidance(
        "Cardinality between the two Logical Entity/Attribute endpoints.",
        "Choose the exact supported cardinality and explain its independent evidence basis.",
    ),
    "logical_relationship_basis": ColumnGuidance(
        "Evidence and reasoning supporting the Logical Relationship.",
        "Explain the key/business evidence; names alone are insufficient.",
    ),
    "logical_relationship_cardinality_basis": ColumnGuidance(
        "Evidence and reasoning supporting the Logical cardinality.",
        "Explain the cardinality independently from the general relationship basis.",
    ),
    "dimensional_entity_type": ColumnGuidance(
        "Dimensional role of the Entity: fact, dimension, or bridge.",
        "Choose from the declared business process and grain, not naming convention alone.",
    ),
    "dimensional_fact_type": ColumnGuidance(
        "Fact behavior for a fact Entity.",
        "Populate exactly for fact Entities; use null for dimensions and bridges.",
    ),
    "dimensional_entity_grain_definition": ColumnGuidance(
        "Declared row grain for a fact or bridge Entity.",
        "Populate for facts and bridges before measures; dimensions may use null.",
    ),
    "dimensional_entity_dependency_order": ColumnGuidance(
        "Non-negative dependency order used to sequence Dimensional processing.",
        "Use zero or a higher integer derived from proven dependencies; lower orders run first.",
    ),
    "dimensional_attribute_data_type": ColumnGuidance(
        "Canonical target data type of the Dimensional Attribute.",
        "Choose the type supported by Silver lineage and target policy; never narrow silently.",
    ),
    "dimensional_attribute_is_nullable": ColumnGuidance(
        "Whether the Dimensional Attribute may be null.",
        "Set from grain, role, key, and source evidence; non-none key roles require false.",
    ),
    "dimensional_attribute_ordinal_position": ColumnGuidance(
        "One-based deterministic position of the Dimensional Attribute within its Entity.",
        "Use a positive position unique within the Entity and preserve intended column order.",
    ),
    "dimensional_attribute_role": ColumnGuidance(
        "Semantic dimensional role of the Attribute.",
        "Choose the exact role supported by the model; measure and audit roles activate their "
        "corresponding field contracts.",
    ),
    "dimensional_attribute_key_role": ColumnGuidance(
        "Key role played by the Dimensional Attribute.",
        "Use none when not a key; any other value requires Attribute role key or technical and "
        "non-nullability.",
    ),
    "dimensional_attribute_is_grain_component": ColumnGuidance(
        "Whether the Attribute participates in the declared Dimensional grain.",
        "Set true only when the Attribute is part of the explicit row grain.",
    ),
    "dimensional_attribute_additivity": ColumnGuidance(
        "Additivity behavior of a measure.",
        "Populate only for measure Attributes; use null for non-measures.",
    ),
    "dimensional_attribute_default_aggregation": ColumnGuidance(
        "Default aggregation used for a measure.",
        "Populate only for measures and choose the aggregation supported by the measure semantics.",
    ),
    "dimensional_attribute_aggregation_basis": ColumnGuidance(
        "Reason the measure's aggregation behavior is valid.",
        "Required for non-additive or semi-additive measures; use null for additive measures and "
        "non-measures when no explanation is needed.",
    ),
    "dimensional_attribute_change_behavior": ColumnGuidance(
        "History/change-handling behavior of the Dimensional Attribute.",
        "Choose the exact supported behavior from business history requirements.",
    ),
    "dimensional_attribute_is_audit_column": ColumnGuidance(
        "Whether the Dimensional Attribute is an audit column.",
        "Set true exactly when dimensional_attribute_role is audit; otherwise false.",
    ),
    "dimensional_relationship_kind": ColumnGuidance(
        "Structural kind of the Dimensional Relationship.",
        "Choose the exact fact/dimension/bridge relationship kind supported by the endpoint roles.",
    ),
    "dimensional_relationship_cardinality": ColumnGuidance(
        "Cardinality between the two Dimensional Entity/Attribute endpoints.",
        "Choose the exact supported cardinality and explain its independent evidence basis.",
    ),
    "dimensional_relationship_is_optional": ColumnGuidance(
        "Whether the projected foreign key may be null.",
        "Set explicitly from projected foreign-key nullability; never infer it from cardinality.",
    ),
    "dimensional_relationship_role_name": ColumnGuidance(
        "Optional role-playing name for the relationship.",
        "Use a stable role name when one Dimension plays multiple roles; otherwise use null.",
    ),
    "dimensional_relationship_basis": ColumnGuidance(
        "Evidence and reasoning supporting the Dimensional Relationship.",
        "Explain the business process and lineage evidence; names alone are insufficient.",
    ),
    "dimensional_relationship_cardinality_basis": ColumnGuidance(
        "Evidence and reasoning supporting the Dimensional cardinality.",
        "Explain cardinality independently from relationship optionality and the general basis.",
    ),
}

_DATASET_FIELD_GUIDANCE: dict[tuple[str, str], ColumnGuidance] = {
    ("conceptual_object", "supports"): ColumnGuidance(
        "Evidence links supporting the Conceptual Object.",
        "Include unique active eligible Bronze Object or applicable Assertion evidence with "
        "reason, confidence, status, and lock fields; use an empty array only when status is not "
        "active.",
    ),
    ("conceptual_relationship", "supports"): ColumnGuidance(
        "Evidence links supporting the Conceptual Relationship.",
        "Include unique active eligible Bronze Object or applicable Assertion evidence with an "
        "explicit relationship reason.",
    ),
    ("logical_entity", "submodels"): ColumnGuidance(
        "Logical Submodel memberships for the Entity.",
        "Reference each existing Logical Submodel by exact name at most once; use an empty array "
        "when unassigned.",
    ),
    ("logical_entity", "sources"): ColumnGuidance(
        "Physical or Assertion sources supporting the Logical Entity.",
        "Include unique active eligible Bronze Object evidence or applicable Assertions with "
        "source order, rationale, status, and lock fields.",
    ),
    ("logical_attribute", "sources"): ColumnGuidance(
        "Physical Attribute or Assertion sources supporting the Logical Attribute.",
        "Include unique active eligible Bronze Attribute evidence or applicable Assertions with "
        "source order, rationale, status, and lock fields.",
    ),
    ("dimensional_entity", "submodels"): ColumnGuidance(
        "Dimensional Submodel memberships for the Entity.",
        "Reference each existing Dimensional Submodel by exact name at most once; use an empty "
        "array when unassigned.",
    ),
    ("dimensional_entity", "sources"): ColumnGuidance(
        "Silver Object or Assertion sources supporting the Dimensional Entity.",
        "Include unique active eligible Silver Object contributions backed by applied Logical "
        "Mapping or applicable Assertions, with source role and rationale.",
    ),
    ("dimensional_attribute", "sources"): ColumnGuidance(
        "Silver Attribute or Assertion sources supporting the Dimensional Attribute.",
        "Include unique active eligible Silver Attribute contributions backed by applied Logical "
        "Mapping or applicable Assertions, with source order and rationale.",
    ),
}

_OTHER_DATASETS = frozenset(
    {
        "model_details",
        "model_scope",
        "profiling_profile",
        "analysis_result",
        "modeling_assertion_document",
        "modeling_assertion_record",
        "mapping_dependency",
        "mapping_object",
        "mapping_attribute",
    }
)

_ADDITIONAL_FIELD_GUIDANCE: dict[tuple[str, str], ColumnGuidance] = {
    ("model_details", "model_name"): ColumnGuidance(
        "Canonical user-facing name of this Model.",
        "Use one stable nonblank name unique among active Models for the Tenant; never use a "
        "database ID.",
    ),
    ("model_details", "model_description"): ColumnGuidance(
        "Optional plain-language purpose and scope of the Model.",
        "Describe the business purpose concisely; use null when no description is configured.",
    ),
    ("model_details", "silver_model_naming_instructions"): ColumnGuidance(
        "Optional naming policy for Silver target registration.",
        "Preserve the complete configured policy text exactly; use null when absent and never "
        "invent instructions.",
    ),
    ("model_details", "silver_model_audit_columns_template"): ColumnGuidance(
        "Optional structured Silver audit-column policy template.",
        "Preserve the complete configured JSON object for target registration; use null when "
        "absent and never infer template members.",
    ),
    ("model_details", "gold_model_naming_instructions"): ColumnGuidance(
        "Optional naming policy for Gold target registration.",
        "Preserve the complete configured policy text exactly; use null when absent and never "
        "invent instructions.",
    ),
    ("model_details", "gold_model_technical_columns_template"): ColumnGuidance(
        "Optional structured Gold technical-column policy template.",
        "Preserve the complete configured JSON object for target registration; use null when "
        "absent and never infer template members.",
    ),
    ("model_details", "gold_model_audit_columns_template"): ColumnGuidance(
        "Optional structured Gold audit-column policy template.",
        "Preserve the complete configured JSON object for target registration; use null when "
        "absent and never infer template members.",
    ),
    ("model_scope", "zone_code"): ColumnGuidance(
        "Physical medallion zone of the scoped Object.",
        "Read the exact server-derived zone code. It is context, not sufficient proof of any "
        "workflow eligibility flag.",
    ),
    ("model_scope", "is_bronze_source_eligible"): ColumnGuidance(
        "Whether this Object is eligible physical input for Logical modeling and Mapping.",
        "Treat the server-derived boolean as authoritative; do not derive it from zone_code.",
    ),
    ("model_scope", "is_dimensional_source_eligible"): ColumnGuidance(
        "Whether this Silver Object is an eligible contribution to Dimensional modeling.",
        "Treat the server-derived boolean as authoritative; it includes applied Logical Mapping "
        "eligibility, not only zone membership.",
    ),
    ("model_scope", "is_logical_mapping_target_eligible"): ColumnGuidance(
        "Whether this registered Object may be a Logical Mapping target.",
        "Treat the server-derived boolean as authoritative for Silver Mapping target selection.",
    ),
    ("model_scope", "is_dimensional_mapping_target_eligible"): ColumnGuidance(
        "Whether this registered Object may be a Dimensional Mapping target.",
        "Treat the server-derived boolean as authoritative for Gold Mapping target selection.",
    ),
    ("model_scope", "is_active"): ColumnGuidance(
        "Whether this Model Scope Object is effective.",
        "Read the server-derived value; inactive scope cannot authorize downstream work.",
    ),
    ("profiling_profile", "row_count"): ColumnGuidance(
        "Measured total row count for the profiled physical Attribute's Object.",
        "Copy the non-negative measured count; it must equal non_null_count plus null_count.",
    ),
    ("profiling_profile", "non_null_count"): ColumnGuidance(
        "Measured count of non-null Attribute values.",
        "Copy the non-negative measured count; blank_count and distinct_count cannot exceed it.",
    ),
    ("profiling_profile", "null_count"): ColumnGuidance(
        "Measured count of null Attribute values.",
        "Copy the non-negative measured count; together with non_null_count it equals row_count.",
    ),
    ("profiling_profile", "blank_count"): ColumnGuidance(
        "Optional measured count of blank non-null values.",
        "Copy the non-negative measured count when available; otherwise use null. It cannot "
        "exceed non_null_count.",
    ),
    ("profiling_profile", "distinct_count"): ColumnGuidance(
        "Optional measured count of distinct non-null values.",
        "Copy the non-negative measured count when available; otherwise use null. It cannot "
        "exceed non_null_count.",
    ),
    ("profiling_profile", "min_data_length"): ColumnGuidance(
        "Optional minimum measured value length.",
        "Copy the non-negative measured length when applicable; otherwise use null. It cannot "
        "exceed max_data_length.",
    ),
    ("profiling_profile", "max_data_length"): ColumnGuidance(
        "Optional maximum measured value length.",
        "Copy the non-negative measured length when applicable; otherwise use null. It cannot be "
        "less than min_data_length.",
    ),
    ("profiling_profile", "avg_data_length"): ColumnGuidance(
        "Optional average measured value length.",
        "Copy the non-negative measured decimal when applicable; otherwise use null.",
    ),
    ("analysis_result", "relationship_kind"): ColumnGuidance(
        "Stable classification of the candidate physical-Attribute relationship.",
        "Use a concise evidence-backed kind such as foreign_key_candidate; do not encode a "
        "database ID.",
    ),
    ("analysis_result", "relationship_confidence"): ColumnGuidance(
        "Evidence confidence assigned to the candidate relationship.",
        "Use low, medium, or high from inference strength, independently of optional measured "
        "validation.",
    ),
    ("analysis_result", "relationship_basis"): ColumnGuidance(
        "Evidence and reasoning for the candidate relationship.",
        "Explain the inference from metadata/profile/Assertion evidence; never fabricate measured "
        "validation.",
    ),
    ("analysis_result", "validation_policy_version"): ColumnGuidance(
        "Semantic version of the deterministic relationship-validation policy.",
        "Populate only with the other eight validation fields after measured validation; use null "
        "for inference-only analysis.",
    ),
    ("analysis_result", "validation_result"): ColumnGuidance(
        "Outcome of deterministic relationship validation.",
        "Use supported, inconclusive, or unsupported only with the complete validation field "
        "group; otherwise use null.",
    ),
    ("modeling_assertion_document", "modeling_assertion_document_name"): ColumnGuidance(
        "Stable name of the normalized Assertion source document.",
        "Use a unique human-readable name referenced exactly by its Assertion Records.",
    ),
    ("modeling_assertion_document", "tenant_code"): ColumnGuidance(
        "Optional Tenant scope of the Assertion source document.",
        "Use the exact Model Tenant code when tenant-scoped; otherwise use null.",
    ),
    ("modeling_assertion_document", "system_code"): ColumnGuidance(
        "Optional active System scope of the Assertion source document.",
        "Use an exact active System code when system-scoped; otherwise use null.",
    ),
    ("modeling_assertion_document", "modeling_assertion_file_pattern"): ColumnGuidance(
        "Optional bounded file-name or path pattern identifying the source document.",
        "Store only a locator pattern, never file bytes, secrets, or raw source content; use null "
        "when unavailable.",
    ),
    ("modeling_assertion_document", "modeling_assertion_document_type"): ColumnGuidance(
        "Optional stable classification of the Assertion source document.",
        "Use a concise code such as requirements when known; otherwise use null.",
    ),
    ("modeling_assertion_document", "modeling_assertion_document_description"): ColumnGuidance(
        "Optional plain-language description of the Assertion source.",
        "Describe provenance without copying raw document content; use null when unnecessary.",
    ),
    ("modeling_assertion_document", "modeling_assertion_document_metadata"): ColumnGuidance(
        "Bounded safe structured metadata about the Assertion source document.",
        "Use a JSON object with normalized metadata only. Never include raw content, prompts, "
        "rows, credentials, secrets, or tool output; use an empty object when none exists.",
    ),
    ("modeling_assertion_document", "is_active"): ColumnGuidance(
        "Whether this Assertion source document is effective.",
        "Use true for an effective document or false to retain inactive provenance.",
    ),
    ("modeling_assertion_record", "modeling_assertion_record_key"): ColumnGuidance(
        "Stable canonical key of one normalized factual Assertion.",
        "Use the bounded identifier pattern and keep it stable across revisions; never use a "
        "database ID.",
    ),
    ("modeling_assertion_record", "modeling_assertion_document_name"): ColumnGuidance(
        "Exact owning Assertion Document name.",
        "Copy the canonical name of an existing Modeling Assertion Document.",
    ),
    ("modeling_assertion_record", "modeling_assertion_record_type"): ColumnGuidance(
        "Stable classification of the factual Assertion.",
        "Use a concise code describing the assertion kind, not a database ID.",
    ),
    ("modeling_assertion_record", "modeling_assertion_text"): ColumnGuidance(
        "Normalized human-readable factual Assertion.",
        "State one durable fact; never paste raw prompts, raw rows, document contents, secrets, or "
        "tool output.",
    ),
    ("modeling_assertion_record", "modeling_assertion_details"): ColumnGuidance(
        "Bounded structured details supporting the factual Assertion.",
        "Use safe normalized JSON only; never include raw prompts, rows, files, credentials, "
        "secrets, or tool output. Use an empty object when no details are needed.",
    ),
    ("modeling_assertion_record", "modeling_assertion_source_location"): ColumnGuidance(
        "Optional bounded structured locator within the source document.",
        "Store a safe page/section/cell-style locator, never source contents; use null when no "
        "location is available.",
    ),
    ("modeling_assertion_record", "modeling_assertion_applicable_layers"): ColumnGuidance(
        "Unique Model layers for which this Assertion is valid support.",
        "Choose unique values from analysis, conceptual, logical, dimensional, and mapping; do "
        "not claim a layer unsupported by the fact.",
    ),
    ("modeling_assertion_record", "modeling_assertion_confidence"): ColumnGuidance(
        "Optional confidence assigned to the normalized Assertion.",
        "Use low, medium, or high when confidence is known; otherwise use null.",
    ),
    ("mapping_dependency", "modeled_entity_type"): ColumnGuidance(
        "Modeled layer whose Mapping uses the source System.",
        "Use logical_entity for Bronze-to-Silver or dimensional_entity for Silver-to-Gold.",
    ),
    ("mapping_dependency", "source_system_code"): ColumnGuidance(
        "Active source System participating in Mapping for the modeled layer.",
        "Copy the exact active pipeline/source System code; never use the target System code by "
        "assumption.",
    ),
    ("mapping_dependency", "source_system_dependency_order"): ColumnGuidance(
        "Non-negative execution dependency order for this source System and modeled layer.",
        "Derive from proven prerequisites; lower orders execute before higher orders.",
    ),
    ("mapping_object", "source_system_code"): ColumnGuidance(
        "Active source System contributing to this target Object Mapping.",
        "Copy the exact System represented by lineage and the matching Mapping Dependency.",
    ),
    ("mapping_object", "modeled_entity_type"): ColumnGuidance(
        "Modeled layer that produces the target Object.",
        "Use logical_entity for an eligible Silver target or dimensional_entity for Gold.",
    ),
    ("mapping_object", "modeled_entity_name"): ColumnGuidance(
        "Exact modeled Entity bound to the target Object and source System.",
        "Copy an existing Entity name from the declared modeled_entity_type layer.",
    ),
    ("mapping_object", "object_dependency_order"): ColumnGuidance(
        "Non-negative execution dependency order for the target Object Mapping.",
        "Derive from proven target dependencies; lower orders execute before higher orders.",
    ),
    ("mapping_object", "artifact_type"): ColumnGuidance(
        "Artifact representation required for generated implementation code.",
        "Use sql_file, python_file, or python_notebook from governed materialization. The six "
        "authored Mapping Object fields must be all present or all null.",
    ),
    ("mapping_object", "artifact_generation_instructions"): ColumnGuidance(
        "Complete bounded instructions for generating the target artifact.",
        "Copy governed materializer output exactly. It is present only with every other authored "
        "Mapping Object field; never include secrets or placeholders.",
    ),
    ("mapping_object", "mapping_profile_key"): ColumnGuidance(
        "Deployed Mapping contract profile key for the package.",
        "Copy the exact key returned by governed materialization; never invent or substitute a "
        "profile.",
    ),
    ("mapping_object", "mapping_profile_version"): ColumnGuidance(
        "Semantic version of the deployed Mapping contract profile.",
        "Copy the exact major.minor.patch version paired with mapping_profile_key.",
    ),
    ("mapping_object", "mapping_package_document"): ColumnGuidance(
        "Complete normalized executable Mapping package bound to the declared profile.",
        "Copy the governed validate-and-materialize result; never hand-build or reconstruct it. "
        "It is present only with the full authored field group.",
    ),
    ("mapping_object", "object_mapping_transformation_document"): ColumnGuidance(
        "Complete normalized Object-level direct or derived transformation contract.",
        "Copy schema_version 1.0 governed materializer output. Null means the binding is "
        "unauthored, not an implicit direct transformation.",
    ),
    ("mapping_attribute", "source_system_code"): ColumnGuidance(
        "Active source System inherited from the exact parent Mapping Object.",
        "Match the parent Mapping Object and Mapping Dependency exactly.",
    ),
    ("mapping_attribute", "modeled_entity_type"): ColumnGuidance(
        "Modeled layer inherited from the exact parent Mapping Object.",
        "Match the parent: logical_entity for Silver or dimensional_entity for Gold.",
    ),
    ("mapping_attribute", "modeled_entity_name"): ColumnGuidance(
        "Exact modeled Entity inherited from the parent Mapping Object.",
        "Copy the parent Entity name exactly; never bind the Attribute across Entities.",
    ),
    ("mapping_attribute", "modeled_attribute_name"): ColumnGuidance(
        "Exact modeled Attribute projected to the physical target Attribute.",
        "Copy an existing active Attribute name on modeled_entity_name in the declared layer.",
    ),
    ("mapping_attribute", "attribute_mapping_transformation_document"): ColumnGuidance(
        "Optional normalized direct or expression transformation for the target Attribute.",
        "Copy schema_version 1.0 governed materializer output. Null means the binding is "
        "unauthored; a completed direct mapping is explicit.",
    ),
}

_PROFILE_PERCENT_FIELDS = {
    "percent_populated": "populated values",
    "percent_duplicates": "duplicate non-null values",
    "percent_null": "null values",
    "percent_blank": "blank values",
    "percent_distinct": "distinct non-null values",
}

_ANALYSIS_VALIDATION_COUNT_FIELDS = {
    "validation_source_non_null_count": "non-null source endpoint values",
    "validation_source_distinct_count": "distinct non-null source endpoint values",
    "validation_target_non_null_count": "non-null target endpoint values",
    "validation_target_distinct_count": "distinct non-null target endpoint values",
    "validation_source_missing_target_count": "source values missing from the target",
    "validation_unused_target_count": "target values unused by the source",
    "validation_duplicate_target_key_count": "duplicate candidate target keys",
}

_NESTED_FIELD_GUIDANCE: dict[str, ColumnGuidance] = {
    "modeling_assertion_record_key": ColumnGuidance(
        "Stable key of the referenced Modeling Assertion Record.",
        "Copy the exact canonical key from an existing Assertion Record applicable to the owning "
        "Model layer.",
    ),
    "support_source_type": ColumnGuidance(
        "Discriminator selecting the physical or Assertion evidence variant.",
        "Use exactly the schema literal matching the populated source field; never populate the "
        "other variant.",
    ),
    "source_object": ColumnGuidance(
        "Complete physical Object natural key used as evidence or lineage.",
        "Populate every nested key field from one eligible physical Object for the owning layer.",
    ),
    "source_attribute": ColumnGuidance(
        "Complete physical Attribute natural key used as lineage.",
        "Populate every nested key field from one eligible physical Attribute for the owning "
        "layer.",
    ),
    "assertion_record": ColumnGuidance(
        "Complete canonical key of a Modeling Assertion used as evidence.",
        "Reference an existing effective Assertion Record whose applicable_layers includes the "
        "owning Model layer.",
    ),
    "support_role": ColumnGuidance(
        "Optional semantic role played by this evidence source.",
        "Use a concise evidence role when needed to distinguish supports; otherwise use null.",
    ),
    "support_reason": ColumnGuidance(
        "Required evidence-backed reason this source supports the owning record.",
        "Explain the direct relationship between the evidence and modeled claim; never use a "
        "placeholder.",
    ),
    "support_reason_detail": ColumnGuidance(
        "Optional additional evidence reasoning.",
        "Add bounded clarification when support_reason is insufficient; otherwise use null.",
    ),
    "support_confidence": ColumnGuidance(
        "Confidence assigned to this evidence link.",
        "Use low, medium, or high from evidence strength; do not overstate unresolved support.",
    ),
    "support_status": ColumnGuidance(
        "Lifecycle status of this evidence link.",
        "Use active for effective support, needs_review for unresolved support, and inactive or "
        "deprecated only for explicit retirement.",
    ),
    "support_is_locked": ColumnGuidance(
        "Whether this applied evidence link is protected from replacement.",
        "Preserve the applied value; use false for a new unlocked support and never alter a locked "
        "one.",
    ),
    "source_order": ColumnGuidance(
        "Optional positive precedence order among sources for the owning record.",
        "Use a positive integer only when source precedence is evidenced; otherwise use null.",
    ),
    "rationale": ColumnGuidance(
        "Required reasoning for using this lineage source.",
        "Explain how the source contributes to the modeled record; never use a placeholder.",
    ),
    "status": ColumnGuidance(
        "Lifecycle status of this source link.",
        "Use active for effective lineage, needs_review for unresolved lineage, and inactive or "
        "deprecated only for explicit retirement.",
    ),
    "is_locked": ColumnGuidance(
        "Whether this applied source link is protected from replacement.",
        "Preserve the applied value; use false for a new unlocked link and never alter a locked "
        "one.",
    ),
    "source_role": ColumnGuidance(
        "Required role played by this source in the Dimensional record.",
        "Use a concise business-process role supported by lineage; never invent one from names.",
    ),
    "submodel_name": ColumnGuidance(
        "Exact Submodel referenced by this membership.",
        "Copy an existing Submodel name from the owning Logical or Dimensional layer.",
    ),
    "membership_status": ColumnGuidance(
        "Lifecycle status of this Submodel membership.",
        "Use active for effective membership, needs_review for unresolved membership, and inactive "
        "or deprecated only for explicit retirement.",
    ),
    "membership_is_locked": ColumnGuidance(
        "Whether this applied Submodel membership is protected from replacement.",
        "Preserve the applied value; use false for a new membership and never alter a locked one.",
    ),
}

_NESTED_DEFINITION_GUIDANCE: dict[str, ColumnGuidance] = {
    "AssertionRecordKey": ColumnGuidance(
        "Canonical reference to one Modeling Assertion Record.",
        "Use the exact stable Assertion key and verify that it applies to the owning layer.",
    ),
    "ObjectSupportRecord": ColumnGuidance(
        "Conceptual evidence link backed by one physical Object.",
        "Use an eligible Bronze Object and record explicit reason, confidence, lifecycle, and "
        "lock.",
    ),
    "AssertionSupportRecord": ColumnGuidance(
        "Conceptual evidence link backed by one Modeling Assertion.",
        "Use an existing Assertion applicable to Conceptual work and record explicit support "
        "reason, confidence, lifecycle, and lock.",
    ),
    "SupportRecord": ColumnGuidance(
        "Discriminated Conceptual support: physical Object or Modeling Assertion.",
        "Choose exactly one variant with support_source_type and populate its complete fields.",
    ),
    "LogicalObjectSourceRecord": ColumnGuidance(
        "Logical Entity lineage backed by one eligible Bronze Object.",
        "Use the complete physical key plus rationale, optional precedence, lifecycle, and lock.",
    ),
    "LogicalAssertionSourceRecord": ColumnGuidance(
        "Logical Entity lineage backed by one applicable Modeling Assertion.",
        "Use the complete Assertion key plus rationale, optional precedence, lifecycle, and lock.",
    ),
    "LogicalEntitySourceRecord": ColumnGuidance(
        "Discriminated Logical Entity source: Bronze Object or Modeling Assertion.",
        "Choose exactly one variant with support_source_type and populate its complete fields.",
    ),
    "AttributePhysicalSourceRecord": ColumnGuidance(
        "Modeled Attribute lineage backed by one eligible physical Attribute.",
        "Logical uses Bronze; Dimensional uses Silver backed by applied Logical Mapping. Include "
        "the complete key, rationale, optional precedence, lifecycle, and lock.",
    ),
    "AttributeAssertionSourceRecord": ColumnGuidance(
        "Modeled Attribute lineage backed by one applicable Modeling Assertion.",
        "Use the complete Assertion key plus rationale, optional precedence, lifecycle, and lock.",
    ),
    "AttributeSourceRecord": ColumnGuidance(
        "Discriminated Attribute source: physical Attribute or Modeling Assertion.",
        "Choose exactly one variant with support_source_type and populate its complete fields.",
    ),
    "DimensionalObjectSourceRecord": ColumnGuidance(
        "Dimensional Entity lineage backed by one eligible Silver Object contribution.",
        "Require applied Logical Mapping and include source role, rationale, optional precedence, "
        "lifecycle, and lock.",
    ),
    "DimensionalAssertionSourceRecord": ColumnGuidance(
        "Dimensional Entity lineage backed by one applicable Modeling Assertion.",
        "Include source role, complete Assertion key, rationale, optional precedence, lifecycle, "
        "and lock.",
    ),
    "DimensionalEntitySourceRecord": ColumnGuidance(
        "Discriminated Dimensional Entity source: Silver Object or Modeling Assertion.",
        "Choose exactly one variant with support_source_type and populate its complete fields.",
    ),
    "PhysicalObjectKey": ColumnGuidance(
        "Complete ID-free physical Object natural key.",
        "Populate all key fields from one eligible Metadata Object; never substitute database IDs.",
    ),
    "PhysicalAttributeKey": ColumnGuidance(
        "Complete ID-free physical Attribute natural key.",
        "Populate all key fields from one eligible Metadata Attribute; never substitute database "
        "IDs.",
    ),
    "SubmodelMembershipRecord": ColumnGuidance(
        "Lifecycle-bound membership in one same-layer Submodel.",
        "Reference an existing Submodel by exact name and preserve lifecycle and lock fields.",
    ),
    "QACurrentCodeReference": ColumnGuidance(
        "Trusted read-only reference to one current Code target relevant to a QA System.",
        "Join generated_code by every field. The nested system_code is the Code target System, not "
        "the outer QA pipeline/source System.",
    ),
    "ValidationLiteral": ColumnGuidance(
        "Scalar literal allowed by Validation Check assertion contracts.",
        "Use boolean, integer, finite decimal, text, date text, or timestamp text exactly as "
        "required by validation_result_data_type and the chosen assertion shape.",
    ),
}

_GOVERNED_MAPPING_CONTRACTS: dict[tuple[str, str], type[BaseModel]] = {
    ("mapping_object", "mapping_package_document"): MappingPackageDocumentV1,
    (
        "mapping_object",
        "object_mapping_transformation_document",
    ): ObjectMappingTransformationDocumentV1,
    (
        "mapping_attribute",
        "attribute_mapping_transformation_document",
    ): AttributeMappingTransformationDocumentV1,
}

_GOVERNED_MAPPING_DEFINITION_GUIDANCE: dict[str, ColumnGuidance] = {
    "MappingPackageDocumentV1": ColumnGuidance(
        "Exact normalized executable Mapping package produced for one target and source System.",
        "Author it inside MappingCandidateV1 and pass that complete candidate to "
        "validate_and_materialize_mapping_candidate; stage only the returned record.",
    ),
    "MappingLoadV1": ColumnGuidance(
        "Target write and concurrent-System execution semantics for the Mapping package.",
        "Derive write mode, merge keys, partitioning, and concurrency from target grain and "
        "orchestration behavior.",
    ),
    "NamedStepV1": ColumnGuidance(
        "One named transformation step in the package dependency graph.",
        "Use declared source aliases or step outputs as inputs and keep dependencies acyclic.",
    ),
    "PackageBatchRuleV1": ColumnGuidance(
        "Optional bounded batch rule for one executable source.",
        "Use only the source Object's declared batch Attribute and canonical unique values.",
    ),
    "PackageExecutableSourceV1": ColumnGuidance(
        "One physical source Object that generated code may read.",
        "Select it from trusted Mapping authoring context and give it one stable SQL-safe alias.",
    ),
    "PackageProvenanceV1": ColumnGuidance(
        "Non-executable original-ingestion or prior-Mapping lineage for one source Object.",
        "Copy only context-provided IDs and populate exactly the ID list allowed by lineage_kind.",
    ),
    "PydanticProfileV1": ColumnGuidance(
        "Deployed Mapping profile identity and exact schema digest.",
        "Copy key, version, and digest unchanged from get_model_mapping_authoring_context.",
    ),
    "RuntimeParameterV1": ColumnGuidance(
        "One declared runtime parameter consumed by generated orchestration code.",
        "Define a stable name, type, purpose, and safe default without credentials or secrets.",
    ),
    "SourceSystemDependencyV1": ColumnGuidance(
        "Required predecessor source System for this Mapping package.",
        "Copy the exact predecessor and reason from trusted Mapping authoring context.",
    ),
    "TargetDependencyV1": ColumnGuidance(
        "Required predecessor target Object for this Mapping package.",
        "Copy the exact predecessor and reason from trusted Mapping authoring context.",
    ),
    "ObjectMappingTransformationDocumentV1": ColumnGuidance(
        "Exact Object-level direct or derived transformation for one modeled Entity binding.",
        "Author it only inside MappingCandidateV1 using package source aliases, then stage the "
        "governed materializer output.",
    ),
    "ObjectAggregationV1": ColumnGuidance(
        "One named aggregate output in an Object transformation.",
        "Declare deterministic logic and the complete unique set of grouping inputs.",
    ),
    "ObjectFilterV1": ColumnGuidance(
        "One deterministic row filter in an Object transformation.",
        "Write a nonblank filter expression using only declared inputs.",
    ),
    "ObjectJoinV1": ColumnGuidance(
        "One join between two declared Object source aliases.",
        "Reference only source_aliases and provide an explicit join type and condition.",
    ),
    "ObjectUnionV1": ColumnGuidance(
        "One union across two or more declared Object source aliases.",
        "Use unique aliases and explain deterministic column alignment.",
    ),
    "AttributeMappingTransformationDocumentV1": ColumnGuidance(
        "Exact direct or expression transformation for one modeled-to-target Attribute binding.",
        "Author it only inside MappingCandidateV1 using context source columns, then stage the "
        "governed materializer output.",
    ),
    "AttributeSourceColumnV1": ColumnGuidance(
        "One physical source Attribute addressed through a declared executable alias.",
        "Copy the alias and Attribute ID from trusted Mapping authoring context.",
    ),
}

_GOVERNED_MAPPING_FIELD_GUIDANCE: dict[str, ColumnGuidance] = {
    "schema_version": ColumnGuidance(
        "Version discriminator for this governed Mapping JSON contract.",
        "Use the exact literal 1.0; do not substitute the Model or profile version.",
    ),
    "package_ref": ColumnGuidance(
        "Stable SQL-safe identifier for this complete Mapping package.",
        "Choose one nonblank identifier that remains stable while authoring the same package.",
    ),
    "route": ColumnGuidance(
        "Modeled-to-physical route governed by this package.",
        "Use logical_to_silver for a Logical target or dimensional_to_gold for a Dimensional "
        "target, matching the requested authoring context.",
    ),
    "target_object_id": ColumnGuidance(
        "Database ID of the exact registered target Object in trusted authoring context.",
        "Copy context.target.object_id unchanged; never guess or reuse a source Object ID.",
    ),
    "artifact_type": ColumnGuidance(
        "Complete generated artifact representation expected for this target.",
        "Use sql_file, python_file, or python_notebook according to user and orchestration needs.",
    ),
    "artifact_generation_instructions": ColumnGuidance(
        "Bounded instructions that govern code generation for this Mapping package.",
        "State deterministic orchestration requirements without secrets, credentials, or raw "
        "physical rows.",
    ),
    "pydantic_profile": ColumnGuidance(
        "Exact deployed profile used to validate and normalize the package.",
        "Copy the complete profile object from trusted Mapping authoring context.",
    ),
    "executable_sources": ColumnGuidance(
        "Physical source Objects that generated code is allowed to read.",
        "Include each required context source once with a unique alias; omit lineage-only sources.",
    ),
    "non_executable_provenance": ColumnGuidance(
        "Lineage sources that support the Mapping but are not executable inputs.",
        "Include only context-provided original-ingestion or prior-Mapping provenance.",
    ),
    "runtime_parameters": ColumnGuidance(
        "Bounded runtime parameters required by generated code.",
        "List each parameter once; use an empty list when no runtime parameter is required.",
    ),
    "source_system_dependencies": ColumnGuidance(
        "Predecessor source Systems required before this Mapping can execute.",
        "Copy the complete dependency list and reasons from trusted authoring context.",
    ),
    "target_dependencies": ColumnGuidance(
        "Predecessor target Objects required before this Mapping can execute.",
        "Copy the complete dependency list and reasons from trusted authoring context.",
    ),
    "steps": ColumnGuidance(
        "Complete acyclic transformation-step graph for the package.",
        "Declare every required step once; names and outputs must be unique and inputs resolvable.",
    ),
    "grain_and_deduplication": ColumnGuidance(
        "Target row grain and deterministic duplicate-handling contract.",
        "Copy or refine the modeled Entity grain and state how duplicates are resolved.",
    ),
    "load": ColumnGuidance(
        "Complete target load behavior for generated orchestration code.",
        "Derive it from target keys, grain, partitioning, and concurrent-System behavior.",
    ),
    "write_mode": ColumnGuidance(
        "Target persistence mode: append, overwrite, or merge.",
        "Choose from modeled load semantics; merge requires merge_keys and other modes forbid "
        "them.",
    ),
    "merge_keys": ColumnGuidance(
        "Canonical target Attribute IDs used to match rows during merge.",
        "For merge, copy the complete unique key IDs from context; otherwise use an empty list.",
    ),
    "partition_basis": ColumnGuidance(
        "Optional explanation of target partition behavior.",
        "State the evidence-backed basis when partitioning matters; otherwise use null.",
    ),
    "concurrent_system_write_mode": ColumnGuidance(
        "How multiple source Systems may safely write the same target.",
        "Choose disjoint_partitions, idempotent_merge, or serialized from actual target behavior.",
    ),
    "concurrent_write_basis": ColumnGuidance(
        "Required evidence for the selected concurrent-System write mode.",
        "Explain why concurrent or serialized execution is safe for this target.",
    ),
    "depends_on": ColumnGuidance(
        "Other package step names that must complete before this step.",
        "Use unique declared step names, exclude the current step, and keep the graph acyclic.",
    ),
    "inputs": ColumnGuidance(
        "Executable source aliases or prior step outputs consumed by this step.",
        "List each declared input once and never reference an undeclared alias or output.",
    ),
    "output": ColumnGuidance(
        "Unique symbolic output produced by this package step.",
        "Use one SQL-safe identifier that later steps may reference.",
    ),
    "attribute_id": ColumnGuidance(
        "Database ID of the batch Attribute on this executable source Object.",
        "Copy the exact source batch_attribute_id from trusted authoring context.",
    ),
    "values": ColumnGuidance(
        "Canonical unique batch values allowed by this source rule.",
        "Use only evidenced signed integer values; the contract normalizes their order.",
    ),
    "object_id": ColumnGuidance(
        "Database ID of one executable source Object in trusted authoring context.",
        "Copy the exact context source Object ID; never substitute a target or unrelated Object.",
    ),
    "alias": ColumnGuidance(
        "Stable SQL-safe alias assigned to this executable source Object.",
        "Use a unique identifier and reuse it exactly in transformations, provenance, and steps.",
    ),
    "role": ColumnGuidance(
        "Business or technical role of this executable source in the Mapping.",
        "Explain its direct contribution to the target; never use a placeholder.",
    ),
    "batch_rule": ColumnGuidance(
        "Optional batch restriction for this executable source.",
        "Populate the complete rule only when the context source declares a batch Attribute; "
        "otherwise use null.",
    ),
    "lineage_kind": ColumnGuidance(
        "Whether provenance came from original ingestion or a prior Mapping.",
        "Use original_ingestion or prior_mapping exactly as represented by context lineage.",
    ),
    "source_object_id": ColumnGuidance(
        "Database ID of the physical Object represented by this provenance.",
        "Copy the exact source Object ID from trusted authoring context.",
    ),
    "ingestion_object_mapping_ids": ColumnGuidance(
        "Original-ingestion Mapping IDs supporting this provenance.",
        "Populate a nonempty context subset only for original_ingestion; otherwise use empty.",
    ),
    "prior_object_mapping_ids": ColumnGuidance(
        "Prior applied Mapping IDs supporting this provenance.",
        "Populate a nonempty context subset only for prior_mapping; otherwise use empty.",
    ),
    "executable_source_aliases": ColumnGuidance(
        "Executable aliases through which this provenance reaches the target.",
        "Use a nonempty unique subset of aliases declared in executable_sources.",
    ),
    "key": ColumnGuidance(
        "Deployed Mapping profile key.",
        "Copy the exact literal key from trusted authoring context.",
    ),
    "version": ColumnGuidance(
        "Deployed semantic version of the Mapping profile.",
        "Copy the exact version paired with the profile key and digest.",
    ),
    "schema_digest": ColumnGuidance(
        "Lowercase SHA-256 digest of the deployed Mapping profile schema.",
        "Copy profile.schema_digest unchanged from trusted authoring context.",
    ),
    "data_type": ColumnGuidance(
        "Declared runtime data type of this parameter.",
        "Use the orchestration-supported type name required by the generated artifact.",
    ),
    "purpose": ColumnGuidance(
        "Required explanation of why this runtime parameter exists.",
        "Describe how generated code uses it without including sensitive values.",
    ),
    "default_value": ColumnGuidance(
        "Optional safe scalar default for this runtime parameter.",
        "Use text, integer, boolean, or null as appropriate; never embed a credential or secret.",
    ),
    "predecessor_source_system_id": ColumnGuidance(
        "Database ID of a predecessor source System.",
        "Copy the exact context dependency ID; do not infer it from names.",
    ),
    "predecessor_target_object_id": ColumnGuidance(
        "Database ID of a predecessor target Object.",
        "Copy the exact context dependency ID; do not infer it from names.",
    ),
    "reason": ColumnGuidance(
        "Required evidence-backed reason this predecessor must complete first.",
        "Copy the trusted context reason unchanged.",
    ),
    "transformation_kind": ColumnGuidance(
        "Discriminator selecting the governed transformation shape.",
        "Use only the literal permitted by the owning Object or Attribute contract.",
    ),
    "source_aliases": ColumnGuidance(
        "Executable source aliases available to this Object transformation.",
        "Use a unique nonempty subset of aliases declared by the Mapping package.",
    ),
    "joins": ColumnGuidance(
        "Deterministic joins required by this Object transformation.",
        "List joins in normalized form; use an empty list when no join is required.",
    ),
    "unions": ColumnGuidance(
        "Deterministic unions required by this Object transformation.",
        "List unions in normalized form; use an empty list when no union is required.",
    ),
    "filters": ColumnGuidance(
        "Deterministic filters required by this Object transformation.",
        "List filters in normalized form; use an empty list when no filter is required.",
    ),
    "aggregations": ColumnGuidance(
        "Named aggregations required by this Object transformation.",
        "Use unique output names; use an empty list when no aggregation is required.",
    ),
    "entity_contribution_logic": ColumnGuidance(
        "Complete logic describing how this binding contributes rows to the modeled Entity.",
        "State the deterministic contribution at target grain using declared aliases and steps.",
    ),
    "rationale": ColumnGuidance(
        "Evidence-backed reason for the selected Object transformation.",
        "Explain how the transformation implements the modeled Entity intent.",
    ),
    "output_name": ColumnGuidance(
        "Unique symbolic output name for this aggregation.",
        "Use one SQL-safe identifier not reused by another aggregation.",
    ),
    "grouping_inputs": ColumnGuidance(
        "Inputs that define grouping grain for this aggregation.",
        "List each grouping input once; use an empty list only for a global aggregate.",
    ),
    "left_alias": ColumnGuidance(
        "Declared source alias on the left side of this join.",
        "Copy one exact value from source_aliases.",
    ),
    "right_alias": ColumnGuidance(
        "Declared source alias on the right side of this join.",
        "Copy one exact value from source_aliases distinct when the join requires it.",
    ),
    "join_type": ColumnGuidance(
        "Relational join type applied to the two aliases.",
        "Use inner, left, right, full, or cross according to evidenced transformation semantics.",
    ),
    "condition": ColumnGuidance(
        "Deterministic join condition for the two aliases.",
        "Reference declared aliases and explicit keys; never infer a condition from names alone.",
    ),
    "input_aliases": ColumnGuidance(
        "Two or more declared source aliases participating in this union.",
        "Use a unique normalized subset of source_aliases.",
    ),
    "all": ColumnGuidance(
        "Whether the union preserves duplicates.",
        "Use true for UNION ALL behavior or false for duplicate elimination, based on target "
        "grain.",
    ),
    "alignment": ColumnGuidance(
        "Deterministic column alignment across union inputs.",
        "Describe output columns, compatible types, and any explicit null or cast behavior.",
    ),
    "source_columns": ColumnGuidance(
        "Physical source columns used by this Attribute transformation.",
        "For direct use exactly one; for expression use the complete unique context-backed set.",
    ),
    "step_output": ColumnGuidance(
        "Optional package step output consumed by this Attribute transformation.",
        "Copy an exact declared package output when needed; otherwise use null.",
    ),
    "source_alias": ColumnGuidance(
        "Executable source alias containing this physical Attribute.",
        "Copy an exact package alias available to the owning Entity binding.",
    ),
    "source_attribute_id": ColumnGuidance(
        "Database ID of the physical source Attribute.",
        "Copy the exact Attribute ID beneath source_alias from trusted authoring context.",
    ),
}

_GOVERNED_MAPPING_OWNER_FIELD_GUIDANCE: dict[tuple[str, str], ColumnGuidance] = {
    ("MappingPackageDocumentV1", "source_system_id"): ColumnGuidance(
        "Database ID of the source System being mapped into this target.",
        "Copy context.source_system.system_id unchanged.",
    ),
    ("PackageProvenanceV1", "source_system_id"): ColumnGuidance(
        "Database ID of the source System that owns this provenance Object.",
        "Copy the exact provenance System ID from trusted context.",
    ),
    ("NamedStepV1", "name"): ColumnGuidance(
        "Stable SQL-safe name of this package step.",
        "Use one unique identifier and reference it exactly from depends_on.",
    ),
    ("RuntimeParameterV1", "name"): ColumnGuidance(
        "Stable SQL-safe runtime parameter name.",
        "Use one unique identifier expected by generated orchestration code.",
    ),
    ("NamedStepV1", "logic"): ColumnGuidance(
        "Complete deterministic transformation logic for this package step.",
        "Explain computation from declared inputs to its single named output.",
    ),
    ("AttributeMappingTransformationDocumentV1", "logic"): ColumnGuidance(
        "Complete plain-language Attribute transformation logic.",
        "Explain how source columns or step output produce the target Attribute.",
    ),
    ("ObjectAggregationV1", "expression"): ColumnGuidance(
        "Deterministic aggregate expression that produces output_name.",
        "Reference declared inputs and state any null or type behavior explicitly.",
    ),
    ("ObjectFilterV1", "expression"): ColumnGuidance(
        "Deterministic predicate applied by this filter.",
        "Reference declared inputs and state null behavior explicitly.",
    ),
    ("AttributeMappingTransformationDocumentV1", "expression"): ColumnGuidance(
        "Optional executable expression for the target Attribute.",
        "Use null for direct; expression requires a nonblank expression using declared sources.",
    ),
}

_FIELD_GUIDANCE: dict[str, dict[str, tuple[str, str]]] = {
    "generated_code": {
        "tenant_code": (
            "Tenant code in the target Object natural key.",
            "Copy the exact target Tenant code from the current Model context.",
        ),
        "system_code": (
            "System code in the target Object natural key.",
            "Copy the exact target Object System code; this is not the QA pipeline System.",
        ),
        "connection_code": (
            "Connection code in the target Object natural key.",
            "Copy the exact target Connection code.",
        ),
        "object_schema": (
            "Schema in the target Object natural key.",
            "Copy the exact target Object schema.",
        ),
        "object_name": (
            "Name in the target Object natural key.",
            "Copy the exact target Object name.",
        ),
        "modeled_entity_type": (
            "Modeled layer that produces the target Object.",
            "Use logical_entity for Silver targets or dimensional_entity for Gold targets.",
        ),
        "artifact_type": (
            "Complete generated artifact representation.",
            "Use the applied Mapping artifact type unless the governed authoring context "
            "explicitly permits another type.",
        ),
        "generated_code_content": (
            "Complete SQL file, Python file, or Python notebook content.",
            "Store one complete UTF-8 artifact in one logical record.",
        ),
        "mapping_context_digest": (
            "Canonical current applied Mapping digest for this exact Code target.",
            "Copy target_mapping_context_digest from get_model_code_generation_document.",
        ),
        "source_context_digest": (
            "Canonical current applied source-context digest for this exact Code target.",
            "Copy target_source_context_digest from get_model_code_generation_document.",
        ),
        "generated_code_digest": (
            "Lowercase SHA-256 digest of the complete artifact content.",
            "Hash generated_code_content encoded as UTF-8; the server recomputes it.",
        ),
        "generated_code_status": (
            "Lifecycle status of the Code Artifact.",
            "Use active for effective code or needs_review for a retained proposal.",
        ),
        "generated_code_is_locked": (
            "Whether the applied Code Artifact is protected from replacement.",
            "Preserve the applied value; use false for a new unlocked artifact.",
        ),
    },
    "qa_authoring_context": {
        "tenant_code": (
            "Exact Model Tenant code for this trusted QA context.",
            "Match this row by the selected Model Tenant; copy it into Validation Groups.",
        ),
        "system_code": (
            "Exact pipeline/source System code represented by applied Mapping.",
            "Match one explicitly selected QA System; do not substitute a target System code.",
        ),
        "mapping_context_digest": (
            "Server-derived aggregate digest of all current Mapping targets for this System.",
            "Copy unchanged into validation_group.mapping_context_digest; never recompute it.",
        ),
        "code_context_digest": (
            "Server-derived aggregate digest of current relevant Code, or null when none exists.",
            "Copy unchanged into validation_group.code_context_digest; never recompute it.",
        ),
        "mapping_target_count": (
            "Bounded count of complete active Mapping target contexts containing this System.",
            "Use as coverage evidence; it must be positive and is not an output quota.",
        ),
        "current_code_target_count": (
            "Bounded count of current relevant Code references for this System.",
            "It must equal current_code_references length and may be zero.",
        ),
        "current_code_references": (
            "Authoritative bounded references to current relevant generated_code records.",
            "Join every reference to generated_code by all published fields, use those Code "
            "contents when present, and ignore unreferenced or stale artifacts.",
        ),
    },
    "validation_group": {
        "tenant_code": (
            "Tenant that owns the Model and Validation Group.",
            "Use the Model Tenant code.",
        ),
        "system_code": (
            "Pipeline/source System whose Mapping coverage this Group validates.",
            "Use one active source System code represented by applied Mapping.",
        ),
        "validation_group_name": (
            "Stable name of the related Validation Check group.",
            "Use the same name in every child validation_check record.",
        ),
        "validation_group_description": (
            "Optional purpose and coverage of the Validation Group.",
            "Use null when no additional explanation is needed; never embed raw data.",
        ),
        "mapping_context_digest": (
            "Aggregate digest of current Mapping contexts relevant to the Group System.",
            "Copy unchanged from the exact qa_authoring_context Snapshot row.",
        ),
        "code_context_digest": (
            "Optional aggregate digest of current Code Artifacts relevant to the Group System.",
            "Copy unchanged from the exact qa_authoring_context Snapshot row, including null.",
        ),
        "is_active": (
            "Whether the Validation Group is effective.",
            "Use true for an effective Group or false to retain it as inactive history.",
        ),
    },
    "validation_check": {
        "tenant_code": (
            "Tenant code inherited from the owning Validation Group.",
            "Match the owning Group exactly.",
        ),
        "system_code": (
            "Pipeline/source System code inherited from the owning Validation Group.",
            "Match the owning Group exactly.",
        ),
        "validation_group_name": (
            "Natural-key name of the owning Validation Group.",
            "Match the owning Group exactly; never use a database ID.",
        ),
        "validation_check_name": (
            "Stable name of this deterministic Validation Check.",
            "Use a unique name within the owning Group.",
        ),
        "validation_check_description": (
            "Optional business or technical intent of the Check.",
            "Explain what failure means; use null when the name is sufficient.",
        ),
        "validation_category_code": (
            "Stable lower-case category used to organize Checks.",
            "Use a bounded code such as technical.execution or business.reconciliation.",
        ),
        "validation_severity": (
            "Operational importance of a failed Check.",
            "Use blocking, warning, or informational.",
        ),
        "validation_query_sql": (
            "Query A: governed Databricks SQL evaluated by later orchestration.",
            "Fully qualify every physical relation as catalog.schema.table. Only a temporary "
            "relation declared earlier in this SQL batch may be unqualified. Use read or "
            "temporary-object SQL only. Except for executes_successfully, the final statement "
            "must return exactly one row and one column at runtime.",
        ),
        "validation_comparison_query_sql": (
            "Optional Query B used as the comparison operand.",
            "Populate only when comparison_value_type is query. Fully qualify physical "
            "relations as catalog.schema.table; only earlier same-batch temporary relations "
            "may be unqualified. Its final statement must return exactly one row and one column.",
        ),
        "validation_result_data_type": (
            "Expected scalar type produced by Query A and its comparison operand.",
            "Use null only for executes_successfully; otherwise both Query A and query-valued "
            "Query B cells must use the exact declared type.",
        ),
        "validation_comparison_operator": (
            "Deterministic assertion applied to Query A.",
            "Choose one operator and satisfy its exact x-gds-assertion-shapes contract.",
        ),
        "validation_comparison_value_type": (
            "Source of the comparison operand.",
            "Use none, literal, literal_list, or query exactly as the operator shape requires.",
        ),
        "validation_comparison_value": (
            "Optional typed literal or homogeneous literal list comparison operand.",
            "Populate only for literal or literal_list; values must match result_data_type.",
        ),
        "is_active": (
            "Whether the Validation Check is effective.",
            "Use true for an effective Check or false to retain it as inactive history.",
        ),
    },
}

_ASSERTION_SHAPES: tuple[dict[str, Any], ...] = (
    {
        "operators": ["executes_successfully"],
        "result_data_types": [None],
        "comparison_query": "must_be_null",
        "comparison_value_types": ["none"],
        "comparison_value": "must_be_null",
        "query_a_must_return_rows": False,
        "query_a_result_cardinality": "ignored",
        "query_b_result_cardinality": "must_be_absent",
        "result_cell_type_field": None,
        "cardinality_mismatch_outcome": "not_applicable",
        "cardinality_mismatch_is_assertion_failure": False,
    },
    {
        "operators": ["is_null", "is_not_null"],
        "result_data_types": ["boolean", "integer", "decimal", "text", "date", "timestamp"],
        "comparison_query": "must_be_null",
        "comparison_value_types": ["none"],
        "comparison_value": "must_be_null",
        "query_a_must_return_rows": True,
        "query_a_result_cardinality": "exactly_one_row_one_column",
        "query_b_result_cardinality": "must_be_absent",
        "result_cell_type_field": "validation_result_data_type",
        "cardinality_mismatch_outcome": "query_contract_execution_error",
        "cardinality_mismatch_is_assertion_failure": False,
    },
    {
        "operators": ["is_true", "is_false"],
        "result_data_types": ["boolean"],
        "comparison_query": "must_be_null",
        "comparison_value_types": ["none"],
        "comparison_value": "must_be_null",
        "query_a_must_return_rows": True,
        "query_a_result_cardinality": "exactly_one_row_one_column",
        "query_b_result_cardinality": "must_be_absent",
        "result_cell_type_field": "validation_result_data_type",
        "cardinality_mismatch_outcome": "query_contract_execution_error",
        "cardinality_mismatch_is_assertion_failure": False,
    },
    {
        "operators": ["equal", "not_equal"],
        "result_data_types": ["boolean", "integer", "decimal", "text", "date", "timestamp"],
        "comparison_query": "required_only_for_query_value_type",
        "comparison_value_types": ["literal", "query"],
        "comparison_value": "required_only_for_literal_value_type",
        "query_a_must_return_rows": True,
        "query_a_result_cardinality": "exactly_one_row_one_column",
        "query_b_result_cardinality": "exactly_one_row_one_column_when_present",
        "result_cell_type_field": "validation_result_data_type",
        "cardinality_mismatch_outcome": "query_contract_execution_error",
        "cardinality_mismatch_is_assertion_failure": False,
    },
    {
        "operators": [
            "greater_than",
            "greater_than_or_equal",
            "less_than",
            "less_than_or_equal",
        ],
        "result_data_types": ["integer", "decimal", "date", "timestamp"],
        "comparison_query": "required_only_for_query_value_type",
        "comparison_value_types": ["literal", "query"],
        "comparison_value": "required_only_for_literal_value_type",
        "query_a_must_return_rows": True,
        "query_a_result_cardinality": "exactly_one_row_one_column",
        "query_b_result_cardinality": "exactly_one_row_one_column_when_present",
        "result_cell_type_field": "validation_result_data_type",
        "cardinality_mismatch_outcome": "query_contract_execution_error",
        "cardinality_mismatch_is_assertion_failure": False,
    },
    {
        "operators": ["in", "not_in"],
        "result_data_types": ["boolean", "integer", "decimal", "text", "date", "timestamp"],
        "comparison_query": "must_be_null",
        "comparison_value_types": ["literal_list"],
        "comparison_value": "required_homogeneous_nonempty_list",
        "query_a_must_return_rows": True,
        "query_a_result_cardinality": "exactly_one_row_one_column",
        "query_b_result_cardinality": "must_be_absent",
        "result_cell_type_field": "validation_result_data_type",
        "cardinality_mismatch_outcome": "query_contract_execution_error",
        "cardinality_mismatch_is_assertion_failure": False,
    },
)


def model_dataset_population_rules(dataset: str) -> tuple[str, ...]:
    """Return concise common and cross-field authoring rules."""
    specific = _DATASET_RULES.get(dataset)
    if specific is None:
        return ()
    record_rule = (
        "Read each complete server-derived record by canonical names; do not stage, edit, or "
        "recompute its values."
        if dataset in {"model_scope", "qa_authoring_context"}
        else "Author one complete record using canonical names rather than database IDs. "
        "Preserve applied lock fields and every nested member not intentionally changed."
    )
    return (
        "Supply every required field and no unlisted field. A required nullable field must "
        "still be present; use null only when its field guidance permits it.",
        record_rule,
        *specific,
    )


def _modeled_field_guidance(dataset: str, field: str) -> ColumnGuidance:
    exact = _DATASET_FIELD_GUIDANCE.get((dataset, field))
    if exact is not None:
        return exact
    exact = _MODELED_FIELD_GUIDANCE.get(field)
    if exact is not None:
        return exact

    label = field.replace("_", " ")
    if field.startswith("from_") or field.startswith("to_"):
        return ColumnGuidance(
            f"Exact referenced {label} endpoint.",
            "Copy the canonical name from the referenced record in the future Model graph; "
            "never invent a database ID or dangling endpoint.",
        )
    if field.endswith("_name"):
        return ColumnGuidance(
            f"Stable canonical name identifying the {label.removesuffix(' name')}.",
            "Use a concise nonblank name that remains stable across revisions. If this is a "
            "reference, copy the exact canonical name from the referenced record.",
        )
    if field.endswith("_definition"):
        return ColumnGuidance(
            f"Plain-language definition of the {label.removesuffix(' definition')}.",
            "Explain business meaning concisely from available evidence; never use a placeholder.",
        )
    if field.endswith("_confidence"):
        return ColumnGuidance(
            f"Evidence confidence assigned to the {label.removesuffix(' confidence')}.",
            "Use low, medium, or high according to evidence strength; unresolved claims use low "
            "or needs_review status rather than invented certainty.",
        )
    if field.endswith("_status"):
        return ColumnGuidance(
            f"Lifecycle status of the {label.removesuffix(' status')}.",
            "Use active only for supported effective work, needs_review for a retained proposal, "
            "and inactive or deprecated only for explicit retirement.",
        )
    if field.endswith("_is_locked"):
        return ColumnGuidance(
            f"Whether the {label.removesuffix(' is locked')} is protected from replacement.",
            "Preserve the applied value. Use false for a new unlocked record; never change a true "
            "value or a locked applied record.",
        )
    raise ValueError(f"Model field guidance is missing for {dataset}.{field}")


def _additional_field_guidance(dataset: str, field: str) -> ColumnGuidance:
    exact = _ADDITIONAL_FIELD_GUIDANCE.get((dataset, field))
    if exact is not None:
        return exact

    physical_fields = {
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "attribute_name",
    }
    if field in physical_fields and dataset in {
        "model_scope",
        "profiling_profile",
        "mapping_object",
        "mapping_attribute",
    }:
        label = field.replace("_", " ")
        if dataset in {"mapping_object", "mapping_attribute"}:
            subject = "eligible registered target"
            layer_rule = (
                "Use the exact Silver target for logical_entity or Gold target for "
                "dimensional_entity."
            )
        elif dataset == "profiling_profile":
            subject = "eligible Bronze Attribute"
            layer_rule = "Copy the exact key from the active eligible Bronze Attribute."
        else:
            subject = "scoped physical Object"
            layer_rule = "Read the exact server-derived key; Model Scope is not writable."
        return ColumnGuidance(
            f"{label.capitalize()} in the {subject} natural key.",
            f"{layer_rule} Preserve the canonical Metadata value; never use a database ID.",
        )

    if dataset == "analysis_result" and (field.startswith("from_") or field.startswith("to_")):
        endpoint, key_field = field.split("_", maxsplit=1)
        return ColumnGuidance(
            f"{key_field.replace('_', ' ').capitalize()} in the {endpoint} physical Attribute "
            "endpoint.",
            "Copy the exact canonical value from an active eligible Bronze Attribute. Every six "
            "fields identify one endpoint; never use a database ID.",
        )

    percentage_subject = _PROFILE_PERCENT_FIELDS.get(field)
    if dataset == "profiling_profile" and percentage_subject is not None:
        return ColumnGuidance(
            f"Optional measured percentage of {percentage_subject}.",
            "Copy the measured decimal between 0 and 100 inclusive when available; otherwise "
            "use null.",
        )

    validation_subject = _ANALYSIS_VALIDATION_COUNT_FIELDS.get(field)
    if dataset == "analysis_result" and validation_subject is not None:
        return ColumnGuidance(
            f"Measured non-negative count of {validation_subject}.",
            "Populate only with all eight other validation fields from the same deterministic "
            "run; use null for inference-only analysis.",
        )

    if field.endswith("_status"):
        return ColumnGuidance(
            f"Lifecycle status of the {field.removesuffix('_status').replace('_', ' ')}.",
            "Use active for effective work, needs_review for a retained proposal, and inactive or "
            "deprecated only for explicit retirement.",
        )
    if field.endswith("_is_locked"):
        return ColumnGuidance(
            f"Whether the {field.removesuffix('_is_locked').replace('_', ' ')} is protected.",
            "Preserve the applied value. Use false for a new unlocked record; never replace a "
            "locked applied record.",
        )
    raise ValueError(f"Model field guidance is missing for {dataset}.{field}")


def _nested_field_guidance(
    dataset: str,
    definition: str,
    field: str,
) -> ColumnGuidance:
    if field in {"source_object", "source_attribute"}:
        subject = "Object" if field == "source_object" else "Attribute"
        if dataset.startswith("dimensional_"):
            return ColumnGuidance(
                f"Complete Silver {subject} natural key used as Dimensional lineage.",
                f"Populate every nested key field from one eligible Silver {subject} backed by "
                "applied Logical Mapping.",
            )
        return ColumnGuidance(
            f"Complete Bronze {subject} natural key used as evidence or Logical lineage.",
            f"Populate every nested key field from one active eligible Bronze {subject}.",
        )

    if field == "assertion_record":
        layer = dataset.split("_", maxsplit=1)[0]
        return ColumnGuidance(
            f"Complete canonical key of a Modeling Assertion used in the {layer} layer.",
            "Reference an existing effective Assertion Record whose applicable_layers contains "
            f"{layer}.",
        )

    exact = _NESTED_FIELD_GUIDANCE.get(field)
    if exact is not None:
        return exact

    physical_fields = {
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "attribute_name",
    }
    if field in physical_fields and definition in {
        "PhysicalObjectKey",
        "PhysicalAttributeKey",
        "QACurrentCodeReference",
    }:
        target = definition == "QACurrentCodeReference"
        if target:
            subject = "current Code target"
            population_guidance = (
                "Copy the exact Code target value with every sibling reference field from "
                "qa_authoring_context. Its system_code is the target System, not the outer QA "
                "pipeline/source System."
            )
        elif dataset.startswith("dimensional_"):
            subject = "eligible Silver source"
            population_guidance = (
                "Copy the exact canonical Metadata value with every sibling key field from a "
                "Silver source backed by applied Logical Mapping; never use a database ID."
            )
        else:
            subject = "active eligible Bronze source"
            population_guidance = (
                "Copy the exact canonical Metadata value with every sibling key field from an "
                "active eligible Bronze source; never use a database ID."
            )
        return ColumnGuidance(
            f"{field.replace('_', ' ').capitalize()} in the complete physical {subject} "
            "natural key.",
            population_guidance,
        )

    qa_guidance = {
        "modeled_entity_type": ColumnGuidance(
            "Modeled layer of the current referenced Code Artifact.",
            "Copy logical_entity or dimensional_entity unchanged from the trusted QA context.",
        ),
        "artifact_type": ColumnGuidance(
            "Artifact representation of the current referenced Code Artifact.",
            "Copy sql_file, python_file, or python_notebook unchanged from trusted QA context.",
        ),
        "generated_code_digest": ColumnGuidance(
            "Lowercase SHA-256 digest identifying the current Code Artifact content.",
            "Copy the trusted digest unchanged and join it with every sibling reference field.",
        ),
    }
    if definition == "QACurrentCodeReference" and field in qa_guidance:
        return qa_guidance[field]
    raise ValueError(f"Nested Model field guidance is missing for {definition}.{field}")


def _governed_mapping_field_guidance(
    definition: str,
    field: str,
) -> ColumnGuidance:
    guidance = _GOVERNED_MAPPING_OWNER_FIELD_GUIDANCE.get((definition, field))
    if guidance is None:
        guidance = _GOVERNED_MAPPING_FIELD_GUIDANCE.get(field)
    if guidance is None:
        raise ValueError(f"Governed Mapping field guidance is missing for {definition}.{field}")
    return guidance


def _annotate_governed_mapping_definition(
    definition_name: str,
    definition_schema: MutableMapping[str, object],
) -> None:
    guidance = _GOVERNED_MAPPING_DEFINITION_GUIDANCE.get(definition_name)
    if guidance is None:
        raise ValueError(f"Governed Mapping definition guidance is missing for {definition_name}")
    definition_schema["description"] = guidance.description
    definition_schema["x-gds-population-guidance"] = guidance.population_guidance
    if definition_schema.get("type") != "object":
        return
    raw_properties = definition_schema.get("properties")
    if not isinstance(raw_properties, dict):
        raise ValueError(f"{definition_name} generated an invalid governed Mapping property schema")
    properties = cast(dict[str, object], raw_properties)
    for field, raw_property_schema in properties.items():
        if not isinstance(raw_property_schema, dict):
            raise ValueError(f"{definition_name}.{field} has no governed Mapping property schema")
        property_schema = cast(dict[str, object], raw_property_schema)
        field_guidance = _governed_mapping_field_guidance(definition_name, field)
        property_schema["description"] = field_guidance.description
        property_schema["x-gds-population-guidance"] = field_guidance.population_guidance


def _governed_mapping_authoring_schema(
    contract: type[BaseModel],
) -> dict[str, object]:
    schema = cast(
        dict[str, object],
        contract.model_json_schema(mode="validation"),
    )
    _annotate_governed_mapping_definition(contract.__name__, schema)
    raw_definitions = schema.get("$defs")
    if isinstance(raw_definitions, dict):
        definitions = cast(dict[str, object], raw_definitions)
        for definition_name, raw_definition_schema in definitions.items():
            if not isinstance(raw_definition_schema, dict):
                raise ValueError(f"{definition_name} has no governed Mapping definition schema")
            _annotate_governed_mapping_definition(
                definition_name,
                cast(dict[str, object], raw_definition_schema),
            )
    return schema


def _attach_governed_mapping_schemas(
    dataset: str,
    schema: MutableMapping[str, object],
) -> None:
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        raise ValueError(f"{dataset} generated an invalid property schema")
    properties = cast(dict[str, object], raw_properties)
    for (contract_dataset, field), contract in _GOVERNED_MAPPING_CONTRACTS.items():
        if contract_dataset != dataset:
            continue
        raw_property_schema = properties.get(field)
        if not isinstance(raw_property_schema, dict):
            raise ValueError(f"{dataset}.{field} has no property schema")
        property_schema = cast(dict[str, object], raw_property_schema)
        property_schema["x-gds-authoritative-validator"] = contract.__name__
        property_schema["x-gds-authoring-tool"] = "validate_and_materialize_mapping_candidate"
        property_schema["x-gds-stage-record-validation"] = (
            "exact"
            if contract is MappingPackageDocumentV1
            else "bounded_outer_shape_only_use_governed_materializer"
        )
        property_schema["x-gds-governed-authoring-schema"] = _governed_mapping_authoring_schema(
            contract
        )


def _data_types(schema: dict[str, object]) -> list[str]:
    values: list[str] = []
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        values.append(raw_type)
    elif isinstance(raw_type, list):
        values.extend(value for value in cast(list[object], raw_type) if isinstance(value, str))
    raw_any_of = schema.get("anyOf")
    if isinstance(raw_any_of, list):
        for branch in cast(list[object], raw_any_of):
            if isinstance(branch, dict):
                for value in _data_types(cast(dict[str, object], branch)):
                    if value not in values:
                        values.append(value)
    return values


def _enum_values(schema: dict[str, object]) -> list[object]:
    if "const" in schema:
        return [schema["const"]]
    raw_enum = schema.get("enum")
    if isinstance(raw_enum, list):
        return cast(list[object], raw_enum)
    raw_any_of = schema.get("anyOf")
    if isinstance(raw_any_of, list):
        values: list[object] = []
        for branch in cast(list[object], raw_any_of):
            if isinstance(branch, dict):
                values.extend(_enum_values(cast(dict[str, object], branch)))
        return values
    return []


def _json_scalar(value: object) -> JsonScalar:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError("Model accepted value is not a JSON scalar")


def _constraints(schema: dict[str, object]) -> dict[str, object]:
    result = {key: deepcopy(schema[key]) for key in _CONSTRAINT_KEYS if key in schema}
    raw_any_of = schema.get("anyOf")
    if isinstance(raw_any_of, list):
        branches = [
            _constraints(cast(dict[str, object], branch))
            for branch in cast(list[object], raw_any_of)
            if isinstance(branch, dict)
        ]
        if branches:
            result["anyOf"] = branches
    return result


def _accepted_values(schema: dict[str, object]) -> DatasetColumnAcceptedValues:
    constraints = _constraints(schema)
    enum_values = _enum_values(schema)
    if "const" in schema:
        return DatasetColumnAcceptedValues(
            kind="fixed",
            values=tuple(_json_scalar(value) for value in enum_values),
            references=(),
            constraints=constraints,
        )
    if enum_values:
        return DatasetColumnAcceptedValues(
            kind="literal",
            values=tuple(_json_scalar(value) for value in enum_values),
            references=(),
            constraints=constraints,
        )
    nonnull_types = [value for value in _data_types(schema) if value != "null"]
    if nonnull_types == ["boolean"]:
        return DatasetColumnAcceptedValues(
            kind="literal",
            values=(False, True),
            references=(),
            constraints=constraints,
        )
    return DatasetColumnAcceptedValues(
        kind="constrained" if constraints else "freeform",
        values=(),
        references=(),
        constraints=constraints,
    )


def _build_description(
    dataset: str,
    schema: MutableMapping[str, object],
) -> DatasetDescription:
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        raise ValueError(f"{dataset} generated an invalid property schema")
    properties = cast(dict[str, object], raw_properties)
    required = set(cast(list[str], schema.get("required", [])))
    canonical_key = set(cast(list[str], schema.get("x-gds-canonical-key", [])))
    columns: list[DatasetColumnDescription] = []
    for field, raw_property_schema in properties.items():
        if not isinstance(raw_property_schema, dict):
            raise ValueError(f"{dataset}.{field} has no property schema")
        property_schema = cast(dict[str, object], raw_property_schema)
        if dataset in _FIELD_GUIDANCE:
            description, population_guidance = _FIELD_GUIDANCE[dataset][field]
            guidance = ColumnGuidance(description, population_guidance)
        elif dataset in _MODELED_LAYER_DATASETS:
            guidance = _modeled_field_guidance(dataset, field)
        elif dataset in _OTHER_DATASETS:
            guidance = _additional_field_guidance(dataset, field)
        else:
            raise ValueError(f"Model dataset guidance is missing for {dataset}")
        if field in canonical_key:
            population_guidance = (
                f"{guidance.population_guidance} This field is part of the canonical key; "
                "changing it identifies a different record."
            )
        else:
            population_guidance = guidance.population_guidance
        accepted_values = _accepted_values(property_schema)
        column = DatasetColumnDescription(
            name=field,
            data_types=tuple(_data_types(property_schema)),
            required=field in required,
            nullable="null" in _data_types(property_schema),
            description=guidance.description,
            population_guidance=population_guidance,
            accepted_values=accepted_values,
            examples=guidance.examples,
        )
        document = column.model_dump(mode="json")
        property_schema["description"] = guidance.description
        property_schema["x-gds-population-guidance"] = population_guidance
        property_schema["x-gds-accepted-values"] = document["accepted_values"]
        if guidance.examples:
            property_schema["examples"] = list(guidance.examples)
        columns.append(column)
    return DatasetDescription(
        population_rules=model_dataset_population_rules(dataset),
        columns=tuple(columns),
    )


def _enrich_nested_definitions(
    dataset: str,
    schema: MutableMapping[str, object],
) -> None:
    raw_definitions = schema.get("$defs")
    if not isinstance(raw_definitions, dict):
        return
    definitions = cast(dict[str, object], raw_definitions)
    for definition_name, raw_definition_schema in definitions.items():
        if not isinstance(raw_definition_schema, dict):
            continue
        definition_schema = cast(dict[str, object], raw_definition_schema)
        definition_guidance = _NESTED_DEFINITION_GUIDANCE.get(definition_name)
        if definition_guidance is None:
            raise ValueError(f"Nested Model definition guidance is missing for {definition_name}")
        definition_schema["description"] = definition_guidance.description
        definition_schema["x-gds-population-guidance"] = definition_guidance.population_guidance
        if definition_schema.get("type") != "object":
            continue
        raw_properties = definition_schema.get("properties")
        if not isinstance(raw_properties, dict):
            raise ValueError(f"{definition_name} generated an invalid nested property schema")
        properties = cast(dict[str, object], raw_properties)
        for field, raw_property_schema in properties.items():
            if not isinstance(raw_property_schema, dict):
                raise ValueError(f"{definition_name} generated an invalid nested property schema")
            property_schema = cast(dict[str, object], raw_property_schema)
            guidance = _nested_field_guidance(dataset, definition_name, field)
            property_schema["description"] = guidance.description
            property_schema["x-gds-population-guidance"] = guidance.population_guidance
            property_schema["x-gds-accepted-values"] = _accepted_values(property_schema).model_dump(
                mode="json"
            )


def enrich_model_dataset_schema(
    dataset: str,
    schema: MutableMapping[str, object],
) -> None:
    """Add stable GDS extensions without weakening the exact JSON Schema."""
    rules = model_dataset_population_rules(dataset)
    if not rules:
        return
    _attach_governed_mapping_schemas(dataset, schema)
    description = _build_description(dataset, schema)
    description_document = description.model_dump(mode="json")
    schema["x-gds-population-rules"] = description_document["population_rules"]
    schema["x-gds-columns"] = description_document["columns"]
    _enrich_nested_definitions(dataset, schema)
    raw_properties = schema.get("properties")
    assert isinstance(raw_properties, dict)
    properties = cast(dict[str, object], raw_properties)

    if dataset == "generated_code":
        schema["x-gds-context-digest-contract"] = {
            "mapping_context_digest": {
                "copy_from_tool": "get_model_code_generation_document",
                "result_field": "target_mapping_context_digest",
            },
            "source_context_digest": {
                "copy_from_tool": "get_model_code_generation_document",
                "result_field": "target_source_context_digest",
            },
            "generated_code_digest": {
                "source_field": "generated_code_content",
                "algorithm": "sha256_utf8_lower_hex",
            },
        }
        schema["x-gds-apply-order"] = ["mapping", "generated_code"]
        return

    if dataset == "qa_authoring_context":
        schema["x-gds-trusted-context-contract"] = {
            "server_derived": True,
            "snapshot_only": True,
            "change_set_eligible": False,
            "copy_to_validation_group": {
                "join_fields": ["tenant_code", "system_code"],
                "fields": ["mapping_context_digest", "code_context_digest"],
                "copy_unchanged": True,
            },
            "current_code_join": {
                "dataset": "generated_code",
                "reference_fields": _QA_CURRENT_CODE_REFERENCE_FIELDS,
                "content_field": "generated_code_content",
                "all_reference_fields_must_match": True,
                "exclude_unreferenced_records": True,
                "empty_references_mean_no_current_relevant_code": True,
            },
            "bounds": {
                "maximum_system_contexts_per_snapshot": 20_000,
                "maximum_mapping_targets_per_system": 20_000,
                "maximum_current_code_references_per_system": 20_000,
                "maximum_target_system_associations_per_snapshot": 50_000,
            },
        }
        return

    if dataset == "validation_group":
        schema["x-gds-context-digest-contract"] = {
            **deepcopy(_COMMON_DIGEST_ALGORITHM),
            "entry_sort": "ascending_canonical_json",
            "trusted_snapshot_source": {
                "dataset": "qa_authoring_context",
                "join_fields": ["tenant_code", "system_code"],
                "copy_unchanged": True,
            },
            "mapping_context_digest": {
                "scope": "all_complete_active_target_contexts_containing_group_system_code",
                "entry_fields": _QA_MAPPING_ENTRY_FIELDS,
                "target_fields": _TARGET_FIELDS,
                "empty_result": "invalid_applied_mapping_required",
            },
            "code_context_digest": {
                "scope": "current_active_code_for_mapping_context_targets",
                "current_code_requires_exact_target_mapping_and_source_digests": True,
                "entry_fields": _QA_CODE_ENTRY_FIELDS,
                "target_fields": _TARGET_FIELDS,
                "empty_result": None,
            },
        }
        schema["x-gds-apply-order"] = [
            "mapping",
            "current_relevant_generated_code_when_present",
            "qa",
        ]
        return

    if dataset != "validation_check":
        return

    for name in ("validation_query_sql", "validation_comparison_query_sql"):
        property_schema = properties[name]
        assert isinstance(property_schema, dict)
        cast(dict[str, object], property_schema)["x-gds-max-utf8-bytes"] = 100_000
    comparison_value = properties["validation_comparison_value"]
    assert isinstance(comparison_value, dict)
    cast(dict[str, object], comparison_value)["x-gds-max-json-utf8-bytes"] = 65_536
    schema["x-gds-assertion-shapes"] = deepcopy(_ASSERTION_SHAPES)
    schema["x-gds-sql-policy"] = {
        "dialect": "databricks_sql",
        "allowed": ["read", "unqualified_temporary_view", "unqualified_temporary_table"],
        "rejected": ["dml", "persistent_ddl"],
        "physical_relations": "require_catalog_schema_table",
        "unqualified_relations": "previously_declared_same_batch_temporary_only",
        "apply_executes_sql": False,
    }
    schema["x-gds-apply-order"] = [
        "mapping",
        "current_relevant_generated_code_when_present",
        "qa",
    ]


__all__ = ["enrich_model_dataset_schema", "model_dataset_population_rules"]
