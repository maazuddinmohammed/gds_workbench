from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.assertions import (
    AssertionDocumentDetail,
    AssertionDocumentFilters,
    AssertionDocumentPage,
    AssertionDocumentReference,
    AssertionDocumentSummary,
    AssertionPayloadNotSafeError,
    AssertionRecordDetail,
    AssertionRecordFilters,
    AssertionRecordPage,
    AssertionRecordSummary,
    DatabaseAssertionsService,
    SourceSystemReference,
    SourceTenantReference,
    create_assertions_router,
)


class StaticAssertionsService:
    document_filters: AssertionDocumentFilters | None = None
    record_filters: AssertionRecordFilters | None = None

    async def list_documents(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionDocumentFilters,
        page_size: int,
        cursor: str | None,
    ) -> AssertionDocumentPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.document_filters = filters
        return AssertionDocumentPage(
            model_id=18,
            model_revision=4,
            items=(
                AssertionDocumentSummary(
                    modeling_assertion_document_id=101,
                    workflow_run_id=None,
                    modeling_assertion_document_name="Customer rules",
                    modeling_assertion_document_type="business_rules",
                    source_tenant=SourceTenantReference(
                        tenant_id=8,
                        tenant_code="GRDM",
                        tenant_name="Global Reference Data",
                    ),
                    source_system=SourceSystemReference(
                        system_id=9,
                        system_code="CRM",
                        system_name="Customer Relationship Management",
                    ),
                    is_active=True,
                    record_count=3,
                    active_record_count=2,
                    locked_record_count=1,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_document(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        modeling_assertion_document_id: int,
    ) -> AssertionDocumentDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, modeling_assertion_document_id) == (7, 18, 101)
        return AssertionDocumentDetail(
            modeling_assertion_document_id=101,
            workflow_run_id=None,
            modeling_assertion_document_name="Customer rules",
            modeling_assertion_file_pattern="customer-rules-*.xlsx",
            modeling_assertion_document_type="business_rules",
            modeling_assertion_document_description="Governed Customer rules.",
            modeling_assertion_document_metadata={
                "source_kind": "workbook",
                "worksheet_count": 3,
            },
            source_tenant=SourceTenantReference(
                tenant_id=8,
                tenant_code="GRDM",
                tenant_name="Global Reference Data",
            ),
            source_system=SourceSystemReference(
                system_id=9,
                system_code="CRM",
                system_name="Customer Relationship Management",
            ),
            is_active=True,
            record_count=3,
            active_record_count=2,
            locked_record_count=1,
            agent_run_id=None,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def list_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionRecordFilters,
        page_size: int,
        cursor: str | None,
    ) -> AssertionRecordPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.record_filters = filters
        return AssertionRecordPage(
            model_id=18,
            model_revision=4,
            items=(
                AssertionRecordSummary(
                    modeling_assertion_record_id=201,
                    workflow_run_id=None,
                    document=AssertionDocumentReference(
                        modeling_assertion_document_id=101,
                        modeling_assertion_document_name="Customer rules",
                        modeling_assertion_document_type="business_rules",
                        source_tenant=SourceTenantReference(
                            tenant_id=8,
                            tenant_code="GRDM",
                            tenant_name="Global Reference Data",
                        ),
                        source_system=SourceSystemReference(
                            system_id=9,
                            system_code="CRM",
                            system_name="Customer Relationship Management",
                        ),
                        is_active=True,
                    ),
                    modeling_assertion_record_key="customer.one_per_party",
                    modeling_assertion_record_type="grain_rule",
                    modeling_assertion_applicable_layers=("conceptual", "logical"),
                    modeling_assertion_confidence="high",
                    modeling_assertion_record_status="active",
                    modeling_assertion_record_is_locked=True,
                    updated_at=datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_record(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        modeling_assertion_record_id: int,
    ) -> AssertionRecordDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, modeling_assertion_record_id) == (7, 18, 201)
        return AssertionRecordDetail(
            modeling_assertion_record_id=201,
            workflow_run_id=None,
            document=AssertionDocumentReference(
                modeling_assertion_document_id=101,
                modeling_assertion_document_name="Customer rules",
                modeling_assertion_document_type="business_rules",
                source_tenant=None,
                source_system=SourceSystemReference(
                    system_id=9,
                    system_code="CRM",
                    system_name="Customer Relationship Management",
                ),
                is_active=True,
            ),
            modeling_assertion_record_key="customer.one_per_party",
            modeling_assertion_record_type="grain_rule",
            modeling_assertion_text="A Customer represents one governed party.",
            modeling_assertion_details={
                "subject": "customer",
                "grain": "governed_party",
            },
            modeling_assertion_source_location={
                "sheet": "Customer",
                "row": 12,
            },
            modeling_assertion_applicable_layers=("conceptual", "logical"),
            modeling_assertion_confidence="high",
            modeling_assertion_record_status="active",
            modeling_assertion_record_is_locked=True,
            agent_run_id=None,
            created_at=datetime(2026, 8, 24, 13, 5, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_assertion_document_ledger_normalizes_exact_filters() -> None:
    service = StaticAssertionsService()
    app = FastAPI()
    app.include_router(
        create_assertions_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/assertions/documents",
            params={
                "source_system_id": "9",
                "source_system_code": "  CRM ",
                "active": "true",
                "name_prefix": "  Cust  ",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "model_id": 18,
        "model_revision": 4,
        "items": [
            {
                "modeling_assertion_document_id": 101,
                "workflow_run_id": None,
                "modeling_assertion_document_name": "Customer rules",
                "modeling_assertion_document_type": "business_rules",
                "source_tenant": {
                    "tenant_id": 8,
                    "tenant_code": "GRDM",
                    "tenant_name": "Global Reference Data",
                },
                "source_system": {
                    "system_id": 9,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "is_active": True,
                "record_count": 3,
                "active_record_count": 2,
                "locked_record_count": 1,
                "updated_at": "2026-08-24T14:00:00Z",
            }
        ],
        "next_cursor": None,
    }
    assert service.document_filters == AssertionDocumentFilters(
        source_system_id=9,
        source_system_code="crm",
        active=True,
        name_prefix="cust",
    )


def test_assertion_document_detail_returns_bounded_normalized_metadata() -> None:
    app = FastAPI()
    app.include_router(
        create_assertions_router(
            identity_provider=_identity_provider(),
            service=StaticAssertionsService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/assertions/documents/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_run_id"] is None
    assert payload["modeling_assertion_document_metadata"] == {
        "source_kind": "workbook",
        "worksheet_count": 3,
    }
    assert payload["modeling_assertion_file_pattern"] == "customer-rules-*.xlsx"
    assert "file_content" not in response.text


def test_assertion_record_ledger_normalizes_review_filters() -> None:
    service = StaticAssertionsService()
    app = FastAPI()
    app.include_router(
        create_assertions_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/assertions/records",
            params={
                "document_id": "101",
                "document_name": "  Customer Rules ",
                "source_system_id": "9",
                "source_system_code": " CRM ",
                "status": "INACTIVE",
                "locked": "true",
                "applicable_layer": "CONCEPTUAL",
                "key_prefix": " Customer. ",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_revision"] == 4
    assert payload["items"][0]["workflow_run_id"] is None
    assert payload["items"][0]["document"]["source_system"]["system_code"] == "CRM"
    assert payload["items"][0]["modeling_assertion_record_key"] == (
        "customer.one_per_party"
    )
    assert "modeling_assertion_text" not in payload["items"][0]
    assert service.record_filters == AssertionRecordFilters(
        document_id=101,
        document_name="customer rules",
        source_system_id=9,
        source_system_code="crm",
        status="inactive",
        locked=True,
        applicable_layer="conceptual",
        key_prefix="customer.",
    )


def test_assertion_record_detail_returns_full_normalized_assertion() -> None:
    app = FastAPI()
    app.include_router(
        create_assertions_router(
            identity_provider=_identity_provider(),
            service=StaticAssertionsService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/assertions/records/201")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_run_id"] is None
    assert payload["modeling_assertion_text"] == (
        "A Customer represents one governed party."
    )
    assert payload["modeling_assertion_details"] == {
        "subject": "customer",
        "grain": "governed_party",
    }
    assert payload["modeling_assertion_source_location"] == {
        "sheet": "Customer",
        "row": 12,
    }
    assert "workbook_content" not in response.text
    assert "raw_rows" not in response.text


class AssertionsTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_model.model_revision" in query:
            assert parameters == (7, 18)
            return {"model_revision": 4}
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
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
        assert "model.modeling_assertion_document AS document" in query
        assert "target_model.tenant_id = %s" in query
        assert parameters[:10] == (
            7,
            18,
            9,
            9,
            "crm",
            "crm",
            True,
            True,
            "cust",
            "cust",
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "modeling_assertion_document_id": 101,
                "workflow_run_id": None,
                "modeling_assertion_document_name": "Customer rules",
                "modeling_assertion_document_type": "business_rules",
                "source_tenant": {
                    "tenant_id": 8,
                    "tenant_code": "GRDM",
                    "tenant_name": "Global Reference Data",
                },
                "source_system": {
                    "system_id": 9,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "is_active": True,
                "record_count": 3,
                "active_record_count": 2,
                "locked_record_count": 1,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "modeling_assertion_document_id": 102,
                "workflow_run_id": 81,
                "modeling_assertion_document_name": "Customer privacy rules",
                "modeling_assertion_document_type": "business_rules",
                "source_tenant": None,
                "source_system": {
                    "system_id": 9,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "is_active": True,
                "record_count": 1,
                "active_record_count": 1,
                "locked_record_count": 0,
                "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class AssertionsDatabase:
    def __init__(self) -> None:
        self.transaction = AssertionsTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AssertionsTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


@pytest.mark.asyncio
async def test_database_assertion_documents_are_authorized_and_cursor_bound() -> None:
    database = AssertionsDatabase()
    service = DatabaseAssertionsService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    filters = AssertionDocumentFilters(
        source_system_id=9,
        source_system_code="crm",
        active=True,
        name_prefix="cust",
    )

    first = await service.list_documents(
        _principal(),
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_documents(
        _principal(),
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert first.model_revision == 4
    assert [item.modeling_assertion_document_id for item in first.items] == [101]
    assert [item.modeling_assertion_document_id for item in second.items] == [102]
    assert second.items[0].workflow_run_id == 81
    assert database.transaction.offsets == [0, 1]

    with pytest.raises(InvalidRequestError):
        await service.list_documents(
            _principal(),
            tenant_id=7,
            model_id=18,
            filters=AssertionDocumentFilters(name_prefix="privacy"),
            page_size=1,
            cursor=first.next_cursor,
        )


class AssertionRecordsTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_model.model_revision" in query:
            assert parameters == (7, 18)
            return {"model_revision": 4}
        assert "security.entra_principal_identity" in query
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
        assert "model.modeling_assertion_record AS record" in query
        assert parameters[:19] == (
            7,
            18,
            101,
            101,
            "customer rules",
            "customer rules",
            9,
            9,
            "crm",
            "crm",
            "inactive",
            "inactive",
            True,
            True,
            "conceptual",
            "conceptual",
            "customer.",
            "customer.",
            "customer.",
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "modeling_assertion_record_id": 201,
                "workflow_run_id": None,
                "document": {
                    "modeling_assertion_document_id": 101,
                    "modeling_assertion_document_name": "Customer rules",
                    "modeling_assertion_document_type": "business_rules",
                    "source_tenant": None,
                    "source_system": {
                        "system_id": 9,
                        "system_code": "CRM",
                        "system_name": "Customer Relationship Management",
                    },
                    "is_active": True,
                },
                "modeling_assertion_record_key": "customer.one_per_party",
                "modeling_assertion_record_type": "grain_rule",
                "modeling_assertion_applicable_layers": ["conceptual", "logical"],
                "modeling_assertion_confidence": "high",
                "modeling_assertion_record_status": "active",
                "modeling_assertion_record_is_locked": True,
                "updated_at": datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
            },
            {
                "modeling_assertion_record_id": 202,
                "workflow_run_id": 81,
                "document": {
                    "modeling_assertion_document_id": 101,
                    "modeling_assertion_document_name": "Customer rules",
                    "modeling_assertion_document_type": "business_rules",
                    "source_tenant": None,
                    "source_system": {
                        "system_id": 9,
                        "system_code": "CRM",
                        "system_name": "Customer Relationship Management",
                    },
                    "is_active": True,
                },
                "modeling_assertion_record_key": "customer.primary_address",
                "modeling_assertion_record_type": "relationship_rule",
                "modeling_assertion_applicable_layers": ["conceptual"],
                "modeling_assertion_confidence": "medium",
                "modeling_assertion_record_status": "active",
                "modeling_assertion_record_is_locked": True,
                "updated_at": datetime(2026, 8, 24, 14, 6, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class AssertionRecordsDatabase:
    def __init__(self) -> None:
        self.transaction = AssertionRecordsTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AssertionRecordsTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_assertion_records_apply_every_normalized_filter() -> None:
    database = AssertionRecordsDatabase()
    service = DatabaseAssertionsService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    filters = AssertionRecordFilters(
        document_id=101,
        document_name="customer rules",
        source_system_id=9,
        source_system_code="crm",
        status="inactive",
        locked=True,
        applicable_layer="conceptual",
        key_prefix="customer.",
    )

    first = await service.list_records(
        _principal(),
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_records(
        _principal(),
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.modeling_assertion_record_id for item in first.items] == [201]
    assert [item.modeling_assertion_record_id for item in second.items] == [202]
    assert second.items[0].workflow_run_id == 81
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]


class AssertionDetailTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
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
        assert "document.modeling_assertion_document_metadata" in query
        assert parameters == (7, 18, 101)
        return {
            "modeling_assertion_document_id": 101,
            "workflow_run_id": None,
            "modeling_assertion_document_name": "Customer rules",
            "modeling_assertion_file_pattern": "customer-rules-*.xlsx",
            "modeling_assertion_document_type": "business_rules",
            "modeling_assertion_document_description": "Governed Customer rules.",
            "modeling_assertion_document_metadata": {
                "source_kind": "workbook",
                "worksheet_count": 3,
            },
            "metadata_is_oversized": False,
            "source_tenant": None,
            "source_system": {
                "system_id": 9,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
            },
            "is_active": True,
            "record_count": 3,
            "active_record_count": 2,
            "locked_record_count": 1,
            "agent_run_id": None,
            "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class AssertionDetailDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AssertionDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield AssertionDetailTransaction()


@pytest.mark.asyncio
async def test_database_assertion_document_detail_is_model_and_tenant_scoped() -> None:
    service = DatabaseAssertionsService(
        database=AssertionDetailDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    detail = await service.read_document(
        _principal(),
        tenant_id=7,
        model_id=18,
        modeling_assertion_document_id=101,
    )

    assert detail.workflow_run_id is None
    assert detail.modeling_assertion_document_metadata == {
        "source_kind": "workbook",
        "worksheet_count": 3,
    }
    assert detail.source_system is not None
    assert detail.source_system.system_code == "CRM"


class AssertionRecordDetailTransaction:
    def __init__(self, *, unsafe: bool = False) -> None:
        self.unsafe = unsafe

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
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
        assert "record.modeling_assertion_text" in query
        assert parameters == (7, 18, 201)
        return {
            "modeling_assertion_record_id": 201,
            "workflow_run_id": None,
            "document": {
                "modeling_assertion_document_id": 101,
                "modeling_assertion_document_name": "Customer rules",
                "modeling_assertion_document_type": "business_rules",
                "source_tenant": None,
                "source_system": None,
                "is_active": True,
            },
            "modeling_assertion_record_key": "customer.one_per_party",
            "modeling_assertion_record_type": "grain_rule",
            "modeling_assertion_text": "A Customer is one governed party.",
            "text_is_oversized": False,
            "modeling_assertion_details": (
                {"raw_rows": [["private"]]}
                if self.unsafe
                else {"subject": "customer", "grain": "governed_party"}
            ),
            "details_are_oversized": False,
            "modeling_assertion_source_location": {"sheet": "Customer", "row": 12},
            "source_location_is_oversized": False,
            "modeling_assertion_applicable_layers": ["conceptual", "logical"],
            "modeling_assertion_confidence": "high",
            "modeling_assertion_record_status": "active",
            "modeling_assertion_record_is_locked": True,
            "agent_run_id": None,
            "created_at": datetime(2026, 8, 24, 13, 5, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class AssertionRecordDetailDatabase:
    def __init__(self, *, unsafe: bool = False) -> None:
        self.unsafe = unsafe

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AssertionRecordDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield AssertionRecordDetailTransaction(unsafe=self.unsafe)


@pytest.mark.asyncio
async def test_database_assertion_record_detail_returns_governed_json_only() -> None:
    service = DatabaseAssertionsService(
        database=AssertionRecordDetailDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    detail = await service.read_record(
        _principal(),
        tenant_id=7,
        model_id=18,
        modeling_assertion_record_id=201,
    )

    assert detail.workflow_run_id is None
    assert detail.modeling_assertion_details == {
        "subject": "customer",
        "grain": "governed_party",
    }
    assert detail.modeling_assertion_source_location == {
        "sheet": "Customer",
        "row": 12,
    }


@pytest.mark.asyncio
async def test_database_assertion_record_detail_rejects_raw_row_dumps() -> None:
    service = DatabaseAssertionsService(
        database=AssertionRecordDetailDatabase(unsafe=True),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    with pytest.raises(AssertionPayloadNotSafeError):
        await service.read_record(
            _principal(),
            tenant_id=7,
            model_id=18,
            modeling_assertion_record_id=201,
        )
