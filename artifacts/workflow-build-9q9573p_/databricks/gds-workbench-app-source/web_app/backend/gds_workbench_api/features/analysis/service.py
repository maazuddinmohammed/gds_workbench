"""Execute one already-running Analysis inference run."""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import ModelValidationIssue
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    PhysicalAttributeKey,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

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
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageRunner,
)

from .candidate import AnalysisInferenceCandidateValidator

_logger = logging.getLogger(__name__)


class AnalysisInferenceExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class AnalysisInferencePlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class AnalysisInferenceContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle: ...


class AnalysisInferenceChangeSetHandoff(Protocol):
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


class AnalysisInferenceNoOpCompleter(Protocol):
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


class AnalysisInferenceLifecycle(Protocol):
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


class AnalysisInferenceExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_inference_execution_failed",
            message=("Analysis inference failed before a validated draft was committed."),
        )


class AnalysisInferenceFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_inference_finalization_failed",
            message="Analysis finalization outcome could not be confirmed.",
        )


class AnalysisInferenceRunLifecycle(Protocol):
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


class AnalysisInferenceExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> WorkflowChangeSetHandoffResult | None: ...


class AnalysisInferenceWorkflow:
    """Bind the public route to one explicit supported Analysis mode."""

    def __init__(
        self,
        *,
        lifecycle: AnalysisInferenceRunLifecycle,
        executor: AnalysisInferenceExecutor,
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
            expected_workflow="analysis",
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
    ) -> WorkflowChangeSetHandoffResult | None:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseAnalysisInferenceExecutor:
    """Load frozen inputs, repair one candidate, and hand off one complete draft."""

    def __init__(
        self,
        *,
        database: AnalysisInferenceExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: AnalysisInferenceChangeSetHandoff,
        no_op: AnalysisInferenceNoOpCompleter,
        lifecycle: AnalysisInferenceLifecycle,
        plan_repository: AnalysisInferencePlanRepository | None = None,
        context_repository: AnalysisInferenceContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresAgentContextRepository()
        selected_context_policy = context_policy or load_default_agent_context_policy()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=selected_context_policy,
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
    ) -> WorkflowChangeSetHandoffResult | None:
        finalization_attempted = False
        changes: tuple[StageModelChange, ...] = ()
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

            execution_mode = cast(WorkflowExecutionMode, plan.workflow_execution_mode)
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
                stage="analysis.relationship_inference",
                status="running",
                message=(
                    f"Analysis relationship inference started for {selected_object_count} "
                    "selected Objects. The next persisted milestone follows bounded "
                    "agent response validation."
                ),
                current=0 if selected_object_count else None,
                total=selected_object_count or None,
                finding_count=0,
            )
            if not any(selected.attributes for selected in context.context.selected_objects):
                raise InvalidRequestError(
                    "The selected Analysis scope contains no Attributes to analyze."
                )
            validator = _candidate_validator(context)
            resolver_key = f"workflow.analysis.{execution_mode}.relationship_inference.context"
            outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="relationship_inference",
                resolver_values={
                    resolver_key: context.embedded_context,
                    "workflow.validation_failures": [],
                },
                context=context.embedded_context,
                output_schema=validator.output_schema(),
                allowed_tool_names=(
                    context.tool_catalog.allowed_tool_names
                    if context.tool_catalog is not None
                    else ()
                ),
                local_tool_catalog=context.tool_catalog,
                validator=validator,
            )
            candidate = outcome.candidate
            final_attempt = outcome.attempt_count
            changes = validator.parse_validated(candidate)
            finding_count = sum(len(change.records) for change in changes)
            warning = outcome.was_repaired or bool(outcome.warning_codes)
            final_event = progress.event(
                attempt=final_attempt,
                stage="analysis.backend_validation",
                status="warning" if warning else "running",
                message=(
                    "Analysis inference completed without effective changes."
                    if not changes
                    else "Analysis findings are ready in a validated draft."
                ),
                current=1,
                total=1,
                finding_count=finding_count,
            )
            if changes:
                finalization_attempted = True
                finalization = await self._handoff.finalize(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    expected_workflow="analysis",
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    changes=changes,
                    final_event=final_event,
                )
                return finalization.handoff

            finalization_attempted = True
            await self._no_op.complete(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                request=AuthoringNoOpRequest(
                    expected_workflow="analysis",
                    expected_execution_mode=execution_mode,
                    expected_correlation_id=plan.correlation_id,
                    expected_model_revision=expected_model_revision,
                    candidate_digest=authoring_no_op_candidate_digest(plan),
                    final_event=final_event,
                ),
            )
            return None
        except Exception as error:
            if isinstance(error, WorkflowChangeSetValidationError) and changes:
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        model_id=model_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="analysis",
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        changes=changes,
                        issues=error.issues,
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
                    "Analysis Workflow Run finalization remains pending.",
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
                        "Analysis inference failure state could not be persisted.",
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
        ) and stage_codes == ("relationship_inference",)
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "analysis"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError(
                "The Analysis inference run does not use the fixed execution path."
            )


def _candidate_validator(
    context: AgentContextBundle,
) -> AnalysisInferenceCandidateValidator:
    selected_attributes = tuple(
        PhysicalAttributeKey(
            tenant_code=attribute.tenant_code,
            system_code=attribute.system_code,
            connection_code=attribute.connection_code,
            object_schema=attribute.object_schema,
            object_name=attribute.object_name,
            attribute_name=attribute.attribute_name,
        )
        for selected in context.context.selected_objects
        for attribute in selected.attributes
    )
    return AnalysisInferenceCandidateValidator(
        selected_attribute_keys=selected_attributes,
        applied=context.context.analysis_relationships,
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return AnalysisInferenceFinalizationFailedError()
    return AnalysisInferenceExecutionFailedError()


__all__ = [
    "AnalysisInferenceExecutionFailedError",
    "AnalysisInferenceFinalizationFailedError",
    "AnalysisInferenceWorkflow",
    "DatabaseAnalysisInferenceExecutor",
]
