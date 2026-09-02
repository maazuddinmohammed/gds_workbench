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

from gds_workbench_api.features.conceptual import (
    AssertionRecordReference,
    ConceptualAssertionSupport,
    ConceptualFilters,
    ConceptualObjectDetail,
    ConceptualObjectPage,
    ConceptualObjectSummary,
    ConceptualObjectSupport,
    ConceptualRelationshipDetail,
    ConceptualRelationshipPage,
    ConceptualRelationshipSummary,
    ConceptualSupportLimitExceededError,
    DatabaseConceptualService,
    PhysicalObjectReference,
    create_conceptual_router,
)


class StaticConceptualService:
    object_filters: ConceptualFilters | None = None

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ConceptualFilters,
        page_size: int,
        cursor: str | None,
    ) -> ConceptualObjectPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.object_filters = filters
        return ConceptualObjectPage(
            model_id=18,
            model_revision=4,
            items=(
                ConceptualObjectSummary(
                    conceptual_object_id=101,
                    workflow_run_id=None,
                    conceptual_object_name="Customer",
                    conceptual_object_type="business_entity",
                    conceptual_object_confidence="high",
                    conceptual_object_status="active",
                    conceptual_object_is_locked=False,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        conceptual_object_id: int,
    ) -> ConceptualObjectDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, conceptual_object_id) == (7, 18, 101)
        return ConceptualObjectDetail(
            conceptual_object_id=101,
            workflow_run_id=None,
            conceptual_object_name="Customer",
            conceptual_object_definition="A governed party receiving services.",
            conceptual_object_type="business_entity",
            conceptual_object_grain="One governed party",
            conceptual_object_aliases=("Client",),
            conceptual_object_confidence="high",
            conceptual_object_status="active",
            conceptual_object_is_locked=False,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            supports=(
                ConceptualObjectSupport(
                    conceptual_support_id=301,
                    workflow_run_id=None,
                    support_source_type="object",
                    source_object=PhysicalObjectReference(
                        object_id=501,
                        tenant_code="GRDM",
                        system_code="CRM",
                        connection_code="crm_prod",
                        object_schema="bronze_crm",
                        object_name="customer_raw",
                    ),
                    support_role="primary",
                    support_reason="Supplies Customer identity.",
                    support_reason_detail=None,
                    support_confidence="high",
                    support_status="active",
                    support_is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
                ConceptualAssertionSupport(
                    conceptual_support_id=302,
                    workflow_run_id=81,
                    support_source_type="assertion",
                    assertion_record=AssertionRecordReference(
                        modeling_assertion_record_id=701,
                        modeling_assertion_record_key="customer.one_per_party",
                        modeling_assertion_document_name="customer_domain_rules",
                        modeling_assertion_record_type="grain_rule",
                        modeling_assertion_text="A Customer is one governed party.",
                        modeling_assertion_confidence="high",
                        modeling_assertion_record_status="active",
                    ),
                    support_role="business_rule",
                    support_reason="Confirms the grain.",
                    support_reason_detail=None,
                    support_confidence="high",
                    support_status="active",
                    support_is_locked=True,
                    created_at=datetime(2026, 8, 24, 13, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 1, tzinfo=UTC),
                ),
            ),
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ConceptualFilters,
        page_size: int,
        cursor: str | None,
    ) -> ConceptualRelationshipPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        assert filters == ConceptualFilters(
            status="active",
            locked=True,
            name_exact="customer places order",
        )
        return ConceptualRelationshipPage(
            model_id=18,
            model_revision=4,
            items=(
                ConceptualRelationshipSummary(
                    conceptual_relationship_id=201,
                    workflow_run_id=None,
                    from_conceptual_object_id=101,
                    from_conceptual_object_name="Customer",
                    to_conceptual_object_id=102,
                    to_conceptual_object_name="Order",
                    conceptual_relationship_name="Customer places Order",
                    conceptual_relationship_type="association",
                    conceptual_relationship_cardinality="one_to_many",
                    conceptual_relationship_confidence="high",
                    conceptual_relationship_status="active",
                    conceptual_relationship_is_locked=True,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        conceptual_relationship_id: int,
    ) -> ConceptualRelationshipDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, conceptual_relationship_id) == (7, 18, 201)
        return ConceptualRelationshipDetail(
            conceptual_relationship_id=201,
            workflow_run_id=None,
            from_conceptual_object_id=101,
            from_conceptual_object_name="Customer",
            to_conceptual_object_id=102,
            to_conceptual_object_name="Order",
            conceptual_relationship_name="Customer places Order",
            conceptual_relationship_type="association",
            conceptual_relationship_definition="A Customer may place Orders.",
            conceptual_relationship_cardinality="one_to_many",
            conceptual_relationship_basis="Customer and Order metadata.",
            conceptual_relationship_cardinality_basis="Observed Customer keys.",
            conceptual_relationship_confidence="high",
            conceptual_relationship_status="active",
            conceptual_relationship_is_locked=True,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            supports=(
                ConceptualAssertionSupport(
                    conceptual_support_id=303,
                    workflow_run_id=None,
                    support_source_type="assertion",
                    assertion_record=AssertionRecordReference(
                        modeling_assertion_record_id=702,
                        modeling_assertion_record_key="order.customer",
                        modeling_assertion_document_name="order_rules",
                        modeling_assertion_record_type="relationship_rule",
                        modeling_assertion_text="Each Order belongs to a Customer.",
                        modeling_assertion_confidence="high",
                        modeling_assertion_record_status="active",
                    ),
                    support_role="cardinality",
                    support_reason="Defines the relationship.",
                    support_reason_detail=None,
                    support_confidence="high",
                    support_status="active",
                    support_is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
            ),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_conceptual_object_ledger_normalizes_review_filters() -> None:
    service = StaticConceptualService()
    app = FastAPI()
    app.include_router(
        create_conceptual_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/conceptual/objects",
            params={
                "status": "INACTIVE",
                "locked": "false",
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
                "conceptual_object_id": 101,
                "workflow_run_id": None,
                "conceptual_object_name": "Customer",
                "conceptual_object_type": "business_entity",
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "updated_at": "2026-08-24T14:00:00Z",
            }
        ],
        "next_cursor": None,
    }
    assert service.object_filters == ConceptualFilters(
        status="inactive",
        locked=False,
        name_prefix="cust",
    )


def test_conceptual_ledger_rejects_ambiguous_name_filters() -> None:
    app = FastAPI()
    app.include_router(
        create_conceptual_router(
            identity_provider=_identity_provider(),
            service=StaticConceptualService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/conceptual/objects",
            params={"name_exact": "Customer", "name_prefix": "Cust"},
        )

    assert response.status_code == 422


def test_conceptual_object_detail_returns_typed_normalized_support_rows() -> None:
    app = FastAPI()
    app.include_router(
        create_conceptual_router(
            identity_provider=_identity_provider(),
            service=StaticConceptualService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/conceptual/objects/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload["conceptual_object_definition"] == (
        "A governed party receiving services."
    )
    assert payload["workflow_run_id"] is None
    assert payload["supports"][0]["support_source_type"] == "object"
    assert payload["supports"][0]["source_object"]["object_name"] == "customer_raw"
    assert payload["supports"][1]["support_source_type"] == "assertion"
    assert (
        payload["supports"][1]["assertion_record"]["modeling_assertion_record_key"]
        == "customer.one_per_party"
    )
    assert "modeling_assertion_details" not in response.text


def test_conceptual_relationship_ledger_normalizes_review_filters() -> None:
    app = FastAPI()
    app.include_router(
        create_conceptual_router(
            identity_provider=_identity_provider(),
            service=StaticConceptualService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/conceptual/relationships",
            params={
                "status": "ACTIVE",
                "locked": "true",
                "name_exact": "  Customer Places Order  ",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_revision"] == 4
    assert payload["items"][0]["workflow_run_id"] is None
    assert payload["items"][0]["from_conceptual_object_name"] == "Customer"
    assert payload["items"][0]["to_conceptual_object_name"] == "Order"
    assert payload["items"][0]["conceptual_relationship_cardinality"] == ("one_to_many")


def test_conceptual_relationship_detail_returns_full_basis_and_typed_support() -> None:
    app = FastAPI()
    app.include_router(
        create_conceptual_router(
            identity_provider=_identity_provider(),
            service=StaticConceptualService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/conceptual/relationships/201"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conceptual_relationship_definition"] == (
        "A Customer may place Orders."
    )
    assert payload["conceptual_relationship_basis"] == ("Customer and Order metadata.")
    assert payload["conceptual_relationship_cardinality_basis"] == (
        "Observed Customer keys."
    )
    assert payload["supports"][0]["support_source_type"] == "assertion"
    assert payload["supports"][0]["workflow_run_id"] is None


class ConceptualTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_model.model_revision" in query:
            assert "target_model.tenant_id = %s" in query
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
        assert "JOIN model.model AS target_model" in query
        assert "target_model.tenant_id = %s" in query
        assert parameters[:10] == (
            7,
            18,
            "active",
            "active",
            False,
            False,
            None,
            None,
            "cust",
            "cust",
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "conceptual_object_id": 101,
                "workflow_run_id": None,
                "conceptual_object_name": "Customer",
                "conceptual_object_type": "business_entity",
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "conceptual_object_id": 102,
                "workflow_run_id": 81,
                "conceptual_object_name": "Customer Account",
                "conceptual_object_type": "business_entity",
                "conceptual_object_confidence": "medium",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class ConceptualDatabase:
    def __init__(self) -> None:
        self.transaction = ConceptualTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ConceptualTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_conceptual_objects_are_authorized_and_cursor_bound() -> None:
    database = ConceptualDatabase()
    service = DatabaseConceptualService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = ConceptualFilters(
        status="active",
        locked=False,
        name_prefix="cust",
    )

    first = await service.list_objects(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_objects(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert first.model_revision == 4
    assert [item.conceptual_object_name for item in first.items] == ["Customer"]
    assert [item.conceptual_object_name for item in second.items] == [
        "Customer Account"
    ]
    assert second.items[0].workflow_run_id == 81
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]

    with pytest.raises(InvalidRequestError):
        await service.list_objects(
            principal,
            tenant_id=7,
            model_id=18,
            filters=ConceptualFilters(name_prefix="customer account"),
            page_size=1,
            cursor=first.next_cursor,
        )


class ConceptualDetailTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "object.conceptual_object_definition" in query:
            assert "JOIN model.model AS target_model" in query
            assert "target_model.tenant_id = %s" in query
            assert parameters == (7, 18, 101)
            return {
                "conceptual_object_id": 101,
                "workflow_run_id": None,
                "conceptual_object_name": "Customer",
                "conceptual_object_definition": (
                    "A governed party receiving services."
                ),
                "conceptual_object_type": "business_entity",
                "conceptual_object_grain": "One governed party",
                "conceptual_object_aliases": ["Client"],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
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
        assert "FROM workflow.conceptual_support AS support" in query
        assert "JOIN model.model AS target_model" in query
        assert "jsonb_agg" not in query
        assert parameters == (7, 18, 101, 2001)
        common = {
            "support_role": "primary",
            "support_reason": "Supplies Customer identity.",
            "support_reason_detail": None,
            "support_confidence": "high",
            "support_status": "active",
            "support_is_locked": False,
            "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        }
        return [
            {
                **common,
                "conceptual_support_id": 301,
                "workflow_run_id": None,
                "support_source_type": "object",
                "source_object_id": 501,
                "source_tenant_code": "GRDM",
                "source_system_code": "CRM",
                "source_connection_code": "crm_prod",
                "source_object_schema": "bronze_crm",
                "source_object_name": "customer_raw",
                "modeling_assertion_record_id": None,
            },
            {
                **common,
                "conceptual_support_id": 302,
                "workflow_run_id": 81,
                "support_source_type": "assertion",
                "source_object_id": None,
                "modeling_assertion_record_id": 701,
                "modeling_assertion_record_key": "customer.one_per_party",
                "modeling_assertion_document_name": "customer_domain_rules",
                "modeling_assertion_record_type": "grain_rule",
                "modeling_assertion_text": "A Customer is one governed party.",
                "modeling_assertion_confidence": "high",
                "modeling_assertion_record_status": "active",
            },
        ]


class ConceptualDetailDatabase:
    def __init__(self) -> None:
        self.transaction = ConceptualDetailTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ConceptualDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_conceptual_object_detail_reads_every_normalized_support() -> (
    None
):
    service = DatabaseConceptualService(
        database=ConceptualDetailDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_object(
        principal,
        tenant_id=7,
        model_id=18,
        conceptual_object_id=101,
    )

    assert detail.workflow_run_id is None
    assert len(detail.supports) == 2
    assert isinstance(detail.supports[0], ConceptualObjectSupport)
    assert detail.supports[0].source_object.object_name == "customer_raw"
    assert isinstance(detail.supports[1], ConceptualAssertionSupport)
    assert (
        detail.supports[1].assertion_record.modeling_assertion_record_key
        == "customer.one_per_party"
    )


class ConceptualSupportOverflowTransaction(ConceptualDetailTransaction):
    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "FROM workflow.conceptual_support AS support" in query
        assert parameters == (7, 18, 101, 2001)
        return [{} for _ in range(2001)]


class ConceptualSupportOverflowDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ConceptualSupportOverflowTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield ConceptualSupportOverflowTransaction()


@pytest.mark.asyncio
async def test_conceptual_detail_fails_closed_above_the_support_bound() -> None:
    service = DatabaseConceptualService(
        database=ConceptualSupportOverflowDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(ConceptualSupportLimitExceededError):
        await service.read_object(
            principal,
            tenant_id=7,
            model_id=18,
            conceptual_object_id=101,
        )


class ConceptualRelationshipTransaction:
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
        assert "FROM workflow.conceptual_relationship AS relationship" in query
        assert "JOIN model.model AS target_model" in query
        assert "from_object.model_id = relationship.model_id" in query
        assert "to_object.model_id = relationship.model_id" in query
        assert parameters[:10] == (
            7,
            18,
            "active",
            "active",
            True,
            True,
            "customer places order",
            "customer places order",
            None,
            None,
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "conceptual_relationship_id": 201,
                "workflow_run_id": None,
                "from_conceptual_object_id": 101,
                "from_conceptual_object_name": "Customer",
                "to_conceptual_object_id": 102,
                "to_conceptual_object_name": "Order",
                "conceptual_relationship_name": "Customer places Order",
                "conceptual_relationship_type": "association",
                "conceptual_relationship_cardinality": "one_to_many",
                "conceptual_relationship_confidence": "high",
                "conceptual_relationship_status": "active",
                "conceptual_relationship_is_locked": True,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "conceptual_relationship_id": 202,
                "workflow_run_id": 82,
                "from_conceptual_object_id": 101,
                "from_conceptual_object_name": "Customer",
                "to_conceptual_object_id": 103,
                "to_conceptual_object_name": "Invoice",
                "conceptual_relationship_name": "Customer receives Invoice",
                "conceptual_relationship_type": "association",
                "conceptual_relationship_cardinality": "one_to_many",
                "conceptual_relationship_confidence": "high",
                "conceptual_relationship_status": "active",
                "conceptual_relationship_is_locked": True,
                "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class ConceptualRelationshipDatabase:
    def __init__(self) -> None:
        self.transaction = ConceptualRelationshipTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ConceptualRelationshipTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_conceptual_relationships_are_authorized_and_cursor_bound() -> (
    None
):
    database = ConceptualRelationshipDatabase()
    service = DatabaseConceptualService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = ConceptualFilters(
        status="active",
        locked=True,
        name_exact="customer places order",
    )

    first = await service.list_relationships(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_relationships(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert first.model_revision == 4
    assert [item.conceptual_relationship_id for item in first.items] == [201]
    assert [item.conceptual_relationship_id for item in second.items] == [202]
    assert second.items[0].workflow_run_id == 82
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]


class ConceptualRelationshipDetailTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "relationship.conceptual_relationship_definition" in query:
            assert "JOIN model.model AS target_model" in query
            assert "from_object.model_id = relationship.model_id" in query
            assert "to_object.model_id = relationship.model_id" in query
            assert parameters == (7, 18, 201)
            return {
                "conceptual_relationship_id": 201,
                "workflow_run_id": None,
                "from_conceptual_object_id": 101,
                "from_conceptual_object_name": "Customer",
                "to_conceptual_object_id": 102,
                "to_conceptual_object_name": "Order",
                "conceptual_relationship_name": "Customer places Order",
                "conceptual_relationship_type": "association",
                "conceptual_relationship_definition": ("A Customer may place Orders."),
                "conceptual_relationship_cardinality": "one_to_many",
                "conceptual_relationship_basis": "Customer and Order metadata.",
                "conceptual_relationship_cardinality_basis": (
                    "Observed Customer keys."
                ),
                "conceptual_relationship_confidence": "high",
                "conceptual_relationship_status": "active",
                "conceptual_relationship_is_locked": True,
                "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
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
        assert "FROM workflow.conceptual_support AS support" in query
        assert "JOIN workflow.conceptual_relationship AS relationship" in query
        assert "jsonb_agg" not in query
        assert parameters == (7, 18, 201, 2001)
        return [
            {
                "conceptual_support_id": 303,
                "workflow_run_id": None,
                "support_source_type": "assertion",
                "support_role": "cardinality",
                "support_reason": "Defines the relationship.",
                "support_reason_detail": None,
                "support_confidence": "high",
                "support_status": "active",
                "support_is_locked": False,
                "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                "source_object_id": None,
                "modeling_assertion_record_id": 702,
                "modeling_assertion_record_key": "order.customer",
                "modeling_assertion_document_name": "order_rules",
                "modeling_assertion_record_type": "relationship_rule",
                "modeling_assertion_text": "Each Order belongs to a Customer.",
                "modeling_assertion_confidence": "high",
                "modeling_assertion_record_status": "active",
            }
        ]


class ConceptualRelationshipDetailDatabase:
    def __init__(self) -> None:
        self.transaction = ConceptualRelationshipDetailTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ConceptualRelationshipDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_conceptual_relationship_detail_reads_normalized_support() -> (
    None
):
    service = DatabaseConceptualService(
        database=ConceptualRelationshipDetailDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_relationship(
        principal,
        tenant_id=7,
        model_id=18,
        conceptual_relationship_id=201,
    )

    assert detail.workflow_run_id is None
    assert detail.conceptual_relationship_basis == "Customer and Order metadata."
    assert len(detail.supports) == 1
    assert isinstance(detail.supports[0], ConceptualAssertionSupport)
    assert detail.supports[0].workflow_run_id is None
