"""Contracts for the authorized Metadata catalog."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS,
    DATASETS_BY_NAME,
    MetadataDataset,
    SnapshotSection,
    normalize_natural_key_value,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

type OperationalDataset = Literal[
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
]

OPERATIONAL_DATASETS: tuple[OperationalDataset, ...] = (
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
)

FOUNDATIONAL_DATASETS: tuple[MetadataDataset, ...] = (
    "project",
    "tenant",
    "system",
    "connection",
    "tenant_metadata_discovery_scope",
)

REFERENCE_DATASETS: tuple[MetadataDataset, ...] = (
    "system_type",
    "connection_type",
    "object_type",
    "zone",
    "chunk_type",
    "file_type",
    "data_operation",
    "process_type",
)

METADATA_DATASETS: tuple[MetadataDataset, ...] = tuple(definition.name for definition in DATASETS)
if (
    *FOUNDATIONAL_DATASETS,
    *REFERENCE_DATASETS,
    *OPERATIONAL_DATASETS,
) != METADATA_DATASETS:
    raise RuntimeError("web Metadata dataset inventory does not match the canonical registry")

MAX_METADATA_EXPORT_ROWS_PER_SHEET = 10_000
MAX_METADATA_EXPORT_ROWS = 50_000


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MetadataDatasetDescription(ContractModel):
    dataset: MetadataDataset
    label: str = Field(min_length=1, max_length=200)
    section: SnapshotSection
    change_set_eligible: bool
    read_only: bool
    columns: tuple[str, ...] = Field(min_length=1, max_length=64)
    natural_key: tuple[str, ...] = Field(min_length=1, max_length=24)
    filter_fields: tuple[str, ...] = Field(min_length=1, max_length=24)


class MetadataDatasetRegistry(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    datasets: tuple[MetadataDatasetDescription, ...] = Field(
        min_length=len(METADATA_DATASETS),
        max_length=len(METADATA_DATASETS),
    )


class MetadataDatasetDetail(MetadataDatasetDescription):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    row_schema: dict[str, JsonValue]


type MetadataFilterValue = str | bool | int | date | datetime | None
type ZoneCode = Literal["source", "bronze", "silver", "gold"]
type ActiveState = Literal["active", "inactive", "all"]


class MetadataFilter(ContractModel):
    field: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    value: MetadataFilterValue

    @field_validator("value")
    @classmethod
    def bound_string_value(cls, value: MetadataFilterValue) -> MetadataFilterValue:
        if isinstance(value, str) and len(value) > 400:
            raise ValueError("filter string values may contain at most 400 characters")
        return value


class MetadataRowPage(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    dataset: MetadataDataset
    items: tuple[dict[str, object], ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_shared_rows(self) -> MetadataRowPage:
        row_model = DATASETS_BY_NAME[self.dataset].row_model
        for item in self.items:
            row_model.model_validate(item, strict=True)
        return self


@dataclass(frozen=True, slots=True)
class MetadataWorkbookDownload:
    content: bytes
    filename: str
    sheet_count: int


def normalize_metadata_code(field: str, value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_natural_key_value(field, value)
    if not isinstance(normalized, str) or not normalized:
        raise ValueError(f"{field} must be nonblank")
    return normalized


class ObjectCatalogFilters(ContractModel):
    zone: ZoneCode | None = None
    system_code: str | None = Field(default=None, min_length=1, max_length=100)
    source_tenant_code: str | None = Field(default=None, min_length=1, max_length=100)
    active_state: ActiveState = "active"

    @field_validator("zone", mode="before")
    @classmethod
    def normalize_zone(cls, value: object) -> object:
        return normalize_metadata_code("zone_code", value) if isinstance(value, str) else value

    @field_validator("system_code", "source_tenant_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(info.field_name, str):
            raise ValueError("filter field is invalid")
        return normalize_metadata_code(info.field_name, value) if isinstance(value, str) else value


class ObjectCatalogSummary(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_type_code: str = Field(min_length=1, max_length=100)
    zone_code: ZoneCode
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)
    attribute_count: int = Field(ge=0)
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    is_active: bool


class ObjectCatalogPage(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    items: tuple[ObjectCatalogSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ObjectAttribute(ContractModel):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_ordinal_position: int = Field(gt=0)
    attribute_description: str | None = Field(default=None, max_length=2000)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    attribute_nullability: bool
    is_surrogate_key: bool
    is_natural_key: bool
    is_meta_data: bool
    is_masking_required: bool
    is_mapped: bool
    is_purge: bool
    is_active: bool


class ObjectCatalogDetail(ObjectCatalogSummary):
    object_type_name: str = Field(min_length=1, max_length=200)
    object_description: str | None = Field(default=None, max_length=2000)
    connection_name: str = Field(min_length=1, max_length=200)
    is_locked: bool
    attributes: tuple[ObjectAttribute, ...] = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_attribute_count(self) -> ObjectCatalogDetail:
        if self.attribute_count != len(self.attributes):
            raise ValueError("attribute_count must match the returned Attributes")
        return self


class MetadataService(Protocol):
    async def list_datasets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> MetadataDatasetRegistry: ...

    async def describe_dataset(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
    ) -> MetadataDatasetDetail: ...

    async def list_rows(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        filters: tuple[MetadataFilter, ...],
        page_size: int,
        cursor: str | None,
    ) -> MetadataRowPage: ...

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        filters: ObjectCatalogFilters,
        page_size: int,
        cursor: str | None,
    ) -> ObjectCatalogPage: ...

    async def get_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        object_id: int,
    ) -> ObjectCatalogDetail: ...

    async def export_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sheet_codes: Literal["all"] | tuple[str, ...],
    ) -> MetadataWorkbookDownload: ...


class MetadataDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class MetadataRepository(Protocol):
    async def list_export_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: OperationalDataset,
        limit: int,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        filters: tuple[MetadataFilter, ...],
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_objects(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        filters: ObjectCatalogFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ObjectCatalogSummary]: ...

    async def get_object(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        object_id: int,
    ) -> ObjectCatalogDetail | None: ...


class MetadataObjectNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="metadata_object_not_found",
            message="Metadata Object was not found.",
        )
