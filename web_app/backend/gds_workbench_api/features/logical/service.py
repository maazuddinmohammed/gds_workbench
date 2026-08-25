"""Execute one already-running Logical authoring run."""

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
    AgentWorkflowTerminalResult,
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
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageOutcome,
    AgentStageRunner,
)

from .candidate import LogicalCandidateValidator
from .detailed import (
    DetailedLogicalEntityDetail,
    DetailedLogicalEntityDetailValidator,
    DetailedLogicalPolicy,
    DetailedLogicalReconciliationValidator,
    DetailedLogicalTopologyContribution,
    DetailedLogicalTopologyContributionValidator,
    DetailedLogicalTopologyReconciliationValidator,
    DetailedLogicalValidationLeadValidator,
    DetailedLogicalValidationWorkerResult,
    DetailedLogicalValidationWorkerValidator,
    build_logical_relationship_signal_ledger,
    build_logical_validation_packages,
    decide_logical_detailed_handoff,
    load_default_detailed_logical_policy,
    logical_applied_record_refs,
)
from .policy import project_logical_audit_policy

_logger = logging.getLogger(__name__)


class LogicalExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class LogicalPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class LogicalContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle: ...


class LogicalChangeSetHandoff(Protocol):
    async def finalize(
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
        final_event: AgentWorkflowEvent,
    ) -> WorkflowChangeSetFinalizationResult: ...


class LogicalNoOpCompleter(Protocol):
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


class LogicalLifecycle(Protocol):
    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None: ...

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> AgentWorkflowTerminalResult: ...


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


class LogicalRunLifecycle(Protocol):
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


class LogicalExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> LogicalExecutionResult: ...


class LogicalWorkflow:
    """Bind the public route to one explicit Logical execution mode."""

    def __init__(self, *, lifecycle: LogicalRunLifecycle, executor: LogicalExecutor) -> None:
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
            expected_workflow="logical",
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
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> LogicalExecutionResult:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseLogicalExecutor:
    """Load frozen inputs, repair one candidate, and hand off one atomic draft."""

    def __init__(
        self,
        *,
        database: LogicalExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: LogicalChangeSetHandoff,
        no_op: LogicalNoOpCompleter,
        lifecycle: LogicalLifecycle,
        plan_repository: LogicalPlanRepository | None = None,
        context_repository: LogicalContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
        detailed_policy: DetailedLogicalPolicy | None = None,
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
        self._detailed_policy = detailed_policy or load_default_detailed_logical_policy()

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> LogicalExecutionResult:
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

            execution_mode = plan.workflow_execution_mode
            is_detailed = execution_mode == "detailed_coverage"
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage=(
                        "logical.topology_builder" if is_detailed else "logical.candidate_authoring"
                    ),
                    status="running",
                    message=(
                        "Logical detailed coverage started."
                        if is_detailed
                        else "Logical candidate authoring started."
                    ),
                    current=0,
                    total=(len(context.context.selected_objects) if is_detailed else 1),
                    finding_count=0,
                ),
            )
            validator = _candidate_validator(context)
            if is_detailed:
                (
                    candidate,
                    outcome,
                    intermediate_warning,
                    final_event_sequence,
                    final_attempt,
                ) = await self._execute_detailed(
                    principal,
                    plan=plan,
                    context=context,
                    validator=validator,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
            elif execution_mode in ("one_shot", "tool_assisted"):
                resolver_values: dict[str, object] = {
                    (
                        f"workflow.logical.{execution_mode}.candidate_authoring.context"
                    ): context.embedded_context,
                    "workflow.validation_failures": [],
                }
                naming = context.context.model_details.silver_model_naming_instructions
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
                intermediate_warning = False
                final_event_sequence = 3
                final_attempt = outcome.attempt_count
            else:
                raise InvalidRequestError("The Logical run does not use the fixed execution path.")
            changes = validator.parse_validated(candidate)
            changes = project_logical_audit_policy(
                changes=changes,
                applied=context.context.applied.logical,
                raw_template=(context.context.model_details.silver_model_audit_columns_template),
            )
            warning = intermediate_warning or outcome.was_repaired or bool(outcome.warning_codes)
            if not changes:
                finalization_attempted = True
                return await self._no_op.complete(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                    request=AuthoringNoOpRequest(
                        expected_workflow="logical",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_model_revision=expected_model_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=AgentWorkflowEvent(
                            sequence=final_event_sequence,
                            attempt=final_attempt,
                            stage="logical.backend_validation",
                            status="warning" if warning else "running",
                            message="Logical authoring completed with no effective change.",
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
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="logical",
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=AgentWorkflowEvent(
                    sequence=final_event_sequence,
                    attempt=final_attempt,
                    stage="logical.backend_validation",
                    status="warning" if warning else "running",
                    message="Logical candidate is ready in a validated draft.",
                    current=1,
                    total=1,
                    finding_count=staged_record_count,
                ),
            )
            return finalization.handoff
        except Exception as error:
            safe_error = _safe_execution_error(
                error,
                finalization_attempted=finalization_attempted,
            )
            if finalization_attempted:
                _logger.warning(
                    "Logical Workflow Run finalization remains pending.",
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
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        failure_code=safe_error.code[:100],
                        safe_failure_message=safe_error.message[:2000],
                    )
                except Exception:
                    _logger.warning(
                        "Logical failure state could not be persisted.",
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
        validator: LogicalCandidateValidator,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> tuple[JsonValue, AgentStageOutcome, bool, int, int]:
        contributions: list[DetailedLogicalTopologyContribution] = []
        intermediate_warning = False
        max_attempt = 1
        for selected in context.context.selected_objects:
            source_attributes = _physical_attribute_keys(selected)
            if not source_attributes:
                raise InvalidRequestError(
                    "Detailed Logical coverage requires Attributes for every selected Object."
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
                    "applied_logical": _applied_logical_context(context),
                },
            )
            contribution_validator = DetailedLogicalTopologyContributionValidator(
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
            contribution = contribution_validator.parse_validated(outcome.candidate)
            contributions.append(contribution)
            max_attempt = max(max_attempt, outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or contribution.disposition == "needs_review"
                or outcome.was_repaired
                or bool(outcome.warning_codes)
            )

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=3,
                attempt=1,
                stage="logical.topology_reconciler",
                status="running",
                message="Logical Object contributions are ready for topology reconciliation.",
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
                "applied_logical": _applied_logical_context(context),
            },
        )
        topology_validator = DetailedLogicalTopologyReconciliationValidator(
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

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=4,
                attempt=1,
                stage="logical.entity_detail_builder",
                status="running",
                message="Logical topology is ready for Entity detail authoring.",
                current=0 if topology.entities else None,
                total=len(topology.entities) if topology.entities else None,
                finding_count=len(topology.entities),
            ),
        )
        contribution_by_ref = {item.contribution_ref: item for item in contributions}
        selected_by_ref = {
            f"object_{item.selection_order:05d}": item for item in context.context.selected_objects
        }
        details: list[DetailedLogicalEntityDetail] = []
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
                },
            )
            detail_validator = DetailedLogicalEntityDetailValidator(
                entity=entity,
                topology=topology,
                contributions=tuple(contributions),
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

        relationship_ledger = build_logical_relationship_signal_ledger(
            entity_details=tuple(details),
            max_signals=self._detailed_policy.max_relationship_signals,
        )
        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=5,
                attempt=1,
                stage="logical.relationship_signal_derivation",
                status="running",
                message="Deterministic Logical relationship signals are ready.",
                current=(len(relationship_ledger.signals) if relationship_ledger.signals else None),
                total=(len(relationship_ledger.signals) if relationship_ledger.signals else None),
                finding_count=len(relationship_ledger.signals),
            ),
        )
        applied_refs = logical_applied_record_refs(context.context.applied.logical)
        reconciliation_context = cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "model": _detailed_model_context(context),
                "topology": topology.model_dump(mode="json"),
                "entity_details": [item.model_dump(mode="json") for item in details],
                "relationship_signal_ledger": relationship_ledger.model_dump(mode="json"),
                "applied_logical": _applied_logical_context(context),
                "required_applied_record_refs": list(applied_refs),
            },
        )
        reconciliation_validator = DetailedLogicalReconciliationValidator(
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
            max_attempt = max(max_attempt, repair_count + 1)
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=plan.workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=repair_count + 1,
                    stage="logical.whole_model_reconciliation",
                    status="running",
                    message="Logical whole-model reconciliation started.",
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
            reconciliation = reconciliation_validator.parse_validated(
                reconciliation_outcome.candidate
            )
            max_attempt = max(max_attempt, reconciliation_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or reconciliation_outcome.was_repaired
                or bool(reconciliation_outcome.warning_codes)
            )
            if not any(
                (
                    reconciliation.submodels,
                    reconciliation.entities,
                    reconciliation.attributes,
                    reconciliation.relationships,
                )
            ):
                return (
                    reconciliation_validator.materialize_validated(
                        reconciliation_outcome.candidate
                    ),
                    reconciliation_outcome,
                    intermediate_warning,
                    sequence + 1,
                    max_attempt,
                )
            packages = build_logical_validation_packages(
                candidate=reconciliation,
                package_size=self._detailed_policy.validation_package_size,
                max_packages=self._detailed_policy.max_validation_packages,
            )

            sequence += 1
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=plan.workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=repair_count + 1,
                    stage="logical.validator_worker",
                    status="running",
                    message="Logical validation packages are ready for review.",
                    current=0,
                    total=len(packages),
                    finding_count=len(packages),
                ),
            )
            worker_results: list[DetailedLogicalValidationWorkerResult] = []
            for package in packages:
                worker_context = cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "model": _detailed_model_context(context),
                        "validation_package": package.model_dump(mode="json"),
                    },
                )
                worker_validator = DetailedLogicalValidationWorkerValidator(package=package)
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
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=repair_count + 1,
                    stage="logical.validator_lead",
                    status="running",
                    message="Logical validation findings are ready for reconciliation.",
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
            lead_validator = DetailedLogicalValidationLeadValidator(
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
            decision = decide_logical_detailed_handoff(
                reconciliation_validator=reconciliation_validator,
                reconciliation_candidate=reconciliation_outcome.candidate,
                validation_lead=lead,
                worker_results=tuple(worker_results),
            )
            if decision.next_stage == "handoff":
                if decision.handoff_candidate is None:
                    raise AgentCandidateValidationError()
                return (
                    decision.handoff_candidate,
                    reconciliation_outcome,
                    intermediate_warning,
                    sequence + 1,
                    max_attempt,
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
            or plan.model_workflow != "logical"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Logical run does not use the fixed execution path.")


def _detailed_resolver_values(
    context: AgentContextBundle,
    *,
    stage_code: str,
    stage_context: JsonValue,
    validation_failures: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    values: dict[str, object] = {
        f"workflow.logical.detailed_coverage.{stage_code}.context": stage_context
    }
    if stage_code in {
        "topology_builder",
        "topology_reconciler",
        "entity_detail_builder",
        "whole_model_reconciliation",
    }:
        naming = context.context.model_details.silver_model_naming_instructions
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


def _applied_logical_context(context: AgentContextBundle) -> JsonValue:
    section = context.context.applied.logical
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
    return LogicalCandidateValidator(
        selected_object_keys=selected_objects,
        selected_attribute_keys=selected_attributes,
        assertion_record_keys=assertion_keys,
        applied=context.context.applied.logical,
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


__all__ = [
    "DatabaseLogicalExecutor",
    "LogicalExecutionFailedError",
    "LogicalFinalizationFailedError",
    "LogicalWorkflow",
]
