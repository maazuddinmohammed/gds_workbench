"""Strict Release-1 ``mapping.standard@1.0.0`` contracts.

The schema-bundle digest is derived from these models. Configuration may pin
that digest, but configuration is never authoritative over the generated
schemas.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any, Literal, Self, cast

from gds_etl_workbench.domain.mapping_contracts import (
    BIGINT_MAX as _BIGINT_MAX,
)
from gds_etl_workbench.domain.mapping_contracts import (
    ArtifactType,
    ConcurrentWriteMode,
    FqnText,
    Identifier,
    InstructionsText,
    Layer,
    LogicText,
    LowerHexDigest,
    MappingContractModel,
    MappingPackageDocumentV1,
    ModeledEntityType,
    NamedStepV1,
    NonNegativeOrder,
    OptionalOrdinaryText,
    OrdinaryText,
    PositiveDatabaseId,
    PositiveOrdinal,
    Route,
    RuntimeDefault,
    SignedBigInt,
    WriteMode,
    validate_mapping_package_document,
)
from gds_etl_workbench.domain.mapping_profiles import (
    MAPPING_STANDARD_PROFILE_KEY,
    MAPPING_STANDARD_PROFILE_VERSION,
    canonical_mapping_json_bytes,
)
from gds_etl_workbench.domain.mapping_profiles import (
    mapping_package_digest as shared_mapping_package_digest,
)
from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

SCHEMA_BUNDLE_VERSION = "1.0"
MAPPING_PROFILE_KEY = MAPPING_STANDARD_PROFILE_KEY
MAPPING_PROFILE_VERSION = MAPPING_STANDARD_PROFILE_VERSION
MAX_MAPPING_SECTION_BYTES = 16 * 1_024 * 1_024
MAX_GENERATOR_DOCUMENT_BYTES = 4 * 1_024 * 1_024
MAX_MAPPING_PACKAGES_PER_RUN = 1_000
MAX_ATTRIBUTE_MAPPER_ITEMS = 500

_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(?:"
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}|"
    r"\b(?:api[_ -]?key|password|token)\s*[:=]\s*\S{8,}|"
    r"\b(?:AccountKey|SharedAccessSignature)=\S+|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"\bdapi[a-f0-9]{20,}"
    r")"
)


class ObjectJoinV1(MappingContractModel):
    left_alias: Identifier
    right_alias: Identifier
    join_type: Literal["inner", "left", "right", "full", "cross"]
    condition: LogicText


class ObjectUnionV1(MappingContractModel):
    input_aliases: list[Identifier] = Field(min_length=2, max_length=128)
    all: bool
    alignment: LogicText

    @field_validator("input_aliases")
    @classmethod
    def validate_input_aliases(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Union aliases")


class ObjectFilterV1(MappingContractModel):
    expression: LogicText


class ObjectAggregationV1(MappingContractModel):
    output_name: Identifier
    expression: LogicText
    grouping_inputs: list[Identifier] = Field(max_length=128)

    @field_validator("grouping_inputs")
    @classmethod
    def validate_grouping_inputs(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Aggregation grouping inputs")


class ObjectMappingTransformationDocumentV1(MappingContractModel):
    schema_version: Literal["1.0"]
    transformation_kind: Literal["direct", "derived"]
    source_aliases: list[Identifier] = Field(min_length=1, max_length=128)
    joins: list[ObjectJoinV1] = Field(max_length=256)
    unions: list[ObjectUnionV1] = Field(max_length=256)
    filters: list[ObjectFilterV1] = Field(max_length=256)
    aggregations: list[ObjectAggregationV1] = Field(max_length=256)
    entity_contribution_logic: LogicText
    rationale: OrdinaryText

    @field_validator("source_aliases")
    @classmethod
    def validate_source_aliases(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Object-transformation aliases")

    @model_validator(mode="after")
    def validate_transform(self) -> Self:
        aliases = set(self.source_aliases)
        if any(
            item.left_alias not in aliases or item.right_alias not in aliases for item in self.joins
        ):
            raise ValueError("Join aliases must be declared source aliases")
        if any(not set(item.input_aliases) <= aliases for item in self.unions):
            raise ValueError("Union aliases must be declared source aliases")
        _require_unique(
            [item.output_name for item in self.aggregations],
            "Aggregation output names",
        )
        _require_max_bytes(self, 256 * 1_024, "Object transformation")
        return self


class AttributeSourceColumnV1(MappingContractModel):
    source_alias: Identifier
    source_attribute_id: PositiveDatabaseId


class AttributeMappingTransformationDocumentV1(MappingContractModel):
    schema_version: Literal["1.0"]
    transformation_kind: Literal["direct", "expression"]
    source_columns: list[AttributeSourceColumnV1] = Field(max_length=128)
    step_output: Identifier | None
    expression: LogicText | None
    logic: LogicText

    @model_validator(mode="after")
    def validate_transform(self) -> Self:
        _require_unique(
            [(item.source_alias, item.source_attribute_id) for item in self.source_columns],
            "Attribute source columns",
        )
        if self.transformation_kind == "direct":
            if len(self.source_columns) != 1 or self.expression is not None:
                raise ValueError(
                    "Direct Attribute transformations require one source column and "
                    "a null expression"
                )
        elif self.expression is None:
            raise ValueError("Expression Attribute transformations require an expression")
        _require_max_bytes(self, 64 * 1_024, "Attribute transformation")
        return self


class HeaderMappingV1(MappingContractModel):
    mapping_object_id: PositiveDatabaseId
    transformation: ObjectMappingTransformationDocumentV1


class HeaderCoverageV1(MappingContractModel):
    expected_mapping_object_ids: list[PositiveDatabaseId] = Field(
        min_length=1,
        max_length=64,
    )
    returned_mapping_object_ids: list[PositiveDatabaseId] = Field(
        min_length=1,
        max_length=64,
    )

    @field_validator("expected_mapping_object_ids", "returned_mapping_object_ids")
    @classmethod
    def validate_ids(cls, values: list[int]) -> list[int]:
        return _sorted_unique(values, "Header coverage IDs")


class HeaderMapperOutputV1(MappingContractModel):
    schema_version: Literal["1.0"]
    package: MappingPackageDocumentV1
    headers: list[HeaderMappingV1] = Field(min_length=1, max_length=64)
    coverage: HeaderCoverageV1

    @field_validator("headers")
    @classmethod
    def normalize_headers(cls, values: list[HeaderMappingV1]) -> list[HeaderMappingV1]:
        return sorted(values, key=lambda item: item.mapping_object_id)

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        returned = [item.mapping_object_id for item in self.headers]
        _require_unique(returned, "Header Mapping IDs")
        if sorted(returned) != self.coverage.returned_mapping_object_ids:
            raise ValueError("Returned header coverage must equal the supplied headers")
        if not set(returned) <= set(self.coverage.expected_mapping_object_ids):
            raise ValueError("Returned headers must belong to expected header coverage")
        package_aliases = {item.alias for item in self.package.executable_sources}
        for item in self.headers:
            if not set(item.transformation.source_aliases) <= package_aliases:
                raise ValueError("Header transformations may use only package source aliases")
        return self


class AttributeMappingItemV1(MappingContractModel):
    mapping_object_id: PositiveDatabaseId
    mapping_attribute_id: PositiveDatabaseId | None
    local_ref: Identifier | None
    modeled_entity_type: ModeledEntityType
    logical_attribute_id: PositiveDatabaseId | None
    dimensional_attribute_id: PositiveDatabaseId | None
    target_attribute_id: PositiveDatabaseId
    disposition: Literal["create", "update", "unchanged"]
    transformation: AttributeMappingTransformationDocumentV1

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if (self.mapping_attribute_id is None) == (self.local_ref is None):
            raise ValueError(
                "Exactly one existing Mapping Attribute ID or new local reference is required"
            )
        logical = self.logical_attribute_id is not None
        dimensional = self.dimensional_attribute_id is not None
        if logical == dimensional or logical != (self.modeled_entity_type == "logical_entity"):
            raise ValueError("Exactly one typed modeled Attribute must match the layer")
        if self.disposition == "create" and self.mapping_attribute_id is not None:
            raise ValueError("Create disposition requires a new local reference")
        if self.disposition != "create" and self.mapping_attribute_id is None:
            raise ValueError("Update and unchanged dispositions require an existing binding")
        return self


class TargetAttributeDispositionV1(MappingContractModel):
    target_attribute_id: PositiveDatabaseId
    disposition: Literal["mapped", "already_mapped", "intentionally_unmapped"]
    reason: OptionalOrdinaryText

    @model_validator(mode="after")
    def validate_reason(self) -> Self:
        if (self.reason is not None) != (self.disposition == "intentionally_unmapped"):
            raise ValueError(
                "A reason is required only for intentionally-unmapped target Attributes"
            )
        return self


class AttributeCoverageV1(MappingContractModel):
    expected_target_attribute_ids: list[PositiveDatabaseId] = Field(
        min_length=1,
        max_length=MAX_ATTRIBUTE_MAPPER_ITEMS,
    )
    returned_target_attribute_ids: list[PositiveDatabaseId] = Field(
        min_length=1,
        max_length=MAX_ATTRIBUTE_MAPPER_ITEMS,
    )
    expected_existing_mapping_attribute_ids: list[PositiveDatabaseId] = Field(
        max_length=MAX_ATTRIBUTE_MAPPER_ITEMS
    )
    returned_existing_mapping_attribute_ids: list[PositiveDatabaseId] = Field(
        max_length=MAX_ATTRIBUTE_MAPPER_ITEMS
    )

    @field_validator(
        "expected_target_attribute_ids",
        "returned_target_attribute_ids",
        "expected_existing_mapping_attribute_ids",
        "returned_existing_mapping_attribute_ids",
    )
    @classmethod
    def validate_ids(cls, values: list[int]) -> list[int]:
        return _sorted_unique(values, "Attribute coverage IDs")


class AttributeMapperBatchOutputV1(MappingContractModel):
    schema_version: Literal["1.0"]
    package_ref: Identifier
    target_object_id: PositiveDatabaseId
    source_system_id: PositiveDatabaseId
    chunk_index: int = Field(ge=1, le=100)
    chunk_count: int = Field(ge=1, le=100)
    package_digest: LowerHexDigest
    coverage_manifest_digest: LowerHexDigest
    attribute_mappings: list[AttributeMappingItemV1] = Field(max_length=MAX_ATTRIBUTE_MAPPER_ITEMS)
    target_attribute_dispositions: list[TargetAttributeDispositionV1] = Field(
        max_length=MAX_ATTRIBUTE_MAPPER_ITEMS
    )
    coverage: AttributeCoverageV1

    @field_validator("attribute_mappings")
    @classmethod
    def normalize_attribute_mappings(
        cls, values: list[AttributeMappingItemV1]
    ) -> list[AttributeMappingItemV1]:
        return sorted(
            values,
            key=lambda item: (
                item.target_attribute_id,
                item.mapping_object_id,
                item.mapping_attribute_id or 0,
                item.local_ref or "",
            ),
        )

    @field_validator("target_attribute_dispositions")
    @classmethod
    def normalize_dispositions(
        cls, values: list[TargetAttributeDispositionV1]
    ) -> list[TargetAttributeDispositionV1]:
        return sorted(values, key=lambda item: item.target_attribute_id)

    @model_validator(mode="after")
    def validate_batch(self) -> Self:
        if self.chunk_index > self.chunk_count:
            raise ValueError("Chunk index cannot exceed chunk count")
        mapping_ids = [
            item.mapping_attribute_id
            for item in self.attribute_mappings
            if item.mapping_attribute_id is not None
        ]
        local_refs = [
            item.local_ref for item in self.attribute_mappings if item.local_ref is not None
        ]
        _require_unique(mapping_ids, "Existing Mapping Attribute IDs")
        _require_unique(local_refs, "New Mapping Attribute local references")
        _require_unique(
            [
                (
                    item.mapping_object_id,
                    item.logical_attribute_id,
                    item.dimensional_attribute_id,
                    item.target_attribute_id,
                )
                for item in self.attribute_mappings
            ],
            "Attribute Mapping identities",
        )
        dispositions = [item.target_attribute_id for item in self.target_attribute_dispositions]
        _require_unique(dispositions, "Target Attribute dispositions")
        if sorted(dispositions) != self.coverage.returned_target_attribute_ids:
            raise ValueError("Returned target coverage must equal target dispositions")
        if not set(dispositions) <= set(self.coverage.expected_target_attribute_ids):
            raise ValueError("Returned target coverage must belong to expected coverage")
        if sorted(mapping_ids) != self.coverage.returned_existing_mapping_attribute_ids:
            raise ValueError("Returned existing-child coverage must equal existing mappings")
        if not set(mapping_ids) <= set(self.coverage.expected_existing_mapping_attribute_ids):
            raise ValueError("Returned existing children must belong to expected coverage")
        if not {item.target_attribute_id for item in self.attribute_mappings} <= set(dispositions):
            raise ValueError("Every mapped target Attribute requires one target disposition")
        return self


class GeneratorSchemaV1(MappingContractModel):
    document_version: Literal["1.0"]
    profile_key: Literal["mapping.standard"]
    profile_version: Literal["1.0.0"]
    profile_schema_digest: LowerHexDigest


class GeneratorAppliedModelV1(MappingContractModel):
    model_name: OrdinaryText
    model_revision: int = Field(ge=1, le=_BIGINT_MAX)
    source_context_digest: LowerHexDigest


class GeneratorSourceSystemPredecessorV1(MappingContractModel):
    code: Identifier
    name: OrdinaryText
    reason: OrdinaryText


class GeneratorSourceSystemV1(MappingContractModel):
    code: Identifier
    name: OrdinaryText
    dependency_order: NonNegativeOrder
    predecessors: list[GeneratorSourceSystemPredecessorV1] = Field(max_length=64)

    @field_validator("predecessors")
    @classmethod
    def normalize_predecessors(
        cls, values: list[GeneratorSourceSystemPredecessorV1]
    ) -> list[GeneratorSourceSystemPredecessorV1]:
        return sorted(values, key=lambda item: item.code)

    @model_validator(mode="after")
    def validate_predecessors(self) -> Self:
        _require_unique([item.code for item in self.predecessors], "Source predecessors")
        return self


class GeneratorArtifactV1(MappingContractModel):
    type: ArtifactType
    generation_instructions: InstructionsText


class GeneratorTargetPredecessorV1(MappingContractModel):
    target_fqn: FqnText
    reason: OrdinaryText


class GeneratorDependencyWavesV1(MappingContractModel):
    target_order: NonNegativeOrder
    target_predecessors: list[GeneratorTargetPredecessorV1] = Field(max_length=128)

    @field_validator("target_predecessors")
    @classmethod
    def normalize_predecessors(
        cls, values: list[GeneratorTargetPredecessorV1]
    ) -> list[GeneratorTargetPredecessorV1]:
        return sorted(values, key=lambda item: item.target_fqn)

    @model_validator(mode="after")
    def validate_predecessors(self) -> Self:
        _require_unique(
            [item.target_fqn for item in self.target_predecessors],
            "Target predecessors",
        )
        return self


class GeneratorTargetColumnV1(MappingContractModel):
    name: Identifier
    data_type: OrdinaryText
    nullable: bool
    ordinal: PositiveOrdinal
    definition: OptionalOrdinaryText


class GeneratorTargetV1(MappingContractModel):
    catalog: Identifier
    schema_name: Identifier = Field(alias="schema")
    object_name: Identifier
    fqn: FqnText
    zone: Literal["silver", "gold"]
    description: OptionalOrdinaryText
    grain_and_deduplication: OrdinaryText
    columns: list[GeneratorTargetColumnV1] = Field(min_length=1, max_length=5_000)

    @field_validator("columns")
    @classmethod
    def normalize_columns(
        cls, values: list[GeneratorTargetColumnV1]
    ) -> list[GeneratorTargetColumnV1]:
        return sorted(values, key=lambda item: item.ordinal)

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        names = [item.name for item in self.columns]
        ordinals = [item.ordinal for item in self.columns]
        _require_unique(names, "Target column names")
        if sorted(ordinals) != list(range(1, len(ordinals) + 1)):
            raise ValueError("Target column ordinals must be complete and unique")
        return self


class GeneratorUsedColumnV1(MappingContractModel):
    name: Identifier
    data_type: OrdinaryText
    nullable: bool
    definition: OptionalOrdinaryText
    meaning: OptionalOrdinaryText


class GeneratorBatchRuleV1(MappingContractModel):
    attribute_name: Identifier
    values: list[SignedBigInt] = Field(max_length=1_000)

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: list[int]) -> list[int]:
        return _sorted_unique(values, "Generator batch values")


class GeneratorExecutableSourceV1(MappingContractModel):
    alias: Identifier
    zone: Literal["bronze", "silver", "gold"]
    catalog: Identifier
    schema_name: Identifier = Field(alias="schema")
    object_name: Identifier
    fqn: FqnText
    used_columns: list[GeneratorUsedColumnV1] = Field(
        min_length=1,
        max_length=10_000,
    )
    batch_rule: GeneratorBatchRuleV1 | None

    @field_validator("used_columns")
    @classmethod
    def normalize_columns(cls, values: list[GeneratorUsedColumnV1]) -> list[GeneratorUsedColumnV1]:
        return sorted(values, key=lambda item: item.name)

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        _require_unique([item.name for item in self.used_columns], "Used source columns")
        return self


class GeneratorOriginalSourceProvenanceV1(MappingContractModel):
    source_system_code: Identifier
    source_system_name: OrdinaryText
    connection_code: Identifier
    source_object_name: OrdinaryText
    lineage_kind: Literal["original_ingestion", "prior_mapping"]
    lineage_path: list[OrdinaryText] = Field(min_length=1, max_length=32)
    executable_source_aliases: list[Identifier] = Field(min_length=1, max_length=16)

    @field_validator("executable_source_aliases")
    @classmethod
    def validate_aliases(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Provenance executable aliases")


class GeneratorRuntimeParameterV1(MappingContractModel):
    name: Identifier
    data_type: OrdinaryText
    purpose: OrdinaryText
    default_value: RuntimeDefault


class GeneratorNamedStepV1(MappingContractModel):
    name: Identifier
    depends_on: list[Identifier] = Field(max_length=256)
    inputs: list[Identifier] = Field(max_length=256)
    output: Identifier
    logic: LogicText

    @field_validator("depends_on", "inputs")
    @classmethod
    def validate_references(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Generator step references")


class GeneratorLoadV1(MappingContractModel):
    write_mode: WriteMode
    merge_keys: list[Identifier] = Field(max_length=5_000)
    partition_basis: OptionalOrdinaryText
    concurrent_system_write_mode: ConcurrentWriteMode
    concurrent_write_basis: OrdinaryText
    grain_and_deduplication: OrdinaryText

    @field_validator("merge_keys")
    @classmethod
    def validate_merge_keys(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Generator merge keys")

    @model_validator(mode="after")
    def validate_write_mode(self) -> Self:
        if self.write_mode == "merge" and not self.merge_keys:
            raise ValueError("Merge writes require at least one merge key")
        if self.write_mode != "merge" and self.merge_keys:
            raise ValueError("Only merge writes may declare merge keys")
        return self


class GeneratorEntityContributionV1(MappingContractModel):
    layer: Layer
    entity_name: OrdinaryText
    definition: OrdinaryText
    transformation_kind: Literal["direct", "derived"]
    source_aliases: list[Identifier] = Field(min_length=1, max_length=128)
    joins: list[ObjectJoinV1] = Field(max_length=256)
    unions: list[ObjectUnionV1] = Field(max_length=256)
    filters: list[ObjectFilterV1] = Field(max_length=256)
    aggregations: list[ObjectAggregationV1] = Field(max_length=256)
    entity_contribution_logic: LogicText
    rationale: OrdinaryText

    @field_validator("source_aliases")
    @classmethod
    def validate_source_aliases(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Entity-contribution aliases")


class GeneratorColumnContributorV1(MappingContractModel):
    entity_name: OrdinaryText
    attribute_name: OrdinaryText
    source_alias: Identifier
    source_column_name: Identifier


class GeneratorTargetColumnMappingV1(MappingContractModel):
    target_column_name: Identifier
    disposition: Literal["mapped", "already_mapped", "intentionally_unmapped"]
    reason: OptionalOrdinaryText
    contributors: list[GeneratorColumnContributorV1] = Field(max_length=32)
    kind: Literal["direct", "expression"]
    step_output: Identifier | None
    expression: LogicText | None
    logic: LogicText
    rationale: OrdinaryText

    @field_validator("contributors")
    @classmethod
    def normalize_contributors(
        cls, values: list[GeneratorColumnContributorV1]
    ) -> list[GeneratorColumnContributorV1]:
        return sorted(
            values,
            key=lambda item: (
                item.entity_name,
                item.attribute_name,
                item.source_alias,
                item.source_column_name,
            ),
        )

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        intentionally_unmapped = self.disposition == "intentionally_unmapped"
        if (self.reason is not None) != intentionally_unmapped:
            raise ValueError("A reason is required only for intentionally-unmapped columns")
        _require_unique(
            [
                (
                    item.entity_name,
                    item.attribute_name,
                    item.source_alias,
                    item.source_column_name,
                )
                for item in self.contributors
            ],
            "Target-column contributors",
        )
        if intentionally_unmapped:
            if self.contributors or self.expression is not None or self.step_output is not None:
                raise ValueError("Intentionally-unmapped columns cannot declare mapping content")
        elif self.kind == "direct":
            if len(self.contributors) != 1 or self.expression is not None:
                raise ValueError(
                    "Direct target-column mappings require one contributor and no expression"
                )
        elif self.expression is None:
            raise ValueError("Expression target-column mappings require an expression")
        return self


class GeneratorDocumentV1(MappingContractModel):
    document_schema: GeneratorSchemaV1 = Field(alias="schema")
    applied_model: GeneratorAppliedModelV1
    route: Route
    source_system: GeneratorSourceSystemV1
    artifact: GeneratorArtifactV1
    dependency_waves: GeneratorDependencyWavesV1
    target: GeneratorTargetV1
    executable_sources: list[GeneratorExecutableSourceV1] = Field(
        min_length=1,
        max_length=128,
    )
    original_source_provenance: list[GeneratorOriginalSourceProvenanceV1] = Field(max_length=128)
    runtime_parameters: list[GeneratorRuntimeParameterV1] = Field(max_length=128)
    named_steps: list[GeneratorNamedStepV1] = Field(min_length=1, max_length=256)
    load: GeneratorLoadV1
    entity_contributions: list[GeneratorEntityContributionV1] = Field(
        min_length=1,
        max_length=64,
    )
    target_columns: list[GeneratorTargetColumnMappingV1] = Field(
        min_length=1,
        max_length=5_000,
    )

    @field_validator("executable_sources")
    @classmethod
    def normalize_sources(
        cls, values: list[GeneratorExecutableSourceV1]
    ) -> list[GeneratorExecutableSourceV1]:
        return sorted(values, key=lambda item: item.alias)

    @field_validator("original_source_provenance")
    @classmethod
    def normalize_provenance(
        cls, values: list[GeneratorOriginalSourceProvenanceV1]
    ) -> list[GeneratorOriginalSourceProvenanceV1]:
        return sorted(
            values,
            key=lambda item: (
                item.source_system_code,
                item.connection_code,
                item.source_object_name,
            ),
        )

    @field_validator("runtime_parameters")
    @classmethod
    def normalize_parameters(
        cls, values: list[GeneratorRuntimeParameterV1]
    ) -> list[GeneratorRuntimeParameterV1]:
        return sorted(values, key=lambda item: item.name)

    @field_validator("named_steps")
    @classmethod
    def normalize_steps(cls, values: list[GeneratorNamedStepV1]) -> list[GeneratorNamedStepV1]:
        return sorted(values, key=lambda item: item.name)

    @field_validator("entity_contributions")
    @classmethod
    def normalize_entity_contributions(
        cls, values: list[GeneratorEntityContributionV1]
    ) -> list[GeneratorEntityContributionV1]:
        return sorted(values, key=lambda item: (item.layer, item.entity_name))

    @field_validator("target_columns")
    @classmethod
    def normalize_target_columns(
        cls, values: list[GeneratorTargetColumnMappingV1]
    ) -> list[GeneratorTargetColumnMappingV1]:
        return sorted(values, key=lambda item: item.target_column_name)

    @model_validator(mode="after")
    def validate_document(self) -> Self:
        if (self.route == "logical_to_silver") != (self.target.zone == "silver"):
            raise ValueError("Mapping route and target zone must agree")
        source_aliases = [item.alias for item in self.executable_sources]
        _require_unique(source_aliases, "Generator executable-source aliases")
        if sum(len(item.used_columns) for item in self.executable_sources) > 10_000:
            raise ValueError("Used source columns total cannot exceed 10000")
        source_alias_set = set(source_aliases)
        for item in self.original_source_provenance:
            if not set(item.executable_source_aliases) <= source_alias_set:
                raise ValueError("Provenance aliases must name executable sources")
        _require_unique(
            [item.name for item in self.runtime_parameters],
            "Generator runtime-parameter names",
        )
        step_names = [item.name for item in self.named_steps]
        outputs = [item.output for item in self.named_steps]
        _require_unique(step_names, "Generator step names")
        _require_unique(outputs, "Generator step outputs")
        step_name_set = set(step_names)
        output_set = set(outputs)
        for step in self.named_steps:
            if step.name in step.depends_on or not set(step.depends_on) <= step_name_set:
                raise ValueError("Generator step dependencies must name other steps")
            if not set(step.inputs) <= source_alias_set | output_set:
                raise ValueError("Generator step inputs must name sources or step outputs")
        _require_acyclic_steps(self.named_steps)

        expected_layer = "logical" if self.route == "logical_to_silver" else "dimensional"
        entity_names = [item.entity_name for item in self.entity_contributions]
        _require_unique(entity_names, "Entity-contribution names")
        for item in self.entity_contributions:
            if item.layer != expected_layer:
                raise ValueError("Entity-contribution layer must agree with the Mapping route")
            if not set(item.source_aliases) <= source_alias_set:
                raise ValueError("Entity contributions may use only executable sources")
            aliases = set(item.source_aliases)
            if any(
                join.left_alias not in aliases or join.right_alias not in aliases
                for join in item.joins
            ):
                raise ValueError("Entity-contribution joins must use declared aliases")
            if any(not set(union.input_aliases) <= aliases for union in item.unions):
                raise ValueError("Entity-contribution unions must use declared aliases")
            _require_unique(
                [aggregation.output_name for aggregation in item.aggregations],
                "Entity-contribution aggregation outputs",
            )
        target_names = [item.name for item in self.target.columns]
        target_mapping_names = [item.target_column_name for item in self.target_columns]
        _require_unique(target_mapping_names, "Target-column mappings")
        if sorted(target_names) != sorted(target_mapping_names):
            raise ValueError("Target-column mappings must cover every target column exactly once")
        if not set(self.load.merge_keys) <= set(target_names):
            raise ValueError("Generator merge keys must name target columns")
        source_columns = {
            item.alias: {column.name for column in item.used_columns}
            for item in self.executable_sources
        }
        for item in self.target_columns:
            if item.step_output is not None and item.step_output not in output_set:
                raise ValueError("Target-column step output must name a committed package step")
            if any(
                contributor.source_alias not in source_alias_set
                for contributor in item.contributors
            ):
                raise ValueError("Target-column contributors must name executable sources")
            if any(
                contributor.source_column_name not in source_columns[contributor.source_alias]
                for contributor in item.contributors
            ):
                raise ValueError("Target-column contributors must name embedded source columns")
            if any(
                contributor.entity_name not in entity_names for contributor in item.contributors
            ):
                raise ValueError("Target-column contributors must name embedded Entities")
        _reject_secret_shaped_values(self.model_dump(mode="json"))
        _require_max_bytes(self, MAX_GENERATOR_DOCUMENT_BYTES, "Generator document")
        return self


_SCHEMA_ROOTS: tuple[type[MappingContractModel], ...] = tuple(
    sorted(
        (HeaderMapperOutputV1, AttributeMapperBatchOutputV1, GeneratorDocumentV1),
        key=lambda item: item.__name__,
    )
)


def canonical_json_bytes(value: JsonValue | BaseModel | dict[str, Any]) -> bytes:
    """Encode contract JSON v1: UTF-8, sorted keys, compact, finite, no floats."""

    if isinstance(value, BaseModel):
        raw: object = value.model_dump(mode="json")
    else:
        raw = value
    return canonical_mapping_json_bytes(raw)


def parse_contract_json(raw: str | bytes | bytearray) -> dict[str, JsonValue]:
    """Parse one object-root contract while rejecting duplicate keys and floats."""

    def object_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    def reject_float(_value: str) -> float:
        raise ValueError("floating-point JSON values are not allowed")

    def reject_constant(_value: str) -> float:
        raise ValueError("non-finite JSON values are not allowed")

    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=object_pairs,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("invalid contract JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("contract JSON must have an object root")
    return cast(dict[str, JsonValue], parsed)


def mapping_schema_bundle() -> dict[str, JsonValue]:
    """Return the deterministic schema wrapper used by the registry digest.

    Compatibility is pinned to Pydantic 2.13.4. Each root schema is generated in
    validation mode, and entries are ordered lexicographically by class name.
    """

    schemas: list[JsonValue] = []
    for root in _SCHEMA_ROOTS:
        schema = cast(dict[str, JsonValue], root.model_json_schema(mode="validation"))
        _assert_strict_object_schemas(schema)
        schemas.append({"class_name": root.__name__, "json_schema": schema})
    return {
        "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
        "json_schema_mode": "validation",
        "schemas": schemas,
    }


def mapping_schema_bundle_digest() -> str:
    """Return lowercase SHA-256 of the canonical generated schema bundle."""

    return hashlib.sha256(canonical_json_bytes(mapping_schema_bundle())).hexdigest()


def mapping_package_digest(package: MappingPackageDocumentV1) -> str:
    """Return the contract-canonical digest for one validated package."""

    validated = validate_mapping_package_document(package)
    return shared_mapping_package_digest(validated.model_dump(mode="json"))


def require_mapping_section_size(value: JsonValue | BaseModel | dict[str, Any]) -> None:
    """Fail before invocation when a complete Mapping Section exceeds 16 MiB."""

    if len(canonical_json_bytes(value)) > MAX_MAPPING_SECTION_BYTES:
        raise ValueError("Mapping Section exceeds its canonical byte limit")


def _sorted_unique(values: list[Any], label: str) -> list[Any]:
    _require_unique(values, label)
    return sorted(values)


def _require_unique(values: Sequence[Any], label: str) -> None:
    try:
        unique = set(values)
    except TypeError as exc:
        raise ValueError(f"{label} must be hashable") from exc
    if len(unique) != len(values):
        raise ValueError(f"{label} must be unique")


def _require_acyclic_steps(steps: Sequence[NamedStepV1 | GeneratorNamedStepV1]) -> None:
    remaining = {step.name: set(step.depends_on) for step in steps}
    while remaining:
        ready = {name for name, dependencies in remaining.items() if not dependencies}
        if not ready:
            raise ValueError("Named-step dependencies must be acyclic")
        remaining = {
            name: dependencies - ready
            for name, dependencies in remaining.items()
            if name not in ready
        }


def _require_max_bytes(value: BaseModel, limit: int, label: str) -> None:
    if len(canonical_json_bytes(value)) > limit:
        raise ValueError(f"{label} exceeds its canonical byte limit")


def _reject_secret_shaped_values(value: object) -> None:
    if isinstance(value, str):
        if _SECRET_VALUE_PATTERN.search(value):
            raise ValueError("Generator documents cannot contain secret-shaped values")
        return
    if isinstance(value, list | tuple):
        for item in cast(Sequence[object], value):
            _reject_secret_shaped_values(item)
        return
    if isinstance(value, dict):
        for item in cast(dict[object, object], value).values():
            _reject_secret_shaped_values(item)


def _assert_strict_object_schemas(schema: dict[str, JsonValue]) -> None:
    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                properties = value.get("properties")
                required = value.get("required")
                if value.get("additionalProperties") is not False:
                    raise RuntimeError("Mapping schema object permits extra fields")
                if isinstance(properties, dict) and set(properties) != set(
                    cast(list[str], required)
                ):
                    raise RuntimeError("Mapping schema has optional object properties")
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(schema)
