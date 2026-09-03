"""HTTP router for the authorized Metadata catalog."""

import json
from datetime import date, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Path, Query, Response
from fastapi.requests import Request
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.metadata import (
    DATASETS_BY_NAME,
    MetadataDataset,
    normalize_natural_key_value,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from gds_workbench_api.features.metadata.contracts import (
    ActiveState,
    MetadataDatasetDetail,
    MetadataDatasetRegistry,
    MetadataFilter,
    MetadataRowPage,
    MetadataService,
    ObjectCatalogDetail,
    ObjectCatalogFilters,
    ObjectCatalogPage,
    normalize_metadata_code,
)
from gds_workbench_api.features.metadata.workbook import XLSX_MEDIA_TYPE


class DatasetRowsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: str | None = Field(default=None, max_length=4096)
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


class MetadataWorkbookExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    sheet_codes: Literal["all"] | list[str] = "all"


class ObjectListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: str | None = Field(default=None, max_length=30)
    system_code: str | None = Field(default=None, max_length=100)
    source_tenant_code: str | None = Field(default=None, max_length=100)
    active_state: ActiveState = "active"
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("zone", "system_code", "source_tenant_code", mode="before")
    @classmethod
    def normalize_filters(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        if not isinstance(info.field_name, str):
            raise ValueError("filter field is invalid")
        field = "zone_code" if info.field_name == "zone" else info.field_name
        return normalize_metadata_code(field, value)


def _parse_filters(
    dataset: MetadataDataset,
    encoded_filters: str | None,
) -> tuple[MetadataFilter, ...]:
    if encoded_filters is None:
        return ()
    try:
        payload: object = json.loads(encoded_filters)
    except json.JSONDecodeError as error:
        raise InvalidRequestError("Metadata filters must be one JSON object.") from error
    if not isinstance(payload, dict):
        raise InvalidRequestError("Metadata filters must be one bounded JSON object.")
    filter_document = cast(dict[object, object], payload)
    if len(filter_document) > 16:
        raise InvalidRequestError("Metadata filters must be one bounded JSON object.")
    allowed = set(DATASETS_BY_NAME[dataset].search_fields)
    requested: list[tuple[str, object]] = []
    for raw_field, value in filter_document.items():
        if not isinstance(raw_field, str):
            raise InvalidRequestError(f"{dataset} does not expose the requested filter field.")
        requested.append((raw_field, value))
    filters: list[MetadataFilter] = []
    for field, value in sorted(requested):
        if field not in allowed:
            raise InvalidRequestError(f"{dataset} does not expose the requested filter field.")
        field_info = DATASETS_BY_NAME[dataset].row_model.model_fields[field]
        if field_info.annotation is None:
            raise InvalidRequestError(f"{dataset} filter field is invalid.")
        field_type = field_info.annotation
        if field_info.metadata:
            field_type = Annotated[(field_type, *field_info.metadata)]
        adapter: TypeAdapter[object] = TypeAdapter(field_type)
        try:
            validated = adapter.validate_json(
                json.dumps(value, separators=(",", ":")),
                strict=True,
            )
        except ValidationError as error:
            raise InvalidRequestError(f"{dataset} filter value does not match {field}.") from error
        normalized = normalize_natural_key_value(field, validated)
        if normalized is not None and not isinstance(normalized, (str, bool, int, date, datetime)):
            raise InvalidRequestError(f"{dataset} filter field is invalid.")
        filters.append(MetadataFilter(field=field, value=normalized))
    return tuple(filters)


def create_metadata_router(
    *,
    identity_provider: IdentityProvider,
    service: MetadataService,
) -> APIRouter:
    """Create the metadata router for later application/runtime composition."""
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/metadata", tags=["metadata"])

    async def list_datasets(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
    ) -> MetadataDatasetRegistry:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_datasets(principal, tenant_id=tenant_id)

    router.add_api_route(
        "/datasets",
        list_datasets,
        methods=["GET"],
        response_model=MetadataDatasetRegistry,
    )

    async def describe_dataset(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        dataset: MetadataDataset,
    ) -> MetadataDatasetDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.describe_dataset(
            principal,
            tenant_id=tenant_id,
            dataset=dataset,
        )

    router.add_api_route(
        "/datasets/{dataset}",
        describe_dataset,
        methods=["GET"],
        response_model=MetadataDatasetDetail,
    )

    async def list_rows(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        dataset: MetadataDataset,
        query: Annotated[DatasetRowsQuery, Query()],
    ) -> MetadataRowPage:
        principal = identity_provider.authenticate(request.headers)
        return await service.list_rows(
            principal,
            tenant_id=tenant_id,
            dataset=dataset,
            filters=_parse_filters(dataset, query.filters),
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/datasets/{dataset}/rows",
        list_rows,
        methods=["GET"],
        response_model=MetadataRowPage,
    )

    async def export_workbook(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        command: MetadataWorkbookExportRequest,
    ) -> Response:
        principal = identity_provider.authenticate(request.headers)
        requested = command.sheet_codes
        sheet_codes: Literal["all"] | tuple[str, ...] = (
            tuple(requested) if isinstance(requested, list) else requested
        )
        download = await service.export_workbook(
            principal,
            tenant_id=tenant_id,
            sheet_codes=sheet_codes,
        )
        return Response(
            content=download.content,
            media_type=XLSX_MEDIA_TYPE,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{download.filename}"',
                "X-Content-Type-Options": "nosniff",
                "X-GDS-Sheet-Count": str(download.sheet_count),
            },
        )

    router.add_api_route(
        "/exports/xlsx",
        export_workbook,
        methods=["POST"],
        response_class=Response,
    )

    async def list_objects(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        query: Annotated[ObjectListQuery, Query()],
    ) -> ObjectCatalogPage:
        principal = identity_provider.authenticate(request.headers)
        filters = ObjectCatalogFilters.model_validate(
            {
                "zone": query.zone,
                "system_code": query.system_code,
                "source_tenant_code": query.source_tenant_code,
                "active_state": query.active_state,
            },
            strict=True,
        )
        return await service.list_objects(
            principal,
            tenant_id=tenant_id,
            filters=filters,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/objects",
        list_objects,
        methods=["GET"],
        response_model=ObjectCatalogPage,
    )

    async def get_object(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        object_id: Annotated[int, Path(gt=0)],
    ) -> ObjectCatalogDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.get_object(
            principal,
            tenant_id=tenant_id,
            object_id=object_id,
        )

    router.add_api_route(
        "/objects/{object_id}",
        get_object,
        methods=["GET"],
        response_model=ObjectCatalogDetail,
    )
    return router
