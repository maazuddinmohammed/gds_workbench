"""Active Model Scope read contracts."""

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    normalize_natural_key_value,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gds_workbench_api.features.metadata.contracts import ObjectAttribute

type ZoneCode = Literal["source", "bronze", "silver", "gold"]


class ModelScopeObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_scope_id: int = Field(gt=0)
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
    zone_code: ZoneCode
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    attribute_count: int = Field(ge=0)
    is_bronze_source_eligible: bool
    is_dimensional_source_eligible: bool
    is_logical_mapping_target_eligible: bool
    is_dimensional_mapping_target_eligible: bool
    created_at: datetime
    updated_at: datetime


class ModelScopePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[ModelScopeObject, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ModelScopeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
    zone_code: ZoneCode
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    attribute_count: int = Field(ge=0)
    is_in_active_scope: bool


class ModelScopeCandidatePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[ModelScopeCandidate, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ModelScopeDetail(ModelScopeObject):
    attributes: tuple[ObjectAttribute, ...] = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_attribute_count(self) -> ModelScopeDetail:
        if self.attribute_count != len(self.attributes):
            raise ValueError("attribute_count must match the returned Attributes")
        return self


class ModelScopeObjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_scope_object_not_found",
            message="The requested active Model Scope Object was not found.",
        )


class ModelScopeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: ZoneCode | None = None
    system_code: str | None = Field(default=None, max_length=100)
    source_tenant_code: str | None = Field(default=None, max_length=100)
    object_name: str | None = Field(default=None, max_length=400)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator(
        "zone",
        "system_code",
        "source_tenant_code",
        "object_name",
        mode="before",
    )
    @classmethod
    def normalize_filter(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        if not isinstance(info.field_name, str):
            raise ValueError("filter field is invalid")
        field = "zone_code" if info.field_name == "zone" else info.field_name
        normalized = normalize_natural_key_value(field, value)
        if not isinstance(normalized, str) or not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized
