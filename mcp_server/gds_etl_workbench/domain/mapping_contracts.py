"""Exact shared Pydantic contract for one authored Mapping package."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated, Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gds_etl_workbench.domain.mapping_profiles import (
    canonical_mapping_json_bytes,
    resolve_mapping_profile_schema_digest,
)

_BIGINT_MIN = -(2**63)
BIGINT_MAX = 2**63 - 1
_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_NONBLANK_PATTERN = r"^[\s\S]*\S[\s\S]*$"
_LOWER_HEX_64_PATTERN = r"^[0-9a-f]{64}$"
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(?:"
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}|"
    r"\b(?:api[_ -]?key|password|token)\s*[:=]\s*\S{8,}|"
    r"\b(?:AccountKey|SharedAccessSignature)=\S+|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"\bdapi[a-f0-9]{20,}"
    r")"
)
MAX_GENERATOR_DOCUMENT_BYTES = 4 * 1_024 * 1_024

Identifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
]
OrdinaryText = Annotated[
    str,
    Field(min_length=1, max_length=2_000, pattern=_NONBLANK_PATTERN),
]
OptionalOrdinaryText = (
    Annotated[
        str,
        Field(min_length=1, max_length=2_000, pattern=_NONBLANK_PATTERN),
    ]
    | None
)
LogicText = Annotated[
    str,
    Field(min_length=1, max_length=16_384, pattern=_NONBLANK_PATTERN),
]
InstructionsText = Annotated[
    str,
    Field(min_length=1, max_length=32_768, pattern=_NONBLANK_PATTERN),
]
FqnText = Annotated[
    str,
    Field(min_length=1, max_length=1_024, pattern=_NONBLANK_PATTERN),
]
LowerHexDigest = Annotated[str, Field(pattern=_LOWER_HEX_64_PATTERN)]
PositiveDatabaseId = Annotated[int, Field(ge=1, le=BIGINT_MAX)]
SignedBigInt = Annotated[int, Field(ge=_BIGINT_MIN, le=BIGINT_MAX)]
PositiveOrdinal = Annotated[int, Field(ge=1, le=5_000)]
NonNegativeOrder = Annotated[int, Field(ge=0, le=BIGINT_MAX)]
RuntimeDefault = Annotated[str, Field(max_length=2_000)] | SignedBigInt | bool | None

Route = Literal["logical_to_silver", "dimensional_to_gold"]
ArtifactType = Literal["sql_file", "python_file", "python_notebook"]
WriteMode = Literal["append", "overwrite", "merge"]
ConcurrentWriteMode = Literal[
    "disjoint_partitions",
    "idempotent_merge",
    "serialized",
]
Layer = Literal["logical", "dimensional"]
ModeledEntityType = Literal["logical_entity", "dimensional_entity"]


class MappingContractModel(BaseModel):
    """Base shape required at every Mapping contract boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        serialize_by_alias=True,
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


class PydanticProfileV1(MappingContractModel):
    key: Literal["mapping.standard"]
    version: Literal["1.0.0"]
    schema_digest: LowerHexDigest

    @model_validator(mode="after")
    def validate_deployed_profile(self) -> Self:
        if self.schema_digest != resolve_mapping_profile_schema_digest(
            self.key,
            self.version,
        ):
            raise ValueError("Mapping package profile digest is not deployed.")
        return self


class PackageBatchRuleV1(MappingContractModel):
    attribute_id: PositiveDatabaseId
    values: list[SignedBigInt] = Field(max_length=1_000)

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: list[int]) -> list[int]:
        return _sorted_unique(values, "Batch values")


class PackageExecutableSourceV1(MappingContractModel):
    object_id: PositiveDatabaseId
    alias: Identifier
    role: OrdinaryText
    batch_rule: PackageBatchRuleV1 | None


class PackageProvenanceV1(MappingContractModel):
    lineage_kind: Literal["original_ingestion", "prior_mapping"]
    source_system_id: PositiveDatabaseId
    source_object_id: PositiveDatabaseId
    ingestion_object_mapping_ids: list[PositiveDatabaseId] = Field(max_length=16)
    prior_object_mapping_ids: list[PositiveDatabaseId] = Field(max_length=16)
    executable_source_aliases: list[Identifier] = Field(min_length=1, max_length=16)

    @field_validator(
        "ingestion_object_mapping_ids",
        "prior_object_mapping_ids",
        "executable_source_aliases",
    )
    @classmethod
    def validate_unique_lists(cls, values: list[int] | list[str]) -> list[int] | list[str]:
        return _sorted_unique(values, "Provenance references")

    @model_validator(mode="after")
    def validate_lineage_kind(self) -> Self:
        if self.lineage_kind == "original_ingestion":
            if not self.ingestion_object_mapping_ids or self.prior_object_mapping_ids:
                raise ValueError(
                    "Original-ingestion provenance requires ingestion IDs and forbids "
                    "prior-Mapping IDs"
                )
        elif not self.prior_object_mapping_ids or self.ingestion_object_mapping_ids:
            raise ValueError(
                "Prior-Mapping provenance requires prior-Mapping IDs and forbids ingestion IDs"
            )
        return self


class RuntimeParameterV1(MappingContractModel):
    name: Identifier
    data_type: OrdinaryText
    purpose: OrdinaryText
    default_value: RuntimeDefault


class SourceSystemDependencyV1(MappingContractModel):
    predecessor_source_system_id: PositiveDatabaseId
    reason: OrdinaryText


class TargetDependencyV1(MappingContractModel):
    predecessor_target_object_id: PositiveDatabaseId
    reason: OrdinaryText


class NamedStepV1(MappingContractModel):
    name: Identifier
    depends_on: list[Identifier] = Field(max_length=256)
    inputs: list[Identifier] = Field(max_length=256)
    output: Identifier
    logic: LogicText

    @field_validator("depends_on", "inputs")
    @classmethod
    def validate_unique_names(cls, values: list[str]) -> list[str]:
        return _sorted_unique(values, "Step references")


class MappingLoadV1(MappingContractModel):
    write_mode: WriteMode
    merge_keys: list[PositiveDatabaseId] = Field(max_length=5_000)
    partition_basis: OptionalOrdinaryText
    concurrent_system_write_mode: ConcurrentWriteMode
    concurrent_write_basis: OrdinaryText

    @field_validator("merge_keys")
    @classmethod
    def validate_merge_keys(cls, values: list[int]) -> list[int]:
        return _sorted_unique(values, "Merge-key IDs")

    @model_validator(mode="after")
    def validate_write_mode(self) -> Self:
        if self.write_mode == "merge" and not self.merge_keys:
            raise ValueError("Merge writes require at least one merge key")
        if self.write_mode != "merge" and self.merge_keys:
            raise ValueError("Only merge writes may declare merge keys")
        return self


class MappingPackageDocumentV1(MappingContractModel):
    schema_version: Literal["1.0"]
    package_ref: Identifier
    route: Route
    target_object_id: PositiveDatabaseId
    source_system_id: PositiveDatabaseId
    artifact_type: ArtifactType
    artifact_generation_instructions: InstructionsText
    pydantic_profile: PydanticProfileV1
    executable_sources: list[PackageExecutableSourceV1] = Field(
        min_length=1,
        max_length=128,
    )
    non_executable_provenance: list[PackageProvenanceV1] = Field(max_length=128)
    runtime_parameters: list[RuntimeParameterV1] = Field(max_length=128)
    source_system_dependencies: list[SourceSystemDependencyV1] = Field(max_length=256)
    target_dependencies: list[TargetDependencyV1] = Field(max_length=256)
    steps: list[NamedStepV1] = Field(min_length=1, max_length=256)
    grain_and_deduplication: OrdinaryText
    load: MappingLoadV1

    @field_validator("executable_sources")
    @classmethod
    def normalize_sources(
        cls, values: list[PackageExecutableSourceV1]
    ) -> list[PackageExecutableSourceV1]:
        return sorted(values, key=lambda item: item.alias)

    @field_validator("non_executable_provenance")
    @classmethod
    def normalize_provenance(cls, values: list[PackageProvenanceV1]) -> list[PackageProvenanceV1]:
        return sorted(
            values,
            key=lambda item: (
                item.lineage_kind,
                item.source_system_id,
                item.source_object_id,
            ),
        )

    @field_validator("runtime_parameters")
    @classmethod
    def normalize_parameters(cls, values: list[RuntimeParameterV1]) -> list[RuntimeParameterV1]:
        return sorted(values, key=lambda item: item.name)

    @field_validator("source_system_dependencies")
    @classmethod
    def normalize_source_dependencies(
        cls, values: list[SourceSystemDependencyV1]
    ) -> list[SourceSystemDependencyV1]:
        return sorted(values, key=lambda item: item.predecessor_source_system_id)

    @field_validator("target_dependencies")
    @classmethod
    def normalize_target_dependencies(
        cls, values: list[TargetDependencyV1]
    ) -> list[TargetDependencyV1]:
        return sorted(values, key=lambda item: item.predecessor_target_object_id)

    @field_validator("steps")
    @classmethod
    def normalize_steps(cls, values: list[NamedStepV1]) -> list[NamedStepV1]:
        return sorted(values, key=lambda item: item.name)

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        aliases = [item.alias for item in self.executable_sources]
        _require_unique(aliases, "Executable-source aliases")
        _require_unique(
            [item.name for item in self.runtime_parameters],
            "Runtime-parameter names",
        )
        _require_unique(
            [item.predecessor_source_system_id for item in self.source_system_dependencies],
            "Source-System dependencies",
        )
        _require_unique(
            [item.predecessor_target_object_id for item in self.target_dependencies],
            "Target dependencies",
        )
        alias_set = set(aliases)
        for item in self.non_executable_provenance:
            if not set(item.executable_source_aliases) <= alias_set:
                raise ValueError("Provenance aliases must name executable sources")

        step_names = [item.name for item in self.steps]
        outputs = [item.output for item in self.steps]
        _require_unique(step_names, "Step names")
        _require_unique(outputs, "Step outputs")
        step_name_set = set(step_names)
        for step in self.steps:
            if step.name in step.depends_on or not set(step.depends_on) <= step_name_set:
                raise ValueError("Step dependencies must name other package steps")
            if not set(step.inputs) <= alias_set | set(outputs):
                raise ValueError("Step inputs must name executable aliases or step outputs")
        _require_acyclic_steps(self.steps)
        _require_max_bytes(self, 512 * 1_024, "Mapping package")
        return self


class GeneratorSchemaV1(MappingContractModel):
    document_version: Literal["1.0"]
    profile_key: Literal["mapping.standard"]
    profile_version: Literal["1.0.0"]
    profile_schema_digest: LowerHexDigest


class GeneratorAppliedModelV1(MappingContractModel):
    model_name: OrdinaryText
    model_revision: int = Field(ge=1, le=BIGINT_MAX)
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
        cls,
        values: list[GeneratorSourceSystemPredecessorV1],
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
        cls,
        values: list[GeneratorTargetPredecessorV1],
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
        cls,
        values: list[GeneratorTargetColumnV1],
    ) -> list[GeneratorTargetColumnV1]:
        return sorted(values, key=lambda item: item.ordinal)

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        _require_unique([item.name for item in self.columns], "Target column names")
        ordinals = [item.ordinal for item in self.columns]
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
    used_columns: list[GeneratorUsedColumnV1] = Field(min_length=1, max_length=10_000)
    batch_rule: GeneratorBatchRuleV1 | None

    @field_validator("used_columns")
    @classmethod
    def normalize_columns(
        cls,
        values: list[GeneratorUsedColumnV1],
    ) -> list[GeneratorUsedColumnV1]:
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
        cls,
        values: list[GeneratorColumnContributorV1],
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
    executable_sources: list[GeneratorExecutableSourceV1] = Field(min_length=1, max_length=128)
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
        cls,
        values: list[GeneratorExecutableSourceV1],
    ) -> list[GeneratorExecutableSourceV1]:
        return sorted(values, key=lambda item: item.alias)

    @field_validator("original_source_provenance")
    @classmethod
    def normalize_provenance(
        cls,
        values: list[GeneratorOriginalSourceProvenanceV1],
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
        cls,
        values: list[GeneratorRuntimeParameterV1],
    ) -> list[GeneratorRuntimeParameterV1]:
        return sorted(values, key=lambda item: item.name)

    @field_validator("named_steps")
    @classmethod
    def normalize_steps(
        cls,
        values: list[GeneratorNamedStepV1],
    ) -> list[GeneratorNamedStepV1]:
        return sorted(values, key=lambda item: item.name)

    @field_validator("entity_contributions")
    @classmethod
    def normalize_entity_contributions(
        cls,
        values: list[GeneratorEntityContributionV1],
    ) -> list[GeneratorEntityContributionV1]:
        return sorted(values, key=lambda item: (item.layer, item.entity_name))

    @field_validator("target_columns")
    @classmethod
    def normalize_target_columns(
        cls,
        values: list[GeneratorTargetColumnMappingV1],
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
        reject_secret_shaped_values(self.model_dump(mode="json"))
        _require_max_bytes(self, MAX_GENERATOR_DOCUMENT_BYTES, "Generator document")
        return self


def validate_mapping_package_document(value: object) -> MappingPackageDocumentV1:
    """Validate and normalize one exact ``mapping.standard@1.0.0`` package."""

    if isinstance(value, MappingPackageDocumentV1):
        return value
    return MappingPackageDocumentV1.model_validate(value, strict=True)


def reject_secret_shaped_values(value: object) -> None:
    """Reject credential-like text without returning or logging the matched value."""

    _reject_secret_shaped_values(value)


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
    if len(canonical_mapping_json_bytes(value.model_dump(mode="json"))) > limit:
        raise ValueError(f"{label} exceeds its canonical byte limit")


def _reject_secret_shaped_values(value: object) -> None:
    if isinstance(value, str):
        if _SECRET_VALUE_PATTERN.search(value):
            raise ValueError("Generator documents cannot contain secret-shaped values")
        return
    if isinstance(value, dict):
        for nested in cast(dict[object, object], value).values():
            _reject_secret_shaped_values(nested)
        return
    if isinstance(value, list):
        for nested in cast(list[object], value):
            _reject_secret_shaped_values(nested)
