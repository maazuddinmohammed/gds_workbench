"""Tenant-owned Mapping read contracts aligned with binding persistence."""

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


class MappingDependencyFilters(ContractModel):
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


class MappingTargetSummary(ContractModel):
    object_id: int = Field(gt=0)
    connection_id: int = Field(gt=0)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone_code: Literal["silver", "gold"]


class MappingTargetPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[MappingTargetSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class MappingObjectSummary(ContractModel):
    mapping_object_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    target: PhysicalObjectReference
    source: ModeledEntityReference
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
