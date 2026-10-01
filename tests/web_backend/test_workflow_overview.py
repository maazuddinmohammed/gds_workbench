# pyright: reportPrivateUsage=false
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.features.workflows.overview import (
    DatabaseWorkflowOverviewService,
    ModelWorkflowOverview,
    WorkflowLedgerEntry,
)
from gds_workbench_api.features.workflows.overview.contracts import (
    ModelSectionState,
    OverviewWorkflow,
    WorkflowMetric,
    WorkflowRunState,
)
from gds_workbench_api.features.workflows.overview.service import _section_state
from gds_workbench_api.main import create_app


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
        # No retained cross-Tenant scope in this isolated service fixture.
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        assert "workflow.attribute_profile" in query
        assert "workflow.analysis_result" in query
        assert "model.modeling_assertion_record" in query
        assert "workflow.conceptual_object" in query
        assert "workflow.logical_entity" in query
        assert "workflow.dimensional_entity" in query
        assert "workflow.mapping_object" in query
        assert "workflow.generated_code" in query
        assert "workflow.validation_group" in query
        assert "workflow.attribute_enrichment" in query
        assert "workflow.object_enrichment" in query
        assert "PARTITION BY run.model_workflow" in query
        assert "modeled_entity_type =" not in query
        assert parameters == (7, 18)
        created = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
        base = {
            "model_id": 18,
            "model_revision": 4,
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
                "locked_count": 2,
                "latest_run_id": 1049,
                "latest_run_state": "completed_with_repair",
                "latest_run_created_at": created,
            },
            {**base, "workflow": "assertions", "result_count": 6},
            {**base, "workflow": "conceptual", "result_count": 0},
            {**base, "workflow": "logical", "result_count": 0},
            {**base, "workflow": "dimensional", "result_count": 0},
            {**base, "workflow": "metadata_enrichment", "result_count": 3},
            {**base, "workflow": "mapping", "result_count": 4},
            {
                **base,
                "workflow": "code_generation",
                "result_count": 2,
                "latest_run_state": "failed",
            },
            {
                **base,
                "workflow": "validation",
                "result_count": 1,
                "latest_run_state": "running",
            },
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
    assert overview.items[2].state == "results_available"
    assert overview.items[4].state == "not_started"
    assert overview.items[4].quality_warning_codes == ()
    assert overview.items[5].quality_warning_codes == (
        "conceptual_results_unavailable",
    )
    assert overview.items[6].quality_warning_codes == ("logical_results_unavailable",)

    assert [(item.section, item.state) for item in overview.section_states] == [
        ("overview", "available"),
        ("settings", "available"),
        ("scope", "ready"),
        ("metadata-enrichment", "results_available"),
        ("profiling", "results_available"),
        ("assertions", "results_available"),
        ("analysis", "results_available"),
        ("conceptual", "not_run"),
        ("logical", "not_run"),
        ("dimensional", "not_run"),
        ("mapping", "results_available"),
        ("code-generation", "failed"),
        ("validation", "running"),
    ]


@pytest.mark.parametrize(
    "workflow",
    [
        "metadata_enrichment",
        "profiling",
        "analysis",
        "conceptual",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
        "validation",
    ],
)
@pytest.mark.parametrize(
    ("run_state", "count", "result_offset", "expected"),
    [
        (None, 0, None, "not_run"),
        (None, 1, 0, "results_available"),
        ("queued", 1, 0, "queued"),
        ("running", 1, 0, "running"),
        ("failed", 1, 0, "failed"),
        ("completed", 1, -1, "completed"),
        ("completed_with_repair", 1, -1, "completed"),
        ("completed", 0, None, "completed"),
        ("completed", 1, 1, "results_available"),
        ("completed", 1, None, "results_available"),
    ],
)
def test_section_status_preserves_run_failures_and_external_results(
    workflow: OverviewWorkflow,
    run_state: WorkflowRunState | None,
    count: int,
    result_offset: int | None,
    expected: ModelSectionState,
) -> None:
    completed_at = datetime(2026, 9, 28, 12, tzinfo=UTC)
    metric = WorkflowMetric(
        model_id=18,
        model_revision=4,
        workflow=workflow,
        result_count=count,
        locked_count=0,
        latest_run_state=run_state,
        latest_run_completed_at=completed_at
        if run_state in ("completed", "completed_with_repair")
        else None,
        latest_result_updated_at=completed_at + timedelta(seconds=result_offset)
        if result_offset is not None
        else None,
    )
    assert _section_state(metric) == expected


@pytest.mark.parametrize(
    ("workflow", "count", "expected"),
    [
        ("scope", 0, "empty"),
        ("scope", 1, "ready"),
        ("assertions", 0, "not_run"),
        ("assertions", 1, "results_available"),
    ],
)
def test_manual_sections_do_not_claim_a_workflow_completed(
    workflow: OverviewWorkflow,
    count: int,
    expected: ModelSectionState,
) -> None:
    metric = WorkflowMetric(
        model_id=18,
        model_revision=4,
        workflow=workflow,
        result_count=count,
        locked_count=0,
    )
    assert _section_state(metric) == expected
