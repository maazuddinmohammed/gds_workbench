"""Tenant-owned normalized Logical model review contracts."""

from datetime import datetime
from typing import Annotated, Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

MAX_DETAIL_ROWS = 2000

type ModeledStatus = Literal["active", "inactive", "deprecated"]
type Confidence = Literal["low", "medium", "high"]
type Cardinality = Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModeledFilters(ContractModel):
    status: ModeledStatus | None = None
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


class LogicalEntityFilters(ModeledFilters):
    logical_submodel_id: int | None = Field(default=None, gt=0)


# Layer-specific public name retained for callers using the earlier name.
LogicalFilters = LogicalEntityFilters


class LogicalEntitySummary(ContractModel):
    logical_entity_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    logical_entity_name: str = Field(min_length=1, max_length=255)
    logical_entity_type: Literal[
        "core",
        "reference",
        "transaction",
        "event",
        "bridge",
        "history",
        "snapshot",
        "association",
        "aggregate",
        "other",
    ]
    logical_entity_dependency_order: int = Field(ge=0)
    logical_entity_confidence: Confidence
    logical_entity_status: ModeledStatus
    logical_entity_is_locked: bool
    updated_at: datetime


class LogicalEntityPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[LogicalEntitySummary, ...] = Field(max_length=200)
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
    modeling_assertion_record_status: ModeledStatus


class LogicalSubmodelMembership(ContractModel):
    logical_entity_submodel_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    logical_submodel_id: int = Field(gt=0)
    logical_submodel_name: str = Field(min_length=1, max_length=255)
    membership_status: ModeledStatus
    membership_is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalEntitySourceBase(ContractModel):
    logical_entity_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    source_order: int | None = Field(default=None, gt=0)
    rationale: str = Field(min_length=1)
    status: ModeledStatus
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalObjectSource(LogicalEntitySourceBase):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectReference


class LogicalAssertionSource(LogicalEntitySourceBase):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordReference


type LogicalEntitySource = Annotated[
    LogicalObjectSource | LogicalAssertionSource,
    Field(discriminator="support_source_type"),
]


class LogicalEntityDetail(LogicalEntitySummary):
    logical_entity_definition: str = Field(min_length=1)
    logical_entity_type_detail: str | None = Field(default=None, min_length=1)
    logical_entity_grain: str = Field(min_length=1)
    created_at: datetime
    submodels: tuple[LogicalSubmodelMembership, ...] = Field(max_length=MAX_DETAIL_ROWS)
    sources: tuple[LogicalEntitySource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class PhysicalAttributeReference(PhysicalObjectReference):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)


class LogicalAttributeFilters(ModeledFilters):
    logical_entity_id: int | None = Field(default=None, gt=0)


class LogicalAttributeSummary(ContractModel):
    logical_attribute_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    logical_entity_id: int = Field(gt=0)
    logical_entity_name: str = Field(min_length=1, max_length=255)
    logical_attribute_name: str = Field(min_length=1, max_length=255)
    logical_attribute_data_type: str = Field(min_length=1, max_length=100)
    logical_attribute_is_nullable: bool
    logical_attribute_is_primary_key: bool
    logical_attribute_is_natural_key: bool
    logical_attribute_is_surrogate_key: bool
    logical_attribute_ordinal_position: int = Field(gt=0)
    logical_attribute_is_audit_column: bool
    logical_attribute_status: ModeledStatus
    logical_attribute_is_locked: bool
    updated_at: datetime


class LogicalAttributePage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[LogicalAttributeSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class LogicalAttributeSourceBase(ContractModel):
    logical_attribute_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    source_order: int | None = Field(default=None, gt=0)
    rationale: str = Field(min_length=1)
    status: ModeledStatus
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalAttributePhysicalSource(LogicalAttributeSourceBase):
    logical_entity_source_mapping_id: int = Field(gt=0)
    support_source_type: Literal["attribute"]
    source_attribute: PhysicalAttributeReference


class LogicalAttributeAssertionSource(LogicalAttributeSourceBase):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordReference


type LogicalAttributeSource = Annotated[
    LogicalAttributePhysicalSource | LogicalAttributeAssertionSource,
    Field(discriminator="support_source_type"),
]


class LogicalAttributeDetail(LogicalAttributeSummary):
    logical_attribute_definition: str = Field(min_length=1)
    created_at: datetime
    sources: tuple[LogicalAttributeSource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class LogicalRelationshipFilters(ModeledFilters):
    logical_entity_id: int | None = Field(default=None, gt=0)


class LogicalRelationshipSummary(ContractModel):
    logical_relationship_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    from_logical_entity_id: int = Field(gt=0)
    from_logical_entity_name: str = Field(min_length=1, max_length=255)
    from_logical_attribute_id: int = Field(gt=0)
    from_logical_attribute_name: str = Field(min_length=1, max_length=255)
    to_logical_entity_id: int = Field(gt=0)
    to_logical_entity_name: str = Field(min_length=1, max_length=255)
    to_logical_attribute_id: int = Field(gt=0)
    to_logical_attribute_name: str = Field(min_length=1, max_length=255)
    logical_relationship_name: str = Field(min_length=1, max_length=255)
    logical_relationship_cardinality: Cardinality
    logical_relationship_confidence: Confidence
    logical_relationship_status: ModeledStatus
    logical_relationship_is_locked: bool
    updated_at: datetime


class LogicalRelationshipPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[LogicalRelationshipSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class LogicalRelationshipDetail(LogicalRelationshipSummary):
    logical_relationship_definition: str = Field(min_length=1)
    logical_relationship_basis: str = Field(min_length=1)
    logical_relationship_cardinality_basis: str = Field(min_length=1)
    created_at: datetime


class LogicalSubmodelSummary(ContractModel):
    logical_submodel_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    logical_submodel_name: str = Field(min_length=1, max_length=255)
    logical_submodel_status: ModeledStatus
    logical_submodel_is_locked: bool
    entity_count: int = Field(ge=0)
    updated_at: datetime


class LogicalSubmodelPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[LogicalSubmodelSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class LogicalSubmodelEntityMembership(ContractModel):
    logical_entity_submodel_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    logical_entity_id: int = Field(gt=0)
    logical_entity_name: str = Field(min_length=1, max_length=255)
    logical_entity_type: Literal[
        "core",
        "reference",
        "transaction",
        "event",
        "bridge",
        "history",
        "snapshot",
        "association",
        "aggregate",
        "other",
    ]
    logical_entity_status: ModeledStatus
    membership_status: ModeledStatus
    membership_is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalSubmodelDetail(LogicalSubmodelSummary):
    logical_submodel_definition: str = Field(min_length=1)
    created_at: datetime
    entities: tuple[LogicalSubmodelEntityMembership, ...] = Field(max_length=MAX_DETAIL_ROWS)


class LogicalEntityNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_entity_not_found",
            message="The requested Logical Entity was not found.",
        )


class LogicalAttributeNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_attribute_not_found",
            message="The requested Logical Attribute was not found.",
        )


class LogicalRelationshipNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_relationship_not_found",
            message="The requested Logical Relationship was not found.",
        )


class LogicalSubmodelNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_submodel_not_found",
            message="The requested Logical Submodel was not found.",
        )


class LogicalDetailLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_detail_limit_exceeded",
            message="The Logical artifact has too many related rows to return safely.",
        )


class ModeledListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ModeledStatus | None = None
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


class LogicalAttributeListQuery(ModeledListQuery):
    logical_entity_id: int | None = Field(default=None, gt=0)


class LogicalEntityListQuery(ModeledListQuery):
    logical_submodel_id: int | None = Field(default=None, gt=0)


class LogicalRelationshipListQuery(ModeledListQuery):
    logical_entity_id: int | None = Field(default=None, gt=0)
