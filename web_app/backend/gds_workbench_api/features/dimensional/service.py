"""Start governed Dimensional Runs and execute them after worker claim."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast
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
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    LogicalAttributeKey,
    LogicalEntityKey,
    normalize_project_key_value,
)
from gds_etl_workbench.domain.snapshots.project import DimensionalSection, ProjectChangeSetDataset
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
)
from pydantic import BaseModel, JsonValue

from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizer,
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    AgentContextRepository,
    PostgresAgentContextRepository,
    focus_subject_area,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import project_key_fields
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
    PostgresAgentRunPlanRepository,
    ProjectWorkflow,
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
    project_validation_issues,
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

    changes: tuple[StageProjectChange, ...] = ()
    issues: tuple[ProjectValidationIssue, ...] = ()


class DimensionalLifecycle(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_workflow: ProjectWorkflow,
        expected_execution_mode: WorkflowExecutionMode | None,
        expected_project_revision: int,
    ) -> AgentWorkflowRunStart: ...

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_project_revision: int,
        event: AgentWorkflowEvent,
    ) -> None: ...

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_project_revision: int,
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
            expected_workflow="dimensional",
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
        workflow_run_claim_token: UUID,
        expected_project_revision: int,
    ) -> DimensionalExecutionResult:
        """Build the selected Subject Areas one after another, or Optimize the whole model.

        A Build call works on the Logical Entities built from one area's Objects and sees
        the Dimensional model as earlier areas left it, so a shared dimension is created
        once and reused. Every call returns only changes; they reach the Project as one draft.
        """
        finalization_attempted = False
        staged: _Staged = {}
        rejected = _RejectedCandidate()
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

            project_details = context.context.project_details
            technical, audit = effective_gold_templates(
                project_details.gold_model_technical_columns_template,
                project_details.gold_model_audit_columns_template,
            )
            validate_dimensional_gold_policy(
                naming_instructions=effective_naming_instructions(
                    "dimensional",
                    project_details.gold_model_naming_instructions,
                ),
                raw_technical_template=technical,
                raw_audit_template=audit,
            )
            snapshot, physical_scope = context.snapshot, context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Dimensional validation context is unavailable.")
            execution_mode = plan.workflow_execution_mode
            operation = plan.workflow_operation
            stage_code = f"{operation}_authoring"
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_project_revision=expected_project_revision,
            )
            fact_types = tuple(
                item.dimensional_fact_type_code
                for item in snapshot.dimensional.fact_types
                if item.dimensional_fact_type_is_active
            )
            model = snapshot.dimensional
            warnings: list[str] = []
            final_attempt = 1
            # Optimize is one call over the whole model; Build is one call per area.
            calls = plan.subject_areas if operation == "build" else (None,)
            for position, area in enumerate(calls, start=1):
                bundle = (
                    context
                    if area is None
                    else focus_subject_area(
                        context,
                        plan=plan,
                        subject_area=area,
                        logical=snapshot.logical,
                        dimensional=model,
                    )
                )
                if bundle is None:
                    # No active Logical Entity is built from this area's Objects yet.
                    warnings.append(
                        f"{area.subject_area_name if area else 'Model'}: skipped, no Logical "
                        "Entities."
                    )
                    continue
                validator = _candidate_validator(bundle, fact_types=fact_types)
                inputs = len(bundle.context.selected_logical_entities)
                await progress.append(
                    attempt=1,
                    stage=f"dimensional.{stage_code}",
                    status="running",
                    message=(
                        "Optimizing the whole Dimensional model."
                        if area is None
                        else f"Building {area.subject_area_name} ({position} of {len(calls)}): "
                        f"{inputs} Logical {'Entity' if inputs == 1 else 'Entities'}."
                    ),
                    current=position - 1,
                    total=len(calls),
                    finding_count=sum(len(records) for records in staged.values()),
                )

                async def validate_complete_candidate(
                    value: JsonValue,
                    validator: DimensionalCandidateValidator = validator,
                    bundle: AgentContextBundle = bundle,
                    staged: _Staged = staged,
                    building: bool = area is not None,
                ) -> AgentCandidateValidation:
                    try:
                        candidate_changes = _project_dimensional_changes(
                            validator=validator, candidate=value, context=bundle
                        )
                    except DimensionalProjectionConflictError as projection_error:
                        issues = (
                            ProjectValidationIssue(
                                code="gold_projection_conflict",
                                dataset="dimensional_entity",
                                record_number=None,
                                fields=(),
                                message=projection_error.message,
                            ),
                        )
                        # An earlier complete projected draft is more useful than a later
                        # candidate that could not be projected.
                        if not rejected.changes:
                            rejected.changes = _staged_changes(
                                _with_staged(staged, validator.parse_validated(value))
                            )
                            rejected.issues = issues
                        return AgentCandidateValidation(issues=project_validation_issues(issues))
                    documents = _with_staged(staged, candidate_changes)
                    checked = validate_future_graph(
                        snapshot=snapshot,
                        staged_documents={
                            dataset: list(records.values())
                            for dataset, records in documents.items()
                        },
                        physical_scope=physical_scope,
                    )
                    # Build measures the area's coverage; Optimize only cleans up.
                    coverage = validator.validate_coverage(value) if building else ()
                    if checked.issues or coverage:
                        rejected.changes = _staged_changes(documents)
                        rejected.issues = checked.issues + tuple(
                            ProjectValidationIssue(
                                code=issue.code.removeprefix("candidate."),
                                dataset="dimensional_entity",
                                record_number=None,
                                fields=(),
                                message=issue.message,
                            )
                            for issue in coverage
                        )
                    return AgentCandidateValidation(
                        issues=project_validation_issues(checked.issues) + coverage
                    )

                resolver_values: dict[str, object] = {
                    f"workflow.dimensional.{execution_mode}.{stage_code}.context": (
                        bundle.embedded_context
                    ),
                    "workflow.validation_failures": [],
                    "project.naming_instructions": effective_naming_instructions(
                        "dimensional", project_details.gold_model_naming_instructions
                    ),
                }
                try:
                    outcome = await self._stage_runner.run(
                        plan=plan,
                        stage_code=stage_code,
                        resolver_values=resolver_values,
                        context=bundle.embedded_context,
                        output_schema=validator.output_schema(),
                        allowed_tool_names=(
                            bundle.tool_catalog.allowed_tool_names
                            if bundle.tool_catalog is not None
                            else ()
                        ),
                        local_tool_catalog=bundle.tool_catalog,
                        validator=validator,
                        final_validation=validate_complete_candidate,
                    )
                except AgentCandidateValidationError as error:
                    # After every attempt only advisory coverage may still fall short.
                    if (
                        project_details.dimensional_enforce_coverage_threshold
                        or error.candidate is None
                        or not error.issues
                        or any(
                            issue.code != "candidate.entity_coverage_incomplete"
                            for issue in error.issues
                        )
                    ):
                        raise
                    candidate = error.candidate
                    final_attempt = plan.selection.validation_retry_count + 1
                    warnings.append(
                        f"{area.subject_area_name if area else 'Model'}: {error.issues[0].message}"
                    )
                else:
                    candidate = outcome.candidate
                    final_attempt = max(final_attempt, outcome.attempt_count)
                    if outcome.was_repaired or outcome.warning_codes:
                        warnings.append(f"{area.subject_area_name if area else 'Model'}: repaired.")
                changes = _project_dimensional_changes(
                    validator=validator, candidate=candidate, context=bundle
                )
                staged = _with_staged(staged, changes)
                model = _with_changes(model, changes)
                rejected.changes, rejected.issues = (), ()

            changes = _staged_changes(staged)
            # A Build over several areas also reports coverage across the whole selection; a
            # one-area Build already reported its area's shortfall.
            if operation == "build" and len(calls) > 1:
                coverage = _candidate_validator(context, fact_types=fact_types).coverage_of(
                    model.entities
                )
                if coverage:
                    warnings.append(f"Run selection: {coverage[0].message}")
            if not changes:
                finalization_attempted = True
                return await self._no_op.complete(
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    request=AuthoringNoOpRequest(
                        expected_workflow="dimensional",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_project_revision=expected_project_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=final_attempt,
                            stage="dimensional.backend_validation",
                            status="warning" if warnings else "running",
                            message=" ".join(
                                [
                                    f"Dimensional {operation} produced no effective change.",
                                    *warnings,
                                ]
                            )[:2000],
                            current=len(calls),
                            total=len(calls),
                            finding_count=0,
                        ),
                    ),
                )

            finalization_attempted = True
            finalized = await self._handoff.finalize(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_workflow="dimensional",
                expected_project_revision=expected_project_revision,
                changes=changes,
                final_event=progress.event(
                    attempt=final_attempt,
                    stage="dimensional.backend_validation",
                    status="warning" if warnings else "running",
                    message=(
                        f"Dimensional {operation} completed with notes. {' '.join(warnings)}"[:2000]
                        if warnings
                        else f"Dimensional {operation} is ready in a validated draft."
                    ),
                    current=len(calls),
                    total=len(calls),
                    finding_count=sum(len(change.records) for change in changes),
                ),
            )
            return finalized.handoff
        except Exception as error:
            retention_issues = (
                error.issues if isinstance(error, WorkflowChangeSetValidationError) else ()
            )
            changes = _staged_changes(staged)
            if (
                isinstance(error, AgentCandidateValidationError)
                and rejected.changes
                # Coverage is checked only by this workflow, not by draft retention.
                and any(issue.code != "entity_coverage_incomplete" for issue in rejected.issues)
            ):
                changes, retention_issues = rejected.changes, rejected.issues
            if retention_issues and changes and isinstance(error, WorkbenchError):
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="dimensional",
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
                    "Dimensional Workflow Run finalization remains pending.",
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
                        workflow_run_claim_token=workflow_run_claim_token,
                        expected_project_revision=expected_project_revision,
                        failure_code=safe_error.code[:100],
                        safe_failure_message=safe_error.message[:2000],
                    )
                except Exception:
                    _logger.warning(
                        "Dimensional failure state could not be persisted.",
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
        if (
            plan.project_id != project_id
            or plan.workflow_run_id != workflow_run_id
            or plan.project_revision != expected_project_revision
            or plan.project_workflow != "dimensional"
            or plan.modeled_entity_type != "logical_entity"
            or plan.workflow_execution_mode not in ("one_shot", "tool_assisted")
            or plan.workflow_operation is None
            or stage_codes != (f"{plan.workflow_operation}_authoring",)
        ):
            raise InvalidRequestError("The Dimensional run does not use the fixed execution path.")


def _candidate_validator(
    context: AgentContextBundle, *, fact_types: tuple[str, ...]
) -> DimensionalCandidateValidator:
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
    context_record_ids = tuple(
        record.context_record_id for record in context.context.context.records
    )
    technical, audit = effective_gold_templates(
        context.context.project_details.gold_model_technical_columns_template,
        context.context.project_details.gold_model_audit_columns_template,
    )
    return DimensionalCandidateValidator(
        selected_entity_keys=selected_entities,
        selected_attribute_keys=selected_attributes,
        context_record_ids=context_record_ids,
        applied=context.context.applied.dimensional,
        fact_types=fact_types,
        raw_technical_template=technical,
        raw_audit_template=audit,
        coverage_threshold_percent=context.context.project_details.dimensional_coverage_threshold_percent,
    )


def _project_dimensional_changes(
    *,
    validator: DimensionalCandidateValidator,
    candidate: JsonValue,
    context: AgentContextBundle,
) -> tuple[StageProjectChange, ...]:
    details = context.context.project_details
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


type _Staged = dict[ProjectChangeSetDataset, dict[tuple[str, ...], dict[str, object]]]
_DATASET_KINDS = {
    "dimensional_entity": "entity",
    "dimensional_attribute": "attribute",
    "dimensional_relationship": "relationship",
}


def _record_key(dataset: str, record: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        normalize_project_key_value(str(record[name]))
        for name in project_key_fields("dimensional", _DATASET_KINDS[dataset])
    )


def _with_staged(staged: _Staged, changes: tuple[StageProjectChange, ...]) -> _Staged:
    """A later call's complete record replaces an earlier one with the same identity."""
    merged: _Staged = {dataset: dict(records) for dataset, records in staged.items()}
    for change in changes:
        records = merged.setdefault(change.dataset, {})
        for record in change.records:
            records[_record_key(change.dataset, record)] = record
    return merged


def _staged_changes(staged: _Staged) -> tuple[StageProjectChange, ...]:
    return tuple(
        StageProjectChange(dataset=dataset, records=list(records.values()))
        for dataset, records in staged.items()
        if records
    )


def _with_changes(
    model: DimensionalSection, changes: tuple[StageProjectChange, ...]
) -> DimensionalSection:
    """The model as the next area sees it: saved records with this run's changes applied."""
    sections = {
        "dimensional_entity": ("entities", DimensionalEntityRecord),
        "dimensional_attribute": ("attributes", DimensionalAttributeRecord),
        "dimensional_relationship": ("relationships", DimensionalRelationshipRecord),
    }
    update: dict[str, tuple[BaseModel, ...]] = {}
    for change in changes:
        field, record_type = sections[change.dataset]
        current = update.get(field, cast(tuple[BaseModel, ...], getattr(model, field)))
        records = {
            _record_key(change.dataset, record.model_dump(mode="json")): record
            for record in current
        }
        for record in change.records:
            records[_record_key(change.dataset, record)] = record_type.model_validate_json(
                json.dumps(record)
            )
        update[field] = tuple(records.values())
    return model.model_copy(update=update)


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
