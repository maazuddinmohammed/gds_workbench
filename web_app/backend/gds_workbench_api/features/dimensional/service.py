"""Execute one already-running Dimensional authoring run."""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ProfilingProfileRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    PostgresAgentContextRepository,
    SelectedObjectContext,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
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
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

from .candidate import DimensionalCandidateValidator
from .detailed import (
    DetailedDimensionalEntityDetail,
    DetailedDimensionalEntityDetailValidator,
    DetailedDimensionalPolicy,
    DetailedDimensionalReconciliationValidator,
    DetailedDimensionalTopologyContribution,
    DetailedDimensionalTopologyContributionValidator,
    DetailedDimensionalTopologyReconciliationValidator,
    DetailedDimensionalValidationLeadValidator,
    DetailedDimensionalValidationWorkerResult,
    DetailedDimensionalValidationWorkerValidator,
    build_dimensional_relationship_signal_ledger,
    build_projected_dimensional_validation_packages,
    decide_dimensional_detailed_handoff,
    dimensional_applied_record_refs,
    load_default_detailed_dimensional_policy,
)
from .policy import (
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
    validate_dimensional_gold_policy,
)

_logger = logging.getLogger(__name__)


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
        detailed_policy: DetailedDimensionalPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresAgentContextRepository()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=context_policy or load_default_agent_context_policy(),
        )
        self._handoff = handoff
        self._no_op = no_op
        self._lifecycle = lifecycle
        self._detailed_policy = detailed_policy or load_default_detailed_dimensional_policy()

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
        try:
            async with self._database.write_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_MODEL_WRITE,
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
                naming_instructions=model_details.gold_model_naming_instructions,
                raw_technical_template=(model_details.gold_model_technical_columns_template),
                raw_audit_template=model_details.gold_model_audit_columns_template,
            )

            execution_mode = plan.workflow_execution_mode
            is_detailed = execution_mode == "detailed_coverage"
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_model_revision=expected_model_revision,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage=(
                        "dimensional.topology_builder"
                        if is_detailed
                        else "dimensional.candidate_authoring"
                    ),
                    status="running",
                    message=(
                        "Dimensional detailed coverage started."
                        if is_detailed
                        else "Dimensional candidate authoring started."
                    ),
                    current=0,
                    total=(len(context.context.selected_objects) if is_detailed else 1),
                    finding_count=0,
                ),
            )
            validator = _candidate_validator(context)
            if is_detailed:
                (
                    changes,
                    final_attempt,
                    intermediate_warning,
                    final_event_sequence,
                ) = await self._execute_detailed(
                    principal,
                    plan=plan,
                    context=context,
                    validator=validator,
                    workflow_run_claim_token=workflow_run_claim_token,
                    expected_model_revision=expected_model_revision,
                )
            elif execution_mode in ("one_shot", "tool_assisted"):
                resolver_values: dict[str, object] = {
                    (
                        f"workflow.dimensional.{execution_mode}.candidate_authoring.context"
                    ): context.embedded_context,
                    "workflow.validation_failures": [],
                }
                naming = context.context.model_details.gold_model_naming_instructions
                if naming is not None:
                    resolver_values["model.naming_instructions"] = naming
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
                )
                candidate = outcome.candidate
                final_attempt = outcome.attempt_count
                intermediate_warning = outcome.was_repaired or bool(outcome.warning_codes)
                final_event_sequence = 3
                changes = _project_dimensional_changes(
                    validator=validator,
                    candidate=candidate,
                    context=context,
                )
            else:
                raise InvalidRequestError(
                    "The Dimensional run does not use the fixed execution path."
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
                        final_event=AgentWorkflowEvent(
                            sequence=final_event_sequence,
                            attempt=final_attempt,
                            stage="dimensional.backend_validation",
                            status=("warning" if intermediate_warning else "running"),
                            message=("Dimensional authoring completed with no effective change."),
                            current=1,
                            total=1,
                            finding_count=0,
                        ),
                    ),
                )

            staged_record_count = sum(len(change.records) for change in changes)
            final_event = AgentWorkflowEvent(
                sequence=final_event_sequence,
                attempt=final_attempt,
                stage="dimensional.backend_validation",
                status="warning" if intermediate_warning else "running",
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

    async def _execute_detailed(
        self,
        principal: RequestPrincipal,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        validator: DimensionalCandidateValidator,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
    ) -> tuple[tuple[StageModelChange, ...], int, bool, int]:
        contributions: list[DetailedDimensionalTopologyContribution] = []
        intermediate_warning = False
        max_attempt = 1
        for selected in context.context.selected_objects:
            source_attributes = _physical_attribute_keys(selected)
            if not source_attributes:
                raise InvalidRequestError(
                    "Detailed Dimensional coverage requires Attributes for every selected Object."
                )
            contribution_ref = f"object_{selected.selection_order:05d}"
            stage_context = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": _detailed_model_context(context),
                    "contribution_ref": contribution_ref,
                    "selected_object": selected.model_dump(mode="json"),
                    "profiles": [
                        item.model_dump(mode="json")
                        for item in context.context.profiles
                        if _profile_matches_selected(item, selected)
                    ],
                    "analysis_relationships": [
                        item.model_dump(mode="json")
                        for item in context.context.analysis_relationships
                        if _analysis_matches_selected(item, selected)
                    ],
                    "assertions": context.context.assertion.model_dump(mode="json"),
                    "applied_dimensional": _applied_dimensional_context(context),
                },
            )
            contribution_validator = DetailedDimensionalTopologyContributionValidator(
                contribution_ref=contribution_ref,
                source_object=_physical_object_key(selected),
                source_attributes=source_attributes,
            )
            outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="topology_builder",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="topology_builder",
                    stage_context=stage_context,
                ),
                context=stage_context,
                output_schema=contribution_validator.output_schema(),
                allowed_tool_names=(),
                validator=contribution_validator,
            )
            contributions.append(contribution_validator.parse_validated(outcome.candidate))
            max_attempt = max(max_attempt, outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning or outcome.was_repaired or bool(outcome.warning_codes)
            )
        intermediate_warning = intermediate_warning or any(
            item.disposition == "needs_review" for item in contributions
        )

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            expected_model_revision=expected_model_revision,
            event=AgentWorkflowEvent(
                sequence=3,
                attempt=1,
                stage="dimensional.topology_reconciler",
                status="running",
                message=("Dimensional Object contributions are ready for topology reconciliation."),
                current=len(contributions),
                total=len(contributions),
                finding_count=len(contributions),
            ),
        )
        topology_context = cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "model": _detailed_model_context(context),
                "contributions": [item.model_dump(mode="json") for item in contributions],
                "applied_dimensional": _applied_dimensional_context(context),
            },
        )
        topology_validator = DetailedDimensionalTopologyReconciliationValidator(
            contributions=tuple(contributions)
        )
        topology_outcome = await self._stage_runner.run(
            plan=plan,
            stage_code="topology_reconciler",
            resolver_values=_detailed_resolver_values(
                context,
                stage_code="topology_reconciler",
                stage_context=topology_context,
            ),
            context=topology_context,
            output_schema=topology_validator.output_schema(),
            allowed_tool_names=(),
            validator=topology_validator,
        )
        topology = topology_validator.parse_validated(topology_outcome.candidate)
        max_attempt = max(max_attempt, topology_outcome.attempt_count)
        intermediate_warning = (
            intermediate_warning
            or topology_outcome.was_repaired
            or bool(topology_outcome.warning_codes)
        )
        if not topology.entities:
            return (), max_attempt, intermediate_warning, 4

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            expected_model_revision=expected_model_revision,
            event=AgentWorkflowEvent(
                sequence=4,
                attempt=1,
                stage="dimensional.entity_detail_builder",
                status="running",
                message="Dimensional topology is ready for Entity detail authoring.",
                current=0 if topology.entities else None,
                total=len(topology.entities) if topology.entities else None,
                finding_count=len(topology.entities),
            ),
        )
        contribution_by_ref = {item.contribution_ref: item for item in contributions}
        selected_by_ref = {
            f"object_{item.selection_order:05d}": item for item in context.context.selected_objects
        }
        assertion_record_keys = tuple(
            record.modeling_assertion_record_key for record in context.context.assertion.records
        )
        details: list[DetailedDimensionalEntityDetail] = []
        for entity in topology.entities:
            contribution_refs = {
                item.split(".", maxsplit=1)[0] for item in entity.contribution_refs
            }
            relevant_contributions = tuple(
                contribution_by_ref[item] for item in sorted(contribution_refs)
            )
            detail_context = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": _detailed_model_context(context),
                    "topology": topology.model_dump(mode="json"),
                    "entity": entity.model_dump(mode="json"),
                    "contributions": [
                        item.model_dump(mode="json") for item in relevant_contributions
                    ],
                    "selected_objects": [
                        selected_by_ref[item].model_dump(mode="json")
                        for item in sorted(contribution_refs)
                    ],
                    "assertions": context.context.assertion.model_dump(mode="json"),
                },
            )
            detail_validator = DetailedDimensionalEntityDetailValidator(
                entity=entity,
                topology=topology,
                contributions=tuple(contributions),
                assertion_record_keys=assertion_record_keys,
            )
            detail_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="entity_detail_builder",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="entity_detail_builder",
                    stage_context=detail_context,
                ),
                context=detail_context,
                output_schema=detail_validator.output_schema(),
                allowed_tool_names=(),
                validator=detail_validator,
            )
            details.append(detail_validator.parse_validated(detail_outcome.candidate))
            max_attempt = max(max_attempt, detail_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or detail_outcome.was_repaired
                or bool(detail_outcome.warning_codes)
            )

        relationship_ledger = build_dimensional_relationship_signal_ledger(
            entity_details=tuple(details),
            max_signals=self._detailed_policy.max_relationship_signals,
        )
        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            workflow_run_claim_token=workflow_run_claim_token,
            expected_model_revision=expected_model_revision,
            event=AgentWorkflowEvent(
                sequence=5,
                attempt=1,
                stage="dimensional.relationship_signal_derivation",
                status="running",
                message="Deterministic Dimensional relationship signals are ready.",
                current=(len(relationship_ledger.signals) if relationship_ledger.signals else None),
                total=(len(relationship_ledger.signals) if relationship_ledger.signals else None),
                finding_count=len(relationship_ledger.signals),
            ),
        )
        applied_refs = dimensional_applied_record_refs(context.context.applied.dimensional)
        reconciliation_context = cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "model": _detailed_model_context(context),
                "topology": topology.model_dump(mode="json"),
                "entity_details": [item.model_dump(mode="json") for item in details],
                "relationship_signal_ledger": relationship_ledger.model_dump(mode="json"),
                "applied_dimensional": _applied_dimensional_context(context),
                "required_applied_record_refs": list(applied_refs),
            },
        )
        reconciliation_validator = DetailedDimensionalReconciliationValidator(
            topology=topology,
            entity_details=tuple(details),
            relationship_signal_refs=relationship_ledger.signal_refs,
            applied_record_refs=applied_refs,
            final_validator=validator,
        )

        sequence = 6
        repair_count = 0
        validation_failures: list[dict[str, object]] = []
        while True:
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=plan.workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_model_revision=expected_model_revision,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=repair_count + 1,
                    stage="dimensional.whole_model_reconciliation",
                    status="running",
                    message="Dimensional whole-model reconciliation started.",
                    current=0,
                    total=1,
                    finding_count=len(validation_failures),
                ),
            )
            reconciliation_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="whole_model_reconciliation",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="whole_model_reconciliation",
                    stage_context=reconciliation_context,
                    validation_failures=validation_failures,
                ),
                context=reconciliation_context,
                output_schema=reconciliation_validator.output_schema(),
                allowed_tool_names=(),
                validator=reconciliation_validator,
            )
            materialized_candidate = reconciliation_validator.materialize_validated(
                reconciliation_outcome.candidate
            )
            max_attempt = max(
                max_attempt,
                repair_count + 1,
                reconciliation_outcome.attempt_count,
            )
            intermediate_warning = (
                intermediate_warning
                or reconciliation_outcome.was_repaired
                or bool(reconciliation_outcome.warning_codes)
            )
            projected_changes = _project_dimensional_changes(
                validator=validator,
                candidate=materialized_candidate,
                context=context,
            )
            if not projected_changes:
                return (), max_attempt, intermediate_warning, sequence + 1
            packages = build_projected_dimensional_validation_packages(
                projected_changes=projected_changes,
                package_size=self._detailed_policy.validation_package_size,
                max_packages=self._detailed_policy.max_validation_packages,
            )

            sequence += 1
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=plan.workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_model_revision=expected_model_revision,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=repair_count + 1,
                    stage="dimensional.validator_worker",
                    status="running",
                    message="Dimensional validation packages are ready for review.",
                    current=0,
                    total=len(packages),
                    finding_count=len(packages),
                ),
            )
            worker_results: list[DetailedDimensionalValidationWorkerResult] = []
            for package in packages:
                worker_context = cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "model": _detailed_model_context(context),
                        "validation_package": package.model_dump(mode="json"),
                    },
                )
                worker_validator = DetailedDimensionalValidationWorkerValidator(package=package)
                worker_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="validator_worker",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="validator_worker",
                        stage_context=worker_context,
                    ),
                    context=worker_context,
                    output_schema=worker_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=worker_validator,
                )
                worker_results.append(worker_validator.parse_validated(worker_outcome.candidate))
                max_attempt = max(max_attempt, worker_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or worker_outcome.was_repaired
                    or bool(worker_outcome.warning_codes)
                )

            sequence += 1
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=plan.workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                expected_model_revision=expected_model_revision,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=repair_count + 1,
                    stage="dimensional.validator_lead",
                    status="running",
                    message=("Dimensional validation findings are ready for reconciliation."),
                    current=len(worker_results),
                    total=len(worker_results),
                    finding_count=sum(len(item.findings) for item in worker_results),
                ),
            )
            lead_context = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": _detailed_model_context(context),
                    "worker_results": [item.model_dump(mode="json") for item in worker_results],
                },
            )
            lead_validator = DetailedDimensionalValidationLeadValidator(
                worker_results=tuple(worker_results)
            )
            lead_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="validator_lead",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="validator_lead",
                    stage_context=lead_context,
                ),
                context=lead_context,
                output_schema=lead_validator.output_schema(),
                allowed_tool_names=(),
                validator=lead_validator,
            )
            lead = lead_validator.parse_validated(lead_outcome.candidate)
            max_attempt = max(max_attempt, lead_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or lead_outcome.was_repaired
                or bool(lead_outcome.warning_codes)
            )
            decision = decide_dimensional_detailed_handoff(
                reconciliation_validator=reconciliation_validator,
                reconciliation_candidate=reconciliation_outcome.candidate,
                validation_lead=lead,
                worker_results=tuple(worker_results),
            )
            if decision.next_stage == "handoff":
                if decision.handoff_candidate is None:
                    raise AgentCandidateValidationError()
                return (
                    projected_changes,
                    max_attempt,
                    intermediate_warning,
                    sequence + 1,
                )
            if repair_count >= plan.selection.validation_retry_count:
                raise AgentCandidateValidationError()
            repair_count += 1
            intermediate_warning = True
            validation_failures = [
                item.model_dump(mode="json") for item in decision.validation_failures
            ]
            sequence += 1

    @staticmethod
    def _validate_plan(
        plan: AgentRunPlan,
        *,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> None:
        stage_codes = tuple(stage.stage_code for stage in plan.stages)
        mode_path_is_valid = (
            plan.workflow_execution_mode in ("one_shot", "tool_assisted")
            and stage_codes == ("candidate_authoring",)
        ) or (
            plan.workflow_execution_mode == "detailed_coverage"
            and stage_codes
            == (
                "topology_builder",
                "topology_reconciler",
                "entity_detail_builder",
                "whole_model_reconciliation",
                "validator_worker",
                "validator_lead",
            )
        )
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "dimensional"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Dimensional run does not use the fixed execution path.")


def _detailed_resolver_values(
    context: AgentContextBundle,
    *,
    stage_code: str,
    stage_context: JsonValue,
    validation_failures: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    values: dict[str, object] = {
        f"workflow.dimensional.detailed_coverage.{stage_code}.context": (stage_context)
    }
    if stage_code in {
        "topology_builder",
        "topology_reconciler",
        "entity_detail_builder",
        "whole_model_reconciliation",
    }:
        naming = context.context.model_details.gold_model_naming_instructions
        if naming is not None:
            values["model.naming_instructions"] = naming
    if stage_code == "whole_model_reconciliation":
        values["workflow.validation_failures"] = validation_failures or []
    return values


def _detailed_model_context(context: AgentContextBundle) -> JsonValue:
    return cast(
        JsonValue,
        {
            "model_id": context.context.model_id,
            "model_name": context.context.model_name,
            "model_revision": context.context.model_revision,
            "model_details": context.context.model_details.model_dump(mode="json"),
        },
    )


def _applied_dimensional_context(context: AgentContextBundle) -> JsonValue:
    section = context.context.applied.dimensional
    return None if section is None else cast(JsonValue, section.model_dump(mode="json"))


def _physical_object_key(selected: SelectedObjectContext) -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code=selected.object.tenant_code,
        system_code=selected.object.system_code,
        connection_code=selected.object.connection_code,
        object_schema=selected.object.object_schema,
        object_name=selected.object.object_name,
    )


def _physical_attribute_keys(
    selected: SelectedObjectContext,
) -> tuple[PhysicalAttributeKey, ...]:
    return tuple(
        PhysicalAttributeKey(
            tenant_code=item.tenant_code,
            system_code=item.system_code,
            connection_code=item.connection_code,
            object_schema=item.object_schema,
            object_name=item.object_name,
            attribute_name=item.attribute_name,
        )
        for item in selected.attributes
    )


def _profile_matches_selected(
    profile: ProfilingProfileRecord,
    selected: SelectedObjectContext,
) -> bool:
    return _normalized_object_identity(
        profile.tenant_code,
        profile.system_code,
        profile.connection_code,
        profile.object_schema,
        profile.object_name,
    ) == _selected_identity(selected)


def _analysis_matches_selected(
    relationship: AnalysisResultRecord,
    selected: SelectedObjectContext,
) -> bool:
    selected_key = _selected_identity(selected)
    return selected_key in {
        _normalized_object_identity(
            relationship.from_tenant_code,
            relationship.from_system_code,
            relationship.from_connection_code,
            relationship.from_object_schema,
            relationship.from_object_name,
        ),
        _normalized_object_identity(
            relationship.to_tenant_code,
            relationship.to_system_code,
            relationship.to_connection_code,
            relationship.to_object_schema,
            relationship.to_object_name,
        ),
    }


def _selected_identity(selected: SelectedObjectContext) -> tuple[str, ...]:
    return _normalized_object_identity(
        selected.object.tenant_code,
        selected.object.system_code,
        selected.object.connection_code,
        selected.object.object_schema,
        selected.object.object_name,
    )


def _normalized_object_identity(*values: str) -> tuple[str, ...]:
    return tuple(normalize_model_key_value(value) for value in values)


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
