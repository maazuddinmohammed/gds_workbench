"""Execute one already-running Conceptual authoring run."""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import (
    ModelValidationIssue,
    validate_future_graph,
)
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    PhysicalObjectKey,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    PostgresAgentContextRepository,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.naming import (
    effective_naming_instructions,
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
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.progress import (
    AgentWorkflowProgress,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
    model_validation_issues,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageRunner,
)

from .candidate import ConceptualCandidateValidator

_logger = logging.getLogger(__name__)


class ConceptualExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class ConceptualPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class ConceptualContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle: ...


class ConceptualChangeSetHandoff(Protocol):
    async def retain_failed_candidate(
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
        issues: tuple[ModelValidationIssue, ...],
        failure_code: str,
        safe_failure_message: str,
    ) -> object: ...

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


class ConceptualNoOpCompleter(Protocol):
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


class ConceptualLifecycle(Protocol):
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


class ConceptualExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_execution_failed",
            message=("Conceptual authoring failed before a validated draft was committed."),
        )


class ConceptualFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_finalization_failed",
            message="Conceptual finalization outcome could not be confirmed.",
        )


type ConceptualExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class ConceptualRunLifecycle(Protocol):
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
    ) -> AgentWorkflowRunStart: ...


class ConceptualExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> ConceptualExecutionResult: ...


class ConceptualWorkflow:
    """Bind the public route to one explicit supported Conceptual mode."""

    def __init__(
        self,
        *,
        lifecycle: ConceptualRunLifecycle,
        executor: ConceptualExecutor,
    ) -> None:
        self._lifecycle = lifecycle
        self._executor = executor

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
        return await self._lifecycle.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="conceptual",
            expected_execution_mode=expected_execution_mode,
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
    ) -> ConceptualExecutionResult:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseConceptualExecutor:
    """Load frozen inputs, repair one candidate, and hand off one validated draft."""

    def __init__(
        self,
        *,
        database: ConceptualExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: ConceptualChangeSetHandoff,
        no_op: ConceptualNoOpCompleter,
        lifecycle: ConceptualLifecycle,
        plan_repository: ConceptualPlanRepository | None = None,
        context_repository: ConceptualContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresAgentContextRepository()
        self._context_policy = context_policy or load_default_agent_context_policy()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=self._context_policy,
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
    ) -> ConceptualExecutionResult:
        finalization_attempted = False
        changes: tuple[StageModelChange, ...] = ()
        rejected_changes: tuple[StageModelChange, ...] = ()
        rejected_issues: tuple[ModelValidationIssue, ...] = ()
        try:
            async with self._database.write_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_MODEL_WRITE,
                    model_id=model_id,
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

            execution_mode = plan.workflow_execution_mode
            selected_object_count = len(context.context.selected_objects)
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage=("conceptual.candidate_authoring"),
                status="running",
                message=(
                    f"Conceptual candidate authoring started for {selected_object_count} "
                    "selected Objects. The next persisted milestone follows bounded "
                    "agent response validation."
                ),
                current=0 if selected_object_count else None,
                total=selected_object_count or None,
                finding_count=0,
            )

            validator = _candidate_validator(context)
            snapshot = context.snapshot
            physical_scope = context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Conceptual validation context is unavailable.")

            async def validate_complete_candidate(value: JsonValue) -> AgentCandidateValidation:
                nonlocal rejected_changes, rejected_issues
                candidate_changes = validator.parse_validated(value)
                checked = validate_future_graph(
                    snapshot=snapshot,
                    staged_documents={
                        change.dataset: change.records for change in candidate_changes
                    },
                    physical_scope=physical_scope,
                )
                if checked.issues:
                    rejected_changes = candidate_changes
                    rejected_issues = checked.issues
                return AgentCandidateValidation(issues=model_validation_issues(checked.issues))

            resolver_key = f"workflow.conceptual.{execution_mode}.candidate_authoring.context"
            resolver_values: dict[str, object] = {
                resolver_key: context.embedded_context,
                "workflow.validation_failures": [],
            }
            resolver_values["model.naming_instructions"] = effective_naming_instructions(
                "conceptual",
                context.context.model_details.silver_model_naming_instructions,
            )
            outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="candidate_authoring",
                resolver_values=resolver_values,
                context=context.embedded_context,
                output_schema=validator.output_schema(),
                allowed_tool_names=(
                    context.tool_catalog.allowed_tool_names
                    if context.tool_catalog is not None
                    else ()
                ),
                local_tool_catalog=context.tool_catalog,
                validator=validator,
                final_validation=validate_complete_candidate,
            )
            candidate = outcome.candidate
            final_attempt = outcome.attempt_count
            changes = validator.parse_validated(candidate)
            warning = outcome.was_repaired or bool(outcome.warning_codes)
            if not changes:
                finalization_attempted = True
                return await self._no_op.complete(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    request=AuthoringNoOpRequest(
                        expected_workflow="conceptual",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_model_revision=expected_model_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=final_attempt,
                            stage="conceptual.backend_validation",
                            status="warning" if warning else "running",
                            message=("Conceptual authoring completed with no effective change."),
                            current=1,
                            total=1,
                            finding_count=0,
                        ),
                    ),
                )

            staged_record_count = sum(len(change.records) for change in changes)
            finalization_attempted = True
            finalization = await self._handoff.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="conceptual",
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=progress.event(
                    attempt=final_attempt,
                    stage="conceptual.backend_validation",
                    status="warning" if warning else "running",
                    message="Conceptual candidate is ready in a validated draft.",
                    current=1,
                    total=1,
                    finding_count=staged_record_count,
                ),
            )
            return finalization.handoff
        except Exception as error:
            retention_issues = (
                error.issues if isinstance(error, WorkflowChangeSetValidationError) else ()
            )
            if isinstance(error, AgentCandidateValidationError) and rejected_changes:
                changes = rejected_changes
                retention_issues = rejected_issues
            if retention_issues and changes and isinstance(error, WorkbenchError):
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        model_id=model_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="conceptual",
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        changes=changes,
                        issues=retention_issues,
                        failure_code=error.code,
                        safe_failure_message=(
                            "Validation failed. A rejected draft was retained for review."
                        ),
                    )
                except Exception as retention_error:
                    _logger.warning(
                        "Rejected Workflow draft retention remains pending.",
                        extra={"workflow_run_id": workflow_run_id, "model_id": model_id},
                    )
                    raise _safe_execution_error(
                        retention_error,
                        finalization_attempted=True,
                    ) from None
                raise error from None
            safe_error = _safe_execution_error(
                error,
                finalization_attempted=finalization_attempted,
            )
            if finalization_attempted:
                _logger.warning(
                    "Conceptual Workflow Run finalization remains pending.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
            else:
                try:
                    await self._lifecycle.fail(
                        principal,
                        workflow_run_id=workflow_run_id,
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        failure_code=safe_error.code[:100],
                        safe_failure_message=safe_error.message[:2000],
                    )
                except Exception:
                    _logger.warning(
                        "Conceptual failure state could not be persisted.",
                        extra={
                            "workflow_run_id": workflow_run_id,
                            "model_id": model_id,
                            "failure_code": safe_error.code[:100],
                        },
                    )
            raise safe_error from None

    @staticmethod
    def _validate_plan(
        plan: AgentRunPlan,
        *,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> None:
        stage_codes = tuple(stage.stage_code for stage in plan.stages)
        mode_path_is_valid = plan.workflow_execution_mode in (
            "one_shot",
            "tool_assisted",
        ) and stage_codes == ("candidate_authoring",)
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "conceptual"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Conceptual run does not use the fixed execution path.")


def _candidate_validator(context: AgentContextBundle) -> ConceptualCandidateValidator:
    selected = tuple(
        PhysicalObjectKey(
            tenant_code=item.object.tenant_code,
            system_code=item.object.system_code,
            connection_code=item.object.connection_code,
            object_schema=item.object.object_schema,
            object_name=item.object.object_name,
        )
        for item in context.context.selected_objects
    )
    assertion_keys = tuple(
        record.modeling_assertion_record_key for record in context.context.assertion.records
    )
    return ConceptualCandidateValidator(
        selected_object_keys=selected,
        assertion_record_keys=assertion_keys,
        applied=context.context.applied.conceptual,
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return ConceptualFinalizationFailedError()
    return ConceptualExecutionFailedError()


__all__ = [
    "ConceptualWorkflow",
    "ConceptualExecutionFailedError",
    "ConceptualFinalizationFailedError",
    "DatabaseConceptualExecutor",
]
