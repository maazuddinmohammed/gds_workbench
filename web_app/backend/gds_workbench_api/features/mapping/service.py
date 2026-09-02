"""Execute one already-running governed Mapping authoring Run."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
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
    ModelWorkflow,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

from .complete_candidate import CompleteMappingCandidateValidator
from .execution_context import (
    MappingExecutionContextLimits,
    build_mapping_execution_context,
)
from .preparation_contracts import (
    MappingOutputTemplate,
    MappingPreparation,
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
    ) -> MappingPreparation: ...


class MappingChangeSetHandoff(Protocol):
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


class MappingNoOpCompleter(Protocol):
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


class MappingLifecycle(Protocol):
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
    ) -> AgentWorkflowTerminalResult: ...


class MappingRunLifecycle(Protocol):
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


class MappingExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
    ) -> MappingExecutionResult: ...


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
    """Bind the explicit Mapping route to the shared governed lifecycle."""

    def __init__(
        self,
        *,
        lifecycle: MappingRunLifecycle,
        executor: MappingExecutor,
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
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            expected_model_revision=expected_model_revision,
        )


class DatabaseMappingExecutor:
    """Run one frozen Mapping plan and hand off only one complete atomic draft."""

    def __init__(
        self,
        *,
        preparation_service: MappingPreparationService,
        agent_executor: AgentExecutor,
        handoff: MappingChangeSetHandoff,
        no_op: MappingNoOpCompleter,
        lifecycle: MappingLifecycle,
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
        try:
            preparation = await self._preparation_service.prepare(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            plan = preparation.plan.agent_plan
            _validate_plan(
                preparation,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            if not preparation.readiness.ready:
                raise InvalidRequestError("Mapping readiness checks must pass before authoring.")
            execution_mode = plan.workflow_execution_mode
            if execution_mode is None:
                raise InvalidRequestError("Mapping requires an explicit execution mode.")

            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_model_revision=expected_model_revision,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage="mapping.mapping_authoring",
                    status="running",
                    message="Mapping authoring started.",
                    current=0,
                    total=1,
                    finding_count=0,
                ),
            )

            if not _has_actionable_authoring(preparation):
                finalization_attempted = True
                return await self._complete_no_op(
                    principal,
                    preparation=preparation,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    expected_model_revision=expected_model_revision,
                    sequence=3,
                    attempt=1,
                    warning=False,
                    message="Mapping preservation completed with no effective change.",
                )

            execution_context = build_mapping_execution_context(
                preparation=preparation,
                execution_mode=execution_mode,
                limits=self._context_limits,
            )
            validator = CompleteMappingCandidateValidator(preparation=preparation)
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
            )
            candidate = outcome.candidate
            outcomes = (outcome,)
            final_sequence = 3

            result = validator.parse_validated(candidate)
            changes = result.changes
            warning = any(
                outcome.was_repaired or bool(outcome.warning_codes) for outcome in outcomes
            )
            final_attempt = max(outcome.attempt_count for outcome in outcomes)
            if not changes:
                finalization_attempted = True
                return await self._complete_no_op(
                    principal,
                    preparation=preparation,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    expected_model_revision=expected_model_revision,
                    sequence=final_sequence,
                    attempt=final_attempt,
                    warning=warning,
                    message="Mapping authoring completed with no effective change.",
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
                    message="Mapping candidate is ready in a validated draft.",
                    current=1,
                    total=1,
                    finding_count=staged_record_count,
                ),
            )
            return finalized.handoff
        except Exception as error:
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
        or mode not in ("one_shot", "tool_assisted", "detailed_coverage")
        or plan.model_id != model_id
        or mapping_plan.model_id != model_id
        or plan.workflow_run_id != workflow_run_id
        or mapping_plan.workflow_run_id != workflow_run_id
        or plan.model_revision != expected_model_revision
        or mapping_plan.model_revision != expected_model_revision
        or plan.correlation_id != mapping_plan.correlation_id
        or plan.modeled_entity_type != mapping_plan.modeled_entity_type
        or plan.selected_object_ids != (mapping_plan.pair.target_object_id,)
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
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return MappingFinalizationFailedError()
    return MappingExecutionFailedError()


__all__ = [
    "DatabaseMappingExecutor",
    "MappingExecutionFailedError",
    "MappingFinalizationFailedError",
    "MappingWorkflow",
]
