"""Tenant-owned normalized Logical model review contracts."""

from datetime import datetime
from typing import Annotated, Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from gds_workbench_api.features.context.contracts import ContextRecordReference

MAX_DETAIL_ROWS = 2000

# Model relationships point child -> parent, so only these two remain.
type ModelCardinality = Literal["many_to_one", "one_to_one"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModeledFilters(ContractModel):
    active: bool | None = None
    locked: bool | None = None
    name_exact: str | None = Field(default=None, min_length=1, max_length=255)
    name_prefix: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name_exact", "name_prefix", mode="before")
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
    # Entities with an active Object source among the area's active member Objects.
    subject_area_id: int | None = Field(default=None, gt=0)


# Layer-specific public name retained for callers using the earlier name.
LogicalFilters = LogicalEntityFilters


class LogicalEntitySummary(ContractModel):
    logical_entity_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    logical_entity_schema_name: str = Field(min_length=1, max_length=400)
    logical_entity_name: str = Field(min_length=1, max_length=255)
    # A code from reference.logical_entity_type; the list can grow without a release.
    logical_entity_type: str = Field(min_length=1, max_length=50)
    logical_entity_dependency_order: int = Field(ge=0)
    logical_entity_is_active: bool
    logical_entity_is_locked: bool
    updated_at: datetime


class LogicalEntityPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[LogicalEntitySummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class PhysicalObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)


class EntitySubjectArea(ContractModel):
    """An active Subject Area reached through the Entity's active Object sources."""

    subject_area_id: int = Field(gt=0)
    subject_area_name: str = Field(min_length=1, max_length=255)


class SubjectAreaBuild(ContractModel):
    """The area's newest Build in one layer that decides its state.

    A cancelled Build, or one whose draft was discarded, superseded or expired, is skipped,
    so the Build before it decides. `at` is when that Build started (running), its draft
    was validated (draft_waiting), its draft was applied or it needed no change (applied),
    or it failed.
    """

    state: Literal["not_built", "running", "draft_waiting", "applied", "failed"]
    workflow_run_id: int | None = Field(default=None, gt=0)
    at: datetime | None = None


class ModelSubjectArea(ContractModel):
    """An active Subject Area with how much of it one layer models, and its last Build."""

    subject_area_id: int = Field(gt=0)
    subject_area_name: str = Field(min_length=1, max_length=255)
    subject_area_definition: str = Field(min_length=1)
    table_count: int = Field(ge=0)
    # Member Objects that are also members of another active area.
    shared_table_count: int = Field(ge=0)
    # Member Objects that reach an active Entity of this layer.
    modeled_table_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    build: SubjectAreaBuild


class WaitingDraft(ContractModel):
    """The layer's newest unexpired Build or Optimize draft still waiting for Apply."""

    workflow_run_id: int = Field(gt=0)
    workflow_operation: Literal["build", "optimize"]


class ModelSubjectAreaPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[ModelSubjectArea, ...] = Field(max_length=1_000)
    waiting_draft: WaitingDraft | None = None


class LogicalEntitySourceBase(ContractModel):
    logical_entity_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    rationale: str | None = Field(default=None, min_length=1)
    is_active: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalObjectSource(LogicalEntitySourceBase):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectReference


class LogicalContextSource(LogicalEntitySourceBase):
    support_source_type: Literal["context_record"]
    context_record: ContextRecordReference


type LogicalEntitySource = Annotated[
    LogicalObjectSource | LogicalContextSource,
    Field(discriminator="support_source_type"),
]


class LogicalEntityDetail(LogicalEntitySummary):
    logical_entity_definition: str = Field(min_length=1)
    logical_entity_grain: str = Field(min_length=1)
    created_at: datetime
    subject_areas: tuple[EntitySubjectArea, ...] = Field(max_length=MAX_DETAIL_ROWS)
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
    logical_entity_schema_name: str = Field(min_length=1, max_length=400)
    logical_entity_name: str = Field(min_length=1, max_length=255)
    logical_attribute_name: str = Field(min_length=1, max_length=255)
    logical_attribute_data_type: str = Field(min_length=1, max_length=100)
    logical_attribute_is_nullable: bool
    logical_attribute_is_natural_key: bool
    logical_attribute_is_surrogate_key: bool
    logical_attribute_ordinal_position: int = Field(gt=0)
    logical_attribute_is_audit_column: bool
    logical_attribute_is_active: bool
    logical_attribute_is_locked: bool
    updated_at: datetime


class LogicalAttributePage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[LogicalAttributeSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class LogicalAttributeSourceBase(ContractModel):
    logical_attribute_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    rationale: str | None = Field(default=None, min_length=1)
    is_active: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalAttributePhysicalSource(LogicalAttributeSourceBase):
    logical_entity_source_mapping_id: int = Field(gt=0)
    support_source_type: Literal["attribute"]
    source_attribute: PhysicalAttributeReference


class LogicalAttributeContextSource(LogicalAttributeSourceBase):
    support_source_type: Literal["context_record"]
    context_record: ContextRecordReference


type LogicalAttributeSource = Annotated[
    LogicalAttributePhysicalSource | LogicalAttributeContextSource,
    Field(discriminator="support_source_type"),
]


class LogicalAttributeDetail(LogicalAttributeSummary):
    logical_attribute_definition: str = Field(min_length=1)
    created_at: datetime
    sources: tuple[LogicalAttributeSource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class LogicalRelationshipFilters(ModeledFilters):
    logical_entity_id: int | None = Field(default=None, gt=0)


class LogicalRelationshipSummary(ContractModel):
    """Child -> parent: the from Attribute is the foreign key, to is the parent's key.

    Relationships have no name; name filters match the from (foreign-key) Attribute.
    """

    logical_relationship_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    from_logical_entity_id: int = Field(gt=0)
    from_logical_entity_schema_name: str = Field(min_length=1, max_length=400)
    from_logical_entity_name: str = Field(min_length=1, max_length=255)
    from_logical_attribute_id: int = Field(gt=0)
    from_logical_attribute_name: str = Field(min_length=1, max_length=255)
    to_logical_entity_id: int = Field(gt=0)
    to_logical_entity_schema_name: str = Field(min_length=1, max_length=400)
    to_logical_entity_name: str = Field(min_length=1, max_length=255)
    to_logical_attribute_id: int = Field(gt=0)
    to_logical_attribute_name: str = Field(min_length=1, max_length=255)
    logical_relationship_cardinality: ModelCardinality
    logical_relationship_is_active: bool
    logical_relationship_is_locked: bool
    updated_at: datetime


class LogicalRelationshipPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[LogicalRelationshipSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class LogicalRelationshipDetail(LogicalRelationshipSummary):
    logical_relationship_basis: str = Field(min_length=1)
    created_at: datetime


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


class LogicalDetailLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_detail_limit_exceeded",
            message="The Logical artifact has too many related rows to return safely.",
        )


class ModeledListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool | None = None
    locked: bool | None = None
    name_exact: str | None = Field(default=None, max_length=255)
    name_prefix: str | None = Field(default=None, max_length=255)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("name_exact", "name_prefix", mode="before")
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
    subject_area_id: int | None = Field(default=None, gt=0)


class LogicalRelationshipListQuery(ModeledListQuery):
    logical_entity_id: int | None = Field(default=None, gt=0)
