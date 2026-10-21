"""Exact dispatch from a durable claim to one Workflow executor."""

from __future__ import annotations

from contextlib import nullcontext, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gds_etl_workbench.domain.errors import InvalidRequestError

from gds_workbench_api.runtime_diagnostics import RuntimeDiagnostics

from .contracts import WorkflowExecutionClaim, WorkflowExecutor

if TYPE_CHECKING:
    from gds_workbench_api.features.workflows.authoring.lifecycle import (
        DatabaseAgentWorkflowLifecycle,
    )
    from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder


@dataclass(frozen=True, slots=True)
class WorkflowExecutionServices:
    profiling: WorkflowExecutor
    analysis_inference: WorkflowExecutor
    analysis_validation: WorkflowExecutor
    conceptual: WorkflowExecutor
    logical: WorkflowExecutor
    dimensional: WorkflowExecutor
    mapping: WorkflowExecutor
    code_generation: WorkflowExecutor
    validation: WorkflowExecutor
    metadata_enrichment: WorkflowExecutor
    usage_recorder: DatabaseWorkflowUsageRecorder | None = None
    lifecycle: DatabaseAgentWorkflowLifecycle | None = None


class WorkflowExecutionDispatcher:
    def __init__(
        self, services: WorkflowExecutionServices, *, diagnostics: RuntimeDiagnostics | None = None
    ) -> None:
        self._services = services
        self._diagnostics = diagnostics

    async def execute(self, claim: WorkflowExecutionClaim) -> object:
        if claim.project_workflow == "profiling":
            executor = self._services.profiling
        elif claim.project_workflow == "analysis":
            executor = (
                self._services.analysis_validation
                if claim.workflow_execution_mode is None
                else self._services.analysis_inference
            )
        elif claim.project_workflow == "conceptual":
            executor = self._services.conceptual
        elif claim.project_workflow == "logical":
            executor = self._services.logical
        elif claim.project_workflow == "dimensional":
            executor = self._services.dimensional
        elif claim.project_workflow == "mapping":
            executor = self._services.mapping
        elif claim.project_workflow == "code_generation":
            executor = self._services.code_generation
        elif claim.project_workflow == "validation":
            executor = self._services.validation
        elif claim.project_workflow == "metadata_enrichment":
            executor = self._services.metadata_enrichment
        else:
            raise InvalidRequestError("The requested workflow executor is unavailable.")

        recording = (
            self._services.usage_recorder.track_run(claim)
            if self._services.usage_recorder is not None
            else nullcontext()
        )
        executor_started = False
        try:
            if self._diagnostics is not None:
                self._diagnostics.enter("usage_initialization")
            async with recording:
                executor_started = True
                if self._diagnostics is not None:
                    self._diagnostics.enter("executor")
                return await executor.execute_started(
                    claim.principal,
                    tenant_id=claim.tenant_id,
                    project_id=claim.project_id,
                    workflow_run_id=claim.workflow_run_id,
                    expected_project_revision=claim.project_revision,
                    workflow_run_claim_token=claim.workflow_run_claim_token,
                )
        except Exception:
            if not executor_started and self._services.lifecycle is not None:
                # Startup runs before the executor's failure handler. Use the same
                # governed claim/revision/identity checks; never clear a claim directly.
                with suppress(Exception):
                    await self._services.lifecycle.fail(
                        claim.principal,
                        workflow_run_id=claim.workflow_run_id,
                        expected_project_revision=claim.project_revision,
                        workflow_run_claim_token=claim.workflow_run_claim_token,
                        failure_code="workflow_usage_unavailable",
                        safe_failure_message=(
                            "Workflow usage tracking could not initialize before execution. "
                            "Check database compatibility and access."
                        ),
                    )
            # If terminalization is unavailable, preserve bounded recovery and the
            # original cause for the worker's non-disclosing diagnostic.
            raise


__all__ = ["WorkflowExecutionDispatcher", "WorkflowExecutionServices"]
