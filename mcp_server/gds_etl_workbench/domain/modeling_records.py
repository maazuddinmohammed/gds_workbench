"""Portable project records shared by snapshots and Project Change Sets."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from gds_etl_workbench.domain.context_safety import (
    CONTEXT_RECORD_TEXT_MAX_CHARACTERS,
    CONTEXT_SOURCE_REFERENCE_MAX_BYTES,
)

Code100 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
]
Name400 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=400, pattern=r"\S"),
]
DigestVersion = Annotated[
    str,
    StringConstraints(min_length=1, max_length=50, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"),
]
StableKey = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$",
    ),
]
NonblankText = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
NamingInstructions = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32_768, pattern=r"\S"),
]
Percentage = Annotated[Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=4)]
Status = Literal["active", "inactive", "deprecated"]
Cardinality = Literal[
    "one_to_one",
    "one_to_many",
    "many_to_one",
    "many_to_many",
]
InferredCardinality = Cardinality | Literal["unknown"]
# Model relationships point child -> parent, so only these two remain.
ModelCardinality = Literal["many_to_one", "one_to_one"]
# Label codes come from reference lists; validation checks the active rows.
ReferenceCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,49}$")]
JsonObject = dict[str, object]
ANALYSIS_VALIDATION_FIELDS = (
    "validation_policy_version",
    "validation_result",
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
)


def normalize_project_key_value[T](value: T) -> T:
    """Normalize one textual Project natural-key value for comparison."""
    if isinstance(value, str):
        return cast(T, value.strip(" ").casefold())
    return value


def has_mapping_transformation_content(value: object) -> bool:
    """Recognize content without treating false/zero custom rules as blanks."""
    if isinstance(value, dict):
        return any(
            has_mapping_transformation_content(item)
            for item in cast(dict[str, object], value).values()
        )
    if isinstance(value, list):
        return any(has_mapping_transformation_content(item) for item in cast(list[object], value))
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


class ModelingRecord(BaseModel):
    """Portable record; numeric database/audit IDs stay internal. Context UUIDs are portable."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PhysicalObjectKey(ModelingRecord):
    tenant_code: Code100
    system_code: Code100
    connection_code: Code100
    object_schema: Name400
    object_name: Name400


class PhysicalAttributeKey(PhysicalObjectKey):
    attribute_name: Name400


class ProjectSchemaDefinition(ModelingRecord):
    schema_name: Name400
    description: (
        Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=r"\S")] | None
    )


class ProjectDetailsRecord(ModelingRecord):
    project_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    project_description: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=2000, pattern=r"\S"),
        ]
        | None
    )
    silver_model_naming_instructions: NamingInstructions | None
    silver_model_audit_columns_template: JsonObject | None
    gold_model_naming_instructions: NamingInstructions | None
    gold_model_technical_columns_template: JsonObject | None
    gold_model_audit_columns_template: JsonObject | None
    logical_schemas: tuple[ProjectSchemaDefinition, ...] = Field(default=(), max_length=100)
    dimensional_schemas: tuple[ProjectSchemaDefinition, ...] = Field(default=(), max_length=100)
    logical_entity_scd_type: Literal["type_1", "type_2"] | None = None
    dimensional_entity_scd_type: Literal["type_1", "type_2"] | None = None
    logical_coverage_threshold_percent: int = Field(default=70, ge=1, le=100, strict=True)
    dimensional_coverage_threshold_percent: int = Field(default=60, ge=1, le=100, strict=True)
    logical_enforce_coverage_threshold: bool = Field(default=False, strict=True)
    dimensional_enforce_coverage_threshold: bool = Field(default=False, strict=True)
    default_mapping_source_system_code: Code100 | None = None

    @model_validator(mode="after")
    def validate_policy_fields(self) -> ProjectDetailsRecord:
        for schemas in (self.logical_schemas, self.dimensional_schemas):
            _require_unique((schema.schema_name for schema in schemas), "Project schema names")
            if _json_size([schema.model_dump(mode="json") for schema in schemas]) > 262_144:
                raise ValueError("Project schema configuration is too large.")
        naming_instructions = (
            self.silver_model_naming_instructions,
            self.gold_model_naming_instructions,
        )
        if any(
            value is not None and len(value.encode("utf-8")) > 32_768
            for value in naming_instructions
        ):
            raise ValueError("Project naming instructions are too large.")
        templates = (
            self.silver_model_audit_columns_template,
            self.gold_model_technical_columns_template,
            self.gold_model_audit_columns_template,
        )
        if any(value is not None and _json_size(value) > 262_144 for value in templates):
            raise ValueError("A Project policy template is too large.")
        return self


class ProjectInputScopeRecord(PhysicalObjectKey):
    project_input_scope_is_locked: bool
    is_active: bool


ContextRecordId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


class ContextRecordReference(ModelingRecord):
    context_record_id: ContextRecordId


class ObjectEnrichmentRecord(PhysicalObjectKey):
    expected_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    object_description: (
        Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=r"\S")] | None
    )
    is_locked: bool

    @field_validator("object_description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value.encode("utf-8")) > 2000
            or any((ord(c) < 32 and c not in "\t\n\r") or ord(c) == 127 for c in value)
        ):
            raise ValueError("Enrichment description must be safe text within 2,000 UTF-8 bytes.")
        return value


class AttributeEnrichmentRecord(PhysicalAttributeKey):
    expected_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    attribute_description: (
        Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=r"\S")] | None
    )
    attribute_inferred_data_type: (
        Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")] | None
    )
    is_natural_key: bool | None
    is_primary_key: bool | None
    is_nullable: bool | None
    is_pii: bool | None
    is_locked: bool

    @field_validator("attribute_description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return ObjectEnrichmentRecord.validate_description(value)

    @field_validator("attribute_inferred_data_type")
    @classmethod
    def validate_inferred_type(cls, value: str | None) -> str | None:
        if value is not None and any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Inferred type cannot contain control characters.")
        return value


class ProfilingProfileRecord(PhysicalAttributeKey):
    row_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    blank_count: int | None = Field(default=None, ge=0)
    distinct_count: int | None = Field(default=None, ge=0)
    min_data_length: int | None = Field(default=None, ge=0)
    max_data_length: int | None = Field(default=None, ge=0)
    avg_data_length: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=6,
    )
    percent_populated: Percentage | None = None
    percent_duplicates: Percentage | None = None
    percent_null: Percentage | None = None
    percent_blank: Percentage | None = None
    percent_distinct: Percentage | None = None

    @model_validator(mode="after")
    def validate_profile(self) -> ProfilingProfileRecord:
        if self.non_null_count + self.null_count != self.row_count:
            raise ValueError("Profile non-null and null counts must equal row count.")
        if self.blank_count is not None and self.blank_count > self.non_null_count:
            raise ValueError("Profile blank count cannot exceed non-null count.")
        if self.distinct_count is not None and self.distinct_count > self.non_null_count:
            raise ValueError("Profile distinct count cannot exceed non-null count.")
        if (
            self.min_data_length is not None
            and self.max_data_length is not None
            and self.min_data_length > self.max_data_length
        ):
            raise ValueError("Profile minimum length cannot exceed maximum length.")
        return self


type AnalysisValidationResult = Literal[
    "supported",
    "inconclusive",
    "unsupported",
]


class AnalysisValidationEvidence(BaseModel):
    """Aggregate integrity shared by deterministic execution and staged records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    validation_source_non_null_count: int = Field(ge=0)
    validation_source_distinct_count: int = Field(ge=0)
    validation_target_non_null_count: int = Field(ge=0)
    validation_target_distinct_count: int = Field(ge=0)
    validation_source_missing_target_count: int = Field(ge=0)
    validation_unused_target_count: int = Field(ge=0)
    validation_duplicate_target_key_count: int = Field(ge=0)
    validation_result: AnalysisValidationResult

    @model_validator(mode="after")
    def validate_evidence(self) -> AnalysisValidationEvidence:
        if self.validation_source_distinct_count > self.validation_source_non_null_count:
            raise ValueError("Source validation counts do not reconcile")
        if (self.validation_source_non_null_count == 0) != (
            self.validation_source_distinct_count == 0
        ):
            raise ValueError("Source validation counts do not reconcile")
        if self.validation_target_distinct_count > self.validation_target_non_null_count:
            raise ValueError("Target validation counts do not reconcile")
        if (self.validation_target_non_null_count == 0) != (
            self.validation_target_distinct_count == 0
        ):
            raise ValueError("Target validation counts do not reconcile")
        if self.validation_source_missing_target_count > self.validation_source_distinct_count:
            raise ValueError("Missing-target count exceeds source distinct count")
        if self.validation_unused_target_count > self.validation_target_distinct_count:
            raise ValueError("Unused-target count exceeds target distinct count")
        if (
            self.validation_source_distinct_count - self.validation_source_missing_target_count
            != self.validation_target_distinct_count - self.validation_unused_target_count
        ):
            raise ValueError("Matched distinct counts do not reconcile")
        expected_duplicate_count = (
            self.validation_target_non_null_count - self.validation_target_distinct_count
        )
        if self.validation_duplicate_target_key_count != expected_duplicate_count:
            raise ValueError("Duplicate-target count does not reconcile")

        expected_result: AnalysisValidationResult
        if self.validation_source_non_null_count == 0 or self.validation_target_non_null_count == 0:
            expected_result = "inconclusive"
        elif (
            self.validation_source_missing_target_count == 0
            and self.validation_duplicate_target_key_count == 0
        ):
            expected_result = "supported"
        else:
            expected_result = "unsupported"
        if self.validation_result != expected_result:
            raise ValueError("Analysis validation result does not match its evidence")
        return self


class AnalysisResultRecord(ModelingRecord):
    from_tenant_code: Code100
    from_system_code: Code100
    from_connection_code: Code100
    from_object_schema: Name400
    from_object_name: Name400
    from_attribute_name: Name400
    to_tenant_code: Code100
    to_system_code: Code100
    to_connection_code: Code100
    to_object_schema: Name400
    to_object_name: Name400
    to_attribute_name: Name400
    relationship_kind: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    inferred_cardinality: InferredCardinality = "unknown"
    relationship_basis: NonblankText
    validation_policy_version: DigestVersion | None = None
    validation_result: Literal["supported", "inconclusive", "unsupported"] | None = None
    validation_source_non_null_count: int | None = Field(default=None, ge=0)
    validation_source_distinct_count: int | None = Field(default=None, ge=0)
    validation_target_non_null_count: int | None = Field(default=None, ge=0)
    validation_target_distinct_count: int | None = Field(default=None, ge=0)
    validation_source_missing_target_count: int | None = Field(default=None, ge=0)
    validation_unused_target_count: int | None = Field(default=None, ge=0)
    validation_duplicate_target_key_count: int | None = Field(default=None, ge=0)
    analysis_result_status: Status
    analysis_result_is_locked: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> AnalysisResultRecord:
        validation_values = tuple(getattr(self, field) for field in ANALYSIS_VALIDATION_FIELDS)
        if any(value is None for value in validation_values) and not all(
            value is None for value in validation_values
        ):
            raise ValueError("Analysis validation fields must all be present or all be absent.")
        if self.validation_result is not None:
            AnalysisValidationEvidence.model_validate(
                {field: getattr(self, field) for field in ANALYSIS_VALIDATION_FIELDS[1:]},
                strict=True,
            )
        from_key = (
            normalize_project_key_value(self.from_tenant_code),
            normalize_project_key_value(self.from_system_code),
            normalize_project_key_value(self.from_connection_code),
            normalize_project_key_value(self.from_object_schema),
            normalize_project_key_value(self.from_object_name),
            normalize_project_key_value(self.from_attribute_name),
        )
        to_key = (
            normalize_project_key_value(self.to_tenant_code),
            normalize_project_key_value(self.to_system_code),
            normalize_project_key_value(self.to_connection_code),
            normalize_project_key_value(self.to_object_schema),
            normalize_project_key_value(self.to_object_name),
            normalize_project_key_value(self.to_attribute_name),
        )
        if from_key == to_key:
            raise ValueError("Analysis endpoints must be different.")
        return self


class ContextTypeRecord(ModelingRecord):
    context_type_name: Annotated[
        str, StringConstraints(min_length=1, max_length=200, pattern=r"\S")
    ]
    context_type_description: str | None


class ContextGroupRecord(ModelingRecord):
    context_group_name: Annotated[
        str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")
    ]
    context_type_name: Annotated[
        str, StringConstraints(min_length=1, max_length=200, pattern=r"\S")
    ]
    context_group_description: (
        Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=r"\S")] | None
    )
    source_system_code: Code100 | None
    is_active: bool


class ContextRecord(ContextRecordReference):
    context_group_name: Annotated[
        str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")
    ]
    context_text: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=CONTEXT_RECORD_TEXT_MAX_CHARACTERS, pattern=r"\S"
        ),
    ]
    source_reference: str | None
    status: Status
    is_locked: bool

    @field_validator("source_reference")
    @classmethod
    def validate_source_reference(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > CONTEXT_SOURCE_REFERENCE_MAX_BYTES:
            raise ValueError("Context source reference is too large")
        return value


class SubjectAreaRecord(ModelingRecord):
    """One named focus window over Input Scope tables; not a separate model."""

    subject_area_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    subject_area_definition: NonblankText
    subject_area_is_active: bool
    subject_area_is_locked: bool


class SubjectAreaTableRecord(ModelingRecord):
    """One Input Scope table in one Subject Area; a table may sit in several areas."""

    subject_area_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    tenant_code: Code100
    system_code: Code100
    connection_code: Code100
    object_schema: Name400
    object_name: Name400
    subject_area_table_is_active: bool
    subject_area_table_is_locked: bool


class LogicalObjectSourceRecord(ModelingRecord):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectKey
    rationale: NonblankText | None = None
    is_active: bool
    is_locked: bool


class LogicalContextSourceRecord(ModelingRecord):
    support_source_type: Literal["context_record"]
    context_record: ContextRecordReference
    rationale: NonblankText | None = None
    is_active: bool
    is_locked: bool


type LogicalEntitySourceRecord = Annotated[
    LogicalObjectSourceRecord | LogicalContextSourceRecord,
    Field(discriminator="support_source_type"),
]


class LogicalEntityKey(ModelingRecord):
    logical_entity_schema_name: Name400
    logical_entity_name: Annotated[
        str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")
    ]


class LogicalAttributeKey(LogicalEntityKey):
    logical_attribute_name: Annotated[
        str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")
    ]


class DimensionalLogicalEntitySourceRecord(ModelingRecord):
    support_source_type: Literal["logical_entity"]
    source_logical_entity: LogicalEntityKey
    rationale: NonblankText | None = None
    is_active: bool
    is_locked: bool


type DimensionalEntitySourceRecord = Annotated[
    DimensionalLogicalEntitySourceRecord | LogicalContextSourceRecord,
    Field(discriminator="support_source_type"),
]


class AttributePhysicalSourceRecord(ModelingRecord):
    support_source_type: Literal["attribute"]
    source_attribute: PhysicalAttributeKey
    rationale: NonblankText | None = None
    is_active: bool
    is_locked: bool


class AttributeContextSourceRecord(ModelingRecord):
    support_source_type: Literal["context_record"]
    context_record: ContextRecordReference
    rationale: NonblankText | None = None
    is_active: bool
    is_locked: bool


type AttributeSourceRecord = Annotated[
    AttributePhysicalSourceRecord | AttributeContextSourceRecord,
    Field(discriminator="support_source_type"),
]


class AttributeLogicalSourceRecord(ModelingRecord):
    support_source_type: Literal["logical_attribute"]
    source_logical_attribute: LogicalAttributeKey
    rationale: NonblankText | None = None
    is_active: bool
    is_locked: bool


type DimensionalAttributeSourceRecord = Annotated[
    AttributeLogicalSourceRecord | AttributeContextSourceRecord,
    Field(discriminator="support_source_type"),
]


class LogicalEntityTypeRecord(ModelingRecord):
    """One read-only Logical Entity type label from reference.logical_entity_type."""

    logical_entity_type_code: ReferenceCode
    logical_entity_type_description: NonblankText
    logical_entity_type_is_active: bool


class DimensionalFactTypeRecord(ModelingRecord):
    """One read-only fact type label from reference.dimensional_fact_type."""

    dimensional_fact_type_code: ReferenceCode
    dimensional_fact_type_description: NonblankText
    dimensional_fact_type_is_active: bool


class LogicalEntityRecord(ModelingRecord):
    logical_entity_schema_name: Name400
    logical_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_entity_definition: NonblankText
    logical_entity_type: ReferenceCode
    logical_entity_grain: NonblankText
    logical_entity_dependency_order: int = Field(ge=0)
    logical_entity_is_active: bool
    logical_entity_is_locked: bool
    sources: tuple[LogicalEntitySourceRecord, ...]

    @model_validator(mode="after")
    def validate_sources(self) -> LogicalEntityRecord:
        _require_unique_sources(self.sources, "Logical Entity sources")
        return self


class LogicalAttributeRecord(ModelingRecord):
    logical_entity_schema_name: Name400
    logical_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_attribute_definition: NonblankText
    logical_attribute_data_type: Code100
    logical_attribute_is_nullable: bool
    logical_attribute_is_natural_key: bool
    logical_attribute_is_surrogate_key: bool
    logical_attribute_ordinal_position: int = Field(gt=0)
    logical_attribute_is_audit_column: bool
    logical_attribute_is_active: bool
    logical_attribute_is_locked: bool
    sources: tuple[AttributeSourceRecord, ...]

    @model_validator(mode="after")
    def validate_key_policy(self) -> LogicalAttributeRecord:
        if self.logical_attribute_is_natural_key and self.logical_attribute_is_surrogate_key:
            raise ValueError("A Logical Attribute cannot be both natural and surrogate key.")
        if (
            self.logical_attribute_is_natural_key or self.logical_attribute_is_surrogate_key
        ) and self.logical_attribute_is_nullable:
            raise ValueError("A Logical key Attribute cannot be nullable.")
        _require_unique_sources(self.sources, "Logical Attribute sources")
        return self


class LogicalRelationshipRecord(ModelingRecord):
    """Child -> parent: the from Attribute is the foreign key; to is the parent's key."""

    from_logical_entity_schema_name: Name400
    to_logical_entity_schema_name: Name400
    from_logical_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    from_logical_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    to_logical_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    to_logical_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_relationship_cardinality: ModelCardinality
    logical_relationship_basis: NonblankText
    logical_relationship_is_active: bool
    logical_relationship_is_locked: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> LogicalRelationshipRecord:
        if (
            normalize_project_key_value(self.from_logical_entity_schema_name),
            normalize_project_key_value(self.from_logical_entity_name),
            normalize_project_key_value(self.from_logical_attribute_name),
        ) == (
            normalize_project_key_value(self.to_logical_entity_schema_name),
            normalize_project_key_value(self.to_logical_entity_name),
            normalize_project_key_value(self.to_logical_attribute_name),
        ):
            raise ValueError("Logical Relationship endpoints must be different.")
        return self


class DimensionalEntityRecord(ModelingRecord):
    dimensional_entity_schema_name: Name400
    dimensional_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_entity_definition: NonblankText
    dimensional_entity_type: Literal["fact", "dimension", "bridge"]
    dimensional_fact_type: ReferenceCode | None
    dimensional_entity_grain_definition: NonblankText | None
    dimensional_entity_dependency_order: int = Field(ge=0)
    dimensional_entity_is_active: bool
    dimensional_entity_is_locked: bool
    sources: tuple[DimensionalEntitySourceRecord, ...]

    @model_validator(mode="after")
    def validate_entity_policy(self) -> DimensionalEntityRecord:
        if (self.dimensional_entity_type == "fact") != (self.dimensional_fact_type is not None):
            raise ValueError("Dimensional fact type is required only for facts.")
        if (
            self.dimensional_entity_type in ("fact", "bridge")
            and self.dimensional_entity_grain_definition is None
        ):
            raise ValueError("Fact and bridge Entities require a grain definition.")
        _require_unique_sources(self.sources, "Dimensional Entity sources")
        return self


class DimensionalAttributeRecord(ModelingRecord):
    dimensional_entity_schema_name: Name400
    dimensional_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_attribute_definition: NonblankText
    dimensional_attribute_data_type: Code100
    dimensional_attribute_is_nullable: bool
    dimensional_attribute_ordinal_position: int = Field(gt=0)
    dimensional_attribute_is_natural_key: bool
    dimensional_attribute_is_surrogate_key: bool
    dimensional_attribute_is_audit_column: bool
    dimensional_attribute_is_active: bool
    dimensional_attribute_is_locked: bool
    sources: tuple[DimensionalAttributeSourceRecord, ...]

    @model_validator(mode="after")
    def validate_attribute_policy(self) -> DimensionalAttributeRecord:
        if (
            self.dimensional_attribute_is_natural_key
            and self.dimensional_attribute_is_surrogate_key
        ):
            raise ValueError("A Dimensional Attribute cannot be both natural and surrogate key.")
        if (
            self.dimensional_attribute_is_natural_key or self.dimensional_attribute_is_surrogate_key
        ) and self.dimensional_attribute_is_nullable:
            raise ValueError("A Dimensional key Attribute cannot be nullable.")
        _require_unique_sources(self.sources, "Dimensional Attribute sources")
        return self


class DimensionalRelationshipRecord(ModelingRecord):
    """Child -> parent: a fact, bridge or outrigger foreign key -> the dimension's key.

    Kind, optionality and many-to-one cardinality are worked out, never stored.
    """

    from_dimensional_entity_schema_name: Name400
    to_dimensional_entity_schema_name: Name400
    from_dimensional_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    from_dimensional_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    to_dimensional_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    to_dimensional_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_relationship_role_name: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
        ]
        | None
    ) = None
    dimensional_relationship_basis: NonblankText | None = None
    dimensional_relationship_is_active: bool
    dimensional_relationship_is_locked: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> DimensionalRelationshipRecord:
        if (
            normalize_project_key_value(self.from_dimensional_entity_schema_name),
            normalize_project_key_value(self.from_dimensional_entity_name),
            normalize_project_key_value(self.from_dimensional_attribute_name),
        ) == (
            normalize_project_key_value(self.to_dimensional_entity_schema_name),
            normalize_project_key_value(self.to_dimensional_entity_name),
            normalize_project_key_value(self.to_dimensional_attribute_name),
        ):
            raise ValueError("Dimensional Relationship endpoints must be different.")
        return self


class MappingObjectRecord(ModelingRecord):
    modeled_entity_schema_name: Name400
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    source_system_code: Code100
    output_template_code: Code100 | None
    object_dependency_order: int = Field(ge=0)
    mapping_transformation_document: JsonObject | None
    object_mapping_status: Status
    object_mapping_is_locked: bool

    @model_validator(mode="after")
    def validate_transformation_size(self) -> MappingObjectRecord:
        transformation = self.mapping_transformation_document
        if transformation is not None and _json_size(transformation) > 524_288:
            raise ValueError("Mapping transformation document exceeds 524,288 bytes.")
        return self


class MappingAttributeRecord(ModelingRecord):
    modeled_entity_schema_name: Name400
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    modeled_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    source_system_code: Code100
    output_template_code: Code100 | None
    attribute_mapping_transformation_document: JsonObject | None
    attribute_mapping_status: Status
    attribute_mapping_is_locked: bool

    @model_validator(mode="after")
    def validate_transformation(self) -> MappingAttributeRecord:
        transformation = self.attribute_mapping_transformation_document
        if transformation is not None and _json_size(transformation) > 65_536:
            raise ValueError("Attribute Mapping document exceeds 65,536 bytes.")
        return self


VALIDATION_QUERY_MAX_BYTES = 100_000


class GeneratedCodeRecord(ModelingRecord):
    modeled_entity_schema_name: Name400
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    artifact_name: Name400
    artifact_type: Literal["sql_file", "python_file", "python_notebook"]
    code_storage_type: Literal["table", "git"] = "table"
    code_repository_url: str | None = None
    code_commit_path: str | None = None
    code_entry_point: str | None = None
    code_parameters: JsonValue = None
    generated_code_content: NonblankText | None = None
    generated_code_status: Status
    generated_code_is_locked: bool

    @model_validator(mode="after")
    def validate_content(self) -> GeneratedCodeRecord:
        if self.code_storage_type == "table" and self.generated_code_content is None:
            raise ValueError("Table-stored Code requires content.")
        if any(
            ord(character) < 32 and character not in {"\t", "\n", "\r"}
            for character in self.generated_code_content or ""
        ):
            raise ValueError("Generated Code contains an unsupported control character.")
        if self.artifact_name.strip() != self.artifact_name or any(
            separator in self.artifact_name for separator in ("/", "\\")
        ):
            raise ValueError("Artifact name must be a file name, not a path.")
        if self.artifact_name in {".", ".."}:
            raise ValueError("Artifact name is invalid.")
        return self


class GeneratedCodeSourceSystemRecord(ModelingRecord):
    modeled_entity_schema_name: Name400
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    artifact_name: Name400
    source_system_code: Code100
    generated_code_source_system_status: Status
    generated_code_source_system_is_locked: bool


class ValidationGroupRecord(ModelingRecord):
    tenant_code: Code100
    system_code: Code100
    validation_group_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=200, pattern=r"\S"),
    ]
    validation_group_description: NonblankText | None
    is_active: bool
    is_locked: bool

    @field_validator("validation_group_description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 16_384:
            raise ValueError("Validation Group description is too large.")
        return value


type ValidationLiteral = bool | int | float | str


class ValidationCheckRecord(ModelingRecord):
    """Validation definition with a scalar result except for execution-only checks."""

    tenant_code: Code100
    system_code: Code100
    validation_group_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=200, pattern=r"\S"),
    ]
    validation_check_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=200, pattern=r"\S"),
    ]
    validation_check_description: NonblankText | None
    validation_category_code: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,99}$"),
    ]
    validation_severity: Literal["blocking", "warning", "informational"]
    validation_query_sql: NonblankText
    validation_comparison_query_sql: NonblankText | None
    validation_result_data_type: (
        Literal["boolean", "integer", "decimal", "text", "date", "timestamp"] | None
    )
    validation_comparison_operator: Literal[
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
    ]
    validation_comparison_value_type: Literal[
        "none",
        "literal",
        "literal_list",
        "query",
    ]
    validation_comparison_value: ValidationLiteral | tuple[ValidationLiteral, ...] | None
    is_active: bool
    is_locked: bool

    @field_validator("validation_check_description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 16_384:
            raise ValueError("Validation Check description is too large.")
        return value

    @field_validator("validation_query_sql", "validation_comparison_query_sql")
    @classmethod
    def validate_query_size(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > VALIDATION_QUERY_MAX_BYTES:
            raise ValueError("Validation query exceeds 100,000 bytes.")
        return value

    @field_validator("validation_comparison_value")
    @classmethod
    def validate_comparison_value_size(
        cls,
        value: ValidationLiteral | tuple[ValidationLiteral, ...] | None,
    ) -> ValidationLiteral | tuple[ValidationLiteral, ...] | None:
        if value is not None and _json_size(value) > 65_536:
            raise ValueError("Validation comparison value is too large.")
        return value

    @model_validator(mode="after")
    def validate_assertion(self) -> ValidationCheckRecord:
        operator = self.validation_comparison_operator
        result_type = self.validation_result_data_type
        value_type = self.validation_comparison_value_type
        value = self.validation_comparison_value
        query_b = self.validation_comparison_query_sql

        if operator == "executes_successfully":
            valid_shape = (
                result_type is None and value_type == "none" and value is None and query_b is None
            )
        elif operator in {"is_null", "is_not_null"}:
            valid_shape = (
                result_type is not None
                and value_type == "none"
                and value is None
                and query_b is None
            )
        elif operator in {"is_true", "is_false"}:
            valid_shape = (
                result_type == "boolean"
                and value_type == "none"
                and value is None
                and query_b is None
            )
        elif operator in {"equal", "not_equal"}:
            valid_shape = result_type is not None and (
                (value_type == "literal" and value is not None and query_b is None)
                or (value_type == "query" and value is None and query_b is not None)
            )
        elif operator in {
            "greater_than",
            "greater_than_or_equal",
            "less_than",
            "less_than_or_equal",
        }:
            valid_shape = result_type in {
                "integer",
                "decimal",
                "date",
                "timestamp",
            } and (
                (value_type == "literal" and value is not None and query_b is None)
                or (value_type == "query" and value is None and query_b is not None)
            )
        else:
            valid_shape = (
                result_type is not None
                and value_type == "literal_list"
                and isinstance(value, tuple)
                and 1 <= len(value) <= 10_000
                and query_b is None
            )
        if not valid_shape:
            raise ValueError("Validation assertion shape is invalid.")

        values = value if isinstance(value, tuple) else (value,)
        if value_type in {"literal", "literal_list"} and not all(
            _validation_literal_matches(result_type, item) for item in values
        ):
            raise ValueError("Validation comparison value does not match its result type.")
        return self


def _validation_literal_matches(result_type: str | None, value: object) -> bool:
    if result_type == "boolean":
        return type(value) is bool
    if result_type == "integer":
        return type(value) is int
    if result_type == "decimal":
        return type(value) is int or (type(value) is float and math.isfinite(value))
    if result_type == "text":
        return isinstance(value, str)
    if result_type == "date" and isinstance(value, str):
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True
    if result_type == "timestamp" and isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return False
        return True
    return False


def _require_unique(values: Iterable[str], label: str) -> None:
    normalized = [normalize_project_key_value(value) for value in values]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique.")


def _require_unique_sources(sources: Iterable[Any], label: str) -> None:
    keys: list[tuple[str, ...]] = []
    for source in sources:
        if source.support_source_type == "context_record":
            key = (
                "context",
                normalize_project_key_value(source.context_record.context_record_id),
            )
        elif source.support_source_type in {"logical_entity", "logical_attribute"}:
            logical = (
                source.source_logical_entity
                if source.support_source_type == "logical_entity"
                else source.source_logical_attribute
            )
            key = (
                source.support_source_type,
                normalize_project_key_value(logical.logical_entity_schema_name),
                normalize_project_key_value(logical.logical_entity_name),
                *(
                    (normalize_project_key_value(logical.logical_attribute_name),)
                    if source.support_source_type == "logical_attribute"
                    else ()
                ),
            )
        else:
            physical = getattr(source, "source_object", None) or source.source_attribute
            key = (
                source.support_source_type,
                normalize_project_key_value(physical.tenant_code),
                normalize_project_key_value(physical.system_code),
                normalize_project_key_value(physical.connection_code),
                normalize_project_key_value(physical.object_schema),
                normalize_project_key_value(physical.object_name),
                *(
                    (normalize_project_key_value(physical.attribute_name),)
                    if hasattr(physical, "attribute_name")
                    else ()
                ),
            )
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label} must be unique.")


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
