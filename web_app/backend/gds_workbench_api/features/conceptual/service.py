"""Execute one already-running Conceptual authoring run."""

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
    DetailedEntityConsolidationValidator,
    DetailedEntityDetail,
    DetailedEntityDetailValidator,
    DetailedObjectContribution,
    DetailedObjectContributionValidator,
    DetailedReconciliationValidator,
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
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=context_policy or load_default_agent_context_policy(),
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
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage=(
                        "conceptual.object_contribution"
                        if is_detailed
                        else "conceptual.candidate_authoring"
                    ),
                    status="running",
                    message=(
                        "Conceptual detailed coverage started."
                        if is_detailed
                        else "Conceptual candidate authoring started."
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
                    final_attempt,
                ) = await self._execute_detailed(
                    principal,
                    plan=plan,
                    context=context,
                    validator=validator,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                final_event_sequence = 8
            elif execution_mode in ("one_shot", "tool_assisted"):
                resolver_key = f"workflow.conceptual.{execution_mode}.candidate_authoring.context"
                resolver_values: dict[str, object] = {
                    resolver_key: context.embedded_context,
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
                final_attempt = outcome.attempt_count
                final_event_sequence = 3
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
                        final_event=AgentWorkflowEvent(
                            sequence=final_event_sequence,
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
                final_event=AgentWorkflowEvent(
                    sequence=final_event_sequence,
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
        principal: RequestPrincipal,
        *,
        plan: AgentRunPlan,
        context: AgentContextBundle,
        validator: ConceptualCandidateValidator,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> tuple[JsonValue, AgentStageOutcome, bool, int]:
        contributions: list[DetailedObjectContribution] = []
        intermediate_warning = False
        max_attempt = 1
        for selected in context.context.selected_objects:
            contribution_ref = f"object_{selected.selection_order}"
            stage_context = _object_contribution_context(
                context,
                selected=selected,
                contribution_ref=contribution_ref,
            )
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
                stage="conceptual.entity_consolidation",
                status="running",
                message="Object contributions are ready for entity consolidation.",
                current=len(contributions),
                total=len(context.context.selected_objects),
                finding_count=len(contributions),
            ),
        )
        consolidation_context = cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "model": _detailed_model_context(context),
                "contributions": [item.model_dump(mode="json") for item in contributions],
            },
        )
        consolidation_validator = DetailedEntityConsolidationValidator(
            contributions=tuple(contributions)
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
        consolidation = consolidation_validator.parse_validated(consolidation_outcome.candidate)
        max_attempt = max(max_attempt, consolidation_outcome.attempt_count)
        intermediate_warning = (
            intermediate_warning
            or consolidation_outcome.was_repaired
            or bool(consolidation_outcome.warning_codes)
        )

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=4,
                attempt=1,
                stage="conceptual.entity_attribute_detail",
                status="running",
                message="Consolidated entities are ready for detailed authoring.",
                current=0 if consolidation.entities else None,
                total=(len(consolidation.entities) if consolidation.entities else None),
                finding_count=len(consolidation.entities),
            ),
        )
        contribution_by_ref = {item.contribution_ref: item for item in contributions}
        selected_by_ref = {
            f"object_{item.selection_order}": item for item in context.context.selected_objects
        }
        details: list[DetailedEntityDetail] = []
        for entity in consolidation.entities:
            contribution_refs = {
                item.split(".", maxsplit=1)[0] for item in entity.contribution_refs
            }
            entity_contributions = tuple(
                contribution_by_ref[reference] for reference in sorted(contribution_refs)
            )
            detail_context = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": _detailed_model_context(context),
                    "entity": entity.model_dump(mode="json"),
                    "contributions": [
                        item.model_dump(mode="json") for item in entity_contributions
                    ],
                    "selected_objects": [
                        selected_by_ref[reference].model_dump(mode="json")
                        for reference in sorted(contribution_refs)
                    ],
                },
            )
            detail_validator = DetailedEntityDetailValidator(
                entity=entity,
                contributions=tuple(contributions),
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
            details.append(detail_validator.parse_validated(detail_outcome.candidate))
            max_attempt = max(max_attempt, detail_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or detail_outcome.was_repaired
                or bool(detail_outcome.warning_codes)
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
        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=5,
                attempt=1,
                stage="conceptual.relationship_candidate_derivation",
                status="running",
                message="Deterministic relationship evidence packages are ready.",
                current=(len(relationship_packages) if relationship_packages else None),
                total=(len(relationship_packages) if relationship_packages else None),
                finding_count=len(relationship_packages),
            ),
        )

        refinements: list[DetailedRelationshipRefinement] = []
        for package in relationship_packages:
            refinement_context = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": _detailed_model_context(context),
                    "entity_details": [item.model_dump(mode="json") for item in details],
                    "relationship_package": package.model_dump(mode="json"),
                },
            )
            refinement_validator = DetailedRelationshipRefinementValidator(
                package=package,
                entity_details=tuple(details),
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
            refinements.append(refinement_validator.parse_validated(refinement_outcome.candidate))
            max_attempt = max(max_attempt, refinement_outcome.attempt_count)
            intermediate_warning = (
                intermediate_warning
                or refinement_outcome.was_repaired
                or bool(refinement_outcome.warning_codes)
            )

        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=6,
                attempt=1,
                stage="conceptual.relationship_cardinality_refinement",
                status="running",
                message="Relationship packages are ready for whole-model reconciliation.",
                current=(len(refinements) if refinements else None),
                total=(len(relationship_packages) if relationship_packages else None),
                finding_count=len(refinements),
            ),
        )

        applied_refs = conceptual_applied_record_refs(context.context.applied.conceptual)
        reconciliation_context = cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "model": _detailed_model_context(context),
                "consolidation": consolidation.model_dump(mode="json"),
                "entity_details": [item.model_dump(mode="json") for item in details],
                "relationship_packages": [
                    item.model_dump(mode="json") for item in relationship_packages
                ],
                "relationship_refinements": [item.model_dump(mode="json") for item in refinements],
                "applied_conceptual": (
                    None
                    if context.context.applied.conceptual is None
                    else context.context.applied.conceptual.model_dump(mode="json")
                ),
                "required_applied_record_refs": list(applied_refs),
            },
        )
        reconciliation_validator = DetailedReconciliationValidator(
            entity_details=tuple(details),
            relationship_package_refs=tuple(item.package_ref for item in relationship_packages),
            applied_record_refs=applied_refs,
            final_validator=validator,
        )
        await self._lifecycle.append_event(
            principal,
            workflow_run_id=plan.workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
            event=AgentWorkflowEvent(
                sequence=7,
                attempt=1,
                stage="conceptual.whole_model_reconciliation",
                status="running",
                message="Whole-model reconciliation and backend validation started.",
                current=0,
                total=1,
                finding_count=len(details) + len(refinements),
            ),
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
        max_attempt = max(max_attempt, final_outcome.attempt_count)
        return (
            reconciliation_validator.materialize_validated(final_outcome.candidate),
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
    naming = context.context.model_details.silver_model_naming_instructions
    if naming is not None:
        values["model.naming_instructions"] = naming
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
            "model_details": context.context.model_details.model_dump(mode="json"),
        },
    )


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
