"""Exact dispatch from a durable claim to one Workflow executor."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gds_etl_workbench.domain.errors import InvalidRequestError

from .contracts import WorkflowExecutionClaim, WorkflowExecutor

if TYPE_CHECKING:
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


class WorkflowExecutionDispatcher:
    def __init__(self, services: WorkflowExecutionServices) -> None:
        self._services = services

    async def execute(self, claim: WorkflowExecutionClaim) -> object:
        if claim.model_workflow == "profiling":
            executor = self._services.profiling
        elif claim.model_workflow == "analysis":
            executor = (
                self._services.analysis_validation
                if claim.workflow_execution_mode is None
                else self._services.analysis_inference
            )
        elif claim.model_workflow == "conceptual":
            executor = self._services.conceptual
        elif claim.model_workflow == "logical":
            executor = self._services.logical
        elif claim.model_workflow == "dimensional":
            executor = self._services.dimensional
        elif claim.model_workflow == "mapping":
            executor = self._services.mapping
        elif claim.model_workflow == "code_generation":
            executor = self._services.code_generation
        elif claim.model_workflow == "validation":
            executor = self._services.validation
        elif claim.model_workflow == "metadata_enrichment":
            executor = self._services.metadata_enrichment
        else:
            raise InvalidRequestError("The requested workflow executor is unavailable.")

        recording = (
            self._services.usage_recorder.track_run(claim)
            if self._services.usage_recorder is not None
            else nullcontext()
        )
        async with recording:
            return await executor.execute_started(
                claim.principal,
                tenant_id=claim.tenant_id,
                model_id=claim.model_id,
                workflow_run_id=claim.workflow_run_id,
                expected_model_revision=claim.model_revision,
                workflow_run_claim_token=claim.workflow_run_claim_token,
            )


__all__ = ["WorkflowExecutionDispatcher", "WorkflowExecutionServices"]
