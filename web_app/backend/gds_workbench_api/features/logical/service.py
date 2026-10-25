"""Start governed Logical Runs and execute them after worker claim."""

from __future__ import annotations

import logging
from typing import cast
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
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.domain.snapshots.project import ProjectChangeSetDataset
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
)
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.audit_policy import effective_audit_template
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
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionDatabase

from .candidate import LogicalCandidateValidator
from .policy import project_logical_audit_policy

_logger = logging.getLogger(__name__)


class LogicalExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_execution_failed",
            message="Logical authoring failed before a validated draft was committed.",
        )


class LogicalFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="logical_finalization_failed",
            message="Logical finalization outcome could not be confirmed.",
        )


type LogicalExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class LogicalWorkflow:
    """Start governed Runs; author a complete Logical draft only after worker claim."""

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
            expected_workflow="logical",
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
    ) -> LogicalExecutionResult:
        finalization_attempted = False
        changes: tuple[StageProjectChange, ...] = ()
        recovery_context: tuple[LogicalCandidateValidator, AgentContextBundle] | None = None
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
            selected_object_label = "Object" if selected_object_count == 1 else "Objects"
            candidate_mode_label = "one-shot" if execution_mode == "one_shot" else "tool-assisted"
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage=("logical.candidate_authoring"),
                status="running",
                message=(
                    f"Logical {candidate_mode_label} candidate authoring started "
                    f"for {selected_object_count} selected {selected_object_label}; the next "
                    "persisted milestone follows bounded agent-response validation."
                ),
                current=None,
                total=None,
                finding_count=0,
            )
            validator = _candidate_validator(context)
            recovery_context = validator, context
            snapshot = context.snapshot
            physical_scope = context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Logical validation context is unavailable.")

            async def validate_complete_candidate(value: JsonValue) -> AgentCandidateValidation:
                changes = project_logical_audit_policy(
                    changes=validator.parse_validated(value),
                    applied=context.context.applied.logical,
                    raw_template=context.context.project_details.silver_model_audit_columns_template,
                )
                staged: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
                    change.dataset: change.records for change in changes
                }
                checked = validate_future_graph(
                    snapshot=snapshot,
                    staged_documents=staged,
                    physical_scope=physical_scope,
                )
                return AgentCandidateValidation(
                    issues=validator.agent_issues(value, checked.issues, staged)
                    + validator.validate_coverage(value)
                )

            resolver_values: dict[str, object] = {
                (
                    f"workflow.logical.{execution_mode}.candidate_authoring.context"
                ): context.embedded_context,
                "workflow.validation_failures": [],
            }
            resolver_values["project.naming_instructions"] = effective_naming_instructions(
                "logical",
                context.context.project_details.silver_model_naming_instructions,
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
                # Only advisory coverage may fall short; all other validation blocks.
                if (
                    context.context.project_details.logical_enforce_coverage_threshold
                    or error.candidate is None
                    or not error.issues
                    or any(
                        issue.code != "candidate.object_coverage_incomplete"
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
            changes = validator.parse_validated(candidate)
            changes = project_logical_audit_policy(
                changes=changes,
                applied=context.context.applied.logical,
                raw_template=(context.context.project_details.silver_model_audit_columns_template),
            )
            if not changes:
                finalization_attempted = True
                return await self._no_op.complete(
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    request=AuthoringNoOpRequest(
                        expected_workflow="logical",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_project_revision=expected_project_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=final_attempt,
                            stage="logical.backend_validation",
                            status="warning" if warning else "running",
                            message=(
                                "Logical final attempt produced no effective change; "
                                f"coverage target remains unmet. {coverage_warning}"
                                if coverage_warning
                                else "Logical authoring completed with no effective change."
                            ),
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
                expected_workflow="logical",
                expected_project_revision=expected_project_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=progress.event(
                    attempt=final_attempt,
                    stage="logical.backend_validation",
                    status="warning" if warning else "running",
                    message=(
                        "Logical draft returned after the final attempt with partial coverage. "
                        f"{coverage_warning}"
                        if coverage_warning
                        else "Logical candidate is ready in a validated draft."
                    ),
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
            if (
                isinstance(error, AgentCandidateValidationError)
                and error.candidate is not None
                and recovery_context is not None
                # Coverage is checked only by this workflow, not by draft retention.
                and any(
                    issue.code != "candidate.object_coverage_incomplete" for issue in error.issues
                )
            ):
                recovery_validator, recovery_bundle = recovery_context
                changes = project_logical_audit_policy(
                    changes=recovery_validator.parse_validated(error.candidate),
                    applied=recovery_bundle.context.applied.logical,
                    raw_template=(
                        recovery_bundle.context.project_details.silver_model_audit_columns_template
                    ),
                )
                # Issues name the agent's answer paths; the retained draft lists datasets.
                retention_issues = tuple(
                    ProjectValidationIssue(
                        code=issue.code.removeprefix("candidate."),
                        dataset=(
                            "logical_relationship"
                            if issue.path[:1] == ("relationships",)
                            else "logical_attribute"
                            if issue.path[:1] == ("entities",) and "attributes" in issue.path
                            else "logical_entity"
                            if issue.path[:1] in ((), ("entities",), ("retire",))
                            else str(issue.path[0])
                        ),
                        record_number=None,
                        fields=tuple(
                            str(part)
                            for part in issue.path[1:]
                            if isinstance(part, str) and part != "attributes"
                        ),
                        message=issue.message,
                    )
                    for issue in error.issues
                )
            if retention_issues and changes and isinstance(error, WorkbenchError):
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="logical",
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
                    "Logical Workflow Run finalization remains pending.",
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
                        "Logical failure state could not be persisted.",
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
            or plan.project_workflow != "logical"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Logical run does not use the fixed execution path.")


def _candidate_validator(context: AgentContextBundle) -> LogicalCandidateValidator:
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
    selected_attributes: list[PhysicalAttributeKey] = []
    # A missing Attribute definition defaults to its source column's Project description.
    descriptions: dict[PhysicalAttributeKey, str] = {}
    for selected in context.context.selected_objects:
        for attribute in selected.attributes:
            key = PhysicalAttributeKey(
                tenant_code=attribute.tenant_code,
                system_code=attribute.system_code,
                connection_code=attribute.connection_code,
                object_schema=attribute.object_schema,
                object_name=attribute.object_name,
                attribute_name=attribute.attribute_name,
            )
            selected_attributes.append(key)
            if attribute.attribute_description:
                descriptions[key] = attribute.attribute_description
    audit_template = effective_audit_template(
        context.context.project_details.silver_model_audit_columns_template
    )
    return LogicalCandidateValidator(
        selected_object_keys=selected_objects,
        selected_attribute_keys=tuple(selected_attributes),
        context_record_ids=tuple(
            record.context_record_id for record in context.context.context.records
        ),
        applied=context.context.applied.logical,
        coverage_threshold_percent=context.context.project_details.logical_coverage_threshold_percent,
        attribute_descriptions=descriptions,
        # The backend projects audit columns, so business Attributes cannot take their names.
        reserved_attribute_names=tuple(
            str(column["semantic_name"])
            for column in cast(list[dict[str, object]], audit_template["columns"])
        ),
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return LogicalFinalizationFailedError()
    return LogicalExecutionFailedError()


__all__ = ["LogicalWorkflow", "LogicalExecutionFailedError", "LogicalFinalizationFailedError"]
