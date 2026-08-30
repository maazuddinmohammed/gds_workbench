"""Execute one already-running Logical authoring run."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.metadata_records import AttributeRecord
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    LogicalAttributeRecord,
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
from pydantic import BaseModel, JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)
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
    agent_request_envelope_bytes,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageOutcome,
    AgentStageRunner,
)
from gds_workbench_api.prompt_rendering import render_prompt

from .candidate import LogicalCandidateValidator
from .detailed import (
    DetailedLogicalEntityDetail,
    DetailedLogicalEntityDetailValidator,
    DetailedLogicalEntityTopology,
    DetailedLogicalPolicy,
    DetailedLogicalReconciliationCandidate,
    DetailedLogicalReconciliationValidator,
    DetailedLogicalRelationshipSignal,
    DetailedLogicalRelationshipSignalLedger,
    DetailedLogicalTopologyContribution,
    DetailedLogicalTopologyContributionValidator,
    DetailedLogicalTopologyProposal,
    DetailedLogicalTopologyReconciliation,
    DetailedLogicalTopologyReconciliationValidator,
    DetailedLogicalValidationLead,
    DetailedLogicalValidationLeadValidator,
    DetailedLogicalValidationPackage,
    DetailedLogicalValidationRecord,
    DetailedLogicalValidationWorkerResult,
    DetailedLogicalValidationWorkerValidator,
    build_logical_relationship_signal_ledger,
    decide_logical_detailed_handoff,
    load_default_detailed_logical_policy,
    logical_applied_record_refs,
    logical_json_bytes,
    logical_json_digest,
    logical_validation_records,
    merge_logical_entity_detail_partitions,
    merge_logical_reconciliation_partitions,
    merge_logical_topology_partitions,
)
from .policy import project_logical_audit_policy

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TopologyBuilderBatch:
    contribution_ref: str
    source_attributes: tuple[PhysicalAttributeKey, ...]
    context: JsonValue


@dataclass(frozen=True, slots=True)
class _TopologyReconciliationBatch:
    contributions: tuple[DetailedLogicalTopologyContribution, ...]
    context: JsonValue


@dataclass(frozen=True, slots=True)
class _EntityDetailBatch:
    entity: DetailedLogicalEntityTopology
    topology: DetailedLogicalTopologyReconciliation
    contributions: tuple[DetailedLogicalTopologyContribution, ...]
    context: JsonValue


@dataclass(frozen=True, slots=True)
class _ReconciliationBatch:
    topology: DetailedLogicalTopologyReconciliation
    entity_details: tuple[DetailedLogicalEntityDetail, ...]
    relationship_signal_refs: tuple[str, ...]
    applied_record_refs: tuple[str, ...]
    context: JsonValue


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
        selected_context_policy = context_policy or load_default_agent_context_policy()
        self._context_policy = selected_context_policy
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=selected_context_policy,
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
            for batch in self._topology_builder_batches(
                plan=plan,
                context=context,
                selected=selected,
            ):
                contribution_validator = DetailedLogicalTopologyContributionValidator(
                    contribution_ref=batch.contribution_ref,
                    source_object=_physical_object_key(selected),
                    source_attributes=batch.source_attributes,
                    max_result_bytes=self._detailed_result_limit,
                )
                outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="topology_builder",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="topology_builder",
                        stage_context=batch.context,
                    ),
                    context=batch.context,
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
        topology_partitions: list[DetailedLogicalTopologyReconciliation] = []
        topology_outcome: AgentStageOutcome | None = None
        for topology_batch in self._topology_reconciliation_batches(
            plan=plan,
            context=context,
            contributions=tuple(contributions),
        ):
            topology_validator = DetailedLogicalTopologyReconciliationValidator(
                contributions=topology_batch.contributions,
                max_result_bytes=self._detailed_result_limit,
            )
            topology_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="topology_reconciler",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="topology_reconciler",
                    stage_context=topology_batch.context,
                ),
                context=topology_batch.context,
                output_schema=topology_validator.output_schema(),
                allowed_tool_names=(),
                validator=topology_validator,
            )
            topology_partitions.append(
                topology_validator.parse_validated(topology_outcome.candidate)
            )
            max_attempt = max(max_attempt, topology_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or topology_outcome.was_repaired
                or bool(topology_outcome.warning_codes)
            )
        if topology_outcome is None:
            raise AgentCandidateValidationError()
        topology = (
            topology_partitions[0]
            if len(topology_partitions) == 1
            else merge_logical_topology_partitions(
                contributions=tuple(contributions),
                partitions=tuple(topology_partitions),
            )
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
        details: list[DetailedLogicalEntityDetail] = []
        for entity in topology.entities:
            detail_partitions: list[DetailedLogicalEntityDetail] = []
            for detail_batch in self._entity_detail_batches(
                plan=plan,
                context=context,
                entity=entity,
                topology=topology,
                contributions=tuple(contributions),
            ):
                detail_validator = DetailedLogicalEntityDetailValidator(
                    entity=detail_batch.entity,
                    topology=detail_batch.topology,
                    contributions=detail_batch.contributions,
                    max_result_bytes=self._detailed_result_limit,
                )
                detail_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="entity_detail_builder",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="entity_detail_builder",
                        stage_context=detail_batch.context,
                    ),
                    context=detail_batch.context,
                    output_schema=detail_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=detail_validator,
                )
                detail_partitions.append(detail_validator.parse_validated(detail_outcome.candidate))
                max_attempt = max(max_attempt, detail_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or detail_outcome.was_repaired
                    or bool(detail_outcome.warning_codes)
                )
            details.append(
                detail_partitions[0]
                if len(detail_partitions) == 1
                else merge_logical_entity_detail_partitions(
                    entity=entity,
                    topology=topology,
                    contributions=tuple(contributions),
                    partitions=tuple(detail_partitions),
                )
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
            bounded_failures = _bounded_validation_failures(validation_failures)
            reconciliation_batches = self._reconciliation_batches(
                plan=plan,
                context=context,
                topology=topology,
                entity_details=tuple(details),
                relationship_ledger=relationship_ledger,
                applied_record_refs=applied_refs,
                validation_failures=bounded_failures,
            )
            reconciliation_validator = DetailedLogicalReconciliationValidator(
                topology=topology,
                entity_details=tuple(details),
                relationship_signal_refs=relationship_ledger.signal_refs,
                applied_record_refs=applied_refs,
                final_validator=validator,
                max_result_bytes=None,
            )
            reconciliation_partitions: list[DetailedLogicalReconciliationCandidate] = []
            reconciliation_outcome: AgentStageOutcome | None = None
            for reconciliation_batch in reconciliation_batches:
                scoped_validator = (
                    DetailedLogicalReconciliationValidator(
                        topology=topology,
                        entity_details=tuple(details),
                        relationship_signal_refs=relationship_ledger.signal_refs,
                        applied_record_refs=applied_refs,
                        final_validator=validator,
                        max_result_bytes=self._detailed_result_limit,
                    )
                    if len(reconciliation_batches) == 1
                    else DetailedLogicalReconciliationValidator(
                        topology=reconciliation_batch.topology,
                        entity_details=reconciliation_batch.entity_details,
                        relationship_signal_refs=(reconciliation_batch.relationship_signal_refs),
                        applied_record_refs=reconciliation_batch.applied_record_refs,
                        max_result_bytes=self._detailed_result_limit,
                        require_exact_base_records=True,
                    )
                )
                reconciliation_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="whole_model_reconciliation",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="whole_model_reconciliation",
                        stage_context=reconciliation_batch.context,
                        validation_failures=bounded_failures,
                    ),
                    context=reconciliation_batch.context,
                    output_schema=scoped_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=scoped_validator,
                )
                reconciliation_partitions.append(
                    scoped_validator.parse_validated(reconciliation_outcome.candidate)
                )
                max_attempt = max(max_attempt, reconciliation_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or reconciliation_outcome.was_repaired
                    or bool(reconciliation_outcome.warning_codes)
                )
            if reconciliation_outcome is None:
                raise AgentCandidateValidationError()
            reconciliation = (
                reconciliation_partitions[0]
                if len(reconciliation_partitions) == 1
                else merge_logical_reconciliation_partitions(
                    partitions=tuple(reconciliation_partitions),
                    reviewed_submodel_refs=tuple(
                        item.canonical_submodel_ref for item in topology.submodels
                    ),
                    reviewed_entity_refs=tuple(item.canonical_entity_ref for item in details),
                    reviewed_relationship_signal_refs=relationship_ledger.signal_refs,
                    reviewed_applied_record_refs=applied_refs,
                )
            )
            reconciliation_candidate = cast(
                JsonValue,
                reconciliation.model_dump(mode="json"),
            )
            if (await reconciliation_validator.validate(reconciliation_candidate)).issues:
                raise AgentCandidateValidationError()
            if not any(
                (
                    reconciliation.submodels,
                    reconciliation.entities,
                    reconciliation.attributes,
                    reconciliation.relationships,
                )
            ):
                return (
                    reconciliation_validator.materialize_validated(reconciliation_candidate),
                    reconciliation_outcome,
                    intermediate_warning,
                    sequence + 1,
                    max_attempt,
                )
            packages = self._validation_packages(
                plan=plan,
                context=context,
                candidate=reconciliation,
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
                worker_context = _validation_worker_context(context, package=package)
                worker_validator = DetailedLogicalValidationWorkerValidator(
                    package=package,
                    max_result_bytes=self._detailed_result_limit,
                )
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
            lead_partitions: list[DetailedLogicalValidationLead] = []
            for lead_batch in self._validation_lead_batches(
                plan=plan,
                context=context,
                worker_results=tuple(worker_results),
            ):
                lead_context = _validation_lead_context(
                    context,
                    worker_results=lead_batch,
                )
                lead_validator = DetailedLogicalValidationLeadValidator(
                    worker_results=lead_batch,
                    max_result_bytes=self._detailed_result_limit,
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
                lead_partitions.append(lead_validator.parse_validated(lead_outcome.candidate))
                max_attempt = max(max_attempt, lead_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or lead_outcome.was_repaired
                    or bool(lead_outcome.warning_codes)
                )
            lead = (
                lead_partitions[0]
                if len(lead_partitions) == 1
                else _merge_validation_leads(
                    worker_results=tuple(worker_results),
                    partitions=tuple(lead_partitions),
                )
            )
            decision = decide_logical_detailed_handoff(
                reconciliation_validator=reconciliation_validator,
                reconciliation_candidate=reconciliation_candidate,
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

    @property
    def _detailed_request_limit(self) -> int:
        return max(1, self._context_policy.stage_max_context_bytes // 2)

    @property
    def _detailed_result_limit(self) -> int:
        return min(
            self._context_policy.max_candidate_bytes,
            max(1, self._context_policy.stage_max_context_bytes // 8),
        )

    @property
    def _detailed_source_record_limit(self) -> int:
        return max(1, min(10_000, self._detailed_result_limit // 2_048))

    def _topology_builder_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        selected: SelectedObjectContext,
    ) -> tuple[_TopologyBuilderBatch, ...]:
        source_attributes = _physical_attribute_keys(selected)
        if not source_attributes:
            raise InvalidRequestError(
                "Detailed Logical coverage requires Attributes for every selected Object."
            )
        base_ref = f"object_{selected.selection_order:05d}"
        full_context = _topology_builder_context(
            context,
            selected=selected,
            attributes=selected.attributes,
            contribution_ref=base_ref,
            batch_index=1,
            batch_count=1,
            bounded_support=False,
        )
        if len(source_attributes) <= self._detailed_source_record_limit:
            validator = DetailedLogicalTopologyContributionValidator(
                contribution_ref=base_ref,
                source_object=_physical_object_key(selected),
                source_attributes=source_attributes,
                max_result_bytes=self._detailed_result_limit,
            )
            if self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_builder",
                stage_context=full_context,
                output_schema=validator.output_schema(),
            ):
                return (
                    _TopologyBuilderBatch(
                        contribution_ref=base_ref,
                        source_attributes=source_attributes,
                        context=full_context,
                    ),
                )

        raw_batches: list[tuple[AttributeRecord, ...]] = []
        pending: list[AttributeRecord] = []
        for attribute in selected.attributes:
            candidate = (*pending, attribute)
            reference = f"{base_ref}_batch_99999"
            candidate_context = _topology_builder_context(
                context,
                selected=selected,
                attributes=candidate,
                contribution_ref=reference,
                batch_index=99_999,
                batch_count=99_999,
                bounded_support=True,
            )
            candidate_keys = _physical_attribute_keys(
                selected.model_copy(update={"attributes": candidate})
            )
            candidate_validator = DetailedLogicalTopologyContributionValidator(
                contribution_ref=reference,
                source_object=_physical_object_key(selected),
                source_attributes=candidate_keys,
                max_result_bytes=self._detailed_result_limit,
            )
            if len(candidate) <= self._detailed_source_record_limit and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_builder",
                stage_context=candidate_context,
                output_schema=candidate_validator.output_schema(),
            ):
                pending.append(attribute)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One selected Logical Attribute exceeds the bounded detailed stage size."
                )
            raw_batches.append(tuple(pending))
            pending = [attribute]
        if pending:
            raw_batches.append(tuple(pending))

        batches: list[_TopologyBuilderBatch] = []
        batch_count = len(raw_batches)
        for position, raw_attributes in enumerate(raw_batches, start=1):
            reference = base_ref if batch_count == 1 else f"{base_ref}_batch_{position:05d}"
            typed_selected = selected.model_copy(update={"attributes": raw_attributes})
            keys = _physical_attribute_keys(typed_selected)
            stage_context = _topology_builder_context(
                context,
                selected=selected,
                attributes=raw_attributes,
                contribution_ref=reference,
                batch_index=position,
                batch_count=batch_count,
                bounded_support=True,
            )
            final_validator = DetailedLogicalTopologyContributionValidator(
                contribution_ref=reference,
                source_object=_physical_object_key(selected),
                source_attributes=keys,
                max_result_bytes=self._detailed_result_limit,
            )
            if not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_builder",
                stage_context=stage_context,
                output_schema=final_validator.output_schema(),
            ):
                raise InvalidRequestError(
                    "One selected Logical Attribute exceeds the bounded detailed stage size."
                )
            batches.append(
                _TopologyBuilderBatch(
                    contribution_ref=reference,
                    source_attributes=keys,
                    context=stage_context,
                )
            )
        return tuple(batches)

    def _detailed_stage_fits(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        stage_code: str,
        stage_context: JsonValue,
        output_schema: dict[str, JsonValue],
        validation_failures: JsonValue = None,
    ) -> bool:
        if logical_json_bytes(stage_context) > self._detailed_request_limit:
            return False
        resolver_values = _detailed_resolver_values(
            context,
            stage_code=stage_code,
            stage_context=stage_context,
            validation_failures=validation_failures,
        )
        stage = next(
            (candidate for candidate in plan.stages if candidate.stage_code == stage_code),
            None,
        )
        if stage is None:
            raise InvalidRequestError("The frozen agent stage is unavailable.")
        rendered = render_prompt(
            templates=stage.templates,
            variables=stage.variables,
            resolver_values=resolver_values,
        )
        request = AgentExecutionRequest(
            workflow_run_id=plan.workflow_run_id,
            workflow="logical",
            stage=stage_code,
            execution_mode="detailed_coverage",
            selection=plan.selection,
            system_prompt=rendered.system,
            instruction_prompt=rendered.instruction,
            tool_instruction=rendered.tool_instruction,
            context=cast(
                JsonValue,
                {"original_context": stage_context, "repair": None},
            ),
            output_schema=output_schema,
            allowed_tool_names=(),
        )
        return agent_request_envelope_bytes(request) <= self._detailed_request_limit

    def _topology_reconciliation_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        contributions: tuple[DetailedLogicalTopologyContribution, ...],
    ) -> tuple[_TopologyReconciliationBatch, ...]:
        full_context = _topology_reconciliation_context(
            context,
            contributions=contributions,
            batch_index=1,
            batch_count=1,
            bounded_support=False,
        )
        full_validator = DetailedLogicalTopologyReconciliationValidator(
            contributions=contributions,
            max_result_bytes=self._detailed_result_limit,
        )
        full_proposal_count = sum(len(item.proposals) for item in contributions)
        if full_proposal_count <= self._detailed_source_record_limit and self._detailed_stage_fits(
            plan=plan,
            context=context,
            stage_code="topology_reconciler",
            stage_context=full_context,
            output_schema=full_validator.output_schema(),
        ):
            return (
                _TopologyReconciliationBatch(
                    contributions=contributions,
                    context=full_context,
                ),
            )

        raw_batches: list[tuple[DetailedLogicalTopologyContribution, ...]] = []
        pending: list[DetailedLogicalTopologyContribution] = []
        for contribution in contributions:
            candidate = (*pending, contribution)
            candidate_context = _topology_reconciliation_context(
                context,
                contributions=candidate,
                batch_index=99_999,
                batch_count=99_999,
                bounded_support=True,
            )
            candidate_validator = DetailedLogicalTopologyReconciliationValidator(
                contributions=candidate,
                max_result_bytes=self._detailed_result_limit,
            )
            if sum(
                len(item.proposals) for item in candidate
            ) <= self._detailed_source_record_limit and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_reconciler",
                stage_context=candidate_context,
                output_schema=candidate_validator.output_schema(),
            ):
                pending.append(contribution)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Logical topology contribution exceeds the bounded stage size."
                )
            raw_batches.append(tuple(pending))
            pending = [contribution]
        if pending:
            raw_batches.append(tuple(pending))
        batches = tuple(
            _TopologyReconciliationBatch(
                contributions=batch,
                context=_topology_reconciliation_context(
                    context,
                    contributions=batch,
                    batch_index=position,
                    batch_count=len(raw_batches),
                    bounded_support=True,
                ),
            )
            for position, batch in enumerate(raw_batches, start=1)
        )
        if any(
            not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_reconciler",
                stage_context=batch.context,
                output_schema=DetailedLogicalTopologyReconciliationValidator(
                    contributions=batch.contributions,
                    max_result_bytes=self._detailed_result_limit,
                ).output_schema(),
            )
            for batch in batches
        ):
            raise InvalidRequestError(
                "One Logical topology contribution exceeds the bounded stage size."
            )
        return batches

    def _entity_detail_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        entity: DetailedLogicalEntityTopology,
        topology: DetailedLogicalTopologyReconciliation,
        contributions: tuple[DetailedLogicalTopologyContribution, ...],
    ) -> tuple[_EntityDetailBatch, ...]:
        contribution_by_ref = {item.contribution_ref: item for item in contributions}
        relevant_refs = tuple(item.split(".", maxsplit=1)[0] for item in entity.contribution_refs)
        relevant_contributions = tuple(
            contribution_by_ref[item] for item in dict.fromkeys(relevant_refs)
        )
        full_context = _entity_detail_context(
            context,
            entity=entity,
            topology=topology,
            contributions=relevant_contributions,
            batch_index=1,
            batch_count=1,
        )
        full_validator = DetailedLogicalEntityDetailValidator(
            entity=entity,
            topology=topology,
            contributions=contributions,
            max_result_bytes=self._detailed_result_limit,
        )
        source_attribute_count = sum(
            len(proposal.source_attributes)
            for contribution in relevant_contributions
            for proposal_ref, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
            if proposal_ref in entity.contribution_refs
        )
        if (
            source_attribute_count <= self._detailed_source_record_limit
            and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="entity_detail_builder",
                stage_context=full_context,
                output_schema=full_validator.output_schema(),
            )
        ):
            return (
                _EntityDetailBatch(
                    entity=entity,
                    topology=topology,
                    contributions=contributions,
                    context=full_context,
                ),
            )

        submodels = tuple(
            item
            for item in topology.submodels
            if item.canonical_submodel_ref in entity.submodel_refs
        )
        slices: list[
            tuple[DetailedLogicalEntityTopology, tuple[DetailedLogicalTopologyContribution, ...]]
        ] = []
        proposal_by_ref = {
            proposal_ref: (contribution, proposal)
            for contribution in relevant_contributions
            for proposal_ref, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
        }
        for proposal_ref in entity.contribution_refs:
            contribution, proposal = proposal_by_ref[proposal_ref]
            proposal_slices: list[DetailedLogicalTopologyProposal] = [proposal]
            scoped_entity = entity.model_copy(update={"contribution_refs": (proposal_ref,)})
            scoped_contribution = contribution.model_copy(update={"proposals": (proposal,)})
            scoped_topology = DetailedLogicalTopologyReconciliation(
                submodels=submodels,
                entities=(scoped_entity,),
                discarded_contribution_refs=(),
            )
            provisional_context = _entity_detail_context(
                context,
                entity=scoped_entity,
                topology=scoped_topology,
                contributions=(scoped_contribution,),
                batch_index=99_999,
                batch_count=99_999,
            )
            provisional_validator = DetailedLogicalEntityDetailValidator(
                entity=scoped_entity,
                topology=scoped_topology,
                contributions=(scoped_contribution,),
                max_result_bytes=self._detailed_result_limit,
            )
            if len(
                proposal.source_attributes
            ) > self._detailed_source_record_limit or not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="entity_detail_builder",
                stage_context=provisional_context,
                output_schema=provisional_validator.output_schema(),
            ):
                proposal_slices = []
                pending: list[PhysicalAttributeKey] = []
                for source_attribute in proposal.source_attributes:
                    candidate_attributes = (*pending, source_attribute)
                    candidate_proposal = proposal.model_copy(
                        update={"source_attributes": candidate_attributes}
                    )
                    candidate_contribution = contribution.model_copy(
                        update={"proposals": (candidate_proposal,)}
                    )
                    candidate_context = _entity_detail_context(
                        context,
                        entity=scoped_entity,
                        topology=scoped_topology,
                        contributions=(candidate_contribution,),
                        batch_index=99_999,
                        batch_count=99_999,
                    )
                    candidate_validator = DetailedLogicalEntityDetailValidator(
                        entity=scoped_entity,
                        topology=scoped_topology,
                        contributions=(candidate_contribution,),
                        max_result_bytes=self._detailed_result_limit,
                    )
                    if len(
                        candidate_attributes
                    ) <= self._detailed_source_record_limit and self._detailed_stage_fits(
                        plan=plan,
                        context=context,
                        stage_code="entity_detail_builder",
                        stage_context=candidate_context,
                        output_schema=candidate_validator.output_schema(),
                    ):
                        pending.append(source_attribute)
                        continue
                    if not pending:
                        raise InvalidRequestError(
                            "One authoritative Logical source Attribute exceeds the bounded "
                            "Entity detail stage size."
                        )
                    proposal_slices.append(
                        proposal.model_copy(update={"source_attributes": tuple(pending)})
                    )
                    pending = [source_attribute]
                if pending:
                    proposal_slices.append(
                        proposal.model_copy(update={"source_attributes": tuple(pending)})
                    )
            slices.extend(
                (
                    scoped_entity,
                    (contribution.model_copy(update={"proposals": (item,)}),),
                )
                for item in proposal_slices
            )

        batches: list[_EntityDetailBatch] = []
        batch_count = len(slices)
        for position, (scoped_entity, scoped_contributions) in enumerate(
            slices,
            start=1,
        ):
            scoped_topology = DetailedLogicalTopologyReconciliation(
                submodels=submodels,
                entities=(scoped_entity,),
                discarded_contribution_refs=(),
            )
            stage_context = _entity_detail_context(
                context,
                entity=scoped_entity,
                topology=scoped_topology,
                contributions=scoped_contributions,
                batch_index=position,
                batch_count=batch_count,
            )
            scoped_validator = DetailedLogicalEntityDetailValidator(
                entity=scoped_entity,
                topology=scoped_topology,
                contributions=scoped_contributions,
                max_result_bytes=self._detailed_result_limit,
            )
            if not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="entity_detail_builder",
                stage_context=stage_context,
                output_schema=scoped_validator.output_schema(),
            ):
                raise InvalidRequestError(
                    "One authoritative Logical source Attribute exceeds the bounded Entity "
                    "detail stage size."
                )
            batches.append(
                _EntityDetailBatch(
                    entity=scoped_entity,
                    topology=scoped_topology,
                    contributions=scoped_contributions,
                    context=stage_context,
                )
            )
        return tuple(batches)

    def _reconciliation_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        topology: DetailedLogicalTopologyReconciliation,
        entity_details: tuple[DetailedLogicalEntityDetail, ...],
        relationship_ledger: DetailedLogicalRelationshipSignalLedger,
        applied_record_refs: tuple[str, ...],
        validation_failures: JsonValue,
    ) -> tuple[_ReconciliationBatch, ...]:
        full_context = _reconciliation_context(
            context,
            topology=topology,
            entity_details=entity_details,
            relationship_signals=relationship_ledger.signals,
            applied_record_refs=applied_record_refs,
            batch_index=1,
            batch_count=1,
            bounded_support=False,
        )
        full_validator = DetailedLogicalReconciliationValidator(
            topology=topology,
            entity_details=entity_details,
            relationship_signal_refs=relationship_ledger.signal_refs,
            applied_record_refs=applied_record_refs,
            max_result_bytes=self._detailed_result_limit,
        )
        if (
            _reconciliation_baseline_bytes(
                topology=topology,
                entity_details=entity_details,
                relationship_signal_refs=relationship_ledger.signal_refs,
                applied_record_refs=applied_record_refs,
            )
            <= self._detailed_result_limit
            and len(relationship_ledger.signals) <= self._detailed_source_record_limit
            and len(applied_record_refs) <= self._detailed_source_record_limit
            and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="whole_model_reconciliation",
                stage_context=full_context,
                output_schema=full_validator.output_schema(),
                validation_failures=validation_failures,
            )
        ):
            return (
                _ReconciliationBatch(
                    topology=topology,
                    entity_details=entity_details,
                    relationship_signal_refs=relationship_ledger.signal_refs,
                    applied_record_refs=applied_record_refs,
                    context=full_context,
                ),
            )

        batch_inputs: list[
            tuple[
                DetailedLogicalTopologyReconciliation,
                tuple[DetailedLogicalEntityDetail, ...],
                tuple[DetailedLogicalRelationshipSignal, ...],
                tuple[str, ...],
            ]
        ] = []
        topology_entity_by_ref = {item.canonical_entity_ref: item for item in topology.entities}
        for detail in entity_details:
            topology_entity = topology_entity_by_ref[detail.canonical_entity_ref]
            scoped_submodels = tuple(
                item
                for item in topology.submodels
                if item.canonical_submodel_ref in topology_entity.submodel_refs
            )
            scoped_topology = DetailedLogicalTopologyReconciliation(
                submodels=scoped_submodels,
                entities=(topology_entity,),
                discarded_contribution_refs=(),
            )
            pending: list[LogicalAttributeRecord] = []
            for attribute in detail.attributes:
                candidate_attributes = (*pending, attribute)
                candidate_detail = detail.model_copy(update={"attributes": candidate_attributes})
                candidate_context = _reconciliation_context(
                    context,
                    topology=scoped_topology,
                    entity_details=(candidate_detail,),
                    relationship_signals=(),
                    applied_record_refs=(),
                    batch_index=99_999,
                    batch_count=99_999,
                    bounded_support=True,
                )
                candidate_validator = DetailedLogicalReconciliationValidator(
                    topology=scoped_topology,
                    entity_details=(candidate_detail,),
                    relationship_signal_refs=(),
                    applied_record_refs=(),
                    max_result_bytes=self._detailed_result_limit,
                    require_exact_base_records=True,
                )
                if _reconciliation_baseline_bytes(
                    topology=scoped_topology,
                    entity_details=(candidate_detail,),
                    relationship_signal_refs=(),
                    applied_record_refs=(),
                ) <= self._detailed_result_limit and self._detailed_stage_fits(
                    plan=plan,
                    context=context,
                    stage_code="whole_model_reconciliation",
                    stage_context=candidate_context,
                    output_schema=candidate_validator.output_schema(),
                    validation_failures=validation_failures,
                ):
                    pending.append(attribute)
                    continue
                if not pending:
                    raise InvalidRequestError(
                        "One authoritative Logical Attribute exceeds the bounded whole-model "
                        "stage size."
                    )
                batch_inputs.append(
                    (
                        scoped_topology,
                        (detail.model_copy(update={"attributes": tuple(pending)}),),
                        (),
                        (),
                    )
                )
                pending = [attribute]
            if pending:
                batch_inputs.append(
                    (
                        scoped_topology,
                        (detail.model_copy(update={"attributes": tuple(pending)}),),
                        (),
                        (),
                    )
                )

        pending_signals: list[DetailedLogicalRelationshipSignal] = []
        empty_topology = DetailedLogicalTopologyReconciliation(
            submodels=(),
            entities=(),
            discarded_contribution_refs=(),
        )
        for signal in relationship_ledger.signals:
            candidate_signals = (*pending_signals, signal)
            candidate_context = _reconciliation_context(
                context,
                topology=empty_topology,
                entity_details=(),
                relationship_signals=candidate_signals,
                applied_record_refs=(),
                batch_index=99_999,
                batch_count=99_999,
                bounded_support=True,
            )
            candidate_validator = DetailedLogicalReconciliationValidator(
                topology=empty_topology,
                entity_details=(),
                relationship_signal_refs=tuple(item.signal_ref for item in candidate_signals),
                applied_record_refs=(),
                max_result_bytes=self._detailed_result_limit,
                require_exact_base_records=True,
            )
            signal_values = cast(
                JsonValue,
                [item.model_dump(mode="json") for item in candidate_signals],
            )
            if (
                len(candidate_signals) <= self._detailed_source_record_limit
                and logical_json_bytes(signal_values) <= self._detailed_result_limit
                and self._detailed_stage_fits(
                    plan=plan,
                    context=context,
                    stage_code="whole_model_reconciliation",
                    stage_context=candidate_context,
                    output_schema=candidate_validator.output_schema(),
                    validation_failures=validation_failures,
                )
            ):
                pending_signals.append(signal)
                continue
            if not pending_signals:
                raise InvalidRequestError(
                    "One authoritative Logical relationship signal exceeds the bounded "
                    "whole-model stage size."
                )
            batch_inputs.append((empty_topology, (), tuple(pending_signals), ()))
            pending_signals = [signal]
        if pending_signals:
            batch_inputs.append((empty_topology, (), tuple(pending_signals), ()))

        pending_refs: list[str] = []
        for applied_ref in applied_record_refs:
            candidate_refs = (*pending_refs, applied_ref)
            candidate_context = _reconciliation_context(
                context,
                topology=empty_topology,
                entity_details=(),
                relationship_signals=(),
                applied_record_refs=candidate_refs,
                batch_index=99_999,
                batch_count=99_999,
                bounded_support=True,
            )
            candidate_validator = DetailedLogicalReconciliationValidator(
                topology=empty_topology,
                entity_details=(),
                relationship_signal_refs=(),
                applied_record_refs=candidate_refs,
                max_result_bytes=self._detailed_result_limit,
                require_exact_base_records=True,
            )
            if len(
                candidate_refs
            ) <= self._detailed_source_record_limit and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="whole_model_reconciliation",
                stage_context=candidate_context,
                output_schema=candidate_validator.output_schema(),
                validation_failures=validation_failures,
            ):
                pending_refs.append(applied_ref)
                continue
            if not pending_refs:
                raise InvalidRequestError(
                    "One authoritative applied Logical reference exceeds the bounded "
                    "whole-model stage size."
                )
            batch_inputs.append((empty_topology, (), (), tuple(pending_refs)))
            pending_refs = [applied_ref]
        if pending_refs:
            batch_inputs.append((empty_topology, (), (), tuple(pending_refs)))
        if not batch_inputs:
            batch_inputs.append((empty_topology, (), (), ()))

        batches: list[_ReconciliationBatch] = []
        batch_count = len(batch_inputs)
        for position, (
            scoped_topology,
            scoped_details,
            scoped_signals,
            scoped_applied_refs,
        ) in enumerate(batch_inputs, start=1):
            stage_context = _reconciliation_context(
                context,
                topology=scoped_topology,
                entity_details=scoped_details,
                relationship_signals=scoped_signals,
                applied_record_refs=scoped_applied_refs,
                batch_index=position,
                batch_count=batch_count,
                bounded_support=True,
            )
            scoped_validator = DetailedLogicalReconciliationValidator(
                topology=scoped_topology,
                entity_details=scoped_details,
                relationship_signal_refs=tuple(item.signal_ref for item in scoped_signals),
                applied_record_refs=scoped_applied_refs,
                max_result_bytes=self._detailed_result_limit,
                require_exact_base_records=True,
            )
            if not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="whole_model_reconciliation",
                stage_context=stage_context,
                output_schema=scoped_validator.output_schema(),
                validation_failures=validation_failures,
            ):
                raise InvalidRequestError(
                    "A Logical reconciliation batch exceeds the bounded whole-model stage size."
                )
            batches.append(
                _ReconciliationBatch(
                    topology=scoped_topology,
                    entity_details=scoped_details,
                    relationship_signal_refs=tuple(item.signal_ref for item in scoped_signals),
                    applied_record_refs=scoped_applied_refs,
                    context=stage_context,
                )
            )
        return tuple(batches)

    def _validation_packages(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        candidate: DetailedLogicalReconciliationCandidate,
    ) -> tuple[DetailedLogicalValidationPackage, ...]:
        records = logical_validation_records(candidate)
        raw_packages: list[tuple[DetailedLogicalValidationRecord, ...]] = []
        pending: list[DetailedLogicalValidationRecord] = []
        for record in records:
            candidate_records = (*pending, record)
            package = _logical_validation_package(
                package_ref="validation_99999",
                records=candidate_records,
            )
            worker_context = _validation_worker_context(context, package=package)
            worker_validator = DetailedLogicalValidationWorkerValidator(
                package=package,
                max_result_bytes=self._detailed_result_limit,
            )
            if len(
                candidate_records
            ) <= self._detailed_policy.validation_package_size and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_worker",
                stage_context=worker_context,
                output_schema=worker_validator.output_schema(),
            ):
                pending.append(record)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One authoritative Logical validation record exceeds the bounded worker "
                    "stage size."
                )
            raw_packages.append(tuple(pending))
            pending = [record]
        if pending:
            raw_packages.append(tuple(pending))
        if not raw_packages or len(raw_packages) > self._detailed_policy.max_validation_packages:
            raise InvalidRequestError("Logical validation exceeds its configured package limit.")
        packages = tuple(
            _logical_validation_package(
                package_ref=f"validation_{position:05d}",
                records=raw_records,
            )
            for position, raw_records in enumerate(raw_packages, start=1)
        )
        if any(
            not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_worker",
                stage_context=_validation_worker_context(context, package=package),
                output_schema=DetailedLogicalValidationWorkerValidator(
                    package=package,
                    max_result_bytes=self._detailed_result_limit,
                ).output_schema(),
            )
            for package in packages
        ):
            raise InvalidRequestError(
                "One authoritative Logical validation record exceeds the bounded worker stage size."
            )
        return packages

    def _validation_lead_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        worker_results: tuple[DetailedLogicalValidationWorkerResult, ...],
    ) -> tuple[tuple[DetailedLogicalValidationWorkerResult, ...], ...]:
        full_context = _validation_lead_context(context, worker_results=worker_results)
        full_validator = DetailedLogicalValidationLeadValidator(
            worker_results=worker_results,
            max_result_bytes=self._detailed_result_limit,
        )
        if self._detailed_stage_fits(
            plan=plan,
            context=context,
            stage_code="validator_lead",
            stage_context=full_context,
            output_schema=full_validator.output_schema(),
        ):
            return (worker_results,)
        batches: list[tuple[DetailedLogicalValidationWorkerResult, ...]] = []
        pending: list[DetailedLogicalValidationWorkerResult] = []
        for result in worker_results:
            candidate = (*pending, result)
            candidate_context = _validation_lead_context(
                context,
                worker_results=candidate,
            )
            candidate_validator = DetailedLogicalValidationLeadValidator(
                worker_results=candidate,
                max_result_bytes=self._detailed_result_limit,
            )
            if self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_lead",
                stage_context=candidate_context,
                output_schema=candidate_validator.output_schema(),
            ):
                pending.append(result)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Logical validation result exceeds the bounded lead stage size."
                )
            batches.append(tuple(pending))
            pending = [result]
        if pending:
            batches.append(tuple(pending))
        return tuple(batches)

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
    validation_failures: JsonValue = None,
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


def _bounded_validation_failures(
    failures: Sequence[Mapping[str, object]],
) -> JsonValue:
    raw = cast(JsonValue, [dict(item) for item in failures])
    if logical_json_bytes(raw) <= 8_192:
        return raw
    projected: list[JsonValue] = []
    for order, failure in enumerate(failures, start=1):
        record_refs = failure.get("record_refs")
        refs = (
            [item for item in cast(Sequence[object], record_refs) if isinstance(item, str)]
            if isinstance(record_refs, (list, tuple))
            else []
        )
        record = cast(JsonValue, dict(failure))
        projected.append(
            cast(
                JsonValue,
                {
                    "finding_order": order,
                    "finding_ref": failure.get("finding_ref"),
                    "severity": failure.get("severity"),
                    "code": failure.get("code"),
                    "message": _supporting_value_projection(
                        cast(JsonValue, failure.get("message")),
                        maximum_text_bytes=512,
                    ),
                    "record_ref_count": len(refs),
                    "ordered_record_ref_digest": logical_json_digest(cast(JsonValue, refs)),
                    "record_refs": refs[:10],
                    "record_refs_complete": len(refs) <= 10,
                    "canonical_utf8_bytes": logical_json_bytes(record),
                    "canonical_sha256": logical_json_digest(record),
                },
            )
        )
    manifest = cast(
        JsonValue,
        {
            "projection_contract": "identity_digest_bounded_validation_failures_v1",
            "finding_count": len(failures),
            "ordered_findings_sha256": logical_json_digest(raw),
            "findings": projected,
        },
    )
    if logical_json_bytes(manifest) <= 32_768:
        return manifest
    return cast(
        JsonValue,
        {
            "projection_contract": "digest_only_validation_failures_v1",
            "finding_count": len(failures),
            "ordered_findings_sha256": logical_json_digest(raw),
            "first_finding_ref": failures[0].get("finding_ref") if failures else None,
            "last_finding_ref": failures[-1].get("finding_ref") if failures else None,
        },
    )


def _detailed_model_context(context: AgentContextBundle) -> JsonValue:
    details = context.context.model_details
    return cast(
        JsonValue,
        {
            "model_id": context.context.model_id,
            "model_name": context.context.model_name,
            "model_revision": context.context.model_revision,
            "model_description": details.model_description,
            "silver_naming_instructions": _supporting_value_projection(
                details.silver_model_naming_instructions,
                maximum_text_bytes=2_048,
            ),
            "silver_audit_template": _supporting_value_projection(
                cast(JsonValue, details.silver_model_audit_columns_template),
                maximum_text_bytes=0,
            ),
        },
    )


def _applied_logical_context(context: AgentContextBundle) -> JsonValue:
    section = context.context.applied.logical
    return None if section is None else cast(JsonValue, section.model_dump(mode="json"))


def _topology_builder_context(
    context: AgentContextBundle,
    *,
    selected: SelectedObjectContext,
    attributes: Sequence[AttributeRecord],
    contribution_ref: str,
    batch_index: int,
    batch_count: int,
    bounded_support: bool,
) -> JsonValue:
    selected_slice = selected.model_copy(update={"attributes": tuple(attributes)})
    profiles = tuple(
        item for item in context.context.profiles if _profile_matches_selected(item, selected)
    )
    analysis = tuple(
        item
        for item in context.context.analysis_relationships
        if _analysis_matches_selected(item, selected)
    )
    if not bounded_support:
        assertions: JsonValue = cast(
            JsonValue,
            context.context.assertion.model_dump(mode="json"),
        )
        profile_context: JsonValue = cast(
            JsonValue,
            [item.model_dump(mode="json") for item in profiles],
        )
        analysis_context: JsonValue = cast(
            JsonValue,
            [item.model_dump(mode="json") for item in analysis],
        )
        applied_context = _applied_logical_context(context)
    else:
        assertions = cast(
            JsonValue,
            {
                "projection_contract": "identity_digest_bounded_semantics_v1",
                "documents": _supporting_records_projection(
                    context.context.assertion.documents,
                    identity_fields=("modeling_assertion_document_name",),
                    semantic_fields=(
                        "modeling_assertion_document_type",
                        "modeling_assertion_document_description",
                        "tenant_code",
                        "system_code",
                        "is_active",
                    ),
                    maximum_bytes=1_536,
                ),
                "records": _supporting_records_projection(
                    context.context.assertion.records,
                    identity_fields=(
                        "modeling_assertion_record_key",
                        "modeling_assertion_document_name",
                    ),
                    semantic_fields=(
                        "modeling_assertion_record_type",
                        "modeling_assertion_text",
                        "modeling_assertion_applicable_layers",
                        "modeling_assertion_confidence",
                        "modeling_assertion_record_status",
                        "modeling_assertion_record_is_locked",
                    ),
                    maximum_bytes=4_096,
                ),
            },
        )
        profile_context = _supporting_records_projection(
            profiles,
            identity_fields=(
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
                "attribute_name",
            ),
            semantic_fields=(),
            maximum_bytes=1_536,
        )
        analysis_context = _supporting_records_projection(
            analysis,
            identity_fields=(
                "from_tenant_code",
                "from_system_code",
                "from_connection_code",
                "from_object_schema",
                "from_object_name",
                "from_attribute_name",
                "to_tenant_code",
                "to_system_code",
                "to_connection_code",
                "to_object_schema",
                "to_object_name",
                "to_attribute_name",
            ),
            semantic_fields=(
                "relationship_kind",
                "relationship_confidence",
                "relationship_basis",
            ),
            maximum_bytes=1_536,
        )
        applied = context.context.applied.logical
        applied_records: tuple[BaseModel, ...] = ()
        if applied is not None:
            applied_records = (
                *applied.submodels,
                *applied.entities,
                *applied.attributes,
                *applied.relationships,
            )
        applied_context = _supporting_records_projection(
            applied_records,
            identity_fields=(
                "logical_submodel_name",
                "logical_entity_name",
                "logical_attribute_name",
                "logical_relationship_name",
            ),
            semantic_fields=(),
            maximum_bytes=1_536,
        )
    attribute_values = cast(
        list[JsonValue],
        [item.model_dump(mode="json") for item in attributes],
    )
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "contribution_ref": contribution_ref,
            "batch_manifest": {
                "batch_index": batch_index,
                "batch_count": batch_count,
                "record_count": len(attribute_values),
                "ordered_record_digest": logical_json_digest(cast(JsonValue, attribute_values)),
                "records_are_lossless": True,
                "supporting_evidence_may_be_projected": bounded_support,
            },
            "selected_object": selected_slice.model_dump(mode="json"),
            "profiles": profile_context,
            "analysis_relationships": analysis_context,
            "assertions": assertions,
            "applied_logical": applied_context,
        },
    )


def _topology_reconciliation_context(
    context: AgentContextBundle,
    *,
    contributions: Sequence[DetailedLogicalTopologyContribution],
    batch_index: int,
    batch_count: int,
    bounded_support: bool,
) -> JsonValue:
    contribution_values = cast(
        list[JsonValue],
        [item.model_dump(mode="json") for item in contributions],
    )
    if bounded_support:
        applied = context.context.applied.logical
        applied_records: tuple[BaseModel, ...] = ()
        if applied is not None:
            applied_records = (
                *applied.submodels,
                *applied.entities,
                *applied.attributes,
                *applied.relationships,
            )
        applied_context = _supporting_records_projection(
            applied_records,
            identity_fields=(
                "logical_submodel_name",
                "logical_entity_name",
                "logical_attribute_name",
                "logical_relationship_name",
            ),
            semantic_fields=(),
            maximum_bytes=1_536,
        )
    else:
        applied_context = _applied_logical_context(context)
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "batch_manifest": {
                "batch_index": batch_index,
                "batch_count": batch_count,
                "record_count": len(contribution_values),
                "proposal_count": sum(len(item.proposals) for item in contributions),
                "ordered_record_digest": logical_json_digest(cast(JsonValue, contribution_values)),
                "records_are_lossless": True,
                "supporting_evidence_may_be_projected": bounded_support,
            },
            "contributions": contribution_values,
            "applied_logical": applied_context,
        },
    )


def _entity_detail_context(
    context: AgentContextBundle,
    *,
    entity: DetailedLogicalEntityTopology,
    topology: DetailedLogicalTopologyReconciliation,
    contributions: Sequence[DetailedLogicalTopologyContribution],
    batch_index: int,
    batch_count: int,
) -> JsonValue:
    selected_by_object = {
        _selected_identity(item): item for item in context.context.selected_objects
    }
    selected_slices: list[JsonValue] = []
    for contribution in contributions:
        object_identity = _normalized_object_identity(
            contribution.source_object.tenant_code,
            contribution.source_object.system_code,
            contribution.source_object.connection_code,
            contribution.source_object.object_schema,
            contribution.source_object.object_name,
        )
        selected = selected_by_object.get(object_identity)
        if selected is None:
            raise InvalidRequestError(
                "A Logical topology contribution has no authoritative selected Object."
            )
        expected = {
            tuple(_physical_attribute_key_value(item))
            for proposal in contribution.proposals
            for item in proposal.source_attributes
        }
        attributes = tuple(
            item
            for item in selected.attributes
            if tuple(_physical_attribute_key_value_from_record(item)) in expected
        )
        if len(attributes) != len(expected):
            raise InvalidRequestError(
                "A Logical topology contribution lost authoritative Attribute evidence."
            )
        selected_slices.append(
            cast(
                JsonValue,
                selected.model_copy(update={"attributes": attributes}).model_dump(mode="json"),
            )
        )
    contribution_values = cast(
        list[JsonValue],
        [item.model_dump(mode="json") for item in contributions],
    )
    selected_values = selected_slices
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "batch_manifest": {
                "batch_index": batch_index,
                "batch_count": batch_count,
                "contribution_count": len(contribution_values),
                "ordered_contribution_digest": logical_json_digest(
                    cast(JsonValue, contribution_values)
                ),
                "selected_object_count": len(selected_values),
                "ordered_selected_object_digest": logical_json_digest(
                    cast(JsonValue, selected_values)
                ),
                "authoritative_records_are_lossless": True,
            },
            "topology": topology.model_dump(mode="json"),
            "entity": entity.model_dump(mode="json"),
            "contributions": contribution_values,
            "selected_objects": selected_values,
        },
    )


def _reconciliation_baseline_bytes(
    *,
    topology: DetailedLogicalTopologyReconciliation,
    entity_details: Sequence[DetailedLogicalEntityDetail],
    relationship_signal_refs: Sequence[str],
    applied_record_refs: Sequence[str],
) -> int:
    baseline = DetailedLogicalReconciliationCandidate(
        submodels=tuple(item.submodel for item in topology.submodels),
        entities=tuple(item.entity for item in entity_details),
        attributes=tuple(attribute for item in entity_details for attribute in item.attributes),
        relationships=(),
        reviewed_submodel_refs=tuple(item.canonical_submodel_ref for item in topology.submodels),
        reviewed_entity_refs=tuple(item.canonical_entity_ref for item in entity_details),
        reviewed_relationship_signal_refs=tuple(relationship_signal_refs),
        reviewed_applied_record_refs=tuple(applied_record_refs),
    )
    return logical_json_bytes(cast(JsonValue, baseline.model_dump(mode="json")))


def _reconciliation_context(
    context: AgentContextBundle,
    *,
    topology: DetailedLogicalTopologyReconciliation,
    entity_details: Sequence[DetailedLogicalEntityDetail],
    relationship_signals: Sequence[DetailedLogicalRelationshipSignal],
    applied_record_refs: Sequence[str],
    batch_index: int,
    batch_count: int,
    bounded_support: bool,
) -> JsonValue:
    detail_values = cast(
        list[JsonValue],
        [item.model_dump(mode="json") for item in entity_details],
    )
    signal_values = cast(
        list[JsonValue],
        [item.model_dump(mode="json") for item in relationship_signals],
    )
    applied_ref_values = list(applied_record_refs)
    if bounded_support:
        applied_by_ref = _applied_logical_records_by_ref(context)
        applied_context = _supporting_records_projection(
            tuple(applied_by_ref[item] for item in applied_record_refs),
            identity_fields=(
                "logical_submodel_name",
                "logical_entity_name",
                "logical_attribute_name",
                "logical_relationship_name",
            ),
            semantic_fields=(
                "logical_submodel_definition",
                "logical_entity_definition",
                "logical_attribute_definition",
                "logical_relationship_definition",
            ),
            maximum_bytes=4_096,
        )
    else:
        applied_context = _applied_logical_context(context)
    topology_value = cast(JsonValue, topology.model_dump(mode="json"))
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "batch_manifest": {
                "batch_index": batch_index,
                "batch_count": batch_count,
                "topology_digest": logical_json_digest(topology_value),
                "entity_detail_count": len(detail_values),
                "ordered_entity_detail_digest": logical_json_digest(cast(JsonValue, detail_values)),
                "relationship_signal_count": len(signal_values),
                "ordered_relationship_signal_digest": logical_json_digest(
                    cast(JsonValue, signal_values)
                ),
                "applied_record_ref_count": len(applied_ref_values),
                "ordered_applied_record_ref_digest": logical_json_digest(
                    cast(JsonValue, applied_ref_values)
                ),
                "authoritative_records_are_lossless": True,
                "supporting_applied_records_may_be_projected": bounded_support,
            },
            "topology": topology_value,
            "entity_details": detail_values,
            "relationship_signal_ledger": {
                "schema_version": "1.0",
                "signals": signal_values,
            },
            "applied_logical": applied_context,
            "required_applied_record_refs": applied_ref_values,
        },
    )


def _applied_logical_records_by_ref(
    context: AgentContextBundle,
) -> dict[str, BaseModel]:
    section = context.context.applied.logical
    if section is None:
        return {}
    records: dict[str, BaseModel] = {}
    for item in section.submodels:
        records[f"submodel:{normalize_model_key_value(item.logical_submodel_name)}"] = item
    for item in section.entities:
        records[f"entity:{normalize_model_key_value(item.logical_entity_name)}"] = item
    for item in section.attributes:
        records[
            "attribute:"
            f"{normalize_model_key_value(item.logical_entity_name)}|"
            f"{normalize_model_key_value(item.logical_attribute_name)}"
        ] = item
    for item in section.relationships:
        records[
            "relationship:"
            f"{normalize_model_key_value(item.from_logical_entity_name)}|"
            f"{normalize_model_key_value(item.from_logical_attribute_name)}|"
            f"{normalize_model_key_value(item.to_logical_entity_name)}|"
            f"{normalize_model_key_value(item.to_logical_attribute_name)}|"
            f"{normalize_model_key_value(item.logical_relationship_name)}"
        ] = item
    if len(records) != (
        len(section.submodels)
        + len(section.entities)
        + len(section.attributes)
        + len(section.relationships)
    ):
        raise InvalidRequestError("Applied Logical record identities must be unique.")
    return records


def _logical_validation_package(
    *,
    package_ref: str,
    records: Sequence[DetailedLogicalValidationRecord],
) -> DetailedLogicalValidationPackage:
    return DetailedLogicalValidationPackage(
        package_ref=package_ref,
        records=tuple(records),
        record_digests=tuple(
            logical_json_digest(item.record.model_dump(mode="json")) for item in records
        ),
    )


def _validation_worker_context(
    context: AgentContextBundle,
    *,
    package: DetailedLogicalValidationPackage,
) -> JsonValue:
    package_value = cast(JsonValue, package.model_dump(mode="json"))
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "package_manifest": {
                "package_ref": package.package_ref,
                "record_count": len(package.records),
                "record_refs": list(package.record_refs),
                "record_digests": list(package.record_digests),
                "canonical_package_sha256": logical_json_digest(package_value),
                "records_are_lossless": True,
            },
            "validation_package": package_value,
        },
    )


def _validation_lead_context(
    context: AgentContextBundle,
    *,
    worker_results: Sequence[DetailedLogicalValidationWorkerResult],
) -> JsonValue:
    values = cast(
        list[JsonValue],
        [item.model_dump(mode="json") for item in worker_results],
    )
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "worker_result_manifest": {
                "result_count": len(values),
                "package_refs": [item.package_ref for item in worker_results],
                "ordered_result_digest": logical_json_digest(cast(JsonValue, values)),
                "results_are_lossless": True,
            },
            "worker_results": values,
        },
    )


def _merge_validation_leads(
    *,
    worker_results: tuple[DetailedLogicalValidationWorkerResult, ...],
    partitions: tuple[DetailedLogicalValidationLead, ...],
) -> DetailedLogicalValidationLead:
    finding_refs = tuple(
        finding.finding_ref for result in worker_results for finding in result.findings
    )
    blocking_refs = tuple(
        finding.finding_ref
        for result in worker_results
        for finding in result.findings
        if finding.severity == "error"
    )
    briefs = tuple(item.repair_brief for item in partitions if item.repair_brief is not None)
    repair_brief: str | None = None
    if blocking_refs:
        combined = "\n".join(briefs)
        repair_brief = (
            combined
            if combined and len(combined) <= 32_768
            else (
                f"Repair {len(blocking_refs)} blocking Logical validation findings; "
                "use the exact blocking finding references."
            )
        )
    merged = DetailedLogicalValidationLead(
        reviewed_package_refs=tuple(item.package_ref for item in worker_results),
        reviewed_finding_refs=finding_refs,
        blocking_finding_refs=blocking_refs,
        repair_brief=repair_brief,
    )
    return DetailedLogicalValidationLeadValidator(
        worker_results=worker_results,
        max_result_bytes=None,
    ).parse_validated(cast(JsonValue, merged.model_dump(mode="json")))


def _supporting_records_projection(
    records: Sequence[BaseModel],
    *,
    identity_fields: tuple[str, ...],
    semantic_fields: tuple[str, ...],
    maximum_bytes: int,
) -> JsonValue:
    raw_records = [cast(dict[str, JsonValue], record.model_dump(mode="json")) for record in records]
    section_digest = logical_json_digest(cast(JsonValue, raw_records))
    base: dict[str, JsonValue] = {
        "schema_version": "1.0",
        "record_count": len(raw_records),
        "ordered_records_sha256": section_digest,
        "projection_complete": True,
        "records": [],
    }
    accepted: list[JsonValue] = []
    for order, raw in enumerate(raw_records, start=1):
        projection = _supporting_record_projection(
            raw,
            order=order,
            identity_fields=identity_fields,
            semantic_fields=semantic_fields,
        )
        base["records"] = [*accepted, projection]
        if logical_json_bytes(cast(JsonValue, base)) <= maximum_bytes:
            accepted.append(projection)
            continue
        base["projection_complete"] = False
        base["records"] = accepted
        base["omitted_record_count"] = len(raw_records) - len(accepted)
        base["omitted_order_start"] = len(accepted) + 1
        base["omitted_order_end"] = len(raw_records)
        base["omitted_ordered_records_sha256"] = logical_json_digest(
            cast(JsonValue, raw_records[len(accepted) :])
        )
        break
    if logical_json_bytes(cast(JsonValue, base)) > maximum_bytes:
        base["records"] = []
        base["projection_complete"] = not raw_records
        base["omitted_record_count"] = len(raw_records)
        base["omitted_order_start"] = 1 if raw_records else None
        base["omitted_order_end"] = len(raw_records) if raw_records else None
        base["omitted_ordered_records_sha256"] = section_digest
    if logical_json_bytes(cast(JsonValue, base)) > maximum_bytes:
        raise InvalidRequestError("A supporting Logical evidence manifest is too large.")
    return cast(JsonValue, base)


def _supporting_record_projection(
    record: dict[str, JsonValue],
    *,
    order: int,
    identity_fields: tuple[str, ...],
    semantic_fields: tuple[str, ...],
) -> JsonValue:
    byte_count = logical_json_bytes(cast(JsonValue, record))
    digest = logical_json_digest(cast(JsonValue, record))
    identity = {name: record[name] for name in identity_fields if name in record}
    if byte_count <= 2_048:
        return cast(
            JsonValue,
            {
                "record_order": order,
                "record_identity": identity,
                "canonical_utf8_bytes": byte_count,
                "canonical_sha256": digest,
                "projection_kind": "full_record",
                "record": record,
            },
        )
    semantics = {
        name: _supporting_value_projection(record.get(name), maximum_text_bytes=1_024)
        for name in semantic_fields
        if name in record
    }
    included = set(identity) | set(semantics)
    omitted = [
        {
            "field": name,
            "canonical_utf8_bytes": logical_json_bytes(value),
            "canonical_sha256": logical_json_digest(value),
        }
        for name, value in record.items()
        if name not in included
    ]
    return cast(
        JsonValue,
        {
            "record_order": order,
            "record_identity": identity,
            "canonical_utf8_bytes": byte_count,
            "canonical_sha256": digest,
            "projection_kind": "bounded_semantic_projection",
            "semantic_fields": semantics,
            "included_fields": list(semantics),
            "included_canonical_utf8_bytes": logical_json_bytes(cast(JsonValue, semantics)),
            "omitted_fields": omitted,
        },
    )


def _supporting_value_projection(
    value: JsonValue,
    *,
    maximum_text_bytes: int,
) -> JsonValue:
    if not isinstance(value, str) or len(value.encode("utf-8")) <= maximum_text_bytes:
        if maximum_text_bytes == 0 and value is not None:
            return cast(
                JsonValue,
                {
                    "projection_kind": "digest_only",
                    "canonical_utf8_bytes": logical_json_bytes(value),
                    "canonical_sha256": logical_json_digest(value),
                },
            )
        return value
    encoded = value.encode("utf-8")
    prefix = encoded[:maximum_text_bytes]
    while prefix:
        try:
            decoded = prefix.decode("utf-8")
            break
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    else:
        decoded = ""
    return cast(
        JsonValue,
        {
            "projection_kind": "utf8_prefix",
            "value_prefix": decoded,
            "original_utf8_bytes": len(encoded),
            "included_utf8_bytes": len(prefix),
            "canonical_sha256": logical_json_digest(value),
            "omitted_suffix": True,
        },
    )


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


def _physical_attribute_key_value(
    item: PhysicalAttributeKey,
) -> tuple[str, str, str, str, str, str]:
    return (
        *_normalized_object_identity(
            item.tenant_code,
            item.system_code,
            item.connection_code,
            item.object_schema,
            item.object_name,
        ),
        normalize_model_key_value(item.attribute_name),
    )


def _physical_attribute_key_value_from_record(
    item: AttributeRecord,
) -> tuple[str, str, str, str, str, str]:
    return (
        *_normalized_object_identity(
            item.tenant_code,
            item.system_code,
            item.connection_code,
            item.object_schema,
            item.object_name,
        ),
        normalize_model_key_value(item.attribute_name),
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


def _normalized_object_identity(
    tenant_code: str,
    system_code: str,
    connection_code: str,
    object_schema: str,
    object_name: str,
) -> tuple[str, str, str, str, str]:
    return (
        normalize_model_key_value(tenant_code),
        normalize_model_key_value(system_code),
        normalize_model_key_value(connection_code),
        normalize_model_key_value(object_schema),
        normalize_model_key_value(object_name),
    )


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
