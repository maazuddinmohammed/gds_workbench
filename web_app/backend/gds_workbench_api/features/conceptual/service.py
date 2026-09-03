"""Execute one already-running Conceptual authoring run."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    ObjectSupportRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ProfilingProfileRecord,
    SupportRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
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
from gds_workbench_api.features.workflows.authoring.naming import (
    effective_naming_instructions,
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
from gds_workbench_api.features.workflows.authoring.progress import (
    AgentWorkflowProgress,
    intermediate_progress_points,
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

from .candidate import ConceptualCandidateValidator
from .detailed import (
    DetailedConceptualPolicy,
    DetailedConsolidatedEntity,
    DetailedEntityConsolidation,
    DetailedEntityConsolidationValidator,
    DetailedEntityDetail,
    DetailedEntityDetailValidator,
    DetailedEntityProposal,
    DetailedObjectContribution,
    DetailedObjectContributionValidator,
    DetailedReconciliationValidator,
    DetailedRelationshipPackage,
    DetailedRelationshipRefinement,
    DetailedRelationshipRefinementValidator,
    conceptual_applied_record_refs,
    derive_relationship_packages,
    load_default_detailed_conceptual_policy,
)

_logger = logging.getLogger(__name__)


class ConceptualExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class ConceptualPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class ConceptualContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle: ...


class ConceptualChangeSetHandoff(Protocol):
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


class ConceptualNoOpCompleter(Protocol):
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


class ConceptualLifecycle(Protocol):
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


class ConceptualExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_execution_failed",
            message=("Conceptual authoring failed before a validated draft was committed."),
        )


class ConceptualFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="conceptual_finalization_failed",
            message="Conceptual finalization outcome could not be confirmed.",
        )


type ConceptualExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class ConceptualRunLifecycle(Protocol):
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


class ConceptualExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> ConceptualExecutionResult: ...


class ConceptualWorkflow:
    """Bind the public route to one explicit supported Conceptual mode."""

    def __init__(
        self,
        *,
        lifecycle: ConceptualRunLifecycle,
        executor: ConceptualExecutor,
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
            expected_workflow="conceptual",
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
    ) -> ConceptualExecutionResult:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseConceptualExecutor:
    """Load frozen inputs, repair one candidate, and hand off one validated draft."""

    def __init__(
        self,
        *,
        database: ConceptualExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: ConceptualChangeSetHandoff,
        no_op: ConceptualNoOpCompleter,
        lifecycle: ConceptualLifecycle,
        plan_repository: ConceptualPlanRepository | None = None,
        context_repository: ConceptualContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
        detailed_policy: DetailedConceptualPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresAgentContextRepository()
        self._context_policy = context_policy or load_default_agent_context_policy()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=self._context_policy,
        )
        self._handoff = handoff
        self._no_op = no_op
        self._lifecycle = lifecycle
        self._detailed_policy = detailed_policy or load_default_detailed_conceptual_policy()

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> ConceptualExecutionResult:
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
            selected_object_count = len(context.context.selected_objects)
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage=(
                    "conceptual.object_contribution"
                    if is_detailed
                    else "conceptual.candidate_authoring"
                ),
                status="running",
                message=(
                    f"Detailed Conceptual coverage started for {selected_object_count} "
                    "selected Objects."
                    if is_detailed
                    else (
                        f"Conceptual candidate authoring started for {selected_object_count} "
                        "selected Objects. The next persisted milestone follows bounded "
                        "agent response validation."
                    )
                ),
                current=0 if selected_object_count else None,
                total=selected_object_count or None,
                finding_count=0,
            )

            validator = _candidate_validator(context)
            if is_detailed:
                (
                    candidate,
                    outcome,
                    intermediate_warning,
                    final_attempt,
                ) = await self._execute_detailed(
                    plan=plan,
                    context=context,
                    validator=validator,
                    progress=progress,
                )
            elif execution_mode in ("one_shot", "tool_assisted"):
                resolver_key = f"workflow.conceptual.{execution_mode}.candidate_authoring.context"
                resolver_values: dict[str, object] = {
                    resolver_key: context.embedded_context,
                    "workflow.validation_failures": [],
                }
                resolver_values["model.naming_instructions"] = effective_naming_instructions(
                    "conceptual",
                    context.context.model_details.silver_model_naming_instructions,
                )
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
                final_attempt = outcome.attempt_count
            else:
                raise InvalidRequestError(
                    "The Conceptual run does not use the fixed execution path."
                )
            changes = validator.parse_validated(candidate)
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
                        expected_workflow="conceptual",
                        expected_execution_mode=execution_mode,
                        expected_correlation_id=plan.correlation_id,
                        expected_model_revision=expected_model_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=final_attempt,
                            stage="conceptual.backend_validation",
                            status="warning" if warning else "running",
                            message=("Conceptual authoring completed with no effective change."),
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
                expected_workflow="conceptual",
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=progress.event(
                    attempt=final_attempt,
                    stage="conceptual.backend_validation",
                    status="warning" if warning else "running",
                    message="Conceptual candidate is ready in a validated draft.",
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
                    "Conceptual Workflow Run finalization remains pending.",
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
                        "Conceptual failure state could not be persisted.",
                        extra={
                            "workflow_run_id": workflow_run_id,
                            "model_id": model_id,
                            "failure_code": safe_error.code[:100],
                        },
                    )
            raise safe_error from None

    async def _execute_detailed(
        self,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        validator: ConceptualCandidateValidator,
        progress: AgentWorkflowProgress,
    ) -> tuple[JsonValue, AgentStageOutcome, bool, int]:
        stage_context_limit = _detailed_stage_context_limit(self._context_policy)
        contributions: list[DetailedObjectContribution] = []
        selected_by_contribution_ref: dict[str, SelectedObjectContext] = {}
        intermediate_warning = False
        max_attempt = 1
        selected_objects = context.context.selected_objects
        object_progress_points = intermediate_progress_points(
            len(selected_objects),
            maximum_events=5,
        )
        for selected_index, selected in enumerate(selected_objects):
            contribution_contexts = _object_contribution_contexts(
                context,
                selected=selected,
                include_global_evidence=selected_index == 0,
                analysis_relationships=_owned_analysis_relationships(
                    context,
                    selected=selected,
                ),
                maximum_bytes=stage_context_limit,
            )
            for contribution_ref, stage_context in contribution_contexts:
                selected_by_contribution_ref[contribution_ref] = selected
                contribution_validator = DetailedObjectContributionValidator(
                    contribution_ref=contribution_ref,
                    source_object=_physical_object_key(selected),
                )
                outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="object_contribution",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="object_contribution",
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
                    or contribution.disposition == "blocked"
                    or outcome.was_repaired
                    or bool(outcome.warning_codes)
                )
            completed_object_count = selected_index + 1
            if completed_object_count in object_progress_points:
                await progress.append(
                    attempt=max_attempt,
                    stage="conceptual.object_contribution",
                    status="warning" if intermediate_warning else "running",
                    message=(
                        f"Object contribution coverage processed {completed_object_count} of "
                        f"{len(selected_objects)} selected Objects."
                    ),
                    current=completed_object_count,
                    total=len(selected_objects),
                    finding_count=0,
                )
        if object_progress_points:
            await progress.append(
                attempt=max_attempt,
                stage="conceptual.object_contribution",
                status="warning" if intermediate_warning else "running",
                message=(
                    f"Object contribution coverage completed {len(selected_objects)} of "
                    f"{len(selected_objects)} selected Objects."
                ),
                current=len(selected_objects),
                total=len(selected_objects),
                finding_count=len(contributions),
            )

        await progress.append(
            attempt=1,
            stage="conceptual.entity_consolidation",
            status="warning" if intermediate_warning else "running",
            message="Input coverage is ready for business-concept consolidation.",
            current=len(contributions),
            total=len(contributions),
            finding_count=len(contributions),
        )
        consolidation_parts: list[DetailedEntityConsolidation] = []
        consolidation_context_count = sum(
            1
            for _ in _consolidation_contexts(
                context,
                contributions=tuple(contributions),
                maximum_bytes=stage_context_limit,
            )
        )
        consolidation_progress_points = intermediate_progress_points(
            consolidation_context_count,
            maximum_events=2,
        )
        for consolidation_index, (
            consolidation_context,
            scoped_contributions,
        ) in enumerate(
            _consolidation_contexts(
                context,
                contributions=tuple(contributions),
                maximum_bytes=stage_context_limit,
            ),
            start=1,
        ):
            consolidation_validator = DetailedEntityConsolidationValidator(
                contributions=scoped_contributions
            )
            consolidation_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="entity_consolidation",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="entity_consolidation",
                    stage_context=consolidation_context,
                ),
                context=consolidation_context,
                output_schema=consolidation_validator.output_schema(),
                allowed_tool_names=(),
                validator=consolidation_validator,
            )
            consolidation_parts.append(
                consolidation_validator.parse_validated(consolidation_outcome.candidate)
            )
            max_attempt = max(max_attempt, consolidation_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or consolidation_outcome.was_repaired
                or bool(consolidation_outcome.warning_codes)
            )
            if consolidation_index in consolidation_progress_points:
                await progress.append(
                    attempt=consolidation_outcome.attempt_count,
                    stage="conceptual.entity_consolidation",
                    status="warning" if intermediate_warning else "running",
                    message=(
                        f"Concept consolidation processed {consolidation_index} of "
                        f"{consolidation_context_count} bounded batches."
                    ),
                    current=consolidation_index,
                    total=consolidation_context_count,
                    finding_count=0,
                )
        consolidation = _merge_consolidations(
            parts=tuple(consolidation_parts),
            contributions=tuple(contributions),
        )
        if consolidation_progress_points:
            await progress.append(
                attempt=max_attempt,
                stage="conceptual.entity_consolidation",
                status="warning" if intermediate_warning else "running",
                message=(
                    f"Concept consolidation completed {consolidation_context_count} of "
                    f"{consolidation_context_count} bounded batches."
                ),
                current=consolidation_context_count,
                total=consolidation_context_count,
                finding_count=len(consolidation.entities),
            )

        await progress.append(
            attempt=1,
            stage="conceptual.entity_attribute_detail",
            status="warning" if intermediate_warning else "running",
            message="Consolidated business concepts are ready for detailed authoring.",
            current=0 if consolidation.entities else None,
            total=(len(consolidation.entities) if consolidation.entities else None),
            finding_count=len(consolidation.entities),
        )
        details: list[DetailedEntityDetail] = []
        entity_progress_points = intermediate_progress_points(
            len(consolidation.entities),
            maximum_events=2,
        )
        for entity_index, entity in enumerate(consolidation.entities, start=1):
            detail_parts: list[DetailedEntityDetail] = []
            for detail_context, scoped_entity, scoped_contributions in _detail_contexts(
                context,
                entity=entity,
                contributions=tuple(contributions),
                selected_by_contribution_ref=selected_by_contribution_ref,
                maximum_bytes=stage_context_limit,
            ):
                detail_validator = DetailedEntityDetailValidator(
                    entity=scoped_entity,
                    contributions=scoped_contributions,
                )
                detail_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="entity_attribute_detail",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="entity_attribute_detail",
                        stage_context=detail_context,
                    ),
                    context=detail_context,
                    output_schema=detail_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=detail_validator,
                )
                detail_parts.append(detail_validator.parse_validated(detail_outcome.candidate))
                max_attempt = max(max_attempt, detail_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or detail_outcome.was_repaired
                    or bool(detail_outcome.warning_codes)
                )
            details.append(
                _merge_entity_details(
                    parts=tuple(detail_parts),
                    entity=entity,
                    contributions=tuple(contributions),
                )
            )
            if entity_index in entity_progress_points:
                await progress.append(
                    attempt=max_attempt,
                    stage="conceptual.entity_attribute_detail",
                    status="warning" if intermediate_warning else "running",
                    message=(
                        f"Concept detail authoring processed {entity_index} of "
                        f"{len(consolidation.entities)} consolidated concepts."
                    ),
                    current=entity_index,
                    total=len(consolidation.entities),
                    finding_count=0,
                )
        if entity_progress_points:
            await progress.append(
                attempt=max_attempt,
                stage="conceptual.entity_attribute_detail",
                status="warning" if intermediate_warning else "running",
                message=(
                    f"Concept detail authoring completed {len(consolidation.entities)} of "
                    f"{len(consolidation.entities)} consolidated concepts."
                ),
                current=len(consolidation.entities),
                total=len(consolidation.entities),
                finding_count=len(details),
            )

        attributes = tuple(
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
        relationship_packages = derive_relationship_packages(
            entity_details=tuple(details),
            attributes=attributes,
            analysis_relationships=context.context.analysis_relationships,
            max_packages=self._detailed_policy.max_relationship_packages,
        )
        await progress.append(
            attempt=1,
            stage="conceptual.relationship_candidate_derivation",
            status="warning" if intermediate_warning else "running",
            message="Deterministic relationship evidence packages are ready.",
            current=(len(relationship_packages) if relationship_packages else None),
            total=(len(relationship_packages) if relationship_packages else None),
            finding_count=len(relationship_packages),
        )

        refinements: list[DetailedRelationshipRefinement] = []
        package_progress_points = intermediate_progress_points(
            len(relationship_packages),
            maximum_events=2,
        )
        for package_index, package in enumerate(relationship_packages, start=1):
            refinement_parts: list[DetailedRelationshipRefinement] = []
            for refinement_context, scoped_package, endpoint_details in _refinement_contexts(
                context,
                package=package,
                entity_details=tuple(details),
                maximum_bytes=stage_context_limit,
            ):
                refinement_validator = DetailedRelationshipRefinementValidator(
                    package=scoped_package,
                    entity_details=endpoint_details,
                )
                refinement_outcome = await self._stage_runner.run(
                    plan=plan,
                    stage_code="relationship_cardinality_refinement",
                    resolver_values=_detailed_resolver_values(
                        context,
                        stage_code="relationship_cardinality_refinement",
                        stage_context=refinement_context,
                    ),
                    context=refinement_context,
                    output_schema=refinement_validator.output_schema(),
                    allowed_tool_names=(),
                    validator=refinement_validator,
                )
                refinement_parts.append(
                    refinement_validator.parse_validated(refinement_outcome.candidate)
                )
                max_attempt = max(max_attempt, refinement_outcome.attempt_count)
                intermediate_warning = (
                    intermediate_warning
                    or refinement_outcome.was_repaired
                    or bool(refinement_outcome.warning_codes)
                )
            refinements.append(
                _merge_relationship_refinements(
                    parts=tuple(refinement_parts),
                    package=package,
                    entity_details=tuple(details),
                )
            )
            if package_index in package_progress_points:
                await progress.append(
                    attempt=max_attempt,
                    stage="conceptual.relationship_cardinality_refinement",
                    status="warning" if intermediate_warning else "running",
                    message=(
                        f"Relationship refinement processed {package_index} of "
                        f"{len(relationship_packages)} evidence packages."
                    ),
                    current=package_index,
                    total=len(relationship_packages),
                    finding_count=0,
                )
        if package_progress_points:
            await progress.append(
                attempt=max_attempt,
                stage="conceptual.relationship_cardinality_refinement",
                status="warning" if intermediate_warning else "running",
                message=(
                    f"Relationship refinement completed {len(relationship_packages)} of "
                    f"{len(relationship_packages)} evidence packages."
                ),
                current=len(relationship_packages),
                total=len(relationship_packages),
                finding_count=len(refinements),
            )

        await progress.append(
            attempt=1,
            stage="conceptual.relationship_cardinality_refinement",
            status="warning" if intermediate_warning else "running",
            message="Relationship packages are ready for whole-model reconciliation.",
            current=(len(refinements) if refinements else None),
            total=(len(relationship_packages) if relationship_packages else None),
            finding_count=len(refinements),
        )

        reconciliation_context_count = sum(
            1
            for _ in _reconciliation_contexts(
                context,
                contributions=tuple(contributions),
                consolidation=consolidation,
                entity_details=tuple(details),
                relationship_packages=relationship_packages,
                relationship_refinements=tuple(refinements),
                maximum_bytes=stage_context_limit,
            )
        )
        await progress.append(
            attempt=1,
            stage="conceptual.whole_model_reconciliation",
            status="warning" if intermediate_warning else "running",
            message="Whole-model reconciliation and backend validation started.",
            current=0 if reconciliation_context_count else None,
            total=reconciliation_context_count or None,
            finding_count=len(details) + len(refinements),
        )
        reconciled_candidates: list[JsonValue] = []
        final_outcome: AgentStageOutcome | None = None
        reconciliation_progress_points = intermediate_progress_points(
            reconciliation_context_count,
            maximum_events=2,
        )
        for reconciliation_index, (
            reconciliation_context,
            scoped_details,
            scoped_input_refs,
            scoped_package_refs,
            scoped_applied_refs,
        ) in enumerate(
            _reconciliation_contexts(
                context,
                contributions=tuple(contributions),
                consolidation=consolidation,
                entity_details=tuple(details),
                relationship_packages=relationship_packages,
                relationship_refinements=tuple(refinements),
                maximum_bytes=stage_context_limit,
            ),
            start=1,
        ):
            reconciliation_validator = DetailedReconciliationValidator(
                entity_details=scoped_details,
                input_contribution_refs=scoped_input_refs,
                relationship_package_refs=scoped_package_refs,
                applied_record_refs=scoped_applied_refs,
            )
            final_outcome = await self._stage_runner.run(
                plan=plan,
                stage_code="whole_model_reconciliation",
                resolver_values=_detailed_resolver_values(
                    context,
                    stage_code="whole_model_reconciliation",
                    stage_context=reconciliation_context,
                    include_validation_failures=True,
                ),
                context=reconciliation_context,
                output_schema=reconciliation_validator.output_schema(),
                allowed_tool_names=(),
                validator=reconciliation_validator,
            )
            reconciled_candidates.append(
                reconciliation_validator.materialize_validated(final_outcome.candidate)
            )
            max_attempt = max(max_attempt, final_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or final_outcome.was_repaired
                or bool(final_outcome.warning_codes)
            )
            if reconciliation_index in reconciliation_progress_points:
                await progress.append(
                    attempt=final_outcome.attempt_count,
                    stage="conceptual.whole_model_reconciliation",
                    status="warning" if intermediate_warning else "running",
                    message=(
                        f"Whole-model reconciliation processed {reconciliation_index} of "
                        f"{reconciliation_context_count} bounded batches."
                    ),
                    current=reconciliation_index,
                    total=reconciliation_context_count,
                    finding_count=0,
                )
        if final_outcome is None:
            raise AgentCandidateValidationError()
        candidate = _merge_reconciled_candidates(
            reconciled_candidates,
            entity_details=tuple(details),
        )
        if (await validator.validate(candidate)).issues:
            raise AgentCandidateValidationError()
        if reconciliation_progress_points:
            await progress.append(
                attempt=max_attempt,
                stage="conceptual.whole_model_reconciliation",
                status="warning" if intermediate_warning else "running",
                message=(
                    f"Whole-model reconciliation completed {reconciliation_context_count} of "
                    f"{reconciliation_context_count} bounded batches."
                ),
                current=reconciliation_context_count,
                total=reconciliation_context_count,
                finding_count=len(reconciled_candidates),
            )
        return (
            candidate,
            final_outcome,
            intermediate_warning,
            max_attempt,
        )

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
                "object_contribution",
                "entity_consolidation",
                "entity_attribute_detail",
                "relationship_cardinality_refinement",
                "whole_model_reconciliation",
            )
        )
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "conceptual"
            or plan.modeled_entity_type is not None
            or not mode_path_is_valid
        ):
            raise InvalidRequestError("The Conceptual run does not use the fixed execution path.")


def _candidate_validator(context: AgentContextBundle) -> ConceptualCandidateValidator:
    selected = tuple(
        PhysicalObjectKey(
            tenant_code=item.object.tenant_code,
            system_code=item.object.system_code,
            connection_code=item.object.connection_code,
            object_schema=item.object.object_schema,
            object_name=item.object.object_name,
        )
        for item in context.context.selected_objects
    )
    assertion_keys = tuple(
        record.modeling_assertion_record_key for record in context.context.assertion.records
    )
    return ConceptualCandidateValidator(
        selected_object_keys=selected,
        assertion_record_keys=assertion_keys,
        applied=context.context.applied.conceptual,
    )


def _detailed_resolver_values(
    context: AgentContextBundle,
    *,
    stage_code: str,
    stage_context: JsonValue,
    include_validation_failures: bool = False,
) -> dict[str, object]:
    values: dict[str, object] = {
        f"workflow.conceptual.detailed_coverage.{stage_code}.context": stage_context
    }
    values["model.naming_instructions"] = effective_naming_instructions(
        "conceptual",
        context.context.model_details.silver_model_naming_instructions,
    )
    if include_validation_failures:
        values["workflow.validation_failures"] = []
    return values


def _detailed_model_context(context: AgentContextBundle) -> JsonValue:
    return cast(
        JsonValue,
        {
            "model_id": context.context.model_id,
            "model_name": context.context.model_name,
            "model_revision": context.context.model_revision,
            "model_description": context.context.model_details.model_description,
            "conceptual_authoring_guidance": {
                "purpose": (
                    "Create a compact business view of important concepts and their "
                    "business relationships."
                ),
                "grouping": (
                    "Many selected physical Objects may support one Conceptual concept; "
                    "never create one concept per Object merely for coverage."
                ),
                "excluded_structure": (
                    "Do not model physical columns, keys, normalization, table design, "
                    "dependency order, or a copy of the Logical Model."
                ),
                "coverage_dispositions": [
                    "represented",
                    "context_only",
                    "excluded",
                    "blocked",
                ],
                "relationship_rule": (
                    "Use business meaning and supported Analysis or Assertions first; "
                    "matching physical names are supporting evidence only."
                ),
            },
        },
    )


def _detailed_stage_context_limit(policy: AgentContextPolicy) -> int:
    """Reserve prompt, schema, JSON escaping, and repair headroom."""

    return max(1, min(64 * 1024, policy.stage_max_context_bytes // 8))


def _object_contribution_contexts(
    context: AgentContextBundle,
    *,
    selected: SelectedObjectContext,
    include_global_evidence: bool,
    analysis_relationships: tuple[AnalysisResultRecord, ...],
    maximum_bytes: int,
) -> tuple[tuple[str, JsonValue], ...]:
    base_ref = f"object_{selected.selection_order}"
    if len(context.context.selected_objects) == 1:
        legacy = _object_contribution_context(
            context,
            selected=selected,
            contribution_ref=base_ref,
        )
        if _json_bytes(legacy) <= maximum_bytes:
            return ((base_ref, legacy),)

    records: list[tuple[str, str, JsonValue]] = [
        (
            "selected_object",
            base_ref,
            cast(JsonValue, selected.model_dump(mode="json")),
        )
    ]
    records.extend(
        (
            "profile",
            _attribute_record_ref(profile),
            cast(JsonValue, profile.model_dump(mode="json")),
        )
        for profile in context.context.profiles
        if _profile_matches_selected(profile, selected)
    )
    records.extend(
        (
            "analysis_relationship",
            f"analysis_{index:05d}",
            cast(JsonValue, relationship.model_dump(mode="json")),
        )
        for index, relationship in enumerate(analysis_relationships, start=1)
    )
    if include_global_evidence:
        records.extend(
            (
                "assertion_document",
                f"assertion_document_{index:05d}",
                cast(JsonValue, document.model_dump(mode="json")),
            )
            for index, document in enumerate(
                context.context.assertion.documents,
                start=1,
            )
        )
        records.extend(
            (
                "assertion_record",
                record.modeling_assertion_record_key,
                cast(JsonValue, record.model_dump(mode="json")),
            )
            for record in context.context.assertion.records
        )
        applied = context.context.applied.conceptual
        if applied is not None:
            records.extend(
                (
                    "applied_conceptual_object",
                    f"object:{normalize_model_key_value(record.conceptual_object_name)}",
                    cast(JsonValue, record.model_dump(mode="json")),
                )
                for record in applied.objects
            )
            records.extend(
                (
                    "applied_conceptual_relationship",
                    _relationship_record_ref(record),
                    cast(JsonValue, record.model_dump(mode="json")),
                )
                for record in applied.relationships
            )

    fragment_bytes = max(128, min(8 * 1024, maximum_bytes // 4))
    fragments = [
        fragment
        for dataset, record_ref, value in records
        for fragment in _json_record_fragments(
            dataset=dataset,
            record_ref=record_ref,
            value=value,
            maximum_fragment_bytes=fragment_bytes,
        )
    ]
    page_contexts = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "contribution_ref": f"{base_ref}_page_99999",
            "source_object": cast(
                JsonValue,
                _physical_object_key(selected).model_dump(mode="json"),
            ),
            "global_evidence_included": include_global_evidence,
        },
        item_key="evidence_fragments",
        items=fragments,
        maximum_bytes=maximum_bytes,
    )
    page_count = len(page_contexts)
    results: list[tuple[str, JsonValue]] = []
    for page_index, raw_context in enumerate(page_contexts, start=1):
        contribution_ref = base_ref if page_count == 1 else f"{base_ref}_page_{page_index:05d}"
        stage_context = cast(dict[str, JsonValue], raw_context)
        stage_context["contribution_ref"] = contribution_ref
        if _json_bytes(cast(JsonValue, stage_context)) > maximum_bytes:
            raise InvalidRequestError(
                "A Conceptual Object contribution page exceeds its safe byte limit."
            )
        results.append((contribution_ref, cast(JsonValue, stage_context)))
    return tuple(results)


def _object_contribution_context(
    context: AgentContextBundle,
    *,
    selected: SelectedObjectContext,
    contribution_ref: str,
) -> JsonValue:
    profiles = [
        profile.model_dump(mode="json")
        for profile in context.context.profiles
        if _profile_matches_selected(profile, selected)
    ]
    relationships = [
        relationship.model_dump(mode="json")
        for relationship in context.context.analysis_relationships
        if _analysis_matches_selected(relationship, selected)
    ]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "contribution_ref": contribution_ref,
            "selected_object": selected.model_dump(mode="json"),
            "profiles": profiles,
            "analysis_relationships": relationships,
            "assertions": context.context.assertion.model_dump(mode="json"),
            "applied_conceptual": (
                None
                if context.context.applied.conceptual is None
                else context.context.applied.conceptual.model_dump(mode="json")
            ),
        },
    )


def _owned_analysis_relationships(
    context: AgentContextBundle,
    *,
    selected: SelectedObjectContext,
) -> tuple[AnalysisResultRecord, ...]:
    selected_order_by_identity = {
        _selected_identity(item): item.selection_order for item in context.context.selected_objects
    }
    owned: list[AnalysisResultRecord] = []
    for relationship in context.context.analysis_relationships:
        endpoint_identities = (
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
        )
        owners = sorted(
            selected_order_by_identity[identity]
            for identity in endpoint_identities
            if identity in selected_order_by_identity
        )
        if owners and owners[0] == selected.selection_order:
            owned.append(relationship)
    return tuple(owned)


def _consolidation_contexts(
    context: AgentContextBundle,
    *,
    contributions: tuple[DetailedObjectContribution, ...],
    maximum_bytes: int,
) -> tuple[tuple[JsonValue, tuple[DetailedObjectContribution, ...]], ...]:
    legacy = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "contributions": [item.model_dump(mode="json") for item in contributions],
        },
    )
    if _json_bytes(legacy) <= maximum_bytes:
        return ((legacy, contributions),)

    proposal_lookup: dict[
        str,
        tuple[DetailedObjectContribution, DetailedEntityProposal],
    ] = {}
    items: list[JsonValue] = []
    for contribution in contributions:
        for proposal_ref, proposal in zip(
            contribution.proposal_refs,
            contribution.proposals,
            strict=True,
        ):
            proposal_lookup[proposal_ref] = (contribution, proposal)
            items.append(_compact_proposal(proposal_ref, proposal))
    pages = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
        },
        item_key="contribution_proposals",
        items=items,
        maximum_bytes=maximum_bytes,
    )
    results: list[tuple[JsonValue, tuple[DetailedObjectContribution, ...]]] = []
    for page in pages:
        raw_items = cast(dict[str, JsonValue], page)["contribution_proposals"]
        if not isinstance(raw_items, list):
            raise AgentCandidateValidationError()
        grouped: dict[str, list[DetailedEntityProposal]] = {}
        originals: dict[str, DetailedObjectContribution] = {}
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise AgentCandidateValidationError()
            proposal_ref = raw_item.get("proposal_ref")
            if not isinstance(proposal_ref, str):
                raise AgentCandidateValidationError()
            contribution, proposal = proposal_lookup[proposal_ref]
            grouped.setdefault(contribution.contribution_ref, []).append(proposal)
            originals[contribution.contribution_ref] = contribution
        scoped = tuple(
            DetailedObjectContribution(
                contribution_ref=reference,
                source_object=originals[reference].source_object,
                disposition="represented",
                rationale=originals[reference].rationale,
                proposals=tuple(grouped[reference]),
            )
            for reference in sorted(grouped)
        )
        results.append((page, scoped))
    return tuple(results)


def _merge_consolidations(
    *,
    parts: tuple[DetailedEntityConsolidation, ...],
    contributions: tuple[DetailedObjectContribution, ...],
) -> DetailedEntityConsolidation:
    if len(parts) == 1:
        return parts[0]
    proposal_by_ref = {
        proposal_ref: proposal
        for contribution in contributions
        for proposal_ref, proposal in zip(
            contribution.proposal_refs,
            contribution.proposals,
            strict=True,
        )
    }
    components: list[set[str]] = []
    for part in parts:
        for entity in part.entities:
            references = set(entity.contribution_refs)
            semantic_keys = {
                _proposal_semantic_key(proposal_by_ref[reference]) for reference in references
            }
            matches = [
                index
                for index, component in enumerate(components)
                if semantic_keys
                & {_proposal_semantic_key(proposal_by_ref[reference]) for reference in component}
            ]
            if not matches:
                components.append(references)
                continue
            merged = references
            for index in reversed(matches):
                merged.update(components.pop(index))
            components.append(merged)

    discarded = tuple(
        sorted(reference for part in parts for reference in part.discarded_contribution_refs)
    )
    entities: list[DetailedConsolidatedEntity] = []
    for index, references in enumerate(
        sorted(components, key=lambda value: tuple(sorted(value))),
        start=1,
    ):
        names_by_key: dict[str, str] = {}
        for reference in sorted(references):
            name = proposal_by_ref[reference].object.conceptual_object_name
            names_by_key.setdefault(normalize_model_key_value(name), name)
        entities.append(
            DetailedConsolidatedEntity(
                canonical_entity_ref=f"entity_{index:05d}",
                contribution_refs=tuple(sorted(references)),
                candidate_names=tuple(names_by_key.values()),
            )
        )
    merged = DetailedEntityConsolidation(
        entities=tuple(entities),
        discarded_contribution_refs=discarded,
    )
    return DetailedEntityConsolidationValidator(contributions=contributions).parse_validated(
        cast(JsonValue, merged.model_dump(mode="json"))
    )


def _detail_contexts(
    context: AgentContextBundle,
    *,
    entity: DetailedConsolidatedEntity,
    contributions: tuple[DetailedObjectContribution, ...],
    selected_by_contribution_ref: dict[str, SelectedObjectContext],
    maximum_bytes: int,
) -> tuple[
    tuple[
        JsonValue,
        DetailedConsolidatedEntity,
        tuple[DetailedObjectContribution, ...],
    ],
    ...,
]:
    contribution_by_ref = {item.contribution_ref: item for item in contributions}
    contribution_refs = {item.split(".", maxsplit=1)[0] for item in entity.contribution_refs}
    entity_contributions = tuple(
        contribution_by_ref[reference] for reference in sorted(contribution_refs)
    )
    legacy = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "entity": entity.model_dump(mode="json"),
            "contributions": [item.model_dump(mode="json") for item in entity_contributions],
            "selected_objects": [
                selected_by_contribution_ref[reference].model_dump(mode="json")
                for reference in sorted(contribution_refs)
            ],
        },
    )
    if _json_bytes(legacy) <= maximum_bytes:
        return ((legacy, entity, contributions),)

    proposal_lookup = {
        proposal_ref: (contribution, proposal)
        for contribution in contributions
        for proposal_ref, proposal in zip(
            contribution.proposal_refs,
            contribution.proposals,
            strict=True,
        )
    }
    items = [
        cast(
            JsonValue,
            {
                **cast(
                    dict[str, JsonValue],
                    _compact_proposal(reference, proposal_lookup[reference][1]),
                ),
                "selected_object": _compact_selected_object(
                    selected_by_contribution_ref[proposal_lookup[reference][0].contribution_ref]
                ),
            },
        )
        for reference in entity.contribution_refs
    ]
    pages = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "entity": cast(
                JsonValue,
                {
                    "canonical_entity_ref": entity.canonical_entity_ref,
                    "preferred_candidate_name": sorted(
                        entity.candidate_names,
                        key=normalize_model_key_value,
                    )[0],
                },
            ),
        },
        item_key="contribution_proposals",
        items=items,
        maximum_bytes=maximum_bytes,
    )
    results: list[
        tuple[
            JsonValue,
            DetailedConsolidatedEntity,
            tuple[DetailedObjectContribution, ...],
        ]
    ] = []
    for page in pages:
        raw_items = cast(dict[str, JsonValue], page)["contribution_proposals"]
        if not isinstance(raw_items, list):
            raise AgentCandidateValidationError()
        references = tuple(
            cast(str, item["proposal_ref"]) for item in raw_items if isinstance(item, dict)
        )
        grouped: dict[str, list[DetailedEntityProposal]] = {}
        originals: dict[str, DetailedObjectContribution] = {}
        for reference in references:
            contribution, proposal = proposal_lookup[reference]
            grouped.setdefault(contribution.contribution_ref, []).append(proposal)
            originals[contribution.contribution_ref] = contribution
        scoped_contributions = tuple(
            DetailedObjectContribution(
                contribution_ref=reference,
                source_object=originals[reference].source_object,
                disposition="represented",
                rationale=originals[reference].rationale,
                proposals=tuple(grouped[reference]),
            )
            for reference in sorted(grouped)
        )
        names_by_key: dict[str, str] = {}
        for reference in references:
            name = proposal_lookup[reference][1].object.conceptual_object_name
            names_by_key.setdefault(normalize_model_key_value(name), name)
        scoped_entity = DetailedConsolidatedEntity(
            canonical_entity_ref=entity.canonical_entity_ref,
            contribution_refs=references,
            candidate_names=tuple(names_by_key.values()),
        )
        results.append((page, scoped_entity, scoped_contributions))
    return tuple(results)


def _merge_entity_details(
    *,
    parts: tuple[DetailedEntityDetail, ...],
    entity: DetailedConsolidatedEntity,
    contributions: tuple[DetailedObjectContribution, ...],
) -> DetailedEntityDetail:
    if not parts:
        raise AgentCandidateValidationError()
    merged_object = parts[0].object
    for part in parts[1:]:
        merged_object = _merge_conceptual_objects(merged_object, part.object)
    proposal_by_ref = {
        proposal_ref: proposal
        for contribution in contributions
        for proposal_ref, proposal in zip(
            contribution.proposal_refs,
            contribution.proposals,
            strict=True,
        )
    }
    merged_object = _merge_object_supports(
        merged_object,
        tuple(
            support
            for reference in entity.contribution_refs
            for support in proposal_by_ref[reference].object.supports
        ),
    )
    merged = DetailedEntityDetail(
        canonical_entity_ref=entity.canonical_entity_ref,
        object=merged_object,
    )
    return DetailedEntityDetailValidator(
        entity=entity,
        contributions=contributions,
    ).parse_validated(cast(JsonValue, merged.model_dump(mode="json")))


def _refinement_contexts(
    context: AgentContextBundle,
    *,
    package: DetailedRelationshipPackage,
    entity_details: tuple[DetailedEntityDetail, ...],
    maximum_bytes: int,
) -> tuple[
    tuple[
        JsonValue,
        DetailedRelationshipPackage,
        tuple[DetailedEntityDetail, ...],
    ],
    ...,
]:
    details_by_ref = {item.canonical_entity_ref: item for item in entity_details}
    endpoint_details = (
        details_by_ref[package.from_entity_ref],
        details_by_ref[package.to_entity_ref],
    )
    endpoint_context = [_compact_entity_detail(item) for item in endpoint_details]
    full_context = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "endpoint_entity_details": endpoint_context,
            "relationship_package": package.model_dump(mode="json"),
        },
    )
    if _json_bytes(full_context) <= maximum_bytes:
        return ((full_context, package, endpoint_details),)
    pages = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "endpoint_entity_details": cast(JsonValue, endpoint_context),
            "relationship_package": cast(
                JsonValue,
                {
                    "package_ref": package.package_ref,
                    "from_entity_ref": package.from_entity_ref,
                    "to_entity_ref": package.to_entity_ref,
                },
            ),
        },
        item_key="relationship_signals",
        items=[cast(JsonValue, item.model_dump(mode="json")) for item in package.signals],
        maximum_bytes=maximum_bytes,
    )
    results: list[
        tuple[
            JsonValue,
            DetailedRelationshipPackage,
            tuple[DetailedEntityDetail, ...],
        ]
    ] = []
    for page in pages:
        raw_signals = cast(dict[str, JsonValue], page)["relationship_signals"]
        if not isinstance(raw_signals, list):
            raise AgentCandidateValidationError()
        scoped_dump = package.model_dump(mode="json")
        scoped_dump["signals"] = raw_signals
        scoped = DetailedRelationshipPackage.model_validate_json(
            _canonical_json(cast(JsonValue, scoped_dump)),
            strict=True,
        )
        results.append((page, scoped, endpoint_details))
    return tuple(results)


def _merge_relationship_refinements(
    *,
    parts: tuple[DetailedRelationshipRefinement, ...],
    package: DetailedRelationshipPackage,
    entity_details: tuple[DetailedEntityDetail, ...],
) -> DetailedRelationshipRefinement:
    if not parts:
        raise AgentCandidateValidationError()
    if len(parts) == 1:
        return parts[0]
    proposed = [item.relationship for item in parts if item.relationship is not None]
    if len(proposed) == len(parts):
        relationship = proposed[0]
        try:
            for candidate in proposed[1:]:
                relationship = _merge_conceptual_relationships(
                    relationship,
                    candidate,
                )
            merged = DetailedRelationshipRefinement(
                package_ref=package.package_ref,
                disposition="proposed",
                rationale="All byte-bounded evidence pages proposed the same relationship.",
                relationship=relationship,
            )
        except AgentCandidateValidationError:
            merged = DetailedRelationshipRefinement(
                package_ref=package.package_ref,
                disposition="needs_review",
                rationale="Byte-bounded evidence pages produced conflicting refinements.",
                relationship=None,
            )
    elif not proposed and all(item.disposition == "no_relationship" for item in parts):
        merged = DetailedRelationshipRefinement(
            package_ref=package.package_ref,
            disposition="no_relationship",
            rationale="No byte-bounded evidence page supported a relationship.",
            relationship=None,
        )
    else:
        merged = DetailedRelationshipRefinement(
            package_ref=package.package_ref,
            disposition="needs_review",
            rationale="Byte-bounded evidence pages produced conflicting refinements.",
            relationship=None,
        )
    return DetailedRelationshipRefinementValidator(
        package=package,
        entity_details=entity_details,
    ).parse_validated(cast(JsonValue, merged.model_dump(mode="json")))


def _reconciliation_contexts(
    context: AgentContextBundle,
    *,
    contributions: tuple[DetailedObjectContribution, ...],
    consolidation: DetailedEntityConsolidation,
    entity_details: tuple[DetailedEntityDetail, ...],
    relationship_packages: tuple[DetailedRelationshipPackage, ...],
    relationship_refinements: tuple[DetailedRelationshipRefinement, ...],
    maximum_bytes: int,
) -> tuple[
    tuple[
        JsonValue,
        tuple[DetailedEntityDetail, ...],
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
    ],
    ...,
]:
    input_refs = tuple(item.contribution_ref for item in contributions)
    applied_refs = conceptual_applied_record_refs(context.context.applied.conceptual)
    legacy = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
            "consolidation": consolidation.model_dump(mode="json"),
            "entity_details": [item.model_dump(mode="json") for item in entity_details],
            "relationship_packages": [
                item.model_dump(mode="json") for item in relationship_packages
            ],
            "relationship_refinements": [
                item.model_dump(mode="json") for item in relationship_refinements
            ],
            "input_coverage": [
                {
                    "contribution_ref": item.contribution_ref,
                    "source_object": item.source_object.model_dump(mode="json"),
                    "disposition": item.disposition,
                    "rationale": item.rationale,
                }
                for item in contributions
            ],
            "required_input_contribution_refs": list(input_refs),
            "applied_conceptual": (
                None
                if context.context.applied.conceptual is None
                else context.context.applied.conceptual.model_dump(mode="json")
            ),
            "required_applied_record_refs": list(applied_refs),
        },
    )
    if _json_bytes(legacy) <= maximum_bytes:
        return (
            (
                legacy,
                entity_details,
                input_refs,
                tuple(item.package_ref for item in relationship_packages),
                applied_refs,
            ),
        )

    items: list[JsonValue] = [
        cast(
            JsonValue,
            {
                "work_item_type": "entity_detail",
                "entity_ref": detail.canonical_entity_ref,
                "entity_detail": _compact_entity_detail(detail),
            },
        )
        for detail in entity_details
    ]
    items.extend(
        cast(
            JsonValue,
            {
                "work_item_type": "input_coverage",
                "contribution_ref": item.contribution_ref,
                "source_object": item.source_object.model_dump(mode="json"),
                "disposition": item.disposition,
                "rationale": _truncate_utf8(item.rationale, 2_000),
            },
        )
        for item in contributions
    )
    refinement_by_ref = {item.package_ref: item for item in relationship_refinements}
    items.extend(
        cast(
            JsonValue,
            {
                "work_item_type": "relationship_refinement",
                "package_ref": package.package_ref,
                "from_entity_ref": package.from_entity_ref,
                "to_entity_ref": package.to_entity_ref,
                "refinement": _compact_relationship_refinement(
                    refinement_by_ref[package.package_ref]
                ),
            },
        )
        for package in relationship_packages
    )
    applied = context.context.applied.conceptual
    if applied is not None:
        fragment_bytes = max(128, min(8 * 1024, maximum_bytes // 4))
        applied_records: list[tuple[str, JsonValue]] = [
            (
                f"object:{normalize_model_key_value(record.conceptual_object_name)}",
                cast(JsonValue, record.model_dump(mode="json")),
            )
            for record in applied.objects
        ]
        applied_records.extend(
            (_relationship_record_ref(record), cast(JsonValue, record.model_dump(mode="json")))
            for record in applied.relationships
        )
        for record_ref, value in applied_records:
            fragments = _json_record_fragments(
                dataset="applied_conceptual",
                record_ref=record_ref,
                value=value,
                maximum_fragment_bytes=fragment_bytes,
            )
            for fragment in fragments:
                raw_fragment = cast(dict[str, JsonValue], fragment)
                fragment_index = raw_fragment["fragment_index"]
                fragment_count = raw_fragment["fragment_count"]
                items.append(
                    cast(
                        JsonValue,
                        {
                            "work_item_type": "applied_evidence_fragment",
                            "review_ref": (
                                f"{record_ref}#fragment_{fragment_index}_of_{fragment_count}"
                            ),
                            **raw_fragment,
                        },
                    )
                )

    pages = _pack_context_items(
        base={
            "schema_version": "1.0",
            "model": _detailed_model_context(context),
        },
        item_key="reconciliation_work_items",
        items=items,
        maximum_bytes=max(1, maximum_bytes - min(2 * 1024, maximum_bytes // 8)),
    )
    detail_by_ref = {item.canonical_entity_ref: item for item in entity_details}
    results: list[
        tuple[
            JsonValue,
            tuple[DetailedEntityDetail, ...],
            tuple[str, ...],
            tuple[str, ...],
            tuple[str, ...],
        ]
    ] = []
    for page in pages:
        raw_items = cast(dict[str, JsonValue], page)["reconciliation_work_items"]
        if not isinstance(raw_items, list):
            raise AgentCandidateValidationError()
        entity_refs = tuple(
            cast(str, item["entity_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "entity_detail"
        )
        input_contribution_refs = tuple(
            cast(str, item["contribution_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "input_coverage"
        )
        package_refs = tuple(
            cast(str, item["package_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "relationship_refinement"
        )
        review_refs = tuple(
            cast(str, item["review_ref"])
            for item in raw_items
            if isinstance(item, dict) and item.get("work_item_type") == "applied_evidence_fragment"
        )
        page_context = cast(dict[str, JsonValue], page)
        page_context["required_entity_refs"] = list(entity_refs)
        page_context["required_input_contribution_refs"] = list(input_contribution_refs)
        page_context["required_relationship_package_refs"] = list(package_refs)
        page_context["required_applied_review_refs"] = list(review_refs)
        if _json_bytes(cast(JsonValue, page_context)) > maximum_bytes:
            raise InvalidRequestError(
                "A Conceptual reconciliation page exceeds its safe byte limit."
            )
        results.append(
            (
                cast(JsonValue, page_context),
                tuple(detail_by_ref[reference] for reference in entity_refs),
                input_contribution_refs,
                package_refs,
                review_refs,
            )
        )
    return tuple(results)


def _merge_reconciled_candidates(
    candidates: Sequence[JsonValue],
    *,
    entity_details: tuple[DetailedEntityDetail, ...],
) -> JsonValue:
    objects: dict[str, ConceptualObjectRecord] = {}
    relationships: dict[tuple[str, str, str], ConceptualRelationshipRecord] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise AgentCandidateValidationError()
        raw_objects = candidate.get("objects")
        raw_relationships = candidate.get("relationships")
        if not isinstance(raw_objects, list) or not isinstance(raw_relationships, list):
            raise AgentCandidateValidationError()
        for raw_object in raw_objects:
            record = ConceptualObjectRecord.model_validate_json(
                _canonical_json(cast(JsonValue, raw_object)),
                strict=True,
            )
            key = normalize_model_key_value(record.conceptual_object_name)
            objects[key] = (
                record if key not in objects else _merge_conceptual_objects(objects[key], record)
            )
        for raw_relationship in raw_relationships:
            record = ConceptualRelationshipRecord.model_validate_json(
                _canonical_json(cast(JsonValue, raw_relationship)),
                strict=True,
            )
            key = _relationship_key(record)
            relationships[key] = (
                record
                if key not in relationships
                else _merge_conceptual_relationships(relationships[key], record)
            )
    for detail in entity_details:
        key = normalize_model_key_value(detail.object.conceptual_object_name)
        candidate = objects.get(key)
        if candidate is None:
            raise AgentCandidateValidationError()
        objects[key] = _merge_object_supports(candidate, detail.object.supports)
    return cast(
        JsonValue,
        {
            "objects": [item.model_dump(mode="json") for item in objects.values()],
            "relationships": [item.model_dump(mode="json") for item in relationships.values()],
        },
    )


def _compact_proposal(
    proposal_ref: str,
    proposal: DetailedEntityProposal,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "proposal_ref": proposal_ref,
            "local_entity_ref": proposal.local_entity_ref,
            "candidate_name": proposal.object.conceptual_object_name,
            "candidate_definition": _truncate_utf8(
                proposal.object.conceptual_object_definition,
                2_000,
            ),
            "candidate_type": proposal.object.conceptual_object_type,
            "candidate_grain": _truncate_utf8(
                proposal.object.conceptual_object_grain,
                2_000,
            ),
            "candidate_aliases": list(proposal.object.conceptual_object_aliases[:20]),
            "candidate_alias_count": len(proposal.object.conceptual_object_aliases),
            "physical_support_sources": [
                _compact_support_source(item)
                for item in proposal.object.supports
                if isinstance(item, ObjectSupportRecord)
            ],
            "assertion_support_count": sum(
                not isinstance(item, ObjectSupportRecord) for item in proposal.object.supports
            ),
        },
    )


def _proposal_semantic_key(proposal: DetailedEntityProposal) -> tuple[str, str, str]:
    record = proposal.object
    return (
        " ".join(record.conceptual_object_definition.split()).casefold(),
        " ".join(record.conceptual_object_grain.split()).casefold(),
        normalize_model_key_value(record.conceptual_object_type),
    )


def _compact_selected_object(selected: SelectedObjectContext) -> JsonValue:
    return cast(
        JsonValue,
        {
            "selection_order": selected.selection_order,
            "object": selected.object.model_dump(mode="json"),
            "attribute_count": len(selected.attributes),
        },
    )


def _compact_entity_detail(detail: DetailedEntityDetail) -> JsonValue:
    record = detail.object
    return cast(
        JsonValue,
        {
            "canonical_entity_ref": detail.canonical_entity_ref,
            "conceptual_object_name": record.conceptual_object_name,
            "conceptual_object_definition": _truncate_utf8(
                record.conceptual_object_definition,
                2_000,
            ),
            "conceptual_object_type": record.conceptual_object_type,
            "conceptual_object_grain": _truncate_utf8(
                record.conceptual_object_grain,
                2_000,
            ),
            "conceptual_object_aliases": list(record.conceptual_object_aliases[:20]),
            "conceptual_object_alias_count": len(record.conceptual_object_aliases),
            "conceptual_object_confidence": record.conceptual_object_confidence,
            "conceptual_object_status": record.conceptual_object_status,
            "support_sources": [_compact_support_source(item) for item in record.supports[:20]],
            "support_source_count": len(record.supports),
        },
    )


def _compact_relationship_refinement(
    refinement: DetailedRelationshipRefinement,
) -> JsonValue:
    relationship = refinement.relationship
    if relationship is None:
        return cast(
            JsonValue,
            {
                "disposition": refinement.disposition,
                "rationale": refinement.rationale,
                "relationship": None,
            },
        )
    return cast(
        JsonValue,
        {
            "disposition": refinement.disposition,
            "rationale": refinement.rationale,
            "relationship": {
                "from_conceptual_object_name": relationship.from_conceptual_object_name,
                "to_conceptual_object_name": relationship.to_conceptual_object_name,
                "conceptual_relationship_name": relationship.conceptual_relationship_name,
                "conceptual_relationship_type": relationship.conceptual_relationship_type,
                "conceptual_relationship_cardinality": (
                    relationship.conceptual_relationship_cardinality
                ),
                "conceptual_relationship_confidence": (
                    relationship.conceptual_relationship_confidence
                ),
                "conceptual_relationship_status": relationship.conceptual_relationship_status,
                "support_sources": [
                    _compact_support_source(item) for item in relationship.supports[:20]
                ],
                "support_source_count": len(relationship.supports),
            },
        },
    )


def _compact_support_source(support: SupportRecord) -> JsonValue:
    if isinstance(support, ObjectSupportRecord):
        return cast(
            JsonValue,
            {
                "support_source_type": "object",
                "source_object": support.source_object.model_dump(mode="json"),
            },
        )
    return cast(
        JsonValue,
        {
            "support_source_type": "assertion",
            "assertion_record": support.assertion_record.model_dump(mode="json"),
        },
    )


def _merge_conceptual_objects(
    first: ConceptualObjectRecord,
    second: ConceptualObjectRecord,
) -> ConceptualObjectRecord:
    first_dump = first.model_dump(mode="json")
    if (
        normalize_model_key_value(first.conceptual_object_name)
        != normalize_model_key_value(second.conceptual_object_name)
        or first.conceptual_object_is_locked
        or second.conceptual_object_is_locked
    ):
        raise AgentCandidateValidationError()
    aliases: dict[str, str] = {}
    for alias in (*first.conceptual_object_aliases, *second.conceptual_object_aliases):
        aliases.setdefault(normalize_model_key_value(alias), alias)
    supports = _merge_supports(first.supports, second.supports)
    first_dump["conceptual_object_aliases"] = list(aliases.values())
    first_dump["supports"] = [item.model_dump(mode="json") for item in supports]
    return ConceptualObjectRecord.model_validate_json(
        _canonical_json(cast(JsonValue, first_dump)),
        strict=True,
    )


def _merge_object_supports(
    record: ConceptualObjectRecord,
    supports: Sequence[SupportRecord],
) -> ConceptualObjectRecord:
    value = record.model_dump(mode="json")
    value["supports"] = [
        item.model_dump(mode="json") for item in _merge_supports(record.supports, supports)
    ]
    return ConceptualObjectRecord.model_validate_json(
        _canonical_json(cast(JsonValue, value)),
        strict=True,
    )


def _merge_conceptual_relationships(
    first: ConceptualRelationshipRecord,
    second: ConceptualRelationshipRecord,
) -> ConceptualRelationshipRecord:
    first_dump = first.model_dump(mode="json")
    if (
        _relationship_key(first) != _relationship_key(second)
        or first.conceptual_relationship_is_locked
        or second.conceptual_relationship_is_locked
    ):
        raise AgentCandidateValidationError()
    if (
        first.conceptual_relationship_type != second.conceptual_relationship_type
        or first.conceptual_relationship_cardinality != second.conceptual_relationship_cardinality
    ):
        first_dump["conceptual_relationship_cardinality"] = "unknown"
        first_dump["conceptual_relationship_cardinality_basis"] = (
            "Byte-bounded evidence pages disagreed; user review is required."
        )
        first_dump["conceptual_relationship_confidence"] = "low"
        first_dump["conceptual_relationship_status"] = "active"
    supports = _merge_supports(first.supports, second.supports)
    first_dump["supports"] = [item.model_dump(mode="json") for item in supports]
    return ConceptualRelationshipRecord.model_validate_json(
        _canonical_json(cast(JsonValue, first_dump)),
        strict=True,
    )


def _merge_supports(
    first: Sequence[SupportRecord],
    second: Sequence[SupportRecord],
) -> tuple[SupportRecord, ...]:
    merged: dict[tuple[str, ...], SupportRecord] = {}
    for support in (*first, *second):
        key = _support_key(support)
        existing = merged.get(key)
        if existing is None or _canonical_json(
            cast(JsonValue, support.model_dump(mode="json"))
        ) < _canonical_json(cast(JsonValue, existing.model_dump(mode="json"))):
            merged[key] = support
    return tuple(merged.values())


def _support_key(support: SupportRecord) -> tuple[str, ...]:
    if isinstance(support, ObjectSupportRecord):
        return (
            "object",
            *_normalized_object_identity(
                support.source_object.tenant_code,
                support.source_object.system_code,
                support.source_object.connection_code,
                support.source_object.object_schema,
                support.source_object.object_name,
            ),
        )
    return (
        "assertion",
        normalize_model_key_value(support.assertion_record.modeling_assertion_record_key),
    )


def _relationship_key(record: ConceptualRelationshipRecord) -> tuple[str, str, str]:
    return (
        normalize_model_key_value(record.from_conceptual_object_name),
        normalize_model_key_value(record.to_conceptual_object_name),
        normalize_model_key_value(record.conceptual_relationship_name),
    )


def _relationship_record_ref(record: ConceptualRelationshipRecord) -> str:
    return (
        "relationship:"
        f"{normalize_model_key_value(record.from_conceptual_object_name)}|"
        f"{normalize_model_key_value(record.to_conceptual_object_name)}|"
        f"{normalize_model_key_value(record.conceptual_relationship_name)}"
    )


def _attribute_record_ref(record: ProfilingProfileRecord) -> str:
    return "|".join(
        normalize_model_key_value(value)
        for value in (
            record.tenant_code,
            record.system_code,
            record.connection_code,
            record.object_schema,
            record.object_name,
            record.attribute_name,
        )
    )


def _json_record_fragments(
    *,
    dataset: str,
    record_ref: str,
    value: JsonValue,
    maximum_fragment_bytes: int,
) -> tuple[JsonValue, ...]:
    text = _canonical_json(value)
    parts = _split_utf8(text, maximum_fragment_bytes)
    return tuple(
        cast(
            JsonValue,
            {
                "dataset": dataset,
                "record_ref": record_ref,
                "fragment_index": index,
                "fragment_count": len(parts),
                "json_text": part,
            },
        )
        for index, part in enumerate(parts, start=1)
    )


def _pack_context_items(
    *,
    base: dict[str, JsonValue],
    item_key: str,
    items: Sequence[JsonValue],
    maximum_bytes: int,
) -> tuple[JsonValue, ...]:
    pages: list[list[JsonValue]] = []
    current: list[JsonValue] = []
    candidates: Iterable[JsonValue] = items if items else (cast(JsonValue, None),)
    for item in candidates:
        trial_items = current if item is None else [*current, item]
        trial = cast(
            JsonValue,
            {
                **base,
                item_key: trial_items,
                "page": {"index": 99999, "count": 99999},
            },
        )
        if _json_bytes(trial) <= maximum_bytes:
            current = trial_items
            continue
        if not current:
            raise InvalidRequestError(
                "A Conceptual detailed evidence item exceeds its safe byte limit."
            )
        pages.append(current)
        current = [] if item is None else [item]
        single = cast(
            JsonValue,
            {
                **base,
                item_key: current,
                "page": {"index": 99999, "count": 99999},
            },
        )
        if _json_bytes(single) > maximum_bytes:
            raise InvalidRequestError(
                "A Conceptual detailed evidence item exceeds its safe byte limit."
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
        raise InvalidRequestError("A Conceptual detailed context page exceeds its safe byte limit.")
    return contexts


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


def _truncate_utf8(value: str, maximum_bytes: int) -> str:
    parts = _split_utf8(value, maximum_bytes)
    return parts[0]


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_bytes(value: JsonValue) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def _physical_object_key(selected: SelectedObjectContext) -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code=selected.object.tenant_code,
        system_code=selected.object.system_code,
        connection_code=selected.object.connection_code,
        object_schema=selected.object.object_schema,
        object_name=selected.object.object_name,
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


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return ConceptualFinalizationFailedError()
    return ConceptualExecutionFailedError()


__all__ = [
    "ConceptualWorkflow",
    "ConceptualExecutionFailedError",
    "ConceptualFinalizationFailedError",
    "DatabaseConceptualExecutor",
]
