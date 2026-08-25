from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, LiteralString, Protocol, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from psycopg import Connection

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.analysis import (
    AnalysisEndpoint,
    AnalysisEvidence,
    AnalysisFindingDetail,
    AnalysisFindingFilters,
    AnalysisFindingPage,
    AnalysisFindingSummary,
    AnalysisWorkflowProvenance,
    DatabaseAnalysisReviewService,
    create_analysis_review_router,
)
from gds_workbench_api.features.profiling import (
    AttributeProfile,
    DatabaseProfilingReviewService,
    ProfileWorkflowProvenance,
    ProfilingObjectDetail,
    ProfilingObjectFilters,
    ProfilingObjectLedgerItem,
    ProfilingObjectPage,
    create_profiling_router,
)


class DisposablePostgres(Protocol):
    def connect_owner(self) -> Connection[dict[str, Any]]: ...

    def web_runtime_dsn(self) -> str: ...


DEMO_METADATA_SEED = (
    Path(__file__).parents[2] / "database" / "seed" / "01_metadata_snapshot_demo.sql"
)


class StaticProfilingReviewService:
    profiling_filters: ProfilingObjectFilters | None = None
    analysis_filters: AnalysisFindingFilters | None = None

    async def list_profiling_objects(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: ProfilingObjectFilters,
        page_size: int,
        cursor: str | None,
    ) -> ProfilingObjectPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.profiling_filters = filters
        return ProfilingObjectPage(
            model_id=18,
            model_revision=4,
            items=(
                ProfilingObjectLedgerItem(
                    object_id=501,
                    source_tenant_id=8,
                    source_tenant_code="GRDM",
                    source_tenant_name="Global Reference Data",
                    system_id=31,
                    system_code="CRM",
                    system_name="Customer Relationship Management",
                    connection_id=21,
                    connection_code="BRONZE",
                    object_schema="bronze_crm",
                    object_name="customer_raw",
                    profiled_attribute_count=12,
                    last_profiled_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_profiling_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        object_id: int,
    ) -> ProfilingObjectDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, object_id) == (7, 18, 501)
        return ProfilingObjectDetail(
            model_id=18,
            model_revision=4,
            object_id=501,
            source_tenant_id=8,
            source_tenant_code="GRDM",
            source_tenant_name="Global Reference Data",
            system_id=31,
            system_code="CRM",
            system_name="Customer Relationship Management",
            connection_id=21,
            connection_code="BRONZE",
            object_schema="bronze_crm",
            object_name="customer_raw",
            profiled_attribute_count=1,
            last_profiled_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            attribute_profiles=(
                AttributeProfile(
                    attribute_id=601,
                    attribute_name="customer_id",
                    attribute_ordinal_position=1,
                    attribute_data_type="bigint",
                    source_context_digest="a" * 64,
                    row_count=100,
                    non_null_count=99,
                    null_count=1,
                    blank_count=None,
                    distinct_count=99,
                    min_data_length=None,
                    max_data_length=None,
                    avg_data_length=None,
                    percent_populated=Decimal("99.0000"),
                    percent_duplicates=Decimal("0.0000"),
                    percent_null=Decimal("1.0000"),
                    percent_blank=None,
                    percent_distinct=Decimal("100.0000"),
                    provenance=ProfileWorkflowProvenance(
                        agent_run_id=None,
                        workflow_run_id=None,
                    ),
                    created_at=datetime(2026, 8, 24, 13, 59, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            profiles_truncated=False,
        )

    async def list_analysis_findings(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AnalysisFindingFilters,
        page_size: int,
        cursor: str | None,
    ) -> AnalysisFindingPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.analysis_filters = filters
        return AnalysisFindingPage(
            model_id=18,
            model_revision=4,
            items=(
                AnalysisFindingSummary(
                    analysis_result_id=701,
                    from_endpoint=AnalysisEndpoint(
                        object_id=501,
                        attribute_id=601,
                        source_tenant_id=8,
                        source_tenant_code="GRDM",
                        source_tenant_name="Global Reference Data",
                        system_id=31,
                        system_code="CRM",
                        system_name="Customer Relationship Management",
                        connection_id=21,
                        connection_code="BRONZE",
                        object_schema="bronze_crm",
                        object_name="customer_raw",
                        attribute_name="country_code",
                        attribute_data_type="varchar",
                    ),
                    to_endpoint=AnalysisEndpoint(
                        object_id=502,
                        attribute_id=602,
                        source_tenant_id=8,
                        source_tenant_code="GRDM",
                        source_tenant_name="Global Reference Data",
                        system_id=31,
                        system_code="CRM",
                        system_name="Customer Relationship Management",
                        connection_id=21,
                        connection_code="BRONZE",
                        object_schema="bronze_crm",
                        object_name="country_raw",
                        attribute_name="country_code",
                        attribute_data_type="varchar",
                    ),
                    relationship_kind="reference",
                    relationship_confidence="high",
                    validation_state="validated",
                    validation_result="supported",
                    status="needs_review",
                    is_locked=True,
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_analysis_finding(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        analysis_result_id: int,
    ) -> AnalysisFindingDetail:
        page = await self.list_analysis_findings(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=AnalysisFindingFilters(show_inactive=True),
            page_size=25,
            cursor=None,
        )
        summary = page.items[0]
        assert analysis_result_id == summary.analysis_result_id
        return AnalysisFindingDetail(
            **summary.model_dump(),
            relationship_basis="Country code inclusion and target uniqueness were verified.",
            evidence=AnalysisEvidence(
                validation_policy_version="1.0.0",
                validation_policy_digest="b" * 64,
                result="supported",
                source_non_null_count=99,
                source_distinct_count=3,
                target_non_null_count=3,
                target_distinct_count=3,
                source_missing_target_count=0,
                unused_target_count=0,
                duplicate_target_key_count=0,
            ),
            provenance=AnalysisWorkflowProvenance(
                agent_run_id=None,
                inference_workflow_run_id=None,
                validation_workflow_run_id=None,
            ),
            created_at=datetime(2026, 8, 24, 13, 59, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_profiling_ledger_is_object_level_and_normalizes_filters() -> None:
    service = StaticProfilingReviewService()
    app = FastAPI()
    app.include_router(
        create_profiling_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/profiling"
            "?source_tenant_code=%20GRDM%20&system_code=CRM"
            "&object_schema=Bronze_CRM&object_name=Customer_Raw&page_size=25"
        )

    assert response.status_code == 200
    assert service.profiling_filters == ProfilingObjectFilters(
        source_tenant_code="grdm",
        system_code="crm",
        object_schema="bronze_crm",
        object_name="customer_raw",
    )
    payload = response.json()
    assert payload["model_revision"] == 4
    assert payload["items"][0]["object_id"] == 501
    assert payload["items"][0]["profiled_attribute_count"] == 12
    assert "attribute_profiles" not in payload["items"][0]


def test_profiling_object_detail_returns_normalized_profiles_with_nullable_provenance() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_profiling_router(
            identity_provider=_identity_provider(),
            service=StaticProfilingReviewService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/profiling/501")

    assert response.status_code == 200
    profile = response.json()["attribute_profiles"][0]
    assert profile["attribute_name"] == "customer_id"
    assert profile["provenance"] == {
        "agent_run_id": None,
        "workflow_run_id": None,
    }
    assert profile["source_context_digest"] == "a" * 64
    assert "created_by" not in profile


def test_analysis_ledger_keeps_from_and_to_filters_directional() -> None:
    service = StaticProfilingReviewService()
    app = FastAPI()
    app.include_router(
        create_analysis_review_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/analysis"
            "?object_id=501&from_object_id=501&to_object_id=502"
            "&validation_state=VALIDATED"
            "&status=Needs_Review&locked=true&show_inactive=true&page_size=25"
        )

    assert response.status_code == 200
    assert service.analysis_filters == AnalysisFindingFilters(
        object_id=501,
        from_object_id=501,
        to_object_id=502,
        validation_state="validated",
        status="needs_review",
        locked=True,
        show_inactive=True,
    )
    item = response.json()["items"][0]
    assert item["from_endpoint"]["object_id"] == 501
    assert item["to_endpoint"]["object_id"] == 502
    assert item["validation_state"] == "validated"
    assert "relationship_basis" not in item


def test_analysis_detail_normalizes_endpoints_and_evidence() -> None:
    app = FastAPI()
    app.include_router(
        create_analysis_review_router(
            identity_provider=_identity_provider(),
            service=StaticProfilingReviewService(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/analysis/701")

    assert response.status_code == 200
    payload = response.json()
    assert payload["from_endpoint"]["attribute_name"] == "country_code"
    assert payload["to_endpoint"]["object_name"] == "country_raw"
    assert payload["evidence"]["source_missing_target_count"] == 0
    assert payload["evidence"]["validation_policy_digest"] == "b" * 64
    assert payload["provenance"] == {
        "agent_run_id": None,
        "inference_workflow_run_id": None,
        "validation_workflow_run_id": None,
    }
    assert "validation_source_non_null_count" not in payload


def test_analysis_defaults_hide_inactive_findings() -> None:
    service = StaticProfilingReviewService()
    app = FastAPI()
    app.include_router(
        create_analysis_review_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/analysis?page_size=25")

    assert response.status_code == 200
    assert service.analysis_filters == AnalysisFindingFilters(show_inactive=False)


def test_profiling_and_analysis_routes_are_read_only() -> None:
    service = StaticProfilingReviewService()
    app = FastAPI()
    app.include_router(
        create_profiling_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )
    app.include_router(
        create_analysis_review_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/profiling",
        "/api/v1/tenants/{tenant_id}/models/{model_id}/profiling/{object_id}",
        "/api/v1/tenants/{tenant_id}/models/{model_id}/analysis",
        ("/api/v1/tenants/{tenant_id}/models/{model_id}/analysis/{analysis_result_id}"),
    ):
        methods = {method for method in paths[path] if method != "parameters"}
        assert methods == {"get"}


class ReviewTransaction:
    def __init__(self) -> None:
        self.profiling_offsets: list[int] = []
        self.analysis_offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "workflow.analysis_result" in query:
            assert parameters == (7, 7, 18, 701)
            assert "target_model.tenant_id = %s" in query
            return {
                "analysis_result_id": 701,
                "from_object_id": 501,
                "from_attribute_id": 601,
                "from_source_tenant_id": 8,
                "from_source_tenant_code": "GRDM",
                "from_source_tenant_name": "Global Reference Data",
                "from_system_id": 31,
                "from_system_code": "CRM",
                "from_system_name": "Customer Relationship Management",
                "from_connection_id": 21,
                "from_connection_code": "BRONZE",
                "from_object_schema": "bronze_crm",
                "from_object_name": "customer_raw",
                "from_attribute_name": "country_code",
                "from_attribute_data_type": "varchar",
                "to_object_id": 502,
                "to_attribute_id": 602,
                "to_source_tenant_id": 8,
                "to_source_tenant_code": "GRDM",
                "to_source_tenant_name": "Global Reference Data",
                "to_system_id": 31,
                "to_system_code": "CRM",
                "to_system_name": "Customer Relationship Management",
                "to_connection_id": 21,
                "to_connection_code": "BRONZE",
                "to_object_schema": "bronze_crm",
                "to_object_name": "country_raw",
                "to_attribute_name": "country_code",
                "to_attribute_data_type": "varchar",
                "relationship_kind": "reference",
                "relationship_confidence": "high",
                "relationship_basis": (
                    "Country code inclusion and target uniqueness were verified."
                ),
                "relationship_basis_truncated": False,
                "validation_state": "validated",
                "validation_policy_version": "1.0.0",
                "validation_policy_digest": "b" * 64,
                "validation_result": "supported",
                "validation_source_non_null_count": 99,
                "validation_source_distinct_count": 3,
                "validation_target_non_null_count": 3,
                "validation_target_distinct_count": 3,
                "validation_source_missing_target_count": 0,
                "validation_unused_target_count": 0,
                "validation_duplicate_target_key_count": 0,
                "agent_run_id": None,
                "inference_workflow_run_id": None,
                "validation_workflow_run_id": None,
                "status": "needs_review",
                "is_locked": True,
                "created_at": datetime(2026, 8, 24, 13, 59, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        if "count(profile.attribute_id)" in query:
            assert parameters == (7, 7, 18, 501)
            assert "target_model.tenant_id = %s" in query
            return {
                "object_id": 501,
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "connection_id": 21,
                "connection_code": "BRONZE",
                "object_schema": "bronze_crm",
                "object_name": "customer_raw",
                "profiled_attribute_count": 1,
                "last_profiled_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        if "SELECT target_model.model_id" in query:
            assert parameters == (7, 18)
            assert "target_model.tenant_id = %s" in query
            return {"model_id": 18, "model_revision": 4}
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
        return {
            "principal_id": 41,
            "principal_display_name": "Maaz",
            "is_super_admin": False,
            "effective_role": "tenant_admin",
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
        if "workflow.analysis_result" in query:
            assert "target_model.tenant_id = %s" in query
            assert parameters[:18] == (
                7,
                7,
                18,
                501,
                501,
                501,
                501,
                501,
                502,
                502,
                "validated",
                "validated",
                "needs_review",
                "needs_review",
                "needs_review",
                True,
                True,
                True,
            )
            limit, offset = parameters[-2:]
            assert limit == 2
            self.analysis_offsets.append(offset)
            endpoint = {
                "from_object_id": 501,
                "from_attribute_id": 601,
                "from_source_tenant_id": 8,
                "from_source_tenant_code": "GRDM",
                "from_source_tenant_name": "Global Reference Data",
                "from_system_id": 31,
                "from_system_code": "CRM",
                "from_system_name": "Customer Relationship Management",
                "from_connection_id": 21,
                "from_connection_code": "BRONZE",
                "from_object_schema": "bronze_crm",
                "from_object_name": "customer_raw",
                "from_attribute_name": "country_code",
                "from_attribute_data_type": "varchar",
                "to_object_id": 502,
                "to_attribute_id": 602,
                "to_source_tenant_id": 8,
                "to_source_tenant_code": "GRDM",
                "to_source_tenant_name": "Global Reference Data",
                "to_system_id": 31,
                "to_system_code": "CRM",
                "to_system_name": "Customer Relationship Management",
                "to_connection_id": 21,
                "to_connection_code": "BRONZE",
                "to_object_schema": "bronze_crm",
                "to_object_name": "country_raw",
                "to_attribute_name": "country_code",
                "to_attribute_data_type": "varchar",
            }
            rows = [
                {
                    "analysis_result_id": 701,
                    **endpoint,
                    "relationship_kind": "reference",
                    "relationship_confidence": "high",
                    "validation_state": "validated",
                    "validation_result": "supported",
                    "status": "needs_review",
                    "is_locked": True,
                    "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                },
                {
                    "analysis_result_id": 702,
                    **endpoint,
                    "relationship_kind": "lookup",
                    "relationship_confidence": "medium",
                    "validation_state": "validated",
                    "validation_result": "supported",
                    "status": "needs_review",
                    "is_locked": True,
                    "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
                },
            ]
            return rows[offset : offset + limit]
        assert "workflow.attribute_profile" in query
        assert "target_model.tenant_id = %s" in query
        if "profile.agent_run_id" in query:
            assert parameters == (7, 18, 501, 2001)
            return [
                {
                    "attribute_id": 601,
                    "attribute_name": "customer_id",
                    "attribute_ordinal_position": 1,
                    "attribute_data_type": "bigint",
                    "agent_run_id": None,
                    "workflow_run_id": None,
                    "source_context_digest": "a" * 64,
                    "row_count": 100,
                    "non_null_count": 99,
                    "null_count": 1,
                    "blank_count": None,
                    "distinct_count": 99,
                    "min_data_length": None,
                    "max_data_length": None,
                    "avg_data_length": None,
                    "percent_populated": Decimal("99.0000"),
                    "percent_duplicates": Decimal("0.0000"),
                    "percent_null": Decimal("1.0000"),
                    "percent_blank": None,
                    "percent_distinct": Decimal("100.0000"),
                    "created_at": datetime(2026, 8, 24, 13, 59, tzinfo=UTC),
                    "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                }
            ]
        assert parameters[:3] == (7, 7, 18)
        assert parameters[3:13] == (
            None,
            None,
            "grdm",
            "grdm",
            "crm",
            "crm",
            "bronze_crm",
            "bronze_crm",
            None,
            None,
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.profiling_offsets.append(offset)
        rows = [
            {
                "object_id": 501,
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "connection_id": 21,
                "connection_code": "BRONZE",
                "object_schema": "bronze_crm",
                "object_name": "customer_raw",
                "profiled_attribute_count": 12,
                "last_profiled_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "object_id": 502,
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "connection_id": 21,
                "connection_code": "BRONZE",
                "object_schema": "bronze_crm",
                "object_name": "country_raw",
                "profiled_attribute_count": 4,
                "last_profiled_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class ReviewDatabase:
    def __init__(self) -> None:
        self.transaction = ReviewTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReviewTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_profiling_ledger_is_tenant_scoped_and_cursor_paged() -> None:
    database = ReviewDatabase()
    service = DatabaseProfilingReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = ProfilingObjectFilters(
        source_tenant_code="grdm",
        system_code="crm",
        object_schema="bronze_crm",
    )

    first = await service.list_profiling_objects(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_profiling_objects(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.object_name for item in first.items] == ["customer_raw"]
    assert [item.object_name for item in second.items] == ["country_raw"]
    assert first.model_revision == 4
    assert second.next_cursor is None
    assert database.transaction.profiling_offsets == [0, 1]


@pytest.mark.asyncio
async def test_database_cursor_is_bound_to_normalized_filters() -> None:
    database = ReviewDatabase()
    service = DatabaseProfilingReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    first = await service.list_profiling_objects(
        principal,
        tenant_id=7,
        model_id=18,
        filters=ProfilingObjectFilters(
            source_tenant_code="grdm",
            system_code="crm",
            object_schema="bronze_crm",
        ),
        page_size=1,
        cursor=None,
    )

    with pytest.raises(InvalidRequestError, match="pagination cursor"):
        await service.list_profiling_objects(
            principal,
            tenant_id=7,
            model_id=18,
            filters=ProfilingObjectFilters(object_name="different_object"),
            page_size=1,
            cursor=first.next_cursor,
        )


@pytest.mark.asyncio
async def test_database_profiling_detail_preserves_nullable_run_provenance() -> None:
    service = DatabaseProfilingReviewService(
        database=ReviewDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_profiling_object(
        principal,
        tenant_id=7,
        model_id=18,
        object_id=501,
    )

    assert detail.model_revision == 4
    assert detail.attribute_profiles[0].provenance == ProfileWorkflowProvenance(
        agent_run_id=None,
        workflow_run_id=None,
    )
    assert detail.profiles_truncated is False


@pytest.mark.asyncio
async def test_database_analysis_ledger_applies_directional_review_filters() -> None:
    database = ReviewDatabase()
    service = DatabaseAnalysisReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    filters = AnalysisFindingFilters(
        object_id=501,
        from_object_id=501,
        to_object_id=502,
        validation_state="validated",
        status="needs_review",
        locked=True,
        show_inactive=True,
    )

    first = await service.list_analysis_findings(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_analysis_findings(
        principal,
        tenant_id=7,
        model_id=18,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.analysis_result_id for item in first.items] == [701]
    assert [item.analysis_result_id for item in second.items] == [702]
    assert first.items[0].from_endpoint.object_id == 501
    assert first.items[0].to_endpoint.object_id == 502
    assert database.transaction.analysis_offsets == [0, 1]


@pytest.mark.asyncio
async def test_database_analysis_detail_normalizes_evidence_and_nullable_provenance() -> (
    None
):
    service = DatabaseAnalysisReviewService(
        database=ReviewDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_analysis_finding(
        principal,
        tenant_id=7,
        model_id=18,
        analysis_result_id=701,
    )

    assert detail.evidence is not None
    assert detail.evidence.source_missing_target_count == 0
    assert detail.provenance == AnalysisWorkflowProvenance(
        agent_run_id=None,
        inference_workflow_run_id=None,
        validation_workflow_run_id=None,
    )
    assert detail.from_endpoint.object_id == 501
    assert detail.to_endpoint.object_id == 502


@pytest.mark.asyncio
async def test_database_review_labels_gds_objects_from_discovery_scope(
    web_postgres_database: DisposablePostgres,
) -> None:
    suffix = uuid4().hex[:12]
    with web_postgres_database.connect_owner() as connection:
        existing = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        if existing is None:
            connection.execute(
                cast(LiteralString, DEMO_METADATA_SEED.read_text(encoding="utf-8"))
            )
        tenant = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        assert tenant is not None
        tenant_id = tenant["tenant_id"]
        assert isinstance(tenant_id, int) and not isinstance(tenant_id, bool)
        model = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id
            """,
            (tenant_id, f"Profiling analysis source Tenant {suffix}"),
        ).fetchone()
        endpoints = connection.execute(
            """
            SELECT object_record.object_id,
                   object_record.object_schema,
                   attribute.attribute_id
              FROM core.object AS object_record
              JOIN core.attribute AS attribute
                ON attribute.object_id = object_record.object_id
               AND attribute.attribute_name = 'customer_id'
             WHERE object_record.object_schema IN ('source_demo', 'bronze_demo')
            """
        ).fetchall()
        assert model is not None and len(endpoints) == 2
        by_schema = {str(row["object_schema"]): row for row in endpoints}
        source = by_schema["source_demo"]
        bronze = by_schema["bronze_demo"]
        unassigned = connection.execute(
            """
            INSERT INTO core.object (
                connection_id,
                object_schema,
                object_name,
                object_type_id,
                zone_id
            )
            SELECT connection.connection_id,
                   %s,
                   %s,
                   object_type.object_type_id,
                   zone.zone_id
              FROM core.connection AS connection
             CROSS JOIN reference.object_type AS object_type
             CROSS JOIN reference.zone AS zone
             WHERE connection.connection_code = 'DEMO_GDS'
               AND object_type.object_type_code = 'TABLE'
               AND zone.zone_code = 'bronze'
            RETURNING object_id
            """,
            (f"unassigned_review_{suffix}", f"hidden_review_{suffix}"),
        ).fetchone()
        assert unassigned is not None
        unassigned_attribute = connection.execute(
            """
            INSERT INTO core.attribute (
                object_id,
                attribute_name,
                attribute_ordinal_position,
                attribute_data_type
            ) VALUES (%s, 'customer_id', 1, 'BIGINT')
            RETURNING attribute_id
            """,
            (unassigned["object_id"],),
        ).fetchone()
        assert unassigned_attribute is not None
        connection.execute(
            """
            INSERT INTO model.model_scope (model_id, object_id)
            VALUES (%s, %s), (%s, %s), (%s, %s)
            """,
            (
                model["model_id"],
                source["object_id"],
                model["model_id"],
                bronze["object_id"],
                model["model_id"],
                unassigned["object_id"],
            ),
        )
        connection.execute(
            """
            INSERT INTO workflow.attribute_profile (
                model_id,
                attribute_id,
                object_id,
                source_context_digest,
                row_count,
                non_null_count,
                null_count
            ) VALUES
                (%s, %s, %s, %s, 10, 8, 2),
                (%s, %s, %s, %s, 10, 8, 2)
            """,
            (
                model["model_id"],
                bronze["attribute_id"],
                bronze["object_id"],
                "a" * 64,
                model["model_id"],
                unassigned_attribute["attribute_id"],
                unassigned["object_id"],
                "b" * 64,
            ),
        )
        valid_finding = connection.execute(
            """
            INSERT INTO workflow.analysis_result (
                model_id,
                from_object_id,
                from_attribute_id,
                to_object_id,
                to_attribute_id,
                relationship_kind,
                relationship_basis
            ) VALUES (%s, %s, %s, %s, %s, %s, 'Assigned endpoint')
            RETURNING analysis_result_id
            """,
            (
                model["model_id"],
                source["object_id"],
                source["attribute_id"],
                bronze["object_id"],
                bronze["attribute_id"],
                f"assigned_{suffix}",
            ),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO workflow.analysis_result (
                model_id,
                from_object_id,
                from_attribute_id,
                to_object_id,
                to_attribute_id,
                relationship_kind,
                relationship_basis
            ) VALUES (%s, %s, %s, %s, %s, %s, 'Unassigned endpoint')
            """,
            (
                model["model_id"],
                source["object_id"],
                source["attribute_id"],
                unassigned["object_id"],
                unassigned_attribute["attribute_id"],
                f"unassigned_{suffix}",
            ),
        )
        assert valid_finding is not None
        model_id = model["model_id"]
        valid_finding_id = valid_finding["analysis_result_id"]

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    profiling_service = DatabaseProfilingReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    analysis_service = DatabaseAnalysisReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.DEVELOPMENT,
        entra_tenant_id=None,
        entra_object_id=None,
    )
    await database.open()
    try:
        profile_page = await profiling_service.list_profiling_objects(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=ProfilingObjectFilters(),
            page_size=20,
            cursor=None,
        )
        profile_detail = await profiling_service.read_profiling_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            object_id=bronze["object_id"],
        )
        finding_page = await analysis_service.list_analysis_findings(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=AnalysisFindingFilters(show_inactive=True),
            page_size=20,
            cursor=None,
        )
        finding_detail = await analysis_service.read_analysis_finding(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            analysis_result_id=valid_finding_id,
        )
    finally:
        await database.close()

    assert [item.object_id for item in profile_page.items] == [bronze["object_id"]]
    assert profile_page.items[0].source_tenant_code == "DEMO_TENANT"
    assert profile_detail.source_tenant_code == "DEMO_TENANT"
    assert [item.analysis_result_id for item in finding_page.items] == [
        valid_finding_id
    ]
    assert finding_page.items[0].from_endpoint.source_tenant_code == "DEMO_TENANT"
    assert finding_page.items[0].to_endpoint.source_tenant_code == "DEMO_TENANT"
    assert finding_detail.from_endpoint.source_tenant_code == "DEMO_TENANT"
    assert finding_detail.to_endpoint.source_tenant_code == "DEMO_TENANT"
