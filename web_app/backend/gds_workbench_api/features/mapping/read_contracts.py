"""Tenant-owned Mapping review contracts."""

import json
from datetime import datetime
from typing import Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

type MappingEntityType = Literal["logical_entity", "dimensional_entity"]
type MappingStatus = Literal["active", "needs_review", "inactive", "deprecated"]
type JsonObject = dict[str, JsonValue]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingDependencyFilters(ContractModel):
    entity_type: MappingEntityType | None = None
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, min_length=1, max_length=100)
    status: MappingStatus | None = None
    locked: bool | None = None

    @field_validator("entity_type", "source_system_code", "status", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip(" ").lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized


class MappingListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: MappingEntityType | None = None
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, max_length=100)
    status: MappingStatus | None = None
    locked: bool | None = None
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("entity_type", "source_system_code", "status", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip(" ").lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized


class SourceSystemReference(ContractModel):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)


class PhysicalObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone_code: str = Field(min_length=1, max_length=100)


class ModeledEntityReference(ContractModel):
    entity_type: MappingEntityType
    entity_id: int = Field(gt=0)
    entity_name: str = Field(min_length=1, max_length=255)


class PhysicalAttributeReference(ContractModel):
    object: PhysicalObjectReference
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_ordinal_position: int = Field(gt=0)
    attribute_data_type: str = Field(min_length=1, max_length=200)


class ModeledAttributeReference(ContractModel):
    entity: ModeledEntityReference
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=255)


class MappingDependencySummary(ContractModel):
    mapping_source_system_dependency_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    entity_type: MappingEntityType
    source_system: SourceSystemReference
    dependency_order: int = Field(ge=0)
    status: MappingStatus
    is_locked: bool
    updated_at: datetime


class MappingDependencyPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[MappingDependencySummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class MappingObjectSummary(ContractModel):
    mapping_object_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    target: PhysicalObjectReference
    source: ModeledEntityReference
    source_system: SourceSystemReference
    dependency_order: int = Field(ge=0)
    artifact_type: Literal["sql_file", "python_file", "python_notebook"] | None = None
    status: MappingStatus
    is_locked: bool
    updated_at: datetime


class MappingObjectPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[MappingObjectSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class MappingProfileProvenance(ContractModel):
    profile_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    profile_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    profile_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class OutputTemplateProvenance(ContractModel):
    output_template_id: int = Field(gt=0)
    output_template_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    output_template_name: str = Field(min_length=1, max_length=200)
    output_template_target_type: Literal["mapping_object", "mapping_attribute"]
    output_template_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    is_active: bool


class MappingObjectDetail(MappingObjectSummary):
    artifact_generation_instructions: str | None = Field(
        default=None,
        min_length=1,
        max_length=32768,
    )
    mapping_profile: MappingProfileProvenance | None = None
    mapping_package_document: JsonObject | None = None
    mapping_document_format: Literal["free_form", "structured"] | None = None
    mapping_document: JsonObject | None = None
    output_template: OutputTemplateProvenance | None = None
    created_at: datetime

    @field_validator("mapping_package_document")
    @classmethod
    def bound_package_document(cls, value: JsonObject | None) -> JsonObject | None:
        _require_json_size(value, maximum=524_288, label="Mapping package document")
        return value

    @field_validator("mapping_document")
    @classmethod
    def bound_mapping_document(cls, value: JsonObject | None) -> JsonObject | None:
        _require_json_size(value, maximum=262_144, label="Object Mapping document")
        return value

    @model_validator(mode="after")
    def validate_authored_group(self) -> Self:
        authored = (
            self.artifact_type,
            self.artifact_generation_instructions,
            self.mapping_profile,
            self.mapping_package_document,
            self.mapping_document,
        )
        if any(value is None for value in authored) and any(
            value is not None for value in authored
        ):
            raise ValueError("Object Mapping authored fields must be entirely present or absent")
        if self.mapping_document is None:
            if self.mapping_document_format is not None or self.output_template is not None:
                raise ValueError("Mapping document provenance requires a Mapping document")
        elif self.output_template is None:
            if self.mapping_document_format != "free_form":
                raise ValueError("A Mapping without an Output Template is free-form")
        else:
            if self.mapping_document_format != "structured":
                raise ValueError("A templated Mapping is structured")
            if self.output_template.output_template_target_type != "mapping_object":
                raise ValueError("Object Mapping requires mapping_object template provenance")
        return self


class MappingObjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_object_not_found",
            message="The requested Object Mapping was not found.",
        )


class MappingAttributeSummary(ContractModel):
    mapping_attribute_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    mapping_object_id: int = Field(gt=0)
    target: PhysicalAttributeReference
    source: ModeledAttributeReference
    source_system: SourceSystemReference
    status: MappingStatus
    is_locked: bool
    updated_at: datetime


class MappingAttributePage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[MappingAttributeSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ParentObjectMappingReference(ContractModel):
    mapping_object_id: int = Field(gt=0)
    dependency_order: int = Field(ge=0)
    artifact_type: Literal["sql_file", "python_file", "python_notebook"] | None = None
    mapping_profile: MappingProfileProvenance | None = None
    status: MappingStatus
    is_locked: bool


class MappingAttributeDetail(MappingAttributeSummary):
    parent_object_mapping: ParentObjectMappingReference
    mapping_document_format: Literal["free_form", "structured"] | None = None
    mapping_document: JsonObject | None = None
    output_template: OutputTemplateProvenance | None = None
    created_at: datetime

    @field_validator("mapping_document")
    @classmethod
    def bound_mapping_document(cls, value: JsonObject | None) -> JsonObject | None:
        _require_json_size(value, maximum=65_536, label="Attribute Mapping document")
        return value

    @model_validator(mode="after")
    def validate_document_provenance(self) -> Self:
        if self.parent_object_mapping.mapping_object_id != self.mapping_object_id:
            raise ValueError("Attribute Mapping parent reference does not match")
        if self.mapping_document is None:
            if self.mapping_document_format is not None or self.output_template is not None:
                raise ValueError("Mapping document provenance requires a Mapping document")
        elif self.output_template is None:
            if self.mapping_document_format != "free_form":
                raise ValueError("A Mapping without an Output Template is free-form")
        else:
            if self.mapping_document_format != "structured":
                raise ValueError("A templated Mapping is structured")
            if self.output_template.output_template_target_type != "mapping_attribute":
                raise ValueError("Attribute Mapping requires mapping_attribute template provenance")
        return self


class MappingAttributeNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_attribute_not_found",
            message="The requested Attribute Mapping was not found.",
        )


def _require_json_size(value: JsonObject | None, *, maximum: int, label: str) -> None:
    if value is None:
        return
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if len(encoded) > maximum:
        raise ValueError(f"{label} is too large")
