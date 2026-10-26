"""Start governed Logical Runs and execute them after worker claim."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
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
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    normalize_project_key_value,
)
from gds_etl_workbench.domain.snapshots.project import LogicalSection, ProjectChangeSetDataset
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
)
from pydantic import BaseModel, JsonValue

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
    focus_subject_area,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import project_key_fields
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
        """Build the selected Subject Areas one after another, or Optimize the whole model.

        Each Build call sees one area's Objects and the model as earlier areas left it, so a
        shared table's Entity is created once and then reused. Every call returns only
        changes; they accumulate in memory and reach the Project as one draft.
        """
        finalization_attempted = False
        staged: dict[ProjectChangeSetDataset, dict[tuple[str, ...], dict[str, object]]] = {}
        failed_changes: tuple[StageProjectChange, ...] = ()
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

            snapshot = context.snapshot
            physical_scope = context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Logical validation context is unavailable.")
            execution_mode = plan.workflow_execution_mode
            operation = plan.workflow_operation
            stage_code = f"{operation}_authoring"
            details = context.context.project_details
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            entity_types = tuple(
                item.logical_entity_type_code
                for item in snapshot.logical.entity_types
                if item.logical_entity_type_is_active
            )
            model = snapshot.logical
            warnings: list[str] = []
            final_attempt = 1
            # Optimize is one call over the whole model; Build is one call per area.
            calls = plan.subject_areas if operation == "build" else (None,)
            for position, area in enumerate(calls, start=1):
                bundle = (
                    context
                    if area is None
                    else focus_subject_area(context, plan=plan, subject_area=area, logical=model)
                )
                if bundle is None:
                    # An area whose Objects all left the eligible scope has nothing to build.
                    warnings.append(f"{area.subject_area_name if area else 'Model'}: skipped.")
                    continue
                validator = _candidate_validator(bundle, entity_types=entity_types)
                inputs = len(bundle.context.selected_objects)
                await progress.append(
                    attempt=1,
                    stage=f"logical.{stage_code}",
                    status="running",
                    message=(
                        "Optimizing the whole Logical model."
                        if area is None
                        else f"Building {area.subject_area_name} ({position} of {len(calls)}): "
                        f"{inputs} {'Object' if inputs == 1 else 'Objects'}."
                    ),
                    current=position - 1,
                    total=len(calls),
                    finding_count=sum(len(records) for records in staged.values()),
                )

                async def validate_complete_candidate(
                    value: JsonValue,
                    validator: LogicalCandidateValidator = validator,
                    model: LogicalSection = model,
                    staged: _Staged = staged,
                    building: bool = area is not None,
                ) -> AgentCandidateValidation:
                    changes = project_logical_audit_policy(
                        changes=validator.parse_validated(value),
                        applied=model,
                        raw_template=details.silver_model_audit_columns_template,
                    )
                    documents = _staged_documents(_with_staged(staged, changes))
                    checked = validate_future_graph(
                        snapshot=snapshot,
                        staged_documents=documents,
                        physical_scope=physical_scope,
                    )
                    return AgentCandidateValidation(
                        issues=validator.agent_issues(value, checked.issues, documents)
                        # Build measures the area's coverage; Optimize only cleans up.
                        + (validator.validate_coverage(value) if building else ())
                    )

                resolver_values: dict[str, object] = {
                    f"workflow.logical.{execution_mode}.{stage_code}.context": (
                        bundle.embedded_context
                    ),
                    "workflow.validation_failures": [],
                    "project.naming_instructions": effective_naming_instructions(
                        "logical", details.silver_model_naming_instructions
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
                    coverage_only = bool(error.issues) and all(
                        issue.code == "candidate.object_coverage_incomplete"
                        for issue in error.issues
                    )
                    # After every attempt only advisory coverage may still fall short.
                    if (
                        details.logical_enforce_coverage_threshold
                        or error.candidate is None
                        or not coverage_only
                    ):
                        # Coverage is checked only by this workflow, not by draft retention.
                        if not coverage_only:
                            try:
                                failed_changes = project_logical_audit_policy(
                                    changes=validator.parse_validated(error.candidate),
                                    applied=model,
                                    raw_template=details.silver_model_audit_columns_template,
                                )
                            except Exception:
                                failed_changes = ()
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
                changes = project_logical_audit_policy(
                    changes=validator.parse_validated(candidate),
                    applied=model,
                    raw_template=details.silver_model_audit_columns_template,
                )
                staged = _with_staged(staged, changes)
                model = _with_changes(model, changes)

            changes = tuple(
                StageProjectChange(dataset=dataset, records=list(records.values()))
                for dataset, records in staged.items()
                if records
            )
            if operation == "build":
                coverage = _candidate_validator(context, entity_types=entity_types).coverage_of(
                    model.entities
                )
                if coverage:
                    warnings.append(f"Run selection: {coverage[0].message}")
            summary = (
                f"Logical {operation} completed with notes. {' '.join(warnings)}"[:2000]
                if warnings
                else f"Logical {operation} is ready in a validated draft."
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
                            status="warning" if warnings else "running",
                            message=" ".join(
                                [f"Logical {operation} produced no effective change.", *warnings]
                            )[:2000],
                            current=len(calls),
                            total=len(calls),
                            finding_count=0,
                        ),
                    ),
                )

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
                    status="warning" if warnings else "running",
                    message=summary,
                    current=len(calls),
                    total=len(calls),
                    finding_count=sum(len(change.records) for change in changes),
                ),
            )
            return finalization.handoff
        except Exception as error:
            retention_issues = (
                error.issues if isinstance(error, WorkflowChangeSetValidationError) else ()
            )
            # Keep earlier areas and the failed answer as a rejected draft for review.
            retained = _with_staged(staged, failed_changes)
            if isinstance(error, AgentCandidateValidationError) and failed_changes:
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
            retained_changes = tuple(
                StageProjectChange(dataset=dataset, records=list(records.values()))
                for dataset, records in retained.items()
                if records
            )
            if retention_issues and retained_changes and isinstance(error, WorkbenchError):
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="logical",
                        expected_project_revision=expected_project_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        changes=retained_changes,
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
        if (
            plan.project_id != project_id
            or plan.workflow_run_id != workflow_run_id
            or plan.project_revision != expected_project_revision
            or plan.project_workflow != "logical"
            or plan.modeled_entity_type is not None
            or plan.workflow_execution_mode not in ("one_shot", "tool_assisted")
            or plan.workflow_operation is None
            or stage_codes != (f"{plan.workflow_operation}_authoring",)
        ):
            raise InvalidRequestError("The Logical run does not use the fixed execution path.")


def _candidate_validator(
    bundle: AgentContextBundle, *, entity_types: tuple[str, ...]
) -> LogicalCandidateValidator:
    selected_objects = tuple(
        PhysicalObjectKey(
            tenant_code=item.object.tenant_code,
            system_code=item.object.system_code,
            connection_code=item.object.connection_code,
            object_schema=item.object.object_schema,
            object_name=item.object.object_name,
        )
        for item in bundle.context.selected_objects
    )
    selected_attributes: list[PhysicalAttributeKey] = []
    # A missing Attribute definition defaults to its source column's Project description.
    descriptions: dict[PhysicalAttributeKey, str] = {}
    for selected in bundle.context.selected_objects:
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
    details = bundle.context.project_details
    audit_template = effective_audit_template(details.silver_model_audit_columns_template)
    return LogicalCandidateValidator(
        selected_object_keys=selected_objects,
        selected_attribute_keys=tuple(selected_attributes),
        context_record_ids=tuple(
            record.context_record_id for record in bundle.context.context.records
        ),
        applied=bundle.context.applied.logical,
        entity_types=entity_types,
        coverage_threshold_percent=details.logical_coverage_threshold_percent,
        attribute_descriptions=descriptions,
        # The backend projects audit columns, so business Attributes cannot take their names.
        reserved_attribute_names=tuple(
            str(column["semantic_name"])
            for column in cast(list[dict[str, object]], audit_template["columns"])
        ),
    )


type _Staged = dict[ProjectChangeSetDataset, dict[tuple[str, ...], dict[str, object]]]
_DATASET_KINDS = {
    "logical_entity": "entity",
    "logical_attribute": "attribute",
    "logical_relationship": "relationship",
}


def _record_key(dataset: str, record: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        normalize_project_key_value(str(record[name]))
        for name in project_key_fields("logical", _DATASET_KINDS[dataset])
    )


def _with_staged(staged: _Staged, changes: tuple[StageProjectChange, ...]) -> _Staged:
    """A later call's complete record replaces an earlier one with the same identity."""
    merged: _Staged = {dataset: dict(records) for dataset, records in staged.items()}
    for change in changes:
        records = merged.setdefault(change.dataset, {})
        for record in change.records:
            records[_record_key(change.dataset, record)] = record
    return merged


def _staged_documents(
    staged: _Staged,
) -> dict[ProjectChangeSetDataset, list[dict[str, object]]]:
    return {dataset: list(records.values()) for dataset, records in staged.items()}


def _with_changes(model: LogicalSection, changes: tuple[StageProjectChange, ...]) -> LogicalSection:
    """The model as the next area sees it: saved records with this run's changes applied."""
    sections = {
        "logical_entity": ("entities", LogicalEntityRecord),
        "logical_attribute": ("attributes", LogicalAttributeRecord),
        "logical_relationship": ("relationships", LogicalRelationshipRecord),
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
        return LogicalFinalizationFailedError()
    return LogicalExecutionFailedError()


__all__ = ["LogicalWorkflow", "LogicalExecutionFailedError", "LogicalFinalizationFailedError"]
