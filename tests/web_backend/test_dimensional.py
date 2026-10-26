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
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.features.dimensional import (
    DatabaseDimensionalService,
    DimensionalAttributeDetail,
    DimensionalAttributeFilters,
    DimensionalAttributeLogicalSource,
    DimensionalAttributePage,
    DimensionalAttributeSummary,
    DimensionalLogicalEntitySource,
    DimensionalObjectDetail,
    DimensionalObjectFilters,
    DimensionalObjectPage,
    DimensionalObjectSummary,
    DimensionalRelationshipDetail,
    DimensionalRelationshipFilters,
    DimensionalRelationshipPage,
    DimensionalRelationshipSummary,
    EntitySubjectArea,
    create_dimensional_router,
)
from gds_workbench_api.features.logical import ModelSubjectArea, ModelSubjectAreaPage
from gds_workbench_api.features.dimensional.read_contracts import (
    LogicalAttributeReference,
    LogicalEntityReference,
)


class StaticDimensionalService:
    filters: DimensionalObjectFilters | None = None

    async def list_subject_areas(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> ModelSubjectAreaPage:
        assert (tenant_id, project_id) == (7, 18)
        return ModelSubjectAreaPage(
            project_id=18,
            project_revision=4,
            items=(
                ModelSubjectArea(
                    subject_area_id=41,
                    subject_area_name="Sales",
                    subject_area_definition="Customer orders.",
                    table_count=3,
                    entity_count=2,
                ),
            ),
        )

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalObjectFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalObjectPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, page_size, cursor) == (7, 18, 25, None)
        self.filters = filters
        return DimensionalObjectPage(
            project_id=18,
            project_revision=4,
            items=(self._object(),),
            next_cursor=None,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_entity_id: int,
    ) -> DimensionalObjectDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, dimensional_entity_id) == (7, 18, 101)
        item = self._object()
        return DimensionalObjectDetail(
            **item.model_dump(),
            dimensional_entity_definition="One row per submitted order.",
            dimensional_entity_grain_definition="One submitted order.",
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            subject_areas=(EntitySubjectArea(subject_area_id=301, subject_area_name="Sales"),),
            sources=(
                DimensionalLogicalEntitySource(
                    dimensional_entity_source_mapping_id=401,
                    workflow_run_id=None,
                    support_source_type="logical_entity",
                    source_logical_entity=LogicalEntityReference(
                        logical_entity_id=501,
                        logical_entity_schema_name="silver_sales",
                        logical_entity_name="order",
                    ),
                    rationale="Supplies the fact grain.",
                    is_active=True,
                    is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
            ),
        )

    @staticmethod
    def _object() -> DimensionalObjectSummary:
        return DimensionalObjectSummary(
            dimensional_entity_id=101,
            workflow_run_id=None,
            dimensional_entity_schema_name="gold",
            dimensional_entity_name="Fact Order",
            dimensional_entity_type="fact",
            dimensional_fact_type="transaction",
            dimensional_entity_dependency_order=0,
            dimensional_entity_is_active=True,
            dimensional_entity_is_locked=False,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalAttributePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == DimensionalAttributeFilters(
            active=True,
            name_exact="order amount",
            dimensional_entity_id=101,
        )
        return DimensionalAttributePage(
            project_id=18,
            project_revision=4,
            items=(self._attribute(),),
            next_cursor=None,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_attribute_id: int,
    ) -> DimensionalAttributeDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, dimensional_attribute_id) == (7, 18, 701)
        item = self._attribute()
        return DimensionalAttributeDetail(
            **item.model_dump(),
            dimensional_attribute_definition="Submitted order amount.",
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            sources=(
                DimensionalAttributeLogicalSource(
                    dimensional_attribute_source_mapping_id=801,
                    workflow_run_id=None,
                    dimensional_entity_source_mapping_id=401,
                    support_source_type="logical_attribute",
                    source_logical_attribute=LogicalAttributeReference(
                        logical_entity_id=501,
                        logical_entity_schema_name="silver_sales",
                        logical_entity_name="order",
                        logical_attribute_id=502,
                        logical_attribute_name="order_amount",
                    ),
                    rationale=None,
                    is_active=True,
                    is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
            ),
        )

    @staticmethod
    def _attribute() -> DimensionalAttributeSummary:
        return DimensionalAttributeSummary(
            dimensional_attribute_id=701,
            workflow_run_id=None,
            dimensional_entity_id=101,
            dimensional_entity_schema_name="gold",
            dimensional_entity_name="Fact Order",
            dimensional_attribute_name="Order Amount",
            dimensional_attribute_data_type="DECIMAL(18,2)",
            dimensional_attribute_is_nullable=False,
            dimensional_attribute_ordinal_position=2,
            dimensional_attribute_is_natural_key=False,
            dimensional_attribute_is_surrogate_key=False,
            dimensional_attribute_is_audit_column=False,
            dimensional_attribute_is_active=True,
            dimensional_attribute_is_locked=False,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: DimensionalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalRelationshipPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == DimensionalRelationshipFilters(
            active=False,
            locked=True,
            dimensional_entity_id=101,
        )
        return DimensionalRelationshipPage(
            project_id=18,
            project_revision=4,
            items=(self._relationship(),),
            next_cursor=None,
        )

    async def read_relationship(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dimensional_relationship_id: int,
    ) -> DimensionalRelationshipDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, dimensional_relationship_id) == (7, 18, 901)
        relationship = self._relationship()
        return DimensionalRelationshipDetail(
            **relationship.model_dump(),
            dimensional_relationship_basis=None,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )

    @staticmethod
    def _relationship() -> DimensionalRelationshipSummary:
        return DimensionalRelationshipSummary(
            dimensional_relationship_id=901,
            workflow_run_id=None,
            from_dimensional_entity_id=101,
            from_dimensional_entity_schema_name="gold",
            from_dimensional_entity_name="Fact Order",
            from_dimensional_attribute_id=702,
            from_dimensional_attribute_name="Customer Key",
            to_dimensional_entity_id=102,
            to_dimensional_entity_schema_name="gold",
            to_dimensional_entity_name="Dim Customer",
            to_dimensional_attribute_id=703,
            to_dimensional_attribute_name="Customer Key",
            dimensional_relationship_role_name="ordering_customer",
            dimensional_relationship_is_active=True,
            dimensional_relationship_is_locked=True,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_dimensional_object_collection_and_detail_are_normalized() -> None:
    service = StaticDimensionalService()
    app = FastAPI()
    app.include_router(
        create_dimensional_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        collection = client.get(
            "/api/v1/tenants/7/projects/18/dimensional/objects",
            params={
                "active": "false",
                "locked": "false",
                "name_prefix": "  Fact  ",
                "subject_area_id": "301",
                "page_size": "25",
            },
        )
        detail = client.get("/api/v1/tenants/7/projects/18/dimensional/objects/101")
        retired = client.get(
            "/api/v1/tenants/7/projects/18/dimensional/objects",
            params={"status": "active"},
        )

    assert collection.status_code == 200
    assert collection.json()["items"][0]["dimensional_entity_is_active"] is True
    assert collection.json()["items"][0]["dimensional_fact_type"] == "transaction"
    assert service.filters == DimensionalObjectFilters(
        active=False,
        locked=False,
        name_prefix="fact",
        subject_area_id=301,
    )
    assert retired.status_code == 422
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["workflow_run_id"] is None
    assert payload["subject_areas"] == [{"subject_area_id": 301, "subject_area_name": "Sales"}]
    assert "submodels" not in payload
    assert payload["sources"][0]["support_source_type"] == "logical_entity"
    assert payload["sources"][0]["is_active"] is True
    assert "source_order" not in payload["sources"][0]
    assert "source_role" not in payload["sources"][0]
    assert "agent_run_id" not in detail.text
    assert "prompt" not in detail.text


def test_dimensional_attribute_collection_and_detail_return_normalized_sources() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_dimensional_router(
            identity_provider=_identity_provider(),
            service=StaticDimensionalService(),
        )
    )

    with TestClient(app) as client:
        collection = client.get(
            "/api/v1/tenants/7/projects/18/dimensional/attributes",
            params={
                "active": "true",
                "name_exact": " Order Amount ",
                "dimensional_entity_id": "101",
            },
        )
        detail = client.get("/api/v1/tenants/7/projects/18/dimensional/attributes/701")

    assert collection.status_code == 200
    assert (
        collection.json()["items"][0]["dimensional_attribute_is_natural_key"] is False
    )
    assert detail.status_code == 200
    assert detail.json()["sources"][0]["source_logical_attribute"][
        "logical_attribute_name"
    ] == ("order_amount")
    assert detail.json()["sources"][0]["rationale"] is None


def test_dimensional_relationship_collection_and_detail_return_named_endpoints() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_dimensional_router(
            identity_provider=_identity_provider(),
            service=StaticDimensionalService(),
        )
    )

    with TestClient(app) as client:
        collection = client.get(
            "/api/v1/tenants/7/projects/18/dimensional/relationships",
            params={
                "active": "false",
                "locked": "true",
                "dimensional_entity_id": "101",
            },
        )
        detail = client.get(
            "/api/v1/tenants/7/projects/18/dimensional/relationships/901"
        )

    assert collection.status_code == 200
    item = collection.json()["items"][0]
    assert item["to_dimensional_entity_name"] == "Dim Customer"
    assert item["dimensional_relationship_role_name"] == "ordering_customer"
    assert item["dimensional_relationship_is_active"] is True
    for retired in (
        "dimensional_relationship_name",
        "dimensional_relationship_kind",
        "dimensional_relationship_cardinality",
        "dimensional_relationship_is_optional",
    ):
        assert retired not in item
    assert detail.status_code == 200
    assert detail.json()["dimensional_relationship_basis"] is None
    assert "dimensional_relationship_cardinality_basis" not in detail.json()
    assert "dimensional_relationship_definition" not in detail.json()


class DimensionalObjectsTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_project.project_revision" in query:
            return {"project_revision": 4}
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
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        assert "FROM workflow.dimensional_entity AS entity" in query
        assert "entity.dimensional_entity_is_active = %s" in query
        # The area is reached through active Logical sources and their Object sources.
        assert "JOIN workflow.logical_entity AS logical" in query
        assert "logical.logical_entity_is_active" in query
        assert "logical_source.logical_entity_source_mapping_is_active" in query
        assert "member.subject_area_table_is_active" in query
        assert parameters == (
            7, 18, True, True, None, None, None, None, None, None, None, 301, 301, 2, 0
        )
        return [
            {
                "dimensional_entity_id": 101,
                "workflow_run_id": None,
                "dimensional_entity_schema_name": "gold",
                "dimensional_entity_name": "Fact Order",
                "dimensional_entity_type": "fact",
                "dimensional_fact_type": "transaction",
                "dimensional_entity_dependency_order": 0,
                "dimensional_entity_is_active": True,
                "dimensional_entity_is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        ]


class DimensionalObjectsDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[DimensionalObjectsTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield DimensionalObjectsTransaction()


@pytest.mark.asyncio
async def test_database_dimensional_objects_filter_by_subject_area_through_logical() -> None:
    service = DatabaseDimensionalService(
        database=DimensionalObjectsDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    page = await service.list_objects(
        principal,
        tenant_id=7,
        project_id=18,
        filters=DimensionalObjectFilters(active=True, subject_area_id=301),
        page_size=1,
        cursor=None,
    )

    assert [item.dimensional_entity_name for item in page.items] == ["Fact Order"]
    assert page.next_cursor is None


def test_dimensional_subject_areas_list_each_area_with_its_entity_count() -> None:
    app = FastAPI()
    app.include_router(
        create_dimensional_router(identity_provider=_identity_provider(), service=StaticDimensionalService())
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/projects/18/dimensional/subject-areas")

    assert response.status_code == 200
    assert response.json() == {
        "project_id": 18,
        "project_revision": 4,
        "items": [
            {
                "subject_area_id": 41,
                "subject_area_name": "Sales",
                "subject_area_definition": "Customer orders.",
                "table_count": 3,
                "entity_count": 2,
            }
        ],
    }
