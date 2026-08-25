from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.main import create_app
from gds_workbench_api.features.workflows.overview import (
    DatabaseWorkflowOverviewService,
    ModelWorkflowOverview,
    WorkflowLedgerEntry,
)


class StaticWorkflowOverviewService:
    async def read_overview(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelWorkflowOverview:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id) == (7, 18)
        return ModelWorkflowOverview(
            model_id=18,
            model_revision=4,
            items=(
                WorkflowLedgerEntry(
                    workflow="scope",
                    result_count=25,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=None,
                    latest_run_state=None,
                    latest_run_created_at=None,
                    state="ready",
                    quality_warning_codes=(),
                ),
                WorkflowLedgerEntry(
                    workflow="profiling",
                    result_count=18,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=1048,
                    latest_run_state="completed",
                    latest_run_created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                    state="results_available",
                    quality_warning_codes=(),
                ),
                WorkflowLedgerEntry(
                    workflow="analysis",
                    result_count=0,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=None,
                    latest_run_state=None,
                    latest_run_created_at=None,
                    state="not_started",
                    quality_warning_codes=(),
                ),
                WorkflowLedgerEntry(
                    workflow="assertions",
                    result_count=0,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=None,
                    latest_run_state=None,
                    latest_run_created_at=None,
                    state="not_started",
                    quality_warning_codes=(),
                ),
                WorkflowLedgerEntry(
                    workflow="conceptual",
                    result_count=0,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=None,
                    latest_run_state=None,
                    latest_run_created_at=None,
                    state="not_started",
                    quality_warning_codes=(),
                ),
                WorkflowLedgerEntry(
                    workflow="logical",
                    result_count=0,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=None,
                    latest_run_state=None,
                    latest_run_created_at=None,
                    state="not_started",
                    quality_warning_codes=("conceptual_results_unavailable",),
                ),
                WorkflowLedgerEntry(
                    workflow="dimensional",
                    result_count=0,
                    needs_review_count=0,
                    locked_count=0,
                    latest_run_id=None,
                    latest_run_state=None,
                    latest_run_created_at=None,
                    state="not_started",
                    quality_warning_codes=("logical_results_unavailable",),
                ),
            ),
        )


def test_model_overview_route_returns_authoritative_workflow_ledger() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        workflow_overview_service=StaticWorkflowOverviewService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/overview")

    assert response.status_code == 200
    assert response.json()["items"][:2] == [
        {
            "workflow": "scope",
            "result_count": 25,
            "needs_review_count": 0,
            "locked_count": 0,
            "latest_run_id": None,
            "latest_run_state": None,
            "latest_run_created_at": None,
            "state": "ready",
            "quality_warning_codes": [],
        },
        {
            "workflow": "profiling",
            "result_count": 18,
            "needs_review_count": 0,
            "locked_count": 0,
            "latest_run_id": 1048,
            "latest_run_state": "completed",
            "latest_run_created_at": "2026-08-24T14:00:00Z",
            "state": "results_available",
            "quality_warning_codes": [],
        },
    ]


class OverviewTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
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
        assert "workflow.attribute_profile" in query
        assert "workflow.analysis_result" in query
        assert "model.modeling_assertion_record" in query
        assert "workflow.conceptual_object" in query
        assert "workflow.logical_entity" in query
        assert "workflow.dimensional_entity" in query
        assert parameters == (7, 18)
        created = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
        base = {
            "model_id": 18,
            "model_revision": 4,
            "needs_review_count": 0,
            "locked_count": 0,
            "latest_run_id": None,
            "latest_run_state": None,
            "latest_run_created_at": None,
        }
        return [
            {**base, "workflow": "scope", "result_count": 25},
            {
                **base,
                "workflow": "profiling",
                "result_count": 18,
                "latest_run_id": 1048,
                "latest_run_state": "completed",
                "latest_run_created_at": created,
            },
            {
                **base,
                "workflow": "analysis",
                "result_count": 37,
                "needs_review_count": 15,
                "locked_count": 2,
                "latest_run_id": 1049,
                "latest_run_state": "completed_with_repair",
                "latest_run_created_at": created,
            },
            {**base, "workflow": "assertions", "result_count": 6},
            {**base, "workflow": "conceptual", "result_count": 0},
            {**base, "workflow": "logical", "result_count": 0},
            {**base, "workflow": "dimensional", "result_count": 0},
        ]


class OverviewDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[OverviewTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield OverviewTransaction()


@pytest.mark.asyncio
async def test_overview_states_are_results_driven_and_prerequisites_only_warn() -> None:
    service = DatabaseWorkflowOverviewService(
        database=OverviewDatabase(),
        authorizer=AuthorizationService(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    overview = await service.read_overview(principal, tenant_id=7, model_id=18)

    assert tuple(item.workflow for item in overview.items) == (
        "scope",
        "profiling",
        "analysis",
        "assertions",
        "conceptual",
        "logical",
        "dimensional",
    )
    assert overview.items[2].state == "needs_review"
    assert overview.items[4].state == "not_started"
    assert overview.items[4].quality_warning_codes == ()
    assert overview.items[5].quality_warning_codes == (
        "conceptual_results_unavailable",
    )
    assert overview.items[6].quality_warning_codes == ("logical_results_unavailable",)
