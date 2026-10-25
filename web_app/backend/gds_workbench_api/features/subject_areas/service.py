"""Start governed Subject Area Runs and execute them after worker claim."""

from __future__ import annotations

import logging
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    ProjectValidationIssue,
    validate_future_graph,
)
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    PhysicalObjectKey,
)
from gds_etl_workbench.domain.snapshots.project import ProjectChangeSetDataset
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
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowLifecycle,
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpCompleter,
    AuthoringNoOpReceipt,
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
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageRunner,
)
from gds_workbench_api.features.workflows.authoring.subject_area_policy import (
    load_subject_area_policy,
)
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionDatabase

from .candidate import SubjectAreaCandidateValidator

_logger = logging.getLogger(__name__)


class SubjectAreaExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="subject_area_execution_failed",
            message="Subject Area authoring failed before a validated draft was committed.",
        )


class SubjectAreaFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="subject_area_finalization_failed",
            message="Subject Area finalization outcome could not be confirmed.",
        )


type SubjectAreaExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class SubjectAreaWorkflow:
    """Start governed Runs; author one Subject Area draft only after worker claim."""

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
        self._context_policy = context_policy or load_default_agent_context_policy()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=self._context_policy,
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
            expected_workflow="subject_area",
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
    ) -> SubjectAreaExecutionResult:
        finalization_attempted = False
        changes: tuple[StageProjectChange, ...] = ()
        rejected_changes: tuple[StageProjectChange, ...] = ()
        rejected_issues: tuple[ProjectValidationIssue, ...] = ()
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

            execution_mode = plan.workflow_execution_mode
            selected_object_count = len(context.context.selected_objects)
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage="subject_area.candidate_authoring",
                status="running",
                message=(
                    f"Subject Area authoring started for {selected_object_count} Input Scope "
                    "tables. The next persisted milestone follows bounded agent response "
                    "validation."
                ),
                current=0 if selected_object_count else None,
                total=selected_object_count or None,
                finding_count=0,
            )

            validator = _candidate_validator(context)
            snapshot = context.snapshot
            physical_scope = context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Subject Area validation context is unavailable.")

            async def validate_complete_candidate(value: JsonValue) -> AgentCandidateValidation:
                nonlocal rejected_changes, rejected_issues
                candidate_changes = validator.parse_validated(value)
                staged: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
                    change.dataset: change.records for change in candidate_changes
                }
                checked = validate_future_graph(
                    snapshot=snapshot,
                    staged_documents=staged,
                    physical_scope=physical_scope,
                )
                if checked.issues:
                    rejected_changes = candidate_changes
                    rejected_issues = checked.issues
                return AgentCandidateValidation(
                    issues=validator.agent_issues(value, checked.issues, staged)
                )

            resolver_key = f"workflow.subject_area.{execution_mode}.candidate_authoring.context"
            resolver_values: dict[str, object] = {
                resolver_key: context.embedded_context,
                "workflow.validation_failures": [],
            }
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
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    request=AuthoringNoOpRequest(
                        expected_workflow="subject_area",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_project_revision=expected_project_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=final_attempt,
                            stage="subject_area.backend_validation",
                            status="warning" if warning else "running",
                            message="Subject Area authoring completed with no effective change.",
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
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="subject_area",
                expected_project_revision=expected_project_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=progress.event(
                    attempt=final_attempt,
                    stage="subject_area.backend_validation",
                    status="warning" if warning else "running",
                    message="Subject Areas are ready in a validated draft.",
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
                        project_id=project_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="subject_area",
                        expected_project_revision=expected_project_revision,
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
                    "Subject Area Workflow Run finalization remains pending.",
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
                        "Subject Area failure state could not be persisted.",
                        extra={
                            "workflow_run_id": workflow_run_id,
                            "project_id": project_id,
                            "failure_code": safe_error.code[:100],
                        },
                    )
            raise safe_error from None

    @staticmethod
    def _validate_plan(
        plan: AgentRunPlan,
        *,
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
    ) -> None:
        stage_codes = tuple(stage.stage_code for stage in plan.stages)
        mode_path_is_valid = plan.workflow_execution_mode in (
            "one_shot",
            "tool_assisted",
        ) and stage_codes == ("candidate_authoring",)
        if (
            plan.project_id != project_id
            or plan.workflow_run_id != workflow_run_id
            or plan.project_revision != expected_project_revision
            or plan.project_workflow != "subject_area"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Subject Area run does not use the fixed execution path.")


def _candidate_validator(context: AgentContextBundle) -> SubjectAreaCandidateValidator:
    selected = context.context.selected_objects
    return SubjectAreaCandidateValidator(
        selected_object_keys=tuple(
            PhysicalObjectKey(
                tenant_code=item.object.tenant_code,
                system_code=item.object.system_code,
                connection_code=item.object.connection_code,
                object_schema=item.object.object_schema,
                object_name=item.object.object_name,
            )
            for item in selected
        ),
        column_counts=tuple(len(item.attributes) for item in selected),
        applied=context.context.applied.subject_area,
        max_subject_area_columns=load_subject_area_policy().max_subject_area_columns,
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return SubjectAreaFinalizationFailedError()
    return SubjectAreaExecutionFailedError()


__all__ = [
    "SubjectAreaExecutionFailedError",
    "SubjectAreaFinalizationFailedError",
    "SubjectAreaWorkflow",
]
