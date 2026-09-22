from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_workbench_api.features.code_generation.router import (
    ExecuteCodeGenerationRunRequest,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)
from gds_workbench_api.main import create_app


@dataclass
class _StaticCodeGenerationWorkflowService:
    changed: bool = True
    starts: list[tuple[int, int, int, int]] = field(
        default_factory=lambda: list[tuple[int, int, int, int]]()
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
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal
        self.starts.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
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
        self.executions.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )


def _client(service: _StaticCodeGenerationWorkflowService) -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            code_generation_workflow_service=service,
        )
    )


def test_execute_endpoint_starts_without_process_local_execution() -> None:
    service = _StaticCodeGenerationWorkflowService()

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/code-generation/runs/1048/execute",
            json={"expected_model_revision": 4},
        )

    assert response.status_code == 202
    assert (
        ExecuteCodeGenerationRunRequest.model_validate(
            {"expected_model_revision": 4}, strict=True
        ).expected_model_revision
        == 4
    )
    assert set(ExecuteCodeGenerationRunRequest.model_fields) == {
        "expected_model_revision"
    }
    assert response.json() == {
        "changed": True,
        "workflow_run_id": 1048,
        "workflow_run_state": "running",
        "started_at": "2026-08-24T10:00:00Z",
        "model_revision": 4,
    }
    assert "workflow_run_claim_token" not in response.text
    assert service.starts == [(7, 18, 1048, 4)]
    assert service.executions == []


def test_execute_endpoint_does_not_duplicate_an_already_started_run() -> None:
    service = _StaticCodeGenerationWorkflowService(changed=False)

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/code-generation/runs/1048/execute",
            json={"expected_model_revision": 4},
        )

    assert response.status_code == 200
    assert service.starts == [(7, 18, 1048, 4)]
    assert service.executions == []
