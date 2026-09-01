from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.features.workflows.execution import (
    WorkflowExecutionClaim,
    WorkflowExecutionDispatcher,
    WorkflowExecutionServices,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> object:
        self.calls.append(
            {
                "principal": principal,
                "tenant_id": tenant_id,
                "model_id": model_id,
                "workflow_run_id": workflow_run_id,
                "expected_model_revision": expected_model_revision,
                "workflow_run_claim_token": workflow_run_claim_token,
            }
        )
        return object()


def _claim(
    *,
    model_workflow: str,
    workflow_execution_mode: str | None = None,
    actor_principal_type: str = "user",
) -> WorkflowExecutionClaim:
    claimed_at = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
    return WorkflowExecutionClaim.model_validate(
        {
            "workflow_run_id": 701,
            "tenant_id": 7,
            "model_id": 18,
            "model_revision": 4,
            "model_workflow": model_workflow,
            "workflow_execution_mode": workflow_execution_mode,
            "correlation_id": UUID("11111111-1111-1111-1111-111111111111"),
            "actor_principal_type": actor_principal_type,
            "actor_entra_tenant_id": UUID("22222222-2222-2222-2222-222222222222"),
            "actor_entra_object_id": UUID("33333333-3333-3333-3333-333333333333"),
            "workflow_run_claim_token": UUID("44444444-4444-4444-4444-444444444444"),
            "workflow_run_claimed_time": claimed_at,
            "workflow_run_claim_expires_time": claimed_at + timedelta(seconds=30),
            "workflow_run_recovery_count": 0,
        },
        strict=True,
    )


def _services() -> tuple[WorkflowExecutionServices, dict[str, RecordingExecutor]]:
    executors = {
        name: RecordingExecutor()
        for name in (
            "profiling",
            "analysis_inference",
            "analysis_validation",
            "conceptual",
            "logical",
            "dimensional",
            "mapping",
            "code_generation",
            "qa",
        )
    }
    return WorkflowExecutionServices(**executors), executors


@pytest.mark.parametrize(
    ("model_workflow", "workflow_execution_mode", "expected_executor"),
    [
        ("profiling", None, "profiling"),
        ("analysis", "one_shot", "analysis_inference"),
        ("analysis", None, "analysis_validation"),
        ("conceptual", "tool_assisted", "conceptual"),
        ("logical", "detailed_coverage", "logical"),
        ("dimensional", "one_shot", "dimensional"),
        ("mapping", "tool_assisted", "mapping"),
        ("code_generation", None, "code_generation"),
        ("qa", None, "qa"),
    ],
)
@pytest.mark.asyncio
async def test_dispatcher_routes_each_claim_to_the_exact_workflow_executor(
    model_workflow: str,
    workflow_execution_mode: str | None,
    expected_executor: str,
) -> None:
    services, executors = _services()
    claim = _claim(
        model_workflow=model_workflow,
        workflow_execution_mode=workflow_execution_mode,
    )

    await WorkflowExecutionDispatcher(services).execute(claim)

    called = [name for name, executor in executors.items() if executor.calls]
    assert called == [expected_executor]
    assert executors[expected_executor].calls == [
        {
            "principal": RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=UUID("22222222-2222-2222-2222-222222222222"),
                entra_object_id=UUID("33333333-3333-3333-3333-333333333333"),
            ),
            "tenant_id": 7,
            "model_id": 18,
            "workflow_run_id": 701,
            "expected_model_revision": 4,
            "workflow_run_claim_token": UUID("44444444-4444-4444-4444-444444444444"),
        }
    ]


@pytest.mark.asyncio
async def test_dispatcher_reconstructs_a_workload_principal_server_side() -> None:
    services, executors = _services()

    await WorkflowExecutionDispatcher(services).execute(
        _claim(
            model_workflow="code_generation",
            actor_principal_type="service_principal",
        )
    )

    principal = executors["code_generation"].calls[0]["principal"]
    assert principal.actor_kind is ActorKind.WORKLOAD


def test_claim_repr_never_exposes_the_raw_claim_token() -> None:
    claim = _claim(model_workflow="profiling")

    assert str(claim.workflow_run_claim_token) not in repr(claim)


def test_claim_serialization_never_exposes_the_raw_claim_token() -> None:
    claim = _claim(model_workflow="profiling")
    token = str(claim.workflow_run_claim_token)

    assert "workflow_run_claim_token" not in claim.model_dump()
    assert token not in claim.model_dump_json()
