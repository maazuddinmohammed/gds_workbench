"""Tenant-owned Mapping read contracts for Entity-owned Mapping."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

type MappingEntityType = Literal["logical_entity", "dimensional_entity"]
type MappingStatus = Literal["active", "inactive", "deprecated"]
type JsonObject = dict[str, JsonValue]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingFilters(ContractModel):
    entity_type: MappingEntityType | None = None
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, min_length=1, max_length=100)
    status: MappingStatus | None = None
    locked: bool | None = None


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
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized


class MappingAttributeFilters(MappingFilters):
    mapping_object_id: int | None = Field(default=None, gt=0)


class MappingAttributeListQuery(MappingListQuery):
    mapping_object_id: int | None = Field(default=None, gt=0)


class SourceSystemReference(ContractModel):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)


class ModeledEntityReference(ContractModel):
    entity_type: MappingEntityType
    entity_id: int = Field(gt=0)
    entity_schema_name: str = Field(min_length=1, max_length=400)
    entity_name: str = Field(min_length=1, max_length=255)


class ModeledAttributeReference(ContractModel):
    ordinal_position: int = Field(gt=0)
    data_type: str = Field(min_length=1, max_length=200)
    entity: ModeledEntityReference
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=255)


class MappingGenerationAttribute(ContractModel):
    attribute_id: int
    attribute_name: str
    modeled_attribute_name: str
    ordinal_position: int
    is_locked: bool
    is_authored: bool


class MappingGenerationTarget(ModeledEntityReference):
    source_system: SourceSystemReference
    entity_name: str
    mapping_object_id: int | None
    object_order: int
    is_locked: bool
    has_sources: bool
    attributes: tuple[MappingGenerationAttribute, ...]


class MappingGenerationPage(ContractModel):
    model_id: int
    model_revision: int
    items: tuple[MappingGenerationTarget, ...]
    next_cursor: str | None


class MappingObjectSummary(ContractModel):
    mapping_object_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    target: ModeledEntityReference
    source_system: SourceSystemReference
    dependency_order: int = Field(ge=0)
    status: MappingStatus
    is_locked: bool
    updated_at: datetime


class MappingObjectPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[MappingObjectSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class OutputTemplateProvenance(ContractModel):
    output_template_id: int = Field(gt=0)
    output_template_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    output_template_name: str = Field(min_length=1, max_length=200)
    output_template_target_type: Literal["mapping_object", "mapping_attribute"]
    output_template_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    is_active: bool


class MappingObjectDetail(MappingObjectSummary):
    mapping_document: JsonObject | None = None
    output_template: OutputTemplateProvenance | None = None
    created_at: datetime

    @field_validator("mapping_document")
    @classmethod
    def bound_mapping_document(cls, value: JsonObject | None) -> JsonObject | None:
        _require_json_size(value, maximum=524_288)
        return value


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
    target: ModeledAttributeReference
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
    status: MappingStatus
    is_locked: bool


class MappingAttributeDetail(MappingAttributeSummary):
    parent_object_mapping: ParentObjectMappingReference
    mapping_document: JsonObject | None = None
    output_template: OutputTemplateProvenance | None = None
    created_at: datetime

    @field_validator("mapping_document")
    @classmethod
    def bound_mapping_document(cls, value: JsonObject | None) -> JsonObject | None:
        _require_json_size(value, maximum=65_536)
        return value


class MappingAttributeNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_attribute_not_found",
            message="The requested Attribute Mapping was not found.",
        )


def _require_json_size(value: JsonObject | None, *, maximum: int) -> None:
    if (
        value is not None
        and len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        )
        > maximum
    ):
        raise ValueError("Mapping document is too large")
