"""Execute one already-running Validation authoring Workflow Run."""

from __future__ import annotations

import json
import logging
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import VALIDATION_AGENT_EXECUTION_MODE
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpReceipt,
    AuthoringNoOpRequest,
    authoring_no_op_candidate_digest,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    ModelWorkflow,
    PostgresAgentRunPlanRepository,
)
from gds_workbench_api.features.workflows.authoring.progress import (
    AgentWorkflowProgress,
    intermediate_progress_points,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

from .candidate import (
    ValidatedValidationSystemCandidate,
    ValidationSystemCandidateValidator,
    reconcile_validation_candidates,
)
from .context import PostgresValidationContextRepository, ValidationExecutionContext

_logger = logging.getLogger(__name__)


class ValidationExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class ValidationPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class ValidationContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> ValidationExecutionContext: ...


class ValidationChangeSetHandoff(Protocol):
    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
    ) -> WorkflowChangeSetFinalizationResult: ...


class ValidationNoOpCompleter(Protocol):
    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        request: AuthoringNoOpRequest,
    ) -> AuthoringNoOpReceipt: ...


class ValidationLifecycle(Protocol):
    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None: ...

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> AgentWorkflowTerminalResult: ...


class ValidationExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="validation_execution_failed",
            message="Validation authoring failed before a validated draft was committed.",
        )


class ValidationFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="validation_finalization_failed",
            message="Validation finalization outcome could not be confirmed.",
        )


type ValidationExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class ValidationRunLifecycle(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_execution_mode: None,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart: ...


class ValidationExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> ValidationExecutionResult: ...


class ValidationWorkflow:
    def __init__(self, *, lifecycle: ValidationRunLifecycle, executor: ValidationExecutor) -> None:
        self._lifecycle = lifecycle
        self._executor = executor

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        return await self._lifecycle.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="validation",
            expected_execution_mode=None,
            expected_model_revision=expected_model_revision,
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
    ) -> ValidationExecutionResult:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseValidationExecutor:
    def __init__(
        self,
        *,
        database: ValidationExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: ValidationChangeSetHandoff,
        no_op: ValidationNoOpCompleter,
        lifecycle: ValidationLifecycle,
        plan_repository: ValidationPlanRepository | None = None,
        context_repository: ValidationContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresValidationContextRepository()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=context_policy or load_default_agent_context_policy(),
        )
        self._handoff = handoff
        self._no_op = no_op
        self._lifecycle = lifecycle

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> ValidationExecutionResult:
        finalization_attempted = False
        try:
            async with self._database.write_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_MODEL_WRITE,
                )
                plan = await self._plan_repository.load(
                    transaction,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                )
                self._validate_plan(
                    plan,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                )
                context = await self._context_repository.load(
                    transaction,
                    tenant_id=tenant_id,
                    plan=plan,
                )

            system_count = len(context.systems)
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage="validation.validation_generation",
                status="running",
                message=f"Validation generation started for {system_count} Systems.",
                current=0,
                total=system_count,
                finding_count=0,
            )

            stage_plan = plan.model_copy(
                update={"workflow_execution_mode": VALIDATION_AGENT_EXECUTION_MODE}
            )
            candidates: list[ValidatedValidationSystemCandidate] = []
            progress_points = intermediate_progress_points(system_count) | {system_count}
            highest_attempt = 1
            warning_seen = False
            for position, system in enumerate(context.systems, start=1):
                validator = ValidationSystemCandidateValidator(context=system)
                outcome = await self._stage_runner.run(
                    plan=stage_plan,
                    stage_code="validation_generation",
                    resolver_values={
                        "workflow.validation.common.validation_context": (
                            _system_context_manifest(system.system_ref, system.agent_context)
                        ),
                        "workflow.validation_failures": [],
                    },
                    context=system.agent_context,
                    output_schema=validator.output_schema(),
                    allowed_tool_names=(),
                    validator=validator,
                )
                candidates.append(validator.parse_validated(outcome.candidate))
                highest_attempt = max(highest_attempt, outcome.attempt_count)
                warning_seen = warning_seen or bool(outcome.was_repaired or outcome.warning_codes)
                if position in progress_points:
                    message = (
                        f"Validation generation validated {position} of {system_count} Systems."
                    )
                    if warning_seen:
                        message += " One or more candidates required repair."
                    await progress.append(
                        attempt=highest_attempt,
                        stage="validation.validation_generation",
                        status="warning" if warning_seen else "running",
                        message=message,
                        current=position,
                        total=system_count,
                        finding_count=0,
                    )

            changes = reconcile_validation_candidates(
                context=context,
                candidates=tuple(candidates),
            )
            if not changes:
                finalization_attempted = True
                return await self._no_op.complete(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    request=AuthoringNoOpRequest(
                        expected_workflow="validation",
                        expected_execution_mode=None,
                        expected_correlation_id=plan.correlation_id,
                        expected_model_revision=expected_model_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=highest_attempt,
                            stage="validation.backend_validation",
                            status="warning" if warning_seen else "running",
                            message="Validation authoring completed with no effective change.",
                            current=1,
                            total=1,
                            finding_count=0,
                        ),
                    ),
                )

            staged_record_count = sum(len(change.records) for change in changes)
            finalization_attempted = True
            finalized = await self._handoff.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="validation",
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=progress.event(
                    attempt=highest_attempt,
                    stage="validation.backend_validation",
                    status="warning" if warning_seen else "running",
                    message="Validation candidate is ready in a validated draft.",
                    current=1,
                    total=1,
                    finding_count=staged_record_count,
                ),
            )
            return finalized.handoff
        except Exception as error:
            safe_error = _safe_execution_error(
                error,
                finalization_attempted=finalization_attempted,
            )
            if finalization_attempted:
                _logger.warning(
                    "Validation Workflow Run finalization remains pending.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
                raise safe_error from None
            try:
                await self._lifecycle.fail(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    failure_code=safe_error.code[:100],
                    safe_failure_message=safe_error.message[:2000],
                )
            except Exception as persistence_error:
                _logger.warning(
                    "Validation failure state could not be persisted.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
                raise _safe_execution_error(
                    persistence_error,
                    finalization_attempted=False,
                ) from None
            raise safe_error from None

    @staticmethod
    def _validate_plan(
        plan: AgentRunPlan,
        *,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> None:
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "validation"
            or plan.workflow_execution_mode is not None
            or plan.modeled_entity_type is not None
            or plan.selected_object_ids
            or not plan.selected_system_codes
            or len(plan.stages) != 1
            or plan.stages[0].stage_code != "validation_generation"
        ):
            raise InvalidRequestError("The Validation run does not use the fixed execution path.")


def _system_context_manifest(system_ref: str, context: JsonValue) -> JsonValue:
    encoded = json.dumps(
        context,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return cast(
        JsonValue,
        {
            "system_ref": system_ref,
            "system_context_delivery": "request_context_original_context",
            "system_context_sha256": sha256(encoded).hexdigest(),
            "system_context_byte_count": len(encoded),
        },
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return ValidationFinalizationFailedError()
    return ValidationExecutionFailedError()
