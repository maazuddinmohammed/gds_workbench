import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal, LiteralString
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.errors import workbench_error_response
from gds_workbench_api.features.metadata import (
    DatabaseMetadataService,
    MetadataDataset,
    MetadataDatasetDetail,
    MetadataDatasetRegistry,
    MetadataFilter,
    MetadataRowPage,
    MetadataWorkbookDownload,
    ObjectAttribute,
    ObjectCatalogDetail,
    ObjectCatalogFilters,
    ObjectCatalogPage,
    ObjectCatalogSummary,
    create_metadata_router,
    metadata_dataset_detail,
    metadata_dataset_registry,
)


class StaticMetadataService:
    filters: tuple[MetadataFilter, ...] = ()
    object_filters: ObjectCatalogFilters | None = None

    async def list_datasets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> MetadataDatasetRegistry:
        assert principal == RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        )
        return metadata_dataset_registry(tenant_id=tenant_id)

    async def describe_dataset(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
    ) -> MetadataDatasetDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        return metadata_dataset_detail(tenant_id=tenant_id, dataset=dataset)

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
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        assert dataset == "source_object"
        assert page_size == 1
        assert cursor is None
        self.filters = filters
        return MetadataRowPage(
            tenant_id=tenant_id,
            dataset=dataset,
            items=(
                {
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "connection_code": "MAIN",
                    "object_schema": "sales",
                    "object_name": "Customer",
                    "source_tenant_code": "NWA",
                    "fc_object_schema": None,
                    "fc_object_name": None,
                    "object_transformation": None,
                    "object_description": "Customer master",
                    "batch_attribute_name": "UpdatedAt",
                    "object_type_code": "TABLE",
                    "zone_code": "source",
                    "is_locked": False,
                    "is_active": True,
                },
            ),
            next_cursor="next-page",
        )

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        filters: ObjectCatalogFilters,
        page_size: int,
        cursor: str | None,
    ) -> ObjectCatalogPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        assert page_size == 1
        assert cursor is None
        self.object_filters = filters
        return ObjectCatalogPage(
            tenant_id=tenant_id,
            items=(
                ObjectCatalogSummary(
                    object_id=101,
                    object_schema="sales",
                    object_name="CustomerSilver",
                    object_type_code="TABLE",
                    zone_code="silver",
                    connection_id=11,
                    connection_code="MAIN",
                    system_id=3,
                    system_code="ERP",
                    system_name="Enterprise Resource Planning",
                    source_tenant_id=8,
                    source_tenant_code="GRDM",
                    source_tenant_name="Global Reference Data",
                    attribute_count=12,
                    batch_attribute_name="UpdatedAt",
                    is_active=True,
                ),
            ),
            next_cursor=None,
        )

    async def get_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        object_id: int,
    ) -> ObjectCatalogDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        assert object_id == 101
        return ObjectCatalogDetail(
            object_id=101,
            object_schema="sales",
            object_name="CustomerSilver",
            object_type_code="TABLE",
            object_type_name="Table",
            object_description="Conformed customer",
            zone_code="silver",
            connection_id=11,
            connection_code="MAIN",
            connection_name="Shared Silver",
            system_id=3,
            system_code="ERP",
            system_name="Enterprise Resource Planning",
            source_tenant_id=8,
            source_tenant_code="GRDM",
            source_tenant_name="Global Reference Data",
            attribute_count=1,
            batch_attribute_name="UpdatedAt",
            is_locked=False,
            is_active=True,
            attributes=(
                ObjectAttribute(
                    attribute_id=501,
                    attribute_name="CustomerId",
                    attribute_ordinal_position=1,
                    attribute_description="Customer identifier",
                    attribute_data_type="bigint",
                    attribute_nullability=False,
                    is_surrogate_key=True,
                    is_natural_key=False,
                    is_meta_data=False,
                    is_masking_required=False,
                    is_mapped=True,
                    is_purge=False,
                    is_active=True,
                ),
            ),
        )

    async def export_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sheet_codes: Literal["all"] | tuple[str, ...],
    ) -> MetadataWorkbookDownload:
        raise AssertionError((principal, tenant_id, sheet_codes))


def test_dataset_registry_uses_server_derived_identity_and_complete_v2_inventory() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=StaticMetadataService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/metadata/datasets")

    assert response.status_code == 200
    document = response.json()
    assert document["schema_version"] == "1.0"
    assert document["tenant_id"] == 7
    assert [item["dataset"] for item in document["datasets"]] == [
        "project",
        "tenant",
        "system",
        "connection",
        "system_type",
        "connection_type",
        "object_type",
        "zone",
        "chunk_type",
        "file_type",
        "data_operation",
        "process_type",
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
    assert [item["section"] for item in document["datasets"][:4]] == [
        "foundational"
    ] * 4
    assert [item["section"] for item in document["datasets"][4:12]] == ["reference"] * 8
    assert [item["section"] for item in document["datasets"][12:]] == [
        "operational"
    ] * 16
    assert all(item["read_only"] for item in document["datasets"][:12])
    assert all(not item["change_set_eligible"] for item in document["datasets"][:12])
    assert all(not item["read_only"] for item in document["datasets"][12:])
    assert all(item["change_set_eligible"] for item in document["datasets"][12:])
    source_object = document["datasets"][12]
    assert source_object["natural_key"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    ]
    assert source_object["filter_fields"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "source_tenant_code",
        "object_type_code",
        "zone_code",
        "is_locked",
        "is_active",
    ]
    assert "connection_value" not in response.text


def test_dataset_detail_exposes_canonical_ordered_field_schema() -> None:
    app = FastAPI()
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=StaticMetadataService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/metadata/datasets/source_object")

    assert response.status_code == 200
    document = response.json()
    assert document["tenant_id"] == 7
    assert document["dataset"] == "source_object"
    assert list(document["row_schema"]["properties"]) == document["columns"]
    assert document["row_schema"]["properties"]["tenant_code"]["type"] == "string"
    assert document["row_schema"]["properties"]["object_description"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert "tenant_code" in document["row_schema"]["required"]
    assert document["fixed_values"] == {"zone_code": "source"}
    assert "connection_value" not in response.text


def test_dataset_rows_normalize_exact_sheet_filters_without_free_text_search() -> None:
    service = StaticMetadataService()
    app = FastAPI()
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/metadata/datasets/source_object/rows",
            params={
                "filters": json.dumps(
                    {"system_code": " CRM ", "is_active": True},
                    separators=(",", ":"),
                ),
                "page_size": "1",
            },
        )
        rejected_search = client.get(
            "/api/v1/tenants/7/metadata/datasets/source_object/rows",
            params={"search": "customer"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "tenant_id": 7,
        "dataset": "source_object",
        "items": [
            {
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "MAIN",
                "object_schema": "sales",
                "object_name": "Customer",
                "source_tenant_code": "NWA",
                "fc_object_schema": None,
                "fc_object_name": None,
                "object_transformation": None,
                "object_description": "Customer master",
                "batch_attribute_name": "UpdatedAt",
                "object_type_code": "TABLE",
                "zone_code": "source",
                "is_locked": False,
                "is_active": True,
            }
        ],
        "next_cursor": "next-page",
    }
    assert service.filters == (
        MetadataFilter(field="is_active", value=True),
        MetadataFilter(field="system_code", value="crm"),
    )
    assert rejected_search.status_code == 422


def test_dataset_filters_enforce_the_selected_sheet_field_types() -> None:
    app = FastAPI()
    app.add_exception_handler(WorkbenchError, workbench_error_response)
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=StaticMetadataService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/metadata/datasets/source_object/rows",
            params={
                "filters": '{"is_active":"true"}',
                "page_size": "1",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


class ReferenceRowsService(StaticMetadataService):
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
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        assert dataset == "zone"
        assert filters == (MetadataFilter(field="zone_code", value="bronze"),)
        assert page_size == 10
        assert cursor is None
        return MetadataRowPage(
            tenant_id=tenant_id,
            dataset=dataset,
            items=(
                {
                    "zone_code": "bronze",
                    "zone_name": "Bronze",
                    "zone_description": "Raw persisted ingestion",
                    "is_active": True,
                },
            ),
        )


def test_reference_dataset_rows_use_the_same_authorized_normalized_contract() -> None:
    app = FastAPI()
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=ReferenceRowsService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/metadata/datasets/zone/rows",
            params={"filters": '{"zone_code":" Bronze "}', "page_size": "10"},
        )

    assert response.status_code == 200
    assert response.json()["dataset"] == "zone"
    assert response.json()["items"][0]["zone_name"] == "Bronze"
    assert "connection_value" not in response.text


class CatalogTransaction:
    def __init__(self) -> None:
        self.authorization_calls = 0

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert "WITH actor AS" in query
        assert parameters[-1] == 7
        self.authorization_calls += 1
        return {
            "principal_id": 41,
            "principal_display_name": "Maaz",
            "is_super_admin": False,
            "effective_role": "viewer",
            "authorized": True,
            "denial_code": None,
            "lock_owner_display_name": None,
            "lock_expires_time": None,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class CatalogDatabase:
    def __init__(self) -> None:
        self.transaction = CatalogTransaction()
        self.isolations: list[ReadIsolation] = []

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[CatalogTransaction]:
        self.isolations.append(isolation)
        yield self.transaction


def _source_object(name: str) -> dict[str, object]:
    return {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": name,
        "source_tenant_code": "NWA",
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": None,
        "batch_attribute_name": None,
        "object_type_code": "TABLE",
        "zone_code": "source",
        "is_locked": False,
        "is_active": True,
    }


class CatalogRepository:
    def __init__(self) -> None:
        self.rows = [_source_object("Customer"), _source_object("Order")]
        self.calls: list[tuple[int, int, tuple[MetadataFilter, ...]]] = []
        self.object_calls: list[tuple[int, int, ObjectCatalogFilters]] = []
        self.detail_calls: list[tuple[int, int]] = []

    async def list_export_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        limit: int,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError((transaction, tenant_id, dataset, limit))

    async def list_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        filters: tuple[MetadataFilter, ...],
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]:
        assert transaction is not None
        assert tenant_id == 7
        assert dataset == "source_object"
        self.calls.append((limit, offset, filters))
        return self.rows[offset : offset + limit]

    async def list_objects(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        filters: ObjectCatalogFilters,
        limit: int,
        offset: int,
    ) -> Sequence[ObjectCatalogSummary]:
        assert transaction is not None
        assert tenant_id == 7
        self.object_calls.append((limit, offset, filters))
        rows = (
            ObjectCatalogSummary(
                object_id=101,
                object_schema="sales",
                object_name="CustomerSilver",
                object_type_code="TABLE",
                zone_code="silver",
                connection_id=11,
                connection_code="MAIN",
                system_id=3,
                system_code="ERP",
                system_name="Enterprise Resource Planning",
                source_tenant_id=8,
                source_tenant_code="GRDM",
                source_tenant_name="Global Reference Data",
                attribute_count=12,
                batch_attribute_name="UpdatedAt",
                is_active=True,
            ),
        )
        return rows[offset : offset + limit]

    async def get_object(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        object_id: int,
    ) -> ObjectCatalogDetail | None:
        assert transaction is not None
        self.detail_calls.append((tenant_id, object_id))
        return ObjectCatalogDetail(
            object_id=object_id,
            object_schema="sales",
            object_name="CustomerSilver",
            object_type_code="TABLE",
            object_type_name="Table",
            object_description=None,
            zone_code="silver",
            connection_id=11,
            connection_code="MAIN",
            connection_name="Shared Silver",
            system_id=3,
            system_code="ERP",
            system_name="Enterprise Resource Planning",
            source_tenant_id=8,
            source_tenant_code="GRDM",
            source_tenant_name="Global Reference Data",
            attribute_count=0,
            batch_attribute_name=None,
            is_locked=False,
            is_active=True,
            attributes=(),
        )


class ReferenceCatalogRepository(CatalogRepository):
    async def list_rows(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        dataset: MetadataDataset,
        filters: tuple[MetadataFilter, ...],
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]:
        assert transaction is not None
        assert tenant_id == 7
        assert dataset == "zone"
        self.calls.append((limit, offset, filters))
        return (
            {
                "zone_code": "bronze",
                "zone_name": "Bronze",
                "zone_description": None,
                "is_active": True,
            },
        )


@pytest.mark.asyncio
async def test_database_dataset_detail_requires_selected_tenant_authorization() -> None:
    database = CatalogDatabase()
    service = DatabaseMetadataService(
        database=database,
        repository=CatalogRepository(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    result = await service.describe_dataset(
        principal,
        tenant_id=7,
        dataset="source_object",
    )

    assert result.dataset == "source_object"
    assert result.tenant_id == 7
    properties = result.row_schema["properties"]
    assert isinstance(properties, dict)
    assert tuple(properties) == result.columns
    assert database.transaction.authorization_calls == 1
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]


@pytest.mark.asyncio
async def test_database_reference_rows_require_selected_tenant_authorization() -> None:
    database = CatalogDatabase()
    repository = ReferenceCatalogRepository()
    service = DatabaseMetadataService(
        database=database,
        repository=repository,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = (MetadataFilter(field="zone_code", value="bronze"),)

    result = await service.list_rows(
        principal,
        tenant_id=7,
        dataset="zone",
        filters=filters,
        page_size=10,
        cursor=None,
    )

    assert result.items[0]["zone_name"] == "Bronze"
    assert repository.calls == [(11, 0, filters)]
    assert database.transaction.authorization_calls == 1
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]


@pytest.mark.asyncio
async def test_database_metadata_rows_reauthorize_and_use_query_bound_signed_paging() -> (
    None
):
    database = CatalogDatabase()
    repository = CatalogRepository()
    service = DatabaseMetadataService(
        database=database,
        repository=repository,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = (MetadataFilter(field="system_code", value="crm"),)

    first = await service.list_rows(
        principal,
        tenant_id=7,
        dataset="source_object",
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_rows(
        principal,
        tenant_id=7,
        dataset="source_object",
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item["object_name"] for item in first.items] == ["Customer"]
    assert [item["object_name"] for item in second.items] == ["Order"]
    assert second.next_cursor is None
    assert repository.calls == [(2, 0, filters), (2, 1, filters)]
    assert database.transaction.authorization_calls == 2
    assert database.isolations == [
        ReadIsolation.REPEATABLE_READ,
        ReadIsolation.REPEATABLE_READ,
    ]


def test_object_catalog_uses_only_normalized_zone_system_and_source_tenant_filters() -> (
    None
):
    service = StaticMetadataService()
    app = FastAPI()
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/metadata/objects",
            params={
                "zone": " Silver ",
                "system_code": " ERP ",
                "source_tenant_code": " GRDM ",
                "page_size": "1",
            },
        )

    assert response.status_code == 200
    assert service.object_filters == ObjectCatalogFilters(
        zone="silver",
        system_code="erp",
        source_tenant_code="grdm",
        active_state="active",
    )
    assert response.json()["items"] == [
        {
            "object_id": 101,
            "object_schema": "sales",
            "object_name": "CustomerSilver",
            "object_type_code": "TABLE",
            "zone_code": "silver",
            "connection_id": 11,
            "connection_code": "MAIN",
            "system_id": 3,
            "system_code": "ERP",
            "system_name": "Enterprise Resource Planning",
            "source_tenant_id": 8,
            "source_tenant_code": "GRDM",
            "source_tenant_name": "Global Reference Data",
            "attribute_count": 12,
            "batch_attribute_name": "UpdatedAt",
            "is_active": True,
        }
    ]
    assert "connection_value" not in response.text


@pytest.mark.asyncio
async def test_database_object_catalog_reauthorizes_and_bounds_repository_reads() -> (
    None
):
    database = CatalogDatabase()
    repository = CatalogRepository()
    service = DatabaseMetadataService(
        database=database,
        repository=repository,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = ObjectCatalogFilters(
        zone="silver",
        system_code="erp",
        source_tenant_code="grdm",
    )

    result = await service.list_objects(
        principal,
        tenant_id=7,
        filters=filters,
        page_size=1,
        cursor=None,
    )

    assert [item.object_id for item in result.items] == [101]
    assert repository.object_calls == [(2, 0, filters)]
    assert database.transaction.authorization_calls == 1
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]


def test_object_detail_returns_bounded_attributes_without_secret_or_raw_fields() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_metadata_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=StaticMetadataService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/metadata/objects/101")

    assert response.status_code == 200
    document = response.json()
    assert document["object_name"] == "CustomerSilver"
    assert document["source_tenant_code"] == "GRDM"
    assert document["attributes"] == [
        {
            "attribute_id": 501,
            "attribute_name": "CustomerId",
            "attribute_ordinal_position": 1,
            "attribute_description": "Customer identifier",
            "attribute_data_type": "bigint",
            "attribute_nullability": False,
            "is_surrogate_key": True,
            "is_natural_key": False,
            "is_meta_data": False,
            "is_masking_required": False,
            "is_mapped": True,
            "is_purge": False,
            "is_active": True,
        }
    ]
    assert "connection_value" not in response.text
    assert "raw" not in response.text.lower()
    assert "secret" not in response.text.lower()


@pytest.mark.asyncio
async def test_database_object_detail_reauthorizes_before_repository_read() -> None:
    database = CatalogDatabase()
    repository = CatalogRepository()
    service = DatabaseMetadataService(
        database=database,
        repository=repository,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    result = await service.get_object(principal, tenant_id=7, object_id=101)

    assert result.object_name == "CustomerSilver"
    assert repository.detail_calls == [(7, 101)]
    assert database.transaction.authorization_calls == 1
    assert database.isolations == [ReadIsolation.REPEATABLE_READ]
