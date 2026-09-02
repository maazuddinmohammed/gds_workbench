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

from gds_workbench_api.features.logical import (
    AssertionRecordReference,
    DatabaseLogicalService,
    LogicalAssertionSource,
    LogicalAttributeDetail,
    LogicalAttributeFilters,
    LogicalAttributePage,
    LogicalAttributePhysicalSource,
    LogicalAttributeSummary,
    LogicalEntityDetail,
    LogicalEntityFilters,
    LogicalEntityPage,
    LogicalEntitySummary,
    LogicalObjectSource,
    LogicalRelationshipDetail,
    LogicalRelationshipFilters,
    LogicalRelationshipPage,
    LogicalRelationshipSummary,
    LogicalSubmodelDetail,
    LogicalSubmodelEntityMembership,
    LogicalSubmodelMembership,
    LogicalSubmodelPage,
    LogicalSubmodelSummary,
    ModeledFilters,
    PhysicalAttributeReference,
    PhysicalObjectReference,
    create_logical_router,
)


class StaticLogicalService:
    filters: LogicalEntityFilters | None = None

    async def list_entities(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalEntityFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalEntityPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.filters = filters
        return LogicalEntityPage(
            model_id=18,
            model_revision=4,
            items=(
                LogicalEntitySummary(
                    logical_entity_id=101,
                    workflow_run_id=None,
                    logical_entity_name="Customer",
                    logical_entity_type="core",
                    logical_entity_dependency_order=0,
                    logical_entity_confidence="high",
                    logical_entity_status="active",
                    logical_entity_is_locked=False,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_entity(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_entity_id: int,
    ) -> LogicalEntityDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, logical_entity_id) == (7, 18, 101)
        return LogicalEntityDetail(
            logical_entity_id=101,
            workflow_run_id=None,
            logical_entity_name="Customer",
            logical_entity_definition="One governed customer.",
            logical_entity_type="core",
            logical_entity_type_detail=None,
            logical_entity_grain="One row per customer.",
            logical_entity_dependency_order=0,
            logical_entity_confidence="high",
            logical_entity_status="active",
            logical_entity_is_locked=False,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            submodels=(
                LogicalSubmodelMembership(
                    logical_entity_submodel_id=201,
                    workflow_run_id=None,
                    logical_submodel_id=301,
                    logical_submodel_name="Customer Domain",
                    membership_status="active",
                    membership_is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
            ),
            sources=(
                LogicalObjectSource(
                    logical_entity_source_mapping_id=401,
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
                    source_order=1,
                    rationale="Supplies Customer identity.",
                    status="active",
                    is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
                LogicalAssertionSource(
                    logical_entity_source_mapping_id=402,
                    workflow_run_id=81,
                    support_source_type="assertion",
                    assertion_record=AssertionRecordReference(
                        modeling_assertion_record_id=601,
                        modeling_assertion_record_key="customer.grain",
                        modeling_assertion_document_name="customer_rules",
                        modeling_assertion_record_type="grain_rule",
                        modeling_assertion_text="One row represents one Customer.",
                        modeling_assertion_confidence="high",
                        modeling_assertion_record_status="active",
                    ),
                    source_order=None,
                    rationale="Defines the grain.",
                    status="active",
                    is_locked=True,
                    created_at=datetime(2026, 8, 24, 13, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 1, tzinfo=UTC),
                ),
            ),
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalAttributePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        assert filters == LogicalAttributeFilters(
            status="active",
            name_exact="customer id",
            logical_entity_id=101,
        )
        return LogicalAttributePage(
            model_id=18,
            model_revision=4,
            items=(
                LogicalAttributeSummary(
                    logical_attribute_id=701,
                    workflow_run_id=None,
                    logical_entity_id=101,
                    logical_entity_name="Customer",
                    logical_attribute_name="Customer ID",
                    logical_attribute_data_type="BIGINT",
                    logical_attribute_is_nullable=False,
                    logical_attribute_is_primary_key=True,
                    logical_attribute_is_natural_key=False,
                    logical_attribute_is_surrogate_key=True,
                    logical_attribute_ordinal_position=1,
                    logical_attribute_is_audit_column=False,
                    logical_attribute_status="active",
                    logical_attribute_is_locked=False,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_attribute_id: int,
    ) -> LogicalAttributeDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, logical_attribute_id) == (7, 18, 701)
        return LogicalAttributeDetail(
            logical_attribute_id=701,
            workflow_run_id=None,
            logical_entity_id=101,
            logical_entity_name="Customer",
            logical_attribute_name="Customer ID",
            logical_attribute_definition="Stable warehouse identifier.",
            logical_attribute_data_type="BIGINT",
            logical_attribute_is_nullable=False,
            logical_attribute_is_primary_key=True,
            logical_attribute_is_natural_key=False,
            logical_attribute_is_surrogate_key=True,
            logical_attribute_ordinal_position=1,
            logical_attribute_is_audit_column=False,
            logical_attribute_status="active",
            logical_attribute_is_locked=False,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            sources=(
                LogicalAttributePhysicalSource(
                    logical_attribute_source_mapping_id=801,
                    workflow_run_id=None,
                    logical_entity_source_mapping_id=401,
                    support_source_type="attribute",
                    source_attribute=PhysicalAttributeReference(
                        object_id=501,
                        attribute_id=502,
                        tenant_code="GRDM",
                        system_code="CRM",
                        connection_code="crm_prod",
                        object_schema="bronze_crm",
                        object_name="customer_raw",
                        attribute_name="customer_id",
                    ),
                    source_order=1,
                    rationale="Maps the stable Customer identifier.",
                    status="active",
                    is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
            ),
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: LogicalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalRelationshipPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == LogicalRelationshipFilters(
            status="inactive",
            locked=True,
            logical_entity_id=102,
        )
        return LogicalRelationshipPage(
            model_id=18,
            model_revision=4,
            items=(self._relationship(),),
            next_cursor=None,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_relationship_id: int,
    ) -> LogicalRelationshipDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, logical_relationship_id) == (7, 18, 901)
        relationship = self._relationship()
        return LogicalRelationshipDetail(
            **relationship.model_dump(),
            logical_relationship_definition="Each Order references one Customer.",
            logical_relationship_basis="The governed Customer key appears on Order.",
            logical_relationship_cardinality_basis="Observed and asserted key usage.",
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )

    @staticmethod
    def _relationship() -> LogicalRelationshipSummary:
        return LogicalRelationshipSummary(
            logical_relationship_id=901,
            workflow_run_id=None,
            from_logical_entity_id=102,
            from_logical_entity_name="Order",
            from_logical_attribute_id=702,
            from_logical_attribute_name="Customer ID",
            to_logical_entity_id=101,
            to_logical_entity_name="Customer",
            to_logical_attribute_id=701,
            to_logical_attribute_name="Customer ID",
            logical_relationship_name="Order references Customer",
            logical_relationship_cardinality="many_to_one",
            logical_relationship_confidence="high",
            logical_relationship_status="active",
            logical_relationship_is_locked=True,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def list_submodels(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ModeledFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalSubmodelPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == ModeledFilters(status="active", name_prefix="customer")
        return LogicalSubmodelPage(
            model_id=18,
            model_revision=4,
            items=(
                LogicalSubmodelSummary(
                    logical_submodel_id=301,
                    workflow_run_id=None,
                    logical_submodel_name="Customer Domain",
                    logical_submodel_status="active",
                    logical_submodel_is_locked=False,
                    entity_count=1,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_submodel(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        logical_submodel_id: int,
    ) -> LogicalSubmodelDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, logical_submodel_id) == (7, 18, 301)
        return LogicalSubmodelDetail(
            logical_submodel_id=301,
            workflow_run_id=None,
            logical_submodel_name="Customer Domain",
            logical_submodel_definition="Customer-facing governed entities.",
            logical_submodel_status="active",
            logical_submodel_is_locked=False,
            entity_count=1,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            entities=(
                LogicalSubmodelEntityMembership(
                    logical_entity_submodel_id=201,
                    workflow_run_id=None,
                    logical_entity_id=101,
                    logical_entity_name="Customer",
                    logical_entity_type="core",
                    logical_entity_status="active",
                    membership_status="active",
                    membership_is_locked=False,
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


def test_logical_entity_collection_normalizes_review_filters() -> None:
    service = StaticLogicalService()
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/logical/entities",
            params={
                "status": "INACTIVE",
                "locked": "false",
                "name_prefix": "  Cust  ",
                "logical_submodel_id": "301",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["workflow_run_id"] is None
    assert response.json()["items"][0]["logical_entity_name"] == "Customer"
    assert service.filters == LogicalEntityFilters(
        status="inactive",
        locked=False,
        name_prefix="cust",
        logical_submodel_id=301,
    )


def test_logical_entity_detail_returns_all_normalized_memberships_and_sources() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/logical/entities/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_run_id"] is None
    assert payload["submodels"][0]["logical_submodel_name"] == "Customer Domain"
    assert payload["sources"][0]["source_object"]["object_name"] == "customer_raw"
    assert (
        payload["sources"][1]["assertion_record"]["modeling_assertion_record_key"]
        == "customer.grain"
    )
    assert "agent_run_id" not in response.text
    assert "prompt" not in response.text


def test_logical_attribute_collection_and_detail_use_exact_normalized_sources() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        collection = client.get(
            "/api/v1/tenants/7/models/18/logical/attributes",
            params={
                "status": "ACTIVE",
                "name_exact": "  Customer ID  ",
                "logical_entity_id": "101",
                "page_size": "25",
            },
        )
        detail = client.get("/api/v1/tenants/7/models/18/logical/attributes/701")

    assert collection.status_code == 200
    assert collection.json()["items"][0]["logical_entity_name"] == "Customer"
    assert detail.status_code == 200
    source = detail.json()["sources"][0]
    assert source["workflow_run_id"] is None
    assert source["source_attribute"]["attribute_name"] == "customer_id"


def test_logical_relationship_collection_and_detail_return_named_endpoints() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        collection = client.get(
            "/api/v1/tenants/7/models/18/logical/relationships",
            params={
                "status": "INACTIVE",
                "locked": "true",
                "logical_entity_id": "102",
            },
        )
        detail = client.get("/api/v1/tenants/7/models/18/logical/relationships/901")

    assert collection.status_code == 200
    item = collection.json()["items"][0]
    assert item["from_logical_entity_name"] == "Order"
    assert item["to_logical_attribute_name"] == "Customer ID"
    assert detail.status_code == 200
    assert detail.json()["logical_relationship_cardinality_basis"] == (
        "Observed and asserted key usage."
    )


def test_logical_submodel_collection_and_detail_return_bounded_memberships() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        collection = client.get(
            "/api/v1/tenants/7/models/18/logical/submodels",
            params={"status": "ACTIVE", "name_prefix": " Customer "},
        )
        detail = client.get("/api/v1/tenants/7/models/18/logical/submodels/301")

    assert collection.status_code == 200
    assert collection.json()["items"][0]["entity_count"] == 1
    assert detail.status_code == 200
    assert detail.json()["entities"][0]["logical_entity_name"] == "Customer"


class LogicalCollectionTransaction:
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
        assert "FROM workflow.logical_entity AS entity" in query
        assert "JOIN model.model AS target_model" in query
        assert "target_model.tenant_id = %s" in query
        assert "FROM workflow.logical_entity_submodel AS membership" in query
        assert "membership.logical_entity_submodel_status" in query
        assert parameters[:11] == (
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
            "cust",
        )
        assert parameters[11:13] == (301, 301)
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "logical_entity_id": 101,
                "workflow_run_id": None,
                "logical_entity_name": "Customer",
                "logical_entity_type": "core",
                "logical_entity_dependency_order": 0,
                "logical_entity_confidence": "high",
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "logical_entity_id": 102,
                "workflow_run_id": 81,
                "logical_entity_name": "Customer Account",
                "logical_entity_type": "association",
                "logical_entity_dependency_order": 1,
                "logical_entity_confidence": "medium",
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class LogicalCollectionDatabase:
    def __init__(self) -> None:
        self.transaction = LogicalCollectionTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[LogicalCollectionTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_logical_entities_are_tenant_authorized_and_cursor_bound() -> (
    None
):
    database = LogicalCollectionDatabase()
    service = DatabaseLogicalService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = LogicalEntityFilters(
        status="active",
        locked=False,
        name_prefix="cust",
        logical_submodel_id=301,
    )

    first = await service.list_entities(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_entities(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.logical_entity_name for item in first.items] == ["Customer"]
    assert [item.logical_entity_name for item in second.items] == ["Customer Account"]
    assert second.items[0].workflow_run_id == 81
    assert database.transaction.offsets == [0, 1]

    with pytest.raises(InvalidRequestError):
        await service.list_entities(
            principal,
            tenant_id=7,
            model_id=18,
            filters=LogicalEntityFilters(
                name_prefix="account", logical_submodel_id=301
            ),
            page_size=1,
            cursor=first.next_cursor,
        )
