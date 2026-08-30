"""Execute one already-running Dimensional authoring run."""

from __future__ import annotations

import logging
from collections.abc import Sequence
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
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner
from gds_workbench_api.prompt_rendering import render_prompt

from .candidate import DimensionalCandidateValidator
from .detailed import (
    DetailedDimensionalDraftManifest,
    DetailedDimensionalEntityDetail,
    DetailedDimensionalEntityDetailValidator,
    DetailedDimensionalEntityTopology,
    DetailedDimensionalPolicy,
    DetailedDimensionalReconciliationReceipt,
    DetailedDimensionalReconciliationReceiptValidator,
    DetailedDimensionalRelationshipSignal,
    DetailedDimensionalRelationshipSignalLedger,
    DetailedDimensionalTopologyContribution,
    DetailedDimensionalTopologyContributionValidator,
    DetailedDimensionalTopologyReconciliation,
    DetailedDimensionalTopologyReconciliationValidator,
    DetailedDimensionalValidationLead,
    DetailedDimensionalValidationLeadValidator,
    DetailedDimensionalValidationPackage,
    DetailedDimensionalValidationRecord,
    DetailedDimensionalValidationWorkerResult,
    DetailedDimensionalValidationWorkerValidator,
    build_dimensional_draft_manifest,
    build_dimensional_relationship_signal_ledger,
    build_projected_dimensional_validation_packages,
    dimensional_applied_record_refs,
    dimensional_json_bytes,
    dimensional_json_digest,
    load_default_detailed_dimensional_policy,
    materialize_dimensional_reviewed_candidate,
    merge_dimensional_entity_detail_partitions,
    merge_dimensional_topology_partitions,
)
from .policy import (
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
    validate_dimensional_gold_policy,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TopologyBuilderBatch:
    contribution_ref: str
    source_attributes: tuple[PhysicalAttributeKey, ...]
    context: JsonValue


@dataclass(frozen=True, slots=True)
class _EntityDetailBatch:
    entity: DetailedDimensionalEntityTopology
    topology: DetailedDimensionalTopologyReconciliation
    contributions: tuple[DetailedDimensionalTopologyContribution, ...]
    context: JsonValue


@dataclass(frozen=True, slots=True)
class _ReconciliationBatch:
    partition_ref: str
    relationship_signals: tuple[DetailedDimensionalRelationshipSignal, ...]
    context: JsonValue


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
        selected_context_policy = context_policy or load_default_agent_context_policy()
        self._context_policy = selected_context_policy
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=selected_context_policy,
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
            for batch in self._topology_builder_batches(
                plan=plan,
                context=context,
                selected=selected,
            ):
                contribution_validator = DetailedDimensionalTopologyContributionValidator(
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
        topology_partitions: list[DetailedDimensionalTopologyReconciliation] = []
        for contribution_batch, topology_context in self._topology_reconciliation_batches(
            plan=plan,
            context=context,
            contributions=tuple(contributions),
        ):
            topology_validator = DetailedDimensionalTopologyReconciliationValidator(
                contributions=contribution_batch,
                max_result_bytes=self._detailed_result_limit,
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
            topology_partitions.append(
                topology_validator.parse_validated(topology_outcome.candidate)
            )
            max_attempt = max(max_attempt, topology_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or topology_outcome.was_repaired
                or bool(topology_outcome.warning_codes)
            )
        topology = merge_dimensional_topology_partitions(
            contributions=tuple(contributions),
            partitions=tuple(topology_partitions),
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
        assertion_record_keys = tuple(
            record.modeling_assertion_record_key for record in context.context.assertion.records
        )
        details: list[DetailedDimensionalEntityDetail] = []
        for entity in topology.entities:
            detail_partitions: list[DetailedDimensionalEntityDetail] = []
            for batch in self._entity_detail_batches(
                plan=plan,
                context=context,
                topology=topology,
                entity=entity,
                contributions=tuple(contributions),
            ):
                detail_validator = DetailedDimensionalEntityDetailValidator(
                    entity=batch.entity,
                    topology=batch.topology,
                    contributions=batch.contributions,
                    assertion_record_keys=assertion_record_keys,
                    max_result_bytes=self._detailed_result_limit,
                )
                detail_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="entity_detail_builder",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="entity_detail_builder",
                        stage_context=batch.context,
                    ),
                    context=batch.context,
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
                merge_dimensional_entity_detail_partitions(
                    entity=entity,
                    topology=topology,
                    contributions=tuple(contributions),
                    partitions=tuple(detail_partitions),
                    assertion_record_keys=assertion_record_keys,
                )
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
        draft_manifest = build_dimensional_draft_manifest(
            topology=topology,
            entity_details=tuple(details),
            relationship_ledger=relationship_ledger,
            applied_record_refs=applied_refs,
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
            receipts: list[DetailedDimensionalReconciliationReceipt] = []
            for batch in self._reconciliation_batches(
                plan=plan,
                context=context,
                manifest=draft_manifest,
                relationship_ledger=relationship_ledger,
                validation_failures=validation_failures,
            ):
                receipt_validator = DetailedDimensionalReconciliationReceiptValidator(
                    partition_ref=batch.partition_ref,
                    manifest=draft_manifest,
                    relationship_signals=batch.relationship_signals,
                    max_result_bytes=self._detailed_result_limit,
                )
                reconciliation_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="whole_model_reconciliation",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="whole_model_reconciliation",
                        stage_context=batch.context,
                        validation_failures=_bounded_validation_failure_summary(
                            validation_failures
                        ),
                    ),
                    context=batch.context,
                    output_schema=receipt_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=receipt_validator,
                )
                receipts.append(receipt_validator.parse_validated(reconciliation_outcome.candidate))
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
            materialized_candidate = materialize_dimensional_reviewed_candidate(
                topology=topology,
                entity_details=tuple(details),
                relationship_ledger=relationship_ledger,
                manifest=draft_manifest,
                receipts=tuple(receipts),
                applied_record_refs=applied_refs,
            )
            complete_validation = await validator.validate(materialized_candidate)
            if complete_validation.issues:
                raise AgentCandidateValidationError()
            projected_changes = _project_dimensional_changes(
                validator=validator,
                candidate=materialized_candidate,
                context=context,
            )
            if not projected_changes:
                return (), max_attempt, intermediate_warning, sequence + 1
            packages = self._validation_packages(
                plan=plan,
                context=context,
                projected_changes=projected_changes,
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
                worker_validator = DetailedDimensionalValidationWorkerValidator(
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
            leads: list[DetailedDimensionalValidationLead] = []
            for lead_batch, lead_context in self._validation_lead_batches(
                plan=plan,
                context=context,
                worker_results=tuple(worker_results),
            ):
                lead_validator = DetailedDimensionalValidationLeadValidator(
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
                leads.append(lead_validator.parse_validated(lead_outcome.candidate))
                max_attempt = max(max_attempt, lead_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or lead_outcome.was_repaired
                    or bool(lead_outcome.warning_codes)
                )
            lead = _merge_validation_leads(
                worker_results=tuple(worker_results),
                leads=tuple(leads),
            )
            if not lead.blocking_finding_refs:
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
                item.model_dump(mode="json")
                for result in worker_results
                for item in result.findings
                if item.finding_ref in set(lead.blocking_finding_refs)
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

    def _topology_builder_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        selected: SelectedObjectContext,
    ) -> tuple[_TopologyBuilderBatch, ...]:
        if not selected.attributes:
            raise InvalidRequestError(
                "Detailed Dimensional coverage requires Attributes for every selected Object."
            )
        base_ref = f"object_{selected.selection_order:05d}"
        model_context = _detailed_model_context(context)
        selected_document = selected.model_dump(mode="json")
        all_attribute_documents = [item.model_dump(mode="json") for item in selected.attributes]
        selection_manifest = cast(
            JsonValue,
            {
                "selection_order": selected.selection_order,
                "selected_object_digest": dimensional_json_digest(selected_document),
                "total_attribute_count": len(selected.attributes),
                "total_attribute_digest": dimensional_json_digest(
                    cast(JsonValue, all_attribute_documents)
                ),
            },
        )
        support = _topology_support_context(context, selected)
        raw_batches: list[tuple[AttributeRecord, ...]] = []
        offset = 0
        while offset < len(selected.attributes):
            low = 1
            high = min(32, len(selected.attributes) - offset)
            accepted_size = 0
            while low <= high:
                size = (low + high) // 2
                candidate = selected.attributes[offset : offset + size]
                reference = f"{base_ref}_batch_99999"
                keys = _physical_attribute_keys(
                    selected.model_copy(update={"attributes": candidate})
                )
                stage_context = _topology_builder_context(
                    selected=selected,
                    attributes=candidate,
                    contribution_ref=reference,
                    batch_index=99_999,
                    batch_count=99_999,
                    model_context=model_context,
                    selection_manifest=selection_manifest,
                    support=support,
                )
                validator = DetailedDimensionalTopologyContributionValidator(
                    contribution_ref=reference,
                    source_object=_physical_object_key(selected),
                    source_attributes=keys,
                    max_result_bytes=self._detailed_result_limit,
                )
                output_floor = _minimum_topology_contribution(
                    contribution_ref=reference,
                    source_object=_physical_object_key(selected),
                    source_attributes=keys,
                )
                if dimensional_json_bytes(
                    output_floor
                ) <= self._detailed_result_limit // 2 and self._detailed_stage_fits(
                    plan=plan,
                    context=context,
                    stage_code="topology_builder",
                    stage_context=stage_context,
                    output_schema=validator.output_schema(),
                ):
                    accepted_size = size
                    low = size + 1
                else:
                    high = size - 1
            if accepted_size == 0:
                raise InvalidRequestError(
                    "One selected Dimensional Attribute exceeds the bounded detailed stage size."
                )
            raw_batches.append(selected.attributes[offset : offset + accepted_size])
            offset += accepted_size

        covered_attributes = tuple(attribute for batch in raw_batches for attribute in batch)
        if covered_attributes != selected.attributes:
            raise AgentCandidateValidationError()

        batches: list[_TopologyBuilderBatch] = []
        batch_count = len(raw_batches)
        for position, attributes in enumerate(raw_batches, start=1):
            reference = base_ref if batch_count == 1 else f"{base_ref}_batch_{position:05d}"
            typed_selected = selected.model_copy(update={"attributes": attributes})
            keys = _physical_attribute_keys(typed_selected)
            stage_context = _topology_builder_context(
                selected=selected,
                attributes=attributes,
                contribution_ref=reference,
                batch_index=position,
                batch_count=batch_count,
                model_context=model_context,
                selection_manifest=selection_manifest,
                support=support,
            )
            validator = DetailedDimensionalTopologyContributionValidator(
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
                output_schema=validator.output_schema(),
            ):
                raise InvalidRequestError(
                    "One selected Dimensional Attribute exceeds the bounded detailed stage size."
                )
            batches.append(
                _TopologyBuilderBatch(
                    contribution_ref=reference,
                    source_attributes=keys,
                    context=stage_context,
                )
            )
        return tuple(batches)

    def _topology_reconciliation_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        contributions: tuple[DetailedDimensionalTopologyContribution, ...],
    ) -> tuple[tuple[tuple[DetailedDimensionalTopologyContribution, ...], JsonValue], ...]:
        batches: list[tuple[DetailedDimensionalTopologyContribution, ...]] = []
        pending: list[DetailedDimensionalTopologyContribution] = []
        for contribution in contributions:
            candidate = (*pending, contribution)
            stage_context = _topology_reconciliation_context(context, candidate)
            validator = DetailedDimensionalTopologyReconciliationValidator(
                contributions=candidate,
                max_result_bytes=self._detailed_result_limit,
            )
            if self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_reconciler",
                stage_context=stage_context,
                output_schema=validator.output_schema(),
            ):
                pending.append(contribution)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Dimensional topology contribution exceeds the bounded stage size."
                )
            batches.append(tuple(pending))
            pending = [contribution]
        if pending:
            batches.append(tuple(pending))
        result = tuple(
            (batch, _topology_reconciliation_context(context, batch)) for batch in batches
        )
        if any(
            not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="topology_reconciler",
                stage_context=stage_context,
                output_schema=DetailedDimensionalTopologyReconciliationValidator(
                    contributions=batch,
                    max_result_bytes=self._detailed_result_limit,
                ).output_schema(),
            )
            for batch, stage_context in result
        ):
            raise InvalidRequestError(
                "One Dimensional topology contribution exceeds the bounded stage size."
            )
        return result

    def _entity_detail_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        topology: DetailedDimensionalTopologyReconciliation,
        entity: DetailedDimensionalEntityTopology,
        contributions: tuple[DetailedDimensionalTopologyContribution, ...],
    ) -> tuple[_EntityDetailBatch, ...]:
        proposal_by_ref = {
            reference: (contribution, proposal)
            for contribution in contributions
            for reference, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
        }
        batches: list[tuple[str, ...]] = []
        pending: list[str] = []
        pending_attribute_count = 0
        for reference in entity.contribution_refs:
            entry = proposal_by_ref.get(reference)
            if entry is None:
                raise AgentCandidateValidationError()
            candidate = (*pending, reference)
            attribute_count = pending_attribute_count + len(entry[1].source_attributes)
            batch = _entity_detail_batch(
                context,
                topology=topology,
                entity=entity,
                contributions=contributions,
                proposal_refs=candidate,
            )
            validator = DetailedDimensionalEntityDetailValidator(
                entity=batch.entity,
                topology=batch.topology,
                contributions=batch.contributions,
                assertion_record_keys=tuple(
                    item.modeling_assertion_record_key for item in context.context.assertion.records
                ),
                max_result_bytes=self._detailed_result_limit,
            )
            if attribute_count <= 32 and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="entity_detail_builder",
                stage_context=batch.context,
                output_schema=validator.output_schema(),
            ):
                pending.append(reference)
                pending_attribute_count = attribute_count
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Dimensional Entity contribution exceeds the bounded detail stage size."
                )
            batches.append(tuple(pending))
            pending = [reference]
            pending_attribute_count = len(entry[1].source_attributes)
        if pending:
            batches.append(tuple(pending))
        result = tuple(
            _entity_detail_batch(
                context,
                topology=topology,
                entity=entity,
                contributions=contributions,
                proposal_refs=batch,
            )
            for batch in batches
        )
        for batch in result:
            validator = DetailedDimensionalEntityDetailValidator(
                entity=batch.entity,
                topology=batch.topology,
                contributions=batch.contributions,
                assertion_record_keys=tuple(
                    item.modeling_assertion_record_key for item in context.context.assertion.records
                ),
                max_result_bytes=self._detailed_result_limit,
            )
            if not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="entity_detail_builder",
                stage_context=batch.context,
                output_schema=validator.output_schema(),
            ):
                raise InvalidRequestError(
                    "One Dimensional Entity contribution exceeds the bounded detail stage size."
                )
        return result

    def _reconciliation_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        manifest: DetailedDimensionalDraftManifest,
        relationship_ledger: DetailedDimensionalRelationshipSignalLedger,
        validation_failures: list[dict[str, object]],
    ) -> tuple[_ReconciliationBatch, ...]:
        raw_batches: list[tuple[DetailedDimensionalRelationshipSignal, ...]] = []
        pending: list[DetailedDimensionalRelationshipSignal] = []
        signals: Sequence[DetailedDimensionalRelationshipSignal | None] = (
            relationship_ledger.signals if relationship_ledger.signals else (None,)
        )
        for signal in signals:
            candidate = tuple(pending) if signal is None else (*pending, signal)
            position = len(raw_batches) + 1
            partition_ref = f"reconciliation_{position:05d}"
            stage_context = _reconciliation_context(
                context,
                partition_ref=partition_ref,
                manifest=manifest,
                relationship_signals=candidate,
                validation_failures=validation_failures,
            )
            validator = DetailedDimensionalReconciliationReceiptValidator(
                partition_ref=partition_ref,
                manifest=manifest,
                relationship_signals=candidate,
                max_result_bytes=self._detailed_result_limit,
            )
            if len(candidate) <= 32 and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="whole_model_reconciliation",
                stage_context=stage_context,
                output_schema=validator.output_schema(),
                validation_failures=_bounded_validation_failure_summary(validation_failures),
            ):
                if signal is not None:
                    pending.append(signal)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Dimensional relationship signal exceeds the bounded stage size."
                )
            raw_batches.append(tuple(pending))
            pending = [] if signal is None else [signal]
        if pending or not raw_batches:
            raw_batches.append(tuple(pending))
        batches: list[_ReconciliationBatch] = []
        for position, batch in enumerate(raw_batches, start=1):
            partition_ref = f"reconciliation_{position:05d}"
            stage_context = _reconciliation_context(
                context,
                partition_ref=partition_ref,
                manifest=manifest,
                relationship_signals=batch,
                validation_failures=validation_failures,
            )
            validator = DetailedDimensionalReconciliationReceiptValidator(
                partition_ref=partition_ref,
                manifest=manifest,
                relationship_signals=batch,
                max_result_bytes=self._detailed_result_limit,
            )
            if not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="whole_model_reconciliation",
                stage_context=stage_context,
                output_schema=validator.output_schema(),
                validation_failures=_bounded_validation_failure_summary(validation_failures),
            ):
                raise InvalidRequestError(
                    "One Dimensional relationship signal exceeds the bounded stage size."
                )
            batches.append(
                _ReconciliationBatch(
                    partition_ref=partition_ref,
                    relationship_signals=batch,
                    context=stage_context,
                )
            )
        return tuple(batches)

    def _validation_packages(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        projected_changes: tuple[StageModelChange, ...],
    ) -> tuple[DetailedDimensionalValidationPackage, ...]:
        initial_packages = build_projected_dimensional_validation_packages(
            projected_changes=projected_changes,
            package_size=self._detailed_policy.validation_package_size,
            max_packages=self._detailed_policy.max_validation_packages,
        )
        records = tuple(record for package in initial_packages for record in package.records)
        grouped: list[tuple[DetailedDimensionalValidationRecord, ...]] = []
        pending: list[DetailedDimensionalValidationRecord] = []
        for record in records:
            candidate = (*pending, record)
            package = _validation_package(99_999, candidate)
            stage_context = _validation_worker_context(context, package)
            validator = DetailedDimensionalValidationWorkerValidator(
                package=package,
                max_result_bytes=self._detailed_result_limit,
            )
            if len(
                candidate
            ) <= self._detailed_policy.validation_package_size and self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_worker",
                stage_context=stage_context,
                output_schema=validator.output_schema(),
            ):
                pending.append(record)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Dimensional validation record exceeds the bounded stage size."
                )
            grouped.append(tuple(pending))
            pending = [record]
        if pending:
            grouped.append(tuple(pending))
        if not grouped or len(grouped) > self._detailed_policy.max_validation_packages:
            raise InvalidRequestError(
                "Dimensional validation exceeds its configured package limit."
            )
        packages = tuple(
            _validation_package(position, batch) for position, batch in enumerate(grouped, start=1)
        )
        if any(
            not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_worker",
                stage_context=_validation_worker_context(context, package),
                output_schema=DetailedDimensionalValidationWorkerValidator(
                    package=package,
                    max_result_bytes=self._detailed_result_limit,
                ).output_schema(),
            )
            for package in packages
        ):
            raise InvalidRequestError(
                "One Dimensional validation record exceeds the bounded stage size."
            )
        return packages

    def _validation_lead_batches(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        worker_results: tuple[DetailedDimensionalValidationWorkerResult, ...],
    ) -> tuple[
        tuple[tuple[DetailedDimensionalValidationWorkerResult, ...], JsonValue],
        ...,
    ]:
        grouped: list[tuple[DetailedDimensionalValidationWorkerResult, ...]] = []
        pending: list[DetailedDimensionalValidationWorkerResult] = []
        for result in worker_results:
            candidate = (*pending, result)
            stage_context = _validation_lead_context(context, candidate)
            validator = DetailedDimensionalValidationLeadValidator(
                worker_results=candidate,
                max_result_bytes=self._detailed_result_limit,
            )
            if self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_lead",
                stage_context=stage_context,
                output_schema=validator.output_schema(),
            ):
                pending.append(result)
                continue
            if not pending:
                raise InvalidRequestError(
                    "One Dimensional validation result exceeds the bounded lead stage size."
                )
            grouped.append(tuple(pending))
            pending = [result]
        if pending:
            grouped.append(tuple(pending))
        result = tuple((batch, _validation_lead_context(context, batch)) for batch in grouped)
        if any(
            not self._detailed_stage_fits(
                plan=plan,
                context=context,
                stage_code="validator_lead",
                stage_context=stage_context,
                output_schema=DetailedDimensionalValidationLeadValidator(
                    worker_results=batch,
                    max_result_bytes=self._detailed_result_limit,
                ).output_schema(),
            )
            for batch, stage_context in result
        ):
            raise InvalidRequestError(
                "One Dimensional validation result exceeds the bounded lead stage size."
            )
        return result

    def _detailed_stage_fits(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        stage_code: str,
        stage_context: JsonValue,
        output_schema: dict[str, JsonValue],
        validation_failures: object | None = None,
    ) -> bool:
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
            workflow="dimensional",
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


def _topology_builder_context(
    *,
    selected: SelectedObjectContext,
    attributes: Sequence[AttributeRecord],
    contribution_ref: str,
    batch_index: int,
    batch_count: int,
    model_context: JsonValue,
    selection_manifest: JsonValue,
    support: JsonValue,
) -> JsonValue:
    batch_documents = [item.model_dump(mode="json") for item in attributes]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": model_context,
            "contribution_ref": contribution_ref,
            "batch": {
                "batch_index": batch_index,
                "batch_count": batch_count,
                "attribute_count": len(attributes),
                "attribute_digest": dimensional_json_digest(cast(JsonValue, batch_documents)),
            },
            "authoritative_selection_manifest": selection_manifest,
            "selected_object": {
                "selection_order": selected.selection_order,
                "object": _compact_selected_object(selected),
                "attributes": [_compact_selected_attribute(item) for item in attributes],
            },
            "support": support,
        },
    )


def _topology_support_context(
    context: AgentContextBundle,
    selected: SelectedObjectContext,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "profiles": _support_projection(
                tuple(
                    item.model_dump(mode="json")
                    for item in context.context.profiles
                    if _profile_matches_selected(item, selected)
                )
            ),
            "analysis_relationships": _support_projection(
                tuple(
                    item.model_dump(mode="json")
                    for item in context.context.analysis_relationships
                    if _analysis_matches_selected(item, selected)
                )
            ),
            "assertions": _support_projection(
                tuple(item.model_dump(mode="json") for item in context.context.assertion.records)
            ),
            "applied_dimensional": _applied_dimensional_manifest(context),
        },
    )


def _topology_reconciliation_context(
    context: AgentContextBundle,
    contributions: Sequence[DetailedDimensionalTopologyContribution],
) -> JsonValue:
    documents = [item.model_dump(mode="json") for item in contributions]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "contribution_manifest": {
                "count": len(documents),
                "digest": dimensional_json_digest(cast(JsonValue, documents)),
            },
            "contributions": documents,
            "applied_dimensional": _applied_dimensional_manifest(context),
        },
    )


def _entity_detail_batch(
    context: AgentContextBundle,
    *,
    topology: DetailedDimensionalTopologyReconciliation,
    entity: DetailedDimensionalEntityTopology,
    contributions: tuple[DetailedDimensionalTopologyContribution, ...],
    proposal_refs: tuple[str, ...],
) -> _EntityDetailBatch:
    expected_refs = set(proposal_refs)
    partition_contributions: list[DetailedDimensionalTopologyContribution] = []
    for contribution in contributions:
        proposals = tuple(
            proposal
            for reference, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
            if reference in expected_refs
        )
        if not proposals:
            continue
        partition_contributions.append(contribution.model_copy(update={"proposals": proposals}))
    actual_refs = tuple(
        reference
        for contribution in partition_contributions
        for reference in contribution.proposal_refs
    )
    if len(actual_refs) != len(set(actual_refs)) or set(actual_refs) != expected_refs:
        raise AgentCandidateValidationError()
    partition_entity = entity.model_copy(update={"contribution_refs": proposal_refs})
    required_submodels = set(entity.submodel_refs)
    partition_topology = topology.model_copy(
        update={
            "submodels": tuple(
                item
                for item in topology.submodels
                if item.canonical_submodel_ref in required_submodels
            ),
            "entities": (partition_entity,),
            "discarded_contribution_refs": (),
        }
    )
    contribution_documents = [item.model_dump(mode="json") for item in partition_contributions]
    stage_context = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "topology": partition_topology.model_dump(mode="json"),
            "entity": partition_entity.model_dump(mode="json"),
            "contribution_manifest": {
                "count": len(contribution_documents),
                "digest": dimensional_json_digest(cast(JsonValue, contribution_documents)),
            },
            "contributions": contribution_documents,
            "assertions": _support_projection(
                tuple(item.model_dump(mode="json") for item in context.context.assertion.records)
            ),
        },
    )
    return _EntityDetailBatch(
        entity=partition_entity,
        topology=partition_topology,
        contributions=tuple(partition_contributions),
        context=stage_context,
    )


def _reconciliation_context(
    context: AgentContextBundle,
    *,
    partition_ref: str,
    manifest: DetailedDimensionalDraftManifest,
    relationship_signals: Sequence[DetailedDimensionalRelationshipSignal],
    validation_failures: list[dict[str, object]],
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "partition_ref": partition_ref,
            "review_manifest": manifest.model_dump(mode="json"),
            "relationship_signals": [item.model_dump(mode="json") for item in relationship_signals],
            "validation_failure_summary": _bounded_validation_failure_summary(validation_failures),
        },
    )


def _validation_package(
    position: int,
    records: Sequence[DetailedDimensionalValidationRecord],
) -> DetailedDimensionalValidationPackage:
    return DetailedDimensionalValidationPackage(
        package_ref=f"validation_{position:05d}",
        records=tuple(records),
        record_digests=tuple(
            dimensional_json_digest(item.record.model_dump(mode="json")) for item in records
        ),
    )


def _validation_worker_context(
    context: AgentContextBundle,
    package: DetailedDimensionalValidationPackage,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "validation_package": package.model_dump(mode="json"),
        },
    )


def _validation_lead_context(
    context: AgentContextBundle,
    worker_results: Sequence[DetailedDimensionalValidationWorkerResult],
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "worker_results": [item.model_dump(mode="json") for item in worker_results],
        },
    )


def _merge_validation_leads(
    *,
    worker_results: tuple[DetailedDimensionalValidationWorkerResult, ...],
    leads: tuple[DetailedDimensionalValidationLead, ...],
) -> DetailedDimensionalValidationLead:
    if not worker_results or not leads:
        raise AgentCandidateValidationError()
    package_refs = tuple(item.package_ref for item in worker_results)
    finding_refs = tuple(
        finding.finding_ref for item in worker_results for finding in item.findings
    )
    blocking_refs = tuple(
        finding.finding_ref
        for item in worker_results
        for finding in item.findings
        if finding.severity == "error"
    )
    actual_packages = tuple(reference for item in leads for reference in item.reviewed_package_refs)
    actual_findings = tuple(reference for item in leads for reference in item.reviewed_finding_refs)
    actual_blocking = tuple(reference for item in leads for reference in item.blocking_finding_refs)
    if not all(
        (
            _exact_unique(actual_packages, package_refs),
            _exact_unique(actual_findings, finding_refs),
            _exact_unique(actual_blocking, blocking_refs),
        )
    ):
        raise AgentCandidateValidationError()
    return DetailedDimensionalValidationLead(
        reviewed_package_refs=package_refs,
        reviewed_finding_refs=finding_refs,
        blocking_finding_refs=blocking_refs,
        repair_brief=(
            "Repair the blocking Dimensional validation findings." if blocking_refs else None
        ),
    )


def _bounded_validation_failure_summary(
    failures: list[dict[str, object]],
) -> JsonValue:
    documents = cast(JsonValue, failures)
    included = failures[:20]
    return cast(
        JsonValue,
        {
            "finding_count": len(failures),
            "findings_digest": dimensional_json_digest(documents),
            "included_finding_count": len(included),
            "included_findings": included,
            "is_complete": len(included) == len(failures),
        },
    )


def _compact_selected_object(selected: SelectedObjectContext) -> JsonValue:
    document = selected.object.model_dump(mode="json")
    document.pop("object_description", None)
    document.pop("object_transformation", None)
    document["record_digest"] = dimensional_json_digest(selected.object.model_dump(mode="json"))
    return cast(JsonValue, document)


def _compact_selected_attribute(attribute: AttributeRecord) -> JsonValue:
    document = attribute.model_dump(mode="json")
    document.pop("attribute_description", None)
    document.pop("attribute_custom_code", None)
    document["record_digest"] = dimensional_json_digest(attribute.model_dump(mode="json"))
    return cast(JsonValue, document)


def _support_projection(records: Sequence[JsonValue]) -> JsonValue:
    included = [_bounded_json_projection(item) for item in records[:4]]
    return cast(
        JsonValue,
        {
            "record_count": len(records),
            "records_digest": dimensional_json_digest(cast(JsonValue, list(records))),
            "included_record_count": len(included),
            "included_records_digest": dimensional_json_digest(cast(JsonValue, included)),
            "included_records": included,
            "is_complete": len(included) == len(records),
        },
    )


def _bounded_json_projection(value: JsonValue, *, depth: int = 0) -> JsonValue:
    if isinstance(value, str):
        return value if len(value) <= 512 else value[:512]
    if isinstance(value, list):
        if depth >= 4:
            return cast(JsonValue, {"item_count": len(value)})
        return [_bounded_json_projection(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        if depth >= 4:
            return cast(JsonValue, {"field_count": len(value)})
        return {
            key: _bounded_json_projection(item, depth=depth + 1)
            for key, item in sorted(value.items())[:40]
        }
    return value


def _applied_dimensional_manifest(context: AgentContextBundle) -> JsonValue:
    section = context.context.applied.dimensional
    document = None if section is None else section.model_dump(mode="json")
    refs = dimensional_applied_record_refs(section)
    return cast(
        JsonValue,
        {
            "record_count": len(refs),
            "record_refs_digest": dimensional_json_digest(cast(JsonValue, list(refs))),
            "section_digest": dimensional_json_digest(cast(JsonValue, document)),
        },
    )


def _minimum_topology_contribution(
    *,
    contribution_ref: str,
    source_object: PhysicalObjectKey,
    source_attributes: tuple[PhysicalAttributeKey, ...],
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "contribution_ref": contribution_ref,
            "source_object": source_object.model_dump(mode="json"),
            "disposition": "represented",
            "rationale": "Selected Silver contribution.",
            "proposals": [
                {
                    "local_entity_ref": "entity",
                    "candidate_entity_name": "Entity",
                    "candidate_entity_type": "dimension",
                    "candidate_fact_type": None,
                    "candidate_entity_grain_definition": None,
                    "candidate_submodel_names": [],
                    "source_attributes": [
                        item.model_dump(mode="json") for item in source_attributes
                    ],
                }
            ],
        },
    )


def _exact_unique(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return len(actual) == len(set(actual)) and set(actual) == set(expected)


def _detailed_resolver_values(
    context: AgentContextBundle,
    *,
    stage_code: str,
    stage_context: JsonValue,
    validation_failures: object | None = None,
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
    details = context.context.model_details.model_dump(mode="json")
    return cast(
        JsonValue,
        {
            "model_id": context.context.model_id,
            "model_name": context.context.model_name,
            "model_revision": context.context.model_revision,
            "model_details_digest": dimensional_json_digest(details),
            "model_description": _bounded_json_projection(
                cast(JsonValue, details.get("model_description"))
            ),
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
