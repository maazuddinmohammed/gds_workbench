"""Start governed Dimensional Runs and execute them after worker claim."""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
    LogicalAttributeKey,
    LogicalEntityKey,
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
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.naming import (
    effective_naming_instructions,
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
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionDatabase

from .candidate import DimensionalCandidateValidator
from .policy import (
    DimensionalProjectionConflictError,
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
    validate_dimensional_gold_policy,
)

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _RejectedCandidate:
    """Per-run recovery state, preserved across repair attempts and malformed responses."""

    changes: tuple[StageModelChange, ...] = ()
    issues: tuple[ModelValidationIssue, ...] = ()


class DimensionalLifecycle(Protocol):
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

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
        event: AgentWorkflowEvent,
    ) -> None: ...

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
        failure_code: str,
        safe_failure_message: str,
    ) -> object: ...


class DimensionalExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dimensional_execution_failed",
            message=("Dimensional authoring failed before a validated draft was committed."),
        )


class DimensionalFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dimensional_finalization_failed",
            message="The Dimensional authoring outcome could not be confirmed.",
        )


type DimensionalExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class DimensionalWorkflow:
    """Start governed Runs; author a complete Dimensional draft only after worker claim."""

    def __init__(
        self,
        *,
        database: WorkflowExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: WorkflowChangeSetFinalizer,
        no_op: AuthoringNoOpCompleter,
        lifecycle: DimensionalLifecycle,
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
            expected_workflow="dimensional",
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
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
    ) -> DimensionalExecutionResult:
        finalization_attempted = False
        changes: tuple[StageModelChange, ...] = ()
        rejected = _RejectedCandidate()
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

            model_details = context.context.model_details
            technical, audit = effective_gold_templates(
                model_details.gold_model_technical_columns_template,
                model_details.gold_model_audit_columns_template,
            )
            validate_dimensional_gold_policy(
                naming_instructions=effective_naming_instructions(
                    "dimensional",
                    model_details.gold_model_naming_instructions,
                ),
                raw_technical_template=technical,
                raw_audit_template=audit,
            )

            execution_mode = plan.workflow_execution_mode
            selected_object_count = len(context.context.selected_logical_entities)
            selected_object_label = (
                "Logical Entity" if selected_object_count == 1 else "Logical Entities"
            )
            candidate_mode_label = "one-shot" if execution_mode == "one_shot" else "tool-assisted"
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_model_revision=expected_model_revision,
            )
            await progress.append(
                attempt=1,
                stage=("dimensional.candidate_authoring"),
                status="running",
                message=(
                    f"Dimensional {candidate_mode_label} candidate authoring started for "
                    f"{selected_object_count} selected {selected_object_label}; the next "
                    "persisted milestone follows bounded agent-response validation."
                ),
                current=None,
                total=None,
                finding_count=0,
            )
            validator = _candidate_validator(context)
            snapshot, physical_scope = context.snapshot, context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Dimensional validation context is unavailable.")

            async def validate_complete_candidate(value: JsonValue) -> AgentCandidateValidation:
                try:
                    candidate_changes = _project_dimensional_changes(
                        validator=validator,
                        candidate=value,
                        context=context,
                    )
                except DimensionalProjectionConflictError as projection_error:
                    issues = (
                        ModelValidationIssue(
                            code="gold_projection_conflict",
                            dataset="dimensional_entity",
                            record_number=None,
                            fields=(),
                            message=projection_error.message,
                        ),
                    )
                    # An earlier complete projected draft is more useful than a later
                    # candidate that could not be projected. Retain the raw candidate
                    # only when no complete projected rejection exists yet.
                    if not rejected.changes:
                        rejected.changes = validator.parse_validated(value)
                        rejected.issues = issues
                    return AgentCandidateValidation(issues=model_validation_issues(issues))
                checked = validate_future_graph(
                    snapshot=snapshot,
                    staged_documents={
                        change.dataset: change.records for change in candidate_changes
                    },
                    physical_scope=physical_scope,
                )
                coverage = validator.validate_coverage(value)
                coverage_issues = tuple(
                    ModelValidationIssue(
                        code=issue.code.removeprefix("candidate."),
                        dataset="dimensional_entity",
                        record_number=None,
                        fields=(),
                        message=issue.message,
                    )
                    for issue in coverage
                )
                if checked.issues or coverage_issues:
                    rejected.changes = candidate_changes
                    rejected.issues = checked.issues + coverage_issues
                return AgentCandidateValidation(
                    issues=model_validation_issues(checked.issues) + coverage
                )

            resolver_values: dict[str, object] = {
                (
                    f"workflow.dimensional.{execution_mode}.candidate_authoring.context"
                ): context.embedded_context,
                "workflow.validation_failures": [],
            }
            resolver_values["model.naming_instructions"] = effective_naming_instructions(
                "dimensional",
                context.context.model_details.gold_model_naming_instructions,
            )
            coverage_warning: str | None = None
            try:
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
            except AgentCandidateValidationError as error:
                # The shared runner attaches a checked candidate only after all attempts.
                # Coverage alone may fall short; every other validation remains blocking.
                if (
                    error.candidate is None
                    or not error.issues
                    or any(
                        issue.code != "candidate.entity_coverage_incomplete"
                        for issue in error.issues
                    )
                ):
                    raise
                candidate = error.candidate
                final_attempt = plan.selection.validation_retry_count + 1
                coverage_warning = error.issues[0].message
                warning = True
            else:
                candidate = outcome.candidate
                final_attempt = outcome.attempt_count
                warning = outcome.was_repaired or bool(outcome.warning_codes)
            changes = _project_dimensional_changes(
                validator=validator,
                candidate=candidate,
                context=context,
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
                        expected_workflow="dimensional",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_model_revision=expected_model_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=final_attempt,
                            stage="dimensional.backend_validation",
                            status=("warning" if warning else "running"),
                            message=(
                                "Dimensional final attempt produced no effective change; "
                                f"coverage target remains unmet. {coverage_warning}"
                                if coverage_warning
                                else "Dimensional authoring completed with no effective change."
                            ),
                            current=1,
                            total=1,
                            finding_count=0,
                        ),
                    ),
                )

            staged_record_count = sum(len(change.records) for change in changes)
            final_event = progress.event(
                attempt=final_attempt,
                stage="dimensional.backend_validation",
                status="warning" if warning else "running",
                message=(
                    "Dimensional draft returned after the final attempt with partial coverage. "
                    f"{coverage_warning}"
                    if coverage_warning
                    else "Dimensional candidate is ready in a validated draft."
                ),
                current=1,
                total=1,
                finding_count=staged_record_count,
            )
            finalization_attempted = True
            finalized = await self._handoff.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_workflow="dimensional",
                expected_model_revision=expected_model_revision,
                changes=changes,
                final_event=final_event,
            )
            return finalized.handoff
        except Exception as error:
            retention_issues = (
                error.issues if isinstance(error, WorkflowChangeSetValidationError) else ()
            )
            if isinstance(error, AgentCandidateValidationError) and rejected.changes:
                changes, retention_issues = rejected.changes, rejected.issues
            if retention_issues and changes and isinstance(error, WorkbenchError):
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        model_id=model_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="dimensional",
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
                    "Dimensional Workflow Run finalization remains pending.",
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
                        workflow_run_claim_token=workflow_run_claim_token,
                        expected_model_revision=expected_model_revision,
                        failure_code=safe_error.code[:100],
                        safe_failure_message=safe_error.message[:2000],
                    )
                except Exception:
                    _logger.warning(
                        "Dimensional failure state could not be persisted.",
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
            or plan.model_workflow != "dimensional"
            or plan.modeled_entity_type != "logical_entity"
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Dimensional run does not use the fixed execution path.")


def _candidate_validator(context: AgentContextBundle) -> DimensionalCandidateValidator:
    selected_entities = tuple(
        LogicalEntityKey(
            logical_entity_schema_name=item.entity.logical_entity_schema_name,
            logical_entity_name=item.entity.logical_entity_name,
        )
        for item in context.context.selected_logical_entities
    )
    selected_attributes = tuple(
        LogicalAttributeKey(
            logical_entity_schema_name=attribute.logical_entity_schema_name,
            logical_entity_name=attribute.logical_entity_name,
            logical_attribute_name=attribute.logical_attribute_name,
        )
        for item in context.context.selected_logical_entities
        for attribute in item.attributes
    )
    assertion_keys = tuple(
        record.modeling_assertion_record_key for record in context.context.assertion.records
    )
    return DimensionalCandidateValidator(
        selected_entity_keys=selected_entities,
        selected_attribute_keys=selected_attributes,
        assertion_record_keys=assertion_keys,
        applied=context.context.applied.dimensional,
        coverage_threshold_percent=context.context.model_details.dimensional_coverage_threshold_percent,
    )


def _project_dimensional_changes(
    *,
    validator: DimensionalCandidateValidator,
    candidate: JsonValue,
    context: AgentContextBundle,
) -> tuple[StageModelChange, ...]:
    details = context.context.model_details
    technical, audit = effective_gold_templates(
        details.gold_model_technical_columns_template,
        details.gold_model_audit_columns_template,
    )
    changes = validator.parse_validated(candidate)
    changes = project_dimensional_gold_policy(
        changes=changes,
        applied=context.context.applied.dimensional,
        raw_technical_template=technical,
        raw_audit_template=audit,
        scd_type=details.dimensional_entity_scd_type,
    )
    return project_dimensional_foreign_key_policy(
        changes=changes,
        applied=context.context.applied.dimensional,
        raw_technical_template=technical,
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return DimensionalFinalizationFailedError()
    return DimensionalExecutionFailedError()


__all__ = [
    "DimensionalWorkflow",
    "DimensionalExecutionFailedError",
    "DimensionalFinalizationFailedError",
]
