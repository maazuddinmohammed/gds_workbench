"""Public contracts for tenant-owned Modeling Assertion review reads."""

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.assertion_safety import (
    ASSERTION_DOCUMENT_METADATA_MAX_BYTES,
    ASSERTION_RECORD_DETAILS_MAX_BYTES,
    ASSERTION_RECORD_SOURCE_LOCATION_MAX_BYTES,
    ASSERTION_RECORD_TEXT_MAX_CHARACTERS,
    validate_assertion_json,
)
from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

type AssertionStatus = Literal["active", "needs_review", "inactive", "deprecated"]
type ApplicableLayer = Literal[
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
]
type Confidence = Literal["low", "medium", "high"]
type JsonObject = dict[str, JsonValue]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceTenantReference(ContractModel):
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)


class SourceSystemReference(ContractModel):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)


class AssertionDocumentFilters(ContractModel):
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None
    name_prefix: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("source_system_code", "name_prefix", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        return _normalize_filter_text(value, info.field_name)


class AssertionRecordFilters(ContractModel):
    document_id: int | None = Field(default=None, gt=0)
    document_name: str | None = Field(default=None, min_length=1, max_length=255)
    source_system_id: int | None = Field(default=None, gt=0)
    source_system_code: str | None = Field(default=None, min_length=1, max_length=100)
    status: AssertionStatus | None = None
    locked: bool | None = None
    applicable_layer: ApplicableLayer | None = None
    key_prefix: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator(
        "document_name",
        "source_system_code",
        "status",
        "applicable_layer",
        "key_prefix",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        return _normalize_filter_text(value, info.field_name)


class AssertionDocumentSummary(ContractModel):
    modeling_assertion_document_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    modeling_assertion_document_name: str = Field(min_length=1, max_length=255)
    modeling_assertion_document_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    source_tenant: SourceTenantReference | None = None
    source_system: SourceSystemReference | None = None
    is_active: bool
    record_count: int = Field(ge=0)
    active_record_count: int = Field(ge=0)
    needs_review_record_count: int = Field(ge=0)
    locked_record_count: int = Field(ge=0)
    updated_at: datetime


class AssertionDocumentPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[AssertionDocumentSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class AssertionDocumentDetail(AssertionDocumentSummary):
    modeling_assertion_file_pattern: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    modeling_assertion_document_description: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )
    modeling_assertion_document_metadata: JsonObject
    agent_run_id: str | None = Field(default=None, min_length=1, max_length=500)
    created_at: datetime

    @field_validator("modeling_assertion_document_metadata")
    @classmethod
    def bound_metadata(cls, value: JsonObject) -> JsonObject:
        validate_safe_json(
            value,
            maximum_bytes=ASSERTION_DOCUMENT_METADATA_MAX_BYTES,
            label="Assertion Document metadata",
        )
        return value


class AssertionDocumentReference(ContractModel):
    modeling_assertion_document_id: int = Field(gt=0)
    modeling_assertion_document_name: str = Field(min_length=1, max_length=255)
    modeling_assertion_document_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    source_tenant: SourceTenantReference | None = None
    source_system: SourceSystemReference | None = None
    is_active: bool


class AssertionRecordSummary(ContractModel):
    modeling_assertion_record_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    document: AssertionDocumentReference
    modeling_assertion_record_key: str = Field(min_length=1, max_length=100)
    modeling_assertion_record_type: str = Field(min_length=1, max_length=100)
    modeling_assertion_applicable_layers: tuple[ApplicableLayer, ...] = Field(max_length=5)
    modeling_assertion_confidence: Confidence | None = None
    modeling_assertion_record_status: AssertionStatus
    modeling_assertion_record_is_locked: bool
    updated_at: datetime


class AssertionRecordPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[AssertionRecordSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class AssertionRecordDetail(AssertionRecordSummary):
    modeling_assertion_text: str = Field(
        min_length=1,
        max_length=ASSERTION_RECORD_TEXT_MAX_CHARACTERS,
    )
    modeling_assertion_details: JsonObject
    modeling_assertion_source_location: JsonObject | None = None
    agent_run_id: str | None = Field(default=None, min_length=1, max_length=500)
    created_at: datetime

    @field_validator("modeling_assertion_details")
    @classmethod
    def bound_details(cls, value: JsonObject) -> JsonObject:
        validate_safe_json(
            value,
            maximum_bytes=ASSERTION_RECORD_DETAILS_MAX_BYTES,
            label="Assertion Record details",
        )
        return value

    @field_validator("modeling_assertion_source_location")
    @classmethod
    def bound_source_location(cls, value: JsonObject | None) -> JsonObject | None:
        if value is not None:
            validate_safe_json(
                value,
                maximum_bytes=ASSERTION_RECORD_SOURCE_LOCATION_MAX_BYTES,
                label="Assertion Record source location",
            )
        return value


class AssertionDocumentNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="assertion_document_not_found",
            message="The requested Assertion Document was not found.",
        )


class AssertionRecordNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="assertion_record_not_found",
            message="The requested Assertion Record was not found.",
        )


class AssertionPayloadNotSafeError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="assertion_payload_not_safe",
            message="The Assertion detail contains content that cannot be returned safely.",
        )


def validate_safe_json(
    value: JsonObject,
    *,
    maximum_bytes: int,
    label: str,
) -> None:
    validate_assertion_json(
        value,
        maximum_bytes=maximum_bytes,
        label=label,
    )


def _normalize_filter_text(value: object, field_name: str | None) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip(" ").lower()
    if not normalized:
        raise ValueError(f"{field_name or 'filter'} must be nonblank")
    return normalized
