"""Exact dispatch from a durable claim to one Workflow executor."""

from dataclasses import dataclass

from .contracts import WorkflowExecutionClaim, WorkflowExecutor


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
        else:
            executor = self._services.code_generation

        return await executor.execute_started(
            claim.principal,
            tenant_id=claim.tenant_id,
            model_id=claim.model_id,
            workflow_run_id=claim.workflow_run_id,
            expected_model_revision=claim.model_revision,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )


__all__ = ["WorkflowExecutionDispatcher", "WorkflowExecutionServices"]
