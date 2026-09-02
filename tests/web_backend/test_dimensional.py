from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.features.dimensional import (
    DimensionalAttributeDetail,
    DimensionalAttributeFilters,
    DimensionalAttributePage,
    DimensionalAttributePhysicalSource,
    DimensionalAttributeSummary,
    DimensionalObjectDetail,
    DimensionalObjectPage,
    DimensionalObjectSummary,
    DimensionalPhysicalObjectSource,
    DimensionalRelationshipDetail,
    DimensionalRelationshipFilters,
    DimensionalRelationshipPage,
    DimensionalRelationshipSummary,
    DimensionalSubmodelMembership,
    ModeledFilters,
    PhysicalAttributeReference,
    PhysicalObjectReference,
    create_dimensional_router,
)


class StaticDimensionalService:
    filters: ModeledFilters | None = None

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ModeledFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalObjectPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.filters = filters
        return DimensionalObjectPage(
            model_id=18,
            model_revision=4,
            items=(self._object(),),
            next_cursor=None,
        )

    async def read_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_entity_id: int,
    ) -> DimensionalObjectDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, dimensional_entity_id) == (7, 18, 101)
        item = self._object()
        return DimensionalObjectDetail(
            **item.model_dump(),
            dimensional_entity_definition="One row per submitted order.",
            dimensional_entity_grain_definition="One submitted order.",
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            submodels=(
                DimensionalSubmodelMembership(
                    dimensional_entity_submodel_id=201,
                    workflow_run_id=None,
                    dimensional_submodel_id=301,
                    dimensional_submodel_name="Sales Mart",
                    membership_status="active",
                    membership_is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
            ),
            sources=(
                DimensionalPhysicalObjectSource(
                    dimensional_entity_source_mapping_id=401,
                    workflow_run_id=None,
                    support_source_type="object",
                    source_object=PhysicalObjectReference(
                        object_id=501,
                        tenant_code="GRDM",
                        system_code="SILVER",
                        connection_code="lakehouse",
                        object_schema="silver_sales",
                        object_name="order",
                    ),
                    source_role="fact_source",
                    source_order=1,
                    rationale="Supplies the fact grain.",
                    status="active",
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
            dimensional_entity_name="Fact Order",
            dimensional_entity_type="fact",
            dimensional_fact_type="transaction",
            dimensional_entity_dependency_order=0,
            dimensional_entity_confidence="high",
            dimensional_entity_status="active",
            dimensional_entity_is_locked=False,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: DimensionalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalAttributePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == DimensionalAttributeFilters(
            status="active",
            name_exact="order amount",
            dimensional_entity_id=101,
        )
        return DimensionalAttributePage(
            model_id=18,
            model_revision=4,
            items=(self._attribute(),),
            next_cursor=None,
        )

    async def read_attribute(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dimensional_attribute_id: int,
    ) -> DimensionalAttributeDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, dimensional_attribute_id) == (7, 18, 701)
        item = self._attribute()
        return DimensionalAttributeDetail(
            **item.model_dump(),
            dimensional_attribute_definition="Submitted order amount.",
            dimensional_attribute_aggregation_basis=None,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            sources=(
                DimensionalAttributePhysicalSource(
                    dimensional_attribute_source_mapping_id=801,
                    workflow_run_id=None,
                    dimensional_entity_source_mapping_id=401,
                    support_source_type="attribute",
                    source_attribute=PhysicalAttributeReference(
                        object_id=501,
                        attribute_id=502,
                        tenant_code="GRDM",
                        system_code="SILVER",
                        connection_code="lakehouse",
                        object_schema="silver_sales",
                        object_name="order",
                        attribute_name="order_amount",
                    ),
                    source_order=1,
                    rationale="Maps the governed amount.",
                    status="active",
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
            dimensional_entity_name="Fact Order",
            dimensional_attribute_name="Order Amount",
            dimensional_attribute_data_type="DECIMAL(18,2)",
            dimensional_attribute_is_nullable=False,
            dimensional_attribute_ordinal_position=2,
            dimensional_attribute_role="measure",
            dimensional_attribute_key_role="none",
            dimensional_attribute_is_grain_component=False,
            dimensional_attribute_additivity="additive",
            dimensional_attribute_default_aggregation="sum",
            dimensional_attribute_change_behavior=None,
            dimensional_attribute_is_audit_column=False,
            dimensional_attribute_confidence="high",
            dimensional_attribute_status="active",
            dimensional_attribute_is_locked=False,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def list_relationships(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: DimensionalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> DimensionalRelationshipPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == DimensionalRelationshipFilters(
            status="inactive",
            locked=True,
            dimensional_entity_id=101,
        )
        return DimensionalRelationshipPage(
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
        dimensional_relationship_id: int,
    ) -> DimensionalRelationshipDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, dimensional_relationship_id) == (7, 18, 901)
        relationship = self._relationship()
        return DimensionalRelationshipDetail(
            **relationship.model_dump(),
            dimensional_relationship_definition="Fact Order references Dim Customer.",
            dimensional_relationship_basis="The conformed Customer key.",
            dimensional_relationship_cardinality_basis="Many facts per Customer.",
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )

    @staticmethod
    def _relationship() -> DimensionalRelationshipSummary:
        return DimensionalRelationshipSummary(
            dimensional_relationship_id=901,
            workflow_run_id=None,
            from_dimensional_entity_id=101,
            from_dimensional_entity_name="Fact Order",
            from_dimensional_attribute_id=702,
            from_dimensional_attribute_name="Customer Key",
            to_dimensional_entity_id=102,
            to_dimensional_entity_name="Dim Customer",
            to_dimensional_attribute_id=703,
            to_dimensional_attribute_name="Customer Key",
            dimensional_relationship_name="Order to Customer",
            dimensional_relationship_kind="fact_dimension",
            dimensional_relationship_cardinality="many_to_one",
            dimensional_relationship_is_optional=False,
            dimensional_relationship_role_name="ordering_customer",
            dimensional_relationship_confidence="high",
            dimensional_relationship_status="active",
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
            "/api/v1/tenants/7/models/18/dimensional/objects",
            params={
                "status": "INACTIVE",
                "locked": "false",
                "name_prefix": "  Fact  ",
                "page_size": "25",
            },
        )
        detail = client.get("/api/v1/tenants/7/models/18/dimensional/objects/101")

    assert collection.status_code == 200
    assert service.filters == ModeledFilters(
        status="inactive",
        locked=False,
        name_prefix="fact",
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["workflow_run_id"] is None
    assert payload["submodels"][0]["dimensional_submodel_name"] == "Sales Mart"
    assert payload["sources"][0]["source_role"] == "fact_source"
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
            "/api/v1/tenants/7/models/18/dimensional/attributes",
            params={
                "status": "ACTIVE",
                "name_exact": " Order Amount ",
                "dimensional_entity_id": "101",
            },
        )
        detail = client.get("/api/v1/tenants/7/models/18/dimensional/attributes/701")

    assert collection.status_code == 200
    assert collection.json()["items"][0]["dimensional_attribute_role"] == "measure"
    assert detail.status_code == 200
    assert detail.json()["sources"][0]["source_attribute"]["attribute_name"] == (
        "order_amount"
    )


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
            "/api/v1/tenants/7/models/18/dimensional/relationships",
            params={
                "status": "INACTIVE",
                "locked": "true",
                "dimensional_entity_id": "101",
            },
        )
        detail = client.get("/api/v1/tenants/7/models/18/dimensional/relationships/901")

    assert collection.status_code == 200
    item = collection.json()["items"][0]
    assert item["to_dimensional_entity_name"] == "Dim Customer"
    assert item["dimensional_relationship_role_name"] == "ordering_customer"
    assert item["dimensional_relationship_is_optional"] is False
    assert detail.status_code == 200
    assert detail.json()["dimensional_relationship_cardinality_basis"] == (
        "Many facts per Customer."
    )
    assert detail.json()["dimensional_relationship_is_optional"] is False
