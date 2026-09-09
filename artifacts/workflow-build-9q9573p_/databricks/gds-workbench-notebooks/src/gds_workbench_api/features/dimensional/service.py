"""Execute one already-running Dimensional authoring run."""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
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
    PhysicalAttributeKey,
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
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

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


class DimensionalExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DimensionalPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class DimensionalContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle: ...


class DimensionalChangeSetFinalizer(Protocol):
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
        workflow_run_claim_token: UUID,
        expected_workflow: ModelWorkflow,
        expected_model_revision: int,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
    ) -> WorkflowChangeSetFinalizationResult: ...


class DimensionalLifecycle(Protocol):
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


class DimensionalNoOpCompleter(Protocol):
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


class DimensionalRunLifecycle(Protocol):
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


class DimensionalExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
    ) -> DimensionalExecutionResult: ...


class DimensionalWorkflow:
    """Bind the public route to one explicit Dimensional execution mode."""

    def __init__(
        self,
        *,
        lifecycle: DimensionalRunLifecycle,
        executor: DimensionalExecutor,
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
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            expected_model_revision=expected_model_revision,
        )


class DatabaseDimensionalExecutor:
    """Load frozen Silver inputs, validate one candidate, and hand off atomically."""

    def __init__(
        self,
        *,
        database: DimensionalExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: DimensionalChangeSetFinalizer,
        no_op: DimensionalNoOpCompleter,
        lifecycle: DimensionalLifecycle,
        plan_repository: DimensionalPlanRepository | None = None,
        context_repository: DimensionalContextRepository | None = None,
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
            validate_dimensional_gold_policy(
                naming_instructions=effective_naming_instructions(
                    "dimensional",
                    model_details.gold_model_naming_instructions,
                ),
                raw_technical_template=(model_details.gold_model_technical_columns_template),
                raw_audit_template=model_details.gold_model_audit_columns_template,
            )

            execution_mode = plan.workflow_execution_mode
            selected_object_count = len(context.context.selected_objects)
            selected_object_label = "Object" if selected_object_count == 1 else "Objects"
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
                if checked.issues:
                    rejected.changes, rejected.issues = candidate_changes, checked.issues
                return AgentCandidateValidation(issues=model_validation_issues(checked.issues))

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
                            message=("Dimensional authoring completed with no effective change."),
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
                message="Dimensional candidate is ready in a validated draft.",
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
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Dimensional run does not use the fixed execution path.")


def _candidate_validator(context: AgentContextBundle) -> DimensionalCandidateValidator:
    selected_objects = tuple(
        PhysicalObjectKey(
            tenant_code=item.object.tenant_code,
            system_code=item.object.system_code,
            connection_code=item.object.connection_code,
            object_schema=item.object.object_schema,
            object_name=item.object.object_name,
        )
        for item in context.context.selected_objects
    )
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
    assertion_keys = tuple(
        record.modeling_assertion_record_key for record in context.context.assertion.records
    )
    return DimensionalCandidateValidator(
        selected_object_keys=selected_objects,
        selected_attribute_keys=selected_attributes,
        assertion_record_keys=assertion_keys,
        applied=context.context.applied.dimensional,
    )


def _project_dimensional_changes(
    *,
    validator: DimensionalCandidateValidator,
    candidate: JsonValue,
    context: AgentContextBundle,
) -> tuple[StageModelChange, ...]:
    details = context.context.model_details
    changes = validator.parse_validated(candidate)
    changes = project_dimensional_gold_policy(
        changes=changes,
        applied=context.context.applied.dimensional,
        raw_technical_template=details.gold_model_technical_columns_template,
        raw_audit_template=details.gold_model_audit_columns_template,
    )
    return project_dimensional_foreign_key_policy(
        changes=changes,
        applied=context.context.applied.dimensional,
        raw_technical_template=details.gold_model_technical_columns_template,
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
    "DatabaseDimensionalExecutor",
    "DimensionalExecutionFailedError",
    "DimensionalFinalizationFailedError",
    "DimensionalWorkflow",
]
