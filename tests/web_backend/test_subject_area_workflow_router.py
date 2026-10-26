"""The Subject Area execute route only starts a run; a worker executes it later."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.features.subject_areas.router import ExecuteSubjectAreaRunRequest
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)
from gds_workbench_api.main import create_app

_CLAIM_TOKEN = UUID("44444444-4444-4444-8444-444444444444")
_EXECUTE = "/api/v1/tenants/7/projects/18/subject-areas/runs/1048/execute"


@dataclass
class _StaticSubjectAreaWorkflowService:
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
        project_id: int,
        workflow_run_id: int,
        expected_execution_mode: str,
        expected_project_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal
        self.starts.append(
            (
                tenant_id,
                project_id,
                workflow_run_id,
                expected_execution_mode,
                expected_project_revision,
            )
        )
        return AgentWorkflowRunStart(
            changed=self.changed,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
            project_revision=expected_project_revision,
        )

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
    ) -> None:
        del principal
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.executions.append((tenant_id, project_id, workflow_run_id, expected_project_revision))


def _client(service: _StaticSubjectAreaWorkflowService) -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            subject_area_workflow_service=service,
        )
    )


def test_execute_endpoint_starts_without_process_local_execution() -> None:
    service = _StaticSubjectAreaWorkflowService()

    with _client(service) as client:
        response = client.post(
            _EXECUTE, json={"execution_mode": "tool_assisted", "expected_project_revision": 4}
        )

    assert response.status_code == 202
    assert response.json()["workflow_run_state"] == "running"
    assert (
        ExecuteSubjectAreaRunRequest.model_validate(
            {"execution_mode": "tool_assisted", "expected_project_revision": 4}, strict=True
        ).expected_project_revision
        == 4
    )
    assert service.starts == [(7, 18, 1048, "tool_assisted", 4)]
    assert service.executions == []


def test_execute_endpoint_does_not_duplicate_an_already_started_run() -> None:
    service = _StaticSubjectAreaWorkflowService(changed=False)

    with _client(service) as client:
        response = client.post(
            _EXECUTE, json={"execution_mode": "one_shot", "expected_project_revision": 4}
        )

    assert response.status_code == 200
    assert service.starts == [(7, 18, 1048, "one_shot", 4)]
    assert service.executions == []


def test_execute_endpoint_accepts_explicit_one_shot_mode() -> None:
    service = _StaticSubjectAreaWorkflowService()

    with _client(service) as client:
        response = client.post(
            _EXECUTE, json={"execution_mode": "one_shot", "expected_project_revision": 4}
        )

    assert response.status_code == 202
    assert service.starts == [(7, 18, 1048, "one_shot", 4)]
    assert service.executions == []


def test_execute_endpoint_rejects_unknown_modes_and_fields_before_starting() -> None:
    service = _StaticSubjectAreaWorkflowService()
    # The run's tables are frozen when it is created; execute cannot pick tables.
    bodies: tuple[dict[str, object], ...] = (
        {"execution_mode": "batch", "expected_project_revision": 4},
        {"execution_mode": "one_shot", "expected_project_revision": 0},
        {"execution_mode": "one_shot", "expected_project_revision": 4, "tables": ["t1"]},
    )

    with _client(service) as client:
        responses = [client.post(_EXECUTE, json=body) for body in bodies]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert service.starts == []
