"""Start governed Code Generation Runs and execute them after worker claim."""

from __future__ import annotations

import json
import logging
from hashlib import sha256
from typing import Any, Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.contracts import MAX_MODEL_STAGE_PAYLOAD_BYTES
from gds_etl_workbench.application.change_sets.model import (
    StageModelChange,
    validate_model_stage_changes,
)
from gds_etl_workbench.application.change_sets.model_validation import (
    ModelValidationIssue,
    validate_future_graph,
)
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
    has_mapping_transformation_content,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
)
from pydantic import JsonValue, ValidationError

from gds_workbench_api.capabilities import CODE_GENERATION_AGENT_EXECUTION_MODE
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizer,
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    project_downstream_inputs,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
    AgentWorkflowTerminalResult,
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
    ModelWorkflow,
    PostgresAgentRunPlanRepository,
)
from gds_workbench_api.features.workflows.authoring.progress import (
    AgentWorkflowProgress,
    intermediate_progress_points,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentContextPolicy,
    AgentExecutor,
    AgentValidationIssue,
    load_default_agent_context_policy,
    model_validation_issues,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionDatabase

from .artifact_context import CodeGenerationArtifactContext, ModeledEntityType
from .candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
    GeneratedSqlArtifact,
)
from .context import (
    CodeGenerationExecutionContext,
    PostgresCodeGenerationContextRepository,
)

_logger = logging.getLogger(__name__)

_PARTIAL_AUTHORING_CONTRACT = (
    "Authoritative partial-authoring contract for this Run: "
    "These rules take precedence over older instructions that reject incomplete "
    "Mapping. Generate reviewable SQL for every selected mapped System, even "
    "when its Object or Attribute transformations are missing. Preserve grounded "
    "transformations and use only the supplied source metadata and saved logic. "
    "For each required output Attribute without an evidenced expression, emit "
    "CAST(NULL AS its declared target data type) AS its target column name, "
    "including nonnullable columns; this is an explicit review placeholder, "
    "not a business default. Continue to omit database/framework-populated "
    "columns required by the delivery contract. Never invent source columns, "
    "joins, filters, deduplication, defaults or cross-System reconciliation. "
    "If no evidenced rowset or join supports a branch, use a zero-row typed-NULL "
    "projection with WHERE FALSE for that branch. If a combined file lacks "
    "evidenced System-combination logic, preserve grounded stages and finish "
    "with that zero-row projection; do not invent UNION or joins. Return "
    "missing_requirement_evidence alongside the covered artifacts whenever "
    "logic is missing or placeholders are used. It is a review warning, not a "
    "reason to omit an Entity or System. Conflicting requirements still require "
    "conflicting_requirement and no artifacts. Retain exact selected-System "
    "coverage, requested file layout and SQL-only structural requirements. "
    "Put warnings in issues, never comments or prose inside SQL."
)


class CodeGenerationContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> CodeGenerationExecutionContext: ...


class CodeGenerationLifecycle(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_execution_mode: None,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart: ...

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


class CodeGenerationExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="code_generation_execution_failed",
            message="Code Generation failed before SQL artifacts could be committed.",
        )


class CodeGenerationFinalizationFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="code_generation_finalization_failed",
            message="Code Generation finalization outcome could not be confirmed.",
        )


type CodeGenerationExecutionResult = WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt


class CodeGenerationWorkflow:
    """Start governed Runs; generate SQL artifacts only after worker claim."""

    def __init__(
        self,
        *,
        database: WorkflowExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: WorkflowChangeSetFinalizer,
        no_op: AuthoringNoOpCompleter,
        lifecycle: CodeGenerationLifecycle,
        plan_repository: AgentRunPlanRepository | None = None,
        context_repository: CodeGenerationContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresCodeGenerationContextRepository()
        self._context_policy = context_policy or load_default_agent_context_policy()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=self._context_policy,
        )
        self._handoff = handoff
        self._no_op = no_op
        self._lifecycle = lifecycle

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        return await self._lifecycle.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="code_generation",
            expected_execution_mode=None,
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
    ) -> CodeGenerationExecutionResult:
        finalization_attempted = False
        changes: tuple[StageModelChange, ...] = ()
        rejected_changes: tuple[StageModelChange, ...] = ()
        rejected_issues: tuple[ModelValidationIssue, ...] = ()
        try:
            async with self._database.write_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await self._authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_MODEL_WRITE,
                    model_id=model_id,
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

            snapshot, physical_scope = context.snapshot, context.physical_scope
            if snapshot is None or physical_scope is None:
                raise InvalidRequestError("The Code Generation validation context is unavailable.")
            target_count = len(context.targets)
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage="code_generation.sql_generation",
                status="running",
                message=f"SQL generation started for {target_count} Entities.",
                current=0,
                total=target_count,
                finding_count=0,
            )

            guide_content = _guide_content(context)
            stage_plan = plan.model_copy(
                update={
                    "workflow_execution_mode": CODE_GENERATION_AGENT_EXECUTION_MODE,
                    # Backend authoring policy also follows the frozen system
                    # prompt, so an older version cannot prohibit partial SQL.
                    # The stored prompt and original frozen plan stay unchanged.
                    "stages": tuple(
                        stage.model_copy(
                            update={
                                "templates": stage.templates.model_copy(
                                    update={
                                        "system": stage.templates.system
                                        + "\n\n"
                                        + _PARTIAL_AUTHORING_CONTRACT
                                    }
                                )
                            }
                        )
                        if stage.stage_code == "sql_generation"
                        else stage
                        for stage in plan.stages
                    ),
                }
            )
            artifacts: list[GeneratedSqlArtifact] = []
            progress_points = intermediate_progress_points(target_count) | {target_count}
            highest_attempt = 1
            warning_seen = False
            incomplete_target_count = 0
            review_target_count = 0
            placeholder_target_count = 0
            for position, target in enumerate(context.targets, start=1):
                target_context = _target_agent_context(
                    context,
                    target_ref=target.target_ref,
                )
                prompt_values = project_downstream_inputs(
                    "code_generation", cast(dict[str, Any], target_context)
                )
                selected_systems = {code.strip().casefold() for code in target.source_system_codes}
                active_attributes = {
                    attribute["attribute_name"].strip().casefold()
                    for attribute in prompt_values["target_metadata"].get("attributes", [])
                    if attribute.get("is_active", True)
                }
                object_coverage = {
                    row["source_system_code"].strip().casefold()
                    for row in prompt_values["object_transformations"]
                    if has_mapping_transformation_content(row.get("transformation"))
                }
                attribute_coverage = {
                    (
                        row["source_system_code"].strip().casefold(),
                        row["target_attribute_name"].strip().casefold(),
                    )
                    for row in prompt_values["attribute_transformations"]
                    if has_mapping_transformation_content(row.get("transformation"))
                }
                incomplete_mapping = not selected_systems <= object_coverage or any(
                    (system, attribute) not in attribute_coverage
                    for system in selected_systems
                    for attribute in active_attributes
                )
                incomplete_target_count += int(incomplete_mapping)
                run_guide = guide_content
                if plan.code_generation_file_layout is not None:
                    run_guide += "\n\nRun delivery contract: " + (
                        "Write exactly one transformation SQL file for this Object combining "
                        "its selected Systems. Build isolated System branches. Combine only "
                        "according to applied Mapping; never invent UNION, joins "
                        "or reconciliation. "
                        if plan.code_generation_file_layout == "combined"
                        else "Write one standalone transformation SQL file per selected System "
                        "for this Object. Never use temporary state from another file. "
                    )
                    run_guide += (
                        "Use successive CREATE OR REPLACE TEMPORARY VIEW statements where "
                        "Mapping needs stages; declare each temporary dependency before use. "
                        "Finish each file with one explicit target-column SELECT through "
                        "SourceSystemID in registered order. Omit the target surrogate and "
                        "framework-populated audit/history fields. No SELECT *, persistent DDL, "
                        "DML, loading commands, comments, Markdown or prose in transformation SQL. "
                        "The runtime writes the target. Use the published guide's resolved "
                        "identifiers and confirmed runtime parameters. Separate files cannot "
                        "replace Mapping that requires joint System comparison; report missing "
                        "or incompatible evidence instead of inventing independent transformations."
                    )
                if target.preserved_artifact_names:
                    run_guide += (
                        "\nPreserve these existing file names; do not emit them: "
                        + ", ".join(target.preserved_artifact_names)
                    )
                run_guide += "\n\n" + _PARTIAL_AUTHORING_CONTRACT
                prompt_values["sql_generation_guide"] = run_guide
                prompt_context = cast(
                    JsonValue,
                    {
                        "__gds_downstream_inputs__": "code_generation",
                        "values": prompt_values,
                    },
                )
                context_budget = self._context_policy.stage_max_context_bytes
                result_budget = None if context_budget is None else max(1, context_budget // 2)
                readers = build_downstream_readers(
                    "code_generation",
                    prompt_values,
                    max_result_bytes=None
                    if result_budget is None
                    else max(1, result_budget // stage_plan.selection.max_turns),
                    max_page_records=200,
                    max_cumulative_result_bytes=result_budget,
                )
                validator = CodeGenerationCandidateValidator(
                    targets=(
                        CodeGenerationTargetReference(
                            target_ref=target.target_ref,
                            modeled_entity_id=target.modeled_entity_id,
                            source_system_codes=target.source_system_codes,
                            file_layout=plan.code_generation_file_layout,
                            preserved_artifact_names=target.preserved_artifact_names,
                        ),
                    )
                )

                async def validate_complete_candidate(
                    value: JsonValue,
                    validator: CodeGenerationCandidateValidator = validator,
                    position: int = position,
                ) -> AgentCandidateValidation:
                    nonlocal rejected_changes, rejected_issues
                    try:
                        candidate_changes = _generated_code_changes(
                            artifacts=(*artifacts, *validator.parse_validated(value)),
                            contexts=context.targets[:position],
                            modeled_entity_type=cast(ModeledEntityType, plan.modeled_entity_type),
                        )
                        validate_model_stage_changes(list(candidate_changes))
                    except InvalidRequestError, ValidationError:
                        return AgentCandidateValidation(
                            issues=(
                                AgentValidationIssue(
                                    code="candidate.change_set_bounds",
                                    path=(),
                                    message=(
                                        "Combined Code exceeds Model Change Set limits. "
                                        "Reduce redundant artifacts while retaining all target "
                                        "and System coverage."
                                    ),
                                ),
                            )
                        )
                    checked = validate_future_graph(
                        snapshot=snapshot,
                        staged_documents={
                            change.dataset: change.records for change in candidate_changes
                        },
                        physical_scope=physical_scope,
                    )
                    if checked.issues and position == target_count:
                        rejected_changes, rejected_issues = candidate_changes, checked.issues
                    return AgentCandidateValidation(issues=model_validation_issues(checked.issues))

                outcome = await self._stage_runner.run(
                    plan=stage_plan,
                    stage_code="sql_generation",
                    resolver_values={
                        "workflow.code_generation.common.sql_generation.context": (
                            _target_context_manifest(target_context)
                        ),
                        "workflow.code_generation.sql_generation_guide": run_guide,
                        "workflow.validation_failures": [],
                    },
                    context=prompt_context,
                    output_schema=validator.output_schema(),
                    allowed_tool_names=readers.allowed_tool_names,
                    local_tool_catalog=readers,
                    validator=validator,
                    max_candidate_bytes=MAX_MODEL_STAGE_PAYLOAD_BYTES,
                    final_validation=validate_complete_candidate,
                )
                artifacts.extend(validator.parse_validated(outcome.candidate))
                highest_attempt = max(highest_attempt, outcome.attempt_count)
                candidate_warnings = validator.warning_codes(outcome.candidate)
                review_target_count += int(incomplete_mapping or bool(candidate_warnings))
                placeholder_target_count += int(
                    "code_generation.typed_null_placeholder" in candidate_warnings
                )
                warning_seen = warning_seen or bool(
                    outcome.was_repaired or outcome.warning_codes or review_target_count
                )
                if position in progress_points:
                    message = f"SQL generation validated {position} of {target_count} Entities."
                    if review_target_count:
                        message += (
                            f" SQL for {review_target_count} Entities needs review: "
                            f"{incomplete_target_count} have incomplete Mapping and "
                            f"{placeholder_target_count} contain typed NULL placeholders."
                        )
                    elif warning_seen:
                        message += " One or more candidates required repair."
                    await progress.append(
                        attempt=highest_attempt,
                        stage="code_generation.sql_generation",
                        status="warning" if warning_seen else "running",
                        message=message,
                        current=position,
                        total=target_count,
                        finding_count=0,
                    )
            changes = _generated_code_changes(
                artifacts=tuple(artifacts),
                contexts=context.targets,
                modeled_entity_type=cast(ModeledEntityType, plan.modeled_entity_type),
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
                        expected_workflow="code_generation",
                        expected_execution_mode=None,
                        expected_correlation_id=plan.correlation_id,
                        expected_model_revision=expected_model_revision,
                        candidate_digest=authoring_no_op_candidate_digest(plan),
                        final_event=progress.event(
                            attempt=highest_attempt,
                            stage="code_generation.backend_validation",
                            status="warning" if warning_seen else "running",
                            message=(
                                "Code Generation completed with no effective change. "
                                "SQL needs review for missing Mapping or "
                                "NULL/zero-row placeholders."
                                if review_target_count
                                else "Code Generation completed with no effective change."
                            ),
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
                expected_workflow="code_generation",
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                changes=changes,
                final_event=progress.event(
                    attempt=highest_attempt,
                    stage="code_generation.backend_validation",
                    status="warning" if warning_seen else "running",
                    message=(
                        "Generated Code is in a validated draft and needs review for missing "
                        "Mapping or NULL/zero-row placeholders."
                        if review_target_count
                        else "Generated Code is ready in a validated draft."
                    ),
                    current=1,
                    total=1,
                    finding_count=staged_record_count,
                ),
            )
            return finalization.handoff
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
                        expected_workflow="code_generation",
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
                    "Code Generation Workflow Run finalization remains pending.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
                raise safe_error from None
            try:
                await self._lifecycle.fail(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    failure_code=safe_error.code[:100],
                    safe_failure_message=safe_error.message[:2000],
                )
            except Exception as persistence_error:
                _logger.warning(
                    "Code Generation failure state could not be persisted.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
                raise _safe_execution_error(
                    persistence_error,
                    finalization_attempted=False,
                ) from None
            raise safe_error from None

    @staticmethod
    def _validate_plan(
        plan: AgentRunPlan,
        *,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> None:
        if (
            plan.model_id != model_id
            or plan.workflow_run_id != workflow_run_id
            or plan.model_revision != expected_model_revision
            or plan.model_workflow != "code_generation"
            or plan.workflow_execution_mode is not None
            or plan.modeled_entity_type
            not in {
                "logical_entity",
                "dimensional_entity",
            }
            or len(plan.stages) != 1
            or plan.stages[0].stage_code != "sql_generation"
        ):
            raise InvalidRequestError(
                "The Code Generation run does not use the fixed execution path."
            )


def _generated_code_changes(
    *,
    artifacts: tuple[GeneratedSqlArtifact, ...],
    contexts: tuple[CodeGenerationArtifactContext, ...],
    modeled_entity_type: ModeledEntityType,
) -> tuple[StageModelChange, ...]:
    by_ref = {context.target_ref: context for context in contexts}
    if (
        not artifacts
        or len(by_ref) != len(contexts)
        or {artifact.target_ref for artifact in artifacts} != set(by_ref)
        or any(
            artifact.modeled_entity_id != by_ref[artifact.target_ref].modeled_entity_id
            for artifact in artifacts
        )
    ):
        raise InvalidRequestError("Code Generation candidate and context coverage differ.")

    code_records: list[GeneratedCodeRecord] = []
    system_records: list[GeneratedCodeSourceSystemRecord] = []
    for artifact in artifacts:
        context = by_ref[artifact.target_ref]
        code_records.append(
            GeneratedCodeRecord(
                modeled_entity_type=modeled_entity_type,
                modeled_entity_schema_name=context.modeled_entity_schema_name,
                modeled_entity_name=context.modeled_entity_name,
                artifact_name=artifact.artifact_name,
                artifact_type="sql_file",
                generated_code_content=artifact.generated_sql,
                generated_code_status="active",
                generated_code_is_locked=False,
            ),
        )
        system_records.extend(
            GeneratedCodeSourceSystemRecord(
                modeled_entity_type=modeled_entity_type,
                modeled_entity_schema_name=context.modeled_entity_schema_name,
                modeled_entity_name=context.modeled_entity_name,
                artifact_name=artifact.artifact_name,
                source_system_code=system_code,
                generated_code_source_system_status="active",
                generated_code_source_system_is_locked=False,
            )
            for system_code in artifact.source_system_codes
        )

    staged_code = _reconcile_generated_code(code_records, contexts)
    staged_systems = _reconcile_generated_code_source_systems(system_records, contexts)
    changes: list[StageModelChange] = []
    if staged_code:
        changes.append(
            StageModelChange(
                dataset="generated_code",
                records=[record.model_dump(mode="json") for record in staged_code],
            )
        )
    if staged_systems:
        changes.append(
            StageModelChange(
                dataset="generated_code_source_system",
                records=[record.model_dump(mode="json") for record in staged_systems],
            )
        )
    return tuple(changes)


def _reconcile_generated_code(
    candidates: list[GeneratedCodeRecord],
    contexts: tuple[CodeGenerationArtifactContext, ...],
) -> tuple[GeneratedCodeRecord, ...]:
    applied = {
        _artifact_key(record): (record, context)
        for context in contexts
        for record in context.applied_generated_code
    }
    candidate_by_key = {_artifact_key(record): record for record in candidates}
    if len(candidate_by_key) != len(candidates) or len(applied) != sum(
        len(context.applied_generated_code) for context in contexts
    ):
        raise InvalidRequestError("Generated Code artifact names are ambiguous.")

    changed: list[GeneratedCodeRecord] = []
    for key, record in candidate_by_key.items():
        prior = applied.get(key)
        if prior is None:
            changed.append(record)
            continue
        prior_record, context = prior
        if prior_record.generated_code_is_locked:
            continue
        current_names = {name.strip().casefold() for name in context.current_artifact_names}
        if record != prior_record or record.artifact_name.strip().casefold() not in current_names:
            changed.append(record)
    for key, (record, _) in applied.items():
        if (
            key not in candidate_by_key
            and record.generated_code_status == "active"
            and not record.generated_code_is_locked
        ):
            changed.append(record.model_copy(update={"generated_code_status": "inactive"}))
    return tuple(changed)


def _reconcile_generated_code_source_systems(
    candidates: list[GeneratedCodeSourceSystemRecord],
    contexts: tuple[CodeGenerationArtifactContext, ...],
) -> tuple[GeneratedCodeSourceSystemRecord, ...]:
    applied_records = [
        record for context in contexts for record in context.applied_generated_code_source_systems
    ]
    applied = {_source_system_key(record): record for record in applied_records}
    candidate_by_key = {_source_system_key(record): record for record in candidates}
    if len(candidate_by_key) != len(candidates) or len(applied) != len(applied_records):
        raise InvalidRequestError("Generated Code source System assignments are ambiguous.")

    changed = [
        record
        for key, record in candidate_by_key.items()
        if record != applied.get(key)
        and (key not in applied or not applied[key].generated_code_source_system_is_locked)
    ]
    changed.extend(
        record.model_copy(update={"generated_code_source_system_status": "inactive"})
        for key, record in applied.items()
        if key not in candidate_by_key
        and record.generated_code_source_system_status == "active"
        and not record.generated_code_source_system_is_locked
    )
    return tuple(changed)


def _artifact_key(record: GeneratedCodeRecord) -> tuple[str, ...]:
    return (
        record.modeled_entity_type,
        record.modeled_entity_schema_name.strip().casefold(),
        record.modeled_entity_name.strip().casefold(),
        record.artifact_name.strip().casefold(),
    )


def _source_system_key(
    record: GeneratedCodeSourceSystemRecord,
) -> tuple[str, ...]:
    return (
        record.modeled_entity_type,
        record.modeled_entity_schema_name.strip().casefold(),
        record.modeled_entity_name.strip().casefold(),
        record.artifact_name.strip().casefold(),
        record.source_system_code.strip().casefold(),
    )


def _guide_content(context: CodeGenerationExecutionContext) -> str:
    value = context.agent_context
    if not isinstance(value, dict):
        raise InvalidRequestError("The Code Generation guide context is unavailable.")
    targets = value.get("targets")
    if not isinstance(targets, list) or not targets:
        raise InvalidRequestError("The Code Generation guide context is unavailable.")

    contents: list[str] = []
    for target in targets:
        if not isinstance(target, dict):
            raise InvalidRequestError("The Code Generation guide context is unavailable.")
        source_context = target.get("context")
        if not isinstance(source_context, dict):
            raise InvalidRequestError("The Code Generation guide context is unavailable.")
        guide = source_context.get("guide")
        if not isinstance(guide, dict):
            raise InvalidRequestError("The Code Generation guide context is unavailable.")
        content = guide.get("content")
        if not isinstance(content, str) or not content.strip() or "\x00" in content:
            raise InvalidRequestError("The Code Generation guide context is unavailable.")
        contents.append(content)
    if len(set(contents)) != 1:
        raise InvalidRequestError("The Code Generation guide context is inconsistent.")
    return contents[0]


def _target_agent_context(
    context: CodeGenerationExecutionContext,
    *,
    target_ref: str,
) -> JsonValue:
    value = context.agent_context
    if not isinstance(value, dict):
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    targets = value.get("targets")
    if not isinstance(targets, list) or len(targets) != len(context.targets):
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    matches = [
        target
        for target in targets
        if isinstance(target, dict) and target.get("target_ref") == target_ref
    ]
    if len(matches) != 1:
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    match = matches[0]
    source_context = match.get("context")
    if not isinstance(source_context, dict):
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    guide = source_context.get("guide")
    if not isinstance(guide, dict):
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    content = guide.get("content")
    if not isinstance(content, str) or not content.strip() or "\x00" in content:
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    content_bytes = content.encode("utf-8")
    delivered_guide = {name: item for name, item in guide.items() if name != "content"}
    delivered_guide.update(
        {
            "content_delivery": "sql_generation_guide_variable",
            "content_sha256": sha256(content_bytes).hexdigest(),
            "content_byte_count": len(content_bytes),
        }
    )
    return cast(
        JsonValue,
        {
            "targets": [
                {
                    **match,
                    "context": {**source_context, "guide": delivered_guide},
                }
            ]
        },
    )


def _target_context_manifest(target_context: JsonValue) -> JsonValue:
    encoded = _canonical_json(target_context)
    target_ref: JsonValue = None
    if isinstance(target_context, dict):
        targets = target_context.get("targets")
        if isinstance(targets, list) and len(targets) == 1 and isinstance(targets[0], dict):
            target_ref = targets[0].get("target_ref")
    if not isinstance(target_ref, str):
        raise InvalidRequestError("The Code Generation target context is unavailable.")
    return cast(
        JsonValue,
        {
            "target_ref": target_ref,
            "target_context_delivery": "workflow_variables_and_optional_readers",
            "target_context_sha256": sha256(encoded).hexdigest(),
            "target_context_byte_count": len(encoded),
        },
    )


def _canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _safe_execution_error(
    error: Exception,
    *,
    finalization_attempted: bool,
) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    if finalization_attempted:
        return CodeGenerationFinalizationFailedError()
    return CodeGenerationExecutionFailedError()
