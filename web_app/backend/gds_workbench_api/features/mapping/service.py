"""Start governed Mapping Runs and execute them after worker claim."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import (
    ModelValidationIssue,
    PhysicalModelCatalog,
    validate_future_graph,
)
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset, ModelSnapshot
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolRequestError,
    AgentContextToolResultTooLargeError,
    AgentExecutionFailedError,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizer as MappingChangeSetHandoff,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowLifecycle,
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpCompleter as MappingNoOpCompleter,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpReceipt,
    AuthoringNoOpRequest,
    authoring_no_op_candidate_digest,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentContextPolicy,
    AgentContextTooLargeError,
    AgentExecutor,
    load_default_agent_context_policy,
    model_validation_issues,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageRunner,
)

from .complete_candidate import (
    CompleteMappingCandidateValidator,
)
from .execution_context import (
    MappingExecutionContextLimits,
    build_mapping_execution_context,
)
from .preparation_contracts import (
    MappingOutputTemplate,
    MappingPreparation,
    MappingRunContextUnavailableError,
)

_logger = logging.getLogger(__name__)


class MappingPreparationService(Protocol):
    async def prepare(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> tuple[MappingPreparation, ...]: ...


class MappingExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_execution_failed",
            message="Mapping authoring failed before a validated draft was committed.",
        )


class MappingFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_finalization_failed",
            message="Mapping finalization outcome could not be confirmed.",
        )


type MappingExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class MappingWorkflow:
    """Start governed Runs; author a complete Mapping draft only after worker claim."""

    def __init__(
        self,
        *,
        preparation_service: MappingPreparationService,
        agent_executor: AgentExecutor,
        handoff: MappingChangeSetHandoff,
        no_op: MappingNoOpCompleter,
        lifecycle: AgentWorkflowLifecycle,
        context_policy: AgentContextPolicy | None = None,
        context_limits: MappingExecutionContextLimits | None = None,
    ) -> None:
        self._preparation_service = preparation_service
        self._context_policy = context_policy or load_default_agent_context_policy()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=self._context_policy,
        )
        self._handoff = handoff
        self._no_op = no_op
        self._lifecycle = lifecycle
        self._context_limits = context_limits

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
            expected_workflow="mapping",
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
    ) -> MappingExecutionResult:
        finalization_attempted = False
        changes: tuple[StageModelChange, ...] = ()
        rejected_changes: tuple[StageModelChange, ...] = ()
        rejected_issues: tuple[ModelValidationIssue, ...] = ()
        try:
            preparations = await self._preparation_service.prepare(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            if not preparations:
                raise InvalidRequestError("Select at least one eligible Mapping Object.")
            preparation = preparations[0]
            warning = False
            final_attempt = 1
            sequence = 2
            failures: list[Exception] = []
            first_rejected_changes: tuple[StageModelChange, ...] = ()
            first_rejected_issues: tuple[ModelValidationIssue, ...] = ()
            completed = 0
            unmatched = 0
            partial = 0
            empty = 0
            for index, preparation in enumerate(preparations):
                plan = preparation.plan.agent_plan
                _validate_plan(
                    preparation,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                )
                if any(
                    issue.code == "context.identity_drift" for issue in preparation.readiness.issues
                ):
                    raise MappingRunContextUnavailableError()
                await self._lifecycle.append_event(
                    principal,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    expected_model_revision=expected_model_revision,
                    event=AgentWorkflowEvent(
                        sequence=sequence,
                        attempt=1,
                        stage="mapping.mapping_authoring",
                        status="running",
                        message=f"Authoring Mapping target {index + 1} of {len(preparations)}.",
                        current=index,
                        total=len(preparations),
                        finding_count=0,
                    ),
                )
                sequence += 1
                pair_stage = "mapping.pair_preserved"
                pair_message = "Existing Mapping preserved; no authoring was needed."
                pair_attempt = 1
                pair_failed = False
                pair_warning = False
                rejected_changes, rejected_issues = (), ()
                try:
                    if not preparation.readiness.ready:
                        raise InvalidRequestError(
                            " ".join(issue.message for issue in preparation.readiness.issues)
                        )
                    execution_mode = plan.workflow_execution_mode
                    if execution_mode is None:
                        raise InvalidRequestError("Mapping requires an explicit execution mode.")
                    if not _has_actionable_authoring(preparation):
                        completed += 1
                    else:
                        validator = CompleteMappingCandidateValidator(preparation=preparation)
                        snapshot, physical_scope = preparation.snapshot, preparation.physical_scope
                        if snapshot is None or physical_scope is None:
                            raise MappingRunContextUnavailableError()

                        async def validate_complete_candidate(
                            value: JsonValue,
                            validator: CompleteMappingCandidateValidator = validator,
                            prior_changes: tuple[StageModelChange, ...] = changes,
                            snapshot: ModelSnapshot = snapshot,
                            physical_scope: PhysicalModelCatalog = physical_scope,
                        ) -> AgentCandidateValidation:
                            nonlocal rejected_changes, rejected_issues
                            candidate_changes = validator.parse_validated(value).changes
                            combined: dict[ModelChangeSetDataset, list[dict[str, object]]] = {}
                            for change in (*prior_changes, *candidate_changes):
                                combined.setdefault(change.dataset, []).extend(change.records)
                            checked = validate_future_graph(
                                snapshot=snapshot,
                                staged_documents=combined,
                                physical_scope=physical_scope,
                            )
                            if checked.issues:
                                rejected_changes = candidate_changes
                                rejected_issues = checked.issues
                            else:
                                rejected_changes, rejected_issues = (), ()
                            return AgentCandidateValidation(
                                issues=model_validation_issues(checked.issues)
                            )

                        execution_context = build_mapping_execution_context(
                            preparation=preparation,
                            execution_mode=execution_mode,
                            limits=self._context_limits,
                        )
                        outcome = await self._stage_runner.run(
                            plan=plan,
                            stage_code="mapping_authoring",
                            resolver_values=_mapping_resolver_values(
                                preparation,
                                stage_code="mapping_authoring",
                                context=execution_context.embedded_context,
                            ),
                            context=execution_context.embedded_context,
                            output_schema=validator.output_schema(),
                            allowed_tool_names=(
                                execution_context.tool_catalog.allowed_tool_names
                                if execution_context.tool_catalog is not None
                                else ()
                            ),
                            local_tool_catalog=execution_context.tool_catalog,
                            validator=validator,
                            final_validation=validate_complete_candidate,
                        )
                        result = validator.parse_validated(outcome.candidate)
                        changes += result.changes
                        no_source = (
                            result.normalized.outcome == "no_applicable_source"
                            and not result.has_transformations
                        )
                        unmatched += int(no_source)
                        partial += int(result.is_partial)
                        empty += int(not result.has_transformations and not no_source)
                        if not result.has_transformations:
                            pair_stage = (
                                "mapping.pair_no_source" if no_source else "mapping.pair_empty"
                            )
                            pair_message = (
                                "No transformations available. Selected transformations are blank; "
                                "no new Mapping pair was created."
                            )
                        else:
                            pair_stage = (
                                "mapping.pair_partial"
                                if result.is_partial
                                else "mapping.pair_completed"
                            )
                            pair_message = (
                                f"{result.mapped_attribute_count} of {result.attribute_count} "
                                "Attributes have transformations. "
                                + (
                                    "Object transformation available. "
                                    if result.has_object_transformation
                                    else "Object transformation is blank. "
                                )
                                + "Missing selected transformations are blank."
                            )
                        if result.warnings:
                            pair_message = (
                                pair_message
                                + " "
                                + " ".join(
                                    dict.fromkeys(issue.message for issue in result.warnings)
                                )
                            )[:2000]
                        pair_warning = result.is_partial or bool(result.warnings)
                        pair_attempt = outcome.attempt_count
                        warning |= (
                            outcome.was_repaired or bool(outcome.warning_codes) or pair_warning
                        )
                        final_attempt = max(final_attempt, outcome.attempt_count)
                        completed += 1
                except (
                    AgentCandidateValidationError,
                    AgentExecutionFailedError,
                    AgentContextTooLargeError,
                    AgentContextToolRequestError,
                    AgentContextToolResultTooLargeError,
                    InvalidRequestError,
                ) as pair_error:
                    # Only bounded authoring failures are local to a pair. Claim,
                    # authorization, lock, revision and unexpected errors abort the Run.
                    safe = _safe_execution_error(pair_error, finalization_attempted=False)
                    if (
                        not failures
                        and isinstance(pair_error, AgentCandidateValidationError)
                        and pair_error.candidate is not None
                    ):
                        first_rejected_changes = rejected_changes
                        first_rejected_issues = rejected_issues
                    failures.append(pair_error)
                    warning = True
                    pair_failed = True
                    pair_stage = "mapping.pair_failed"
                    pair_message = safe.message[:2000]
                # Dependency order can differ from selection order. Keep the
                # frozen selection ordinal so diagnostics identify the correct pair.
                await self._lifecycle.append_event(
                    principal,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    expected_model_revision=expected_model_revision,
                    event=AgentWorkflowEvent(
                        sequence=sequence,
                        attempt=pair_attempt,
                        stage=pair_stage,
                        status="warning" if pair_failed or pair_warning else "running",
                        message=pair_message,
                        current=preparation.plan.selection_ordinal,
                        total=len(preparations),
                        finding_count=int(pair_failed),
                    ),
                )
                sequence += 1
            # A partial draft contains validated transformations, including explicit
            # blanks for omitted selected output. A failure
            # with no successful changes must not be reported as a successful no-op.
            if failures and not changes:
                rejected_changes, rejected_issues = first_rejected_changes, first_rejected_issues
                raise failures[0]
            # One section per dataset; each pair retains its own identity and frozen evidence.
            combined_records: dict[ModelChangeSetDataset, list[dict[str, object]]] = {}
            for change in changes:
                combined_records.setdefault(change.dataset, []).extend(change.records)
            changes = tuple(
                StageModelChange(dataset=dataset, records=records)
                for dataset, records in combined_records.items()
            )
            final_sequence = sequence
            if not changes:
                finalization_attempted = True
                return await self._complete_no_op(
                    principal,
                    preparation=preparations[0],
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    expected_model_revision=expected_model_revision,
                    sequence=final_sequence,
                    attempt=final_attempt,
                    warning=warning,
                    message=(
                        f"Mapping completed with no effective change; {unmatched} pairs "
                        f"had no applicable source, {empty} returned no output, "
                        f"{partial} have partial mappings, {len(failures)} failed."
                    ),
                )

            staged_record_count = sum(len(change.records) for change in changes)
            finalization_attempted = True
            finalized = await self._handoff.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_workflow="mapping",
                expected_model_revision=expected_model_revision,
                changes=changes,
                final_event=AgentWorkflowEvent(
                    sequence=final_sequence,
                    attempt=final_attempt,
                    stage="mapping.backend_validation",
                    status="warning" if warning else "running",
                    message=(
                        f"{completed} of {len(preparations)} Mapping targets assessed; "
                        f"{partial} have partial mappings; {empty} returned no output; "
                        f"{unmatched} had no applicable source; {len(failures)} failed. "
                        "Review the draft and run events."
                    ),
                    current=len(preparations),
                    total=len(preparations),
                    finding_count=staged_record_count,
                ),
            )
            return finalized.handoff
        except Exception as error:
            retention_issues = (
                error.issues if isinstance(error, WorkflowChangeSetValidationError) else ()
            )
            if isinstance(error, AgentCandidateValidationError) and rejected_changes:
                changes, retention_issues = rejected_changes, rejected_issues
            if retention_issues and changes and isinstance(error, WorkbenchError):
                try:
                    await self._handoff.retain_failed_candidate(
                        principal,
                        tenant_id=tenant_id,
                        model_id=model_id,
                        workflow_run_id=workflow_run_id,
                        expected_workflow="mapping",
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
                    "Mapping Workflow Run finalization remains pending.",
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
                        "Mapping failure state could not be persisted.",
                        extra={
                            "workflow_run_id": workflow_run_id,
                            "model_id": model_id,
                            "failure_code": safe_error.code[:100],
                        },
                    )
            raise safe_error from None

    async def _complete_no_op(
        self,
        principal: RequestPrincipal,
        *,
        preparation: MappingPreparation,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
        sequence: int,
        attempt: int,
        warning: bool,
        message: str,
    ) -> AuthoringNoOpReceipt:
        plan = preparation.plan.agent_plan
        execution_mode = plan.workflow_execution_mode
        if execution_mode is None:
            raise InvalidRequestError("Mapping requires an explicit execution mode.")
        return await self._no_op.complete(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            request=AuthoringNoOpRequest(
                expected_workflow="mapping",
                expected_execution_mode=execution_mode,
                expected_correlation_id=plan.correlation_id,
                expected_model_revision=expected_model_revision,
                candidate_digest=authoring_no_op_candidate_digest(plan),
                final_event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=attempt,
                    stage="mapping.backend_validation",
                    status="warning" if warning else "running",
                    message=message,
                    current=1,
                    total=1,
                    finding_count=0,
                ),
            ),
        )


def _validate_plan(
    preparation: MappingPreparation,
    *,
    model_id: int,
    workflow_run_id: int,
    expected_model_revision: int,
) -> None:
    mapping_plan = preparation.plan
    plan = mapping_plan.agent_plan
    mode = plan.workflow_execution_mode
    expected_stages = ("mapping_authoring",)
    if (
        plan.model_workflow != "mapping"
        or mode not in ("one_shot", "tool_assisted")
        or plan.model_id != model_id
        or mapping_plan.model_id != model_id
        or plan.workflow_run_id != workflow_run_id
        or mapping_plan.workflow_run_id != workflow_run_id
        or plan.model_revision != expected_model_revision
        or mapping_plan.model_revision != expected_model_revision
        or plan.correlation_id != mapping_plan.correlation_id
        or plan.modeled_entity_type != mapping_plan.modeled_entity_type
        or plan.selected_entity_ids != (mapping_plan.pair.modeled_entity_id,)
        or tuple(stage.stage_code for stage in plan.stages) != expected_stages
    ):
        raise InvalidRequestError("The frozen Mapping execution plan is invalid.")


def _has_actionable_authoring(preparation: MappingPreparation) -> bool:
    return any(
        header.action in {"author", "extend"}
        or any(child.action in {"author", "extend"} for child in header.attribute_actions)
        for header in preparation.readiness.headers
    )


def _mapping_resolver_values(
    preparation: MappingPreparation,
    *,
    stage_code: str,
    context: JsonValue,
) -> Mapping[str, object]:
    mode = preparation.plan.agent_plan.workflow_execution_mode
    if mode is None:
        raise InvalidRequestError("Mapping requires an explicit execution mode.")
    values: dict[str, object] = {
        f"workflow.mapping.{mode}.{stage_code}.context": context,
        "workflow.validation_failures": [],
    }
    object_template = _selected_template(preparation, target_type="mapping_object")
    attribute_template = _selected_template(
        preparation,
        target_type="mapping_attribute",
    )
    values["workflow.mapping.object_output_template"] = (
        None if object_template is None else object_template.model_dump(mode="json")
    )
    values["workflow.mapping.attribute_output_template"] = (
        None if attribute_template is None else attribute_template.model_dump(mode="json")
    )
    return values


def _selected_template(
    preparation: MappingPreparation,
    *,
    target_type: str,
) -> MappingOutputTemplate | None:
    selections = preparation.plan.output_template_selections
    selection = (
        selections.mapping_object
        if target_type == "mapping_object"
        else selections.mapping_attribute
    )
    if selection is None:
        return None
    return next(
        (
            item
            for item in preparation.context.output_templates.definitions
            if item.output_template_id == selection.output_template_id
            and item.target_type == target_type
            and item.schema_digest == selection.schema_digest
            and item.schema_digest_is_valid
            and item.is_active
        ),
        None,
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, AgentCandidateValidationError):
        mapping_issues = [
            issue.message for issue in error.issues if issue.code.startswith("mapping.")
        ]
        if mapping_issues:
            return WorkbenchError(
                "mapping_evidence_unresolved", " ".join(dict.fromkeys(mapping_issues))
            )
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return MappingFinalizationFailedError()
    return MappingExecutionFailedError()


__all__ = ["MappingWorkflow", "MappingExecutionFailedError", "MappingFinalizationFailedError"]
