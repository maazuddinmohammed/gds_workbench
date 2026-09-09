"""Read contracts for profiled Objects and Attribute Profiles."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.snapshots.metadata import normalize_natural_key_value
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class ReviewContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProfilingObjectFilters(ReviewContract):
    object_id: int | None = Field(default=None, gt=0)
    source_tenant_code: str | None = Field(default=None, max_length=100)
    system_code: str | None = Field(default=None, max_length=100)
    object_schema: str | None = Field(default=None, max_length=400)
    object_name: str | None = Field(default=None, max_length=400)

    @field_validator(
        "source_tenant_code",
        "system_code",
        "object_schema",
        "object_name",
        mode="before",
    )
    @classmethod
    def normalize_filter(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        if not isinstance(info.field_name, str):
            raise ValueError("filter field is invalid")
        normalized = normalize_natural_key_value(info.field_name, value)
        if not isinstance(normalized, str) or not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized


class ProfilingObjectLedgerItem(ReviewContract):
    object_id: int = Field(gt=0)
    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    profiled_attribute_count: int = Field(ge=1)
    last_profiled_at: datetime


class ProfilingObjectPage(ReviewContract):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[ProfilingObjectLedgerItem, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ProfileWorkflowProvenance(ReviewContract):
    agent_run_id: str | None = Field(default=None, max_length=500)
    workflow_run_id: int | None = Field(default=None, gt=0)


class AttributeProfile(ReviewContract):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_ordinal_position: int = Field(gt=0)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    source_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    blank_count: int | None = Field(default=None, ge=0)
    distinct_count: int | None = Field(default=None, ge=0)
    min_data_length: int | None = Field(default=None, ge=0)
    max_data_length: int | None = Field(default=None, ge=0)
    avg_data_length: Decimal | None = Field(default=None, ge=0)
    percent_populated: Decimal | None = Field(default=None, ge=0, le=100)
    percent_duplicates: Decimal | None = Field(default=None, ge=0, le=100)
    percent_null: Decimal | None = Field(default=None, ge=0, le=100)
    percent_blank: Decimal | None = Field(default=None, ge=0, le=100)
    percent_distinct: Decimal | None = Field(default=None, ge=0, le=100)
    provenance: ProfileWorkflowProvenance
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_metrics(self) -> AttributeProfile:
        if self.non_null_count + self.null_count != self.row_count:
            raise ValueError("non-null and null counts must equal row count")
        if self.blank_count is not None and self.blank_count > self.non_null_count:
            raise ValueError("blank count cannot exceed non-null count")
        if self.distinct_count is not None and self.distinct_count > self.non_null_count:
            raise ValueError("distinct count cannot exceed non-null count")
        if (
            self.min_data_length is not None
            and self.max_data_length is not None
            and self.min_data_length > self.max_data_length
        ):
            raise ValueError("minimum length cannot exceed maximum length")
        return self


class ProfilingObjectDetail(ProfilingObjectLedgerItem):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    attribute_profiles: tuple[AttributeProfile, ...] = Field(max_length=2000)
    profiles_truncated: bool

    @model_validator(mode="after")
    def validate_returned_profile_count(self) -> ProfilingObjectDetail:
        returned_count = len(self.attribute_profiles)
        if returned_count > self.profiled_attribute_count:
            raise ValueError("returned Profiles cannot exceed the Profile count")
        if not self.profiles_truncated and returned_count != self.profiled_attribute_count:
            raise ValueError("complete Profile detail must return every Profile")
        return self


class ProfilingObjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="profiling_object_not_found",
            message="The requested profiled Object was not found in the active Model.",
        )
