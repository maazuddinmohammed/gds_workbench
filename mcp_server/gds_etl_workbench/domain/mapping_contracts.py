"""Exact shared Pydantic contract for one authored Mapping package."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal, Self

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

Identifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
]
OrdinaryText = Annotated[
    str,
    Field(min_length=1, max_length=2_000, pattern=_NONBLANK_PATTERN),
]
OptionalOrdinaryText = Annotated[
    str,
    Field(min_length=1, max_length=2_000, pattern=_NONBLANK_PATTERN),
] | None
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
                "Prior-Mapping provenance requires prior-Mapping IDs and forbids "
                "ingestion IDs"
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
    def normalize_provenance(
        cls, values: list[PackageProvenanceV1]
    ) -> list[PackageProvenanceV1]:
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
    def normalize_parameters(
        cls, values: list[RuntimeParameterV1]
    ) -> list[RuntimeParameterV1]:
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


def validate_mapping_package_document(value: object) -> MappingPackageDocumentV1:
    """Validate and normalize one exact ``mapping.standard@1.0.0`` package."""

    if isinstance(value, MappingPackageDocumentV1):
        return value
    return MappingPackageDocumentV1.model_validate(value, strict=True)


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


def _require_acyclic_steps(steps: Sequence[NamedStepV1]) -> None:
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
