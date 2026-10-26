"""Tenant-owned normalized Dimensional model review contracts."""

from datetime import datetime
from typing import Annotated, Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import Field

from gds_workbench_api.features.logical import (
    ContextRecordReference,
    ContractModel,
    EntitySubjectArea,
    ModeledFilters,
    ModeledListQuery,
)

MAX_DETAIL_ROWS = 2000

# Layer-specific public name; kept identical to the shared normalized filter contract.
DimensionalFilters = ModeledFilters


class DimensionalObjectFilters(ModeledFilters):
    # Entities whose active Logical sources have an active Object among the area's
    # active member Objects.
    subject_area_id: int | None = Field(default=None, gt=0)


class DimensionalObjectSummary(ContractModel):
    dimensional_entity_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    dimensional_entity_schema_name: str = Field(min_length=1, max_length=400)
    dimensional_entity_name: str = Field(min_length=1, max_length=255)
    dimensional_entity_type: Literal["fact", "dimension", "bridge"]
    # A code from reference.dimensional_fact_type; only facts have one.
    dimensional_fact_type: str | None = Field(default=None, min_length=1, max_length=50)
    dimensional_entity_dependency_order: int = Field(ge=0)
    dimensional_entity_is_active: bool
    dimensional_entity_is_locked: bool
    updated_at: datetime


class DimensionalObjectPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[DimensionalObjectSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class DimensionalObjectSourceBase(ContractModel):
    dimensional_entity_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    rationale: str | None = Field(default=None, min_length=1)
    is_active: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class LogicalEntityReference(ContractModel):
    logical_entity_id: int = Field(gt=0)
    logical_entity_schema_name: str = Field(min_length=1, max_length=400)
    logical_entity_name: str = Field(min_length=1, max_length=255)


class LogicalAttributeReference(LogicalEntityReference):
    logical_attribute_id: int = Field(gt=0)
    logical_attribute_name: str = Field(min_length=1, max_length=255)


class DimensionalLogicalEntitySource(DimensionalObjectSourceBase):
    support_source_type: Literal["logical_entity"]
    source_logical_entity: LogicalEntityReference


class DimensionalContextSource(DimensionalObjectSourceBase):
    support_source_type: Literal["context_record"]
    context_record: ContextRecordReference


type DimensionalObjectSource = Annotated[
    DimensionalLogicalEntitySource | DimensionalContextSource,
    Field(discriminator="support_source_type"),
]


class DimensionalObjectDetail(DimensionalObjectSummary):
    dimensional_entity_definition: str = Field(min_length=1)
    dimensional_entity_grain_definition: str | None = Field(default=None, min_length=1)
    created_at: datetime
    subject_areas: tuple[EntitySubjectArea, ...] = Field(max_length=MAX_DETAIL_ROWS)
    sources: tuple[DimensionalObjectSource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class DimensionalAttributeFilters(ModeledFilters):
    dimensional_entity_id: int | None = Field(default=None, gt=0)


class DimensionalAttributeSummary(ContractModel):
    dimensional_attribute_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    dimensional_entity_id: int = Field(gt=0)
    dimensional_entity_schema_name: str = Field(min_length=1, max_length=400)
    dimensional_entity_name: str = Field(min_length=1, max_length=255)
    dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    dimensional_attribute_data_type: str = Field(min_length=1, max_length=100)
    dimensional_attribute_is_nullable: bool
    dimensional_attribute_ordinal_position: int = Field(gt=0)
    dimensional_attribute_is_natural_key: bool
    dimensional_attribute_is_surrogate_key: bool
    dimensional_attribute_is_audit_column: bool
    dimensional_attribute_is_active: bool
    dimensional_attribute_is_locked: bool
    updated_at: datetime


class DimensionalAttributePage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[DimensionalAttributeSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class DimensionalAttributeSourceBase(ContractModel):
    dimensional_attribute_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    rationale: str | None = Field(default=None, min_length=1)
    is_active: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class DimensionalAttributeLogicalSource(DimensionalAttributeSourceBase):
    dimensional_entity_source_mapping_id: int = Field(gt=0)
    support_source_type: Literal["logical_attribute"]
    source_logical_attribute: LogicalAttributeReference


class DimensionalAttributeContextSource(DimensionalAttributeSourceBase):
    support_source_type: Literal["context_record"]
    context_record: ContextRecordReference


type DimensionalAttributeSource = Annotated[
    DimensionalAttributeLogicalSource | DimensionalAttributeContextSource,
    Field(discriminator="support_source_type"),
]


class DimensionalAttributeDetail(DimensionalAttributeSummary):
    dimensional_attribute_definition: str = Field(min_length=1)
    created_at: datetime
    sources: tuple[DimensionalAttributeSource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class DimensionalRelationshipFilters(ModeledFilters):
    dimensional_entity_id: int | None = Field(default=None, gt=0)


class DimensionalRelationshipSummary(ContractModel):
    """Child -> parent: a fact, bridge or outrigger foreign key -> the dimension's key.

    Relationships have no name; name filters match the from (foreign-key) Attribute.
    """

    dimensional_relationship_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    from_dimensional_entity_id: int = Field(gt=0)
    from_dimensional_entity_schema_name: str = Field(min_length=1, max_length=400)
    from_dimensional_entity_name: str = Field(min_length=1, max_length=255)
    from_dimensional_attribute_id: int = Field(gt=0)
    from_dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    to_dimensional_entity_id: int = Field(gt=0)
    to_dimensional_entity_schema_name: str = Field(min_length=1, max_length=400)
    to_dimensional_entity_name: str = Field(min_length=1, max_length=255)
    to_dimensional_attribute_id: int = Field(gt=0)
    to_dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    # Set only for role-playing references, such as OrderDate and ShipDate.
    dimensional_relationship_role_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    dimensional_relationship_is_active: bool
    dimensional_relationship_is_locked: bool
    updated_at: datetime


class DimensionalRelationshipPage(ContractModel):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[DimensionalRelationshipSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class DimensionalRelationshipDetail(DimensionalRelationshipSummary):
    # Needed only when the link does not follow a Logical Relationship.
    dimensional_relationship_basis: str | None = Field(default=None, min_length=1)
    created_at: datetime


class DimensionalObjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dimensional_object_not_found",
            message="The requested Dimensional Object was not found.",
        )


class DimensionalAttributeNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dimensional_attribute_not_found",
            message="The requested Dimensional Attribute was not found.",
        )


class DimensionalRelationshipNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dimensional_relationship_not_found",
            message="The requested Dimensional Relationship was not found.",
        )


class DimensionalDetailLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dimensional_detail_limit_exceeded",
            message="The Dimensional artifact has too many related rows to return safely.",
        )


class DimensionalObjectListQuery(ModeledListQuery):
    subject_area_id: int | None = Field(default=None, gt=0)


class DimensionalAttributeListQuery(ModeledListQuery):
    dimensional_entity_id: int | None = Field(default=None, gt=0)


class DimensionalRelationshipListQuery(ModeledListQuery):
    dimensional_entity_id: int | None = Field(default=None, gt=0)
