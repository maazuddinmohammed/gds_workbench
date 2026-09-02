"""Public contracts for stored SQL Code Generation review and download."""

from datetime import datetime
from typing import Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gds_workbench_api.features.mapping.read_contracts import (
    ModeledEntityReference,
    PhysicalObjectReference,
    SourceSystemReference,
)

type MappingEntityType = Literal["logical_entity", "dimensional_entity"]

MAX_SELECTED_ARTIFACTS = 25
MAX_BULK_SQL_BYTES = 32 * 1024 * 1024


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CodeGenerationTargetFilters(ContractModel):
    entity_type: MappingEntityType | None = None
    system_id: int | None = Field(default=None, gt=0)
    system_code: str | None = Field(default=None, min_length=1, max_length=100)
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator(
        "entity_type",
        "system_code",
        "source_system_code",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip(" ").lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized


class CodeGenerationTargetQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: MappingEntityType | None = None
    system_id: int | None = Field(default=None, gt=0)
    system_code: str | None = Field(default=None, max_length=100)
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, max_length=100)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator(
        "entity_type",
        "system_code",
        "source_system_code",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip(" ").lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized


class StoredSqlArtifactSummary(ContractModel):
    generated_sql_artifact_id: int = Field(gt=0)
    artifact_name: str = Field(min_length=1, max_length=400)
    workflow_run_id: int | None = Field(default=None, gt=0)
    generated_at: datetime
    generated_code_status: Literal["active", "inactive", "deprecated"]
    source_system_codes: tuple[str, ...] = Field(max_length=200)
    artifact_is_current: bool


class CodeMappingSupport(ContractModel):
    mapping_object_id: int = Field(gt=0)
    source: ModeledEntityReference
    source_system: SourceSystemReference
    dependency_order: int = Field(ge=0)


class CodeGenerationTargetObjectReference(PhysicalObjectReference):
    """A physical target and the Tenant whose data it represents.

    The regular Tenant/System/Connection fields identify the physical placement.
    For Bronze, Silver, and Gold that placement can be GDS; source Tenant remains
    a distinct Object property.
    """

    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)


class CodeGenerationTargetSummary(ContractModel):
    target: CodeGenerationTargetObjectReference
    entity_type: MappingEntityType
    mapping_supports: tuple[CodeMappingSupport, ...] = Field(
        min_length=1,
        max_length=200,
    )
    mapping_support_count: int = Field(gt=0)
    mapping_supports_truncated: bool
    source_systems: tuple[SourceSystemReference, ...] = Field(
        min_length=1,
        max_length=200,
    )
    source_system_count: int = Field(gt=0, le=200)
    artifacts: tuple[StoredSqlArtifactSummary, ...] = Field(max_length=5_000)
    artifact_count: int = Field(ge=0, le=5_000)

    @model_validator(mode="after")
    def validate_source_system_count(self) -> Self:
        if self.source_system_count != len(self.source_systems):
            raise ValueError("Source System count does not match returned Systems")
        if self.artifact_count != len(self.artifacts):
            raise ValueError("Artifact count does not match returned artifacts")
        return self


class CodeGenerationTargetPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[CodeGenerationTargetSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class SqlGenerationGuideProvenance(ContractModel):
    sql_generation_guide_id: int = Field(gt=0)
    sql_generation_guide_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    sql_generation_guide_name: str = Field(min_length=1, max_length=200)
    guide_is_active: bool
    sql_generation_guide_version_id: int = Field(gt=0)
    sql_generation_guide_version_number: int = Field(gt=0)
    sql_generation_guide_version_status: Literal["draft", "published", "retired"]
    sql_generation_guide_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SqlGeneratorProvenance(ContractModel):
    generator_code: str | None = Field(
        pattern=r"^[a-z][a-z0-9_.-]{0,99}$",
    )
    generator_version: str | None = Field(
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    )
    generated_by_display_name: str = Field(min_length=1, max_length=200)


class GeneratedSqlArtifactDetail(ContractModel):
    generated_sql_artifact_id: int = Field(gt=0)
    artifact_name: str = Field(min_length=1, max_length=400)
    model_id: int = Field(gt=0)
    target: CodeGenerationTargetObjectReference
    entity_type: MappingEntityType
    source_systems: tuple[SourceSystemReference, ...] = Field(max_length=200)
    source_system_count: int = Field(ge=0, le=200)
    mapping_supports: tuple[CodeMappingSupport, ...] = Field(max_length=200)
    mapping_support_count: int = Field(ge=0)
    mapping_supports_truncated: bool
    artifact_is_current: bool
    generated_code_status: Literal["active", "inactive", "deprecated"]
    guide: SqlGenerationGuideProvenance | None
    workflow_run_id: int | None = Field(default=None, gt=0)
    generator: SqlGeneratorProvenance | None
    generated_at: datetime
    generated_sql: str = Field(min_length=1, repr=False)
    generated_sql_byte_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounded_sql_and_supports(self) -> Self:
        if len(self.generated_sql.encode()) != self.generated_sql_byte_count:
            raise ValueError("generated SQL byte count does not match its content")
        if self.mapping_support_count < len(self.mapping_supports):
            raise ValueError("Mapping support count is smaller than returned supports")
        if self.mapping_supports_truncated != (
            self.mapping_support_count > len(self.mapping_supports)
        ):
            raise ValueError("Mapping support truncation state is inconsistent")
        if self.source_system_count != len(self.source_systems):
            raise ValueError("Source System count does not match returned Systems")
        return self


class SqlArtifactDownload(ContractModel):
    generated_sql_artifact_id: int = Field(gt=0)
    artifact_name: str = Field(min_length=1, max_length=400)
    target: CodeGenerationTargetObjectReference
    entity_type: MappingEntityType
    generated_sql: str = Field(min_length=1, repr=False)
    generated_sql_byte_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounded_sql(self) -> Self:
        if len(self.generated_sql.encode()) != self.generated_sql_byte_count:
            raise ValueError("generated SQL byte count does not match its content")
        return self


class GeneratedSqlArtifactNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="generated_sql_artifact_not_found",
            message="The requested generated SQL artifact was not found.",
        )


class SqlArtifactBundleLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="generated_sql_bundle_limit_exceeded",
            message="The selected generated SQL artifacts exceed the safe bundle limit.",
        )
