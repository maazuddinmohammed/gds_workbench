"""Tenant-owned Subject Area review contracts."""

from datetime import datetime

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SubjectAreaSummary(ContractModel):
    subject_area_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    subject_area_name: str = Field(min_length=1, max_length=255)
    subject_area_definition: str = Field(min_length=1)
    subject_area_is_active: bool
    subject_area_is_locked: bool
    table_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    shared_table_count: int = Field(ge=0)
    updated_at: datetime


class SubjectAreaPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    scope_table_count: int = Field(ge=0)
    unassigned_table_count: int = Field(ge=0)
    items: tuple[SubjectAreaSummary, ...] = Field(max_length=1_000)


class SubjectAreaMembership(ContractModel):
    subject_area_id: int = Field(gt=0)
    subject_area_name: str = Field(min_length=1, max_length=255)
    subject_area_table_id: int = Field(gt=0)
    subject_area_table_is_locked: bool


class ScopeTable(ContractModel):
    """One active Input Scope table with the active areas it belongs to."""

    object_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_description: str | None = None
    zone_code: str = Field(min_length=1, max_length=100)
    column_count: int = Field(ge=0)
    areas: tuple[SubjectAreaMembership, ...] = Field(max_length=1_000)


class ScopeTablePage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[ScopeTable, ...] = Field(max_length=10_000)


class SubjectAreaDetail(SubjectAreaSummary):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    tables: tuple[ScopeTable, ...] = Field(max_length=10_000)


class SubjectAreaNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="subject_area_not_found",
            message="The Subject Area was not found in this Project.",
        )


class ScopeTableLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="scope_table_limit_exceeded",
            message="This Project has more Input Scope tables than one review page can show.",
        )


__all__ = [
    "ContractModel",
    "ScopeTable",
    "ScopeTableLimitExceededError",
    "ScopeTablePage",
    "SubjectAreaDetail",
    "SubjectAreaMembership",
    "SubjectAreaNotFoundError",
    "SubjectAreaPage",
    "SubjectAreaSummary",
]
