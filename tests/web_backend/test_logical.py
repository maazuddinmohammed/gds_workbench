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
    ContextRecordReference,
    DatabaseLogicalService,
    EntitySubjectArea,
    LogicalAttributeDetail,
    LogicalAttributeFilters,
    LogicalAttributePage,
    LogicalAttributePhysicalSource,
    LogicalAttributeSummary,
    LogicalContextSource,
    LogicalEntityDetail,
    LogicalEntityFilters,
    LogicalEntityPage,
    LogicalEntitySummary,
    LogicalObjectSource,
    LogicalRelationshipDetail,
    LogicalRelationshipFilters,
    LogicalRelationshipPage,
    LogicalRelationshipSummary,
    ModelSubjectArea,
    ModelSubjectAreaPage,
    PhysicalAttributeReference,
    PhysicalObjectReference,
    SubjectAreaBuild,
    WaitingDraft,
    create_logical_router,
)


class StaticLogicalService:
    filters: LogicalEntityFilters | None = None

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
                    shared_table_count=1,
                    entity_count=2,
                    build=SubjectAreaBuild(
                        state="draft_waiting",
                        workflow_run_id=1050,
                        at=datetime(2026, 10, 26, 13, 20, tzinfo=UTC),
                    ),
                ),
            ),
            waiting_draft=WaitingDraft(workflow_run_id=1050, workflow_operation="build"),
        )

    async def list_entities(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: LogicalEntityFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalEntityPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, page_size, cursor) == (7, 18, 25, None)
        self.filters = filters
        return LogicalEntityPage(
            project_id=18,
            project_revision=4,
            items=(
                LogicalEntitySummary(
                    logical_entity_id=101,
                    workflow_run_id=None,
                    logical_entity_schema_name="silver",
                    logical_entity_name="Customer",
                    logical_entity_type="core",
                    logical_entity_dependency_order=0,
                    logical_entity_is_active=True,
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
        project_id: int,
        logical_entity_id: int,
    ) -> LogicalEntityDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, logical_entity_id) == (7, 18, 101)
        return LogicalEntityDetail(
            logical_entity_id=101,
            workflow_run_id=None,
            logical_entity_schema_name="silver",
            logical_entity_name="Customer",
            logical_entity_definition="One governed customer.",
            logical_entity_type="core",
            logical_entity_grain="One row per customer.",
            logical_entity_dependency_order=0,
            logical_entity_is_active=True,
            logical_entity_is_locked=False,
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            subject_areas=(
                EntitySubjectArea(subject_area_id=301, subject_area_name="Customer"),
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
                    rationale="Supplies Customer identity.",
                    is_active=True,
                    is_locked=False,
                    created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                ),
                LogicalContextSource(
                    logical_entity_source_mapping_id=402,
                    workflow_run_id=81,
                    support_source_type="context_record",
                    context_record=ContextRecordReference(
                        context_record_id="f6c97e13-4665-53e0-aa01-865c4b35e7b2",
                        context_group_name="customer_rules",
                        context_type_name="Business Rules",
                        context_text="One row represents one Customer.",
                        source_reference=None,
                        status="active",
                    ),
                    rationale=None,
                    is_active=True,
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
        project_id: int,
        filters: LogicalAttributeFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalAttributePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, page_size, cursor) == (7, 18, 25, None)
        assert filters == LogicalAttributeFilters(
            active=True,
            name_exact="customer id",
            logical_entity_id=101,
        )
        return LogicalAttributePage(
            project_id=18,
            project_revision=4,
            items=(
                LogicalAttributeSummary(
                    logical_attribute_id=701,
                    workflow_run_id=None,
                    logical_entity_id=101,
                    logical_entity_schema_name="silver",
                    logical_entity_name="Customer",
                    logical_attribute_name="Customer ID",
                    logical_attribute_data_type="BIGINT",
                    logical_attribute_is_nullable=False,
                    logical_attribute_is_natural_key=False,
                    logical_attribute_is_surrogate_key=True,
                    logical_attribute_ordinal_position=1,
                    logical_attribute_is_audit_column=False,
                    logical_attribute_is_active=True,
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
        project_id: int,
        logical_attribute_id: int,
    ) -> LogicalAttributeDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, logical_attribute_id) == (7, 18, 701)
        return LogicalAttributeDetail(
            logical_attribute_id=701,
            workflow_run_id=None,
            logical_entity_id=101,
            logical_entity_schema_name="silver",
            logical_entity_name="Customer",
            logical_attribute_name="Customer ID",
            logical_attribute_definition="Stable warehouse identifier.",
            logical_attribute_data_type="BIGINT",
            logical_attribute_is_nullable=False,
            logical_attribute_is_natural_key=False,
            logical_attribute_is_surrogate_key=True,
            logical_attribute_ordinal_position=1,
            logical_attribute_is_audit_column=False,
            logical_attribute_is_active=True,
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
                    rationale="Maps the stable Customer identifier.",
                    is_active=True,
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
        project_id: int,
        filters: LogicalRelationshipFilters,
        page_size: int,
        cursor: str | None,
    ) -> LogicalRelationshipPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert filters == LogicalRelationshipFilters(
            active=False,
            locked=True,
            logical_entity_id=102,
        )
        return LogicalRelationshipPage(
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
        logical_relationship_id: int,
    ) -> LogicalRelationshipDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, logical_relationship_id) == (7, 18, 901)
        relationship = self._relationship()
        return LogicalRelationshipDetail(
            **relationship.model_dump(),
            logical_relationship_basis="The governed Customer key appears on Order.",
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )

    @staticmethod
    def _relationship() -> LogicalRelationshipSummary:
        return LogicalRelationshipSummary(
            logical_relationship_id=901,
            workflow_run_id=None,
            from_logical_entity_id=102,
            from_logical_entity_schema_name="silver",
            from_logical_entity_name="Order",
            from_logical_attribute_id=702,
            from_logical_attribute_name="Customer ID",
            to_logical_entity_id=101,
            to_logical_entity_schema_name="silver",
            to_logical_entity_name="Customer",
            to_logical_attribute_id=701,
            to_logical_attribute_name="Customer ID",
            logical_relationship_cardinality="many_to_one",
            logical_relationship_is_active=True,
            logical_relationship_is_locked=True,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
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
            "/api/v1/tenants/7/projects/18/logical/entities",
            params={
                "active": "false",
                "locked": "false",
                "name_prefix": "  Cust  ",
                "subject_area_id": "301",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["workflow_run_id"] is None
    assert item["logical_entity_name"] == "Customer"
    assert item["logical_entity_is_active"] is True
    assert "logical_entity_status" not in item
    assert service.filters == LogicalEntityFilters(
        active=False,
        locked=False,
        name_prefix="cust",
        subject_area_id=301,
    )


@pytest.mark.parametrize(
    "params",
    [{"status": "active"}, {"logical_submodel_id": "301"}, {"active": "maybe"}],
)
def test_logical_entity_collection_rejects_retired_filters(params: dict[str, str]) -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/projects/18/logical/entities", params=params)

    assert response.status_code == 422


def test_logical_submodel_routes_are_gone() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        collection = client.get("/api/v1/tenants/7/projects/18/logical/submodels")
        detail = client.get("/api/v1/tenants/7/projects/18/logical/submodels/301")

    assert (collection.status_code, detail.status_code) == (404, 404)


def test_logical_entity_detail_returns_derived_subject_areas_and_sources() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(
            identity_provider=_identity_provider(),
            service=StaticLogicalService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/projects/18/logical/entities/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_run_id"] is None
    assert payload["subject_areas"] == [
        {"subject_area_id": 301, "subject_area_name": "Customer"}
    ]
    assert "submodels" not in payload
    assert "logical_entity_type_detail" not in payload
    assert payload["sources"][0]["support_source_type"] == "object"
    assert payload["sources"][0]["source_object"]["object_name"] == "customer_raw"
    assert payload["sources"][0]["is_active"] is True
    assert "source_order" not in payload["sources"][0]
    assert payload["sources"][1]["rationale"] is None
    assert payload["sources"][1]["context_record"] == {
        "context_record_id": "f6c97e13-4665-53e0-aa01-865c4b35e7b2",
        "context_group_name": "customer_rules",
        "context_type_name": "Business Rules",
        "context_text": "One row represents one Customer.",
        "source_reference": None,
        "status": "active",
    }
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
            "/api/v1/tenants/7/projects/18/logical/attributes",
            params={
                "active": "true",
                "name_exact": "  Customer ID  ",
                "logical_entity_id": "101",
                "page_size": "25",
            },
        )
        detail = client.get("/api/v1/tenants/7/projects/18/logical/attributes/701")

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
            "/api/v1/tenants/7/projects/18/logical/relationships",
            params={
                "active": "false",
                "locked": "true",
                "logical_entity_id": "102",
            },
        )
        detail = client.get("/api/v1/tenants/7/projects/18/logical/relationships/901")

    assert collection.status_code == 200
    item = collection.json()["items"][0]
    assert item["from_logical_entity_name"] == "Order"
    assert item["to_logical_attribute_name"] == "Customer ID"
    assert item["logical_relationship_is_active"] is True
    assert "logical_relationship_name" not in item
    assert detail.status_code == 200
    assert detail.json()["logical_relationship_basis"] == (
        "The governed Customer key appears on Order."
    )
    assert "logical_relationship_definition" not in detail.json()
    assert "logical_relationship_cardinality_basis" not in detail.json()


class LogicalCollectionTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_project.project_revision" in query:
            assert "target_project.tenant_id = %s" in query
            assert parameters == (7, 18)
            return {"project_revision": 4}
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
        # No retained cross-Tenant scope in this isolated service fixture.
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        assert "FROM workflow.logical_entity AS entity" in query
        assert "JOIN project.project AS target_project" in query
        assert "target_project.tenant_id = %s" in query
        assert "entity.logical_entity_is_active = %s" in query
        # The area filter follows active Object sources to the area's active members.
        assert "JOIN workflow.subject_area_table AS member" in query
        assert "member.subject_area_table_is_active" in query
        assert "source.logical_entity_source_mapping_is_active" in query
        assert "submodel" not in query
        assert parameters[:11] == (
            7,
            18,
            True,
            True,
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
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Customer",
                "logical_entity_type": "core",
                "logical_entity_dependency_order": 0,
                "logical_entity_is_active": True,
                "logical_entity_is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "logical_entity_id": 102,
                "workflow_run_id": 81,
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Customer Account",
                "logical_entity_type": "association",
                "logical_entity_dependency_order": 1,
                "logical_entity_is_active": True,
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
        active=True,
        locked=False,
        name_prefix="cust",
        subject_area_id=301,
    )

    first = await service.list_entities(
        principal,
        tenant_id=7,
        project_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_entities(
        principal,
        tenant_id=7,
        project_id=18,
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
            project_id=18,
            filters=LogicalEntityFilters(name_prefix="account", subject_area_id=301),
            page_size=1,
            cursor=first.next_cursor,
        )


class LogicalDetailTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "FROM workflow.logical_entity AS entity" in query:
            assert parameters == (7, 18, 101)
            assert "logical_entity_type_detail" not in query
            return {
                "logical_entity_id": 101,
                "workflow_run_id": None,
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Customer",
                "logical_entity_definition": "One governed customer.",
                "logical_entity_type": "core",
                "logical_entity_grain": "One row per customer.",
                "logical_entity_dependency_order": 0,
                "logical_entity_is_active": True,
                "logical_entity_is_locked": False,
                "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        return await LogicalCollectionTransaction().fetch_one(query, parameters)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        assert parameters == (7, 18, 101, 2001)
        if "FROM workflow.subject_area AS area" in query:
            # Only active areas whose active members hold an active Object source.
            assert "area.subject_area_is_active" in query
            assert "member.subject_area_table_is_active" in query
            assert "source.logical_entity_source_mapping_is_active" in query
            return [{"subject_area_id": 301, "subject_area_name": "Customer"}]
        assert "FROM workflow.logical_entity_source_mapping AS source" in query
        assert "source.support_source_type" not in query
        assert "WHEN source.source_object_id IS NOT NULL THEN 'object'" in query
        common = {
            "workflow_run_id": None,
            "is_active": True,
            "is_locked": False,
            "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            "source_object_id": None,
            "source_tenant_code": None,
            "source_system_code": None,
            "source_connection_code": None,
            "source_object_schema": None,
            "source_object_name": None,
            "context_record_id": None,
            "context_group_name": None,
            "context_type_name": None,
            "context_text": None,
            "source_reference": None,
            "context_record_status": None,
        }
        return [
            {
                **common,
                "logical_entity_source_mapping_id": 401,
                "support_source_type": "object",
                "rationale": None,
                "source_object_id": 501,
                "source_tenant_code": "GRDM",
                "source_system_code": "CRM",
                "source_connection_code": "crm_prod",
                "source_object_schema": "bronze_crm",
                "source_object_name": "customer_raw",
            },
            {
                **common,
                "logical_entity_source_mapping_id": 402,
                "support_source_type": "context_record",
                "rationale": "Defines the grain.",
                "is_active": False,
                "context_record_id": "f6c97e13-4665-53e0-aa01-865c4b35e7b2",
                "context_group_name": "customer_rules",
                "context_type_name": "Business Rules",
                "context_text": "One row represents one Customer.",
                "context_record_status": "active",
            },
        ]


class LogicalDetailDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[LogicalDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield LogicalDetailTransaction()


@pytest.mark.asyncio
async def test_database_logical_entity_detail_derives_subject_areas_and_source_kinds() -> None:
    service = DatabaseLogicalService(
        database=LogicalDetailDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_entity(
        principal, tenant_id=7, project_id=18, logical_entity_id=101
    )

    assert detail.subject_areas == (
        EntitySubjectArea(subject_area_id=301, subject_area_name="Customer"),
    )
    object_source, context_source = detail.sources
    assert isinstance(object_source, LogicalObjectSource)
    assert object_source.rationale is None
    assert object_source.source_object.object_name == "customer_raw"
    assert isinstance(context_source, LogicalContextSource)
    assert context_source.is_active is False


def test_logical_subject_areas_list_each_area_with_its_entity_count() -> None:
    app = FastAPI()
    app.include_router(
        create_logical_router(identity_provider=_identity_provider(), service=StaticLogicalService())
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/projects/18/logical/subject-areas")

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
                "shared_table_count": 1,
                "entity_count": 2,
                "build": {
                    "state": "draft_waiting",
                    "workflow_run_id": 1050,
                    "at": "2026-10-26T13:20:00Z",
                },
            }
        ],
        "waiting_draft": {"workflow_run_id": 1050, "workflow_operation": "build"},
    }
