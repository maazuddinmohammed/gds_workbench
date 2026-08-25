"""Tenant-owned normalized Dimensional model review contracts."""

from datetime import datetime
from typing import Annotated, Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import Field

from gds_workbench_api.features.logical import (
    AssertionRecordReference,
    Cardinality,
    Confidence,
    ContractModel,
    ModeledFilters,
    ModeledListQuery,
    ModeledStatus,
    PhysicalAttributeReference,
    PhysicalObjectReference,
)

MAX_DETAIL_ROWS = 2000

# Layer-specific public name; kept identical to the shared normalized filter contract.
DimensionalFilters = ModeledFilters


class DimensionalObjectSummary(ContractModel):
    dimensional_entity_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    dimensional_entity_name: str = Field(min_length=1, max_length=255)
    dimensional_entity_type: Literal["fact", "dimension", "bridge"]
    dimensional_fact_type: (
        Literal[
            "transaction",
            "periodic_snapshot",
            "accumulating_snapshot",
            "factless",
        ]
        | None
    ) = None
    dimensional_entity_dependency_order: int = Field(ge=0)
    dimensional_entity_confidence: Confidence
    dimensional_entity_status: ModeledStatus
    dimensional_entity_is_locked: bool
    updated_at: datetime


class DimensionalObjectPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[DimensionalObjectSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class DimensionalSubmodelMembership(ContractModel):
    dimensional_entity_submodel_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    dimensional_submodel_id: int = Field(gt=0)
    dimensional_submodel_name: str = Field(min_length=1, max_length=255)
    membership_status: ModeledStatus
    membership_is_locked: bool
    created_at: datetime
    updated_at: datetime


class DimensionalObjectSourceBase(ContractModel):
    dimensional_entity_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    source_role: str = Field(min_length=1, max_length=255)
    source_order: int | None = Field(default=None, gt=0)
    rationale: str = Field(min_length=1)
    status: ModeledStatus
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class DimensionalPhysicalObjectSource(DimensionalObjectSourceBase):
    support_source_type: Literal["object"]
    source_object: PhysicalObjectReference


class DimensionalAssertionSource(DimensionalObjectSourceBase):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordReference


type DimensionalObjectSource = Annotated[
    DimensionalPhysicalObjectSource | DimensionalAssertionSource,
    Field(discriminator="support_source_type"),
]


class DimensionalObjectDetail(DimensionalObjectSummary):
    dimensional_entity_definition: str = Field(min_length=1)
    dimensional_entity_grain_definition: str | None = Field(default=None, min_length=1)
    created_at: datetime
    submodels: tuple[DimensionalSubmodelMembership, ...] = Field(max_length=MAX_DETAIL_ROWS)
    sources: tuple[DimensionalObjectSource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class DimensionalAttributeFilters(ModeledFilters):
    dimensional_entity_id: int | None = Field(default=None, gt=0)


class DimensionalAttributeSummary(ContractModel):
    dimensional_attribute_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    dimensional_entity_id: int = Field(gt=0)
    dimensional_entity_name: str = Field(min_length=1, max_length=255)
    dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    dimensional_attribute_data_type: str = Field(min_length=1, max_length=100)
    dimensional_attribute_is_nullable: bool
    dimensional_attribute_ordinal_position: int = Field(gt=0)
    dimensional_attribute_role: Literal[
        "key",
        "descriptor",
        "measure",
        "degenerate_dimension",
        "bridge_weight",
        "technical",
        "audit",
    ]
    dimensional_attribute_key_role: Literal[
        "none",
        "surrogate",
        "business",
        "foreign",
    ]
    dimensional_attribute_is_grain_component: bool
    dimensional_attribute_additivity: (
        Literal[
            "additive",
            "semi_additive",
            "non_additive",
        ]
        | None
    ) = None
    dimensional_attribute_default_aggregation: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    dimensional_attribute_change_behavior: (
        Literal[
            "fixed",
            "overwrite",
            "historize",
        ]
        | None
    ) = None
    dimensional_attribute_is_audit_column: bool
    dimensional_attribute_confidence: Confidence
    dimensional_attribute_status: ModeledStatus
    dimensional_attribute_is_locked: bool
    updated_at: datetime


class DimensionalAttributePage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[DimensionalAttributeSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class DimensionalAttributeSourceBase(ContractModel):
    dimensional_attribute_source_mapping_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    source_order: int | None = Field(default=None, gt=0)
    rationale: str = Field(min_length=1)
    status: ModeledStatus
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class DimensionalAttributePhysicalSource(DimensionalAttributeSourceBase):
    dimensional_entity_source_mapping_id: int = Field(gt=0)
    support_source_type: Literal["attribute"]
    source_attribute: PhysicalAttributeReference


class DimensionalAttributeAssertionSource(DimensionalAttributeSourceBase):
    support_source_type: Literal["assertion"]
    assertion_record: AssertionRecordReference


type DimensionalAttributeSource = Annotated[
    DimensionalAttributePhysicalSource | DimensionalAttributeAssertionSource,
    Field(discriminator="support_source_type"),
]


class DimensionalAttributeDetail(DimensionalAttributeSummary):
    dimensional_attribute_definition: str = Field(min_length=1)
    dimensional_attribute_aggregation_basis: str | None = Field(
        default=None,
        min_length=1,
    )
    created_at: datetime
    sources: tuple[DimensionalAttributeSource, ...] = Field(max_length=MAX_DETAIL_ROWS)


class DimensionalRelationshipFilters(ModeledFilters):
    dimensional_entity_id: int | None = Field(default=None, gt=0)


class DimensionalRelationshipSummary(ContractModel):
    dimensional_relationship_id: int = Field(gt=0)
    workflow_run_id: int | None = Field(default=None, gt=0)
    from_dimensional_entity_id: int = Field(gt=0)
    from_dimensional_entity_name: str = Field(min_length=1, max_length=255)
    from_dimensional_attribute_id: int = Field(gt=0)
    from_dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    to_dimensional_entity_id: int = Field(gt=0)
    to_dimensional_entity_name: str = Field(min_length=1, max_length=255)
    to_dimensional_attribute_id: int = Field(gt=0)
    to_dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    dimensional_relationship_name: str = Field(min_length=1, max_length=255)
    dimensional_relationship_kind: str = Field(min_length=1, max_length=50)
    dimensional_relationship_cardinality: Cardinality
    dimensional_relationship_is_optional: bool
    dimensional_relationship_role_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    dimensional_relationship_confidence: Confidence
    dimensional_relationship_status: ModeledStatus
    dimensional_relationship_is_locked: bool
    updated_at: datetime


class DimensionalRelationshipPage(ContractModel):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[DimensionalRelationshipSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class DimensionalRelationshipDetail(DimensionalRelationshipSummary):
    dimensional_relationship_definition: str = Field(min_length=1)
    dimensional_relationship_basis: str = Field(min_length=1)
    dimensional_relationship_cardinality_basis: str = Field(min_length=1)
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


class DimensionalAttributeListQuery(ModeledListQuery):
    dimensional_entity_id: int | None = Field(default=None, gt=0)


class DimensionalRelationshipListQuery(ModeledListQuery):
    dimensional_entity_id: int | None = Field(default=None, gt=0)
