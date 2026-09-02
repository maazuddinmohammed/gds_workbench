"""Atomic durable receipt for an unchanged authoring candidate."""

from __future__ import annotations

import hashlib
import json
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Literal, LiteralString, Protocol, Self
from uuid import UUID

from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)

from .lifecycle import (
    AgentWorkflowEvent,
    raise_workflow_lifecycle_error,
    workflow_identity_triple,
)
from .plan import AgentRunPlan, ModelWorkflow, WorkflowExecutionMode

_AUTHORING_WORKFLOWS = frozenset(
    {
        "analysis",
        "conceptual",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
        "validation",
    }
)

_COMPLETE_AUTHORING_NO_OP_SQL: LiteralString = """
SELECT receipt.changed,
       receipt.workflow_run_id,
       receipt.workflow_run_state,
       receipt.model_id,
       receipt.model_revision,
       receipt.model_workflow,
       receipt.workflow_execution_mode,
       receipt.correlation_id,
       receipt.candidate_digest,
       receipt.final_event_sequence,
       receipt.final_event_attempt,
       receipt.final_event_stage,
       receipt.final_event_status,
       receipt.final_event_message,
       receipt.final_event_current,
       receipt.final_event_total,
       receipt.final_finding_count,
       receipt.completed_time AS completed_at
  FROM application.complete_authoring_workflow_run_no_op(
       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s, %s, %s
  ) AS receipt
"""


def authoring_no_op_candidate_digest(plan: AgentRunPlan) -> str:
    """Digest the immutable plan identity and unchanged authoring result."""
    document = {
        "schema_version": "1.0",
        "model_id": plan.model_id,
        "model_revision": plan.model_revision,
        "model_workflow": plan.model_workflow,
        "workflow_execution_mode": plan.workflow_execution_mode,
        "selected_scope_digest": plan.selected_scope_digest,
        "result": "no_effective_change",
    }
    encoded = json.dumps(
        document,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AuthoringNoOpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_workflow: ModelWorkflow
    expected_execution_mode: WorkflowExecutionMode | None
    expected_correlation_id: UUID
    expected_model_revision: int = Field(gt=0)
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_event: AgentWorkflowEvent

    @model_validator(mode="after")
    def validate_authoring_workflow(self) -> Self:
        if self.expected_workflow not in _AUTHORING_WORKFLOWS:
            raise ValueError("Only an authoring Workflow can complete with a no-op receipt")
        if (self.expected_workflow in {"code_generation", "validation"}) != (
            self.expected_execution_mode is None
        ):
            raise ValueError("The authoring Workflow execution mode is invalid")
        if (
            self.final_event.stage != f"{self.expected_workflow}.backend_validation"
            or self.final_event.status not in ("running", "warning")
            or self.final_event.current != 1
            or self.final_event.total != 1
            or self.final_event.finding_count != 0
        ):
            raise ValueError("The no-op backend-validation event is invalid")
        return self


class AuthoringNoOpReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: Literal["completed", "completed_with_repair"]
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None
    correlation_id: UUID
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool
    final_event: AgentWorkflowEvent
    completed_at: datetime

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if (
            self.final_event.stage != f"{self.model_workflow}.backend_validation"
            or self.final_event.status not in ("running", "warning")
            or self.final_event.current != 1
            or self.final_event.total != 1
            or self.final_event.finding_count != 0
            or (self.workflow_run_state == "completed_with_repair")
            != (self.final_event.attempt > 1)
        ):
            raise ValueError("The no-op receipt event is invalid")
        return self


class AuthoringNoOpTransaction(Protocol):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None: ...


class AuthoringNoOpDatabase(Protocol):
    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[AuthoringNoOpTransaction]: ...


class PostgresAuthoringNoOpRepository:
    def __init__(self, transaction: AuthoringNoOpTransaction) -> None:
        self._transaction = transaction

    async def complete(
        self,
        *,
        identity: tuple[UUID, UUID, str],
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        request: AuthoringNoOpRequest,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _COMPLETE_AUTHORING_NO_OP_SQL,
            identity
            + (
                tenant_id,
                model_id,
                workflow_run_id,
                request.expected_workflow,
                request.expected_execution_mode,
                request.expected_correlation_id,
                request.expected_model_revision,
                request.candidate_digest,
                request.final_event.sequence,
                request.final_event.attempt,
                request.final_event.stage,
                request.final_event.status,
                request.final_event.message,
                request.final_event.current,
                request.final_event.total,
                request.final_event.finding_count,
            ),
        )


class DatabaseAuthoringNoOpService:
    """Commit or exactly replay one server-owned no-op receipt."""

    def __init__(self, *, database: AuthoringNoOpDatabase) -> None:
        self._database = database

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        request: AuthoringNoOpRequest,
    ) -> AuthoringNoOpReceipt:
        identity = workflow_identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                row = await PostgresAuthoringNoOpRepository(transaction).complete(
                    identity=identity,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    request=request,
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        if row is None or not isinstance(row.get("changed"), bool):
            raise DependencyUnavailableError()
        try:
            receipt = AuthoringNoOpReceipt.model_validate(
                {
                    "model_id": row.get("model_id"),
                    "model_revision": row.get("model_revision"),
                    "workflow_run_id": row.get("workflow_run_id"),
                    "workflow_run_state": row.get("workflow_run_state"),
                    "model_workflow": row.get("model_workflow"),
                    "workflow_execution_mode": row.get("workflow_execution_mode"),
                    "correlation_id": row.get("correlation_id"),
                    "candidate_digest": row.get("candidate_digest"),
                    "replayed": not row["changed"],
                    "final_event": {
                        "sequence": row.get("final_event_sequence"),
                        "attempt": row.get("final_event_attempt"),
                        "stage": row.get("final_event_stage"),
                        "status": row.get("final_event_status"),
                        "message": row.get("final_event_message"),
                        "current": row.get("final_event_current"),
                        "total": row.get("final_event_total"),
                        "finding_count": row.get("final_finding_count"),
                    },
                    "completed_at": row.get("completed_at"),
                },
                strict=True,
            )
        except Exception:
            raise DependencyUnavailableError() from None
        if (
            receipt.model_id != model_id
            or receipt.workflow_run_id != workflow_run_id
            or receipt.model_revision != request.expected_model_revision
            or receipt.model_workflow != request.expected_workflow
            or receipt.workflow_execution_mode != request.expected_execution_mode
            or receipt.correlation_id != request.expected_correlation_id
            or receipt.candidate_digest != request.candidate_digest
            or receipt.final_event != request.final_event
        ):
            raise DependencyUnavailableError()
        return receipt


__all__ = [
    "AuthoringNoOpDatabase",
    "AuthoringNoOpReceipt",
    "AuthoringNoOpRequest",
    "DatabaseAuthoringNoOpService",
    "PostgresAuthoringNoOpRepository",
    "authoring_no_op_candidate_digest",
]
