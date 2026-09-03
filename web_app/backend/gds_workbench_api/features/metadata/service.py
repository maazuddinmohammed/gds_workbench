"""Authorized Metadata catalog behavior."""

import json
from collections.abc import Mapping
from datetime import date, datetime
from hashlib import sha256
from typing import Literal, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.metadata import (
    DATASETS_BY_NAME,
    MetadataDataset,
    normalize_natural_key_value,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from pydantic import JsonValue, ValidationError

from gds_workbench_api.features.metadata.contracts import (
    MAX_METADATA_EXPORT_ROWS,
    MAX_METADATA_EXPORT_ROWS_PER_SHEET,
    METADATA_DATASETS,
    OPERATIONAL_DATASETS,
    MetadataDatabase,
    MetadataDatasetDescription,
    MetadataDatasetDetail,
    MetadataDatasetRegistry,
    MetadataFilter,
    MetadataObjectNotFoundError,
    MetadataRepository,
    MetadataRowPage,
    MetadataWorkbookDownload,
    ObjectCatalogDetail,
    ObjectCatalogFilters,
    ObjectCatalogPage,
    OperationalDataset,
)
from gds_workbench_api.features.metadata.workbook import (
    MetadataWorkbookSheet,
    build_metadata_workbook,
)


class DatabaseMetadataService:
    """Authorize every catalog read and apply bounded, query-bound pagination."""

    def __init__(
        self,
        *,
        database: MetadataDatabase,
        repository: MetadataRepository,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._repository = repository
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_datasets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> MetadataDatasetRegistry:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
        return metadata_dataset_registry(tenant_id=tenant_id)

    async def list_rows(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        filters: tuple[MetadataFilter, ...],
        page_size: int,
        cursor: str | None,
    ) -> MetadataRowPage:
        allowed = set(DATASETS_BY_NAME[dataset].search_fields)
        if (
            tuple(sorted(filters, key=lambda item: item.field)) != filters
            or len({item.field for item in filters}) != len(filters)
            or any(item.field not in allowed for item in filters)
        ):
            raise InvalidRequestError("Metadata filters do not match the selected dataset.")
        filter_document = json.dumps(
            [item.model_dump(mode="json") for item in filters],
            separators=(",", ":"),
            sort_keys=True,
        )
        collection = (
            f"web_metadata_rows:{tenant_id}:{dataset}:{page_size}:"
            f"{sha256(filter_document.encode()).hexdigest()}"
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            rows = await self._repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset=dataset,
                filters=filters,
                limit=page_size + 1,
                offset=offset,
            )
        row_model = DATASETS_BY_NAME[dataset].row_model
        items = tuple(
            row_model.model_validate(dict(row), strict=True).model_dump()
            for row in rows[:page_size]
        )
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return MetadataRowPage(
            tenant_id=tenant_id,
            dataset=dataset,
            items=items,
            next_cursor=next_cursor,
        )

    async def describe_dataset(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
    ) -> MetadataDatasetDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
        return metadata_dataset_detail(tenant_id=tenant_id, dataset=dataset)

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        filters: ObjectCatalogFilters,
        page_size: int,
        cursor: str | None,
    ) -> ObjectCatalogPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = f"web_metadata_objects:{tenant_id}:{page_size}:{filter_digest}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            rows = await self._repository.list_objects(
                transaction,
                tenant_id=tenant_id,
                filters=filters,
                limit=page_size + 1,
                offset=offset,
            )
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return ObjectCatalogPage(
            tenant_id=tenant_id,
            items=tuple(rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def get_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        object_id: int,
    ) -> ObjectCatalogDetail:
        if object_id <= 0:
            raise InvalidRequestError("Object ID must be positive.")
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            result = await self._repository.get_object(
                transaction,
                tenant_id=tenant_id,
                object_id=object_id,
            )
        if result is None:
            raise MetadataObjectNotFoundError()
        return result

    async def export_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sheet_codes: Literal["all"] | tuple[str, ...],
    ) -> MetadataWorkbookDownload:
        selected = _resolve_export_sheet_codes(sheet_codes)
        exported: list[MetadataWorkbookSheet] = []
        total_rows = 0
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            for dataset in selected:
                definition = DATASETS_BY_NAME[dataset]
                rows = await self._repository.list_export_rows(
                    transaction,
                    tenant_id=tenant_id,
                    dataset=dataset,
                    limit=MAX_METADATA_EXPORT_ROWS_PER_SHEET + 1,
                )
                if len(rows) > MAX_METADATA_EXPORT_ROWS_PER_SHEET:
                    raise InvalidRequestError("Metadata workbook exceeds its row limit.")
                try:
                    validated = tuple(
                        definition.row_model.model_validate(
                            dict(row),
                            strict=True,
                        ).model_dump()
                        for row in rows
                    )
                except ValidationError as error:
                    raise InvalidRequestError(
                        "Metadata workbook row does not match its canonical schema."
                    ) from error
                validated = tuple(
                    sorted(
                        validated,
                        key=lambda row: _metadata_export_sort_key(
                            definition.canonical_key,
                            row,
                        ),
                    )
                )
                total_rows += len(validated)
                if total_rows > MAX_METADATA_EXPORT_ROWS:
                    raise InvalidRequestError("Metadata workbook exceeds its row limit.")
                exported.append(
                    MetadataWorkbookSheet(
                        code=dataset,
                        name=definition.label,
                        columns=tuple(definition.row_model.model_fields),
                        canonical_key=definition.canonical_key,
                        row_schema=definition.row_model.model_json_schema(),
                        rows=validated,
                    )
                )
        try:
            content = build_metadata_workbook(tenant_id=tenant_id, sheets=tuple(exported))
        except Exception as error:
            raise InvalidRequestError(
                "Metadata workbook contains a value that Excel cannot represent."
            ) from error
        return MetadataWorkbookDownload(
            content=content,
            filename=(f"gds_operational_metadata__tenant_{tenant_id}__{len(exported)}_sheets.xlsx"),
            sheet_count=len(exported),
        )


def _metadata_dataset_description(dataset: MetadataDataset) -> MetadataDatasetDescription:
    definition = DATASETS_BY_NAME[dataset]
    return MetadataDatasetDescription(
        dataset=dataset,
        label=definition.label,
        section=definition.section,
        change_set_eligible=definition.change_set_eligible,
        read_only=not definition.change_set_eligible,
        columns=tuple(definition.row_model.model_fields),
        natural_key=definition.canonical_key,
        filter_fields=definition.search_fields,
    )


def metadata_dataset_registry(*, tenant_id: int) -> MetadataDatasetRegistry:
    """Project all canonical V2 sheets without database internals."""
    return MetadataDatasetRegistry(
        tenant_id=tenant_id,
        datasets=tuple(_metadata_dataset_description(name) for name in METADATA_DATASETS),
    )


def metadata_dataset_detail(
    *,
    tenant_id: int,
    dataset: MetadataDataset,
) -> MetadataDatasetDetail:
    """Expose canonical field types and bounds for one authorized Metadata sheet."""
    description = _metadata_dataset_description(dataset)
    definition = DATASETS_BY_NAME[dataset]
    return MetadataDatasetDetail(
        **description.model_dump(),
        tenant_id=tenant_id,
        row_schema=definition.row_model.model_json_schema(),
        fixed_values=cast(dict[str, JsonValue], dict(definition.fixed_values)),
    )


def _resolve_export_sheet_codes(
    sheet_codes: Literal["all"] | tuple[str, ...],
) -> tuple[OperationalDataset, ...]:
    if sheet_codes == "all":
        return OPERATIONAL_DATASETS
    if (
        not 1 <= len(sheet_codes) <= len(OPERATIONAL_DATASETS)
        or len(set(sheet_codes)) != len(sheet_codes)
        or any(not 1 <= len(code) <= 100 for code in sheet_codes)
        or any(code not in OPERATIONAL_DATASETS for code in sheet_codes)
    ):
        raise InvalidRequestError("Metadata workbook sheet selection is invalid.")
    selected = set(sheet_codes)
    return tuple(dataset for dataset in OPERATIONAL_DATASETS if dataset in selected)


def _metadata_export_sort_key(
    canonical_key: tuple[str, ...],
    row: Mapping[str, object],
) -> tuple[str, ...]:
    encoded: list[str] = []
    for field in canonical_key:
        value = normalize_natural_key_value(field, row[field])
        if value is None:
            encoded.append("0:")
        elif isinstance(value, bool):
            encoded.append(f"1:{int(value)}")
        elif isinstance(value, int):
            encoded.append(f"2:{value:+020d}")
        elif isinstance(value, (date, datetime)):
            encoded.append(f"3:{value.isoformat()}")
        else:
            encoded.append(f"4:{value}")
    return tuple(encoded)
