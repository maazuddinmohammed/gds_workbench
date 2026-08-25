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

from gds_workbench_api.features.mapping import (
    DatabaseMappingReviewService,
    MappingAttributeDetail,
    MappingAttributePage,
    MappingAttributeSummary,
    MappingDependencyFilters,
    MappingDependencyPage,
    MappingDependencySummary,
    MappingObjectDetail,
    MappingObjectPage,
    MappingObjectSummary,
    MappingProfileProvenance,
    ModeledAttributeReference,
    ModeledEntityReference,
    OutputTemplateProvenance,
    ParentObjectMappingReference,
    PhysicalAttributeReference,
    PhysicalObjectReference,
    SourceSystemReference,
    create_mapping_review_router,
)


class StaticMappingReviewService:
    dependency_filters: MappingDependencyFilters | None = None
    object_filters: MappingDependencyFilters | None = None
    attribute_filters: MappingDependencyFilters | None = None

    async def list_dependencies(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingDependencyPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.dependency_filters = filters
        return MappingDependencyPage(
            model_id=18,
            model_revision=4,
            items=(
                MappingDependencySummary(
                    mapping_source_system_dependency_id=301,
                    workflow_run_id=None,
                    entity_type="logical_entity",
                    source_system=SourceSystemReference(
                        system_id=31,
                        system_code="CRM",
                        system_name="Customer Relationship Management",
                    ),
                    dependency_order=0,
                    status="needs_review",
                    is_locked=False,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def list_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingObjectPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.object_filters = filters
        return MappingObjectPage(
            model_id=18,
            model_revision=4,
            items=(
                MappingObjectSummary(
                    mapping_object_id=401,
                    workflow_run_id=None,
                    target=PhysicalObjectReference(
                        object_id=501,
                        tenant_id=7,
                        tenant_code="ACME",
                        tenant_name="Acme",
                        system_id=32,
                        system_code="GDS",
                        system_name="Global Data Store",
                        connection_id=21,
                        connection_code="SILVER",
                        object_schema="silver_crm",
                        object_name="customer",
                        zone_code="silver",
                    ),
                    source=ModeledEntityReference(
                        entity_type="logical_entity",
                        entity_id=101,
                        entity_name="Customer",
                    ),
                    source_system=SourceSystemReference(
                        system_id=31,
                        system_code="CRM",
                        system_name="Customer Relationship Management",
                    ),
                    dependency_order=1,
                    artifact_type="sql_file",
                    status="active",
                    is_locked=True,
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
        mapping_object_id: int,
    ) -> MappingObjectDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, mapping_object_id) == (7, 18, 401)
        summary = (
            await self.list_objects(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                filters=MappingDependencyFilters(),
                page_size=25,
                cursor=None,
            )
        ).items[0]
        return MappingObjectDetail(
            **summary.model_dump(),
            artifact_generation_instructions="Create one idempotent Silver merge.",
            mapping_profile=MappingProfileProvenance(
                profile_key="mapping.standard",
                profile_version="1.0.0",
                profile_schema_digest="a" * 64,
                package_digest="b" * 64,
            ),
            mapping_package_document={"source_systems": ["CRM"]},
            mapping_document_format="structured",
            mapping_document={
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "mapping_summary": "One Customer per customer_id.",
                "nested_extension": {"supported": True},
            },
            output_template=OutputTemplateProvenance(
                output_template_id=801,
                output_template_code="standard_mapping_object",
                output_template_name="Standard Mapping Object",
                output_template_target_type="mapping_object",
                output_template_schema_digest="c" * 64,
                is_active=True,
            ),
            created_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )

    async def list_attributes(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: MappingDependencyFilters,
        page_size: int,
        cursor: str | None,
    ) -> MappingAttributePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.attribute_filters = filters
        target_object = (
            (
                await self.list_objects(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    filters=MappingDependencyFilters(),
                    page_size=25,
                    cursor=None,
                )
            )
            .items[0]
            .target
        )
        return MappingAttributePage(
            model_id=18,
            model_revision=4,
            items=(
                MappingAttributeSummary(
                    mapping_attribute_id=601,
                    workflow_run_id=None,
                    mapping_object_id=401,
                    target=PhysicalAttributeReference(
                        object=target_object,
                        attribute_id=701,
                        attribute_name="customer_id",
                        attribute_ordinal_position=1,
                        attribute_data_type="bigint",
                    ),
                    source=ModeledAttributeReference(
                        entity=ModeledEntityReference(
                            entity_type="logical_entity",
                            entity_id=101,
                            entity_name="Customer",
                        ),
                        attribute_id=201,
                        attribute_name="Customer ID",
                    ),
                    source_system=SourceSystemReference(
                        system_id=31,
                        system_code="CRM",
                        system_name="Customer Relationship Management",
                    ),
                    status="needs_review",
                    is_locked=False,
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
        mapping_attribute_id: int,
    ) -> MappingAttributeDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, mapping_attribute_id) == (7, 18, 601)
        summary = (
            await self.list_attributes(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                filters=MappingDependencyFilters(),
                page_size=25,
                cursor=None,
            )
        ).items[0]
        return MappingAttributeDetail(
            **summary.model_dump(),
            parent_object_mapping=ParentObjectMappingReference(
                mapping_object_id=401,
                dependency_order=1,
                artifact_type="sql_file",
                mapping_profile=MappingProfileProvenance(
                    profile_key="mapping.standard",
                    profile_version="1.0.0",
                    profile_schema_digest="a" * 64,
                    package_digest="b" * 64,
                ),
                status="active",
                is_locked=True,
            ),
            mapping_document_format="structured",
            mapping_document={
                "schema_version": "1.0",
                "transformation_kind": "expression",
                "mapping_summary": "Normalize CRM customer ID.",
                "expression": {"sql": "cast(customer_id as bigint)"},
            },
            output_template=OutputTemplateProvenance(
                output_template_id=802,
                output_template_code="standard_mapping_attribute",
                output_template_name="Standard Mapping Attribute",
                output_template_target_type="mapping_attribute",
                output_template_schema_digest="d" * 64,
                is_active=True,
            ),
            created_at=datetime(2026, 8, 24, 13, 1, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_mapping_dependency_ledger_normalizes_filters() -> None:
    service = StaticMappingReviewService()
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/mapping/dependencies",
            params={
                "entity_type": "LOGICAL_ENTITY",
                "source_system_code": "  CrM  ",
                "status": "NEEDS_REVIEW",
                "locked": "false",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    assert service.dependency_filters == MappingDependencyFilters(
        entity_type="logical_entity",
        source_system_code="crm",
        status="needs_review",
        locked=False,
    )
    assert response.json() == {
        "model_id": 18,
        "model_revision": 4,
        "items": [
            {
                "mapping_source_system_dependency_id": 301,
                "workflow_run_id": None,
                "entity_type": "logical_entity",
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "dependency_order": 0,
                "status": "needs_review",
                "is_locked": False,
                "updated_at": "2026-08-24T14:00:00Z",
            }
        ],
        "next_cursor": None,
    }


def test_mapping_object_ledger_is_target_first_and_normalizes_filters() -> None:
    service = StaticMappingReviewService()
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/mapping/objects",
            params={
                "entity_type": "LOGICAL_ENTITY",
                "source_system_id": "31",
                "status": "ACTIVE",
                "locked": "true",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    assert service.object_filters == MappingDependencyFilters(
        entity_type="logical_entity",
        source_system_id=31,
        status="active",
        locked=True,
    )
    item = response.json()["items"][0]
    assert item["target"] == {
        "object_id": 501,
        "tenant_id": 7,
        "tenant_code": "ACME",
        "tenant_name": "Acme",
        "system_id": 32,
        "system_code": "GDS",
        "system_name": "Global Data Store",
        "connection_id": 21,
        "connection_code": "SILVER",
        "object_schema": "silver_crm",
        "object_name": "customer",
        "zone_code": "silver",
    }
    assert item["source"] == {
        "entity_type": "logical_entity",
        "entity_id": 101,
        "entity_name": "Customer",
    }
    assert item["workflow_run_id"] is None
    assert "mapping_document" not in item


def test_mapping_object_detail_preserves_dynamic_document_and_template_provenance() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=_identity_provider(),
            service=StaticMappingReviewService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/mapping/objects/401")

    assert response.status_code == 200
    payload = response.json()
    assert payload["target"]["object_name"] == "customer"
    assert payload["source"]["entity_name"] == "Customer"
    assert payload["source_system"]["system_code"] == "CRM"
    assert payload["mapping_document_format"] == "structured"
    assert payload["mapping_document"]["nested_extension"] == {"supported": True}
    assert payload["output_template"] == {
        "output_template_id": 801,
        "output_template_code": "standard_mapping_object",
        "output_template_name": "Standard Mapping Object",
        "output_template_target_type": "mapping_object",
        "output_template_schema_digest": "c" * 64,
        "is_active": True,
    }
    assert payload["workflow_run_id"] is None
    assert "created_by" not in payload


def test_mapping_attribute_ledger_is_target_first_and_filters_through_parent() -> None:
    service = StaticMappingReviewService()
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/mapping/attributes",
            params={
                "entity_type": "LOGICAL_ENTITY",
                "source_system_code": " CRM ",
                "status": "NEEDS_REVIEW",
                "locked": "false",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    assert service.attribute_filters == MappingDependencyFilters(
        entity_type="logical_entity",
        source_system_code="crm",
        status="needs_review",
        locked=False,
    )
    item = response.json()["items"][0]
    assert item["target"]["object"]["object_name"] == "customer"
    assert item["target"]["attribute_name"] == "customer_id"
    assert item["source"]["entity"]["entity_name"] == "Customer"
    assert item["source"]["attribute_name"] == "Customer ID"
    assert item["source_system"]["system_code"] == "CRM"
    assert item["workflow_run_id"] is None
    assert "mapping_document" not in item


def test_mapping_attribute_detail_returns_parent_support_and_dynamic_document() -> None:
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=_identity_provider(),
            service=StaticMappingReviewService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/mapping/attributes/601")

    assert response.status_code == 200
    payload = response.json()
    assert payload["target"]["attribute_name"] == "customer_id"
    assert payload["source"]["attribute_name"] == "Customer ID"
    assert payload["parent_object_mapping"]["mapping_object_id"] == 401
    assert payload["parent_object_mapping"]["mapping_profile"]["profile_key"] == (
        "mapping.standard"
    )
    assert payload["mapping_document_format"] == "structured"
    assert payload["mapping_document"]["expression"] == {
        "sql": "cast(customer_id as bigint)"
    }
    assert payload["output_template"]["output_template_target_type"] == (
        "mapping_attribute"
    )
    assert payload["workflow_run_id"] is None


def test_mapping_review_routes_are_read_only() -> None:
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=_identity_provider(),
            service=StaticMappingReviewService(),
        )
    )

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/dependencies",
        "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/objects",
        (
            "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/objects/{mapping_object_id}"
        ),
        "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/attributes",
        (
            "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/attributes/{mapping_attribute_id}"
        ),
    ):
        methods = {method for method in paths[path] if method != "parameters"}
        assert methods == {"get"}


class MappingTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_model.model_revision" in query:
            assert parameters == (7, 18)
            assert "target_model.tenant_id = %s" in query
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
        assert "workflow.mapping_source_system_dependency" in query
        assert "target_model.tenant_id = %s" in query
        assert parameters[:12] == (
            7,
            18,
            "logical_entity",
            "logical_entity",
            31,
            31,
            "crm",
            "crm",
            "needs_review",
            "needs_review",
            False,
            False,
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "mapping_source_system_dependency_id": 301,
                "workflow_run_id": None,
                "entity_type": "logical_entity",
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "dependency_order": 0,
                "status": "needs_review",
                "is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "mapping_source_system_dependency_id": 302,
                "workflow_run_id": 81,
                "entity_type": "logical_entity",
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "dependency_order": 1,
                "status": "needs_review",
                "is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class MappingDatabase:
    def __init__(self) -> None:
        self.transaction = MappingTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[MappingTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_mapping_dependencies_are_authorized_and_cursor_bound() -> None:
    database = MappingDatabase()
    service = DatabaseMappingReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = MappingDependencyFilters(
        entity_type="logical_entity",
        source_system_id=31,
        source_system_code="crm",
        status="needs_review",
        locked=False,
    )

    first = await service.list_dependencies(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_dependencies(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert first.model_revision == 4
    assert [item.mapping_source_system_dependency_id for item in first.items] == [301]
    assert second.items[0].workflow_run_id == 81
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]

    with pytest.raises(InvalidRequestError):
        await service.list_dependencies(
            principal,
            tenant_id=7,
            model_id=18,
            filters=MappingDependencyFilters(source_system_code="erp"),
            page_size=1,
            cursor=first.next_cursor,
        )


class ObjectMappingTransaction:
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
        assert "workflow.list_model_object_eligibility" in query
        assert "workflow.mapping_object" in query
        assert "target_model.tenant_id = %s" in query
        assert parameters == (
            7,
            18,
            "logical_entity",
            "logical_entity",
            31,
            31,
            "crm",
            "crm",
            "active",
            "active",
            True,
            True,
            26,
            0,
        )
        return [
            {
                "mapping_object_id": 401,
                "workflow_run_id": None,
                "target": {
                    "object_id": 501,
                    "tenant_id": 7,
                    "tenant_code": "ACME",
                    "tenant_name": "Acme",
                    "system_id": 32,
                    "system_code": "GDS",
                    "system_name": "Global Data Store",
                    "connection_id": 21,
                    "connection_code": "SILVER",
                    "object_schema": "silver_crm",
                    "object_name": "customer",
                    "zone_code": "silver",
                },
                "source": {
                    "entity_type": "logical_entity",
                    "entity_id": 101,
                    "entity_name": "Customer",
                },
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "dependency_order": 1,
                "artifact_type": "sql_file",
                "status": "active",
                "is_locked": True,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        ]


class ObjectMappingDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ObjectMappingTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield ObjectMappingTransaction()


@pytest.mark.asyncio
async def test_database_mapping_objects_use_current_target_eligibility() -> None:
    service = DatabaseMappingReviewService(
        database=ObjectMappingDatabase(),
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
        model_id=18,
        filters=MappingDependencyFilters(
            entity_type="logical_entity",
            source_system_id=31,
            source_system_code="crm",
            status="active",
            locked=True,
        ),
        page_size=25,
        cursor=None,
    )

    assert page.model_revision == 4
    assert page.items[0].target.object_name == "customer"
    assert page.items[0].source.entity_name == "Customer"
    assert page.items[0].workflow_run_id is None


class ObjectMappingDetailTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "workflow.mapping_object" in query:
            assert "target_model.tenant_id = %s" in query
            assert "LEFT JOIN application.output_template" in query
            assert parameters == (7, 18, 401)
            return {
                "mapping_object_id": 401,
                "workflow_run_id": None,
                "target": {
                    "object_id": 501,
                    "tenant_id": 7,
                    "tenant_code": "ACME",
                    "tenant_name": "Acme",
                    "system_id": 32,
                    "system_code": "GDS",
                    "system_name": "Global Data Store",
                    "connection_id": 21,
                    "connection_code": "SILVER",
                    "object_schema": "silver_crm",
                    "object_name": "customer",
                    "zone_code": "silver",
                },
                "source": {
                    "entity_type": "logical_entity",
                    "entity_id": 101,
                    "entity_name": "Customer",
                },
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "dependency_order": 1,
                "artifact_type": "sql_file",
                "status": "active",
                "is_locked": True,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "artifact_generation_instructions": "Create Silver SQL.",
                "mapping_profile": {
                    "profile_key": "mapping.standard",
                    "profile_version": "1.0.0",
                    "profile_schema_digest": "a" * 64,
                    "package_digest": "b" * 64,
                },
                "mapping_package_document": {"source_systems": ["CRM"]},
                "mapping_document_format": "free_form",
                "mapping_document": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "free_form_extension": ["preserved"],
                },
                "output_template": None,
                "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
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
        raise AssertionError((query, parameters))


class ObjectMappingDetailDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ObjectMappingDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield ObjectMappingDetailTransaction()


@pytest.mark.asyncio
async def test_database_mapping_object_detail_keeps_free_form_json_dynamic() -> None:
    service = DatabaseMappingReviewService(
        database=ObjectMappingDetailDatabase(),
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
        mapping_object_id=401,
    )

    assert detail.mapping_document_format == "free_form"
    assert detail.mapping_document == {
        "schema_version": "1.0",
        "transformation_kind": "direct",
        "free_form_extension": ["preserved"],
    }
    assert detail.output_template is None
    assert detail.workflow_run_id is None


class AttributeMappingTransaction:
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
        assert "workflow.list_model_attribute_eligibility" in query
        assert "workflow.mapping_attribute" in query
        assert "target_model.tenant_id = %s" in query
        assert parameters == (
            7,
            18,
            "logical_entity",
            "logical_entity",
            31,
            31,
            "crm",
            "crm",
            "needs_review",
            "needs_review",
            False,
            False,
            26,
            0,
        )
        return [
            {
                "mapping_attribute_id": 601,
                "workflow_run_id": None,
                "mapping_object_id": 401,
                "target": {
                    "object": {
                        "object_id": 501,
                        "tenant_id": 7,
                        "tenant_code": "ACME",
                        "tenant_name": "Acme",
                        "system_id": 32,
                        "system_code": "GDS",
                        "system_name": "Global Data Store",
                        "connection_id": 21,
                        "connection_code": "SILVER",
                        "object_schema": "silver_crm",
                        "object_name": "customer",
                        "zone_code": "silver",
                    },
                    "attribute_id": 701,
                    "attribute_name": "customer_id",
                    "attribute_ordinal_position": 1,
                    "attribute_data_type": "bigint",
                },
                "source": {
                    "entity": {
                        "entity_type": "logical_entity",
                        "entity_id": 101,
                        "entity_name": "Customer",
                    },
                    "attribute_id": 201,
                    "attribute_name": "Customer ID",
                },
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "status": "needs_review",
                "is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        ]


class AttributeMappingDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AttributeMappingTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield AttributeMappingTransaction()


@pytest.mark.asyncio
async def test_database_mapping_attributes_filter_via_parent_source_system() -> None:
    service = DatabaseMappingReviewService(
        database=AttributeMappingDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    page = await service.list_attributes(
        principal,
        tenant_id=7,
        model_id=18,
        filters=MappingDependencyFilters(
            entity_type="logical_entity",
            source_system_id=31,
            source_system_code="crm",
            status="needs_review",
            locked=False,
        ),
        page_size=25,
        cursor=None,
    )

    assert page.model_revision == 4
    assert page.items[0].target.attribute_name == "customer_id"
    assert page.items[0].source.attribute_name == "Customer ID"
    assert page.items[0].source_system.system_code == "CRM"


class AttributeMappingDetailTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "workflow.mapping_attribute" in query:
            assert "target_model.tenant_id = %s" in query
            assert "LEFT JOIN application.output_template" in query
            assert parameters == (7, 18, 601)
            return {
                "mapping_attribute_id": 601,
                "workflow_run_id": None,
                "mapping_object_id": 401,
                "target": {
                    "object": {
                        "object_id": 501,
                        "tenant_id": 7,
                        "tenant_code": "ACME",
                        "tenant_name": "Acme",
                        "system_id": 32,
                        "system_code": "GDS",
                        "system_name": "Global Data Store",
                        "connection_id": 21,
                        "connection_code": "SILVER",
                        "object_schema": "silver_crm",
                        "object_name": "customer",
                        "zone_code": "silver",
                    },
                    "attribute_id": 701,
                    "attribute_name": "customer_id",
                    "attribute_ordinal_position": 1,
                    "attribute_data_type": "bigint",
                },
                "source": {
                    "entity": {
                        "entity_type": "logical_entity",
                        "entity_id": 101,
                        "entity_name": "Customer",
                    },
                    "attribute_id": 201,
                    "attribute_name": "Customer ID",
                },
                "source_system": {
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                },
                "status": "needs_review",
                "is_locked": False,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "parent_object_mapping": {
                    "mapping_object_id": 401,
                    "dependency_order": 1,
                    "artifact_type": "sql_file",
                    "mapping_profile": {
                        "profile_key": "mapping.standard",
                        "profile_version": "1.0.0",
                        "profile_schema_digest": "a" * 64,
                        "package_digest": "b" * 64,
                    },
                    "status": "active",
                    "is_locked": True,
                },
                "mapping_document_format": "structured",
                "mapping_document": {
                    "schema_version": "1.0",
                    "transformation_kind": "expression",
                    "custom_expression": {"kind": "cast"},
                },
                "output_template": {
                    "output_template_id": 802,
                    "output_template_code": "standard_mapping_attribute",
                    "output_template_name": "Standard Mapping Attribute",
                    "output_template_target_type": "mapping_attribute",
                    "output_template_schema_digest": "d" * 64,
                    "is_active": True,
                },
                "created_at": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
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
        raise AssertionError((query, parameters))


class AttributeMappingDetailDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AttributeMappingDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield AttributeMappingDetailTransaction()


@pytest.mark.asyncio
async def test_database_mapping_attribute_detail_returns_parent_support() -> None:
    service = DatabaseMappingReviewService(
        database=AttributeMappingDetailDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_attribute(
        principal,
        tenant_id=7,
        model_id=18,
        mapping_attribute_id=601,
    )

    assert detail.parent_object_mapping.mapping_object_id == 401
    assert detail.parent_object_mapping.mapping_profile is not None
    assert (
        detail.parent_object_mapping.mapping_profile.profile_key == "mapping.standard"
    )
    assert detail.mapping_document == {
        "schema_version": "1.0",
        "transformation_kind": "expression",
        "custom_expression": {"kind": "cast"},
    }
    assert detail.output_template is not None
    assert detail.output_template.output_template_target_type == "mapping_attribute"
