"""Execute one already-running Analysis inference run."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations_with_replacement
from typing import Literal, Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.metadata_records import AttributeRecord
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    PhysicalAttributeKey,
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

from .candidate import AnalysisInferenceCandidateValidator, AnalysisInferenceRelationship
from .detailed import (
    DetailedAnalysisCandidateFinderResult,
    DetailedAnalysisCandidateFinderValidator,
    DetailedAnalysisEndpointCandidate,
    DetailedAnalysisPolicy,
    DetailedAnalysisReconciliationValidator,
    DetailedAnalysisRelationshipResolverValidator,
    DetailedAnalysisResolutionDecision,
    DetailedAnalysisResolutionResult,
    DetailedAnalysisReviewerValidator,
    analysis_applied_records_by_ref,
    load_default_detailed_analysis_policy,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _DetailedFinderSlice:
    slice_ref: str
    context: JsonValue
    left_attributes: tuple[PhysicalAttributeKey, ...]
    right_attributes: tuple[PhysicalAttributeKey, ...]


@dataclass(frozen=True, slots=True)
class _DetailedEvidenceFragment:
    dataset: str
    record_ref: str
    fragment_ref: str
    value: JsonValue
    context_item: JsonValue


class AnalysisInferenceExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class AnalysisInferencePlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class AnalysisInferenceContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle: ...


class AnalysisInferenceChangeSetHandoff(Protocol):
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


class AnalysisInferenceNoOpCompleter(Protocol):
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


class AnalysisInferenceLifecycle(Protocol):
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


class AnalysisInferenceExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_inference_execution_failed",
            message=("Analysis inference failed before a validated draft was committed."),
        )


class AnalysisInferenceFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_inference_finalization_failed",
            message="Analysis finalization outcome could not be confirmed.",
        )


class AnalysisInferenceRunLifecycle(Protocol):
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


class AnalysisInferenceExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> WorkflowChangeSetHandoffResult | None: ...


class AnalysisInferenceWorkflow:
    """Bind the public route to one explicit supported Analysis mode."""

    def __init__(
        self,
        *,
        lifecycle: AnalysisInferenceRunLifecycle,
        executor: AnalysisInferenceExecutor,
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
            expected_workflow="analysis",
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
    ) -> WorkflowChangeSetHandoffResult | None:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseAnalysisInferenceExecutor:
    """Load frozen inputs, repair one candidate, and hand off one complete draft."""

    def __init__(
        self,
        *,
        database: AnalysisInferenceExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: AnalysisInferenceChangeSetHandoff,
        no_op: AnalysisInferenceNoOpCompleter,
        lifecycle: AnalysisInferenceLifecycle,
        plan_repository: AnalysisInferencePlanRepository | None = None,
        context_repository: AnalysisInferenceContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
        detailed_policy: DetailedAnalysisPolicy | None = None,
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
        self._detailed_policy = detailed_policy or load_default_detailed_analysis_policy()

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> WorkflowChangeSetHandoffResult | None:
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

            execution_mode = cast(WorkflowExecutionMode, plan.workflow_execution_mode)
            is_detailed = execution_mode == "detailed_coverage"
            detailed_slice_count = _analysis_slice_count(context) if is_detailed else 1
            if is_detailed and detailed_slice_count > self._detailed_policy.max_object_pairs:
                raise InvalidRequestError(
                    "The detailed Analysis selection contains too many bounded slices."
                )
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage=(
                        "analysis.candidate_finder"
                        if is_detailed
                        else "analysis.relationship_inference"
                    ),
                    status="running",
                    message=(
                        "Analysis detailed candidate discovery started."
                        if is_detailed
                        else "Analysis relationship inference started."
                    ),
                    current=None if is_detailed else 0,
                    total=None if is_detailed else detailed_slice_count,
                    finding_count=0,
                ),
            )
            if not any(selected.attributes for selected in context.context.selected_objects):
                raise InvalidRequestError(
                    "The selected Analysis scope contains no Attributes to analyze."
                )
            validator = _candidate_validator(context)
            if is_detailed:
                (
                    candidate,
                    outcome,
                    intermediate_warning,
                    final_attempt,
                ) = await self._execute_detailed(
                    principal,
                    plan=plan,
                    context=context,
                    validator=validator,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                final_event_sequence = 6
            else:
                resolver_key = f"workflow.analysis.{execution_mode}.relationship_inference.context"
                outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="relationship_inference",
                    resolver_values={
                        resolver_key: context.embedded_context,
                        "workflow.validation_failures": [],
                    },
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
                final_attempt = outcome.attempt_count
                final_event_sequence = 3
            changes = validator.parse_validated(candidate)
            finding_count = sum(len(change.records) for change in changes)
            warning = intermediate_warning or outcome.was_repaired or bool(outcome.warning_codes)
            final_event = AgentWorkflowEvent(
                sequence=final_event_sequence,
                attempt=final_attempt,
                stage="analysis.backend_validation",
                status="warning" if warning else "running",
                message=(
                    "Analysis inference completed without effective changes."
                    if not changes
                    else "Analysis findings are ready in a validated draft."
                ),
                current=1,
                total=1,
                finding_count=finding_count,
            )
            if changes:
                finalization_attempted = True
                finalization = await self._handoff.finalize(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                    expected_workflow="analysis",
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    changes=changes,
                    final_event=final_event,
                )
                return finalization.handoff

            finalization_attempted = True
            await self._no_op.complete(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=workflow_run_claim_token,
                request=AuthoringNoOpRequest(
                    expected_workflow="analysis",
                    expected_execution_mode=execution_mode,
                    expected_correlation_id=plan.correlation_id,
                    expected_model_revision=expected_model_revision,
                    candidate_digest=authoring_no_op_candidate_digest(plan),
                    final_event=final_event,
                ),
            )
            return None
        except Exception as error:
            safe_error = _safe_execution_error(
                error,
                finalization_attempted=finalization_attempted,
            )
            if finalization_attempted:
                _logger.warning(
                    "Analysis Workflow Run finalization remains pending.",
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
                        "Analysis inference failure state could not be persisted.",
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
        validator: AnalysisInferenceCandidateValidator,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> tuple[JsonValue, AgentStageOutcome, bool, int]:
        if _analysis_slice_count(context) > self._detailed_policy.max_object_pairs:
            raise InvalidRequestError(
                "The detailed Analysis selection contains too many bounded slices."
            )

        maximum_stage_context_bytes = _detailed_stage_context_limit(self._context_policy)
        maximum_stage_result_bytes = min(
            self._context_policy.max_candidate_bytes,
            maximum_stage_context_bytes,
        )
        maximum_finder_context_bytes = max(4_096, maximum_stage_context_bytes // 2)
        evidence_slice_count = 0
        for evidence_slice_count, _ in enumerate(
            _candidate_finder_slices(
                context,
                maximum_context_bytes=maximum_finder_context_bytes,
            ),
            start=1,
        ):
            if evidence_slice_count > self._detailed_policy.max_candidate_slices:
                raise InvalidRequestError(
                    "The detailed Analysis selection contains too many bounded evidence slices."
                )
        finder_runs: dict[str, DetailedAnalysisCandidateFinderResult] = {}
        intermediate_warning = False
        max_attempt = 1
        candidate_count = 0
        for slice_count, finder_slice in enumerate(
            _candidate_finder_slices(
                context,
                maximum_context_bytes=maximum_finder_context_bytes,
            ),
            start=1,
        ):
            if slice_count > self._detailed_policy.max_candidate_slices:
                raise InvalidRequestError(
                    "The detailed Analysis selection contains too many bounded evidence slices."
                )
            finder_validator = DetailedAnalysisCandidateFinderValidator(
                slice_ref=finder_slice.slice_ref,
                left_attributes=finder_slice.left_attributes,
                right_attributes=finder_slice.right_attributes,
                max_candidates=self._detailed_policy.max_candidates_per_slice,
                max_result_bytes=maximum_stage_result_bytes,
            )
            outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="candidate_finder",
                resolver_values=_detailed_resolver_values(
                    stage_code="candidate_finder",
                    stage_context=finder_slice.context,
                ),
                context=finder_slice.context,
                output_schema=finder_validator.output_schema(),
                allowed_tool_names=(),
                validator=finder_validator,
            )
            finder = finder_validator.parse_validated(outcome.candidate)
            candidate_count += len(finder.candidates)
            if candidate_count > self._detailed_policy.max_total_candidates:
                raise InvalidRequestError(
                    "The detailed Analysis run produced too many bounded candidates."
                )
            if finder.candidates:
                finder_runs[finder.coverage.slice_ref] = finder
            max_attempt = max(max_attempt, outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or finder.coverage.disposition == "needs_review"
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
                stage="analysis.relationship_resolver",
                status="running",
                message="Bounded candidates are ready for relationship resolution.",
                current=None,
                total=None,
                finding_count=candidate_count,
            ),
        )

        resolutions: list[DetailedAnalysisResolutionResult] = []
        applied_by_ref = analysis_applied_records_by_ref(context.context.analysis_relationships)
        resolved_finder_refs: set[str] = set()
        for finder_slice in _candidate_finder_slices(
            context,
            maximum_context_bytes=maximum_finder_context_bytes,
        ):
            finder = finder_runs.get(finder_slice.slice_ref)
            if finder is None:
                continue
            resolved_finder_refs.add(finder_slice.slice_ref)
            for resolver_context, batch_candidates in _resolver_batches(
                finder_slice=finder_slice,
                finder=finder,
                applied_by_ref=applied_by_ref,
                maximum_context_bytes=maximum_stage_context_bytes,
                maximum_result_bytes=maximum_stage_result_bytes,
            ):
                resolver_validator = DetailedAnalysisRelationshipResolverValidator(
                    candidates=batch_candidates,
                    max_result_bytes=maximum_stage_result_bytes,
                )
                outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="relationship_resolver",
                    resolver_values=_detailed_resolver_values(
                        stage_code="relationship_resolver",
                        stage_context=resolver_context,
                    ),
                    context=resolver_context,
                    output_schema=resolver_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=resolver_validator,
                )
                resolution = resolver_validator.parse_validated(outcome.candidate)
                resolutions.append(resolution)
                max_attempt = max(max_attempt, outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or any(item.disposition == "needs_review" for item in resolution.decisions)
                    or outcome.was_repaired
                    or bool(outcome.warning_codes)
                )
        if resolved_finder_refs != set(finder_runs):
            raise AgentCandidateValidationError()

        decisions = tuple(
            decision for resolution in resolutions for decision in resolution.decisions
        )
        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=4,
                attempt=1,
                stage="analysis.whole_slice_reconciler",
                status="running",
                message="Resolved slices are ready for complete reconciliation.",
                current=None,
                total=None,
                finding_count=len(decisions),
            ),
        )
        reconciled_relationships: dict[tuple[str, ...], AnalysisInferenceRelationship] = {}
        reconciliation_outcome: AgentStageOutcome | None = None
        for reconciliation_context, batch_decisions, batch_applied in _reconciliation_batches(
            context,
            decisions=decisions,
            applied_by_ref=applied_by_ref,
            maximum_context_bytes=maximum_stage_context_bytes,
        ):
            reconciliation_validator = DetailedAnalysisReconciliationValidator(
                decisions=batch_decisions,
                applied_by_ref=batch_applied,
                final_validator=validator,
                max_result_bytes=maximum_stage_result_bytes,
            )
            reconciliation_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="whole_slice_reconciler",
                resolver_values=_detailed_resolver_values(
                    stage_code="whole_slice_reconciler",
                    stage_context=reconciliation_context,
                ),
                context=reconciliation_context,
                output_schema=reconciliation_validator.output_schema(),
                allowed_tool_names=(),
                validator=reconciliation_validator,
            )
            materialized = cast(
                Mapping[str, JsonValue],
                reconciliation_validator.materialize_validated(reconciliation_outcome.candidate),
            )
            raw_relationships = materialized.get("relationships")
            if not isinstance(raw_relationships, list):
                raise AgentCandidateValidationError()
            for raw_relationship in raw_relationships:
                relationship = AnalysisInferenceRelationship.model_validate(
                    raw_relationship,
                    strict=True,
                )
                key = _inference_relationship_key(relationship)
                existing = reconciled_relationships.get(key)
                reconciled_relationships[key] = (
                    relationship
                    if existing is None
                    else _merge_inference_relationships(existing, relationship)
                )
            max_attempt = max(max_attempt, reconciliation_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or reconciliation_outcome.was_repaired
                or bool(reconciliation_outcome.warning_codes)
            )
        if reconciliation_outcome is None:
            raise AgentCandidateValidationError()
        candidate = cast(
            JsonValue,
            {
                "relationships": [
                    relationship.model_dump(mode="json")
                    for relationship in reconciled_relationships.values()
                ]
            },
        )
        if (await validator.validate(candidate)).issues:
            raise AgentCandidateValidationError()

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=5,
                attempt=1,
                stage="analysis.analysis_reviewer",
                status="running",
                message="Reconciled relationships are ready for complete review.",
                current=None,
                total=None,
                finding_count=len(reconciled_relationships),
            ),
        )
        review_outcome: AgentStageOutcome | None = None
        review_finding_count = 0
        for (
            reviewer_context,
            batch_relationships,
            batch_relationship_refs,
            batch_applied_refs,
        ) in _review_batches(
            context,
            relationships=tuple(reconciled_relationships.values()),
            applied_by_ref=applied_by_ref,
            maximum_context_bytes=maximum_stage_context_bytes,
        ):
            reviewer_validator = DetailedAnalysisReviewerValidator(
                relationships=batch_relationships,
                relationship_refs=batch_relationship_refs,
                applied_record_refs=batch_applied_refs,
                max_findings=self._detailed_policy.max_review_findings,
                max_result_bytes=maximum_stage_result_bytes,
            )
            review_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="analysis_reviewer",
                resolver_values=_detailed_resolver_values(
                    stage_code="analysis_reviewer",
                    stage_context=reviewer_context,
                ),
                context=reviewer_context,
                output_schema=reviewer_validator.output_schema(),
                allowed_tool_names=(),
                validator=reviewer_validator,
            )
            review = reviewer_validator.parse_validated(review_outcome.candidate)
            if any(item.severity == "blocker" for item in review.findings):
                raise AgentCandidateValidationError()
            review_finding_count += len(review.findings)
            if review_finding_count > self._detailed_policy.max_review_findings:
                raise AgentCandidateValidationError()
            max_attempt = max(max_attempt, review_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or bool(review.findings)
                or review_outcome.was_repaired
                or bool(review_outcome.warning_codes)
            )
        if review_outcome is None:
            raise AgentCandidateValidationError()
        return candidate, review_outcome, intermediate_warning, max_attempt

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
            and stage_codes == ("relationship_inference",)
        ) or (
            plan.workflow_execution_mode == "detailed_coverage"
            and stage_codes
            == (
                "candidate_finder",
                "relationship_resolver",
                "whole_slice_reconciler",
                "analysis_reviewer",
            )
        )
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "analysis"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError(
                "The Analysis inference run does not use the fixed execution path."
            )


def _candidate_validator(
    context: AgentContextBundle,
) -> AnalysisInferenceCandidateValidator:
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
    return AnalysisInferenceCandidateValidator(
        selected_attribute_keys=selected_attributes,
        applied=context.context.analysis_relationships,
    )


def _analysis_slice_count(context: AgentContextBundle) -> int:
    object_count = len(context.context.selected_objects)
    return object_count * (object_count + 1) // 2


def _candidate_finder_slices(
    context: AgentContextBundle,
    *,
    maximum_context_bytes: int,
) -> Iterator[_DetailedFinderSlice]:
    if maximum_context_bytes < 4_096:
        raise InvalidRequestError("The detailed Analysis context limit is too small.")
    chunk_bytes = max(2_048, min(8 * 1024, maximum_context_bytes // 4))
    position = 0
    for left_object, right_object in combinations_with_replacement(
        context.context.selected_objects, 2
    ):
        left_chunks = _attribute_chunks(left_object.attributes, maximum_bytes=chunk_bytes)
        right_chunks = (
            left_chunks
            if left_object.selection_order == right_object.selection_order
            else _attribute_chunks(right_object.attributes, maximum_bytes=chunk_bytes)
        )
        chunk_pairs = (
            combinations_with_replacement(left_chunks, 2)
            if left_object.selection_order == right_object.selection_order
            else ((left, right) for left in left_chunks for right in right_chunks)
        )
        for left_chunk, right_chunk in chunk_pairs:
            selected_objects = [_selected_object_evidence(left_object, left_chunk)]
            if left_object.selection_order == right_object.selection_order:
                combined = _merge_attribute_chunks(left_chunk, right_chunk)
                selected_objects = [_selected_object_evidence(left_object, combined)]
            else:
                selected_objects.append(_selected_object_evidence(right_object, right_chunk))
            selected_keys = {_attribute_key(attribute) for attribute in (*left_chunk, *right_chunk)}
            profiles = tuple(
                profile
                for profile in context.context.profiles
                if _attribute_key(profile) in selected_keys
            )
            relevant_applied = _relevant_applied_analysis(
                context,
                selected_keys=selected_keys,
            )
            for stage_context in _candidate_evidence_pages(
                context,
                selected_objects=tuple(selected_objects),
                profiles=profiles,
                relevant_applied=relevant_applied,
                maximum_bytes=maximum_context_bytes,
            ):
                position += 1
                slice_ref = f"slice_{position:05d}"
                typed_context = cast(dict[str, JsonValue], stage_context)
                typed_context["slice_ref"] = slice_ref
                yield _DetailedFinderSlice(
                    slice_ref=slice_ref,
                    context=stage_context,
                    left_attributes=tuple(_physical_attribute(item) for item in left_chunk),
                    right_attributes=tuple(_physical_attribute(item) for item in right_chunk),
                )


def _attribute_chunks(
    attributes: tuple[AttributeRecord, ...],
    *,
    maximum_bytes: int,
) -> tuple[tuple[AttributeRecord, ...], ...]:
    chunks: list[tuple[AttributeRecord, ...]] = []
    current: list[AttributeRecord] = []
    for attribute in attributes:
        candidate = [*current, attribute]
        payload = cast(
            JsonValue,
            [_physical_attribute(item).model_dump(mode="json") for item in candidate],
        )
        if current and _json_bytes(payload) > maximum_bytes:
            chunks.append(tuple(current))
            current = [attribute]
        else:
            current = candidate
        single_payload = cast(
            JsonValue,
            [_physical_attribute(item).model_dump(mode="json") for item in current],
        )
        if _json_bytes(single_payload) > maximum_bytes:
            raise InvalidRequestError(
                "A selected Analysis Attribute exceeds the bounded evidence size."
            )
    if current:
        chunks.append(tuple(current))
    return tuple(chunks) or ((),)


def _merge_attribute_chunks(
    left: tuple[AttributeRecord, ...],
    right: tuple[AttributeRecord, ...],
) -> tuple[AttributeRecord, ...]:
    merged: list[AttributeRecord] = []
    seen: set[tuple[str, ...]] = set()
    for attribute in (*left, *right):
        key = _attribute_key(attribute)
        if key not in seen:
            seen.add(key)
            merged.append(attribute)
    return tuple(merged)


def _selected_object_evidence(
    selected: SelectedObjectContext,
    attributes: tuple[AttributeRecord, ...],
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "selection_order": selected.selection_order,
            "object": selected.object.model_dump(mode="json"),
            "attributes": [attribute.model_dump(mode="json") for attribute in attributes],
        },
    )


def _candidate_evidence_pages(
    context: AgentContextBundle,
    *,
    selected_objects: tuple[JsonValue, ...],
    profiles: tuple[ProfilingProfileRecord, ...],
    relevant_applied: Mapping[str, AnalysisResultRecord],
    maximum_bytes: int,
) -> tuple[JsonValue, ...]:
    dumped_profiles = [cast(JsonValue, profile.model_dump(mode="json")) for profile in profiles]
    legacy = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "slice_ref": "slice_00000",
            "selected_objects": list(selected_objects),
            "profiles": dumped_profiles,
            "assertions": context.context.assertion.model_dump(mode="json"),
            "applied_records": [
                {
                    "applied_record_ref": reference,
                    "relationship": relationship.model_dump(mode="json"),
                }
                for reference, relationship in relevant_applied.items()
            ],
        },
    )
    if _json_bytes(legacy) <= maximum_bytes:
        return (legacy,)

    records: list[tuple[str, str, JsonValue]] = []
    for selected_index, selected in enumerate(selected_objects, start=1):
        selected_value = cast(dict[str, JsonValue], selected)
        records.append(
            (
                "selected_object",
                f"selected_object_{selected_index:05d}",
                selected_value["object"],
            )
        )
        raw_attributes = selected_value["attributes"]
        if not isinstance(raw_attributes, list):
            raise AgentCandidateValidationError()
        records.extend(
            (
                "selected_attribute",
                f"selected_object_{selected_index:05d}_attribute_{attribute_index:05d}",
                attribute,
            )
            for attribute_index, attribute in enumerate(raw_attributes, start=1)
        )
    records.extend(
        ("profiling_profile", f"profile_{index:05d}", profile)
        for index, profile in enumerate(dumped_profiles, start=1)
    )
    records.extend(
        (
            "modeling_assertion_document",
            f"assertion_document_{index:05d}",
            cast(JsonValue, document.model_dump(mode="json")),
        )
        for index, document in enumerate(context.context.assertion.documents, start=1)
    )
    records.extend(
        (
            "modeling_assertion_record",
            f"assertion_record_{index:05d}",
            cast(JsonValue, record.model_dump(mode="json")),
        )
        for index, record in enumerate(context.context.assertion.records, start=1)
    )
    records.extend(
        (
            "applied_analysis",
            reference,
            cast(JsonValue, relationship.model_dump(mode="json")),
        )
        for reference, relationship in relevant_applied.items()
    )
    identity_objects: list[JsonValue] = []
    for selected in selected_objects:
        selected_value = cast(dict[str, JsonValue], selected)
        raw_object = cast(dict[str, JsonValue], selected_value["object"])
        raw_attributes = cast(list[dict[str, JsonValue]], selected_value["attributes"])
        identity_objects.append(
            cast(
                JsonValue,
                {
                    "selection_order": selected_value["selection_order"],
                    "object": {
                        name: raw_object[name]
                        for name in (
                            "tenant_code",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                        )
                    },
                    "attributes": [
                        _physical_attribute_json(attribute) for attribute in raw_attributes
                    ],
                },
            )
        )
    return _fragmented_evidence_pages(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "slice_ref": "slice_00000",
            "selected_objects": identity_objects,
        },
        item_key="evidence_fragments",
        records=records,
        maximum_bytes=maximum_bytes,
    )


def _relevant_applied_analysis(
    context: AgentContextBundle,
    *,
    selected_keys: set[tuple[str, ...]],
) -> dict[str, AnalysisResultRecord]:
    return {
        reference: relationship
        for reference, relationship in analysis_applied_records_by_ref(
            context.context.analysis_relationships
        ).items()
        if _relationship_endpoint_key(relationship, "from") in selected_keys
        and _relationship_endpoint_key(relationship, "to") in selected_keys
    }


def _physical_attribute(attribute: AttributeRecord) -> PhysicalAttributeKey:
    return PhysicalAttributeKey(
        tenant_code=attribute.tenant_code,
        system_code=attribute.system_code,
        connection_code=attribute.connection_code,
        object_schema=attribute.object_schema,
        object_name=attribute.object_name,
        attribute_name=attribute.attribute_name,
    )


def _detailed_model_context(context: AgentContextBundle) -> JsonValue:
    return cast(
        JsonValue,
        {
            "model_name": context.context.model_name,
            "model_revision": context.context.model_revision,
            "model_description": context.context.model_details.model_description,
        },
    )


def _resolver_batches(
    *,
    finder_slice: _DetailedFinderSlice,
    finder: DetailedAnalysisCandidateFinderResult,
    applied_by_ref: Mapping[str, AnalysisResultRecord],
    maximum_context_bytes: int,
    maximum_result_bytes: int,
) -> Iterator[tuple[JsonValue, tuple[DetailedAnalysisEndpointCandidate, ...]]]:
    batch: list[DetailedAnalysisEndpointCandidate] = []
    for candidate in finder.candidates:
        batch.append(candidate)
        resolver_context = _resolver_batch_context(
            finder_slice=finder_slice,
            finder=finder,
            candidates=tuple(batch),
            applied_by_ref=applied_by_ref,
        )
        if (
            _json_bytes(resolver_context) <= maximum_context_bytes
            and _json_bytes(_minimum_resolution_result(tuple(batch))) <= maximum_result_bytes
        ):
            continue
        overflow = batch.pop()
        if not batch:
            raise InvalidRequestError(
                "A detailed Analysis resolver candidate exceeds the bounded stage size."
            )
        yield (
            _resolver_batch_context(
                finder_slice=finder_slice,
                finder=finder,
                candidates=tuple(batch),
                applied_by_ref=applied_by_ref,
            ),
            tuple(batch),
        )
        batch = [overflow]
        overflow_context = _resolver_batch_context(
            finder_slice=finder_slice,
            finder=finder,
            candidates=tuple(batch),
            applied_by_ref=applied_by_ref,
        )
        if (
            _json_bytes(overflow_context) > maximum_context_bytes
            or _json_bytes(_minimum_resolution_result(tuple(batch))) > maximum_result_bytes
        ):
            raise InvalidRequestError(
                "A detailed Analysis resolver candidate exceeds the bounded stage size."
            )
    if batch:
        yield (
            _resolver_batch_context(
                finder_slice=finder_slice,
                finder=finder,
                candidates=tuple(batch),
                applied_by_ref=applied_by_ref,
            ),
            tuple(batch),
        )


def _resolver_batch_context(
    *,
    finder_slice: _DetailedFinderSlice,
    finder: DetailedAnalysisCandidateFinderResult,
    candidates: tuple[DetailedAnalysisEndpointCandidate, ...],
    applied_by_ref: Mapping[str, AnalysisResultRecord],
) -> JsonValue:
    endpoint_pairs = {
        frozenset((_attribute_key(item.left_attribute), _attribute_key(item.right_attribute)))
        for item in candidates
    }
    relevant_applied = [
        (reference, cast(JsonValue, relationship.model_dump(mode="json")))
        for reference, relationship in applied_by_ref.items()
        if frozenset(
            (
                _relationship_endpoint_key(relationship, "from"),
                _relationship_endpoint_key(relationship, "to"),
            )
        )
        in endpoint_pairs
    ]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "source_slice_ref": finder_slice.slice_ref,
            "source_evidence_manifest": _context_evidence_manifest(finder_slice.context),
            "candidate_finder_result": {
                "schema_version": "1.0",
                "coverage": finder.coverage.model_dump(mode="json"),
                "candidates": [item.model_dump(mode="json") for item in candidates],
            },
            "applied_analysis_manifest": _record_manifest(relevant_applied),
            "applied_analysis_deferred_to_reconciliation": bool(relevant_applied),
        },
    )


def _minimum_resolution_result(
    candidates: tuple[DetailedAnalysisEndpointCandidate, ...],
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "decisions": [
                {
                    "candidate_ref": item.candidate_ref,
                    "disposition": "relationship",
                    "relationship": {
                        **{
                            f"from_{field}": getattr(item.left_attribute, field)
                            for field in (
                                "tenant_code",
                                "system_code",
                                "connection_code",
                                "object_schema",
                                "object_name",
                                "attribute_name",
                            )
                        },
                        **{
                            f"to_{field}": getattr(item.right_attribute, field)
                            for field in (
                                "tenant_code",
                                "system_code",
                                "connection_code",
                                "object_schema",
                                "object_name",
                                "attribute_name",
                            )
                        },
                        "relationship_kind": "reference",
                        "relationship_confidence": "low",
                        "relationship_basis": "x",
                    },
                    "rationale": "x",
                }
                for item in candidates
            ],
        },
    )


def _reconciliation_batches(
    context: AgentContextBundle,
    *,
    decisions: tuple[DetailedAnalysisResolutionDecision, ...],
    applied_by_ref: Mapping[str, AnalysisResultRecord],
    maximum_context_bytes: int,
) -> Iterator[
    tuple[
        JsonValue,
        tuple[DetailedAnalysisResolutionDecision, ...],
        dict[str, AnalysisResultRecord],
    ]
]:
    fragment_bytes = _evidence_fragment_bytes(maximum_context_bytes)
    decision_by_fragment_ref: dict[str, DetailedAnalysisResolutionDecision] = {}
    applied_by_fragment_ref: dict[str, AnalysisResultRecord] = {}
    work_items: list[JsonValue] = []
    manifest_records: list[tuple[str, JsonValue]] = []
    for decision in decisions:
        value = cast(JsonValue, decision.model_dump(mode="json"))
        manifest_records.append((decision.candidate_ref, value))
        for fragment in _record_fragments(
            dataset="analysis_resolution_decision",
            record_ref=decision.candidate_ref,
            value=value,
            maximum_fragment_bytes=fragment_bytes,
        ):
            scoped = decision.model_copy(update={"candidate_ref": fragment.fragment_ref})
            decision_by_fragment_ref[fragment.fragment_ref] = scoped
            work_items.append(
                cast(
                    JsonValue,
                    {
                        "work_item_type": "resolution_fragment",
                        "review_ref": fragment.fragment_ref,
                        "decision_summary": _resolution_decision_summary(scoped),
                        **cast(dict[str, JsonValue], fragment.context_item),
                    },
                )
            )
    for reference, relationship in applied_by_ref.items():
        value = cast(JsonValue, relationship.model_dump(mode="json"))
        manifest_records.append((reference, value))
        for fragment in _record_fragments(
            dataset="applied_analysis",
            record_ref=reference,
            value=value,
            maximum_fragment_bytes=fragment_bytes,
        ):
            applied_by_fragment_ref[fragment.fragment_ref] = relationship
            work_items.append(
                cast(
                    JsonValue,
                    {
                        "work_item_type": "applied_analysis_fragment",
                        "review_ref": fragment.fragment_ref,
                        "relationship_summary": _relationship_summary(relationship),
                        **cast(dict[str, JsonValue], fragment.context_item),
                    },
                )
            )
    pages = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "work_manifest": _record_manifest(manifest_records),
        },
        item_key="reconciliation_work_items",
        items=work_items,
        maximum_bytes=maximum_context_bytes,
    )
    for page in pages:
        raw_items = cast(dict[str, JsonValue], page)["reconciliation_work_items"]
        if not isinstance(raw_items, list):
            raise AgentCandidateValidationError()
        decision_refs = tuple(
            cast(str, item["review_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "resolution_fragment"
        )
        applied_refs = tuple(
            cast(str, item["review_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "applied_analysis_fragment"
        )
        yield (
            page,
            tuple(decision_by_fragment_ref[reference] for reference in decision_refs),
            {reference: applied_by_fragment_ref[reference] for reference in applied_refs},
        )


def _review_batches(
    context: AgentContextBundle,
    *,
    relationships: tuple[AnalysisInferenceRelationship, ...],
    applied_by_ref: Mapping[str, AnalysisResultRecord],
    maximum_context_bytes: int,
) -> Iterator[
    tuple[
        JsonValue,
        tuple[AnalysisInferenceRelationship, ...],
        tuple[str, ...],
        tuple[str, ...],
    ]
]:
    fragment_bytes = _evidence_fragment_bytes(maximum_context_bytes)
    relationship_by_fragment_ref: dict[str, AnalysisInferenceRelationship] = {}
    applied_by_fragment_ref: dict[str, AnalysisResultRecord] = {}
    work_items: list[JsonValue] = []
    manifest_records: list[tuple[str, JsonValue]] = []
    for position, relationship in enumerate(relationships, start=1):
        reference = f"relationship_{position:05d}"
        value = cast(JsonValue, relationship.model_dump(mode="json"))
        manifest_records.append((reference, value))
        for fragment in _record_fragments(
            dataset="reconciled_analysis",
            record_ref=reference,
            value=value,
            maximum_fragment_bytes=fragment_bytes,
        ):
            relationship_by_fragment_ref[fragment.fragment_ref] = relationship
            work_items.append(
                cast(
                    JsonValue,
                    {
                        "work_item_type": "relationship_fragment",
                        "review_ref": fragment.fragment_ref,
                        "relationship_summary": _relationship_summary(relationship),
                        **cast(dict[str, JsonValue], fragment.context_item),
                    },
                )
            )
    for reference, relationship in applied_by_ref.items():
        value = cast(JsonValue, relationship.model_dump(mode="json"))
        manifest_records.append((reference, value))
        for fragment in _record_fragments(
            dataset="applied_analysis",
            record_ref=reference,
            value=value,
            maximum_fragment_bytes=fragment_bytes,
        ):
            applied_by_fragment_ref[fragment.fragment_ref] = relationship
            work_items.append(
                cast(
                    JsonValue,
                    {
                        "work_item_type": "applied_analysis_fragment",
                        "review_ref": fragment.fragment_ref,
                        "relationship_summary": _relationship_summary(relationship),
                        **cast(dict[str, JsonValue], fragment.context_item),
                    },
                )
            )
    pages = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "work_manifest": _record_manifest(manifest_records),
        },
        item_key="review_work_items",
        items=work_items,
        maximum_bytes=maximum_context_bytes,
    )
    for page in pages:
        raw_items = cast(dict[str, JsonValue], page)["review_work_items"]
        if not isinstance(raw_items, list):
            raise AgentCandidateValidationError()
        relationship_refs = tuple(
            cast(str, item["review_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "relationship_fragment"
        )
        applied_refs = tuple(
            cast(str, item["review_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "applied_analysis_fragment"
        )
        yield (
            page,
            tuple(relationship_by_fragment_ref[reference] for reference in relationship_refs),
            relationship_refs,
            applied_refs,
        )


def _detailed_resolver_values(
    *,
    stage_code: str,
    stage_context: JsonValue,
) -> dict[str, object]:
    return {
        f"workflow.analysis.detailed_coverage.{stage_code}.context": stage_context,
        "workflow.validation_failures": [],
    }


def _detailed_stage_context_limit(policy: AgentContextPolicy) -> int:
    maximum_bytes = min(64 * 1024, policy.stage_max_context_bytes // 8)
    if maximum_bytes < 4_096:
        raise InvalidRequestError("The detailed Analysis context limit is too small.")
    return maximum_bytes


def _fragmented_evidence_pages(
    *,
    base: dict[str, JsonValue],
    item_key: str,
    records: list[tuple[str, str, JsonValue]],
    maximum_bytes: int,
) -> tuple[JsonValue, ...]:
    fragment_bytes = _evidence_fragment_bytes(maximum_bytes)
    fragments = tuple(
        fragment.context_item
        for dataset, record_ref, value in records
        for fragment in _record_fragments(
            dataset=dataset,
            record_ref=record_ref,
            value=value,
            maximum_fragment_bytes=fragment_bytes,
        )
    )
    return _pack_context_items(
        base={
            **base,
            "evidence_manifest": _record_manifest(
                [(f"{dataset}:{record_ref}", value) for dataset, record_ref, value in records]
            ),
        },
        item_key=item_key,
        items=list(fragments),
        maximum_bytes=maximum_bytes,
    )


def _record_fragments(
    *,
    dataset: str,
    record_ref: str,
    value: JsonValue,
    maximum_fragment_bytes: int,
) -> tuple[_DetailedEvidenceFragment, ...]:
    text = _canonical_json(value)
    encoded = text.encode("utf-8")
    digest = sha256(encoded).hexdigest()
    parts = _split_utf8(text, maximum_fragment_bytes)
    fragments: list[_DetailedEvidenceFragment] = []
    for index, part in enumerate(parts, start=1):
        fragment_ref = _bounded_fragment_ref(
            record_ref,
            fragment_index=index,
            fragment_count=len(parts),
        )
        fragments.append(
            _DetailedEvidenceFragment(
                dataset=dataset,
                record_ref=record_ref,
                fragment_ref=fragment_ref,
                value=value,
                context_item=cast(
                    JsonValue,
                    {
                        "dataset": dataset,
                        "record_ref": record_ref,
                        "record_sha256": digest,
                        "record_byte_count": len(encoded),
                        "fragment_index": index,
                        "fragment_count": len(parts),
                        "json_text": part,
                    },
                ),
            )
        )
    return tuple(fragments)


def _pack_context_items(
    *,
    base: dict[str, JsonValue],
    item_key: str,
    items: list[JsonValue],
    maximum_bytes: int,
) -> tuple[JsonValue, ...]:
    pages: list[list[JsonValue]] = []
    current: list[JsonValue] = []
    candidates: tuple[JsonValue | None, ...] = tuple(items) or (None,)
    for item in candidates:
        trial_items = current if item is None else [*current, item]
        trial = cast(
            JsonValue,
            {
                **base,
                item_key: trial_items,
                "page": {"index": 99_999, "count": 99_999},
            },
        )
        if _json_bytes(trial) <= maximum_bytes:
            current = trial_items
            continue
        if not current:
            raise InvalidRequestError(
                "A detailed Analysis evidence fragment exceeds the bounded stage size."
            )
        pages.append(current)
        current = [] if item is None else [item]
        single = cast(
            JsonValue,
            {
                **base,
                item_key: current,
                "page": {"index": 99_999, "count": 99_999},
            },
        )
        if _json_bytes(single) > maximum_bytes:
            raise InvalidRequestError(
                "A detailed Analysis evidence fragment exceeds the bounded stage size."
            )
    pages.append(current)
    page_count = len(pages)
    contexts = tuple(
        cast(
            JsonValue,
            {
                **base,
                item_key: page,
                "page": {"index": index, "count": page_count},
            },
        )
        for index, page in enumerate(pages, start=1)
    )
    if any(_json_bytes(item) > maximum_bytes for item in contexts):
        raise InvalidRequestError("A detailed Analysis context page exceeds its safe byte limit.")
    return contexts


def _record_manifest(records: list[tuple[str, JsonValue]]) -> JsonValue:
    entries = [
        {
            "record_ref": reference,
            "record_sha256": sha256(_canonical_json(value).encode("utf-8")).hexdigest(),
            "record_byte_count": _json_bytes(value),
        }
        for reference, value in records
    ]
    return cast(
        JsonValue,
        {
            "record_count": len(records),
            "record_byte_count": sum(cast(int, item["record_byte_count"]) for item in entries),
            "records_sha256": sha256(
                _canonical_json(cast(JsonValue, entries)).encode("utf-8")
            ).hexdigest(),
        },
    )


def _context_evidence_manifest(context: JsonValue) -> JsonValue:
    if isinstance(context, dict):
        manifest = context.get("evidence_manifest")
        if isinstance(manifest, dict):
            return cast(JsonValue, manifest)
    return _record_manifest([("source_slice", context)])


def _resolution_decision_summary(
    decision: DetailedAnalysisResolutionDecision,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "candidate_ref": decision.candidate_ref,
            "disposition": decision.disposition,
            "relationship": (
                None
                if decision.relationship is None
                else _relationship_summary(decision.relationship)
            ),
        },
    )


def _relationship_summary(
    relationship: AnalysisInferenceRelationship | AnalysisResultRecord,
) -> JsonValue:
    basis = relationship.relationship_basis
    return cast(
        JsonValue,
        {
            **{
                f"{endpoint}_{field}": getattr(relationship, f"{endpoint}_{field}")
                for endpoint in ("from", "to")
                for field in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "attribute_name",
                )
            },
            "relationship_kind": relationship.relationship_kind,
            "relationship_confidence": relationship.relationship_confidence,
            "relationship_basis_sha256": sha256(basis.encode("utf-8")).hexdigest(),
            "relationship_basis_byte_count": len(basis.encode("utf-8")),
            "analysis_result_status": getattr(relationship, "analysis_result_status", None),
            "analysis_result_is_locked": getattr(relationship, "analysis_result_is_locked", None),
        },
    )


def _physical_attribute_json(value: Mapping[str, JsonValue]) -> JsonValue:
    return cast(
        JsonValue,
        {
            field: value[field]
            for field in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
                "attribute_name",
            )
        },
    )


def _evidence_fragment_bytes(maximum_context_bytes: int) -> int:
    return max(128, min(8 * 1024, maximum_context_bytes // 8))


def _bounded_fragment_ref(
    record_ref: str,
    *,
    fragment_index: int,
    fragment_count: int,
) -> str:
    if fragment_count == 1:
        return record_ref
    suffix = f"_fragment_{fragment_index:05d}"
    if len(record_ref) + len(suffix) <= 100:
        return f"{record_ref}{suffix}"
    digest = sha256(record_ref.encode("utf-8")).hexdigest()[:12]
    return f"{record_ref[:70]}_fragment_{fragment_index:05d}_{digest}"


def _split_utf8(value: str, maximum_bytes: int) -> tuple[str, ...]:
    if maximum_bytes < 1:
        raise ValueError("UTF-8 fragment limit must be positive")
    data = value.encode("utf-8")
    if not data:
        return ("",)
    parts: list[str] = []
    offset = 0
    while offset < len(data):
        end = min(len(data), offset + maximum_bytes)
        while end > offset:
            try:
                parts.append(data[offset:end].decode("utf-8"))
                offset = end
                break
            except UnicodeDecodeError:
                end -= 1
        else:
            raise ValueError("UTF-8 fragment limit cannot contain one code point")
    return tuple(parts)


def _merge_inference_relationships(
    first: AnalysisInferenceRelationship,
    second: AnalysisInferenceRelationship,
) -> AnalysisInferenceRelationship:
    if _inference_relationship_key(first) != _inference_relationship_key(second):
        raise AgentCandidateValidationError()
    first_json = cast(JsonValue, first.model_dump(mode="json"))
    second_json = cast(JsonValue, second.model_dump(mode="json"))
    return first if _canonical_json(first_json) <= _canonical_json(second_json) else second


def _attribute_key(record: object) -> tuple[str, ...]:
    return tuple(
        normalize_model_key_value(cast(str, getattr(record, field)))
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
        )
    )


def _relationship_endpoint_key(
    relationship: AnalysisResultRecord,
    endpoint: Literal["from", "to"],
) -> tuple[str, ...]:
    return tuple(
        normalize_model_key_value(cast(str, getattr(relationship, f"{endpoint}_{field}")))
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
        )
    )


def _inference_relationship_key(
    relationship: AnalysisInferenceRelationship | AnalysisResultRecord,
) -> tuple[str, ...]:
    return tuple(
        normalize_model_key_value(cast(str, getattr(relationship, field)))
        for field in (
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
            "relationship_kind",
        )
    )


def _json_bytes(value: JsonValue) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return AnalysisInferenceFinalizationFailedError()
    return AnalysisInferenceExecutionFailedError()


__all__ = [
    "AnalysisInferenceExecutionFailedError",
    "AnalysisInferenceFinalizationFailedError",
    "AnalysisInferenceWorkflow",
    "DatabaseAnalysisInferenceExecutor",
]
