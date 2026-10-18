"""Bounded HTTP contracts for Project Context groups and records."""

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.context_safety import (
    CONTEXT_RECORD_TEXT_MAX_CHARACTERS,
    CONTEXT_SOURCE_REFERENCE_MAX_BYTES,
)
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import ContextRecordId
from pydantic import BaseModel, ConfigDict, Field, field_validator

type ContextStatus = Literal["active", "inactive", "deprecated"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ContextType(ContractModel):
    context_type_id: int = Field(gt=0)
    context_type_name: str = Field(min_length=1, max_length=200)
    context_type_description: str | None = Field(default=None, max_length=2000)


class ContextTypeCollection(ContractModel):
    items: tuple[ContextType, ...]


class SourceSystemReference(ContractModel):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)


class ContextSourceSystemPage(ContractModel):
    items: tuple[SourceSystemReference, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ContextGroupFilters(ContractModel):
    context_type_id: int | None = Field(default=None, gt=0)
    source_system_id: int | None = Field(default=None, gt=0)
    active: bool | None = None
    name_prefix: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name_prefix", mode="before")
    @classmethod
    def normalize_name_prefix(cls, value: object) -> object:
        return value.strip(" ").lower() if isinstance(value, str) else value


class ContextRecordFilters(ContractModel):
    group_id: int | None = Field(default=None, gt=0)
    context_type_id: int | None = Field(default=None, gt=0)
    source_system_id: int | None = Field(default=None, gt=0)
    status: ContextStatus | None = None
    locked: bool | None = None
    text_search: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("text_search", mode="before")
    @classmethod
    def normalize_text_search(cls, value: object) -> object:
        return value.strip(" ").lower() if isinstance(value, str) else value


class ContextGroupReference(ContractModel):
    context_group_id: int = Field(gt=0)
    context_group_name: str = Field(min_length=1, max_length=255)
    context_type: ContextType
    source_system: SourceSystemReference | None = None
    is_active: bool


class ContextGroupSummary(ContextGroupReference):
    record_count: int = Field(ge=0)
    active_record_count: int = Field(ge=0)
    locked_record_count: int = Field(ge=0)
    updated_at: datetime


class ContextGroupDetail(ContextGroupSummary):
    context_group_description: str | None = Field(default=None, max_length=2000)
    created_at: datetime


class ContextGroupPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[ContextGroupSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ContextRecordSummary(ContractModel):
    context_record_id: ContextRecordId
    group: ContextGroupReference
    context_text_preview: str = Field(max_length=500)
    text_truncated: bool
    source_reference_preview: str | None = Field(max_length=500)
    source_reference_truncated: bool
    status: ContextStatus
    is_locked: bool
    updated_at: datetime


class ContextRecordDetail(ContextRecordSummary):
    context_text: str = Field(min_length=1, max_length=CONTEXT_RECORD_TEXT_MAX_CHARACTERS)
    source_reference: str | None = Field(
        default=None, max_length=CONTEXT_SOURCE_REFERENCE_MAX_BYTES
    )
    created_at: datetime

    @field_validator("source_reference")
    @classmethod
    def bound_source_reference(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > CONTEXT_SOURCE_REFERENCE_MAX_BYTES:
            raise ValueError("Context source reference is too large")
        return value


class ContextRecordPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[ContextRecordSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ContextGroupNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__("context_group_not_found", "The requested Context Group was not found.")


class ContextRecordNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__("context_record_not_found", "The requested Context Record was not found.")


class ContextPayloadNotSafeError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__("context_payload_not_safe", "The Context detail exceeds its safe bounds.")


class ContextRecordReference(ContractModel):
    context_record_id: ContextRecordId
    context_group_name: str = Field(min_length=1, max_length=255)
    context_type_name: str = Field(min_length=1, max_length=200)
    context_text: str = Field(min_length=1, max_length=CONTEXT_RECORD_TEXT_MAX_CHARACTERS)
    source_reference: str | None
    status: ContextStatus
