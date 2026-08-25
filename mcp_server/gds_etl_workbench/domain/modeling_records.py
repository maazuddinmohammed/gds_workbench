"""ID-free modeling records shared by snapshots and Model Change Sets."""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from gds_etl_workbench.domain.assertion_safety import (
    ASSERTION_DOCUMENT_METADATA_MAX_BYTES,
    ASSERTION_RECORD_DETAILS_MAX_BYTES,
    ASSERTION_RECORD_SOURCE_LOCATION_MAX_BYTES,
    ASSERTION_RECORD_TEXT_MAX_CHARACTERS,
    validate_assertion_json,
)
from gds_etl_workbench.domain.mapping_contracts import (
    validate_mapping_package_document,
)
from gds_etl_workbench.domain.mapping_profiles import validate_mapping_package_profile

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
Status = Literal["active", "needs_review", "inactive", "deprecated"]
Confidence = Literal["low", "medium", "high"]
Cardinality = Literal[
    "one_to_one",
    "one_to_many",
    "many_to_one",
    "many_to_many",
]
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


def normalize_model_key_value[T](value: T) -> T:
    """Normalize one textual Model natural-key value for comparison."""
    if isinstance(value, str):
        return cast(T, value.strip(" ").casefold())
    return value


class ModelingRecord(BaseModel):
    """Exact ID-free modeling record; database and audit IDs are never fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PhysicalObjectKey(ModelingRecord):
    tenant_code: Code100
    system_code: Code100
    connection_code: Code100
    object_schema: Name400
    object_name: Name400


class PhysicalAttributeKey(PhysicalObjectKey):
    attribute_name: Name400


class ModelDetailsRecord(ModelingRecord):
    model_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    model_description: (
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

    @model_validator(mode="after")
    def validate_policy_fields(self) -> ModelDetailsRecord:
        naming_instructions = (
            self.silver_model_naming_instructions,
            self.gold_model_naming_instructions,
        )
        if any(
            value is not None and len(value.encode("utf-8")) > 32_768
            for value in naming_instructions
        ):
            raise ValueError("Model naming instructions are too large.")
        templates = (
            self.silver_model_audit_columns_template,
            self.gold_model_technical_columns_template,
            self.gold_model_audit_columns_template,
        )
        if any(value is not None and _json_size(value) > 262_144 for value in templates):
            raise ValueError("A Model policy template is too large.")
        return self


class ModelScopeRecord(PhysicalObjectKey):
    zone_code: Code100
    is_bronze_source_eligible: bool
    is_dimensional_source_eligible: bool
    is_logical_mapping_target_eligible: bool
    is_dimensional_mapping_target_eligible: bool
    model_scope_is_locked: bool
    is_active: bool


class AssertionRecordKey(ModelingRecord):
    modeling_assertion_record_key: StableKey


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
    relationship_confidence: Literal["low", "medium", "high"]
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
    analysis_result_status: Literal[
        "active",
        "needs_review",
        "inactive",
        "deprecated",
    ]
    analysis_result_is_locked: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> AnalysisResultRecord:
        validation_values = tuple(getattr(self, field) for field in ANALYSIS_VALIDATION_FIELDS)
        if any(value is None for value in validation_values) and not all(
            value is None for value in validation_values
        ):
            raise ValueError("Analysis validation fields must all be present or all be absent.")
        from_key = (
            normalize_model_key_value(self.from_tenant_code),
            normalize_model_key_value(self.from_system_code),
            normalize_model_key_value(self.from_connection_code),
            normalize_model_key_value(self.from_object_schema),
            normalize_model_key_value(self.from_object_name),
            normalize_model_key_value(self.from_attribute_name),
        )
        to_key = (
            normalize_model_key_value(self.to_tenant_code),
            normalize_model_key_value(self.to_system_code),
            normalize_model_key_value(self.to_connection_code),
            normalize_model_key_value(self.to_object_schema),
            normalize_model_key_value(self.to_object_name),
            normalize_model_key_value(self.to_attribute_name),
        )
        if from_key == to_key:
            raise ValueError("Analysis endpoints must be different.")
        return self


class ModelingAssertionDocumentRecord(ModelingRecord):
    modeling_assertion_document_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    tenant_code: Code100 | None
    system_code: Code100 | None
    modeling_assertion_file_pattern: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=500, pattern=r"\S"),
        ]
        | None
    )
    modeling_assertion_document_type: Code100 | None
    modeling_assertion_document_description: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=2000, pattern=r"\S"),
        ]
        | None
    )
    modeling_assertion_document_metadata: JsonObject
    is_active: bool

    @field_validator("modeling_assertion_document_metadata")
    @classmethod
    def validate_metadata(cls, value: JsonObject) -> JsonObject:
        validate_assertion_json(
            value,
            maximum_bytes=ASSERTION_DOCUMENT_METADATA_MAX_BYTES,
            label="Assertion Document metadata",
        )
        return value


class ModelingAssertionRecordRecord(AssertionRecordKey):
    modeling_assertion_document_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    modeling_assertion_record_type: Code100
    modeling_assertion_text: NonblankText
    modeling_assertion_details: JsonObject
    modeling_assertion_source_location: JsonObject | None
    modeling_assertion_applicable_layers: tuple[
        Literal["analysis", "conceptual", "logical", "dimensional", "mapping"],
        ...,
    ]
    modeling_assertion_confidence: Confidence | None
    modeling_assertion_record_status: Status
    modeling_assertion_record_is_locked: bool

    @field_validator("modeling_assertion_text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if len(value) > ASSERTION_RECORD_TEXT_MAX_CHARACTERS:
            raise ValueError("Assertion Record text is too large")
        return value

    @field_validator("modeling_assertion_details")
    @classmethod
    def validate_details(cls, value: JsonObject) -> JsonObject:
        validate_assertion_json(
            value,
            maximum_bytes=ASSERTION_RECORD_DETAILS_MAX_BYTES,
            label="Assertion Record details",
        )
        return value

    @field_validator("modeling_assertion_source_location")
    @classmethod
    def validate_source_location(cls, value: JsonObject | None) -> JsonObject | None:
        if value is not None:
            validate_assertion_json(
                value,
                maximum_bytes=ASSERTION_RECORD_SOURCE_LOCATION_MAX_BYTES,
                label="Assertion Record source location",
            )
        return value

    @model_validator(mode="after")
    def validate_layers(self) -> ModelingAssertionRecordRecord:
        if len(set(self.modeling_assertion_applicable_layers)) != len(
            self.modeling_assertion_applicable_layers
        ):
            raise ValueError("Assertion applicable layers must be unique.")
        return self


class ObjectSupportRecord(ModelingRecord):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectKey
    support_role: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
        ]
        | None
    )
    support_reason: NonblankText
    support_reason_detail: NonblankText | None
    support_confidence: Confidence
    support_status: Status
    support_is_locked: bool


class AssertionSupportRecord(ModelingRecord):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordKey
    support_role: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
        ]
        | None
    )
    support_reason: NonblankText
    support_reason_detail: NonblankText | None
    support_confidence: Confidence
    support_status: Status
    support_is_locked: bool


type SupportRecord = Annotated[
    ObjectSupportRecord | AssertionSupportRecord,
    Field(discriminator="support_source_type"),
]


class ConceptualObjectRecord(ModelingRecord):
    conceptual_object_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    conceptual_object_definition: NonblankText
    conceptual_object_type: Code100
    conceptual_object_grain: NonblankText
    conceptual_object_aliases: tuple[str, ...]
    conceptual_object_confidence: Confidence
    conceptual_object_status: Status
    conceptual_object_is_locked: bool
    supports: tuple[SupportRecord, ...]

    @model_validator(mode="after")
    def validate_nested_keys(self) -> ConceptualObjectRecord:
        _require_unique(self.conceptual_object_aliases, "Conceptual Object aliases")
        _require_unique_sources(self.supports, "Conceptual Object supports")
        return self


class ConceptualRelationshipRecord(ModelingRecord):
    from_conceptual_object_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    to_conceptual_object_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    conceptual_relationship_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    conceptual_relationship_type: Code100
    conceptual_relationship_definition: NonblankText
    conceptual_relationship_cardinality: Cardinality | Literal["unknown"]
    conceptual_relationship_basis: NonblankText
    conceptual_relationship_cardinality_basis: NonblankText
    conceptual_relationship_confidence: Confidence
    conceptual_relationship_status: Status
    conceptual_relationship_is_locked: bool
    supports: tuple[SupportRecord, ...]

    @model_validator(mode="after")
    def validate_relationship(self) -> ConceptualRelationshipRecord:
        if normalize_model_key_value(self.from_conceptual_object_name) == normalize_model_key_value(
            self.to_conceptual_object_name
        ):
            raise ValueError("Conceptual Relationship endpoints must be different.")
        _require_unique_sources(self.supports, "Conceptual Relationship supports")
        return self


class SubmodelMembershipRecord(ModelingRecord):
    submodel_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    membership_status: Status
    membership_is_locked: bool


class LogicalObjectSourceRecord(ModelingRecord):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectKey
    source_order: int | None = Field(default=None, gt=0)
    rationale: NonblankText
    status: Status
    is_locked: bool


class LogicalAssertionSourceRecord(ModelingRecord):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordKey
    source_order: int | None = Field(default=None, gt=0)
    rationale: NonblankText
    status: Status
    is_locked: bool


type LogicalEntitySourceRecord = Annotated[
    LogicalObjectSourceRecord | LogicalAssertionSourceRecord,
    Field(discriminator="support_source_type"),
]


class DimensionalObjectSourceRecord(LogicalObjectSourceRecord):
    source_role: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]


class DimensionalAssertionSourceRecord(LogicalAssertionSourceRecord):
    source_role: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]


type DimensionalEntitySourceRecord = Annotated[
    DimensionalObjectSourceRecord | DimensionalAssertionSourceRecord,
    Field(discriminator="support_source_type"),
]


class AttributePhysicalSourceRecord(ModelingRecord):
    support_source_type: Literal["attribute"]
    source_attribute: PhysicalAttributeKey
    source_order: int | None = Field(default=None, gt=0)
    rationale: NonblankText
    status: Status
    is_locked: bool


class AttributeAssertionSourceRecord(ModelingRecord):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordKey
    source_order: int | None = Field(default=None, gt=0)
    rationale: NonblankText
    status: Status
    is_locked: bool


type AttributeSourceRecord = Annotated[
    AttributePhysicalSourceRecord | AttributeAssertionSourceRecord,
    Field(discriminator="support_source_type"),
]


class LogicalSubmodelRecord(ModelingRecord):
    logical_submodel_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_submodel_definition: NonblankText
    logical_submodel_status: Status
    logical_submodel_is_locked: bool


class LogicalEntityRecord(ModelingRecord):
    logical_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_entity_definition: NonblankText
    logical_entity_type: Literal[
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
    ]
    logical_entity_type_detail: NonblankText | None
    logical_entity_grain: NonblankText
    logical_entity_dependency_order: int = Field(ge=0)
    logical_entity_confidence: Confidence
    logical_entity_status: Status
    logical_entity_is_locked: bool
    submodels: tuple[SubmodelMembershipRecord, ...]
    sources: tuple[LogicalEntitySourceRecord, ...]

    @model_validator(mode="after")
    def validate_type_detail(self) -> LogicalEntityRecord:
        if (self.logical_entity_type == "other") != (self.logical_entity_type_detail is not None):
            raise ValueError("Logical Entity type detail is required only for 'other'.")
        _require_unique(
            (membership.submodel_name for membership in self.submodels),
            "Logical Entity Submodel memberships",
        )
        _require_unique_sources(self.sources, "Logical Entity sources")
        return self


class LogicalAttributeRecord(ModelingRecord):
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
    logical_attribute_is_primary_key: bool
    logical_attribute_is_natural_key: bool
    logical_attribute_is_surrogate_key: bool
    logical_attribute_ordinal_position: int = Field(gt=0)
    logical_attribute_is_audit_column: bool
    logical_attribute_status: Status
    logical_attribute_is_locked: bool
    sources: tuple[AttributeSourceRecord, ...]

    @model_validator(mode="after")
    def validate_key_policy(self) -> LogicalAttributeRecord:
        if self.logical_attribute_is_natural_key and self.logical_attribute_is_surrogate_key:
            raise ValueError("A Logical Attribute cannot be both natural and surrogate key.")
        if (
            self.logical_attribute_is_primary_key
            or self.logical_attribute_is_natural_key
            or self.logical_attribute_is_surrogate_key
        ) and self.logical_attribute_is_nullable:
            raise ValueError("A Logical key Attribute cannot be nullable.")
        _require_unique_sources(self.sources, "Logical Attribute sources")
        return self


class LogicalRelationshipRecord(ModelingRecord):
    logical_relationship_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    logical_relationship_definition: NonblankText
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
    logical_relationship_cardinality: Cardinality
    logical_relationship_confidence: Confidence
    logical_relationship_basis: NonblankText
    logical_relationship_cardinality_basis: NonblankText
    logical_relationship_status: Status
    logical_relationship_is_locked: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> LogicalRelationshipRecord:
        if (
            normalize_model_key_value(self.from_logical_entity_name),
            normalize_model_key_value(self.from_logical_attribute_name),
        ) == (
            normalize_model_key_value(self.to_logical_entity_name),
            normalize_model_key_value(self.to_logical_attribute_name),
        ):
            raise ValueError("Logical Relationship endpoints must be different.")
        return self


class DimensionalSubmodelRecord(ModelingRecord):
    dimensional_submodel_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_submodel_definition: NonblankText
    dimensional_submodel_status: Status
    dimensional_submodel_is_locked: bool


class DimensionalEntityRecord(ModelingRecord):
    dimensional_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_entity_definition: NonblankText
    dimensional_entity_type: Literal["fact", "dimension", "bridge"]
    dimensional_fact_type: (
        Literal[
            "transaction",
            "periodic_snapshot",
            "accumulating_snapshot",
            "factless",
        ]
        | None
    )
    dimensional_entity_grain_definition: NonblankText | None
    dimensional_entity_dependency_order: int = Field(ge=0)
    dimensional_entity_confidence: Confidence
    dimensional_entity_status: Status
    dimensional_entity_is_locked: bool
    submodels: tuple[SubmodelMembershipRecord, ...]
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
        _require_unique(
            (membership.submodel_name for membership in self.submodels),
            "Dimensional Entity Submodel memberships",
        )
        _require_unique_sources(self.sources, "Dimensional Entity sources")
        return self


class DimensionalAttributeRecord(ModelingRecord):
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
    dimensional_attribute_role: Literal[
        "key",
        "descriptor",
        "measure",
        "degenerate_dimension",
        "bridge_weight",
        "technical",
        "audit",
    ]
    dimensional_attribute_key_role: Literal["none", "surrogate", "business", "foreign"]
    dimensional_attribute_is_grain_component: bool
    dimensional_attribute_additivity: (
        Literal[
            "additive",
            "semi_additive",
            "non_additive",
        ]
        | None
    )
    dimensional_attribute_default_aggregation: Code100 | None
    dimensional_attribute_aggregation_basis: NonblankText | None
    dimensional_attribute_change_behavior: (
        Literal[
            "fixed",
            "overwrite",
            "historize",
        ]
        | None
    )
    dimensional_attribute_is_audit_column: bool
    dimensional_attribute_confidence: Confidence
    dimensional_attribute_status: Status
    dimensional_attribute_is_locked: bool
    sources: tuple[AttributeSourceRecord, ...]

    @model_validator(mode="after")
    def validate_attribute_policy(self) -> DimensionalAttributeRecord:
        if self.dimensional_attribute_key_role != "none" and (
            self.dimensional_attribute_role not in ("key", "technical")
        ):
            raise ValueError("A Dimensional key role requires a key or technical Attribute.")
        measure_fields = (
            self.dimensional_attribute_additivity,
            self.dimensional_attribute_default_aggregation,
            self.dimensional_attribute_aggregation_basis,
        )
        if self.dimensional_attribute_role == "measure":
            if measure_fields[0] is None or measure_fields[1] is None:
                raise ValueError("A measure requires additivity and default aggregation.")
            if measure_fields[0] != "additive" and measure_fields[2] is None:
                raise ValueError("A non-additive measure requires an aggregation basis.")
        elif any(value is not None for value in measure_fields):
            raise ValueError("Measure policy fields are valid only for measures.")
        if self.dimensional_attribute_is_audit_column != (
            self.dimensional_attribute_role == "audit"
        ):
            raise ValueError("Dimensional audit flag and role must agree.")
        _require_unique_sources(self.sources, "Dimensional Attribute sources")
        return self


class DimensionalRelationshipRecord(ModelingRecord):
    dimensional_relationship_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    dimensional_relationship_definition: NonblankText
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
    dimensional_relationship_kind: Annotated[
        str,
        StringConstraints(min_length=1, max_length=50, pattern=r"\S"),
    ]
    dimensional_relationship_cardinality: Cardinality
    dimensional_relationship_is_optional: bool
    dimensional_relationship_role_name: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
        ]
        | None
    )
    dimensional_relationship_confidence: Confidence
    dimensional_relationship_basis: NonblankText
    dimensional_relationship_cardinality_basis: NonblankText
    dimensional_relationship_status: Status
    dimensional_relationship_is_locked: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> DimensionalRelationshipRecord:
        if (
            normalize_model_key_value(self.from_dimensional_entity_name),
            normalize_model_key_value(self.from_dimensional_attribute_name),
        ) == (
            normalize_model_key_value(self.to_dimensional_entity_name),
            normalize_model_key_value(self.to_dimensional_attribute_name),
        ):
            raise ValueError("Dimensional Relationship endpoints must be different.")
        return self


class MappingDependencyRecord(ModelingRecord):
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    source_system_code: Code100
    source_system_dependency_order: int = Field(ge=0)
    mapping_source_system_dependency_status: Status
    mapping_source_system_dependency_is_locked: bool


class MappingObjectRecord(PhysicalObjectKey):
    source_system_code: Code100
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    object_dependency_order: int = Field(ge=0)
    artifact_type: Literal["sql_file", "python_file", "python_notebook"] | None
    artifact_generation_instructions: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=32768, pattern=r"\S"),
        ]
        | None
    )
    mapping_profile_key: (
        Annotated[
            str,
            StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,99}$"),
        ]
        | None
    )
    mapping_profile_version: DigestVersion | None
    mapping_package_document: JsonObject | None
    object_mapping_transformation_document: JsonObject | None
    object_mapping_status: Status
    object_mapping_is_locked: bool

    @field_validator("mapping_package_document")
    @classmethod
    def validate_and_normalize_package(cls, value: JsonObject | None) -> JsonObject | None:
        if value is None:
            return None
        package = validate_mapping_package_document(value)
        return cast(JsonObject, package.model_dump(mode="json"))

    @model_validator(mode="after")
    def validate_authored_group(self) -> MappingObjectRecord:
        authored = (
            self.artifact_type,
            self.artifact_generation_instructions,
            self.mapping_profile_key,
            self.mapping_profile_version,
            self.mapping_package_document,
            self.object_mapping_transformation_document,
        )
        if any(value is None for value in authored) and any(
            value is not None for value in authored
        ):
            raise ValueError("Mapping authored fields must be entirely present or absent.")
        package = self.mapping_package_document
        if package is not None:
            assert self.mapping_profile_key is not None
            assert self.mapping_profile_version is not None
            validate_mapping_package_profile(
                package,
                self.mapping_profile_key,
                self.mapping_profile_version,
            )
        transformation = self.object_mapping_transformation_document
        if transformation is not None and (
            transformation.get("schema_version") != "1.0"
            or transformation.get("transformation_kind") not in ("direct", "derived")
            or _json_size(transformation) > 262_144
        ):
            raise ValueError("Object Mapping transformation contract is invalid.")
        return self


class MappingAttributeRecord(PhysicalAttributeKey):
    source_system_code: Code100
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    modeled_attribute_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
    ]
    attribute_mapping_transformation_document: JsonObject | None
    attribute_mapping_status: Status
    attribute_mapping_is_locked: bool

    @model_validator(mode="after")
    def validate_transformation(self) -> MappingAttributeRecord:
        transformation = self.attribute_mapping_transformation_document
        if transformation is not None and (
            transformation.get("schema_version") != "1.0"
            or transformation.get("transformation_kind") not in ("direct", "expression")
            or _json_size(transformation) > 65_536
        ):
            raise ValueError("Attribute Mapping transformation contract is invalid.")
        return self


def _require_unique(values: Iterable[str], label: str) -> None:
    normalized = [normalize_model_key_value(value) for value in values]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique.")


def _require_unique_sources(sources: Iterable[Any], label: str) -> None:
    keys: list[tuple[str, ...]] = []
    for source in sources:
        if source.support_source_type == "assertion":
            key = (
                "assertion",
                normalize_model_key_value(source.assertion_record.modeling_assertion_record_key),
            )
        else:
            physical = getattr(source, "source_object", None) or source.source_attribute
            key = (
                source.support_source_type,
                normalize_model_key_value(physical.tenant_code),
                normalize_model_key_value(physical.system_code),
                normalize_model_key_value(physical.connection_code),
                normalize_model_key_value(physical.object_schema),
                normalize_model_key_value(physical.object_name),
                *(
                    (normalize_model_key_value(physical.attribute_name),)
                    if hasattr(physical, "attribute_name")
                    else ()
                ),
            )
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label} must be unique.")


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
