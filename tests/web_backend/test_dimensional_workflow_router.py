from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.features.dimensional.router import (
    ExecuteDimensionalRunRequest,
    create_dimensional_workflow_router,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)


@dataclass
class _StaticDimensionalWorkflowService:
    changed: bool = True
    starts: list[tuple[int, int, int, str, int]] = field(
        default_factory=lambda: list[tuple[int, int, int, str, int]]()
    )
    executions: list[tuple[int, int, int, int]] = field(
        default_factory=lambda: list[tuple[int, int, int, int]]()
    )

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_execution_mode: str,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal
        self.starts.append(
            (
                tenant_id,
                model_id,
                workflow_run_id,
                expected_execution_mode,
                expected_model_revision,
            )
        )
        return AgentWorkflowRunStart(
            changed=self.changed,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
            model_revision=expected_model_revision,
        )

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> None:
        del principal
        self.executions.append((tenant_id, model_id, workflow_run_id, expected_model_revision))


def _client(service: _StaticDimensionalWorkflowService) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_dimensional_workflow_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=service,
        )
    )
    return TestClient(app)


def test_execute_endpoint_starts_without_process_local_execution() -> None:
    service = _StaticDimensionalWorkflowService()

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/dimensional/runs/1048/execute",
            json={
                "execution_mode": "tool_assisted",
                "expected_model_revision": 4,
            },
        )

    assert response.status_code == 202
    assert (
        ExecuteDimensionalRunRequest.model_validate(
            {
                "execution_mode": "tool_assisted",
                "expected_model_revision": 4,
            },
            strict=True,
        ).expected_model_revision
        == 4
    )
    assert service.starts == [(7, 18, 1048, "tool_assisted", 4)]
    assert service.executions == []


def test_execute_endpoint_does_not_reschedule_an_already_started_one_shot_run() -> None:
    service = _StaticDimensionalWorkflowService(changed=False)

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/dimensional/runs/1048/execute",
            json={"execution_mode": "one_shot", "expected_model_revision": 4},
        )

    assert response.status_code == 200
    assert service.starts == [(7, 18, 1048, "one_shot", 4)]
    assert service.executions == []


def test_execute_endpoint_accepts_explicit_detailed_coverage_mode() -> None:
    service = _StaticDimensionalWorkflowService()

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/dimensional/runs/1048/execute",
            json={
                "execution_mode": "detailed_coverage",
                "expected_model_revision": 4,
            },
        )

    assert response.status_code == 202
    assert service.starts == [(7, 18, 1048, "detailed_coverage", 4)]
    assert service.executions == []
