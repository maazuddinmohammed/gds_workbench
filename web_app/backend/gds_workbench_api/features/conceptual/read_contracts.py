"""Tenant-owned Conceptual Object and Relationship review contracts."""

from datetime import datetime
from typing import Annotated, Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

type ConceptualStatus = Literal["active", "inactive", "deprecated"]
type Confidence = Literal["low", "medium", "high"]
type ConceptualCardinality = Literal[
    "one_to_one",
    "one_to_many",
    "many_to_one",
    "many_to_many",
    "unknown",
]
type ConceptualAlias = Annotated[str, Field(min_length=1, max_length=255)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ConceptualFilters(ContractModel):
    status: ConceptualStatus | None = None
    locked: bool | None = None
    name_exact: str | None = Field(default=None, min_length=1, max_length=255)
    name_prefix: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("status", "name_exact", "name_prefix", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip(" ").lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized

    @model_validator(mode="after")
    def reject_ambiguous_name_filter(self) -> Self:
        if self.name_exact is not None and self.name_prefix is not None:
            raise ValueError("name_exact and name_prefix are mutually exclusive")
        return self


class ConceptualObjectSummary(ContractModel):
    conceptual_object_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    conceptual_object_name: str = Field(min_length=1, max_length=255)
    conceptual_object_type: str = Field(min_length=1, max_length=100)
    conceptual_object_confidence: Confidence
    conceptual_object_status: ConceptualStatus
    conceptual_object_is_locked: bool
    updated_at: datetime


class ConceptualObjectPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[ConceptualObjectSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ConceptualRelationshipSummary(ContractModel):
    conceptual_relationship_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    from_conceptual_object_id: int = Field(gt=0)
    from_conceptual_object_name: str = Field(min_length=1, max_length=255)
    to_conceptual_object_id: int = Field(gt=0)
    to_conceptual_object_name: str = Field(min_length=1, max_length=255)
    conceptual_relationship_name: str = Field(min_length=1, max_length=255)
    conceptual_relationship_type: str = Field(min_length=1, max_length=100)
    conceptual_relationship_cardinality: ConceptualCardinality
    conceptual_relationship_confidence: Confidence
    conceptual_relationship_status: ConceptualStatus
    conceptual_relationship_is_locked: bool
    updated_at: datetime


class ConceptualRelationshipPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[ConceptualRelationshipSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class PhysicalObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)


class AssertionRecordReference(ContractModel):
    modeling_assertion_record_id: int = Field(gt=0)
    modeling_assertion_record_key: str = Field(min_length=1, max_length=100)
    modeling_assertion_document_name: str = Field(min_length=1, max_length=255)
    modeling_assertion_record_type: str = Field(min_length=1, max_length=100)
    modeling_assertion_text: str = Field(min_length=1)
    modeling_assertion_confidence: Confidence | None = None
    modeling_assertion_record_status: ConceptualStatus


class ConceptualSupportBase(ContractModel):
    conceptual_support_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    support_role: str | None = Field(default=None, min_length=1, max_length=255)
    support_reason: str = Field(min_length=1)
    support_reason_detail: str | None = Field(default=None, min_length=1)
    support_confidence: Confidence
    support_status: ConceptualStatus
    support_is_locked: bool
    created_at: datetime
    updated_at: datetime


class ConceptualObjectSupport(ConceptualSupportBase):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectReference


class ConceptualAssertionSupport(ConceptualSupportBase):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordReference


type ConceptualSupport = Annotated[
    ConceptualObjectSupport | ConceptualAssertionSupport,
    Field(discriminator="support_source_type"),
]


class ConceptualObjectDetail(ConceptualObjectSummary):
    conceptual_object_definition: str = Field(min_length=1)
    conceptual_object_grain: str = Field(min_length=1)
    conceptual_object_aliases: tuple[ConceptualAlias, ...] = Field(max_length=1000)
    created_at: datetime
    supports: tuple[ConceptualSupport, ...] = Field(max_length=2000)


class ConceptualRelationshipDetail(ConceptualRelationshipSummary):
    conceptual_relationship_definition: str = Field(min_length=1)
    conceptual_relationship_basis: str = Field(min_length=1)
    conceptual_relationship_cardinality_basis: str = Field(min_length=1)
    created_at: datetime
    supports: tuple[ConceptualSupport, ...] = Field(max_length=2000)


class ConceptualObjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_object_not_found",
            message="The requested Conceptual Object was not found.",
        )


class ConceptualRelationshipNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_relationship_not_found",
            message="The requested Conceptual Relationship was not found.",
        )


class ConceptualSupportLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_support_limit_exceeded",
            message="The Conceptual artifact has too many Support rows to return safely.",
        )


class ConceptualListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ConceptualStatus | None = None
    locked: bool | None = None
    name_exact: str | None = Field(default=None, max_length=255)
    name_prefix: str | None = Field(default=None, max_length=255)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("status", "name_exact", "name_prefix", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip(" ").lower()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        return normalized

    @model_validator(mode="after")
    def reject_ambiguous_name_filter(self) -> Self:
        if self.name_exact is not None and self.name_prefix is not None:
            raise ValueError("name_exact and name_prefix are mutually exclusive")
        return self
