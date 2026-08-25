from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.features.conceptual.router import ExecuteConceptualRunRequest
from gds_workbench_api.features.conceptual.service import ConceptualWorkflow
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)
from gds_workbench_api.main import create_app

_CLAIM_TOKEN = UUID("44444444-4444-4444-8444-444444444444")


@dataclass
class _StaticConceptualWorkflowService:
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
        workflow_run_claim_token: UUID,
    ) -> None:
        del principal
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.executions.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )


@dataclass
class _Lifecycle:
    expected_bindings: list[tuple[str, str | None]] = field(
        default_factory=lambda: list[tuple[str, str | None]]()
    )

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: str,
        expected_execution_mode: str | None,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal, tenant_id, model_id
        self.expected_bindings.append((expected_workflow, expected_execution_mode))
        return AgentWorkflowRunStart(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
            model_revision=expected_model_revision,
        )


@dataclass
class _Executor:
    calls: int = 0

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> WorkflowChangeSetHandoffResult:
        assert workflow_run_claim_token == _CLAIM_TOKEN
        del principal, tenant_id, model_id, workflow_run_id, expected_model_revision
        self.calls += 1
        return WorkflowChangeSetHandoffResult(
            model_id=18,
            workflow_run_id=1048,
            model_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            replayed=False,
            draft_revision=2,
            candidate_digest="c" * 64,
            staged_record_count=1,
            validated_at=datetime(2026, 8, 24, 10, 1, tzinfo=UTC),
        )


def _client(service: _StaticConceptualWorkflowService) -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            conceptual_workflow_service=service,
        )
    )


def test_execute_endpoint_starts_without_process_local_execution() -> None:
    service = _StaticConceptualWorkflowService()

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/conceptual/runs/1048/execute",
            json={
                "execution_mode": "tool_assisted",
                "expected_model_revision": 4,
            },
        )

    assert response.status_code == 202
    assert (
        ExecuteConceptualRunRequest.model_validate(
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


def test_execute_endpoint_does_not_duplicate_an_already_started_run() -> None:
    service = _StaticConceptualWorkflowService(changed=False)

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/conceptual/runs/1048/execute",
            json={"execution_mode": "one_shot", "expected_model_revision": 4},
        )

    assert response.status_code == 200
    assert service.starts == [(7, 18, 1048, "one_shot", 4)]
    assert service.executions == []


@pytest.mark.asyncio
async def test_workflow_binds_route_to_the_explicit_conceptual_mode() -> None:
    lifecycle = _Lifecycle()
    executor = _Executor()
    service = ConceptualWorkflow(lifecycle=lifecycle, executor=executor)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    await service.start(
        principal,
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_execution_mode="tool_assisted",
        expected_model_revision=4,
    )
    await service.execute_started(
        principal,
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert lifecycle.expected_bindings == [("conceptual", "tool_assisted")]
    assert executor.calls == 1


def test_execute_endpoint_accepts_explicit_detailed_mode() -> None:
    service = _StaticConceptualWorkflowService()

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/conceptual/runs/1048/execute",
            json={
                "execution_mode": "detailed_coverage",
                "expected_model_revision": 4,
            },
        )

    assert response.status_code == 202
    assert service.starts == [(7, 18, 1048, "detailed_coverage", 4)]
    assert service.executions == []
