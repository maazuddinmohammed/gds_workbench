"""Internal durable Workflow Run execution contracts."""

from datetime import datetime
from typing import Literal, Protocol, Self
from uuid import UUID

from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from pydantic import BaseModel, ConfigDict, Field, model_validator

type ModelWorkflow = Literal[
    "profiling",
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "qa",
]
type WorkflowExecutionMode = Literal[
    "one_shot",
    "tool_assisted",
    "detailed_coverage",
]


class WorkflowExecutionClaim(BaseModel):
    """One internal claim returned only to the web worker."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workflow_run_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None = None
    correlation_id: UUID
    actor_principal_type: Literal["user", "service_principal"]
    actor_entra_tenant_id: UUID
    actor_entra_object_id: UUID
    workflow_run_claim_token: UUID = Field(repr=False, exclude=True)
    workflow_run_claimed_time: datetime
    workflow_run_claim_expires_time: datetime
    workflow_run_recovery_count: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def validate_execution_shape(self) -> Self:
        requires_mode = self.model_workflow in {
            "conceptual",
            "logical",
            "dimensional",
            "mapping",
        }
        if requires_mode and self.workflow_execution_mode is None:
            raise ValueError("The claimed Workflow Run requires an execution mode")
        if self.model_workflow in {"profiling", "code_generation", "qa"} and (
            self.workflow_execution_mode is not None
        ):
            raise ValueError("The claimed Workflow Run cannot use an execution mode")
        if self.workflow_run_claim_expires_time <= self.workflow_run_claimed_time:
            raise ValueError("The Workflow Run claim expiry is invalid")
        return self

    @property
    def principal(self) -> RequestPrincipal:
        return RequestPrincipal(
            actor_kind=(
                ActorKind.HUMAN if self.actor_principal_type == "user" else ActorKind.WORKLOAD
            ),
            entra_tenant_id=self.actor_entra_tenant_id,
            entra_object_id=self.actor_entra_object_id,
        )


class WorkflowExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> object: ...


__all__ = [
    "ModelWorkflow",
    "WorkflowExecutionClaim",
    "WorkflowExecutionMode",
    "WorkflowExecutor",
]
