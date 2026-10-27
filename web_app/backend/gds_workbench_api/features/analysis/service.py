"""Start governed Analysis Inference Runs and execute them after worker claim."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    PhysicalAttributeKey,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
)
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizer,
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    AgentContextRepository,
    PostgresAgentContextRepository,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import (
    analysis_table_inputs,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowLifecycle,
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpCompleter,
    AuthoringNoOpRequest,
    authoring_no_op_candidate_digest,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    AgentRunPlanRepository,
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
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionDatabase

from .candidate import (
    AnalysisInferenceCandidateValidator,
    AnalysisTableCandidateValidator,
    merge_table_findings,
)

_logger = logging.getLogger(__name__)


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


class AnalysisInferenceWorkflow:
    """Start governed Runs; author inferred relationships only after worker claim."""

    def __init__(
        self,
        *,
        database: WorkflowExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: WorkflowChangeSetFinalizer,
        no_op: AuthoringNoOpCompleter,
        lifecycle: AgentWorkflowLifecycle,
        plan_repository: AgentRunPlanRepository | None = None,
        context_repository: AgentContextRepository | None = None,
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

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_execution_mode: WorkflowExecutionMode,
        expected_project_revision: int,
    ) -> AgentWorkflowRunStart:
        return await self._lifecycle.start(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="analysis",
            expected_execution_mode=expected_execution_mode,
            expected_project_revision=expected_project_revision,
        )

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
    ) -> WorkflowChangeSetHandoffResult | None:
        finalization_attempted = False
        changes: tuple[StageProjectChange, ...] = ()
        try:
            async with self._database.write_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_PROJECT_WRITE,
                    project_id=project_id,
                )
                plan = await self._plan_repository.load(
                    transaction,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                )
                self._validate_plan(
                    plan,
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                    expected_project_revision=expected_project_revision,
                )
                context = await self._context_repository.load(
                    transaction,
                    tenant_id=tenant_id,
                    plan=plan,
                )

            execution_mode = cast(WorkflowExecutionMode, plan.workflow_execution_mode)
            selected_object_count = len(context.context.selected_objects)
            per_table = plan.workflow_operation == "per_table"
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage="analysis.relationship_inference",
                status="running",
                message=(
                    f"Analysis started for {selected_object_count} selected Objects, "
                    "one table per call."
                    if per_table
                    else f"Analysis relationship inference started for {selected_object_count} "
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
            notes: list[str] = []
            if per_table:
                changes, final_attempt, notes, warning = await self._infer_by_table(
                    plan=plan, context=context, progress=progress
                )
            else:
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
                final_attempt = outcome.attempt_count
                changes = validator.parse_validated(outcome.candidate)
                warning = outcome.was_repaired or bool(outcome.warning_codes)
            finding_count = sum(len(change.records) for change in changes)
            summary = (
                "Analysis inference completed without effective changes."
                if not changes
                else "Analysis findings are ready in a validated draft."
            )
            final_event = progress.event(
                attempt=final_attempt,
                stage="analysis.backend_validation",
                status="warning" if warning else "running",
                message=f"{summary} {' '.join(notes)}"[:2000] if notes else summary,
                current=1,
                total=1,
                finding_count=finding_count,
            )
            if changes:
                finalization_attempted = True
                finalization = await self._handoff.finalize(
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                    expected_workflow="analysis",
                    expected_project_revision=expected_project_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    changes=changes,
                    final_event=final_event,
                )
                return finalization.handoff

            finalization_attempted = True
            await self._no_op.complete(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                request=AuthoringNoOpRequest(
                    expected_workflow="analysis",
                    expected_execution_mode=execution_mode,
                    expected_correlation_id=plan.correlation_id,
                    expected_project_revision=expected_project_revision,
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
                        project_id=project_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="analysis",
                        expected_project_revision=expected_project_revision,
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
                        extra={"workflow_run_id": workflow_run_id, "project_id": project_id},
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
                        "project_id": project_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
            else:
                try:
                    await self._lifecycle.fail(
                        principal,
                        workflow_run_id=workflow_run_id,
                        expected_project_revision=expected_project_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        failure_code=safe_error.code[:100],
                        safe_failure_message=safe_error.message[:2000],
                    )
                except Exception:
                    _logger.warning(
                        "Analysis inference failure state could not be persisted.",
                        extra={
                            "workflow_run_id": workflow_run_id,
                            "project_id": project_id,
                            "failure_code": safe_error.code[:100],
                        },
                    )
            raise safe_error from None

    async def _infer_by_table(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        progress: AgentWorkflowProgress,
    ) -> tuple[tuple[StageProjectChange, ...], int, list[str], bool]:
        """Make one call per selected table, two at a time, and join the answers in order.

        Each call sees its table in full and the key directory of every selected table, and
        returns only the links that start in its table. A table whose call still fails after
        its repair attempts adds a warning; the other tables' findings are kept, and the run
        fails only when no table could be analyzed. Findings on a pair of columns that is
        already linked are dropped before the draft.
        """
        tables = analysis_table_inputs(cast(dict[str, Any], context.embedded_context))
        selected_attribute_keys = _selected_attribute_keys(context)
        applied = context.context.analysis_relationships
        answers: list[tuple[StageProjectChange, ...]] = [() for _ in tables]
        failures: list[WorkbenchError] = []
        notes: list[str] = []
        pending = iter(enumerate(tables))
        progress_lock = asyncio.Lock()
        # Progress every 6 tables; the final event reports completion.
        progress_points = frozenset(range(6, len(tables), 6))
        final_attempt = 1
        completed = 0
        repaired = False

        async def analyze_tables() -> None:
            nonlocal final_attempt, completed, repaired
            # Taking the next table has no await, so two workers never share one.
            for position, inputs in pending:
                focus = inputs["focus_table"]
                name = f"{focus['object_schema']}.{focus['object_name']}"
                validator = AnalysisTableCandidateValidator(
                    inputs=inputs,
                    selected_attribute_keys=selected_attribute_keys,
                    applied=applied,
                )
                attempt_count = 1
                failure: WorkbenchError | None = None
                try:
                    outcome = await self._stage_runner.run(
                        plan=plan,
                        stage_code="per_table_authoring",
                        resolver_values={"workflow.validation_failures": []},
                        context=cast(JsonValue, {"prompt_inputs": inputs}),
                        output_schema=validator.output_schema(),
                        allowed_tool_names=(),
                        validator=validator,
                    )
                    answers[position] = validator.parse_validated(outcome.candidate)
                    attempt_count = outcome.attempt_count
                    repaired = repaired or outcome.was_repaired or bool(outcome.warning_codes)
                except WorkbenchError as error:
                    failure = error
                    failures.append(error)
                    notes.append(f"{name} was not analyzed: {error.message}")
                # Event order must stay sequential across the two workers. Failed tables are
                # always reported; otherwise progress is reported every 6 tables.
                async with progress_lock:
                    final_attempt = max(final_attempt, attempt_count)
                    completed += 1
                    if failure is None and completed not in progress_points:
                        continue
                    await progress.append(
                        attempt=final_attempt,
                        stage="analysis.per_table_authoring",
                        status="running" if failure is None else "warning",
                        message=f"Analyzed {completed} of {len(tables)} tables."
                        if failure is None
                        else f"{name} was not analyzed ({failure.code}).",
                        current=completed,
                        total=len(tables),
                        finding_count=sum(
                            len(change.records) for answer in answers for change in answer
                        ),
                    )

        workers = [asyncio.create_task(analyze_tables()) for _ in range(min(2, len(tables)))]
        try:
            await asyncio.gather(*workers)
        finally:
            # A lost claim, fatal error or cancellation stops the sibling worker too.
            for worker in workers:
                if not worker.done():
                    worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        if failures and len(failures) == len(tables):
            raise failures[0]
        changes, dropped = merge_table_findings(answers, applied)
        if dropped:
            notes.append(
                f"Dropped {dropped} {'finding' if dropped == 1 else 'findings'} on column "
                "pairs that were already linked."
            )
        return changes, final_attempt, notes, repaired or bool(failures)

    @staticmethod
    def _validate_plan(
        plan: AgentRunPlan,
        *,
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
    ) -> None:
        stage_codes = tuple(stage.stage_code for stage in plan.stages)
        mode_path_is_valid = (
            plan.workflow_operation is None
            and plan.workflow_execution_mode in ("one_shot", "tool_assisted")
            and stage_codes == ("relationship_inference",)
        ) or (
            plan.workflow_operation == "per_table"
            and plan.workflow_execution_mode == "one_shot"
            and stage_codes == ("per_table_authoring",)
        )
        if (
            plan.project_id != project_id
            or plan.workflow_run_id != workflow_run_id
            or plan.project_revision != expected_project_revision
            or plan.project_workflow != "analysis"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError(
                "The Analysis inference run does not use the fixed execution path."
            )


def _candidate_validator(
    context: AgentContextBundle,
) -> AnalysisInferenceCandidateValidator:
    return AnalysisInferenceCandidateValidator(
        selected_attribute_keys=_selected_attribute_keys(context),
        applied=context.context.analysis_relationships,
    )


def _selected_attribute_keys(context: AgentContextBundle) -> tuple[PhysicalAttributeKey, ...]:
    return tuple(
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
]
