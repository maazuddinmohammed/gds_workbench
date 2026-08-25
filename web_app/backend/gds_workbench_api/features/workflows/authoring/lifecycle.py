"""Governed state and safe event persistence for agent-backed Workflow Runs."""

from __future__ import annotations

import re
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Literal, LiteralString, Never, Protocol, Self
from uuid import UUID

from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    WorkbenchError,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.features.workflows.authoring.plan import (
    ModelWorkflow,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

_RUN_BINDING_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND run.model_workflow = %s
   AND run.workflow_execution_mode IS NOT DISTINCT FROM %s
"""

_START_SQL: LiteralString = """
SELECT started.changed,
       started.workflow_run_id,
       started.workflow_run_state,
       started.started_time AS started_at
  FROM application.start_workflow_run(%s, %s, %s, %s, %s) AS started
"""

_APPEND_EVENT_SQL: LiteralString = """
SELECT event.model_event_log_id
  FROM application.append_workflow_run_event(
       %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s
  ) AS event
"""

_COMPLETE_SQL: LiteralString = """
SELECT completed.changed,
       completed.workflow_run_id,
       completed.workflow_run_state,
       completed.completed_time AS completed_at
  FROM application.complete_workflow_run(%s, %s, %s, %s, %s, %s) AS completed
"""

_FAIL_SQL: LiteralString = """
SELECT failed.changed,
       failed.workflow_run_id,
       failed.workflow_run_state,
       failed.completed_time AS completed_at
  FROM application.fail_workflow_run(%s, %s, %s, %s, %s, %s, %s) AS failed
"""

type RunningState = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_repair",
    "failed",
]
type TerminalState = Literal["completed", "completed_with_repair", "failed"]
type ProgressStatus = Literal["running", "warning", "blocked"]


class LifecycleTransaction(Protocol):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None: ...


class AgentWorkflowLifecycleDatabase(Protocol):
    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[LifecycleTransaction]: ...


class AgentWorkflowRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: RunningState
    started_at: datetime | None
    model_revision: int = Field(gt=0)


class AgentWorkflowTerminalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: TerminalState
    completed_at: datetime


class AgentWorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sequence: int = Field(gt=1)
    attempt: int = Field(gt=0, le=6)
    stage: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    status: ProgressStatus
    message: str = Field(min_length=1, max_length=2000)
    current: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, gt=0)
    finding_count: int = Field(ge=0)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip() or re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("Workflow event messages must be safe printable text")
        return value

    @model_validator(mode="after")
    def validate_progress(self) -> Self:
        if (self.current is None) != (self.total is None):
            raise ValueError("Workflow event progress must be complete or absent")
        if self.current is not None and self.total is not None and self.current > self.total:
            raise ValueError("Workflow event progress exceeds its total")
        return self


async def append_agent_workflow_event(
    transaction: LifecycleTransaction,
    principal: RequestPrincipal,
    *,
    workflow_run_id: int,
    expected_model_revision: int,
    event: AgentWorkflowEvent,
) -> None:
    """Append or exactly replay one event inside the caller's transaction."""
    identity = workflow_identity_triple(principal)
    try:
        row = await transaction.fetch_one(
            _APPEND_EVENT_SQL,
            identity
            + (
                workflow_run_id,
                expected_model_revision,
                event.sequence,
                event.attempt,
                event.stage,
                event.status,
                event.message,
                event.current,
                event.total,
                event.finding_count,
            ),
        )
    except Exception as error:
        raise_workflow_lifecycle_error(error)
    if row is None:
        raise DependencyUnavailableError()


async def complete_agent_workflow_run(
    transaction: LifecycleTransaction,
    principal: RequestPrincipal,
    *,
    workflow_run_id: int,
    expected_model_revision: int,
    finding_count: int,
) -> AgentWorkflowTerminalResult:
    """Complete or exactly replay one Run inside the caller's transaction."""
    identity = workflow_identity_triple(principal)
    try:
        row = await transaction.fetch_one(
            _COMPLETE_SQL,
            identity + (workflow_run_id, expected_model_revision, finding_count),
        )
    except Exception as error:
        raise_workflow_lifecycle_error(error)
    if row is None:
        raise DependencyUnavailableError()
    return AgentWorkflowTerminalResult.model_validate(row, strict=True)


class DatabaseAgentWorkflowLifecycle:
    """Use only the governed Workflow Run functions for lifecycle mutations."""

    def __init__(self, *, database: AgentWorkflowLifecycleDatabase) -> None:
        self._database = database

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
        identity = workflow_identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                binding = await transaction.fetch_one(
                    _RUN_BINDING_SQL,
                    (
                        tenant_id,
                        model_id,
                        workflow_run_id,
                        expected_workflow,
                        expected_execution_mode,
                    ),
                )
                if binding is None:
                    raise WorkflowRunNotFoundError()
                row = await transaction.fetch_one(
                    _START_SQL,
                    identity + (workflow_run_id, expected_model_revision),
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return AgentWorkflowRunStart.model_validate(
            {**row, "model_revision": expected_model_revision},
            strict=True,
        )

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None:
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                await append_agent_workflow_event(
                    transaction,
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    event=event,
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        finding_count: int,
    ) -> AgentWorkflowTerminalResult:
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                result = await complete_agent_workflow_run(
                    transaction,
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    finding_count=finding_count,
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        return result

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> AgentWorkflowTerminalResult:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", failure_code):
            raise InvalidRequestError("Workflow failure metadata is invalid.")
        if (
            not safe_failure_message.strip()
            or len(safe_failure_message.encode("utf-8")) > 2000
            or re.search(r"[\x00-\x1f\x7f]", safe_failure_message)
        ):
            raise InvalidRequestError("Workflow failure metadata is invalid.")
        return await self._terminal(
            principal,
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            query=_FAIL_SQL,
            parameters=(
                workflow_run_id,
                expected_model_revision,
                failure_code,
                safe_failure_message,
            ),
        )

    async def _terminal(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        query: LiteralString,
        parameters: tuple[object, ...],
    ) -> AgentWorkflowTerminalResult:
        identity = workflow_identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                row = await transaction.fetch_one(query, identity + parameters)
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return AgentWorkflowTerminalResult.model_validate(row, strict=True)


def workflow_identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type


def raise_workflow_lifecycle_error(error: Exception) -> Never:
    if isinstance(error, WorkbenchError) and not isinstance(
        error,
        DependencyUnavailableError,
    ):
        raise error
    message = _primary_database_message(error)
    if message == "stale_model_revision":
        raise ModelRevisionConflictError() from error
    if message == "Workflow Run is unavailable":
        raise WorkflowRunNotFoundError() from error
    if message == "Workflow Run belongs to another Principal":
        raise AuthorizationDeniedError() from error
    for prefix in (
        "Workflow Run start denied: ",
        "Workflow Run event denied: ",
        "Workflow Run completion denied: ",
        "Workflow Run no-op completion denied: ",
        "Workflow Run failure denied: ",
    ):
        if message.startswith(prefix):
            code = message.removeprefix(prefix)
            if code == "tenant_lock_required":
                raise TenantLockRequiredError() from error
            if code == "tenant_locked":
                raise TenantLockedError("another Principal") from error
            raise AuthorizationDeniedError() from error
    if message.startswith("Workflow Run "):
        raise InvalidRequestError("The Workflow Run state transition is invalid.") from error
    raise DependencyUnavailableError() from error


def _primary_database_message(error: Exception) -> str:
    current: BaseException = error
    for _ in range(4):
        diagnostic = getattr(current, "diag", None)
        primary = getattr(diagnostic, "message_primary", None)
        if isinstance(primary, str) and primary:
            return primary
        if current.__cause__ is None:
            return str(current)
        current = current.__cause__
    return ""
