from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.features.analysis.router import (
    ExecuteAnalysisInferenceRunRequest,
)
from gds_workbench_api.features.analysis.service import AnalysisInferenceWorkflow
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    ModelWorkflow,
    WorkflowExecutionMode,
)
from gds_workbench_api.main import create_app

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


@dataclass
class _StaticService:
    changed: bool = True
    starts: list[tuple[int, int, int, WorkflowExecutionMode, int]] = field(
        default_factory=lambda: list[tuple[int, int, int, WorkflowExecutionMode, int]]()
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
        expected_execution_mode: WorkflowExecutionMode,
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
    ) -> object:
        del principal
        self.executions.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )
        return None


@dataclass
class _Lifecycle:
    bindings: list[tuple[str, str | None]] = field(
        default_factory=lambda: list[tuple[str, str | None]]()
    )

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_execution_mode: WorkflowExecutionMode | None,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal, tenant_id, model_id
        self.bindings.append((expected_workflow, expected_execution_mode))
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
    ) -> WorkflowChangeSetHandoffResult | None:
        assert workflow_run_claim_token == _CLAIM_TOKEN
        del principal, tenant_id, model_id, workflow_run_id, expected_model_revision
        self.calls += 1
        return None


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _client(service: _StaticService) -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            analysis_inference_workflow_service=service,
        )
    )


@pytest.mark.parametrize(
    "execution_mode",
    ("one_shot", "tool_assisted", "detailed_coverage"),
)
def test_inference_route_starts_without_process_local_execution(
    execution_mode: WorkflowExecutionMode,
) -> None:
    service = _StaticService()

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/analysis/inference-runs/1048/execute",
            json={
                "execution_mode": execution_mode,
                "expected_model_revision": 4,
            },
        )

    assert response.status_code == 202
    assert (
        ExecuteAnalysisInferenceRunRequest.model_validate(
            {
                "execution_mode": execution_mode,
                "expected_model_revision": 4,
            },
            strict=True,
        ).expected_model_revision
        == 4
    )
    assert service.starts == [(7, 18, 1048, execution_mode, 4)]
    assert service.executions == []


def test_inference_route_does_not_duplicate_an_already_started_run() -> None:
    service = _StaticService(changed=False)

    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/analysis/inference-runs/1048/execute",
            json={"execution_mode": "tool_assisted", "expected_model_revision": 4},
        )

    assert response.status_code == 200
    assert service.executions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted"))
async def test_workflow_binds_route_to_requested_analysis_mode(
    execution_mode: WorkflowExecutionMode,
) -> None:
    lifecycle = _Lifecycle()
    executor = _Executor()
    workflow = AnalysisInferenceWorkflow(lifecycle=lifecycle, executor=executor)

    await workflow.start(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_execution_mode=execution_mode,
        expected_model_revision=4,
    )
    await workflow.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert lifecycle.bindings == [("analysis", execution_mode)]
    assert executor.calls == 1
